/**
 * Vigia do cadastro de discos (D-068). Projeto próprio do Apps Script (script.google.com > Novo projeto,
 * nome vigia-cadastro), na conta da Monstro, separado do fila-por-email.gs: abre a planilha pelo ID.
 *
 * A cada 5 minutos olha a aba cadastro_rascunhos. Se houver disco com status "aprovado" e ainda
 * sem produto_id, pede ao GitHub a rodada curta "Cadastro de discos aprovados"
 * (.github/workflows/cadastro.yml), que cria o produto oculto na Nuvemshop em 1 a 3 minutos.
 * Assim o disco aparece na loja poucos minutos depois de aprovado no Painel, sem esperar a rotina
 * de hora em hora. Se o vigia falhar, nada se perde: a rotina de hora em hora cria do mesmo jeito.
 *
 * Não cria produto nem mexe na loja: só avisa o GitHub. Não manda email.
 *
 * Configuração (uma vez):
 *  1. Project Settings (engrenagem) > Script Properties > Add: GITHUB_TOKEN = o token do GitHub
 *     (fine-grained, só o repositório público novo, permissão Contents: Read and write).
 *     Adicione GITHUB_REPO = DONO/REPOSITORIO_PUBLICO e PLANILHA_ID = ID privado da planilha.
 *  2. Rode instalarVigiaCadastro uma vez e autorize.
 * Toda madrugada (3h) também move para a pasta "arquivo" (ao lado da "entrada") as fotos dos discos
 * publicados ou descartados, para a entrada ficar só com a leva nova. Nada é apagado.
 *
 * Funções para rodar à mão: instalarVigiaCadastro, desinstalarVigiaCadastro, dispararCadastroAgora, arquivarFotos.
 */

var VIGIA_REPO = PropertiesService.getScriptProperties().getProperty('GITHUB_REPO') || ''; // DONO/REPOSITORIO_PUBLICO, configurado só no Apps Script
var VIGIA_ABA = 'cadastro_rascunhos';
var VIGIA_PLANILHA = PropertiesService.getScriptProperties().getProperty('PLANILHA_ID') || ''; // valor privado nas propriedades
var VIGIA_REPETIR_MIN = 20;   // pendente há mais que isso e sem novidade: pede de novo (rodada falhou ou foi cancelada)

/** Rode uma vez para ligar o vigia (a cada 5 minutos). */
function instalarVigiaCadastro() {
  desinstalarVigiaCadastro();
  ScriptApp.newTrigger('vigiarCadastro').timeBased().everyMinutes(5).create();
  ScriptApp.newTrigger('arquivarFotos').timeBased().everyDays(1).atHour(3).create();   // madrugada
  if (!PropertiesService.getScriptProperties().getProperty('GITHUB_TOKEN')) {
    Logger.log('Atenção: falta a propriedade GITHUB_TOKEN (Project Settings > Script Properties).');
  }
  Logger.log('Pronto: o vigia do cadastro olha a planilha a cada 5 minutos.');
}

/** Desliga só o vigia (não mexe no agendamento da fila). */
function desinstalarVigiaCadastro() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    var f = t.getHandlerFunction();
    if (f === 'vigiarCadastro' || f === 'arquivarFotos') ScriptApp.deleteTrigger(t);
  });
}

/** Teste: pede a rodada de cadastro agora, mesmo sem disco aprovado pendente. */
function dispararCadastroAgora() {
  Logger.log(dispararCadastro_() ? 'Pedido enviado ao GitHub.' : 'Falhou: veja a mensagem acima.');
}

/** Chamado pelo agendamento. */
function vigiarCadastro() {
  var trava = LockService.getScriptLock();
  if (!trava.tryLock(1000)) return;
  try {
    var props = PropertiesService.getScriptProperties();
    var pendentes = aprovadosPendentes_();
    if (!pendentes.length) { props.deleteProperty('CADASTRO_PEDIDOS'); return; }

    var anteriores = (props.getProperty('CADASTRO_PEDIDOS') || '').split(',').filter(String);
    var ultimo = Number(props.getProperty('CADASTRO_ULTIMO_PEDIDO') || 0);
    var novidade = pendentes.some(function (id) { return anteriores.indexOf(id) < 0; });
    var parado = Date.now() - ultimo > VIGIA_REPETIR_MIN * 60 * 1000;
    if (!novidade && !parado) return;   // já pediu por esses discos; a rodada está na fila ou rodando

    if (dispararCadastro_()) {
      props.setProperty('CADASTRO_PEDIDOS', pendentes.join(','));
      props.setProperty('CADASTRO_ULTIMO_PEDIDO', String(Date.now()));
    }
  } finally {
    trava.releaseLock();
  }
}

/** IDs com status "aprovado" e sem produto_id na aba cadastro_rascunhos. */
function aprovadosPendentes_() {
  var aba = SpreadsheetApp.openById(VIGIA_PLANILHA).getSheetByName(VIGIA_ABA);
  if (!aba || aba.getLastRow() < 2) return [];
  var v = aba.getRange(1, 1, aba.getLastRow(), aba.getLastColumn()).getDisplayValues();
  var cab = v[0];
  var cId = cab.indexOf('id'), cSt = cab.indexOf('status'), cProd = cab.indexOf('produto_id');
  if (cId < 0 || cSt < 0 || cProd < 0) return [];
  var ids = [];
  for (var i = 1; i < v.length; i++) {
    var st = String(v[i][cSt]).trim().toLowerCase();
    if (st === 'aprovado' && !String(v[i][cProd]).trim() && String(v[i][cId]).trim()) ids.push(String(v[i][cId]).trim());
  }
  return ids;
}

/** Pede ao GitHub a rodada "Cadastro de discos aprovados". Devolve true se o GitHub aceitou. */
function dispararCadastro_() {
  if (!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(VIGIA_REPO)) { Logger.log('Configure GITHUB_REPO nas propriedades: DONO/REPOSITORIO_PUBLICO.'); return false; }
  var token = PropertiesService.getScriptProperties().getProperty('GITHUB_TOKEN');
  if (!token) { Logger.log('Falta a propriedade GITHUB_TOKEN.'); return false; }
  var resp = UrlFetchApp.fetch('https://api.github.com/repos/' + VIGIA_REPO + '/dispatches', {
    method: 'post',
    contentType: 'application/json',
    headers: { Authorization: 'Bearer ' + token, Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28' },
    payload: JSON.stringify({ event_type: 'cadastro' }),
    muteHttpExceptions: true
  });
  var codigo = resp.getResponseCode();
  if (codigo === 204) return true;
  // Nunca registra o token; só o código e o começo da resposta do GitHub.
  Logger.log('GitHub respondeu HTTP ' + codigo + '. Confira repositório e permissão do token.');
  return false;
}

/**
 * Move da pasta de entrada para "Cadastro de Discos/arquivo" as fotos dos discos já publicados ou
 * descartados. Reconhece a foto pelo começo do nome (o código do disco, ex.: "2026-10-15-01 01 capa…").
 * Fotos novas (IMG_…) e de discos ainda em revisão, aprovados, criados ou com erro ficam onde estão.
 */
function arquivarFotos() {
  var ss = SpreadsheetApp.openById(VIGIA_PLANILHA);
  var v = ss.getSheetByName(VIGIA_ABA).getDataRange().getDisplayValues();
  var cab = v[0], cId = cab.indexOf('id'), cSt = cab.indexOf('status');
  var prontos = {};
  for (var i = 1; i < v.length; i++) {
    var st = String(v[i][cSt]).trim().toLowerCase(), id = String(v[i][cId]).trim();
    if (id && (st === 'publicado' || st.indexOf('descartado') === 0)) prontos[id] = true;
  }
  var cfg = ss.getSheetByName('Configuração').getDataRange().getDisplayValues(), idEntrada = '';
  cfg.forEach(function (r) { if (String(r[0]).trim() === 'Cadastro: pasta de entrada Drive (ID)') idEntrada = String(r[1]).trim(); });
  if (!idEntrada) { Logger.log('Falta o ID da pasta de entrada na aba Configuração.'); return; }
  var entrada = DriveApp.getFolderById(idEntrada), pais = entrada.getParents();
  if (!pais.hasNext()) { Logger.log('A pasta de entrada não tem pasta acima.'); return; }
  var acima = pais.next(), achou = acima.getFoldersByName('arquivo');
  var arquivo = achou.hasNext() ? achou.next() : acima.createFolder('arquivo');
  var arquivos = entrada.getFiles(), movidos = 0;
  while (arquivos.hasNext()) {
    var f = arquivos.next(), m = f.getName().match(/^(\d{4}-\d{2}-\d{2}-\d+) /);
    if (m && prontos[m[1]]) { f.moveTo(arquivo); movidos++; }
  }
  Logger.log(movidos + ' fotos movidas para "arquivo".');
}

