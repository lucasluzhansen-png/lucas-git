"""Agente Auditor de baixas (AU-01): avisa o dentista quando o paciente foi atendido e os procedimentos não foram baixados. Só avisa."""
from hansen.agentes.base import Proposta


class Auditoria:
    nome = "auditoria"
    tipos = {"baixa_pendente"}

    def tratar(self, tipo: str, texto: str = "", dados: dict | None = None) -> Proposta | None:
        if tipo == "baixa_pendente":
            return Proposta("AU-01", "baixa_pendente", "Marcar o procedimento como feito e escrever o que foi feito; se houve prótese, abrir a OS.")
        return None
