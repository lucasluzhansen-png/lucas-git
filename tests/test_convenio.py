import json
from datetime import datetime

from hansen.canal import CanalSimulado, Notificador
from hansen.clinus import carregar_backup, guia_atrasada, guia_calc, op_nome
from hansen.ledger import LedgerManager
from hansen.maestro import Maestro
from hansen.rotina_financeira import rodar_clinica
from hansen.yaml_parser import carregar_todos

AGORA = datetime(2026, 3, 10, 10, 0)
HOJE = AGORA.date()

GUIAS = [
    {"id": "g1", "pacId": "p1", "convenio": "Bradesco (Odontoprev)", "numero": "111", "valor": "1.000,00", "status": "criada", "criadoEm": "2026-03-01T10:00:00Z"},   # criada há 9 dias
    {"id": "g2", "pacId": "p1", "convenio": "Petrobras (CODEBA)", "numero": "222", "valor": "500", "status": "enviada", "envio": "2026-03-01"},                     # enviada há 9 dias
    {"id": "g3", "pacId": "p2", "convenio": "bradesco", "numero": "333", "valor": "800", "status": "glosada", "glosado": "200", "motivoGlosa": "sem cobertura", "recurso": "", "envio": "2026-02-10"},
    {"id": "g4", "pacId": "p2", "convenio": "bradesco", "numero": "444", "valor": "600", "status": "faturada", "envio": "2026-02-01", "previsao": "2026-03-05"},   # repasse atrasado
    {"id": "g5", "pacId": "p2", "convenio": "bradesco", "numero": "555", "valor": "300", "status": "paga", "envio": "2026-02-01", "previsao": "2026-03-01", "repasse": "2026-03-02"},
    {"id": "g6", "pacId": "p1", "convenio": "Petrobras", "numero": "666", "valor": "700", "status": "autorizada", "envio": "2026-03-08"},                          # legado = aprovada; enviada há 2 dias: ok
]
PACS = [
    {"id": "p1", "nome": "Ana", "convenio": "sim", "convQual": "Petrobras (CODEBA)", "orcamento": {"aprovadoEm": "2026-03-02", "convItens": {"x": {"valor": "100", "qtd": 2, "convenio": "Petrobras"}}}},
    {"id": "p2", "nome": "Bia", "convenio": "sim", "convQual": "Bradesco", "orcamento": {"aprovadoEm": "2026-03-01", "convItens": {"x": {"valor": "900", "qtd": 1, "convenio": "Bradesco"}}}},
    {"id": "p3", "nome": "Caio", "convenio": "sim", "convQual": "Bradesco", "orcamento": {"aprovadoEm": "2026-03-01", "convItens": {"x": {"valor": "400", "qtd": 1, "convenio": "Bradesco"}}}},                       # sem guia
    {"id": "p4", "nome": "Davi", "convenio": "sim", "convQual": "Bradesco", "encerramento": {"emISO": "2026-03-05"}, "orcamento": {"aprovadoEm": "2026-03-01", "convItens": {"x": {"valor": "400", "qtd": 1}}}},  # encerrado
    {"id": "p5", "nome": "Eva", "convenio": "sim", "convQual": "Bradesco", "orcamento": {"aprovadoEm": "2026-03-09", "convItens": {"x": {"valor": "400", "qtd": 1}}}},                                              # aprovado ontem
]


def _setup(tmp_path, agora=AGORA):
    f = tmp_path / "b.json"
    f.write_text(json.dumps({"versao": "hrpg_v1", "pacientes": PACS, "stores": {"clinus_guias": json.dumps(GUIAS)}}), encoding="utf-8")
    led = LedgerManager(tmp_path / "l")
    m = Maestro(led, estado=tmp_path / "est", notificador=Notificador(CanalSimulado(), led, carregar_todos()["R-02"]))
    return m, carregar_backup(f)


def test_logica_de_guia_espelha_o_clinus():
    assert op_nome("Bradesco (Odontoprev)") == "Bradesco/Odontoprev" and op_nome("") == "Convênio sem nome" and op_nome("unimed") == "Unimed"
    g = {"valor": "800", "glosado": "200", "status": "glosada", "recurso": ""}
    assert guia_calc(g)["perdido"] == 200 and guia_calc(g)["esperado"] == 600
    assert guia_calc({**g, "recurso": "deferido"})["perdido"] == 0                       # recurso deferido: valor volta
    assert guia_atrasada(GUIAS[3], HOJE) and not guia_atrasada(GUIAS[4], HOJE) and not guia_atrasada(GUIAS[0], HOJE)


def test_sugestoes_de_convenio(tmp_path):
    m, c = _setup(tmp_path)
    rodar_clinica(m, c, AGORA)
    titulos = [t.titulo.split(" [")[0] for t in m.tarefas.tarefas.values() if t.titulo.startswith("Convênio")]
    assert sorted(titulos) == sorted([
        "Convênio: criar a guia do tratamento aprovado",      # Caio (Davi encerrado, Eva aprovou ontem)
        "Convênio: guia criada e ainda não enviada",          # g1
        "Convênio: autorização pendente",                     # g2 (g6 enviada há 2 dias não)
        "Convênio: glosa sem recurso",                        # g3
        "Convênio: repasse ATRASADO",                         # g4
        "Convênio: conferir repasses da operadora (fechamento do mês)",  # só Bradesco: g4 é de fevereiro; g2 (Petrobras) é do mês atual; g3 glosada sem recurso não conta
    ])
    assert {t.responsavel for t in m.tarefas.tarefas.values() if t.titulo.startswith("Convênio")} == {"recepcao"}


def test_prioridades_repasse_e_glosa_amarelas(tmp_path):
    m, c = _setup(tmp_path)
    rodar_clinica(m, c, AGORA)
    pr = {t.titulo.split(" [")[0]: t.prioridade for t in m.tarefas.tarefas.values() if t.titulo.startswith("Convênio")}
    assert pr["Convênio: repasse ATRASADO"] == "amarela" and pr["Convênio: glosa sem recurso"] == "amarela"
    assert pr["Convênio: guia criada e ainda não enviada"] == "verde"


def test_fechamento_do_mes_so_a_partir_do_dia_5(tmp_path):
    m, c = _setup(tmp_path)
    rodar_clinica(m, c, datetime(2026, 3, 4, 10, 0))
    assert not any("fechamento do mês" in t.titulo for t in m.tarefas.tarefas.values())


def test_nao_repete_e_ledger_sem_dados_de_paciente(tmp_path):
    m, c = _setup(tmp_path)
    rodar_clinica(m, c, AGORA)
    n = len(m.tarefas.tarefas)
    assert rodar_clinica(m, c, AGORA) == [] and len(m.tarefas.tarefas) == n
    txt = "".join(p.read_text(encoding="utf-8") for p in (tmp_path / "l").glob("*.json"))
    assert not any(x in txt for x in ("Ana", "Bia", "Caio", "Davi", "Eva"))
    assert m.ledger.verificar()


def test_backup_sem_guias_nao_quebra(tmp_path):
    f = tmp_path / "b.json"
    f.write_text(json.dumps({"versao": "hrpg_v1", "pacientes": [], "stores": {}}), encoding="utf-8")
    led = LedgerManager(tmp_path / "l")
    m = Maestro(led, estado=tmp_path / "e", notificador=Notificador(CanalSimulado(), led, carregar_todos()["R-02"]))
    assert rodar_clinica(m, carregar_backup(f), AGORA) == []
