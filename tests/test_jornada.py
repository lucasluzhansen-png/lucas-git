import json
from datetime import datetime

from hansen.canal import CanalSimulado, Notificador
from hansen.clinus import carregar_backup
from hansen.ledger import LedgerManager
from hansen.maestro import Maestro
from hansen.painel_comercial import TIPOS_FINANCEIRO, cartoes
from hansen.rotina_jornada import rodar
from hansen.yaml_parser import carregar_todos

AGORA = datetime(2026, 3, 20, 10, 0)


def _p(pid, nome, aprov=None, alta=None):
    p = {"id": pid, "nome": nome, "tel": "11999990000", "orcamento": {"aprovadoEm": aprov} if aprov else {}}
    if alta:
        p["encerramento"] = {"emISO": alta}
    return p


PACS = [_p("a", "Ana", "2026-03-01"),                  # aprovada há 19 dias, sem consulta: iniciar
        _p("b", "Bia", "2026-02-01"),                  # em andamento, última consulta há 40 dias: parado
        _p("c", "Caio", "2026-02-01"),                 # em andamento, com consulta futura: ok
        _p("d", "Davi", "2026-01-01", "2026-03-01"),   # alta há 19 dias sem retorno
        _p("e", "Eva", "2026-03-18"),                  # aprovada há 2 dias: ainda cedo
        _p("f", "Fabio", "2025-12-01", "2026-03-15")]  # alta há 5 dias: cedo
AGENDA = [{"pacId": "b", "data": "2026-02-08", "status": "concluido"}, {"pacId": "c", "data": "2026-03-25", "status": "agendado"}]


def _setup(tmp_path, agenda=AGENDA):
    f = tmp_path / "b.json"
    f.write_text(json.dumps({"versao": "hrpg_v1", "pacientes": PACS, "stores": {"clinus_agenda_v2": json.dumps(agenda)}}), encoding="utf-8")
    led = LedgerManager(tmp_path / "l")
    m = Maestro(led, estado=tmp_path / "est", notificador=Notificador(CanalSimulado(), led, carregar_todos()["R-02"]))
    return m, carregar_backup(f)


def test_jornada(tmp_path):
    m, c = _setup(tmp_path)
    itens = rodar(m, c, AGORA)
    assert sorted((i.nome, i.tipo) for i in itens) == [("Ana", "iniciar_tratamento"), ("Bia", "tratamento_parado"), ("Davi", "retorno_alta")]
    assert all("Ana" not in t.titulo and "Bia" not in t.titulo for t in m.tarefas.tarefas.values())
    assert rodar(m, c, AGORA) == []  # sem repetir
    cs = cartoes(m, c, "financeiro", TIPOS_FINANCEIRO)
    assert {x["nome"] for x in cs} == {"Ana", "Bia", "Davi"}
    assert all("wa.me" in x["link"] and "Hansen" in x["texto"] for x in cs)


def test_fecha_sozinha_quando_agenda(tmp_path):
    m, c = _setup(tmp_path)
    rodar(m, c, AGORA)
    _, c2 = _setup(tmp_path, AGENDA + [{"pacId": "a", "data": "2026-03-27", "status": "agendado"}])
    rodar(m, c2, AGORA)
    abertas = [t for t in m.tarefas.tarefas.values() if t.estado in ("aberta", "escalada")]
    assert len(abertas) == 2
