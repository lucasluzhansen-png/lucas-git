"""Maestro com vida própria: roda a cada poucos minutos (agendado no Windows), atualiza os dados e COBRA por notificação.
Uso: python -m hansen.maestro_vivo --perfil lucas|recepcao [--agora AAAA-MM-DDTHH:MM] [--sem-aviso]
Configuração opcional em maestro.config.json (fora do Git): {"pastas_backup": ["C:\\\\Users\\\\Lucas\\\\OneDrive\\\\ClinusBackup"]}"""
import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Callable

from hansen import hoje
from hansen.cobrador import Aviso, decidir
from hansen.notificacao import notificar_windows
from hansen.tarefas import ler_tarefas
from hansen.yaml_parser import carregar_todos

PADROES = ("hansen-rpg-backup-*.json", "clinus-backup-*.json")  # backup manual e backup automático da pasta de nuvem do Clinus


def achar_backup(pastas: list[Path]) -> Path | None:
    cand = [f for pasta in pastas if Path(pasta).exists() for pad in PADROES for f in Path(pasta).glob(pad)]
    return max(cand, key=lambda f: f.stat().st_mtime) if cand else None


def carregar_config(arquivo: Path = Path("maestro.config.json")) -> dict:
    cfg = json.loads(arquivo.read_text(encoding="utf-8")) if arquivo.exists() else {}
    cfg.setdefault("pastas_backup", [str(Path.home() / "Downloads")])
    return cfg


def tick(perfil: str, agora: datetime, base: Path, pastas: list[Path], notificar: Callable[[str, str], object] = notificar_windows) -> list[Aviso]:
    """Um ciclo: (1) reprocessa o backup se houver arquivo novo ou passou o intervalo; (2) decide e envia os avisos devidos."""
    pops = carregar_todos()
    pop = pops["MA-01"]
    estado_arq = base / "estado" / f"cobrador_{perfil}.json"
    estado = json.loads(estado_arq.read_text(encoding="utf-8")) if estado_arq.exists() else {}
    backup = achar_backup(pastas)
    idade = None
    if backup:
        idade = (agora - datetime.fromtimestamp(backup.stat().st_mtime)).total_seconds() / 3600
        ref = f"{backup.name}|{backup.stat().st_mtime}"
        ultimo = estado.get("processado")
        min_intervalo = next(r.parametros["atualizar_min"] for r in pop.regras_de_decisao if "atualizar_min" in r.parametros)
        velho = not ultimo or (agora - datetime.fromisoformat(ultimo["quando"])).total_seconds() / 60 >= min_intervalo
        if not ultimo or ultimo["ref"] != ref or velho:
            try:
                hoje.executar(backup, agora, base)
                estado["processado"] = {"ref": ref, "quando": agora.isoformat()}
            except (ValueError, KeyError, OSError) as e:  # backup quebrado não pode derrubar a cobrança
                estado["erro"] = f"{agora:%d/%m %H:%M} {type(e).__name__}"
    avisos = decidir(pop, ler_tarefas(base / "estado" / "tarefas.json"), perfil, agora, estado, idade)
    for a in avisos:
        notificar(a.titulo, a.texto)
    estado_arq.parent.mkdir(parents=True, exist_ok=True)
    estado_arq.write_text(json.dumps(estado), encoding="utf-8")
    return avisos


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Maestro com vida própria")
    ap.add_argument("--perfil", choices=["lucas", "recepcao"], required=True)
    ap.add_argument("--agora", help="simulação: AAAA-MM-DDTHH:MM")
    ap.add_argument("--sem-aviso", action="store_true", help="só mostra no terminal, sem notificação do Windows")
    a = ap.parse_args()
    cfg = carregar_config()
    agora = datetime.fromisoformat(a.agora) if a.agora else datetime.now()
    saida = tick(a.perfil, agora, Path("saida") / "hoje", [Path(p) for p in cfg["pastas_backup"]],
                 (lambda t, x: print(f"[aviso] {t}: {x}")) if a.sem_aviso else notificar_windows)
    if not saida:
        print("Nada a cobrar agora.")
