"""Agente Sala de espera (R-01): avisa a Recepção quando o paciente espera mais de 15 minutos. Só avisa."""
from hansen.agentes.base import Proposta


class SalaEspera:
    nome = "sala_espera"
    tipos = {"sala_espera", "avisar_proximo"}

    def tratar(self, tipo: str, texto: str = "", dados: dict | None = None) -> Proposta | None:
        d = dados or {}
        if tipo == "sala_espera":
            return Proposta("R-01", "paciente_esperando", f"Paciente aguardando há {d.get('minutos', '?')} minutos.")
        if tipo == "avisar_proximo":
            return Proposta("R-01", "avisar_proximo", "Avisar o paciente seguinte da retenção.")
        return None
