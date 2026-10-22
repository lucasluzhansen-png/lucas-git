"""Agente Jornada (JN-01): acompanha o paciente do plano aprovado à alta e sugere o contato. Nunca decide nada clínico."""
from hansen.agentes.base import Proposta


class Jornada:
    nome = "jornada"
    tipos = {"iniciar_tratamento", "tratamento_parado", "retorno_alta"}

    def tratar(self, tipo: str, texto: str = "", dados: dict | None = None) -> Proposta | None:
        d = dados or {}
        dias = d.get("dias", "?")
        det = {"iniciar_tratamento": f"Plano aprovado há {dias} dias sem início agendado.",
               "tratamento_parado": f"Tratamento parado há {dias} dias sem consulta marcada.",
               "retorno_alta": f"Alta há {dias} dias sem retorno marcado."}.get(tipo)
        return Proposta("JN-01", tipo, det) if det else None
