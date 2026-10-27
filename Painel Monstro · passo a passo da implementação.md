# Painel Monstro · passo a passo da implementação

Oct 6, 2026 · @Túlio Queiroz

Você não escreve código. Em cada sessão você abre o Claude Code, cola um texto pronto e acompanha. Ele escreve, testa e explica em português. Este roteiro diz exatamente onde clicar e o que colar, sessão por sessão.

## Comece por aqui: tudo em ordem

**Não tem data marcada.** Faça no seu ritmo, uma sessão depois da outra, só passando para a próxima quando a anterior estiver conferida. Dá para fazer duas por dia. A única regra de calendário: a Sessão 7 (carrinho) precisa estar pronta antes da Black Friday, e a régua automática no Brevo (Sessão 10) pode ser construída já, mas só é ligada de verdade depois da Black Friday. Marque cada item conforme for fazendo.

### Bloco 1 · Hoje

- [ ] Sessão 1 · Etapa 0 · Preparar o projeto. Sonnet, 45 min. Pode instalar Python e Git no caminho.
- [ ] Copiar `clientes.csv`, `vendas.csv` e `produtos.csv` de `Reativacao\2026-10\entrada` para `painel-monstro\dados\entrada`. 5 min.
- [ ] Sessão 2 · Etapa 1 · Ler as planilhas. Sonnet, 45 min.

### Bloco 2 · Contas (1 hora, antes da Sessão 3)

- [ ] GitHub: criar a conta, ligar a verificação em duas etapas e guardar os códigos de recuperação.
- [ ] Nuvemshop: criar o aplicativo sob medida Painel Monstro, só leitura, e guardar o token.
- [ ] Google: criar a planilha Painel Monstro · dados, a conta de serviço e a chave JSON; compartilhar a planilha com o email da conta de serviço.
- [ ] Guardar tudo no gerenciador de senhas do Google.

### Bloco 3 · Dados direto da loja

- [ ] Sessão 3 · Etapa 2 · Ler direto da Nuvemshop. **Opus**, 50 min. Antes: token no `.env`.

### Bloco 4 · CRM rodando sozinho (pronto antes da Black Friday)

- [ ] Sessão 4 · Etapa 3 · Régua e indicadores. Sonnet, 50 min.
- [ ] Sessão 5 · Etapa 4 · Planilha Google. Sonnet, 1h. Antes: arquivo JSON na pasta `credenciais` e ID da planilha no `.env`.
- [ ] Preencher a aba custos: investimento no Meta do mês e margem média de usados e de lacrados.
- [ ] Sessão 6 · Etapa 5 · Rodar sozinho no GitHub. **Opus**, 50 min. Antes: repositório privado `painel-monstro`.
- [ ] Sessão 7 · Etapa 5.1 · Carrinho abandonado. **Opus**, 1h. Depois: teste com um carrinho seu.
- [ ] Confirmar que você e a Mariana recebem o email da fila às 10h e às 17h.

### Bloco 5 · Painel e fila completa

- [ ] Sessão 8 · Etapa 6 · Painel no Looker Studio, com a página Vale a pena?. Sonnet, 1h.
- [ ] Sessão 9 · Etapa 5.2 · Fila única de WhatsApp. Sonnet, 45 min.

### Bloco 6 · Brevo (construir já, ligar depois da Black Friday)

- [ ] Gerar a chave de API do Brevo.
- [ ] Sessão 10 · Etapa 7 · Régua automática no Brevo. Sonnet, 1h. Só desligar o modo teste depois de conferir.
- [ ] 18/01: decisão do teste do WhatsApp de 45 dias. Traga os números para a conversa do projeto.

### Bloco 7 · Garimpo e Meta (quando quiser)

- [ ] Sessão 11 · Etapa 8 · Garimpo e públicos do Meta. Sonnet, 1h.

### Enquanto o Painel não fica pronto (fora do Claude Code)

- [ ] A fila única (VIP, 45 dias, carrinho) já sai pelo Painel a partir de 12/10; a lista semanal manual não é mais necessária.
- [ ] Até a Sessão 7 ficar pronta, a Mariana usa a planilha `Carrinhos-Monstro-ferramenta.xlsx` para os carrinhos.
- [ ] Primeira terça de cada mês: pedir roda a reativação do mês na conversa do projeto.

## O ritual de toda sessão

Toda sessão segue os mesmos 8 passos. Na primeira vez leva uns minutos; depois vira automático.

1. **Abra o app do Claude** no computador (menu Iniciar do Windows, digite Claude).
2. **Clique na aba Code**, no alto, no centro da janela.
3. **Escolha Local** e clique em **Select folder**. Navegue até `C:\Users\tulio\painel-monstro` e confirme.
4. **Confira o modo de permissão**, no seletor ao lado do botão de enviar. Deixe em **Manual**: assim ele pede sua autorização antes de mudar um arquivo ou rodar um comando.
5. **Cole o texto de abertura** (abaixo) e envie. Ele lê o projeto e diz em 3 linhas onde paramos. Na Sessão 1 você pula este passo.
6. **Cole o texto da etapa** e envie. Acompanhe. Quando ele pedir permissão, leia o que ele explica e clique para aprovar. Se não entender, escreva: me explique antes, em palavras simples.
7. **Confira o resultado** do jeito que cada sessão indica. Só passe para a próxima quando estiver ok.
8. **Cole o texto de encerramento** e envie. Ele registra o que foi feito para a próxima sessão, seja com ele ou com o Codex. Depois feche a sessão.

**Qual modelo usar:** no seletor de modelo ao lado do botão de enviar, escolha o **Sonnet** para o dia a dia. Troque para o **Opus** nas sessões 3, 6 e 7 (API da Nuvemshop, GitHub e carrinho), que têm mais peças se encaixando, ou quando ele errar a mesma coisa duas vezes. O Opus gasta mais do seu limite de uso, por isso fica para quando faz diferença.

**Texto de abertura** (passo 5):

```
Leia o AGENTS.md, o docs/ESTADO.md e as últimas entradas do docs/HISTORICO.md.
Rode os testes. Depois me diga em 3 linhas em que ponto o projeto está, se algo está quebrado e qual é o próximo passo.
Não mude nada ainda.
```

**Texto de encerramento** (passo 8):

```
Vamos encerrar por hoje. Siga o protocolo de passagem de bastão do AGENTS.md: atualize docs/ESTADO.md, acrescente a entrada em docs/HISTORICO.md, registre decisões em docs/DECISOES.md e faça o commit.
Me mostre o resumo do que ficou registrado.
```

Os mesmos textos estão no arquivo `PROMPTS.md`, dentro da pasta `painel-monstro`.

## Mapa das sessões

Uma sessão por etapa. Cada uma leva de 45 minutos a 1h30 do seu tempo.

| Sessão | Etapa | Modelo | Antes, você precisa |
| --- | --- | --- | --- |
| 1 | 0 · Preparar o projeto | Sonnet | Nada |
| 2 | 1 · Ler as planilhas | Sonnet | Copiar 3 arquivos (5 min) |
| 3 | 2 · Ler direto da Nuvemshop | Opus | Aplicativo na Nuvemshop (10 min) |
| 4 | 3 · Régua e indicadores | Sonnet | Nada |
| 5 | 4 · Gravar na Planilha Google | Sonnet | Planilha e conta de serviço do Google (30 min) |
| 6 | 5 · Rodar sozinho no GitHub | Opus | Conta e repositório no GitHub (10 min) |
| 7 | 5.1 · Carrinho abandonado | Opus | Nada. Pronta antes da Black Friday |
| 8 | 6 · Painel no Looker Studio | Sonnet | Nada |
| 9 | 5.2 · Fila única de WhatsApp | Sonnet | Nada |
| 10 | 7 · Régua automática no Brevo | Sonnet | Chave do Brevo (5 min). Ligar só depois da Black Friday |
| 11 | 8 · Garimpo e públicos do Meta | Sonnet | Nada |

Nada disso mexe na loja. O Painel só lê dados da Nuvemshop e, até você liberar, só simula o que faria no Brevo.

## Contas que você vai precisar

São quatro, e só uma é nova. Dá para criar cada uma na sessão em que ela aparece (o passo a passo está lá) ou fazer tudo de uma vez numa tarde, em mais ou menos 1 hora.

| Conta | Já tem? | O que fazer | Quando | Custo |
| --- | --- | --- | --- | --- |
| Nuvemshop | Sim | Criar o aplicativo sob medida e guardar o token | Sessão 3 | Grátis no plano Escala |
| Google da loja | Provavelmente | Criar a planilha e a conta de serviço | Sessão 5 | Grátis, sem cartão |
| GitHub | Não | Criar a conta e o repositório privado | Sessão 6 | Grátis |
| Brevo | Sim | Gerar uma chave de API | Sessão 10 | Já incluso no plano |

**Onde guardar as chaves:** no gerenciador de senhas do Chrome ou do Google (senhas.google.com), uma entrada para cada, com o nome Painel Monstro e o serviço. Nunca num bloco de notas solto nem no WhatsApp.

### Criar a conta do GitHub (10 minutos)

1. Abra github.com e clique em **Sign up**.
2. Use o email da loja, crie uma senha forte e escolha um nome de usuário, por exemplo `monstrodiscos`.
3. Resolva o desafio de verificação (um quebra-cabeça) e digite o código que chega por email.
4. Se perguntar sobre plano, fique no **Free**. Pode pular as perguntas de personalização.
5. Ligue a verificação em duas etapas: foto do perfil no canto superior direito, **Settings**, **Password and authentication**, **Enable two-factor authentication**. Escolha o app autenticador (Google Authenticator no celular), escaneie o QR code e digite o código.
6. **Baixe os códigos de recuperação** que ele mostra e guarde no gerenciador de senhas. Sem eles, perder o celular trava a conta.

O repositório `painel-monstro` você cria na Sessão 6.

### Conta Google da loja

Use a conta Google que já tem o email da loja, com verificação em duas etapas ligada (myaccount.google.com, **Segurança**, **Verificação em duas etapas**). Se a loja não tiver uma, crie em accounts.google.com, **Criar conta**, **Para trabalho ou minha empresa**. No primeiro acesso ao console.cloud.google.com ele pede para aceitar os termos e escolher o país; não precisa cadastrar cartão. Se aparecer oferta de teste gratuito com cartão, ignore.

## Sessão 1 · Etapa 0 · Preparar o projeto

**Hoje. Uns 45 minutos. Modelo: Sonnet.** O Claude Code confere o que falta no seu computador, monta as pastas do projeto e liga o controle de versões (o Git, que guarda cada mudança e permite voltar atrás).

1. Faça os passos 1 a 4 do ritual: app do Claude, aba **Code**, **Local**, **Select folder** na pasta `painel-monstro`, modo **Manual**.
2. Cole este texto e envie:

```
Leia o AGENTS.md inteiro e siga o protocolo de passagem de bastão. Depois:
1. Confira se o Python 3.12 e o Git estão instalados no meu computador e me diga como instalar o que faltar.
2. Crie a estrutura de pastas descrita no AGENTS.md, um ambiente virtual Python e o arquivo requirements.txt.
3. Inicie o repositório git local (ainda sem GitHub).
4. Me explique em poucas linhas o que foi criado.
Não leia nenhum arquivo da pasta dados/ ainda.
```

3. Ele vai pedir permissão para rodar comandos que só consultam o computador (por exemplo, `python --version`). Pode aprovar.
4. **Se ele disser que falta o Python:** abra python.org/downloads no navegador e clique no botão amarelo de download. Abra o arquivo baixado. **Na primeira tela, marque a caixa Add python.exe to PATH** (fica embaixo) e só então clique em **Install Now**. Esse detalhe evita a maioria dos problemas.
5. **Se ele disser que falta o Git:** abra git-scm.com/downloads/win, baixe o instalador de 64 bits, abra e clique em **Next** em todas as telas, até **Install** e **Finish**.
6. Instalou alguma coisa? Feche o app do Claude e abra de novo (para ele enxergar o que foi instalado), refaça os passos 1 a 4 do ritual e escreva: instalei o que faltava, pode continuar a etapa 0.
7. Ele vai pedir permissão para criar pastas e arquivos. Aprove.

**Como conferir:** ele mostra a lista de pastas criadas (como `painel_monstro`, `dados`, `testes`) e diz que o repositório git foi iniciado. Se aparecer algum erro vermelho, copie o texto do erro, cole e escreva: o que isso significa e como resolvo?

8. Cole o **texto de encerramento** e feche a sessão.

## Sessão 2 · Etapa 1 · Ler as planilhas

**Logo depois da Sessão 1. Uns 45 minutos. Modelo: Sonnet.** O Painel aprende a ler as exportações da Nuvemshop e confere se chega nos mesmos números do script que já usamos.

**Antes (5 minutos), no Explorador de Arquivos:**

1. Abra a pasta `Monstro Discos\Reativacao\2026-10\entrada`.
2. Selecione os 3 arquivos (`clientes.csv`, `vendas.csv` e `produtos.csv`) e aperte Ctrl+C.
3. Abra a pasta `Monstro Discos\painel-monstro\dados\entrada` (criada na Sessão 1) e aperte Ctrl+V.

**No Claude Code:**

1. Ritual, passos 1 a 5 (inclusive o texto de abertura).
2. Cole este texto e envie:

```
Implemente o coletor por planilhas (painel_monstro/coletor/planilhas_csv.py) seguindo o AGENTS.md.
Ele deve ler as 3 exportações da Nuvemshop em dados/entrada/ e montar as tabelas clientes, pedidos, itens e produtos.
Depois rode a referencia/reativacao.py com os mesmos arquivos e compare: total de pedidos pagos, compradores únicos e volumes de cada etapa da régua têm que bater.
Crie testes com dados fictícios. Me mostre a comparação lado a lado.
```

3. Aprove as criações de arquivo e os testes. Essa é a etapa em que ele mais escreve código; pode levar uns 15 minutos.

**Como conferir:** ele mostra uma tabela com duas colunas, Painel e Referência, e os números são iguais. Os valores mudam conforme o dia em que você roda; o que importa é que as duas colunas batam. **Se algum número não bater**, não avance. Escreva: me mostre onde está a diferença e por quê.

4. Texto de encerramento e feche.

## Sessão 3 · Etapa 2 · Ler direto da Nuvemshop

**Uns 50 minutos. Modelo: Opus.** A partir daqui ninguém precisa mais exportar planilha: o Painel busca os dados direto da loja.

**Antes, parte A: criar o aplicativo na Nuvemshop (10 minutos)**

1. Entre no painel da loja na Nuvemshop.
2. Menu **Aplicativos**, depois **Aplicativos sob medida**, depois **Criar aplicativo sob medida**.
3. Nome: `Painel Monstro`.
4. Permissões: marque só **leitura** de **Pedidos**, **Clientes** e **Produtos**. Não marque escrita nem acesso total. (Os carrinhos abandonados vêm junto com a leitura de pedidos.)
5. Clique em **Salvar**, depois no nome do aplicativo e em **Revelar**. O token aparece uma vez só: copie e guarde no gerenciador de senhas do navegador ou do Google.

Os nomes dos botões podem mudar um pouco. Se travar, procure por aplicativo sob medida na ajuda da Nuvemshop.

**Antes, parte B: guardar o token sem passar pelo chat**

1. Ritual, passos 1 a 5.
2. Escreva: crie o arquivo .env a partir do env-exemplo.txt e abra no Bloco de Notas.
3. O Bloco de Notas abre. Na linha `NUVEMSHOP_TOKEN=`, cole o token logo depois do sinal de igual, sem espaço. Aperte Ctrl+S e feche o Bloco de Notas.
4. Volte ao Claude Code e escreva: salvei o token no .env.

**Nunca cole o token no chat**, nem aqui nem no Claude Code. Ele fica só no arquivo `.env`, que nunca vai para a internet.

**Agora a etapa.** Cole este texto e envie:

```
Implemente o coletor pela API da Nuvemshop (painel_monstro/coletor/nuvemshop_api.py), só leitura, seguindo as notas do AGENTS.md e a documentação oficial.
Primeira execução: baixa tudo. Próximas: só o que mudou desde a última.
Respeite o limite de requisições. Não imprima o token em lugar nenhum.
No fim, compare os totais da API com os da Etapa 1 e me mostre as diferenças.
```

**Como conferir:** os totais da API e os da planilha batem. Pode haver diferença só nos pedidos feitos depois do dia da exportação, e ele deve dizer quais são.

Texto de encerramento e feche.

## Sessão 4 · Etapa 3 · Régua e indicadores

**Uns 50 minutos. Modelo: Sonnet. Antes: nada.** O Painel passa a calcular sozinho a etapa de cada cliente, o grupo de controle e os números do objetivo.

1. Ritual, passos 1 a 5.
2. Cole este texto e envie:

```
Implemente painel_monstro/motor/regua.py e painel_monstro/motor/indicadores.py seguindo as regras de negócio do AGENTS.md.
A régua precisa dar os mesmos números da referência. Os indicadores precisam usar a aba custos para margem, Meta e Brevo.
Escreva testes para cada regra (janelas, VIP, controle, uma compra zera o relógio).
Me mostre os indicadores de hoje numa tabela.
```

**Como conferir:** a tabela mostra a receita de quem volta perto de R$6,3 mil por mês e uns 1.058 clientes no último ano. Números muito diferentes disso: escreva me explique por que esse número está diferente do documento de estratégia.

Texto de encerramento e feche.

## Sessão 5 · Etapa 4 · Gravar na Planilha Google

**Uns 1h30, metade disso no Google. Modelo: Sonnet.** É a parte mais chata do projeto, e só se faz uma vez.

**Antes, parte A: a planilha (2 minutos).** Entre no Google Drive com a conta da loja. Clique em **Novo**, **Planilhas Google**, **Planilha em branco**. Renomeie para `Painel Monstro · dados`. Olhe o endereço no navegador: o ID é o trecho entre `/d/` e `/edit`. Copie e guarde.

**Antes, parte B: a conta de serviço (o "robô" que escreve na planilha).**

1. Abra console.cloud.google.com com a mesma conta da loja.
2. No alto, clique no seletor de projeto e em **Novo projeto**. Nome `painel-monstro`, **Criar**. Confira que ele ficou selecionado no alto.
3. Menu, **APIs e serviços**, **Biblioteca**. Procure **Google Sheets API**, abra e clique em **Ativar**. Volte e faça o mesmo com **Google Drive API**.
4. Menu, **IAM e administrador**, **Contas de serviço**, **Criar conta de serviço**. Nome `painel-monstro`, **Criar e continuar**, depois **Concluir** (pode pular as permissões).
5. Clique na conta criada, aba **Chaves**, **Adicionar chave**, **Criar nova chave**, formato **JSON**, **Criar**. Um arquivo vai baixar.
6. Mova esse arquivo para a pasta `painel-monstro\credenciais` (crie a pasta se não existir) e renomeie para `google-service-account.json`.
7. Na mesma tela da conta de serviço, copie o email dela (termina em `iam.gserviceaccount.com`).
8. Volte à planilha, clique em **Compartilhar**, cole esse email, escolha **Editor** e envie.

**Caminho mais curto para os passos 4 e 5** (a tela do Google muda de vez em quando):

1. No menu da esquerda, **APIs e serviços**, **Credenciais**.
2. No alto, **+ Criar credenciais**, **Conta de serviço**.
3. Nome `painel-monstro`, **Criar e continuar**. Na tela de papéis, não escolha nada e clique em **Continuar**, depois **Concluir**.
4. De volta em Credenciais, a conta aparece na seção **Contas de serviço**. **Clique no email dela** (termina em `iam.gserviceaccount.com`).
5. Só agora aparecem as abas no alto: clique em **Chaves**, **Adicionar chave**, **Criar nova chave**, **JSON**, **Criar**. O arquivo baixa sozinho.

A faixa de teste gratuito com crédito pode ser dispensada; não precisa de cartão.

Se travar em qualquer ponto, abra o Claude Code na pasta e escreva: me guie para criar a conta de serviço do Google, estou no passo tal.

**Antes, parte C: o ID no .env.** No Claude Code (ritual 1 a 5), escreva: abra o arquivo .env no Bloco de Notas. Na linha `PLANILHA_ID=`, cole o ID da planilha. Ctrl+S, feche, e escreva: salvei o ID da planilha.

**Agora a etapa:**

```
Implemente painel_monstro/saidas/planilha_google.py: grava cada tabela numa aba da planilha, atualizando sem duplicar.
Crie também as abas custos e alertas com o cabeçalho pronto para eu preencher.
Rode uma vez e me diga quantas linhas foram para cada aba.
```

**Como conferir:** abra a planilha no navegador e veja as abas preenchidas. Depois preencha a aba **custos** com o investimento no Meta do mês e a margem média de usados e de lacrados.

Texto de encerramento e feche.

## Sessão 6 · Etapa 5 · Rodar sozinho no GitHub

**Uns 50 minutos.** Modelo: Opus. Depois desta sessão, o Painel atualiza sozinho de hora em hora, com o computador desligado.

**Antes (10 minutos):**

1. Crie a conta em github.com, se ainda não tiver.
2. Ligue a verificação em duas etapas: foto do perfil no canto superior direito, **Settings**, **Password and authentication**, **Enable two-factor authentication**.
3. Clique no **+** no canto superior direito e em **New repository**. Nome `painel-monstro`, marque **Private**, não mude mais nada e clique em **Create repository**.

**No Claude Code** (ritual 1 a 5):

```
Prepare a rotina automática:
1. Crie .github/workflows/rotina.yml rodando de hora em hora: coletor pela API, motor, planilha.
2. Me guie, clique por clique, para cadastrar os segredos no GitHub (Settings > Secrets and variables > Actions).
3. Confira que nenhum dado de cliente nem chave está no repositório antes de enviar.
4. Conecte o repositório local ao GitHub e envie.
5. Rode a rotina manualmente uma vez e me mostre o resultado.
```

- No passo 2 ele vai te guiar para colar o token da Nuvemshop, o ID da planilha e o conteúdo do arquivo do Google **no site do GitHub**, não no chat.
- No passo 4, uma janela do navegador vai pedir para você entrar no GitHub e autorizar. Autorize.

**Como conferir:** no site do GitHub, abra o repositório e clique em **Actions**. A rotina aparece com um sinal verde. Na hora seguinte, a planilha atualiza sozinha.

Texto de encerramento e feche.

## Sessão 7 · Etapa 5.1 · Carrinho abandonado

**Precisa estar pronta antes da Black Friday. Uns 1h. Modelo: Opus. Antes: nada.** Se você e a Mariana já estiverem usando a planilha `Carrinhos-Monstro-ferramenta.xlsx`, ele importa os seus textos e parâmetros.

```
Implemente o módulo de carrinho abandonado (painel_monstro/saidas/carrinhos.py) seguindo a seção "Carrinho abandonado" do AGENTS.md.
Primeiro, crie na Planilha Google as abas Configuração, Mensagens, Fila, Bloqueio e Resultados com a mesma estrutura de dados/referencia-privada/Carrinhos-Monstro-ferramenta.xlsx (se eu já estiver usando essa planilha, importe os meus modelos e parâmetros em vez dos padrões).
1. Buscar os carrinhos pela API, aplicar os filtros (janela, quem já comprou, estoque, duplicados, bloqueio) e decidir o toque e a oferta.
2. Escrever a mensagem de cada um e o link do WhatsApp, e gravar na aba carrinhos da planilha.
3. Detectar sozinho quando o carrinho virou pedido e marcar como recuperado.
4. Mandar a fila do dia por email às 10h e às 17h.
Comece me mostrando a fila de hoje sem gravar nada, para eu conferir o tom das mensagens.
```

**Como conferir:**

1. Ele mostra a fila de hoje com mensagem e link. Leia o tom das mensagens com calma; se quiser mudar, mude na aba **Mensagens**.
2. Faça um teste real: no site, coloque um disco barato no carrinho com o seu email e telefone e não pague. No dia seguinte, ele aparece na fila. Finalize a compra pelo link: na hora seguinte, a linha vira **Recuperado**. Depois cancele o pedido na Nuvemshop.
3. Às 10h e às 17h, você e a Mariana recebem o email da fila.

Texto de encerramento e feche.

## Sessão 8 · Etapa 6 · Painel no Looker Studio

**Uns 1h. Modelo: Sonnet. Antes: nada.** Nesta sessão quem clica é você, no Looker Studio; o Claude Code prepara a planilha e dita os cliques.

```
Me guie, clique por clique, para montar no Looker Studio um painel ligado à Planilha Google com 4 páginas:
1. Objetivo: receita de quem volta, as 3 peças (clientes, taxa, gasto) e a meta.
2. Aquisição: CPA, custo por cliente novo, ROAS do Meta e ROAS geral.
3. Régua: cada etapa contra o grupo de controle.
4. Base e email: abertura, inválidos, descadastros, base ativa.
Antes, crie na planilha as abas de resumo que deixam o painel simples de montar.
```

Depois das 4 páginas, escreva também: agora a página Vale a pena?, seguindo a seção Fila única de WhatsApp e medição do AGENTS.md.

**Como conferir:** abra o link do painel no celular e veja os números de hoje.

## Sessão 9 · Etapa 5.2 · Fila única de WhatsApp

**Uns 45 minutos. Modelo: Sonnet. Antes: nada.** Liga o VIP e o garimpo de 45 dias à mesma fila do carrinho. Até aqui, a lista dos 45 dias sai toda segunda comigo, quando você pedir lista do WhatsApp da semana.

```
Siga a seção "Fila única de WhatsApp e medição" do AGENTS.md.
1. Ligue à aba Fila as origens VIP aos 75 dias e garimpo aos 45 dias, com prioridade, limite diário e a regra de 1 WhatsApp a cada 30 dias.
2. Importe da planilha manual os grupos do teste de 45 dias que já foram sorteados desde 12/10, sem sortear de novo.
3. Crie a aba Régua com as janelas e ofertas editáveis e faça o motor ler dela.
Comece me mostrando a fila de amanhã sem gravar nada.
```

**Como conferir:** a fila mostra as quatro origens na ordem certa e ninguém aparece duas vezes no mês.

## Sessão 10 · Etapa 7 · Régua automática no Brevo

**Construa quando chegar aqui, em modo teste; só desligue o modo teste depois da Black Friday. Uns 1h. Modelo: Sonnet.**

**Antes (5 minutos):** no Brevo, menu do perfil no canto superior direito, **SMTP e API**, aba **Chaves API**, **Gerar nova chave**, nome `painel-monstro`. Copie. No Claude Code, escreva: abra o arquivo .env no Bloco de Notas. Cole a chave depois de `BREVO_API_KEY=`, Ctrl+S, feche e escreva: salvei a chave do Brevo. Ele também vai te guiar para cadastrar a chave nos segredos do GitHub.

```
Implemente painel_monstro/saidas/brevo.py: todo dia atualiza os atributos dos contatos (ETAPA, DIAS_SEM_COMPRAR, FAMILIA, VIP, CONTROLE) e coloca cada cliente na lista da etapa dele, sem colocar o grupo de controle.
Comece em modo teste e me mostre o que faria. Só desligue o modo teste quando eu confirmar.
Depois me guie para criar no Brevo uma automação por lista para cada etapa.
```

**Como conferir:** em modo teste, a lista do que ele faria bate com as listas do mês. Só então escreva: pode desligar o modo teste.

## Sessão 11 · Etapa 8 · Garimpo e públicos do Meta

**Uns 1h. Modelo: Sonnet. Antes: nada.**

```
Implemente a lista de garimpo: um Google Forms alimenta a aba desejos, e a rotina compara cada produto novo com os desejos abertos. Quando bater, cria um alerta na aba alertas com a mensagem de WhatsApp pronta.
Implemente também a exportação mensal de públicos para o Meta (quem não abre email e quem sumiu há mais de 180 dias).
```

**Como conferir:** cadastre um desejo de teste com um disco que acabou de entrar no site e veja o alerta aparecer na hora seguinte.

## Se preferir usar o Codex

O projeto funciona igual no Codex. Abra o Codex, escolha a mesma pasta `painel-monstro` e siga o mesmo ritual, com os mesmos textos. O Codex lê o `AGENTS.md` sozinho, e os arquivos da pasta `docs` dizem onde o projeto parou. Dá para fazer uma sessão num e a próxima no outro.

## Quando travar

- **Erro na tela:** copie a mensagem de erro, cole no Claude Code e escreva: o que isso significa e como resolvo?
- **Ele quer fazer algo que você não entendeu:** escreva me explique antes, em palavras simples. Aprovar sem entender é o único jeito real de dar problema.
- **Ele parece perdido ou repetindo erro:** clique no botão de parar, feche a sessão, abra outra e cole o texto de abertura. Ele retoma do que ficou registrado.
- **Dúvida de estratégia** (o que medir, se vale mudar uma regra): traga para a conversa do projeto Monstro Discos.
- **A rotina parou no GitHub:** o GitHub manda email quando falha. Abra o Claude Code e escreva: a rotina do GitHub falhou, veja o que aconteceu.

## Cinco regras que não mudam

1. Chaves só no arquivo `.env` e nos segredos do GitHub. Nunca no chat, nunca num print.
2. Dados de clientes ficam na pasta `dados` e na Planilha Google, nunca no GitHub. O Claude Code confere antes de cada envio.
3. O repositório no GitHub é sempre privado.
4. Nada escreve no Brevo sem você desligar o modo teste.
5. Se uma chave vazar, apague na hora e crie outra (Nuvemshop: excluir o aplicativo e criar outro; Google: apagar a chave da conta de serviço; Brevo: apagar a chave).
