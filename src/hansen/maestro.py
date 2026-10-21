"""Maestro: orquestra os POPs. Decide só o que o YAML permite; risco clínico vai para humano."""
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from hansen.agentes.recepcao import Recepcao
from hansen.agentes.rotina import Rotina
from hansen.canal import Notificador
from hansen.cerebro import Cerebro
from hansen.ledger import LedgerManager
from hansen.tarefas import TarefaManager
from hansen.yaml_parser import POP, carregar_todos

# Quem pode agir sozinho. Tudo o resto vira pedido de aprovação humana.
AUTONOMOS = {"IA_AUDITA", "IA_EXECUTA", "IA_SOZINHA"}  # só agem sozinhos se aprovacao_humana=false no YAML


@dataclass
class Decisao:
    pop_id: str
    estado: str  # executado | aguarda_humano | escalado_humano
    acao: str
    detalhe: str
    tarefa_id: int | None = None


class Maestro:
    def __init__(self, ledger: LedgerManager, pops: dict[str, POP] | None = None, cerebro: Cerebro | None = None,
                 estado: Path | None = None, notificador: Notificador | None = None):
        self.ledger = ledger
        self.cerebro = cerebro
        self.pops = pops or carregar_todos()
        self.agentes = [Recepcao(self.pops), Rotina()]
        self.notificador = notificador
        self._arq_pausas = Path(estado) / "pausas.json" if estado else None
        if estado:
            Path(estado).mkdir(parents=True, exist_ok=True)
        self.pausados: set[str] = set(json.loads(self._arq_pausas.read_text(encoding="utf-8"))) if self._arq_pausas and self._arq_pausas.exists() else set()
        self.tarefas = TarefaManager(ledger, self.pops["A-06"], arquivo=Path(estado) / "tarefas.json" if estado else None)

    def receber_mensagem(self, texto: str) -> Decisao:
        """Entrada em texto livre: o cérebro classifica, o resto segue o YAML."""
        i = self.cerebro.interpretar(texto)
        return self.processar(i.tipo, texto)

    def processar(self, tipo: str, texto: str = "", dados: dict | None = None) -> Decisao:
        agente = next((a for a in self.agentes if tipo in a.tipos), None)
        if agente is None:  # sem agente para o evento: nunca improvisar
            return self._fechar("-", "escalado_humano", "sem_agente", "Sem agente para este evento.", tipo, texto, dados)
        if agente.nome in self.pausados:  # veto do RT: agente pausado nunca age
            return self._fechar("-", "escalado_humano", "agente_pausado", f"Agente {agente.nome} pausado pelo RT.", tipo, texto, dados)
        prop = agente.tratar(tipo, texto, dados)
        if prop is None:
            return self._fechar("-", "escalado_humano", "sem_regra", "Nenhuma regra aplicável.", tipo, texto, dados)
        pop = self.pops[prop.pop_id]
        # Regra de ouro: autonomia vem do nível do POP, não do código.
        autonomo = pop.automacao.nivel in AUTONOMOS and not pop.automacao.aprovacao_humana
        estado = "executado" if autonomo else "aguarda_humano"
        return self._fechar(prop.pop_id, estado, prop.efeito, prop.detalhe, tipo, texto, dados, prop.tarefa)

    def pausar(self, agente: str, por: str, papel: str) -> bool:
        return self._alternar_pausa(agente, por, papel, pausar=True)

    def retomar(self, agente: str, por: str, papel: str) -> bool:
        return self._alternar_pausa(agente, por, papel, pausar=False)

    def _alternar_pausa(self, agente, por, papel, pausar) -> bool:
        """Só o RT pausa/retoma, e só agentes que existem. Tudo fica no ledger."""
        acao = "pausar_agente" if pausar else "retomar_agente"
        ok = papel == "rt" and agente in {a.nome for a in self.agentes}
        if ok:
            (self.pausados.add if pausar else self.pausados.discard)(agente)
            if self._arq_pausas:
                self._arq_pausas.write_text(json.dumps(sorted(self.pausados)), encoding="utf-8")
        self.ledger.registar(
            pop_id="-", ator={"type": "humano", "id": por, "papel": papel}, acao=acao,
            resultado="sucesso" if ok else "falha", entrada={"agente": agente}, saida={},
            privacidade={"dado_sensivel": False, "base_legal_lgpd": "obrigacao_legal", "retencao_anos": 5},
        )
        return ok

    def _fechar(self, pop_id, estado, acao, detalhe, tipo, texto, dados=None, tarefa_req=None) -> Decisao:
        dados = dados or {}
        self.ledger.registar(
            pop_id=pop_id,
            ator={"type": "agente_ia", "id": "maestro", "papel": "orquestrador"},
            acao=str(acao),
            resultado="sucesso",
            entrada={"tipo": tipo, "texto": texto, "dados": {k: v for k, v in dados.items() if k not in ("telefone", "nome")}},
            saida={"estado": estado, "detalhe": detalhe},
            privacidade={"dado_sensivel": True, "base_legal_lgpd": "execucao_contrato", "retencao_anos": 5},
        )
        if acao == "enviar_lembrete" and estado == "executado" and self.notificador and dados.get("telefone"):
            self.notificador.lembrete_paciente(
                dados.get("nome", ""), dados["telefone"], datetime.fromisoformat(dados["consulta_em"]), datetime.fromisoformat(dados["agora"]))
        tarefa = self._tarefa_para_humano(pop_id, estado, str(acao), detalhe, tarefa_req)
        return Decisao(pop_id, estado, str(acao), detalhe, tarefa.id if tarefa else None)

    def _tarefa_para_humano(self, pop_id, estado, acao, detalhe, tarefa_req=None):
        """Tudo que depende de gente vira tarefa cobrada pelo A-06; o que a IA executou sozinha, não."""
        if tarefa_req and estado == "executado":  # pedido explícito do agente (ex.: A-06 IA_EXECUTA)
            return self.tarefas.criar(**tarefa_req)
        if estado == "executado" and acao != "marcar_no_show":
            return None
        prioridade = "verde" if estado == "aguarda_humano" else "amarela"
        titulo = {
            "marcar_no_show": "Ligar ao paciente: risco de no-show",
            "agente_pausado": "Agente pausado pelo RT: tratar este pedido manualmente",
            "sem_agente": "Pedido sem agente responsável: tratar manualmente",
            "sem_regra": "A IA não encontrou regra para este pedido: tratar manualmente",
        }.get(acao) or f"Aprovar decisão da IA ({pop_id}): {acao}"
        quem = self.pops["A-06"].responsaveis
        chave = {"marcar_no_show": "ligacao_no_show", "agente_pausado": "tratar_manual", "sem_agente": "tratar_manual", "sem_regra": "tratar_manual"}.get(acao, "aprovacao_ia")
        return self.tarefas.criar(f"{titulo}. {detalhe}", "maestro", quem[chave], prioridade)
