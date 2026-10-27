# Painel Monstro · instruções para agentes

Este arquivo vale para qualquer agente de programação (Claude Code, Codex ou outro). O `CLAUDE.md` só aponta para cá. Mantenha tudo o que é regra do projeto aqui, num lugar só.

Painel de LTV e automação de relacionamento da Monstro Discos (loja de discos e selo em Goiânia, loja online em lojamonstro.com.br na Nuvemshop, plano Escala).

## Quem usa e como falar com ele

- O dono do projeto é o Túlio, responsável pelo marketing da loja. **Ele não é programador.**
- Explique tudo em português simples, sem jargão. Quando precisar de uma ação dele (clicar em algo, criar uma conta, colar uma chave), dê o passo a passo com os nomes exatos dos botões.
- Antes de qualquer ação que não tem volta (apagar dados, alterar contatos no Brevo, publicar no GitHub), explique o que vai acontecer e peça confirmação.
- Ao terminar cada etapa, diga em 3 a 5 linhas o que foi feito e como ele pode conferir que funcionou.
- Em textos para o usuário final (emails, painel), não use travessão no meio de frases.

## Objetivo do painel

Fazer a receita de quem volta a comprar sair de 25% para 35% da receita da loja online em 12 meses (de cerca de R$6,3 mil para R$9 mil por mês), sem o custo total de marketing passar de 15% da receita.

Receita de quem volta = clientes que compraram nos últimos 12 meses × taxa de volta por mês × gasto por recompra. Referência de outubro/2026: 1.058 clientes × 2,2% × R$267.

## Arquitetura (sem servidor, custo zero)

- **Código:** Python 3.12; migração para repositório público novo preparada em D-079, ainda sem publicação. O antigo continua privado como backup.
- **Rotina:** GitHub Actions agendado de hora em hora (cron). Sem webhooks.
- **Banco de dados:** uma Planilha Google privada, uma aba por tabela, acessada com conta de serviço do Google (biblioteca gspread).
- **Painel:** uma página no claude.ai (montada no Cowork) que lê as abas da Planilha Google. O Looker Studio foi abandonado (D-043).
- **Fontes:** API da Nuvemshop (aplicativo sob medida, só leitura) ou, como alternativa, as planilhas exportadas da Nuvemshop colocadas em `dados/entrada/`.
- **Saídas:** Brevo (API v3), lista de garimpo (alertas), públicos para o Meta (CSV).

## Estrutura de pastas

```
painel_monstro/        código
  coletor/             nuvemshop_api.py, planilhas_csv.py
  motor/               regua.py, indicadores.py, raspadinha.py
  saidas/              planilha_google.py, brevo.py, garimpo.py, meta.py, carrinhos.py, raspadinha.py
  config.py            lê o .env e os segredos
tests/                 testes com dados de exemplo anonimizados
referencia/            reativacao.py (versão atual da régua, roda com CSV)
dados/                 dados reais, NUNCA vão para o git
credenciais/           chaves, NUNCA vão para o git
raspadinha_pagina/     página pública da raspadinha (GitHub Pages, repositório separado); sem dado de cliente
.github/workflows/     rotina.yml
```

## Segurança e privacidade (regras fixas)

- Tokens e chaves só no `.env` local e nos Secrets do GitHub. Nunca no código, nunca em commit, nunca impressos no terminal.
- Dados de clientes (nome, email, telefone, endereço) nunca vão para o repositório. Testes usam dados fictícios.
- A integração com a Nuvemshop é só leitura. **Exceção D-062:** a raspadinha cria cupons (`POST /coupons`), e só com a aba `Raspadinha` em Modo = Real e o comando `--criar-cupons`, rodado com o Túlio acompanhando.
- Tudo que escreve no Brevo começa em modo teste (`BREVO_MODO_TESTE=sim`): só mostra o que faria. **Nunca desligue o modo teste, nem proponha a mudança, sem o Túlio escrever exatamente "pode desligar o modo teste".** O painel nunca dispara email diretamente; ele atualiza atributos e listas, e as automações do Brevo enviam.
- Respeitar quem não aceita marketing (campo Marketing = "Não aceita" na Nuvemshop) e quem se descadastrou no Brevo.

## Notas das APIs (confira sempre na documentação oficial antes de implementar)

- **Nuvemshop:** base `https://api.nuvemshop.com.br/2025-03/2399989/` (a documentação atual usa versão no endereço; a `v1` ainda responde). Cabeçalhos `Authorization: Bearer <token>` (conferido em 07/10/2026; o antigo `Authentication: bearer` não é mais o documentado) e `User-Agent` com nome do app e email. Paginação com `per_page` (até 200) seguindo o cabeçalho `Link`. Limite: balde de 40 requisições que esvazia 2 por segundo (cabeçalhos `x-rate-limit-*`). Resposta 404 numa lista quer dizer "nada encontrado". Uma consulta entrega no máximo 10.000 registros. O pedido não traz o valor do frete: calcular por total − subtotal + desconto. Recursos usados: orders, customers, products. Buscar só o que mudou desde a última execução (`updated_at_min`).
- **Brevo:** API v3, cabeçalho `api-key`. Contatos, atributos e listas. Atributo de primeiro nome: `FIRSTNAME` (conferido em 10/10/2026; `NOME` não existe). Plano Starter: automação para até 2.000 contatos. O Brevo desativa a chave depois de 90 dias sem chamada bem-sucedida: a rotina lê a conta a cada rodada. O Túlio desativou o bloqueio de IP das chaves de API (o GitHub roda de IPs que mudam). Guia da régua: `docs/BREVO.md`.
- **Google Sheets:** conta de serviço com acesso de Editor à planilha. Limite de 10 milhões de células.

## Regras de negócio

### Dados e contas
- Pedido válido: status de pagamento "Confirmado" ou "Parcialmente estornado", e pedido não cancelado (pago e depois cancelado não conta como compra em nenhum indicador nem na régua; D-028). Na exportação CSV, cada linha é um item; os campos do pedido se repetem por número do pedido.
- Custo de cada venda digital: 10% de remuneração de marketing + taxas de pagamento (média 2,1%) + frete pago pela loja + desconto + custo do disco (campo Custo do produto ou margem média por tipo, informada na aba `custos`).
- Etiqueta prata = disco consignado: só existe na loja física; manter exclusão defensiva de benefícios no motor.

### Régua mensal (dias desde a última compra)
| Etapa | Janela | Oferta |
|---|---|---|
| 0 · Pós-compra | 15 a 44 dias, só quem tem 1 compra | Obrigado + novidades do gênero, sem desconto |
| 1 · Lembrete | 45 a 74 dias | Novidades + "o que você está caçando?", sem desconto |
| VIP · WhatsApp | 75 a 104 dias, VIP = 3+ compras ou R$1.000+ gastos | Mensagem pessoal, sem cupom |
| 2 · Convite | 90 a 119 dias | Frete grátis acima de R$150 por 10 dias (VOLTAFRETE<MÊS>) |
| 3 · Última chamada | 180 a 209 dias | 10% por 7 dias, em toda a loja (VOLTA10<MÊS>) |
| Descanso | 210+ dias | Só newsletter e datas grandes |

- 10% de cada etapa vai para o grupo de controle e não recebe nada. O sorteio usa semente fixa por mês para ser reproduzível.
- Comprou, o relógio zera. Máximo de um benefício a cada 90 dias por cliente. Teto de R$30 de custo por pedido recuperado.
- Resultado de cada etapa = taxa de compra em 30 dias de quem recebeu menos a do controle.
- Implementação de referência: `referencia/reativacao.py`. A versão nova deve dar os mesmos números com os mesmos arquivos.

### Carrinho abandonado
- **Tudo é configurável pelo Túlio, sem mexer no código.** O modelo da ferramenta é `dados/referencia-privada/Carrinhos-Monstro-ferramenta.xlsx`. Na Planilha Google do Painel, criar as abas com a mesma estrutura: `Configuração` (parâmetros e valores), `Mensagens` (modelos com marcadores), `Fila`, `Bloqueio` e `Resultados`. O código lê os parâmetros e os modelos dessas abas a cada execução; os valores abaixo são só o padrão inicial.
- Fonte: API da Nuvemshop, `GET /checkouts` (lista) e `GET /checkouts/{id}`. Exige permissão de leitura de pedidos. Traz contato, itens, valor e `abandoned_checkout_url`. Só aparecem carrinhos que chegaram à segunda etapa do checkout; a API guarda 30 dias. Não há webhook: buscar de hora em hora na rotina.
- O email automático de carrinho da Nuvemshop já está ativo e sai 6 horas depois. O Painel não mexe nele.
- Entra na fila: carrinho entre "Começar a contatar depois de (horas)" e "Parar de contatar depois de (dias)"; sem pedido pago do mesmo email ou telefone depois do carrinho; um por cliente (o mais recente); fora quem está na aba `Bloqueio`; acima do valor mínimo, se houver.
- Estoque: conferir cada item na API de produtos na hora de montar a fila e de novo logo antes de mandar a fila por email. Gravar o horário da conferência. Se algum item esgotou, Estoque = Parcial ou Esgotado, o modelo vira ESGOTADO e a mensagem não leva o link do carrinho.
- Escolha do modelo pelo próximo toque: 1 = T1 (ou T1_UNICO se todos os itens são usados de exemplar único, ou T1_RECORRENTE se o cliente já comprou antes); 2 = T2_FRETE se o valor passa do mínimo de frete grátis, senão T2_ESCASSEZ; 3 = T3_CUPOM se passa do mínimo de cupom, senão T2_ESCASSEZ. VIP e cliente frequente nunca recebem modelo com cupom. Máximo de toques e intervalo entre eles vêm da aba `Configuração`.
- D-055 (somente carrinho): segundo toque oferece frete grátis apenas com pelo menos R$200 de produtos após desconto, sem frete, e custo da loja confirmado em BRL maior que zero e até R$30. Parâmetros Custo máximo do frete grátis (R$) e Limite do frete garantido no checkout? ficam no fim da Configuração. Custo ausente, inválido, retirada ou garantia do checkout Não: mensagem sem benefício, nunca estimar pelo frete cobrado do cliente. Escolha manual de modelo não contorna. A garantia começa Não porque o cupom nativo de frete grátis não tem teto em reais; liberar exige solução validada no checkout. Terceiro toque mantém 10% com as regras existentes.
- D-056 substitui D-055 para mensagens: cotar por GET /unstable/{store}/carts/{id}/shipping/quotations com read_shipping_quotation. Só opções ship BRL, ignorar retirada; não guardar JWT assigned_token nem usar PUT. T2: R$200 em produtos após desconto e entrega mais barata cotada positiva até R$30 oferece frete grátis nessa modalidade; caso contrário antecipa T3_CUPOM se R$200 e restrições atuais permitirem. Abaixo do mínimo: sem benefício. T3_CUPOM enviado encerra o ciclo, mesmo quando foi apenas o segundo envio; nunca inventar toque. Recuperação continua detectada. A chave antiga de garantia do checkout é legado e não bloqueia mensagem; preço cotado não é custo final de etiqueta nem trava de cupom no checkout.
- D-059: Túlio confirmou ofertas de 10% e frete para toda a loja, inclusive consignados, e escolheu ampliar VOLTA10OUT existente. Cupons VOLTA10OUT e VOLTAFRETEOUT conferidos válidos sem restrição de categorias/produtos. Carrinho mantém R$200, cotação até R$30, regras VIP e registro real. Substitui restrições de produto anteriores; não habilita Brevo nem envia mensagens.
- Registro histórico D-058 (superado por D-059): Túlio confirmou que 10% e frete são gerais para usados e lacrados. Substitui exclusividade de usados da D-057 apenas no carrinho; consignados de etiqueta prata continuam fora de qualquer benefício. Mensagem T3 diz 10% nos discos. Mínimos R$200, teto da cotação R$30, regras VIP e medição real ficam como estão. Regra de email não foi alterada. Cupom precisa permitir essa abrangência; consulta de 13/10 mostrou VOLTA10OUT ainda limitado a categorias usadas, aguardando definição de cupom próprio ou ampliação.
- Marcadores aceitos nos modelos: {nome}, {itens}, {valor}, {link_carrinho}, {cupom}, {prazo}, {assinatura}, {loja}. Marcador desconhecido: deixar como está e avisar na coluna Observações.
- Link do WhatsApp: `https://wa.me/<telefone só com dígitos, com 55>?text=<mensagem codificada>`. Se a coluna "Mensagem editada" tiver texto, ele substitui a mensagem pronta. Telefone inválido: marcar na linha e não gerar link.
- Colunas de entrada da fila são preenchidas pelo Painel; Toques já enviados, Último envio em, Status, Modelo escolhido e Mensagem editada pertencem à Mariana e nunca são sobrescritas pelo código.
- Exceção autorizada em D-047: o Apps Script registra Último envio em ao aumentar manualmente Toques já enviados, uma célula por vez. Não altera data ao diminuir, apagar ou repetir o contador. Colagens de várias células não registram data automaticamente. Horário é o da marcação na planilha, não confirmação do WhatsApp; o Python continua preservando as colunas manuais.
- D-049: o fluxo normal é marcar a caixa Enviei agora, acrescentada no fim da Fila. O Apps Script registra contador, data/hora e status numa operação, desmarca a caixa e muda Situação para Envio registrado até a rotina recalcular. Mantém Respondeu quando já marcado, recusa inválidos/recusas/recuperados e linhas fora de Contatar, usa trava para não duplicar evento. Python nunca altera a caixa nem o histórico manual. Trocar apenas status não registra envio. Guia em docs/COMO_MARCAR_ENVIOS.md.
- D-050: não mover colunas da Fila. Python verifica os cabeçalhos e interrompe se diferirem do modelo. Usar ocultação/visualizações de filtro, com contador e data visíveis. Não zerar registros reais para testar; caixas vazias não significam envio pendente. Preferência de congelar colunas é preservada pela formatação.
- D-053: Status Respondeu com 0 toques não vira envio inferido; a trava de 30 dias passa a valer a partir do dia em que o Painel viu a resposta (aba `respostas_vistas`).
- D-051: visualizações pessoais Para enviar, Acompanhar respostas e Histórico e busca na Fila, acessíveis pelo menu Fila Monstro. Ações Respondeu agora, Contato inválido agora e Não quer agora no fim atualizam Status/Situação e desmarcam sem contar envio. Respondeu suspende próximos toques do ciclo; recuperação automática tem prioridade. Não usar Recuperado manualmente no fluxo normal.
- O envio do WhatsApp é sempre manual (Mariana). Nunca automatizar envio de WhatsApp.
- D-048: número inexistente no WhatsApp recebe Status Contato inválido, sem incrementar toques. A linha vira Encerrado: contato inválido, sem link; o telefone é excluído das tentativas de todas as origens enquanto houver esse status. Não grava recusa em Bloqueio nem altera consentimento/email no Brevo. Corrigido o telefone, revisar o status para retomar. Se já houve envio real antes, o histórico de toques é preservado.
- A fila do dia vai por email nos horários da aba `Configuração` (padrão 10h e 17h), só com as linhas em situação "Contatar".
- Recuperado = pedido pago do mesmo email ou telefone em até 7 dias depois do primeiro toque. Registrar receita, cupom usado e o modelo de cada envio, para comparar os modelos.
- Fase futura (só com aprovação do Túlio): aplicar cupom direto no carrinho com `POST /checkouts/{cart_id}/coupon`, que exige permissão de escrita em pedidos.

### Famílias de gênero
Rock e Prog, Brasil, Metal, Groove (soul, funk, jazz, blues, rap). Definidas pelas categorias do produto e, na falta, por palavras-chave de artistas (ver `referencia/reativacao.py`).

### Indicadores do painel
Receita de quem volta por mês; clientes novos que voltam em 90 dias; LTV de 12 meses por coorte; CPA do Meta; custo real por cliente novo (investimento ÷ clientes novos); ROAS do Meta; ROAS geral (receita total ÷ mídia total); LTV ÷ custo por cliente novo; margem bruta; custo total de marketing ÷ receita; descontos e fretes pagos ÷ receita; vendas atribuídas por envio (Brevo); incremento de cada etapa da régua; abertura, emails inválidos e descadastros; garimpo (pedidos, avisos, vendas por aviso); carrinhos (por dia, valor abandonado, contatados, taxa de recuperação por toque e por oferta, receita recuperada, custo dos cupons). Cada indicador tem um alerta configurável na aba `alertas`.

### Abas da planilha
clientes, pedidos, itens, produtos (com data em que entrou ou voltou ao estoque), regua, carrinhos, bloqueio, desejos, custos (preenchida pelo Túlio, uma linha por mês, colunas `mes` (AAAA-MM), `investimento_meta`, `compras_meta`, `receita_meta`, `custo_brevo`, `receita_brevo`, `margem_usados`, `margem_lacrados`, `embalagem`, `frete_pago_loja`; ver D-026), indicadores, alertas.

## Como trabalhar neste projeto

- Uma etapa por vez, na ordem do arquivo `PROMPTS.md`. Não adiantar etapas.
- Siga o protocolo de passagem de bastão abaixo em toda sessão.
- Escrever testes para o motor da régua e para os indicadores.
- Fazer commits pequenos com mensagem em português.
- Se algo depender de uma decisão de negócio que não está aqui, perguntar ao Túlio em vez de supor.

## Protocolo de passagem de bastão (obrigatório)

O projeto pode ser continuado por outro agente a qualquer momento. Por isso, a memória do projeto fica nos arquivos, nunca só na conversa.

**Ao começar uma sessão:**
1. Leia este arquivo inteiro.
2. Leia `docs/ESTADO.md` (onde o projeto está agora) e as 3 últimas entradas de `docs/HISTORICO.md`.
3. Leia `docs/DECISOES.md` antes de mudar qualquer regra de negócio ou de arquitetura.
4. Rode os testes e confirme que está tudo verde antes de mexer em código.
5. Diga ao Túlio, em 3 linhas, em que ponto o projeto está e o que você vai fazer.

**Ao terminar uma sessão (mesmo se parar no meio de uma etapa):**
1. Atualize `docs/ESTADO.md`: etapa atual, o que está funcionando, o que está pela metade, próximo passo exato e pendências do Túlio.
2. Acrescente uma entrada no topo de `docs/HISTORICO.md`: data, agente usado, o que foi feito, arquivos alterados, como conferir e problemas conhecidos.
3. Se alguma decisão foi tomada (com ou sem o Túlio), registre em `docs/DECISOES.md` com número, data, decisão e motivo.
4. Faça commit com mensagem em português começando pela etapa, por exemplo `etapa 2: coletor da API com paginação`.

Nunca registre chaves, tokens ou dados de clientes nesses arquivos.

## Fila única de WhatsApp e medição (decidido em 2026-10-07)

Mapa visual com todas as decisões: artifact "Mapa do Painel Monstro" (claude.ai). Decisões D-014 a D-021 em docs/DECISOES.md.

- **Uma fila só.** Carrinho, alerta de garimpo, VIP aos 75 dias e garimpo aos 45 dias caem na mesma aba `Fila`, com a coluna `Origem`. Ordem de prioridade e limite diário vêm da aba `Configuração` (padrão: Carrinho, Garimpo, VIP, 45 dias; 40 mensagens por dia). O que passar do limite fica para o dia seguinte, começando pela menor prioridade.
- **1 WhatsApp a cada 30 dias por pessoa.** Carrinho e alerta de garimpo passam por cima do limite (o cliente puxou o assunto), mas contam para ele: quem recebeu carrinho não recebe o de 45 dias no mesmo mês. Bloqueio e "Não aceita" valem para todas as origens. Estoque conferido antes de cada linha.
- **Garimpo aos 45 dias.** Sem cupom. Cita o último disco comprado, sugere 1 disco em estoque da família de gênero e pergunta o que a pessoa procura. Respostas vão para a aba `desejos`.
- **Teste do WhatsApp de 45 dias (12/10/2026 a 18/01/2027).** Sorteio de quem completa 45 dias: 10% controle geral (nada além da newsletter), 30% sem WhatsApp, 60% com WhatsApp. Emails da régua iguais para os dois últimos grupos. Guardar o grupo de cada cliente na aba `regua`. Depois do teste (D-022): se aprovado, todos recebem WhatsApp menos o controle fixo de 10%; os percentuais ficam na aba `Configuração`, editáveis.
- **Carrinho com grupo de comparação.** Um percentual sorteado (padrão 10%, aba `Configuração`) recebe só o email da Nuvemshop, para medir quanto o WhatsApp recupera a mais. Depois de 3 meses, cair para 5% (D-022).
- **Cupom do 3º toque.** A regra de valor mínimo já vale como aprovação. Se o parâmetro "Cupom precisa de aprovação do Léo?" estiver em Sim, a linha fica em "Aguardar aprovação".
- **Destinatários da fila** (10h e 17h) vêm da aba `Configuração`. Nunca escrever emails de pessoas no código.
- **Régua editável.** As janelas (15, 45, 75, 90, 180, 210 dias), critérios de VIP, ofertas e cupons da régua também ficam numa aba `Régua`, lida a cada execução, como no carrinho.
- **Página "Vale a pena?" no painel.** Para cada ação (cada etapa da régua, WhatsApp de 45 dias, carrinho): receita a mais = (taxa de compra de quem recebeu menos a do grupo de comparação) × pessoas que receberam × gasto médio; menos o custo (cupons, frete pago, 10% de marketing). Mostrar só quando houver pelo menos 30 pessoas em cada grupo; antes disso, "dados insuficientes".

## Fila única: o que nunca pode travar (decidido em 2026-10-10, D-039 a D-042)

- **Nada some em silêncio.** O que não foi contatado passa para o próximo dia de fila, mais antigos primeiro dentro de cada prioridade; o excesso do limite diário também. Só sai quando não faz mais sentido (carrinho depois da janela de dias, 45 dias depois de 30 dias, VIP fora da janela) e então vira "Encerrado sem contato", conta como "Não contatados" e o cliente segue a régua.
- **Nunca avança o toque sem marcação.** Linha que estava na fila e não foi marcada volta com o aviso "Estava na fila de ontem e não foi marcada: confira no WhatsApp antes de enviar", no mesmo toque.
- **Dias da fila** (aba `Configuração`, padrão "seg a sáb"): nos outros dias não sai fila e o prazo entre toques não conta.
- **Rodada que falha não estraga nada.** O Painel calcula tudo antes de escrever; falha numa aba mantém o conteúdo antigo e a rodada seguinte recalcula. O email das 10h e das 17h que não saiu sai depois, com "(atrasada)", uma vez só. Sem rodada boa por 3 horas, o Apps Script manda alerta.
- **Contatos à mão** (aba `contatos_manuais`) valem para a trava de 30 dias. Nome de disco nas mensagens: "Álbum (Artista)".

## Raspadinha online (decidido em 2026-10-14, D-062)

Guia completo: `docs/RASPADINHA.md`. Página pública: `raspadinha_pagina/` (instruções no README da pasta).

- **O prêmio é sorteado no Painel, antes do envio, nunca na página.** A página só mostra o que veio no link do cliente.
- **Cupom único por cliente, de uso único**, só letras e números (a Nuvemshop não aceita hífen), criado pelo Painel na Nuvemshop.
  Nunca usar um código compartilhado por prêmio (quem descobrisse o código do maior prêmio usaria sem ter ganhado).
- **Tudo é configurável na aba `Raspadinha`** (prêmios, quantidades, validade, pedido mínimo, cumulativo, público, controle, trava de
  benefício, endereço da página). Linha ausente ou ilegível = padrão; Modo ilegível = Teste.
- **Regras da casa valem:** quem não aceita marketing fica de fora; trava de 1 benefício a cada 90 dias (cupom usado, Etapa 2/3 da
  régua, raspadinha anterior); 10% de grupo de controle; resultado só com 30+ pessoas por grupo.
- **Uma campanha nunca é sorteada de novo.** `--forcar` refaz só se nenhum cupom foi criado.
- **Criar cupom é ação real na loja:** exige Modo = Real na aba E `--criar-cupons`. Antes, mostrar o resumo do sorteio ao Túlio.
- **O Painel não manda email.** Gera `dados/raspadinha/<campanha>_brevo.csv` (EMAIL, FIRSTNAME, RASPA_LINK, RASPA_ATE) para o Túlio
  importar no Brevo. Isso não mexe no modo teste do Brevo (D-007).
- A rotina de hora em hora só calcula o uso dos cupons e o resultado (abas `raspadinha_envios` e `raspadinha_resultados`); sem
  campanha, não grava nada. Falha aqui nunca derruba a rodada.
- A chave que embaralha o link (`CHAVE_LINK` no motor) e a `CHAVE` do `raspadinha_pagina/index.html` têm de ser iguais; um teste confere.
  Mudar a chave quebra os links já enviados.

## Abas que o painel lê: nome e ordem das colunas são fixos (D-043)

O painel no claude.ai lê estas abas: `atual`, `mensal`, `coortes`, `regua_hoje`, `regua_resultados`, `carrinhos_dia`, `vale_a_pena`, `indicadores`, `Resultados`, `Configuração`, `Mensagens` e `custos`.

- **Nunca** renomeie essas abas nem renomeie, apague ou reordene colunas delas. Coluna nova entra só no fim; linha nova de parâmetro entra só no fim da `Configuração` e da `Mensagens`.
- Mudou algo que o painel lê ou uma regra do guia? Anote em `docs/ESTADO.md`, na seção "Avisar o Cowork", para o Túlio atualizar o painel e o guia.
- `custos` é do Túlio: mês como `2026-10` ou data; margens como `40` ou `0,4`. O Painel só lê e normaliza, nunca escreve nos dados dela.
- Custos automáticos (D-046): ficam na aba separada `custos_automaticos`; a rotina combina com `custos` sem alterar lançamentos manuais, que têm prioridade. Busca o mês anterior diariamente e guarda os anteriores no cache privado. Receita do Brevo vem de GET `/ecommerce/attribution/metrics`; Meta usa Insights só com `ads_read`. Frete grátis usa entregas em pedidos pagos não cancelados, exclui retirada e requer `read_fulfillment_orders`. Falha de consulta deixa pendência, nunca custo zero inventado. Mensalidade do Brevo, margens e embalagem continuam manuais.

## Garimpo e públicos do Meta (D-045)

- **Pedidos de disco** vêm da aba `desejos` (à mão) e da aba do Google Forms ("Respostas ao formulário 1"); o Painel reconhece as colunas pelo texto do cabeçalho (artista, disco, WhatsApp/nome, data, status). Não renomeie a aba do formulário.
- **Aviso de garimpo** = linha `ALERTA_GARIMPO` na fila única (origem Garimpo). Só vale disco que entrou na loja depois do pedido. Um pedido gera um aviso só. Nunca é enviado sozinho.
- **Públicos do Meta** (`meta_sumiu_180`, `meta_nao_abre`, `meta_compradores_180`) ficam em abas da Planilha Google privada e, se pedido, em `dados/meta/` (fora do git). Nunca commitar CSV de público nem dado de cliente.
- Só entra em público de reativação quem aceita marketing; descadastrado do Brevo nunca entra. Compradores dos últimos 180 dias vão como exclusão da prospecção (D-008).

Confirmação D-058 (13/10/2026): mesmo VOLTA10<MÊS> no carrinho e email, usados e lacrados, sem cupom separado. VOLTA10OUT sem teto em reais. R$30 limita só cotação de frete no carrinho. Consignados não existem no site; excluir apenas por proteção.


## Cadastro de discos (Etapa 10, D-067)

- Exceção adicional de escrita: `POST /products` e `POST /products/{id}/images` só para linhas `aprovado` de `cadastro_rascunhos`. Produto sempre nasce oculto (`published: false`), estoque 1 e SKU estável por ID. A chave publicar direto não contorna a trava. Nunca PUT/DELETE de produto existente neste fluxo, nem somar estoque.
- Guardar diário `cadastro_execucao` antes do POST e `produto_id` antes das imagens. Não apagar/copiar o diário para outro disco; resposta incerta exige reconciliação, nunca repetir POST às cegas. Actions já serializa as rodadas; não executar cadastro local simultaneamente.
- `cadastro_fotos` pertence ao Cowork; exceção autorizada: a rotina completa somente `arquivo_drive_id` vazio usando nome exatamente igual a `observacao`, único na entrada configurada. Ausência ou repetição bloqueia o disco com pendência; preservar IDs preenchidos e demais células. Ajustar cópias privadas em `site/<id_disco>/` da pasta pai da entrada, acessada pelo ID da Configuração; nunca depender do caminho J:. Etiqueta não sobe para a loja, originais não são alterados. Nenhum dado de cliente em `cadastro_*`.
- Discogs somente GET; `DISCOGS_TOKEN` exclusivamente no .env/Secrets, sem fotos do Discogs. Preço da etiqueta é manual, referência não substitui preço. Revisar os R$200 fictícios do piloto antes de aprovar.
- `scripts/corrigir_frete.py` é ferramenta separada, fora da rotina/Actions. NÃO executar sem autorização escrita. Aplicação exige a frase exata `pode aplicar as correções de frete`, `--aplicar` e `--autorizacao`; só peso e medidas das linhas Sim, relatório privado antes/depois. Nenhuma autorização de cadastro libera esta correção.
- Contratos e limites operacionais: `docs/CADASTRO.md` e bloco Avisar o Cowork no ESTADO. UTM não foi ligada aos pedidos por ausência dos campos na API consultada.
- A identificação de fotos novas segue `docs/CADASTRO_IA.md` (`scripts/cadastro_lote.py`, D-078).


## Migração pública preparada (D-079, 26/10/2026)

- O Túlio aceitou publicar código e documentação, mas NÃO autorizou tornar repositório público nem push nesta sessão. Publicação depende de confirmação nova. Preparar só cópia local independente com um único commit, sem .git antigo, tags, branches ou remote.
- Auditar TODOS os git ls-files, incluindo testes, docs, referência e Apps Script. Cliente real nunca é fixture. XLSX de referência fora do git, cópia apenas em dados/referencia-privada/. Relatórios com achados e endereços reais só em dados/auditoria-publica/.
- Actions público usa apenas o arquivo dados/cache-publico/api.aes256, AES-256-GCM com CACHE_KEY de 32 bytes base64 em Secret. Sem chave ou autenticação válida: nova coleta, sem fallback de texto puro. Nunca actions/cache com dados/api, nem upload-artifact de dados reais.
- Logs só de contagens e mensagens fixas. Não imprimir exceções/respostas HTTP, prévias de clientes, argumentos pessoais ou traceback. Fronteiras CLI usam log_publico. Não ativar debug HTTP ou printenv.
- Workflows só schedule, workflow_dispatch e repository_dispatch, contents: read, runner padrão. Nada de pull_request_target. Desligar Actions do antigo antes de ligar o novo; concorrência não é entre repositórios.
- Vigia lê GITHUB_REPO, GITHUB_TOKEN e PLANILHA_ID de Propriedades do script. Nunca colar emails reais, IDs internos ou segredo do Cofre no código versionado. Atualizar produção manualmente com configuração privada; não apagar Acessos nem reexecutar prepararCofre.
- Passo a passo, Secrets, permissões e limites de verificação de URLs: docs/MIGRACAO_PUBLICA.md. Nenhuma migração autoriza mudar modo do Brevo ou rodar correção de frete.
