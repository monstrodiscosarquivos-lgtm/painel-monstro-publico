# Régua automática no Brevo · guia (Etapa 7)

**Estado: sempre em MODO TESTE.** O Painel lê o Brevo e mostra o que faria; não escreve nada lá. O modo teste só sai quando o Túlio escreve exatamente
`pode desligar o modo teste` na conversa do projeto.

## Como funciona
1. Todo dia (primeira rodada depois das 6h, horário de Brasília) o Painel calcula, para cada cliente que aceita marketing, cinco atributos:
   `ETAPA`, `DIAS_SEM_COMPRAR`, `FAMILIA`, `VIP`, `CONTROLE`, e a lista do Brevo em que ele deve estar.
2. Compara com o que já está no Brevo e monta o plano: atributos a atualizar, listas a acrescentar e a tirar.
3. Em modo teste só grava o plano nas abas `brevo_plano` (resumo) e `brevo_mudancas` (quem mudou de etapa ou de lista).
4. A cada rodada de hora em hora o Painel também lê a conta do Brevo (uma leitura simples). Isso mantém a chave viva: o Brevo
   desativa a chave depois de 90 dias sem nenhuma chamada bem-sucedida.
5. Se o Brevo recusar a chave ou bloquear o IP, a rodada continua normal, o status vai para a aba `rodada` e o script do Google manda o
   email de alerta (um por dia por tipo de erro) para o endereço "Email de alerta (rotina parada)" da aba `Configuração`.

## Regras fixas
- O Painel nunca dispara email. Ele atualiza atributos e listas; quem envia são as automações do Brevo.
- Só atualiza contatos que **já existem** no Brevo. Não cria contato novo.
- Contato descadastrado no Brevo (`emailBlacklisted`) e quem não aceita marketing na Nuvemshop nunca são tocados.
- Grupo de controle (cerca de 10% de cada etapa) fica com `CONTROLE = Sim` e **fora das listas**. O sorteio é estável por cliente e por ciclo
  (muda só quando o cliente compra de novo); não muda de um dia para o outro.
- VIP (3+ compras ou R$1.000+) com 75 a 104 dias não entra em lista de email: recebe WhatsApp pela fila.
- Quem está em Descanso (210+ dias) ou sem etapa não entra em lista.
- A chave nunca aparece em log, aba ou mensagem.

## O que o Túlio cria no Brevo (uma vez só)

### 1. Os 5 atributos de contato
No Brevo: **Contatos** > **Configurações** > **Atributos de contato** > **Adicionar um novo atributo**. Crie, com os nomes **exatamente assim**
(maiúsculas, com sublinhado):

| Nome | Tipo |
|---|---|
| `ETAPA` | Texto |
| `DIAS_SEM_COMPRAR` | Número |
| `FAMILIA` | Texto |
| `VIP` | Booleano (sim/não) |
| `CONTROLE` | Booleano (sim/não) |

### 2. As 4 listas
**Contatos** > **Listas** > **Criar uma lista**. Nomes exatos (o ponto no meio é " · " com espaços):

- `Painel · Etapa 0 Pós-compra`
- `Painel · Etapa 1 Lembrete`
- `Painel · Etapa 2 Convite`
- `Painel · Etapa 3 Última chamada`

Os nomes podem mudar na coluna **Lista no Brevo** da aba `Régua`; se mudar lá, use o mesmo nome no Brevo.

### 3. Uma automação por lista
Para cada uma das 4 listas: **Automações** > **Criar uma automação** > **Começar do zero**:
1. **Gatilho:** "Um contato é adicionado a uma lista" e escolha a lista.
2. **Ação:** "Enviar um email" e escolha ou crie o modelo da etapa (texto da régua no `AGENTS.md`).
   - Etapa 0: obrigado + novidades do gênero (`{{ contact.FAMILIA }}`), sem desconto.
   - Etapa 1: novidades + "o que você está caçando?", sem desconto.
   - Etapa 2: frete grátis acima de R$150 por 10 dias (cupom do mês).
   - Etapa 3: 10% por 7 dias, em toda a loja (cupom do mês).
3. Em **Configurações da automação**, deixe desligada a opção de o mesmo contato entrar de novo (ou permita só depois de 90 dias).
4. **Deixe a automação desligada** até decidirmos ligar a régua. Com o modo teste, nenhuma lista recebe contatos, então nada dispara.

### Atenção antes de liberar
Quando o modo teste for desligado, no primeiro dia **todo mundo que está dentro das janelas entra nas listas de uma vez** (em 10/10/2026 seriam
cerca de 330 pessoas) e as automações ligadas mandam o email na hora. Decida antes se quer ligar as automações no mesmo dia ou aos poucos.
O plano Starter do Brevo permite automação para até 2.000 contatos.

## Como conferir (em modo teste)
Na aba `brevo_plano` da Planilha Google:
- `modo`: deve dizer "TESTE (nada foi escrito no Brevo)".
- `clientes na régua`, `descadastrados (não mexe)`, `atributos a atualizar`, `entram em lista`, `saem de lista`, `controle (sem lista)`.
- `listas que faltam no Brevo` e `atributos que faltam no Brevo`: depois de criar tudo acima, as duas linhas devem dizer "nenhuma" e "nenhum".
- Os totais de cada etapa (recebe + controle) batem com a aba `regua_hoje`. A divisão controle/recebe é estável por cliente e pode diferir
  um pouco da lista mensal manual (que sorteia de novo todo mês).

Na aba `rodada`: `brevo_status` (ok (modo teste), erro: chave_invalida, erro: bloqueio_ip, sem chave) e `brevo_ultima_leitura_ok`.

## Desligar o modo teste (só com a frase exata)
O Túlio escreve na conversa: **pode desligar o modo teste**. Só então o agente diz o passo a passo para mudar a variável do repositório
`BREVO_MODO_TESTE` para `nao` no GitHub (Settings > Secrets and variables > Actions > Variables). Para voltar, apague a variável ou ponha `sim`.

## Chave de pausa, etapas ligadas e cupom por contato (7.1)

Quatro grupos de linhas no fim da aba `Configuração` (nomes exatos; maiúsculas e minúsculas tanto faz):

| Parâmetro | Valor | O que faz |
|---|---|---|
| `Régua no Brevo` | Ligada ou Pausada | Pausada: os atributos continuam atualizando; as listas ficam congeladas (ninguém entra nem sai) |
| `Pausa programada de` | 20/11/2026 | Início da pausa automática (em branco = sem pausa) |
| `Pausa programada até` | 30/11/2026 | Último dia da pausa; a régua volta no dia seguinte |
| `Etapa 0 no Brevo` | Ligada | 15 a 44 dias, só quem tem 1 compra |
| `Etapa 1 no Brevo` | Desligada | 45 a 74 dias |
| `Etapa 2 no Brevo` | Desligada | 90 a 119 dias |
| `Etapa 3 no Brevo` | Desligada | 180 a 209 dias |

- **Linha ausente ou valor que o Painel não entende = o mais seguro** (régua Pausada, etapa Desligada), com aviso na aba `brevo_plano`.
  Datas podem ser dd/mm/aaaa, aaaa-mm-dd ou data da planilha. Pausa com só uma das datas, ou fim antes do início, também vira Pausada.
- **Etapa desligada:** ninguém novo entra na lista dela; quem já está sai pela regra normal.
- **Régua pausada** (chave ou pausa programada, contando as duas pontas): ninguém entra e ninguém sai de nenhuma lista da régua.
  Ao religar, entra só quem ainda não está na lista.
- A aba `brevo_plano` mostra, no fim, **Régua no Brevo** (Ligada / Pausada / Em pausa programada até dd/mm), **Etapas ligadas** e avisos.
  Se você mudar uma dessas linhas, o plano é refeito na rodada seguinte (não espera o dia seguinte).

### Ordem para ligar uma etapa (importante)
1. **Primeiro, no Brevo:** confira a automação da etapa e ligue-a.
2. **Confira se a automação permite que o contato entre de novo num ciclo futuro.** Quem compra e volta a sumir passa pela etapa outra vez meses depois;
   se a automação não deixar reentrar, essa pessoa nunca mais receberá o email da etapa. Em **Configurações da automação**, deixe a reentrada permitida
   (de preferência só depois de 90 dias).
3. **Só então, aqui:** mude `Etapa N no Brevo` para Ligada. Ligar aqui antes de ligar lá faria o contato entrar na lista sem ninguém para enviar.

### Cupom por contato (Etapas 2 e 3)
- Atributos novos de texto no Brevo: **`CUPOM`** e **`CUPOM_ATE`** (crie em Contatos > Configurações > Atributos de contato).
- **Só quando o contato ENTRA na lista da Etapa 2 ou 3:** `CUPOM` = o cupom da etapa na aba `Régua` com `<MÊS>` trocado pelo mês atual
  (`VOLTAFRETE<MÊS>` em outubro vira `VOLTAFRETEOUT`); `CUPOM_ATE` = hoje + a validade da etapa, em dd/mm.
- Os atributos são gravados **antes** de o contato entrar na lista, em chamadas separadas e uma por uma (a automação dispara na entrada).
- No email da automação use `{{ contact.CUPOM }}` e `{{ contact.CUPOM_ATE }}`.
- **O cupom do mês na Nuvemshop precisa valer até 10 dias (Etapa 2) ou 7 dias (Etapa 3) depois do fim do mês**, porque quem entra no último dia do mês
  recebe a validade contada a partir dele.

## Como o Painel escreve no Brevo (modo real)

1. Cria os atributos que faltam (`ETAPA`, `DIAS_SEM_COMPRAR`, `FAMILIA`, `VIP`, `CONTROLE`, `CUPOM`, `CUPOM_ATE`).
2. Atualiza os atributos **contato por contato**, na hora, até 10 chamadas por segundo, com no máximo 7 minutos por rodada; quem vai entrar numa lista vai primeiro.
   O que não couber continua na rodada seguinte (a aba `brevo_plano` mostra `pendentes de aplicar`). A importação em lote do Brevo não é usada.
3. **Só depois** coloca na lista quem teve os atributos gravados (a automação do Brevo dispara na entrada).
4. Tira das listas quem deixou de ser alvo da etapa.
5. Falha em um contato não derruba os outros. Chave inválida ou bloqueio de IP interrompem e disparam o alerta por email.

### Virar para o modo real (só depois de o Túlio escrever "pode desligar o modo teste")
1. No Brevo, confirme que a **automação da Etapa 0 está ATIVADA** (quem entrar na lista dispara o email na hora; se estiver desativada, ninguém recebe e depois ligar não recupera quem já entrou).
2. No GitHub, no repositório: **Settings** > **Secrets and variables** > **Actions** > aba **Variables** > **New repository variable**.
   Name: `BREVO_MODO_TESTE`, Value: `nao`. Clique em **Add variable**.
3. A rodada do minuto 7 da próxima hora refaz o plano (a troca de modo força isso) e aplica. Acompanhe pela aba `brevo_plano`
   (`modo` = REAL, `aplicado no Brevo`, `pendentes de aplicar`).
4. **Voltar atrás:** mude a variável para `sim` (ou apague). A rodada seguinte volta ao modo teste; o que já foi escrito no Brevo fica como está.
