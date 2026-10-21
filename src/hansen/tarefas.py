"""Tarefas (POP A-06): agentes cobram humanos; o RT sempre pode vetar. Regras vêm do YAML."""
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from hansen.ledger import LedgerManager
from hansen.yaml_parser import POP

PRIV = {"dado_sensivel": False, "base_legal_lgpd": "obrigacao_legal", "retencao_anos": 5}


@dataclass
class Tarefa:
    id: int
    titulo: str
    solicitante: str
    responsavel: str
    prioridade: str  # vermelha | amarela | verde
    criada_em: datetime
    estado: str = "aberta"  # aberta | escalada | fechada | vetada
    evidencia: str | None = None
    alerta_pendente: bool = False


class TarefaManager:
    def __init__(self, ledger: LedgerManager, pop_a06: POP, agora: Callable[[], datetime] = lambda: datetime.now(timezone.utc), arquivo: Path | None = None):
        self.ledger, self.agora, self.arquivo = ledger, agora, arquivo
        self.tarefas: dict[int, Tarefa] = {}
        self._carregar()
        regra = {r.efeito: r for r in pop_a06.regras_de_decisao}
        self._limite = timedelta(minutes=regra["escalar"].parametros["minutos"])

    def _carregar(self):
        if self.arquivo and self.arquivo.exists():
            for d in json.loads(self.arquivo.read_text(encoding="utf-8")):
                d["criada_em"] = datetime.fromisoformat(d["criada_em"])
                self.tarefas[d["id"]] = Tarefa(**d)

    def salvar(self):
        if self.arquivo:
            dados = [{**asdict(t), "criada_em": t.criada_em.isoformat()} for t in self.tarefas.values()]
            self.arquivo.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")

    def alertas_pendentes(self) -> list[Tarefa]:
        return [t for t in self.tarefas.values() if t.alerta_pendente]

    def alerta_enviado(self, id: int):
        self.tarefas[id].alerta_pendente = False
        self.salvar()

    def _log(self, acao, ator, t: Tarefa, resultado="sucesso", **saida):
        self.ledger.registar(
            pop_id="A-06", ator=ator, acao=acao, resultado=resultado,
            entrada={"tarefa": t.id, "titulo": t.titulo}, saida=saida, privacidade=PRIV,
        )

    def criar(self, titulo, solicitante, responsavel, prioridade="verde") -> Tarefa:
        t = Tarefa(len(self.tarefas) + 1, titulo, solicitante, responsavel, prioridade, self.agora())
        self.tarefas[t.id] = t
        self.salvar()
        self._log("criar_tarefa", {"type": "agente_ia", "id": "agente_pendencias", "papel": "rotina"}, t, responsavel=responsavel)
        return t

    def escalar_vencidas(self) -> list[Tarefa]:
        """Vermelhas abertas há mais que o limite do YAML → alerta ao RT (a chamada em si é humana/telefone)."""
        novas = [
            t for t in self.tarefas.values()
            if t.estado == "aberta" and t.prioridade == "vermelha" and self.agora() - t.criada_em >= self._limite
        ]
        for t in novas:
            t.estado, t.alerta_pendente = "escalada", True
            self._log("escalar_para_rt", {"type": "agente_ia", "id": "agente_pendencias", "papel": "rotina"}, t, notificado="rt")
        self.salvar()
        return novas

    def fechar(self, id: int, por: str, evidencia: str | None) -> bool:
        t = self.tarefas[id]
        ator = {"type": "humano", "id": por, "papel": "equipe"}
        if t.estado in ("fechada", "vetada"):
            return False
        if not evidencia:  # regra do YAML: fecho sem evidência é rejeitado
            self._log("fechar_tarefa", ator, t, resultado="falha", motivo="sem_evidencia")
            return False
        t.estado, t.evidencia = "fechada", evidencia
        self.salvar()
        self._log("fechar_tarefa", ator, t, notificado=t.solicitante)  # notifica sempre o solicitante
        return True

    def vetar(self, id: int, por: str, papel: str, motivo: str) -> bool:
        """Só o RT veta. Tentativas de outros papéis ficam registradas como falha."""
        t = self.tarefas[id]
        ator = {"type": "humano", "id": por, "papel": papel}
        if papel != "rt":
            self._log("vetar_tarefa", ator, t, resultado="falha", motivo="sem_autoridade")
            return False
        t.estado = "vetada"
        self.salvar()
        self._log("vetar_tarefa", ator, t, motivo=motivo)
        return True
