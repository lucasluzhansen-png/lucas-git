"""Painel comercial: cartões para o Dr. Lucas, montados a partir das TAREFAS COMERCIAIS ABERTAS + dados do Clinus.
Cada cartão tem nome, texto formal sugerido (sem valores) e link que abre o WhatsApp já preenchido: quem envia é o humano.
O arquivo contém nomes e telefones: uso interno, fica em saida/ (fora do Git)."""
import re
from datetime import datetime
from html import escape
from pathlib import Path
from urllib.parse import quote

from hansen.clinus import ClinusDados, _digitos
from hansen.maestro import Maestro
from hansen.textos import modelo_aniversario, texto as montar_texto

# prefixo do título da tarefa → (modelo, POP, rótulo)
TIPOS = {
    "Retomar contato: orçamento em aberto": ("retomar_orcamento", "CM-02", "Orçamento em aberto"),
    "Reativar paciente parado": ("reativar_paciente", "CM-02", "Paciente parado"),
    "Contatar para revisão/manutenção vencida": ("revisar_manutencao", "CM-02", "Revisão / manutenção"),
    "Parabenizar aniversariante": ("parabens", "CM-01", "Aniversário (sem consentimento p/ envio automático)"),
}


TIPOS_FINANCEIRO = {
    "Cobrar parcela em atraso": ("cobrar_atraso", "FN-01", "Parcela em atraso"),
    "Lembrar parcela a vencer": ("lembrar_vencimento", "FN-01", "Parcela a vencer"),
}


AVISO_COMERCIAL = ("Sugestões da IA. <b>Revise o texto antes de enviar.</b> A IA não cita valores ou condições de pagamento (única exceção: "
                   "o abatimento de aniversário no clareamento, definido pelo RT); se o paciente perguntar, responda você. "
                   "Este arquivo tem nomes e telefones: uso interno, não compartilhe.")
AVISO_FINANCEIRO = ("Sugestões da IA para a Recepção. <b>Revise o texto antes de enviar.</b> Cobrança sempre cordial: sem ameaça, sem constrangimento "
                    "e sem expor a dívida a terceiros. Confira o valor e o vencimento no Clinus antes de falar com o paciente. "
                    "Este arquivo tem nomes e telefones: uso interno, não compartilhe.")


# tarefas internas da clínica (sem paciente): aparecem como cartões simples, sem botão de WhatsApp
INTERNOS = {
    "Conta a pagar": "Conta a pagar", "Compra": "Compra", "Agendar manutenção preventiva": "Equipamento",
    "Fechar o caixa": "Caixa", "Convênio": "Convênio", "Laboratório": "Laboratório",
}


def cartoes_internos(m: Maestro) -> list[dict]:
    donos = {m.pops["A-06"].responsaveis[k] for k in ("financeiro", "decisao_compras", "laboratorio", "contabilidade")}
    saida = []
    for t in m.tarefas.tarefas.values():
        rotulo = next((r for k, r in INTERNOS.items() if t.titulo.startswith(k)), None)
        if t.estado not in ("aberta", "escalada") or t.responsavel not in donos or not rotulo:
            continue
        titulo, _, detalhe = t.titulo.partition("]. ")
        saida.append({"tarefa": t.id, "rotulo": rotulo, "titulo": titulo.split(" [")[0], "detalhe": detalhe or "", "quem": t.responsavel, "urgente": t.prioridade == "amarela"})
    return saida


def cartoes(m: Maestro, clinus: ClinusDados, quem: str = "contato_comercial", tipos: dict | None = None) -> list[dict]:
    dono = m.pops["A-06"].responsaveis[quem]
    tipos = tipos or TIPOS
    saida = []
    for t in m.tarefas.tarefas.values():
        if t.estado not in ("aberta", "escalada") or t.responsavel != dono:
            continue
        tipo = next(((k, v) for k, v in tipos.items() if t.titulo.startswith(k)), None)
        ref = re.search(r"\[paciente ([^\]]+)\]", t.titulo)
        if not tipo or not ref:
            continue
        pac = clinus.por_id.get(ref.group(1))
        if not pac:
            continue
        modelo, pop, rotulo = tipo[1]
        if modelo == "parabens":
            modelo = modelo_aniversario(m.pops[pop])
        data = re.search(r"(?:desde|vence em) (\d{2}/\d{2})", t.titulo)
        texto = montar_texto(m.pops[pop], modelo, pac["nome"], data_hora=data.group(1) if data else "")
        dig = _digitos(pac["tel"])
        dias = re.search(r"há (\d+) dias", t.titulo)
        saida.append({"tarefa": t.id, "rotulo": rotulo, "nome": pac["nome"], "dias": dias.group(1) if dias else "",
                      "texto": texto, "link": f"https://wa.me/55{dig}?text={quote(texto)}" if dig else ""})
    return saida


def gerar(m: Maestro, clinus: ClinusDados, destino: Path, agora: datetime | None = None,
          quem: str = "contato_comercial", tipos: dict | None = None, titulo: str = "Painel comercial",
          aviso: str = AVISO_COMERCIAL, internos: bool = False) -> Path:
    cs = cartoes(m, clinus, quem, tipos)
    ints = cartoes_internos(m) if internos else []
    blocos_int = "".join(
        f'<div class="c{" u" if c["urgente"] else ""}"><div class="t">{escape(c["rotulo"])}{" · URGENTE" if c["urgente"] else ""} · para {escape(c["quem"])}</div>'
        f'<div class="n">{escape(c["titulo"])} <span class="id">tarefa #{c["tarefa"]}</span></div><div class="m">{escape(c["detalhe"])}</div></div>' for c in ints)
    agora = agora or datetime.now()
    blocos = "".join(
        f'<div class="c"><div class="t">{escape(c["rotulo"])}' + (f" · {c['dias']} dias" if c["dias"] else "") + f'</div>'
        f'<div class="n">{escape(c["nome"])} <span class="id">tarefa #{c["tarefa"]}</span></div>'
        f'<div class="m">{escape(c["texto"])}</div>'
        + (f'<a class="b" href="{escape(c["link"])}" target="_blank" rel="noopener">Abrir no WhatsApp</a>' if c["link"]
           else '<div class="sem">Sem telefone válido: ligar ou corrigir o cadastro no Clinus.</div>')
        + "</div>" for c in cs) or ("" if ints else '<p>Nenhuma sugestão aberta. 🎉</p>')
    html = f"""<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(titulo)}</title>
<style>
:root{{--bg:#fafafa;--tx:#222;--card:#fff;--bd:#ddd;--ac:#1a7f4b}}
@media(prefers-color-scheme:dark){{:root{{--bg:#1c1c1e;--tx:#eee;--card:#2a2a2c;--bd:#444}}}}
body{{font-family:system-ui,sans-serif;background:var(--bg);color:var(--tx);max-width:760px;margin:20px auto;padding:0 16px}}
h1{{font-size:1.3rem}} .aviso{{font-size:.85rem;opacity:.8;border-left:4px solid #e65100;padding:6px 10px;margin:10px 0}}
.c{{background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:12px 14px;margin:12px 0}}
.t{{font-size:.8rem;text-transform:uppercase;opacity:.7}} .n{{font-weight:600;font-size:1.05rem;margin:2px 0 6px}} .id{{font-weight:400;font-size:.8rem;opacity:.6}}
.m{{font-size:.92rem;background:rgba(127,127,127,.12);border-radius:8px;padding:8px 10px;margin-bottom:8px}}
.b{{display:inline-block;background:var(--ac);color:#fff;text-decoration:none;padding:8px 14px;border-radius:8px}} .sem{{color:#c62828;font-size:.9rem}} .u{{border-left:5px solid #e65100}}
</style>
<h1>{escape(titulo)} · {agora:%d/%m/%Y %H:%M}</h1>
<div class="aviso">{aviso}</div>
{blocos_int}{blocos}
</html>"""
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(html, encoding="utf-8")
    return destino
