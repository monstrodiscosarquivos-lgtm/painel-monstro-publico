# Especificação · pedidos fora da Nuvemshop e origens da raspadinha (D-080 e D-081)

Pedido do Túlio em 26/10/2026. Leia o `AGENTS.md` antes. As duas partes são independentes: faça uma, teste, depois a outra.

**Onde trabalhar:** nesta pasta (`migracao-publica/painel-monstro-publico`), que é o repositório público `painel-monstro-publico`. O ambiente Python e o `.env` ficam na pasta principal: rode os testes com `..\..\.venv\Scripts\python -m pytest -q`. Repositório público: nada de dados de clientes no código, nos testes ou nos docs.

**Arquivos principais:**

- `apps-script/painel-web/painel-monstro.html`: fonte do Painel. Depois de editar, gere a versão web com `python apps-script/painel-web/montar_painel_web.py`.
- `apps-script/raspadinha/Sorteio.gs`: sorteio da raspadinha.
- `apps-script/painel-web/Cofre.gs`: lista de abas restritas.

**Abas que o Cowork já criou na planilha (não crie, não renomeie):**

- `pedidos_manuais`, com os cabeçalhos `id, data_venda, descricao, forma_pagamento, valor_total, frete, taxa, parcelas, modo, mes_unico, cronograma, situacao, incluido_em, atualizado_em`.
- `rasp_campanhas` ganhou a coluna `origens`, na coluna R, no fim.

---

## Parte 1 · Pedidos fora da Nuvemshop na comissão (D-080)

Alguns pedidos são pagos fora da loja, quase sempre no PagBank parcelado sem juros. O Túlio ganha comissão quando o dinheiro cai. Ele precisa lançar esses pedidos no Painel e escolher como entram:

- **Mês único:** o pedido inteiro conta num mês escolhido.
- **Por parcela:** cada parcela conta no mês em que cai.

### Tela (aba Comissão, bloco novo "Pedidos fora da Nuvemshop")

Siga o estilo do bloco "Produtos sem comissão" (`renderSemCom`, `salvarSemCom`).

1. Botão **Lançar pedido de fora**, que abre um formulário com:
   - **data da venda;**
   - **descrição livre** (ex.: "Venda na loja física, 3 LPs"). Avise no rótulo: "Não precisa pôr nome completo nem telefone";
   - **forma de pagamento:** PagBank, Pix, Dinheiro ou Outro;
   - **valor total;**
   - **frete:** padrão 0;
   - **taxa:** em R$ ou em %; se ficar vazia, usa a taxa estimada da Configuração para cartão;
   - **número de parcelas.**
2. **Como entra na comissão:** duas opções, por parcela ou mês único.
   - **Por parcela:** pede a data da 1ª parcela e mostra a lista das parcelas (mês e valor), uma por mês a partir dela, com o valor total dividido igualmente. Os centavos que sobram vão para a 1ª parcela. Cada mês e cada valor podem ser editados antes de salvar. A soma tem que fechar com o valor total; se não fechar, mostre aviso e não salve.
   - **Mês único:** escolhe o mês (AAAA-MM).
3. **Lista dos pedidos lançados.** Cada linha mostra data, descrição, total, modo e meses. Tem os botões **Editar** e **Cancelar**. Cancelar só muda `situacao` para `cancelado`, nunca apaga a linha.

### Gravação

Uma linha por pedido em `pedidos_manuais`:

| Coluna | Valor |
|---|---|
| `id` | `M` + AAAAMMDD + 3 letras aleatórias |
| `modo` | `parcelas` ou `mes` |
| `cronograma` | JSON `[{"mes":"2026-11","valor":200}, ...]` (no modo `mes`, um item só) |
| `situacao` | `ativo` ou `cancelado` |
| `incluido_em`, `atualizado_em` | data e hora da gravação |

Valores numéricos com ponto decimal.

### Cálculo (`comCalc`)

Para o mês `m`, cada pedido manual ativo com item de cronograma em `m` entra como um pedido extra, com a fração `f = valor_da_parcela / valor_total`:

- **vendido:** + `valor_total × f`;
- **frete:** + `frete × f`;
- **taxa:** + `taxa × f`. Se a taxa estiver vazia, use `valor_total × taxa estimada do cartão / 100 × f`;
- **base da comissão:** + `(valor_total − frete − taxa) × f`.

Ele aparece na lista de pedidos do mês com a marca **"fora da Nuvemshop"** e a parcela (ex.: "parcela 2 de 3"). Também entra no registro do mês (`comRegistrar`) e na cascata, numa linha própria: "Pedidos fora da Nuvemshop". Não aplica cupom, estorno nem produtos sem comissão.

`comMeses()` precisa incluir os meses que só têm pedido manual (ex.: uma parcela no mês seguinte).

### Acesso

Só o nível especial lê e altera essa aba. Acrescente `'pedidos_manuais'` em `SO_ESPECIAL` no `Cofre.gs`. Ao Túlio, diga para mudar **só essa linha** no Apps Script do Cofre, sem colar o arquivo inteiro: a versão pública do Cofre tem valores de exemplo.

### Testes

O projeto tem testes de JavaScript ou do painel? Se tiver, siga o padrão. Se não tiver, extraia o cálculo das parcelas para uma função pura e teste com Node. Casos:

- R$600 em 3x divide 200/200/200;
- R$100 em 3x divide 33,34/33,33/33,33;
- soma diferente do total recusa;
- modo `mes` cai inteiro no mês escolhido;
- pedido cancelado não conta;
- base de uma parcela com frete e taxa proporcionais.

---

## Parte 2 · Origens da raspadinha (D-081)

Hoje a origem vem do `utm_source` do link:

- `canal_()` no `Sorteio.gs` só reconhece `email` e `instagram`; o resto vira `outro` ou `direto`.
- O `utm_source` original já é gravado em `rasp_jogadas`.
- O Túlio quer mandar a mesma raspadinha por WhatsApp, pela lista de transmissão, pelo grupo da loja etc. e ver no Painel de onde veio cada jogada e cada venda.

### Configuração da campanha (Painel, aba Raspadinha)

1. **Origens prontas:** `email`, `instagram`, `whatsapp`.
2. **Origens personalizadas:** campo novo "Outras origens desta campanha", com botão **Adicionar origem**.
   - Cada origem tem um nome (ex.: "Lista de transmissão") e um código gerado a partir do nome: minúsculas, sem acento, com hífen (ex.: `lista-transmissao`). O código pode ser editado.
   - Grave na coluna `origens` como JSON: `[{"codigo":"lista-transmissao","nome":"Lista de transmissão"}]`.
   - Amplie a leitura de `rasp_campanhas` de `A1:Q200` para `A1:R200`.
3. **Canais permitidos:** a lista atual (`canais`) ganha a opção `whatsapp`. As origens personalizadas valem sempre que estiverem cadastradas.
4. **Links prontos:** a seção de links da campanha, onde hoje estão os links de email e Instagram (perto da linha que monta `?c=...&utm_campaign=...`), ganha um link para cada origem:
   - WhatsApp: `utm_source=whatsapp&utm_medium=mensagem`;
   - personalizada: `utm_source=<codigo>&utm_medium=<codigo>`.

   Cada link tem um botão **Copiar**.

### Sorteio (`Sorteio.gs`)

1. `canal_(c, cp)`:
   - `email` e `instagram` como hoje;
   - `/whats|wpp|zap/` vira `whatsapp`;
   - se o `utm_source` for igual ao `codigo` de uma origem da campanha, o canal é esse código;
   - sem `utm_source`, `direto`; o resto, `outro`.

   Use o mesmo canal em `abriu_` e `jogar_`.
2. **Bloqueio por canal:** como hoje para `email` e `instagram`, e o mesmo para `whatsapp` se ele não estiver nos canais permitidos. Origem personalizada cadastrada nunca é bloqueada.
3. `lerCampanha_` passa a ler a coluna `origens` (JSON; se for inválido, use lista vazia).

### Resultados (Painel)

1. Na tabela por canal da campanha (perto de `nomeCanal`), os nomes ficam assim: `whatsapp` = "WhatsApp"; origem personalizada = o `nome` cadastrado; `outro` = "Outra origem".
2. **Jogadas antigas** com canal `outro`: reclassifique no Painel pelo `utm_source` gravado, usando a mesma regra, sem alterar a planilha.
3. **Mapa de cupons** (`RASP_CUPONS`, usado na aba Resultados): use o mesmo nome de origem, para a venda aparecer como "Raspadinha · WhatsApp", "Raspadinha · Lista de transmissão" etc.

### Testes

Teste puro de `canal_` com:

- `brevo`, `instagram` e `wpp`;
- código personalizado exato;
- código parecido que não bate (vira `outro`);
- sem origem (`direto`).

Teste também o gerador de código do nome: "Lista de Transmissão" vira `lista-transmissao`.

---

## Fechamento

1. Rode `montar_painel_web.py` e a suíte inteira de testes.
2. Registre D-080 e D-081 no `docs/DECISOES.md` e o que mudou no `docs/ESTADO.md`. Em `docs/RASPADINHA.md`, explique as origens.
3. Dê ao Túlio, em português simples, a lista do que ELE faz, com os nomes dos botões:
   1. Commit e push nesta pasta (`git add -A; git commit -m "..."; git push`).
   2. Cofre: trocar só a linha do `SO_ESPECIAL` e salvar.
   3. Projeto "Raspadinha · sorteio" no Apps Script:
      - **Antes de colar o código novo**, confira em Configurações do projeto > Propriedades do script se existe `PLANILHA_ID`. A versão pública do código lê o ID dali. Se não existir, crie com o ID da planilha (o mesmo do `.env`).
      - Cole o `Sorteio.gs` novo e salve.
      - **Implantar > Gerenciar implantações >** lápis **> Versão: Nova versão > Implantar**, mantendo o mesmo endereço.
   4. Projeto "Painel Monstro" (Entrada): colar o `Painel.html` novo e implantar uma nova versão da mesma forma.
   5. Avisar o Cowork para republicar o Painel do claude.ai a partir de `apps-script/painel-web/painel-monstro.html`.
4. Não altere nada na loja, no Brevo nem nas campanhas reais para testar.
