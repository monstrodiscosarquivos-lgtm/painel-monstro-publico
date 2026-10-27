# Atualização do CRM no Cowork

Túlio usa o painel como interface de operação do CRM. Atualizar a interface e seu guia para refletir as regras atuais; a Planilha Google continua sendo a fonte dos dados. Leia AGENTS.md e as decisões D-049 a D-059 antes de alterar fluxos. Este documento não contém dados de clientes.

## Fila e acompanhamento

Três visualizações na mesma Fila:
- Para enviar: Situação = Contatar. Não listar todos com Status Em andamento como pendentes, pois eles podem já ter sido enviados.
- Acompanhar: ciclos com Toques já enviados > 0, sem Recuperado = Sim e sem Status Não quer, Contato inválido ou Recuperado. Incluir Em conversa. Busca por nome ou telefone; conferir identificação e origem.
- Histórico: todos os ciclos com Carrinho preenchido, incluindo encerrados.

Usar Carrinho como chave estável do ciclo. Origem diferencia Carrinho, Garimpo, VIP e 45 dias. Não usar nome ou posição visual como chave de escrita. Um cliente pode ter vários ciclos; não apagar os anteriores nem misturar seus contadores.

Mostrar Cliente, Telefone, Origem, Situação, Status, Toques já enviados, Último envio em, Próximo toque, Modelo usado, Cupom, Mensagem pronta, Mensagem editada e Observações. Mostrar horário da última rodada boa da aba rodada. Abrir WhatsApp não confirma envio.

## Ações humanas

Quatro ações, uma célula por vez na planilha:
- Enviei agora: Apps Script registra contador, horário e Em andamento; Situação provisória Envio registrado. Caixa volta a false. Não clicar novamente para a mesma mensagem.
- Respondeu agora: Status Respondeu, Situação Em conversa; pausa os próximos toques do ciclo, sem registrar envio. D-053 registra também trava de 30 dias para respostas com zero envios, sem inventar toque.
- Contato inválido agora: sem contar envio; preserva histórico, encerra tentativa de WhatsApp e exclui o telefone das tentativas conforme D-048.
- Não quer agora: sem contar novo envio; rotina mantém bloqueio, sem descadastrar email no Brevo.

Recuperado é automático: compra válida do mesmo email/telefone até sete dias depois do primeiro toque; exibir resultado e receita, não exigir marcação manual.

IMPORTANTE PARA A INTERFACE CRM: onEdit é gatilho de edição humana na Planilha Google. Escrever checkbox via API NÃO executa onEdit. Inspecionar a ponte de escrita atual do painel e integrar a ação a um backend autorizado que execute o registro equivalente, com trava, validação do ciclo e contador/data/status. Não implementar botão que só escreve TRUE via API e afirma sucesso. Até existir integração validada, abrir a linha da Fila para a marcação humana. Nunca colocar token, conta de serviço ou chave no frontend. Refletir leitura de confirmação após ação; desabilitar cliques enquanto processa. Não somar contador otimisticamente sem confirmação.

## Sequência do carrinho D-056

- Primeiro envio: após 12 horas, sem benefício; modelo T1, T1_UNICO ou T1_RECORRENTE.
- No segundo envio: pelo menos R$200 em produtos após desconto, sem incluir frete. Python cota entrega pela API oficial experimental, GET /carts/{id}/shipping/quotations, read_shipping_quotation. Usa a opção ship BRL mais barata, ignora retirada. Não faz PUT nem guarda assigned_token.
- Cotação positiva até R$30: T2_FRETE, frete grátis na modalidade econômica cotada.
- Sem frete elegível (caro, ausente, já gratuito ou falha): T3_CUPOM antecipado, se atingir R$200 e as restrições permitirem. D-059: os 10% valem para toda a loja, com exclusão defensiva de consignados. VOLTA10OUT e VOLTAFRETEOUT foram conferidos válidos, sem restrição de categorias ou produtos.
- Se T3_CUPOM foi enviado no segundo, ciclo encerra com DOIS envios reais. Não mostrar terceiro envio como realizado nem mandar oferta final repetida.
- Se T2_FRETE foi enviado no segundo e não houve compra/resposta/encerramento, T3_CUPOM no terceiro, respeitando regras.
- Abaixo de R$200: sem benefício. T2_LEMBRETE é mensagem neutra; T2_ESCASSEZ só quando cabe afirmar exemplar único. Estoque parcial/esgotado usa ESGOTADO e não promete link/benefício.

Mostrar rótulos humanos: Lembrete, Frete grátis, 10% nos discos (oferta final), Estoque alterado. Oferta não é número de envio: Próximo toque = 2 com Modelo usado = T3_CUPOM significa desconto antecipado no SEGUNDO envio.

Usar mensagem e link produzidos pelo Python. Não recalcular ofertas nem cotar com chave no navegador. Observações trazem cotação/antecipação. Cotação é preço ao cliente naquele momento, não custo final da etiqueta nem garantia do cupom após alteração de endereço/itens.

Configuração: Carrinho mínimo para frete grátis (R$) = 200, Carrinho mínimo para cupom de desconto (R$) = 200, Custo máximo do frete grátis (R$) = 30. Linha Limite do frete garantido no checkout? é legado D-055 e não bloqueia mensagens desde D-056. Não renomear nem reordenar as colunas das abas usadas pelo painel; novos campos só no fim.

## Outras mudanças já disponíveis

custos_automaticos é separada de custos; cálculo combina ambas e valores manuais têm prioridade. Meta e receita Brevo/frete têm fontes automáticas; mensalidade do Brevo, margens e embalagem continuam manuais. Não escrever por cima de custos.

Régua no Brevo e pausa programada estão na Configuração (D-052/D-053). Respeitar modo teste e estado de pausa; não enviar WhatsApp automaticamente nem alterar Brevo pelo frontend.

## Conferência de entrega

Validar em dados fictícios: clique de envio não duplica; resposta com zero envio não inventa toque; recusa/inválido não contam envio; recuperação automática; oferta antecipada tem dois envios; carrinho lacrado pode receber os 10% gerais; consignado fica excluído por proteção. Confirmar que operar no painel e na planilha usa o mesmo registro, sem duas bases concorrentes. Guia deve explicar onde buscar uma resposta e que a caixa desmarcar após sucesso é normal.

## Correção mais recente D-059

Ofertas de 10% e frete para toda a loja, com exclusão defensiva de consignados. Túlio ampliou o cupom existente; ambos os cupons foram conferidos em leitura, válidos e sem restrição de produtos/categorias. Mensagens e Oferta da Régua alinhadas. Brevo continua em modo teste. Atualizar textos do CRM e do guia; usar a Fila recalculada, não os links antigos do email.

Confirmação D-058 (13/10/2026): mesmo VOLTA10<MÊS> no carrinho e email, usados e lacrados, sem cupom separado. VOLTA10OUT sem teto em reais. R$30 limita só cotação de frete no carrinho. Consignados não existem no site; excluir apenas por proteção.
