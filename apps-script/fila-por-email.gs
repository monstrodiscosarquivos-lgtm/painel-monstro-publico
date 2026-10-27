/**
 * Fila de WhatsApp por email e alerta de rotina parada. Fica DENTRO da Planilha Google
 * (Extensões > Apps Script). Não usa senha nem chave: roda na conta do Túlio.
 *
 * O que faz, a cada hora (um agendamento só):
 *  1. Fila: às 10h e às 17h dos "Dias da fila" (aba Configuração) manda por email as linhas com
 *     Situação = "Contatar". Se um envio não saiu na hora, o próximo ciclo manda com "(atrasada)" no
 *     assunto. Cada horário do dia é enviado uma única vez, nunca em duplicata. Nas segundas, junto
 *     vai o resumo da semana (aba resumo_semana).
 *  2. Resumo: toda segunda a partir das 8h manda o resumo da semana (aba resumo_email, montada pelo
 *     Painel) para os endereços do campo "Emails do resumo" da aba Configuração. Uma vez por segunda;
 *     se não saiu às 8h, sai na hora seguinte com "(atrasado)".
 *  3. Alerta do Brevo: se a aba `rodada` mostra brevo_status "erro..." (chave inválida ou bloqueio de IP), manda o mesmo
 *     email de alerta, no máximo um por dia para cada tipo de erro.
 *  4. Alerta: se a aba `rodada` mostra que nenhuma rodada do Painel deu certo há mais de 3 horas
 *     (parâmetro "Horas sem rodada para alertar"), manda um email de alerta para o endereço da linha
 *     "Email de alerta (rotina parada)" da aba Configuração. Um alerta por parada, sem repetir.
 *
 * Ao marcar Enviei agora, registra contador, data/hora e status com uma única marcação.
 * Não envia nada ao cliente: o WhatsApp é sempre enviado por uma pessoa.
 * Funções para rodar à mão: instalar, desinstalar, enviarAgora, enviarResumoAgora, testarAlerta.
 */

var HORARIOS = [10, 17];            // padrão; vale a linha "Horários da fila" da aba Configuração (ex.: "10h, 13h e 17h")
var FUSO = 'America/Sao_Paulo';
var ABA_FILA = 'Fila';
var ABA_CONFIG = 'Configuração';
var ABA_RODADA = 'rodada';
var ABA_SEMANA = 'resumo_semana';
var ABA_ATUAL = 'atual';
var ABA_RESUMO = 'resumo_email';
var HORA_DO_RESUMO = 8;   // segunda, 8h (Brasília)
var AVISO_NAO_MARCADA = 'Estava na fila de ontem';

/** Visualizações pessoais: alternar não muda a tela de outra pessoa. */
function onOpen() {
  SpreadsheetApp.getUi().createMenu('Fila Monstro')
    .addItem('Para enviar', 'verParaEnviar')
    .addItem('Acompanhar respostas', 'verAcompanhar')
    .addItem('Histórico e busca de cliente', 'verHistorico').addToUi();
}
function verParaEnviar() { abrirVisaoFila_(101001, 'Para enviar'); }
function verAcompanhar() { abrirVisaoFila_(101002, 'Acompanhar respostas'); }
function verHistorico() { abrirVisaoFila_(101003, 'Histórico: use Ctrl + F para buscar nome ou telefone'); }
function abrirVisaoFila_(id, titulo) {
  var ss = SpreadsheetApp.getActiveSpreadsheet(), aba = ss.getSheetByName(ABA_FILA);
  var url = ss.getUrl().split('#')[0] + '#gid=' + aba.getSheetId() + '&fvid=' + id;
  SpreadsheetApp.getUi().showModalDialog(HtmlService.createHtmlOutput(
    '<p><a target="_blank" href="' + url + '">Abrir ' + titulo + '</a></p>' +
    '<p>Na lista, use Ctrl + F para procurar nome ou telefone. A visualização é pessoal.</p>'), 'Fila Monstro');
}

/** Gatilho simples da planilha: só registra aumento de um contador editado individualmente. */
function onEdit(e) {
  if (!e || !e.range) return;
  var r = e.range;
  if (r.getNumRows() !== 1 || r.getNumColumns() !== 1 || r.getRow() < 2) return;
  var aba = r.getSheet();
  if (aba.getName() !== ABA_FILA) return;
  var cab = aba.getRange(1, 1, 1, aba.getLastColumn()).getValues()[0];
  var toques = cab.indexOf('Toques já enviados') + 1;
  var data = cab.indexOf('Último envio em') + 1;
  var envio = cab.indexOf('Enviei agora') + 1;
  var acoes = {'Respondeu agora': 'Respondeu', 'Contato inválido agora': 'Contato inválido', 'Não quer agora': 'Não quer'};
  for (var nome in acoes) {
    if (r.getColumn() === cab.indexOf(nome) + 1) {
      registrarResposta_(e, cab, acoes[nome]);
      return;
    }
  }
  if (envio && r.getColumn() === envio) {
    registrarEnvio_(e, cab);
    return;
  }
  if (!toques || !data || r.getColumn() !== toques) return;
  function contador(v) {
    if (v === undefined || v === null || String(v).trim() === '') return 0;
    var s = String(v).trim();
    return /^\d+$/.test(s) ? Number(s) : NaN;
  }
  var antes = contador(e.oldValue);
  var depois = contador(e.value);
  // A edição pode já ter mudado outra vez antes deste evento ser processado.
  if (!isFinite(antes) || !isFinite(depois) || depois <= antes || contador(r.getValue()) !== depois) return;
  aba.getRange(r.getRow(), data).setValue(Utilities.formatDate(new Date(), FUSO, 'yyyy-MM-dd HH:mm'));
}

/** Marca um resultado humano sem contar outro envio e sem apagar histórico. */
function registrarResposta_(e, cab, novo) {
  if (String(e.value).toUpperCase() !== 'TRUE' || String(e.oldValue).toUpperCase() === 'TRUE') return;
  var trava = LockService.getDocumentLock();
  trava.waitLock(5000);
  try {
    var r = e.range, aba = r.getSheet(), linha = r.getRow();
    if (r.getValue() !== true) return;
    var status = cab.indexOf('Status') + 1, situacao = cab.indexOf('Situação') + 1;
    var id = cab.indexOf('Carrinho') + 1, rec = cab.indexOf('Recuperado') + 1;
    if (!id || !status || !situacao || !aba.getRange(linha, id).getValue()) {
      r.setNote('Registro não realizado: linha sem identificação ou cabeçalhos inválidos.');
      r.setValue(false); return;
    }
    var anterior = String(aba.getRange(linha, status).getValue() || '');
    // Não desfaz compra reconhecida nem recusa anterior com um clique em Respondeu.
    if (novo === 'Respondeu' && (['Não quer', 'Contato inválido', 'Recuperado'].indexOf(anterior) >= 0 ||
        (rec && aba.getRange(linha, rec).getValue() === 'Sim'))) {
      r.setNote('Resposta não registrada: ciclo encerrado. Revise o Status se foi uma correção.');
      r.setValue(false); return;
    }
    aba.getRange(linha, status).setValue(novo);
    aba.getRange(linha, situacao).setValue(novo === 'Respondeu' ? 'Em conversa' :
      (novo === 'Contato inválido' ? 'Encerrado: contato inválido' : 'Encerrado: bloqueado'));
    r.setValue(false);
    r.setNote(novo + ' registrado. Contador e data do envio preservados.');
  } finally { trava.releaseLock(); }
}

/** Uma marcação depois do envio real. Escrita por script não dispara onEdit novamente. */
function registrarEnvio_(e, cab) {
  if (String(e.value).toUpperCase() !== 'TRUE' || String(e.oldValue).toUpperCase() === 'TRUE') return;
  var trava = LockService.getDocumentLock();
  trava.waitLock(5000);
  try {
    var r = e.range, aba = r.getSheet(), linha = r.getRow();
    if (r.getValue() !== true) return; // evento duplicado ou caixa já desmarcada
    var toques = cab.indexOf('Toques já enviados') + 1;
    var data = cab.indexOf('Último envio em') + 1;
    var status = cab.indexOf('Status') + 1;
    var situacao = cab.indexOf('Situação') + 1;
    if (!toques || data !== toques + 1 || status !== data + 1 || !situacao) {
      r.setNote('Cabeçalhos da Fila diferentes do modelo. Registro não realizado.');
      r.setValue(false);
      return;
    }
    var s = String(aba.getRange(linha, status).getValue() || '').trim();
    var sit = String(aba.getRange(linha, situacao).getValue() || '').trim();
    if (['Não quer', 'Contato inválido', 'Recuperado'].indexOf(s) >= 0 || sit !== 'Contatar') {
      r.setNote('Registro não realizado: esta linha não está liberada para contato.');
      r.setValue(false);
      return;
    }
    var texto = String(aba.getRange(linha, toques).getValue() || '').trim();
    var n = texto === '' ? 0 : (/^\d+$/.test(texto) ? Number(texto) : NaN);
    if (!isFinite(n)) {
      r.setNote('Registro não realizado: contador de envios inválido.');
      r.setValue(false);
      return;
    }
    aba.getRange(linha, toques, 1, 3).setValues([[n + 1, Utilities.formatDate(new Date(), FUSO, 'yyyy-MM-dd HH:mm'),
      s === 'Respondeu' ? s : 'Em andamento']]);
    aba.getRange(linha, situacao).setValue('Envio registrado');
    r.setValue(false);
    r.setNote('Envio registrado. Não marque novamente para a mesma mensagem.');
  } finally {
    trava.releaseLock();
  }
}

/** Rode UMA vez: cria o agendamento de hora em hora. Rodar de novo não duplica. */
function instalar() {
  removerAgendamentos_();
  ScriptApp.newTrigger('cadaHora').timeBased().everyHours(1).create();
  // Não manda como "atrasada" o que já passou do horário antes da instalação.
  var hora = Number(Utilities.formatDate(new Date(), FUSO, 'H'));
  horariosDaFila_(lerConfig_()).forEach(function (h) { if (h <= hora) marcarEnviado_(h); });
  Logger.log('Pronto: verificação de hora em hora. Fuso do script: ' + Session.getScriptTimeZone() +
    ' (a fila usa sempre o horário de Brasília).');
}

/** Rode para parar tudo. */
function desinstalar() {
  removerAgendamentos_();
  Logger.log('Agendamento removido.');
}

/** Teste: manda a fila agora, ignorando horário e "já enviado", sem marcar nada como enviado. */
function enviarAgora() {
  enviarFila_({ forcar: true });
}

/** Teste: manda o resumo da semana agora, para quem está em "Emails do resumo". */
function enviarResumoAgora() {
  enviarResumo_({ forcar: true });
}

/** Teste: manda o aviso da newsletter agora, com o que estiver na aba newsletter_aviso. */
function enviarNewsletterAgora() {
  enviarNewsletter_({ forcar: true });
}

/** Teste: manda um alerta de exemplo para o destinatário configurado. */
function testarAlerta() {
  var config = lerConfig_();
  enviar_(destinatarios_(config['Email de alerta (rotina parada)']), 'Painel Monstro: teste do alerta',
    '<p>Este é um teste do alerta de rotina parada. Se chegou, o alerta está funcionando.</p>');
}

/** Chamada de hora em hora pelo agendamento. */
function cadaHora() {
  try { verificarRodada_(); } catch (e) { Logger.log('Erro no alerta: ' + e); }
  try { verificarBrevo_(); } catch (e) { Logger.log('Erro no alerta do Brevo: ' + e); }
  try { enviarResumo_({ forcar: false }); } catch (e) { Logger.log('Não consegui enviar o resumo agora: ' + e); }
  try { enviarNewsletter_({ forcar: false }); } catch (e) { Logger.log('Não consegui enviar o aviso da newsletter: ' + e); }
  var config = lerConfig_();
  var hoje = new Date();
  var diaDaSemana = Number(Utilities.formatDate(hoje, FUSO, 'u')) - 1;   // 0 = segunda
  if (diasDaFila_(config['Dias da fila']).indexOf(diaDaSemana) < 0) {
    Logger.log('Hoje não é dia de fila; o pendente passa para o próximo dia de fila.');
    return;
  }
  try {
    enviarFila_({ forcar: false });
  } catch (e) {
    // Não marcou como enviado: a próxima hora tenta de novo e sai como "(atrasada)".
    Logger.log('Não consegui enviar a fila agora: ' + e);
  }
}

// ---------------------------------------------------------------- fila

function enviarFila_(opcoes) {
  var agora = new Date();
  var hora = Number(Utilities.formatDate(agora, FUSO, 'H'));
  var hoje = Utilities.formatDate(agora, FUSO, 'yyyy-MM-dd');
  var config = lerConfig_();
  var horarios = horariosDaFila_(config);
  var devidos = opcoes.forcar ? horarios.slice() : horarios.filter(function (h) { return h <= hora && !jaEnviado_(h); });
  if (!devidos.length) return;
  var atrasada = !opcoes.forcar && devidos.some(function (h) { return h < hora; });

  var destinos = destinatarios_(config['Emails que recebem a fila']);
  var limite = Number(config['Limite de mensagens por dia']) || 40;
  var ordem = String(config['Ordem de prioridade da fila'] || 'Carrinho, Garimpo, VIP, 45 dias')
    .split(',').map(function (x) { return x.trim(); });
  var segunda = Number(Utilities.formatDate(agora, FUSO, 'u')) === 1;

  var linhas = lerFila_().filter(function (l) { return l['Situação'] === 'Contatar'; });
  linhas.sort(function (a, b) {
    var ra = ordem.indexOf(String(a['Origem'] || 'Carrinho')), rb = ordem.indexOf(String(b['Origem'] || 'Carrinho'));
    ra = ra < 0 ? 99 : ra; rb = rb < 0 ? 99 : rb;
    if (ra !== rb) return ra - rb;
    return String(a['Abandonado em']).localeCompare(String(b['Abandonado em']));   // mais antigos primeiro
  });
  var total = linhas.length;
  linhas = linhas.slice(0, limite);
  var resumoSemana = segunda ? lerResumoSemana_() : null;

  if (!total && !resumoSemana) {
    Logger.log('Nenhum carrinho ou contato para hoje; nada enviado.');
    if (!opcoes.forcar) devidos.forEach(marcarEnviado_);
    return;
  }
  var horaTexto = Utilities.formatDate(agora, FUSO, 'HH:mm');
  var assunto = 'Fila de WhatsApp (' + horaTexto + '): ' + total + ' para contatar' + (atrasada ? ' (atrasada)' : '');
  var html = montarHtml_(linhas, total, limite, resumoSemana, atrasada, dadosDe_());
  enviar_(destinos, assunto, html);
  if (!opcoes.forcar) devidos.forEach(marcarEnviado_);   // só marca depois que o envio deu certo
  Logger.log('Fila enviada: ' + linhas.length + ' de ' + total + ' linhas' + (atrasada ? ' (atrasada)' : '') + '.');
}

/** Rótulo humano do modelo, igual ao do painel. Código que não é T1/T2 e não está na lista aparece como veio. */
function rotuloModelo_(codigo) {
  var c = String(codigo || '').trim();
  if (!c) return '';
  var u = c.toUpperCase();
  var fixos = { 'T2_FRETE': 'Frete grátis', 'T3_CUPOM': '10% nos discos (oferta final)', 'ESGOTADO': 'Estoque alterado',
    'ALERTA_GARIMPO': 'Aviso de garimpo', 'G45': 'Garimpo de 45 dias', 'VIP': 'VIP' };
  if (fixos[u]) return fixos[u];
  if (/^T[12]($|_)/.test(u)) return 'Lembrete';
  return c;
}

function jaEnviado_(hora) {
  var chave = 'enviado:' + Utilities.formatDate(new Date(), FUSO, 'yyyy-MM-dd') + ':' + hora;
  return PropertiesService.getScriptProperties().getProperty(chave) === '1';
}

function marcarEnviado_(hora) {
  var chave = 'enviado:' + Utilities.formatDate(new Date(), FUSO, 'yyyy-MM-dd') + ':' + hora;
  PropertiesService.getScriptProperties().setProperty(chave, '1');
}

// ---------------------------------------------------------------- resumo da segunda

function enviarResumo_(opcoes) {
  var agora = new Date();
  var hora = Number(Utilities.formatDate(agora, FUSO, 'H'));
  var hoje = Utilities.formatDate(agora, FUSO, 'yyyy-MM-dd');
  var segunda = Number(Utilities.formatDate(agora, FUSO, 'u')) === 1;
  var chave = 'resumo:' + hoje;
  var props = PropertiesService.getScriptProperties();
  if (!opcoes.forcar) {
    if (!segunda || hora < HORA_DO_RESUMO || props.getProperty(chave) === '1') return;
  }
  var aba = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(ABA_RESUMO);
  if (!aba || aba.getLastRow() < 2) { Logger.log('A aba resumo_email ainda não existe; nada enviado.'); return; }
  var assunto = String(aba.getRange(2, 1).getValue());
  var html = String(aba.getRange(2, 2).getValue());
  var atrasado = !opcoes.forcar && hora > HORA_DO_RESUMO;
  var config = lerConfig_();
  enviar_(destinatarios_(config['Emails do resumo']), assunto + (atrasado ? ' (atrasado)' : ''), html);
  if (!opcoes.forcar) props.setProperty(chave, '1');   // só marca depois que o envio deu certo
  Logger.log('Resumo enviado' + (atrasado ? ' (atrasado)' : '') + '.');
}

// ---------------------------------------------------------------- aviso da newsletter (quarta)

/** O Painel monta a aba newsletter_aviso (assunto e texto) na quarta, a partir das 17h. Aqui só manda, uma vez. */
function enviarNewsletter_(opcoes) {
  var aba = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('newsletter_aviso');
  if (!aba || aba.getLastRow() < 2) return;
  var celula = aba.getRange(2, 1).getValue();
  // O Painel grava texto "AAAA-MM-DD HH:mm"; se a planilha converteu para data, formata de volta no horário de Brasília
  var geradoEm = (celula && typeof celula.getTime === 'function') ? Utilities.formatDate(celula, FUSO, 'yyyy-MM-dd HH:mm') : String(celula).trim();
  var hoje = Utilities.formatDate(new Date(), FUSO, 'yyyy-MM-dd');
  var props = PropertiesService.getScriptProperties();
  var chave = 'newsletter:' + geradoEm;
  if (!opcoes.forcar) {
    if (geradoEm.slice(0, 10) !== hoje || props.getProperty(chave) === '1') return;
  }
  var assunto = String(aba.getRange(2, 3).getValue());
  var html = String(aba.getRange(2, 4).getValue());
  enviar_(destinatarios_(lerConfig_()['Emails do resumo']), assunto, html);
  if (!opcoes.forcar) props.setProperty(chave, '1');   // só marca depois que o envio deu certo
  Logger.log('Aviso da newsletter enviado.');
}

// ---------------------------------------------------------------- alerta de rotina parada

function verificarBrevo_() {
  var aba = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(ABA_RODADA);
  if (!aba || aba.getLastRow() < 2) return;
  var cab = aba.getRange(1, 1, 1, aba.getLastColumn()).getValues()[0].map(String);
  var linha = aba.getRange(2, 1, 1, aba.getLastColumn()).getValues()[0];
  var status = String(linha[cab.indexOf('brevo_status')] || '');
  if (status.indexOf('erro') !== 0) return;
  var detalhe = String(linha[cab.indexOf('brevo_detalhe')] || '');
  var ultimaBoa = String(linha[cab.indexOf('brevo_ultima_leitura_ok')] || '');
  var props = PropertiesService.getScriptProperties();
  var chave = 'alertabrevo:' + status + ':' + Utilities.formatDate(new Date(), FUSO, 'yyyy-MM-dd');
  if (props.getProperty(chave) === '1') return;   // no máximo um aviso por dia para cada tipo de erro
  var ajuda = status.indexOf('bloqueio_ip') >= 0
    ? 'No Brevo, abra o menu da conta, Segurança, Endereços IP autorizados, e desative o bloqueio de IP para chaves de API. O GitHub roda de endereços que mudam.'
    : (status.indexOf('chave_invalida') >= 0
      ? 'A chave foi recusada. No Brevo, crie uma chave nova (SMTP e API, Chaves de API) e troque o segredo BREVO_API_KEY no GitHub e no arquivo .env.'
      : 'Veja o detalhe abaixo e a aba Actions do GitHub.');
  var html = '<div style="font-family:Arial,sans-serif;font-size:14px">' +
    '<p><b>O Painel não consegue falar com o Brevo.</b></p>' +
    '<p>Situação: <b>' + esc_(status) + '</b>' + (detalhe ? ' (' + esc_(detalhe) + ')' : '') + '</p>' +
    '<p>' + esc_(ajuda) + '</p>' +
    (ultimaBoa ? '<p>Última chamada que deu certo: ' + esc_(ultimaBoa) + '. O Brevo desativa a chave depois de 90 dias sem uma chamada bem-sucedida.</p>' : '') +
    '<p>Nenhuma mensagem é enviada por causa disso; só a atualização da régua no Brevo fica parada.</p></div>';
  enviar_(destinatarios_(lerConfig_()['Email de alerta (rotina parada)']), 'ALERTA Painel Monstro: problema com o Brevo', html);
  props.setProperty(chave, '1');
}

function verificarRodada_() {
  var aba = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(ABA_RODADA);
  if (!aba || aba.getLastRow() < 2) return;
  var texto = String(aba.getRange(2, 1).getDisplayValue()).trim();   // "AAAA-MM-DD HH:mm" (Brasília)
  if (!texto) return;
  var ultima = Utilities.parseDate(texto, FUSO, 'yyyy-MM-dd HH:mm');
  var config = lerConfig_();
  var limiteHoras = Number(config['Horas sem rodada para alertar']) || 3;
  var horasParado = (new Date().getTime() - ultima.getTime()) / 3600000;
  if (horasParado < limiteHoras) return;
  var props = PropertiesService.getScriptProperties();
  var chave = 'alerta:' + texto;
  if (props.getProperty(chave) === '1') return;   // já avisei dessa parada
  var html = '<div style="font-family:Arial,sans-serif;font-size:14px">' +
    '<p><b>A rotina do Painel Monstro está parada.</b></p>' +
    '<p>A última rodada que deu certo foi em <b>' + esc_(texto) + '</b> (há cerca de ' + Math.floor(horasParado) + ' horas).</p>' +
    '<p>O que fazer: abra a aba <b>Actions</b> do repositório no GitHub, clique em <b>Rotina do Painel</b> e veja o erro da última execução. ' +
    'Os dados já baixados não se perdem e a fila continua como estava; ela se atualiza sozinha quando a rotina voltar.</p>' +
    '</div>';
  enviar_(destinatarios_(config['Email de alerta (rotina parada)']),
    'ALERTA Painel Monstro: sem rodada há ' + Math.floor(horasParado) + 'h', html);
  props.setProperty(chave, '1');
}

// ---------------------------------------------------------------- apoio

function removerAgendamentos_() {
  // Remove só o agendamento desta fila: o vigia do cadastro (vigia-cadastro.gs) tem o seu próprio.
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'cadaHora') ScriptApp.deleteTrigger(t);
  });
}

function enviar_(destinos, assunto, html) {
  GmailApp.sendEmail(destinos.join(','), assunto, 'Abra este email em um leitor que mostre HTML.', { htmlBody: html, name: 'Painel Monstro' });
}

function destinatarios_(texto) {
  var lista = String(texto || '').split(/[,;\s]+/).filter(function (e) { return e.indexOf('@') > 0; });
  if (!lista.length) lista = [Session.getEffectiveUser().getEmail()];   // sem destinatário: avisa o dono da planilha
  return lista;
}

function lerConfig_() {
  var aba = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(ABA_CONFIG);
  var saida = {};
  if (!aba) return saida;
  aba.getDataRange().getValues().slice(1).forEach(function (l) { if (l[0]) saida[String(l[0]).trim()] = l[1]; });
  return saida;
}

function lerFila_() {
  var aba = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(ABA_FILA);
  if (!aba) return [];
  var v = aba.getDataRange().getValues();
  if (v.length < 2) return [];
  var cab = v[0].map(String);
  return v.slice(1).filter(function (l) { return l[0] !== ''; }).map(function (l) {
    var o = {};
    cab.forEach(function (nome, i) { o[nome] = l[i]; });
    return o;
  });
}

function lerResumoSemana_() {
  var aba = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(ABA_SEMANA);
  if (!aba || aba.getLastRow() < 2) return null;
  return aba.getDataRange().getDisplayValues().slice(1).filter(function (l) { return l[0] !== ''; });
}

function dadosDe_() {
  var aba = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(ABA_RODADA);
  if (!aba || aba.getLastRow() < 2) return '';
  return String(aba.getRange(2, 1).getDisplayValue());
}

/** "10h, 13h e 17h" em [10, 13, 17]. Vazio ou ilegível: o padrão (10h e 17h). */
function horariosDaFila_(config) {
  var texto = String((config && config['Horários da fila']) || '');
  var achados = texto.match(/\d{1,2}/g) || [];
  var horas = {};
  achados.forEach(function (n) { var h = Number(n); if (h >= 0 && h <= 23) horas[h] = true; });
  var lista = Object.keys(horas).map(Number).sort(function (a, b) { return a - b; });
  return lista.length ? lista : HORARIOS.slice();
}

/** "seg a sáb", "seg, qua, sex", "todos" em números (0 = segunda). Texto ilegível: seg a sáb. */
function diasDaFila_(texto) {
  var t = String(texto || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').trim();
  var padrao = [0, 1, 2, 3, 4, 5];
  if (!t) return padrao;
  if (t.indexOf('todo') >= 0 || t.indexOf('diari') >= 0) return [0, 1, 2, 3, 4, 5, 6];
  var nomes = ['seg', 'ter', 'qua', 'qui', 'sex', 'sab', 'dom'];
  var tokens = t.match(/seg|ter|qua|qui|sex|sab|dom|\ba\b|ate|-/g) || [];
  var dias = {}, anterior = null, intervalo = false;
  tokens.forEach(function (tk) {
    var i = nomes.indexOf(tk);
    if (i >= 0) {
      if (intervalo && anterior !== null) {
        var j = anterior;
        while (true) { dias[j] = true; if (j === i) break; j = (j + 1) % 7; }
        intervalo = false;
      } else { dias[i] = true; }
      anterior = i;
    } else { intervalo = true; }
  });
  var lista = Object.keys(dias).map(Number).sort();
  return lista.length ? lista : padrao;
}

function esc_(texto) {
  return String(texto === null || texto === undefined ? '' : texto)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/** Link do WhatsApp: usa a mensagem editada pela Mariana, se houver; senão o link pronto do Painel. */
function linkWhatsapp_(l) {
  var editada = String(l['Mensagem editada'] || '').trim();
  var telefone = String(l['Telefone'] || '').replace(/\D/g, '');
  if (editada && telefone) return 'https://wa.me/' + telefone + '?text=' + encodeURIComponent(editada);
  return String(l['Abrir WhatsApp'] || '');
}

function montarHtml_(linhas, total, limite, resumoSemana, atrasada, dadosDe) {
  var p = [];
  p.push('<div style="font-family:Arial,sans-serif;font-size:14px;color:#222">');
  if (atrasada) p.push('<p style="color:#b00"><b>Atenção: este email estava previsto para antes e saiu atrasado.</b></p>');
  if (resumoSemana) {
    p.push('<p><b>Resumo da semana</b></p><table style="border-collapse:collapse">');
    resumoSemana.forEach(function (l) {
      p.push('<tr><td style="padding:2px 12px 2px 0">' + esc_(l[0]) + '</td><td style="padding:2px 0"><b>' + esc_(l[1]) + '</b></td></tr>');
    });
    p.push('</table><hr>');
  }
  p.push('<p><b>' + total + '</b> contato(s) para fazer agora.' +
    (total > limite ? ' Mostrando os primeiros ' + limite + ' (limite do dia); o resto fica para o próximo dia de fila.' : '') + '</p>');
  if (linhas.length) {
    p.push('<table style="border-collapse:collapse;width:100%">');
    p.push('<tr style="background:#eee;text-align:left"><th style="padding:6px">Origem</th><th style="padding:6px">Cliente</th>' +
      '<th style="padding:6px">Disco(s)</th><th style="padding:6px">Toque</th><th style="padding:6px">Modelo</th><th style="padding:6px">WhatsApp</th></tr>');
    linhas.forEach(function (l) {
      var link = linkWhatsapp_(l);
      var aviso = String(l['Observações'] || '').indexOf(AVISO_NAO_MARCADA) >= 0;
      p.push('<tr style="border-bottom:1px solid #ddd' + (aviso ? ';background:#fff4e5' : '') + '">' +
        '<td style="padding:6px">' + esc_(l['Origem'] || 'Carrinho') + '</td>' +
        '<td style="padding:6px">' + esc_(l['Cliente']) + '</td>' +
        '<td style="padding:6px">' + esc_(l['Itens']) + '</td>' +
        '<td style="padding:6px">' + esc_(l['Próximo toque']) + 'º</td>' +
        '<td style="padding:6px">' + esc_(rotuloModelo_(l['Modelo usado'])) + '</td>' +
        '<td style="padding:6px">' + (link ? '<a href="' + esc_(link) + '">Abrir WhatsApp</a>' : 'sem link') +
        (aviso ? '<br><b>Estava na fila de ontem e não foi marcada: confira no WhatsApp antes de enviar</b>' : '') + '</td></tr>');
    });
    p.push('</table>');
  }
  p.push('<p>Depois de enviar, marque <b>Enviei agora</b> na linha da planilha, uma célula por vez. ' +
    'O contador, a data/hora e o status são registrados automaticamente. Não edite <b>Próximo toque</b>. ' +
    'O que não for marcado volta amanhã com aviso, no mesmo toque.</p>');
  p.push('<p style="color:#888;font-size:12px">Enviado automaticamente pelo Painel Monstro' +
    (dadosDe ? ' · dados da última rodada: ' + esc_(dadosDe) : '') + '. O WhatsApp é sempre enviado por uma pessoa.</p>');
  p.push('</div>');
  return p.join('');
}
