import json
from datetime import datetime

from hansen.canal import CanalSimulado, Notificador
from hansen.clinus import carregar_backup
from hansen.ledger import LedgerManager
from hansen.maestro import Maestro
from hansen.rotina_comercial import rodar
from hansen.yaml_parser import carregar_todos

AGORA = datetime(2026, 3, 10, 10, 0)  # terça, horário comercial
PACS = [
    {"id": "p1", "nome": "Ana", "tel": "71900000001", "nascimento": "1990-03-10", "consentimentoComercial": True},
    {"id": "p2", "nome": "Bia", "tel": "71900000002", "nascimento": "1985-03-10"},  # aniversário, SEM consentimento
    {"id": "p3", "nome": "Caio", "tel": "71900000003", "decisao": "pensar", "ultimaAcao": "2026-03-01T10:00:00Z"},  # 9 dias
    {"id": "p4", "nome": "Davi", "tel": "71900000004", "ultimaAcao": "2025-10-01T10:00:00Z"},  # parado
    {"id": "p5", "nome": "Eva", "tel": "71900000005", "decisao": "pensar", "ultimaAcao": "2026-03-08T10:00:00Z"},  # 2 dias: cedo
    {"id": "p6", "nome": "Fábio", "tel": "", "nascimento": "1970-03-10"},
    {"id": "p7", "nome": "Gil", "tel": "71900000007", "ultimaAcao": "2025-10-01T10:00:00Z", "arquivado": True},
]
RET = [{"id": "r1", "pacId": "p5", "data": "2026-03-11", "status": "aberto"}, {"id": "r2", "pacId": "p5", "data": "2026-03-30"}]


def _setup(tmp_path):
    f = tmp_path / "b.json"
    f.write_text(json.dumps({"versao": "hrpg_v1", "pacientes": PACS,
                             "stores": {"clinus_retornos_v1": json.dumps(RET), "clinus_agenda_v2": "[]"}}), encoding="utf-8")
    led = LedgerManager(tmp_path / "l")
    canal = CanalSimulado()
    m = Maestro(led, estado=tmp_path / "est", notificador=Notificador(canal, led, carregar_todos()["R-02"]))
    return m, carregar_backup(f), canal


def test_aniversario_so_envia_com_consentimento(tmp_path):
    m, c, canal = _setup(tmp_path)
    rodar(m, c, AGORA)
    textos = [t for _, t in canal.enviadas]
    assert any("feliz aniversário" in t and "Ana" in t for t in textos)
    assert not any("Bia" in t for t in textos)  # sem consentimento: não envia
    assert any("sem consentimento" in t.titulo for t in m.tarefas.tarefas.values())


def test_retorno_agendado_envia_lembrete_formal(tmp_path):
    m, c, canal = _setup(tmp_path)
    rodar(m, c, AGORA)
    ret = [t for _, t in canal.enviadas if "retorno" in t]
    assert len(ret) == 1 and "11/03" in ret[0] and "Senhor(a) Eva" in ret[0]  # r2 está longe: não


def test_orcamento_e_parado_viram_sugestao_para_o_dr_lucas(tmp_path):
    m, c, _ = _setup(tmp_path)
    rodar(m, c, AGORA)
    ts = [t for t in m.tarefas.tarefas.values() if "orçamento" in t.titulo or "Reativar" in t.titulo]
    assert {t.responsavel for t in ts} == {"lucas"}
    assert len(ts) == 2  # Caio (orçamento) e Davi (parado); Eva cedo demais; Gil arquivado


def test_sem_valores_ou_descontos_nas_mensagens_e_tarefas(tmp_path):
    m, c, canal = _setup(tmp_path)
    rodar(m, c, AGORA)
    tudo = " ".join(t for _, t in canal.enviadas) + " ".join(t.titulo for t in m.tarefas.tarefas.values())
    assert "R$" not in tudo and "desconto" not in tudo.lower().replace("sem citar valores ou descontos", "")


def test_nao_repete_no_mesmo_dia_e_ledger_sem_dados(tmp_path):
    m, c, canal = _setup(tmp_path)
    rodar(m, c, AGORA)
    n_msgs, n_tarefas = len(canal.enviadas), len(m.tarefas.tarefas)
    rodar(m, c, AGORA)
    assert (len(canal.enviadas), len(m.tarefas.tarefas)) == (n_msgs, n_tarefas)
    txt = "".join(p.read_text(encoding="utf-8") for p in (tmp_path / "l").glob("*.json"))
    assert not any(x in txt for x in ("Ana", "Caio", "7190000", "1990-03-10"))
    assert m.ledger.verificar()


def test_limite_diario_de_sugestoes(tmp_path):
    m, c, _ = _setup(tmp_path)
    for i in range(10):
        c.por_id[f"x{i}"] = {"id": f"x{i}", "nome": f"N{i}", "tel": "1", "nascimento": "", "decisao": "pensar",
                             "ultima_acao": "2026-01-01T00:00:00Z", "ativo": True, "consentimento": False}
    itens = rodar(m, c, AGORA)
    assert sum(1 for i in itens if "tarefa #" in i.resultado and i.tipo in ("orcamento_aberto", "paciente_parado")) == 5
    assert any("limite diário" in i.resultado for i in itens)


def test_fora_do_horario_nao_envia_e_tenta_depois(tmp_path):
    m, c, canal = _setup(tmp_path)
    rodar(m, c, datetime(2026, 3, 10, 21, 0))  # noite: fora da janela
    assert canal.enviadas == []
    rodar(m, c, AGORA)  # na janela comercial do mesmo dia civil
    assert any("feliz aniversário" in t for _, t in canal.enviadas)
