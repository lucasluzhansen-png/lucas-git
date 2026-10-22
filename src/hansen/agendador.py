"""Agendador: relógio do sistema. tick() é chamado a cada minuto por cron/loop; nada fica preso em memória."""
import time
from datetime import datetime, timezone

from hansen.canal import SILENCIO_ATE_H, Notificador
from hansen.tarefas import TarefaManager


class Agendador:
    def __init__(self, tarefas: TarefaManager, notificador: Notificador, destino_rt: str):
        self.tarefas, self.notificador, self.destino_rt = tarefas, notificador, destino_rt

    def tick(self, agora: datetime) -> list[int]:
        """Escala vermelhas vencidas e entrega alertas ao RT; na madrugada, retém até 07h."""
        novas = self.tarefas.escalar_vencidas()
        for t in novas:  # registra o silenciamento uma vez só
            if agora.hour < SILENCIO_ATE_H:
                self.notificador.alertar_rt(t.titulo, self.destino_rt, agora)
        enviados = []
        for t in self.tarefas.alertas_pendentes():
            if agora.hour >= SILENCIO_ATE_H:
                self.notificador.alertar_rt(t.titulo, self.destino_rt, agora)
                self.tarefas.alerta_enviado(t.id)
                enviados.append(t.id)
        return enviados

    def rodar(self, intervalo_s: int = 60):  # pragma: no cover
        while True:
            self.tick(datetime.now(timezone.utc).astimezone())
            time.sleep(intervalo_s)
