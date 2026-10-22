from hansen.folha_aprovacao import POPS_DA_FOLHA, gerar
from hansen.yaml_parser import carregar_todos


def test_folha_reflete_os_yamls(tmp_path):
    html = gerar(tmp_path / "f.html").read_text(encoding="utf-8")
    for pid in POPS_DA_FOLHA:
        assert f"{pid} ·" in html
    assert "15% de abatimento no clareamento" in html and "Prezado" not in html
    assert "intervalo_contato_dias = 15" in html and "dias_orcamento = 7" in html
    assert "Dra. Jussara Hansen" in html and "validar com o CRO" in html


def test_folha_muda_quando_o_yaml_muda(tmp_path):
    pops = carregar_todos()
    for r in pops["CM-01"].regras_de_decisao:
        if r.efeito == "enviar_parabens":
            r.parametros["desconto_clareamento"] = 0
    html = gerar(tmp_path / "f.html", pops).read_text(encoding="utf-8")
    assert "abatimento no clareamento" not in html  # oferta desligada: texto simples, folha acompanha
