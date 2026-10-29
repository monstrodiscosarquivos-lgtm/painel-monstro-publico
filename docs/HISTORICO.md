# Histórico

Uma entrada por sessão, a mais recente no topo. Nunca apague entradas antigas.

Modelo:

```
## AAAA-MM-DD · agente · etapa
- Feito:
- Arquivos alterados:
- Como conferir:
- Problemas conhecidos:
- Próximo passo:
```

## 2026-10-29 · Antigravity · confirmação de recortes D-091 e push no repositório público
- Feito: executado `recortar-lote 2026-10-28 --confirmar` com atualização dos cantos de 335 fotos em `cadastro_fotos` e limpeza da coluna `fotos_ajustadas` em `cadastro_rascunhos` para regeneração das prévias pelo Painel. Auditoria de segurança confirmada limpa no repositório público e executados `git add`, `git commit` ("Indicações da fila (D-089) e recorte por fundo branco (D-091)") e `git push` com sucesso em `migracao-publica/painel-monstro-publico`.
- Arquivos alterados: planilha Google (`cadastro_fotos`, `cadastro_rascunhos`), `migracao-publica/painel-monstro-publico` (commit e push), `docs/ESTADO.md`, `docs/HISTORICO.md`.
- Como conferir: conferir `cadastro_fotos` na planilha e commits no repositório público GitHub `monstrodiscosarquivos-lgtm/painel-monstro-publico`.
- Problemas conhecidos: nenhum.
- Próximo passo: acompanhar regeneração das prévias nas próximas rodadas da rotina (20 discos por vez).

## 2026-10-29 · Antigravity · detecção de cantos por fundo branco e comando recortar-lote (D-091)
- Feito: implementada detecção de cantos por fundo branco em fotos claras/em pé (capas com minAreaRect e 1% de margem; vinil com bounding box e 2% de folga, rejeitando diâmetros < 50% do menor lado para não recortar apenas o rótulo). Novo comando recortar-lote LOTE [--confirmar] para recalcular cantos e gerar folhas de prévias. Executado no lote 2026-10-28 em modo simulação: 95 discos processados, 298 fotos com novo recorte automático e 37 inteiras, 8 folhas de prévias geradas em dados/cadastro_ia/2026-10-28/folhas_previas/. Criados 4 testes sintéticos e suíte completa executada com 757 testes passando. Planilha não alterada (aguardando ok).
- Arquivos alterados: scripts/cadastro_lote.py, tests/test_cadastro_lote.py, docs/DECISOES.md, docs/CADASTRO_IA.md, docs/ESTADO.md, docs/HISTORICO.md.
- Como conferir: .venv\Scripts\python -m pytest tests/test_cadastro_lote.py -q (41 testes) e folhas de prévias em dados/cadastro_ia/2026-10-28/folhas_previas/.
- Problemas conhecidos: nenhum.
- Próximo passo: aguardar OK do Túlio para rodar recortar-lote 2026-10-28 --confirmar.

## 2026-10-29 · Antigravity · indicações mais certeiras na fila G45 e VIP (D-089)
- Feito: implementado gênero fino primeiro com base na subcategoria da loja (caindo para a família larga apenas se não houver estoque na subcategoria); desempate priorizando mesmo artista (+2) e artistas com coocorrência em pedidos de outros clientes (+1); fallback para modelo `G45_GERAL` sem recomendação específica para itens sem gênero confiável (adicionado à aba Mensagens); lista KW de Metal ampliada com bandas nacionais (Violator, Korzus, Torture Squad, Dorsal Atlântica, Nervosa, Crypta, Shaman); formato natural de nome na mensagem ("Álbum, do Artista"). Criados 5 testes específicos cobrindo todos os cenários exigidos e suíte completa executada com 753 testes passando.
- Arquivos alterados: `painel_monstro/motor/generos.py`, `painel_monstro/saidas/carrinhos.py`, `painel_monstro/saidas/carrinhos_planilha.py`, `painel_monstro/saidas/fila_unica.py`, `painel_monstro/saidas/regua_planilha.py`, `tests/test_fila_unica.py`, `docs/DECISOES.md`, `docs/ESTADO.md`, `docs/HISTORICO.md`.
- Como conferir: `.venv\Scripts\python -m pytest tests/test_fila_unica.py -q` (27 testes) e `.venv\Scripts\python -m pytest -q` (753 testes passando).
- Problemas conhecidos: nenhum.
- Próximo passo: commit das alterações da D-089.

## 2026-10-29 · Antigravity · gravação do lote 2026-10-28 (93 rascunhos)
- Feito: processado o lote `2026-10-28` com 346 fotos na pasta `entrada`. Geradas 29 folhas de contato, estruturado o lote com 93 discos para cadastrar e 4 pulados (d01 a d03 de sobras anteriores e d84 sem capa frontal). Rodada a conferência (0 erros, 101 avisos) e, após confirmação do Túlio, executado `gravar --confirmar`: gravados 93 rascunhos (`2026-10-28-03` a `2026-10-28-95`) em `cadastro_rascunhos`, inseridas 338 linhas em `cadastro_fotos` e renomeadas 339 fotos na pasta `entrada`. Preços mantidos em branco para preenchimento posterior no Painel.
- Arquivos alterados: `dados/cadastro_ia/2026-10-28/lote.json`, `dados/cadastro_ia/2026-10-28/conferencia.md`, `dados/cadastro_ia/2026-10-28/plano.json`, `docs/HISTORICO.md`, `docs/ESTADO.md`.
- Como conferir: aba Cadastro do Painel (`2026-10-28-03` a `2026-10-28-95`).
- Problemas conhecidos: nenhum.
- Próximo passo: Túlio definir os preços e revisar/aprovar os 93 rascunhos no Painel.

## 2026-10-27 · Antigravity · garimpo aceita nome de produto colado (D-085)
- Feito: nova `garimpo.palavras_do_pedido` (ignora parênteses, anos, formato/estado e palavras de 1 a 2 letras; com "/" ou ":" vale o primeiro trecho depois do artista; cor do pedido obrigatória; disco só com ano mantém o ano). `alertas_garimpo` passa a usar essa função; `juntar_desejos` guarda o artista do formulário (coluna interna `artista`). 4 testes novos (Bon Jovi casa, Coisa de Louco vermelho não casa com azul, Nenhum de Nós 1992 não casa com Cardume, palavras extraídas).
- Arquivos alterados: `painel_monstro/saidas/garimpo.py`, `painel_monstro/saidas/fila_unica.py`, `tests/test_garimpo_e_meta.py`, `docs/DECISOES.md`, `docs/ESTADO.md`, `docs/HISTORICO.md`.
- Como conferir: `.venv\Scripts\python -m pytest tests/test_garimpo_e_meta.py tests/test_fila_unica.py -q` (56 passando). Na próxima rodada, a aba `Fila` pode ganhar linhas Garimpo de pedidos antigos que passaram a casar.
- Problemas conhecidos: pedidos cujo disco é uma letra ou sigla (Maglore "V", Heaven's Guardian "D.O.L.L.") ficam só com o artista obrigatório e casam com qualquer disco do artista que chegar.
- Próximo passo: nenhum. Túlio confirmou que disco de uma letra/sigla pode casar com qualquer disco do artista; ele confere na Fila se o aviso serve.

## 2026-10-27 · Antigravity · script de cadastro por agente local (D-078) e gravação do lote 2026-10-27
- Feito: implementado `scripts/cadastro_lote.py` (`folhas`, `recorte`, `conferir`, `gravar`, `renomear-lote`) conforme `docs/CADASTRO_IA_SCRIPT.md`, adicionado `CADASTRO_PASTA_LOCAL` em `painel_monstro/config.py` e `env-exemplo.txt`, e criada a suíte `tests/test_cadastro_lote.py` (37 testes cobrindo regressão exata do lote 2026-10-26, validações, numeração, colisões, retomada por `plano.json`, modo simulação, detecção sintética e 92,1% de acerto nas fotos reais). Conferido o lote antigo `2026-10-26` contra a planilha real (recusado com 142 erros de fotos já cadastradas). Geradas as folhas do lote `2026-10-27` (29 fotos na pasta `entrada`), montado `dados/cadastro_ia/2026-10-27/lote.json` (2 discos para cadastrar e 7 pulados), rodado `conferir` (0 erros, 0 avisos) e, após confirmação do Túlio, executado `gravar --confirmar` (gravados `2026-10-27-01` e `2026-10-27-02` em `cadastro_rascunhos` e 8 linhas em `cadastro_fotos`, com 12 fotos renomeadas na pasta `entrada`).
- Arquivos alterados: `scripts/cadastro_lote.py`, `tests/test_cadastro_lote.py`, `painel_monstro/config.py`, `env-exemplo.txt`, `AGENTS.md`, `PROMPTS.md`, `docs/DECISOES.md`, `docs/ESTADO.md`, `docs/HISTORICO.md`.
- Como conferir: `..\..\.venv\Scripts\python.exe -m pytest -q` (754 testes passando) e aba Cadastro do Painel (`2026-10-27-01` e `2026-10-27-02`).
- Problemas conhecidos: nenhum.
- Próximo passo: revisar e aprovar os rascunhos `2026-10-27-01` e `2026-10-27-02` na aba Cadastro do Painel.

## 2026-10-27 · Antigravity · publicar disco ao aprovar (D-082) e excluir cupons cancelados (D-083)
- Feito: Parte 1 (D-082): coluna `publicar` no fim de `cadastro_rascunhos`, caixa **Mostrar na loja assim que for criado** (marcada por padrão, com aviso amarelo em pendências de repetido/etiqueta) no Painel e publicação via `PUT /products/{id}` com `{"published": True}` somente após a última imagem confirmada na rotina (`painel_monstro/saidas/cadastro.py`), mantendo o `POST /products` sempre oculto e tratando falha de `PUT` como `criado` com pendência sem repetir. Parte 2 (D-083): `apagarCupom_` e suporte a `apagar` em `processarCancelamentos` (`apps-script/raspadinha/Sorteio.gs`) com trava contra cupom ativo/usado, botão **Excluir cupons cancelados (N)** e exclusão individual com confirmação no Painel, ocultação padrão dos excluídos (**Mostrar excluídos**) e preservação integral das métricas da campanha. `Painel.html` regerado com `montar_painel_web.py`. Cofre não alterado.
- Arquivos alterados: `painel_monstro/saidas/cadastro.py`, `tests/test_cadastro.py`, `apps-script/raspadinha/Sorteio.gs`, `apps-script/painel-web/painel-monstro.html`, `apps-script/painel-web/Painel.html`, `apps-script/teste_local.js`, `docs/DECISOES.md`, `docs/ESTADO.md`, `docs/HISTORICO.md`, `docs/CADASTRO.md`, `docs/RASPADINHA.md`.
- Como conferir: `..\..\.venv\Scripts\python -m pytest -q` (717 testes passando) e `node apps-script/teste_local.js` (42 testes passando).
- Problemas conhecidos: nenhum.
- Próximo passo: Túlio atualizar `Sorteio.gs` no Apps Script da raspadinha (Nova implantação) e `Painel.html` no projeto Entrada do Painel (Nova implantação).

## 2026-10-27 · Antigravity · origens da raspadinha (D-081) e pedidos fora da Nuvemshop na comissão (D-080)
- Feito: Parte 2 (D-081): coluna `origens` (R) em `rasp_campanhas`, reconhecimento de origens personalizadas e WhatsApp (`whats|wpp|zap`) em `Sorteio.gs` (`canal_`), bloqueio de `whatsapp` quando não permitido e liberação de origens personalizadas, seção "Outras origens desta campanha" no formulário da raspadinha no Painel, links prontos com botão Copiar e reclassificação imediata das jogadas antigas salvas como `outro`. Parte 1 (D-080): aba `pedidos_manuais` protegida em `SO_ESPECIAL` (`Cofre.gs`), bloco "Pedidos fora da Nuvemshop" na seção Comissão do Painel com formulário (Por parcela com divisão automática e resto na 1ª parcela, ou Mês único), rateio proporcional de valor, frete e taxa em `comCalc`, exibição na lista de pedidos do mês, na cascata e nos critérios registrados, e inclusão de meses futuros em `comMeses()`. `Painel.html` regerado com `montar_painel_web.py`.
- Arquivos alterados: `apps-script/raspadinha/Sorteio.gs`, `apps-script/painel-web/Cofre.gs`, `apps-script/painel-web/painel-monstro.html`, `apps-script/painel-web/Painel.html`, `apps-script/teste_local.js`, `tests/test_raspadinha.py`, `docs/DECISOES.md`, `docs/ESTADO.md`, `docs/HISTORICO.md`, `docs/RASPADINHA.md`.
- Como conferir: `node apps-script/teste_local.js` (40 testes passando) e `..\..\.venv\Scripts\python -m pytest -q` (708 testes passando).
- Problemas conhecidos: nenhum.
- Próximo passo: Túlio adicionar `origens` na célula `R1` de `rasp_campanhas` e atualizar as implantações do Sorteio, do Cofre e da Entrada no Apps Script conforme o passo a passo.

## 26/10/2026 · Codex · etapa 10, preparação da migração pública (D-079)

- Feito: auditoria de todos os rastreados; XLSX fora do git, contatos reais anonimizados, IDs internos retirados de fonte, Cofre com exemplos, vigia por propriedades. Cache AES-256-GCM autenticado nos dois workflows, proteção de logs e testes de privacidade. Exportador gera cópia auditada, sem histórico/remote, com identidade institucional de exemplo.
- Arquivos: workflows, Apps Script, docs/memória, scripts de auditoria/exportação, cache_seguro.py, log_publico.py, entradas CLI e testes. Untracked preexistentes do usuário preservados e fora da migração. Relatórios com originais exclusivamente em dados/auditoria-publica/.
- Conferir: base inicial 658 testes verdes. Validação final e commit limpo registrados no ESTADO/guia. Conferir rev-list --all --count = 1 dentro da cópia de migração, sem remote. Não publicar o histórico privado.
- Limites: sem push, criação de repositório, configuração de Secrets, alteração de ACL ou implantação externa. Nenhuma API de cliente/Brevo chamada. URL de sorteio é pública intencionalmente; ACL/login externos não comprovados. Frete continua sem execução/autorização.
- Próximo passo: Túlio revisar a entrega e confirmar antes da publicação; depois seguir docs/MIGRACAO_PUBLICA.md. Antigo continua privado, desligar seu Actions antes do novo.

## 15/10/2026 · Codex · etapa 10, fotos pelo nome exato

- Feito: completa somente arquivo_drive_id vazio de cadastro_fotos, pelo nome exato em observacao na entrada configurada. IDs existentes preservados; grava em lote por disco após revalidar linhas. Nome ausente/inexistente/repetido vira pendência sem criar produto e sem alterar status ou outras pendências. Confere inclusive etiquetas, que continuam fora do site.
- Arquivos: saidas/cadastro.py, tests/test_cadastro.py, AGENTS.md, docs/CADASTRO.md, DECISOES.md e ESTADO.md; esta entrada de HISTORICO. Nenhuma coluna nova.
- Como conferir: base com 600 testes verdes antes das mudanças; 616 passaram depois, sem rede. Testa nomes, duplicados/paginação, preenchimento persistente, IDs preservados, concorrência e bloqueio de produto aprovado. Aplicação real preencheu os 64 IDs; rascunhos e todas as demais colunas conferidos intactos. Backup privado fora do git, conforme ESTADO.
- Limites: vínculo de IDs não valida upload/cota do Drive nem cria produto. Nenhuma imagem baixada/copiada e nenhuma correção de frete executada. Commit e push autorizados explicitamente neste ajuste.
- Próximo passo: Cowork preservar os IDs preenchidos; próxima rotina pode gerar as prévias e Túlio revisa preços/conservação antes de aprovar.

## 15/10/2026 · Codex · Etapa 10, cadastro oculto e idempotente (D-067)

- Feito: cadastro aprovado gera produto sempre oculto, estoque 1, diário antes do POST, ID antes de imagens e reconciliação por SKU. Rascunhos recebem referências, Discogs opcional e prévias privadas; originais preservados e etiquetas excluídas. Só processar.py e cantos JSON do piloto copiados, sem fotos. Configurado ID Drive informado pelo Túlio e preparado contrato de 37 colunas/cadastro_fotos, preservando as 11 linhas originais.
- Arquivos: docs/CADASTRO.md incluído; cadastro.py, fotos.py, discogs.py, utm.py isolado, corrigir_frete.py, referência do piloto, requisitos, configuração, workflow, rotina, testes, auditor e AGENTS/DECISOES/ESTADO. Correção incidental de PermissionError temporário ao substituir cache de anúncios no Windows, com testes de preservação do arquivo anterior.
- Conferir: 600 testes Python passaram com dados/imagens fictícios, incluindo comparação das 45 marcações do piloto, idempotência e frete simulado em API falsa. Contratos e próximo passo exato no bloco Avisar o Cowork do ESTADO e docs/CADASTRO.md. Não alterou modo Brevo nem rodou rotina completa local.
- Limites: nenhum produto ou imagem criado na loja real e nenhuma correção de frete executada contra a loja, nem simulação. Discogs real ainda depende do Secret. Primeiras prévias exigem validar upload/cota da conta de serviço no Drive; Editor foi confirmado somente em leitura. Preços 200 do piloto precisam revisão. UTM não disponível no pedido/documentação consultados: nenhuma coluna adicionada a pedidos. Frete aguarda autorização escrita separada. Commit e push autorizados no pedido da Etapa 10.



---

## 2026-10-15 · Codex · etapa 9 (classificação e direção do Cowork)
- Feito: tipo() reconhece _local em qualquer posição, [evento] e alcance como evento; rmk como remarketing. Preservadas prioridade do tipo manual e de evento, classificação sazonal e leitura sem distinguir maiúsculas/minúsculas. Registrado, conforme informação do Túlio: Cowork publicou aba Anúncios e agendou direção seg/qua/sex às 7h46 em anuncios_direcao.
- Arquivos alterados: saidas/anuncios.py, tests/test_anuncios.py, docs/ANUNCIOS.md, ESTADO.md, DECISOES.md, HISTORICO.md.
- Como conferir: testes de nomes no começo/meio/fim, maiúsculas, sobreposição e casos sem marcador. Base antes da alteração: 494 testes verdes; após a mudança, 508 testes passaram. Uma execução no sandbox teve WinError 5 transitório ao substituir cache fictício; repetição completa fora do sandbox passou.
- Problemas conhecidos: nenhum novo; sem consulta ao Meta nem alteração de planilha/agendamento nesta sessão.
- Próximo passo: conferir classificação após a próxima rotina; commit e push autorizados pelo Túlio.

## 2026-10-15 · Codex · etapa 9 (anúncios do Meta, D-066)
- Feito: coleta apenas GET com ads_read, atribuição igual aos custos automáticos, histórico mensal desde julho/2025 com retomada e sete dias móveis, anúncios diários/miniatura e agregado 7d, horas 3d, estrutura, comparações semanais e sete alertas. Prefixo anuncios_, lista explícita de campos agregados, sem clientes nem token no cache. Configuração no fim e abas de entrada do Cowork preservadas. Workflow ganhou opção de reconstruir anúncios separada da Nuvemshop; falha de Meta ou gravação de anúncios não derruba a rotina.
- Arquivos alterados: saidas/anuncios.py, rotina.py, workflow, tests/test_anuncios.py, test_rotina.py, docs/ANUNCIOS.md, ESTADO.md, HISTORICO.md, DECISOES.md. Correção prévia de tipo na receita em motor/raspadinha.py para deixar base verde (454 testes), preservando vazios.
- Como conferir: 494 testes Python passaram (40 novos da Etapa 9), sem rede; instruções em docs/ANUNCIOS.md para Run workflow e anuncios_resumo. ESTADO contém contrato final de todas as abas para Cowork.
- Problemas conhecidos: conta real não consultada localmente, conforme especificação (proxy); validar dados no Actions. Orçamentos/status são atuais, semana corrente parcial e retornos de estoque anteriores a 14/10 desconhecidos. Direção do Cowork não é agendada pelo Python.
- Próximo passo: rodar Actions, conferir estado ok e período em anuncios_resumo, entregar bloco Avisar o Cowork. Commit e push autorizados pelo Túlio.

## 2026-10-15 · Antigravity · leitura do projeto e pendência de segurança
- Feito: leitura completa do estado do projeto pelo protocolo. Túlio gerou códigos de recuperação novos no GitHub (antigos invalidados) e guardou fora do projeto; pendência marcada como feita. Apagado `github-recovery-codes.txt` da pasta (estava ignorado pelo `.gitignore` e fora do controle de versão; só tinha os códigos antigos).
- Arquivos alterados: docs/ESTADO.md, docs/HISTORICO.md.
- Como conferir: o arquivo não existe mais na pasta do projeto; ESTADO mostra a pendência de segurança marcada.
- Problemas conhecidos: `python -m pytest` no Windows (Python 3.12): 452 passam, 2 falham em tests/test_raspadinha.py (TypeError de dtype do pandas, já registrado antes). Inconsistências apontadas ao Túlio, ainda não corrigidas: avisos antigos dizendo "Brevo em modo teste" (está em modo real desde 14/10), D-059 x exclusão de etiqueta prata, trechos desatualizados de "O que está funcionando" e pendência de custos (frete e Meta já validados em 12/10).
- Próximo passo: corrigir as 2 falhas da raspadinha antes da primeira campanha e limpar as inconsistências do ESTADO com a confirmação do Túlio.

## 2026-10-14 · Claude (Cowork) · raspadinha online (D-062)
- Feito: raspadinha online pronta em modo teste. Motor `painel_monstro/motor/raspadinha.py` (sorteio com saco de cartelas, controle, trava de benefício, cupom único só letras e números, link embaralhado, uso e resultado). Saída `painel_monstro/saidas/raspadinha.py` (abas `Raspadinha`, `raspadinha_lista`, `raspadinha_envios`, `raspadinha_resultados`; criação de cupons por `POST /coupons` só com Modo = Real e `--criar-cupons`; CSV para o Brevo). Rotina horária calcula uso e resultado (sem campanha, não grava nada). Página pública mobile first em `raspadinha_pagina/` (index.html, cartela-fechada.jpg, modelo de email). AGENTS.md ganhou a seção da raspadinha e a exceção de escrita na Nuvemshop.
- Arquivos alterados: painel_monstro/motor/raspadinha.py, painel_monstro/saidas/raspadinha.py, painel_monstro/rotina.py, tests/test_raspadinha.py, raspadinha_pagina/*, docs/RASPADINHA.md, AGENTS.md, docs/DECISOES.md, docs/ESTADO.md, docs/HISTORICO.md.
- Como conferir: `python -m pytest` (440 testes passam; 25 da raspadinha). `scripts/auditar_repositorio.py` limpo. Abrir `raspadinha_pagina/index.html` sem parâmetro mostra "Essa cartela não abriu".
- Problemas conhecidos: nada foi rodado contra a Planilha Google nem contra a Nuvemshop reais (o ambiente da sessão do Cowork não alcança a API do Google: a rede bloqueou oauth2.googleapis.com). A primeira execução real cria as abas `Raspadinha` e `raspadinha_lista`. Testes rodados em Python 3.10 (Linux) por falta do 3.12 no ambiente; o código não usa nada exclusivo do 3.12. O filtro `default` do Brevo no modelo de email precisa ser conferido na prévia.
- Próximo passo: Túlio publica a página (raspadinha_pagina/README.md), cria os atributos RASPA_LINK e RASPA_ATE no Brevo, preenche a aba `Raspadinha` e roda a primeira campanha em modo teste com um público pequeno.

## 2026-10-14 · Claude · ajuste da atribuição manual (D-065)
- Feito: pedido atribuído já reconhecido por qualquer ciclo da Fila fica só na Fila; nota da linha traz quantos foram ignorados, por origem.
- Arquivos alterados: painel_monstro/saidas/atribuicoes.py, resumos_painel.py, tests/test_atribuicoes.py, docs/ATRIBUICOES.md, docs.
- Como conferir: aba `vale_a_pena`, nota da linha "Indicações e contatos manuais".
- Problemas conhecidos: nenhum novo.
- Próximo passo: nenhum.


## 2026-10-14 · Claude · atribuição manual de pedidos (D-064)
- Feito: módulo saidas/atribuicoes.py, linha "Indicações e contatos manuais" em `vale_a_pena` (colunas novas `pedidos` e `receita_atribuida` no fim), parâmetro "Prefixo de cupom de indicação" na Configuração, linha no email de segunda.
- Arquivos alterados: painel_monstro/saidas/atribuicoes.py, resumos_painel.py, resumo_email.py, regua_planilha.py, tests/test_atribuicoes.py, docs/ATRIBUICOES.md.
- Como conferir: docs/ATRIBUICOES.md, "Como conferir".
- Problemas conhecidos: tests/test_rotina.py falhou uma vez na suíte completa e passou nas execuções seguintes (intermitente, não investigado); 2 falhas antigas da raspadinha.
- Próximo passo: Cowork passar a escrever na aba `atribuicoes`.


## 2026-10-14 · Claude · revisão do fila-por-email.gs
- Feito: email da fila mostra o rótulo humano do modelo; `newsletter_aviso!A2` confirmado como texto (RAW) com teste e o script aceita também Date; removida a segunda declaração de `config` em `enviarFila_`.
- Arquivos alterados: apps-script/fila-por-email.gs, apps-script/teste_local.js, tests/test_newsletter.py, docs/NEWSLETTER.md, docs/ESTADO.md.
- Como conferir: node apps-script/teste_local.js (35 testes) e pytest tests/test_newsletter.py.
- Problemas conhecidos: o Túlio precisa colar o script de novo no Apps Script.
- Próximo passo: colar o script atualizado.


## 2026-10-14 · Claude · newsletter semanal (D-063)
- Feito: colunas `imagem`, `descricao` e `no_estoque_desde` no fim de `produtos`; módulo saidas/newsletter.py; abas `newsletter_semana` e `newsletter_aviso` geradas na quarta às 17h; Apps Script manda o aviso. Primeira rodada depois do deploy baixa todos os produtos de novo (para trazer imagem e descrição).
- Arquivos alterados: painel_monstro/saidas/newsletter.py, coletor/nuvemshop_api.py, coletor/planilhas_csv.py, rotina.py, apps-script/fila-por-email.gs e teste_local.js, tests/test_newsletter.py, docs/NEWSLETTER.md.
- Como conferir: docs/NEWSLETTER.md, seção "Como conferir".
- Problemas conhecidos: 2 testes de tests/test_raspadinha.py já falhavam antes (TypeError de dtype do pandas), fora desta etapa. O Túlio precisa colar o script atualizado no Apps Script para o aviso sair.
- Próximo passo: Cowork usar `newsletter_semana` e preencher `newsletter_historico`.


## 2026-10-14 · Claude · coluna estorno na aba pedidos (D-061)
- Feito: coluna `estorno` acrescentada no fim de `pedidos`. API não informa o valor estornado, então fica vazia no caminho da API; a exportação CSV preenche pela coluna "Estorno" (exportações antigas sem ela ficam vazias). Colunas existentes intactas.
- Arquivos alterados: painel_monstro/coletor/nuvemshop_api.py, painel_monstro/coletor/planilhas_csv.py, tests/test_planilhas_csv.py, docs.
- Como conferir: aba `pedidos`, última coluna `estorno`; com CSV, o pedido 2963 mostra 36,43. 415 testes passam.
- Problemas conhecidos: na rotina da API o painel não tem estorno real; se precisar, importar o CSV.
- Próximo passo: Cowork ler a coluna quando houver valor.


## 2026-10-14 · Claude · taxa real do Nuvem Pago (D-060)
- Feito: a pedido do Cowork, verificado se a API oficial entrega a taxa real por pedido. Não entrega: pedido sem campo de taxa, transações vazias, pagamentos 404. Nada alterado no código; `taxas` e `total_liquido` continuam vazias na API e preenchidas só pela exportação CSV. Aviso da aba `comissao` e das linhas "Comissão: ..." registrado: não mexer.
- Arquivos alterados: docs/ESTADO.md, docs/HISTORICO.md, docs/DECISOES.md.
- Como conferir: ler D-060 em docs/DECISOES.md.
- Problemas conhecidos: o painel precisa continuar usando a taxa estimada (Configuração) quando não houver valor real.
- Próximo passo: se o Túlio quiser a taxa real, exportar os pedidos em CSV da Nuvemshop e colocar em dados/entrada/.


## 2026-10-13 · Codex · etapa 5.1 (confirmação D-058)
- Feito: D-058 confirmada pelo Túlio: todos os cupons valem para usados e lacrados em toda a loja online, tanto no carrinho quanto na régua de email. Mesmo VOLTA10<MÊS>, sem cupom separado para carrinho. VOLTA10OUT conferido em leitura: válido, 10%, sem restrição de categorias/produtos e max_discount_amount ausente (sem teto em reais, conforme correção explícita do Túlio). R$30 é somente o teto da cotação para oferecer frete no carrinho; mínimo R$200 mantido. Consignados só existem na loja física; exclusão de etiqueta prata mantida como proteção caso apareçam na fonte. Oferta da Etapa 3 e ajuda de Cupom de desconto na Configuração já atualizadas pelo Túlio.
- Arquivos alterados: motor de carrinhos, testes, AGENTS.md, DECISOES, ESTADO e guias Cowork/frete.
- Como conferir: testes Python e auditoria antes da publicação autorizada; consulta do cupom somente GET.
- Problemas conhecidos: nenhum cupom ou registro manual da Fila alterado; Brevo segue em modo teste.
- Próximo passo: Cowork usar confirmação D-058 no CRM e guia.

## 2026-10-13 · Codex · etapa 5.1 (ofertas para toda a loja, D-059)
- Feito: autorização para ampliar VOLTA10OUT e publicar regra geral; Túlio ajustou o cupom. Consulta GET confirmou ambos os cupons válidos e sem restrição de produtos/categorias. Removida exclusão de consignados, texto T3 e Oferta da Régua reais alinhados. Fila recalculada sem alterar campos manuais, quatro pendentes: um frete, dois descontos e um primeiro contato sem oferta.
- Arquivos alterados: AGENTS.md, saidas/carrinhos.py, regua_planilha.py, tests/test_carrinhos.py e docs de estado, decisão, Brevo, frete e passagem Cowork.
- Como conferir: 413 testes Python passaram; ler Fila na visualização Para enviar e seus textos atuais. Backup privado anterior em dados/backup-fila; auditoria limpa (59 commits); publicado no GitHub em 8552941.
- Problemas conhecidos: email já recebido contém links antigos; usar Fila atual. Cotação não garante custo final da etiqueta ou mudança posterior de endereço. Nenhum envio de email/WhatsApp nem escrita no Brevo.
- Próximo passo: Cowork atualizar CRM e guia com docs/PASSAGEM_COWORK_CRM.md. Publicação autorizada nesta conversa.

## 2026-10-13 · Codex · etapa 5.1 (oferta geral de carrinho)
- Feito: Túlio corrigiu a abrangência, geral para usados e lacrados no carrinho. D-058 substitui D-057 nesse ponto. Motor e texto padrão T3 corrigidos; consignados continuam excluídos de benefícios. Passagem Cowork atualizada. Consulta GET de cupom confirmou VOLTA10OUT válido, 10%, mas categorias ainda usadas; não foi alterado na loja.
- Arquivos alterados: saidas/carrinhos.py, tests/test_carrinhos.py, AGENTS.md e docs.
- Como conferir: 413 testes Python, lacrado com categorias conflitantes recebe modelo de desconto; consignado não recebe cupom/desconto de frete. Sem mudança no Brevo ou no consentimento.
- Problemas conhecidos: código ainda local; publicação e escolha entre cupom próprio de carrinho e ampliação do atual aguardam resposta do Túlio. Cupom compartilhado com emails não deve ser ampliado implicitamente. Não houve envio nem mudança de cupom.
- Próximo passo: decidir cupom, configurar abrangência, atualizar modelo da planilha e publicar após confirmação.

## 2026-10-13 · Codex · etapa 5.1 (fila das 17h e passagem ao CRM)
- Feito: leitura do email das 17h (oito contatos) e comparação com Fila; quatro pendentes, três enviados/em conversa e um encerrado. Recalculo real preservou campos manuais. Identificado produto com categorias usadas/novas conflitantes, que recebia oferta de usados; proteção por nome/categorias conservadora. Novo T2_LEMBRETE neutro no fim de Mensagens, sem alegar exemplar único para lacrado. Passagem detalhada para Cowork com contratos de leitura/escrita, visualizações e sequência de ofertas.
- Arquivos alterados: saidas/carrinhos.py, carrinhos_planilha.py, tests/test_carrinhos.py, docs/PASSAGEM_COWORK_CRM.md, docs/ESTADO.md, docs/HISTORICO.md e docs/DECISOES.md.
- Como conferir: 412 testes Python, incluindo lacrado, consignado, modelo manual e categorias conflitantes; nenhum evento fictício contado. Mensagens da Fila substituem links antigos do email. Não houve envio de email/WhatsApp nesta sessão.
- Problemas conhecidos: escrita de checkbox por API do CRM não dispara onEdit. Cowork deve integrar registro no backend ou abrir a Fila para edição humana. Publicação da correção de lacrado aguarda confirmação do Túlio; email entregue não pode ser alterado retroativamente.
- Próximo passo: publicar após confirmação e entregar arquivo ao Cowork. Não registrar nomes/telefones de clientes no repositório.

## 2026-10-13 · Codex · etapa 5.1 (cotação e desconto antecipado)
- Feito: GET de cotação experimental testado ao vivo, entrega ship BRL mais barata sem retirada; função retorna R$36,75, sem tokens ou dados pessoais em log. Fonte passa a ser preço cotado ao cliente conforme esclarecimento do Túlio. Frete até R$30 no segundo envio a partir de R$200; alternativa 10% com mesmo mínimo e restrições atuais. Oferta final já enviada encerra sem repetir; modelos enviados consideram marcação recente antes da contabilização, sem somar toque fictício. Chave antiga de garantia vira legado sem bloquear mensagem. D-056.
- Arquivos alterados: saidas/carrinhos.py, carrinhos_planilha.py, tests/test_carrinhos.py, test_carrinhos_planilha.py, AGENTS.md e docs.
- Como conferir: 410 testes Python, casos de cotação/retirada/moeda/falha/manual, primeiro toque sem cotar e fechamento com dois envios reais. Publicação autorizada explicitamente pelo Túlio. Sem mudança no Apps Script.
- Problemas conhecidos: endpoint experimental depende de read_shipping_quotation e destino no carrinho; falha não libera frete. Preço ao cliente é cotação, não custo final da etiqueta. Cupom precisa estar configurado para entrega econômica e condições da loja; esta mudança não altera cupons nem protege contra alteração posterior de endereço/itens.
- Validação final: recálculo da Fila real preservou todos os campos manuais; quatro Contatar, sendo um T2_FRETE, dois T3_CUPOM e um sem benefício. Publicado no GitHub (e4aeeb9).
- Próximo passo: conferir mensagem da Fila e próxima rodada; WhatsApp continua manual.

## 2026-10-13 · Codex · etapa 5.1 (teto de frete no carrinho)
- Feito: D-055, R$200 em produtos após desconto, custo da loja até R$30 e proteção do checkout obrigatória para oferecer T2_FRETE. Custo só do campo documentado shipping_cost_owner, consulta individual em leitura se necessário. Falhas, valores inválidos, retirada e escolha manual não contornam. Dois parâmetros novos no fim da Configuração; mínimo atualizado na planilha real, garantia do checkout Não. T3 preservado.
- Arquivos alterados: saidas/carrinhos.py, carrinhos_planilha.py, tests/test_carrinhos.py, test_carrinhos_planilha.py, test_rotina.py, AGENTS.md e docs.
- Como conferir: 406 testes Python e 31 Apps Script. Testes novos cobrem R$199,99/R$200, R$30/R$30,01, custo ausente/zero/infinito, moeda, retirada, falha de rede, modelo manual e terceiro toque. Consulta real de 54 carrinhos e três consultas individuais sem custo; nenhum dado pessoal nos registros versionados. Publicação autorizada pelo Túlio.
- Problemas conhecidos: cupom nativo de frete grátis não tem teto em reais; oferta fica suspensa até solução de checkout validada. A trava não muda cupons que já foram enviados nem promoções da loja. Na abertura havia teste de idempotência falhando porque comparava duração variável da rodada; excluída aba rodada da comparação de tabelas, preservando verificações de dados/incremental, base ficou verde antes de alterar motor.
- Próximo passo: decisão do dono/Túlio sobre mecanismo que garanta teto no checkout. Não substituir por crédito parcial sem autorização.

## 2026-10-13 · Claude Code · email da fila (por que não veio às 10h)
- Feito: conferido na caixa do Túlio (Gmail) que os emails da fila saíram em 10/10 17:26, 12/10 10:31 e 12/10 17:31 e que hoje não havia nada em Contatar às 10h (por isso o script não mandou). O script passou a ler os horários da linha "Horários da fila" da Configuração; D-054.
- Arquivos alterados: `apps-script/fila-por-email.gs`, `apps-script/teste_local.js`, `docs/DECISOES.md`, `docs/HISTORICO.md`.
- Como conferir: `node apps-script/teste_local.js` (31 testes). O Túlio precisa colar o script de novo e escrever "10h, 13h e 17h" na linha "Horários da fila".
- Problemas conhecidos: o script novo só vale depois de colado no Apps Script.

## 2026-10-13 · Claude Code · etapa 7.1 (caminho de escrita do Brevo e decisão do Respondeu agora)
- Feito: conferida a documentação oficial do Brevo antes de liberar a escrita; a importação em lote exige lista e é assíncrona, então a aplicação passou a atualizar contato por contato (PUT, 10 por segundo, 7 minutos por rodada, falha isolada, pendências na rodada seguinte) e a listar depois (adicionar à lista em chamada separada). Trocar o modo refaz o plano na hora. Decisão do Túlio: "Respondeu agora" não registra toque inferido e a trava de 30 dias vale para Status Respondeu com 0 toques (aba `respostas_vistas`). D-052 e D-053.
- Arquivos alterados: `painel_monstro/saidas/{brevo,carrinhos_planilha}.py`, `painel_monstro/rotina.py`, `tests/test_brevo.py`, `tests/test_brevo_pausa.py`, `tests/test_fluxo_sem_travas.py`, `AGENTS.md`, `docs/BREVO.md`, docs.
- Como conferir: `pytest` (403 passed); `brevo_plano` mostra `modo`, `aplicado no Brevo` e `pendentes de aplicar`.
- Problemas conhecidos: o modo real nunca rodou contra o Brevo de verdade; o primeiro dia aplica cerca de 2.000 atualizações em várias rodadas. Virar a chave (variável `BREVO_MODO_TESTE` = nao) depende do Túlio no GitHub, com a automação da Etapa 0 ativada antes.

## 2026-10-13 · Claude Code · etapa 7.1 (chave de pausa e cupom por contato)
- Feito: política da régua no Brevo (`Régua no Brevo`, pausa programada, `Etapa N no Brevo`), cupom por contato (`CUPOM`, `CUPOM_ATE`) só na entrada das etapas 2 e 3, atributos gravados na hora (PUT, um por contato) antes da inclusão na lista (chamada separada), plano refeito quando a configuração muda, linhas novas no fim do `brevo_plano`, `docs/BREVO.md`. `github-recovery-codes.txt` saiu do controle de versão; `.gitignore` e verificador barram esse tipo de arquivo. D-052.
- Arquivos alterados: `painel_monstro/saidas/{brevo,regua_planilha}.py`, `painel_monstro/rotina.py`, `tests/test_brevo.py`, `tests/test_brevo_pausa.py`, `.gitignore`, `scripts/auditar_repositorio.py`, docs.
- Como conferir: `pytest` (396); aba `brevo_plano` (linhas `Régua no Brevo` e `Etapas ligadas`, `entram em "Painel · Etapa 0 Pós-compra"`).
- Problemas conhecidos: modo teste segue ligado, nada foi escrito no Brevo. O item "Respondeu agora registra toque inferido" não foi feito porque contraria D-049 e D-051; aguarda decisão. Nenhuma alteração na Fila nem no Apps Script nesta sessão.

## 2026-10-13 · Codex · etapa 5.1 (operação diária e acompanhamento)
- Feito: visualizações pessoais dinâmicas Para enviar, Acompanhar respostas e Histórico e busca; menu Fila Monstro e ações de resposta/recusa/inválido salvos diretamente no Apps Script vinculado. Colunas novas no fim, backup privado e leitura comprovando histórico intacto. Python mantém Respondeu em Em conversa e pausa toques do ciclo; compra recuperada tem prioridade.
- Arquivos alterados: apps-script/fila-por-email.gs, apps-script/teste_local.js, saidas/carrinhos.py, carrinhos_planilha.py, fila_unica.py, tests/test_carrinhos_planilha.py, AGENTS.md e docs. D-051.
- Como conferir: 365 testes Python e 29 Apps Script; menu conferido na planilha real. Visualizações têm IDs 101001/101002/101003 e abrangem novas linhas a cada rotina. Recuperação permanece automática, sem caixa manual.
- Validação ao vivo: recálculo com Nuvemshop em leitura preservou todos os campos manuais; zero Contatar e dois Em conversa. Código publicado após autorização. Cabeçalhos com quebra de linha.
- Problemas conhecidos: Google pediu nova autorização, concluída pelo Túlio; menu e link pessoal de acompanhamento validados no navegador (17 linhas visíveis). Visualização abre por link no diálogo em outra guia; nomes podem repetir, conferir telefone e origem. Não há retomada agendada, atribuição de responsável nem desfazer automático. Equipe combina divisão dos contatos quando trabalha simultaneamente. Não foram marcados eventos fictícios em contatos reais.
- Próximo passo: operar pela Fila Monstro e conferir próxima rodada horária; publicação explicitamente autorizada pelo Túlio.

## 2026-10-13 · Codex · etapa 5.1 (visualização diária por situação)
- Feito: substituído filtro temporário por nomes de Cliente, usado na conferência de 12/10, por Situação = Contatar. Contadores, datas e status preservados.
- Arquivos alterados: docs/ESTADO.md e docs/HISTORICO.md; filtro da planilha.
- Como conferir: filtro está em Situação, sem lista fixa de clientes; leitura de retorno confirmou zero pendentes naquele momento. Registros anteriores aparecem ao remover filtro.
- Problemas conhecidos: filtro é visualização de pendentes; para registrar respostas, localizar histórico removendo filtro. Não houve alteração de código nem execução de testes nesta conferência visual.
- Próximo passo: trabalhar sobre Contatar após atualização horária e marcar Enviei agora uma vez após cada envio real.

## 2026-10-12 · Codex · etapa 5.1 (reparo de colunas e separação da fila)
- Feito: identificado Enviei agora movido para N, com escrita Python deslocando campos calculados. Backup privado antes do reparo; coluna voltou ao fim, campos restaurados/recalculados com API atual, mensagens editadas recuperadas do backup quando substituídas por números. Contador/data/status dos 15 envios preservados; apenas caixas zeradas. Criadas visualizações de filtro enviados/pendentes/inválidos e filtro atual Contatar. Campos de operação visíveis e A:D congeladas.
- Arquivos alterados: painel_monstro/saidas/carrinhos_planilha.py, tests/test_carrinhos_planilha.py, AGENTS.md, docs/COMO_MARCAR_ENVIOS.md, docs/ESTADO.md, docs/HISTORICO.md e docs/DECISOES.md. D-050.
- Como conferir: 363 testes Python e 26 Apps Script; dois testes novos garantem falha antes de gravar em cabeçalhos movidos e inserção de contatos sem pular por caixas vazias. Recalculo real: 15 enviados hoje, 2 elegíveis, 2 sem telefone utilizável. Nenhum email nem WhatsApp foi enviado nesta sessão.
- Problemas conhecidos: checkbox volta a ficar vazia após registro, por desenho. Não testar em envio já contado. Ordens das colunas devem ser mantidas; somente ocultar para aproximar campos. Visualizações datadas correspondem a 12/10.
- Próximo passo: prática com contato elegível ainda não enviado e conferência imediata do contador/data; manter histórico real.

## 2026-10-12 · Codex · etapa 5.1 (colunas de operação próximas)
- Feito: a pedido do Túlio, ocultadas N:AJ na Fila real para aproximar Status M e Enviei agora AK. Nomes/ordem das colunas e marcações preservados; mudança apenas visual e reversível.
- Arquivos alterados: docs/COMO_MARCAR_ENVIOS.md, docs/ESTADO.md e docs/HISTORICO.md.
- Como conferir: Status e checkbox lado a lado; reexibir pelas setas entre M/AK para acessar mensagens e links ocultos.
- Problemas conhecidos: checkbox depende da versão mais recente do Apps Script vinculada à planilha; não foi confirmada a atualização pelo usuário nesta sessão.
- Próximo passo: confirmar atualização do script e usar checkbox só após envio real; resposta é Status Respondeu.

## 2026-10-12 · Codex · etapa 5.1 (registro com uma marcação e correção do dia)
- Feito: Enviei agora acrescentado no fim da Fila, checkbox com onEdit que registra contador/data/status, trava e tratamento de evento repetido; situação provisória Envio registrado. Proteção por aviso de Próximo toque na planilha. Túlio confirmou os enviados por Status Em andamento: 15 linhas corrigidas para um toque, com horário da correção 12:11 Brasília, sem reenviar. Registros sem confirmação e contato inválido preservados; backup privado em dados/backup-fila.
- Arquivos alterados: apps-script/fila-por-email.gs, apps-script/teste_local.js, painel_monstro/saidas/carrinhos_planilha.py, tests/test_carrinhos_planilha.py, AGENTS.md e docs, guia novo COMO_MARCAR_ENVIOS.md. D-049.
- Como conferir: testes Python e Apps Script; leitura após gravação confirmou 15 contadores/datas; checkbox na coluna AK. Testes verificam que Python preserva a caixa e que Apps Script não duplica evento nem conta status isolado/recusa/inválido.
- Problemas conhecidos: script novo ainda precisa ser colado e salvo no editor da planilha. Horário da correção não é o horário original de envio. Um erro transitório de permissão do Windows ocorreu numa rodada de teste; reexecução completa verde em pasta temporária nova.
- Próximo passo: Túlio cola e salva versão atual do Apps Script; conferir a caixa num próximo envio real, sem registrar envio fictício.

## 2026-10-12 · Codex · etapa 5.1 (conferência das marcações do dia)
- Feito: comparação somente de leitura entre o email da fila de hoje e a planilha. Todos os 16 contatos do email estão na Fila; 14 com Status Em andamento, 1 Contato inválido e 1 Status vazio. Todos os 16 estão sem Toques já enviados e sem Último envio em.
- Arquivos alterados: docs/HISTORICO.md.
- Como conferir: comparar a lista enviada hoje com as colunas manuais; Próximo toque igual a 1 não comprova envio. Marcar só Status não dispara a gravação da data; é necessário aumentar o contador após envio real.
- Problemas conhecidos: não é possível confirmar envio real pelo WhatsApp a partir dessas marcações. Nenhuma célula foi alterada na conferência, nem nomes/dados de clientes registrados no repositório.
- Próximo passo: equipe confere os envios no WhatsApp e completa o contador somente para mensagens efetivamente enviadas; contato inválido permanece sem toque.

## 2026-10-12 · Codex · etapa 5.1 (contato inválido)
- Feito: Status Contato inválido, encerramento e exclusão do telefone de tentativas de todas as origens, sem toque ou recusa nem bloqueio de email. Contagem separada no fim de Resultados. Menu adicionado e fórmula de edição atualizada na fila real; campos manuais intactos. D-048.
- Arquivos alterados: saidas/carrinhos_planilha.py, saidas/carrinhos.py, saidas/fila_unica.py, tests/test_carrinhos_planilha.py, AGENTS.md e docs.
- Como conferir: 361 testes verdes; novo teste confirma zero toques/recusas e ausência de inclusão em Bloqueio. Na planilha, Status contém Contato inválido e o link editado some ao escolher essa opção.
- Problemas conhecidos: encerramento da situação e contagem são feitos na próxima rotina; Apps Script não precisa mudar por este ajuste.
- Próximo passo: Mariana marca Contato inválido sem contar toque; corrigir o telefone e revisar o status para retomar quando necessário.

## 2026-10-12 · Codex · etapa 5.1 (horário automático ao marcar toque)
- Feito: onEdit simples na Fila grava Último envio em ao aumentar Toques já enviados numa célula manual, em Brasília; redução, exclusão, mesmo número, inválidos, outras abas/colunas e colagens múltiplas preservam a data. Mensagem dos emails da equipe atualizada. D-047.
- Arquivos alterados: apps-script/fila-por-email.gs, apps-script/teste_local.js, AGENTS.md, docs/ESTADO.md, docs/HISTORICO.md e docs/DECISOES.md.
- Como conferir: 360 testes Python na abertura; 22 testes locais do Apps Script, incluindo 4 novos grupos para registro de horário. Após colar e salvar o script vinculado, uma marcação real de envio preenche a data automaticamente.
- Problemas conhecidos: código não foi colado no editor Google nesta sessão; atualização pelo Túlio ainda necessária. Horário é o da marcação; colagens múltiplas não têm valor anterior confiável no evento e exigem registro manual.
- Próximo passo: Túlio substitui conteúdo do script no editor da planilha e salva; não precisa rodar instalar nem onEdit manualmente.

## 2026-10-12 · Codex · etapa 5.1 (fórmulas da edição na fila)
- Feito: fórmula Abrir com minha edição usa ponto e vírgula; rotina corrige linhas existentes e novas. Corrigidas 32 fórmulas na planilha real: zero erros na coluna, campos manuais intactos.
- Arquivos alterados: painel_monstro/saidas/carrinhos_planilha.py, tests/test_carrinhos_planilha.py, docs/ESTADO.md e docs/HISTORICO.md.
- Como conferir: 360 testes verdes; preencher Mensagem editada faz aparecer o link; abrir não envia sozinho nem marca toque. Após envio manual, somar 1 em Toques já enviados e registrar Último envio em com data/hora.
- Problemas conhecidos: nenhum erro de fórmula restante nessa coluna; separador foi ajustado para a localidade da planilha atual.
- Próximo passo: Mariana registra cada envio; guia do Cowork deve explicar as colunas. Apps Script não precisa mudar por esta correção.

## 2026-10-12 · Codex · etapa 6 (token Meta definitivo validado)
- Feito: Túlio criou usuário do sistema painel_monstro, atribuiu app e leitura de desempenho da conta e substituiu o token no .env e Secrets. GET /debug_token confirmou SYSTEM_USER válido com ads_read e expiração/access expiry zero. Insights de setembro retornaram os mesmos valores validados anteriormente.
- Arquivos alterados: docs/ESTADO.md, docs/HISTORICO.md e docs/CUSTOS_AUTOMATICOS.md.
- Como conferir: custos_automaticos já tem fontes ok; conferir próxima execução do Actions. Nenhuma chave foi registrada ou impressa.
- Problemas conhecidos: execução real do GitHub com o token novo ainda não conferida; sem vencimento programado não impede revogação ou retirada de permissão.
- Próximo passo: conferir Actions e atualizar apresentação/guia no Cowork conforme D-046.

## 2026-10-12 · Codex · etapa 6 (Meta validado, token temporário)
- Feito: credenciais salvas pelo Túlio em .env e Secrets; consulta real de Insights de setembro funcionou com ads_read. Atualizada custos_automaticos: todas as fontes ok; aba manual intacta.
- Arquivos alterados: docs/ESTADO.md e docs/HISTORICO.md.
- Como conferir: valores do Meta na aba automática e ads_read concedido em GET /me/permissions. GET /debug_token confirmou token válido do tipo USER, vencendo às 13h de 12/10/2026 no fuso America/Sao_Paulo; nenhuma chave impressa.
- Problemas conhecidos: token de teste vence hoje; execução futura depende de substituí-lo.
- Próximo passo: token de usuário do sistema com ads_read, acesso à conta de anúncios e prazo confirmado; atualizar .env e Secrets.

## 2026-10-12 · Codex · etapa 6 (frete automático validado)
- Feito: permissão Nuvemshop agora efetiva, GET de entregas HTTP 200 com o mesmo token. Corrigida leitura do Response para JSON e ajustado o teste fictício ao contrato real do cliente. Frete de setembro: 5 entregas gratuitas, R$188,96; 3 retiradas excluídas. Aba automática atualizada, custos manuais intactos.
- Arquivos alterados: painel_monstro/saidas/custos_automaticos.py, tests/test_custos_automaticos.py e docs.
- Como conferir: 360 testes verdes e linha Nuvemshop/frete_pago_loja de 2026-09 com estado ok na planilha.
- Problemas conhecidos: acesso Meta ainda não localizado na configuração local.
- Próximo passo: localizar/configurar Meta e conferir próxima rotina do GitHub.

## 2026-10-12 · Codex · etapa 6 (rechecagem dos acessos)
- Feito: após Túlio informar permissão de frete liberada e Meta já configurado, testado GET de fulfillment: chave local ainda responde 403 por falta de read_fulfillment_orders. Configuração local não contém META_ADS_ACCOUNT_ID nem META_ADS_TOKEN.
- Arquivos alterados: docs/ESTADO.md e docs/HISTORICO.md.
- Como conferir: teste de leitura exibiu apenas presença das configurações e código de permissão, sem segredos ou contatos.
- Problemas conhecidos: mudança de permissão ainda não efetiva no token local; localização das credenciais Meta não informada.
- Próximo passo: reautorizar aplicativo Nuvemshop/atualizar token se necessário e localizar configuração Meta. Não colar chaves na conversa.

## 2026-10-12 · Codex · etapa 6 (implementação dos custos automáticos)
- Publicação: commit `cb5cffe` enviado para origin/main; auditoria limpa nos 66 arquivos atuais. A próxima execução real do Actions ainda não foi conferida.
- Feito: receita mensal do Brevo, coletor de frete gratuito por fulfillment e coletor Insights do Meta; cache diário do mês anterior, aba própria, valores manuais preservados e com prioridade, falhas pendentes sem zero inventado. Receita Brevo independe do Meta; indicadores de frete ficam pendentes quando consulta falha e não há valor manual. D-046.
- Arquivos alterados: painel_monstro/saidas/{custos_automaticos,brevo}.py, painel_monstro/{rotina,config}.py, motor/indicadores.py, workflow, env-exemplo, testes, AGENTS.md e docs.
- Como conferir: 360 testes verdes; aba real custos_automaticos criada com 5 linhas de setembro (Brevo ok, Meta/frete pendentes), aba manual lida antes/depois idêntica. Campanha de outubro bateu com a captura. Nenhuma escrita no Brevo ou na Nuvemshop.
- Problemas conhecidos: Nuvemshop devolve 403 Missing required scope: read_fulfillment_orders; Meta sem token/conta. Essas duas fontes só puderam ser validadas com testes fictícios.
- Próximo passo: conferir execução agendada após envio ao GitHub; Túlio libera acessos conforme docs/CUSTOS_AUTOMATICOS.md.

## 2026-10-12 · Codex · etapa 6 (viabilidade de custos automáticos)
- Feito: verificada cada coluna de custos. Encontrado endpoint oficial GET `/ecommerce/attribution/metrics`; consulta da campanha da captura retornou a mesma receita e contagem de pedidos. GET `/account` não trouxe cobrança; nenhuma configuração Meta presente. Consulta mensal de setembro sem filtro retornou vazio, e moeda retornou vazia: não automatizar zeros sem validar cobertura.
- Arquivos alterados: `docs/CUSTOS_AUTOMATICOS.md`, `docs/ESTADO.md`, `docs/HISTORICO.md`.
- Como conferir: fontes oficiais e resultado agregado descritos no guia; consultas somente de leitura, sem contatos ou segredos impressos.
- Problemas conhecidos: integração ainda não implementada. Meta depende de acesso de leitura; mensalidade, margens, embalagem e frete efetivamente pago continuam manuais.
- Próximo passo: configurar acesso ao Meta e validar semântica mensal, moeda e cobertura do Brevo; preservar a aba custos manual.

## 2026-10-12 · Codex · etapa 6 (investigação de custos automáticos)
- Feito: consultada a documentação oficial e, somente por GET, os relatórios de três campanhas enviadas na conta do Brevo. Os relatórios retornaram entrega, abertura e cliques, sem campo de receita. Nenhum contato ou configuração foi alterado.
- Arquivos alterados: `docs/ESTADO.md`, `docs/HISTORICO.md`.
- Como conferir: endpoints oficiais GET `/emailCampaigns` e GET `/emailCampaigns/{campaignId}`; consulta exibiu somente nomes de campos, sem valores pessoais ou segredos.
- Problemas conhecidos: receita visível na interface não foi localizada nesses endpoints; automação não implementada. Integração de anúncios do Meta ainda não configurada.
- Próximo passo: identificar fonte oficial para a receita do Brevo e configurar acesso de leitura à conta de anúncios do Meta. Até lá, custos permanecem manuais.

## 2026-10-12 · Codex · etapa 6 (envio da correção ao GitHub)
- Feito: enviado o commit `1d19a55` para `origin/main` com autorização do Túlio; o GitHub confirmou o recebimento.
- Arquivos alterados: `docs/ESTADO.md`, `docs/HISTORICO.md`.
- Como conferir: Actions > Rotina do Painel, na próxima execução agendada ou por Run workflow.
- Problemas conhecidos: resultado da execução real ainda não conferido; GitHub CLI indisponível neste ambiente.
- Próximo passo: conferir que a rotina termina sem o erro de concatenação.

## 2026-10-12 · Codex · etapa 6 (correção da rotina no Actions)
- Feito: reproduzido `ValueError: No objects to concatenate` com histórico fictício contendo somente `teste45`; o resumo agora retorna uma tabela vazia com os mesmos cabeçalhos quando o filtro não deixa meses. Histórico misto mantém os resultados mensais e não altera a entrada.
- Arquivos alterados: `painel_monstro/saidas/resumos_painel.py`, `tests/test_resumos_painel.py`, `docs/ESTADO.md`, `docs/HISTORICO.md`.
- Como conferir: `.venv/Scripts/python.exe -m pytest -q --basetemp=dados/testes-validacao-actions` (348 passed). O teste novo falhou com o mesmo erro antes da correção.
- Problemas conhecidos: testes precisaram de pasta temporária em `dados/` por restrição do ambiente local. A rotina real não foi executada nem a correção publicada nesta sessão.
- Próximo passo: autorização do Túlio para enviar ao GitHub; conferir a próxima execução do Actions.

## 2026-10-11 · Claude Code · etapa 8 (garimpo e públicos do Meta)
- Feito: `garimpo.py` (junta a aba `desejos` e a aba do Google Forms; separa nome e WhatsApp; um pedido gera um aviso só), `meta.py` (públicos `sumiu_180`, `nao_abre` por segmento do Brevo e `compradores_180`, CSV opcional fora do git), passo mensal da rotina, `Brevo.contatos_do_segmento`, `Configuração` com o ID do segmento, `docs/GARIMPO_E_META.md`. D-045.
- Arquivos alterados: `painel_monstro/saidas/{garimpo,meta,fila_unica,carrinhos_planilha,regua_planilha,brevo}.py`, `painel_monstro/rotina.py`, `tests/test_garimpo_e_meta.py`, `tests/test_rotina.py`, docs, `AGENTS.md`.
- Como conferir: `pytest` (346 passed); abas `meta_*` e `meta_resumo`; teste do garimpo pela aba `desejos` (passo a passo no guia).
- Problemas conhecidos: o formulário e o segmento do Brevo ainda não existem (são passos do Túlio). `meta_nao_abre` fica vazia até o ID do segmento ser preenchido.

## 2026-10-10 · Claude Code · etapa 7 (fechamento e dois reforços)
- Feito: primeira rodada real com o passo do Brevo (modo teste, 55 s). O Google limitou o uso na gravação de várias abas (erro de cota); a rotina manteve o conteúdo antigo, como projetado, e foi reforçada: o cliente do Google agora espera e repete cada requisição quando recebe limite de uso (`BackOffHTTPClient`), as gravações de aba tentam de novo até 4 vezes, a mensagem de erro mostra o motivo e o plano do Brevo é refeito enquanto a aba `brevo_mudancas` estiver vazia. Resultado do plano de 10/10/2026: 2.149 clientes na régua, 187 descadastrados (intocados), 1.962 atributos a atualizar, 328 entrariam em lista (58, 95, 61 e 114 nas etapas 0 a 3), 35 no controle; faltam no Brevo os 5 atributos e as 4 listas.
- Arquivos alterados: `painel_monstro/rotina.py`, `painel_monstro/saidas/planilha_google.py`, `tests/test_brevo.py`, `tests/test_fluxo_sem_travas.py`, `tests/test_planilha_google.py`, `tests/test_rotina.py`, `docs/ESTADO.md`.
- Como conferir: abas `brevo_plano`, `brevo_mudancas` e `rodada` (`brevo_status` = "ok (modo teste)"); `pytest` (326 passed).
- Problemas conhecidos: nada foi escrito no Brevo. A conta tem um atributo `FIRSTNAME` (não `NOME`).

## 2026-10-10 · Claude Code · etapa 7 (régua no Brevo, modo teste)
- Feito: `brevo.py` (cliente com barreira de modo teste, alvo por cliente, plano contra o Brevo, aplicação em lotes para o dia em que o Túlio liberar), passo 6 da rotina (leitura da conta a cada rodada, plano uma vez por dia depois das 6h, abas `brevo_plano` e `brevo_mudancas`, status na aba `rodada`), alerta de erro do Brevo no Apps Script, workflow lendo `BREVO_API_KEY` dos segredos e `BREVO_MODO_TESTE` da variável (padrão "sim"), `docs/BREVO.md`. D-044.
- Arquivos alterados: `painel_monstro/saidas/{brevo,regua_planilha}.py`, `painel_monstro/rotina.py`, `.github/workflows/rotina.yml`, `apps-script/fila-por-email.gs` e `teste_local.js`, `tests/test_brevo.py`, `tests/test_rotina.py`, docs, `AGENTS.md`.
- Como conferir: `pytest` (324 passed); `node apps-script/teste_local.js` (18); aba `brevo_plano` da planilha.
- Problemas conhecidos: nenhum atributo nem lista da régua existe no Brevo ainda (o plano diz o que falta). Nada foi escrito no Brevo.

## 2026-10-10 · Claude Code · etapa 6 curta (painel no claude.ai, custos, resumo de segunda)
- Feito: D-043 (Looker saiu; painel no claude.ai lê as abas listadas); AGENTS.md protege nome e ordem das colunas dessas abas; `docs/LOOKER.md` apagado; `custos` aceita mês como texto, data ou célula de data e margem como 40, 40% ou 0,4; aba `resumo_email` montada a cada rodada (`painel_monstro/saidas/resumo_email.py`) e enviada toda segunda às 8h pelo Apps Script para "Emails do resumo" (uma vez só, "(atrasado)" depois das 8h). Email de teste enviado ao Túlio.
- Arquivos alterados: `painel_monstro/motor/indicadores.py`, `painel_monstro/saidas/{resumo_email,resumos_painel,regua_planilha}.py`, `painel_monstro/rotina.py`, `apps-script/fila-por-email.gs` e `teste_local.js`, `tests/test_custos_e_resumo_email.py`, docs, `AGENTS.md`, `PROMPTS.md`.
- Como conferir: `pytest` (303 passed); `node apps-script/teste_local.js` (16 testes); email de teste na caixa do Túlio.
- Problemas conhecidos: o Apps Script novo precisa ser colado de novo na planilha para valer o resumo de segunda.

## 2026-10-10 · Claude Code · etapa 5.2 (ajustes finais e "nada trava o fluxo")
- Feito: nome do disco "Álbum (Artista)" e textos aprovados de G45, VIP (três sugestões em `{sugestoes}`) e ALERTA_GARIMPO; "Dias da fila" na `Configuração` (prazo congela fora deles); teste de 45 dias começa em 12/10 e fica 30 dias na fila (editável); aba `contatos_manuais` (mecanismo para contatos à mão; os 9 VIPs registrados por engano foram apagados, D-040); estados "Encerrado sem contato", aviso de linha não marcada, abas `resumo_semana` e `rodada`; rotina calcula tudo antes de gravar; Apps Script com envio por horário sem duplicata, "(atrasada)", resumo de segunda e alerta de rotina parada. D-039 a D-042, D-016/021/022 atualizadas.
- Arquivos alterados: `painel_monstro/saidas/{carrinhos,carrinhos_planilha,fila_unica,regua_planilha,resumos_painel,contatos_manuais}.py`, `painel_monstro/rotina.py`, `apps-script/fila-por-email.gs` e `teste_local.js`, `tests/test_fluxo_sem_travas.py` e `tests/simulacao_fila.py`, docs, `AGENTS.md`.
- Como conferir: `pytest` (275 passed); `node apps-script/teste_local.js` (12 testes); `python -m tests.simulacao_fila` mostra uma semana com a Mariana sem marcar e uma rodada que falha.
- Problemas conhecidos: o Apps Script novo precisa ser colado de novo na planilha. O registro dos 9 VIPs foi desfeito a pedido do Túlio: a Mariana não enviou a lista manual.

## 2026-10-10 · Claude Code · etapa 5.2 (fila única e teste de 45 dias)
- Feito: `fila_unica.py` (VIP, 45 dias, aviso de garimpo, uma mensagem por pessoa, trava de 30 dias, prioridade e limite do dia, sugestão em estoque da família de gênero conferida na API), `regua_planilha.py` (aba `Régua`, parâmetros do teste na `Configuração`, modelos G45, VIP e ALERTA_GARIMPO e marcadores novos na `Mensagens`, registro do sorteio na aba `regua`), `generos.py` (famílias, iguais às da referência). Coluna `Origem` no fim da `Fila`; colunas `criado_em` e `atualizado_em` no fim de `produtos`. Resultado do teste de 45 dias entra na linha "WhatsApp de 45 dias" do `vale_a_pena`. Correção: disco "Novo/Lacrado" com categoria errada não recebe mais a mensagem de exemplar único usado. D-038.
- Arquivos alterados: `painel_monstro/saidas/fila_unica.py`, `regua_planilha.py`, `carrinhos.py`, `carrinhos_planilha.py`, `resumos_painel.py`, `rotina.py`, `painel_monstro/motor/generos.py`, `coletor/nuvemshop_api.py`, `coletor/planilhas_csv.py`, testes, `AGENTS.md`, docs.
- Como conferir: `python -m painel_monstro.saidas.fila_unica --amanha --sem-atualizar` (não grava nada); `pytest` dá 232 passed.
- Problemas conhecidos: nada foi enviado ao GitHub nem gravado na planilha nesta sessão. A aba `desejos` nasce vazia: sem pedidos, não há aviso de garimpo. O custo do "Vale a pena?" ainda não inclui frete grátis pago pela loja.

## 2026-10-08 · Claude Code · etapa 6 (abas de resumo) e email da fila
- Feito: email da fila por Google Apps Script (`apps-script/fila-por-email.gs`, D-036), testado pelo Túlio. `resumos_painel.py` grava as abas `atual`, `mensal`, `coortes`, `regua_hoje`, `regua_resultados`, `carrinhos_dia` e `vale_a_pena` como passo 5 da rotina (D-037). Guia clique a clique em `docs/LOOKER.md`. Verificador de privacidade passou a aceitar os dados fictícios dos testes de carrinho.
- Arquivos alterados: `painel_monstro/saidas/resumos_painel.py`, `painel_monstro/rotina.py`, `tests/test_resumos_painel.py`, `tests/test_rotina.py`, `docs/LOOKER.md`, `scripts/auditar_repositorio.py`, docs.
- Como conferir: a planilha tem as abas novas; `pytest` dá 210 passed; o painel do Looker segue `docs/LOOKER.md`.
- Problemas conhecidos: indicadores de custo (CPA, ROAS, margem) ficam vazios até o Túlio preencher a aba `custos`; régua e Vale a pena aparecem só 30 dias depois da primeira rodada gravada.

## 2026-10-08 · Claude Code · etapa 5.1 (parte 2: abas e rotina)
- Feito: `carrinhos_planilha.py` cria as abas Configuração, Mensagens, Bloqueio, Fila e Resultados com os valores padrão (se já existem, não mexe), lê parâmetros e modelos a cada rodada, grava a fila só nas colunas do Painel, detecta recuperação (pedido pago em até 7 dias do primeiro toque; grupo de comparação conta a partir do abandono), acrescenta "Não quer" ao Bloqueio e regrava Resultados. `rotina.py` ganhou o passo 4. Modelo escolhido e intervalo entre toques são respeitados. D-035.
- Arquivos alterados: `painel_monstro/saidas/carrinhos.py`, `painel_monstro/saidas/carrinhos_planilha.py`, `painel_monstro/rotina.py`, `tests/test_carrinhos*.py`, `tests/test_rotina.py`, docs.
- Como conferir: aba Fila da Planilha Google (16 linhas em 08/10); `pytest` dá 201 passed; Actions > Rotina do Painel mostra a linha "Carrinhos" no resumo.
- Problemas conhecidos: o email da fila ainda não existe. A planilha de produção tem uma aba `Página1` vazia (pode apagar).

## 2026-10-08 · Claude Code · etapa 5.1 (parte 1: fila de hoje, sem gravar)
- Feito: `carrinhos.py` com os filtros do AGENTS.md (janela de horas, já comprou, um por cliente, bloqueio, não aceita marketing, estoque conferido na API na hora), modelo pelo próximo toque (VIP sem cupom), mensagem com marcadores, link do WhatsApp, telefone inválido e grupo de comparação reproduzível. A API de carrinhos recusa o parâmetro `fields` (422), então os carrinhos vêm inteiros e são enxugados no código. 17 testes novos (188 no total). Fila real de 08/10: 59 carrinhos guardados, 16 na fila.
- Arquivos alterados: `painel_monstro/saidas/carrinhos.py`, `tests/test_carrinhos.py`, `docs/ESTADO.md`, `docs/HISTORICO.md`.
- Como conferir: `python -m painel_monstro.saidas.carrinhos --hoje` mostra os números e algumas mensagens; `pytest` deve dar 188 passed.
- Problemas conhecidos: nada é gravado na planilha ainda. "Cliente frequente" foi tratado como VIP (3+ compras ou R$1.000+) para não receber cupom; a mensagem T1_RECORRENTE fica no singular ("ficou") mesmo com vários discos.

## 2026-10-08 · Claude Code · etapa 5 (envio ao GitHub e primeira rodada)
- Feito: remoto `origin` configurado e `git push` do histórico (12 commits) depois de a auditoria dar LIMPO. O envio falhava com "Repository not found" porque o Windows guardava o login de outra conta do GitHub; o login guardado foi apagado (com autorização do Túlio) e o Túlio autorizou a conta certa no navegador. Rodada #1 falhou só na gravação (segredo do Google colado incorretamente); rodada #2 verde em 41 s, com os dados baixados na #1 vindos do cache.
- Arquivos alterados: `docs/ESTADO.md`, `docs/HISTORICO.md`.
- Como conferir: no GitHub, Actions > Rotina do Painel mostra a rodada #2 com sinal verde; a planilha tem as abas gravadas.
- Problemas conhecidos: nenhum. A rotina automática de hora em hora começa sozinha no próximo minuto 7.

## 2026-10-08 · Claude Code · mudança de pasta
- Feito: projeto movido para `C:\Users\tulio\painel-monstro`; `.venv` recriado e requirements reinstalado; 171 testes verdes; caminho antigo trocado no guia passo a passo (único arquivo que o citava). D-034.
- Arquivos alterados: `Painel Monstro · passo a passo da implementação.md`, `docs/DECISOES.md`, `docs/ESTADO.md`, `docs/HISTORICO.md`.
- Como conferir: `.venv\Scripts\python.exe -m pytest -q` deve dar 171 passed.
- Problemas conhecidos: nenhum. Se o Claude Code ainda apontar para a pasta antiga, reabra a sessão em `C:\Users\tulio\painel-monstro`.

## 2026-10-08 · Claude Code · etapa 5 (parcial: rotina pronta, falta GitHub)

- Feito: `painel_monstro/rotina.py` (coletor, motor, planilha), `.github/workflows/rotina.yml` (hora em hora, permissão mínima, cache privado dos dados baixados), suporte à chave do Google vinda de um Secret (`GOOGLE_SERVICE_ACCOUNT_JSON`, sem arquivo no disco), `scripts/auditar_repositorio.py`, 20 testes novos (171 no total) e PyYAML no requirements. Carimbos de data da rotina em horário de Brasília. Decisões D-031 a D-033.
- Auditoria antes do envio: nenhum token, chave, CPF ou dado de cliente nos arquivos nem no histórico (10 commits). Achado: a planilha-modelo tinha os 2 emails pessoais da equipe; trocados por exemplos a pedido do Túlio, com reescrita do histórico local (só a planilha mudou em cada commit) e remoção do histórico antigo do `.git`. Original guardado em `dados/referencia-original/`.
- Como conferir: `python scripts/auditar_repositorio.py` termina com LIMPO; `python -m pytest` dá 171 passando; `python -m painel_monstro.rotina` roda os 3 passos em cerca de 20 s.
- Problemas conhecidos: nada enviado ao GitHub ainda; a execução na nuvem só foi simulada em testes. O plano grátis do GitHub dá 2.000 minutos por mês em repositório privado; com o cache cada rotina leva cerca de 1 minuto (cerca de 900 por mês). Se o cache for apagado, a execução seguinte baixa tudo de novo (cerca de 3 minutos).
- Próximo passo: o Túlio cria o repositório e os segredos; então enviar e rodar à mão.

## 2026-10-08 · Claude Code · etapa 4 (primeira gravação real feita)

- Feito: depois que o Túlio ativou a Google Sheets API, o comando gravou as abas na Planilha Google (28 s). Conferido lendo a planilha de volta: clientes 2.838 linhas, pedidos 2.967, itens 4.967, produtos 5.438, indicadores 22, `custos` (10 colunas) e `alertas` (5 colunas) só com cabeçalho. Segunda rodada: exatamente as mesmas linhas (todas distintas, nada duplicado) e `custos` e `alertas` mantidas.
- Arquivos alterados: docs/ESTADO.md, docs/HISTORICO.md.
- Problemas conhecidos: a aba vazia `Página1`, criada pelo Google, continua na planilha.

## 2026-10-08 · Claude Code · etapa 4 (código e testes, antes da primeira gravação)

- Feito: `painel_monstro/saidas/planilha_google.py` (gspread): regrava as abas do Painel sem duplicar, mescla o histórico da `regua` por mês, cria `custos` e `alertas` só com cabeçalho e notas explicativas e lê a aba `custos` para os indicadores. Comando: `python -m painel_monstro.saidas.planilha_google [--regua AAAA-MM] [--forcar-regua]`. 27 testes novos com planilha de mentira (151 no total). Decisão D-030.
- Arquivos alterados: painel_monstro/saidas/planilha_google.py, tests/test_planilha_google.py, docs/ESTADO.md, docs/HISTORICO.md, docs/DECISOES.md.
- Como conferir: `python -m pytest` dá 151 passando. Depois de ativar a API: o comando imprime uma tabela com as linhas gravadas por aba e a planilha mostra as abas preenchidas; rodar duas vezes deixa o mesmo número de linhas.
- Problemas conhecidos: a execução real recebeu 403 do Google (Google Sheets API desativada no projeto), então nada foi gravado. Falha encontrada e corrigida: o gspread troca o 403 por `PermissionError` e o primeiro código não tratava; agora a mensagem diz o que ativar ou com quem compartilhar.
- Próximo passo: o Túlio ativa as APIs; rodar de novo e conferir as linhas.

## 2026-10-08 · Claude Code · etapa 3 (ajustes pedidos pelo Túlio)

- Feito: (1) a aba `custos` fica na Planilha Google, sem `dados/custos.csv`; (2) D-027 confirmada; (3) `frete_pago_loja` por mês na aba `custos`, vazio conta como zero, e o indicador "Descontos e fretes pagos ÷ receita" passou a somar o frete; (4) pedido pago e depois cancelado não conta em lugar nenhum (D-028) nos dois coletores; (5) itens casam com o produto pelo ID do produto da API (D-029), com colunas novas `produto_id` nos itens e `id` nos produtos.
- Resultado do casamento por ID (08/10/2026): 4.444 de 4.525 itens pagos casam; 81 (1,8%) não casam, de 73 produtos que saíram da loja; valem R$ 7.145 de R$ 587.823 (1,2%). Antes, pelo nome, eram 27% sem casar. Dos que casam: 2.696 lacrados, 1.659 usados, 89 de outros tipos (merchandise, combos e semelhantes).
- Arquivos alterados: painel_monstro/coletor/planilhas_csv.py, painel_monstro/coletor/nuvemshop_api.py, painel_monstro/motor/indicadores.py, tests/ajuda.py, tests/test_planilhas_csv.py, tests/test_nuvemshop_api.py, tests/test_indicadores.py, AGENTS.md, docs/DECISOES.md, docs/ESTADO.md, docs/HISTORICO.md.
- Como conferir: `python -m pytest` dá 124 passando; `python scripts/comparar_referencia.py 2026-10` continua em "tudo bate"; os indicadores de receita não mudaram (os 2 pedidos cancelados são de 2023).
- Problemas conhecidos: a margem ainda depende da aba `custos`, que só existe depois da Etapa 4.
- Próximo passo: Etapa 4.

## 2026-10-08 · Claude Code · etapa 3

- Feito: motor da régua (`regua.py`) e indicadores (`indicadores.py`), com 80 testes novos (118 no total), script `indicadores_hoje.py` e comparação com a referência reforçada (agora confere também as pessoas de cada lista). Decisões D-025 a D-027; AGENTS.md ganhou as colunas da aba `custos`.
- Arquivos alterados: painel_monstro/motor/regua.py, painel_monstro/motor/indicadores.py, scripts/indicadores_hoje.py, scripts/comparar_referencia.py, tests/ajuda.py, tests/test_regua.py, tests/test_indicadores.py, AGENTS.md, docs/ESTADO.md, docs/HISTORICO.md, docs/DECISOES.md.
- Como conferir: `python scripts/comparar_referencia.py 2026-10` termina com "tudo bate" e "Mesmas pessoas em cada lista e em cada controle: sim"; `python scripts/indicadores_hoje.py` mostra a tabela; `python -m pytest` dá 118 passando.
- Indicadores de 08/10/2026 (API): receita de quem volta R$ 6.251 por mês (documento: cerca de R$ 6,3 mil); 1.065 clientes nos últimos 12 meses (documento: 1.058); taxa de volta 2,3% (documento: 2,2%); gasto por recompra R$ 251 (documento: R$ 267); participação 28,1% (documento: 25%); clientes novos que voltam em 12 meses 8,6% (D-003: 9%); em 90 dias 7,2%; LTV de 12 meses R$ 225. Régua de hoje (referência 09/10): etapa 0 70+8, etapa 1 89+10, etapa 2 69+8, etapa 3 113+12, VIP 8.
- Problemas conhecidos: indicadores de Meta, Brevo e margem dependem da aba `custos` (vazia); incremento por etapa só aparece 30 dias depois do primeiro envio; garimpo, carrinhos e métricas do Brevo vêm das etapas 5.1, 5.2 e 7. 27% dos itens não casam com o catálogo atual pelo nome (usam a margem de usados). O frete pago pela loja não existe na API. A diferença no gasto por recompra (R$ 251 contra R$ 267) e na participação (28,1% contra 25%) em relação ao documento de estratégia não foi explicada: o documento não registra a data nem a conta usadas.
- Próximo passo: Etapa 4 (gravar na Planilha Google), depois que o Túlio criar a planilha e a conta de serviço.

## 2026-10-07 · Claude Code · etapa 2

- Feito: coletor da API da Nuvemshop (só leitura, primeira execução completa e depois incremental, controle do limite de requisições, token só no cabeçalho), `config.py`, 26 testes novos com API de mentira (38 no total) e script de comparação API × CSV. Primeira execução real: 2.966 pedidos, 2.842 clientes e 5.438 produtos. Notas da API no AGENTS.md atualizadas (D-024).
- Arquivos alterados: painel_monstro/config.py, painel_monstro/coletor/nuvemshop_api.py, scripts/comparar_api_csv.py, tests/test_nuvemshop_api.py, AGENTS.md, docs/ESTADO.md, docs/HISTORICO.md, docs/DECISOES.md.
- Como conferir: `python scripts/comparar_api_csv.py` mostra a tabela API × CSV; `python -m pytest` dá 38 passando; `python -m painel_monstro.coletor.nuvemshop_api` roda em poucos segundos e diz "0 novos".
- Comparação (CSV até 05/10/2026 18:46): nos pedidos em comum, 2.725 de 2.725 batem em email, total, desconto, subtotal, frete calculado, data/hora, cupom e número de itens; clientes em comum: marketing igual em 2.826 de 2.826. Diferenças: +7 pedidos pagos e +11 clientes depois da exportação; +4 pedidos pagos de 2022 e 2023 (2 arquivados e 2 cancelados, R$401,75 dos cancelados) que o CSV não traz, porque a exportação só leva pedidos abertos; −1 (pedido 2983, pago no CSV e estornado hoje). Pagos até o fim do CSV: 2.724 (CSV) × 2.727 (API) = +4 −1.
- Problemas conhecidos: a API é lenta (~4 s por página de 200). O frete não vem pronto, é calculado. Taxas e total líquido do pedido não existem na API (ficam vazios; a margem usará a aba `custos`). Dois pedidos pagos de 2023 estão com status "cancelado" e contam como válidos pela regra de pagamento do AGENTS.md; não afetam a régua (têm mais de 3 anos), mas vale perguntar ao Túlio se pedido cancelado deve contar.
- Próximo passo: Etapa 3 (motor da régua e indicadores).

## 2026-10-07 · Claude Code · etapa 1

- Feito: coletor por planilhas (`planilhas_csv.py`), script de comparação com a referência e 12 testes com dados fictícios. VLibras removido a pedido do Túlio (pasta e variável PYTHONPATH).
- Arquivos alterados: painel_monstro/coletor/planilhas_csv.py, scripts/comparar_referencia.py, tests/test_planilhas_csv.py, docs/ESTADO.md, docs/HISTORICO.md, docs/DECISOES.md (D-023).
- Como conferir: `python scripts/comparar_referencia.py 2026-10` mostra a tabela lado a lado e termina com "tudo bate"; `python -m pytest` dá 12 passando.
- Problemas conhecidos: nenhum. A comparação cria cópias dos dados em `dados/comparacao/`, que fica fora do git.
- Próximo passo: Etapa 2 (API da Nuvemshop), depois que o Túlio criar o aplicativo e o token.

## 2026-10-07 · Claude Code · etapa 0

- Feito: conferido que o Git 2.56 está instalado e o Python 3.12 não (há 3.13 e 3.14). Criadas as pastas do AGENTS.md (painel_monstro/coletor, motor, saidas, tests, dados/entrada, credenciais, .github/workflows), os `__init__.py`, o `requirements.txt` e o repositório git local na branch main.
- Arquivos alterados: requirements.txt, painel_monstro/, tests/, .github/workflows/, dados/ e credenciais/ (as duas últimas ficam fora do git), docs/ESTADO.md, docs/HISTORICO.md.
- Como conferir: `git log` mostra o commit da etapa 0; `git status` fica limpo.
- Problemas conhecidos: `.venv` não criado por falta do Python 3.12. A pasta dados/ não foi lida.
- Próximo passo: instalar o Python 3.12, criar o `.venv` e seguir para a Etapa 1.

## 2026-10-07 · Claude (Cowork) · decisões do mapa

- Criado o artifact "Mapa do Painel Monstro" com 7 diagramas (visão geral, jornada, carrinho, fila única, rotina, painel, cronograma).
- O Túlio decidiu D1 a D13 do mapa; registradas como D-014 a D-021. AGENTS.md ganhou a seção "Fila única de WhatsApp e medição".
- Planilha de referência do carrinho ganhou 5 parâmetros na aba Configuração (emails da fila, limite diário, aprovação do Léo, comparação do carrinho, prioridade).
- PROMPTS.md ganhou a etapa 5.2.
- D-022: teste até 18/01, depois todos menos controle fixo de 10%; regra de decisão de janeiro registrada.
- Próximo: começar a etapa 0 com o Túlio; lista semanal do WhatsApp de 45 dias, manual, a partir de 19/10.

## 2026-10-07 · Claude (Cowork) · antes da etapa 0 (ferramenta de carrinho)
- Feito: criada a ferramenta de carrinho abandonado em planilha (configuração editável, modelos de mensagem com marcadores, fila com mensagem e link do WhatsApp prontos). A regra do carrinho no AGENTS.md passou a dizer que tudo vem dessas abas.
- Arquivos alterados: AGENTS.md, PROMPTS.md, docs/HISTORICO.md, docs/DECISOES.md, dados/referencia-privada/Carrinhos-Monstro-ferramenta.xlsx.
- Como conferir: abrir a planilha, mudar um parâmetro na aba Configuração e ver a fila mudar.
- Problemas conhecidos: na versão manual, quem envia precisa somar o toque e a data depois de cada envio.
- Próximo passo: usar a planilha no lugar do .txt de recuperação até a etapa 5.1.

## 2026-10-06 · Claude (Cowork) · antes da etapa 0 (complemento)
- Feito: incluída a estratégia de carrinho abandonado (seção no AGENTS.md, etapa 5.1 no PROMPTS.md, decisões D-011 e D-012) e copiado o playbook atual de recuperação para `referencia/`.
- Arquivos alterados: AGENTS.md, PROMPTS.md, docs/DECISOES.md, docs/ESTADO.md, docs/HISTORICO.md, referencia/playbook-recuperacao-carrinho.md.
- Como conferir: a seção "Carrinho abandonado" aparece no AGENTS.md.
- Problemas conhecidos: nenhum.
- Próximo passo: Etapa 0.

## 2026-10-06 · Claude (Cowork) · antes da etapa 0
- Feito: desenho do Painel Monstro (objetivo, arquitetura sem servidor, módulos, dados, indicadores e fases) e criação do kit inicial do repositório.
- Arquivos alterados: AGENTS.md, CLAUDE.md, PROMPTS.md, .gitignore, env-exemplo.txt, docs/ESTADO.md, docs/HISTORICO.md, docs/DECISOES.md, referencia/reativacao.py.
- Como conferir: os arquivos existem na pasta `painel-monstro`.
- Problemas conhecidos: o arquivo `.env` não pôde ser criado pela ferramenta remota; o modelo está em `env-exemplo.txt` e o agente cria o `.env` a partir dele.
- Próximo passo: Etapa 0 do PROMPTS.md, depois que as pendências da parte 1 e 2 do passo a passo estiverem prontas.
- Documentos de apoio (fora do repositório, no Claude): "Estratégia de LTV e reativação · Monstro Discos", "Painel Monstro · desenho do CRM" e "Painel Monstro · passo a passo da implementação".
