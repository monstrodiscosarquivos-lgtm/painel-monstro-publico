# Especificação · script do cadastro por IA (Etapa D-078)

Pedido do Túlio em 26/10/2026: tirar do Cowork a identificação dos discos e a gravação dos rascunhos e passar para agentes que rodam no computador dele (Antigravity, Codex), para economizar. O manual que esses agentes vão seguir já está pronto em `docs/CADASTRO_IA.md`. Leia o manual primeiro: este documento descreve o script que ele usa, `scripts/cadastro_lote.py`.

Material de referência: os scripts em `referencia/cadastro_ia/` (no git) e os dois JSON em `dados/referencia-privada/cadastro_ia/` (fora do git, só neste computador: têm nomes de pessoas, como dedicatórias escritas nos discos, e o repositório é público). Não copie os JSON para dentro do repositório; o teste de regressão que usa esses arquivos deve ser marcado com skip quando eles não existirem.

| Arquivo | O que é |
|---|---|
| `dados/referencia-privada/cadastro_ia/exemplo_lote_2026-10-26.json` | O lote de 26/10/2026 (37 discos) no formato de entrada do script. |
| `dados/referencia-privada/cadastro_ia/linhas_gravadas_2026-10-26.json` | O que o Cowork gravou de fato para esse lote: `rasc` (35 linhas de `cadastro_rascunhos`, 38 colunas) e `fotos` (141 linhas de `cadastro_fotos`). É o resultado esperado. |
| `montar_cowork.py` | Script do Cowork que transformou a identificação nessas linhas. Fonte das regras de derivação. |
| `cantos_cowork.py` | Detecção dos cantos das capas usada no lote (linhas de Hough). |

## Regras fixas

- **Só duas escritas:**
  - acrescentar linhas no fim de `cadastro_rascunhos` e de `cadastro_fotos`;
  - renomear fotos dentro da pasta de entrada local.
- **Nunca:**
  - alterar ou apagar linha existente;
  - mexer em outras abas;
  - apagar ou mover foto;
  - chamar a API da Nuvemshop.
- **Status sempre `rascunho`.** A criação do produto continua com a rotina, depois da aprovação no Painel.
- **Sem rede além do Google Sheets.** Reaproveite `PlanilhaGoogle.conectar(config)` (mesma conta de serviço da rotina, pelo `.env`) e as constantes e funções de `painel_monstro/saidas/cadastro.py`: `COLUNAS`, `FOTOS`, `identidade_titulo`, `texto_normal`, `peso_padrao`, `numero`. Não duplique regra que já existe lá.
- **Modo simulação por padrão.** `gravar` só escreve com `--confirmar`.
- **Travessão (—) proibido** em qualquer texto gravado. O `conferir` dá erro se achar.

## Configuração

Nova linha no `.env` e no `env-exemplo.txt`:

```
CADASTRO_PASTA_LOCAL=J:\Meu Drive\Cadastro de Discos\entrada
```

É a pasta `entrada` sincronizada pelo Google Drive para computador. Renomear ali renomeia no Drive e mantém o ID do arquivo.

Arquivos de trabalho em `dados/cadastro_ia/<lote>/`, que já fica fora do git. O lote é a data de hoje no fuso de São Paulo.

## Comandos

### `folhas [--lote AAAA-MM-DD]`

Fotos novas são os arquivos de imagem (`.jpg`, `.jpeg`, `.png`) da pasta local que atendem às duas condições:

- o nome não aparece na coluna `observacao` de `cadastro_fotos`;
- o nome não começa com o padrão de ID (`^\d{4}-\d{2}-\d{2}-\d+ `).

Ordene pela data EXIF (DateTimeOriginal). Se a foto não tiver EXIF, use o horário que vem no nome e, por último, a data de modificação.

Gere folhas JPEG em `folhas/folha_01.jpg`, `folha_02.jpg` e assim por diante:

- 12 miniaturas por folha (4×3), com cerca de 1600 px de largura no total;
- cada miniatura girada pelo EXIF;
- cada miniatura com um rótulo bem legível: número sequencial e horário (`07 · 11:57:40`);
- uma linha mais grossa entre miniaturas com mais de 60 segundos de intervalo, só como dica visual.

Escreva também `fotos.txt` (número, horário, nome do arquivo) e mostre no terminal quantas fotos novas há e quantas folhas foram geradas.

### `recorte ARQUIVO esq topo dir base [--lote]`

Recorta a foto original (girada pelo EXIF) nas frações dadas, de 0 a 1. O lado maior da saída fica limitado a 1600 px. Grave em `zoom/<arquivo-sem-extensão>_<n>.jpg` e mostre o caminho.

### `conferir LOTE.json`

Lê o arquivo de entrada (formato no manual e no exemplo), valida tudo e mostra o que seria gravado, sem escrever na planilha.

Validações que impedem gravar (erros):

- **Arquivo:** JSON inválido, `lote` ausente, código `disco` repetido.
- **Fotos:**
  - arquivo inexistente na pasta;
  - foto usada em dois discos;
  - foto que já está em `cadastro_fotos`;
  - `papel` fora da lista;
  - disco a cadastrar sem nenhuma foto de `capa`, `contracapa` ou `etiqueta`.
- **Campos do disco:**
  - `acao` diferente de `cadastrar` ou `pular`; `pular` sem `motivo`;
  - `genero` fora da lista do manual;
  - `capa` ou `vinil` fora de `M NM VG+ VG G+ G F`;
  - `preco_etiqueta` que não seja número positivo nem `null`;
  - `artista`, `album`, `descricao` ou `tags` vazios.
- **Texto:**
  - travessão (—) em qualquer campo;
  - descrição sem os tópicos `• Capa <nota>` e `• Vinil <nota>` iguais aos campos;
  - tags sem `LP, LP Usado, Vinil Usado`.
- **Consignado:** `bolinha` contendo "prata" com `acao` `cadastrar`.
- **Cantos manuais:** `cantos` que não formam quadrilátero convexo dentro da imagem. Use a mesma checagem de `fotos.processar`.

Avisos (não impedem):

- **Repetido na loja:** existe produto na aba `produtos` com a mesma `identidade_titulo` e estoque maior que 0. Mostre nome, estoque e `lojamonstro.com.br/produtos/<url>/`.
- **Repetido no Painel:** rascunho em `cadastro_rascunhos` com a mesma identidade e status diferente de `descartado...`.
- **Avaliação incerta:** palavras de exagero na descrição (`imperdível`, `raríssimo`, `obra-prima`) ou `confianca` `baixa`.
- **Recorte:** recorte automático que falhou (a foto sai inteira).

Recorte de cada foto que vai para o site, quando não houver `cantos` manual nem `"recorte": "inteira"`:

- **Capa, contracapa, encartes e capa interna.** Porte `detectar` de `cantos_cowork.py`:
  - Canny e HoughLinesP numa cópia com 1000 px de largura;
  - a borda mais externa de cada lado com comprimento mínimo;
  - interseção das 4 retas;
  - saída em escala de 500 px de largura.

  Encarte aberto ou capa interna com largura/altura entre 1,8 e 2,2 recebe o 5º elemento `2`. Se essa proporção ficar fora de 0,9 a 1,12 e de 1,8 a 2,2, descarte os cantos e use a foto inteira. Nas capas e contracapas comuns, descarte também os cantos se a proporção sair de 0,85 a 1,15.
- **Disco.** Neste formato o disco ocupa pouco da foto, então o círculo de `fotos.processar` (raio de 35% a 52%) não acha. Detecte o círculo com:
  - imagem com 800 px de largura, cinza com `medianBlur 5`;
  - `HoughCircles(dp=1.5, minDist=400, param1=100, param2=40)`, raio de 10% a 22% da largura;
  - cantos = quadrado com lado 2×raio×1,04 em volta do centro, em escala de 500 px.

  Sem círculo, sem cantos: `fotos.processar` cai no quadrado central.
- **Etiqueta.** Não recebe cantos (nunca vai para o site).

Confirme a detecção com as fotos reais: as 141 linhas de `linhas_gravadas_2026-10-26.json` têm os cantos que o Cowork usou, e as fotos `IMG_20261025_*.jpg` ainda estão na pasta de entrada. Meta: pelo menos 90% dos cantos a até 2% da largura (10 px na escala 500) do valor de referência. Não é necessário reproduzir os 9 casos marcados como `"recorte": "inteira"` no exemplo.

Prévias: para cada disco, rode `fotos.processar(bytes, papel, cantos)` em cada foto do site e monte uma folha `previas/<disco>.jpg` com as miniaturas na ordem do site e um cabeçalho com o título derivado. É exatamente o que a loja vai receber.

Relatório `conferencia.md`, com:

- erros e avisos, por disco;
- tabela com disco, título, preço, capa/vinil, número de fotos e pendências;
- a última linha "pronto para gravar" ou "corrigir antes de gravar".

Mostre no terminal um resumo e o caminho do relatório.

### `gravar LOTE.json [--confirmar]`

Roda o `conferir`; com qualquer erro, para. Depois monta as linhas.

**IDs.** `<lote>-NN` com dois dígitos, continuando do maior NN já existente para aquele lote em `cadastro_rascunhos`. Discos com `pular` não recebem ID.

**Linha de `cadastro_rascunhos`.** Grave pelos nomes do cabeçalho real (leia a linha 1 e confira que contém todas as `COLUNAS`). Derivação, igual a `montar_cowork.py`:

| Coluna | Valor |
|---|---|
| `id`, `lote` | Como acima. |
| `pasta` | `NN Artista - Album (Ano)`. |
| `status` | `rascunho`. |
| `titulo` | `LP Artista - Album (Ano) - (Vinil Usado)`. Duplo: `- (Vinil Usado, Duplo)`. Sem ano, sem o parêntese do ano. `Vários artistas` e variações viram `Vários`. |
| `marca` | Artista. |
| `categorias` | `LP, Usado, <genero>, Novidades`. |
| `ficha` | `Gravadora, Catálogo, País, Ano.` + ` Prensagem X.` (se diferente do ano) + ` Disco duplo.` + ` Capa dupla (gatefold).` + ` Acompanha: a; b.` + ` Marcas: ....` + ` Bolinha <cor> na etiqueta.` |
| `descricao`, `capa`, `vinil`, `tags` | Do JSON. |
| `preco` | `preco_etiqueta` (vazio se `null`). |
| `preco_origem` | `etiqueta` se houver preço. |
| `peso_kg` | `0,8` duplo; `0,55` gatefold ou com foto de encarte ou capa interna; `0,5` nos outros. |
| `altura_cm`, `largura_cm`, `comprimento_cm` | `2,5`, `32`, `32`. |
| `fotos` | `01 capa.jpg \| 02 contracapa.jpg \| ...` na ordem do site. |
| `seo_titulo` | `LP Artista Album (Ano) - Vinil Usado` (+ ` Duplo`). |
| `seo_descricao` | Primeira frase da descrição (até 120 caracteres, cortando na palavra, com `…`) + ` Vinil usado, exemplar único.` |
| `pendencias` | As do JSON + automáticas, juntas com ` \| `. |
| `estoque` | `1`. |
| `atualizado_em` | `AAAA-MM-DD HH:MM` agora. |
| Demais | Vazias. |

Pendências automáticas:

- **Sem capa limpa.** Se não houver foto `capa`, a foto `etiqueta` vira a capa do site, e a pendência diz: "A capa só foi fotografada no plástico com a etiqueta de preço: essa foto vai para o site. Refotografar sem plástico se quiser."
- **Sem preço.** "Sem etiqueta de preço nas fotos: definir o preço antes de aprovar."
- **Repetido na loja.** "JÁ EXISTE NA LOJA COM ESTOQUE N: lojamonstro.com.br/produtos/<url>/ . Confirmar se é outro exemplar; se for o mesmo disco, descartar este rascunho."
- **Identificação incerta.** Com `confianca` `baixa`: "Identificação incerta: conferir artista, álbum e edição."

**Ordem das fotos do site.**

1. Ignore `etiqueta` e `descartar`.
2. Ordene por papel: capa 1, contracapa 2, encarte frente 3, encarte verso 4, encarte aberto 5, capa interna 6, capa interna verso 7, disco 8, disco lado B 9.
3. Desempate pelo horário.
4. Numere de 1 em diante.

A etiqueta entra em `cadastro_fotos` com ordem `0`, papel `etiqueta` e sem cantos.

**Linha de `cadastro_fotos`.** `id_disco`, `ordem`, `papel`, `arquivo_drive_id` vazio (a rotina completa pelo nome), `cantos` (JSON ou vazio) e `observacao` com o nome novo do arquivo.

**Nomes novos.**

- Fotos do site: `<id> NN <papel>.jpg`. Etiqueta: `<id> 00 etiqueta.jpg`. Descartadas: `<id> descartada <n>.jpg`, para que o `arquivarFotos` do vigia leve tudo junto quando o disco for publicado.
- Fotos de discos pulados não mudam de nome.
- Se o nome novo já existir na pasta, erro.

**Sem `--confirmar`**, mostre a tabela do que seria gravado e os nomes novos, e pare.

**Com `--confirmar`**, siga esta ordem, pensada para poder retomar se cair no meio:

1. Grave o plano em `dados/cadastro_ia/<lote>/plano.json`, com as linhas e o par nome antigo → nome novo.
2. Renomeie os arquivos e anote cada um feito no plano.
3. Acrescente as linhas de `cadastro_rascunhos`, depois as de `cadastro_fotos`, em uma chamada por aba. Use `value_input_option RAW` e o intervalo logo abaixo da última linha preenchida, nunca `append` às cegas.
4. Marque o plano como concluído.

Se o comando for rodado de novo com um plano pela metade, retome dali, sem renomear duas vezes nem duplicar linhas. Para isso, confira os IDs já presentes na aba.

No fim, mostre os IDs gravados, os discos pulados e as fotos renomeadas.

### `renomear-lote LOTE` (extra, para lotes antigos)

Serve para o lote 2026-10-26, gravado pelo Cowork com os nomes da câmera (`IMG_...`). Para cada linha de `cadastro_fotos` daquele lote com `observacao` começando em `IMG_`:

1. renomeie o arquivo local para o padrão acima;
2. atualize só a célula `observacao` daquela linha.

O ID do Drive não muda com a renomeação, então linhas com `arquivo_drive_id` já preenchido continuam válidas. Simulação por padrão; `--confirmar` para valer.

## Testes

Todos sem rede. Use planilha falsa (como os testes atuais do cadastro) e imagens sintéticas.

- **Regressão de derivação.** Com `exemplo_lote_2026-10-26.json` e uma planilha falsa sem rascunhos daquele lote, as linhas geradas batem com `linhas_gravadas_2026-10-26.json`. Compare as colunas `id`, `pasta`, `titulo`, `marca`, `categorias`, `ficha`, `descricao`, `capa`, `vinil`, `preco`, `peso_kg`, `fotos`, `seo_titulo`, `seo_descricao`, `tags`, `preco_origem` e `estoque`. Em `cadastro_fotos`, compare `id_disco`, `ordem` e `papel`. Ignore as pendências de "JÁ EXISTE NA LOJA" e use nomes antigos (sem renomear) nessa comparação.
- **Validações.** Cada erro da lista do `conferir` tem um caso. Teste também o consignado recusado e a foto já cadastrada recusada.
- **IDs.** Continuam a numeração do lote existente.
- **Nomes novos.** Gerados certos; colisão gera erro.
- **Plano.** Interrompido depois de renomear retoma sem duplicar.
- **Simulação.** Sem `--confirmar`, nenhuma chamada de escrita na planilha falsa e nenhum arquivo renomeado.
- **Detecção.** Cantos e círculo em imagem sintética (retângulo claro sobre fundo branco com borda; círculo escuro).
- **Teste com fotos reais.** Marque com `skip` quando `CADASTRO_PASTA_LOCAL` não existir. Ele mede a meta de 90% dos cantos contra a referência.

Rode a suíte inteira. Hoje são 658 testes passando, e nenhum pode quebrar.

## Fechamento

1. `AGENTS.md`: na seção de cadastro (ou numa nova "Cadastro de discos"), uma linha dizendo que a identificação de discos novos segue `docs/CADASTRO_IA.md`.
2. `PROMPTS.md`: novo prompt "Cadastrar discos novos": `Leia docs/CADASTRO_IA.md e cadastre os discos novos da pasta entrada.`
3. `docs/DECISOES.md`: D-078, "Cadastro por agente local", com o motivo (economia de créditos do Cowork; o agente local lê as fotos direto da pasta do Drive).
4. `docs/ESTADO.md`: o que foi entregue e como conferir.
5. Teste de ponta a ponta, sem gravar: rode `folhas` (deve dizer 0 fotos novas se o lote de 26/10 já foi renomeado, ou listar só as que não estão na planilha) e `conferir dados/referencia-privada/cadastro_ia/exemplo_lote_2026-10-26.json`. Esse `conferir` deve recusar todas as fotos por "já está em cadastro_fotos", prova de que não duplica.
6. **Só rode `renomear-lote 2026-10-26 --confirmar` depois que o Túlio autorizar.**
7. Explique ao Túlio em 3 a 5 linhas o que foi feito e peça que ele mesmo faça o commit e o push.
