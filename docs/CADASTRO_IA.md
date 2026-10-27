# Cadastro de discos por IA · manual para o agente

Vale para qualquer agente que rode neste computador (Antigravity, Codex, Claude Code). Leia o `AGENTS.md` antes. Este manual substitui o trabalho que o Cowork fazia na etapa 2 do `docs/CADASTRO.md`: olhar as fotos novas, identificar cada disco e gravar os rascunhos no Painel.

O pedido do Túlio costuma ser curto, por exemplo: "Leia docs/CADASTRO_IA.md e cadastre os discos novos da pasta entrada."

## O que você faz e o que você não faz

Você faz:

1. Agrupa as fotos novas por disco.
2. Identifica cada disco (artista, álbum, ano, gravadora, catálogo, país).
3. Lê o preço na etiqueta.
4. Dá a nota de conservação da capa e do vinil.
5. Escreve a descrição e as tags.
6. Monta o arquivo do lote e roda o script, que confere e grava.

O script faz sozinho: título, categorias, ficha, peso, medidas, SEO, ordem das fotos, recorte das fotos, aviso de disco repetido na loja e a gravação na planilha. Não tente fazer essas partes à mão.

Você não faz:

- Não cria produto na loja. Tudo entra como `rascunho` e só vira produto depois que o Túlio aprova no Painel.
- Não apaga nem move fotos. O script só renomeia as fotos dos discos gravados.
- Não edita a planilha por outro caminho que não seja o script.
- Não altera produto que já existe na loja.
- Não inventa informação. Na dúvida, fique no genérico e anote em `pendencias`.

## Passo a passo

Todos os comandos rodam na pasta do projeto, com o ambiente virtual:

```
.venv\Scripts\python scripts\cadastro_lote.py <comando> ...
```

### 1. Ver as fotos novas

```
.venv\Scripts\python scripts\cadastro_lote.py folhas
```

O comando lista as fotos da pasta `entrada` que ainda não estão em nenhum rascunho. Ele monta folhas de contato (12 miniaturas por folha, com um código em cada foto) em `dados/cadastro_ia/<lote>/folhas/` e escreve a lista código → arquivo em `dados/cadastro_ia/<lote>/fotos.txt`. O lote é a data de hoje (AAAA-MM-DD).

Comece sempre pelas folhas. Abrir as fotos originais uma a uma gasta muito: cada uma tem 4624×2600 pixels.

### 2. Agrupar por disco

As fotos estão em ordem de horário. O formato que o Túlio usa (fundo branco), por disco:

1. **etiqueta**: a capa ainda no plástico, com a etiqueta de preço colada e às vezes uma bolinha colorida. Essa foto marca o começo de um disco novo. Serve só para ler o preço e nunca vai para o site.
2. **capa**: a mesma capa fora do plástico.
3. **contracapa**.
4. **encarte** ou **capa interna**, se houver. Às vezes aberto, ocupando o dobro da largura.
5. **disco**: um lado ou os dois.

Nem sempre vem completo. Às vezes falta a capa limpa, às vezes falta a etiqueta. O intervalo de tempo entre fotos ajuda, mas não decide: dois discos podem estar a 20 segundos um do outro. Decida pelo conteúdo (mesma arte, mesmo artista, mesmo rótulo).

Confira se cada grupo é mesmo de um disco só. Encarte de outro disco dentro da capa acontece.

### 3. Ler detalhes

Para ler etiqueta de preço, número de catálogo, rótulo, ano ou créditos, use o recorte:

```
.venv\Scripts\python scripts\cadastro_lote.py recorte IMG_20261025_115629.jpg 0.30 0.10 0.60 0.45
```

Os 4 números são esquerda, topo, direita e base, de 0 a 1, na foto já girada. A imagem sai em `dados/cadastro_ia/<lote>/zoom/`. Recorte só o que precisa.

Você pode consultar o site do Discogs para confirmar a edição pelo número de catálogo. Não copie textos nem imagens de lá. A rotina já completa faixas e créditos pelo Discogs depois.

### 4. Escrever o arquivo do lote

Salve em `dados/cadastro_ia/<lote>/lote.json`. Modelo completo e real: `dados/referencia-privada/cadastro_ia/exemplo_lote_2026-10-26.json` (37 discos do lote de 26/10/2026). Formato:

```json
{
 "lote": "2026-10-26",
 "discos": [
  {
   "disco": "d31",
   "acao": "cadastrar",
   "fotos": [
    {"arquivo": "IMG_20261025_130215.jpg", "papel": "etiqueta"},
    {"arquivo": "IMG_20261025_130225.jpg", "papel": "contracapa"},
    {"arquivo": "IMG_20261025_130240.jpg", "papel": "disco"}
   ],
   "artista": "Lulu Santos", "album": "Honolulu", "ano": 1990,
   "gravadora": "RCA / BMG Ariola", "catalogo": "150.0013", "pais": "Brasil", "ano_prensagem": "1990",
   "duplo": false, "gatefold": false,
   "preco_etiqueta": 40,
   "bolinha": "amarela",
   "capa": "G+", "vinil": "VG+",
   "acompanha": [],
   "marcas": "manchas de umidade na frente e na contracapa; carimbo de loja antiga na contracapa",
   "genero": "Rock / Pop Nacional",
   "descricao": "…",
   "tags": "Lulu Santos, Honolulu, LP, LP Usado, Vinil Usado, Pop Nacional, Rock Nacional",
   "confianca": "alta",
   "pendencias": "Vinil estimado pela foto (só lado 1)."
  }
 ]
}
```

Campos:

| Campo | Regra |
|---|---|
| `disco` | Código seu (d01, d02...), só para o relatório. |
| `acao` | `cadastrar` ou `pular`. Para `pular`, escreva o `motivo`. |
| `fotos` | Todas as fotos do grupo, na ordem em que foram tiradas. `arquivo` é o nome exato na pasta. |
| `papel` | Um destes: `etiqueta`, `capa`, `contracapa`, `encarte frente`, `encarte verso`, `encarte aberto`, `capa interna`, `capa interna verso`, `disco`, `disco lado B`, `descartar`. Para `descartar`, escreva o `motivo` (repetida, mão na frente, de outro disco). |
| `recorte` / `cantos` | Opcional, só depois de ver a prévia (passo 5). `"recorte": "inteira"` usa a foto inteira. `"cantos": [[x,y],[x,y],[x,y],[x,y]]` marca os 4 cantos à mão (escala de 500 px de largura, na ordem superior esquerdo, superior direito, inferior direito, inferior esquerdo). |
| `artista`, `album` | Como aparecem na capa, com acentos. Coletânea de vários artistas: `Vários`. |
| `ano` | Ano do lançamento original do álbum. |
| `ano_prensagem` | Ano desta prensagem, se der para saber. Senão, vazio. |
| `gravadora`, `catalogo`, `pais` | Lidos no rótulo ou na contracapa. |
| `duplo`, `gatefold` | `true` se for LP duplo ou capa dupla que abre. |
| `preco_etiqueta` | Número lido na etiqueta. `null` se não tiver etiqueta ou se estiver ilegível. Nunca chute. |
| `bolinha` | Cor da bolinha adesiva perto da etiqueta, ou vazio. |
| `capa`, `vinil` | Notas Goldmine: `M`, `NM`, `VG+`, `VG`, `G+`, `G`, `F`. O vinil é avaliado pela foto: se ficou em dúvida, diga em `pendencias`. |
| `acompanha` | O que vem junto (encarte com letras, capa interna, pôster). `[]` se nada. |
| `marcas` | Defeitos e marcas visíveis: escrita a caneta, carimbo, nome do dono, fita adesiva, rasgo, umidade. |
| `genero` | Exatamente um nome da lista abaixo. |
| `descricao`, `tags` | Regras abaixo. |
| `confianca` | `alta`, `media` ou `baixa` na identificação. |
| `pendencias` | O que o Túlio precisa conferir. Vazio se nada. |

Gêneros aceitos (escreva igual):

`Classic Rock` · `Disco / Funk / Soul` · `Discoteca / Eletronico / Dance / House` · `Folk / Country` · `Hard Rock / Heavy Metal / Metal` · `Indie / Rock Alternativo` · `Jazz / Blues` · `MPB - Música Popular Brasileira` · `New Age - Ambient` · `New Wave / Synth Pop` · `Pop` · `Rap / Hip Hop` · `Reggae / Dub` · `Regional` · `Rock / Pop Internacional` · `Rock / Pop Nacional` · `Rock Progressivo / Psicodelico` · `Samba / Pagode` · `Sertanejo` · `Trilha Sonora / Novela`

Samba e pagode ficam em `Samba / Pagode`; forró e música nordestina em `Regional`. Anote em `pendencias` se ficou em dúvida.

### 5. Conferir

```
.venv\Scripts\python scripts\cadastro_lote.py conferir dados\cadastro_ia\<lote>\lote.json
```

O script confere o arquivo e calcula o recorte de cada foto. Ele gera uma prévia por disco em `dados/cadastro_ia/<lote>/previas/` (as fotos como vão ficar no site) e o relatório `conferencia.md`, com:

- erros que impedem a gravação;
- avisos, como disco que já existe na loja com estoque ou rascunho parecido no Painel;
- o título e as categorias que vão ser gravados.

Abra as prévias. Se um recorte cortou parte da capa ou pegou o fundo, ponha `"recorte": "inteira"` naquela foto (ou marque os `cantos` à mão) e rode `conferir` de novo. Corrija os erros até o relatório dizer "pronto para gravar".

### 6. Gravar

```
.venv\Scripts\python scripts\cadastro_lote.py gravar dados\cadastro_ia\<lote>\lote.json --confirmar
```

Sem `--confirmar`, o comando só mostra o que faria. Com `--confirmar`, ele:

1. renomeia as fotos dos discos gravados para `<id> NN papel.jpg` (ex.: `2026-10-27-03 01 capa.jpg`), o que permite ao Drive arquivá-las sozinho depois que o disco for publicado;
2. grava os rascunhos em `cadastro_rascunhos` e as fotos em `cadastro_fotos`.

Não grave duas vezes o mesmo lote: o script recusa fotos que já estão em algum rascunho.

### 7. Avisar o Túlio

Responda em português simples, sem jargão, com:

- quantos rascunhos foram gravados e os códigos (ex.: 2026-10-27-01 a 2026-10-27-18);
- quais estão sem preço;
- quais podem estar repetidos na loja;
- quais capas só foram fotografadas no plástico;
- os discos que você pulou e por quê;
- as fotos descartadas;
- dúvidas de identificação.

Termine com: "Os rascunhos estão no Painel, aba Cadastro. As fotos ficam com link depois da próxima rodada da rotina (ou rode a rotina na mão em Actions)."

## Regras da loja

- **Bolinha prata = disco consignado.** Ele só existe na loja física. Use `"acao": "pular"`. O script recusa de qualquer forma.
- **Disco usado é exemplar único:** estoque 1, sempre um cadastro novo, mesmo se já houver outro igual na loja. O script avisa quando já existe e o Túlio decide.
- **Disco sem a capa ou com fotos que não dão para identificar** (ex.: só a contracapa): pule e explique.
- **Disco lacrado, CD, compacto, fita K7 ou DVD:** este fluxo ainda não cobre. Pule com o motivo "outro formato" e avise o Túlio.
- **Bolinhas de outras cores:** o significado ainda não foi definido. Só registre a cor no campo `bolinha`.

## Como escrever a descrição

Português do Brasil, direto. Dois ou três parágrafos curtos separados por uma linha em branco, depois uma lista com "• ".

- **1º parágrafo:** o que é o disco. Ano, gravadora e, se aparecer na capa ou na contracapa, produtor, estúdio, parcerias, participações.
- **2º parágrafo** (se houver o que dizer): faixas conhecidas ou o repertório lido na contracapa.
- **Lista:** o que vem junto e o estado. Use `• Com encarte original com letras`, `• Capa VG+`, `• Vinil VG+` e um tópico por marca relevante (`• Contracapa com anotação a caneta`).

Proibido:

- **Travessão (—) em qualquer lugar.** Use vírgula, dois-pontos ou ponto.
- **Exagero sem prova:** "imperdível", "raríssimo", "obra-prima".
- **Fato que você não viu nas fotos e não tem certeza absoluta.** Não invente faixa, músico, ano ou história.
- **Palavras vagas sobre o estado** ("bom estado", "conservado"). A nota Goldmine diz isso.

Exemplo real (Moraes Moreira, Bazar Brasileiro):

```
Bazar Brasileiro é o disco de 1980 de Moraes Moreira, lançado pela Ariola e gravado nos estúdios Transamérica. Mistura frevo, forró, afoxé e baião, com parcerias de Fausto Nilo, Capinam, Jorge Mautner, Wally Salomão, Abel Silva, Antonio Risério e Patinhas.

O repertório traz Grito de Guerra, Forró do ABC, Tapioca de Olinda, Que Papo É Esse?, Meninas do Brasil, Cabeleira de Berenice, Pessoal do Alô, Asas de Brasília, Lenda do Pégaso, Meninos do Brasil e Todos Nós, com composição e solo de Davi Moraes.

• Com encarte original ilustrado
• Capa VG+
• Vinil VG+
```

## Tags

Cada tag é algo que um cliente digitaria na busca da loja. Na ordem:

`Artista, nome popular (se houver), Título, parcerias e músicos relevantes, LP, LP Usado, Vinil Usado, [Disco Duplo], gêneros`

Exemplo: `Antonio Carlos Jobim, Tom Jobim, Passarim, LP, LP Usado, Vinil Usado, MPB, Bossa Nova`.

Não use nome colado (`AntonioCarlosJobim`) nem `colecionável`.

## Notas de conservação (Goldmine)

| Nota | Capa | Vinil |
|---|---|---|
| M | Lacrado, perfeito. | Nunca tocado. |
| NM | Quase perfeita, sem desgaste visível. | Brilho total, sem marcas. |
| VG+ | Desgaste leve nas bordas ou nos cantos. | Marcas leves que não afetam o som. |
| VG | Desgaste claro, pequena escrita, costura aberta pequena. | Riscos visíveis, chiado em partes calmas. |
| G+ / G | Muito desgaste, rasgo, umidade, fita adesiva. | Muito risco, chiado constante, toca inteiro. |
| F | Danificada. | Pula ou tem defeito sério. |

Pela foto, o vinil quase nunca passa de VG+. Se só um lado foi fotografado, diga em `pendencias`.
