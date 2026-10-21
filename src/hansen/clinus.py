"""Leitor do backup do Clinus (JSON exportado em "Dados e backup → Exportar JSON").
Só lê; nunca escreve no Clinus. Guarda apenas id, nome e telefone: CPF, fotos e prontuário ficam de fora."""
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


def carregar_backup(caminho: Path) -> ClinusDados:
    bruto = json.loads(Path(caminho).read_text(encoding="utf-8"))
    if bruto.get("versao") != "hrpg_v1":
        raise ValueError("Arquivo não parece um backup do Clinus (versao esperada: hrpg_v1).")
    d = ClinusDados(exportado_em=bruto.get("exportadoEm", ""))
    for p in bruto.get("pacientes") or []:
        enxuto = {"id": p.get("id"), "nome": p.get("nome", ""), "tel": p.get("tel", "")}
        d.por_id[p.get("id")] = enxuto
        if _digitos(p.get("tel")):
            d.por_telefone[_digitos(p["tel"])] = enxuto
    agenda = (bruto.get("stores") or {}).get("clinus_agenda_v2")
    if agenda:  # o backup guarda cada store como texto JSON
        lista = json.loads(agenda) if isinstance(agenda, str) else agenda
        d.agenda = [e for e in lista if isinstance(e, dict)]
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
        f"Outras chaves no backup: {sorted(k for k in stores if 'agenda' in k.lower() or 'consulta' in k.lower())}",
    ])


if __name__ == "__main__":  # python -m hansen.clinus backup.json
    import sys

    print(diagnostico(Path(sys.argv[1])) if len(sys.argv) > 1 else "Uso: python -m hansen.clinus backup.json")
