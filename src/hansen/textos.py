"""Monta mensagens a partir dos modelos do YAML. Parâmetros das regras (ex.: desconto_clareamento) ficam disponíveis como {variáveis}."""
from hansen.yaml_parser import POP


def variaveis(pop: POP, nome: str, **extra) -> dict:
    v = {"nome": nome, "primeiro_nome": (nome.split() or [""])[0], "data_hora": ""}
    for r in pop.regras_de_decisao:
        v.update(r.parametros)
    v.update(extra)
    return v


def texto(pop: POP, modelo: str, nome: str, **extra) -> str:
    return pop.mensagens[modelo].format(**variaveis(pop, nome, **extra))


def modelo_aniversario(pop_cm01: POP) -> str:
    """Com desconto_clareamento > 0 usa o modelo com oferta; com 0 usa o modelo simples (sem valor nem desconto)."""
    desconto = variaveis(pop_cm01, "").get("desconto_clareamento", 0)
    return "parabens" if desconto > 0 else "parabens_simples"
