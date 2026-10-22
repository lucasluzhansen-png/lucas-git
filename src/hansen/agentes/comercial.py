"""Agente Comercial: relacionamento (CM-01, a IA envia lembretes simples) e retomada de orçamentos/reativação (CM-02, só sugere).
Nunca cita valores, descontos ou condições de pagamento."""
from hansen.agentes.base import Proposta
from hansen.textos import modelo_aniversario
from hansen.yaml_parser import POP


class Comercial:
    nome = "comercial"
    tipos = {"aniversario", "retorno", "orcamento_aberto", "paciente_parado", "manutencao_vencida"}

    def __init__(self, pops: dict[str, POP]):
        self.responsavel = pops["A-06"].responsaveis["contato_comercial"]
        self.modelo_aniv = modelo_aniversario(pops["CM-01"])

    def tratar(self, tipo: str, texto: str = "", dados: dict | None = None) -> Proposta | None:
        d = dados or {}
        ref = d.get("ref", "?")
        if tipo == "aniversario":
            if not d.get("consentimento"):  # sem opt-in registado, a IA não envia
                return Proposta("CM-01", "sem_consentimento", "Aniversariante sem consentimento registado: contato manual.", tarefa={
                    "titulo": f"Parabenizar aniversariante [paciente {ref}] (sem consentimento para envio automático)",
                    "solicitante": "maestro", "responsavel": self.responsavel, "prioridade": "verde"})
            return Proposta("CM-01", "enviar_parabens", "Mensagem formal de aniversário.", mensagem={"pop": "CM-01", "template": self.modelo_aniv})
        if tipo == "retorno":
            return Proposta("CM-01", "enviar_lembrete_retorno", "Lembrete formal do retorno agendado.",
                            mensagem={"pop": "CM-01", "template": "retorno_agendado"})
        if tipo == "orcamento_aberto":
            return Proposta("CM-02", "retomar_orcamento", f"Orçamento em aberto há {d.get('dias', '?')} dias. Retomar sem citar valores ou descontos.")
        if tipo == "manutencao_vencida":
            return Proposta("CM-02", "revisar_manutencao", f"Tratamento concluído há {d.get('dias', '?')} dias sem contato. Sugerir revisão/manutenção, sem promoções.")
        if tipo == "paciente_parado":
            return Proposta("CM-02", "reativar_paciente", f"Sem contato há {d.get('dias', '?')} dias. Contato de relacionamento, sem promoções.")
        return None
