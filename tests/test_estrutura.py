from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "hansen"


def test_bloco_main_e_sempre_a_ultima_coisa_do_arquivo():
    """Evita o erro clássico: função definida DEPOIS do `if __name__ == "__main__"` quebra a linha de comando."""
    for f in SRC.rglob("*.py"):
        texto = f.read_text(encoding="utf-8")
        marca = 'if __name__ == "__main__":'
        if marca in texto:
            depois = texto.split(marca, 1)[1]
            assert "\ndef " not in depois and "\nclass " not in depois, f.name
