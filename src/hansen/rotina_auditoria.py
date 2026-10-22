"""Rotina do auditor de baixas (AU-01): consulta atendida cuja ficha de procedimentos continua pendente, 60 min depois do fim.
v1 lê a agenda do Clinus (status "atendida" + fichaPendente). Tarefa se fecha sozinha quando a pendência some."""
from dataclasses import dataclass
from datetime import datetime, timedelta

from hansen.clinus import ClinusDados
from hansen.maestro import Maestro
from hansen.rotina_sala_espera import _inicio
from hansen.sincronizar import Chaves

ATENDIDO = {"atendida", "atendido", "concluido", "realizado", "finalizado"}


@dataclass
class ItemA:
    tipo: str
    resultado: str


def rodar(m: Maestro, clinus: ClinusDados, agora: datetime) -> list[ItemA]:
    chaves = Chaves(m, "auditoria")
    espera = timedelta(minutes=next(r.parametros["minutos_apos_atendimento"] for r in m.pops["AU-01"].regras_de_decisao))
    itens: list[ItemA] = []
    for e in clinus.agenda:
        ini = _inicio(e)
        if not ini or (e.get("status") or "").lower() not in ATENDIDO or not e.get("fichaPendente"):
            continue
        if agora < ini + timedelta(minutes=int(e.get("dur") or 30)) + espera:
            continue
        chave = f"baixa|{e.get('id')}"
        chaves.marcar_ativa(chave)
        if chave in chaves.mapa:
            continue
        d = m.processar("baixa_pendente", dados={"agora": agora.isoformat(), "ref_txt": f"consulta {e.get('id')}"})
        chaves.registrar(chave, d.tarefa_id)
        itens.append(ItemA("baixa_pendente", f"{d.acao} (tarefa #{d.tarefa_id})"))
    chaves.fechar_resolvidas()
    return itens
