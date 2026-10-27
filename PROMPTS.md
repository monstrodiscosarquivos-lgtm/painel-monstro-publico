# Prompts do projeto

Funcionam no Claude Code ou no Codex. Copie e cole um prompt por vez no agente, aberto nesta pasta. Só passe para o próximo quando o "Como conferir" estiver ok.

---

## Etapa 0 · Preparar o projeto

```
Leia o AGENTS.md inteiro e siga o protocolo de passagem de bastão. Depois:
1. Confira se o Python 3.12 e o Git estão instalados no meu computador e me diga como instalar o que faltar.
2. Crie a estrutura de pastas descrita no AGENTS.md, um ambiente virtual Python e o arquivo requirements.txt.
3. Inicie o repositório git local (ainda sem GitHub).
4. Me explique em poucas linhas o que foi criado.
Não leia nenhum arquivo da pasta dados/ ainda.
```

**Como conferir:** o agente mostra a lista de pastas criadas e diz que o git foi iniciado.

---

## Etapa 1 · Ler as planilhas exportadas

Antes: exporte Clientes, Vendas e Produtos da Nuvemshop e coloque os 3 arquivos em `dados/entrada/`.

```
Implemente o coletor por planilhas (painel_monstro/coletor/planilhas_csv.py) seguindo o AGENTS.md.
Ele deve ler as 3 exportações da Nuvemshop em dados/entrada/ e montar as tabelas clientes, pedidos, itens e produtos.
Depois rode a referencia/reativacao.py com os mesmos arquivos e compare: total de pedidos pagos, compradores únicos e volumes de cada etapa da régua têm que bater.
Crie testes com dados fictícios. Me mostre a comparação lado a lado.
```

**Como conferir:** os números da versão nova e da referência são iguais.

---

## Etapa 2 · Ler direto da API da Nuvemshop

Antes: crie o aplicativo sob medida na Nuvemshop e coloque o token no arquivo `.env` (copie o arquivo `env-exemplo.txt`, renomeie a cópia para `.env` e preencha). Não cole o token no chat.

```
Implemente o coletor pela API da Nuvemshop (painel_monstro/coletor/nuvemshop_api.py), só leitura, seguindo as notas do AGENTS.md e a documentação oficial.
Primeira execução: baixa tudo. Próximas: só o que mudou desde a última.
Respeite o limite de requisições. Não imprima o token em lugar nenhum.
No fim, compare os totais da API com os da Etapa 1 e me mostre as diferenças.
```

**Como conferir:** os totais da API e da planilha batem (pode haver diferença só nos pedidos feitos depois da exportação).

---

## Etapa 3 · Motor da régua e indicadores

```
Implemente painel_monstro/motor/regua.py e painel_monstro/motor/indicadores.py seguindo as regras de negócio do AGENTS.md.
A régua precisa dar os mesmos números da referência. Os indicadores precisam usar a aba custos para margem, Meta e Brevo.
Escreva testes para cada regra (janelas, VIP, controle, uma compra zera o relógio).
Me mostre os indicadores de hoje numa tabela.
```

**Como conferir:** a tabela mostra valores parecidos com os do documento de estratégia (receita de quem volta perto de R$6,3 mil por mês, 1.058 clientes no último ano).

---

## Etapa 4 · Gravar na Planilha Google

Antes: crie a planilha "Painel Monstro · dados" e a conta de serviço do Google (o passo a passo está no documento de implementação). Salve o arquivo JSON em `credenciais/` e o ID da planilha no `.env`.

```
Implemente painel_monstro/saidas/planilha_google.py: grava cada tabela numa aba da planilha, atualizando sem duplicar.
Crie também as abas custos e alertas com o cabeçalho pronto para eu preencher.
Rode uma vez e me diga quantas linhas foram para cada aba.
```

**Como conferir:** abra a planilha e veja as abas preenchidas.

---

## Etapa 5 · Rodar sozinho no GitHub

Antes: crie o repositório privado `painel-monstro` no GitHub.

```
Prepare a rotina automática:
1. Crie .github/workflows/rotina.yml rodando de hora em hora: coletor pela API, motor, planilha.
2. Me guie, clique por clique, para cadastrar os segredos no GitHub (Settings > Secrets and variables > Actions).
3. Confira que nenhum dado de cliente nem chave está no repositório antes de enviar.
4. Conecte o repositório local ao GitHub e envie.
5. Rode a rotina manualmente uma vez e me mostre o resultado.
```

**Como conferir:** em GitHub > Actions aparece a rotina com um sinal verde, e a planilha atualiza sozinha na hora seguinte.

---

## Etapa 5.1 · Carrinho abandonado

Antes: confira que o aplicativo da Nuvemshop tem leitura de pedidos (os carrinhos vêm daí).

```
Implemente o módulo de carrinho abandonado (painel_monstro/saidas/carrinhos.py) seguindo a seção "Carrinho abandonado" do AGENTS.md.
Primeiro, crie na Planilha Google as abas Configuração, Mensagens, Fila, Bloqueio e Resultados com a mesma estrutura de dados/referencia-privada/Carrinhos-Monstro-ferramenta.xlsx (se eu já estiver usando essa planilha, importe os meus modelos e parâmetros em vez dos padrões).
1. Buscar os carrinhos pela API, aplicar os filtros (janela, quem já comprou, estoque, duplicados, bloqueio) e decidir o toque e a oferta.
2. Escrever a mensagem de cada um e o link do WhatsApp, e gravar na aba carrinhos da planilha.
3. Detectar sozinho quando o carrinho virou pedido e marcar como recuperado.
4. Mandar a fila do dia por email às 10h e às 17h.
Comece me mostrando a fila de hoje sem gravar nada, para eu conferir o tom das mensagens.
```

**Como conferir:** a fila mostra os carrinhos de hoje com mensagem e link, e um pedido de teste feito a partir de um carrinho aparece como recuperado na hora seguinte.

---

## Etapa 5.2 · Fila única de WhatsApp (início de dezembro)

```
Siga a seção "Fila única de WhatsApp e medição" do AGENTS.md.
1. Ligue à aba Fila as origens VIP aos 75 dias e garimpo aos 45 dias, com prioridade, limite diário e a regra de 1 WhatsApp a cada 30 dias.
2. Importe da planilha manual os grupos do teste de 45 dias que já foram sorteados desde 12/10, sem sortear de novo.
3. Crie a aba Régua com as janelas e ofertas editáveis e faça o motor ler dela.
Comece me mostrando a fila de amanhã sem gravar nada.
```

**Como conferir:** a fila mostra as quatro origens na ordem certa e ninguém aparece duas vezes no mês.

---

## Etapa 6 · Painel (substituída: o painel é uma página no claude.ai, D-043)

```
Me guie, clique por clique, para montar no Looker Studio um painel ligado à Planilha Google com 4 páginas:
1. Objetivo: receita de quem volta, as 3 peças (clientes, taxa, gasto) e a meta.
2. Aquisição: CPA, custo por cliente novo, ROAS do Meta e ROAS geral.
3. Régua: cada etapa contra o grupo de controle.
4. Base e email: abertura, inválidos, descadastros, base ativa.
Antes, crie na planilha as abas de resumo que deixam o painel simples de montar.
```

**Como conferir:** o painel abre no celular e mostra os números de hoje.

---

## Etapa 7 · Régua automática no Brevo (só depois da Black Friday)

```
Implemente painel_monstro/saidas/brevo.py: todo dia atualiza os atributos dos contatos (ETAPA, DIAS_SEM_COMPRAR, FAMILIA, VIP, CONTROLE) e coloca cada cliente na lista da etapa dele, sem colocar o grupo de controle.
Comece em modo teste e me mostre o que faria. Só desligue o modo teste quando eu confirmar.
Depois me guie para criar no Brevo uma automação por lista para cada etapa.
```

**Como conferir:** em modo teste, a lista do que seria feito bate com as listas do mês.

---

## Etapa 8 · Garimpo e públicos do Meta

```
Implemente a lista de garimpo: um Google Forms alimenta a aba desejos, e a rotina compara cada produto novo com os desejos abertos. Quando bater, cria um alerta na aba alertas com a mensagem de WhatsApp pronta.
Implemente também a exportação mensal de públicos para o Meta (quem não abre email e quem sumiu há mais de 180 dias).
```

**Como conferir:** cadastre um desejo de teste com um disco que acabou de entrar e veja o alerta aparecer na hora seguinte.

---

## Sempre que abrir uma sessão nova (ou trocar de agente)

```
Leia o AGENTS.md, o docs/ESTADO.md e as últimas entradas do docs/HISTORICO.md.
Rode os testes. Depois me diga em 3 linhas em que ponto o projeto está, se algo está quebrado e qual é o próximo passo.
Não mude nada ainda.
```

## Antes de fechar uma sessão

```
Vamos encerrar por hoje. Siga o protocolo de passagem de bastão do AGENTS.md: atualize docs/ESTADO.md, acrescente a entrada em docs/HISTORICO.md, registre decisões em docs/DECISOES.md e faça o commit.
Me mostre o resumo do que ficou registrado.
```
