# Migração preparada para repositório público (D-079)

26/10/2026. Nada foi publicado ou enviado ao GitHub nesta preparação. O repositório antigo continua privado. A pasta `migracao-publica/painel-monstro-publico/` contém uma cópia independente, com um único commit, sem remote e sem histórico anterior. Use SOMENTE essa pasta para a primeira publicação.

O nome `painel-monstro-publico` é uma sugestão. Se escolher outro, ajuste o endereço do remote e a propriedade GITHUB_REPO do vigia. Não é necessário renomear módulos Python ou planilhas.

## 1. O que foi retirado da fonte pública

- A planilha-modelo XLSX saiu do versionamento. Cópia privada em `dados/referencia-privada/`; não acompanha a migração.
- Contatos reais encontrados nos testes viraram nomes e telefones fictícios. Referências pessoais relacionadas foram retiradas das decisões históricas.
- Cofre.gs usa emails de exemplo na inicialização; os acessos reais continuam somente no Apps Script/planilha privada. Não rode prepararCofre novamente para migrar o GitHub.
- Identificadores concretos de planilha/pasta foram removidos da fonte. Apps Script usa PLANILHA_ID em Propriedades do script. O painel web recebe o ID do Cofre somente depois da autorização. O modelo de artifact precisa de configuração privada, fora do git.
- `.env`, `dados/`, `credenciais/`, planilhas locais, envelopes cifrados e a cópia de migração estão no `.gitignore`. Arquivos não rastreados preexistentes do usuário não foram incluídos.

Auditoria manual de todos os arquivos rastreados, textos e binários, mais verificação de emails/telefones/CPF/segredos e comparação com nomes completos do cache privado. Limite: revisão de fonte não comprova a configuração de compartilhamento de serviços externos. Relatórios com achados originais e endereços reais ficam somente em `dados/auditoria-publica/`, fora da cópia pública.

## 2. Cache público e logs

Os dois workflows restauram e salvam somente `dados/cache-publico/api.aes256`. `dados/api` existe em texto legível apenas no runner durante a rodada, sem upload de artifact. Criptografia AES-256-GCM com nonce aleatório e autenticação do arquivo inteiro, pela biblioteca cryptography. CACHE_KEY é um Secret novo de 32 bytes aleatórios em base64; não é senha de usuário.

Sem chave válida, com chave diferente, arquivo alterado ou cache ausente: não restaura dados, a rotina baixa novamente. O checkout do Actions começa limpo. Chave ausente/inválida impede salvar o envelope; não existe alternativa de salvar texto puro. Alterar a chave invalida o cache anterior e força uma nova coleta. Ferramenta local recusa sobrescrever cache já existente, para proteger os dados do computador.

O cache antigo em texto puro não é transferido e nunca deve ser importado no público. Cache perdido não deve zerar marcações humanas da planilha. O diário de cadastro existente continua protegendo contra repetição; não apagar cadastro_execucao ou produto_id.

Logs usam contagens e mensagens fixas, sem prévias de clientes, mensagens de exceção, respostas HTTP ou traceback com dados. Detalhes operacionais permanecem nas abas privadas. Testes injetam dados fictícios em sucesso e falhas para conferir stdout/stderr. Não ativar debug HTTP, printenv ou trace do shell no Actions.

## 3. Workflows e endereços

Somente schedule, workflow_dispatch e repository_dispatch; permissões contents: read, runner padrão ubuntu-latest, sem upload-artifact. Checkout não persiste credenciais. Os dois workflows compartilham concorrência e cache cifrado. Concorrência NÃO atravessa repositórios: desligue o antigo antes de ligar o novo.

| Referência | Proteção prevista e risco |
|---|---|
| Planilha Google de dados | Declarada privada. Saber o endereço não dá permissão, mas ACL pública daria. URL/ID retirados da fonte; conferir Compartilhar > Acesso geral > Restrito. Não foi possível provar o acesso anônimo nesta sessão. |
| Pasta Drive de fotos | Privada por configuração declarada, acesso da conta de serviço. ID removido de docs. Confirmar o compartilhamento. |
| Apps Script ENTRADA | Fonte exige login Google e checagem de acesso no Cofre. URL de implantação não estava nos arquivos. Implantação real não foi auditada. |
| Apps Script COFRE | Implantado como Qualquer pessoa, mas código exige SEGREDO e usuário autorizado. URL concreta já fica nas propriedades da ENTRADA. Não expor o SEGREDO. Não é uma página com login próprio. |
| Apps Script SORTEIO | Endpoint intencionalmente público, usado na página da raspadinha. URL concreta permanece no HTML, pois não é credencial. Pode receber chamadas externas e exige controle de abuso; não chamar jogar/abriu para testar a migração. Nenhuma ação real foi executada. |
| Artifact Claude | Não foi localizada URL compartilhável concreta, só cópia da fonte e menções. A publicação e as permissões do artifact não foram comprovadas; fonte de interface não contém as linhas da planilha. |
| Loja, Pages da raspadinha, fontes, logo e contato comercial | Referências públicas intencionais. Contato/endereço da loja não foram classificados como dados de cliente. Links renderizados de campanhas podem conter email ou cupom; jamais versionar emails reais exportados. |

Inventário com os endereços concretos e as limitações de verificação: `dados/auditoria-publica/LINKS_E_RISCOS.md`, na cópia privada original. Ele não deve acompanhar a publicação.

## 4. Criar o repositório novo, sem histórico

Somente após revisar esta entrega e confirmar a publicação:

1. No GitHub, botão **+** no topo > **New repository**.
2. Em **Owner**, escolha a conta/organização usada pela Monstro. **Repository name**: `painel-monstro-publico` (ou seu nome escolhido).
3. Em **Choose visibility**, marque **Public**. Não inicialize README, `.gitignore` nem licença; o primeiro commit já está pronto. Clique **Create repository**. Não use Fork, Import repository ou mudança de visibilidade do antigo.
4. No novo: **Settings > Actions > General > Actions permissions > Disable actions > Save**, para configurar antes da primeira execução.
5. Abra um terminal na pasta limpa indicada acima. Confira:

```powershell
git rev-list --all --count
git remote -v
git status --short
```

O primeiro deve mostrar `1`; os outros não mostram remote nem alterações. Se estiver no projeto antigo, pare e entre na pasta limpa.

6. Copie a URL HTTPS exibida pelo GitHub. Configure-a e envie SOMENTE main, sem `--mirror`, `--all` ou tags do antigo:

```powershell
git remote add origin https://github.com/SEU_USUARIO/painel-monstro-publico.git
git push -u origin main
```

Esses comandos são orientação para a publicação autorizada depois; o agente não os executou. O GitHub pode pedir login da conta com acesso ao novo repositório. Não use o token limitado do vigia para enviar workflows.

## 5. Recriar Secrets e variáveis

No novo: **Settings > Secrets and variables > Actions > Secrets > New repository secret**. Preencha **Name**, **Secret** e clique **Add secret**, uma vez para cada nome:

| Name | Onde obter o valor privado |
|---|---|
| NUVEMSHOP_STORE_ID | Mesmo ID usado no `.env` atual. |
| NUVEMSHOP_TOKEN | Mesmo token do aplicativo da loja; não alterar permissões nesta migração. |
| NUVEMSHOP_USER_AGENT | Mesmo identificador do aplicativo atual. |
| PLANILHA_ID | Mesmo ID da planilha privada. |
| GOOGLE_SERVICE_ACCOUNT_JSON | Conteúdo inteiro do arquivo da conta de serviço em credenciais/, não o nome do arquivo. |
| BREVO_API_KEY | Chave atual do Brevo. |
| META_ADS_ACCOUNT_ID | ID atual da conta de anúncios. |
| META_ADS_TOKEN | Token atual de leitura do Meta. |
| DISCOGS_TOKEN | Token atual do Discogs, se já configurado. |
| CACHE_KEY | Chave nova gerada abaixo, igual para os dois workflows. |

O GitHub NÃO mostra o valor de um Secret antigo para copiar. Use o `.env`, arquivo original de credenciais ou o serviço de origem. Não cole chaves na conversa. GITHUB_TOKEN do Actions é automático e não entra nessa lista; token do vigia é outro, criado no próximo passo.

Para gerar CACHE_KEY sem mostrar no terminal, execute no PowerShell do seu computador, no projeto privado original:

```powershell
& .\.venv\Scripts\python.exe -c "import base64,secrets; print(base64.b64encode(secrets.token_bytes(32)).decode())" | Set-Clipboard
```

Cole no **Secret** de CACHE_KEY e clique **Add secret**. Guarde uma cópia em local privado ou `.env`; nunca em documento público. Trocar a chave só causa nova coleta, não exige recuperar o cache velho.

Em **Variables**, use **New repository variable** para copiar exatamente os valores atuais de `META_ADS_API_VERSION` e `BREVO_MODO_TESTE`. Não altere o modo do Brevo durante a migração. Se ausente, o workflow mantém o padrão seguro `sim`; isso não autoriza desativar modo teste.

## 6. Segurança de contribuições externas

No novo: **Settings > Actions > General**, encontre **Approval for running fork pull request workflows from contributors** (pode aparecer como **Fork pull request workflows from outside collaborators**). Selecione **Require approval for all external contributors > Save**.

Em **Workflow permissions**, mantenha **Read repository contents and packages permissions** e não habilite **Allow GitHub Actions to create and approve pull requests**. Os YAML já limitam o token a contents: read. A opção de aprovação é proteção adicional; os workflows desta versão não têm gatilho de pull request.

## 7. Token novo e Apps Script do vigia

1. Na sua conta GitHub: foto do perfil > **Settings > Developer settings > Personal access tokens > Fine-grained tokens > Generate new token**.
2. **Token name**: `vigia-cadastro-publico`. **Resource owner**: dono do repositório novo. Escolha uma **Expiration** e anote quando renovar.
3. **Repository access > Only select repositories**, marque só o novo repositório.
4. Em **Repository permissions**, adicione **Contents > Read and write**; Metadata de leitura é automático. Essa é a permissão exigida por repository_dispatch, diferente do token contents: read que roda dentro do workflow. Não conceder acesso a todos os repositórios.
5. Clique **Generate token**, copie e guarde em local privado. Se a organização exigir aprovação, aguarde antes do teste.
6. Abra o projeto **vigia-cadastro** no Apps Script da Monstro. **Configurações do projeto** (engrenagem) > **Propriedades do script > Editar propriedades do script**:
   - `GITHUB_TOKEN`: troque pelo token novo.
   - `GITHUB_REPO`: `SEU_USUARIO/painel-monstro-publico`, exatamente dono/nome escolhido, sem https.
   - `PLANILHA_ID`: ID da planilha atual, que já aparecia no código privado antigo. Nada muda na planilha.
7. Copie a versão nova de `apps-script/vigia-cadastro.gs` para esse projeto, clique **Salvar projeto**. Ela lê as três propriedades e não tem mais destino fixo para o repositório antigo. Não executar arquivarFotos para testar.
8. Não reinstale o agendamento se ele já existe e não rode dispararCadastroAgora ainda. O teste do vigia será feito depois do Run workflow completo. Depois dele, escolha **dispararCadastroAgora > Executar**; isso é rodada real e pode criar discos que já estejam aprovados.

Não é preciso republicar ENTRADA, COFRE, SORTEIO ou a página pública da raspadinha para mudar o GitHub. Os dados reais da Mariana e demais acessos permanecem apenas no Apps Script/planilha. Se futuramente atualizar esses fontes saneados, configure PLANILHA_ID nas propriedades do Cofre/Sorteio e use ENTRADA/Cofre/Painel compatíveis; não substituir configuração de produção por placeholders.

## 8. Desligar o antigo e testar o novo

1. No repositório ANTIGO, que continua privado: **Settings > Actions > General > Actions permissions > Disable actions > Save**. Não apagar repositório, histórico, dados ou Secrets antigos. Ele fica como backup privado.
2. Confira que não há execução antiga em andamento; espere concluir antes de ligar o novo. Grupos de concorrência não impedem duas rotinas em repositórios diferentes.
3. No novo: **Settings > Actions > General > Actions permissions**, habilite as actions utilizadas (por exemplo **Allow all actions and reusable workflows**) e clique **Save**, mantendo as proteções acima.
4. **Actions > Rotina do Painel > Run workflow**. Em **Use workflow from**, selecione **main**. Deixe as opções de baixar tudo/rebaixar anúncios desmarcadas; a primeira rodada já começa sem cache e baixa tudo. Clique **Run workflow**.
5. Abra a execução. Primeira rodada: mensagem de cache indisponível é esperada; ao fim, deve aparecer cache criptografado preparado e etapa de salvar somente o envelope. Segunda rodada deve mostrar cache autenticado restaurado. Nunca baixar ou publicar dados/api como artifact para conferir.
6. Confira na planilha a aba rodada e a atualização do painel. Marcações manuais e aprovações continuam na mesma planilha. Não limpar dados para testar. A rotina mantém os efeitos reais que já tinha; disco aprovado pode ser criado oculto, e o Brevo respeita a variável copiada.
7. Só depois, teste o vigia como descrito acima e acompanhe **Actions > Cadastro de discos aprovados**.

## Fontes oficiais conferidas

- [Cobrança do Actions](https://docs.github.com/en/billing/concepts/product-billing/github-actions): runners padrão em repositórios públicos são gratuitos; armazenamento e limites de cache continuam existindo. Não usar larger runners para esta migração.
- [Segurança do cache](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching): leitores e forks podem acessar caches, por isso o envelope é obrigatório.
- [Configurações do Actions](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository): aprovações e desativação de actions.
- [repository_dispatch e token fine-grained](https://docs.github.com/en/rest/repos/repos#create-a-repository-dispatch-event): Contents write para o disparo externo.
- [AESGCM](https://cryptography.io/en/latest/hazmat/primitives/aead/#cryptography.hazmat.primitives.ciphers.aead.AESGCM): criptografia autenticada, chave de 256 bits e nonce aleatório.
