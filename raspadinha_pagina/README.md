# Página pública da raspadinha (GitHub Pages)

Esta pasta é a única parte do Painel que fica pública. Ela **não tem nenhum dado de cliente**. Desde a D-070 a página abre
campanhas (`?c=<código>&utm_...`): pede o email e pede o prêmio ao Apps Script do sorteio (endereço na variável `SORTEIO`
do `index.html`). Links antigos com `t` (D-062) continuam funcionando. Guia completo: `docs/RASPADINHA.md`.

| Arquivo | O que é |
|---|---|
| `index.html` | A página da raspadinha (mobile first). Lê o link, mostra o selo prateado, o cliente raspa com o dedo ou clicando e arrastando, e aparece o cupom com o botão que abre a loja com o desconto aplicado. |
| `cartela-fechada.jpg` | Imagem da cartela fechada, para o email e para a prévia do link. |
| `email-raspadinha.html` | Modelo do email para o Brevo (fica só aqui, não precisa ir para o GitHub Pages). |

## Publicar (uma vez só)

0. No `index.html`, troque `COLE_AQUI_O_ENDERECO_DO_SORTEIO` pelo endereço `/exec` do Apps Script **Raspadinha · sorteio**.
1. No GitHub, com a conta da loja: **New repository**. Nome: `raspadinha`. Marque **Public**. Clique em **Create repository**.
2. Na página do repositório novo: **Add file** > **Upload files**. Arraste `index.html` e `cartela-fechada.jpg`. Clique em **Commit changes**.
3. **Settings** > **Pages**. Em **Branch**, escolha `main` e a pasta `/ (root)`. Clique em **Save**.
4. Espere 1 ou 2 minutos. O endereço aparece no topo da mesma tela, algo como `https://monstrodiscosarquivos-lgtm.github.io/raspadinha/`.
5. Cole esse endereço na linha **Raspadinha: endereço da página** da aba Configuração (o Painel monta os links com ele).

Para conferir: abra o endereço sem nada depois. Deve aparecer "Essa cartela não abriu" (é o certo: sem link de cliente não há cartela).

## Atualizar

Mudou o `index.html` aqui? Suba o arquivo de novo no repositório `raspadinha` (Add file > Upload files, mesmo nome). Links já enviados
continuam funcionando, desde que a chave `CHAVE` do `index.html` continue igual a `CHAVE_LINK` de `painel_monstro/motor/raspadinha.py`
(um teste confere isso).

## Regras da página

- O código só aparece depois de raspar (cerca de 56% do selo, em média). Cada passada tira metade da tinta: dá trabalho de propósito.
- Quem já raspou e abre de novo vê o cupom direto (fica guardado no navegador).
- Cartela vencida mostra "Essa cartela venceu em dd/mm".
- O botão usa o link oficial da Nuvemshop que aplica o cupom: `lojamonstro.com.br/discount/CUPOM?redirect_to=/`.
