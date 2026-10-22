import json
from datetime import datetime

from hansen.canal import CanalSimulado, Notificador
from hansen.clinus import carregar_backup
from hansen.ledger import LedgerManager
from hansen.maestro import Maestro
from hansen.rotina_comercial import rodar as rodar_com
from hansen.rotina_financeira import rodar as rodar_parc, rodar_clinica
from hansen.yaml_parser import carregar_todos

AGORA = datetime(2026, 3, 10, 10, 0)


def _m(tmp_path):
    led = LedgerManager(tmp_path / "l")
    return Maestro(led, estado=tmp_path / "est", notificador=Notificador(CanalSimulado(), led, carregar_todos()["R-02"]))


def _clinus(tmp_path, nome, pacientes, stores):
    f = tmp_path / f"{nome}.json"
    f.write_text(json.dumps({"versao": "hrpg_v1", "pacientes": pacientes, "stores": {k: json.dumps(v) for k, v in stores.items()}}), encoding="utf-8")
    return carregar_backup(f)


def _abertas(m):
    return sorted(t.titulo.split(" [")[0] for t in m.tarefas.tarefas.values() if t.estado in ("aberta", "escalada"))


def test_conta_paga_no_clinus_fecha_a_tarefa(tmp_path):
    m = _m(tmp_path)
    conta = {"id": "c1", "descricao": "Aluguel", "valor": 3500, "vencimento": "2026-03-05", "status": "pendente"}
    rodar_clinica(m, _clinus(tmp_path, "a", [], {"clinus_contas_pagar": [conta]}), AGORA)
    assert _abertas(m) == ["Conta a pagar VENCIDA"]
    rodar_clinica(m, _clinus(tmp_path, "b", [], {"clinus_contas_pagar": [{**conta, "status": "pago", "pagoEm": "2026-03-10"}]}), AGORA)
    assert _abertas(m) == [] and m.resolvidas_auto == 1
    t = m.tarefas.tarefas[1]
    assert t.estado == "fechada" and "Resolvida no Clinus" in t.evidencia


def test_caixa_fechado_fecha_a_tarefa(tmp_path):
    m = _m(tmp_path)
    pac = [{"id": "p", "nome": "X", "orcamento": {"pagamentos": [{"d": "09/03/2026", "valor": "R$ 100,00"}]}}]
    rodar_clinica(m, _clinus(tmp_path, "a", pac, {}), AGORA)
    assert _abertas(m) == ["Fechar o caixa do dia"]
    rodar_clinica(m, _clinus(tmp_path, "b", pac, {"clinus_caixa": [{"data": "2026-03-09", "quem": "Rec"}]}), AGORA)
    assert _abertas(m) == []


def test_guia_que_avancou_fecha_a_tarefa_e_volta_se_o_problema_voltar(tmp_path):
    m = _m(tmp_path)
    g = {"id": "g1", "pacId": "p", "convenio": "Petrobras", "valor": "500", "status": "enviada", "envio": "2026-03-01"}
    rodar_clinica(m, _clinus(tmp_path, "a", [], {"clinus_guias": [g]}), AGORA)
    assert _abertas(m) == ["Convênio: autorização pendente"]
    rodar_clinica(m, _clinus(tmp_path, "b", [], {"clinus_guias": [{**g, "status": "aprovada"}]}), AGORA)  # convênio aprovou
    assert _abertas(m) == []
    rodar_clinica(m, _clinus(tmp_path, "c", [], {"clinus_guias": [g]}), AGORA)  # voltou a ficar pendente: cobra de novo
    assert _abertas(m) == ["Convênio: autorização pendente"]


def test_parcela_paga_fecha_a_cobranca(tmp_path):
    m = _m(tmp_path)
    pac = {"id": "p", "nome": "Ana", "tel": "71900000001", "orcamento": {"parcelas": [{"valor": 100, "venc": "2026-02-20"}], "pagamentos": []}}
    rodar_parc(m, _clinus(tmp_path, "a", [pac], {}), AGORA)
    assert _abertas(m) == ["Cobrar parcela em atraso (sugestão)"]
    pago = {**pac, "orcamento": {**pac["orcamento"], "pagamentos": [{"valor": "100"}]}}
    rodar_parc(m, _clinus(tmp_path, "b", [pago], {}), AGORA)
    assert _abertas(m) == []


def test_comercial_paciente_atendido_fecha_a_sugestao(tmp_path):
    m = _m(tmp_path)
    pac = {"id": "p", "nome": "Bia", "tel": "71900000002", "decisao": "pensar", "ultimaAcao": "2026-02-20T00:00:00Z"}
    rodar_com(m, _clinus(tmp_path, "a", [pac], {}), AGORA)
    assert _abertas(m) == ["Retomar contato: orçamento em aberto ('vai pensar')"]
    atendido = {**pac, "decisao": "fechou", "ultimaAcao": "2026-03-09T00:00:00Z"}  # alguém falou com a paciente
    rodar_com(m, _clinus(tmp_path, "b", [atendido], {}), AGORA)
    assert _abertas(m) == []


def test_tarefa_aberta_pela_equipe_nao_e_fechada_por_engano_e_outras_rotinas_nao_interferem(tmp_path):
    m = _m(tmp_path)
    conta = {"id": "c1", "descricao": "Luz", "valor": 100, "vencimento": "2026-03-05", "status": "pendente"}
    pac = {"id": "p", "nome": "Bia", "tel": "71900000002", "decisao": "pensar", "ultimaAcao": "2026-02-20T00:00:00Z"}
    c = _clinus(tmp_path, "a", [pac], {"clinus_contas_pagar": [conta]})
    rodar_com(m, c, AGORA)
    rodar_clinica(m, c, AGORA)
    rodar_parc(m, c, AGORA)  # rotina de parcelas roda e NÃO pode fechar tarefas de comercial/clínica
    assert len(_abertas(m)) == 2 and m.resolvidas_auto == 0


def test_fechamento_automatico_fica_no_ledger_como_agente(tmp_path):
    m = _m(tmp_path)
    conta = {"id": "c1", "descricao": "Luz", "valor": 100, "vencimento": "2026-03-05", "status": "pendente"}
    rodar_clinica(m, _clinus(tmp_path, "a", [], {"clinus_contas_pagar": [conta]}), AGORA)
    rodar_clinica(m, _clinus(tmp_path, "b", [], {"clinus_contas_pagar": [{**conta, "status": "pago"}]}), AGORA)
    evs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((tmp_path / "l").glob("*.json"))]
    auto = [e for e in evs if e["acao"] == "resolver_automatico"]
    assert len(auto) == 1 and auto[0]["actor"]["type"] == "agente_ia" and m.ledger.verificar()
