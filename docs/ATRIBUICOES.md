# Atribuição manual de pedidos (D-064)

Para somar ao trabalho de LTV pedidos que vieram de indicação ou de conversa manual, sem fingir que são receita a mais.

## Aba `atribuicoes`
Colunas: `numero_pedido`, `origem`, `observacao`, `registrado_em`.
- **Origem:** Indicação, WhatsApp manual ou Outro (outro texto vira Outro).
- Quem escreve é o painel do Cowork. A rotina **só lê**.
- Número pode vir com `#` ou `.0`. Número repetido: vale a última linha.

## O que a rotina faz
Junta a aba com a tabela `pedidos` (só pago e válido, não cancelado) e acrescenta em `vale_a_pena` a linha **"Indicações e contatos manuais"**, com os pedidos e a receita do **mês corrente**.
- `estado` = `sem controle`: não há grupo de controle, então é **receita atribuída, não receita a mais**. As colunas receita_a_mais, custo e resultado ficam vazias.
- Colunas novas no fim de `vale_a_pena`: `pedidos` e `receita_atribuida` (vazias nas outras linhas). `recebeu` repete o número de pedidos e `gasto_medio` é a receita por pedido.
- Receita = subtotal menos desconto (produtos, sem frete), a mesma regra do carrinho.
- **Pedido já reconhecido por qualquer ciclo da Fila conta só na Fila** (Carrinho, Garimpo, VIP ou 45 dias): é o primeiro pedido pago do mesmo email ou telefone em até 7 dias do primeiro toque (ou do abandono, no grupo de comparação). Ele não entra em "Indicações e contatos manuais". A nota da linha diz **quantos foram ignorados por isso** e de qual origem da Fila (ex.: "2 ignorado(s) por já estarem na Fila (Carrinho: 1, VIP: 1)").

## Prefixo de cupom de indicação (opcional)
Nova linha no fim da aba `Configuração`: **Prefixo de cupom de indicação**, vazia por padrão. Se preenchida (ex.: `AMIGO-`), pedidos do mês com cupom que **começa** com esse texto (sem diferenciar maiúsculas) entram sozinhos como Indicação. Uma atribuição manual do mesmo pedido prevalece.

## Como conferir
Na aba `vale_a_pena`, última linha. Se a aba `atribuicoes` não existe, a linha aparece com 0 pedidos.
