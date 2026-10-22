"""Simulação de ~4 meses na clínica: cadastro, orçamento, aprovação, tratamento, alta, cobrança e contador.
Um Clinus FICTÍCIO muda dia a dia (backup gerado em disco); o Maestro roda todo dia útil às 9h e a "Recepção"/"Dr. Lucas"
reagem às tarefas no Clinus. Mostra só o que o Maestro fez em cada dia. Dados 100% inventados."""
import json
import shutil
import sys
from datetime import date, datetime, timedelta

from hansen.caminhos import pasta_saida
from hansen.hoje import executar_completo

TEL = {"ana": "11911110001", "bruno": "11911110002", "carla": "11911110003", "diego": "11911110004"}
NOMES = {"ana": "Ana Lima", "bruno": "Bruno Reis", "carla": "Carla Dias", "diego": "Diego Melo"}


def d(dia: str) -> date:
    return date.fromisoformat(dia)


class ClinusFicticio:
    def __init__(self):
        self.pacs: dict[str, dict] = {}
        self.agenda: list[dict] = []
        self.retornos: list[dict] = []
        self.contas: list[dict] = []

    # --- ações da equipe no Clinus ---
    def cadastrar(self, pid, dia, nascimento="1990-01-01"):
        self.pacs[pid] = {"id": pid, "nome": NOMES[pid], "tel": TEL[pid], "nascimento": nascimento, "criadoEm": f"{dia}T09:00:00",
                          "ultimaAcao": f"{dia}T09:00:00", "orcamento": {"pagamentos": [], "parcelas": []}}

    def vai_pensar(self, pid, dia, valor=3000):
        p = self.pacs[pid]
        p.update(decisao="pensar", ultimaAcao=f"{dia}T11:00:00")
        p["orcamento"]["itens"] = [{"proc": "Plano", "valor": valor}]

    def aprovar(self, pid, dia, valor, parcelas, entrada):
        p = self.pacs[pid]
        p.update(decisao="aprovado", ultimaAcao=f"{dia}T11:00:00")
        o = p["orcamento"]
        o["aprovadoEm"] = dia
        o["itens"] = [{"proc": "Plano", "valor": valor}]
        o["pagamentos"].append({"d": d(dia).strftime("%d/%m/%Y"), "valor": entrada})
        resto = (valor - entrada) / parcelas
        o["parcelas"] = [{"venc": dia, "valor": entrada, "paga": True}] + [
            {"venc": str(d(dia) + timedelta(days=30 * (i + 1))), "valor": resto} for i in range(parcelas)]  # a entrada é a 1ª parcela

    def pagar(self, pid, dia, valor):
        self.pacs[pid]["orcamento"]["pagamentos"].append({"d": d(dia).strftime("%d/%m/%Y"), "valor": valor})

    def marcar(self, pid, dia, hora="10:00"):
        self.agenda.append({"id": f"{pid}{dia}", "pacId": pid, "data": dia, "hora": hora, "status": "agendado", "nome": NOMES[pid]})

    def pagar_parcelas(self, hoje: date):  # pacientes em dia pagam no vencimento (Ana atrasa a 1ª parcela de propósito)
        for pid, p in self.pacs.items():
            o = p["orcamento"]
            for x in o.get("parcelas", []):
                if not x.get("paga") and d(x["venc"]) <= hoje and not (pid == "ana" and hoje < date(2026, 4, 9)):
                    x["paga"] = True
                    self.pagar(pid, str(d(x["venc"])), x["valor"])

    def concluir_consultas(self, hoje: date):  # consulta no passado vira realizada
        for e in self.agenda:
            if e["status"] == "agendado" and d(e["data"]) < hoje:
                e["status"] = "concluido"
                self.pacs[e["pacId"]]["ultimaAcao"] = f"{e['data']}T12:00:00"

    def dar_alta(self, pid, dia):
        self.pacs[pid]["encerramento"] = {"emISO": dia}
        self.pacs[pid]["etapa"] = 10

    def backup(self, caminho, agora: datetime):
        caminho.write_text(json.dumps({"versao": "hrpg_v1", "exportadoEm": agora.isoformat(), "pacientes": list(self.pacs.values()), "stores": {
            "clinus_agenda_v2": json.dumps(self.agenda), "clinus_retornos_v1": json.dumps(self.retornos),
            "clinus_contas_pagar": json.dumps(self.contas)}}), encoding="utf-8")


def roteiro(c: ClinusFicticio):
    """dia → (o que acontece no Clinus nesse dia, antes de o Maestro rodar)"""
    c.contas = [{"id": "c1", "descricao": "Aluguel", "valor": "2500", "vencimento": "2026-03-05", "status": "pago"},
                {"id": "c2", "descricao": "Aluguel", "valor": "2500", "vencimento": "2026-04-05", "status": "pago"}]
    return {
        "2026-03-02": [("Recepção cadastra Ana, Bruno, Carla e Diego", lambda: [c.cadastrar("ana", "2026-03-02"), c.cadastrar("bruno", "2026-03-02"),
                                                                              c.cadastrar("carla", "2026-03-02"), c.cadastrar("diego", "2026-03-02", "1988-03-18")]),
                       ("Bruno recebe orçamento e diz que vai pensar", lambda: c.vai_pensar("bruno", "2026-03-02")),
                       ("Ana aprova o plano e paga a entrada", lambda: c.aprovar("ana", "2026-03-02", 6000, 3, 1500)),
                       ("Carla aprova o plano e paga a entrada", lambda: c.aprovar("carla", "2026-03-02", 2400, 2, 800)),
                       ("Carla agenda sessões até o fim", lambda: [c.marcar("carla", "2026-03-16"), c.marcar("carla", "2026-03-30")])],
        "2026-03-10": [("Bruno aprova o orçamento e paga", lambda: [c.aprovar("bruno", "2026-03-10", 3000, 2, 1000), c.marcar("bruno", "2026-03-17")])],
        "2026-03-11": [("Recepção agenda o início da Ana", lambda: c.marcar("ana", "2026-03-18"))],
        "2026-03-31": [("Dr. Lucas dá alta à Carla (tratamento concluído)", lambda: c.dar_alta("carla", "2026-03-31"))],
        "2026-04-09": [("Ana paga a parcela atrasada", lambda: c.pagar("ana", "2026-04-09", 1500))],
        "2026-04-10": [("Recepção marca o retorno da Carla", lambda: c.marcar("carla", "2026-05-12"))],
        "2026-04-17": [("Ana e Bruno fazem sessões; Bruno agenda a próxima", lambda: c.marcar("bruno", "2026-04-27"))],
        "2026-05-04": [("Recepção contata a Ana e agenda a próxima sessão", lambda: c.marcar("ana", "2026-05-11"))],
        "2026-05-13": [("Dr. Lucas dá alta à Ana e ao Bruno", lambda: [c.dar_alta("ana", "2026-05-13"), c.dar_alta("bruno", "2026-05-13")])],
    }


def main(argv=None):
    base = pasta_saida() / "simulacao_clinica"
    shutil.rmtree(base, ignore_errors=True)
    base.mkdir(parents=True)
    c = ClinusFicticio()
    plano = roteiro(c)
    # sessões "realizadas" extras no passado para o histórico do tratamento da Ana
    c_dias = [date(2026, 3, 2) + timedelta(days=i) for i in range(0, 125)]
    vistos: dict[int, str] = {}
    print("SIMULAÇÃO: 4 meses na clínica (dados fictícios)\n")
    for dia in c_dias:
        if dia.weekday() >= 5:
            continue
        for _, acao in plano.get(str(dia), []):
            acao()
        for desc, _ in plano.get(str(dia), []):
            print(f"{dia:%d/%m} 🏥 CLINUS: {desc}")
        c.concluir_consultas(dia)
        c.pagar_parcelas(dia)
        agora = datetime(dia.year, dia.month, dia.day, 9, 0)
        backup = base / "backup.json"
        c.backup(backup, agora)
        destino, m, dados, msgs = executar_completo(backup, agora, base)
        for t in sorted(m.tarefas.tarefas.values(), key=lambda t: t.id):
            nome = t.titulo.split(" [")[0]
            if t.id not in vistos:
                print(f"{dia:%d/%m} 🎼 MAESTRO cria #{t.id} → {t.responsavel}: {nome}")
            elif vistos[t.id] != t.estado and t.estado == "fechada":
                print(f"{dia:%d/%m} ✅ #{t.id} fechada sozinha: o Clinus mostra que foi resolvido")
            vistos[t.id] = t.estado
            # a equipe faz as tarefas que o Clinus não enxerga (ligação, caixa, envio ao contador) no dia seguinte
            if t.estado == "aberta" and (agora - t.criada_em.replace(tzinfo=None)).days >= 1 and t.responsavel == "recepcao" \
                    and t.titulo.startswith(("Ligar", "Fechar o caixa", "Contabilidade", "Lembrar", "Cobrar")):
                m.tarefas.fechar(t.id, "recepcao", "feito")
                vistos[t.id] = "fechada"
                print(f"{dia:%d/%m} 👩 Recepção faz #{t.id} ({nome[:45]})")
    abertas = [t for t in m.tarefas.tarefas.values() if t.estado in ("aberta", "escalada")]
    print(f"\nFIM: {len(m.tarefas.tarefas)} tarefas no total, {len(abertas)} ainda abertas. Ledger íntegro: {m.ledger.verificar()}")


if __name__ == "__main__":
    main(sys.argv)
