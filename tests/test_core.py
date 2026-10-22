import json

import pytest

from hansen.ledger import LedgerManager
from hansen.yaml_parser import carregar_todos

PRIV = {"dado_sensivel": False, "base_legal_lgpd": "obrigacao_legal", "retencao_anos": 20}
ATOR = {"type": "humano", "id": "u1", "papel": "rt"}


def test_todos_os_pops_validos():
    pops = carregar_todos()
    originais = {"R-00", "R-02", "R-08", "A-01", "A-06", "B-01", "B-02", "B-12", "C-00", "C-19", "C-20", "S-01", "S-07"}
    novos = {"CM-01", "CM-02", "FN-01", "FN-02"}
    assert (originais | novos) <= set(pops)


def test_ledger_cadeia_e_adulteracao(tmp_path):
    l = LedgerManager(tmp_path)
    l.registar(pop_id="A-01", ator=ATOR, acao="x", privacidade=PRIV)
    l.registar(pop_id="A-01", ator=ATOR, acao="y", privacidade=PRIV)
    assert l.verificar()
    f = tmp_path / "0000000001.json"
    d = json.loads(f.read_text())
    d["acao"] = "adulterado"
    f.write_text(json.dumps(d))
    assert not l.verificar()
