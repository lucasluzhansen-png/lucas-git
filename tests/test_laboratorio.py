import json
from datetime import datetime

from hansen.canal import CanalSimulado, Notificador
from hansen.clinus import carregar_backup
from hansen.ledger import LedgerManager
from hansen.maestro import Maestro
from hansen.rotina_laboratorio import rodar
from hansen.yaml_parser import carregar_todos

AGORA = datetime(2026, 3, 10, 10, 0)


def _os(num, etapa, **kw):
    return {"numero": num, "lab": "Lab Sorriso", "pac": "Ana", "etapa": etapa, **kw}


OS = [
    _os("101", "producao", entrega="2026-03-05", marcos={"enviado": "2026-02-20"}),               # atrasada
    _os("102", "enviado", entrega="2026-03-11", marcos={"enviado": "2026-03-01"}),                # vence amanhã
    _os("103", "producao", entrega="2026-03-30", marcos={"enviado": "2026-02-01"}),               # longe, mas 37 dias com o lab: acima do SLA
    _os("104", "enviado", marcos={"enviado": "2026-03-08"}),                                      # sem prazo
    _os("105", "retornou", marcos={"retornou": "2026-03-08"}),                                    # retornou há 2 dias, sem conferência
    _os("106", "retornou", marcos={"retornou": "2026-03-08"}, antiRefacaoEm="2026-03-09"),        # conferida: ok
    _os("107", "prova", problema=True),                                                           # problema
    _os("108", "instalado", entrega="2026-01-01"),                                                # concluída: ignora
    _os("109", "producao", entrega="2026-03-01", arquivada=True),                                 # arquivada: ignora
    _os("110", "producao", entrega="2026-03-20", marcos={"enviado": "2026-03-05"}),               # no prazo e dentro do SLA: ok
]


def _setup(tmp_path, oss=OS, agenda=()):
    f = tmp_path / "b.json"
    f.write_text(json.dumps({"versao": "hrpg_v1", "pacientes": [], "stores": {"lab_os": json.dumps(oss), "clinus_agenda_v2": json.dumps(list(agenda))}}), encoding="utf-8")
    led = LedgerManager(tmp_path / "l")
    m = Maestro(led, estado=tmp_path / "est", notificador=Notificador(CanalSimulado(), led, carregar_todos()["R-02"]))
    return m, carregar_backup(f)


def _titulos(m):
    return sorted((t.titulo.split(" [")[0], t.titulo.split("[")[1].split("]")[0]) for t in m.tarefas.tarefas.values())


def test_sugestoes_do_laboratorio(tmp_path):
    m, c = _setup(tmp_path)
    rodar(m, c, AGORA)
    assert _titulos(m) == sorted([
        ("Laboratório: OS atrasada (cobrar o laboratório)", "OS 101"),
        ("Laboratório: prazo vencendo (confirmar com o laboratório)", "OS 102"),
        ("Laboratório: OS acima do prazo padrão", "OS 103"),
        ("Laboratório: OS enviada sem prazo registado", "OS 104"),
        ("Laboratório: peça retornou, falta a conferência", "OS 105"),
        ("Laboratório: OS com problema", "OS 107"),
    ])
    assert {t.responsavel for t in m.tarefas.tarefas.values()} == {"recepcao"}


def test_prioridades(tmp_path):
    m, c = _setup(tmp_path)
    rodar(m, c, AGORA)
    pr = {t.titulo.split(" [")[0]: t.prioridade for t in m.tarefas.tarefas.values()}
    assert pr["Laboratório: OS atrasada (cobrar o laboratório)"] == "amarela" and pr["Laboratório: OS com problema"] == "amarela"
    assert pr["Laboratório: prazo vencendo (confirmar com o laboratório)"] == "verde"


def test_atrasada_nao_gera_tambem_aviso_de_sla(tmp_path):
    m, c = _setup(tmp_path, [_os("1", "producao", entrega="2026-03-01", marcos={"enviado": "2026-01-01"})])
    rodar(m, c, AGORA)
    assert [t.titulo.split(" [")[0] for t in m.tarefas.tarefas.values()] == ["Laboratório: OS atrasada (cobrar o laboratório)"]


def test_a_ia_nunca_avalia_a_peca(tmp_path):
    m, c = _setup(tmp_path)
    rodar(m, c, AGORA)
    todo = " ".join(t.titulo.lower() for t in m.tarefas.tarefas.values())
    for proibida in ("cor ", "adaptação", "qualidade", "aprovad", "reprovad", "defeito", "refazer"):
        assert proibida not in todo
    assert "a conferência não foi registada" in todo  # só lembra que a conferência humana falta


def test_tarefa_fecha_sozinha_quando_a_os_avanca_no_clinus(tmp_path):
    m, c = _setup(tmp_path)
    rodar(m, c, AGORA)
    avancou = [dict(o) for o in OS]
    avancou[0] = _os("101", "retornou", entrega="2026-03-05", marcos={"enviado": "2026-02-20", "retornou": "2026-03-10"})  # a peça chegou
    avancou[4] = _os("105", "retornou", marcos={"retornou": "2026-03-08"}, antiRefacaoEm="2026-03-10")                       # conferiu
    m2, c2 = _setup(tmp_path / "x", avancou) if (tmp_path / "x").mkdir() is None else (None, None)
    rodar(m, c2, AGORA)
    abertas = {t.titulo.split("[")[1].split("]")[0] for t in m.tarefas.tarefas.values() if t.estado == "aberta"}
    assert "OS 101" not in abertas and "OS 105" not in abertas and "OS 102" in abertas and m.resolvidas_auto == 2


def test_nao_repete_e_ledger_sem_paciente(tmp_path):
    m, c = _setup(tmp_path)
    rodar(m, c, AGORA)
    n = len(m.tarefas.tarefas)
    assert rodar(m, c, AGORA) == [] and len(m.tarefas.tarefas) == n
    txt = "".join(p.read_text(encoding="utf-8") for p in (tmp_path / "l").glob("*.json"))
    assert "Ana" not in txt and m.ledger.verificar()


def test_backup_sem_os_nao_quebra(tmp_path):
    m, c = _setup(tmp_path, [])
    assert rodar(m, c, AGORA) == []


def _chegou(num="111", pac="p1", em="2026-03-08"):
    return _os(num, "retornou", pacId=pac, marcos={"retornou": em}, antiRefacaoEm="2026-03-09")  # conferida: só falta a consulta


def test_peca_chegou_sem_consulta_marcada(tmp_path):
    m, c = _setup(tmp_path, [_chegou()], agenda=[])
    rodar(m, c, AGORA)
    assert _titulos(m) == [("Laboratório: peça chegou e não há consulta marcada", "OS 111")]
    t = next(iter(m.tarefas.tarefas.values()))
    assert t.responsavel == "recepcao" and t.prioridade == "amarela"


def test_consulta_futura_do_mesmo_paciente_evita_o_aviso(tmp_path):
    futura = {"id": "e1", "pacId": "p1", "data": "2026-03-14", "hora": "09:00", "status": "agendado"}
    m, c = _setup(tmp_path, [_chegou()], agenda=[futura])
    rodar(m, c, AGORA)
    assert _titulos(m) == []


def test_consulta_de_outro_paciente_ou_passada_ou_cancelada_nao_conta(tmp_path):
    agenda = [{"id": "e1", "pacId": "p2", "data": "2026-03-14", "status": "agendado"},   # outro paciente
              {"id": "e2", "pacId": "p1", "data": "2026-03-01", "status": "agendado"},   # passada
              {"id": "e3", "pacId": "p1", "data": "2026-03-14", "status": "cancelado"}]  # cancelada
    m, c = _setup(tmp_path, [_chegou()], agenda=agenda)
    rodar(m, c, AGORA)
    assert [t[1] for t in _titulos(m)] == ["OS 111"]


def test_aviso_some_quando_a_recepcao_marca_a_consulta(tmp_path):
    m, c = _setup(tmp_path, [_chegou()], agenda=[])
    rodar(m, c, AGORA)
    assert len(_titulos(m)) == 1
    (tmp_path / "x").mkdir()
    _, c2 = _setup(tmp_path / "x", [_chegou()], agenda=[{"id": "e1", "pacId": "p1", "data": "2026-03-14", "status": "confirmado"}])
    rodar(m, c2, AGORA)
    assert m.resolvidas_auto == 1 and not [t for t in m.tarefas.tarefas.values() if t.estado == "aberta"]


def test_os_sem_paciente_vinculado_nao_gera_aviso_de_agenda(tmp_path):
    m, c = _setup(tmp_path, [_os("112", "retornou", marcos={"retornou": "2026-03-08"}, antiRefacaoEm="2026-03-09")], agenda=[])
    rodar(m, c, AGORA)
    assert _titulos(m) == []                     # sem pacId não dá para saber: não inventa aviso
