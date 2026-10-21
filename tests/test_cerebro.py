import json

from hansen.cerebro import Cerebro
from hansen.ledger import LedgerManager
from hansen.maestro import Maestro


class Fake:
    def __init__(self, resp):
        self.resp = resp

    def completar(self, sistema, usuario):
        return self.resp


def _m(tmp_path, resp):
    return Maestro(LedgerManager(tmp_path), cerebro=Cerebro(Fake(resp)))


def test_llm_classifica_e_yaml_decide(tmp_path):
    m = _m(tmp_path, json.dumps({"tipo": "triagem", "confianca": 0.95}))
    d = m.receber_mensagem("Queria arrumar um dente com canal inflamado")
    assert d.pop_id == "R-00" and d.acao == "bloquear"


def test_baixa_confianca_vai_para_humano(tmp_path):
    d = _m(tmp_path, '{"tipo":"triagem","confianca":0.4}').receber_mensagem("oi")
    assert d.estado == "escalado_humano"


def test_llm_quebrado_nunca_improvisa(tmp_path):
    assert _m(tmp_path, "lixo").receber_mensagem("oi").estado == "escalado_humano"


def test_risco_clinico_ignora_llm(tmp_path):
    c = Cerebro(Fake('{"tipo":"triagem","confianca":1}'))
    assert c.interpretar("Estou sangrando muito").origem == "regra_risco"
