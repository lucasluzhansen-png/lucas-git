"""Cobrador: decide QUANDO e O QUE o Maestro cobra de cada pessoa. Função pura (sem rede, sem Windows): recebe as tarefas e o estado, devolve avisos.
Avisos nunca levam nome de paciente: só contagens e categorias. Regras e textos vêm do MA-01.yaml."""
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta

from hansen.tarefas import Tarefa
from hansen.yaml_parser import POP

CATEGORIAS = (
    ("Conta a pagar VENCIDA", "conta vencida"), ("Conta a pagar a vencer", "conta a vencer"), ("Compra CRÍTICA", "compra crítica"),
    ("Compra", "compra"), ("Fechar o caixa", "caixa sem fechar"), ("Agendar manutenção", "preventiva de equipamento"),
    ("Convênio: repasse", "repasse de convênio atrasado"), ("Convênio: glosa", "glosa sem recurso"), ("Convênio", "pendência de convênio"),
    ("Cobrar parcela", "cobrança de parcela"), ("Lembrar parcela", "parcela a vencer"), ("Retomar contato", "orçamento a retomar"),
    ("Reativar paciente", "paciente a reativar"), ("Contatar para revisão", "revisão/manutenção"), ("Parabenizar", "aniversariante"),
    ("Agendar paciente", "paciente a agendar"), ("Aprovar decisão", "decisão a aprovar"),
)
NOMES = {"lucas": "Dr. Lucas", "recepcao": "Recepção"}


@dataclass
class Aviso:
    titulo: str
    texto: str
    chave: str


def _naive(d: datetime) -> datetime:
    return d.astimezone().replace(tzinfo=None) if d.tzinfo else d


def categoria(titulo: str) -> str:
    return next((c for p, c in CATEGORIAS if titulo.startswith(p)), "tarefa")


def _lista(tarefas: list[Tarefa]) -> str:
    cont = Counter(categoria(t.titulo) for t in tarefas)
    partes = [f"{n}× {c}" if n > 1 else c for c, n in cont.most_common(3)]
    resto = sum(cont.values()) - sum(n for _, n in cont.most_common(3))
    return ", ".join(partes) + (f" e mais {resto}" if resto > 0 else "")


def _params(pop: POP) -> dict:
    p = {}
    for r in pop.regras_de_decisao:
        p.update(r.parametros)
    return p


def na_janela(agora: datetime, pop: POP) -> bool:
    p = _params(pop)
    return agora.weekday() < 5 and p["hora_inicio"] <= agora.hour < p["hora_fim"]


def decidir(pop: POP, tarefas: list[Tarefa], perfil: str, agora: datetime, estado: dict, idade_backup_h: float | None = None) -> list[Aviso]:
    """Devolve os avisos devidos AGORA para o perfil ('lucas' ou 'recepcao') e atualiza `estado` (o que já foi cobrado e quando)."""
    p, msg, hoje = _params(pop), pop.mensagens, agora.date().isoformat()
    if not na_janela(agora, pop):
        return []
    abertas = [t for t in tarefas if t.estado in ("aberta", "escalada")]
    minhas = [t for t in abertas if t.responsavel == perfil]
    urgentes = [t for t in minhas if t.prioridade in ("amarela", "vermelha")]
    avisos: list[Aviso] = []
    saud = "Bom dia" if agora.hour < 12 else "Boa tarde"

    # resumo da manhã (1x por dia, só se houver o que fazer)
    if (agora.hour, agora.minute) >= (p["resumo_h"], p["resumo_min"]) and estado.get("resumo") != hoje:
        estado["resumo"] = hoje
        if minhas:
            avisos.append(Aviso("Maestro Hansen", msg["resumo"].format(saudacao=saud, n=len(minhas), u=len(urgentes)), "resumo"))

    # urgentes: insiste a cada N horas; o tom endurece com os dias em aberto
    ultimo = estado.setdefault("urgentes", {})
    def devida(t: Tarefa) -> bool:
        ult = ultimo.get(str(t.id))
        return ult is None or (agora - datetime.fromisoformat(ult)) >= timedelta(hours=p["intervalo_urgente_h"])

    devidas = [t for t in urgentes if devida(t)]
    if devidas:
        dias = max((agora.date() - _naive(t.criada_em).date()).days for t in devidas)
        nivel = 0 if dias < 1 else (1 if dias < 3 else 2)
        avisos.append(Aviso("Maestro Hansen", msg[f"urgente_{nivel}"].format(categorias=_lista(devidas), dias=dias), f"urgente|{nivel}"))
        for t in devidas:
            ultimo[str(t.id)] = agora.isoformat()
    for k in [k for k in ultimo if k not in {str(t.id) for t in urgentes}]:
        del ultimo[k]  # tarefa resolvida: para de cobrar

    # o Dr. Lucas também é avisado do que está parado com a Recepção
    if perfil == "lucas" and estado.get("escalada") != hoje:
        paradas = [t for t in abertas if t.responsavel == "recepcao" and (agora.date() - _naive(t.criada_em).date()).days >= p["dias_escalar"]]
        if paradas:
            estado["escalada"] = hoje
            avisos.append(Aviso("Maestro Hansen", msg["escalada"].format(n=len(paradas), dias=p["dias_escalar"], categorias=_lista(paradas)), "escalada"))

    # backup antigo
    if idade_backup_h is not None and idade_backup_h >= p["backup_antigo_h"]:
        ult = estado.get("backup")
        if not ult or (agora - datetime.fromisoformat(ult)) >= timedelta(hours=p["intervalo_backup_h"]):
            estado["backup"] = agora.isoformat()
            avisos.append(Aviso("Maestro Hansen", msg["backup_antigo"].format(horas=int(idade_backup_h)), "backup"))

    # fechamento do dia
    if (agora.hour, agora.minute) >= (p["fechamento_h"], p["fechamento_min"]) and estado.get("fechamento") != hoje:
        estado["fechamento"] = hoje
        if minhas:
            avisos.append(Aviso("Maestro Hansen", msg["fechamento"].format(n=len(minhas), u=len(urgentes)), "fechamento"))
    return avisos
