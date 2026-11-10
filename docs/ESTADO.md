# Atualização de sessão · Regras anti-homônimos no cadastro, lote 2026-11-10-a e diagnóstico da loja (D-104), 10/11/2026

- **Regras no código para identificação e descrições (Parte A):**
  - Identificação Discogs com prova física: só aceita correspondência se houver catálogo exato, gravadora + faixas, ou matriz do rótulo nas fotos. Nome de artista e álbum nunca bastam sozinhos.
  - Trava para homônimos e sem título próprio: artista igual ao álbum, "Volume X" ou coletâneas genéricas exigem catálogo ou faixas comprovadas; caso contrário, gera alerta "edição não confirmada" e bloqueia publicação direta (`publicar = 'nao'`).
  - Ano da edição: fixado pelo catálogo comprovado; reedições trazem o texto padrão "Reedição de AAAA do álbum lançado originalmente em AAAA", sem duplicar ano no título.
  - Descrição completa obrigatória: contexto (1 a 3 frases), ficha técnica completa (gravadora, catálogo, país, ano), formato físico (LP simples/duplo, capa, encarte), faixas completas organizadas por Lado A e Lado B, e estado de conservação (Capa e Vinil). Destaques citados no texto DEVEM existir no repertório do disco; se faltar ou houver divergência, gera alerta "descrição incompleta" ou "destaque fora das faixas" e bloqueia publicação.
  - Testes automatizados implementados e validados em `tests/test_cadastro_lote.py`. Suite completa com 818 testes passando (1 ignorado) e 0 problemas na auditoria.

- **Processamento do novo lote 2026-11-10-a (Parte B):**
  - 8 itens processados e gravados como rascunho na aba `cadastro_rascunhos` (IDs `2026-11-10-a-01` a `08`), sem criar nada na Nuvemshop.
  - Fotos renomeadas e organizadas em `entrada/processadas/2026-11-10-a/` no Google Drive.
  - Casos notáveis identificados visualmente nas fotos:
    - Item 3 não era 14 Bis, mas sim Rita Lee & Tutti Frutti - Atrás do Porto Tem Uma Cidade (1980/1974), com etiqueta de R$ 300. Capa original Philips de 1974 com disco da prensagem Fontana Fora de Série de 1980.
    - Dois discos do Belchior: Objeto Direto (1980, R$ 250 na etiqueta) e Alucinação (1976/1980, R$ 500 na etiqueta). Fotos e matrizes distintas, sem duplicidade de registro.
    - Livro de Pedro de Luna sobre o Mundo Livre S/A (R$ 230, exemplar novo lacrado).
    - Faith No More - The Real Thing (1990, R$ 180 na etiqueta).

- **Diagnóstico dos discos já cadastrados na loja (Parte C):**
  - Varredura dos 197 produtos criados pelo cadastro automático:
    - Leandro & Leonardo R$ 60: produto 378897418 (publicado como Vol. 3 de 1989) é na verdade o Vol. 4 de 1990 e traz dedicatória autografada por Leandro e Leonardo na capa; produto 378897954 (publicado como Vol. 4 de 1990) é o Vol. 7 de 1993.
    - Elis Regina: produto 379327344 (publicado como Elis 1980 da EMI) teve a descrição e faixas puxadas do disco homônimo de 1977 da Philips (com "Romaria").
    - Três produtos com ano duplicado no título: Roupa Nova (1982), Roberto Carlos (1993) e Roberta Miranda (1990).
    - 129 produtos da fase inicial com descrição resumida (sem a separação detalhada de faixas por lado).
    - Nenhuma alteração foi gravada na loja ou na planilha referente aos produtos antigos (apenas diagnóstico para decisão do Túlio).

Próximo passo: Túlio avaliar os rascunhos do lote 2026-11-10-a no Painel e aprovar as correções dos álbuns homônimos antigos apontados no diagnóstico.

# Atualização de sessão · Disparo reserva da rotina, ajuste de cron e migração para Node 24 (D-103), 08/11/2026

- **Disparo reserva da rotina e estabilização de agendamento:**
  - Diagnóstico do cron no GitHub Actions: a rotina rodava no minuto 7 (`7 * * * *`). O cron foi alterado para o minuto 17 (`17 * * * *`), fugindo de congestionamentos de horário redondo.
  - Concorrência validada: `concurrency: group: rotina-painel, cancel-in-progress: false` confirmada no `rotina.yml` e compartilhada com o `cadastro.yml`.
  - Habilitado `repository_dispatch: types: [rotina]` sob `on:` no `rotina.yml`, permitindo acionamento pelo Apps Script via token GitHub.
  - Criado o mecanismo de disparo reserva no Apps Script (`apps-script/fila-por-email.gs`):
    - Função `verificarDisparoReserva()`: verifica se a última rodada boa (`rodada!A2`) ocorreu há mais de 75 minutos.
    - Proteções anti-duplicata: trava de execução (`LockService.getScriptLock`), cooldown de 30 minutos entre disparos (`ROTINA_ULTIMO_DISPARO_MS`) e consulta prévia à API do GitHub (`/actions/workflows/rotina.yml/runs?per_page=5`) para checar se há rodadas em `in_progress` ou `queued`.
    - Execução do disparo: envia `repository_dispatch` (evento `rotina`) com fallback automático para `workflow_dispatch`.
    - Registro de logs: grava cada tentativa na aba `disparos_reserva` (data/hora, motivo, minutos sem rodada, sucesso, HTTP status e detalhes) e nas propriedades do script.
    - Função `dispararRotinaReservaAgora()` para teste manual direto pelo editor do Apps Script.
  - Ajuste no alerta por email (`verificarRodada_()`):
    - O email de alerta de rotina parada (> 3 horas) agora informa o estado do disparo reserva (se foi tentado, quando ocorreu e qual foi o código/resposta do GitHub).
  - Atualização dos workflows para Node 24:
    - Atualizadas as actions em `.github/workflows/rotina.yml` e `.github/workflows/cadastro.yml`:
      - `actions/checkout@v6`
      - `actions/setup-python@v7`
      - `actions/cache/restore@v5`
      - `actions/cache/save@v5`
  - Testes e auditoria:
    - 62 testes locais do Apps Script passaram (`node apps-script/teste_local.js`), cobrindo checagem < 75 min, disparo > 75 min, cooldown de 30 min, detecção de rodada em andamento, fallback para workflow_dispatch e conteúdo do email de alerta.
    - Suite de 815 testes Python passou (1 ignorado).
    - Auditoria de publicação (`scripts/auditar_publicacao.py`) confirmou 144 arquivos versionados e 0 problemas.

Próximo passo: Túlio atualizar o script `fila-por-email.gs` no Apps Script da Planilha Google, adicionar as propriedades `GITHUB_REPO` e `GITHUB_TOKEN` e executar a função `instalar`.

# Atualização de sessão · Tela de Conferência física de estoque no Painel Web, 07/11/2026

- **Tela de Conferência na aba Cadastro do Painel Web:**
  - Criada tela completa de conferência integrada diretamente na aba Cadastro, acionada pelo botão de filtro "Conferência".
  - Base de dados unificada: consolida todos os discos ativos da loja (aba `produtos`, cerca de 1.941 produtos com estoque positivo) cruzados com a aba `cadastro_rascunhos` para ler ou gravar o status de conferência. Discos cadastrados direto na loja sem rascunho prévio também entram na lista normalmente.
  - Tabela compacta e responsiva pensada para tela de computador (sem quebrar no celular):
    - Colunas: miniatura da capa (imagem Nuvemshop com lazy-loading ou ícone reserva), título e artista em destaque, preço (preço de venda ou promocional), estado com etiqueta colorida (Novo/Lacrado ou Usado), estoque (destaque visual se zerado), situação no site (Visível ou Oculto), ID do lote, ID na loja (com links diretos para o painel de produtos da Nuvemshop e para o site público) e coluna de conferência.
  - Filtros e busca instantânea:
    - Campo de busca no topo com filtragem em tempo real sem botão, pesquisando por título, artista, ID do lote e ID do produto, ignorando maiúsculas e acentos (`cdNorm`).
    - Filtro de conferência: só os não conferidos (padrão), todos e só os conferidos.
    - Filtro de tipo: todos os discos (exclui livros por padrão), só usados, só novos/lacrados, ou todos incluindo livros.
    - Filtro de situação no site: todos, visíveis ou ocultos.
    - Filtro de estoque: com estoque (padrão) ou todos.
    - Filtro por lote: lista suspensa dinâmica com todos os lotes existentes mais a opção "Sem lote (produtos diretos da loja)".
    - Filtro por período de cadastro: data inicial e data final.
    - Ordenação: por artista (padrão A-Z, ordem das prateleiras da loja física), por título, por data de cadastro (mais recentes ou mais antigos) e por preço (maior ou menor).
  - Barra de progresso e contadores em tempo real:
    - Total de discos listados, quantidade de conferidos, quantidade pendente e barra de progresso com porcentagem visual.
  - Marcação com um clique e persistência:
    - Checkbox em cada linha para marcar como conferido, registrando data/hora e autor (`conferido_em` e `conferido_por`) na planilha.
    - Permite desmarcar a qualquer momento se conferido por engano, limpando a data na planilha.
    - Se o disco veio direto da loja sem rascunho anterior, o Painel cria a linha de referência permanente na aba `cadastro_rascunhos` com ID `loja-<produto_id>` e status `publicado`, sem disparar criação duplicada na Nuvemshop.
    - Suporte a seleção múltipla com marcação e desmarcação em lote.
  - Botão "Imprimir esta lista":
    - Gera e imprime o checklist A4 com os exatos filtros e busca aplicados na tela, sem abrir janelas pop-up.
  - Testes e validação:
    - Teste automatizado com navegador real via Playwright (`tests/test_painel_conferencia.py`) simulando o `google.script.run`, testando navegação, busca instantânea, filtros, marcação/desmarcação e impressão.
    - Teste de truncamento de comentários confirmando sintaxe 100% válida após corte de `//` em linhas de script.
    - 56 testes locais do Apps Script passaram (`node apps-script/teste_local.js`).
    - Suite de 815 testes Python passou (1 ignorado).
    - Auditoria de publicação (`scripts/auditar_publicacao.py`) confirmou 143 arquivos e 0 problemas.

Próximo passo: Túlio atualizar o arquivo `Painel.html` no Google Apps Script seguindo o passo a passo e testar a conferência física pela tela do computador.

# Atualização de sessão · Checklist em PDF no Painel Web, 06/11/2026

- **Checklist de conferência física em PDF no Painel Web:**
  - Criado botão "Checklist em PDF" no cabeçalho do cadastro de discos e na barra superior da lista de conferência (`cd-marcar-topo`).
  - Adicionado modal interativo de configuração (`cd-modal-checklist`) com opções de filtros:
    - Escopo: apenas discos ainda não conferidos (sem etiqueta verde ou com `conferido_em` vazio) ou todos os discos físicos.
    - Filtro por lote: lista suspensa dinâmica contendo todos os lotes cadastrados na planilha ou opção "Todos os lotes".
    - Filtro por período: campos de data inicial e data final (com base no ID do disco `AAAA-MM-DD`).
  - Conteúdo e layout do checklist gerado:
    - Formato A4 em retrato com margens otimizadas para impressão.
    - Cabeçalho repetido em todas as páginas (`thead { display: table-header-group; }`) e paginação no rodapé (`@page { @bottom-right { content: counter(page); } }`).
    - Colunas: quadradinho para marcar à caneta (`.chk-box`), artista e título do álbum em destaque, preço, estado (Novo ou Usado), ID do lote, ID na Nuvemshop e situação no site (Visível ou Oculto).
    - Ordenação natural por Artista (A-Z) para conferência direta nas prateleiras da loja física.
    - Resumo no topo com total de discos, contagem de novos e usados, filtros aplicados e data/hora exata da geração.
    - Barra superior com botão "Imprimir / Salvar como PDF", acionamento automático de impressão via navegador e suporte nativo para salvar em arquivo PDF.
    - Dados sempre lidos na hora diretamente da planilha e da loja, sem listas guardadas desatualizadas.
  - Testes e validação:
    - 55 testes do script local passaram (`apps-script/teste_local.js`), cobrindo extração de artista, filtros, ordenação e estrutura HTML do checklist.
    - Suite de 813 testes do Python passou (1 ignorado).
    - Auditoria de publicação (`scripts/auditar_publicacao.py`) confirmou 143 arquivos versionados e 0 problemas.

Próximo passo: Túlio atualizar o arquivo `Painel.html` no Google Apps Script seguindo o passo a passo e testar a geração do checklist.

# Atualização de sessão · Cadastro dos novos lotes 2026-11-06-a e 2026-11-06-b, 06/11/2026

- **Parte 1 · Ajuste de Chico Buarque - Vida (produto 379329375 e rascunho 2026-11-03-23):**
  - Título refinado para: `LP Chico Buarque - Vida (2024) - (Vinil Verde Translúcido Marmorizado) (Novo/Lacrado)`.
  - Descrição atualizada na loja e planilha para: `Edição em vinil colorido (Verde Translúcido Marmorizado).`.
  - Tags atualizadas incluindo `Vinil Marmorizado` e SEO ajustado com a cor completa.
  - Produto mantido oculto (`published = False`), estoque 1 e preço R$ 280,00 preservados.

- **Parte 2 · Cadastro dos dois lotes novos (subpastas 261106a e 261106b do Drive):**
  - **Lote 2026-11-06-a (53 discos, 193 fotos):**
    - Todos os 53 discos cadastrados como `rascunho` na aba `cadastro_rascunhos` (`2026-11-06-a-01` a `53`) e 193 linhas de fotos em `cadastro_fotos`.
    - 193 fotos renomeadas e movidas junto com 53 capas do Discogs para `J:\Meu Drive\Cadastro de Discos\entrada\processadas\2026-11-06-a\`.
    - Destaques que exigem decisão do Túlio: `d36` (Baby Animals) está sem preço (só ponto vermelho na capa, sem etiqueta); `d26` (The Apples) tem assinatura à caneta na etiqueta do vinil ("Mildo-MYX", marcado como `marcado_vinil: sim`); 7 discos já existem na loja com estoque 1 ativo (Beatles Rock 'N' Roll Music, Santana Freedom, Paul McCartney Broad Street, Simply Red Men and Women, Beatles Hollywood Bowl, Simple Minds Live, Nina Hagen Fearless).
  - **Lote 2026-11-06-b (51 discos, 252 fotos):**
    - Todos os 51 discos cadastrados como `rascunho` na aba `cadastro_rascunhos` (`2026-11-06-b-01` a `51`) e 252 linhas de fotos em `cadastro_fotos`.
    - 252 fotos renomeadas e movidas junto com 51 capas do Discogs para `J:\Meu Drive\Cadastro de Discos\entrada\processadas\2026-11-06-b\`.
    - Destaques que exigem decisão do Túlio: 3 cópias distintas de *Caetano Veloso - Velô* (`d39` R$ 100, `d40` R$ 120 com encarte de letras e assinatura "Euler" no vinil, `d45` R$ 80 com marcas do tempo na capa); 8 repetidos na loja com estoque 1 ativo (Santana Beyond Appearances, Jimi Hendrix Rare Hendrix, The Police Singles, Elis Regina Elis 1974 dupla, Maria Bethânia Talismã, Maria Bethânia Pássaro da Manhã, Maria Bethânia Recital Boite Barroco, Caetano Veloso Caetano 1987); edição histórica de Luiz Gonzaga *Ô Véio Macho* (1962, RCA Victor BBL-1175 com rótulo azul original).
  - **Nenhum produto foi criado na Nuvemshop.** Todos os 104 discos estão gravados como rascunho na planilha para revisão e aprovação do Túlio no Painel.

Verificação: 813 testes Python passaram, 1 ignorado; auditoria de publicação com 143 arquivos versionados e 0 problemas.

Próximo passo: Túlio revisar os rascunhos no Painel, definir o preço de Baby Animals (`2026-11-06-a-36`), conferir os repetidos na loja e aprovar os produtos.

# Atualização de sessão · Chico Buarque - Vida (vinil verde, produto 379329375), 06/11/2026

- **Correção da cor do vinil de Chico Buarque - Vida (produto 379329375 e rascunho 2026-11-03-23):**
  - Título ajustado no padrão dos demais lacrados coloridos da loja para: `LP Chico Buarque - Vida (2024) - (Vinil Verde) (Novo/Lacrado)`.
  - Descrição atualizada incluindo a menção `Edição em vinil colorido (Verde).` tanto na Nuvemshop (com faixas em HTML) quanto na planilha Google.
  - Tags atualizadas incluindo `Vinil Colorido, Vinil Verde` e SEO atualizado para `LP Chico Buarque Vida (2024) - Vinil Verde - Novo Lacrado`.
  - Linha correspondente em `cadastro_rascunhos` (linha 168) atualizada para manter a planilha perfeitamente sincronizada com a loja.
  - Discogs verificado: o release 30492835 (Philips / Universal Music, 2024) é a edição em vinil verde ("Green Translucent Marbled"); as fotos presentes no produto são as fotos oficiais de capa, contracapa e encarte desse mesmo release, mantidas sem alteração.
  - Produto mantido oculto (`published = False`), estoque 1 e preço R$ 280,00 preservados.

Verificação: 813 testes Python passaram, 1 ignorado; auditoria de publicação com 143 arquivos versionados e 0 problemas.

Próximo passo: Túlio revisar o produto no admin da Nuvemshop e publicá-lo quando desejar.

# Atualização de sessão · Conclusão dos 21 discos corrigidos da D-098 na loja, 06/11/2026

- **Diagnóstico e resolução dos 21 discos do lote `2026-10-28`:**
  - Diagnóstico: os 21 discos haviam recebido erro em 05/11/2026 às 11:09 porque a rotina rodou com o commit `0143de9` minutos antes do push do commit `8114f0e` (D-098).
  - Repositório confirmado no GitHub no commit `127e0f9` (que já inclui a D-098).
  - Teste de integração ponta a ponta adicionado em `tests/test_cadastro.py` (`test_processar_linha_foto_vertical_exif_8_com_cantos`), simulando `processar_linha` com foto vertical EXIF 8 e cantos ajustados com giro `ccw`, validando término sem exceção e status publicado.
  - Linhas dos 21 discos atualizadas para `status = 'aprovado'` na aba `cadastro_rascunhos` sem mexer em título, preço, estoque ou fotos.
  - Execução `workflow_dispatch` do `cadastro.yml` (Run ID `42224529557`) acompanhada até o fim: 21 discos criados com sucesso na Nuvemshop, todos com estoque 1 e status `publicado`.
  - Verificação via API e CDN da Nuvemshop: todas as 76 imagens baixadas e validadas; capas e discos perfeitamente quadrados (`1024x1024`), encartes abertos em proporção correta (`1024x576` / `1024x512`), fotos retas e sem erros.
  - Todos os 21 produtos nasceram visíveis na loja (`published = True`), com exceção de pendências informativas herdadas de conferência que não impediram a publicação.

Verificação: 813 testes Python passaram, 1 ignorado; auditoria de publicação com 143 arquivos versionados e 0 problemas.

Próximo passo: Túlio conferir os 21 produtos criados na loja online e no admin da Nuvemshop.

# Atualização de sessão · Livros 2026-11-05, aplicação D-101, Elis Regina e Chico Buarque (Vida), 05/11/2026

- **Parte A · Lote `2026-11-05-livros` gravado e aprovado (`publicar=nao`):**
  - `2026-11-05-livros-01`: `Livro 100 Grandes Álbuns do Rock Gaúcho: Influências e vertentes - Cristiano Bastos e Rafael Cony` (R$ 650) -> criado oculto na Nuvemshop (`produto_id = 379343830`).
  - `2026-11-05-livros-02`: `Livro As Histórias São Iguais: As Aventuras da Relespública na Terra da Garoa e Solidão - Melissa Medroni e Marcelo Dallegrave` (R$ 30) -> criado oculto na Nuvemshop (`produto_id = 379343888`).
- **Parte B · Aplicação da D-101 (`scripts/trocar_fotos_recorte.py --aplicar`):**
  - 34 fotos sem recorte substituídas pela versão recortada em pé nos 27 produtos da Nuvemshop, preservando a ordem exata das imagens e enviando cada imagem nova antes de apagar a antiga.
  - 33 linhas de `cantos` atualizadas em `cadastro_fotos`; relatório salvo em `dados/troca_fotos_recorte_d101.json`.
- **Parte C · Correção das miniaturas de `2026-10-28-95` (`LP Elis Regina - Essa Mulher (1979)`):**
  - Causa raiz: o disco não tinha nenhuma linha em `cadastro_fotos` e trazia `arquivo_drive_id: ""` nos 4 itens de `fotos_ajustadas`.
  - Solução: inseridas as 4 linhas em `cadastro_fotos` (`A698:F701`) apontando para os IDs reais do Google Drive em `entrada` (`2026-10-28-95 01 capa.jpg` a `04 disco.jpg`), já com `cantos` calibrados (incluindo proporção `2` para `encarte aberto`), e limpo `fotos_ajustadas` na linha 145 mantendo `status = "rascunho"`.
- **Parte D · Reidentificação e atualização pontual de `2026-11-03-23` (`Chico Buarque - Vida`, `produto_id = 379329375`, D-101):**
  - Com autorização única do Túlio registrada na D-101, atualizado o produto oculto `379329375` na Nuvemshop para `LP Chico Buarque - Vida (2024) - (Novo/Lacrado)` (release Discogs `30492835`, Philips / Universal Music, 2024), sem prometer cor do vinil no título, descrição, SEO ou tags.
  - Enviadas primeiro as 3 fotos oficiais autorizadas do release `30492835` na ordem capa (`1313827496`), contracapa (`1313827503`) e encarte com letras (`1313827523`, sem a foto do vinil verde), e apagadas em seguida as 4 imagens antigas. Preço (`R$ 280,00`), estoque (`1`), categorias e visibilidade oculta (`published = false`) mantidos intactos.
  - Planilha atualizada em `cadastro_rascunhos` (linha 168) e `cadastro_fotos` (foto da equipe marcada como `referencia`, 3 fotos antigas do *Almanaque* como `descartar` e 3 fotos oficiais do *Vida* em `A702:F704` com IDs do Drive sincronizados). Relatório em `dados/atualizacao_379329375_d101.json`.

Verificação: 805 testes Python passaram, 1 ignorado; auditoria de publicação com 0 problemas.

Próximo passo: Túlio revisar e publicar no admin da Nuvemshop os produtos ocultos `379343830`, `379343888` e `379329375` quando desejar, e definir preço/aprovação do rascunho `2026-10-28-95` no Painel.

# Atualização de sessão · Cadastro do lote 2026-11-05 (`entrada\261105a`), 05/11/2026

Gravação (`gravar --confirmar`) concluída para os 7 discos usados da pasta `J:\Meu Drive\Cadastro de Discos\entrada\261105a` (35 fotos originais: 34 do site + 1 descartada desfocada):
- `2026-11-05-01`: `LP Supertramp - Paris (1980) - (Vinil Usado, Duplo)` (R$ 130, `VG+/VG+`, 9 fotos, `publicar=sim`).
- `2026-11-05-02`: `LP Alice Cooper - Killer (1971) - (Vinil Usado)` (R$ 130, `VG+/VG+`, 4 fotos, `publicar=sim`).
- `2026-11-05-03`: `LP Lou Reed - Mistrial (1986) - (Vinil Usado)` (R$ 130, `VG+/VG+`, 5 fotos + 1 descartada, `publicar=sim`).
- `2026-11-05-04`: `LP Jeff Beck - Blow By Blow (1975) - (Vinil Usado)` (R$ 100, `VG/VG+`, 4 fotos, `publicar=sim`).
- `2026-11-05-05`: `LP Rush - Hemispheres (1978) - (Vinil Usado)` (R$ 80, `G+/VG+`, 4 fotos, `publicar=nao`, alerta `capa não confere com o Discogs`).
- `2026-11-05-06`: `LP Vários - The Concert For Bangla Desh (1971) - (Vinil Usado)` (R$ 350, `VG+/VG+`, 4 fotos: capa, contracapa lisa, 3 discos recortados em proporção `2,55` e `capa interna` de `IMG_3221.JPG` depois dos discos; descrição `"Caixa com 3 LPs"`, `publicar=nao`, alerta `capa não confere com o Discogs`).
- `2026-11-05-07`: `LP The Velvet Underground - Now Playing (2024) (Vinil Cinza) - (Vinil Usado)` (R$ 300, `NM/NM`, 4 fotos, `publicar=sim`).
- Planilha Google: 7 rascunhos gravados em `cadastro_rascunhos` e 34 linhas em `cadastro_fotos`.
- Arquivos movidos para `J:\Meu Drive\Cadastro de Discos\entrada\processadas\2026-11-05\` (35 fotos renomeadas + 7 capas auxiliares `discogs_*.jpg`; nenhuma foto apagada).
- Ajustes de motor: `fotos.py` e `cadastro_lote.py` aceitam proporção entre 1 e 3 em `cantos` (para fotos de 3 discos lado a lado), recorte antes do cálculo de `distancia_capas`, papel `rótulo` em `ORDEM_PAPEIS`, ordem manual opcional por foto em `lote.json` e `User-Agent` ao baixar capa do Discogs.

Verificação: 800 testes Python passaram, 1 ignorado; auditoria de publicação com 139 arquivos versionados e 0 problemas.

Próximo passo: Túlio revisar e aprovar os rascunhos na aba Cadastro do Painel (as miniaturas e links do Drive entram na próxima rodada da rotina).

# Atualização de sessão D-100, 05/11/2026

Troca de fotos oficiais do Discogs concluída com 100% de sucesso para todos os 23 produtos lacrados do lote 2026-11-03 na Nuvemshop.
- Todos os 23 produtos tiveram fotos oficiais enviadas primeiro na ordem (capa primeiro) e fotos antigas apagadas somente após confirmação.
- Ratos de Porão (2026-11-03-17): release atualizado para 24080759 (edição nacional oficial prensada na Rocinante em vinil esfumaçado).
- Coldplay (2026-11-03-27): release atualizado para 31902511 (edição oficial limitada Pink Translucent em vinil rosa translúcido).
- Juli Manzi (2026-11-03-08): aplicadas capa, 2ª e 4ª foto (pulada a 3ª foto deitada).
- Rita Lee (2026-11-03-25): aplicadas as fotos da edição amarela oficial (Yellow Vinyl).
- Planilha Google: releases e URLs atualizados em cadastro_rascunhos para Ratos e Coldplay; 76 fotos antigas dos 23 produtos marcadas com papel 'referencia' na aba cadastro_fotos.
- Relatório de execução completo salvo em dados/troca_fotos_lacrados_2026-11-03.json.

Verificação: 797 testes Python passaram, 1 ignorado; auditoria de publicação com 139 arquivos versionados e 0 problemas.

Próximo passo: definir próxima etapa do projeto com o Túlio.

# Atualização de sessão D-099, 05/11/2026

Implementação local preparada na pasta pública, sem commit ou chamadas reais. Cadastro com referências privadas, oficiais de lacrado, busca barcode, comparação pHash e conferência de título do rótulo lido pelo agente. Soma de estoque exige confirmação de edição e diário; resultado incerto bloqueia nova tentativa. Checklist físico cruza visibilidade/estoque e registra conferido_em.

Verificação final: 792 testes Python passaram, 1 ignorado; 54 testes JS passaram; Painel.html remontado; auditoria com 0 problemas em 136 arquivos versionados.

Próximo passo: Túlio revisar as mudanças locais e as prévias com dados de teste antes de atualizar a versão do Apps Script em uso. Nenhuma pendência de autorização de negócio para as mudanças da D-099. Implantação e execução reais não foram feitas.

## Avisar o Cowork

D-099: filtros Etiqueta verde/Conferência completa; papéis referencia, codigo_barras e oficial; nova configuração de publicação; colunas capa_discogs_url e conferido_em no fim de cadastro_rascunhos; estados somar_estoque/estoque_somado. Painel.html deve ser atualizado manualmente no Apps Script após revisão. Conferência usa a última sincronização dos produtos. OCR fica com o agente visual, via barcode e rotulo_titulo no JSON.

# Estado do projeto

Atualize este arquivo ao fim de toda sessão. Ele responde a uma pergunta: onde o projeto está agora?

**Última atualização:** 05/11/2026: D-098 concluída com OK parcial do Túlio (21 linhas do lote 2026-10-28 aprovadas na planilha; 5 mantidas em rascunho com pendências tratadas, sendo 19 e 32 com cantos recalculados e novas prévias recortadas salvas em previas_d098/; Passarim isolado; Caetano Veloso publicado). 136 testes pytest verdes e auditoria de publicação com 0 problemas.

## D-098 · Correção de recorte com EXIF 8, prévias do lote 2026-10-28 e reconciliação (05/11/2026)
- **Diagnóstico e correção em `fotos.py`:**
  - Identificada causa raiz dos 27 erros do lote `2026-10-28`: fotos verticais com `Exif Orientation: 8` e cantos calculados com giro `"ccw"` em relação à imagem crua. Ao transpor via EXIF, largura e altura se invertiam estourando limites e gerando `ValueError('cantos fora da imagem')`.
  - Ajustado `painel_monstro/saidas/fotos.py` para validar cantos na imagem crua quando falharem na transposta, aplicando recorte e rotação corretos.
  - Teste unitário adicionado em `tests/test_cadastro.py` (`test_exif_orientation_8_com_giro_ccw`).
- **Passarim e Caetano Veloso:**
  - Linha `2026-10-28-13` (Passarim): alterada para status `rascunho` com a pendência `"confirmar se é outro exemplar (já houve um descartado como duplicado)"`.
  - Linha `2026-10-26-30` (Caetano Veloso): foto 4 (`disco`) enviada para o produto `376745518` na Nuvemshop, manifesto do diário `cadastro_execucao` atualizado e status alterado para `publicado`.
- **Aprovação e prévias:**
  - 21 linhas voltaram para status `aprovado` na planilha: `2026-10-28-08`, `09`, `11`, `15`, `16`, `17`, `18`, `20`, `21`, `22`, `23`, `24`, `25`, `26`, `27`, `28`, `29`, `31`, `33`, `36` e `37`.
  - 5 linhas mantidas como `rascunho` com pendências indicadas:
    - `2026-10-28-19` (Chico Buarque): cantos de capa, contracapa e encarte recalculados; pendência `capa sem recorte`; nova prévia em `previa_nova_2026-10-28-19.jpg`.
    - `2026-10-28-32` (Cesar Costa Filho): cantos de capa e contracapa recalculados; pendência `capa sem recorte`; nova prévia em `previa_nova_2026-10-28-32.jpg`.
    - `2026-10-28-30` (Tom & Dito): pendência `"conferir se a foto da capa não é a contracapa"`.
    - `2026-10-28-35` (Os Originais do Samba): pendência `"título não confere: na capa está Alegria de Sambar"`.
    - `2026-10-28-34` (Vários - Samba... Oba!): título corrigido para `Percussonic Series` e mantido como rascunho.

## D-097 · Livros na loja, categorias fora da comissão e lista de marcar vinil (04/11/2026)
- **Parte 1 · Livros na loja (formato "livro"):**
  - Implementado suporte a formato `livro` em `scripts/cadastro_lote.py` e `painel_monstro/saidas/cadastro.py`: título `Livro <Título> - <Autor>`, categoria `Livros`, tags `Livro, Livro de Música`, descrição autoral com tópicos técnicos e tópico `• Novo`. Dispensa notas de capa/vinil e etiqueta. Fotos com recorte padrão `inteira` sem cantos.
  - Coletados metadados de 23 livros da editora Garota FM Books (autores, páginas, ISBNs, dimensões, pesos reais e capas originais em alta resolução salvas em `J:\Meu Drive\Cadastro de Discos\entrada\livro-<slug>.jpg`). Paul McCartney esgotado ficou de fora.
  - Lote `2026-11-04-livros` criado e conferido com 0 erros e 0 avisos em `conferencia.md`.
  - Pendência do Túlio: criar a categoria `Livros` no administrador da Nuvemshop antes da sincronização na loja.
- **Parte 2 · Categorias inteiras sem comissão:**
  - Configuração `Comissão: categorias sem comissão` (padrão inicial: `Livros`), editável na interface em "Percentual e taxas".
  - `comCalc` deduz proporcionalmente da base líquida do pedido os itens pertencentes a essas categorias (mapeados da aba `produtos`), sem duplicar com produtos individuais de `comissao_produtos`.
  - Quadro de comissão (`cm-wf`) exibe linha dedicada `Categorias sem comissão (Livros) (N pedidos): R$ X`. Critérios gravados no histórico.
  - Teste JS em `teste_local.js` cobrindo pedido misto (disco + livro) com dedução exata e não duplicidade.
- **Parte 3 · Lista para marcar o vinil na loja física:**
  - Coluna `marcado_vinil` adicionada a `cadastro_rascunhos`.
  - Painel Web: filtro "Marcar no vinil" mostrando total pendente de discos `criado` ou `publicado` sem marcação, excluindo livros (`cdEhLivro`).
  - Cards grandes para celular com ID, preço, quantidade, status e checkbox "Marcar no vinil" com gravação imediata na planilha e banner de desfazer (10s).
  - Botão "Imprimir lista" com estilos específicos em `@media print`.
- **Testes e compilação:**
  - `Painel.html` recompilado com sucesso via `montar_painel_web.py`.
  - 53 testes JS verdes em `apps-script/teste_local.js`.
  - Teste unitário Python verde em `tests/test_cadastro_lote.py`.
  - Auditoria de publicação (`scripts/auditar_publicacao.py`) com 136 arquivos e 0 problemas.
- **Painel Web (`apps-script/painel-web/painel-monstro.html` e `Painel.html`):**
  - O bloco "Editar cadastro" (antigo "Título, descrição e observação") abre por padrão para rascunhos (`<details class="fmsg" open>`).
  - Novos campos editáveis com gravação seletiva do que mudou:
    - `categorias`: campo texto com sugestões automáticas baseadas em produtos similares da aba `produtos`.
    - `capa`: select com notas Goldmine (`M NM VG+ VG G+ G F`) para usados, sincronizando em tempo real com a linha "• Capa" da descrição e omitido para novo/lacrado.
    - `tags`: campo texto livre.
    - `peso_kg`: campo numérico decimal com texto de ajuda dos padrões de peso da loja.
    - `discogs_url`: campo texto URL.
  - Editor interativo de fotos: reordenação com setas subir/descer (▲/▼), dropdown com todos os papéis aceitos e checkbox "Não usar" (atribui papel etiqueta). Gravação pontual em `cadastro_fotos` e limpeza de `fotos_ajustadas` em `cadastro_rascunhos` para reprocessamento de prévias pela rotina.
  - Validações antes de salvar: título sem travessão, preço positivo quando preenchido, peso entre 0,1 e 2 kg quando preenchido, categorias obrigatórias.
  - Produtos já criados ou publicados: permanecem sem edição direta e exibem aviso com link para o administrador da Nuvemshop (`https://monstrodiscos.lojavirtualnuvem.com.br/admin/products/<produto_id>`).
  - Estoque infinito (sob demanda e pré-venda): caixa "Sob demanda (estoque infinito)" ao lado da quantidade em cards de novo/lacrado e pré-venda. Quando marcada, grava `estoque = "infinito"` e desabilita a quantidade. Botão aprovar aceita "infinito" sem exigir número. Usado continua exemplar único (1), ignorando infinito e sem a caixa na interface.
- **Motor Nuvemshop (`painel_monstro/saidas/cadastro.py`):**
  - `eh_estoque_infinito(linha)`: reconhece `infinito`, `∞` e `sob demanda` (case-insensitive) para novos/lacrados/pré-venda e sempre `False` para usados.
  - `corpo_produto`: monta variante com `stock_management: False` e sem o campo `stock` quando for estoque infinito, conforme documentação oficial da API da Nuvemshop para variantes (`https://tiendanube.github.io/api-documentation/resources/product-variant`).
  - `estoque_da_linha`: retorna `None` para infinito e 1 para usados.
- **Testes e compilação:**
  - 12 testes novos em Python (`tests/test_cadastro.py`) cobrindo `eh_estoque_infinito`, `estoque_da_linha` e montagem de variantes.
  - 3 testes novos em JS (`apps-script/teste_local.js`) cobrindo funções de infinito, renderização de cards e validações de salvar.
  - `Painel.html` recompilado com sucesso via `montar_painel_web.py`.
  - Suíte completa: 782 testes pytest verdes, 51 testes JS verdes e auditoria de publicação com 0 problemas.

## Lote 2026-11-03 · Gravação de 30 discos (1 usado Belchior e 29 lacrados) e correção Baby Consuelo (04/11/2026)
- **Correção Baby Consuelo (linha 118, ID 2026-10-28-68):** corrigido título para `LP Baby Consuelo - Kryshna Baby (1984) - (Vinil Usado)`, pasta para `68 Baby Consuelo - Kryshna Baby (1984)`, ficha para CBS 138.261 Brasil 1984, descrição e tags atualizadas com Kryshna Baby, release Discogs 4886376 vinculado e pendência de conferir título na capa removida.
- **Lote 2026-11-03 gravado na Planilha Google:**
  - 30 rascunhos adicionados a `cadastro_rascunhos` (`2026-11-03-02` a `2026-11-03-31`) com status `rascunho`, estoque 1, preços das etiquetas, tags completas e links/IDs do Discogs.
  - Subcategorias de gênero oficiais da loja atribuídas aos lacrados (`MPB - Música Popular Brasileira`, `Rock / Pop Nacional`, `Hard Rock / Heavy Metal / Metal`, `Pop`, `Rock Progressivo / Psicodelico`, `Indie / Rock Alternativo`, `Samba / Pagode`, `Rock / Pop Internacional`).
  - Ficha técnica oficial (gravadora, catálogo, país) e faixas (tracklist) preenchidas a partir do Discogs para os 24 títulos catalogados.
  - Duplos configurados com peso 0,80 kg (Juli Manzi, Pink Floyd The Endless River, Pink Floyd The Wall, Black Sabbath).
  - 4 casos pulados: `d05` Forfun "Nu" (somar estoque no produto existente ID 378148677), `p01` expositor da loja física, `p02` sobras antigas e `p03` 79 fotos HEIC de discos usados da loja física pertencentes a lotes de usados.
  - 97 fotos registradas em `cadastro_fotos` e renomeadas na pasta de entrada local.
- **Testes e auditoria:** 770 testes passando no pytest e `scripts/auditar_publicacao.py` com 0 problemas.

## D-095 · Conversão HEIC e formato lacrado no agente local (03/11/2026)
- **Comando `converter-heic`:** adicionado a `scripts/cadastro_lote.py` com `pillow-heif` (qualidade 92, preservando metadados EXIF com DateTimeOriginal e pulando arquivos já convertidos). Executado com sucesso convertendo 79 fotos HEIC da pasta `Discos Monstro` para `.jpg` na raiz da entrada.
- **Suporte a `formato: "lacrado"`:** implementado em `derivar_lote` e `validar_lote`, dispensando notas Goldmine e tópicos de estado na descrição, validando tags com `LP, LP Novo, Vinil Lacrado`, títulos no formato `LP <Artista> - <Álbum> (<Ano>) - (Novo/Lacrado)` (com detalhes de cor, duplo e importado quando houver) e categorias `LP, Novo/Lacrado, Nacionais/Importados, Novidades`.
- **Lote 2026-11-03 estruturado e conferido:** 31 discos para cadastrar (Belchior com fotos completas e 30 discos lacrados com fotos da capa e imagens complementares do Discogs) e 3 grupos pulados (loja, sobras antigas e fotos avulsas). Conferência executada com 0 erros e 84 avisos informativos, gerando `conferencia.md` e prévias. Aguardando aprovação do Túlio para gravação real com `--confirmar`.
- **Testes e auditoria:** 2 testes novos em `tests/test_cadastro_lote.py` (770 testes passando) e `scripts/auditar_publicacao.py` com 0 problemas.

## D-092 · aba K7 e nível de acesso restrito "k7" no Cofre e no Painel (29/10/2026)
- **Rotina e módulo k7.py:** a cada rodada, gera a aba `k7_resumo` (formato `bloco, chave, valor_1, valor_2, valor_3, valor_4`) com métricas da fita K7 Goiânia Rock City 2026 (produto 375734821, campanha `grc2026`): blocos `totais`, `por_dia`, `por_banda`, `canais` e `junto_com`.
- **Privacidade absoluta garantida:** conferência em código e testes sintéticos garantem que a aba `k7_resumo` nunca expõe nomes, emails, telefones, cidades ou números de pedidos.
- **Painel (`painel-monstro.html` e `Painel.html`):** aba K7 dedicada na barra de navegação com KPIs grandes, gráfico diário de vendas, ranking de bandas por cliques/sessões/pedidos do GA4, canais de venda e produtos mais comprados em conjunto.
- **Nível restrito `k7` no Cofre (`Cofre.gs`):** `usuario_` aceita nível `k7`; `ler_` aplica whitelist estrita `ABAS_K7` (`k7_resumo` e `ga4_links`), retornando listas vazias (`[]`) para qualquer outra faixa solicitada; `podeGravar_` retorna `false`.
- **Comportamento para usuário `k7` no Painel:** esconde a barra de abas `.tabs`, fixa a visualização na aba K7 e faz requisição ao Cofre exclusivamente para as faixas `k7` e `g4l`.
- **Testes verdes:** 767 testes no pytest (`tests/test_k7.py` e regressão de `test_rotina.py`) e 48 testes no suite JS (`apps-script/teste_local.js`).

## D-091 · recorte de fotos por detecção de fundo branco e comando recortar-lote (29/10/2026)
- **Detecção de fundo branco:** para fotos em pé (H > W) e fundo claro, reduz para 500 px de largura, segmenta por limiar de cinza (< 235 e limiares adaptativos com fechamento morfológico) e contorno principal. Capas e encartes usam minAreaRect com 1% de margem; vinil usa quadrado com 2% de folga e rejeita diâmetros < 50% do menor lado (eliminando recortes falsos no rótulo central). Fallback transparente para o método Hough anterior e foto inteira em caso de falha dupla.
- **Comando recortar-lote LOTE [--confirmar]:** recalcula cantos em lote para fotos já registradas em cadastro_fotos (exceto etiqueta), gera miniaturas individuais em dados/cadastro_ia/<lote>/previas/ e folhas de contato em dados/cadastro_ia/<lote>/folhas_previas/. Com --confirmar, atualiza em lote apenas a coluna cantos de cadastro_fotos e limpa fotos_ajustadas em cadastro_rascunhos.
- **Lote 2026-10-28 gravado na planilha:** após OK do Túlio, executado `recortar-lote 2026-10-28 --confirmar`. Cantos de 335 fotos atualizados em `cadastro_fotos` e coluna `fotos_ajustadas` limpa em `cadastro_rascunhos`. Nas próximas 4 a 5 rodadas da rotina, as miniaturas ajustadas serão geradas na loja (20 discos por vez). Push de D-089 e D-091 enviado ao repositório público `painel-monstro-publico`.
- **Testes sintéticos e regressão:** 4 testes novos em tests/test_cadastro_lote.py (foto em pé com disco grande, capa clara sobre fundo branco com sombra leve, rejeição de rótulo pequeno e simulação/confirmação do comando). Suíte completa com 757 testes passando.

**Última atualização:** 29/10/2026: D-089 (indicações da Fila mais certeiras: gênero fino primeiro, bônus para mesmo artista/coocorrência, modelo G45_GERAL sem recomendação quando sem gênero confiável, KW de Metal ampliado e formato natural "Álbum, do Artista"). Suíte completa com 753 testes verdes.

## D-089 · indicações da fila (G45 e VIP) mais certeiras (29/10/2026)
- **Gênero fino primeiro:** `generos.subcategorias` e `fila_unica.escolher_sugestoes` priorizam discos em estoque da mesma subcategoria da loja (ex.: "Hard Rock / Heavy Metal / Metal", "MPB - Música Popular Brasileira", "Rock / Pop Nacional", "Samba / Pagode", "Jazz / Blues", "Sertanejo", etc.). Só se não houver estoque na subcategoria cai para a família ampla. Cliente de MPB recebe MPB e não sertanejo; Violator nunca recebe MPB.
- **Desempate e bônus:** desempate prioriza discos do mesmo artista (+2) e artistas que aparecem juntos nos pedidos de outros clientes (`coocorrencias_de_artistas`, +1).
- **Sem gênero confiável:** produto sem subcategoria de gênero e artista fora de KW usa mensagem geral sem recomendação específica (`G45_GERAL`). Modelo adicionado aos padrões da aba `Mensagens`.
- **Bandas de Metal nacional:** lista `KW['Metal']` ampliada com Violator, Korzus, Torture Squad, Dorsal Atlântica, Nervosa, Crypta e Shaman (Sepultura, Angra, Krisiun e Viper já existiam).
- **Formato natural na mensagem:** `nome_do_disco_mensagem` gera formato de conversa "Álbum, do Artista" (ex.: "Rasta, do Pepeu Gomes" em vez de "Rasta (Pepeu)").

## Lote 2026-10-28 · cadastro de 93 discos por agente local (29/10/2026)
- **Lote `2026-10-28` gravado:** 346 fotos na pasta `entrada`. 4 casos pulados (`d01` a `d03` de sobras antigas e `d84` de Country & Western 2 sem capa frontal). Gravados 93 rascunhos (`2026-10-28-03` a `2026-10-28-95`) em `cadastro_rascunhos` e 338 fotos em `cadastro_fotos`. 339 arquivos renomeados na pasta local de entrada. Preços mantidos em branco para preenchimento manual pelo Túlio no Painel.

## D-085 · garimpo aceita nome de produto colado (27/10/2026)

- `garimpo.palavras_do_pedido`: artista obrigatório; no disco ignora parênteses, anos, formato/estado e palavras curtas; com "/" ou ":" vale o primeiro trecho; cor do pedido obrigatória; disco só com ano mantém o ano. Nenhuma aba mudou. Disco de uma letra/sigla (Maglore "V", "D.O.L.L.") casa com qualquer disco do artista: Túlio confirmou que fica assim, ele confere na Fila se serve.

## D-078 · cadastro de discos por agente local (`scripts/cadastro_lote.py`, 27/10/2026)

- **Script `scripts/cadastro_lote.py`:** implementa os subcomandos `folhas`, `recorte`, `conferir`, `gravar` e `renomear-lote` conforme `docs/CADASTRO_IA_SCRIPT.md` e `docs/CADASTRO_IA.md`, lendo `CADASTRO_PASTA_LOCAL` (padrão `J:\Meu Drive\Cadastro de Discos\entrada`) em `painel_monstro/config.py`. Reproduz byte a byte as 35 linhas de `cadastro_rascunhos` e as 141 linhas de `cadastro_fotos` do lote de referência `2026-10-26` e atinge 92,1% de acerto automático de cantos nas fotos reais (meta >= 90%).
- **Lote `2026-10-27` gravado:** 29 fotos na pasta `entrada` agrupadas em `dados/cadastro_ia/2026-10-27/lote.json`: 7 grupos pulados (`d01` a `d07`: 3 de imagens avulsas/lacrados do Discogs, 2 de sobras do lote 2026-10-26, 1 disco consignado de bolinha prata Beto Guedes e 1 foto avulsa de Roberto Carlos já publicado) e 2 rascunhos gravados em `cadastro_rascunhos` e `cadastro_fotos` com as 12 fotos renomeadas na pasta `entrada` (`2026-10-27-01` LP Jon Bon Jovi - Blaze of Glory 1990 R$ 100 VG+/VG+ e `2026-10-27-02` LP Nenhum de Nós - Cardume 1989 R$ 75 VG+/VG+).

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
