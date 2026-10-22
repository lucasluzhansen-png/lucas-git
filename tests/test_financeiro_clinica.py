import json
from datetime import datetime

from hansen.canal import CanalSimulado, Notificador
from hansen.clinus import carregar_backup
from hansen.ledger import LedgerManager
from hansen.maestro import Maestro
from hansen.rotina_financeira import rodar_clinica
from hansen.yaml_parser import carregar_todos

AGORA = datetime(2026, 3, 10, 10, 0)

CONTAS = [
    {"id": "c1", "descricao": "Aluguel", "valor": "3.500,00", "vencimento": "2026-03-05", "status": "pendente", "categoria": "Fixo"},   # vencida
    {"id": "c2", "descricao": "Internet", "valor": 200, "vencimento": "2026-03-11", "status": "pendente"},                            # vence amanhã
    {"id": "c3", "descricao": "Luz", "valor": 300, "vencimento": "2026-03-30", "status": "pendente"},                                 # longe
    {"id": "c4", "descricao": "Água", "valor": 100, "vencimento": "2026-03-01", "status": "pago", "pagoEm": "2026-03-01"},          # paga
]
COMPRAS = [
    {"id": "k1", "produto": "Luva", "qtd": 5, "urgencia": "critico", "status": "pendente"},
    {"id": "k2", "produto": "Resina", "qtd": 2, "urgencia": "mensal", "status": "aprovado"},
    {"id": "k3", "produto": "Gesso", "qtd": 1, "urgencia": "mensal", "status": "adiado", "adiadoAte": "2026-03-09"},   # volta a pendente
    {"id": "k4", "produto": "Seringa", "qtd": 1, "urgencia": "mensal", "status": "adiado", "adiadoAte": "2026-04-01"},  # ainda adiado
    {"id": "k5", "produto": "Babador", "qtd": 1, "status": "recebido"},
]
EQUIP = {"equipamentos": [
    {"id": "e1", "nome": "Autoclave", "ativo": True, "proximaEm": "2026-03-20"},   # em 10 dias: dentro dos 15
    {"id": "e2", "nome": "Compressor", "ativo": True, "proximaEm": "2026-06-01"},  # longe
    {"id": "e3", "nome": "Fotopolimerizador", "ativo": False, "proximaEm": "2026-03-01"},  # inativo
]}
PACS = [{"id": "p1", "nome": "Ana", "orcamento": {"pagamentos": [
    {"d": "09/03/2026", "valor": "R$ 300,00", "forma": "PIX"},                       # dia 09 recebido, sem fechamento
    {"d": "08/03/2026", "valor": "R$ 100,00", "forma": "PIX"},                       # dia 08 recebido e fechado
    {"d": "07/03/2026", "valor": "R$ 50,00", "forma": "PIX", "estornadoEm": "x"},   # estornado: não conta
]}}]
CAIXA = [{"data": "2026-03-08", "quem": "Rec"}]


def _setup(tmp_path):
    f = tmp_path / "b.json"
    f.write_text(json.dumps({"versao": "hrpg_v1", "pacientes": PACS, "stores": {
        "clinus_contas_pagar": json.dumps(CONTAS), "clinus_compras": json.dumps(COMPRAS),
        "clinus_equipamentos": json.dumps(EQUIP), "clinus_caixa": json.dumps(CAIXA)}}), encoding="utf-8")
    led = LedgerManager(tmp_path / "l")
    m = Maestro(led, estado=tmp_path / "est", notificador=Notificador(CanalSimulado(), led, carregar_todos()["R-02"]))
    return m, carregar_backup(f)


def _titulos(m):
    return {t.id: (t.titulo, t.responsavel, t.prioridade) for t in m.tarefas.tarefas.values()}


def test_rotina_da_clinica_gera_as_sugestoes_certas(tmp_path):
    m, c = _setup(tmp_path)
    itens = rodar_clinica(m, c, AGORA)
    por_tipo = {}
    for i in itens:
        por_tipo.setdefault(i.tipo, []).append(i.nome)
    assert sorted(por_tipo["conta"]) == ["Aluguel", "Internet"]            # Luz longe, Água paga
    assert sorted(por_tipo["compra"]) == ["Gesso", "Luva", "Resina"]        # Seringa adiada, Babador recebido
    assert por_tipo["equipamento"] == ["Autoclave"]
    assert por_tipo["caixa"] == ["09/03"]                                    # 08 fechado; 07 só estorno


def test_responsaveis_e_prioridades(tmp_path):
    m, c = _setup(tmp_path)
    rodar_clinica(m, c, AGORA)
    t = list(_titulos(m).values())
    por = lambda prefixo: next(x for x in t if x[0].startswith(prefixo))
    assert por("Conta a pagar VENCIDA")[1:] == ("recepcao", "amarela")
    assert por("Conta a pagar a vencer")[1:] == ("recepcao", "verde")
    assert por("Compra CRÍTICA")[1:] == ("lucas", "amarela")                 # o dono decide
    assert por("Compra aprovada")[1] == "recepcao"
    assert por("Fechar o caixa")[1] == "recepcao"
    assert "R$ 3.500,00" in por("Conta a pagar VENCIDA")[0]


def test_nao_repete_a_mesma_sugestao_e_ledger_integro(tmp_path):
    m, c = _setup(tmp_path)
    rodar_clinica(m, c, AGORA)
    n = len(m.tarefas.tarefas)
    assert rodar_clinica(m, c, AGORA) == [] and len(m.tarefas.tarefas) == n
    assert m.ledger.verificar()


def test_conta_que_vence_depois_de_avisada_gera_novo_aviso_de_vencida(tmp_path):
    m, c = _setup(tmp_path)
    rodar_clinica(m, c, AGORA)
    itens = rodar_clinica(m, c, datetime(2026, 3, 13, 10, 0))  # Internet venceu dia 11
    assert any(i.tipo == "conta" and i.nome == "Internet" and "venceu" in i.resultado for i in itens)


def test_backup_sem_esses_cadastros_nao_quebra(tmp_path):
    f = tmp_path / "b.json"
    f.write_text(json.dumps({"versao": "hrpg_v1", "pacientes": [], "stores": {}}), encoding="utf-8")
    led = LedgerManager(tmp_path / "l")
    m = Maestro(led, estado=tmp_path / "e", notificador=Notificador(CanalSimulado(), led, carregar_todos()["R-02"]))
    assert rodar_clinica(m, carregar_backup(f), AGORA) == []


def test_painel_financeiro_mostra_tarefas_internas(tmp_path):
    from hansen.painel_comercial import AVISO_FINANCEIRO, TIPOS_FINANCEIRO, cartoes_internos, gerar
    m, c = _setup(tmp_path)
    rodar_clinica(m, c, AGORA)
    internos = cartoes_internos(m)
    assert {x["rotulo"] for x in internos} == {"Conta a pagar", "Compra", "Equipamento", "Caixa"}
    html = gerar(m, c, tmp_path / "p.html", AGORA, "financeiro", TIPOS_FINANCEIRO, "Painel financeiro", AVISO_FINANCEIRO, internos=True).read_text(encoding="utf-8")
    assert "Autoclave" in html and "Aluguel" in html and "URGENTE" in html and "Nenhuma sugestão aberta" not in html
