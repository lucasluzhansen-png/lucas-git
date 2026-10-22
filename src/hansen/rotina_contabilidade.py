"""Rotina da contabilidade (CT-01): junta o mês/ano do Clinus em planilhas (CSV) e cobra o envio ao contador.
Só junta e cobra; NUNCA calcula imposto. Os CSV ficam na pasta de saída local (nada de paciente vai para tarefa/ledger)."""
import csv
import json
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from hansen.caminhos import pasta_saida
from hansen.clinus import ClinusDados, carregar_backup, data_br
from hansen.maestro import Maestro

MESES = ("", "janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro")


@dataclass
class ItemC:
    tipo: str
    resultado: str


def _p(m: Maestro, chave: str) -> int:
    return next(r.parametros[chave] for r in m.pops["CT-01"].regras_de_decisao if chave in r.parametros)


def _csv(caminho: Path, cabecalho: list[str], linhas: list[list]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", encoding="utf-8-sig", newline="") as f:  # utf-8-sig: o Excel abre os acentos certo
        w = csv.writer(f, delimiter=";")
        w.writerow(cabecalho)
        w.writerows(linhas)


def _mes_de(texto) -> tuple[int, int] | None:
    d = data_br(texto)
    return (d.year, d.month) if d else None


def pacote_mensal(clinus: ClinusDados, ano: int, mes: int, destino: Path) -> dict:
    """Entradas por dia, despesas (contas pagas) e compras do mês. Retorna totais e grava os CSV em destino."""
    pref = f"{ano}-{mes:02d}"
    entradas = sorted((d, v) for d, v in clinus.recebido_por_dia.items() if d.startswith(pref))
    contas = [c for c in clinus.contas_pagar if c["pago"] and (c["vencimento"] or "").startswith(pref)]
    compras = []
    for c in clinus.compras:
        dia = str(c.get("data") or c.get("criadoEm") or "")[:10]
        if dia.startswith(pref) and (c.get("status") or "pendente") not in ("pendente", "adiado", "cancelado"):
            compras.append(c)
    _csv(destino / "entradas.csv", ["data", "total_recebido"], [[d, f"{v:.2f}".replace(".", ",")] for d, v in entradas])
    _csv(destino / "despesas.csv", ["vencimento", "descricao", "valor"], [[c["vencimento"], c["descricao"], f"{c['valor_num']:.2f}".replace(".", ",")] for c in sorted(contas, key=lambda c: c["vencimento"])])
    _csv(destino / "compras.csv", ["data", "produto", "quantidade", "status"], [[str(c.get("data") or c.get("criadoEm") or "")[:10], c["produto"], c.get("qtd", ""), c.get("status", "")] for c in compras])
    return {"entradas": round(sum(v for _, v in entradas), 2), "despesas": round(sum(c["valor_num"] for c in contas), 2), "compras": len(compras)}


def resumo_anual(clinus: ClinusDados, ano: int, destino: Path) -> dict:
    """Resumo por mês + informe de pagamentos por paciente (CONTÉM NOMES: só local, para o contador)."""
    mensal = []
    for mes in range(1, 13):
        pref = f"{ano}-{mes:02d}"
        ent = sum(v for d, v in clinus.recebido_por_dia.items() if d.startswith(pref))
        desp = sum(c["valor_num"] for c in clinus.contas_pagar if c["pago"] and (c["vencimento"] or "").startswith(pref))
        mensal.append([MESES[mes], f"{ent:.2f}".replace(".", ","), f"{desp:.2f}".replace(".", ","), f"{ent - desp:.2f}".replace(".", ",")])
    _csv(destino / "resumo_anual.csv", ["mes", "entradas", "despesas", "saldo"], mensal)
    informes = sorted(((clinus.por_id.get(pid, {}).get("nome") or f"(id {pid})", v) for (pid, a), v in clinus.recebido_por_paciente.items() if a == ano))
    _csv(destino / "informes_pacientes.csv", ["paciente", f"total_pago_{ano}"], [[n, f"{v:.2f}".replace(".", ",")] for n, v in informes])
    return {"pacientes": len(informes), "entradas": round(sum(v for (_, a), v in clinus.recebido_por_paciente.items() if a == ano), 2)}


def rodar(m: Maestro, clinus: ClinusDados, agora: datetime, saida: Path | None = None) -> list[ItemC]:
    arq = m.tarefas.arquivo.parent / "contabilidade.json" if m.tarefas.arquivo else None
    feitos: set[str] = set(json.loads(arq.read_text(encoding="utf-8"))) if arq and arq.exists() else set()
    hoje = agora.date()
    saida = saida or pasta_saida() / "contabilidade"
    itens: list[ItemC] = []
    base = {"agora": agora.isoformat()}

    def sugerir(chave, acao, detalhe, ref):
        if chave in feitos:  # o Clinus não sabe se o envio ao contador foi feito: a tarefa só fecha quando a Recepção marca "Feito"
            return
        m.processar("contabil", dados={**base, "ref_txt": ref, "acao": acao, "detalhe": detalhe})
        feitos.add(chave)
        itens.append(ItemC(acao, detalhe))

    # 1) Fechamento do mês anterior (a partir do dia configurado)
    if hoje.day >= _p(m, "dia_cobranca"):
        ano, mes = (hoje.year, hoje.month - 1) if hoje.month > 1 else (hoje.year - 1, 12)
        t = pacote_mensal(clinus, ano, mes, saida / f"{ano}-{mes:02d}")
        sugerir(f"mes|{ano}-{mes:02d}", "enviar_contador",
                f"Fechamento de {MESES[mes]}/{ano} pronto em contabilidade/{ano}-{mes:02d}: entradas R$ {t['entradas']:.2f}, despesas pagas R$ {t['despesas']:.2f}, {t['compras']} compras",
                f"{mes:02d}/{ano}")

    # 2) IR do ano anterior
    ano_ir = hoje.year - 1
    if _p(m, "ir_mes_inicio") <= hoje.month <= _p(m, "ir_mes_prazo"):
        t = resumo_anual(clinus, ano_ir, saida / f"IR-{ano_ir}")
        sugerir(f"ir|{ano_ir}", "preparar_ir", f"IR {ano_ir}: resumo anual e informes de {t['pacientes']} pacientes prontos em contabilidade/IR-{ano_ir}", f"IR {ano_ir}")
        if hoje.month == _p(m, "ir_mes_prazo"):
            sugerir(f"ir|{ano_ir}|prazo", "prazo_ir", f"IR {ano_ir}: prazo perto, confirmar com o contador se foi entregue", f"IR {ano_ir}")

    if arq:
        arq.write_text(json.dumps(sorted(feitos)), encoding="utf-8")
    return itens


def formatar(itens: list[ItemC]) -> str:
    return "\n".join(f"{i.tipo}  →  {i.resultado}" for i in itens) if itens else "Nada para o contador hoje."


if __name__ == "__main__":  # python -m hansen.rotina_contabilidade backup.json [AAAA-MM-DDTHH:MM|agora]
    from hansen.canal import CanalSimulado, Notificador
    from hansen.ledger import LedgerManager
    from hansen.yaml_parser import carregar_todos

    if len(sys.argv) < 2:
        raise SystemExit("Uso: python -m hansen.rotina_contabilidade backup.json [AAAA-MM-DDTHH:MM|agora]")
    base_dir = pasta_saida() / "contabilidade"
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
