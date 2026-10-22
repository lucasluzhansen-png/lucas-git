"""Painel do dia: roda TODAS as rotinas (lembretes, comercial, financeiro, convênio, cadastros) sobre o backup mais recente do Clinus
e gera UMA página: saida/hoje/painel_do_dia.html. Contém nomes e telefones: uso interno (pasta saida/ fora do Git)."""
import json
import sys
from datetime import datetime
from html import escape
from pathlib import Path
from urllib.parse import quote

from hansen.cadastros import analisar
from hansen.canal import CanalSimulado, Notificador
from hansen.clinus import _digitos, carregar_backup
from hansen.ledger import LedgerManager
from hansen.maestro import Maestro
from hansen.painel_comercial import TIPOS, TIPOS_FINANCEIRO, cartoes, cartoes_internos
from hansen.yaml_parser import carregar_todos

PREFIXOS_CARTAO = tuple(TIPOS) + tuple(TIPOS_FINANCEIRO)
ROTULO_MSG = (("retorno", "Lembrete de retorno"), ("consulta", "Lembrete de consulta"), ("aniversário", "Aniversário"))


def achar_backup_recente(pasta: Path) -> Path | None:
    arqs = sorted(Path(pasta).glob("hansen-rpg-backup-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return arqs[0] if arqs else None


def _mensagens_do_dia(base: Path, hoje: str, novas: list[tuple[str, str]]) -> list[dict]:
    """Mensagens prontas para a Recepção enviar à mão. Ficam salvas durante o dia (para não sumirem se o painel for reaberto)."""
    arq = base / "estado" / "mensagens_hoje.json"
    atual = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {}
    msgs = atual.get("mensagens", []) if atual.get("data") == hoje else []
    ja = {(m["destino"], m["texto"]) for m in msgs}
    for destino, texto in novas:
        if (destino, texto) not in ja:
            rotulo = next((r for k, r in ROTULO_MSG if k in texto.lower()), "Mensagem")
            msgs.append({"destino": destino, "texto": texto, "tipo": rotulo})
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text(json.dumps({"data": hoje, "mensagens": msgs}, ensure_ascii=False), encoding="utf-8")
    return msgs


def _outras_tarefas(m: Maestro, responsavel: str) -> list:
    return [t for t in m.tarefas.tarefas.values() if t.estado in ("aberta", "escalada") and t.responsavel == responsavel
            and not t.titulo.startswith(PREFIXOS_CARTAO)]


def _cartao_pac(c: dict) -> str:
    link = (f'<a class="b" href="{escape(c["link"])}" target="_blank" rel="noopener">Abrir no WhatsApp</a>' if c["link"]
            else '<div class="sem">Sem telefone válido: ligar ou corrigir o cadastro no Clinus.</div>')
    dias = f" · {c['dias']} dias" if c["dias"] else ""
    return (f'<div class="c"><div class="t">{escape(c["rotulo"])}{dias}</div><div class="n">{escape(c["nome"])} <span class="id">tarefa #{c["tarefa"]}</span></div>'
            f'<div class="m">{escape(c["texto"])}</div>{link}</div>')


def _linha_tarefa(t) -> str:
    titulo, _, detalhe = t.titulo.partition("]. ")
    urg = " u" if t.prioridade in ("amarela", "vermelha") else ""
    return (f'<div class="c{urg}"><div class="t">{"URGENTE · " if urg else ""}tarefa #{t.id}</div><div class="n">{escape(titulo.split(" [")[0])}</div>'
            f'<div class="m">{escape(detalhe or "")}</div></div>')


MASCOTE = ('<svg class="mas" viewBox="0 0 80 80" width="64" height="64" role="img" aria-label="Maestro, o mascote do painel">'
           '<path d="M26 10c-9 0-14 9-12 20 1 8 4 16 7 25 1 4 5 4 6 0l4-14c1-3 6-3 7 0l4 14c1 4 5 4 6 0 3-9 6-17 7-25 2-11-3-20-12-20-5 0-7 2-10 2s-5-2-10-2z" '
           'fill="#fff" stroke="#0E5E63" stroke-width="3" stroke-linejoin="round"/>'
           '<circle cx="31" cy="26" r="2.4" fill="#0E5E63"/><circle cx="45" cy="26" r="2.4" fill="#0E5E63"/>'
           '<path d="M32 34q6 6 12 0" fill="none" stroke="#0E5E63" stroke-width="2.6" stroke-linecap="round"/>'
           '<path d="M58 30l16-18" stroke="#c28a2c" stroke-width="3.5" stroke-linecap="round"/><circle cx="75" cy="11" r="3" fill="#c28a2c"/></svg>')


def saudacao(agora: datetime, total: int, urgentes: int) -> str:
    """Frase de bom dia com o resumo do dia (o mascote só comunica; quem decide é a equipe)."""
    h = agora.hour
    oi = "Bom dia" if h < 12 else ("Boa tarde" if h < 18 else "Boa noite")
    if total == 0:
        return f"{oi}, Dr. Lucas! Nada pendente por aqui. 🎉"
    resto = f", {urgentes} urgente(s)" if urgentes else ""
    return f"{oi}, Dr. Lucas! Hoje são {total} coisa(s) para a equipe{resto}. Eu sugiro, vocês decidem."


def renderizar(m: Maestro, dados, backup: Path, agora: datetime, msgs: list[dict], cadastro: dict) -> str:
    resp = m.pops["A-06"].responsaveis
    lucas, rec = resp["contato_comercial"], resp["financeiro"]
    c_lucas = cartoes(m, dados, "contato_comercial", TIPOS)
    c_rec = cartoes(m, dados, "financeiro", TIPOS_FINANCEIRO)
    o_lucas, o_rec = _outras_tarefas(m, lucas), _outras_tarefas(m, rec)
    internos = [c for c in cartoes_internos(m)]
    n_lucas, n_rec = len(c_lucas) + len(o_lucas), len(c_rec) + len(o_rec)
    urgentes = sum(1 for t in m.tarefas.tarefas.values() if t.estado in ("aberta", "escalada") and t.prioridade in ("amarela", "vermelha"))
    idade = ""
    try:
        exp = datetime.fromisoformat(dados.exportado_em.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
        horas = int((agora - exp).total_seconds() // 3600)
        idade = f"Backup exportado há {horas} h" + (" ⚠ <b>antigo: exporte um novo no Clinus</b>" if horas > 24 else "")
    except (ValueError, AttributeError):
        idade = "Data do backup desconhecida"
    cards_msg = "".join(
        f'<div class="c"><div class="t">{escape(x["tipo"])}</div><div class="m">{escape(x["texto"])}</div>'
        f'<a class="b" href="https://wa.me/55{_digitos(x["destino"])}?text={quote(x["texto"])}" target="_blank" rel="noopener">Abrir no WhatsApp</a></div>'
        for x in msgs) or "<p class='v'>Nenhuma mensagem pronta hoje.</p>"
    bloco = lambda cs, os: "".join(_cartao_pac(c) for c in cs) + "".join(_linha_tarefa(t) for t in os) or "<p class='v'>Nada pendente. 🎉</p>"
    cad = cadastro["contagem"]
    agentes = ", ".join(f"{a.nome} ({'pausado' if a.nome in m.pausados else 'ativo'})" for a in m.agentes)
    return f"""<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Painel do dia</title>
<style>
:root{{--bg:#fafafa;--tx:#222;--card:#fff;--bd:#ddd;--ac:#1a7f4b;--u:#e65100}}
@media(prefers-color-scheme:dark){{:root{{--bg:#1c1c1e;--tx:#eee;--card:#2a2a2c;--bd:#444}}}}
body{{font-family:system-ui,sans-serif;background:var(--bg);color:var(--tx);max-width:860px;margin:18px auto;padding:0 16px}}
h1{{font-size:1.35rem;margin:0}} h2{{font-size:1.05rem;margin:26px 0 8px;padding-bottom:4px;border-bottom:2px solid var(--bd)}}
.topo{{display:flex;gap:14px;align-items:center}} .oi{{font-size:1rem;margin-top:2px}} .mas{{flex-shrink:0;background:var(--card);border:1px solid var(--bd);border-radius:50%;padding:4px}}
.sub{{opacity:.7;font-size:.85rem;margin:4px 0 10px}} .aviso{{font-size:.82rem;border-left:4px solid var(--u);padding:6px 10px;margin:10px 0;opacity:.85}}
.nav{{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}} .nav a{{padding:6px 12px;border:1px solid var(--bd);border-radius:999px;text-decoration:none;color:inherit;font-size:.85rem}}
.res{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:12px 0}}
.k{{background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:10px 12px}} .k b{{display:block;font-size:1.6rem}} .k span{{font-size:.8rem;opacity:.7}}
.c{{background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:10px 14px;margin:10px 0}} .u{{border-left:5px solid var(--u)}}
.t{{font-size:.75rem;text-transform:uppercase;opacity:.7}} .n{{font-weight:600;margin:2px 0 6px}} .id{{font-weight:400;font-size:.78rem;opacity:.6}}
.m{{font-size:.9rem;background:rgba(127,127,127,.12);border-radius:8px;padding:7px 10px;margin-bottom:8px}}
.b{{display:inline-block;background:var(--ac);color:#fff;text-decoration:none;padding:7px 14px;border-radius:8px;font-size:.9rem}} .sem{{color:#c62828;font-size:.88rem}} .v{{opacity:.7}}
</style>
<div class="topo">{MASCOTE}<div><h1>Painel do dia · {agora:%d/%m/%Y %H:%M}</h1><div class="oi">{saudacao(agora, n_lucas + n_rec + len(msgs), urgentes)}</div></div></div>
<div class="sub">{idade} · arquivo {escape(backup.name)}</div>
<div class="aviso">Sugestões da IA. <b>Revise antes de enviar.</b> A IA só sugere e cobra a equipe; quem envia mensagens e decide é uma pessoa. Cobrança sempre cordial. Este arquivo tem nomes e telefones: uso interno, não compartilhe.</div>
<div class="nav"><a href="#msgs">Mensagens ({len(msgs)})</a><a href="#lucas">Dr. Lucas ({n_lucas})</a><a href="#rec">Recepção ({n_rec})</a><a href="#cad">Cadastros</a><a href="#sis">Sistema</a></div>
<div class="res"><div class="k"><b>{len(msgs)}</b><span>mensagens prontas</span></div><div class="k"><b>{n_lucas}</b><span>para o Dr. Lucas</span></div><div class="k"><b>{n_rec}</b><span>para a Recepção</span></div><div class="k"><b>{urgentes}</b><span>urgentes</span></div></div>
<h2 id="msgs">Mensagens prontas para enviar (Recepção)</h2>{cards_msg}
<h2 id="lucas">Para o Dr. Lucas</h2>{bloco(c_lucas, o_lucas)}
<h2 id="rec">Para a Recepção</h2>{bloco(c_rec, o_rec)}
<h2 id="cad">Qualidade dos cadastros no Clinus</h2>
<div class="c"><div class="m">{cadastro['com_problema']} de {cadastro['em_trabalho']} pacientes com cadastro a corrigir · sem telefone: {cad.get('sem telefone', 0)} · telefone incompleto: {cad.get('telefone incompleto', 0)} · sem nascimento: {cad.get('sem nascimento', 0)}.<br>Para ver os nomes: <code>python -m hansen.cadastros</code> (gera a planilha).</div></div>
<h2 id="sis">Sistema</h2>
<div class="c"><div class="m">Agentes: {escape(agentes)}.<br>Registo (ledger): {len(list((Path(m.ledger.pasta)).glob('*.json')))} eventos · cadeia {'íntegra ✅' if m.ledger.verificar() else 'ADULTERADA ⚠'}.<br>Modo atual: <b>assistido</b> (nada é enviado automaticamente; a Recepção envia pelo WhatsApp Business).</div></div>
</html>"""


def executar(backup: Path, agora: datetime, base: Path) -> Path:
    from hansen import lembretes, rotina_comercial, rotina_financeira
    pops = carregar_todos()
    base.mkdir(parents=True, exist_ok=True)
    led = LedgerManager(base / "ledger")
    canal = CanalSimulado()
    m = Maestro(led, pops=pops, estado=base / "estado", notificador=Notificador(canal, led, pops["R-02"]))
    dados = carregar_backup(backup)
    lembretes.rodar(m, dados, agora, 48)
    rotina_comercial.rodar(m, dados, agora)
    rotina_financeira.rodar(m, dados, agora)
    rotina_financeira.rodar_clinica(m, dados, agora)
    msgs = _mensagens_do_dia(base, agora.date().isoformat(), canal.enviadas)
    html = renderizar(m, dados, backup, agora, msgs, analisar(dados))
    destino = base / "painel_do_dia.html"
    destino.write_text(html, encoding="utf-8")
    return destino


if __name__ == "__main__":  # python -m hansen.hoje [backup.json|auto]
    arg = sys.argv[1] if len(sys.argv) > 1 else "auto"
    backup = achar_backup_recente(Path.home() / "Downloads") if arg == "auto" else Path(arg)
    if not backup or not backup.exists():
        raise SystemExit("Backup do Clinus não encontrado. No Clinus: Dados e backup → Exportar JSON (vai para a pasta Downloads) e rode de novo.")
    try:
        painel = executar(backup, datetime.now(), Path("saida") / "hoje")
    except (ValueError, KeyError) as e:
        raise SystemExit(f"Não consegui ler o backup {backup.name}: {e}")
    print(f"Backup usado: {backup.name}\\nPAINEL DO DIA: {painel.resolve()}")
    try:
        import webbrowser
        webbrowser.open(painel.resolve().as_uri())
    except Exception:
        pass
