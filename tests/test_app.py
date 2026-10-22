import http.client
import json
import threading
from datetime import datetime
from pathlib import Path

import pytest

from hansen.app import Servico, criar_servidor, ler_ou_criar_token

AGORA = datetime(2026, 3, 10, 10, 0)
PACS = [
    {"id": "p1", "nome": "Ana Exemplo", "tel": "71900000001", "orcamento": {"parcelas": [{"valor": 100, "venc": "2026-02-20"}], "pagamentos": []}},
    {"id": "p2", "nome": "Bia Exemplo", "tel": "71900000002", "decisao": "pensar", "ultimaAcao": "2026-02-20T00:00:00Z", "nascimento": "1990-03-10", "consentimentoComercial": True},
]
STORES = {"clinus_contas_pagar": json.dumps([{"id": "c1", "descricao": "Aluguel", "valor": 3500, "vencimento": "2026-03-05", "status": "pendente"}])}


def _backup(pasta: Path):
    pasta.mkdir(parents=True, exist_ok=True)
    f = pasta / "clinus-backup-latest.json"
    f.write_text(json.dumps({"versao": "hrpg_v1", "exportadoEm": "2026-03-10T12:00:00Z", "pacientes": PACS, "stores": STORES}), encoding="utf-8")
    return f


@pytest.fixture
def srv(tmp_path):
    _backup(tmp_path / "bk")
    servico = Servico(tmp_path / "hoje", [tmp_path / "bk"], agora=lambda: AGORA)
    token = ler_ou_criar_token(tmp_path / "hoje")
    httpd = criar_servidor(servico, token, porta=0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield servico, token, httpd.server_address[1]
    httpd.shutdown()


def chamar(porta, metodo, caminho, corpo=None, host="127.0.0.1"):
    c = http.client.HTTPConnection("127.0.0.1", porta, timeout=10)
    c.request(metodo, caminho, body=json.dumps(corpo) if corpo is not None else None, headers={"Host": f"{host}:{porta}", "Content-Type": "application/json"})
    r = c.getresponse()
    dado = r.read()
    return r.status, dado


def test_sem_token_ou_host_estranho_e_negado(srv):
    _, token, porta = srv
    assert chamar(porta, "GET", "/")[0] == 403
    assert chamar(porta, "GET", "/api/estado?perfil=lucas&k=errado")[0] == 403
    assert chamar(porta, "GET", f"/api/estado?perfil=lucas&k={token}", host="evil.com")[0] == 403   # DNS rebinding
    assert chamar(porta, "POST", "/api/concluir", {"id": 1})[0] == 403


def test_pagina_abre_com_o_codigo(srv):
    _, token, porta = srv
    st, corpo = chamar(porta, "GET", f"/?k={token}")
    assert st == 200 and b"Maestro Hansen" in corpo and b"Feito" in corpo


def test_estado_da_recepcao_e_do_dr_lucas(srv):
    _, token, porta = srv
    rec = json.loads(chamar(porta, "GET", f"/api/estado?perfil=recepcao&k={token}")[1])
    luc = json.loads(chamar(porta, "GET", f"/api/estado?perfil=lucas&k={token}")[1])
    assert not rec["sem_backup"] and rec["backup"]["nome"] == "clinus-backup-latest.json"
    rotulos = {c["rotulo"] for c in rec["cartoes"]} | {t["categoria"] for t in rec["tarefas"]}
    assert "Parcela em atraso" in rotulos and "conta vencida" in rotulos
    assert any("analisar o plano" in c["texto"] for c in luc["cartoes"])           # orçamento da Bia vai para o Dr. Lucas
    assert rec["resumo"]["urgentes"] >= 2 and rec["saudacao"].startswith("Bom dia")
    assert any("feliz aniversário" in m["texto"] for m in rec["mensagens"]) and luc["mensagens"] == []


def test_botao_feito_fecha_a_tarefa(srv):
    _, token, porta = srv
    rec = json.loads(chamar(porta, "GET", f"/api/estado?perfil=recepcao&k={token}")[1])
    conta = next(t for t in rec["tarefas"] if t["categoria"] == "conta vencida")
    st, corpo = chamar(porta, "POST", f"/api/concluir?k={token}", {"id": conta["id"], "perfil": "recepcao"})
    assert st == 200 and json.loads(corpo)["ok"]
    depois = json.loads(chamar(porta, "GET", f"/api/estado?perfil=recepcao&k={token}")[1])
    assert all(t["id"] != conta["id"] for t in depois["tarefas"])
    assert not json.loads(chamar(porta, "POST", f"/api/concluir?k={token}", {"id": 99999})[1])["ok"]


def test_avisos_na_tela_sem_nome_de_paciente_e_sem_repetir(srv):
    _, token, porta = srv
    e1 = json.loads(chamar(porta, "GET", f"/api/estado?perfil=recepcao&k={token}")[1])
    textos = " ".join(a["texto"] for a in e1["avisos"])
    assert "Ana" not in textos and "Bia" not in textos and any("URGENTE" in a["texto"] for a in e1["avisos"])
    e2 = json.loads(chamar(porta, "GET", f"/api/estado?perfil=recepcao&k={token}")[1])
    assert e2["avisos"] == []                                                         # não insiste antes de 2 h


def test_backup_arrastado_para_a_pagina(tmp_path):
    servico = Servico(tmp_path / "hoje", [tmp_path / "nada"], agora=lambda: AGORA)
    assert servico.estado("lucas")["sem_backup"]
    assert "JSON" in servico.salvar_backup_manual("isto não é json")
    assert "backup do Clinus" in servico.salvar_backup_manual(json.dumps({"versao": "outro"}))
    bom = json.dumps({"versao": "hrpg_v1", "pacientes": PACS, "stores": STORES})
    assert servico.salvar_backup_manual(bom) == ""
    assert not servico.estado("recepcao")["sem_backup"]


def test_backup_quebrado_nao_derruba(tmp_path):
    (tmp_path / "bk").mkdir()
    (tmp_path / "bk" / "clinus-backup-latest.json").write_text("{ não é json", encoding="utf-8")
    servico = Servico(tmp_path / "hoje", [tmp_path / "bk"], agora=lambda: AGORA)
    e = servico.estado("lucas")
    assert e["sem_backup"] and "Não consegui ler" in e["erro"]


def test_token_persiste(tmp_path):
    assert ler_ou_criar_token(tmp_path) == ler_ou_criar_token(tmp_path)
