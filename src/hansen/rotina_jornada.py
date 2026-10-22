"""Rotina da jornada do paciente (JN-01): do plano aprovado à alta. Só sugere; a Recepção revisa e envia.
Sinais vêm do Clinus: orçamento aprovado, agenda (consultas) e encerramento. Tarefas se fecham sozinhas quando o paciente é agendado."""
import json
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from hansen.caminhos import pasta_saida
from hansen.clinus import ClinusDados, carregar_backup, data_br
from hansen.maestro import Maestro
from hansen.sincronizar import Chaves

ATENDIDO = ("concluido", "realizado", "atendido", "finalizado")
MARCADA = ("agendado", "confirmado")


@dataclass
class ItemJ:
    tipo: str
    nome: str
    resultado: str


def _p(m: Maestro, chave: str) -> int:
    return next(r.parametros[chave] for r in m.pops["JN-01"].regras_de_decisao if chave in r.parametros)


def _dia(texto) -> date | None:
    return data_br(str(texto or "")[:10])


def rodar(m: Maestro, clinus: ClinusDados, agora: datetime) -> list[ItemJ]:
    arq = m.tarefas.arquivo.parent / "jornada.json" if m.tarefas.arquivo else None
    feitos: set[str] = set(json.loads(arq.read_text(encoding="utf-8"))) if arq and arq.exists() else set()
    chaves = Chaves(m, "jornada")
    hoje = agora.date()
    itens: list[ItemJ] = []
    base = {"agora": agora.isoformat()}
    futuras: set = set()
    ultima_ate_hoje: dict = {}  # paciente → última consulta atendida (ou marcada no passado e não cancelada)
    for e in clinus.agenda:
        dia, pid, st = _dia(e.get("data")), e.get("pacId"), (e.get("status") or "")
        if not dia or not pid:
            continue
        if dia >= hoje and st in MARCADA:
            futuras.add(pid)
        elif dia <= hoje and st in ATENDIDO + MARCADA:
            ultima_ate_hoje[pid] = max(dia, ultima_ate_hoje.get(pid, dia))
    com_retorno = {r.get("pacId") for r in clinus.retornos if (r.get("status") or "") != "concluido"}

    def sugerir(tipo, p, dias):
        chave = f"{tipo}|{p['id']}"
        chaves.marcar_ativa(chave)
        if chave in feitos:
            return
        d = m.processar(tipo, dados={**base, "ref": p["id"], "dias": dias})
        feitos.add(chave)
        chaves.registrar(chave, d.tarefa_id)
        itens.append(ItemJ(tipo, p["nome"], f"{d.acao} (tarefa #{d.tarefa_id}, {dias} dias)"))

    for p in sorted((p for p in clinus.por_id.values() if p["ativo"] and not p["historico"]), key=lambda p: str(p["id"])):
        pid = p["id"]
        aprov = _dia(p["aprovado_em"])
        if p["encerrado"]:
            alta = _dia(p["encerrado_em"])
            if alta and pid not in futuras and pid not in com_retorno and (hoje - alta).days >= _p(m, "dias_alta"):
                sugerir("retorno_alta", p, (hoje - alta).days)
            continue
        if not aprov or pid in futuras:
            continue
        ult = ultima_ate_hoje.get(pid)
        if ult and ult >= aprov:  # tratamento em andamento
            if (hoje - ult).days >= _p(m, "dias_parado_tratamento"):
                sugerir("tratamento_parado", p, (hoje - ult).days)
        elif (hoje - aprov).days >= _p(m, "dias_inicio"):
            sugerir("iniciar_tratamento", p, (hoje - aprov).days)

    feitos &= chaves.ativas
    chaves.fechar_resolvidas()
    if arq:
        arq.write_text(json.dumps(sorted(feitos)), encoding="utf-8")
    return itens


def formatar(itens: list[ItemJ]) -> str:
    return "\n".join(["paciente  →  o que aconteceu"] + [f"{i.nome}  →  {i.resultado}" for i in itens]) if itens else "Nenhum paciente parado na jornada hoje."


if __name__ == "__main__":  # python -m hansen.rotina_jornada backup.json [AAAA-MM-DDTHH:MM|agora]
    from hansen.canal import CanalSimulado, Notificador
    from hansen.ledger import LedgerManager
    from hansen.yaml_parser import carregar_todos

    if len(sys.argv) < 2:
        raise SystemExit("Uso: python -m hansen.rotina_jornada backup.json [AAAA-MM-DDTHH:MM|agora]")
    base_dir = pasta_saida() / "jornada"
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
