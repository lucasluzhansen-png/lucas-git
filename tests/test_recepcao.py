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


def test_clareamento_encaminha_para_agendamento(tmp_path):
    d = _m(tmp_path).processar("triagem", "Quero fazer clareamento")
    assert (d.pop_id, d.acao) == ("R-00", "encaminhar_agendamento")


def test_pedido_ambiguo_vai_para_humano(tmp_path):
    d = _m(tmp_path).processar("triagem", "Quero clareamento e tirar o siso")
    assert d.estado == "escalado_humano"


def test_titulos_de_tarefa_distintos(tmp_path):
    m = _m(tmp_path)
    m.pausar("recepcao", "lucas", "rt")
    a = m.tarefas.tarefas[m.processar("triagem", "x").tarefa_id].titulo
    b = m.tarefas.tarefas[m.processar("coisa", "x").tarefa_id].titulo
    assert "pausado" in a and "sem agente" in b


def test_tarefa_igual_aberta_nao_duplica(tmp_path):
    m = _m(tmp_path)
    t1 = m.processar("coisa", "x").tarefa_id
    t2 = m.processar("coisa", "y").tarefa_id
    assert t1 == t2


def test_aprovacoes_vao_para_o_dr_lucas_e_ligacao_para_recepcao(tmp_path):
    m = _m(tmp_path)
    aprov = m.tarefas.tarefas[m.processar("triagem", "quero tirar o siso").tarefa_id]
    ligar = m.tarefas.tarefas[m.processar("confirmacao", dados=_d("2026-01-06T07:30:00", "2026-01-06T09:00:00")).tarefa_id]
    assert (aprov.responsavel, ligar.responsavel) == ("lucas", "recepcao")


def test_novos_servicos_encaminham(tmp_path):
    m = _m(tmp_path)
    for frase in ["Quero alinhador", "Preciso de uma coroa", "Faço bruxismo e queria placa", "Tenho PPR solto", "Queria lentes", "Quero restauração"]:
        assert m.processar("triagem", frase).acao == "encaminhar_agendamento", frase


def test_sigla_curta_nao_casa_dentro_de_palavra(tmp_path):
    assert _m(tmp_path).processar("triagem", "Opte por me ligar depois").estado == "escalado_humano"


def test_paciente_atual_com_servico_bloqueado_vai_para_dentista(tmp_path):
    m = _m(tmp_path)
    d = m.processar("triagem", "Estou com dor e preciso de canal", dados={"paciente_atual": True})
    t = m.tarefas.tarefas[d.tarefa_id]
    assert d.acao == "atendimento_clinico_humano" and t.responsavel == "lucas" and t.prioridade == "amarela"


def test_agendamento_vai_para_recepcao(tmp_path):
    m = _m(tmp_path)
    t = m.tarefas.tarefas[m.processar("triagem", "Quero clareamento").tarefa_id]
    assert t.responsavel == "recepcao" and "Agendar" in t.titulo
