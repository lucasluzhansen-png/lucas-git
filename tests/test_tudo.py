from datetime import datetime, timedelta, timezone

from hansen.agendador import Agendador
from hansen.canal import CanalSimulado, Notificador
from hansen.ledger import LedgerManager
from hansen.maestro import Maestro
from hansen.yaml_parser import carregar_todos


def _m(tmp_path, estado=None, canal=None):
    led = LedgerManager(tmp_path / "ledger")
    n = Notificador(canal or CanalSimulado(), led, carregar_todos()["R-02"])
    return Maestro(led, estado=estado, notificador=n)


# --- pausa do RT
def test_so_rt_pausa_e_agente_pausado_escala(tmp_path):
    m = _m(tmp_path)
    assert not m.pausar("recepcao", "x", "recepcao")
    assert not m.pausar("inexistente", "lucas", "rt")
    assert m.pausar("recepcao", "lucas", "rt")
    d = m.processar("triagem", "quero tirar o siso")
    assert d.acao == "agente_pausado" and d.estado == "escalado_humano"
    assert m.retomar("recepcao", "lucas", "rt")
    assert m.processar("triagem", "quero tirar o siso").acao == "bloquear"
    assert m.ledger.verificar()


# --- persistência
def test_estado_sobrevive_a_reinicio(tmp_path):
    est = tmp_path / "estado"
    m = _m(tmp_path, est)
    m.pausar("recepcao", "lucas", "rt")
    m.processar("pendencia", dados={"titulo": "A", "responsavel": "asb", "solicitante": "rt", "prioridade": "vermelha"})
    m2 = Maestro(LedgerManager(tmp_path / "ledger"), estado=est)
    assert "recepcao" in m2.pausados
    assert m2.tarefas.tarefas[1].titulo == "A"
    assert m2.ledger.verificar()


# --- canal + lembrete
def test_lembrete_formal_na_janela(tmp_path):
    c = CanalSimulado()
    m = _m(tmp_path, canal=c)
    dados = {"agora": "2026-01-05T10:00:00", "consulta_em": "2026-01-07T09:00:00", "respondeu": False, "nome": "Maria", "telefone": "+5571999990000"}
    m.processar("confirmacao", dados=dados)
    assert c.enviadas and c.enviadas[0][1].startswith("Prezado(a) Senhor(a) Maria")
    assert "telefone" not in open(sorted((tmp_path / "ledger").glob("*.json"))[0]).read()  # PII fora do ledger


def test_sem_envio_fora_da_janela(tmp_path):
    c = CanalSimulado()
    m = _m(tmp_path, canal=c)
    m.processar("confirmacao", dados={"agora": "2026-01-10T10:00:00", "consulta_em": "2026-01-14T09:00:00", "telefone": "1"})
    assert c.enviadas == []


# --- agendador
def test_agendador_madrugada_silencia_e_envia_as_7h(tmp_path):
    c = CanalSimulado()
    m = _m(tmp_path, tmp_path / "estado", c)
    t0 = datetime(2026, 1, 5, 1, 0)
    relogio = [t0]
    m.tarefas.agora = lambda: relogio[0]
    m.tarefas.criar("Falha crítica", "rt", "asb", "vermelha")
    ag = Agendador(m.tarefas, m.notificador, "rt")
    relogio[0] = t0 + timedelta(minutes=61)  # 02:01
    assert ag.tick(relogio[0]) == [] and c.enviadas == []  # silenciado
    relogio[0] = datetime(2026, 1, 5, 7, 0)
    assert ag.tick(relogio[0]) == [1] and c.enviadas[0][1].startswith("ALERTA")
    assert ag.tick(relogio[0]) == []  # não repete
