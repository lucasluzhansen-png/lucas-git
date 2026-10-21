from dataclasses import dataclass


@dataclass
class Proposta:
    """O que um agente quer fazer. Quem autoriza e registra é o Maestro."""
    pop_id: str
    efeito: str
    detalhe: str
