"""Cérebro: LLM que interpreta mensagens. Só classifica; nunca decide nem faz ação clínica."""
import json
from dataclasses import dataclass
from typing import Protocol

# Tipos que o cérebro pode devolver = POPs implementados no Maestro. Fora disso, humano.
TIPOS_PERMITIDOS = {"triagem", "outro"}
CONFIANCA_MINIMA = 0.8
# Sinais de urgência/risco clínico: nunca passam pelo LLM, vão direto ao humano.
RISCO_CLINICO = ("sangr", "desmai", "febre", "inchaco", "inchaço", "dor forte", "alergia", "emergencia", "emergência")

PROMPT = (
    "Você classifica mensagens de pacientes de uma clínica odontológica. "
    "Responda APENAS JSON: {\"tipo\": \"triagem|outro\", \"confianca\": 0 a 1}. "
    "Use 'triagem' se o paciente pede atendimento/procedimento/agendamento. "
    "Nunca dê diagnóstico, conselho clínico ou resposta ao paciente."
)


class LLM(Protocol):
    def completar(self, sistema: str, usuario: str) -> str: ...


@dataclass
class Intencao:
    tipo: str
    confianca: float
    origem: str  # llm | regra_risco | fallback


class AnthropicLLM:
    def __init__(self, modelo: str = "claude-haiku-5-5"):
        import anthropic  # import tardio: o resto do sistema roda sem a SDK

        self._c, self._modelo = anthropic.Anthropic(), modelo

    def completar(self, sistema: str, usuario: str) -> str:
        r = self._c.messages.create(
            model=self._modelo, max_tokens=100, system=sistema,
            messages=[{"role": "user", "content": usuario}],
        )
        return r.content[0].text


class Cerebro:
    def __init__(self, llm: LLM):
        self.llm = llm

    def interpretar(self, texto: str) -> Intencao:
        if any(s in texto.lower() for s in RISCO_CLINICO):
            return Intencao("outro", 1.0, "regra_risco")
        try:
            dados = json.loads(self.llm.completar(PROMPT, texto))
            tipo, conf = dados["tipo"], float(dados["confianca"])
        except Exception:  # LLM fora do ar, JSON inválido... nunca improvisar
            return Intencao("outro", 0.0, "fallback")
        if tipo not in TIPOS_PERMITIDOS or conf < CONFIANCA_MINIMA:
            return Intencao("outro", conf, "fallback")
        return Intencao(tipo, conf, "llm")
