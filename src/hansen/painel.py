"""Painel: página HTML simples com tarefas e linha do tempo do ledger."""
import json
from html import escape
from pathlib import Path

COR = {"vermelha": "#c62828", "amarela": "#f9a825", "verde": "#2e7d32"}
ESTADO = {"executado": "IA fez sozinha", "aguarda_humano": "Aguarda humano", "escalado_humano": "Passou para humano"}


def gerar(base: Path, tarefas, ledger, mensagens=()) -> Path:
    eventos = [json.loads(f.read_text(encoding="utf-8")) for f in sorted((base / "ledger").glob("*.json"))]
    integra = ledger.verificar()
    linhas_t = "".join(
        f'<tr><td>#{t.id}</td><td><span class="dot" style="background:{COR.get(t.prioridade, "#999")}"></span>{escape(t.prioridade)}</td>'
        f"<td>{escape(t.estado)}</td><td>{escape(t.responsavel)}</td><td>{escape(t.titulo)}</td></tr>"
        for t in tarefas.tarefas.values()
    )
    linhas_e = "".join(
        f"<tr><td>{e['sequence']}</td><td>{escape(e['timestamp'][11:19])}</td><td>{escape(e['pop_id'])}</td>"
        f"<td>{escape(e['actor']['id'])}</td><td>{escape(e['acao'])}</td>"
        f"<td>{escape(ESTADO.get(e['saida'].get('estado', ''), e['saida'].get('estado', '')))}</td><td class='h'>{e['hash_evento'][:10]}…</td></tr>"
        for e in eventos
    )
    linhas_m = "".join(f"<li>{escape(m[1])}</li>" for m in mensagens) or "<li>Nenhuma</li>"
    html = f"""<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Painel Hansen</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:1000px;margin:24px auto;padding:0 16px;color:#222;background:#fafafa}}
h1{{font-size:1.5rem}} h2{{font-size:1.15rem;margin-top:32px}}
.ok{{display:inline-block;padding:6px 12px;border-radius:6px;color:#fff;background:{"#2e7d32" if integra else "#c62828"}}}
table{{width:100%;border-collapse:collapse;background:#fff;font-size:.9rem}}
td,th{{padding:8px;border-bottom:1px solid #e0e0e0;text-align:left;vertical-align:top}} th{{background:#eee}}
.dot{{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px}} .h{{font-family:monospace;color:#777}}
</style>
<h1>Painel Hansen (simulação)</h1>
<p><span class="ok">{"Registo íntegro: nada foi alterado" if integra else "ATENÇÃO: registo adulterado"}</span> &nbsp; {len(eventos)} eventos</p>
<h2>Tarefas</h2>
<table><tr><th></th><th>Prioridade</th><th>Estado</th><th>Responsável</th><th>O quê</th></tr>{linhas_t}</table>
<h2>Mensagens enviadas (simuladas)</h2><ul>{linhas_m}</ul>
<h2>Linha do tempo (ledger)</h2>
<table><tr><th>#</th><th>Hora</th><th>POP</th><th>Quem</th><th>Ação</th><th>Resultado</th><th>Hash</th></tr>{linhas_e}</table>
</html>"""
    destino = base / "painel.html"
    destino.write_text(html, encoding="utf-8")
    return destino
