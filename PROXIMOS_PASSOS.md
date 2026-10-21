# Projeto Hansen v14.0: estado e próximos passos

Cole este arquivo no início de um chat novo.

## Regra de ouro
IA cuida da burocracia e cobra a equipe. Humano cuida do risco clínico. A IA nunca diagnostica, prescreve ou decide clínica. O RT pode vetar tarefas e pausar agentes. Dúvida, falha ou caso sem regra = vai para um humano.

## Repositório
- Repo: `lucasluzhansen-png/lucas-git`, branch `claude/bold-mccarthy-dmc44n`, PR #3 (rascunho).
- Python 3.10+. Instalar: `pip install pydantic pyyaml cryptography pytest`
- Testes (PowerShell): `$env:PYTHONPATH="src"; python -m pytest -q tests` (40 passando)
- Simulação de um dia + painel: `$env:PYTHONPATH="src"; python -m hansen.simulacao` (gera `saida/simulacao/painel.html`)
- Fluxograma: `docs/fluxograma.html`

## O que existe (`src/hansen/`)
- `yaml_parser.py`: valida os 13 POPs em `volumes/Volume_2_Manual_Maquina/pops/` (regras e parâmetros vêm do YAML).
- `ledger.py`: hash-chain + Ed25519 gravado em disco (SIMULA o S3 WORM; chave em memória).
- `cerebro.py`: LLM só classifica o tipo de pedido (guardrails, urgência vai a humano). Testado só com LLM falso; falta testar com `ANTHROPIC_API_KEY`.
- `maestro.py`: roteia por agentes, respeita nível de autonomia, pausa do RT, cria tarefas.
- `agentes/recepcao.py` (R-00, R-02) e `agentes/rotina.py` (A-01, A-06).
- `tarefas.py`: escalada de vermelha em 60 min, fecho só com evidência, veto só do RT, persistência em JSON.
- `canal.py`: WhatsApp SIMULADO (tom formal, seg-sex 8h-18h). `agendador.py`: `tick()` com silêncio de madrugada.
- `painel.py` e `simulacao.py`: página HTML e simulação com dados fictícios.

## Decisões do RT já aplicadas (no YAML)
- Madrugada = 0h às 7h (alertas silenciados até 7h). Janela de mensagens: seg-sex, 8h-18h.
- Abertura (A-01) só registra; sem tarefa.
- Aprovações e alertas vermelhos vão para o Dr. Lucas; ligação de no-show e agendamento, para a Recepção. (A-06.yaml, `responsaveis`)
- Fora do escopo (Endodontia, Exodontia, Periodontia, Odontopediatria): indicar profissionais parceiros. Paciente atual: dentista faz o 1º atendimento e encaminha.
- Serviços da clínica (encaminhar para agendar): orto, alinhadores, PPR, PT, restaurações, lentes, coroas, bruxismo, implantes, clareamento, facetas em resina, próteses. Recepção agenda sozinha, inclusive 1ª consulta.
- "Paciente atual" = telefone encontrado no cadastro (ainda não implementado: falta a base de pacientes).

## Respostas sobre a operação
- Pacientes e agenda: software **Clinus** (decisão do RT). Falta verificar se tem API/exportação para integrar.
- Parceiros: o RT tem a lista e a passará **no final de tudo**. **LEMBRAR O RT disso ao concluir os próximos passos** (nome, especialidade, contato de cada parceiro).
- Canal hoje: WhatsApp Business (aplicativo). **Decisão do RT: migrar para a WhatsApp Business API** (provedor oficial), necessária para envio automático. Falta escolher provedor, custo e consentimento do paciente.

## Premissas ainda NÃO confirmadas com a clínica
- "Madrugada" = 0h às 7h (alertas silenciados até 7h).
- Lista de palavras de risco clínico (cerebro.py) e de procedimentos recusados (R-00.yaml): revisão clínica.
- Número exato da RDC e regras do CFO: conferir em fonte oficial.

## Problemas conhecidos
Nenhum aberto dos 4 anteriores (títulos, serviços, ruído e texto no YAML foram corrigidos).

## Ainda não feito
- WhatsApp real (exige conta Business, consentimento, base legal LGPD, contrato de processamento de dados).
- Agendador rodando sozinho (cron/serviço chamando `tick()` a cada minuto).
- Agente de Esterilização (B-01, B-02), Conformidade (S-01, S-07), Laboratório; POPs HUMANO (B-12, C-19).
- AWS sa-east-1, S3 Object Lock (usar modo Governance até validar com advogado; Compliance é irreversível), chaves nos celulares.
- Persistência do ledger fora do disco local.

## Ordem sugerida
1. Verificar integração com o Clinus (API/exportação) e escolher provedor da WhatsApp Business API.
2. Mostrar `docs/fluxograma.html` e o painel à Dra. Jussara; anotar ajustes.
3. Confirmar premissas com a equipe.
4. Piloto de 2 semanas só com R-02: a IA propõe, a Recepção executa à mão, comparar acertos.
5. Só depois: WhatsApp real, Esterilização, AWS.
6. **No final: lembrar o RT de passar a lista de parceiros.**
