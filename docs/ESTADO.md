# Estado do projeto

Atualize este arquivo ao fim de toda sessão. Ele responde a uma pergunta: onde o projeto está agora?

**Última atualização:** 27/10/2026: D-082 (escolher se o disco aparece na loja ao aprovar no Cadastro) e D-083 (excluir de uma vez na Nuvemshop os cupons cancelados da raspadinha) implementadas, `Painel.html` regerado e testes passando (717 em pytest + 42 em `apps-script/teste_local.js`). Nenhum push ou alteração em serviços externos.

## D-082 e D-083 · publicar disco ao aprovar e excluir cupons cancelados (27/10/2026)

- **D-082 (Parte 1 · publicar disco na loja ao aprovar):** coluna `publicar` adicionada ao fim de `EXTRAS` em `painel_monstro/saidas/cadastro.py` (criada sozinha por `preparar_abas`) e lida em `cadastro_rascunhos!A1:AM500` no Painel. O cartão em revisão traz a caixa **Mostrar na loja assim que for criado** marcada por padrão (com aviso amarelo ao lado quando houver pendência de exemplar repetido ou sem etiqueta de preço) e indica *vai aparecer* ou *fica oculto* nos cartões aprovados/criados. O `POST /products` continua criando oculto (`published: False`); após a última imagem confirmada, se `publicar` não for `nao`, grava `publicacao_pedida: true` no diário e chama `PUT /products/{id}` apenas com `{"published": True}`, mudando `status` para `publicado`. Se o `PUT` falhar, mantém `criado` e registra pendência sem repetir o `PUT`.
- **D-083 (Parte 2 · excluir de uma vez os cupons cancelados):** em `apps-script/raspadinha/Sorteio.gs`, `processarCancelamentos` processa também `apagar` via `apagarCupom_(codigo, id)`, conferindo que o cupom não está ativo nem usado antes de chamar `DELETE /coupons/{id}` (200/204/404 → `apagado <data>`). No Painel, a tabela de cupons da campanha ganha o botão **Excluir cupons cancelados (N)** e o botão **Excluir** individual nas linhas canceladas com confirmação, esconde os excluídos por padrão (com a caixa **Mostrar excluídos**) e preserva todas as jogadas e métricas da campanha. Cofre inalterado.

## D-080 e D-081 · pedidos fora da Nuvemshop e origens da raspadinha (27/10/2026)

- **D-081 (Parte 2 · origens da raspadinha):** coluna `origens` (R) adicionada em `rasp_campanhas` (`Sorteio.gs` e `painel-monstro.html`). `canal_(c, cp)` reconhece origens personalizadas da campanha (comparação exata `s === cod`), `email`, `instagram`, `whatsapp` (`whats|wpp|zap`), `direto` (vazio) e `outro` ("Outra origem"). `jogar_` bloqueia `whatsapp` quando fora de `canais` e nunca bloqueia origem personalizada cadastrada. O Painel adiciona a caixa WhatsApp em Canais, a seção "Outras origens desta campanha" com gerador de código, os links prontos para divulgar com botão Copiar e a reclassificação imediata das jogadas antigas gravadas como `outro`.
- **D-080 (Parte 1 · pedidos fora da Nuvemshop na comissão):** aba `pedidos_manuais` (`id, data_venda, descricao, forma_pagamento, valor_total, frete, taxa, parcelas, modo, mes_unico, cronograma, situacao, incluido_em, atualizado_em`) protegida em `SO_ESPECIAL` (`Cofre.gs`) e criada na primeira gravação. Na seção Comissão do Painel, o bloco "Pedidos fora da Nuvemshop" permite lançar, editar e cancelar (mudando `situacao` para `cancelado`) vendas feitas fora da loja, escolhendo **Por parcela** (divisão automática com resto de centavos na 1ª parcela e cronograma editável validado contra o total) ou **Mês único**. Entra em `comCalc` com rateio proporcional de frete e taxa, aparece na lista de pedidos do mês com a marca "fora da Nuvemshop", na cascata ("Pedidos fora da Nuvemshop") e nos critérios registrados, e `comMeses()` inclui meses futuros dos cronogramas ativos.

## D-079 · migração pública, estado atual

Limite de minutos do repositório privado esgotado. Preparada mudança para repositório público novo; o antigo não será convertido e seu histórico não será transferido. Guia principal: docs/MIGRACAO_PUBLICA.md. Nenhum repositório criado, nenhuma mudança de visibilidade, nenhum push, token ou Secret externo alterado. Nenhuma rodada real de loja/Brevo ou correção de frete executada.

Auditoria manual de todos os rastreados: XLSX retirado do índice e cópia privada mantida; dois contatos reais dos testes anonimizados, menções relacionadas retiradas da decisão histórica, emails pessoais do Cofre trocados por exemplos, ID da planilha/pasta removidos da fonte. Contato/endereço comerciais da loja mantidos por serem públicos institucionais. Dados/credenciais/.env e relatórios locais ignorados. Auditor automático também compara nomes completos e contatos disponíveis no cache privado; coincidência com a marca da própria loja é exceção explícita, não um cliente liberado.

Workflows rotina e cadastro agora restauram/salvam somente envelope AES-256-GCM. Falta/erro de CACHE_KEY ou arquivo adulterado gera nova coleta; nunca cache em texto puro. Logs sem prévias pessoais, respostas HTTP ou traceback bruto, com testes em sucesso/falha. Relatórios originais e lista de URLs em dados/auditoria-publica/, fora da versão pública. Não afirmar que login/ACL externos foram verificados: planilha teve falha DNS na consulta anônima, demais classificações vêm dos fontes/guias.

Próximo passo exato: após revisar e confirmar, seguir docs/MIGRACAO_PUBLICA.md para criar repositório vazio, enviar SOMENTE a cópia migracao-publica/painel-monstro-publico (um commit, sem remote até configuração), recriar Secrets/variáveis e token do vigia. Desligar Actions antigo antes de ativar o novo. O nome público é sugestão; GITHUB_REPO é configurável. Preservar integralmente a planilha, marcações humanas e configuração real do Brevo.

### Avisar o Cowork: migração pública D-079

Nenhuma aba/coluna de dados mudou. Código-fonte de Apps Script agora usa PLANILHA_ID nas propriedades e exemplos de acesso no Cofre. Os projetos já implantados NÃO foram alterados; manter valores privados e Acessos reais. Não substituir implantação por placeholders. Só o vigia precisa receber fonte/propriedades novas para apontar ao novo GitHub (GITHUB_REPO, GITHUB_TOKEN, PLANILHA_ID). Painel web saneado recebe planilha_id via resposta autorizada do Cofre/Entrada. Cache não é mais diretamente dados/api no Actions. Não repor dados pessoais em fixtures ou docs. Aplicativos e planilha continuam privados; URL do sorteio é pública por intenção.

Notas de funcionamento e pendências anteriores abaixo são históricas; referências a cache/repositório privados não substituem a D-079.

## Etapa atual

Etapas 0 a 8 prontas e no GitHub (repositório privado `monstrodiscosarquivos-lgtm/painel-monstro`, rotina de hora em hora). Em produção: carrinho (5.1), fila única de WhatsApp com teste de 45 dias a partir de 12/10/2026 (5.2), email de resumo de segunda (6), régua no Brevo em MODO REAL desde 14/10/2026 (7; `BREVO_MODO_TESTE` = nao, `brevo_plano` com modo REAL) e garimpo + públicos do Meta (8). Pendências do Túlio estão no fim deste arquivo; a etapa seguinte é só ajustar com os primeiros resultados.

## Etapa 9 · anúncios do Meta (D-066)

Implementação em `painel_monstro/saidas/anuncios.py`, integrada por `passo_anuncios` à rotina. Seis saídas agregadas com prefixo anuncios_, sem dados de clientes; duas abas de entrada pertencem ao Cowork. Token e conta vêm dos Secrets já existentes. Coleta apenas GET com ads_read, mesmo critério de atribuição dos custos automáticos. Cache privado em dados/api/anuncios_historico.json, com retomada por mês e atualização dos últimos sete dias.

Pendente: primeira execução real no Actions, pois o proxy local bloqueia Meta. Usar Actions > Rotina do Painel > Run workflow > main, marcar a opção de rebaixar o histórico de anúncios se quiser forçar. Não marcar a opção de baixar tudo da Nuvemshop. Conferir anuncios_resumo com estado ok e última data. Não precisa alterar Apps Script nem credenciais.

Correção prévia: as duas falhas antigas de raspadinha eram inferência de texto na receita com pandas 3; coluna passa a aceitar número preservando vazios e sem regravar campanha sem uso. Base original 452 passaram/2 falharam, base corrigida 454 verdes antes de implementar anúncios. Sem execução real de raspadinha ou alteração de modo do Brevo.

## Raspadinha online (D-062, 14/10/2026)

Pronta em modo teste, ainda não rodada contra a planilha e a loja reais. Pendências do Túlio, nesta ordem:
1. Publicar a página: repositório público `raspadinha` no GitHub com `raspadinha_pagina/index.html` e `cartela-fechada.jpg`, GitHub Pages ligado (passo a passo em `raspadinha_pagina/README.md`).
2. No Brevo, criar os atributos de texto `RASPA_LINK` e `RASPA_ATE`.
3. Pedir ao agente a primeira execução (`python -m painel_monstro.saidas.raspadinha`): cria as abas `Raspadinha` e `raspadinha_lista`. Preencher Campanha, Endereço da página e o público; rodar de novo e conferir o resumo.
4. Só então mudar Modo para Real e pedir `--criar-cupons`. Importar o CSV `dados/raspadinha/<campanha>_brevo.csv` numa lista do Brevo e enviar com `raspadinha_pagina/email-raspadinha.html` (trocar ENDERECO_DA_PAGINA e LINK_DO_WHATSAPP_DA_LOJA).

## O que está funcionando

- Kit inicial: AGENTS.md, CLAUDE.md, PROMPTS.md, .gitignore, env-exemplo.txt e docs/.
- Estrutura de pastas do AGENTS.md, requirements.txt e repositório git local (branch main), ainda sem GitHub (nenhum `remote`).
- `painel_monstro/rotina.py` (`python -m painel_monstro.rotina`): coletor, motor e planilha em sequência, com log só de contagens e resumo para a página da execução do GitHub. Rodada real local em 08/10/2026: 22 s, 22 indicadores (10 calculados), régua de hoje com 70+8, 89+10, 69+8, 113+12 e 8 VIP, planilha regravada sem duplicar. Se o coletor falha, nada é gravado na planilha.
- `.github/workflows/rotina.yml`: roda no minuto 7 de cada hora e à mão (Run workflow, com a opção "Baixar tudo de novo"), permissão só de leitura, uma execução por vez, limite de 20 minutos, cache privado de `dados/api` (D-031, D-032). Os testes conferem hora em hora, permissões, segredos usados e que nada imprime segredo.
- `scripts/auditar_repositorio.py`: confere arquivos atuais, todo o histórico e as mensagens de commit contra os valores reais do `.env` e da chave do Google, chaves privadas, emails, CPF, telefones e arquivos de dados. Rode antes de todo envio ao GitHub. Em 08/10/2026: limpo.
- A planilha-modelo `dados/referencia-privada/Carrinhos-Monstro-ferramenta.xlsx` no repositório tem os emails da equipe trocados por exemplos (D-033); a original está em `dados/referencia-original/` (fora do git). O histórico local foi reescrito antes do primeiro envio, então os hashes dos commits mudaram.
- `painel_monstro/coletor/planilhas_csv.py`: lê as 3 exportações de `dados/entrada/` e monta as tabelas clientes, pedidos, itens e produtos (`coletar()`). 12 testes com dados fictícios, todos verdes (`python -m pytest`).
- `scripts/comparar_referencia.py AAAA-MM`: roda a referência numa cópia em `dados/comparacao/` e mostra a comparação lado a lado. Resultado de 07/10/2026: pedidos pagos (2.724), compradores únicos (2.150) e os volumes de todas as etapas batem com a referência.
- `painel_monstro/config.py`: lê o `.env` (e as variáveis de ambiente, para os Secrets do GitHub). O token não aparece no `repr`.
- `painel_monstro/coletor/nuvemshop_api.py`: só leitura (GET). `python -m painel_monstro.coletor.nuvemshop_api` baixa tudo na primeira vez (cerca de 2 minutos, a API é lenta: ~4 s por página de 200 pedidos) e depois só o que mudou (cerca de 3 s). Guarda em `dados/api/` (fora do git), sem CPF nem endereços. Se a contagem local não bater com a da loja (registro apagado), baixa tudo de novo sozinho. `--completo` força. Monta as mesmas 4 tabelas do coletor por planilhas. 38 testes verdes no total.
- `scripts/comparar_api_csv.py`: compara a API com as exportações CSV (resultado no HISTORICO de 07/10/2026). Diferenças esperadas: a API é mais nova que a exportação (7 pedidos pagos e 11 cadastros depois de 05/10), tem 4 pedidos pagos de 2022 e 2023 (2 arquivados, 2 cancelados) que o CSV não traz, porque a exportação só leva pedidos abertos, e 1 pedido (nº 2983) que foi estornado depois da exportação.
- Observado na API e ainda não usado: `GET /checkouts` funciona com este token (61 carrinhos abandonados) para a etapa 5.1.
- `painel_monstro/motor/regua.py`: etapa e grupo (envio ou controle) de cada cliente, VIP, controle de 10% com semente do mês, limite de 1 benefício a cada 90 dias (quando se informa o histórico) e `resultado_etapas` (taxa de compra em 30 dias de quem recebeu menos a do controle). Janelas e percentuais ficam em `ParametrosRegua`, prontos para virarem a aba `Régua` (D-017). Dá exatamente os mesmos números e as mesmas pessoas da referência (`python scripts/comparar_referencia.py 2026-10` termina em "tudo bate").
- `painel_monstro/motor/indicadores.py`: receita de quem volta, taxa de volta, clientes novos que voltam em 90 dias e em 12 meses, LTV de 12 meses por coorte, margem bruta, descontos, CPA e ROAS do Meta, custo por cliente novo, custo de marketing ÷ receita, incremento por etapa. Lê a aba `custos` (colunas em D-026). O que depende de dado que ainda não existe aparece como "falta custos" ou "falta dados", nunca como zero.
- `scripts/indicadores_hoje.py`: mostra a tabela de indicadores de hoje (atualiza pela API; `--csv` usa as exportações). A aba `custos` vai vir da Planilha Google (Etapa 4); o Túlio não usa `dados/custos.csv`, o script só o lê se existir. Até lá, os indicadores de custo ficam como "falta custos".
- Pedido pago e depois cancelado não conta em lugar nenhum (D-028), nos dois coletores.
- Margem: os itens casam com o produto pelo ID (D-029). Em 08/10/2026, 4.444 de 4.525 itens pagos casam; 81 (1,8%, 1,2% da receita) não casam porque 73 produtos já saíram da loja, e esses usam a margem de usados. A exportação CSV não tem ID: nela o casamento continua pelo nome.
- Frete pago pela loja: coluna `frete_pago_loja` da aba `custos`, por mês; vazio conta como zero (D-027).
- 124 testes verdes (`python -m pytest`): janelas, VIP, controle, relógio zerado por nova compra, limite de benefício, resultado das etapas, aba custos, cancelados, casamento por ID, margem e indicadores com contas feitas à mão.
- `referencia/reativacao.py`: versão atual da régua, roda com as exportações CSV da Nuvemshop. É a referência de números para as etapas 1 e 3.

- `painel_monstro/saidas/planilha_google.py`: grava na Planilha Google com `python -m painel_monstro.saidas.planilha_google` (28 s). Primeira gravação real em 08/10/2026, lida de volta da planilha: clientes 2.838 linhas, pedidos 2.967, itens 4.967, produtos 5.438, indicadores 22, mais os cabeçalhos de `custos` (10 colunas) e `alertas` (5 colunas). Segunda rodada: mesmas linhas, sem duplicar, e `custos` e `alertas` intactas. Os indicadores já leem a aba `custos` da planilha. A aba `regua` só é gravada com `--regua AAAA-MM` (D-030). 151 testes verdes.

## Pela metade

- Fora do escopo e ainda não feito: famílias de gênero e últimos discos por cliente (usados nos emails e no garimpo), destaques em estoque por gênero, abas `carrinhos`, `bloqueio` e `desejos`, ligar o `resultado_etapas` ao histórico da aba `regua` (a leitura do histórico ainda não foi escrita).

## Atenção ao ambiente

- O projeto agora fica em `C:\Users\tulio\painel-monstro` (fora da pasta que sincroniza com a nuvem; D-034). O `.venv` foi recriado ali. Arquivos da pasta `Monstro Discos` (como as exportações da Reativacao) ficam em `C:\Users\tulio\Claude\Projects\Monstro Discos`; hoje nada no código depende deles.
- O Python 3.12 foi instalado e o `.venv` do projeto está pronto, com as bibliotecas do requirements.txt.
- O VLibras (que definia um `PYTHONPATH` global e quebrava o pip) foi removido a pedido do Túlio: programa, pasta e variável. Se o pip voltar a dar erro de `distutils`, confira se `PYTHONPATH` voltou.
- Existe uma pasta `C:\Users\tulio\.venv` criada por engano, fora do projeto. Pode ser apagada com a confirmação do Túlio.

## Próximo passo exato

**Etapa 10:** Cowork integrar Cadastro conforme bloco abaixo; Túlio conferir preços reais e prévias antes de aprovar qualquer disco. Adicionar DISCOGS_TOKEN nos Secrets para enriquecimento. Frete aguarda autorização escrita separada. **Etapa 9 (pendência anterior):** executar manualmente no Actions para carregar o histórico de anúncios e conferir anuncios_resumo. Cowork já publicou a aba Anúncios no painel e agendou a direção seg/qua/sex às 7h46, que grava em anuncios_direcao (informado pelo Túlio). O código de coleta não cria essa automação do Cowork. Referência completa em docs/ANUNCIOS.md. Notas das etapas anteriores abaixo são históricas.


D-058 confirmada pelo Túlio: todos os cupons valem para usados e lacrados em toda a loja online, tanto no carrinho quanto na régua de email. Mesmo VOLTA10<MÊS>, sem cupom separado para carrinho. VOLTA10OUT conferido em leitura: válido, 10%, sem restrição de categorias/produtos e max_discount_amount ausente (sem teto em reais, conforme correção explícita do Túlio). R$30 é somente o teto da cotação para oferecer frete no carrinho; mínimo R$200 mantido. Consignados só existem na loja física; exclusão de etiqueta prata mantida como proteção caso apareçam na fonte. Oferta da Etapa 3 e ajuda de Cupom de desconto na Configuração já atualizadas pelo Túlio.


Passagem CRM: entregar docs/PASSAGEM_COWORK_CRM.md ao Cowork para integrar visualizações, ações e ofertas. Escrita de checkbox por API não dispara onEdit; painel precisa executar registro equivalente no backend ou abrir Fila para marcação humana. Email das 17h de 13/10 tinha oito contatos e links antigos; quatro ainda pendentes na conferência, três já enviados/em conversa e um encerrado. Mensagens recalculadas sem alterar marcações. D-059 publicada: oferta geral e T2_LEMBRETE ativos para a rotina horária. Não usar os links antigos do email para ofertas corrigidas.


D-056: fonte de cotação experimental testada ao vivo com sucesso (R$36,75), usada para decidir mensagens pelo preço ao cliente. A partir de R$200: frete até R$30 no segundo envio, ou 10% antecipados se não elegível. Se os 10% forem enviados no segundo, encerra sem terceiro envio repetido; se houve frete no segundo, desconto vem no terceiro. Registro mantém número real de envios. Notas D-055 de frete suspenso estão superadas para mensagens. A chave antiga de garantia permanece como legado sem efeito. Conferir a próxima rodada e a mensagem antes de enviar manualmente; não precisa mudar Apps Script.


D-055: trava implementada e parâmetros aplicados à Configuração real. Não marcar Limite do frete garantido no checkout? como Sim sem validar mecanismo que imponha teto ao benefício e custo de entrega. Cupom nativo não permite teto em reais; custo ausente nos carrinhos consultados. Próximo passo depende de decisão do Túlio/dono sobre solução de checkout ou eventual crédito parcial, que ainda não foi autorizado. Até lá, T2 sem benefício, T1 e T3 seguem regras existentes. Publicação da trava autorizada nesta conversa.


D-051: usar Fila Monstro > Para enviar ou Acompanhar respostas, clicar Abrir no diálogo; buscar nome/telefone com Ctrl + F. Histórico e busca contém também encerrados. Menu e ações já salvos no Apps Script vinculado; não precisa colar nem executar instalar. Conferir a próxima rotina horária no GitHub e prática apenas em acontecimento real. Versões anteriores sobre filtro temporário e colagem de script estão superadas. Código publicado (571d94d) e recálculo ao vivo confirmou dados manuais preservados, zero Contatar e dois ciclos Em conversa. Túlio concluiu autorização do Google; menu abriu diálogo e link de Acompanhar respostas conferido no navegador: 17 linhas visíveis. Para enviar conferido: zero pendentes. Sem pendência de configuração para esta mudança.


Em 13/10/2026, removido filtro temporário por nomes de Cliente e aplicado Situação = Contatar na Fila real. Leitura confirmou zero pendentes naquele momento; não significa ausência de histórico. Rotina recalcula elegibilidade de hora em hora, e registros enviados continuam acessíveis removendo o filtro. Apps Script validado ao vivo em 12/10: uma marcação registrou toque, horário e Em andamento. Não marcar novamente envios já registrados.


Fila reparada em 12/10/2026 após Enviei agora ter sido movido para N: restaurada ordem canônica, dados calculados recuperados/recalculados e mensagens editadas recuperadas do backup quando substituídas por números. Os 15 envios confirmados continuam com 1 toque e data; caixas zeradas sem apagar o histórico. Recalculo deixou 2 contatos pendentes e 2 sem telefone utilizável. Fila filtrada em Contatar; contador/data/Status/link/checkbox visíveis, A:D congeladas. Criadas visualizações Já enviados, Para enviar e Contatos inválidos. Fazer prática apenas num envio real ainda pendente. D-050, 363 testes Python e 26 Apps Script.

Atualizar o Apps Script vinculado com a versão nova que registra a caixa Enviei agora (D-049). Coluna AK já criada na planilha; 15 envios confirmados corrigidos e conferidos. Até colar e salvar o script, não usar a caixa. Não precisa executar instalar/onEdit. Guia docs/COMO_MARCAR_ENVIOS.md. Status sozinho não registra envio; o fluxo anterior de aumentar contador continua só para correções.

Conferência operacional em 12/10/2026: os 16 contatos do email de hoje existem na Fila, mas todos estão sem contador de envios e sem data; 14 Em andamento, 1 inválido, 1 sem Status. Equipe deve conferir envios reais no WhatsApp antes de marcar; não reenviar só porque o contador está vazio. Alterar somente Status não aciona a data automática. Conferência foi somente leitura, sem alterar marcações.

Atualização da fila D-047 pronta e enviada como código: colar a versão de apps-script/fila-por-email.gs no Apps Script vinculado à planilha e salvar. O onEdit simples não exige executar instalar novamente. Até essa atualização, data/hora ainda são manuais. Mariana aumenta Toques já enviados imediatamente depois de enviar, uma célula por vez; Último envio em passa a ser automático. Não testar aumentando contadores de clientes reais sem envio.

Meta concluído em 12/10/2026: token substituído pelo Túlio no .env e Secrets; teste real confirmou SYSTEM_USER válido, ads_read, expires_at=0 e data_access_expires_at=0 (sem vencimento programado). Insights de setembro conferidos novamente. Brevo e frete já validados; todas as fontes automáticas configuradas. Próximo passo: conferir a próxima rodada do Actions; orientar o Cowork conforme D-046. As notas abaixo sobre token temporário e acessos faltantes estão superadas.

Meta validado ao vivo em 12/10/2026 após cadastro das credenciais: ads_read liberado, Insights de setembro lido e publicado em custos_automaticos; todas as 5 linhas automáticas com estado ok e custos manuais preservados. Token atual é USER e expira em 12/10/2026 às 13h (America/Sao_Paulo). Próximo passo prioritário: gerar token de usuário do sistema com ads_read e acesso à conta de anúncios, conferir validade e substituir nos dois locais. As notas anteriores de Meta sem acesso estão superadas.

Frete liberado e validado ao vivo em 12/10/2026: GET de fulfillment responde 200. Setembro tem 5 entregas gratuitas com custo total de R$188,96 e 3 retiradas excluídas. Aba custos_automaticos atualizada com frete ok, custos manuais intactos. Corrigida conversão da resposta HTTP para JSON. Falta configurar/localizar acesso Meta; as notas de bloqueio de frete abaixo são históricas e estão superadas.

Rechecagem de acessos em 12/10/2026 após o Túlio informar que liberou frete e já tem Meta configurado: a chave local da Nuvemshop ainda responde 403 Missing required scope: read_fulfillment_orders; META_ADS_ACCOUNT_ID e META_ADS_TOKEN continuam ausentes na configuração local. Conferir reautorização do aplicativo e atualizar token quando necessário; indicar onde o acesso Meta está configurado. Não pedir chaves na conversa.

Custos automáticos implementados: fontes combinadas com lançamentos manuais, que têm prioridade, consulta diária do mês anterior. Para frete, liberar read_fulfillment_orders no aplicativo Nuvemshop; para Meta, cadastrar META_ADS_ACCOUNT_ID e META_ADS_TOKEN com ads_read. Conferir a aba custos_automaticos. Mensalidade, margens e embalagem manuais. Os parágrafos de investigação abaixo foram superados por D-046.

Atualização da investigação de custos em 12/10/2026: encontrado e validado GET `/ecommerce/attribution/metrics`; a receita da campanha conferida coincide com a captura do Túlio. O endpoint comum de campanha não traz esse campo, mas o de atribuição traz. Viabilidade por coluna e limites em `docs/CUSTOS_AUTOMATICOS.md`. Ainda não integrado à rotina; Meta requer credenciais de leitura, receita mensal do Brevo requer conferir filtros, moeda e cobertura. Mensalidade, margens, embalagem e frete pago pela loja continuam manuais.

Automação dos custos (consulta em 12/10/2026): ainda não implementada. Consulta GET aos relatórios de três campanhas enviadas do Brevo retornou métricas de entrega, abertura e cliques, sem campo de receita. Isso não prova ausência em toda a API; falta identificar uma fonte oficial da receita exibida na interface. Meta ainda precisa de acesso de leitura à conta de anúncios, não configurado no projeto. `custos` continua manual.

Correção enviada ao GitHub. Conferir a próxima rodada em Actions > Rotina do Painel ou executar Run workflow. Quando não há histórico mensal após excluir `teste45`, `regua_resultados` agora retorna vazia com os mesmos cabeçalhos, em vez de interromper a rotina.

Etapa 7 · Régua automática no Brevo, em MODO REAL desde 14/10/2026 (o Túlio desligou o modo teste com a frase exata; a variável `BREVO_MODO_TESTE` do GitHub é `nao`). Pendente do Túlio: criar no Brevo os 5 atributos, as 4 listas e as 4 automações (passo a passo em `docs/BREVO.md`) e colar o script novo em Extensões > Apps Script. Voltar ao modo teste: pôr `BREVO_MODO_TESTE` = `sim` no GitHub. Próxima: Etapa 8 (garimpo com Google Forms e públicos do Meta).

A rodada da régua de um mês só é gravada com `--regua AAAA-MM` e não é trocada depois (D-030); a primeira rodada real fica para quando o Túlio for mandar a régua. Quem usar a aba `regua` para medir resultado ou limitar benefícios deve ler o histórico dela (colunas `mes`, `email`, `etapa`, `grupo`, `data_referencia`).

Limite conhecido: a API entrega no máximo 10.000 registros por consulta; hoje são 2.966 pedidos, então só vira problema daqui a anos (o coletor avisa com erro claro).

Para os agentes seguintes: o `AGENTS.md` diz 10% de desconto na etapa 3 e a `referencia/reativacao.py` ainda cita 15% no cabeçalho; os volumes não dependem disso, mas o texto da oferta deve seguir o AGENTS.md.

A planilha já recebe `produto_id` nos itens e `id` nos produtos (o casamento da margem depende deles, D-029).

## Avisar o Cowork

- D-071 · Lembrete da raspadinha: nova aba `rasp_lembretes` (só a rotina escreve: cupom, email, campanha, premio, valido_ate, status, quando). Status: `enviado`, `enviado · saiu da lista`, `fora: ...`. O painel lê para mostrar lembretes enviados e quantos usaram depois. Linha nova em Configuração: `Raspadinha: lembrete no Brevo (dias antes de vencer)`. Pendente do Túlio: lista, modelo e automação no Brevo (docs/RASPADINHA.md).

- D-062 · Raspadinha online: abas novas `Raspadinha` (do Túlio), `raspadinha_lista` (do Túlio), `raspadinha_envios` e `raspadinha_resultados` (do Painel). O painel ainda não lê nenhuma delas; se passar a ler, entram na lista fixa do D-043. Colunas em docs/RASPADINHA.md. Sugestão para o painel: card "Raspadinha" com, por campanha, pessoas, cupons usados, receita com cupom, desconto dado e diferença contra o controle (ou "dados insuficientes").

- D-058: no carrinho, frete e desconto abrangem usados/lacrados. Usar texto 10% nos discos e não bloquear lacrado. Etiqueta prata continua excluída. Conferir pendência do cupom e publicação no ESTADO; régua de email não mudou.


- Ler docs/PASSAGEM_COWORK_CRM.md: contrato de Fila, identidade por ciclo, ações e backend de escrita; não confundir oferta T3 com terceiro envio real. T2_LEMBRETE é modelo neutro novo no fim de Mensagens. Desconto de usados exige item elegível; categorias conflitantes com Novo/Lacrado não liberam cupom. Não renomear campos nem duplicar lógica de promoção no frontend.


- D-056: atualizar guia do carrinho para cotação ao cliente, frete até R$30 e 10% antecipados com mínimo R$200. Se a oferta final sair no segundo envio, total do ciclo é dois envios, não três. Observações mostram cotação/antecipação. Fonte experimental e preço estimado não garantem custo final ou trava do cupom no checkout.


- D-055: frete no carrinho só a partir de R$200 em produtos e custo da loja confirmado até R$30. Sem custo/proteção no checkout, segundo toque sem benefício. Não confundir com frete da Etapa 2 de email, que não foi alterada. T3 permanece 10%. Duas linhas novas no fim de Configuração.


- **D-051:** atualizar guia operacional para menu Fila Monstro, visualizações pessoais e quatro caixas de ação no fim. Respondeu pausa o ciclo, sem somar envio; Recuperado é resultado automático. Status e histórico permanecem na mesma posição. Retomada agendada, responsável e desfazer automático ainda não implementados.


- **D-050:** a Fila tem verificação de cabeçalhos para impedir gravação em colunas movidas. Na operação, manter contador/data/Status/link/checkbox visíveis e usar visualizações de filtro para enviados e pendentes. Caixa desmarcada é normal após registro. Em 12/10 foram preservados 15 envios e restaram 2 elegíveis; não registrar esses 15 novamente.

- Visualização da Fila: N:AJ ocultadas em 12/10/2026 para aproximar Status M e Enviei agora AK. Não houve reordenação. Reexibir colunas para acessar mensagens e links quando necessário.

- **D-049, 12/10/2026:** coluna nova Enviei agora no fim da Fila (AK), caixa de confirmação. Atualizar guia: um clique após envio real registra toque/data/status; respostas, recusas e inválidos continuam sendo Status. Situação provisória Envio registrado não deve aparecer como contato pendente. Próximo toque é calculado e tem aviso de proteção. 15 marcações de hoje corrigidas com horário da correção. Colunas antigas mantidas na mesma posição.

- **D-048, 12/10/2026:** opção Contato inválido já adicionada na Fila real. Mariana marca quando número não existe no WhatsApp e não aumenta toque. A próxima rotina encerra a linha e deixa de tentar o mesmo telefone; não registra recusa de marketing. Resultados ganhou contagem separada no fim. Fórmula de edição fica vazia imediatamente nesse status. Nenhuma coluna manual foi alterada. Apps Script não precisa ser atualizado por este ajuste.

- **12/10/2026, D-047:** atualizar o guia da Mariana: após envio, somar 1 em Toques já enviados, uma célula por vez; data/hora são automáticas após instalar o código atualizado. Horário é o da marcação, não confirmação do WhatsApp. Diminuir/apagar/repetir preserva a data; colagens múltiplas não registram horário. Status continua manual. Nome/ordem das colunas preservados.

- **12/10/2026:** corrigidas 32 fórmulas de Abrir com minha edição na Fila real para separador `;`, sem erros nem alteração nas colunas manuais. A rotina agora repara linhas antigas também. Guia da Mariana: após enviar, somar 1 em Toques já enviados, preencher Último envio em com data e hora e manter Status Em andamento enquanto aguarda resposta; Respondeu quando responder, Não quer quando pedir para parar. Mensagem editada serve para criar o link com o texto personalizado; abrir o link não confirma envio nem atualiza os toques. Apps Script não precisa mudar por esta correção.

- **12/10/2026, D-046:** aba nova `custos_automaticos` (mes, fonte, campo, valor, estado, atualizado_em, observacao), sem dados pessoais. Indicadores combinam manual e automático; valor manual ganha. Receita Brevo aparece mesmo sem Meta; frete automático pendente sem valor manual deixa indicadores dependentes vazios. Atualizar guia: mensalidade, margens e embalagem manuais; frete/Meta só enquanto acesso pendente. Colunas existentes preservadas.

- **12/10/2026:** corrigido o caso sem histórico mensal em `regua_resultados`; a aba fica vazia com os mesmos cabeçalhos. Não há mudança de nomes, ordem de colunas ou regras do guia.

Mudanças de 10/10/2026 (Etapa 5.2) que afetam o painel ou o guia. Colunas novas sempre no fim; nenhum nome ou ordem de coluna das abas do painel foi alterado.

- **(Etapa 6, 10/10/2026) O Looker saiu:** o painel é uma página no claude.ai. `docs/LOOKER.md` foi apagado; o guia e o `PROMPTS.md` ainda falam em Looker Studio e devem ser atualizados.
- **`custos`:** passa a aceitar o mês como `2026-10`, data (`01/10/2026`, `2026-10-01`, `out/2026`) ou célula de data; margens como `40`, `40%` ou `0,4`.
- **Aba nova `resumo_email`** (assunto, html, gerado_em; uma linha) e **linha nova "Emails do resumo"** no fim da `Configuração`. O email de resumo sai toda segunda às 8h.
- **Abas protegidas** (nome e ordem das colunas): regra registrada no `AGENTS.md`; coluna nova só no fim.
- **(Etapa 7, 10/10/2026; modo real desde 14/10/2026) Brevo:** abas novas `brevo_plano` (indicador, valor) e `brevo_mudancas` (email, etapa_antes, etapa_depois, controle, entra_na_lista, sai_da_lista), regravadas uma vez por dia; `rodada` ganhou `brevo_status`, `brevo_detalhe` e `brevo_ultima_leitura_ok` no fim; aba `Régua` ganhou `Lista no Brevo` no fim. O painel pode mostrar o plano do Brevo e o estado da chave.
- **Regra do guia:** o atributo de primeiro nome no Brevo é `FIRSTNAME`, não `NOME`. O Painel nunca cria contato no Brevo e nunca toca em descadastrado.
- **(Etapa 8, 11/10/2026) Garimpo e Meta:** abas novas `meta_sumiu_180`, `meta_nao_abre`, `meta_compradores_180` (email, phone, fn, ct) e `meta_resumo` (indicador, valor), regravadas uma vez por mês; `Configuração` ganhou "Brevo: ID do segmento não abre email" no fim; o Painel passou a ler também a aba "Respostas ao formulário 1" do Google Forms. As abas `meta_*` têm emails e telefones: não devem ir para o painel, só para a planilha.
- **(Etapa 7.1, 13/10/2026) Régua no Brevo pausável:** 7 linhas novas no fim da `Configuração` com nomes exatos: `Régua no Brevo`, `Pausa programada de`, `Pausa programada até`, `Etapa 0 no Brevo`, `Etapa 1 no Brevo`, `Etapa 2 no Brevo`, `Etapa 3 no Brevo` (Ligada/Pausada e Ligada/Desligada; datas dd/mm/aaaa). A aba `brevo_plano` ganhou no fim `Régua no Brevo` (Ligada / Pausada / Em pausa programada até dd/mm), `Etapas ligadas`, `configuracao`, contadores novos e `aviso N`. Atributos novos no Brevo: `CUPOM` e `CUPOM_ATE`.
- **Abas novas:** `Régua` (janelas e ofertas editáveis, o motor lê dela), `desejos` (pedidos de disco: email, telefone, nome, desejo, data, status), `contatos_manuais` (WhatsApp feito à mão; hoje vazia), `resumo_semana` (7 dias: enviadas, não contatadas, recuperadas; vai no email de segunda) e `rodada` (hora da última rodada bem-sucedida; o alerta de rotina parada lê dela).
- **`Configuração`:** linhas novas no fim: "Dias da fila" (padrão "seg a sáb"), "Fila única: início" (12/10/2026), "Teste WhatsApp 45 dias: início" (12/10/2026) e "fim" (18/01/2027), "Teste 45 dias: grupo de controle / só email / email e WhatsApp (%)" (10/30/60), "Dias para contatar depois de completar 45 dias" (30), "Email de alerta (rotina parada)" e "Horas sem rodada para alertar" (3).
- **`Mensagens`:** modelos novos G45, VIP e ALERTA_GARIMPO e marcadores novos {ultimo_disco}, {sugestao}, {link_sugestao} e {sugestoes} (no fim da aba). Nome de disco vira "Álbum (Artista)".
- **`Resultados`:** ganhou o bloco "Não contatados" (por origem) antes da tabela "Por primeiro modelo enviado". As linhas de cima não mudaram.
- **`produtos`:** colunas `criado_em` e `atualizado_em` no fim. **`Fila`:** colunas `Origem`, `Encerrado em`, `Na fila desde` e `Recuperado em` no fim.
- **Regras do guia:** teste do WhatsApp de 45 dias começa em 12/10/2026 (não mais 19/10); a lista semanal manual não é mais necessária; a fila só sai nos "Dias da fila"; quem sai da fila sem contato vira "Encerrado sem contato" e conta como "Não contatados"; linha não marcada volta no dia seguinte com aviso e no mesmo toque; email das 10h e das 17h atrasado sai com "(atrasada)".
## Pendências do Túlio

- [x] **Decisão (13/10/2026):** "Respondeu agora" não registra toque inferido; a trava de 30 dias vale para Status Respondeu mesmo com 0 toques (D-053, aba `respostas_vistas`).
- [x] **Segurança (feito em 15/10/2026):** o Túlio gerou códigos de recuperação novos no GitHub e guardou fora do projeto; os antigos não valem mais. O arquivo antigo `github-recovery-codes.txt` foi apagado da pasta do projeto. Ele continua no histórico do repositório privado (commit 4dea02d), mas só com códigos já invalidados.
- [ ] **Brevo (7.1):** criar os atributos `CUPOM` e `CUPOM_ATE` (texto) e conferir a reentrada das automações (guia em `docs/BREVO.md`).
- [ ] Custos: liberar leitura de entregas read_fulfillment_orders na Nuvemshop e configurar acesso Meta ads_read, META_ADS_ACCOUNT_ID e META_ADS_TOKEN (docs/CUSTOS_AUTOMATICOS.md).
- [x] Ativar a Google Sheets API e a Google Drive API (feito em 08/10/2026) e compartilhar a planilha com a conta de serviço (funcionou).
- [ ] Apagar a aba vazia `Página1` da planilha, se quiser (o Painel não mexe nela).
- [x] Criar o repositório PRIVADO `painel-monstro` no GitHub e cadastrar os 5 segredos (feito em 08/10/2026; o segredo do Google precisou ser colado de novo).
- [x] Criar o aplicativo sob medida na Nuvemshop e guardar o token (feito; confirme nas permissões do aplicativo que é só leitura de pedidos, clientes e produtos, mais carrinhos na etapa 5.1).
- [x] Criar a Planilha Google e a conta de serviço do Google (feito).
- [x] Instalar Git for Windows, Python 3.12 e o agente.
- [ ] Preencher a aba `custos` na Planilha Google (a Etapa 4 cria): margem média de usados e de lacrados, investimento no Meta do mês (e compras e receita que o Meta atribui), custo e vendas do Brevo, embalagem e, quando houver campanha de frete grátis, `frete_pago_loja`.
- [x] Chave do Brevo criada, no `.env` e nos segredos do GitHub; bloqueio de IP das chaves de API desativado no Brevo (09/10/2026).
- [ ] **Brevo:** criar os 5 atributos (`ETAPA`, `DIAS_SEM_COMPRAR`, `FAMILIA`, `VIP`, `CONTROLE`), as 4 listas `Painel · Etapa 0 a 3` e uma automação por lista, (passo a passo em `docs/BREVO.md`). Etapa 0 ligada; automações conforme o Túlio ligou. Modo teste já foi desligado em 14/10/2026.
- [ ] **Apps Script:** colar o `apps-script/fila-por-email.gs` novo (Extensões > Apps Script), rodar `instalar` e preencher na aba `Configuração` "Emails que recebem a fila", "Emails do resumo" e "Email de alerta (rotina parada)".
- [ ] **Garimpo:** criar o Google Forms (3 perguntas) vinculado à planilha e divulgar o link (passo a passo em `docs/GARIMPO_E_META.md`).
- [ ] **Meta:** criar no Brevo o segmento "não abre email" e escrever o número na aba `Configuração` (linha "Brevo: ID do segmento não abre email"); subir os 3 públicos no Gerenciador de Anúncios todo mês.
- [ ] Conferir se os segredos do GitHub têm `BREVO_API_KEY` (a rotina de hora em hora já a lê).

## Ritmo combinado (atualizado em 08/10/2026)

- Sem datas fixas: o Túlio faz as sessões em sequência, no ritmo dele, cada uma só depois da anterior conferida.
- Obrigatório: etapa 5.1 (carrinho) pronta antes da Black Friday (27/11).
- Etapa 7 (Brevo): o modo teste foi desligado pelo Túlio em 14/10/2026 (a nota antiga de esperar a Black Friday foi superada).
- Decisão do teste do WhatsApp de 45 dias em 18/01/2027 (D-022).
- Roteiro clique a clique: doc "Painel Monstro · passo a passo da implementação" (claude.ai).

### Avisar o Cowork: comissão e taxa real (D-060, 14/10/2026)

Aba `comissao` e linhas "Comissão: ..." da Configuração são do painel; o Painel Python não escreve nelas. Taxa real do Nuvem Pago por pedido: a API oficial não entrega (sem campo no pedido, `/transactions` vazio, `/payments` 404). `taxas` e `total_liquido` da aba `pedidos` ficam vazias no caminho da API e só vêm da exportação CSV. O painel deve manter a taxa estimada por meio de pagamento da Configuração como padrão.


### Avisar o Cowork: coluna estorno (D-061, 14/10/2026)

Aba `pedidos` ganhou `estorno` no fim (valor estornado, parcial ou total). A API oficial não informa o valor (só o status do pagamento), então a coluna vem vazia na rotina da API e só é preenchida a partir da exportação CSV ("Estorno"). Tratar vazio como "valor desconhecido", não zero. Colunas existentes não mudaram. A aba `comissao` e a coluna `estornos` dela são do painel.


### Avisar o Cowork: newsletter semanal (D-063, 14/10/2026)

Aba `produtos` ganhou no fim `imagem`, `descricao` e `no_estoque_desde`. Nova aba `newsletter_semana` (url, nome, artista, album, ano, tipo, preco, imagem, familia, descricao), gerada quarta a partir das 17h; `newsletter_aviso` é só para o email. O Cowork preenche `newsletter_historico` (url, data_envio) depois de montar a campanha. Guia: docs/NEWSLETTER.md. Túlio: colar o `fila-por-email.gs` atualizado no Apps Script (aviso por email). Brevo continua em modo teste/sem envio.


### Avisar o Cowork: revisão do script da fila (14/10/2026)

O email da fila agora mostra o rótulo humano do modelo (Frete grátis, 10% nos discos (oferta final), Estoque alterado, Aviso de garimpo, Garimpo de 45 dias, VIP, Lembrete). `newsletter_aviso!A2` é texto "AAAA-MM-DD HH:mm". Túlio: colar de novo o `fila-por-email.gs` no Apps Script.


### Avisar o Cowork: atribuições (D-064, 14/10/2026)

Aba `atribuicoes` (numero_pedido, origem, observacao, registrado_em): o painel escreve, a rotina só lê. `vale_a_pena` ganhou a linha "Indicações e contatos manuais" (estado `sem controle`, é receita atribuída, não a mais) e as colunas `pedidos` e `receita_atribuida` no fim. Configuração ganhou no fim "Prefixo de cupom de indicação" (vazio = desligado). Guia: docs/ATRIBUICOES.md.


### Avisar o Cowork: Brevo em modo real e atribuições criadas (14/10/2026)

Brevo não está mais em modo teste: `BREVO_MODO_TESTE` = nao e `brevo_plano` em modo REAL desde 14/10/2026. O Cowork criou a aba `atribuicoes` (registrado_em como texto "AAAA-MM-DD HH:mm"); o painel mostra a linha "sem controle" de `vale_a_pena` com `pedidos` e `receita_atribuida`.

### Avisar o Cowork: ajuste das atribuições (D-065, 14/10/2026)

Pedido atribuído que já foi reconhecido por qualquer ciclo da Fila (Carrinho, Garimpo, VIP ou 45 dias) conta só na Fila e sai de "Indicações e contatos manuais". A `nota` da linha em `vale_a_pena` diz quantos foram ignorados (e de qual origem). Colunas não mudaram.


### Avisar o Cowork: D-059

Integrar docs/PASSAGEM_COWORK_CRM.md: ofertas gerais em toda a loja, ciclo e marcação única preservados, mensagens da Fila como fonte. Escrita por API não dispara onEdit; executar registro equivalente no backend ou abrir a planilha. Atualizar guia e textos de oferta da régua compartilhada; Brevo permanece em modo teste.

### Avisar o Cowork: confirmação de D-058

D-058 confirmada pelo Túlio: todos os cupons valem para usados e lacrados em toda a loja online, tanto no carrinho quanto na régua de email. Mesmo VOLTA10<MÊS>, sem cupom separado para carrinho. VOLTA10OUT conferido em leitura: válido, 10%, sem restrição de categorias/produtos e max_discount_amount ausente (sem teto em reais, conforme correção explícita do Túlio). R$30 é somente o teto da cotação para oferecer frete no carrinho; mínimo R$200 mantido. Consignados só existem na loja física; exclusão de etiqueta prata mantida como proteção caso apareçam na fonte. Oferta da Etapa 3 e ajuda de Cupom de desconto na Configuração já atualizadas pelo Túlio.


### Avisar o Cowork: Etapa 9 · anúncios do Meta (D-066, 15/10/2026)

Ler somente as abas anuncios_ abaixo para a tela de anúncios. Não ler meta_*: essas abas são públicos e contêm dados de clientes. Nenhum nome ou ordem de coluna existente foi alterado. Colunas finais, na ordem:

- `anuncios_campanha_dia`: `data`, `campanha_id`, `campanha`, `tipo`, `status`, `orcamento_dia`, `investido`, `investido_real`, `impressoes`, `alcance`, `frequencia`, `cliques_link`, `ctr_link`, `cpm`, `carrinhos`, `finalizacoes`, `compras`, `receita`, `roas_real`, `cpa_real`.
- `anuncios_hoje`: `data`, `hora`, `campanha_id`, `campanha`, `tipo`, `investido`, `cliques_link`, `carrinhos`, `finalizacoes`, `compras`, `receita`.
- `anuncios_anuncios`: `anuncio_id`, `anuncio`, `campanha_id`, `campanha`, `conjunto`, `tipo`, `status`, `thumb`, `investido_7d`, `compras_7d`, `receita_7d`, `ctr_7d`, `ctr_campanha_7d`, `frequencia_7d`, `investido_30d`, `compras_30d`, `receita_30d`, `cansado`, `motivo`.
- `anuncios_semana`: `semana_inicio`, `escopo`, `investido`, `investido_real`, `variacao_investimento_pct`, `mudou_verba`, `compras`, `receita`, `roas_real`, `cpa_real`, `compras_por_100`, `cliques_link`, `conversao_clique_pct`, `carrinhos`, `finalizacoes`, `discos_criados`, `discos_voltaram`, `discos_entraram`, `pedidos_site`, `receita_site`, `leitura`.
- `anuncios_alertas`: `nivel`, `campanha`, `anuncio`, `regra`, `detalhe`, `desde`.
- `anuncios_resumo`: `chave`, `valor`.
- `anuncios_notas`: `campanha_id`, `tipo`, `data_evento`, `nota`, `registrado_em`.
- `anuncios_direcao`: `data`, `prioridade`, `texto`.

A rotina escreve as seis primeiras abas. O Cowork escreve apenas linhas de anuncios_notas (override de tipo e data_evento; registrado_em como texto AAAA-MM-DD HH:mm) e anuncios_direcao (data, prioridade, texto). A rotina só cria os cabeçalhos dessas duas, se faltarem. Cowork publicou a aba Anúncios no painel e agendou a direção seg/qua/sex às 7h46, que grava em anuncios_direcao (informado pelo Túlio). O Python continua apenas lendo essa aba.

Configuração ganhou dez linhas Anúncios: no fim, com ajuda C e valores iniciais de docs/ANUNCIOS.md. Valores existentes permanecem. Mostrar estado/aviso e data da última coleta boa do resumo, inclusive com dados antigos preservados durante falha. Semanas são seg-dom; semana corrente parcial, divisão sem denominador e leitura sem 4 semanas válidas ficam vazias. Empate não gera diagnóstico. Retornos anteriores a 14/10/2026 são desconhecidos, nunca zero. orcamento_dia/status são fotografia atual, não registro histórico de orçamento. Fotografia atual de no_estoque_desde não reconstrói todos os retornos passados. Nunca oferecer controle de campanha nesta fase.

### Avisar o Cowork: classificação de campanhas (15/10/2026)

Evento: nome contém _local em qualquer posição, [evento] ou alcance. Remarketing: contém rmk ou remarketing. Comparação sem distinguir maiúsculas/minúsculas; tipo manual de anuncios_notas continua prevalecendo, evento tem prioridade sobre remarketing e sazonal. Conforme informado pelo Túlio, aba Anúncios publicada e direção seg/qua/sex às 7h46 já agendada pelo Cowork, gravando em anuncios_direcao. Sem alteração de abas/colunas.


## Etapa 10 · cadastro de discos (D-067, 15/10/2026)

Código integrado à rotina horária com erro isolado. Só aprovado cria oculto, estoque 1, sem atualizar produto existente. Diário durável em planilha e cache protege contra repetição após falha; SKU permite reconciliar POST. Imagens só depois de salvar produto_id. Rascunhos podem ganhar referências, dados Discogs e prévias privadas, nunca aprovação automática. Fotos e preços são lidos pelo Cowork, não pelo Python. Cópias em site/<id_disco>/ da pasta pai da entrada; originais preservados.

Preparação real: entrada Drive por ID fornecido pelo Túlio configurada, cadastro_fotos criada e colunas acrescentadas ao fim; 11 rascunhos preservados. Acesso de leitura e permissão de adicionar na entrada/pasta pai confirmados. Não houve upload de imagens nem criação de produto real. Editor em Meu Drive pode não bastar para upload com conta de serviço por cota/propriedade; validar prévias antes de aprovar. Sem DISCOGS_TOKEN, só esse enriquecimento fica pendente. Não rodamos rotina completa local (Brevo está REAL).

Pela metade: integração do painel pelo Cowork, primeiras prévias e primeira criação oculta real após revisão do Túlio. Rever preços 200 fictícios do lote piloto, conservação do vinil e fotos antes de aprovar. Correção de frete pronta mas NÃO executada contra loja, nem simulação; fora do Actions, espera frase `pode aplicar as correções de frete`. UTM interrompida por falta de landing/referrer no pedido real/documentação; order_origin vazio. Pedidos não ganhou colunas nem origem presumida. Parser isolado testado, eventual captura no site depende de outra etapa autorizada.

### Avisar o Cowork: Etapa 10 · Cadastro

Preservar nomes e ordem dos primeiros 28 campos. Contrato final cadastro_rascunhos, 37 colunas:

```
id,lote,pasta,status,titulo,marca,categorias,ficha,descricao,capa,vinil,preco,preco_referencia,peso_kg,altura_cm,largura_cm,comprimento_cm,discogs_url,discogs_confianca,pendencias,fotos,seo_titulo,seo_descricao,tags,produto_id,link_loja,observacao_tulio,atualizado_em,discogs_id,faixas,creditos,discogs_menor_preco,discogs_a_venda,faixas_na_descricao,preco_origem,cadastro_execucao,fotos_ajustadas
```

cadastro_fotos (Cowork mantém metadados; rotina completa apenas IDs vazios por nome exato), seis colunas exatas:

```
id_disco,ordem,papel,arquivo_drive_id,cantos,observacao
```

- Cowork monta rascunhos e fotos; Túlio revisa e muda status para aprovado. Mostrar preço da etiqueta separado de preco_referencia, pendências, prévias e conservação. R$200 do piloto é fictício: rever antes de aprovar. Faixas só na descrição com faixas_na_descricao=sim; padrão não.
- Nunca limpar/recriar linhas nem copiar IDs/diário ao duplicar disco. produto_id, link_loja, cadastro_execucao e fotos_ajustadas são da rotina. Cadastro_execucao é JSON técnico indispensável para não duplicar criação, não campo de edição. fotos_ajustadas é JSON de objetos ordem/papel/arquivo_drive_id para prévias pelo Drive autenticado; não abrir compartilhamento público.
- Entrada por `Cadastro: pasta de entrada Drive (ID)` na Configuração, já preenchida com ID informado. Não usar J: no código. Imagens devem estar diretamente na entrada; cópias na pasta irmã site/<id_disco>. Papel etiqueta nunca sobe para loja. Cadastro: publicar direto reservado e ignorado: nasce sempre oculto.
- Fluxo status: rascunho > aprovado > criado ou erro: motivo > publicado (detectado por GET após publicação humana na loja). Não oferecer botão que publique automaticamente nesta etapa. Erro incerto exige conferir loja/diário antes de voltar a aprovado, nunca apagar ID para tentar novamente.
- Produto oculto pode não abrir no link público até publicação. Conferir no administrador. Toda escrita externa de cadastro é da rotina; não disparar POST concorrente pelo painel.
- Nenhuma coluna nova em pedidos por UTM; não construir leitura dessas colunas. O painel Anúncios e direção seg/qua/sex 7h46 em anuncios_direcao continuam como informados pelo Túlio.
- Sem mudança necessária no Apps Script da fila. Documentação completa e passo a passo de ativação: docs/CADASTRO.md. Script de frete separado ainda sem autorização de execução.


### Avisar o Cowork: resolução de fotos por nome (ajuste D-067, 15/10/2026)

Sem mudança de abas ou colunas. Agora `observacao` pode conter o nome exato do arquivo original da entrada quando `arquivo_drive_id` está vazio. A rotina busca só na entrada por ID da Configuração, exclui lixeira e considera todas as páginas. Um resultado único preenche somente o ID; IDs existentes e demais células são preservados. Não acrescentar comentários ao nome enquanto usar essa resolução.

Nome vazio, não encontrado ou duplicado deixa pendência `Fotos por nome: ...` no rascunho, mantém status/observações humanas e bloqueia prévia/criação daquele disco, mesmo aprovado. Corrigir o nome/duplicidade e aguardar a próxima rodada; a pendência automática é limpa quando resolver, sem apagar as demais. Todos os arquivos do disco são conferidos antes de gravar seus IDs; a etiqueta também é vinculada, mas nunca enviada para a loja. O Cowork deve preservar IDs preenchidos, podendo continuar fornecendo-os diretamente.

Validação: 616 testes passaram, com casos de nome exato, ausente/repetido, diferença de maiúsculas/espaços, paginação, IDs existentes, edição concorrente e bloqueio antes de qualquer POST. Conferência real inicial: 64 fotos, todas com nome único correspondente na entrada. Aplicação real concluída: os 64 arquivo_drive_id foram preenchidos; releitura confirmou rascunhos e todas as demais colunas intactos. Backup privado em dados/backup-cadastro/fotos-antes-resolucao-nomes.json, fora do git. Nenhuma imagem baixada ou produto criado. Upload/cota Drive, revisão de preço e primeira criação oculta continuam nas pendências anteriores. Correção de frete não executada.


### Avisar o Cowork: cadastro quase imediato (D-068, 15/10/2026)

Implementado pelo próprio Cowork. Workflow `cadastro.yml` (repository_dispatch `cadastro` e manual) roda `--so-cadastro`; vigia `apps-script/vigia-cadastro.gs` dispara a cada 5 minutos quando há `aprovado` sem `produto_id`. Falta o Túlio: push, token fine-grained (Contents: Read and write, só painel-monstro) em Script Properties `GITHUB_TOKEN`, colar o vigia e a versão nova do fila-por-email.gs, rodar `instalarVigiaCadastro`. 623 testes passando.
