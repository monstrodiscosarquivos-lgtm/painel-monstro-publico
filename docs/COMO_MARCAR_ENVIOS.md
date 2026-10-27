# Rotina de WhatsApp na Fila

## Trabalhar sem configurar filtros

Na aba Fila, abra **Fila Monstro** no menu superior e escolha a visualização.
Clique em **Abrir** no diálogo: a mesma Fila abre na visualização escolhida.
As visualizações são pessoais e não alteram a tela de outra pessoa.
Também ficam em **Dados > Visualizações de filtro**.

- **Para enviar:** somente Situação Contatar. Envie manualmente e marque Enviei agora uma vez.
- **Acompanhar respostas:** ciclos com envio registrado, ainda sem recuperação, recusa ou número inválido. Use Ctrl + F com nome ou telefone; confira identificação e origem, pois nomes podem repetir.
- **Histórico e busca:** todos os ciclos com identificação, inclusive encerrados. Use esta opção se não encontrar a resposta em Acompanhar.

## Uma marcação por acontecimento

- **Enviei agora:** soma um toque, registra horário e Em andamento. A caixa volta a ficar vazia; contador e data comprovam o registro.
- **Respondeu agora:** Status Respondeu e Situação Em conversa. Pausa os próximos toques deste ciclo e não soma envio.
- **Contato inválido agora:** número inexistente, sem contar envio. Preserva histórico e impede novas tentativas desse número conforme D-048.
- **Não quer agora:** recusa de WhatsApp, sem contar outro envio. A rotina mantém o bloqueio; não descadastra o email do Brevo.

Compras e receita recuperada são identificadas pela rotina. Não marcar Recuperado manualmente no fluxo normal. Janela de recuperação: pedido pago válido do mesmo email ou telefone em até sete dias do primeiro toque.

Marque uma célula por vez. Não cole várias caixas nem teste em contatos reais.
Uma resposta não registra um envio anterior que ficou sem marcar.
Correções de resposta usam Status; correções de envio exigem revisar contador e horário, sem marcar novamente a caixa.
Não mover colunas. Para reexibir campos ocultos, usar as setas entre as colunas.

## Limites atuais

O WhatsApp continua manual: abrir link não envia nem confirma envio.
A pausa vale para este ciclo, não cancela definitivamente todos os relacionamentos futuros.
Não há retomada agendada, atribuição de responsável ou desfazer automático nesta versão.
Quando duas pessoas trabalharem ao mesmo tempo, combinar quem atende cada contato: a trava impede duplicar registro, mas não impede duas mensagens enviadas manualmente.
Um pedido de disco ainda é registrado em desejos ou no formulário; marcar Respondeu não interpreta a conversa.

## Migração de 12/10/2026

Os quinze envios confirmados naquela sessão foram registrados com um toque e horário da correção, 12:11 Brasília. Não é o horário original das mensagens. O teste operacional posterior confirmou registro automático. Não registrar esses envios novamente.
