# Projeto Hansen v14.0: estado e próximos passos

Cole este arquivo no início de um chat novo.

## Regra de ouro
IA cuida da burocracia e cobra a equipe. Humano cuida do risco clínico. A IA nunca diagnostica, prescreve ou decide clínica. O RT pode vetar tarefas e pausar agentes. Dúvida, falha ou caso sem regra = vai para um humano.

## Repositório
- Repo: `lucasluzhansen-png/lucas-git`, branch `claude/bold-mccarthy-dmc44n`, PR #3 (rascunho).
- Python 3.10+. Instalar: `pip install pydantic pyyaml cryptography pytest`
- Testes (PowerShell): `$env:PYTHONPATH="src"; python -m pytest -q tests` (81 passando)
- Simulação de um dia + painel: `$env:PYTHONPATH="src"; python -m hansen.simulacao` (gera `saida/simulacao/painel.html`)
- Lembretes com o backup real do Clinus: `$env:PYTHONPATH="src"; python -m hansen.lembretes "<backup.json>" agora 720` (720 = janela em horas). Diagnóstico sem dados de paciente: `python -m hansen.clinus "<backup.json>"`.
- Fluxograma: `docs/fluxograma.html`

## O que existe (`src/hansen/`)
- `yaml_parser.py`: valida os 13 POPs em `volumes/Volume_2_Manual_Maquina/pops/` (regras e parâmetros vêm do YAML).
- `ledger.py`: hash-chain + Ed25519 gravado em disco (SIMULA o S3 WORM; chave em memória).
- `cerebro.py`: LLM só classifica o tipo de pedido (guardrails, urgência vai a humano). Testado só com LLM falso; falta testar com `ANTHROPIC_API_KEY`.
- `maestro.py`: roteia por agentes, respeita nível de autonomia, pausa do RT, cria tarefas.
- `agentes/recepcao.py` (R-00, R-02), `agentes/rotina.py` (A-01, A-06) e `agentes/comercial.py` (CM-01, CM-02).
- `folha_aprovacao.py`: gera `docs/folha_aprovacao_pops.html` direto dos YAMLs (`python -m hansen.folha_aprovacao`); refazer sempre que um YAML mudar.
- `agentes/financeiro.py` (FN-01) + `rotina_financeira.py`: parcelas do Clinus (mesma lógica de quitação em ordem do app). `python -m hansen.rotina_financeira "<backup.json>" agora` gera `saida/financeiro/painel_financeiro.html` (cartões para a Recepção com texto cordial e link wa.me; só sugere). Tarefas: `python -m hansen.tarefas_cli saida\\financeiro listar|fechar`.
- `cadastros.py`: relatório de qualidade dos cadastros (`python -m hansen.cadastros "<backup.json>"`): terminal só com contagens; planilha com nomes em `saida/cadastros/` (fora do Git).
- `rotina_comercial.py`: rotina diária do Comercial (`python -m hansen.rotina_comercial "<backup.json>" agora`); ao final gera e abre `saida/comercial/painel_comercial.html` (`painel_comercial.py`): cartões para o Dr. Lucas com nome, texto formal sugerido (CM-02.yaml, sem valores) e link wa.me (quem envia é o humano pelo app do WhatsApp Business). O arquivo tem nomes/telefones: fica em saida/ (fora do Git).
- `tarefas_cli.py`: `python -m hansen.tarefas_cli saida\\comercial listar` e `... fechar N "evidência"` (fecha tarefa; o cartão some do painel).
- `tarefas.py`: escalada de vermelha em 60 min, fecho só com evidência, veto só do RT, persistência em JSON.
- `canal.py`: WhatsApp SIMULADO (tom formal, seg-sex 8h-18h). `agendador.py`: `tick()` com silêncio de madrugada.
- `painel.py` e `simulacao.py`: página HTML e simulação com dados fictícios.

## Decisões do RT já aplicadas (no YAML)
- Madrugada = 0h às 7h (alertas silenciados até 7h). Janela de mensagens: seg-sex, 8h-18h.
- Abertura (A-01) só registra; sem tarefa.
- Aprovações e alertas vermelhos vão para o Dr. Lucas; ligação de no-show e agendamento, para a Recepção. (A-06.yaml, `responsaveis`)
- Fora do escopo (Endodontia, Exodontia, Periodontia, Odontopediatria): indicar profissionais parceiros. Paciente atual: dentista faz o 1º atendimento e encaminha.
- Serviços da clínica (encaminhar para agendar): orto, alinhadores, PPR, PT, restaurações, lentes, coroas, bruxismo, implantes, clareamento, facetas em resina, próteses. Recepção agenda sozinha, inclusive 1ª consulta.
- "Paciente atual" = telefone encontrado no cadastro do Clinus (implementado via backup JSON; falta um jeito prático de atualizar o arquivo todo dia).

## Respostas sobre a operação
- Pacientes e agenda: **Clinus** = app próprio do RT (arquivo HTML único, "Dental Compass · Clinus v2.0"), dados no navegador (localStorage). **Não tem API.** Integração por arquivo: o RT exporta o JSON em "Dados e backup → Exportar JSON" e o sistema lê (`src/hansen/clinus.py`, somente leitura; guarda só id, nome e telefone). Formato: `{versao:"hrpg_v1", pacientes:[...], stores:{clinus_agenda_v2:"<json>"}}`.
- Atenção (Clinus): a chave da API Anthropic fica salva no navegador, e o texto da anamnese vai à API quando o recurso está ligado (o próprio app avisa para exigir consentimento do paciente).
- Parceiros: o RT tem a lista e a passará **no final de tudo**. **LEMBRAR O RT disso ao concluir os próximos passos** (nome, especialidade, contato de cada parceiro).
- Canal hoje: WhatsApp Business (aplicativo). **Decisão do RT: migrar para a WhatsApp Business API** (provedor oficial), necessária para envio automático. Falta escolher provedor, custo e consentimento do paciente.

## Agente Comercial (decisões do RT, 22/10/2026; POPs novos CM-01 e CM-02; folha dos POPs aprovada pelo Dr. Lucas em 22/10/2026, falta a Dra. Jussara e as 5 pendências da folha)
- Faz: orçamentos em aberto ("vai pensar"), reativar pacientes parados, aniversariantes, retornos e manutenção.
- CM-01 (IA envia sozinha): aniversário e lembrete de retorno agendado. Aniversário só com consentimento registado no Clinus (campo `consentimentoComercial`; HOJE NÃO EXISTE no Clinus, então tudo vira tarefa manual até o RT criar esse registo).
- CM-02 (IA só sugere): retomada de orçamento e reativação; tarefa para o Dr. Lucas.
- A IA NUNCA cita valores ou condições de pagamento. ÚNICA EXCEÇÃO (RT, 22/10/2026): o parabéns de aniversário informa 15% de abatimento (antes "desconto") no clareamento válido no mês do aniversário (`desconto_clareamento` no CM-01.yaml; 0 desliga e usa o texto simples). A busca na web NÃO confirmou se oferecer desconto é permitido pelo Código de Ética (CFO 118/2012); VALIDAR com o CRO antes do envio real. O sistema só informa o desconto: a Recepção precisa honrá-lo (o Clinus não controla isso).
- Textos comerciais aprovados pelo RT em 22/10/2026: começam com "Senhor(a) {nome}" (sem "Prezado"); aniversário usa o primeiro nome, tom informal e sincero. "Prezado" foi removido de TODAS as mensagens do sistema (R-00, R-02, CM-01, CM-02); um teste garante. Na mensagem de aniversário a oferta usa a palavra "abatimento" em vez de "desconto" (a substância continua sendo redução de preço: a validação com o CRO continua necessária).
- Valores CONFIRMADOS pelo RT (22/10/2026, CM-02.yaml): orçamento após 7 dias, parado após 90 dias, 1 contato a cada 15 dias por paciente, máx. 5 sugestões/dia. Ainda ASSUMIDOS: retorno avisado 2 dias antes (CM-01); manutenção vencida após 180 dias (regra do Clinus). Textos das mensagens aprovados pelo RT.
- Mensagem de aniversário tende a ser categoria "marketing" na WhatsApp Business API (mais cara que utilidade); conferir com o provedor.
- "Orçamento em aberto" usa a MESMA definição do relatório do Clinus: decisão `pensar` OU zona `orcpendente` OU etapa 7 OU orçamento novo sem aprovação. "Manutenção vencida" = etapa 10 há 180+ dias (também do Clinus). "Base histórica importada" (sem ação humana) é ignorada, como no Clinus. Pacientes na zona `perdidos` não são reativados. Teste com backups reais (21/10 e 09/10): quase nenhum paciente tem `decisao`, nascimento ou retornos preenchidos, então a rotina achou pouco a fazer.
- Formato do store `clinus_retornos_v1` deduzido do código (campos `pacId`, `status`, `devido`/`data`); validar com backup real.

## Agente Financeiro (decisões do RT, 22/10/2026)
- Escopo pedido: pendências com convênio, fechamento de caixa de convênio, compras dental, manutenção de equipamentos, parcelas em atraso, parcelas a vencer, fechamento de caixa, contas a pagar.
- Decisões: A IA SÓ SUGERE; responsável: Recepção (A-06.yaml `financeiro`); atraso após 3 dias.
- FEITO: FN-01 (parcelas a vencer e em atraso). Assumidos: lembrete 3 dias antes, 1 cobrança a cada 7 dias por paciente, 10 sugestões/dia. Cobrança: texto cordial, sem juros/multa/ameaça/negativação (CDC art. 42; conferir com advogado).
- FALTA (precisa da estrutura real dos stores `clinus_caixa`, `clinus_contas_pagar`, `clinus_compras`, `clinus_equipamentos`, `clinus_convenios`): rodar `python -m hansen.clinus "<backup.json>"` e colar a seção "Financeiro" (só nomes de campos e contagens, sem valores).

## Premissas ainda NÃO confirmadas com a clínica
- "Madrugada" = 0h às 7h (alertas silenciados até 7h).
- Lista de palavras de risco clínico (cerebro.py) e de procedimentos recusados (R-00.yaml): revisão clínica.
- Número exato da RDC e regras do CFO: conferir em fonte oficial.

## Testado com backup real (21/10)
Leitor entendeu o formato real do Clinus. Backup tinha 3 pacientes (só 1 com telefone) e 4 consultas; o sistema marcou corretamente "sem telefone: ligar manualmente". Qualidade dos telefones no Clinus é o ponto fraco.

## Problemas conhecidos
Nenhum aberto dos 4 anteriores (títulos, serviços, ruído e texto no YAML foram corrigidos).

## Ainda não feito
- WhatsApp real (exige conta Business, consentimento, base legal LGPD, contrato de processamento de dados).
- Agendador rodando sozinho (cron/serviço chamando `tick()` a cada minuto).
- Agente de Esterilização (B-01, B-02), Conformidade (S-01, S-07), Laboratório; POPs HUMANO (B-12, C-19).
- AWS sa-east-1, S3 Object Lock (usar modo Governance até validar com advogado; Compliance é irreversível), chaves nos celulares.
- Persistência do ledger fora do disco local.

## Ordem sugerida
1. Exportar o backup do Clinus e rodar o sistema com ele (ver `hansen.clinus`); escolher provedor da WhatsApp Business API.
2. Fluxo v1 e folha dos POPs aprovados pelo Dr. Lucas em 22/10/2026 (ver `docs/APROVACOES.md`). Falta a assinatura da Dra. Jussara e fechar as 5 pendências da folha.
3. Confirmar premissas com a equipe.
4. Piloto de 2 semanas só com R-02: a IA propõe, a Recepção executa à mão, comparar acertos.
5. Só depois: WhatsApp real, Esterilização, AWS.
6. **No final: lembrar o RT de passar a lista de parceiros.**
