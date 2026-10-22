import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from hansen.cobrador import categoria, decidir, na_janela
from hansen.maestro_vivo import achar_backup, tick
from hansen.tarefas import Tarefa
from hansen.yaml_parser import carregar_todos

POP = carregar_todos()["MA-01"]
TER = datetime(2026, 3, 10)  # terça


def t(i, titulo, resp="recepcao", prio="amarela", dias_atras=0):
    return Tarefa(i, titulo, "maestro", resp, prio, TER - timedelta(days=dias_atras))


def h(hora, minuto=0, dia=TER):
    return dia.replace(hour=hora, minute=minuto)


def test_so_cobra_seg_sex_8_a_18():
    assert na_janela(h(9), POP) and not na_janela(h(7, 59), POP) and not na_janela(h(18), POP)
    assert not na_janela(h(10, dia=datetime(2026, 3, 14)), POP)  # sábado
    assert decidir(POP, [t(1, "Conta a pagar VENCIDA [conta c1]. x")], "recepcao", h(19), {}) == []


def test_resumo_da_manha_uma_vez_e_so_se_houver_tarefa():
    tarefas = [t(1, "Cobrar parcela em atraso (sugestão) [paciente p]. x"), t(2, "Fechar o caixa do dia [caixa x]. y", prio="verde")]
    est = {}
    assert not any(a.chave == "resumo" for a in decidir(POP, tarefas, "recepcao", h(8, 10), est))   # cedo demais
    av = decidir(POP, tarefas, "recepcao", h(8, 35), est)
    resumo = next(a for a in av if a.chave == "resumo")
    assert "2 tarefa(s)" in resumo.texto and "1 urgente(s)" in resumo.texto and resumo.texto.startswith("Bom dia")
    assert not any(a.chave == "resumo" for a in decidir(POP, tarefas, "recepcao", h(9), est))        # não repete
    assert decidir(POP, [], "recepcao", h(8, 35), {}) == []                                          # sem tarefas: não incomoda


def test_urgente_insiste_a_cada_2_horas_ate_resolver():
    tarefas = [t(1, "Conta a pagar VENCIDA [conta c1]. x")]
    est = {}
    assert [a.chave for a in decidir(POP, tarefas, "recepcao", h(9), est)] == ["resumo", "urgente|0"] or "urgente|0" in [a.chave for a in decidir(POP, tarefas, "recepcao", h(9), {})]
    est = {}
    decidir(POP, tarefas, "recepcao", h(9), est)
    assert not any(a.chave.startswith("urgente") for a in decidir(POP, tarefas, "recepcao", h(10, 30), est))   # só 1h30
    assert any(a.chave.startswith("urgente") for a in decidir(POP, tarefas, "recepcao", h(11, 5), est))        # passou 2h
    tarefas[0].estado = "fechada"
    assert not any(a.chave.startswith("urgente") for a in decidir(POP, tarefas, "recepcao", h(13), est)) and est["urgentes"] == {}


def test_tom_endurece_com_os_dias_em_aberto():
    for dias, esperado in ((0, "URGENTE"), (1, "ATRASADO"), (2, "ATRASADO"), (3, "IGNORADO"), (6, "IGNORADO")):
        av = decidir(POP, [t(1, "Compra CRÍTICA aguardando decisão do dono [compra k]. x", "lucas", dias_atras=dias)], "lucas", h(9), {"resumo": "2026-03-10"})
        assert av and av[0].texto.startswith(esperado), (dias, av)


def test_aviso_nunca_leva_nome_nem_id_de_paciente():
    tarefas = [t(1, "Cobrar parcela em atraso (sugestão) [paciente p42]. 2 parcela(s) em aberto desde 01/02 (37 dias de atraso). Contato cordial.")]
    textos = " ".join(a.texto + a.titulo for a in decidir(POP, tarefas, "recepcao", h(9), {}))
    assert "p42" not in textos and "paciente" not in textos.replace("paciente a", "") and "cobrança de parcela" in textos


def test_lucas_e_avisado_do_que_esta_parado_com_a_recepcao():
    tarefas = [t(1, "Conta a pagar a vencer [conta c]. x", "recepcao", "verde", dias_atras=3), t(2, "Fechar o caixa do dia [caixa d]. y", "recepcao", "verde", dias_atras=0)]
    av = decidir(POP, tarefas, "lucas", h(9), {})
    esc = [a for a in av if a.chave == "escalada"]
    assert len(esc) == 1 and "1 tarefa(s)" in esc[0].texto and "conta a vencer" in esc[0].texto
    assert not [a for a in decidir(POP, tarefas, "recepcao", h(9), {}) if a.chave == "escalada"]   # só o Dr. Lucas recebe a escalada


def test_cada_perfil_recebe_so_o_que_e_seu():
    tarefas = [t(1, "Compra CRÍTICA aguardando decisão do dono [compra k]. x", "lucas"), t(2, "Conta a pagar VENCIDA [conta c]. y", "recepcao")]
    rec = " ".join(a.texto for a in decidir(POP, tarefas, "recepcao", h(9), {}))
    luc = " ".join(a.texto for a in decidir(POP, tarefas, "lucas", h(9), {}))
    assert "conta vencida" in rec and "compra crítica" not in rec
    assert "compra crítica" in luc and "conta vencida" not in luc.split("Recepção")[0]


def test_backup_antigo_avisa_e_nao_repete_em_menos_de_4h():
    est = {}
    assert any(a.chave == "backup" and "30 h" in a.texto for a in decidir(POP, [], "lucas", h(9), est, idade_backup_h=30))
    assert not any(a.chave == "backup" for a in decidir(POP, [], "lucas", h(11), est, idade_backup_h=32))
    assert any(a.chave == "backup" for a in decidir(POP, [], "lucas", h(13, 5), est, idade_backup_h=34))
    assert decidir(POP, [], "lucas", h(9), {}, idade_backup_h=5) == []


def test_fechamento_do_dia_uma_vez():
    tarefas = [t(1, "Fechar o caixa do dia [caixa d]. y", prio="verde")]
    est = {"resumo": "2026-03-10"}
    assert not any(a.chave == "fechamento" for a in decidir(POP, tarefas, "recepcao", h(17, 10), est))
    assert any(a.chave == "fechamento" and "1 tarefa(s)" in a.texto for a in decidir(POP, tarefas, "recepcao", h(17, 35), est))
    assert not any(a.chave == "fechamento" for a in decidir(POP, tarefas, "recepcao", h(17, 50), est))


def test_categorias():
    assert categoria("Convênio: repasse ATRASADO [guia g]. x") == "repasse de convênio atrasado" and categoria("???") == "tarefa"


# ---------- ciclo completo (backup real em arquivo → tarefas → avisos) ----------
def _backup(pasta, nome="clinus-backup-latest.json", mtime=None):
    f = pasta / nome
    f.write_text(json.dumps({"versao": "hrpg_v1", "exportadoEm": "2026-03-10T11:00:00Z", "pacientes": [
        {"id": "p", "nome": "Ana", "tel": "71900000001", "orcamento": {"parcelas": [{"valor": 100, "venc": "2026-02-20"}], "pagamentos": []}}],
        "stores": {"clinus_contas_pagar": json.dumps([{"id": "c1", "descricao": "Aluguel", "valor": 3500, "vencimento": "2026-03-05", "status": "pendente"}])}}), encoding="utf-8")
    if mtime:
        os.utime(f, (mtime, mtime))
    return f


def test_achar_backup_pega_o_mais_recente_entre_manual_e_automatico(tmp_path):
    a = _backup(tmp_path, "hansen-rpg-backup-2026-03-01.json", 100)
    b = _backup(tmp_path, "clinus-backup-latest.json", 200)
    assert achar_backup([tmp_path]) == b and achar_backup([tmp_path / "nada"]) is None
    os.utime(a, (300, 300))
    assert achar_backup([tmp_path]) == a


def test_ciclo_completo_cobra_e_nao_repete(tmp_path):
    pasta, base = tmp_path / "bk", tmp_path / "hoje"
    pasta.mkdir()
    f = _backup(pasta)
    agora = h(9)
    os.utime(f, (agora.timestamp() - 3600, agora.timestamp() - 3600))
    enviados = []
    av1 = tick("recepcao", agora, base, [pasta], lambda ti, tx: enviados.append((ti, tx)))
    assert any("URGENTE" in x[1] and "conta vencida" in x[1] for x in enviados)                   # processou o backup e já cobrou
    assert "Ana" not in " ".join(x[1] for x in enviados)
    n = len(enviados)
    tick("recepcao", h(9, 15), base, [pasta], lambda ti, tx: enviados.append((ti, tx)))
    assert len(enviados) == n                                                                      # 15 min depois: não insiste
    tick("recepcao", h(11, 5), base, [pasta], lambda ti, tx: enviados.append((ti, tx)))
    assert len(enviados) > n                                                                       # 2h depois: insiste


def test_backup_quebrado_nao_derruba_a_cobranca(tmp_path):
    pasta, base = tmp_path / "bk", tmp_path / "hoje"
    pasta.mkdir()
    (pasta / "clinus-backup-latest.json").write_text("{ isto não é json", encoding="utf-8")
    tick("lucas", h(9), base, [pasta], lambda *_: None)  # não pode lançar exceção


def test_linha_de_comando(tmp_path):
    pasta = tmp_path / "bk"
    pasta.mkdir()
    f = _backup(pasta)
    (tmp_path / "maestro.config.json").write_text(json.dumps({"pastas_backup": [str(pasta)]}), encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"), "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run([sys.executable, "-m", "hansen.maestro_vivo", "--perfil", "recepcao", "--agora", "2026-03-10T09:00", "--sem-aviso"],
                       capture_output=True, text=True, env=env, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert "[aviso]" in r.stdout and "Ana" not in r.stdout
