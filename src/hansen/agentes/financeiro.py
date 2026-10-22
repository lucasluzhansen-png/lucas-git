"""Agente Financeiro (FN-01): sugere lembretes de vencimento e cobranças de parcelas. Só sugere; a Recepção revisa e envia."""
from hansen.agentes.base import Proposta


class Financeiro:
    nome = "financeiro"
    tipos = {"parcela_atrasada", "parcela_a_vencer"}

    def tratar(self, tipo: str, texto: str = "", dados: dict | None = None) -> Proposta | None:
        d = dados or {}
        if tipo == "parcela_atrasada":
            return Proposta("FN-01", "cobrar_atraso",
                            f"{d.get('n', '?')} parcela(s) em aberto desde {d.get('desde', '?')} ({d.get('dias', '?')} dias de atraso). Contato cordial, sem ameaça nem constrangimento.")
        if tipo == "parcela_a_vencer":
            return Proposta("FN-01", "lembrar_vencimento", f"Parcela vence em {d.get('vence', '?')}. Lembrete cordial.")
        return None
