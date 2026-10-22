import json
from datetime import datetime

from hansen.canal import CanalSimulado, Notificador
from hansen.clinus import carregar_backup
from hansen.ledger import LedgerManager
from hansen.lembretes import formatar, rodar
from hansen.maestro import Maestro
from hansen.yaml_parser import carregar_todos

AG = [
    {"id": "a", "pacId": "p1", "data": "2026-01-07", "hora": "09:00", "status": "agendado"},
    {"id": "b", "pacId": "p2", "data": "2026-01-07", "hora": "10:00", "status": "confirmado"},
    {"id": "c", "pacId": "p3", "data": "2026-01-06", "hora": "11:00", "status": "agendado"},  # em 1h30: risco
    {"id": "d", "pacId": "p4", "data": "2026-01-06", "hora": "15:00", "status": "agendado"},  # sem telefone
    {"id": "e", "pacId": "p5", "data": "2026-01-06", "hora": "11:30", "status": "agendado"},  # outro risco
]
PAC = [{"id": f"p{i}", "nome": n, "tel": t} for i, (n, t) in enumerate(
    [("Ana", "71900000001"), ("Bia", "71900000002"), ("Caio", "71900000003"), ("Davi", ""), ("Eva", "71900000005")], 1)]
AGORA = datetime(2026, 1, 6, 9, 30)  # terça, horário comercial


def _setup(tmp_path):
    f = tmp_path / "b.json"
    f.write_text(json.dumps({"versao": "hrpg_v1", "pacientes": PAC, "stores": {"clinus_agenda_v2": json.dumps(AG)}}), encoding="utf-8")
    led = LedgerManager(tmp_path / "l")
    canal = CanalSimulado()
    m = Maestro(led, estado=tmp_path / "est", notificador=Notificador(canal, led, carregar_todos()["R-02"]))
    return m, carregar_backup(f), canal


def test_plano_do_dia(tmp_path):
    m, clinus, canal = _setup(tmp_path)
    plano = {i.consulta.id: i for i in rodar(m, clinus, AGORA)}
    assert plano["a"].decisao.acao == "enviar_lembrete"
    assert plano["b"].decisao.acao == "confirmar"
    assert plano["c"].decisao.acao == "marcar_no_show"
    assert plano["d"].decisao is None and "sem telefone" in plano["d"].nota
    assert len(canal.enviadas) == 1 and "Senhor(a) Ana" in canal.enviadas[0][1]


def test_nao_reenvia_lembrete(tmp_path):
    m, clinus, canal = _setup(tmp_path)
    rodar(m, clinus, AGORA)
    plano = {i.consulta.id: i for i in rodar(m, clinus, datetime(2026, 1, 6, 9, 45))}
    assert plano["a"].decisao is None and "já enviado" in plano["a"].nota
    assert len(canal.enviadas) == 1


def test_tarefas_de_no_show_sao_uma_por_consulta_sem_nome(tmp_path):
    m, clinus, _ = _setup(tmp_path)
    rodar(m, clinus, AGORA)
    titulos = [t.titulo for t in m.tarefas.tarefas.values()]
    assert len(titulos) == 2 and len(set(titulos)) == 2  # c e e, distintas
    assert not any(n in t for t in titulos for n in ("Caio", "Eva"))
    ledger_txt = "".join(p.read_text(encoding="utf-8") for p in (tmp_path / "l").glob("*.json"))
    assert not any(n in ledger_txt for n in ("Ana", "Caio", "7190000"))  # sem dados de paciente no ledger
    assert m.ledger.verificar()


def test_lista_para_recepcao_mostra_nomes(tmp_path):
    m, clinus, _ = _setup(tmp_path)
    txt = formatar(rodar(m, clinus, AGORA))
    assert "Caio" in txt and "RISCO DE NO-SHOW" in txt
