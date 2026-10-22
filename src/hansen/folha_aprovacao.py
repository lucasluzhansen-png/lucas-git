"""Gera a folha de aprovação dos POPs a partir dos YAMLs (fonte única de verdade): o que está na folha é o que o sistema faz.
Uso: python -m hansen.folha_aprovacao  →  docs/folha_aprovacao_pops.html"""
from datetime import date
from html import escape
from pathlib import Path

from hansen.textos import modelo_aniversario, variaveis
from hansen.yaml_parser import POP, carregar_todos

POPS_DA_FOLHA = ["R-00", "R-02", "A-01", "A-06", "CM-01", "CM-02", "FN-01", "FN-02", "FN-03", "MA-01"]
NIVEL = {"HUMANO": "Só humano age", "IA_SUGERE": "A IA sugere; um humano decide", "IA_AUDITA": "A IA audita", "IA_EXECUTA": "A IA faz sozinha", "IA_SOZINHA": "A IA faz sozinha"}
MUDOU = [
    "R-00: escopo ampliado (orto, alinhadores, PPR, PT, restaurações, lentes, coroas, bruxismo, implantes, clareamento, facetas, próteses encaminhados para agendar); serviço fora do escopo: indicar profissionais parceiros; paciente atual: dentista faz o 1º atendimento e encaminha.",
    "R-02: janela de mensagens seg-sex 8h-18h; sem resposta 2h antes: risco de no-show e a Recepção liga; mensagem abre direto com “Senhor(a) nome”.",
    "A-01: abertura da clínica só é registada (sem tarefa de aprovação).",
    "A-06: aprovações e alertas vermelhos vão para o Dr. Lucas; ligação de no-show e agendamento para a Recepção.",
    "NOVOS: CM-01 (lembretes de relacionamento) e CM-02 (retomada de orçamentos, reativação e manutenção), aprovados em conteúdo pelo Dr. Lucas em 22/10/2026.",
    "NOVO: FN-01 (Financeiro: lembrete de parcela a vencer e cobrança de atraso). A IA só sugere; a Recepção revisa e envia. Atraso após 3 dias (decisão do RT). Ainda sem aprovação.",
    "NOVO: MA-01 (Cobrança do Maestro: resumo às 8h30 e fechamento às 17h30, insiste a cada 2 h nas urgentes com tom crescente, avisa o Dr. Lucas do que está parado com a Recepção há 2+ dias e avisa quando o backup do Clinus está velho). Notificação do Windows, seg-sex 8h-18h. O Maestro cobra a EQUIPE sozinho; enviar mensagem a paciente e decidir continuam humanos. Tarefas agora também se fecham sozinhas quando o Clinus mostra que o problema acabou.",
    "NOVO: FN-03 (Convênio: guia não criada ou não enviada, autorização pendente, repasse atrasado, glosa sem recurso e fechamento mensal por operadora). Lê o módulo de guias do Clinus. A IA só sugere; responsável: Recepção. Ainda sem aprovação.",
    "NOVO: FN-02 (Financeiro da clínica: contas a pagar, compras, preventiva de equipamentos e fechamento de caixa). A IA só sugere; responsável: Recepção (compras: Dr. Lucas decide). Ainda sem aprovação.",
]
PENDENTE = [
    "Oferta de abatimento de 15% no clareamento (aniversário): validar com o CRO / Código de Ética (CFO 118/2012) antes do envio real.",
    "Consentimento do paciente para mensagens comerciais: criar o registo no Clinus (sem ele, aniversário não é enviado automaticamente).",
    "Valores assumidos a confirmar: retorno avisado 2 dias antes; manutenção vencida após 180 dias (regra do Clinus).",
    "Lista de palavras de urgência clínica e de procedimentos fora do escopo: revisão clínica.",
    "FN-01: confirmar valores assumidos (lembrete 3 dias antes; 1 cobrança a cada 7 dias por paciente; 10 sugestões por dia) e revisar o texto de cobrança.",
    "FN-02: confirmar valores assumidos (conta avisada 2 dias antes; preventiva 15 dias antes; caixa olha os últimos 7 dias) e se as compras pendentes vão mesmo para o Dr. Lucas.",
    "FN-03: confirmar valores assumidos (criar guia 3 dias após aprovar; enviar guia 3 dias após criar; cobrar autorização 7 dias após enviar; fechamento do mês a partir do dia 5) e o que significa “fechamento de caixa de convênio” para a clínica.",
    "Ainda por desenhar: chamados de equipamento parados e diferença de caixa sem explicação (campos do Clinus a conferir).",
    "MA-01: confirmar valores assumidos (insistência a cada 2 h; escalar após 2 dias; backup antigo após 24 h; resumo 8h30; fechamento 17h30) e testar a notificação do Windows (testar_aviso.bat), que não pôde ser testada em Windows real.",
    "Lista de profissionais parceiros (a ser entregue pelo Dr. Lucas).",
]


def _radios(nome: str) -> str:
    return "".join(f'<label><input type="radio" name="{nome}"> {t}</label>' for t in ("Sim", "Não", "Mudar"))


def _linha(nome: str, titulo: str, detalhe: str = "") -> str:
    d = f'<div class="d">{escape(detalhe)}</div>' if detalhe else ""
    return f'<tr><td><b>{titulo}</b>{d}</td><td class="r">{_radios(nome)}</td><td><input class="nota" placeholder="anotação"></td></tr>'


class _Seguro(dict):
    def __missing__(self, chave):  # variável sem exemplo: mostra {nome} em vez de quebrar a folha
        return "{" + chave + "}"


EXEMPLOS_MAESTRO = {"saudacao": "Bom dia", "n": 3, "u": 1, "categorias": "2× conta vencida, compra crítica", "dias": 2, "horas": 30}


def _exemplo(pop: POP, modelo: str) -> str:
    v = variaveis(pop, "Maria Souza", data_hora="11/03", titulo="Falha crítica", **EXEMPLOS_MAESTRO)
    return pop.mensagens[modelo].format_map(_Seguro(v))


def _secao(pop: POP) -> str:
    ia = NIVEL[pop.automacao.nivel]
    if pop.automacao.nivel == "IA_AUDITA" and not pop.automacao.aprovacao_humana:
        ia = "A IA registra sozinha"
    linhas = [_linha(f"{pop.id}-n", f"Autonomia: {ia}", "Aprovação humana por decisão: " + ("sim" if pop.automacao.aprovacao_humana else "não"))]
    for i, r in enumerate(pop.regras_de_decisao):
        par = ", ".join(f"{k} = {v}" for k, v in r.parametros.items())
        linhas.append(_linha(f"{pop.id}-r{i}", escape(r.acao), f"Quando: {r.condicao}" + (f" | Valores: {par}" if par else "")))
    for i, (k, t) in enumerate(pop.mensagens.items()):
        if pop.id == "CM-01" and k in ("parabens", "parabens_simples") and k != modelo_aniversario(pop):
            continue  # mostra só o texto de aniversário que está ativo (oferta ligada ou desligada)
        linhas.append(_linha(f"{pop.id}-m{i}", f"Mensagem “{k}”", _exemplo(pop, k)))
    for i, (k, v) in enumerate(pop.responsaveis.items()):
        linhas.append(_linha(f"{pop.id}-p{i}", f"Responsável: {k.replace('_', ' ')} → {escape(v)}"))
    return f'<h2>{pop.id} · {escape(pop.titulo)}</h2><table>{"".join(linhas)}</table>'


def gerar(destino: Path, pops: dict[str, POP] | None = None) -> Path:
    pops = pops or carregar_todos()
    secoes = "".join(_secao(pops[i]) for i in POPS_DA_FOLHA)
    mudou = "".join(f"<li>{escape(m)}</li>" for m in MUDOU)
    pend = "".join(f'<tr><td><label><input type="checkbox"> {escape(p)}</label></td><td><input class="nota" placeholder="anotação"></td></tr>' for p in PENDENTE)
    html = f'''<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Folha de aprovação dos POPs</title>
<style>
:root{{--bg:#fff;--tx:#222;--bd:#d0d0d0;--hd:#f1f1f1}}
@media(prefers-color-scheme:dark){{:root{{--bg:#1c1c1e;--tx:#eee;--bd:#444;--hd:#2a2a2c}}}}
body{{font-family:system-ui,sans-serif;background:var(--bg);color:var(--tx);max-width:900px;margin:20px auto;padding:0 16px;font-size:14px}}
h1{{font-size:1.25rem;margin:0}} h2{{font-size:1rem;margin:22px 0 6px;background:var(--hd);padding:6px 8px;border-radius:6px}}
table{{width:100%;border-collapse:collapse}} td{{border-bottom:1px solid var(--bd);padding:5px 6px;vertical-align:top}}
.d{{font-size:.82rem;opacity:.75;margin-top:2px}} .r{{white-space:nowrap;width:190px}} .r label{{margin-right:8px}}
.nota{{width:100%;border:0;border-bottom:1px dotted var(--bd);background:transparent;color:inherit;font:inherit}}
.ass{{display:flex;gap:24px;margin-top:28px}} .ass div{{flex:1;border-top:1px solid var(--tx);padding-top:4px;font-size:.85rem}} .sub{{opacity:.7}}
@media print{{body{{font-size:11px;margin:0}} h2{{break-after:avoid}} tr{{break-inside:avoid}} .nota{{border-bottom:1px solid #999}}}}
@media(max-width:600px){{.r{{width:auto;white-space:normal}}}}
</style>
<h1>Hansen Odontologia · Folha de aprovação dos POPs</h1>
<p class="sub">Gerada em {date.today():%d/%m/%Y} direto dos arquivos YAML: o que está aqui é o que o sistema faz. Marque <b>Sim</b>, <b>Não</b> ou <b>Mudar</b>. Só humanos aprovam.</p>
<h2>O que mudou desde o Fluxo v1</h2><ul>{mudou}</ul>
{secoes}
<h2>Pendências (precisam de decisão ou validação)</h2><table>{pend}</table>
<h2>Aprovação</h2>
<p>Data: <input class="nota" style="width:140px" placeholder="__/__/____"> &nbsp; (  ) Aprovado  (  ) Aprovado com mudanças  (  ) Não aprovado</p>
<div class="ass"><div>Dr. Lucas Luz Hansen (RT / DPO)</div><div>Dra. Jussara Hansen (RT)</div></div>
</html>'''
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(html, encoding="utf-8")
    return destino


if __name__ == "__main__":
    print(gerar(Path("docs") / "folha_aprovacao_pops.html").resolve())
