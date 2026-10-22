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


def _extra(c, **campos):
    base = {"nome": "X", "tel": "71911110000", "nascimento": "", "decisao": "", "ultima_acao": "2026-03-01T00:00:00Z",
            "ativo": True, "consentimento": False, "etapa": 3, "zona": "", "orc_aberto": False, "historico": False}
    c.por_id[campos["id"]] = {**base, **campos}


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
        _extra(c, id=f"x{i}", decisao="pensar", orc_aberto=True, ultima_acao="2026-01-01T00:00:00Z")
    itens = rodar(m, c, AGORA)
    assert sum(1 for i in itens if "tarefa #" in i.resultado and i.tipo in ("orcamento_aberto", "paciente_parado")) == 5
    assert any("limite diário" in i.resultado for i in itens)


def test_fora_do_horario_nao_envia_e_tenta_depois(tmp_path):
    m, c, canal = _setup(tmp_path)
    rodar(m, c, datetime(2026, 3, 10, 21, 0))  # noite: fora da janela
    assert canal.enviadas == []
    rodar(m, c, AGORA)  # na janela comercial do mesmo dia civil
    assert any("feliz aniversário" in t for _, t in canal.enviadas)


def test_orcamento_em_aberto_pelas_regras_do_clinus(tmp_path):
    m, c, _ = _setup(tmp_path)
    c.por_id.clear()
    _extra(c, id="z", orc_aberto=True)  # zona 'orcpendente'/etapa 7 já resolvidas em orc_aberto
    itens = rodar(m, c, AGORA)
    assert [i.tipo for i in itens] == ["orcamento_aberto"]


def test_base_historica_importada_nao_e_alvo(tmp_path):
    m, c, _ = _setup(tmp_path)
    c.por_id.clear()
    for i in range(50):
        _extra(c, id=f"h{i}", historico=True, ultima_acao="2024-01-01T00:00:00Z")
    assert rodar(m, c, AGORA) == []


def test_manutencao_vencida_so_etapa_10_apos_180_dias(tmp_path):
    m, c, _ = _setup(tmp_path)
    c.por_id.clear()
    _extra(c, id="a", etapa=10, ultima_acao="2025-08-01T00:00:00Z")  # >180 dias
    _extra(c, id="b", etapa=10, ultima_acao="2026-02-01T00:00:00Z")  # recente
    _extra(c, id="c", etapa=11, ultima_acao="2024-01-01T00:00:00Z")  # concluído e fora (não é parado)
    itens = rodar(m, c, AGORA)
    assert [(i.tipo) for i in itens] == ["manutencao_vencida"]
    assert any("manutenção" in t.titulo for t in m.tarefas.tarefas.values())


def test_perdidos_nao_sao_reativados(tmp_path):
    m, c, _ = _setup(tmp_path)
    c.por_id.clear()
    _extra(c, id="p", zona="perdidos", ultima_acao="2025-01-01T00:00:00Z")
    assert rodar(m, c, AGORA) == []


def test_painel_comercial_cartoes_com_nome_texto_e_link(tmp_path):
    from hansen.painel_comercial import cartoes, gerar
    m, c, _ = _setup(tmp_path)
    rodar(m, c, AGORA)
    cs = {x["nome"]: x for x in cartoes(m, c)}
    assert {"Caio", "Davi", "Bia"} <= set(cs)  # orçamento, parado, aniversário sem consentimento
    assert "analisar o plano" in cs["Caio"]["texto"] and "R$" not in cs["Caio"]["texto"]
    assert cs["Caio"]["link"].startswith("https://wa.me/5571900000003?text=")
    html = gerar(m, c, tmp_path / "p.html", AGORA).read_text(encoding="utf-8")
    assert "Revise o texto" in html and "Caio" in html


def test_painel_some_quando_tarefa_e_fechada(tmp_path):
    from hansen.painel_comercial import cartoes
    m, c, _ = _setup(tmp_path)
    rodar(m, c, AGORA)
    t = next(t for t in m.tarefas.tarefas.values() if "orçamento" in t.titulo)
    assert m.tarefas.fechar(t.id, "lucas", "contato feito")
    assert "Caio" not in {x["nome"] for x in cartoes(m, c)}


def test_cli_de_tarefas_lista_e_fecha(tmp_path):
    from hansen.tarefas_cli import main
    m, c, _ = _setup(tmp_path)
    rodar(m, c, AGORA)
    base = tmp_path  # _setup usa tmp_path/est e tmp_path/l; a CLI espera ledger/ e estado/
    (base / "estado").mkdir(exist_ok=True)
    (base / "estado" / "tarefas.json").write_text((tmp_path / "est" / "tarefas.json").read_text(encoding="utf-8"), encoding="utf-8")
    (base / "ledger").mkdir(exist_ok=True)
    assert main([str(base), "listar"]) == 0
    assert main([str(base), "fechar", "1"]) == 1  # sem evidência
    assert main([str(base), "fechar", "1", "contato feito"]) == 0
