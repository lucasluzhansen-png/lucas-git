"""Simulação de um dia na clínica (dados fictícios, relógio controlado, canal simulado)."""
import shutil
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path

from hansen.agendador import Agendador
from hansen.canal import CanalSimulado, Notificador
from hansen.ledger import LedgerManager
from hansen.maestro import Maestro
from hansen.painel import gerar
from hansen.yaml_parser import carregar_todos

DIA = datetime(2026, 1, 6)  # terça-feira
agora = [DIA]


def h(hora, minuto=0):
    agora[0] = DIA.replace(hour=hora, minute=minuto)
    return agora[0]


def mostra(quando, titulo, d):
    print(f"{quando:%H:%M}  {titulo:<38} → {d.pop_id:4} {d.acao:<18} [{d.estado}]" + (f"  tarefa #{d.tarefa_id}" if d.tarefa_id else ""))


def main():
    base = Path("saida") / "simulacao"  # dentro da pasta do projeto (não na Temp do Windows)
    shutil.rmtree(base, ignore_errors=True)  # cada execução começa limpa
    base.mkdir(parents=True)
    base = base.resolve()
    canal = CanalSimulado()
    ledger = LedgerManager(base / "ledger")
    m = Maestro(ledger, estado=base / "estado", notificador=Notificador(canal, ledger, carregar_todos()["R-02"]))
    m.tarefas.agora = lambda: agora[0]
    ag = Agendador(m.tarefas, m.notificador, carregar_todos()["A-06"].responsaveis["alerta_rt"])

    print("=== MADRUGADA ===")
    q = h(2)
    t = m.tarefas.criar("Falha crítica de infraestrutura", "sistema", "lucas", "vermelha")
    print(f"{q:%H:%M}  Falha crítica registada (tarefa #{t.id}, vermelha)")
    q = h(3, 5)
    ag.tick(q)
    print(f"{q:%H:%M}  60 min passaram → escalada; alerta ao RT SILENCIADO (madrugada). Enviados: {len(canal.enviadas)}")
    q = h(7)
    ag.tick(q)
    print(f"{q:%H:%M}  Alerta entregue ao RT: {canal.enviadas[-1][1]!r}")

    print("\n=== MANHÃ ===")
    q = h(7, 30)
    mostra(q, "Dra. Jussara abre a clínica", m.processar("abertura", dados={"por": "jussara"}))
    q = h(8, 15)
    mostra(q, "Paciente: 'quero fazer um canal'", m.processar("triagem", "Olá, quero fazer um canal"))
    q = h(8, 20)
    mostra(q, "Paciente: 'quero clareamento'", m.processar("triagem", "Quero clareamento"))
    q = h(9)
    base_ev = {"respondeu": False, "nome": "Maria", "telefone": "+55-FICTICIO"}
    mostra(q, "Lembrete: consulta amanhã 10h", m.processar("confirmacao", dados={**base_ev, "agora": q.isoformat(), "consulta_em": (q + timedelta(days=1)).replace(hour=10).isoformat()}))
    q = h(10)
    mostra(q, "Sem resposta, consulta em 1h30", m.processar("confirmacao", dados={**base_ev, "agora": q.isoformat(), "consulta_em": (q + timedelta(minutes=90)).isoformat()}))
    q = h(11)
    pend = m.processar("pendencia", dados={"titulo": "Autoclave sem integrador", "responsavel": "asb", "solicitante": "jussara", "prioridade": "vermelha"})
    mostra(q, "Pendência: autoclave sem integrador", pend)

    print("\n=== TARDE ===")
    q = h(12, 5)
    print(f"{q:%H:%M}  Tarefa fechada SEM evidência? {m.tarefas.fechar(pend.tarefa_id, 'asb', None)}  (esperado: False)")
    q = h(14)
    print(f"{q:%H:%M}  Recepção tenta pausar Rotina? {m.pausar('rotina', 'rec1', 'recepcao')}  (esperado: False)")
    print(f"{q:%H:%M}  RT pausa Recepção? {m.pausar('recepcao', 'lucas', 'rt')}")
    mostra(q, "Triagem com Recepção pausada", m.processar("triagem", "quero um canal"))
    print(f"{q:%H:%M}  RT retoma Recepção? {m.retomar('recepcao', 'lucas', 'rt')}")
    q = h(17)
    print(f"{q:%H:%M}  Fecho COM evidência (foto)? {m.tarefas.fechar(pend.tarefa_id, 'asb', 'foto_integrador.jpg')}")
    q = h(17, 5)
    mostra(q, "Evento desconhecido", m.processar("coisa_estranha", "???"))

    print("\n=== FECHO DO DIA ===")
    for t in m.tarefas.tarefas.values():
        print(f"  #{t.id} [{t.prioridade:8}] {t.estado:9} {t.responsavel:9} {t.titulo[:62]}")
    n = len(list((base / "ledger").glob("*.json")))
    print(f"\nMensagens enviadas (simuladas): {len(canal.enviadas)}")
    print(f"Eventos no ledger: {n} | cadeia íntegra: {ledger.verificar()}")
    print(f"Ficheiros em: {base}")
    painel = gerar(base, m.tarefas, ledger, canal.enviadas)
    print(f"\nPAINEL: {painel}")
    try:
        webbrowser.open(painel.as_uri())  # abre no navegador (falha silenciosa em servidores)
    except Exception:
        pass


if __name__ == "__main__":
    main()
