# Especificação · mostrar na loja ao aprovar (D-082) e excluir cupons cancelados (D-083)

Pedido do Túlio em 27/10/2026. Leia o `AGENTS.md` antes. As duas partes são independentes: faça uma, teste, depois a outra.

Trabalhe nesta pasta (repositório público). Para os testes:

- Python: `..\..\.venv\Scripts\python -m pytest -q`;
- Apps Script: `node apps-script/teste_local.js`.

Nada de dados de clientes no código, nos testes ou nos docs.

---

## Parte 1 · Escolher se o disco aparece na loja ao aprovar (D-082)

Hoje o produto sempre nasce oculto (`published: false`) e o Túlio publica à mão na Nuvemshop. Agora ele quer escolher, em cada rascunho, se o disco já aparece na loja quando for criado. **O padrão é mostrar.** Esta mudança substitui a trava "nasce sempre oculto" do D-067. Registre em DECISOES que foi pedido explícito do Túlio em 27/10/2026.

### Planilha

Nova coluna `publicar` no fim de `cadastro_rascunhos`, depois de `estoque`. Crie pelo mesmo mecanismo que criou `estoque`: a rotina acrescenta colunas que faltam.

- Valores: `sim` ou `nao`.
- Vazio vale `sim`, para os rascunhos que já existem.

### Painel (aba Cadastro)

- Em cada rascunho, uma caixa **"Mostrar na loja assim que for criado"**, marcada por padrão. Ela grava `sim` ou `nao` na coluna `publicar`.
- Se o rascunho tiver pendência com "JÁ EXISTE NA LOJA" ou "Sem etiqueta de preço", mostre ao lado da caixa um aviso amarelo curto: "Confira as pendências antes de deixar aparecer na loja." O aviso não impede nada.
- Na lista de rascunhos aprovados ou criados, mostre "vai aparecer" ou "fica oculto".

### Rotina (`painel_monstro/saidas/cadastro.py`)

1. **A criação continua igual: produto oculto.** O `POST` segue com `published: false`, e as travas atuais continuam valendo durante a criação e as imagens. Isso evita o disco aparecer sem fotos.
2. **Só depois de todas as imagens confirmadas**, e só se `publicar` não for `nao`:
   - faça `PUT /products/{id}` com `{"published": true}`, e nada mais no corpo;
   - registre no diário de idempotência um passo novo, `publicacao_pedida`, ANTES do PUT, e `publicado` depois;
   - grave `status = publicado` e um `link_loja` válido.
3. **Se o PUT falhar ou ficar incerto:** grave `status = criado` e a pendência "Não consegui deixar visível; publique à mão na Nuvemshop". Não repita automaticamente.
4. **Ao retomar um disco** (rodada nova, mesmo `produto_id`): a trava "produto está visível; interrompido" (por volta da linha 420) só pode disparar se o diário NÃO tiver `publicacao_pedida`. Se tiver, o produto visível é o resultado esperado: marque `publicado` e siga.
5. **Esta é uma exceção estreita à regra "nunca alterar produto existente":** só o campo `published`, só no produto que esta própria rotina criou (confira o SKU `CAD...` da linha, como já é feito), e só uma vez.
6. **Disco com `publicar = nao`:** igual a hoje, fica `criado` e oculto.

### Testes

- `publicar` vazio e `sim` publicam depois das imagens;
- `nao` não publica;
- PUT só depois da última imagem;
- falha no PUT deixa `criado` com a pendência;
- retomada com `publicacao_pedida` não dispara a trava;
- produto visível SEM `publicacao_pedida` continua interrompendo;
- o PUT tem só `published`.

Atualize os testes atuais que esperam "sempre oculto" para a regra nova, sem apagar a checagem de que o POST nasce oculto.

---

## Parte 2 · Excluir de uma vez os cupons cancelados (D-083)

Hoje "Cancelar" (D-074) desativa o cupom na Nuvemshop (`valid: false`) e grava `cancelado <data>` em `cupom_status`. Os cupons desativados continuam na lista de cupons da Nuvemshop e no Painel. O Túlio quer limpar tudo de uma vez.

### Painel (aba Raspadinha, seção Cupons da campanha)

1. Botão **"Excluir cupons cancelados (N)"**, que só aparece se N > 0.
2. Confirmação antes de executar: "Apagar N cupons cancelados da Nuvemshop? Eles somem da lista de cupons da loja. As jogadas e os números da campanha continuam no Painel. Não dá para desfazer."
3. Ao confirmar, grava `apagar` em `cupom_status` das linhas `cancelado...` daquela campanha que ainda não foram apagadas. Uma gravação em lote, como o cancelamento em lote atual.
4. **Situações novas em `rpEstado`:**
   - `apagar`: "excluindo…";
   - `apagado <data>`: "excluído";
   - `erro ao apagar...`: "não consegui excluir".
5. A lista esconde os excluídos por padrão, com um filtro **Mostrar excluídos**.
6. As métricas da campanha (jogadas, cupons gerados, usados, vendas) continuam contando essas linhas como antes. Excluir não muda resultado.
7. Também dá para excluir um cupom cancelado sozinho: botão **Excluir** na linha, com a mesma confirmação.

### Sorteio (`apps-script/raspadinha/Sorteio.gs`)

1. **`processarCancelamentos`:** além de `cancelar`, processe `apagar`. Mesmo limite de tempo e mesma trava.
2. **Função nova `apagarCupom_(codigo, id)`:**
   - sem id, use `buscarCupomId_`; se não achar, `apagado <data> (não existia)`;
   - `DELETE /coupons/{id}`: 200, 204 ou 404 viram `apagado <data>`;
   - outro código vira `erro ao apagar: Nuvemshop respondeu N`.
3. **Só apague cupons cujo `cupom_status` comece com `cancelado`** (o Painel grava `apagar` apenas nesses, mas confira de novo no script). Nunca apague cupom ativo ou usado.

### Testes

No `teste_local.js`:

- `apagar` vira `apagado`;
- 404 vira `apagado`;
- erro da Nuvemshop vira `erro ao apagar`;
- linha que não estava cancelada não é apagada.

No Painel, teste que o botão conta só os cancelados da campanha e que as métricas não mudam.

---

## Fechamento

1. Rode a suíte inteira, o `teste_local.js` e o `montar_painel_web.py`.
2. Registre D-082 e D-083 no `docs/DECISOES.md` e atualize `docs/ESTADO.md`, `docs/CADASTRO.md` e `docs/RASPADINHA.md`.
3. Passe ao Túlio, em português simples:
   1. o commit;
   2. o Sorteio: avise que ele vai colar o arquivo inteiro, então confira que o arquivo final está completo; depois Nova versão > Implantar;
   3. o Painel.html na Entrada: Nova versão > Implantar;
   4. avisar o Cowork para republicar o Painel do claude.ai.
4. **Não mexa no Cofre.** Se precisar mudar algo nele, diga exatamente o quê, que o Cowork prepara o arquivo completo com os valores reais.
