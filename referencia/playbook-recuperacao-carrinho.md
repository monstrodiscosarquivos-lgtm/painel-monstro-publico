# Playbook de Recuperação de Carrinho Abandonado — Monstro Discos

Documento de referência para recuperar carrinhos abandonados via WhatsApp. Define quando contatar, quantas vezes, quando oferecer desconto e o que dizer. Atualizado em 28/06/2026.

---

## 1. Princípios

A recuperação só funciona se respeitar três coisas: o tempo natural de decisão do cliente, a margem da loja e a caixa de entrada da pessoa. Contatar cedo demais queima margem com quem ia comprar sozinho. Contatar muito ou com desconto fácil treina o cliente a abandonar de propósito. Insistir demais gera bloqueio.

Por isso o padrão é: **abordagem personalizada, no momento certo, com no máximo 3 toques, e desconto só quando o caso pede.**

Benchmark de referência: WhatsApp tem ~98% de taxa de abertura e taxa de resposta cerca de 8x maior que e-mail, com recuperação típica de 12% a 18% para listas com opt-in. Vale mais um contato bem feito que volume.

---

## 2. Janela de contato (quando abordar)

A preocupação central é não incomodar quem ainda compraria sozinho. A solução é não tratar todo carrinho igual:

| Idade do carrinho | Ação |
|---|---|
| Menos de 3h | **Não contatar.** Janela de conversão natural. A pessoa pode estar só decidindo, comparando frete, ou foi distraída. |
| 3h a 48h | **Janela principal.** Aqui mora a maior parte da recuperação. Prioridade alta. |
| 48h a 7 dias | **Última chance.** Ainda vale, com mensagem mais incisiva e/ou incentivo. |
| Mais de 7 dias | **Frio.** Em geral não compensa, salvo carrinho de valor alto ou item raro. |

Como rodamos em lotes (sempre que você pedir), na prática eu pego o carrinho na primeira passada em que ele já tiver mais de 3h e menos de 7 dias, e a partir daí conto os toques.

---

## 3. Cadência (quantas vezes)

No máximo **3 toques por carrinho**. A partir do 4º contato, a chance de bloqueio cresce mais rápido que a de venda.

- **Toque 1 — Lembrete (sem desconto).** Maioria abandona por distração, frete ou dúvida. Não se queima margem de cara. Foco: lembrar do carrinho + me coloco à disposição para ajudar.
- **Toque 2 — Incentivo leve (~24h depois, se não respondeu).** Razão para agir agora: frete grátis, prova social, "saindo rápido / última cópia" (se for verdade), ou um cupom pequeno.
- **Toque 3 — Última chance (~48–72h depois).** Incentivo com prazo claro ("seu cupom vale até hoje à noite"). Encerra a sequência.

Como o disparo é manual, eu te indico em cada caso se é T1, T2 ou T3, baseado no histórico de tentativas anteriores. Pra isso funcionar, preciso saber quem já foi contatado (ver seção 7, controle).

---

## 4. Política de cupom (quando oferecer)

Regra de ouro: **desconto não é o primeiro recurso, é alavanca para destravar quem travou.** Você me deu autonomia para decidir caso a caso e sugerir cupons existentes ou propor um novo (que marco como "sujeito a aprovação do dono").

Quando **não** oferecer desconto:
- Toque 1, em quase todos os casos.
- Carrinho de valor baixo / item único barato (a margem não comporta).
- Cliente que já compra com frequência (não treinar a esperar desconto).

Quando **vale** oferecer:
- Carrinho de valor alto parado há mais de 24h (frete grátis costuma ser a alavanca mais forte e barata).
- Sinal de objeção de preço.
- Toque 3, como empurrão final com prazo.

Hierarquia de oferta, da mais barata para a loja à mais cara:
1. **Frete grátis** (ou frete fixo simbólico) — geralmente o maior gatilho com menor custo de margem.
2. **Cupom pequeno (5–10%)** — preferir um já existente na Nuvemshop.
3. **Brinde / mimo** (adesivo, bolacha de proteção, etc.) — para cliente colecionador, às vezes vale mais que %.

Sempre que eu sugerir um cupom que ainda não existe, ele vai marcado claramente como **[APROVAR COM O DONO]** para você não disparar antes de confirmar.

---

## 5. Segmentação por caso (a personalização)

Em cada carrinho eu leio o resumo do pedido e classifico o caso antes de escrever a mensagem:

- **Carrinho de valor alto / vários discos:** vale mais esforço. Tom de atendimento dedicado, oferta de frete grátis se travou.
- **Item único e barato:** toque leve, sem desconto, só lembrete.
- **Item raro / última cópia / lançamento:** gatilho de urgência real ("essa é a última que temos"). Forte para colecionador.
- **Cliente recorrente:** tom de quem já conhece, ângulo de relacionamento, evitar desconto.
- **Sinal de dúvida (ex.: frete alto, prazo):** focar em resolver a objeção, não em desconto.

---

## 6. Tom e templates de mensagem

Tom escolhido: **caloroso e com pegada de quem curte música**, sem exageros nem gíria forçada. Próximo, humano, de loja que entende de disco. Mensagem curta, uma pergunta no fim para abrir conversa.

Placeholders entre `{ }` eu preencho em cada caso. Toda mensagem leva o link do carrinho.

### Toque 1 — Lembrete (sem desconto)
> Oi, {nome}! Aqui é da Monstro Discos 🎶
> Vi que você montou um carrinho com {item/resumo} e ele ficou esperando por aí. Separei pra não correr risco de sumir do estoque.
> Quer que eu te ajude a finalizar? É só por aqui: {link_carrinho}
> Qualquer dúvida sobre frete ou prazo, é só me chamar.

### Toque 2 — Incentivo leve (frete grátis / cupom pequeno)
> Oi, {nome}! Voltando aqui sobre seu carrinho na Monstro Discos 🎶
> Pra te dar um empurrãozinho, consigo {oferta: ex. liberar o frete grátis / aplicar o cupom {codigo} de {X}%} no seu pedido com {item/resumo}.
> Finaliza por aqui que já entra com a condição: {link_carrinho}

### Toque 2 — Item raro / urgência (sem desconto)
> Oi, {nome}! Sobre aquele {item} que ficou no seu carrinho na Monstro Discos…
> É uma das últimas cópias que temos e ele costuma sair rápido. Não quis deixar você perder.
> Garante a sua por aqui: {link_carrinho}

### Toque 3 — Última chance (incentivo com prazo)
> Oi, {nome}! Última passada aqui 🙂
> A condição de {oferta} pro seu carrinho ({item/resumo}) vale até {prazo}. Depois disso não consigo segurar.
> Se ainda quiser, é só finalizar: {link_carrinho}

Esses são bases. Em cada caso eu adapto à pessoa e ao produto, não mando texto robô.

---

## 7. Observações operacionais

**Sobre o link de WhatsApp:** o link que eu gero (`https://wa.me/55DDDNUMERO?text=mensagem`) abre a conversa **com o número do cliente** e já com a mensagem escrita. Quem clica precisa estar logado no WhatsApp do número da loja que vai disparar. Ou seja: a pessoa que for enviar abre o link a partir do celular/WhatsApp Web logado no número oficial da Monstro Discos. O número da loja não entra no link — ele define só de qual conta a mensagem sai.

**Controle de toques:** para eu saber se um carrinho está no toque 1, 2 ou 3, preciso de um registro do que já foi enviado. Posso manter uma planilha simples (data, cliente, carrinho, toque, resultado) e atualizar a cada rodada. Sem isso, trato tudo como toque 1.

**LGPD / bom senso:** só contatamos quem deixou o contato no próprio checkout (o que já é o caso dos carrinhos abandonados). Se a pessoa pedir para não receber mais, ela sai da lista.

---

## 8. O que acontece quando você der o comando (processo de execução)

Ver documento separado: `processo-execucao-recuperacao.md`.
