# Newsletter semanal (D-063)

O Painel prepara toda quarta a lista de discos para a newsletter. **Ele não envia nada pelo Brevo**: só monta a aba e avisa por email.

## O que acontece
1. Na rodada de hora em hora, a partir das 17h de quarta (Brasília), o Painel monta a aba `newsletter_semana` e a linha da aba `newsletter_aviso`. Faz isso uma vez por quarta.
2. O script do Google (o mesmo do resumo de segunda) manda um email curto para os "Emails do resumo" da aba `Configuração`: **"Newsletter da semana: N discos prontos"**.
3. O Cowork usa a aba `newsletter_semana` para montar a campanha e, depois de montada, preenche a aba `newsletter_historico` (colunas `url` e `data_envio`). O que está lá não volta na semana seguinte.

## Quais discos entram
- Em estoque (mais de 0) e com Exibir = verdadeiro.
- Entraram ou voltaram ao estoque nos últimos 7 dias (coluna `no_estoque_desde` da aba `produtos`).
- São discos (camiseta, combo e outros itens da loja ficam de fora).
- Não estão na aba `newsletter_historico`. A comparação aceita a url completa ou só o final dela.

## Colunas da aba `newsletter_semana`
`url` (completa), `nome`, `artista`, `album`, `ano`, `tipo` (usado/lacrado), `preco`, `imagem` (tamanho 640), `familia` (mesma regra de gêneros da régua) e `descricao` (texto sem HTML, até 600 caracteres). Mais recentes primeiro.

Artista, álbum e ano saem do nome do produto ("LP Artista - Álbum (1977) (Vinil usado)"). Se o nome não tem separador, o artista fica vazio e o álbum recebe o nome limpo.

## Aba `produtos`: colunas novas no fim
- `imagem`: URL da primeira imagem, pela API oficial, no tamanho 640 (o nome do arquivo troca `-1024-1024` por `-640-0`).
- `descricao`: texto da descrição, sem HTML, até 600 caracteres.
- `no_estoque_desde`: dia (AAAA-MM-DD) em que o produto entrou ou voltou ao estoque; vazio se está sem estoque.

## Como o dia de entrada no estoque é descoberto
A API não guarda esse dia. A rotina compara com a aba `produtos` da rodada anterior: produto que estava sem estoque e agora tem ganha o dia de hoje; produto novo vale o dia em que foi criado; quem continua em estoque mantém o dia. Na primeira vez que a coluna existiu, quem já estava em estoque ficou com o dia da criação, então só os discos criados na última semana entram na primeira newsletter.
**Limite:** se um disco esgotar e voltar entre duas rodadas de uma hora, o retorno não é percebido.

## Como conferir
- Aba `newsletter_semana` na quarta, depois das 17h; aba `newsletter_aviso` com o texto do email.
- Para testar o email sem esperar: no Apps Script, rode `enviarNewsletterAgora`.
- Se a aba `newsletter_historico` não existir, nada é excluído.

## Detalhes do aviso (revisão do script)
- A célula `gerado_em` da aba `newsletter_aviso` é gravada como **texto** "AAAA-MM-DD HH:mm" (gravação sem conversão). O script também aceita o caso de a planilha converter para data.
- O email da fila mostra o rótulo do modelo, igual ao painel: T2_FRETE = Frete grátis; T3_CUPOM = 10% nos discos (oferta final); ESGOTADO = Estoque alterado; ALERTA_GARIMPO = Aviso de garimpo; G45 = Garimpo de 45 dias; VIP = VIP; os demais T1/T2 = Lembrete.


## Importante para o Cowork
Não renomeie nem reordene colunas de `newsletter_semana`. A `newsletter_historico` é sua; o Painel só lê.
