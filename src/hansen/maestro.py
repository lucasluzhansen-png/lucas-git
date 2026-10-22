"""Maestro: orquestra os POPs. Decide só o que o YAML permite; risco clínico vai para humano."""
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from hansen.tarefas import _ler_json_ou_isolar
from hansen.agentes.comercial import Comercial
from hansen.agentes.financeiro import Financeiro
from hansen.agentes.contabilidade import Contabilidade
from hansen.agentes.jornada import Jornada
from hansen.agentes.auditoria import Auditoria
from hansen.agentes.sala_espera import SalaEspera
from hansen.agentes.laboratorio import Laboratorio
from hansen.agentes.recepcao import Recepcao
from hansen.agentes.rotina import Rotina
from hansen.canal import Notificador
from hansen.cerebro import Cerebro
from hansen.clinus import ClinusDados
from hansen.ledger import LedgerManager
from hansen.tarefas import TarefaManager
from hansen.textos import texto as montar_texto
from hansen.yaml_parser import POP, carregar_todos

# Quem pode agir sozinho. Tudo o resto vira pedido de aprovação humana.
AUTONOMOS = {"IA_AUDITA", "IA_EXECUTA", "IA_SOZINHA"}  # só agem sozinhos se aprovacao_humana=false no YAML


@dataclass
class Decisao:
    pop_id: str
    estado: str  # executado | aguarda_humano | escalado_humano
    acao: str
    detalhe: str
    tarefa_id: int | None = None
    envio: str | None = None  # enviado | fora_da_janela | None


class Maestro:
    def __init__(self, ledger: LedgerManager, pops: dict[str, POP] | None = None, cerebro: Cerebro | None = None,
                 estado: Path | None = None, notificador: Notificador | None = None,
                 clinus: ClinusDados | None = None):
        self.ledger = ledger
        self.cerebro = cerebro
        self.pops = pops or carregar_todos()
        self.agentes = [Recepcao(self.pops), Rotina(), Comercial(self.pops), Financeiro(), Laboratorio(), Contabilidade(), Jornada(), SalaEspera(), Auditoria()]
        self.notificador = notificador
        self.clinus = clinus
        self._arq_pausas = Path(estado) / "pausas.json" if estado else None
        if estado:
            Path(estado).mkdir(parents=True, exist_ok=True)
        self.resolvidas_auto = 0  # tarefas fechadas sozinhas porque o Clinus mostra que a situação acabou
        self.pausados: set[str] = set(_ler_json_ou_isolar(self._arq_pausas, [])) if self._arq_pausas and self._arq_pausas.exists() else set()
        self.tarefas = TarefaManager(ledger, self.pops["A-06"], arquivo=Path(estado) / "tarefas.json" if estado else None)

    def receber_mensagem(self, texto: str, dados: dict | None = None) -> Decisao:
        """Entrada em texto livre: o cérebro classifica, o resto segue o YAML."""
        i = self.cerebro.interpretar(texto)
        return self.processar(i.tipo, texto, dados)

    def processar(self, tipo: str, texto: str = "", dados: dict | None = None) -> Decisao:
        dados = dict(dados or {})
        if self.clinus and "paciente_atual" not in dados and dados.get("telefone"):
            dados["paciente_atual"] = self.clinus.eh_paciente_atual(dados["telefone"])  # telefone no cadastro do Clinus
        agente = next((a for a in self.agentes if tipo in a.tipos), None)
        if agente is None:  # sem agente para o evento: nunca improvisar
            return self._fechar("-", "escalado_humano", "sem_agente", "Sem agente para este evento.", tipo, texto, dados)
        if agente.nome in self.pausados:  # veto do RT: agente pausado nunca age
            return self._fechar("-", "escalado_humano", "agente_pausado", f"Agente {agente.nome} pausado pelo RT.", tipo, texto, dados)
        prop = agente.tratar(tipo, texto, dados)
        if prop is None:
            return self._fechar("-", "escalado_humano", "sem_regra", "Nenhuma regra aplicável.", tipo, texto, dados)
        pop = self.pops[prop.pop_id]
        # Regra de ouro: autonomia vem do nível do POP, não do código.
        autonomo = pop.automacao.nivel in AUTONOMOS and not pop.automacao.aprovacao_humana
        estado = "executado" if autonomo else "aguarda_humano"
        return self._fechar(prop.pop_id, estado, prop.efeito, prop.detalhe, tipo, texto, dados, prop.tarefa, prop.mensagem)

    def pausar(self, agente: str, por: str, papel: str) -> bool:
        return self._alternar_pausa(agente, por, papel, pausar=True)

    def retomar(self, agente: str, por: str, papel: str) -> bool:
        return self._alternar_pausa(agente, por, papel, pausar=False)

    def _alternar_pausa(self, agente, por, papel, pausar) -> bool:
        """Só o RT pausa/retoma, e só agentes que existem. Tudo fica no ledger."""
        acao = "pausar_agente" if pausar else "retomar_agente"
        ok = papel == "rt" and agente in {a.nome for a in self.agentes}
        if ok:
            (self.pausados.add if pausar else self.pausados.discard)(agente)
            if self._arq_pausas:
                self._arq_pausas.write_text(json.dumps(sorted(self.pausados)), encoding="utf-8")
        self.ledger.registar(
            pop_id="-", ator={"type": "humano", "id": por, "papel": papel}, acao=acao,
            resultado="sucesso" if ok else "falha", entrada={"agente": agente}, saida={},
            privacidade={"dado_sensivel": False, "base_legal_lgpd": "obrigacao_legal", "retencao_anos": 5},
        )
        return ok

    def _fechar(self, pop_id, estado, acao, detalhe, tipo, texto, dados=None, tarefa_req=None, mensagem=None) -> Decisao:
        dados = dados or {}
        self.ledger.registar(
            pop_id=pop_id,
            ator={"type": "agente_ia", "id": "maestro", "papel": "orquestrador"},
            acao=str(acao),
            resultado="sucesso",
            entrada={"tipo": tipo, "texto": texto, "dados": {k: v for k, v in dados.items() if k not in ("telefone", "nome")}},
            saida={"estado": estado, "detalhe": detalhe},
            privacidade={"dado_sensivel": True, "base_legal_lgpd": "execucao_contrato", "retencao_anos": 5},
        )
        if acao == "enviar_lembrete" and estado == "executado" and self.notificador and dados.get("telefone"):
            self.notificador.lembrete_paciente(
                dados.get("nome", ""), dados["telefone"], datetime.fromisoformat(dados["consulta_em"]), datetime.fromisoformat(dados["agora"]))
        envio = None
        if mensagem and estado == "executado" and self.notificador and dados.get("telefone") and dados.get("agora"):
            texto_msg = montar_texto(self.pops[mensagem["pop"]], mensagem["template"], dados.get("nome", ""), data_hora=dados.get("data_hora", ""))
            envio = self.notificador.enviar_texto(pop_id, str(acao), dados["telefone"], texto_msg, datetime.fromisoformat(dados["agora"]))
        if dados.get("ref_txt"):
            ref = dados["ref_txt"]
        elif dados.get("consulta_id"):
            ref = f"consulta {dados['consulta_id']}"
        elif dados.get("ref"):
            ref = f"paciente {dados['ref']}"
        else:
            ref = None
        tarefa = self._tarefa_para_humano(pop_id, estado, str(acao), detalhe, tarefa_req, ref)
        return Decisao(pop_id, estado, str(acao), detalhe, tarefa.id if tarefa else None, envio)

    def _tarefa_para_humano(self, pop_id, estado, acao, detalhe, tarefa_req=None, ref=None):
        """Tudo que depende de gente vira tarefa cobrada pelo A-06; o que a IA executou sozinha, não."""
        if tarefa_req and estado == "executado":  # pedido explícito do agente (ex.: A-06 IA_EXECUTA)
            return self.tarefas.criar(**tarefa_req)
        if estado == "executado" and acao != "marcar_no_show":
            return None
        prioridade = "verde" if estado == "aguarda_humano" and acao not in ("atendimento_clinico_humano", "cobrar_atraso", "pagar_conta_vencida", "decidir_compra_critica", "cobrar_repasse", "recurso_glosa", "baixa_pendente", "cobrar_lab", "sla_lab", "conferir_peca", "os_problema", "agendar_peca", "enviar_contador", "prazo_ir", "confirmacao_bloqueada", "paciente_esperando") else "amarela"
        titulo = {
            "marcar_no_show": "Ligar ao paciente: risco de no-show",
            "agente_pausado": "Agente pausado pelo RT: tratar este pedido manualmente",
            "sem_agente": "Pedido sem agente responsável: tratar manualmente",
            "sem_regra": "A IA não encontrou regra para este pedido: tratar manualmente",
            "encaminhar_agendamento": "Agendar paciente: serviço realizado pela clínica",
            "atendimento_clinico_humano": "Paciente atual: dentista faz o 1º atendimento e encaminha",
            "retomar_orcamento": "Retomar contato: orçamento em aberto ('vai pensar')",
            "reativar_paciente": "Reativar paciente parado: contato de relacionamento",
            "revisar_manutencao": "Contatar para revisão/manutenção vencida",
            "cobrar_atraso": "Cobrar parcela em atraso (sugestão)",
            "lembrar_vencimento": "Lembrar parcela a vencer (sugestão)",
            "pagar_conta": "Conta a pagar a vencer",
            "pagar_conta_vencida": "Conta a pagar VENCIDA",
            "decidir_compra": "Compra aguardando decisão do dono",
            "decidir_compra_critica": "Compra CRÍTICA aguardando decisão do dono",
            "fazer_pedido": "Compra aprovada: fazer o pedido",
            "agendar_preventiva": "Agendar manutenção preventiva de equipamento",
            "fechar_caixa": "Fechar o caixa do dia",
            "criar_guia": "Convênio: criar a guia do tratamento aprovado",
            "enviar_guia": "Convênio: guia criada e ainda não enviada",
            "cobrar_autorizacao": "Convênio: autorização pendente",
            "cobrar_repasse": "Convênio: repasse ATRASADO",
            "recurso_glosa": "Convênio: glosa sem recurso",
            "conferir_convenio": "Convênio: conferir repasses da operadora (fechamento do mês)",
            "cobrar_lab": "Laboratório: OS atrasada (cobrar o laboratório)",
            "confirmar_prazo_lab": "Laboratório: prazo vencendo (confirmar com o laboratório)",
            "sla_lab": "Laboratório: OS acima do prazo padrão",
            "registrar_prazo_lab": "Laboratório: OS enviada sem prazo registado",
            "conferir_peca": "Laboratório: peça retornou, falta a conferência",
            "os_problema": "Laboratório: OS com problema",
            "agendar_peca": "Laboratório: peça chegou e não há consulta marcada",
            "confirmacao_bloqueada": "Laboratório: confirmação suspensa, peça não conferida (confirmar a peça antes de falar com o paciente)",
            "paciente_esperando": "Sala de espera: paciente aguardando há mais de 15 minutos (ir até ele, oferecer água, informar a previsão)",
            "avisar_proximo": "Sala de espera: avisar o próximo paciente da retenção",
            "baixa_pendente": "Auditoria: paciente atendido sem baixa dos procedimentos (marcar como feito, escrever o que foi feito e abrir OS se houve prótese)",
            "iniciar_tratamento": "Jornada: plano aprovado, agendar o início do tratamento",
            "tratamento_parado": "Jornada: tratamento parado, agendar a próxima sessão",
            "retorno_alta": "Jornada: alta concluída, agendar o retorno",
            "enviar_contador": "Contabilidade: enviar o fechamento do mês ao contador",
            "preparar_ir": "Contabilidade: preparar documentos e resumo do IR",
            "prazo_ir": "Contabilidade: prazo do IR perto, confirmar entrega com o contador",
        }.get(acao) or f"Aprovar decisão da IA ({pop_id}): {acao}"
        if ref:  # referência, sem nome: dados de paciente não vão para tarefas/ledger
            titulo += f" [{ref}]"
        quem = self.pops["A-06"].responsaveis
        chave = {"marcar_no_show": "ligacao_no_show", "agente_pausado": "tratar_manual", "sem_agente": "tratar_manual", "sem_regra": "tratar_manual", "encaminhar_agendamento": "agendar_paciente", "retomar_orcamento": "contato_comercial", "reativar_paciente": "contato_comercial", "revisar_manutencao": "contato_comercial", "cobrar_atraso": "financeiro", "lembrar_vencimento": "financeiro", "pagar_conta": "financeiro", "pagar_conta_vencida": "financeiro",
                 "decidir_compra": "decisao_compras", "decidir_compra_critica": "decisao_compras", "fazer_pedido": "financeiro",
                 "agendar_preventiva": "financeiro", "fechar_caixa": "financeiro", "criar_guia": "financeiro", "enviar_guia": "financeiro",
                 "cobrar_autorizacao": "financeiro", "cobrar_repasse": "financeiro", "recurso_glosa": "financeiro", "conferir_convenio": "financeiro",
                 "cobrar_lab": "laboratorio", "confirmar_prazo_lab": "laboratorio", "sla_lab": "laboratorio", "registrar_prazo_lab": "laboratorio",
                 "conferir_peca": "laboratorio", "os_problema": "laboratorio", "agendar_peca": "laboratorio",
                 "enviar_contador": "contabilidade", "preparar_ir": "contabilidade", "prazo_ir": "contabilidade",
                 "confirmacao_bloqueada": "laboratorio", "paciente_esperando": "sala_espera", "avisar_proximo": "sala_espera", "baixa_pendente": "auditoria",
                 "iniciar_tratamento": "jornada", "tratamento_parado": "jornada", "retorno_alta": "jornada"}.get(acao, "aprovacao_ia")
        return self.tarefas.criar(f"{titulo}. {detalhe}", "maestro", quem[chave], prioridade)
