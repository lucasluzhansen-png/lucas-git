"""Rotina de lembretes: lê a agenda do Clinus e aciona o agente Recepção (R-02) para cada consulta."""
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from hansen.tarefas import _ler_json_ou_isolar
from hansen.caminhos import pasta_saida

from hansen.clinus import ClinusDados, Consulta, carregar_backup
import unicodedata

from hansen.maestro import Decisao, Maestro
from hansen.sincronizar import Chaves

CAMPOS_TIPO = ("tipo", "categoria", "procedimento", "motivo", "titulo", "descricao", "servico")
EM_LAB = ("enviado", "producao")
CONCLUIDAS = ("instalado", "entregue", "cancelada", "cancelado")


@dataclass
class Item:
    consulta: Consulta
    decisao: Decisao | None  # None = nada a fazer / sem telefone
    nota: str = ""


def _horas_antes(m: Maestro) -> int:
    return next(r.parametros["horas_antes"] for r in m.pops["R-02"].regras_de_decisao if r.efeito == "marcar_no_show")


def _norm(s) -> str:
    return unicodedata.normalize("NFKD", str(s or "").lower()).encode("ascii", "ignore").decode()


def _peca_pendente(m: Maestro, clinus: ClinusDados, ev: dict) -> str | None:
    """Prova/instalação de prótese sem a peça conferida contra a OS (LB-01). Retorna o motivo, ou None se pode confirmar."""
    chaves = next(r.palavras_chave for r in m.pops["LB-01"].regras_de_decisao if r.palavras_chave)
    texto = " ".join(_norm(ev.get(k)) for k in CAMPOS_TIPO)
    if not any(k in texto for k in chaves):
        return None
    abertas = [o for o in clinus.lab_os if o.get("pacId") == ev.get("pacId") and (o.get("etapa") or o.get("status") or "") not in CONCLUIDAS]
    if not abertas:
        return "nenhuma OS de laboratório encontrada para este paciente"
    if any(o.get("antiRefacaoEm") and (o.get("etapa") or o.get("status") or "") not in EM_LAB for o in abertas):
        return None
    return "a peça ainda não foi conferida contra a OS"


def rodar(m: Maestro, clinus: ClinusDados, agora: datetime, horas: int = 48) -> list[Item]:
    arq = m.tarefas.arquivo.parent / "lembretes_enviados.json" if m.tarefas.arquivo else None
    enviados: set[str] = set(_ler_json_ou_isolar(arq, [])) if arq and arq.exists() else set()
    limite = _horas_antes(m)
    plano = []
    eventos = {str(e.get("id")): e for e in clinus.agenda}
    trava = Chaves(m, "confirmacao_peca")
    for c in clinus.proximas(agora, horas):
        chave = f"{c.id}|{c.inicio.isoformat()}"  # remarcar muda o horário → novo lembrete
        motivo = _peca_pendente(m, clinus, eventos.get(c.id, {}))
        if motivo:  # trava: prova/instalação não recebe confirmação automática enquanto a peça não estiver conferida
            tchave = f"peca|{chave}"
            trava.marcar_ativa(tchave)
            d = m.processar("confirmacao_bloqueada", dados={"agora": agora.isoformat(), "ref_txt": f"consulta {c.id}",
                                                           "detalhe": f"Confirmação suspensa: {motivo}."})
            trava.registrar(tchave, d.tarefa_id)
            plano.append(Item(c, None, f"confirmação SUSPENSA: {motivo} (tarefa #{d.tarefa_id})"))
            continue
        if not c.telefone:
            plano.append(Item(c, None, "sem telefone: ligar manualmente"))
            continue
        if chave in enviados and (c.inicio - agora).total_seconds() > limite * 3600:
            plano.append(Item(c, None, "lembrete já enviado"))
            continue
        d = m.processar("confirmacao", dados={
            "agora": agora.isoformat(), "consulta_em": c.inicio.isoformat(), "respondeu": c.status == "confirmado",
            "nome": c.nome, "telefone": c.telefone, "consulta_id": c.id,
        })
        if d.acao == "enviar_lembrete":
            enviados.add(chave)
        plano.append(Item(c, d))
    trava.fechar_resolvidas()
    if arq:
        arq.write_text(json.dumps(sorted(enviados)), encoding="utf-8")
    return plano


def formatar(plano: list[Item]) -> str:
    """Lista do dia para a Recepção (contém nomes: uso local, não vai ao ledger)."""
    rot = {"enviar_lembrete": "lembrete enviado", "confirmar": "já confirmado", "adiar_envio": "fora do horário: enviar depois",
           "marcar_no_show": "RISCO DE NO-SHOW: ligar agora"}
    linhas = [f"{'Quando':<12} {'Paciente':<28} O que aconteceu"]
    for i in plano:
        quando = f"{i.consulta.inicio:%d/%m %H:%M}"
        o = i.nota or (rot.get(i.decisao.acao, i.decisao.acao) + (f" (tarefa #{i.decisao.tarefa_id})" if i.decisao.tarefa_id else ""))
        linhas.append(f"{quando:<12} {i.consulta.nome[:27]:<28} {o}")
    return "\n".join(linhas) if plano else "Nenhuma consulta aberta nas próximas horas."


if __name__ == "__main__":  # python -m hansen.lembretes backup.json [AAAA-MM-DDTHH:MM]
    from hansen.canal import CanalSimulado, Notificador
    from hansen.ledger import LedgerManager
    from hansen.yaml_parser import carregar_todos

    if len(sys.argv) < 2:
        raise SystemExit("Uso: python -m hansen.lembretes backup.json [AAAA-MM-DDTHH:MM] [horas]")
    base = pasta_saida() / "lembretes"
    base.mkdir(parents=True, exist_ok=True)
    led = LedgerManager(base / "ledger")
    canal = CanalSimulado()
    maestro = Maestro(led, estado=base / "estado", notificador=Notificador(canal, led, carregar_todos()["R-02"]))
    agora = datetime.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2] != "agora" else datetime.now()
    try:
        dados = carregar_backup(Path(sys.argv[1]))
    except FileNotFoundError:
        raise SystemExit(f"Arquivo não encontrado: {sys.argv[1]}\nVeja o nome certo com: dir $HOME\\Downloads\\hansen-rpg-backup*")
    except (ValueError, KeyError) as e:  # JSON inválido ou arquivo de outro tipo
        raise SystemExit(f"Não consegui ler o backup: {e}")
    horas = int(sys.argv[3]) if len(sys.argv) > 3 else 48  # janela de busca; ex.: 720 = 30 dias
    print(formatar(rodar(maestro, dados, agora, horas)))
    print(f"\nMensagens (simuladas): {len(canal.enviadas)} | ledger íntegro: {led.verificar()}")
