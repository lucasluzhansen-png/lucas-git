from hansen.ledger import LedgerManager
from hansen.maestro import Maestro


def _m(tmp_path):
    return Maestro(LedgerManager(tmp_path))


def test_pendencia_cria_tarefa_autonomamente(tmp_path):
    m = _m(tmp_path)
    d = m.processar("pendencia", dados={"titulo": "Autoclave falhou", "responsavel": "asb", "solicitante": "rt", "prioridade": "vermelha"})
    assert d.estado == "executado"  # A-06 é IA_EXECUTA
    t = m.tarefas.tarefas[d.tarefa_id]
    assert (t.titulo, t.prioridade, t.responsavel) == ("Autoclave falhou", "vermelha", "asb")
    assert m.ledger.verificar()


def test_pendencia_mal_formada_escala_humano(tmp_path):
    d = _m(tmp_path).processar("pendencia", dados={"titulo": "x", "prioridade": "urgentissima"})
    assert d.estado == "escalado_humano"


def test_abertura_so_registra_sem_tarefa(tmp_path):
    d = _m(tmp_path).processar("abertura", dados={"por": "jussara"})
    assert (d.pop_id, d.estado, d.tarefa_id) == ("A-01", "executado", None)  # decisão do RT


def test_abertura_sem_responsavel_escala(tmp_path):
    assert _m(tmp_path).processar("abertura", dados={}).estado == "escalado_humano"
