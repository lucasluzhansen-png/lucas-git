"""Demo Sprint 1: triagem R-00 validada e assinada."""
import json
import tempfile

from hansen.ledger import LedgerManager
from hansen.yaml_parser import carregar_todos

pops = carregar_todos()
r00 = pops["R-00"]
ledger = LedgerManager(tempfile.mkdtemp(prefix="ledger_"))
ev = ledger.registar(
    pop_id=r00.id,
    ator={"type": "agente_ia", "id": "agente_triagem", "papel": "recepcao"},
    acao="bloquear_agendamento",
    entrada={"queixa": "Preciso fazer um canal (Endodontia)"},
    saida={"regra": r00.regras_de_decisao[0].acao},
    privacidade={"dado_sensivel": False, "base_legal_lgpd": "execucao_contrato", "retencao_anos": 5},
)
print(json.dumps(ev, ensure_ascii=False, indent=2))
print("\nCadeia íntegra:", ledger.verificar())
