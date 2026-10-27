# Raspadinha · guia

## Campanhas com sorteio na hora (D-070, 16/10/2026) · o jeito atual

Cada oferta é uma **campanha**, configurada no Painel, aba **Raspadinha**. Serve para email (Brevo) e Instagram.

**Como funciona**
1. A pessoa abre o link da campanha (com UTMs). A página (GitHub Pages) pergunta o email. No link do email ele já vem preenchido (`e={{ contact.EMAIL }}`).
2. A página chama o Apps Script **Raspadinha · sorteio** (`apps-script/raspadinha/Sorteio.gs`, conta da Monstro). Ele:
   - confere se a campanha está valendo (situação, datas, canal);
   - se o email já jogou nessa campanha, devolve o mesmo resultado (um por email);
   - sorteia pela **chance** de cada prêmio. Prêmio que bateu o **máximo** sai do sorteio e a chance dele vai para o prêmio de **reserva**;
   - cria o cupom único na Nuvemshop (`POST /coupons`, uso único, validade em dias, pedido mínimo, cumulativo ou não);
   - grava a jogada em `rasp_jogadas` (canal, UTMs, prêmio, cupom, consentimento, se é contato novo).
3. A pessoa raspa o selo e vê o cupom. Abrir de novo mostra o mesmo resultado (guardado no aparelho e no servidor).
4. O Painel cruza os cupons com os pedidos: quem usou, vendas e desconto, por canal e por prêmio. Em **Resultados**, o pedido com cupom de raspadinha entra na origem "Raspadinha (email/Instagram)".

**Situações da campanha**: rascunho (não abre) · teste (abre, cupom de mentira `TESTE…`, nada é criado na loja) · ativa · pausada · encerrada. Datas de início e fim também valem.

**Campos da campanha** (aba `rasp_campanhas`, uma linha por campanha; os prêmios ficam em JSON na coluna `premios`):
código, nome, situação, início, fim, canais (email, instagram), validade do cupom (dias), pedido mínimo, junta com outros descontos, só quem já comprou, pode sair sem prêmio (padrão Não), mensagem de sem prêmio, começo do cupom, título e texto da página.
Prêmio: nome no selo, tipo (Porcentagem, Valor em R$, Frete grátis, Sem prêmio), valor, chance (%), máximo (vazio = sem limite), reserva (um só, sem máximo). As chances precisam somar 100%.

**Abas**: `rasp_campanhas` (Painel escreve), `rasp_jogadas` e `rasp_eventos` (só o Apps Script escreve). Configuração: `Raspadinha: endereço da página`.

**Segurança**: o prêmio é decidido no servidor, nunca na página; recarregar não muda nada. Um resultado por email e campanha. O máximo de cada prêmio limita o custo mesmo se muita gente jogar. O token da loja fica só nas propriedades do Apps Script.

**Ativar (uma vez)**
1. Apps Script novo `Raspadinha · sorteio` (conta da Monstro), colar `Sorteio.gs`. Propriedades: `NUVEMSHOP_STORE_ID`, `NUVEMSHOP_TOKEN`, `NUVEMSHOP_USER_AGENT` (do `.env`). Rodar `prepararRaspadinha`. Implantar como app da Web: Executar como Eu, Qualquer pessoa. Copiar o `/exec`.
2. Em `raspadinha_pagina/index.html`, trocar `COLE_AQUI_O_ENDERECO_DO_SORTEIO` pelo `/exec`. Publicar a pasta no repositório público `raspadinha` com GitHub Pages (passo a passo em `raspadinha_pagina/README.md`).
3. Em Configurações, preencher `Raspadinha: endereço da página`.
4. Testar com a campanha `teste-raspadinha` (situação teste). Depois mudar para ativa.

### Gerenciar campanhas e cupons (D-074, 20/10/2026)

- **Lista:** filtros Em andamento, Testes, Encerradas e Todas. Clique numa linha para ver a campanha.
- **Botões da campanha:** Pausar/Retomar (a página mostra "pausada"), Ativar de verdade (sai do teste; jogadas de teste deixam de contar), Encerrar (fim = hoje; opção de cancelar os cupons não usados), Reabrir, Duplicar e Excluir (só se nunca criou cupom de verdade).
- **Cupons da campanha:** cada cupom com a situação (não usado, usado com o número do pedido, venceu, cancelado). Busca por email ou código. Cancelar um a um ou todos os não usados.
- **Como o cancelamento acontece:** o Painel marca `cancelar` em `rasp_jogadas`; o Apps Script do sorteio confere a cada 5 minutos (`processarCancelamentos`), desativa o cupom na Nuvemshop e grava `cancelado`. Uma vez só: no projeto "Raspadinha · sorteio", colar o `Sorteio.gs` novo, salvar, rodar `instalarGatilhoCancelamentos` e implantar nova versão.

### Lembrete no Brevo (D-071, 16/10/2026)

Quem raspou, ganhou cupom e ainda não usou recebe um email **2 dias antes de o cupom vencer** (linha `Raspadinha: lembrete no Brevo (dias antes de vencer)` em Configurações; 0 desliga).

**Automático (rotina de hora em hora, `painel_monstro/saidas/raspadinha_lembrete.py`)**
- Pega em `rasp_jogadas` os cupons reais (`criado`) que não aparecem em nenhum pedido, dentro da janela (de 2 dias antes até o último dia), e nunca no mesmo dia em que a pessoa raspou. Só das 9h às 20h.
- Grava no contato `RASP_CUPOM`, `RASP_PREMIO`, `RASP_VALIDADE` (dd/mm), `RASP_CAMPANHA` e `RASP_MINIMO` (cria os atributos se faltarem) e põe o contato na lista **Painel · Raspadinha lembrete**. A automação do Brevo envia o email.
- Quem não está no Brevo só é criado se marcou, na página, que aceita receber novidades. Sem esse aceite, ou descadastrado, fica de fora.
- Um lembrete por cupom. Tudo fica na aba `rasp_lembretes` (cupom, email, campanha, prêmio, validade, status, quando).
- Depois que o cupom vence, o contato sai da lista (para poder entrar de novo numa próxima campanha).
- Brevo em modo teste: só conta quem receberia.

**O Túlio faz no Brevo (uma vez)**
1. Contatos > Listas > Criar lista: **Painel · Raspadinha lembrete** (nome exato).
2. Campanhas > Modelos: novo modelo a partir do código de `raspadinha_pagina/email-lembrete-raspadinha.html` (trocar `LINK_DO_WHATSAPP_DA_LOJA`). Assunto sugerido no comentário do arquivo.
3. Automações > Criar > personalizada. Gatilho: **contato adicionado à lista** Painel · Raspadinha lembrete. Ação: enviar o modelo do passo 2. Nas configurações da automação, permitir que o contato **entre de novo** (para receber o lembrete de outras campanhas). Ativar.

---

## Versão anterior: sorteio antes do envio (D-062)

**Estado: pronta em modo teste.** O Painel sorteia e mostra o plano; só cria cupom na Nuvemshop com a aba em **Modo = Real**
e o comando com `--criar-cupons`. O Painel nunca manda email: gera um CSV para o Túlio importar no Brevo.

## Como funciona

1. O Túlio configura a campanha na aba `Raspadinha` da Planilha Google (prêmios, quantidades e regras) e, se o público for
   "Lista colada", cola os emails na aba `raspadinha_lista`.
2. O agente roda `python -m painel_monstro.saidas.raspadinha`. O Painel:
   - monta o público e tira quem não aceita marketing, o email da loja e quem teve benefício nos últimos N dias
     (cupom usado em pedido, Etapa 2 ou 3 da régua, raspadinha anterior);
   - separa o grupo de controle (padrão 10%, só se o público tiver pelo menos 10 pessoas);
   - sorteia os prêmios de um "saco" com a quantidade de cartelas de cada um. Acabou o saco, quem sobrou fica de fora com
     o motivo "acabaram as cartelas";
   - gera para cada um um cupom único (prefixo + 6 letras/números aleatórios, sem hífen, porque a Nuvemshop não aceita) e o link
     pessoal da página;
   - grava tudo na aba `raspadinha_envios` e um CSV de conferência em `dados/raspadinha/` (fora do git).
   O sorteio usa semente fixa pelo nome da campanha e **uma campanha nunca é sorteada de novo** (como a régua, D-030).
3. Com o plano conferido, o Túlio muda **Modo** para **Real** e pede ao agente para rodar
   `python -m painel_monstro.saidas.raspadinha --criar-cupons`. O Painel cria um cupom por pessoa na Nuvemshop
   (`POST /coupons`: uso único, validade, não cumulativo por padrão) e gera o CSV final `dados/raspadinha/<campanha>_brevo.csv`.
   Rodar de novo não duplica: só cria o que faltou. Cupom que já existia vira "já existia".
4. No Brevo, o Túlio importa o CSV numa lista nova e manda a campanha com o modelo `raspadinha_pagina/email-raspadinha.html`.
5. A rotina de hora em hora marca quem usou o cupom (`pedido`, `receita`, `usado_em` na aba `raspadinha_envios`) e grava a aba
   `raspadinha_resultados`: compra em 30 dias de quem recebeu contra o controle, cupons usados, receita e desconto dado.
   A diferença só aparece com 30 pessoas em cada grupo (D-020); antes disso, "dados insuficientes".

## Segurança contra fraude

- O prêmio é decidido no Painel, antes do envio. A página só mostra o que veio no link. Recarregar não muda nada.
- Cada cupom é único e de uso único. Adivinhar outro código é impraticável (31 símbolos, 6 posições: cerca de 887 milhões de combinações).
- O link é embaralhado só para não estragar a surpresa. Quem decodificar o próprio link só vê o próprio cupom.
- Quem repassa o link repassa um cupom que funciona uma vez só.

## Aba `Raspadinha` (do Túlio)

O Painel cria com os valores abaixo quando a aba não existe e nunca altera o que o Túlio escreveu.

**Prêmios** (uma linha por prêmio, a partir da linha 2):

| Prêmio | Tipo | Valor | Quantidade de cartelas |
|---|---|---|---|
| 10% | Porcentagem | 10 | 60 |
| 15% | Porcentagem | 15 | 25 |
| 20% | Porcentagem | 20 | 5 |
| FRETE GRÁTIS | Frete grátis | 0 | 10 |

Tipos aceitos: Porcentagem, Frete grátis, Valor em R$. Prêmio com quantidade 0 é ignorado. "Prêmio" é o texto grande do selo.

**Parâmetros** (abaixo da linha "Parâmetro | Valor | O que faz"):

| Parâmetro | Padrão | O que faz |
|---|---|---|
| Campanha | (vazio) | Nome único. Cada nome é um sorteio; para outra campanha, troque o nome |
| Modo | Teste | Teste: não cria cupom. Real: deixa criar com `--criar-cupons`. Valor ilegível = Teste |
| Público | Lista colada | "Lista colada" (aba `raspadinha_lista`) ou "Todos que aceitam marketing" (clientes com compra paga) |
| Prefixo do cupom | RASPA | Só letras e números |
| Letras aleatórias no cupom | 6 | Mínimo 5 |
| Validade do cupom (dias) | 15 | A partir do dia do sorteio |
| Pedido mínimo (R$) | 0 | 0 = sem mínimo |
| Vale junto com outras promoções? | Não | Sim ou Não |
| Grupo de controle (%) | 10 | Aceita 10 ou 0,1 |
| Mínimo de pessoas para ter controle | 10 | |
| Dias entre benefícios | 90 | 0 desliga a trava |
| Endereço da página | (vazio) | Endereço do GitHub Pages, ex. `https://monstrodiscosarquivos-lgtm.github.io/raspadinha/` |

Teto em reais por cupom: ainda não existe. A documentação oficial do `POST /coupons` não lista campo de teto; o Túlio não tinha
preferência (14/10/2026). Se um dia quiser, conferir na documentação atual antes de implementar.

## Abas do Painel

- `raspadinha_envios`: `campanha, email, primeiro_nome, grupo (envio/controle/fora), motivo, premio, tipo, valor, cupom, valido_ate,
  link, cupom_criado (não (modo teste) / sim / já existia / erro: ...), criado_em, pedido, receita, usado_em`. Chave: campanha + email.
  Coluna nova só no fim.
- `raspadinha_resultados`: `campanha, grupo, pessoas, compraram, taxa_compra, receita, cupons_usados, receita_com_cupom,
  desconto_dos_cupons, janela_fechada, diferenca_vs_controle`. Regravada a cada rodada; só existe depois da primeira campanha.

## Página pública

Fica em `raspadinha_pagina/` e é publicada num repositório público separado (`raspadinha`) com GitHub Pages. Passo a passo em
`raspadinha_pagina/README.md`. É mobile first: raspa com o dedo; no computador, clicando e arrastando (passar o mouse não raspa).
Cada passada tira metade da tinta e o código só aparece com cerca de 56% do selo raspado, em média. Quem já raspou vê o cupom
direto ao abrir de novo. Cartela vencida mostra a data.

## O que o Túlio faz no Brevo (uma vez só)

**Contatos** > **Configurações** > **Atributos de contato** > **Adicionar um novo atributo**: `RASPA_LINK` (Texto) e `RASPA_ATE` (Texto).
Na importação do CSV, ligue as colunas `RASPA_LINK` e `RASPA_ATE` a esses atributos. Antes de enviar, confira a prévia do email
(o nome usa `{{ contact.FIRSTNAME | default : "EI" }}`; se a prévia mostrar o texto do filtro, troque por `{{ contact.FIRSTNAME }}`).

## Comandos

```
python -m painel_monstro.saidas.raspadinha                  # prepara: sorteio + CSV de conferência (não cria cupom)
python -m painel_monstro.saidas.raspadinha --criar-cupons   # cria os cupons (exige Modo = Real) e gera o CSV para o Brevo
python -m painel_monstro.saidas.raspadinha --resultado      # atualiza uso e resultado agora (a rotina já faz de hora em hora)
python -m painel_monstro.saidas.raspadinha --forcar         # refaz o sorteio da campanha, só se nenhum cupom foi criado
```
