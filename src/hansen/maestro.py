"""Maestro: orquestra os POPs. Decide só o que o YAML permite; risco clínico vai para humano."""
from dataclasses import dataclass

from hansen.agentes.recepcao import Recepcao
from hansen.cerebro import Cerebro
from hansen.ledger import LedgerManager
from hansen.tarefas import TarefaManager
from hansen.yaml_parser import POP, carregar_todos

# Quem pode agir sozinho. Tudo o resto vira pedido de aprovação humana.
AUTONOMOS = {"IA_EXECUTA", "IA_SOZINHA"}


@dataclass
class Decisao:
    pop_id: str
    estado: str  # executado | aguarda_humano | escalado_humano
    acao: str
    detalhe: str
    tarefa_id: int | None = None


class Maestro:
    def __init__(self, ledger: LedgerManager, pops: dict[str, POP] | None = None, cerebro: Cerebro | None = None):
        self.ledger = ledger
        self.cerebro = cerebro
        self.pops = pops or carregar_todos()
        self.agentes = [Recepcao(self.pops)]
        self.tarefas = TarefaManager(ledger, self.pops["A-06"])

    def receber_mensagem(self, texto: str) -> Decisao:
        """Entrada em texto livre: o cérebro classifica, o resto segue o YAML."""
        i = self.cerebro.interpretar(texto)
        return self.processar(i.tipo, texto)

    def processar(self, tipo: str, texto: str = "", dados: dict | None = None) -> Decisao:
        agente = next((a for a in self.agentes if tipo in a.tipos), None)
        if agente is None:  # sem agente para o evento: nunca improvisar
            return self._fechar("-", "escalado_humano", "sem_agente", "Sem agente para este evento.", tipo, texto, dados)
        prop = agente.tratar(tipo, texto, dados)
        if prop is None:
            return self._fechar("-", "escalado_humano", "sem_regra", "Nenhuma regra aplicável.", tipo, texto, dados)
        pop = self.pops[prop.pop_id]
        # Regra de ouro: autonomia vem do nível do POP, não do código.
        autonomo = pop.automacao.nivel in AUTONOMOS and not pop.automacao.aprovacao_humana
        estado = "executado" if autonomo else "aguarda_humano"
        return self._fechar(prop.pop_id, estado, prop.efeito, prop.detalhe, tipo, texto, dados)

    def _fechar(self, pop_id, estado, acao, detalhe, tipo, texto, dados=None) -> Decisao:
        self.ledger.registar(
            pop_id=pop_id,
            ator={"type": "agente_ia", "id": "maestro", "papel": "orquestrador"},
            acao=str(acao),
            resultado="sucesso",
            entrada={"tipo": tipo, "texto": texto, "dados": dados or {}},
            saida={"estado": estado, "detalhe": detalhe},
            privacidade={"dado_sensivel": True, "base_legal_lgpd": "execucao_contrato", "retencao_anos": 5},
        )
        tarefa = self._tarefa_para_humano(pop_id, estado, str(acao), detalhe)
        return Decisao(pop_id, estado, str(acao), detalhe, tarefa.id if tarefa else None)

    def _tarefa_para_humano(self, pop_id, estado, acao, detalhe):
        """Tudo que depende de gente vira tarefa cobrada pelo A-06; o que a IA executou sozinha, não."""
        if estado == "executado" and acao != "marcar_no_show":
            return None
        prioridade = "verde" if estado == "aguarda_humano" else "amarela"
        titulo = {
            "marcar_no_show": "Ligar ao paciente: risco de no-show",
            "aguarda_humano": f"Aprovar decisão da IA ({pop_id}): {acao}",
            "escalado_humano": f"IA sem regra aplicável, tratar manualmente ({pop_id})",
        }.get(acao if acao == "marcar_no_show" else estado)
        return self.tarefas.criar(f"{titulo}. {detalhe}", "maestro", "recepcao", prioridade)
