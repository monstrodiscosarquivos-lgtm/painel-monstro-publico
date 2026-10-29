# Especificação · aba K7 e nível de acesso "k7" (D-092)

Pedido do Túlio em 29/10/2026. Leia o `AGENTS.md` antes.

**Trabalhe somente nesta pasta** (`migracao-publica/painel-monstro-publico`). Não altere nada em `C:\Users\tulio\painel-monstro`.

## Objetivo

Uma aba própria no Painel para acompanhar a **Fita K7 Goiânia Rock City 2026**: produto 375734821, campanha `grc2026` dos links das bandas (D-076). Algumas pessoas, como as bandas e os parceiros do projeto, entram com um nível novo, `k7`, e veem **só essa aba**.

## 1. Rotina: aba nova `k7_resumo`, sem dados pessoais

Gerada a cada rodada a partir das tabelas que a rotina já tem (`pedidos`, `itens`, `ga4_links`, `ga4_diario`). Formato longo, com as colunas `bloco, chave, valor_1, valor_2, valor_3, valor_4`, para não precisar de abas novas a cada ideia. Blocos:

- **`totais`:**
  - fitas vendidas (pedidos válidos, soma das quantidades do produto);
  - receita da fita (valor dos itens, sem frete);
  - número de pedidos;
  - ticket médio;
  - primeira e última venda;
  - estoque atual do produto.
- **`por_dia`:** data, fitas vendidas, receita, sessões na página da fita (GA4, se houver).
- **`por_banda`:** banda (utm_source), cliques ou sessões, carrinhos, compras e receita atribuídas pelo GA4. É o mesmo dado do ranking atual da aba Resultados.
- **`canais`:** de onde vieram as compras da fita pelo GA4 (links das bandas, Instagram, email, direto...), com sessões e compras.
- **`junto_com`:** os 10 produtos mais comprados no mesmo pedido da fita (nome do produto e quantas vezes). Ajuda a ver quem a fita trouxe para a loja.

**Nunca** inclua nome, email, telefone, cidade ou número de pedido. A aba é lida pelo nível `k7`. Teste que nenhuma coluna tem `@` nem número de telefone.

## 2. Painel: aba "K7"

Em `apps-script/painel-web/painel-monstro.html`, aba nova **K7** na barra de abas, usando só `k7_resumo` e `ga4_links`:

1. Topo com os números grandes: fitas vendidas, receita, pedidos e estoque restante.
2. Gráfico simples de vendas por dia (mesmo estilo dos gráficos do Painel).
3. **Ranking das bandas:** mover/reaproveitar o ranking que já existe em Resultados ("Links das bandas"). Ele continua aparecendo em Resultados para quem tem acesso a Resultados.
4. Canais de venda da fita e "comprado junto com a fita".
5. Texto curto explicando que a atribuição por banda vem do GA4 (quem clicou no link da banda), então uma compra feita depois por outro caminho conta para o outro caminho.

## 3. Nível de acesso `k7`

**Cofre** (`apps-script/painel-web/Cofre.gs`):

- `usuario_` aceita o nível `k7` além de `especial` e `comum`.
- Nível `k7` **só lê** `k7_resumo` e `ga4_links`. Qualquer outra faixa pedida volta vazia (lista branca, não lista negra).
- Nível `k7` **não grava nada**: `podeGravar_` retorna falso.
- **Não mude** o `SO_ESPECIAL` nem os outros níveis. No fim, me diga as linhas exatas que mudaram: o Cowork monta o Cofre completo com os dados reais. Não peça para o Túlio colar o arquivo inteiro do repositório.

**Painel:**

- Com `PM.nivel === 'k7'`, mostra só a aba K7, sem a barra das outras abas, e pede ao Cofre só as faixas da aba K7 (não peça as outras).
- `especial` e `comum` veem a aba K7 junto com as demais.

**Aba `Acessos` da planilha:** o Túlio inclui as pessoas com nível `k7` (email, nome, k7). Documente em `apps-script/painel-web/LEIA-ME.md`.

## 4. Testes

- `k7_resumo` com dados fictícios: totais, por dia, por banda e "junto com" corretos. Pedido cancelado não conta.
- Nenhum dado pessoal na aba.
- No `teste_local.js`:
  - Cofre com nível k7 lê só as duas abas e não grava;
  - Painel com nível k7 mostra só a aba K7 e pede só as faixas dela.

## 5. Fechamento

1. Rode `montar_painel_web.py`, `node apps-script/teste_local.js` e a suíte Python uma vez (Python: `..\..\.venv\Scripts\python -m pytest -q`).
2. Registre D-092 em `docs/DECISOES.md` e `docs/ESTADO.md`.
3. Dê ao Túlio o passo a passo:
   1. commit nesta pasta;
   2. Painel.html na Entrada, com Nova versão > Implantar, copiando com `Get-Content ... -Raw -Encoding UTF8 | Set-Clipboard`;
   3. o trecho do Cofre (o Cowork prepara o arquivo completo);
   4. como incluir pessoas com nível k7 na aba Acessos;
   5. avisar o Cowork para republicar o Painel do claude.ai.
