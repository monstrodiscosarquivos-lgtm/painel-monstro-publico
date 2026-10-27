# Garimpo (Google Forms) e públicos do Meta · guia (Etapa 8)

## 1. Lista de garimpo: o cliente pede um disco e a loja avisa quando chega

### Como funciona
1. O cliente preenche um formulário curto (3 perguntas). As respostas caem numa aba da mesma Planilha Google.
2. A cada rodada de hora em hora, o Painel junta as respostas do formulário com a aba `desejos` (onde a Mariana anota pedidos à mão).
3. Quando entra na loja um disco que combina com o pedido (as palavras de artista e disco aparecem no nome, ele tem estoque e entrou
   **depois** do pedido), o Painel coloca uma linha na fila única de WhatsApp: origem **Garimpo**, modelo `ALERTA_GARIMPO`, com a mensagem
   e o link do disco prontos. Quem envia é sempre a Mariana.
4. Um pedido gera um aviso só: depois que a Mariana marca o primeiro toque, o pedido é considerado atendido.
5. Quem está no `Bloqueio` ou se descadastrou nunca recebe aviso.

### Criar o formulário (uma vez só, com a conta Google da loja, a mesma da planilha)
1. Abra https://forms.google.com e clique em **+ Em branco**.
2. Em "Formulário sem título", escreva: `Garimpo Monstro: me avise quando chegar`. Na descrição:
   `Diga o disco que você procura e a gente te avisa pelo WhatsApp quando chegar.`
3. Contato em duas perguntas (D-072; o formulário antigo tinha uma só, `Seu nome e WhatsApp com DDD`, e as respostas antigas continuam valendo):
   - `Seu nome`. **Resposta curta**. **Obrigatória**.
   - `Seu WhatsApp com DDD`. **Resposta curta**. **Obrigatória**. Descrição: `Ex.: 62 99999-0000`. Validação (três pontinhos >
     Validação da resposta): **Expressão regular** > **Corresponde a** `^[0-9 ()+.-]{10,20}$`, texto de erro
     `Digite só o número com DDD, ex.: 62 99999-0000`.
4. Clique no **+** (Adicionar pergunta) e crie a segunda:
   - Texto: `Artista ou banda`. Tipo: **Resposta curta**. **Obrigatória**.
5. Terceira pergunta:
   - Texto: `Qual disco você procura?`. Tipo: **Resposta curta**. Pode deixar **não** obrigatória. Descrição: `Um disco por
     resposta. Quer mais de um? Envie de novo. Em branco = qualquer disco do artista.`
   - Quarta pergunta (D-072): `Formato`. Tipo: **Múltipla escolha**. Opções: `Qualquer formato`, `LP (vinil)`, `CD`, `Compacto`,
     `Fita K7`, `DVD`. Não obrigatória. Pedido de CD só avisa quando chega CD; de LP, só LP. Sem a pergunta (ou em branco), vale
     a palavra escrita no pedido ("CD ...", "vinil"); sem nada, qualquer formato serve.
6. Importante: mantenha as palavras **WhatsApp**, **Artista**, **disco** e **Formato** nos títulos das perguntas. O Painel reconhece as colunas pelo texto.
7. Engrenagem **Configurações** > **Apresentação** > **Mensagem de confirmação**: `Anotado! Quando chegar, a Mariana te avisa pelo WhatsApp.`
8. Aba **Respostas** > ícone verde **Vincular ao Planilhas** > **Selecionar planilha existente** > escolha **Painel Monstro · dados**
   (a mesma planilha) > **Selecionar**. Vai nascer uma aba nova chamada **Respostas ao formulário 1**. **Não renomeie.**
9. Botão **Enviar** (canto de cima) > ícone de **link** > marque "Encurtar URL" > **Copiar**. Use esse link no Instagram, no WhatsApp
   e num QR code na loja.

### Como conferir
O aviso só dispara para disco que entrou **depois** do pedido. Para testar sem esperar chegar disco novo, use a aba `desejos` (à mão):
1. Veja na aba `produtos` um disco que entrou há pouco (coluna `criado_em`) e anote artista e data.
2. Na aba `desejos`, nova linha: `telefone` = seu WhatsApp com DDD (só números, com 55), `nome` = seu nome, `desejo` = o artista (e o disco),
   `data` = **um dia antes** da data de entrada do disco.
3. Na rodada seguinte (minuto 7 de cada hora), a aba `Fila` ganha uma linha com `Origem` = Garimpo, `Modelo usado` = ALERTA_GARIMPO e
   a mensagem pronta. Depois do teste, escreva `Avisado` na coluna `status` dessa linha de `desejos` para ela parar de gerar aviso.

## 2. Públicos do Meta (todo mês)

### O que o Painel monta (primeira rodada de cada mês)
| Aba da planilha | Para que serve |
|---|---|
| `meta_sumiu_180` | Quem sumiu há mais de 180 dias e aceita marketing (anúncio de reativação) |
| `meta_nao_abre` | Quem não abre email (segmento do Brevo) |
| `meta_compradores_180` | Quem comprou nos últimos 180 dias (**excluir** dos anúncios de prospecção, D-008) |
| `meta_resumo` | Quantos contatos em cada lista e avisos |

Colunas de cada aba: `email`, `phone` (com 55), `fn` (primeiro nome), `ct` (cidade). Nada disso vai para o repositório.

### Criar o segmento "não abre email" no Brevo (uma vez só)
1. No Brevo: **Contatos** > **Segmentos** > **Criar um segmento**.
2. Condição: contatos que **não abriram** nenhuma campanha de email nos últimos 90 dias (em "Atividade de e-mail"/"Comportamento").
3. Salve. O número do segmento aparece no final do endereço da página (`.../segment/NÚMERO`).
4. Na aba `Configuração` da planilha, na linha **Brevo: ID do segmento não abre email**, escreva esse número.
5. O Painel refaz a lista sozinho (basta o número mudar). Sem o número, `meta_nao_abre` fica vazia e `meta_resumo` avisa.

### Subir no Meta (todo mês)
1. Abra a aba (por exemplo `meta_sumiu_180`) > **Arquivo** > **Fazer download** > **Valores separados por vírgula (.csv)**.
2. No Gerenciador de Anúncios: **Públicos** > **Criar público** > **Público personalizado** > **Lista de clientes**.
3. Envie o CSV; o Meta reconhece `email`, `phone`, `fn` e `ct` e codifica tudo ao importar. Nome sugerido: `Sumiu 180d 2026-10`.
4. Faça o mesmo com `meta_nao_abre` e com `meta_compradores_180` (este vai como **exclusão** nas campanhas de prospecção).

Alternativa no computador: `python -m painel_monstro.saidas.meta --csv` grava os 3 CSV em `dados/meta/AAAA-MM/` (pasta fora do git).
