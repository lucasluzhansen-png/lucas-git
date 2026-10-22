import csv
import json

from hansen.cadastros import analisar, gravar_planilha, resumo
from hansen.clinus import carregar_backup

PACS = [
    {"id": "1", "nome": "Ana", "tel": "(71) 99999-0000", "nascimento": "1990-05-02", "ultimaAcao": "2026-10-01T00:00:00Z"},   # ok
    {"id": "2", "nome": "Bia", "tel": "", "nascimento": "1990-05-02", "ultimaAcao": "2026-10-02T00:00:00Z"},                   # sem tel
    {"id": "3", "nome": "Caio", "tel": "9999", "nascimento": "", "ultimaAcao": "2026-10-03T00:00:00Z"},                         # incompleto + sem nasc
    {"id": "4", "nome": "Davi", "tel": "", "nascimento": "", "origemImport": True, "log": [{"t": "📥 importado"}]},               # histórico
    {"id": "5", "nome": "Eva", "tel": "", "nascimento": "", "arquivado": True},                                                  # inativa
]


def _dados(tmp_path):
    f = tmp_path / "b.json"
    f.write_text(json.dumps({"versao": "hrpg_v1", "pacientes": PACS, "stores": {}}), encoding="utf-8")
    return carregar_backup(f)


def test_contagens(tmp_path):
    r = analisar(_dados(tmp_path))
    assert (r["ativos"], r["historico"], r["em_trabalho"], r["com_problema"]) == (4, 1, 3, 2)
    assert r["contagem"] == {"sem telefone": 1, "telefone incompleto": 1, "sem nascimento": 1}


def test_resumo_do_terminal_nao_tem_nomes(tmp_path):
    txt = resumo(analisar(_dados(tmp_path)))
    assert not any(n in txt for n in ("Ana", "Bia", "Caio", "Davi"))


def test_planilha_tem_nomes_e_abre_no_excel(tmp_path):
    r = analisar(_dados(tmp_path))
    arq = gravar_planilha(r["linhas"], tmp_path / "x" / "c.csv")
    bruto = arq.read_bytes()
    assert bruto.startswith(b"\xef\xbb\xbf")  # BOM utf-8
    linhas = list(csv.DictReader(arq.open(encoding="utf-8-sig"), delimiter=";"))
    assert [l["nome"] for l in linhas] == ["Caio", "Bia"]  # mais recentes primeiro


def test_roda_pela_linha_de_comando(tmp_path):
    import os, subprocess, sys
    from pathlib import Path
    f = tmp_path / "b.json"
    f.write_text(json.dumps({"versao": "hrpg_v1", "pacientes": PACS, "stores": {}}), encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"), "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run([sys.executable, "-m", "hansen.cadastros", str(f)], capture_output=True, text=True, env=env, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert "a corrigir: 2 de 3" in r.stdout and "Bia" not in r.stdout
    assert (tmp_path / "saida" / "cadastros" / "cadastros_a_corrigir.csv").exists()
