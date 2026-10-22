"""Agente Laboratório (LB-01): acompanha PRAZOS e ETAPAS das OS e cobra a equipe. Nunca avalia a peça."""
from hansen.agentes.base import Proposta


class Laboratorio:
    nome = "laboratorio"
    tipos = {"os_lab"}

    def tratar(self, tipo: str, texto: str = "", dados: dict | None = None) -> Proposta | None:
        d = dados or {}
        return Proposta("LB-01", d.get("acao", "cobrar_lab"), d.get("detalhe", "")) if tipo == "os_lab" else None
