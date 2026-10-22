"""Leitor do backup do Clinus (JSON exportado em "Dados e backup → Exportar JSON").
Só lê; nunca escreve no Clinus. Guarda só o necessário (id, nome, telefone, nascimento, decisão do orçamento, última ação,
consentimento): CPF, fotos, prontuário e anamnese ficam de fora."""
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

# Estados da agenda do Clinus em que o lembrete ainda faz sentido.
ABERTOS = {"agendado", "confirmado", ""}


def _digitos(tel: str | None) -> str:
    d = re.sub(r"\D", "", tel or "")
    return d[-11:] if len(d) >= 10 else ""  # ignora +55; descarta números incompletos


@dataclass
class Consulta:
    id: str
    paciente_id: str
    nome: str
    telefone: str
    inicio: datetime
    status: str


@dataclass
class ClinusDados:
    exportado_em: str = ""
    por_telefone: dict[str, dict] = field(default_factory=dict)
    por_id: dict[str, dict] = field(default_factory=dict)
    agenda: list[dict] = field(default_factory=list)
    retornos: list[dict] = field(default_factory=list)
    contas_pagar: list[dict] = field(default_factory=list)
    compras: list[dict] = field(default_factory=list)
    equipamentos: list[dict] = field(default_factory=list)
    caixa: list[dict] = field(default_factory=list)
    lab_os: list[dict] = field(default_factory=list)  # store lab_os (ordens de serviço do laboratório)
    guias: list[dict] = field(default_factory=list)  # store clinus_guias (módulo "Faturamento de convênio")
    recebido_por_dia: dict[str, float] = field(default_factory=dict)  # "AAAA-MM-DD" → total recebido (para conferir o fechamento de caixa)
    recebido_por_paciente: dict[tuple[str, int], float] = field(default_factory=dict)  # (id do paciente, ano) → total recebido (informes do IR)
    stores_brutos: dict = field(default_factory=dict)  # só para diagnóstico de estrutura; nada daqui é usado como dado de paciente

    def eh_paciente_atual(self, telefone: str | None) -> bool:
        return _digitos(telefone) in self.por_telefone

    def consultas_entre(self, de: datetime, ate: datetime) -> list[Consulta]:
        """Consultas ainda abertas no intervalo, com telefone resolvido pelo cadastro."""
        saida = []
        for ev in self.agenda:
            try:
                inicio = datetime.fromisoformat(f"{ev['data']}T{ev.get('hora') or '00:00'}")
            except (KeyError, ValueError):
                continue  # evento mal formado: ignora, nunca adivinha
            if not (de <= inicio <= ate) or (ev.get("status") or "").lower() not in ABERTOS:
                continue
            pac = self.por_id.get(ev.get("pacId"), {})
            saida.append(Consulta(str(ev.get("id", "")), str(ev.get("pacId", "")), ev.get("nome") or pac.get("nome", ""),
                                  pac.get("tel", ""), inicio, (ev.get("status") or "")))
        return sorted(saida, key=lambda c: c.inicio)

    def proximas(self, agora: datetime, horas: int = 24) -> list[Consulta]:
        return self.consultas_entre(agora, agora + timedelta(hours=horas))


def _valor(v) -> float:
    """Valor em reais: aceita número ou texto no formato brasileiro ("1.500,00", "R$ 300")."""
    if isinstance(v, (int, float)):
        return float(v)
    t = re.sub(r"[^\d,.\-]", "", str(v or ""))
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return 0.0


def _pago(orc: dict) -> float:
    """Total recebido do orçamento (estornos não contam), como no Clinus (`_valorPago`)."""
    pg = orc.get("pagamentos")
    if isinstance(pg, list) and pg:
        return sum(0.0 if (not x or x.get("estornadoEm")) else _valor(x.get("valor")) for x in pg)
    return _valor(orc.get("pago")) if orc.get("pago") not in (None, "") else 0.0


def situacao_parcelas(parcelas: list[dict], pago: float, hoje: date) -> list[dict]:
    """O dinheiro recebido quita as parcelas na ordem (como no Clinus, `_situacaoParcelas`)."""
    saldo, saida = round(pago, 2), []
    for pc in parcelas:
        valor = _valor(pc.get("valor"))
        usado = min(saldo, valor)
        saldo = round(saldo - usado, 2)
        quitada = usado >= valor - 0.01
        try:
            dias = (hoje - datetime.strptime(str(pc.get("venc"))[:10], "%Y-%m-%d").date()).days
        except ValueError:
            dias = None
        saida.append({"valor": valor, "venc": str(pc.get("venc") or "")[:10], "quitada": quitada,
                      "restante": round(valor - usado, 2),
                      "atraso": 0 if quitada or dias is None or dias <= 0 else dias,
                      "dias_ate_vencer": None if dias is None else -dias})
    return saida


_ISO = re.compile(r"\d{4}-\d{2}-\d{2}$")


def data_br(texto) -> date | None:
    """Data em 'AAAA-MM-DD' ou 'DD/MM/AAAA' (só a parte da data)."""
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(texto or "")[:10], fmt).date()
        except ValueError:
            continue
    return None


def op_nome(s) -> str:
    """Nome da operadora normalizado, como no Clinus (`_opNome`)."""
    t = str(s or "").strip()
    if not t:
        return "Convênio sem nome"
    if re.search(r"bradesco|odontoprev", t, re.I):
        return "Bradesco/Odontoprev"
    if re.search(r"codeba", t, re.I):
        return "CODEBA"
    if re.search(r"petrobras", t, re.I):
        return "Petrobras"
    return t[:1].upper() + t[1:]


def guia_status(g: dict) -> str:
    return "aprovada" if g.get("status") == "autorizada" else (g.get("status") or "criada")


def guia_calc(g: dict) -> dict:
    """Valores da guia, como no Clinus (`_guiaCalc`)."""
    v = _valor(g.get("valor"))
    gl = min(v, _valor(g.get("glosado")))
    st = guia_status(g)
    perdido = 0.0 if g.get("recurso") == "deferido" else gl
    esperado = _valor(g.get("valorEsperado")) if _valor(g.get("valorEsperado")) > 0 else v - perdido
    recebido = _valor(g.get("valorRecebido")) if _valor(g.get("valorRecebido")) > 0 else (esperado if st == "paga" else 0.0)
    return {"valor": v, "glosado": gl, "perdido": perdido, "esperado": esperado, "recebido": recebido, "a_receber": max(0.0, esperado - recebido)}


def guia_atrasada(g: dict, hoje: date) -> bool:
    """Repasse atrasado, como no Clinus (`_guiaAtrasada`): não paga, não só criada, previsão vencida e sem repasse registado."""
    prev = data_br(g.get("previsao"))
    return guia_status(g) not in ("paga", "criada") and bool(prev) and prev < hoje and not g.get("repasse")


def _historico(p: dict) -> bool:
    """Base importada sem nenhuma ação humana (mesma regra do Clinus, `_ehHistorico`): não é lead nem paciente a reativar."""
    if not p.get("origemImport"):
        return False
    if p.get("orcamento") or p.get("zona") or (p.get("etapa") or 2) > 2:
        return False
    if p.get("proxSessao") and p.get("proxSessao") != "—":
        return False
    return all(isinstance(x, dict) and isinstance(x.get("t"), str)
               and (x["t"].startswith("📥") or x["t"].startswith("🔁 Entrou na fila de reativação")) for x in (p.get("log") or []))


def _orc_aberto(p: dict) -> bool:
    """Orçamento em aberto, como no relatório do Clinus: decisão 'vai pensar', zona 'Orç. pendente', etapa 7 ou orçamento novo parado."""
    orc = p.get("orcamento") or {}
    em_aberto = bool(orc) and not orc.get("aprovadoEm") and bool(orc.get("itens"))
    return p.get("decisao") == "pensar" or p.get("zona") == "orcpendente" or p.get("etapa") == 7 or (em_aberto and bool(p.get("orcamentosFechados")))


def carregar_backup(caminho: Path) -> ClinusDados:
    bruto = json.loads(Path(caminho).read_text(encoding="utf-8"))
    if bruto.get("versao") != "hrpg_v1":
        raise ValueError("Arquivo não parece um backup do Clinus (versao esperada: hrpg_v1).")
    d = ClinusDados(exportado_em=bruto.get("exportadoEm", ""))
    d.stores_brutos = dict(bruto.get("stores") or {})
    for p in bruto.get("pacientes") or []:
        enxuto = {
            "id": p.get("id"), "nome": p.get("nome", ""), "tel": p.get("tel", ""),
            "nascimento": p.get("nascimento") or "", "decisao": p.get("decisao") or "",
            "ultima_acao": p.get("ultimaAcao") or p.get("criadoEm") or "",
            "aprovado_em": str((p.get("orcamento") or {}).get("aprovadoEm") or ""),
            "encerrado": bool((p.get("encerramento") or {}).get("emISO")), "encerrado_em": str((p.get("encerramento") or {}).get("emISO") or ""),
            "conv_valor": sum(_valor(it.get("valor")) * (float(it.get("qtd")) if str(it.get("qtd") or "").replace(".", "", 1).isdigit() else 1.0)
                              for it in ((p.get("orcamento") or {}).get("convItens") or {}).values() if isinstance(it, dict)),
            "conv_operadora": op_nome(next((it.get("convenio") for it in ((p.get("orcamento") or {}).get("convItens") or {}).values() if isinstance(it, dict)), None) or p.get("convQual")),
            "parcelas": [x for x in ((p.get("orcamento") or {}).get("parcelas") or []) if isinstance(x, dict)],
            "pago": _pago(p.get("orcamento") or {}),
            "etapa": p.get("etapa") if isinstance(p.get("etapa"), int) else None, "zona": p.get("zona") or "",
            "orc_aberto": _orc_aberto(p), "historico": _historico(p),
            "ativo": not (p.get("deleted") or p.get("arquivado") or p.get("ativo") is False),
            # opt-in para mensagens comerciais: só vale se o Clinus tiver registado explicitamente
            "consentimento": bool(p.get("consentimentoComercial") or p.get("consentimentoMensagens")),
        }
        d.por_id[p.get("id")] = enxuto
        if _digitos(p.get("tel")):
            d.por_telefone[_digitos(p["tel"])] = enxuto
    agenda = (bruto.get("stores") or {}).get("clinus_agenda_v2")
    if agenda:  # o backup guarda cada store como texto JSON
        lista = json.loads(agenda) if isinstance(agenda, str) else agenda
        d.agenda = [e for e in lista if isinstance(e, dict)]
    stores = bruto.get("stores") or {}

    def lista(chave):
        v = stores.get(chave)
        try:
            return (json.loads(v) if isinstance(v, str) else v) or []
        except ValueError:
            return []

    d.contas_pagar = [{**c, "valor_num": _valor(c.get("valor")), "pago": c.get("status") == "pago"} for c in lista("clinus_contas_pagar")
                      if isinstance(c, dict) and c.get("id") and c.get("descricao") and _valor(c.get("valor")) > 0 and _ISO.match(str(c.get("vencimento") or ""))]
    d.compras = [c for c in lista("clinus_compras") if isinstance(c, dict) and isinstance(c.get("id"), str) and isinstance(c.get("produto"), str) and c["produto"]]
    eq = lista("clinus_equipamentos")
    d.equipamentos = [e for e in (eq.get("equipamentos") if isinstance(eq, dict) else []) or [] if isinstance(e, dict)]
    d.lab_os = [o for o in lista("lab_os") if isinstance(o, dict) and (o.get("numero") or o.get("id")) and not o.get("arquivada")]
    d.guias = [g for g in lista("clinus_guias") if isinstance(g, dict) and g.get("id")]
    d.caixa = [c for c in lista("clinus_caixa") if isinstance(c, dict) and _ISO.match(str(c.get("data") or ""))]
    for p in bruto.get("pacientes") or []:  # recebimentos por dia (estornados e transferidos não contam), como o caixa do Clinus
        for pg in ((p.get("orcamento") or {}).get("pagamentos") or []):
            if not isinstance(pg, dict) or pg.get("estornadoEm") or pg.get("transferido"):
                continue
            dia = data_br(pg.get("d")) or data_br(pg.get("iso"))
            if dia and _valor(pg.get("valor")):
                d.recebido_por_dia[dia.isoformat()] = round(d.recebido_por_dia.get(dia.isoformat(), 0.0) + _valor(pg.get("valor")), 2)
                k = (str(p.get("id")), dia.year)
                d.recebido_por_paciente[k] = round(d.recebido_por_paciente.get(k, 0.0) + _valor(pg.get("valor")), 2)
    ret = (bruto.get("stores") or {}).get("clinus_retornos_v1")
    if ret:
        lista = json.loads(ret) if isinstance(ret, str) else ret
        d.retornos = [e for e in lista if isinstance(e, dict)]
    return d


def diagnostico(caminho: Path) -> str:
    """Resumo SEM dados de paciente (só contagens e nomes de campos) para conferir se o backup foi entendido."""
    from collections import Counter

    bruto = json.loads(Path(caminho).read_text(encoding="utf-8"))
    d = carregar_backup(caminho)
    stores = bruto.get("stores") or {}
    ag_bruta = stores.get("clinus_agenda_v2")
    datas = sorted(str(e.get("data")) for e in d.agenda if e.get("data"))
    campos = Counter(k for e in d.agenda for k in e)
    status = Counter((e.get("status") or "(vazio)") for e in d.agenda)
    agora = datetime.now()
    com_tel = sum(1 for p in d.por_id.values() if _digitos(p.get("tel")))
    return "\n".join([
        f"Backup exportado em: {d.exportado_em or '(sem data)'}",
        f"Pacientes: {len(d.por_id)} (com telefone válido: {com_tel})",
        f"Chave da agenda no backup: {'sim' if ag_bruta else 'NÃO ENCONTRADA'} | eventos: {len(d.agenda)}",
        f"Datas da agenda: {datas[0]} até {datas[-1]}" if datas else "Datas da agenda: nenhuma",
        f"Eventos de hoje em diante: {sum(1 for x in datas if x >= agora.strftime('%Y-%m-%d'))}",
        f"Status encontrados: {dict(status)}",
        f"Campos dos eventos: {sorted(campos)}",
        *_resumo_comercial(d, agora),
        f"Outras chaves no backup: {sorted(k for k in stores if 'agenda' in k.lower() or 'consulta' in k.lower())}",
    ])


def _resumo_comercial(d: ClinusDados, agora: datetime) -> list[str]:
    """Contagens para o agente Comercial, sem nomes nem telefones."""
    from collections import Counter

    def dt(t):
        try:
            x = datetime.fromisoformat(str(t).replace("Z", "+00:00"))
            return x.replace(tzinfo=None)
        except ValueError:
            return None

    ativos = [p for p in d.por_id.values() if p["ativo"]]
    dias = [(agora - x).days for p in ativos if (x := dt(p["ultima_acao"]))]
    sem_data = len(ativos) - len(dias)
    nasc_ok = sum(1 for p in ativos if re.match(r"\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}", p["nascimento"] or ""))
    aniv_30 = 0
    for p in ativos:
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", p["nascimento"] or "") or None
        if m:
            try:
                prox = datetime(agora.year, int(m[2]), int(m[3]))
            except ValueError:
                continue
            if prox < agora.replace(hour=0, minute=0, second=0, microsecond=0):
                prox = prox.replace(year=agora.year + 1)
            aniv_30 += (prox - agora).days <= 30
    campos_ret = Counter(k for r in d.retornos for k in r)
    return _resumo_financeiro(d, agora) + [
        f"Pacientes ativos: {len(ativos)} | decisão do orçamento: {dict(Counter(p['decisao'] or '(vazio)' for p in ativos))}",
        f"Última ação: sem data em {sem_data}; há 7+ dias: {sum(1 for x in dias if x >= 7)}; há 90+ dias: {sum(1 for x in dias if x >= 90)}",
        f"Nascimento preenchido: {nasc_ok} | aniversários nos próximos 30 dias: {aniv_30}",
        f"Orçamento em aberto (definição do Clinus): {sum(1 for p in ativos if p['orc_aberto'])} | base histórica importada: {sum(1 for p in ativos if p['historico'])}",
        f"Tratamento concluído (etapa 10): {sum(1 for p in ativos if p['etapa'] == 10 and not p['zona'])} | etapas: {dict(sorted(Counter(p['etapa'] for p in ativos).items(), key=lambda kv: (kv[0] is None, kv[0] or 0)))}",
        f"Consentimento comercial registado: {sum(1 for p in ativos if p['consentimento'])}",
        f"Retornos: {len(d.retornos)} | campos: {sorted(campos_ret)}",
    ]


def _resumo_financeiro(d: ClinusDados, agora: datetime) -> list[str]:
    """Só contagens e NOMES DE CAMPOS (nenhum valor, nome ou telefone)."""
    com_parc = [p for p in d.por_id.values() if p["ativo"] and p["parcelas"]]
    atrasadas = pacientes_atrasados = 0
    for p in com_parc:
        n = sum(1 for x in situacao_parcelas(p["parcelas"], p["pago"], agora.date()) if x["atraso"] >= 3)
        atrasadas += n
        pacientes_atrasados += n > 0
    from collections import Counter
    st = dict(Counter(guia_status(g) for g in d.guias))
    atras = sum(1 for g in d.guias if guia_atrasada(g, agora.date()))
    ativas_lab = [o for o in d.lab_os if (o.get("etapa") or o.get("status")) not in ("instalado", "entregue", "cancelada", "cancelado")]
    lab = f"Laboratório (OS): {len(d.lab_os)} OS | em andamento: {len(ativas_lab)} | por etapa: {dict(Counter((o.get('etapa') or o.get('status') or '(vazio)') for o in ativas_lab))}"
    guias = f"Convênio (guias): {len(d.guias)} guia(s) | por status: {st} | repasse atrasado: {atras}"
    return [lab, guias, f"Financeiro: pacientes com parcelamento: {len(com_parc)} | parcelas atrasadas (3+ dias): {atrasadas} em {pacientes_atrasados} paciente(s)"] + _estrutura_stores(d)


def _estrutura_stores(d: ClinusDados) -> list[str]:
    linhas = []
    for chave, rotulo in (("clinus_caixa", "caixa"), ("clinus_contas_pagar", "contas a pagar"), ("clinus_compras", "compras"),
                          ("clinus_equipamentos", "equipamentos"), ("clinus_convenios", "tabelas de convênio")):
        bruto = d.stores_brutos.get(chave)
        if bruto is None:
            linhas.append(f"  [{rotulo}] não existe no backup")
            continue
        try:
            dado = json.loads(bruto) if isinstance(bruto, str) else bruto
        except ValueError:
            linhas.append(f"  [{rotulo}] ilegível")
            continue
        if isinstance(dado, list):
            campos = sorted({k for e in dado if isinstance(e, dict) for k in e})
            linhas.append(f"  [{rotulo}] lista com {len(dado)} item(ns); campos: {campos}")
        elif isinstance(dado, dict):
            linhas.append(f"  [{rotulo}] objeto com {len(dado)} chave(s); chaves de 1º nível: {sorted(dado)[:15]}")
        else:
            linhas.append(f"  [{rotulo}] tipo {type(dado).__name__}")
    return linhas


if __name__ == "__main__":  # python -m hansen.clinus backup.json
    import sys

    print(diagnostico(Path(sys.argv[1])) if len(sys.argv) > 1 else "Uso: python -m hansen.clinus backup.json")
