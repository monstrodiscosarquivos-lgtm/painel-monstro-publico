# Frete e desconto no carrinho

## Sequência D-056, aprovada em 13/10/2026

1. Após 12 horas: lembrete sem benefício.
2. Após intervalo configurado, se não comprou: pelo menos R$200 em produtos após desconto, sem frete. Cotar opções do carrinho pela API. Entrega mais barata até R$30 oferece frete grátis nessa modalidade. Sem cotação elegível, antecipa os 10% para usados e lacrados conforme D-058, respeitando regras VIP. Abaixo de R$200: mensagem sem benefício.
3. Se recebeu frete no segundo e não comprou, oferece 10%. Se já recebeu os 10% no segundo, ciclo encerra sem repetir oferta final.

Toques são mensagens realmente enviadas. Antecipar oferta não soma terceiro toque fictício. Recuperação continua medida por compra válida do mesmo email/telefone até sete dias do primeiro envio.

## Fonte de cotação

GET https://api.nuvemshop.com.br/unstable/{store}/carts/{id}/shipping/quotations, permissão read_shipping_quotation. Usa destino e produtos do carrinho; não muda endereço nem modalidade. Só ship em BRL, ignorando pickup. Assigned_token não é guardado nem impresso; não fazemos PUT. Cotação indisponível, moeda desconhecida ou envio já gratuito não liberam novo benefício de frete.

O dado é preço cotado ao cliente, conforme esclarecimento do Túlio. Não é o custo final da etiqueta. Cotação varia se cliente alterar endereço ou produtos. O cupom deve estar configurado para a modalidade econômica; a decisão na mensagem não é uma trava do cupom no checkout.

Configuração: mínimo frete = 200; mínimo cupom = 200; teto cotação = 30. A linha antiga Limite do frete garantido no checkout? permanece por compatibilidade, sem efeito desde D-056.

As notas anteriores D-055 de frete suspenso por falta de custo da loja foram substituídas para decidir mensagens. Nenhuma mudança em cupons ou na régua de email foi feita.

Documentação oficial: https://nuvemshop.dev/en-US/api/resources/unstable/cart

## Cupom geral D-059

Túlio ampliou VOLTA10OUT para toda a loja. Consulta GET confirmou VOLTA10OUT e VOLTAFRETEOUT válidos sem restrição de categorias/produtos. Inclui consignados; mínimos e teto da cotação permanecem. Texto da Mensagens e Oferta da Régua atualizados, sem disparar mensagens ou alterar automações Brevo.

Confirmação D-058 (13/10/2026): mesmo VOLTA10<MÊS> no carrinho e email, usados e lacrados, sem cupom separado. VOLTA10OUT sem teto em reais. R$30 limita só cotação de frete no carrinho. Consignados não existem no site; excluir apenas por proteção.
