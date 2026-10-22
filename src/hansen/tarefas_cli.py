"""Lista e fecha tarefas de uma pasta de estado. Uso:
  python -m hansen.tarefas_cli comercial listar          (ou: financeiro, hoje)
  python -m hansen.tarefas_cli comercial fechar 3 "contato feito em 22/10"
Fechar exige evidência (texto) e fica registado no ledger."""
import sys
from pathlib import Path

from hansen.caminhos import pasta_saida

from hansen.ledger import LedgerManager
from hansen.tarefas import TarefaManager
from hansen.yaml_parser import carregar_todos


def abrir(base: Path) -> TarefaManager:
    return TarefaManager(LedgerManager(base / "ledger"), carregar_todos()["A-06"], arquivo=base / "estado" / "tarefas.json")


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] not in ("listar", "fechar"):
        print(__doc__)
        return 1
    base = Path(argv[0])
    if not base.exists() and (pasta_saida() / argv[0]).exists():  # aceita só o nome: comercial, financeiro, hoje
        base = pasta_saida() / argv[0]
    if not (base / "estado" / "tarefas.json").exists():
        print(f"Nenhuma tarefa em {base}.")
        return 1
    tm = abrir(base)
    if argv[1] == "listar":
        for t in tm.tarefas.values():
            if t.estado in ("aberta", "escalada"):
                print(f"#{t.id:<3} [{t.prioridade:8}] {t.responsavel:9} {t.titulo[:90]}")
        return 0
    if len(argv) < 4 or not argv[2].isdigit() or int(argv[2]) not in tm.tarefas:
        print('Uso: fechar NUMERO "evidência"  (ex.: fechar 3 "contato feito em 22/10")')
        return 1
    ok = tm.fechar(int(argv[2]), "lucas", argv[3])
    print("Tarefa fechada." if ok else "Não foi possível fechar (já fechada, vetada ou sem evidência).")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
