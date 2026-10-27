# Anúncios do Meta no Painel · especificação (Etapa 9)

Pedido do Túlio em 15/10/2026, desenho aprovado no Cowork (decisões D1 a D9 aceitas como recomendadas).
Objetivo: acompanhar as campanhas do Meta no celular, com alertas e uma direção de escala 3 vezes por semana,
e testar a hipótese "semana com pouco disco cadastrado rende menos" sem cair na armadilha da verba.

## Regras que não mudam

- Somente leitura no Meta (`ads_read`). Nenhuma chamada que crie, pause ou altere campanha, conjunto, anúncio ou orçamento.
  Fase 2 (agir) só com aprovação escrita do Túlio.
- Token e conta só em `.env` e GitHub Secrets (`META_ADS_TOKEN`, `META_ADS_ACCOUNT_ID`, já existem). Nunca no código nem em log.
- A API do Meta não responde do computador do Túlio (proxy). Rodar e validar pelo GitHub Actions (`workflow_dispatch`).
- Abas novas têm prefixo `anuncios_`, nunca `meta_` (as `meta_*` são públicos com dados de cliente e o painel do Cowork não lê).
  Nenhuma aba `anuncios_*` pode ter dado de cliente.
- Falha no Meta vira aviso e mantém o conteúdo antigo das abas, sem derrubar o resto da rotina (mesmo padrão de `tentar`).
- Mesma atribuição da `custos_automaticos`: `use_account_attribution_setting=true` e `action_report_time=conversion`.
  Compra = `offsite_conversion.fb_pixel_purchase` (não somar `omni_purchase`). Carrinho = `offsite_conversion.fb_pixel_add_to_cart`.
  Finalização = `offsite_conversion.fb_pixel_initiate_checkout`.

## Coleta (novo módulo `painel_monstro/saidas/anuncios.py`, passo `passo_anuncios` na rotina)

1. Histórico diário por campanha desde 2025-07-01 (`level=campaign`, `time_increment=1`), baixado uma vez em blocos de um mês e
   guardado em `dados/api/anuncios_historico.json` (cache do Actions, como os dados da Nuvemshop).
   Em cada rodada, rebaixar só os últimos 7 dias (a atribuição ainda mexe neles) e substituir no cache.
2. Por anúncio, últimos 30 dias (`level=ad`, `time_increment=1`), com `thumbnail_url` do criativo.
3. Por hora, últimos 3 dias, por campanha (`breakdowns=hourly_stats_aggregated_by_advertiser_time_zone`).
4. Estrutura: campanhas e conjuntos com `effective_status`, `daily_budget` ou `lifetime_budget`, `start_time`, `stop_time`/`end_time`.
5. Paginação completa. Conferir moeda BRL. Respeitar limite de uso (cabeçalho `x-business-use-case-usage`): se passar de 75%, parar e avisar.

## Tipo de campanha

Pelo nome, nesta ordem: contém `_local` em qualquer posição, `[evento]` ou `alcance` = **evento**; contém `rmk` ou `remarketing` = **remarketing**;
contém `black` ou `natal` ou `sazonal` = **sazonal**; o resto = **vendas**. Se a aba `anuncios_notas` tiver `tipo` para a campanha,
ele vale mais que o nome.

## Abas que a rotina grava (todas novas)

`anuncios_campanha_dia` (desde 2025-07-01, uma linha por dia e campanha)
: data, campanha_id, campanha, tipo, status, orcamento_dia, investido, investido_real, impressoes, alcance, frequencia,
  cliques_link, ctr_link, cpm, carrinhos, finalizacoes, compras, receita, roas_real, cpa_real

`anuncios_hoje` (últimos 3 dias por hora)
: data, hora, campanha_id, campanha, tipo, investido, cliques_link, carrinhos, finalizacoes, compras, receita

`anuncios_anuncios` (um por anúncio ativo ou com gasto nos últimos 30 dias)
: anuncio_id, anuncio, campanha_id, campanha, conjunto, tipo, status, thumb, investido_7d, compras_7d, receita_7d, ctr_7d,
  ctr_campanha_7d, frequencia_7d, investido_30d, compras_30d, receita_30d, cansado (sim/não), motivo

`anuncios_semana` (semanas de segunda a domingo, desde 2025-07-07, conta inteira e também só campanhas de vendas)
: semana_inicio, escopo (conta/vendas), investido, investido_real, variacao_investimento_pct, mudou_verba (sim se |variação| >= limite),
  compras, receita, roas_real, cpa_real, compras_por_100 (compras a cada R$ 100 investidos reais), cliques_link, conversao_clique_pct,
  carrinhos, finalizacoes, discos_criados, discos_voltaram, discos_entraram, pedidos_site, receita_site, leitura
- `discos_criados`: produtos que são disco (mesmo filtro da newsletter, sem camiseta e combo) com `criado_em` na semana.
- `discos_voltaram`: pela `no_estoque_desde` (D-063). Antes de 14/10/2026 fica **vazio**, não zero (D9).
- `pedidos_site` e `receita_site`: pedidos pagos e válidos da aba `pedidos` na semana (toda a loja online, qualquer origem).
- `leitura` cruza quantidade e eficiência contra a média das 4 semanas anteriores do mesmo escopo:
  compras acima e ROAS acima = "semana boa"; compras acima e ROAS abaixo = "escalando"; compras abaixo e ROAS acima = "travado";
  compras abaixo e ROAS abaixo = "problema". Menos de 4 semanas de histórico = vazio.

`anuncios_alertas` (recalculada a cada rodada; só alertas abertos)
: nivel (vermelho/amarelo), campanha, anuncio, regra, detalhe, desde
- Entrega cortada: campanha ativa gastou menos que o % mínimo do orçamento do dia ontem.
- Gasto sem venda: campanha de vendas com N dias seguidos de gasto e zero compra.
- Custo por venda acima do teto: CPA real dos últimos 7 dias acima do teto.
- Anúncio cansado: frequência 7d acima do limite em prospecção, ou CTR 7d do anúncio X% abaixo do CTR da campanha com mais de R$ 30 gastos.
- Evento já passou: campanha de evento com gasto hoje depois do `stop_time` ou da `data_evento` em `anuncios_notas`.
- Catálogo suspeito: remarketing com 10 ou mais carrinhos em 7 dias e finalizações menores que 15% dos carrinhos.
- ROAS real 7d da conta abaixo do ROAS de equilíbrio: vermelho.

`anuncios_resumo` (chave, valor): atualizado_em, dias_no_historico, ultima_data, estado (ok/aviso), aviso.

## Abas que o painel do Cowork escreve e a rotina só lê

`anuncios_notas`: campanha_id, tipo, data_evento, nota, registrado_em (texto "AAAA-MM-DD HH:mm"). Notas de resultado de evento (D4).
`anuncios_direcao`: data, prioridade, texto. Escrita pela direção agendada do Cowork (seg/qua/sex 7h46). A rotina não mexe.
Criar as duas abas só com cabeçalho se não existirem.

## Linhas novas no fim da `Configuração` (ajuda na coluna C, como as outras)

| Nome exato | Valor inicial |
|---|---|
| Anúncios: fator de imposto | 1,1383 |
| Anúncios: ROAS de equilíbrio | 2,85 |
| Anúncios: ROAS verde a partir de | 9 |
| Anúncios: ROAS amarelo a partir de | 6 |
| Anúncios: teto do custo por venda (R$) | 37 |
| Anúncios: frequência máxima | 3 |
| Anúncios: queda de CTR para anúncio cansado (%) | 40 |
| Anúncios: entrega mínima do orçamento (%) | 70 |
| Anúncios: dias de gasto sem venda | 3 |
| Anúncios: mudança de verba que marca a semana (%) | 30 |

`investido_real` = investido × fator de imposto. `roas_real` = receita / investido_real. `cpa_real` = investido_real / compras.

## Testes (padrão de `tests/`, sem rede)

Classificação de tipo, semana de segunda a domingo, `leitura` nos 4 quadros e com menos de 4 semanas, cada alerta disparando e não
disparando, `discos_voltaram` vazio antes de 14/10/2026, cache mesclando os 7 dias, falha do Meta mantendo abas antigas, e soma
mensal de `anuncios_campanha_dia` batendo com `meta_do_mes` da `custos_automaticos` (mesmo mês, tolerância de R$ 1).

## Fechamento

Decisão D-066 em DECISOES.md, ESTADO.md com bloco "Avisar o Cowork" listando abas e colunas finais, commit e push.
Depois, uma execução manual no Actions para baixar o histórico e conferir a aba `anuncios_resumo`.

## Implementação e execução (15/10/2026, D-066)

- `painel_monstro/saidas/anuncios.py`: cliente GET com token no cabeçalho, paginação por cursor sem seguir URLs com token e limite de 7 minutos para a coleta. Ultrapassar 75% em qualquer percentual do cabeçalho interrompe a coleta.
- A primeira execução baixa automaticamente desde 01/07/2025. Cada mês completo é salvo no cache privado; interrupção retoma dos meses restantes, sem publicar tabelas parciais. Sem falhas, atualiza os últimos sete dias. Se a rotina ficou parada mais tempo, busca também a lacuna. A reconstrução manual guarda progresso separado até terminar, preservando o cache anterior.
- O cache identifica conta/versão/atribuição por resumo criptográfico, sem guardar token nem ID da conta. Só contém métricas e identificação de campanhas. Campos de resposta fora da lista explícita são descartados.
- Confere BRL e fuso America/Sao_Paulo antes de comparar com os pedidos. Consulta 30 dias por anúncio diariamente e mais um agregado de sete dias para frequência/alcance, que não são somáveis. Inclui anúncios ativos mesmo sem gasto; miniatura fica vazia quando o Meta não disponibiliza criativo.
- `orcamento_dia` e `status` são a fotografia atual da estrutura, não histórico de alterações de orçamento. Orçamento diário de conjuntos ativos é somado quando não há orçamento diário da campanha; orçamento vitalício não é dividido por dias. Nesse caso o alerta de entrega não é calculado. Conferir alterações de verba no gasto semanal, não inferir orçamento antigo.
- Semanas incluem a atual, ainda parcial; o Cowork deve identificá-la. Sem quatro semanas anteriores com ROAS calculável, leitura fica vazia. Empates também ficam vazios. Divisão por zero não vira custo ou ROAS inventado.
- `discos_voltaram` fica vazio nas semanas inteiramente anteriores a 14/10/2026. Na semana que contém essa data, conta só retornos observados de 14/10 em diante. Criação e retorno não são contados duas vezes; `discos_entraram` fica vazio quando o retorno é desconhecido. Datas de retorno vêm da fotografia atual de produtos, não de um histórico de cada movimentação de estoque.
- Alerta de evento no mesmo dia do encerramento exige gasto em uma faixa horária que começa após stop_time; a faixa que atravessa o horário de encerramento não permite afirmar quanto foi gasto depois. `data_evento` manual prevalece sobre stop_time.
- Só depois de toda a coleta e dos cálculos terem sucesso as seis abas de saída são oferecidas para gravação. Falha de coleta atualiza apenas `anuncios_resumo` com estado aviso e preserva a data da última atualização boa. Falha de gravação também não derruba a rotina; a próxima rodada tenta novamente. Data `desde` é mantida para alertas que continuam abertos.
- Dez parâmetros são acrescentados no fim da Configuração, com ajuda na coluna C; valores existentes não são sobrescritos. `anuncios_notas` e `anuncios_direcao` só são criadas com cabeçalho. A rotina nunca escreve em suas linhas.
- Testes locais usam sessões e dados fictícios. Não foi consultada a conta real do Meta neste computador; validação real deve ocorrer no Actions. A comparação mensal automatizada usa a mesma atribuição de `meta_do_mes`, sem somar omni_purchase e sem incluir imposto na comparação do investimento nominal.

### Baixar o histórico pelo GitHub Actions

1. Abrir o repositório privado e clicar em **Actions**.
2. Escolher **Rotina do Painel** e clicar em **Run workflow**.
3. Manter a branch **main**. Para forçar a reconstrução, marcar **Rebaixar histórico de anúncios do Meta desde julho/2025 (na primeira vez é automático)**. Deixar a opção de baixar a Nuvemshop desmarcada.
4. Clicar no botão verde **Run workflow** e abrir a execução. Conferir o passo **Rodar a rotina (coletor, motor, planilha)**.
5. Na planilha, conferir `anuncios_resumo`: estado `ok`, data atualizada, última data e dias no histórico. Se estiver `aviso`, ler a explicação; as demais abas mantêm os dados anteriores. Se o limite de uso interromper um backfill, repetir a mesma execução depois que o limite baixar; meses já completos são reaproveitados. Depois de concluir, manter a opção desmarcada nas execuções normais.

Comando equivalente: `python -m painel_monstro.rotina --anuncios-historico`.
Não precisa alterar Apps Script, criar outro token ou adicionar Secrets novos. As credenciais já existentes continuam apenas no ambiente/Secrets.

### Referências oficiais conferidas

- [Insights API](https://developers.facebook.com/docs/marketing-api/insights/) e [limites de uso](https://developers.facebook.com/docs/marketing-api/overview/rate-limiting/).
- Os endereços da documentação devolveram HTTP 429 nesta consulta. Os campos/parâmetros foram conferidos também no [SDK oficial de Meta, AdAccount](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/adaccount.py), [AdsInsights](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/adsinsights.py) e [AdCreative](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/adcreative.py). Validação contra a versão configurada da conta fica para o Actions.
