import json
from datetime import datetime

from hansen.clinus import carregar_backup
from hansen.ledger import LedgerManager
from hansen.maestro import Maestro

AGENDA = [
    {"id": "e1", "pacId": "p1", "nome": "Maria", "data": "2026-01-07", "hora": "09:00", "status": "agendado"},
    {"id": "e2", "pacId": "p1", "data": "2026-01-07", "hora": "10:00", "status": "faltou"},
    {"id": "e3", "pacId": "p2", "data": "2026-01-09", "hora": "09:00", "status": "confirmado"},
    {"id": "e4", "data": "lixo", "hora": "x"},
]


def _backup(tmp_path):
    f = tmp_path / "backup.json"
    f.write_text(json.dumps({
        "versao": "hrpg_v1", "exportadoEm": "2026-01-06T10:00:00Z",
        "pacientes": [{"id": "p1", "nome": "Maria", "tel": "(71) 99999-0000", "cpf": "000.000.000-00", "imagens": [{"data": "xxx"}]},
                      {"id": "p2", "nome": "João", "tel": ""}],
        "stores": {"clinus_agenda_v2": json.dumps(AGENDA)},
    }), encoding="utf-8")
    return f


def test_telefone_com_ou_sem_mascara_e_ddi(tmp_path):
    d = carregar_backup(_backup(tmp_path))
    assert d.eh_paciente_atual("+55 71 99999-0000") and d.eh_paciente_atual("71999990000")
    assert not d.eh_paciente_atual("71988887777") and not d.eh_paciente_atual("")


def test_nao_guarda_cpf_nem_imagens(tmp_path):
    d = carregar_backup(_backup(tmp_path))
    assert not ({"cpf", "imagens", "anamnese", "prontuario"} & set(d.por_id["p1"]))


def test_proximas_consultas_abertas_e_com_telefone(tmp_path):
    d = carregar_backup(_backup(tmp_path))
    cs = d.proximas(datetime(2026, 1, 6, 12), horas=48)
    assert [c.id for c in cs] == ["e1"]  # e2 faltou, e3 fora da janela, e4 inválido
    assert cs[0].telefone == "(71) 99999-0000"


def test_arquivo_errado_e_recusado(tmp_path):
    f = tmp_path / "x.json"
    f.write_text('{"versao":"outro"}')
    try:
        carregar_backup(f)
        assert False
    except ValueError:
        pass


def test_maestro_usa_clinus_para_paciente_atual(tmp_path):
    m = Maestro(LedgerManager(tmp_path / "l"), clinus=carregar_backup(_backup(tmp_path)))
    atual = m.processar("triagem", "preciso de canal", {"telefone": "71999990000"})
    novo = m.processar("triagem", "preciso de canal", {"telefone": "71911112222"})
    assert (atual.acao, novo.acao) == ("atendimento_clinico_humano", "bloquear")


def test_diagnostico_nao_vaza_dados_de_paciente(tmp_path):
    from hansen.clinus import diagnostico
    txt = diagnostico(_backup(tmp_path))
    assert "Pacientes: 2" in txt and "eventos: 4" in txt
    assert "Maria" not in txt and "99999" not in txt and "000.000" not in txt


def test_diagnostico_roda_pela_linha_de_comando(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"), "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run([sys.executable, "-m", "hansen.clinus", str(_backup(tmp_path))], capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    assert "Pacientes ativos" in r.stdout and "Maria" not in r.stdout
