"""Rotina da sala de espera (R-01): paciente que chegou e espera mais de 15 minutos após o horário marcado.
Só avisa a Recepção (ir até o paciente, oferecer água, informar a previsão) e lembra de avisar o paciente seguinte.
Depende de o Clinus marcar a chegada na agenda (status "chegou"/"aguardando"). Tarefas se fecham sozinhas quando o atendimento começa."""
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from hansen.caminhos import pasta_saida
from hansen.clinus import ABERTOS, ClinusDados, carregar_backup
from hansen.maestro import Maestro
from hansen.sincronizar import Chaves

CHEGOU = {"chegou", "aguardando", "na_recepcao", "em_espera", "checkin", "check-in"}


@dataclass
class ItemS:
    tipo: str
    resultado: str


def _p(m: Maestro, chave: str) -> int:
    return next(r.parametros[chave] for r in m.pops["R-01"].regras_de_decisao if chave in r.parametros)


def _inicio(e: dict) -> datetime | None:
    try:
        return datetime.fromisoformat(f"{e['data']}T{e.get('hora') or '00:00'}")
    except (KeyError, ValueError):
        return None


def rodar(m: Maestro, clinus: ClinusDados, agora: datetime) -> list[ItemS]:
    chaves = Chaves(m, "sala_espera")
    itens: list[ItemS] = []
    limite = timedelta(minutes=_p(m, "minutos_atraso"))
    janela = timedelta(minutes=_p(m, "janela_proximo_min"))
    hoje = [(e, _inicio(e)) for e in clinus.agenda if str(e.get("data")) == agora.date().isoformat()]
    hoje = [(e, i) for e, i in hoje if i]

    def sugerir(chave, tipo, ref, **extra):
        chaves.marcar_ativa(chave)
        if chave in chaves.mapa:
            return
        d = m.processar(tipo, dados={"agora": agora.isoformat(), "ref_txt": ref, **extra})
        chaves.registrar(chave, d.tarefa_id)
        itens.append(ItemS(tipo, f"{d.acao} (tarefa #{d.tarefa_id})"))

    for e, ini in hoje:
        if (e.get("status") or "").lower() not in CHEGOU or agora - ini < limite:
            continue
        sugerir(f"espera|{e.get('id')}", "sala_espera", f"consulta {e.get('id')}", minutos=int((agora - ini).total_seconds() // 60))
        # o paciente seguinte (ainda não chegou, consulta na próxima hora) recebe o aviso de retenção
        seguintes = sorted((i, x) for x, i in hoje if x is not e and (x.get("status") or "").lower() in ABERTOS and agora <= i <= agora + janela)
        if seguintes:
            sugerir(f"proximo|{e.get('id')}|{seguintes[0][1].get('id')}", "avisar_proximo", f"consulta {seguintes[0][1].get('id')}")
    chaves.fechar_resolvidas()
    return itens


def formatar(itens: list[ItemS]) -> str:
    return "\n".join(f"{i.tipo}  →  {i.resultado}" for i in itens) if itens else "Ninguém esperando além do limite."


if __name__ == "__main__":  # python -m hansen.rotina_sala_espera backup.json [AAAA-MM-DDTHH:MM|agora]
    from hansen.canal import CanalSimulado, Notificador
    from hansen.ledger import LedgerManager
    from hansen.yaml_parser import carregar_todos

    if len(sys.argv) < 2:
        raise SystemExit("Uso: python -m hansen.rotina_sala_espera backup.json [AAAA-MM-DDTHH:MM|agora]")
    base_dir = pasta_saida() / "sala_espera"
    base_dir.mkdir(parents=True, exist_ok=True)
    led = LedgerManager(base_dir / "ledger")
    maestro = Maestro(led, estado=base_dir / "estado", notificador=Notificador(CanalSimulado(), led, carregar_todos()["R-02"]))
    agora = datetime.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2] != "agora" else datetime.now()
    try:
        dados = carregar_backup(Path(sys.argv[1]))
    except FileNotFoundError:
        raise SystemExit(f"Arquivo não encontrado: {sys.argv[1]}")
    except (ValueError, KeyError) as e:
        raise SystemExit(f"Não consegui ler o backup: {e}")
    print(formatar(rodar(maestro, dados, agora)))
    print(f"\nLedger íntegro: {led.verificar()}")
