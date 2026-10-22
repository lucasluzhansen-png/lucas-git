"""Rotina financeira diária (FN-01): lê as parcelas do backup do Clinus e aciona o agente Financeiro.
Só sugere: cada sugestão vira tarefa para a Recepção, com cartão no painel (nome, texto cordial e link do WhatsApp)."""
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from hansen.caminhos import pasta_saida

from datetime import timedelta

from hansen.clinus import ClinusDados, carregar_backup, data_br, guia_atrasada, guia_calc, guia_status, op_nome, situacao_parcelas
from hansen.maestro import Maestro
from hansen.sincronizar import Chaves


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

    chaves = Chaves(m, "parcelas")
    pacs = sorted((p for p in clinus.por_id.values() if p["ativo"] and p["parcelas"]), key=lambda p: str(p["id"]))
    cobrar, lembrar = [], []
    for p in pacs:
        sit = situacao_parcelas(p["parcelas"], p["pago"], hoje)
        atras = [x for x in sit if x["atraso"] >= pa["dias_atraso"]]
        if atras:
            cobrar.append((max(x["atraso"] for x in atras), p, atras))
            chaves.marcar_ativa(f"cobranca|{p['id']}")
        for x in sit:
            if not x["quitada"] and x["dias_ate_vencer"] is not None and 0 <= x["dias_ate_vencer"] <= pv["dias_antes"]:
                lembrar.append((p, x))
                chaves.marcar_ativa(f"venc|{p['id']}|{x['venc']}")

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
        chaves.registrar(f"cobranca|{p['id']}", d.tarefa_id)
        usadas += 1
        itens.append(ItemF("atraso", p["nome"], f"{len(atras)} parcela(s), {dias} dias de atraso (tarefa #{d.tarefa_id})"))

    for p, x in lembrar:
        chave = f"venc|{p['id']}|{x['venc']}"
        if chave in feitos:
            continue
        d = m.processar("parcela_a_vencer", dados={**base, "ref": p["id"], "vence": _ddmm(x["venc"])})
        feitos.add(chave)
        chaves.registrar(chave, d.tarefa_id)
        itens.append(ItemF("a_vencer", p["nome"], f"vence em {_ddmm(x['venc'])} (tarefa #{d.tarefa_id})"))

    feitos &= chaves.ativas  # situação que sumiu e voltar a existir deve gerar novo aviso
    chaves.fechar_resolvidas()
    if arq:
        arq.write_text(json.dumps({"cobrancas": avisos, "feitos": sorted(feitos)}), encoding="utf-8")
    return itens


def formatar(itens: list[ItemF]) -> str:
    rot = {"atraso": "Parcela em atraso", "a_vencer": "Parcela a vencer"}
    linhas = [f"{'Tipo':<18} {'Paciente':<28} O que aconteceu"]
    linhas += [f"{rot[i.tipo]:<18} {i.nome[:27]:<28} {i.resultado}" for i in itens]
    return "\n".join(linhas) if itens else "Nenhuma parcela a cobrar ou lembrar hoje."


def _param_fn02(m: Maestro, chave: str) -> int:
    return next(r.parametros[chave] for r in m.pops["FN-02"].regras_de_decisao if chave in r.parametros)


def _brl(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def rodar_clinica(m: Maestro, clinus: ClinusDados, agora: datetime) -> list[ItemF]:
    """Contas a pagar, compras, preventivas de equipamentos e fechamento de caixa (FN-02). Cada situação gera UMA sugestão por estado."""
    arq = m.tarefas.arquivo.parent / "financeiro_clinica.json" if m.tarefas.arquivo else None
    feitos: set[str] = set(json.loads(arq.read_text(encoding="utf-8"))) if arq and arq.exists() else set()
    hoje = agora.date()
    itens: list[ItemF] = []
    base = {"agora": agora.isoformat()}
    chaves = Chaves(m, "clinica")

    def sugerir(chave, tipo_evento, rotulo, nome, detalhe, ref, **extra):
        chaves.marcar_ativa(chave)
        if chave in feitos:
            return
        d = m.processar(tipo_evento, dados={**base, "ref_txt": ref, "detalhe": detalhe, **extra})
        feitos.add(chave)
        chaves.registrar(chave, d.tarefa_id)
        itens.append(ItemF(rotulo, nome, f"{detalhe} (tarefa #{d.tarefa_id})"))

    # 1) Contas a pagar
    antes = _param_fn02(m, "contas_dias_antes")
    for c in sorted(clinus.contas_pagar, key=lambda c: c["vencimento"]):
        if c["pago"]:
            continue
        venc = data_br(c["vencimento"])
        dias = (venc - hoje).days
        if dias > antes:
            continue
        vencida = dias < 0
        quando = f"venceu em {venc:%d/%m}" if vencida else (f"vence hoje" if dias == 0 else f"vence em {venc:%d/%m}")
        sugerir(f"conta|{c['id']}|{'vencida' if vencida else 'a_vencer'}", "conta_pagar", "conta", c["descricao"],
                f"{c['descricao']} ({_brl(c['valor_num'])}) {quando}", f"conta {c['id']}", vencida=vencida)

    # 2) Compras (status do Clinus: pendente aguarda o dono; aprovado: fazer o pedido; adiado volta a pendente na data)
    for c in clinus.compras:
        status = c.get("status") or "pendente"
        if status == "adiado":
            ate = data_br(c.get("adiadoAte"))
            status = "pendente" if ate and ate <= hoje else "adiado"
        crit = c.get("urgencia") == "critico"
        rot = f"{c['produto']} (qtd {c.get('qtd', 1)})"
        if status == "pendente":
            sugerir(f"compra|{c['id']}|pendente", "compra", "compra", c["produto"], f"{rot}{' · CRÍTICO: repor já' if crit else ''}",
                    f"compra {c['id']}", acao="decidir_compra_critica" if crit else "decidir_compra")
        elif status == "aprovado":
            sugerir(f"compra|{c['id']}|aprovado", "compra", "compra", c["produto"], f"{rot}: aprovada, falta fazer o pedido",
                    f"compra {c['id']}", acao="fazer_pedido")

    # 3) Preventiva de equipamentos
    antes_eq = _param_fn02(m, "equipamentos_dias_antes")
    for e in clinus.equipamentos:
        prox = data_br(e.get("proximaEm"))
        if e.get("ativo") is False or not prox or (prox - hoje).days > antes_eq:
            continue
        sugerir(f"equip|{e.get('id')}|{prox}", "equipamento", "equipamento", e.get("nome", "equipamento"),
                f"{e.get('nome', 'Equipamento')}: preventiva prevista para {prox:%d/%m}" + (" (JÁ PASSOU)" if prox < hoje else ""),
                f"equipamento {e.get('id')}")

    # 4) Fechamento de caixa: dia anterior com recebimento e sem fechamento registado
    fechados = {c["data"] for c in clinus.caixa}
    for k in range(1, _param_fn02(m, "caixa_dias_retroativos") + 1):
        dia = hoje - timedelta(days=k)
        if clinus.recebido_por_dia.get(dia.isoformat(), 0) > 0 and dia.isoformat() not in fechados:
            sugerir(f"caixa|{dia}", "caixa_aberto", "caixa", f"{dia:%d/%m}", f"Caixa de {dia:%d/%m} sem fechamento registado", f"caixa {dia}")

    itens += _convenio(m, clinus, agora, feitos, sugerir)
    feitos &= chaves.ativas
    chaves.fechar_resolvidas()
    if arq:
        arq.write_text(json.dumps(sorted(feitos)), encoding="utf-8")
    return itens


def _param_fn03(m: Maestro, chave: str) -> int:
    return next(r.parametros[chave] for r in m.pops["FN-03"].regras_de_decisao if chave in r.parametros)


def _convenio(m: Maestro, clinus: ClinusDados, agora: datetime, feitos: set, sugerir) -> list[ItemF]:
    """FN-03: guias, autorizações, repasses e glosas do módulo de faturamento de convênio do Clinus. Retorna [] (as sugestões entram via `sugerir`)."""
    hoje = agora.date()
    pacs = clinus.por_id

    def dias_desde(texto):
        d = data_br(texto)
        return (hoje - d).days if d else None

    def rot(g):
        p = pacs.get(g.get("pacId"), {})
        return f"{op_nome(g.get('convenio') or p.get('conv_operadora'))} · guia {g.get('numero') or g['id']} ({_brl(guia_calc(g)['valor'])})"

    # tratamento de convênio aprovado, sem nenhuma guia (mesma regra do Clinus, `_convenioSemGuia`)
    com_guia = {g.get("pacId") for g in clinus.guias}
    for p in sorted(pacs.values(), key=lambda p: str(p["id"])):
        d = dias_desde(p["aprovado_em"])
        if p["ativo"] and p["aprovado_em"] and not p["encerrado"] and p["conv_valor"] > 0 and p["id"] not in com_guia \
                and d is not None and d >= _param_fn03(m, "dias_sem_guia"):
            sugerir(f"semguia|{p['id']}", "convenio", "convenio", f"{p['conv_operadora']} · {p['nome']}",
                    f"{p['conv_operadora']}: tratamento aprovado há {d} dias ({_brl(p['conv_valor'])}) sem guia criada",
                    f"paciente {p['id']}", acao="criar_guia")

    for g in clinus.guias:
        st = guia_status(g)
        c = guia_calc(g)
        nome = rot(g)
        if st == "criada":
            d = dias_desde(str(g.get("criadoEm") or "")[:10])
            if d is not None and d >= _param_fn03(m, "dias_guia_criada"):
                sugerir(f"guia|{g['id']}|criada", "convenio", "convenio", nome, f"{nome}: criada há {d} dias e não enviada", f"guia {g['id']}", acao="enviar_guia")
        elif st == "enviada":
            d = dias_desde(g.get("envio"))
            if d is not None and d >= _param_fn03(m, "dias_autorizacao"):
                sugerir(f"guia|{g['id']}|enviada", "convenio", "convenio", nome, f"{nome}: enviada há {d} dias sem aprovação do convênio", f"guia {g['id']}", acao="cobrar_autorizacao")
        elif st == "glosada" and not g.get("recurso"):
            sugerir(f"guia|{g['id']}|glosa", "convenio", "convenio", nome,
                    f"{nome}: glosa de {_brl(c['glosado'])} sem recurso registado" + (f" ({g['motivoGlosa']})" if g.get("motivoGlosa") else ""),
                    f"guia {g['id']}", acao="recurso_glosa")
        if guia_atrasada(g, hoje):
            prev = data_br(g.get("previsao"))
            sugerir(f"guia|{g['id']}|repasse", "convenio", "convenio", nome,
                    f"{nome}: repasse previsto para {prev:%d/%m} ({(hoje - prev).days} dias de atraso), {_brl(c['a_receber'] or c['esperado'])} a receber",
                    f"guia {g['id']}", acao="cobrar_repasse")

    # fechamento do mês: operadoras com guias de meses anteriores ainda a receber
    if hoje.day >= _param_fn03(m, "dia_fechamento"):
        inicio_mes = hoje.replace(day=1)
        por_op: dict[str, list[float]] = {}
        for g in clinus.guias:
            st, c = guia_status(g), guia_calc(g)
            ref = data_br(g.get("envio")) or data_br(str(g.get("criadoEm") or "")[:10])
            conta = st != "paga" and st != "criada" and (st != "glosada" or g.get("recurso") in ("deferido", "enviado")) and c["a_receber"] > 0
            if conta and ref and ref < inicio_mes:
                por_op.setdefault(op_nome(g.get("convenio") or pacs.get(g.get("pacId"), {}).get("conv_operadora")), []).append(c["a_receber"])
        for op, valores in sorted(por_op.items()):
            sugerir(f"fechconv|{op}|{hoje:%Y-%m}", "convenio", "convenio", op,
                    f"{op}: {len(valores)} guia(s) de meses anteriores ainda a receber, total {_brl(sum(valores))}",
                    f"convênio {op} {hoje:%Y-%m}", acao="conferir_convenio")
    return []


def formatar_clinica(itens: list[ItemF]) -> str:
    rot = {"conta": "Conta a pagar", "compra": "Compra", "equipamento": "Equipamento", "caixa": "Caixa", "convenio": "Convênio"}
    return "\n".join([f"{'Tipo':<15} O que aconteceu"] + [f"{rot[i.tipo]:<15} {i.resultado}" for i in itens]) if itens else "Nada pendente na rotina da clínica hoje."


if __name__ == "__main__":  # python -m hansen.rotina_financeira backup.json [AAAA-MM-DDTHH:MM|agora]
    from hansen.canal import CanalSimulado, Notificador
    from hansen.ledger import LedgerManager
    from hansen.painel_comercial import AVISO_FINANCEIRO, TIPOS_FINANCEIRO, cartoes, cartoes_internos, gerar
    from hansen.yaml_parser import carregar_todos

    if len(sys.argv) < 2:
        raise SystemExit("Uso: python -m hansen.rotina_financeira backup.json [AAAA-MM-DDTHH:MM|agora]")
    base_dir = pasta_saida() / "financeiro"
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
    print("\n--- Rotina da clínica (contas, compras, equipamentos, caixa) ---")
    print(formatar_clinica(rodar_clinica(maestro, dados, agora)))
    painel = gerar(maestro, dados, base_dir / "painel_financeiro.html", agora, "financeiro", TIPOS_FINANCEIRO, "Painel financeiro", AVISO_FINANCEIRO, internos=True)
    print(f"\nPAINEL FINANCEIRO ({len(cartoes(maestro, dados, 'financeiro', TIPOS_FINANCEIRO)) + len(cartoes_internos(maestro))} itens abertos): {painel.resolve()}")
    print(f"Ledger íntegro: {led.verificar()}")
    try:
        import webbrowser
        webbrowser.open(painel.resolve().as_uri())
    except Exception:
        pass
