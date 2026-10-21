"""Agente Rotina: abertura da clínica (A-01) e pendências (A-06)."""
from hansen.agentes.base import Proposta

PRIORIDADES = {"vermelha", "amarela", "verde"}


class Rotina:
    tipos = {"abertura", "pendencia"}

    def tratar(self, tipo: str, texto: str = "", dados: dict | None = None) -> Proposta | None:
        d = dados or {}
        if tipo == "abertura":
            quem = d.get("por")
            if not quem:  # abertura sem responsável identificado: humano resolve
                return None
            return Proposta("A-01", "registrar_abertura", f"Abertura registada por {quem}. Agenda do dia notificada.")
        if d.get("prioridade") not in PRIORIDADES or not all(d.get(k) for k in ("titulo", "responsavel", "solicitante")):
            return None  # pendência mal formada nunca é adivinhada
        req = {k: d[k] for k in ("titulo", "solicitante", "responsavel", "prioridade")}
        return Proposta("A-06", "criar_tarefa", f"Pendência criada: {d['titulo']}", tarefa=req)
