/**
 * Painel Monstro · COFRE (D-069). Projeto do Apps Script na conta Gmail da Monstro.
 *
 * Implantar como app da Web: Executar como "Eu" (conta da Monstro);
 * Quem pode acessar "Qualquer pessoa". Só responde a quem manda o SEGREDO (a entrada).
 * Serviço avançado: + Serviços > Google Sheets API (identificador Sheets).
 *
 * Confere cada pedido na aba Acessos (email | nome | nivel | observacao):
 *   especial = vê e altera tudo;
 *   comum    = vê e altera tudo, menos a comissão (aba comissao).
 * Toda gravação fica registrada na aba acessos_log (quando, quem, o quê).
 *
 * Rode prepararCofre() uma vez: cria as abas Acessos e acessos_log e mostra o SEGREDO.
 */

var PLANILHA = PropertiesService.getScriptProperties().getProperty('PLANILHA_ID') || ''; // configurar no Apps Script, nunca no git
var SO_ESPECIAL = ['comissao', 'comissao_produtos', 'pedidos_manuais', 'acessos', 'acessos_log'];  // abas que o nível comum não lê

function prepararCofre() {
  var ss = SpreadsheetApp.openById(PLANILHA);
  if (!ss.getSheetByName('Acessos')) {
    var a = ss.insertSheet('Acessos');
    a.getRange(1, 1, 3, 4).setValues([
      ['email', 'nome', 'nivel', 'observacao'],
      ['administrador@exemplo.com', 'Administrador de exemplo', 'especial', ''],
      ['operacao@exemplo.com', 'Operação de exemplo', 'especial', '']]);
    a.setFrozenRows(1);
  }
  if (!ss.getSheetByName('acessos_log')) {
    ss.insertSheet('acessos_log').getRange(1, 1, 1, 4).setValues([['quando', 'email', 'faixa', 'valor']]);
  }
  var p = PropertiesService.getScriptProperties();
  if (!p.getProperty('SEGREDO')) p.setProperty('SEGREDO', Utilities.getUuid() + Utilities.getUuid());
  Logger.log('SEGREDO (copie para as propriedades da ENTRADA): ' + p.getProperty('SEGREDO'));
}

function doPost(e) {
  var c;
  try { c = JSON.parse(e.postData.contents); } catch (x) { return json_({ ok: false, erro: 'pedido inválido' }); }
  var segredo = PropertiesService.getScriptProperties().getProperty('SEGREDO');
  if (!segredo || c.segredo !== segredo) return json_({ ok: false, erro: 'não autorizado' });
  var u = usuario_(c.email);
  if (!u) return json_({ ok: false, erro: 'sem_acesso' });
  try {
    if (c.acao === 'quem') return json_({ ok: true, nome: u.nome, nivel: u.nivel, planilha_id: PLANILHA });
    if (c.acao === 'ler') return json_({ ok: true, dados: ler_(u, c.ranges || []) });
    if (c.acao === 'gravar') {
      if (!podeGravar_(u, c.range)) return json_({ ok: false, erro: 'sem_permissao' });
      try { Sheets.Spreadsheets.Values.update({ values: c.values }, PLANILHA, c.range, { valueInputOption: 'USER_ENTERED' }); } catch (e1) { var na = String(c.range).split('!')[0].replace(/^'|'$/g, '').trim(), ss = SpreadsheetApp.openById(PLANILHA); if (!ss.getSheetByName(na)) ss.insertSheet(na); Sheets.Spreadsheets.Values.update({ values: c.values }, PLANILHA, c.range, { valueInputOption: 'USER_ENTERED' }); }
      registrar_(u, c.range, c.values);
      return json_({ ok: true });
    }
    return json_({ ok: false, erro: 'ação desconhecida' });
  } catch (x) {
    return json_({ ok: false, erro: 'falha na planilha: ' + String(x && x.message || x).slice(0, 150) });
  }
}

function usuario_(email) {
  email = String(email || '').trim().toLowerCase();
  if (!email) return null;
  var cache = CacheService.getScriptCache(), guardado = cache.get('acessos');   // 1 minuto: mudança na aba vale logo
  var v = guardado ? JSON.parse(guardado) : SpreadsheetApp.openById(PLANILHA).getSheetByName('Acessos').getDataRange().getDisplayValues();
  if (!guardado) cache.put('acessos', JSON.stringify(v), 60);
  for (var i = 1; i < v.length; i++) {
    if (String(v[i][0]).trim().toLowerCase() === email) {
      var nivel = String(v[i][2]).trim().toLowerCase();
      if (nivel === 'especial' || nivel === 'comum') return { email: email, nome: v[i][1], nivel: nivel };
    }
  }
  return null;
}

function aba_(range) { return String(range).split('!')[0].replace(/^'|'$/g, '').trim().toLowerCase(); }

function ler_(u, ranges) {
  var ok = ranges.filter(function (r) { return u.nivel === 'especial' || SO_ESPECIAL.indexOf(aba_(r)) < 0; });
  var out = {};
  if (ok.length) {
    try {
      var resp = Sheets.Spreadsheets.Values.batchGet(PLANILHA, { ranges: ok, valueRenderOption: 'FORMATTED_VALUE' });
      (resp.valueRanges || []).forEach(function (vr, i) { out[ok[i]] = vr.values || []; });
    } catch (x) {
      // Uma aba que ainda não existe derruba a leitura em lote: lê uma por uma e a que faltar volta vazia
      ok.forEach(function (r) {
        try { out[r] = Sheets.Spreadsheets.Values.get(PLANILHA, r, { valueRenderOption: 'FORMATTED_VALUE' }).values || []; }
        catch (y) { out[r] = []; }
      });
    }
  }
  ranges.forEach(function (r) { if (!(r in out)) out[r] = null; });   // null = sem permissão
  return out;
}

function podeGravar_(u, range) {
  if (aba_(range) === 'acessos' || aba_(range) === 'acessos_log') return false;   // acessos só pela planilha
  return u.nivel === 'especial' || SO_ESPECIAL.indexOf(aba_(range)) < 0;
}

function registrar_(u, range, values) {
  try {
    var log = SpreadsheetApp.openById(PLANILHA).getSheetByName('acessos_log');
    if (log) log.appendRow([new Date(), u.email, range, JSON.stringify(values).slice(0, 300)]);
  } catch (x) { /* o registro nunca impede a gravação */ }
}

function json_(o) { return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON); }
