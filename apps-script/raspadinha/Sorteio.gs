/**
 * Raspadinha · SORTEIO (D-070). Projeto do Apps Script na conta Gmail da Monstro.
 *
 * Implantar como app da Web: Executar como "Eu"; Quem pode acessar "Qualquer pessoa".
 * É chamado pela página pública da raspadinha (GitHub Pages). Faz três coisas:
 *   config : devolve o que a página precisa mostrar da campanha (nunca as chances nem os limites);
 *   abriu  : registra que alguém abriu a página (para o funil por canal);
 *   jogar  : sorteia o prêmio pela chance de cada um, respeitando o máximo de cada prêmio,
 *            cria um cupom único na Nuvemshop e grava a jogada. O mesmo email na mesma campanha
 *            recebe sempre o mesmo resultado (abrir de novo não sorteia de novo).
 *
 * Campanhas e prêmios ficam na aba rasp_campanhas (editada pelo Painel, aba Raspadinha).
 * Jogadas em rasp_jogadas; aberturas em rasp_eventos. A conta do cliente nunca é aberta;
 * o token da loja fica só nas propriedades deste projeto.
 *
 * Propriedades do script: NUVEMSHOP_STORE_ID, NUVEMSHOP_TOKEN, NUVEMSHOP_USER_AGENT
 * (os mesmos valores do arquivo .env do painel-monstro). Rode prepararRaspadinha() uma vez.
 *
 * Cancelar cupons (D-074): o Painel escreve "cancelar" na coluna cupom_status; processarCancelamentos() roda a cada
 * 5 minutos (rode instalarGatilhoCancelamentos() uma vez), desativa o cupom na Nuvemshop e grava "cancelado".
 */

var PLANILHA = PropertiesService.getScriptProperties().getProperty('PLANILHA_ID') || ''; // configurar no Apps Script, nunca no git
var API_VERSAO = '2025-03';
var ALFABETO = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789';               // sem 0/O e 1/I/L
var ABA_CAMP = 'rasp_campanhas', ABA_JOG = 'rasp_jogadas', ABA_EV = 'rasp_eventos';
var CAB_CAMP = ['campanha', 'nome', 'status', 'inicio', 'fim', 'canais', 'validade_dias', 'pedido_minimo', 'cumulativo',
  'so_clientes', 'permitir_sem_premio', 'texto_sem_premio', 'prefixo', 'titulo', 'texto', 'premios', 'atualizado_em', 'origens'];
var CAB_JOG = ['quando', 'campanha', 'email', 'canal', 'utm_source', 'utm_medium', 'utm_campaign', 'utm_content',
  'premio', 'tipo', 'valor', 'cupom', 'valido_ate', 'cupom_status', 'consentiu', 'novo_contato', 'cupom_id'];
var CAB_EV = ['quando', 'campanha', 'canal', 'evento', 'utm_medium', 'utm_content'];
var FUSO = 'America/Sao_Paulo';

/** Rode uma vez: cria as abas e a campanha de teste (sem mexer no que já existir). */
function prepararRaspadinha() {
  var ss = SpreadsheetApp.openById(PLANILHA);
  [[ABA_CAMP, CAB_CAMP], [ABA_JOG, CAB_JOG], [ABA_EV, CAB_EV]].forEach(function (x) {
    if (!ss.getSheetByName(x[0])) {
      var a = ss.insertSheet(x[0]);
      a.getRange(1, 1, 1, x[1].length).setValues([x[1]]);
      a.setFrozenRows(1);
      a.getRange('A:Z').setNumberFormat('@');   // tudo como texto: datas e códigos não viram número
    }
  });
  var camp = ss.getSheetByName(ABA_CAMP);
  if (camp.getLastRow() < 2) {
    var hoje = Utilities.formatDate(new Date(), FUSO, 'yyyy-MM-dd');
    var premios = [
      { rotulo: '10%', tipo: 'Porcentagem', valor: 10, chance: 60, maximo: '', reserva: 'Sim' },
      { rotulo: '15%', tipo: 'Porcentagem', valor: 15, chance: 25, maximo: 200, reserva: '' },
      { rotulo: '20%', tipo: 'Porcentagem', valor: 20, chance: 10, maximo: 50, reserva: '' },
      { rotulo: '50%', tipo: 'Porcentagem', valor: 50, chance: 5, maximo: 10, reserva: '' }];
    camp.appendRow(['teste-raspadinha', 'Raspadinha teste', 'teste', hoje, '', 'email, instagram, whatsapp', '7', '0', 'Não',
      'Não', 'Não', 'Não foi dessa vez, mas fica de olho: logo tem mais.', 'RASPA',
      'Raspe e ganhe na Loja Monstro', 'Raspe o selo do disco e descubra seu desconto.', JSON.stringify(premios), hoje, '[]']);
  }
  ['NUVEMSHOP_STORE_ID', 'NUVEMSHOP_TOKEN', 'NUVEMSHOP_USER_AGENT'].forEach(function (k) {
    if (!PropertiesService.getScriptProperties().getProperty(k)) Logger.log('Falta a propriedade ' + k);
  });
  Logger.log('Pronto. Abas: ' + ABA_CAMP + ', ' + ABA_JOG + ', ' + ABA_EV + '.');
}

// ----------------------------------------------------------------------------- entrada
function doPost(e) {
  var c;
  try { c = JSON.parse(e.postData.contents); } catch (x) { return json_({ ok: false, erro: 'pedido inválido' }); }
  try {
    if (c.acao === 'config') return json_(config_(c));
    if (c.acao === 'abriu') return json_(abriu_(c));
    if (c.acao === 'jogar') return json_(jogar_(c));
    return json_({ ok: false, erro: 'ação desconhecida' });
  } catch (x) {
    console.error(x);
    return json_({ ok: false, erro: 'falha', detalhe: 'Tivemos um problema agora. Tente de novo em alguns minutos.' });
  }
}
function doGet(e) { return doPost({ postData: { contents: JSON.stringify(e.parameter || {}) } }); }

// ----------------------------------------------------------------------------- campanhas
function lerCampanha_(id) {
  id = String(id || '').trim().toLowerCase();
  var v = SpreadsheetApp.openById(PLANILHA).getSheetByName(ABA_CAMP).getDataRange().getDisplayValues();
  var cab = v[0];
  for (var i = 1; i < v.length; i++) {
    if (String(v[i][cab.indexOf('campanha')]).trim().toLowerCase() === id) {
      var o = {}; cab.forEach(function (k, j) { o[k] = v[i][j]; });
      try { o.premios = JSON.parse(o.premios || '[]'); } catch (x) { o.premios = []; }
      try { var or = JSON.parse(o.origens || '[]'); o.origens = Array.isArray(or) ? or : []; } catch (x) { o.origens = []; }
      return o;
    }
  }
  return null;
}
function sim_(v) { return /^(sim|s|true|1)$/i.test(String(v || '').trim()); }
function hoje_() { return Utilities.formatDate(new Date(), FUSO, 'yyyy-MM-dd'); }
function dataISO_(v) {
  v = String(v || '').trim(); if (!v) return '';
  var m = v.match(/^(\d{2})\/(\d{2})\/(\d{4})/); if (m) return m[3] + '-' + m[2] + '-' + m[1];
  return v.slice(0, 10);
}
/** Situação da campanha para a página: aberta, teste, em_breve, encerrada, pausada, inexistente. */
function situacao_(cp) {
  if (!cp) return 'inexistente';
  var st = String(cp.status || '').trim().toLowerCase(), h = hoje_();
  if (st === 'pausada') return 'pausada';
  if (st === 'encerrada') return 'encerrada';
  if (st !== 'ativa' && st !== 'teste') return 'inexistente';   // rascunho não abre
  if (dataISO_(cp.inicio) && h < dataISO_(cp.inicio)) return 'em_breve';
  if (dataISO_(cp.fim) && h > dataISO_(cp.fim)) return 'encerrada';
  return st === 'teste' ? 'teste' : 'aberta';
}
function canal_(c, cp) {
  var s = String((c && c.utm_source) || '').trim().toLowerCase();
  if (!s) return 'direto';
  var origs = (cp && Array.isArray(cp.origens)) ? cp.origens : [];
  for (var i = 0; i < origs.length; i++) {
    var cod = String((origs[i] && origs[i].codigo) || '').trim().toLowerCase();
    if (cod && s === cod) return cod;
  }
  if (/brevo|email|newsletter/.test(s)) return 'email';
  if (/insta|ig|facebook|meta/.test(s)) return 'instagram';
  if (/whats|wpp|zap/.test(s)) return 'whatsapp';
  return s ? 'outro' : 'direto';
}
function canaisPermitidos_(cp) { return String(cp.canais || '').toLowerCase(); }

function config_(c) {
  var cp = lerCampanha_(c.campanha), sit = situacao_(cp);
  if (!cp) return { ok: true, situacao: sit };
  return { ok: true, situacao: sit, titulo: cp.titulo, texto: cp.texto, nome: cp.nome, fim: dataISO_(cp.fim),
    premios: cp.premios.filter(function (p) { return p.tipo !== 'Sem prêmio'; }).map(function (p) { return p.rotulo; }) };
}

function abriu_(c) {
  var cp = lerCampanha_(c.campanha); if (!cp) return { ok: true };
  SpreadsheetApp.openById(PLANILHA).getSheetByName(ABA_EV)
    .appendRow([agora_(), cp.campanha, canal_(c, cp), 'abriu', limpa_(c.utm_medium), limpa_(c.utm_content)]);
  return { ok: true };
}

// ----------------------------------------------------------------------------- sorteio
function jogar_(c) {
  var email = String(c.email || '').trim().toLowerCase();
  if (!/^[^\s@]+@[^\s@]+\.[a-z]{2,}$/i.test(email) || email.length > 120) return { ok: false, erro: 'email', detalhe: 'Confira o email digitado.' };
  var cp = lerCampanha_(c.campanha), sit = situacao_(cp);
  if (sit !== 'aberta' && sit !== 'teste') return { ok: false, erro: sit, detalhe: 'Essa raspadinha não está valendo agora.' };
  var canal = canal_(c, cp), permitidos = canaisPermitidos_(cp);
  if ((canal === 'email' && permitidos.indexOf('email') < 0) || (canal === 'instagram' && permitidos.indexOf('instagram') < 0) || (canal === 'whatsapp' && permitidos.indexOf('whatsapp') < 0))
    return { ok: false, erro: 'canal', detalhe: 'Essa raspadinha não está valendo por aqui.' };

  var trava = LockService.getScriptLock();
  trava.waitLock(20000);
  try {
    var ss = SpreadsheetApp.openById(PLANILHA), jog = ss.getSheetByName(ABA_JOG);
    var v = jog.getDataRange().getDisplayValues(), cab = v[0], ci = function (k) { return cab.indexOf(k); };
    var saidos = {};
    for (var i = 1; i < v.length; i++) {
      if (String(v[i][ci('campanha')]) !== cp.campanha) continue;
      var st = String(v[i][ci('cupom_status')]);
      if (sit === 'aberta' && st === 'teste') continue;   // jogada de quando a campanha era teste: não vale mais
      if (String(v[i][ci('email')]).toLowerCase() === email && st.indexOf('erro') !== 0) return resultado_(cp, v[i], cab, true);   // já jogou
      if (st === 'criado' || st === 'teste') saidos[v[i][ci('premio')]] = (saidos[v[i][ci('premio')]] || 0) + 1;
    }
    var clientes = emailsClientes_(ss), novo = !clientes[email];
    if (sim_(cp.so_clientes) && novo) return { ok: false, erro: 'so_clientes', detalhe: 'Essa raspadinha é só para quem já comprou na Loja Monstro. Confira se é o mesmo email das suas compras.' };

    var p = sortear_(cp, saidos);
    var validade = Math.max(1, parseInt(cp.validade_dias, 10) || 7);
    var ate = Utilities.formatDate(new Date(Date.now() + validade * 864e5), FUSO, 'yyyy-MM-dd');
    var cupom = '', status = 'sem prêmio', cupomId = '';
    if (p.tipo !== 'Sem prêmio') {
      if (situacao_(cp) === 'teste') { cupom = 'TESTE' + codigo_(4); status = 'teste'; }
      else {
        var tent = 0;
        do { cupom = (String(cp.prefixo || 'RASPA').toUpperCase().replace(/[^A-Z0-9]/g, '') || 'RASPA') + codigo_(6);
             var criado = criarCupom_(cp, p, cupom, ate); status = criado.status; cupomId = criado.id || ''; tent++; } while (status === 'repetido' && tent < 3);
        if (status !== 'criado') {
          jog.appendRow([agora_(), cp.campanha, email, canal, limpa_(c.utm_source), limpa_(c.utm_medium), limpa_(c.utm_campaign),
            limpa_(c.utm_content), p.rotulo, p.tipo, String(p.valor || ''), cupom, ate, 'erro: ' + status, c.consentiu ? 'Sim' : 'Não', novo ? 'Sim' : 'Não', '']);
          return { ok: false, erro: 'cupom', detalhe: 'Não consegui gerar seu cupom agora. Tente de novo em alguns minutos.' };
        }
      }
    }
    var linha = [agora_(), cp.campanha, email, canal, limpa_(c.utm_source), limpa_(c.utm_medium), limpa_(c.utm_campaign),
      limpa_(c.utm_content), p.rotulo, p.tipo, String(p.valor || ''), cupom, ate, status, c.consentiu ? 'Sim' : 'Não', novo ? 'Sim' : 'Não', String(cupomId)];
    jog.appendRow(linha);
    return resultado_(cp, linha, CAB_JOG, false);
  } finally {
    trava.releaseLock();
  }
}

/**
 * Sorteia pela chance de cada prêmio. Prêmio que bateu o máximo sai do sorteio e a chance dele vai para o
 * prêmio marcado como reserva (ou o primeiro da lista). "Sem prêmio" só entra se a campanha permitir.
 */
function sortear_(cp, saidos) {
  var lista = cp.premios.filter(function (p) {
    return Number(p.chance) > 0 && (p.tipo !== 'Sem prêmio' || sim_(cp.permitir_sem_premio));
  });
  if (!lista.length) throw new Error('campanha sem prêmios');
  var reserva = lista.filter(function (p) { return sim_(p.reserva) && p.tipo !== 'Sem prêmio'; })[0] ||
                lista.filter(function (p) { return p.tipo !== 'Sem prêmio'; })[0] || lista[0];
  var pesos = lista.map(function (p) {
    var max = String(p.maximo === undefined ? '' : p.maximo).trim();
    var esgotado = max !== '' && (saidos[p.rotulo] || 0) >= Number(max);
    return { p: p, peso: esgotado ? 0 : Number(p.chance), esgotado: esgotado };
  });
  var sobra = 0; pesos.forEach(function (x) { if (x.esgotado) sobra += Number(x.p.chance); });
  var temReserva = pesos.filter(function (x) { return x.p === reserva && !x.esgotado; })[0];
  if (temReserva) temReserva.peso += sobra;
  var total = pesos.reduce(function (s, x) { return s + x.peso; }, 0);
  if (total <= 0) return reserva;   // tudo esgotado: fica a reserva
  var r = sorteio_() * total;
  for (var i = 0; i < pesos.length; i++) { r -= pesos[i].peso; if (r < 0) return pesos[i].p; }
  return pesos[pesos.length - 1].p;
}
function sorteio_() {   // número aleatório forte (não dá para prever pelo relógio)
  var b = Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, Utilities.getUuid() + Math.random() + Date.now());
  var n = 0; for (var i = 0; i < 6; i++) n = n * 256 + (b[i] & 255);
  return n / Math.pow(256, 6);
}
function codigo_(n) {
  var s = '', b = Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, Utilities.getUuid() + Math.random());
  for (var i = 0; i < n; i++) s += ALFABETO.charAt((b[i] & 255) % ALFABETO.length);
  return s;
}

/** Cria o cupom na Nuvemshop. Devolve {status, id}: status 'criado', 'repetido' ou a descrição do erro (sem o token). */
function criarCupom_(cp, p, codigo, ate) {
  var pr = PropertiesService.getScriptProperties();
  var loja = pr.getProperty('NUVEMSHOP_STORE_ID'), token = pr.getProperty('NUVEMSHOP_TOKEN');
  if (!loja || !token) return { status: 'faltam as propriedades da Nuvemshop' };
  var tipo = p.tipo === 'Frete grátis' ? 'shipping' : p.tipo === 'Valor em R$' ? 'absolute' : 'percentage';
  var corpo = { code: codigo, type: tipo, max_uses: 1, valid: true, start_date: hoje_(), end_date: ate,
    combines_with_other_discounts: sim_(cp.cumulativo), includes_shipping: false };
  if (tipo !== 'shipping') corpo.value = Number(p.valor).toFixed(2);
  var minimo = Number(String(cp.pedido_minimo || '0').replace(',', '.'));
  if (minimo > 0) corpo.min_price = Math.round(minimo * 100) / 100;
  for (var t = 1; t <= 3; t++) {
    var r = UrlFetchApp.fetch('https://api.nuvemshop.com.br/' + API_VERSAO + '/' + loja + '/coupons', {
      method: 'post', contentType: 'application/json', payload: JSON.stringify(corpo), muteHttpExceptions: true,
      headers: { Authorization: 'Bearer ' + token, 'User-Agent': pr.getProperty('NUVEMSHOP_USER_AGENT') || 'Painel Monstro' } });
    var s = r.getResponseCode();
    if (s === 200 || s === 201) { var id = ''; try { id = JSON.parse(r.getContentText()).id || ''; } catch (x) {} return { status: 'criado', id: id }; }
    if (s === 422 && /code/i.test(r.getContentText())) return { status: 'repetido' };
    if (s === 429 || s >= 500) { Utilities.sleep(1500 * t); continue; }
    return { status: 'Nuvemshop respondeu ' + s };
  }
  return { status: 'Nuvemshop sem resposta' };
}

function emailsClientes_(ss) {
  var cache = CacheService.getScriptCache(), g = cache.get('rasp_clientes');
  if (g) return JSON.parse(g);
  var o = {}, a = ss.getSheetByName('clientes');
  if (a) a.getRange(2, 1, Math.max(a.getLastRow() - 1, 1), 1).getDisplayValues()
    .forEach(function (r) { var e = String(r[0]).trim().toLowerCase(); if (e) o[e] = 1; });
  try { cache.put('rasp_clientes', JSON.stringify(o), 1800); } catch (x) { /* grande demais para o cache: lê sempre */ }
  return o;
}

// ----------------------------------------------------------------------------- resposta para a página
function resultado_(cp, linha, cab, repetido) {
  var o = {}; cab.forEach(function (k, j) { o[k] = linha[j]; });
  var sem = o.tipo === 'Sem prêmio', s = selo_(o.tipo, o.valor, o.premio);
  var ate = String(o.valido_ate || ''), br = ate ? ate.slice(8, 10) + '/' + ate.slice(5, 7) : '';
  var minimo = Number(String(cp.pedido_minimo || '0').replace(',', '.'));
  return { ok: true, repetido: repetido, sem_premio: sem, grande: s[0], pequeno: s[1],
    texto: sem ? '' : o.tipo === 'Frete grátis' ? 'frete grátis' : (o.tipo === 'Valor em R$' ? 'R$ ' + o.valor + ' de desconto' : o.valor + '% de desconto'),
    cupom: o.cupom, ate: ate, ate_br: br, minimo: minimo > 0 ? minimo : 0, teste: o.cupom_status === 'teste',
    texto_sem_premio: cp.texto_sem_premio || 'Não foi dessa vez.' };
}
function selo_(tipo, valor, rotulo) {
  if (tipo === 'Sem prêmio') return ['OPS', 'NÃO FOI'];
  if (tipo === 'Frete grátis') return ['FRETE', 'GRÁTIS'];
  if (tipo === 'Valor em R$') return ['R$' + valor, 'DE DESCONTO'];
  return [String(valor).replace('.', ',') + '%', 'DE DESCONTO'];
}
function agora_() { return Utilities.formatDate(new Date(), FUSO, 'yyyy-MM-dd HH:mm:ss'); }
function limpa_(v) { return String(v || '').replace(/[^\w\-.]/g, '').slice(0, 60); }
function json_(o) { return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON); }

// ----------------------------------------------------------------------------- cancelar cupons (D-074)
/** Rode uma vez: processarCancelamentos a cada 5 minutos (sem duplicar o gatilho). */
function instalarGatilhoCancelamentos() {
  ScriptApp.getProjectTriggers().forEach(function (g) {
    if (g.getHandlerFunction() === 'processarCancelamentos') ScriptApp.deleteTrigger(g);
  });
  ScriptApp.newTrigger('processarCancelamentos').timeBased().everyMinutes(5).create();
  Logger.log('Pronto: cancelamentos conferidos a cada 5 minutos.');
}

/** Desativa na Nuvemshop os cupons marcados "cancelar" pelo Painel e grava o resultado. */
function processarCancelamentos() {
  var trava = LockService.getScriptLock();
  if (!trava.tryLock(20000)) return;
  try {
    var jog = SpreadsheetApp.openById(PLANILHA).getSheetByName(ABA_JOG);
    var v = jog.getDataRange().getDisplayValues(), cab = v[0];
    var iSt = cab.indexOf('cupom_status'), iCod = cab.indexOf('cupom'), iId = cab.indexOf('cupom_id');
    if (iSt < 0) return;
    var feitos = 0, inicio = Date.now();
    for (var i = 1; i < v.length; i++) {
      if (String(v[i][iSt]).trim() !== 'cancelar') continue;
      if (Date.now() - inicio > 240000) break;   // o resto fica para a próxima rodada
      var codigo = String(v[i][iCod]).trim(), id = iId >= 0 ? String(v[i][iId] || '').trim() : '';
      var r = desativarCupom_(codigo, id);
      jog.getRange(i + 1, iSt + 1).setValue(r.status);
      if (iId >= 0 && r.id && !id) jog.getRange(i + 1, iId + 1).setValue(String(r.id));
      feitos++;
    }
    if (feitos) Logger.log(feitos + ' cupom(ns) processado(s).');
  } finally {
    trava.releaseLock();
  }
}

function nuvem_(metodo, caminho, corpo) {
  var pr = PropertiesService.getScriptProperties();
  var loja = pr.getProperty('NUVEMSHOP_STORE_ID'), token = pr.getProperty('NUVEMSHOP_TOKEN');
  var op = { method: metodo, muteHttpExceptions: true, contentType: 'application/json',
    headers: { Authorization: 'Bearer ' + token, 'User-Agent': pr.getProperty('NUVEMSHOP_USER_AGENT') || 'Painel Monstro' } };
  if (corpo) op.payload = JSON.stringify(corpo);
  for (var t = 1; t <= 3; t++) {
    var r = UrlFetchApp.fetch('https://api.nuvemshop.com.br/' + API_VERSAO + '/' + loja + caminho, op);
    if (r.getResponseCode() === 429 || r.getResponseCode() >= 500) { Utilities.sleep(1500 * t); continue; }
    return r;
  }
  return r;
}

/** Acha o id do cupom pelo código (cupons antigos não guardaram o id). */
function buscarCupomId_(codigo) {
  var alvo = codigo.toUpperCase();
  var r = nuvem_('get', '/coupons?q=' + encodeURIComponent(codigo) + '&per_page=50');
  if (r.getResponseCode() === 200) {
    var lista = JSON.parse(r.getContentText() || '[]');
    for (var i = 0; i < lista.length; i++) if (String(lista[i].code).toUpperCase() === alvo) return lista[i].id;
  }
  for (var p = 1; p <= 30; p++) {   // sem busca: percorre as páginas, das mais novas para as mais velhas
    r = nuvem_('get', '/coupons?per_page=200&page=' + p);
    if (r.getResponseCode() !== 200) return null;
    var pagina = JSON.parse(r.getContentText() || '[]');
    for (var j = 0; j < pagina.length; j++) if (String(pagina[j].code).toUpperCase() === alvo) return pagina[j].id;
    if (pagina.length < 200) return null;
  }
  return null;
}

/** Desativa o cupom (valid = false). Se a Nuvemshop não aceitar, apaga. Devolve {status, id}. */
function desativarCupom_(codigo, id) {
  var pr = PropertiesService.getScriptProperties();
  if (!pr.getProperty('NUVEMSHOP_STORE_ID') || !pr.getProperty('NUVEMSHOP_TOKEN')) return { status: 'erro ao cancelar: faltam as propriedades da Nuvemshop' };
  if (!id) id = buscarCupomId_(codigo);
  if (!id) return { status: 'cancelado (não existe na loja)' };
  var r = nuvem_('put', '/coupons/' + id, { valid: false });
  if (r.getResponseCode() === 200) {
    var ok = true; try { ok = JSON.parse(r.getContentText()).valid === false; } catch (x) {}
    if (ok) return { status: 'cancelado ' + hoje_(), id: id };
  }
  if (r.getResponseCode() === 404) return { status: 'cancelado (não existe na loja)', id: id };
  var d = nuvem_('delete', '/coupons/' + id);
  if (d.getResponseCode() === 200 || d.getResponseCode() === 204 || d.getResponseCode() === 404) return { status: 'cancelado ' + hoje_() + ' (apagado)', id: id };
  return { status: 'erro ao cancelar: Nuvemshop respondeu ' + r.getResponseCode() + '/' + d.getResponseCode(), id: id };
}

/** Teste à mão: mostra 1.000 sorteios da campanha de teste sem criar nada. */
function simularSorteio() {
  var cp = lerCampanha_('teste-raspadinha'), cont = {}, saidos = {};
  for (var i = 0; i < 1000; i++) { var p = sortear_(cp, saidos); cont[p.rotulo] = (cont[p.rotulo] || 0) + 1; saidos[p.rotulo] = (saidos[p.rotulo] || 0) + 1; }
  Logger.log(JSON.stringify(cont));
}
