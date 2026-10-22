"""Qualidade dos cadastros do Clinus: quem está sem telefone válido ou sem data de nascimento.
Terminal: só contagens. Planilha local (saida/cadastros/, fora do Git): lista com nomes para a Recepção corrigir."""
import csv
import sys
from collections import Counter
from pathlib import Path

from hansen.clinus import _digitos, carregar_backup
from hansen.rotina_comercial import _data


def analisar(clinus) -> dict:
    ativos = [p for p in clinus.por_id.values() if p["ativo"]]
    trabalho = [p for p in ativos if not p["historico"]]  # base importada sem ação humana fica de fora da lista
    linhas = []
    for p in trabalho:
        tel = _digitos(p["tel"])
        motivos = []
        if not p["tel"]:
            motivos.append("sem telefone")
        elif not tel:
            motivos.append("telefone incompleto")
        if not _data(p["nascimento"]):
            motivos.append("sem nascimento")
        if motivos:
            linhas.append({"nome": p["nome"], "problema": " + ".join(motivos), "ultima_acao": (p["ultima_acao"] or "")[:10], "id": p["id"]})
    cont = Counter(m for l in linhas for m in l["problema"].split(" + "))
    return {
        "ativos": len(ativos), "historico": len(ativos) - len(trabalho), "em_trabalho": len(trabalho),
        "com_problema": len(linhas), "contagem": dict(cont), "linhas": sorted(linhas, key=lambda l: l["ultima_acao"], reverse=True),
    }


def gravar_planilha(linhas: list[dict], destino: Path) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    with open(destino, "w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig e ';' abrem direto no Excel brasileiro
        w = csv.DictWriter(f, fieldnames=["nome", "problema", "ultima_acao", "id"], delimiter=";")
        w.writeheader()
        w.writerows(linhas)
    return destino


def resumo(r: dict) -> str:
    c = r["contagem"]
    return "\n".join([
        f"Pacientes ativos: {r['ativos']} (base histórica importada, ignorada: {r['historico']}; em trabalho: {r['em_trabalho']})",
        f"Com cadastro a corrigir: {r['com_problema']} de {r['em_trabalho']}",
        f"  sem telefone: {c.get('sem telefone', 0)} | telefone incompleto: {c.get('telefone incompleto', 0)} | sem nascimento: {c.get('sem nascimento', 0)}",
    ])


if __name__ == "__main__":  # python -m hansen.cadastros backup.json
    if len(sys.argv) < 2:
        raise SystemExit("Uso: python -m hansen.cadastros backup.json")
    try:
        r = analisar(carregar_backup(Path(sys.argv[1])))
    except FileNotFoundError:
        raise SystemExit(f"Arquivo não encontrado: {sys.argv[1]}")
    except (ValueError, KeyError) as e:
        raise SystemExit(f"Não consegui ler o backup: {e}")
    print(resumo(r))
    if r["linhas"]:
        arq = gravar_planilha(r["linhas"], Path("saida") / "cadastros" / "cadastros_a_corrigir.csv")
        print(f"\nLista com nomes (uso interno da Recepção, não envie a ninguém): {arq.resolve()}")
