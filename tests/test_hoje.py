import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from hansen.hoje import achar_backup_recente, executar, saudacao

AG = [{"id": "a1", "pacId": "p1", "data": "2026-03-11", "hora": "09:00", "status": "agendado"}]
PACS = [
    {"id": "p1", "nome": "Ana", "tel": "71900000001", "nascimento": "1990-03-10", "consentimentoComercial": True, "ultimaAcao": "2026-03-01T00:00:00Z"},
    {"id": "p2", "nome": "Bia", "tel": "71900000002", "decisao": "pensar", "ultimaAcao": "2026-02-20T00:00:00Z"},
    {"id": "p3", "nome": "Caio", "tel": "71900000003", "orcamento": {"parcelas": [{"valor": 100, "venc": "2026-02-20"}], "pagamentos": []}},
]
STORES = {"clinus_agenda_v2": json.dumps(AG),
          "clinus_contas_pagar": json.dumps([{"id": "c1", "descricao": "Aluguel", "valor": "3.500,00", "vencimento": "2026-03-05", "status": "pendente"}]),
          "clinus_guias": json.dumps([{"id": "g1", "pacId": "p1", "convenio": "Petrobras", "valor": "500", "status": "enviada", "envio": "2026-03-01"}])}
AGORA = datetime(2026, 3, 10, 10, 0)


def _backup(tmp_path):
    f = tmp_path / "hansen-rpg-backup-2026-03-10.json"
    f.write_text(json.dumps({"versao": "hrpg_v1", "exportadoEm": "2026-03-10T12:00:00Z", "pacientes": PACS, "stores": STORES}), encoding="utf-8")
    return f


def test_painel_do_dia_junta_tudo(tmp_path):
    html = executar(_backup(tmp_path), AGORA, tmp_path / "hoje").read_text(encoding="utf-8")
    assert "Painel do dia" in html and "Bom dia, Dr. Lucas" in html and "<svg" in html  # mascote + saudação
    assert "Mensagens prontas" in html and "feliz aniversário" in html and "Ana" not in html.split("Mensagens prontas")[0]
    assert "analisar o plano" in html            # comercial: orçamento do Bia
    assert "Parcela em atraso" in html and "Caio" in html     # financeiro: cartão da parcela do Caio
    assert "Conta a pagar VENCIDA" in html and "Aluguel" in html
    assert "Convênio: autorização pendente" in html
    assert "cadeia íntegra" in html and "wa.me/55" in html


def test_mensagens_do_dia_sobrevivem_a_segunda_execucao(tmp_path):
    b = _backup(tmp_path)
    executar(b, AGORA, tmp_path / "hoje")
    html = executar(b, AGORA, tmp_path / "hoje").read_text(encoding="utf-8")  # 2ª rodada: o sistema não "reenvia", mas o painel mantém os cartões do dia
    assert "feliz aniversário" in html


def test_ledger_do_painel_sem_dados_de_paciente(tmp_path):
    executar(_backup(tmp_path), AGORA, tmp_path / "hoje")
    txt = "".join(p.read_text(encoding="utf-8") for p in (tmp_path / "hoje" / "ledger").glob("*.json"))
    assert not any(x in txt for x in ("Ana", "Bia", "Caio", "7190000"))


def test_achar_backup_mais_recente(tmp_path):
    a = tmp_path / "hansen-rpg-backup-A.json"; a.write_text("{}")
    b = tmp_path / "hansen-rpg-backup-B.json"; b.write_text("{}")
    os.utime(a, (1, 1)); os.utime(b, (2, 2))
    assert achar_backup_recente(tmp_path) == b and achar_backup_recente(tmp_path / "nada") is None


def test_saudacao_por_hora():
    assert saudacao(datetime(2026, 1, 1, 8), 3, 1).startswith("Bom dia") and "1 urgente" in saudacao(datetime(2026, 1, 1, 8), 3, 1)
    assert saudacao(datetime(2026, 1, 1, 15), 0, 0).startswith("Boa tarde") and "Nada pendente" in saudacao(datetime(2026, 1, 1, 15), 0, 0)
    assert saudacao(datetime(2026, 1, 1, 20), 2, 0).startswith("Boa noite")


def test_roda_pela_linha_de_comando(tmp_path):
    b = _backup(tmp_path)
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"), "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run([sys.executable, "-m", "hansen.hoje", str(b)], capture_output=True, text=True, env=env, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert "PAINEL DO DIA" in r.stdout and (tmp_path / "saida" / "hoje" / "painel_do_dia.html").exists()
    r2 = subprocess.run([sys.executable, "-m", "hansen.hoje", str(tmp_path / "nao_existe.json")], capture_output=True, text=True, env=env, cwd=tmp_path)
    assert r2.returncode != 0 and "não encontrado" in (r2.stderr + r2.stdout)
