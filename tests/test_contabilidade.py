import json
from datetime import datetime

from hansen.canal import CanalSimulado, Notificador
from hansen.clinus import carregar_backup
from hansen.ledger import LedgerManager
from hansen.maestro import Maestro
from hansen.rotina_contabilidade import rodar
from hansen.yaml_parser import carregar_todos

PACS = [{"id": "p1", "nome": "Ana Souza", "orcamento": {"pagamentos": [{"d": "10/02/2026", "valor": "R$ 500,00"}, {"d": "11/03/2026", "valor": "R$ 100,00"}, {"d": "05/03/2025", "valor": "R$ 900,00"}]}}]
STORES = {"clinus_contas_pagar": json.dumps([{"id": "c1", "descricao": "Aluguel", "valor": "1000", "vencimento": "2026-02-05", "status": "pago"},
                                              {"id": "c2", "descricao": "Luz", "valor": "200", "vencimento": "2026-02-20", "status": "aberto"}]),
          "clinus_compras": json.dumps([{"id": "k1", "produto": "Resina", "qtd": 2, "status": "aprovado", "data": "2026-02-03"}])}


def _setup(tmp_path):
    f = tmp_path / "b.json"
    f.write_text(json.dumps({"versao": "hrpg_v1", "pacientes": PACS, "stores": STORES}), encoding="utf-8")
    led = LedgerManager(tmp_path / "l")
    m = Maestro(led, estado=tmp_path / "est", notificador=Notificador(CanalSimulado(), led, carregar_todos()["R-02"]))
    return m, carregar_backup(f)


def test_fechamento_mensal_e_ir(tmp_path):
    m, c = _setup(tmp_path)
    itens = rodar(m, c, datetime(2026, 3, 2, 9, 0), tmp_path / "out")
    assert [i.tipo for i in itens] == ["enviar_contador", "preparar_ir"]
    assert "R$ 500.00" in itens[0].resultado and "despesas pagas R$ 1000.00" in itens[0].resultado
    assert "Ana" in (tmp_path / "out/IR-2025/informes_pacientes.csv").read_text(encoding="utf-8-sig")
    # nenhum nome de paciente nas tarefas
    assert all("Ana" not in t.titulo for t in m.tarefas.tarefas.values())
    assert rodar(m, c, datetime(2026, 3, 2, 15, 0), tmp_path / "out") == []  # sem repetir


def test_sem_cobranca_fora_da_epoca(tmp_path):
    m, c = _setup(tmp_path)
    itens = rodar(m, c, datetime(2026, 8, 3, 9, 0), tmp_path / "out")
    assert [i.tipo for i in itens] == ["enviar_contador"]  # agosto não é época de IR
