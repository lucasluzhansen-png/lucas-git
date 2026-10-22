"""Rotina financeira diária (FN-01): lê as parcelas do backup do Clinus e aciona o agente Financeiro.
Só sugere: cada sugestão vira tarefa para a Recepção, com cartão no painel (nome, texto cordial e link do WhatsApp)."""
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from hansen.clinus import ClinusDados, carregar_backup, situacao_parcelas
from hansen.maestro import Maestro


@dataclass
class ItemF:
    tipo: str
    nome: str
    resultado: str


def _params(m: Maestro, efeito: str) -> dict:
    return next(r.parametros for r in m.pops["FN-01"].regras_de_decisao if r.efeito == efeito)


def _ddmm(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}"


def rodar(m: Maestro, clinus: ClinusDados, agora: datetime) -> list[ItemF]:
    arq = m.tarefas.arquivo.parent / "financeiro.json" if m.tarefas.arquivo else None
    estado = json.loads(arq.read_text(encoding="utf-8")) if arq and arq.exists() else {}
    avisos: dict[str, str] = estado.get("cobrancas", {})
    feitos: set[str] = set(estado.get("feitos", []))
    hoje = agora.date()
    pa, pv = _params(m, "cobrar_atraso"), _params(m, "lembrar_vencimento")
    itens: list[ItemF] = []
    usadas = sum(1 for v in avisos.values() if v == hoje.isoformat())
    base = {"agora": agora.isoformat()}

    pacs = sorted((p for p in clinus.por_id.values() if p["ativo"] and p["parcelas"]), key=lambda p: str(p["id"]))
    cobrar, lembrar = [], []
    for p in pacs:
        sit = situacao_parcelas(p["parcelas"], p["pago"], hoje)
        atras = [x for x in sit if x["atraso"] >= pa["dias_atraso"]]
        if atras:
            cobrar.append((max(x["atraso"] for x in atras), p, atras))
        for x in sit:
            if not x["quitada"] and x["dias_ate_vencer"] is not None and 0 <= x["dias_ate_vencer"] <= pv["dias_antes"]:
                lembrar.append((p, x))

    for dias, p, atras in sorted(cobrar, key=lambda c: -c[0]):  # maiores atrasos primeiro
        ult = avisos.get(p["id"])
        if ult and (hoje - datetime.fromisoformat(ult).date()).days < pa["intervalo_cobranca_dias"]:
            continue
        if usadas >= pa["maximo_por_dia"]:
            itens.append(ItemF("atraso", p["nome"], "adiado: limite diário de sugestões atingido"))
            continue
        d = m.processar("parcela_atrasada", dados={**base, "ref": p["id"], "n": len(atras), "dias": dias,
                                                   "desde": _ddmm(min(x["venc"] for x in atras))})
        avisos[p["id"]] = hoje.isoformat()
        usadas += 1
        itens.append(ItemF("atraso", p["nome"], f"{len(atras)} parcela(s), {dias} dias de atraso (tarefa #{d.tarefa_id})"))

    for p, x in lembrar:
        chave = f"venc|{p['id']}|{x['venc']}"
        if chave in feitos:
            continue
        d = m.processar("parcela_a_vencer", dados={**base, "ref": p["id"], "vence": _ddmm(x["venc"])})
        feitos.add(chave)
        itens.append(ItemF("a_vencer", p["nome"], f"vence em {_ddmm(x['venc'])} (tarefa #{d.tarefa_id})"))

    if arq:
        arq.write_text(json.dumps({"cobrancas": avisos, "feitos": sorted(feitos)}), encoding="utf-8")
    return itens


def formatar(itens: list[ItemF]) -> str:
    rot = {"atraso": "Parcela em atraso", "a_vencer": "Parcela a vencer"}
    linhas = [f"{'Tipo':<18} {'Paciente':<28} O que aconteceu"]
    linhas += [f"{rot[i.tipo]:<18} {i.nome[:27]:<28} {i.resultado}" for i in itens]
    return "\n".join(linhas) if itens else "Nenhuma parcela a cobrar ou lembrar hoje."


if __name__ == "__main__":  # python -m hansen.rotina_financeira backup.json [AAAA-MM-DDTHH:MM|agora]
    from hansen.canal import CanalSimulado, Notificador
    from hansen.ledger import LedgerManager
    from hansen.painel_comercial import TIPOS_FINANCEIRO, cartoes, gerar
    from hansen.yaml_parser import carregar_todos

    if len(sys.argv) < 2:
        raise SystemExit("Uso: python -m hansen.rotina_financeira backup.json [AAAA-MM-DDTHH:MM|agora]")
    base_dir = Path("saida") / "financeiro"
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
    painel = gerar(maestro, dados, base_dir / "painel_financeiro.html", agora, "financeiro", TIPOS_FINANCEIRO, "Painel financeiro")
    print(f"\nPAINEL FINANCEIRO ({len(cartoes(maestro, dados, 'financeiro', TIPOS_FINANCEIRO))} sugestões abertas): {painel.resolve()}")
    print(f"Ledger íntegro: {led.verificar()}")
    try:
        import webbrowser
        webbrowser.open(painel.resolve().as_uri())
    except Exception:
        pass
