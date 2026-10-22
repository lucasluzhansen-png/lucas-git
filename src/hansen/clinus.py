"""Leitor do backup do Clinus (JSON exportado em "Dados e backup → Exportar JSON").
Só lê; nunca escreve no Clinus. Guarda só o necessário (id, nome, telefone, nascimento, decisão do orçamento, última ação,
consentimento): CPF, fotos, prontuário e anamnese ficam de fora."""
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
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
    for p in bruto.get("pacientes") or []:
        enxuto = {
            "id": p.get("id"), "nome": p.get("nome", ""), "tel": p.get("tel", ""),
            "nascimento": p.get("nascimento") or "", "decisao": p.get("decisao") or "",
            "ultima_acao": p.get("ultimaAcao") or p.get("criadoEm") or "",
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
    return [
        f"Pacientes ativos: {len(ativos)} | decisão do orçamento: {dict(Counter(p['decisao'] or '(vazio)' for p in ativos))}",
        f"Última ação: sem data em {sem_data}; há 7+ dias: {sum(1 for x in dias if x >= 7)}; há 90+ dias: {sum(1 for x in dias if x >= 90)}",
        f"Nascimento preenchido: {nasc_ok} | aniversários nos próximos 30 dias: {aniv_30}",
        f"Orçamento em aberto (definição do Clinus): {sum(1 for p in ativos if p['orc_aberto'])} | base histórica importada: {sum(1 for p in ativos if p['historico'])}",
        f"Tratamento concluído (etapa 10): {sum(1 for p in ativos if p['etapa'] == 10 and not p['zona'])} | etapas: {dict(sorted(Counter(p['etapa'] for p in ativos).items(), key=lambda kv: (kv[0] is None, kv[0] or 0)))}",
        f"Consentimento comercial registado: {sum(1 for p in ativos if p['consentimento'])}",
        f"Retornos: {len(d.retornos)} | campos: {sorted(campos_ret)}",
    ]


if __name__ == "__main__":  # python -m hansen.clinus backup.json
    import sys

    print(diagnostico(Path(sys.argv[1])) if len(sys.argv) > 1 else "Uso: python -m hansen.clinus backup.json")
