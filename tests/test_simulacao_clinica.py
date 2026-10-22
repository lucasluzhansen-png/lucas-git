from hansen import simulacao_clinica


def test_simulacao_roda_e_o_ledger_fica_integro(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HANSEN_SAIDA", str(tmp_path))
    simulacao_clinica.main()
    saida = capsys.readouterr().out
    assert "Ledger íntegro: True" in saida
    for esperado in ("Jornada: plano aprovado", "Jornada: alta concluída", "Cobrar parcela em atraso", "Contabilidade: enviar o fechamento", "fechada sozinha"):
        assert esperado in saida
