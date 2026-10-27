# Cadastro de discos, Discogs, UTMs e correções de frete · especificação (Etapa 10)

Pedido do Túlio em 15/10/2026. Piloto feito no Cowork com 11 discos (aba `cadastro_rascunhos`, lote 2026-10-15).
Decisões do Túlio: título padrão `LP Artista - Título (Ano) - (Vinil Usado)`; disco usado é sempre exemplar único
(cadastro novo, estoque 1, nunca soma estoque); só disco novo soma estoque; o app da Nuvemshop tem acesso total;
fotos vêm do celular para uma pasta no Google Drive; peso padrão aprovado (abaixo).

## Divisão do trabalho

| Etapa | Quem | O quê |
|---|---|---|
| 1. Fotos | Túlio | Primeira foto de cada disco: a etiqueta de preço (no plástico) junto da capa. Depois capa, contracapa, encartes, disco e rótulo, nessa ordem, um disco de cada vez. Sobe para a pasta do Drive `Cadastro de Discos/entrada`. |
| 2. Identificação | Cowork (visão) | Agrupa as fotos por disco pelo horário, identifica a edição (rótulo, catálogo, verso), lê o preço na foto da etiqueta, avalia a capa (Goldmine), lista o que vem junto e o que falta, marca os 4 cantos de capas e encartes para o recorte, escreve a descrição. Grava linhas em `cadastro_rascunhos` (status `rascunho`) e `cadastro_fotos`. |
| 3. Dados | Rotina (este repositório) | Discogs pela API, preço sugerido pelo histórico, peso e medidas padrão, ajuste das fotos. |
| 4. Revisão | Túlio no Painel (aba Cadastro, Cowork faz) | Confere vinil, preço e pendências; muda status para `aprovado`. |
| 5. Publicação | Rotina | Cria o produto oculto na Nuvemshop com as fotos na ordem; grava `produto_id` e `link_loja`; status `criado`. Túlio publica manualmente na Nuvemshop após conferir. A chave de publicar direto não libera visibilidade nesta etapa. |

## Regras que não mudam

- Escrita nova na loja liberada pelo Túlio: **criar produto** (POST /products) e **subir imagens** (POST /products/{id}/images). Somente para linhas com status `aprovado`. Nunca alterar nem apagar produto existente por esta etapa.
- Produto nasce sempre com `published: false` (oculto), conforme trava explícita do Túlio. A chave de publicar direto permanece reservada, sem liberar publicação.
- Idempotência: se a linha já tem `produto_id`, não cria de novo. Grave `produto_id` logo após o POST, antes das imagens.
- Tokens só em Secrets: `DISCOGS_TOKEN` (novo), Nuvemshop e Google como já estão.
- Nenhum dado de cliente nas abas `cadastro_*`.
- Fotos originais nunca são apagadas; o ajuste gera cópias.

## Abas

`cadastro_rascunhos` (já existe, criada pelo Cowork; colunas na ordem):
id, lote, pasta, status, titulo, marca, categorias, ficha, descricao, capa, vinil, preco, preco_referencia, peso_kg,
altura_cm, largura_cm, comprimento_cm, discogs_url, discogs_confianca, pendencias, fotos, seo_titulo, seo_descricao, tags,
produto_id, link_loja, observacao_tulio, atualizado_em
- status: `rascunho` (Cowork) → `aprovado` (Túlio, pelo Painel) → `criado` / `erro: <motivo>` (rotina) → `publicado` (quando a loja mostrar visível).
- descricao: parágrafos separados por linha em branco e tópicos com "• ". Converter para HTML simples (`<p>` e `<ul><li>`).
- categorias: nomes separados por vírgula; mapear para IDs com GET /categories (subcategorias de LP > Usado pelo nome; "Novidades" é categoria própria). Se um nome não existir, status `erro: categoria X não existe` (não criar categoria).

`cadastro_fotos` (Cowork mantém os metadados; a rotina só completa IDs vazios conforme ajuste abaixo): id_disco, ordem, papel, arquivo_drive_id, cantos (JSON com 4 pontos na escala de 500 px de largura, mais proporção e rotação opcionais), observacao.
Exemplo de cantos: `[[40,133],[466,133],[466,557],[44,557]]`; espalhado aberto: `[[30,112],[465,100],[462,322],[33,327],2]`; com giro: `[...,1,"ccw"]`.

## Ajuste das fotos (módulo `painel_monstro/saidas/fotos.py`)

Copiar a lógica de `Cadastro de Discos/_sistema/processar.py` (testada no piloto, 64 fotos):
- Girar pela orientação EXIF; aplicar o giro extra de `cantos` quando houver.
- Capa, contracapa, encartes: transformação de perspectiva pelos 4 cantos com margem de 0,6%, saída 1600×1600 (ou 1600×800 se proporção 2).
- Disco: círculo por HoughCircles, recorte quadrado com 4% de folga; se não achar, quadrado central.
- Rótulo: quadrado central.
- Sem cantos: imagem inteira com o lado maior em 1600 px.
- JPEG qualidade 86 (cerca de 300 a 700 KB por foto). Ordem do site = `ordem` da `cadastro_fotos`.
- Pasta do Drive: ler `entrada`, gravar as ajustadas em `site/<id_disco>/` (conta de serviço com acesso de editor à pasta).

## Discogs (módulo `painel_monstro/coletor/discogs.py`)

- Autenticação: cabeçalho `Authorization: Discogs token=<DISCOGS_TOKEN>` e `User-Agent: PainelMonstro/1.0 +https://lojamonstro.com.br`. Limite 60 pedidos por minuto: espaçar 1,1 s e respeitar `X-Discogs-Ratelimit-Remaining`.
- Se `discogs_url` existe: GET `https://api.discogs.com/releases/{id}`. Se não: GET `/database/search?type=release&catno=<catálogo>&country=Brazil&format=Vinyl` e, sem resultado, `q=<artista título>`; só aceitar com 1 resultado ou com catálogo idêntico; senão deixar `discogs_confianca = baixa` e não preencher.
- Gravar em colunas novas no fim de `cadastro_rascunhos`: discogs_id, faixas (texto "A1 Nome (3:36)" por linha), creditos (produção, músicos principais, capa; até 400 caracteres), discogs_menor_preco e discogs_a_venda (de GET `/marketplace/stats/{id}?curr_abbr=BRL`, quando houver).
- Nunca usar imagens do Discogs na loja (termos de uso); só as fotos da Monstro.
- Acrescentar as faixas ao fim da descrição como "Lado A: … / Lado B: …" somente se a linha tiver `faixas_na_descricao = sim` (padrão: não).

## Preço

- `preco` vem da etiqueta fotografada (lida pelo Cowork) e grava `preco_origem = etiqueta`. Etiqueta ilegível ou ausente: `preco` vazio e pendência "conferir preço". Linha `aprovado` sem preço não vira produto (status `erro: sem preço`).
- A foto da etiqueta tem papel `etiqueta` na `cadastro_fotos` e **nunca** sobe para o site.
- Lote piloto 2026-10-15: preço 200 em todos, só para teste.

`preco_referencia` = mediana dos preços de produtos com o mesmo artista e título (aba `produtos`, normalizando acentos e o sufixo "(Vinil Usado)"); se não houver, mediana do artista em usados dos últimos 24 meses. A referência serve para o Túlio comparar; nunca substitui o preço da etiqueta.

## Peso e medidas padrão (aprovado)

LP usado simples 0,50 kg; LP com capa dupla ou encarte grosso 0,55 kg; LP duplo 0,80 kg; compacto 0,20; CD 0,20; fita K7 0,17.
Medidas de todos: altura 2,5 cm, largura 32 cm, comprimento 32 cm. A Nuvemshop usa centímetros: nunca gravar 0,32.

## Correções de peso e medidas existentes: NÃO EXECUTAR SEM AUTORIZAÇÃO

O dono da loja precisa autorizar. A lista está em `Correcoes-peso-e-medidas-Monstro.xlsx` (pasta do projeto). Implementar o
script `scripts/corrigir_frete.py` que lê essa planilha e altera **só** peso e medidas (PUT /products/{id}/variants/{variant_id})
das linhas com "Sim" na coluna Autoriza, com modo simulação por padrão (`--aplicar` para valer) e relatório antes/depois.
Não rodar no Actions até o Túlio escrever "pode aplicar as correções de frete".

## Origem das vendas (UTM)

- Conferir na documentação e em um pedido real (só leitura) se a API de pedidos devolve a URL de entrada (`landing_url`, ou campo equivalente) e o `referrer`.
- Se devolver: acrescentar no fim da aba `pedidos` as colunas utm_source, utm_medium, utm_campaign, utm_content, origem (sem dado pessoal; extrair só os parâmetros, nunca gravar a URL inteira se tiver email ou token).
- `origem` derivada: email (utm_medium=email ou source=brevo), meta_ads (fbclid ou utm_source=facebook/instagram e medium=paid/cpc), instagram_organico, google (gclid ou source=google), whatsapp, direto/organico.
- Se não devolver: registrar em DECISOES e ESTADO que a origem por UTM precisa de outro caminho (por exemplo, script na loja gravando a UTM no carrinho) e parar.

## Testes e fechamento

Testes sem rede para: conversão da descrição em HTML, mapa de categorias, idempotência do POST, foto com e sem cantos (incluindo proporção 2 e giro), busca Discogs com 0, 1 e vários resultados, preço sugerido, parser de UTM.
Decisão D-067 em DECISOES.md, bloco "Avisar o Cowork" no ESTADO.md com as colunas finais, commit e push.


## Entrega D-067, 15/10/2026

Implementado e testado sem escritas reais na loja. A rotina enriquece rascunhos e processa aprovados, com falha isolada. Publicação final continua manual na Nuvemshop; a rotina detecta `published: true` por GET e marca publicado. Não há atualização de estoque de produtos existentes nesta etapa.

Entrada confirmada: pasta privada registrada na linha `Cadastro: pasta de entrada Drive (ID)` da Configuração. A conta de serviço conseguiu consultar entrada e pasta pai com permissão de adicionar arquivos. Upload real ainda não foi testado: permissão de Editor não garante cota de armazenamento da conta de serviço em Meu Drive. Se o Drive recusar a criação por cota/propriedade, preservar rascunho e usar Drive compartilhado ou autenticação da conta proprietária em uma próxima configuração autorizada. Não aprovar lote antes de conferir prévias.

Copiados somente `processar.py` e `cantos-2026-10-15.json` para `referencia/cadastro_piloto/`; 45 marcações do piloto são comparadas com imagens sintéticas. Nenhuma foto foi copiada para o git. O Cowork preenche cadastro_fotos; a rotina não descobre cantos nem lê preço por OCR.

Colunas novas, no fim dos 28 campos existentes: `discogs_id, faixas, creditos, discogs_menor_preco, discogs_a_venda, faixas_na_descricao, preco_origem, cadastro_execucao, fotos_ajustadas`. As duas últimas são da rotina: diário de idempotência e JSON das cópias privadas ajustadas (`ordem`, `papel`, `arquivo_drive_id`). O painel deve exibir as prévias autenticadas pelo Drive, nunca tornar fotos públicas. `faixas_na_descricao` vazio equivale a não.

O diário sobrevive à perda do cache do Actions porque também fica na planilha. POST incerto é reconciliado por SKU; se não houver confirmação, bloqueia para revisão. Imagem com resposta incerta também bloqueia, sem repetição automática. Para retomar erro após conferir, Túlio volta o status a aprovado, mantendo ID e diário. Nunca limpar esses campos para tentar novamente. Alteração de fotos depois de uma criação parcial é bloqueada. Não executar rotina local em paralelo ao Actions.

### Como conferir e ativar

1. GitHub do projeto > Settings > Secrets and variables > Actions > New repository secret. Name: `DISCOGS_TOKEN`; Secret: token pessoal do Discogs. Não enviar a chave na conversa. Sem token, cadastro continua disponível sem enriquecimento Discogs.
2. Cowork integra as colunas finais e preenche `cadastro_fotos`, com IDs das imagens diretamente na entrada. Manter rascunho enquanto conferir prévias, título, categorias, preço real e conservação. Os R$200 uniformes do lote piloto são teste, não preço confirmado.
3. Actions > Rotina do Painel > Run workflow > main > Run workflow. Não marcar baixar tudo nem reconstruir anúncios para um cadastro comum. Rascunho gera prévia; somente aprovado cria produto oculto. Primeira criação real ainda depende dessa revisão humana.
4. Conferir produto_id, status criado e imagens no administrador da Nuvemshop. Publicar manualmente quando estiver correto. A rodada seguinte reconhece publicado.

### Frete e origem por UTM

A planilha de correção foi localizada em `C:\Users\tulio\Claude\Projects\Monstro Discos\Correcoes-peso-e-medidas-Monstro.xlsx`. O script aceita IDs ou resolve o link da loja por GET com handle único, altera só weight/height/width/depth e grava relatório em dados/correcoes-frete (fora do git). Está pronto, mas NÃO foi executado contra a loja, nem em simulação. Não está no Actions. Autorização do dono e a frase escrita do Túlio são pendências separadas; não executar para testar.

UTM: documentação oficial de pedidos e consulta real de lista, detalhe e client_details não disponibilizaram landing_url/referrer ou equivalente utilizável. `order_origin` veio vazio. Nenhuma coluna foi acrescentada a pedidos e nenhuma origem foi inferida. Parser puro está testado, porém desconectado da coleta. Captura no site/carrinho exige outra implementação autorizada; esta parte para aqui conforme a especificação.


### Ajuste: localizar fotos pelo nome, 15/10/2026

Se `arquivo_drive_id` estiver vazio, a rotina lista os arquivos diretamente na entrada cujo ID está na Configuração e compara o nome exatamente com `observacao`, incluindo extensão, espaços e maiúsculas. Não usa busca aproximada, outras pastas, subpastas ou lixeira. Percorre todas as páginas para detectar homônimos. Só com um resultado grava o ID na célula de `arquivo_drive_id`; nunca troca um ID existente nem altera as demais colunas.

Todas as fotos daquele disco, inclusive etiqueta, precisam ser resolvidas antes das prévias ou criação do produto. Nome ausente, inexistente ou repetido gera linha `Fotos por nome: ...` em `pendencias`, preservando outras pendências e status atual, sem criar produto. Ao corrigir e rodar novamente, a pendência automática é retirada. Etiquetas continuam fora das imagens da loja. A escrita dos IDs é agrupada por disco, depois de conferir que o Cowork não alterou as linhas; se alguma foto não puder ser resolvida, nenhum ID daquele disco é preenchido nessa tentativa.

Ajuste autorizado explicitamente pelo Túlio, inclusive commit e push. Nenhuma aba ou coluna adicionada/reordenada. Pesquisa conforme a documentação oficial de Drive (`files.list`, `parents`, paginação, `trashed = false`): https://developers.google.com/workspace/drive/api/guides/search-files.

## Cadastro quase imediato (D-068, 15/10/2026)

Depois de aprovar no Painel, o disco aparece oculto na loja em cerca de 3 a 8 minutos, sem esperar a rotina de hora em hora.

- `apps-script/vigia-cadastro.gs` (projeto próprio do Apps Script, abre a planilha pelo ID) olha `cadastro_rascunhos` a cada 5 minutos. Achou `aprovado` sem `produto_id`, pede ao GitHub o workflow **Cadastro de discos aprovados** (`.github/workflows/cadastro.yml`).
- O workflow roda `python -m painel_monstro.rotina --so-cadastro`: coleta incremental (para o aviso de disco repetido e o preço de referência) e só o passo do cadastro. Não grava `rodada`, indicadores, fila nem anúncios.
- Mesma fila (`rotina-painel`) e mesmo cache da rotina: se a rotina estiver rodando, o cadastro espera ela terminar.
- O vigia pede uma vez por conjunto de discos pendentes; se continuarem pendentes 20 minutos depois, pede de novo. Rodada que falha não perde nada: a rotina de hora em hora cria os aprovados do mesmo jeito.

### Ativar (uma vez, Túlio)

1. GitHub > Settings (do usuário) > Developer settings > Personal access tokens > Fine-grained tokens > Generate new token. Resource owner: a conta do repositório; Repository access: Only select repositories > `painel-monstro`; Permissions > Repository permissions > **Contents: Read and write** (é o que o GitHub exige para `repository_dispatch`). Validade: 1 ano.
2. script.google.com > Novo projeto, nome `vigia-cadastro` (projeto separado do script da fila; abre a planilha pelo ID). Colar `apps-script/vigia-cadastro.gs` no `Código.gs`.
3. No projeto `vigia-cadastro`: Configurações do projeto (engrenagem) > Propriedades do script > `GITHUB_TOKEN` = o token.
4. Escolher a função `instalarVigiaCadastro` > Executar > autorizar. Para testar sem aprovar nada: `dispararCadastroAgora` e conferir em Actions.

## Tags (padrão definido em 16/10/2026)

Tags servem para a busca da loja: cada tag tem que ser algo que o cliente digitaria. Padrão da maioria dos produtos da loja, sem acentos:

`Artista, nome popular do artista (se houver), Título do disco, músicos/parcerias relevantes, LP, LP Usado, Vinil Usado, [Disco Duplo], gêneros`

Exemplo: `Antonio Carlos Jobim, Tom Jobim, Passarim, LP, LP Usado, Vinil Usado, MPB, Bossa Nova`.

Não usar o estilo antigo de nome colado (`AntonioCarlosJobim`) nem `colecionável`: ninguém busca assim. Os rascunhos do piloto foram corrigidos na planilha; o Passarim já criado deve ser corrigido à mão no administrador (a rotina nunca altera produto existente).

## Escolher se o disco aparece na loja ao aprovar (D-082, 27/10/2026)

- Coluna `publicar` no fim de `cadastro_rascunhos` (`sim`, `nao` ou vazio; vazio vale como `sim`). Criada automaticamente por `preparar_abas`.
- No Painel (aba Cadastro), cada cartão em revisão mostra a opção **Mostrar na loja assim que for criado**, marcada por padrão. Se a linha tiver pendência de já existir na loja ou de falta de etiqueta de preço, aparece um aviso amarelo ao lado lembrando de conferir antes de deixar visível. Nos cartões aprovados e criados, o Painel mostra se o disco *vai aparecer* ou *fica oculto*.
- Na rotina (`painel_monstro/saidas/cadastro.py`), o produto continua nascendo oculto (`POST /products` com `published: False`) para nunca aparecer sem fotos na loja. Depois que todas as imagens são confirmadas:
  - se `publicar` for `nao`, para em `status = criado` (oculto);
  - se `publicar` for `sim` ou vazio, grava `publicacao_pedida: true` em `cadastro_execucao` antes de enviar `PUT /products/{id}` com `{"published": True}` (único campo aceito pelo método) e muda `status` para `publicado`; se o `PUT` falhar, mantém `status = criado` e acrescenta em `pendencias`: `Não consegui deixar visível; publique à mão na Nuvemshop`, sem repetir o `PUT`.
