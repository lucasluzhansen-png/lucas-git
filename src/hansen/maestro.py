"""Maestro: orquestra os POPs. Decide só o que o YAML permite; risco clínico vai para humano."""
import unicodedata
from dataclasses import dataclass

from hansen.cerebro import Cerebro
from hansen.ledger import LedgerManager
from hansen.yaml_parser import POP, carregar_todos

# Quem pode agir sozinho. Tudo o resto vira pedido de aprovação humana.
AUTONOMOS = {"IA_EXECUTA", "IA_SOZINHA"}
TIPO_PARA_POP = {"triagem": "R-00"}  # roteamento; cresce com cada POP implementado


def _norm(t: str) -> str:
    return unicodedata.normalize("NFKD", t.lower()).encode("ascii", "ignore").decode()


@dataclass
class Decisao:
    pop_id: str
    estado: str  # executado | aguarda_humano | escalado_humano
    acao: str
    detalhe: str


class Maestro:
    def __init__(self, ledger: LedgerManager, pops: dict[str, POP] | None = None, cerebro: Cerebro | None = None):
        self.ledger = ledger
        self.cerebro = cerebro
        self.pops = pops or carregar_todos()

    def receber_mensagem(self, texto: str) -> Decisao:
        """Entrada em texto livre: o cérebro classifica, o resto segue o YAML."""
        i = self.cerebro.interpretar(texto)
        return self.processar(i.tipo, texto)

    def processar(self, tipo: str, texto: str) -> Decisao:
        pop = self.pops.get(TIPO_PARA_POP.get(tipo, ""))
        if pop is None:  # sem POP implementado: nunca improvisar
            return self._fechar("-", "escalado_humano", "sem_pop", "Sem POP para este evento.", tipo, texto)
        regra = self._achar_regra(pop, _norm(texto))
        if regra is None:
            return self._fechar(pop.id, "escalado_humano", "sem_regra", "Nenhuma regra aplicável.", tipo, texto)
        # Regra de ouro: autonomia vem do nível do POP, não do código.
        autonomo = pop.automacao.nivel in AUTONOMOS and not pop.automacao.aprovacao_humana
        estado = "executado" if autonomo else "aguarda_humano"
        return self._fechar(pop.id, estado, regra.efeito, regra.acao, tipo, texto)

    @staticmethod
    def _achar_regra(pop: POP, texto: str):
        return next(
            (r for r in pop.regras_de_decisao if r.efeito and any(_norm(k) in texto for k in r.palavras_chave)),
            None,
        )

    def _fechar(self, pop_id, estado, acao, detalhe, tipo, texto) -> Decisao:
        self.ledger.registar(
            pop_id=pop_id,
            ator={"type": "agente_ia", "id": "maestro", "papel": "orquestrador"},
            acao=str(acao),
            resultado="sucesso",
            entrada={"tipo": tipo, "texto": texto},
            saida={"estado": estado, "detalhe": detalhe},
            privacidade={"dado_sensivel": True, "base_legal_lgpd": "execucao_contrato", "retencao_anos": 5},
        )
        return Decisao(pop_id, estado, str(acao), detalhe)
