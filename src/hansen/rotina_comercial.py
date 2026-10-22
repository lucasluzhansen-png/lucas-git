"""Rotina comercial diária (CM-01 e CM-02): lê o backup do Clinus e aciona o agente Comercial.
Limites vêm do YAML; nunca cita valores/descontos; sem consentimento registado a IA não envia."""
import json
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from hansen.clinus import ClinusDados, carregar_backup
from hansen.maestro import Maestro
from hansen.sincronizar import Chaves


@dataclass
class ItemC:
    tipo: str
    nome: str
    resultado: str


def _params(m: Maestro, pop: str, efeito: str) -> dict:
    return next(r.parametros for r in m.pops[pop].regras_de_decisao if r.efeito == efeito)


def _dt(texto: str) -> datetime | None:
    try:
        d = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    return d.astimezone(timezone.utc).replace(tzinfo=None) if d.tzinfo else d


def _data(texto: str) -> date | None:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime((texto or "")[:10], fmt).date()
        except ValueError:
            continue
    return None


def rodar(m: Maestro, clinus: ClinusDados, agora: datetime) -> list[ItemC]:
    arq = m.tarefas.arquivo.parent / "comercial.json" if m.tarefas.arquivo else None
    estado = json.loads(arq.read_text(encoding="utf-8")) if arq and arq.exists() else {}
    feitos: set[str] = set(estado.get("feitos", []))
    contatos: dict[str, str] = estado.get("contatos", {})
    hoje = agora.date()
    antecedencia = _params(m, "CM-01", "enviar_lembrete_retorno")["antecedencia_dias"]
    dias_orc = _params(m, "CM-02", "retomar_orcamento")["dias_orcamento"]
    pr = _params(m, "CM-02", "reativar_paciente")
    dias_man = _params(m, "CM-02", "revisar_manutencao")["dias_manutencao"]
    itens: list[ItemC] = []
    base = {"agora": agora.isoformat()}
    chaves = Chaves(m, "comercial")

    def feito(tipo, chave, nome, d, sem_marcar_se_adiado=True):
        if d.envio == "enviado" or d.tarefa_id:
            feitos.add(chave)
        itens.append(ItemC(tipo, nome, d.acao if not d.tarefa_id else f"{d.acao} (tarefa #{d.tarefa_id})"))

    pacs = sorted((p for p in clinus.por_id.values() if p["ativo"]), key=lambda p: str(p["id"]))

    # 1) Aniversariantes (CM-01)
    for p in pacs:
        nasc = _data(p["nascimento"])
        chave = f"aniv|{p['id']}|{hoje.year}"
        if not nasc or (nasc.month, nasc.day) != (hoje.month, hoje.day) or chave in feitos:
            continue
        if not p["tel"]:
            itens.append(ItemC("aniversario", p["nome"], "sem telefone: parabenizar manualmente"))
            continue
        d = m.processar("aniversario", dados={**base, "ref": p["id"], "nome": p["nome"], "telefone": p["tel"], "consentimento": p["consentimento"]})
        feito("aniversario", chave, p["nome"], d)
        if d.tarefa_id:
            chaves.registrar(f"aniv|{p['id']}|{hoje.year}", d.tarefa_id)

    # 2) Retornos agendados (CM-01)
    for r in clinus.retornos:
        if (r.get("status") or "") == "concluido":
            continue
        alvo = next((_data(str(r[k])) for k in ("devido", "data", "date") if r.get(k)), None)
        if not alvo or not (hoje <= alvo <= hoje + timedelta(days=antecedencia)):
            continue
        p = clinus.por_id.get(r.get("pacId"))
        chave = f"ret|{r.get('id')}|{alvo}"
        if not p or not p["ativo"] or chave in feitos:
            continue
        if not p["tel"]:
            itens.append(ItemC("retorno", p["nome"], "sem telefone: ligar manualmente"))
            continue
        d = m.processar("retorno", dados={**base, "ref": p["id"], "nome": p["nome"], "telefone": p["tel"], "data_hora": f"{alvo:%d/%m}"})
        feito("retorno", chave, p["nome"], d)

    # 3) Sugestões para o Dr. Lucas (CM-02): orçamentos em aberto primeiro, depois pacientes parados
    usadas = sum(1 for v in contatos.values() if v == hoje.isoformat())
    futuros = {e.get("pacId") for e in clinus.agenda
               if (e.get("data") or "") >= hoje.isoformat() and (e.get("status") or "") in ("agendado", "confirmado")}

    def recente(pid):
        ult = _data(contatos.get(pid, ""))
        return bool(ult and (hoje - ult).days < pr["intervalo_contato_dias"])

    candidatos = []
    for p in pacs:
        ult = _dt(p["ultima_acao"])
        dias = (agora - ult).days if ult else 0
        concluido = (p["etapa"] or 0) >= 10 and not p["zona"]
        if p["orc_aberto"]:
            if dias >= dias_orc:
                candidatos.append((0, -dias, "orcamento_aberto", p, dias))
        elif p["historico"]:
            continue  # base importada sem ação humana: não é alvo (mesma regra do Clinus)
        elif concluido:
            if p["etapa"] == 10 and ult and dias >= dias_man:
                candidatos.append((1, -dias, "manutencao_vencida", p, dias))
        elif ult and dias >= pr["dias_parado"] and p["zona"] != "perdidos" and p["id"] not in futuros:
            candidatos.append((2, -dias, "paciente_parado", p, dias))
    for _, _, tipo, p, _d in candidatos:
        chaves.marcar_ativa(f"{tipo}|{p['id']}")  # a situação existe, mesmo que hoje não gere sugestão nova
    for _, _, tipo, p, dias in sorted(candidatos, key=lambda c: (c[0], c[1])):
        if recente(p["id"]):
            continue
        if usadas >= pr["maximo_por_dia"]:
            itens.append(ItemC(tipo, p["nome"], "adiado: limite diário de sugestões atingido"))
            continue
        d = m.processar(tipo, dados={**base, "ref": p["id"], "dias": dias})
        chaves.registrar(f"{tipo}|{p['id']}", d.tarefa_id)
        contatos[p["id"]] = hoje.isoformat()
        usadas += 1
        itens.append(ItemC(tipo, p["nome"], f"{d.acao} (tarefa #{d.tarefa_id}, {dias} dias)"))

    # aniversário sem consentimento: a situação vale só no dia do aniversário
    for p in pacs:
        nasc = _data(p["nascimento"])
        if nasc and (nasc.month, nasc.day) == (hoje.month, hoje.day):
            chaves.marcar_ativa(f"aniv|{p['id']}|{hoje.year}")
    chaves.fechar_resolvidas()
    if arq:
        arq.write_text(json.dumps({"feitos": sorted(feitos), "contatos": contatos}), encoding="utf-8")
    return itens


def formatar(itens: list[ItemC]) -> str:
    rot = {"aniversario": "Aniversário", "retorno": "Retorno", "orcamento_aberto": "Orçamento aberto", "paciente_parado": "Paciente parado", "manutencao_vencida": "Manutenção vencida"}
    linhas = [f"{'Tipo':<18} {'Paciente':<28} O que aconteceu"]
    linhas += [f"{rot[i.tipo]:<18} {i.nome[:27]:<28} {i.resultado}" for i in itens]
    return "\n".join(linhas) if itens else "Nada a fazer hoje no comercial."


if __name__ == "__main__":  # python -m hansen.rotina_comercial backup.json [AAAA-MM-DDTHH:MM|agora]
    from hansen.canal import CanalSimulado, Notificador
    from hansen.ledger import LedgerManager
    from hansen.yaml_parser import carregar_todos

    if len(sys.argv) < 2:
        raise SystemExit("Uso: python -m hansen.rotina_comercial backup.json [AAAA-MM-DDTHH:MM]")
    base_dir = Path("saida") / "comercial"
    base_dir.mkdir(parents=True, exist_ok=True)
    led = LedgerManager(base_dir / "ledger")
    canal = CanalSimulado()
    maestro = Maestro(led, estado=base_dir / "estado", notificador=Notificador(canal, led, carregar_todos()["R-02"]))
    agora = datetime.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2] != "agora" else datetime.now()
    try:
        dados = carregar_backup(Path(sys.argv[1]))
    except FileNotFoundError:
        raise SystemExit(f"Arquivo não encontrado: {sys.argv[1]}")
    except (ValueError, KeyError) as e:
        raise SystemExit(f"Não consegui ler o backup: {e}")
    print(formatar(rodar(maestro, dados, agora)))
    print(f"\nMensagens (simuladas): {len(canal.enviadas)} | ledger íntegro: {led.verificar()}")
    from hansen.painel_comercial import cartoes, gerar
    painel = gerar(maestro, dados, base_dir / "painel_comercial.html", agora)
    print(f"\nPAINEL COMERCIAL ({len(cartoes(maestro, dados))} sugestões abertas): {painel.resolve()}")
    try:
        import webbrowser
        webbrowser.open(painel.resolve().as_uri())
    except Exception:
        pass
