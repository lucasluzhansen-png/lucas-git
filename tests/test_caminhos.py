import types
from pathlib import Path

from hansen import caminhos, notificacao
from hansen.maestro_vivo import carregar_config
from hansen.tarefas_cli import main


def test_fora_do_windows_usa_saida_local(monkeypatch):
    monkeypatch.delenv("HANSEN_SAIDA", raising=False)
    assert caminhos.pasta_saida() == Path("saida")


def test_no_windows_usa_a_pasta_do_usuario_e_nao_a_do_projeto(monkeypatch, tmp_path):
    monkeypatch.setattr(caminhos, "os", types.SimpleNamespace(name="nt", environ={}))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    assert caminhos.pasta_saida() == tmp_path / "HansenMaestro" / "saida"   # nunca dentro de C:\Windows\System32


def test_variavel_de_ambiente_manda_em_tudo(monkeypatch, tmp_path):
    monkeypatch.setenv("HANSEN_SAIDA", str(tmp_path / "x"))
    assert caminhos.pasta_saida() == tmp_path / "x"
    notificacao.registrar_log("Maestro", "teste")           # o aviso de teste não pode falhar por permissão
    assert "teste" in (tmp_path / "x" / "hoje" / "avisos.log").read_text(encoding="utf-8")


def test_config_tambem_e_lida_da_pasta_do_usuario(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)                              # projeto sem config
    pasta = tmp_path / "usuario" / "saida"
    monkeypatch.setenv("HANSEN_SAIDA", str(pasta))
    (pasta.parent).mkdir(parents=True)
    (pasta.parent / "maestro.config.json").write_text('{"pastas_backup": ["D:/nuvem"]}', encoding="utf-8")
    assert carregar_config()["pastas_backup"] == ["D:/nuvem"]


def test_tarefas_cli_aceita_so_o_nome_da_pasta(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("HANSEN_SAIDA", str(tmp_path / "s"))
    (tmp_path / "s" / "financeiro" / "estado").mkdir(parents=True)
    (tmp_path / "s" / "financeiro" / "estado" / "tarefas.json").write_text("[]", encoding="utf-8")
    assert main(["financeiro", "listar"]) == 0
