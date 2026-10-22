from datetime import datetime, timedelta, timezone

import pytest

from hansen.ledger import LedgerManager
from hansen.tarefas import TarefaManager
from hansen.yaml_parser import carregar_todos


class Relogio:
    def __init__(self):
        self.t = datetime(2026, 1, 5, 9, tzinfo=timezone.utc)

    def __call__(self):
        return self.t


@pytest.fixture
def ctx(tmp_path):
    r = Relogio()
    return TarefaManager(LedgerManager(tmp_path), carregar_todos()["A-06"], r), r


def test_vermelha_escala_aos_60_min(ctx):
    m, r = ctx
    m.criar("Autoclave falhou", "rt", "asb", "vermelha")
    r.t += timedelta(minutes=59)
    assert m.escalar_vencidas() == []
    r.t += timedelta(minutes=1)
    assert m.escalar_vencidas()[0].estado == "escalada"


def test_verde_nao_escala(ctx):
    m, r = ctx
    m.criar("Repor luvas", "rt", "asb", "verde")
    r.t += timedelta(hours=5)
    assert m.escalar_vencidas() == []


def test_fecho_sem_evidencia_rejeitado(ctx):
    m, _ = ctx
    t = m.criar("x", "rt", "asb")
    assert not m.fechar(t.id, "asb", None)
    assert m.fechar(t.id, "asb", "foto.jpg")
    assert m.ledger.verificar()


def test_so_rt_veta(ctx):
    m, _ = ctx
    t = m.criar("x", "rt", "asb")
    assert not m.vetar(t.id, "recepcao1", "recepcao", "ordem")
    assert m.vetar(t.id, "lucas", "rt", "não procede")
    assert t.estado == "vetada"
    assert not m.fechar(t.id, "asb", "foto.jpg")  # vetada não fecha
