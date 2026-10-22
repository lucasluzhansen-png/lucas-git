# Projeto Hansen v14.0: estado e próximos passos

Cole este arquivo no início de um chat novo.

## Regra de ouro
IA cuida da burocracia e cobra a equipe. Humano cuida do risco clínico. A IA nunca diagnostica, prescreve ou decide clínica. O RT pode vetar tarefas e pausar agentes. Dúvida, falha ou caso sem regra = vai para um humano.

## COMO VER TUDO (um clique)
- Dê dois cliques em `abrir_painel.bat` (na pasta do projeto): ele pega o backup mais recente do Clinus em Downloads, roda TODAS as rotinas (lembretes, comercial, financeiro, convênio) e abre UMA página: `saida/hoje/painel_do_dia.html`, com o mascote "Maestro" e a saudação do dia. Antes, exporte um backup novo no Clinus (Dados e backup → Exportar JSON).
- Equivalente no PowerShell: `$env:PYTHONPATH="src"; python -m hansen.hoje auto`
- O painel mostra: mensagens prontas (Recepção envia à mão pelo WhatsApp Business), tarefas do Dr. Lucas, tarefas da Recepção, qualidade dos cadastros e estado do sistema. Modo assistido: nada é enviado automaticamente.

## ONDE FICAM OS ARQUIVOS GERADOS (importante no Windows)
- O projeto NÃO deve ficar em `C:\Windows\System32` (pasta protegida: só o PowerShell como Administrador consegue escrever lá; clique duplo e agendador falham com "Acesso negado"). Por isso, no Windows, tudo que o sistema gera vai para `C:\Users\<usuário>\HansenMaestro\saida\` (painéis em `hoje\painel_do_dia.html`, avisos em `hoje\avisos.log`, tarefas em `hoje\estado\`). Pode mudar com a variável `HANSEN_SAIDA`. Fora do Windows: `saida\` no projeto.
- `maestro.config.json` pode ficar na pasta do projeto OU em `C:\Users\<usuário>\HansenMaestro\`.
- Recomendado: mover o projeto para uma pasta normal (ex.: `C:\Users\Lucas\lucas-git`).
- `python -m hansen.tarefas_cli comercial listar` (ou `financeiro`, `hoje`) e `... fechar N "evidência"`.

## MAESTRO COM VIDA PRÓPRIA (MA-01) — cobra sozinho
- Decisões do RT (22/10/2026): notificação do Windows; cobrança FIRME; seg-sex 8h-18h; Dr. Lucas E Recepção (cada um no seu computador).
- Liga: `instalar_maestro.bat lucas` (ou `recepcao`) agenda um ciclo a cada 15 min, sem janela (`maestro_tick.vbs`). Desliga: `desinstalar_maestro.bat`. Teste do aviso: `testar_aviso.bat`.
- Cada ciclo (`src/hansen/maestro_vivo.py`): acha o backup mais recente (`hansen-rpg-backup-*.json` em Downloads OU `clinus-backup-latest.json` da pasta de nuvem do Clinus; configure `maestro.config.json` com `{"pastas_backup": ["C:\\...\\OneDrive\\ClinusBackup"]}`), reprocessa se for novo ou a cada 60 min, e cobra (`cobrador.py`, regras em MA-01.yaml): resumo 8h30, insiste a cada 2 h nas urgentes (tom: URGENTE → ATRASADO → IGNORADO), fechamento 17h30, avisa o Dr. Lucas do que está parado com a Recepção há 2+ dias, avisa se o backup tem 24 h+. Avisos NUNCA levam nome de paciente.
- Tarefas se FECHAM SOZINHAS quando o Clinus mostra que a situação acabou (`sincronizar.py`): conta paga, caixa fechado, guia que avançou, parcela paga, paciente atendido. Registado no ledger como agente.
- LIMITES: (1) o toast do Windows NÃO foi testado em Windows real (rode `testar_aviso.bat`; sempre grava também `avisos.log` na pasta de saída); (2) o computador precisa estar ligado e com o usuário logado; (3) o Maestro só enxerga o que está no backup: o backup automático do Clinus (pasta de nuvem) só grava com o Clinus aberto no Chrome/Edge; (4) cada computador tem o seu estado em `saida\\hoje` (fechar tarefa à mão num PC não aparece no outro; as automáticas funcionam nos dois); (5) o Maestro cobra a EQUIPE sozinho, mas NÃO envia mensagem a paciente sozinho (continua humano).

## Repositório
- Repo: `lucasluzhansen-png/lucas-git`, branch `claude/bold-mccarthy-dmc44n`, PR #3 (rascunho).
- Python 3.10+. Instalar: `pip install pydantic pyyaml cryptography pytest`
- Testes (PowerShell): `$env:PYTHONPATH="src"; python -m pytest -q tests` (138 passando)
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
- `agentes/financeiro.py` (FN-01) + `rotina_financeira.py`: parcelas do Clinus (mesma lógica de quitação em ordem do app). `python -m hansen.rotina_financeira "<backup.json>" agora` gera `saida/financeiro/painel_financeiro.html` (cartões para a Recepção com texto cordial e link wa.me; só sugere). O painel também lista as tarefas internas (contas, compras, equipamentos, caixa, convênio). Tarefas: `python -m hansen.tarefas_cli saida\\financeiro listar|fechar`. Dica PowerShell para pegar o backup mais recente: `$b = Get-ChildItem "$HOME\\Downloads\\hansen-rpg-backup-*.json" | Sort-Object LastWriteTime -Descending | Select-Object -First 1`.
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
- FEITO também: FN-02 (`rodar_clinica` em `rotina_financeira.py`): contas a pagar (store `clinus_contas_pagar`: id, descricao, valor, vencimento, status pago|pendente), compras (`clinus_compras`: produto, qtd, urgencia, status pendente|adiado|aprovado|pedido|recebido; pendente/crítico vai para o Dr. Lucas, aprovado para a Recepção), preventiva de equipamentos (`clinus_equipamentos.equipamentos[].proximaEm`) e fechamento de caixa (dia com recebimentos em `orcamento.pagamentos` sem registo em `clinus_caixa`). Uma sugestão por estado (não repete). Assumidos: conta 2 dias antes, preventiva 15 dias antes, caixa 7 dias. Estruturas confirmadas lendo o código do Clinus; backup real tinha 1 conta a pagar, 0 compras, 0 equipamentos, sem caixa.
- FEITO: FN-03 (convênio), lendo o módulo "Faturamento de convênio" do Clinus ATUALIZADO (store `clinus_guias`: status criada|enviada|aprovada|executada|faturada|paga|glosada, envio, previsao, repasse, glosado, motivoGlosa, recurso, valorEsperado/Recebido). Mesma lógica de repasse atrasado do Clinus. Sugere: guia não criada (orçamento de convênio aprovado sem guia), guia criada e não enviada, autorização pendente, repasse atrasado, glosa sem recurso, fechamento mensal por operadora. Assumidos: 3/3/7 dias e dia 5. ATENÇÃO: o `index.html` deste repositório NÃO é o Clinus (é outro app); o Clinus real está fora do repositório e NÃO foi alterado. Conferido: as regras que o sistema lê (parcelas, orçamento, contas a pagar, compras, equipamentos, caixa, histórico) são idênticas no Clinus atualizado.
- FALTA: chamados de equipamento parados (campos de `ocorrencias` desconhecidos), diferença de caixa sem explicação (campos do fechamento desconhecidos).

## Agente Laboratório (LB-01, criado em 22/10/2026)
- Lê `lab_os` do Clinus (campos: numero, lab, pac, etapa moldagem|enviado|producao|retornou|prova|ajuste|instalado|entregue|cancelada|problema, entrega/prazo, marcos {enviado, retornou, instalado}, problema, arquivada, antiRefacaoEm). `python -m hansen.rotina_laboratorio "<backup.json>" agora`; também roda dentro do painel do dia e do Maestro.
- Sugere (Recepção, só sugere): OS atrasada (cobrar o lab), prazo vencendo (2 dias), acima do prazo padrão (21 dias, do documento original), enviada sem prazo, peça retornou sem conferência anti-refação (1 dia), OS com problema. Tarefas fecham sozinhas quando a OS avança.
- A IA NUNCA avalia a peça (cor, adaptação, qualidade): só prazo e etapa. Um teste garante que nenhum texto fala disso.
- FEITO (22/10/2026, pedido do RT): "peça chegou e o paciente não tem consulta futura marcada" (cruza `lab_os.pacId` com `clinus_agenda_v2`; assumido: avisar 1 dia após a chegada; some sozinho quando a Recepção marca a consulta; OS sem pacId não gera aviso).
- FALTA: a regra "prova da barra + dentes na mesma sessão após o protocolo" (preciso saber como a clínica marca isso na agenda); testar com backup real (o backup de 21/10 não tinha OS); responsável (Recepção) e valores (2 dias / 1 dia) CONFIRMADOS pelo RT em 22/10/2026. O RT vai verificar com OS reais do Clinus.

## Premissas ainda NÃO confirmadas com a clínica
- "Madrugada" = 0h às 7h (alertas silenciados até 7h).
- Lista de palavras de risco clínico (cerebro.py) e de procedimentos recusados (R-00.yaml): revisão clínica.
- Número exato da RDC e regras do CFO: conferir em fonte oficial.

## Testado com backup real (21/10, 2º teste)
Financeiro achou preventiva vencida do ar condicionado (prevista 15/10) e o comercial achou 1 orçamento em aberto há 13 dias. Guias de convênio ainda NÃO testadas com dados reais (o backup usado era anterior ao Clinus atualizado: 0 guias).

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

## Painel web local (146 testes)
- Dois cliques em `abrir_maestro.bat` abre o painel no navegador (perfis Dr. Lucas/Recepção, "Feito", WhatsApp, arrastar backup).
- Código: `src/hansen/app.py`, `src/hansen/web/painel.html`. Log: `app.log`.
- Não testado em Windows real. Pendente: lista de profissionais parceiros (lembrar o Dr. Lucas).
