import json
from datetime import datetime

from hansen.canal import CanalSimulado, Notificador
from hansen.clinus import carregar_backup
from hansen.ledger import LedgerManager
from hansen.lembretes import rodar as lembretes
from hansen.maestro import Maestro
from hansen.rotina_sala_espera import rodar as sala
from hansen.yaml_parser import carregar_todos


def _setup(tmp_path, agenda, oss=(), nome="b"):
    f = tmp_path / f"{nome}.json"
    pac = [{"id": "p1", "nome": "Ana", "tel": "11911110001"}, {"id": "p2", "nome": "Bia", "tel": "11911110002"}]
    f.write_text(json.dumps({"versao": "hrpg_v1", "pacientes": pac, "stores": {"clinus_agenda_v2": json.dumps(agenda), "lab_os": json.dumps(list(oss))}}), encoding="utf-8")
    led = LedgerManager(tmp_path / "l")
    m = Maestro(led, estado=tmp_path / "est", notificador=Notificador(CanalSimulado(), led, carregar_todos()["R-02"]))
    return m, carregar_backup(f)


AGORA = datetime(2026, 5, 5, 10, 0)  # terça, 10h: D-1 da consulta de quarta
PROVA = {"id": "e1", "pacId": "p1", "data": "2026-05-06", "hora": "09:00", "status": "agendado", "tipo": "Prova de prótese"}
LIMPEZA = {"id": "e2", "pacId": "p2", "data": "2026-05-06", "hora": "10:00", "status": "agendado", "tipo": "Limpeza"}


def test_prova_sem_peca_conferida_nao_confirma(tmp_path):
    m, c = _setup(tmp_path, [PROVA, LIMPEZA], [{"numero": "1", "pacId": "p1", "etapa": "retornou"}])
    plano = {i.consulta.id: i for i in lembretes(m, c, AGORA)}
    assert plano["e1"].decisao is None and "SUSPENSA" in plano["e1"].nota
    assert plano["e2"].decisao.acao == "enviar_lembrete"  # consulta comum segue normal
    assert all("11911110001" not in destino for destino, _ in m.notificador.canal.enviadas)  # nada enviado ao paciente da prova


def test_prova_com_peca_conferida_libera_e_fecha_a_tarefa(tmp_path):
    m, c = _setup(tmp_path, [PROVA], [{"numero": "1", "pacId": "p1", "etapa": "retornou"}])
    lembretes(m, c, AGORA)
    assert any(t.titulo.startswith("Laboratório: confirmação suspensa") and t.estado == "aberta" for t in m.tarefas.tarefas.values())
    _, c2 = _setup(tmp_path, [PROVA], [{"numero": "1", "pacId": "p1", "etapa": "retornou", "antiRefacaoEm": "2026-05-05"}], nome="b2")
    plano = lembretes(m, c2, AGORA)
    assert plano[0].decisao.acao == "enviar_lembrete"
    assert all(t.estado == "fechada" for t in m.tarefas.tarefas.values())


def test_prova_sem_os_tambem_trava(tmp_path):
    m, c = _setup(tmp_path, [PROVA])
    assert "nenhuma OS" in lembretes(m, c, AGORA)[0].nota


def test_sala_de_espera_15_minutos(tmp_path):
    hoje = "2026-05-05"
    ag = [{"id": "e1", "pacId": "p1", "data": hoje, "hora": "09:30", "status": "chegou"},
          {"id": "e2", "pacId": "p2", "data": hoje, "hora": "10:15", "status": "confirmado"}]
    m, c = _setup(tmp_path, ag)
    assert sala(m, c, datetime(2026, 5, 5, 9, 44)) == []  # 14 min: cedo
    itens = sala(m, c, datetime(2026, 5, 5, 9, 46))
    assert [i.tipo for i in itens] == ["sala_espera", "avisar_proximo"]
    assert sala(m, c, datetime(2026, 5, 5, 9, 50)) == []  # sem repetir
    ag[0]["status"] = "em_atendimento"
    _, c2 = _setup(tmp_path, ag, nome="b2")
    sala(m, c2, datetime(2026, 5, 5, 9, 55))
    assert all(t.estado == "fechada" for t in m.tarefas.tarefas.values())  # atendimento começou: fecha sozinha
    assert all("Ana" not in t.titulo and "Bia" not in t.titulo for t in m.tarefas.tarefas.values())
