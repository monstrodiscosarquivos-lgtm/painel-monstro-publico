/**
 * Vigia do cadastro de discos (D-068) e relógios dos workflows do Painel (D-109).
 * Projeto próprio do Apps Script (script.google.com > Novo projeto, nome vigia-cadastro),
 * na conta da Monstro, separado do fila-por-email.gs: abre a planilha pelo ID.
 *
 * O que faz:
 *  1. Cadastro (a cada 5 minutos): olha a aba cadastro_rascunhos e, se houver disco aprovado/pendente,
 *     dispara "Cadastro de discos aprovados" (.github/workflows/cadastro.yml) via repository_dispatch ("cadastro").
 *  2. Relógio da Rotina (a cada 1 hora): dispara "Rotina do Painel" (.github/workflows/rotina.yml)
 *     via repository_dispatch ("rotina"), porque o cron do GitHub Actions pode atrasar ou falhar.
 *  3. Relógio do Black rápido (a cada 15 minutos, só entre 26/11/2026 e 01/12/2026 em Brasília):
 *     dispara "Black rápido" (.github/workflows/black-rapido.yml) via repository_dispatch ("black-rapido").
 *
 * Não cria produto nem mexe na loja: só avisa o GitHub. Não manda email.
 *
 * Configuração (uma vez):
 *  1. Project Settings (engrenagem) > Script Properties > Add: GITHUB_TOKEN = o token do GitHub
 *     (fine-grained, só o repositório público novo, permissão Contents: Read and write).
 *     Adicione GITHUB_REPO = DONO/REPOSITORIO_PUBLICO e PLANILHA_ID = ID privado da planilha.
 *  2. Rode instalarVigiaCadastro (para o cadastro) e instalarRelogios (para rotina e Black) uma vez e autorize.
 * Toda madrugada (3h) também move para a pasta "arquivo" (ao lado da "entrada") as fotos dos discos
 * publicados ou descartados, para a entrada ficar só com a leva nova. Nada é apagado.
 *
 * Funções para rodar à mão: instalarVigiaCadastro, desinstalarVigiaCadastro, instalarRelogios,
 * removerRelogiosBlack, dispararCadastroAgora, dispararRotina, dispararBlackRapido, arquivarFotos.
 */

var VIGIA_REPO = PropertiesService.getScriptProperties().getProperty('GITHUB_REPO') || ''; // DONO/REPOSITORIO_PUBLICO, configurado só no Apps Script
var VIGIA_ABA = 'cadastro_rascunhos';
var VIGIA_PLANILHA = PropertiesService.getScriptProperties().getProperty('PLANILHA_ID') || ''; // valor privado nas propriedades
var VIGIA_REPETIR_MIN = 20;   // pendente há mais que isso e sem novidade: pede de novo (rodada falhou ou foi cancelada)
var RELOGIO_FUSO = 'America/Sao_Paulo';
var BLACK_INICIO = '2026-11-26';
var BLACK_FIM = '2026-12-01';

/** Rode uma vez para ligar o vigia (a cada 5 minutos). */
function instalarVigiaCadastro() {
  desinstalarVigiaCadastro();
  ScriptApp.newTrigger('vigiarCadastro').timeBased().everyMinutes(5).create();
  ScriptApp.newTrigger('arquivarFotos').timeBased().everyDays(1).atHour(3).create();   // madrugada
  verificarPropriedadesGitHub_();
  Logger.log('Pronto: o vigia do cadastro olha a planilha a cada 5 minutos.');
}

/** Desliga só o vigia (não mexe no agendamento da fila nem nos relógios). */
function desinstalarVigiaCadastro() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    var f = t.getHandlerFunction();
    if (f === 'vigiarCadastro' || f === 'arquivarFotos') ScriptApp.deleteTrigger(t);
  });
}

/** Cria (sem duplicar) os acionadores de tempo da Rotina (1h) e do Black rápido (15 min). */
function instalarRelogios() {
  removerRelogios_(['dispararRotina', 'dispararBlackRapido']);
  ScriptApp.newTrigger('dispararRotina').timeBased().everyHours(1).create();
  ScriptApp.newTrigger('dispararBlackRapido').timeBased().everyMinutes(15).create();
  verificarPropriedadesGitHub_();
  Logger.log('Pronto: relógios instalados (dispararRotina a cada 1h e dispararBlackRapido a cada 15 min).');
}

/** Remove apenas o acionador de tempo do Black rápido (mantém rotina e vigia do cadastro ativos). */
function removerRelogiosBlack() {
  removerRelogios_(['dispararBlackRapido']);
  Logger.log('Relógio do Black rápido removido.');
}

function removerRelogios_(funcoes) {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (funcoes.indexOf(t.getHandlerFunction()) >= 0) ScriptApp.deleteTrigger(t);
  });
}

function verificarPropriedadesGitHub_() {
  var props = PropertiesService.getScriptProperties();
  if (!props.getProperty('GITHUB_TOKEN')) {
    Logger.log('Atenção: falta a propriedade GITHUB_TOKEN (Project Settings > Script Properties).');
  }
  if (!(VIGIA_REPO || props.getProperty('GITHUB_REPO'))) {
    Logger.log('Atenção: falta a propriedade GITHUB_REPO (Project Settings > Script Properties).');
  }
}

/** Teste: pede a rodada de cadastro agora, mesmo sem disco aprovado pendente. */
function dispararCadastroAgora() {
  Logger.log(dispararCadastro_() ? 'Pedido enviado ao GitHub.' : 'Falhou: veja a mensagem acima.');
}

/** Dispara a "Rotina do Painel" no GitHub Actions (repository_dispatch type: "rotina"). */
function dispararRotina() {
  var ok = dispararDispatch_({ event_type: 'rotina' });
  Logger.log(ok ? 'Rotina disparada no GitHub (rotina).' : 'Falhou: veja a mensagem acima.');
  return ok;
}

/** Dispara o "Black rápido" no GitHub Actions (type: "black-rapido") só de 26/11/2026 a 01/12/2026 (Brasília). */
function dispararBlackRapido() {
  var hoje = Utilities.formatDate(new Date(), RELOGIO_FUSO, 'yyyy-MM-dd');
  if (hoje < BLACK_INICIO || hoje > BLACK_FIM) {
    Logger.log('Black rápido fora do período (' + BLACK_INICIO + ' a ' + BLACK_FIM + '); hoje é ' + hoje + '. Nada disparado.');
    return false;
  }
  var ok = dispararDispatch_({ event_type: 'black-rapido' });
  Logger.log(ok ? 'Black rápido disparado no GitHub (black-rapido).' : 'Falhou: veja a mensagem acima.');
  return ok;
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

/** IDs com status "aprovado" e sem produto_id, com subir_loja = "pedido" ou atualizar_preco = "pedido" na aba cadastro_rascunhos. */
function aprovadosPendentes_() {
  var aba = SpreadsheetApp.openById(VIGIA_PLANILHA).getSheetByName(VIGIA_ABA);
  if (!aba || aba.getLastRow() < 2) return [];
  var v = aba.getRange(1, 1, aba.getLastRow(), aba.getLastColumn()).getDisplayValues();
  var cab = v[0];
  var cId = cab.indexOf('id'), cSt = cab.indexOf('status'), cProd = cab.indexOf('produto_id');
  var cSubir = cab.indexOf('subir_loja');
  var cPreco = cab.indexOf('atualizar_preco');   // D-104: preço corrigido na Conferência
  var cRefazer = cab.indexOf('refazer_discogs');  // D-107: cadastro errado, refazer pelo Discogs
  if (cId < 0) return [];
  var ids = [];
  for (var i = 1; i < v.length; i++) {
    var idVal = String(v[i][cId]).trim();
    if (!idVal) continue;
    var st = cSt >= 0 ? String(v[i][cSt]).trim().toLowerCase() : '';
    var prod = cProd >= 0 ? String(v[i][cProd]).trim() : '';
    var subir = cSubir >= 0 ? String(v[i][cSubir]).trim().toLowerCase() : '';

    var precisaAprovar = (st === 'aprovado' && !prod);
    var precisaSubir = (subir === 'pedido');
    var precisaPreco = cPreco >= 0 && String(v[i][cPreco]).trim().toLowerCase() === 'pedido';
    var precisaRefazer = cRefazer >= 0 && String(v[i][cRefazer]).trim().toLowerCase() === 'pedido';

    if (precisaAprovar || precisaSubir || precisaPreco || precisaRefazer) {
      ids.push(idVal);
    }
  }
  return ids;
}

/** Pede ao GitHub um repository_dispatch usando GITHUB_REPO e GITHUB_TOKEN das Propriedades do script. */
function dispararDispatch_(payload) {
  var props = PropertiesService.getScriptProperties();
  var repo = VIGIA_REPO || props.getProperty('GITHUB_REPO') || '';
  if (!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repo)) { Logger.log('Configure GITHUB_REPO nas propriedades: DONO/REPOSITORIO_PUBLICO.'); return false; }
  var token = props.getProperty('GITHUB_TOKEN');
  if (!token) { Logger.log('Falta a propriedade GITHUB_TOKEN.'); return false; }
  var resp = UrlFetchApp.fetch('https://api.github.com/repos/' + repo + '/dispatches', {
    method: 'post',
    contentType: 'application/json',
    headers: { Authorization: 'Bearer ' + token, Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28' },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  });
  var codigo = resp.getResponseCode();
  if (codigo === 204) return true;
  // Nunca registra o token; só o código HTTP e o evento.
  Logger.log('GitHub respondeu HTTP ' + codigo + ' para ' + payload.event_type + '. Confira repositório e permissão do token.');
  return false;
}

/** Pede ao GitHub a rodada "Cadastro de discos aprovados". Devolve true se o GitHub aceitou. */
function dispararCadastro_() {
  return dispararDispatch_({ event_type: 'cadastro' });
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

