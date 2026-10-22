"""Liga cada tarefa à SITUAÇÃO do Clinus que a originou (a "chave") e a fecha sozinha quando a situação deixa de existir
(parcela paga, conta paga, caixa fechado, guia que avançou...). Assim o Maestro não cobra o que já foi resolvido."""
import json
from pathlib import Path

from hansen.maestro import Maestro


class Chaves:
    def __init__(self, m: Maestro, nome: str):
        self.m = m
        self.arq: Path | None = m.tarefas.arquivo.parent / f"chaves_{nome}.json" if m.tarefas.arquivo else None
        self.mapa: dict[str, int] = {}
        if self.arq and self.arq.exists():
            self.mapa = {k: int(v) for k, v in json.loads(self.arq.read_text(encoding="utf-8")).items()}
        self.ativas: set[str] = set()

    def marcar_ativa(self, chave: str):
        self.ativas.add(chave)

    def registrar(self, chave: str, tarefa_id: int | None):
        if tarefa_id:
            self.mapa[chave] = tarefa_id

    def fechar_resolvidas(self) -> list[int]:
        """Fecha as tarefas cuja situação não está mais ativa. Chame no FIM da rotina, depois de marcar todas as situações ativas."""
        fechadas = []
        for chave, tid in list(self.mapa.items()):
            if chave in self.ativas:
                continue
            if self.m.tarefas.resolver_automatico(tid, "Resolvida no Clinus: a situação não existe mais"):
                fechadas.append(tid)
            del self.mapa[chave]
        if self.arq:
            self.arq.write_text(json.dumps(self.mapa), encoding="utf-8")
        self.m.resolvidas_auto += len(fechadas)
        return fechadas
