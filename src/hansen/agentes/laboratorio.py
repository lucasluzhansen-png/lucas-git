"""Agente Laboratório (LB-01): acompanha PRAZOS e ETAPAS das OS e cobra a equipe. Nunca avalia a peça."""
from hansen.agentes.base import Proposta


class Laboratorio:
    nome = "laboratorio"
    tipos = {"os_lab", "confirmacao_bloqueada"}

    def tratar(self, tipo: str, texto: str = "", dados: dict | None = None) -> Proposta | None:
        d = dados or {}
        if tipo == "confirmacao_bloqueada":
            return Proposta("LB-01", "confirmacao_bloqueada", d.get("detalhe", "Confirmação suspensa: peça não conferida."))
        return Proposta("LB-01", d.get("acao", "cobrar_lab"), d.get("detalhe", "")) if tipo == "os_lab" else None
