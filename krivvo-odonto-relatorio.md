# Relatório de exploração do Krivvo Odonto

**Data da exploração:** 05/10/2026  
**Escopo:** navegação do ambiente autenticado de teste por interface web.  
**Modo:** somente leitura. Não foi salvo paciente, tratamento, orçamento, contrato, pedido de exame, agendamento ou configuração.

## Resumo executivo

O Krivvo reúne gestão de pacientes e prontuário, agenda, formulários de anamnese, procedimentos e tratamentos, orçamento com condições de pagamento, contratos vinculados a orçamento aprovado, solicitação de exames e módulos administrativos. A ficha do paciente funciona como centro do fluxo clínico e comercial, com seções para Dados, Anamnese, Evolução, Odontograma, Tratamentos, HOF, Histórico, Orçamentos, Financeiro, Contratos, Documentos, Fotos, Exames, Receitas e Atestados.

O fluxo conceitual observado é: cadastrar ou selecionar paciente → registrar anamnese e dados clínicos → planejar no odontograma/tratamentos → criar orçamento formal → aprovação → contrato → executar e registrar evolução/tratamentos → controlar recebimentos e documentos. O sistema também permite lançamento de tratamento avulso, explicitamente descrito como diferente de orçamento formal.

Esta exploração confirma telas e formulários, não a execução completa de operações persistidas nem o comportamento de integrações externas. O ambiente estava em período de teste e continha dois pacientes demonstrativos.

## Ambiente e dados visíveis

- Dashboard informa período de teste de 05/10/2026 a 17/10/2026 e alerta que pacientes de demonstração serão removidos ao assinar; dados cadastrados durante o teste seriam mantidos.
- Saudação do dashboard indicava 2 consultas para hoje; receita, a receber e inadimplência apareciam em R$ 0,00; 2 consultas hoje, 2 novos pacientes no mês e 0 orçamentos abertos.
- Lista de pacientes mostrava 2 ativos: João Santos (teste) e Maria Silva (teste), além de abas de ativos e excluídos, busca, filtros por categoria/estado e ordenação.
- Os dados exibidos são demonstração. Não servem como retrato de uma clínica em operação.

## Fluxos percorridos

### 1. Entrada e cadastro de paciente

A tela “Novo Paciente” apresenta nome completo obrigatório; CPF, telefone, e-mail, data de nascimento, CEP, cidade, endereço e gênero. O gênero oferece Masculino, Feminino, Não-binário e Prefiro não informar. A interface informa que não havia categorias cadastradas e aponta Configurações → Categorias de Pacientes. O cadastro rápido também aparece dentro do formulário de agendamento.

**Simulação:** campos e fluxo foram inspecionados sem preencher nem salvar. A ficha demonstrativa mostra contatos, nascimento, status e resumo clínico/comercial.

### 2. Prontuário clínico

O seletor interno da ficha agrupa seções em três blocos:

- **Prontuário clínico:** Dados, Anamnese, Evolução, Odontograma, Tratamentos, HOF, Histórico.
- **Comercial e financeiro:** Orçamentos, Financeiro, Contratos.
- **Documentos e imagens:** Documentos, Fotos, Exames, Receitas, Atestados.

Na ficha de João Santos (teste), dados pessoais estavam preenchidos, mas o resumo mostrava 0 tratamentos, R$ 0,00 e 0 sugestões. A seção Tratamentos estava vazia.

### 3. Tratamento e odontograma

“Lançar Tratamento” declara ser um lançamento avulso com valores fixos da tabela de procedimentos, sem gerar orçamento formal; para valores editáveis, orienta usar “Novo Orçamento”. O formulário oferece escolha de paciente, dentição permanente/decídua/HOF, seleção de dentes/região, procedimento, quantidade, desconto percentual e observações clínicas; há comando de ditado por voz e resumo de subtotal/total. “Salvar Tratamento” permaneceu desabilitado enquanto nenhum procedimento foi selecionado.

O seletor de procedimentos exibiu exemplos como profilaxia, restaurações, endodontia, extrações, implantes, próteses, clareamento, radiografias, toxina botulínica e ácido hialurônico. A lista representa opções do catálogo, não recomendação clínica.

### 4. Orçamento e fechamento comercial

“Orçamento” é uma tela separada, com mapa dental, escolha de paciente, seleção de dentes/região e linhas de procedimento. A interface permite quantidade, valor editável, desconto global, validade (padrão visual de 30 dias) e observações. Há exportação indicada em PDF.

A seção opcional de pagamento mostrou: valor à vista, opção de entrada, parcelamento do saldo, número de parcelas, forma de pagamento (Cartão de Crédito selecionado por padrão), taxa da maquininha e vencimento da primeira parcela. O botão “Salvar e Gerar PDF” estava desabilitado sem itens/valor.

**Distinção funcional relevante:** tratamento avulso usa valores fixos; o orçamento formal permite montar proposta e ajustar valores/condições.

### 5. Contratos

Na ficha, “Contratos de Tratamento” diz gerenciar contratos gerados a partir dos orçamentos do paciente. A tela vazia informa que se deve selecionar itens aprovados do orçamento. “Novo Contrato” abriu um diálogo de seleção e “Criar Contrato” estava desabilitado por não haver orçamento aprovado. Portanto, a dependência orçamento aprovado → contrato está explicitada pela interface, mas geração, assinatura e armazenamento do documento não foram testados.

### 6. Solicitação de exames

A ficha ofereceu “Novo Exame”. O formulário “Pedido de Exames” permite selecionar paciente, registrar indicação clínica, adicionar exames e observações gerais; promete gerar pedido em PDF. “Salvar e Gerar PDF” estava desabilitado sem conteúdo. Na tela de orçamento, o catálogo de procedimentos incluía radiografia panorâmica e periapical; isso é distinto do formulário de pedido de exames.

### 7. Agenda

A agenda possui visões Dia, Semana e Mês, navegação por data, botão Hoje, lista de atendimentos e alerta de agendamentos atrasados com opções Remarcar e Falta. Na semana de 05 a 11 de outubro de 2026, a demonstração mostrava 10 atendimentos, 1 profissional e dois pacientes repetidos em blocos de horários; sábado e domingo sem compromissos.

O formulário “Novo Agendamento” oferece Consulta ou Bloqueio, paciente, cadastro rápido, cadeira/local (Sem local definido ou Consultório 1), data, início/fim, status (Agendado, Confirmado, Concluído, Falta) e observações. O botão Criar agendamento ficou desabilitado por não haver paciente selecionado. Não alterei status, não remarquei consulta e não criei agendamento.

### 8. Anamneses

A área tem abas Formulários e Preenchidas, permite criar formulário e oferece três modelos padrão: Adulto - Primeira Visita (35 perguntas), Adulto - Bruxismo (31) e Criança/Adolescente (30). Cada modelo apresenta link copiável. Também existe área “Preencher no Sistema”, com seletores de formulário e paciente. Nenhum formulário foi copiado, enviado ou preenchido.

### 9. Configurações

Abas observadas:

- **Clínica:** nome da clínica/dentista, CRO e UF, especialização, telefone, site, página inicial preferida, filiais/endereços e imagens (logo, foto do dentista, assinatura digital).
- **Personalização:** cor aplicada aos PDFs timbrados, assinatura digital de tratamentos e formulário público de anamnese; opções de timbrado padrão/personalizado, posição da logo, rodapé e visualização A4.
- **Categorias de Pacientes:** categorias personalizadas com cor e ícone; nenhuma cadastrada.
- **Integrações:** Google Calendar e Mercado Pago. A descrição informa conexão da conta própria do Mercado Pago para emitir boletos diretamente ao paciente.
- **Equipe:** cadastro de membro, perfil e unidade, permissões de recepção para acesso financeiro, lançar receitas/despesas e deletar pacientes, além de dentistas parceiros.
- **Assinatura & Dados:** plano Teste Premium, status em teste, faturas/NF, importação de pacientes por planilha, exportação de dados (Excel/CSV), troca de senha, aplicativo, declarações de segurança e encerramento da assinatura.

Um tour guiado de configurações abriu automaticamente e foi fechado sem avançar. Nenhuma configuração foi modificada, integração conectada, arquivo importado/exportado ou solicitação de nota enviada.

## Catálogo de áreas no menu principal

O menu lateral apresentou: Dashboard, Agenda, Anamneses, Atestados, Comissionamento Equipe, Convênios, Estoque Pro, Exames Pro, Faceograma HOF Pro, Financeiro, Funil de Vendas Pro, Laboratórios, Novidades, Pacientes, Procedimentos, Próteses, Receitas Pro, Relatórios Pro, Suporte, Treinamentos e Configurações.

A existência desses destinos foi confirmada pelo menu. Nesta sessão, diversas rotas administrativas abriram com apenas uma árvore inicial sem conteúdo acessível; não é possível detalhar suas telas, regras ou operações com evidência suficiente. Entre elas: Atestados, Comissionamento, Convênios, Estoque, Faceograma, Financeiro, Funil, Laboratórios, Procedimentos, Próteses, Receitas e Relatórios. Algumas dessas áreas já foram vistas parcialmente em uma exploração anterior, mas isso não foi revalidado nesta sessão.

## Avaliação de fluxo e pontos de atenção

- **Boa organização por paciente:** a ficha concentra clínica, comercial, documentos e histórico sob um seletor de seções.
- **Separação clara entre execução e proposta:** lançamento avulso de tratamento não se confunde com orçamento negociável.
- **Dependência comercial explícita:** a interface orienta que o contrato parte de itens aprovados do orçamento.
- **Agenda com ação operacional:** atraso, remarcar e falta estão próximos da grade; o formulário de agendamento reúne status, cadeira e horário.
- **Materiais ao paciente:** anamnese por link e documentos/PDF têm personalização visual em configurações.
- **Onboarding necessário:** algumas capacidades dependem de categorias, equipe, unidades e integrações configuradas. A demonstração não tinha categoria nem filial e a agenda apresentava “Sem dentista”.
- **Validar coerência de dados:** o cabeçalho da ficha e os dados pessoais mostraram datas de nascimento divergentes por um dia para o mesmo paciente de teste (22/08/1985 versus 21/08/1985). É um achado na demonstração; precisa ser conferido antes de classificar como defeito do sistema.
- **Leitura de indicadores:** dashboard zerado em financeiro e com agendamentos ativos parece compatível com cenário demonstrativo; as demais áreas financeiras não foram acessíveis o bastante para conciliação.

## Cobertura e limitações

**Observado com conteúdo acessível:** Dashboard, menu, lista e cadastro (campos) de pacientes, ficha do paciente, seleção de seções, lançamento de tratamento (formulário), orçamento (formulário e pagamento), contrato (estado vazio e diálogo), pedido de exames (formulário), agenda (grade e formulário), anamneses e todas as seis abas de configurações.

**Não executado:** salvar/editar/excluir dados; enviar WhatsApp ou link; marcar falta/remarcar/concluir consulta; gerar PDFs; assinar contrato; submeter exame; alterar permissões; conectar integrações; importar/exportar dados; alterar assinatura/senha.

**Inacessível ou não verificado em profundidade:** conteúdo interno dos módulos administrativos listados no catálogo. As tentativas de abrir rotas diretamente resultaram em uma árvore de acessibilidade inicial vazia; não se inferiu comportamento funcional a partir apenas dos nomes do menu.

**Conclusão:** a exploração é ampla nas jornadas principais e parcial no inventário total do produto. “De cabo a rabo” exigiria acesso funcional e avaliação de cada módulo administrativo e integração, além de uma sessão autorizada de simulação com dados claramente descartáveis, pois o próprio Krivvo avisa que cadastros feitos durante o teste são mantidos.
