"""Lê e valida os POPs em YAML (fonte única de verdade)."""
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

POPS_DIR = Path(__file__).resolve().parents[2] / "volumes/Volume_2_Manual_Maquina/pops"


class Automacao(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nivel: Literal["HUMANO", "IA_SUGERE", "IA_AUDITA", "IA_EXECUTA", "IA_SOZINHA"]
    aprovacao_humana: bool


class Regra(BaseModel):
    model_config = ConfigDict(extra="forbid")
    condicao: str
    acao: str
    # Opcionais: tornam a regra executável pelo Maestro (sem lógica fixa no Python).
    palavras_chave: list[str] = []
    efeito: Literal["bloquear", "alertar_humano", "escalar", "rejeitar_fecho", "marcar_no_show", "adiar_envio", "encaminhar_agendamento", "atendimento_clinico_humano",
                    "enviar_parabens", "sem_consentimento", "enviar_lembrete_retorno", "retomar_orcamento", "reativar_paciente"] | None = None
    parametros: dict[str, int] = {}


class Passo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    numero: int
    tipo: str
    descricao: str


class Gatilho(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tipo: str
    eventos: list[str]


class POP(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    versao: str
    manual: str
    titulo: str
    automacao: Automacao
    regras_de_decisao: list[Regra] = []
    passos: list[Passo] = []
    gatilho: Gatilho | None = None
    mensagens: dict[str, str] = {}
    responsaveis: dict[str, str] = {}


def carregar_pop(path: Path) -> POP:
    pop = POP(**yaml.safe_load(path.read_text(encoding="utf-8")))
    if path.stem != pop.id:
        raise ValueError(f"{path.name}: id '{pop.id}' difere do nome do ficheiro")
    # Regra de ouro: POP humano nunca pode ser autónomo.
    if pop.automacao.nivel == "HUMANO" and not pop.automacao.aprovacao_humana:
        raise ValueError(f"{pop.id}: nível HUMANO exige aprovacao_humana=true")
    return pop


def carregar_todos(pasta: Path = POPS_DIR) -> dict[str, POP]:
    return {p.stem: carregar_pop(p) for p in sorted(pasta.glob("*.yaml"))}


if __name__ == "__main__":
    try:
        pops = carregar_todos()
    except (ValidationError, ValueError) as e:
        raise SystemExit(f"ERRO: {e}")
    for pop in pops.values():
        print(f"OK {pop.id:5} {pop.automacao.nivel:10} {pop.titulo}")
    print(f"\n{len(pops)} POPs válidos.")
