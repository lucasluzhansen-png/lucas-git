import json
from datetime import date, datetime

from hansen.canal import CanalSimulado, Notificador
from hansen.clinus import _valor, carregar_backup, situacao_parcelas
from hansen.ledger import LedgerManager
from hansen.maestro import Maestro
from hansen.painel_comercial import TIPOS_FINANCEIRO, cartoes
from hansen.rotina_financeira import rodar
from hansen.yaml_parser import carregar_todos

HOJE = date(2026, 3, 10)
AGORA = datetime(2026, 3, 10, 10, 0)


def _parc(*venc, valor=100):
    return [{"valor": valor, "venc": v} for v in venc]


def test_valor_aceita_formato_brasileiro():
    assert _valor("1.500,00") == 1500.0 and _valor("R$ 300") == 300.0 and _valor(250) == 250.0 and _valor("") == 0.0


def test_pagamento_quita_na_ordem_e_calcula_atraso():
    sit = situacao_parcelas(_parc("2026-02-01", "2026-03-01", "2026-04-01"), 150, HOJE)
    assert [x["quitada"] for x in sit] == [True, False, False]
    assert sit[1]["restante"] == 50 and sit[1]["atraso"] == 9  # 01/03 → 10/03
    assert sit[2]["atraso"] == 0 and sit[2]["dias_ate_vencer"] == 22


PACS = [
    {"id": "a", "nome": "Ana", "tel": "71900000001", "orcamento": {"parcelas": _parc("2026-02-20", "2026-03-05"), "pagamentos": []}},   # 2 atrasadas
    {"id": "b", "nome": "Bia", "tel": "71900000002", "orcamento": {"parcelas": _parc("2026-03-08"), "pagamentos": []}},                  # 2 dias: ainda não
    {"id": "c", "nome": "Caio", "tel": "71900000003", "orcamento": {"parcelas": _parc("2026-03-12"), "pagamentos": []}},                 # vence em 2 dias
    {"id": "d", "nome": "Davi", "tel": "71900000004", "orcamento": {"parcelas": _parc("2026-02-01"), "pago": "100"}},                    # quitada
    {"id": "e", "nome": "Eva", "tel": "", "orcamento": {"parcelas": _parc("2026-02-01"), "pagamentos": [{"valor": "100", "estornadoEm": "x"}]}},  # estorno: atrasada
]


def _setup(tmp_path):
    f = tmp_path / "b.json"
    f.write_text(json.dumps({"versao": "hrpg_v1", "pacientes": PACS, "stores": {}}), encoding="utf-8")
    led = LedgerManager(tmp_path / "l")
    m = Maestro(led, estado=tmp_path / "est", notificador=Notificador(CanalSimulado(), led, carregar_todos()["R-02"]))
    return m, carregar_backup(f)


def test_cobranca_e_lembrete_so_sugerem_para_a_recepcao(tmp_path):
    m, c = _setup(tmp_path)
    itens = {(i.tipo, i.nome) for i in rodar(m, c, AGORA)}
    assert itens == {("atraso", "Ana"), ("atraso", "Eva"), ("a_vencer", "Caio")}  # Bia (2 dias) e Davi (quitada) ficam de fora
    assert {t.responsavel for t in m.tarefas.tarefas.values()} == {"recepcao"}


def test_cartoes_cordiais_sem_valor_ameaca_ou_juros(tmp_path):
    m, c = _setup(tmp_path)
    rodar(m, c, AGORA)
    cs = {x["nome"]: x for x in cartoes(m, c, "financeiro", TIPOS_FINANCEIRO)}
    assert "desde 05/03" not in cs["Ana"]["texto"] and "desde 20/02" in cs["Ana"]["texto"]  # a parcela mais antiga em aberto
    assert "vence em 12/03" in cs["Caio"]["texto"]
    for x in cs.values():
        assert not any(w in x["texto"].lower() for w in ("juros", "multa", "spc", "serasa", "protesto", "R$".lower()))
        assert "desconsidere" in x["texto"] or "lembrar" in x["texto"]
    assert cs["Eva"]["link"] == ""  # sem telefone


def test_nao_repete_cobranca_dentro_do_intervalo_e_ledger_sem_dados(tmp_path):
    m, c = _setup(tmp_path)
    rodar(m, c, AGORA)
    n = len(m.tarefas.tarefas)
    rodar(m, c, datetime(2026, 3, 12, 10, 0))  # 2 dias depois: dentro dos 7 dias
    assert len(m.tarefas.tarefas) == n or all("Caio" not in t.titulo for t in m.tarefas.tarefas.values())
    txt = "".join(p.read_text(encoding="utf-8") for p in (tmp_path / "l").glob("*.json"))
    assert not any(x in txt for x in ("Ana", "Caio", "7190000"))
    assert m.ledger.verificar()


def test_limite_diario(tmp_path):
    m, c = _setup(tmp_path)
    for i in range(30):
        c.por_id[f"x{i}"] = {**c.por_id["a"], "id": f"x{i}", "nome": f"N{i}"}
    itens = rodar(m, c, AGORA)
    assert sum("tarefa #" in i.resultado and i.tipo == "atraso" for i in itens) == 10
    assert any("limite diário" in i.resultado for i in itens)
