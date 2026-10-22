"""Agente Recepção: triagem (R-00) e confirmação/no-show (R-02). Regras e parâmetros vêm do YAML."""
import re
import unicodedata
from datetime import datetime, timedelta

from hansen.agentes.base import Proposta
from hansen.yaml_parser import POP

TIPOS = {"triagem", "confirmacao"}


def _norm(t: str) -> str:
    return unicodedata.normalize("NFKD", t.lower()).encode("ascii", "ignore").decode()


class Recepcao:
    nome = "recepcao"
    tipos = TIPOS

    def __init__(self, pops: dict[str, POP]):
        self.r00 = pops["R-00"].regras_de_decisao
        self.r00_efeito = {r.efeito: r for r in self.r00 if r.efeito}
        self.r02 = {r.efeito: r for r in pops["R-02"].regras_de_decisao if r.efeito}

    def tratar(self, tipo: str, texto: str = "", dados: dict | None = None) -> Proposta | None:
        if tipo == "triagem":
            return self._triagem(_norm(texto), dados or {})
        return self._confirmacao(dados or {})

    @staticmethod
    def _bate(chave: str, texto: str) -> bool:
        """Início de palavra; siglas curtas (ppr, pt) só como palavra inteira, para não casar dentro de outras."""
        k = re.escape(_norm(chave))
        return re.search(rf"\b{k}\b" if len(chave) <= 3 else rf"\b{k}", texto) is not None

    def _triagem(self, texto: str, dados: dict) -> Proposta | None:
        achadas = [r for r in self.r00 if r.palavras_chave and any(self._bate(k, texto) for k in r.palavras_chave)]
        if len({r.efeito for r in achadas}) != 1:  # nenhuma regra, ou pedido ambíguo (ex.: canal + clareamento)
            return None  # o Maestro escala para humano
        r = achadas[0]
        if r.efeito == "bloquear" and dados.get("paciente_atual"):
            r = self.r00_efeito["atendimento_clinico_humano"]  # paciente da casa: dentista atende e encaminha
        return Proposta("R-00", r.efeito, r.acao)

    def _confirmacao(self, d: dict) -> Proposta | None:
        agora, consulta = datetime.fromisoformat(d["agora"]), datetime.fromisoformat(d["consulta_em"])
        if d.get("respondeu"):
            return Proposta("R-02", "confirmar", "Paciente confirmou.")
        ns = self.r02["marcar_no_show"]
        if consulta - agora <= timedelta(hours=ns.parametros["horas_antes"]):
            return Proposta("R-02", "marcar_no_show", ns.acao)
        jan = self.r02["adiar_envio"]
        p = jan.parametros
        if agora.weekday() >= 5 or not (p["hora_inicio"] <= agora.hour < p["hora_fim"]):
            return Proposta("R-02", "adiar_envio", jan.acao)
        return Proposta("R-02", "enviar_lembrete", "Enviar lembrete formal ao paciente.")
