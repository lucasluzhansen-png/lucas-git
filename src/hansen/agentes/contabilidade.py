"""Agente Contabilidade (CT-01): junta os números do mês/ano e cobra o envio ao contador. Nunca calcula imposto."""
from hansen.agentes.base import Proposta


class Contabilidade:
    nome = "contabilidade"
    tipos = {"contabil"}

    def tratar(self, tipo: str, texto: str = "", dados: dict | None = None) -> Proposta | None:
        d = dados or {}
        return Proposta("CT-01", d.get("acao", "enviar_contador"), d.get("detalhe", "")) if tipo == "contabil" else None
