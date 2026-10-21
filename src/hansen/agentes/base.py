from dataclasses import dataclass


@dataclass
class Proposta:
    """O que um agente quer fazer. Quem autoriza e registra é o Maestro."""
    pop_id: str
    efeito: str
    detalhe: str
    tarefa: dict | None = None  # pedido de tarefa que o Maestro cria se a ação for autorizada
