from hansen.ledger import LedgerManager
from hansen.maestro import Maestro


def _m(tmp_path):
    return Maestro(LedgerManager(tmp_path))


def test_endodontia_bloqueada_com_aprovacao_humana(tmp_path):
    m = _m(tmp_path)
    d = m.processar("triagem", "Preciso fazer um tratamento de CANAL")
    assert (d.pop_id, d.acao) == ("R-00", "bloquear")
    assert d.estado == "aguarda_humano"  # R-00 é IA_AUDITA: humano confirma
    assert m.ledger.verificar()


def test_servico_permitido_vai_para_agendamento_com_aprovacao(tmp_path):
    d = _m(tmp_path).processar("triagem", "Quero clareamento")
    assert (d.acao, d.estado) == ("encaminhar_agendamento", "aguarda_humano")


def test_evento_desconhecido_nunca_improvisa(tmp_path):
    assert _m(tmp_path).processar("xyz", "qualquer").estado == "escalado_humano"
