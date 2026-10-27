# Custos: fontes automáticas e preenchimento manual

Implementado em 12/10/2026 (D-046). A rotina consulta o mês anterior uma vez por dia, guarda os meses anteriores no cache privado `dados/api/custos_automaticos.json` e publica a aba `custos_automaticos`. Ela combina essas fontes com `custos` sem escrever nos lançamentos manuais, que têm prioridade. Para usar o automático, deixe a respectiva célula manual vazia.

Você informa mensalidade do Brevo, margens de usados/lacrados e embalagem por pedido. Frete e dados Meta continuam manuais enquanto os acessos abaixo não forem configurados.

| Coluna | Fonte e situação |
|---|---|
| mes | Pode ser gerado pelo coletor mensal; no preenchimento manual usar AAAA-MM. |
| investimento_meta | Automatizável pela API de Insights do Meta, campo spend. Falta configurar acesso de leitura à conta de anúncios. |
| compras_meta | Automatizável pelas ações de compra do Meta. Confirmar evento e janela de atribuição iguais aos do Gerenciador; não somar categorias sobrepostas. |
| receita_meta | Automatizável pelos valores das ações de compra do Meta; confirmar moeda e mesma janela de atribuição. |
| custo_brevo | Manual: GET /account informa plano e créditos, mas não retornou valor cobrado. Informar a cobrança real em reais. |
| receita_brevo | Integrada à rotina: GET /ecommerce/attribution/metrics com período do mês anterior; total agregado oficial, incluindo campanhas e automações, sem somar relatórios separados. |
| margem_usados | Manual, percentual. |
| margem_lacrados | Manual, percentual. |
| embalagem | Manual, custo médio por pedido em reais. |
| frete_pago_loja | Código pronto; falta permissão read_fulfillment_orders. O dono confirmou que clientes cobrem o frete normal; soma custo das entregas gratuitas em pedidos pagos não cancelados, exclui retirada. Custo ausente, moeda desconhecida ou custo de entrega zero exigem conferência manual. |

## Brevo: resultado da consulta

Uma consulta de outubro à campanha mostrada pelo Túlio retornou receita de R$ 1.534,60, 8 pedidos e carrinho médio de R$ 191,825, iguais à captura. Somente GET foi usado; nada foi alterado no Brevo.

A consulta de setembro sem filtro de campanha retornou results vazio e totais zero: é zero de receita atribuída no relatório, não zero de vendas da loja nem prova de ausência de influência dos emails. A consulta com e sem filtro da campanha de outubro retornou o mesmo total. A moeda de exibição do Brevo veio vazia; a loja usa BRL nos pedidos, e o valor foi conferido contra a interface. Não converter valores silenciosamente.

A integração usa o total atribuído ao período pela API, sem restringir a campanhas enviadas naquele mês. Não duplica pedidos somando campanhas. Resposta sem total válido vira pendência, não zero. Os testes conferem que a receita aparece mesmo sem Meta configurado. A leitura Meta usa nível da conta, BRL, janela de atribuição da conta e data da conversão; considera apenas offsite_conversion.fb_pixel_purchase, sem somar purchase/omni_purchase sobrepostos.

## Preservação da planilha

`custos` pertence ao Túlio e não é sobrescrita (AGENTS.md, D-043). A aba separada `custos_automaticos` tem mes, fonte, campo, valor, estado, atualizado_em e observacao. `ok` é valor validado; `pendente` não é zero. Falhas de frete sem valor manual deixam indicadores dependentes vazios. Os cabeçalhos e ordem das abas existentes foram preservados. A criação real dessa aba foi conferida e a aba manual ficou idêntica.

## Acessos que faltam

Conclusão em 12/10/2026: Meta também configurado e validado ao vivo. Token SYSTEM_USER com ads_read, válido e sem vencimento programado (expires_at=0 e data_access_expires_at=0); valores de setembro conferidos novamente. O Túlio confirmou substituição no .env e Secrets. Não há acesso pendente; falta conferir a próxima execução do Actions. Os itens abaixo preservam o procedimento de configuração.

Atualização de 12/10/2026: permissão Nuvemshop liberada, frete validado ao vivo e aba atualizada. Setembro: 5 entregas gratuitas totalizando R$188,96, excluindo 3 retiradas. O bloqueio Nuvemshop descrito abaixo foi resolvido; permanece somente o acesso Meta.

- Nuvemshop: GET /orders/{order_id}/fulfillment-orders devolveu 403 Missing required scope: read_fulfillment_orders. Acrescentar somente leitura de entregas ao aplicativo sob medida e reautorizar conforme o fluxo da Nuvemshop. Se gerar token novo, atualizar NUVEMSHOP_TOKEN no .env e nos Secrets do GitHub. O esquema do endpoint foi testado com exemplos oficiais, mas o acesso completo na conta continua bloqueado.
- Meta: configurar META_ADS_ACCOUNT_ID e META_ADS_TOKEN com ads_read no .env e nos Secrets do GitHub. Em Settings > Secrets and variables > Actions > New repository secret, criar cada nome. Não colar token na conversa. Versão ajustável por META_ADS_API_VERSION (padrão v24.0). A integração ainda não foi validada ao vivo por falta desse acesso; nenhuma operação escreve em anúncios.

As consultas bem-sucedidas são reutilizadas no mesmo dia; fontes pendentes tentam de novo na próxima rodada. O código fica pronto para funcionar após liberar os acessos.

Fontes oficiais:
- [Brevo: receita atribuída por período](https://developers.brevo.com/reference/get-attribution-metrics-for-one-or-more-brevo-campaigns-or-workflows)
- [Nuvemshop: detalhes das entregas](https://nuvemshop.dev/en-US/api/resources/2025-03/fulfillment-order)
- [Brevo: endpoints de eCommerce e atribuição](https://github.com/getbrevo/brevo-go/blob/main/docs/EcommerceApi.md)
- [Brevo: informações da conta](https://developers.brevo.com/reference/get-account)
- [Meta: exemplo oficial de relatórios](https://github.com/fbsamples/marketing-api-samples/blob/master/samples/samplecode/ads_reporting.py)
