"""Onde ficam os arquivos gerados (painéis, tarefas, registo). No Windows o projeto pode estar numa pasta protegida (ex.: C:\\Windows\\System32),
onde um programa comum não pode escrever: por isso os arquivos vão para uma pasta do PRÓPRIO usuário. Fora do Windows (e nos testes), `saida/`."""
import os
from pathlib import Path


def pasta_saida() -> Path:
    """Ordem: variável HANSEN_SAIDA → (Windows) ~/HansenMaestro/saida → ./saida."""
    if os.environ.get("HANSEN_SAIDA"):
        return Path(os.environ["HANSEN_SAIDA"])
    if os.name == "nt":
        return Path.home() / "HansenMaestro" / "saida"
    return Path("saida")
