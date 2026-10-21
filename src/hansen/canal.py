"""Canal de mensagens. Hoje só simulado: envio real (WhatsApp Business) exige conta, credenciais e base legal LGPD."""
from datetime import datetime
from typing import Protocol

from hansen.ledger import LedgerManager
from hansen.yaml_parser import POP

PRIV = {"dado_sensivel": True, "base_legal_lgpd": "execucao_contrato", "retencao_anos": 5}
SILENCIO_ATE_H = 7  # ASSUMIDO: "madrugada" = 0h-7h (A-06 silencia alertas até 07h). Confirmar com a clínica.


class Canal(Protocol):
    def enviar(self, destino: str, texto: str) -> None: ...


class CanalSimulado:
    def __init__(self):
        self.enviadas: list[tuple[str, str]] = []

    def enviar(self, destino: str, texto: str) -> None:
        self.enviadas.append((destino, texto))


class Notificador:
    def __init__(self, canal: Canal, ledger: LedgerManager, pop_r02: POP):
        self.canal, self.ledger = canal, ledger
        self._p = {r.efeito: r.parametros for r in pop_r02.regras_de_decisao if r.efeito}["adiar_envio"]

    def na_janela(self, agora: datetime) -> bool:
        return agora.weekday() < 5 and self._p["hora_inicio"] <= agora.hour < self._p["hora_fim"]

    def lembrete_paciente(self, nome: str, destino: str, consulta_em: datetime, agora: datetime) -> str:
        """Tom formal; só em seg-sex no horário comercial (R-02)."""
        if not self.na_janela(agora):
            return self._log("adiar_lembrete", destino, "fora_da_janela")
        texto = (f"Prezado(a) Senhor(a) {nome}, lembramos da sua consulta em "
                 f"{consulta_em:%d/%m às %H:%M}. Poderia confirmar a sua presença? Atenciosamente, Hansen Odontologia.")
        self.canal.enviar(destino, texto)
        return self._log("enviar_lembrete", destino, "enviado")

    def alertar_rt(self, titulo: str, destino: str, agora: datetime) -> str:
        """Alerta interno ao RT. Madrugada: fica registado, mas silenciado até 07h (A-06)."""
        if agora.hour < SILENCIO_ATE_H:
            return self._log("alerta_rt", destino, "silenciado_ate_07h")
        self.canal.enviar(destino, f"ALERTA: {titulo}")
        return self._log("alerta_rt", destino, "enviado")

    def _log(self, acao, destino, estado) -> str:
        self.ledger.registar(
            pop_id="R-02" if "lembrete" in acao else "A-06",
            ator={"type": "agente_ia", "id": "notificador", "papel": "comunicacao"},
            acao=acao, entrada={"destino": destino}, saida={"estado": estado}, privacidade=PRIV,
        )
        return estado
