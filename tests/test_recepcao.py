from hansen.ledger import LedgerManager
from hansen.maestro import Maestro

SEG_10H = "2026-01-05T10:00:00"  # segunda-feira
SAB_10H = "2026-01-10T10:00:00"


def _d(agora, consulta, respondeu=False):
    return {"agora": agora, "consulta_em": consulta, "respondeu": respondeu}


def _m(tmp_path):
    return Maestro(LedgerManager(tmp_path))


def test_no_show_executa_sozinho(tmp_path):
    d = _m(tmp_path).processar("confirmacao", dados=_d("2026-01-06T07:30:00", "2026-01-06T09:00:00"))
    assert (d.acao, d.estado) == ("marcar_no_show", "executado")  # R-02 é IA_SOZINHA


def test_lembrete_em_horario_comercial(tmp_path):
    d = _m(tmp_path).processar("confirmacao", dados=_d(SEG_10H, "2026-01-07T09:00:00"))
    assert (d.acao, d.estado) == ("enviar_lembrete", "executado")


def test_fim_de_semana_adia_envio(tmp_path):
    d = _m(tmp_path).processar("confirmacao", dados=_d(SAB_10H, "2026-01-12T09:00:00"))
    assert d.acao == "adiar_envio"


def test_confirmado(tmp_path):
    d = _m(tmp_path).processar("confirmacao", dados=_d(SEG_10H, "2026-01-07T09:00:00", True))
    assert d.acao == "confirmar"


def test_triagem_continua_via_agente(tmp_path):
    m = _m(tmp_path)
    assert m.processar("triagem", "quero tirar o siso").acao == "bloquear"
    assert m.ledger.verificar()


def test_no_show_cria_tarefa_de_ligacao(tmp_path):
    m = _m(tmp_path)
    d = m.processar("confirmacao", dados=_d("2026-01-06T07:30:00", "2026-01-06T09:00:00"))
    t = m.tarefas.tarefas[d.tarefa_id]
    assert (t.responsavel, t.estado) == ("recepcao", "aberta") and "no-show" in t.titulo


def test_decisao_pendente_de_humano_vira_tarefa(tmp_path):
    m = _m(tmp_path)
    assert m.processar("triagem", "quero tirar o siso").tarefa_id  # aguarda aprovação
    assert m.processar("xyz", "?").tarefa_id  # sem agente


def test_acao_autonoma_sem_pendencia_nao_cria_tarefa(tmp_path):
    d = _m(tmp_path).processar("confirmacao", dados=_d(SEG_10H, "2026-01-07T09:00:00"))
    assert d.tarefa_id is None
