"""Rotina do laboratório (LB-01): lê as OS do Clinus (store lab_os) e cobra prazos, conferência na chegada e problemas.
Só acompanha prazo e etapa; NUNCA avalia a peça. Tarefas se fecham sozinhas quando a OS avança no Clinus."""
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from hansen.caminhos import pasta_saida
from hansen.clinus import ClinusDados, carregar_backup, data_br
from hansen.maestro import Maestro
from hansen.sincronizar import Chaves

CONCLUIDAS = ("instalado", "entregue", "cancelada", "cancelado")
NO_LAB = ("enviado", "producao")  # a peça está com o laboratório


@dataclass
class ItemL:
    nome: str
    resultado: str


def _p(m: Maestro, chave: str) -> int:
    return next(r.parametros[chave] for r in m.pops["LB-01"].regras_de_decisao if chave in r.parametros)


def _prazo(o: dict):
    return data_br(o.get("entrega") or o.get("prazo") or o.get("dataPrevista") or o.get("previsao"))


def rodar(m: Maestro, clinus: ClinusDados, agora: datetime) -> list[ItemL]:
    arq = m.tarefas.arquivo.parent / "laboratorio.json" if m.tarefas.arquivo else None
    feitos: set[str] = set(json.loads(arq.read_text(encoding="utf-8"))) if arq and arq.exists() else set()
    chaves = Chaves(m, "laboratorio")
    hoje = agora.date()
    itens: list[ItemL] = []
    base = {"agora": agora.isoformat()}

    def sugerir(chave, acao, o, detalhe):
        chaves.marcar_ativa(chave)
        if chave in feitos:
            return
        num = o.get("numero") or o.get("id")
        d = m.processar("os_lab", dados={**base, "ref_txt": f"OS {num}", "acao": acao, "detalhe": detalhe})
        feitos.add(chave)
        chaves.registrar(chave, d.tarefa_id)
        itens.append(ItemL(f"OS {num} · {o.get('lab') or 'laboratório?'} · {o.get('pac') or o.get('paciente') or ''}".strip(" ·"), f"{detalhe} (tarefa #{d.tarefa_id})"))

    for o in sorted(clinus.lab_os, key=lambda o: str(o.get("numero") or o.get("id"))):
        etapa = o.get("etapa") or o.get("status") or ""
        if etapa in CONCLUIDAS:
            continue
        num, lab = o.get("numero") or o.get("id"), o.get("lab") or "laboratório não registado"
        rot = f"OS {num} · {lab}"
        prazo = _prazo(o)

        if o.get("problema") or etapa == "problema":
            sugerir(f"os|{num}|problema", "os_problema", o, f"{rot}: marcada com problema")

        if etapa in NO_LAB:
            enviado = data_br((o.get("marcos") or {}).get("enviado")) or data_br(o.get("entrada"))
            if not prazo:
                sugerir(f"os|{num}|semprazo", "registrar_prazo_lab", o, f"{rot}: enviada sem prazo de entrega registado")
            elif prazo < hoje:
                sugerir(f"os|{num}|atrasada", "cobrar_lab", o, f"{rot}: prazo era {prazo:%d/%m} ({(hoje - prazo).days} dias de atraso)")
            elif (prazo - hoje).days <= _p(m, "dias_aviso_prazo"):
                sugerir(f"os|{num}|vencendo", "confirmar_prazo_lab", o, f"{rot}: prazo em {prazo:%d/%m}")
            if enviado and (hoje - enviado).days > _p(m, "sla_dias") and not (prazo and prazo < hoje):
                sugerir(f"os|{num}|sla", "sla_lab", o, f"{rot}: com o laboratório há {(hoje - enviado).days} dias (padrão: até {_p(m, 'sla_dias')})")

        if etapa == "retornou" and not o.get("antiRefacaoEm"):
            chegou = data_br((o.get("marcos") or {}).get("retornou"))
            if chegou and (hoje - chegou).days >= _p(m, "dias_conferencia"):
                sugerir(f"os|{num}|conferir", "conferir_peca", o, f"{rot}: retornou em {chegou:%d/%m} e a conferência não foi registada")

    feitos &= chaves.ativas
    chaves.fechar_resolvidas()
    if arq:
        arq.write_text(json.dumps(sorted(feitos)), encoding="utf-8")
    return itens


def formatar(itens: list[ItemL]) -> str:
    return "\n".join(["OS / laboratório / paciente  →  o que aconteceu"] + [f"{i.nome}  →  {i.resultado}" for i in itens]) if itens else "Nenhuma OS de laboratório pede atenção hoje."


if __name__ == "__main__":  # python -m hansen.rotina_laboratorio backup.json [AAAA-MM-DDTHH:MM|agora]
    from hansen.canal import CanalSimulado, Notificador
    from hansen.ledger import LedgerManager
    from hansen.yaml_parser import carregar_todos

    if len(sys.argv) < 2:
        raise SystemExit("Uso: python -m hansen.rotina_laboratorio backup.json [AAAA-MM-DDTHH:MM|agora]")
    base_dir = pasta_saida() / "laboratorio"
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
