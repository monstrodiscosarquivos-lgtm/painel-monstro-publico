// Teste local do script da fila (sem Google): node apps-script/teste_local.js
// Simula a planilha, o relógio, o Gmail e as propriedades do script, e confere as regras:
// horários 10h e 17h, dias da fila, "(atrasada)", nunca duas vezes o mesmo email, resumo de segunda e alerta de rotina parada.
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const codigo = fs.readFileSync(path.join(__dirname, 'fila-por-email.gs'), 'utf8');

function criarAmbiente(estado) {
  // estado: { agora: ISO em UTC, abas: {nome: [[...]]}, falharEnvio: bool }
  const enviados = [];
  const props = {};
  const log = [];
  const fuso = -3 * 3600 * 1000; // Brasília (sem horário de verão)
  const baseData = Date;
  class Data extends baseData {
    constructor(...a) { if (a.length === 0) super(estado.agora); else super(...a); }
    static now() { return new baseData(estado.agora).getTime(); }
  }
  const pad = (n, t = 2) => String(n).padStart(t, '0');
  const local = (d) => new baseData(d.getTime() + fuso);
  const abas = {};
  const aba = (nome) => {
    const v = estado.abas[nome];
    if (!v) return null;
    return {
      getName: () => nome,
      getDataRange: () => ({ getValues: () => v, getDisplayValues: () => v.map((l) => l.map(String)) }),
      getLastRow: () => v.length,
      getLastColumn: () => Math.max(...v.map((l) => l.length)),
      getRange: (r, c, nl = 1, nc = 1) => ({
        getDisplayValue: () => String(v[r - 1][c - 1]), getValue: () => v[r - 1][c - 1],
        getValues: () => v.slice(r - 1, r - 1 + nl).map((l) => l.slice(c - 1, c - 1 + nc)),
        setValue: (valor) => { v[r - 1][c - 1] = valor; },
        setValues: (valores) => { valores.forEach((l, i) => l.forEach((x, j) => { v[r - 1 + i][c - 1 + j] = x; })); },
        setNote: () => {},
      }),
    };
  };
  if (estado.abas.rodada && !estado.manterRodada) {  // por padrão a última rodada foi há 30 minutos
    const l = local(new baseData(new baseData(estado.agora).getTime() - 30 * 60000));
    estado.abas.rodada[1][0] = `${pad(l.getUTCFullYear(), 4)}-${pad(l.getUTCMonth() + 1)}-${pad(l.getUTCDate())} ${pad(l.getUTCHours())}:${pad(l.getUTCMinutes())}`;
  }
  const contexto = {
    LockService: { getDocumentLock: () => ({ waitLock: () => {}, releaseLock: () => {} }) },
    console, Logger: { log: (m) => log.push(String(m)) }, Date: Data,
    SpreadsheetApp: { getActiveSpreadsheet: () => ({ getSheetByName: aba, getUrl: () => 'https://planilha.exemplo' }) },
    Session: { getScriptTimeZone: () => 'America/Sao_Paulo', getEffectiveUser: () => ({ getEmail: () => 'dono@exemplo.com' }) },
    PropertiesService: { getScriptProperties: () => ({ getProperty: (k) => (k in props ? props[k] : null), setProperty: (k, v) => { props[k] = v; } }) },
    GmailApp: { sendEmail: (para, assunto, corpo, opcoes) => {
      if (estado.falharEnvio) throw new Error('Gmail fora do ar');
      enviados.push({ para, assunto, html: opcoes.htmlBody });
    } },
    ScriptApp: { newTrigger: () => ({ timeBased: () => ({ everyHours: () => ({ create: () => {} }) }) }), getProjectTriggers: () => [], deleteTrigger: () => {} },
    Utilities: {
      formatDate: (d, tz, fmt) => {
        const l = local(d);
        const mapa = { yyyy: pad(l.getUTCFullYear(), 4), MM: pad(l.getUTCMonth() + 1), dd: pad(l.getUTCDate()), HH: pad(l.getUTCHours()),
          mm: pad(l.getUTCMinutes()), H: String(l.getUTCHours()), u: String(l.getUTCDay() === 0 ? 7 : l.getUTCDay()) };
        return fmt.replace(/yyyy|MM|dd|HH|mm|H|u/g, (m) => mapa[m]);
      },
      parseDate: (texto) => { const m = texto.match(/(\d+)-(\d+)-(\d+) (\d+):(\d+)/); return new baseData(Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]) - fuso); },
    },
  };
  vm.createContext(contexto);
  vm.runInContext(codigo, contexto);
  return { ctx: contexto, enviados, props, log };
}

function config(extra = {}) {
  const base = { 'Emails do resumo': 'tulio@exemplo.com', 'Emails que recebem a fila': 'mariana@exemplo.com, tulio@exemplo.com', 'Limite de mensagens por dia': 40,
    'Dias da fila': 'seg a sáb', 'Ordem de prioridade da fila': 'Carrinho, Garimpo, VIP, 45 dias',
    'Email de alerta (rotina parada)': 'alerta@exemplo.com', 'Horas sem rodada para alertar': 3 };
  return [['Parâmetro', 'Valor', 'O que significa']].concat(Object.entries({ ...base, ...extra }).map(([k, v]) => [k, v, '']));
}

const CAB = ['Carrinho', 'Abandonado em', 'Cliente', 'Itens', 'Telefone', 'Próximo toque', 'Situação', 'Modelo usado', 'Abrir WhatsApp',
  'Mensagem editada', 'Observações', 'Origem'];
function fila(...linhas) { return [CAB].concat(linhas); }
const linha = (id, quando, cliente, situacao, origem, obs = '') =>
  [id, quando, cliente, 'LP A', '5562999990000', 1, situacao, 'T1', 'https://wa.me/5562999990000?text=oi', '', obs, origem];

// 19/10/2026 é segunda. Brasília = UTC-3.
const utc = (texto) => new Date(texto + '-03:00').toISOString();
const abasBase = () => ({
  'Configuração': config(),
  'Fila': fila(linha(1, '2026-10-17 11:00', 'Ana', 'Contatar', 'Carrinho'), linha(2, '2026-10-12 08:00', 'Pedro', 'Contatar', 'VIP'),
    linha(3, '2026-10-18 12:00', 'Zé', 'Fica para amanhã', 'Carrinho')),
  'resumo_semana': [['indicador', 'valor'], ['Período', '13/10 a 19/10'], ['Mensagens enviadas (marcadas pela Mariana)', 12], ['Não contatados (saíram da fila sem toque)', 3]],
  'rodada': [['ultima_rodada_ok', 'duracao_s', 'dia_de_fila'], ['2026-10-19 09:40', 50, true]],
});

let n = 0;
function teste(nome, fn) { fn(); n += 1; console.log('ok  ' + nome); }

teste('manda a fila às 10h, uma vez só, com o resumo na segunda', () => {
  const e = { agora: utc('2026-10-19T10:20:00'), abas: abasBase() };
  const a = criarAmbiente(e);
  a.ctx.cadaHora();
  assert.strictEqual(a.enviados.length, 1);
  assert.ok(a.enviados[0].assunto.includes('2 para contatar') && !a.enviados[0].assunto.includes('atrasada'));
  assert.ok(a.enviados[0].html.includes('Resumo da semana') && a.enviados[0].html.includes('Não contatados'));
  assert.deepStrictEqual(a.enviados[0].para.split(','), ['mariana@exemplo.com', 'tulio@exemplo.com']);
  a.ctx.cadaHora(); a.ctx.cadaHora();                   // as rodadas seguintes da mesma hora
  assert.strictEqual(a.enviados.length, 1, 'mandou o mesmo email duas vezes');
});

teste('prioridade: carrinho antes de VIP, mais antigo primeiro', () => {
  const e = { agora: utc('2026-10-20T10:05:00'), abas: abasBase() };
  const a = criarAmbiente(e);
  a.ctx.cadaHora();
  const h = a.enviados[0].html;
  assert.ok(h.indexOf('Ana') < h.indexOf('Pedro'), 'o carrinho deve vir antes do VIP');
  assert.ok(!h.includes('Resumo da semana'), 'resumo só na segunda');
});

teste('às 11h, sem ter saído o das 10h, manda com (atrasada)', () => {
  const e = { agora: utc('2026-10-20T11:30:00'), abas: abasBase() };
  const a = criarAmbiente(e);
  a.ctx.cadaHora();
  assert.strictEqual(a.enviados.length, 1);
  assert.ok(a.enviados[0].assunto.includes('(atrasada)'));
  e.abas.rodada[1][0] = '2026-10-20 12:10'; e.agora = utc('2026-10-20T12:30:00'); a.ctx.cadaHora();
  assert.strictEqual(a.enviados.length, 1, 'não pode repetir');
});

teste('o envio que falhou é repetido na hora seguinte, atrasado', () => {
  const e = { agora: utc('2026-10-20T10:10:00'), abas: abasBase(), falharEnvio: true };
  const a = criarAmbiente(e);
  a.ctx.cadaHora();
  assert.strictEqual(a.enviados.length, 0);
  e.falharEnvio = false; e.agora = utc('2026-10-20T11:10:00'); e.abas.rodada[1][0] = '2026-10-20 10:50';
  a.ctx.cadaHora();
  assert.strictEqual(a.enviados.length, 1);
  assert.ok(a.enviados[0].assunto.includes('(atrasada)'));
});

teste('17h manda de novo (outro horário), uma vez só', () => {
  const e = { agora: utc('2026-10-20T10:10:00'), abas: abasBase() };
  const a = criarAmbiente(e);
  a.ctx.cadaHora();
  e.abas.rodada[1][0] = '2026-10-20 16:50';          // a rotina continua rodando
  e.agora = utc('2026-10-20T17:15:00'); a.ctx.cadaHora(); a.ctx.cadaHora();
  assert.strictEqual(a.enviados.length, 2);
  assert.ok(!a.enviados[1].assunto.includes('atrasada'));
});

teste('horários da fila vêm da Configuração: com 13h, o que ficou pronto de manhã sai ao meio-dia', () => {
  const abas = abasBase();
  abas['Configuração'] = config({ 'Horários da fila': '10h, 13h e 17h' });
  const e = { agora: utc('2026-10-20T10:20:00'), abas };
  const a = criarAmbiente(e);
  a.ctx.cadaHora();
  assert.strictEqual(a.enviados.length, 1);                      // 10h
  e.abas.rodada[1][0] = '2026-10-20 12:50'; e.agora = utc('2026-10-20T13:20:00');
  a.ctx.cadaHora();
  assert.strictEqual(a.enviados.length, 2, 'o horário das 13h não saiu');
  assert.ok(!a.enviados[1].assunto.includes('atrasada'));
  e.abas.rodada[1][0] = '2026-10-20 13:50'; e.agora = utc('2026-10-20T14:20:00'); a.ctx.cadaHora();
  assert.strictEqual(a.enviados.length, 2, 'não pode repetir fora dos horários');
});

teste('horários ilegíveis ou vazios voltam para 10h e 17h', () => {
  const a = criarAmbiente({ agora: utc('2026-10-20T10:00:00'), abas: abasBase() });
  assert.deepStrictEqual(Array.from(a.ctx.horariosDaFila_({ 'Horários da fila': '' })), [10, 17]);
  assert.deepStrictEqual(Array.from(a.ctx.horariosDaFila_({ 'Horários da fila': 'de manhã' })), [10, 17]);
  assert.deepStrictEqual(Array.from(a.ctx.horariosDaFila_({ 'Horários da fila': '17h, 9h e 13h' })), [9, 13, 17]);
  assert.deepStrictEqual(Array.from(a.ctx.horariosDaFila_({ 'Horários da fila': '10h e 25h' })), [10]);
});

teste('domingo não sai fila; segunda manda o pendente', () => {
  const e = { agora: utc('2026-10-18T10:10:00'), abas: abasBase() };   // domingo
  const a = criarAmbiente(e);
  a.ctx.cadaHora();
  assert.strictEqual(a.enviados.length, 0);
  e.abas.rodada[1][0] = '2026-10-19 09:50'; e.agora = utc('2026-10-19T10:10:00'); a.ctx.cadaHora();
  assert.strictEqual(a.enviados.length, 1);
  assert.ok(a.enviados[0].html.includes('Ana'));
});

teste('linha que não foi marcada aparece com o aviso', () => {
  const abas = abasBase();
  abas['Fila'][1][10] = 'Estava na fila de ontem e não foi marcada: confira no WhatsApp antes de enviar';
  const a = criarAmbiente({ agora: utc('2026-10-20T10:10:00'), abas });
  a.ctx.cadaHora();
  assert.ok(a.enviados[0].html.includes('Estava na fila de ontem e não foi marcada: confira no WhatsApp antes de enviar'));
});

teste('mensagem editada pela Mariana gera o link com o texto dela', () => {
  const abas = abasBase();
  abas['Fila'][1][9] = 'Oi, versão editada';
  const a = criarAmbiente({ agora: utc('2026-10-20T10:10:00'), abas });
  a.ctx.cadaHora();
  assert.ok(a.enviados[0].html.includes(encodeURIComponent('Oi, versão editada')));
});

teste('sem destinatário configurado avisa o dono da planilha', () => {
  const abas = abasBase();
  abas['Configuração'] = config({ 'Emails que recebem a fila': '' });
  const a = criarAmbiente({ agora: utc('2026-10-20T10:10:00'), abas });
  a.ctx.cadaHora();
  assert.strictEqual(a.enviados[0].para, 'dono@exemplo.com');
});

teste('alerta: 4 horas sem rodada manda um aviso só, para o email de alerta', () => {
  const abas = abasBase();
  abas['rodada'][1][0] = '2026-10-20 06:00';
  const e = { agora: utc('2026-10-20T10:00:00'), abas, manterRodada: true };
  const a = criarAmbiente(e);
  a.ctx.cadaHora();
  const alertas = a.enviados.filter((x) => x.assunto.startsWith('ALERTA'));
  assert.strictEqual(alertas.length, 1);
  assert.strictEqual(alertas[0].para, 'alerta@exemplo.com');
  e.agora = utc('2026-10-20T11:00:00'); a.ctx.cadaHora();
  assert.strictEqual(a.enviados.filter((x) => x.assunto.startsWith('ALERTA')).length, 1, 'repetiu o alerta');
});

teste('alerta: com rodada recente não manda nada', () => {
  const abas = abasBase();
  abas['rodada'][1][0] = '2026-10-20 08:30';
  const a = criarAmbiente({ agora: utc('2026-10-20T10:00:00'), abas });
  a.ctx.cadaHora();
  assert.strictEqual(a.enviados.filter((x) => x.assunto.startsWith('ALERTA')).length, 0);
});

teste('dias da fila: leitura de "seg a sáb", lista e "todos"', () => {
  const a = criarAmbiente({ agora: utc('2026-10-20T10:00:00'), abas: abasBase() });
  assert.deepStrictEqual(Array.from(a.ctx.diasDaFila_('seg a sáb')), [0, 1, 2, 3, 4, 5]);
  assert.deepStrictEqual(Array.from(a.ctx.diasDaFila_('seg, qua, sex')), [0, 2, 4]);
  assert.deepStrictEqual(Array.from(a.ctx.diasDaFila_('todos')), [0, 1, 2, 3, 4, 5, 6]);
  assert.deepStrictEqual(Array.from(a.ctx.diasDaFila_('xyz')), [0, 1, 2, 3, 4, 5]);
});

const resumos = (a) => a.enviados.filter((x) => x.assunto.startsWith('Resumo da semana'));
const comResumo = (abas) => ({ ...abas, 'resumo_email': [['assunto', 'html', 'gerado_em'],
  ['Resumo da semana do Painel Monstro (19/10/2026)', '<p>Resumo de teste</p>', '2026-10-19 07:07']] });

teste('resumo: segunda às 8h manda uma vez só, para os Emails do resumo', () => {
  const e = { agora: utc('2026-10-19T08:10:00'), abas: comResumo(abasBase()) };   // segunda
  const a = criarAmbiente(e);
  a.ctx.cadaHora(); a.ctx.cadaHora();
  assert.strictEqual(resumos(a).length, 1);
  assert.strictEqual(resumos(a)[0].para, 'tulio@exemplo.com');
  assert.ok(!resumos(a)[0].assunto.includes('atrasado'));
});

teste('resumo: antes das 8h não manda; depois das 8h manda atrasado', () => {
  const e = { agora: utc('2026-10-19T07:30:00'), abas: comResumo(abasBase()) };
  const a = criarAmbiente(e);
  a.ctx.cadaHora();
  assert.strictEqual(resumos(a).length, 0);
  e.abas.rodada[1][0] = '2026-10-19 08:50'; e.agora = utc('2026-10-19T09:30:00');
  a.ctx.cadaHora();
  assert.strictEqual(resumos(a).length, 1);
  assert.ok(resumos(a)[0].assunto.includes('(atrasado)'));
});

teste('resumo: fora da segunda não manda, mesmo em dia de fila', () => {
  const a = criarAmbiente({ agora: utc('2026-10-20T08:10:00'), abas: comResumo(abasBase()) });   // terça
  a.ctx.cadaHora();
  assert.strictEqual(resumos(a).length, 0);
});

teste('resumo: sem destinatário avisa o dono; falha de envio repete na hora seguinte', () => {
  const abas = comResumo(abasBase());
  abas['Configuração'] = config({ 'Emails do resumo': '' });
  const e = { agora: utc('2026-10-19T08:10:00'), abas, falharEnvio: true };
  const a = criarAmbiente(e);
  a.ctx.cadaHora();
  assert.strictEqual(resumos(a).length, 0);
  e.falharEnvio = false; e.abas.rodada[1][0] = '2026-10-19 08:50'; e.agora = utc('2026-10-19T09:10:00');
  a.ctx.cadaHora();
  assert.strictEqual(resumos(a).length, 1);
  assert.strictEqual(resumos(a)[0].para, 'dono@exemplo.com');
});

const alertasBrevo = (a) => a.enviados.filter((x) => x.assunto.includes('problema com o Brevo'));
const comBrevo = (status, detalhe = '') => {
  const abas = abasBase();
  abas['rodada'] = [['ultima_rodada_ok', 'duracao_s', 'dia_de_fila', 'brevo_status', 'brevo_detalhe', 'brevo_ultima_leitura_ok'],
    ['2026-10-20 09:40', 50, true, status, detalhe, '2026-10-19 22:07']];
  return abas;
};

teste('brevo: chave inválida ou bloqueio de IP manda o alerta, uma vez por dia', () => {
  const e = { agora: utc('2026-10-20T10:00:00'), abas: comBrevo('erro: bloqueio_ip', 'O Brevo bloqueou o acesso por endereço de IP.'), manterRodada: true };
  const a = criarAmbiente(e);
  a.ctx.cadaHora(); a.ctx.cadaHora();
  assert.strictEqual(alertasBrevo(a).length, 1);
  assert.strictEqual(alertasBrevo(a)[0].para, 'alerta@exemplo.com');
  assert.ok(alertasBrevo(a)[0].html.includes('bloqueio de IP') && alertasBrevo(a)[0].html.includes('2026-10-19 22:07'));
  e.agora = utc('2026-10-21T10:00:00'); e.abas.rodada[1][0] = '2026-10-21 09:40';
  a.ctx.cadaHora();
  assert.strictEqual(alertasBrevo(a).length, 2, 'no dia seguinte avisa de novo se continuar');
});

teste('brevo: situação ok ou sem chave não manda alerta', () => {
  for (const s of ['ok (modo teste)', 'ok', 'sem chave']) {
    const a = criarAmbiente({ agora: utc('2026-10-20T10:00:00'), abas: comBrevo(s), manterRodada: true });
    a.ctx.cadaHora();
    assert.strictEqual(alertasBrevo(a).length, 0, s);
  }
});

function eventoToque(ctx, oldValue, value, opcoes = {}) {
  const aba = ctx.SpreadsheetApp.getActiveSpreadsheet().getSheetByName(opcoes.aba || 'Fila');
  const row = opcoes.row || 2, col = opcoes.col || 1;
  const r = aba.getRange(row, col);
  r.setValue(value === undefined ? '' : value);
  return { oldValue, value, range: { ...r, getSheet: () => aba, getRow: () => row, getColumn: () => col,
    getNumRows: () => opcoes.rows || 1, getNumColumns: () => opcoes.cols || 1 } };
}
function ambienteToques() {
  const estado = { agora: utc('2026-10-19T10:35:00'), abas: {
    Fila: [['Toques já enviados', 'Último envio em', 'Status'], ['', 'data antiga', 'Em andamento']],
    Outra: [['Toques já enviados', 'Último envio em'], ['', 'data antiga']],
  } };
  return { estado, ...criarAmbiente(estado) };
}
teste('primeiro toque registra horario de Brasilia sem alterar status', () => {
  const e = ambienteToques();
  e.ctx.onEdit(eventoToque(e.ctx, undefined, '1'));
  assert.equal(e.estado.abas.Fila[1][1], '2026-10-19 10:35');
  assert.equal(e.estado.abas.Fila[1][2], 'Em andamento');
  assert.equal(e.enviados.length, 0);
});
teste('novo toque atualiza data; diminuir apagar repetir e valores invalidos preservam', () => {
  for (const [antes, depois, muda] of [['1', '2', true], ['2', '1', false], ['2', undefined, false],
    ['1', '1', false], [undefined, '0', false], ['1', '1.5', false], ['1', '-1', false], ['erro', '2', false]]) {
    const e = ambienteToques(); e.ctx.onEdit(eventoToque(e.ctx, antes, depois));
    assert.equal(e.estado.abas.Fila[1][1], muda ? '2026-10-19 10:35' : 'data antiga');
  }
});
teste('ignora outra aba coluna cabecalho e colagem de varias celulas', () => {
  for (const o of [{ aba: 'Outra' }, { col: 3 }, { row: 1 }, { rows: 2 }, { cols: 2 }]) {
    const e = ambienteToques(); e.ctx.onEdit(eventoToque(e.ctx, '1', '2', o));
    assert.equal(e.estado.abas.Fila[1][1], 'data antiga');
    assert.equal(e.estado.abas.Outra[1][1], 'data antiga');
  }
});
teste('evento atrasado e execução manual nao registram toque', () => {
  const e = ambienteToques(); const evento = eventoToque(e.ctx, '1', '2');
  e.estado.abas.Fila[1][0] = '3'; e.ctx.onEdit(evento); e.ctx.onEdit();
  assert.equal(e.estado.abas.Fila[1][1], 'data antiga');
});
function ambienteEnvio(status = '', situacao = 'Contatar', toques = '') {
  const estado = { agora: utc('2026-10-19T10:35:00'), abas: { Fila: [
    ['Toques já enviados', 'Último envio em', 'Status', 'Situação', 'Enviei agora'],
    [toques, 'data antiga', status, situacao, false]] } };
  return { estado, ...criarAmbiente(estado) };
}
teste('caixa registra envio completo e desmarca sem mandar WhatsApp', () => {
  const a = ambienteEnvio(); const e = eventoToque(a.ctx, 'FALSE', true, { col: 5 });
  a.ctx.onEdit(e);
  assert.deepEqual(a.estado.abas.Fila[1], [1, '2026-10-19 10:35', 'Em andamento', 'Envio registrado', false]);
  assert.equal(a.enviados.length, 0);
  a.ctx.onEdit(e); // evento repetido não duplica o contador
  assert.equal(a.estado.abas.Fila[1][0], 1);
});
teste('proximo envio aumenta contador e preserva Respondeu', () => {
  const a = ambienteEnvio('Respondeu', 'Contatar', 1);
  a.ctx.onEdit(eventoToque(a.ctx, 'FALSE', true, { col: 5 }));
  assert.equal(a.estado.abas.Fila[1][0], 2);
  assert.equal(a.estado.abas.Fila[1][2], 'Respondeu');
});
teste('caixa nao registra invalidos recusas recuperados ou linha fora de Contatar', () => {
  for (const [status, sit] of [['Contato inválido', 'Contatar'], ['Não quer', 'Contatar'], ['Recuperado', 'Contatar'],
    ['', 'Encerrado'], ['Em andamento', 'Envio registrado']]) {
    const a = ambienteEnvio(status, sit);
    a.ctx.onEdit(eventoToque(a.ctx, 'FALSE', true, { col: 5 }));
    assert.equal(a.estado.abas.Fila[1][0], '');
    assert.equal(a.estado.abas.Fila[1][1], 'data antiga');
    assert.equal(a.estado.abas.Fila[1][4], false);
  }
});
teste('editar apenas status ou desmarcar caixa nao aumenta contador', () => {
  const a = ambienteEnvio();
  a.ctx.onEdit(eventoToque(a.ctx, '', 'Em andamento', { col: 3 }));
  a.ctx.onEdit(eventoToque(a.ctx, 'TRUE', false, { col: 5 }));
  assert.equal(a.estado.abas.Fila[1][0], '');
});
function ambienteResposta(status = 'Em andamento', recuperado = '') {
  const estado = { agora: utc('2026-10-19T10:35:00'), abas: { Fila: [
    ['Carrinho', 'Toques já enviados', 'Último envio em', 'Status', 'Situação', 'Recuperado',
     'Respondeu agora', 'Contato inválido agora', 'Não quer agora'],
    ['ciclo-ficticio', 1, 'data antiga', status, 'Aguardar intervalo', recuperado, false, false, false]] } };
  return { estado, ...criarAmbiente(estado) };
}
teste('acoes de resposta recusa e invalido preservam contador e horario', () => {
  for (const [col, status, situacao] of [[7, 'Respondeu', 'Em conversa'],
       [8, 'Contato inválido', 'Encerrado: contato inválido'], [9, 'Não quer', 'Encerrado: bloqueado']]) {
    const a = ambienteResposta(); const evento = eventoToque(a.ctx, 'FALSE', true, {col});
    a.ctx.onEdit(evento); a.ctx.onEdit(evento);
    assert.equal(a.estado.abas.Fila[1][3], status);
    assert.equal(a.estado.abas.Fila[1][4], situacao);
    assert.equal(a.estado.abas.Fila[1][1], 1);
    assert.equal(a.estado.abas.Fila[1][2], 'data antiga');
    assert.equal(a.estado.abas.Fila[1][col-1], false);
    assert.equal(a.enviados.length, 0);
  }
});
teste('resposta nao reabre recusa invalido ou recuperacao', () => {
  for (const [status, rec] of [['Não quer',''], ['Contato inválido',''], ['Recuperado',''], ['Em andamento','Sim']]) {
    const a = ambienteResposta(status,rec);
    a.ctx.onEdit(eventoToque(a.ctx, 'FALSE', true, {col:7}));
    assert.equal(a.estado.abas.Fila[1][3],status);
    assert.equal(a.estado.abas.Fila[1][6],false);
  }
});
teste('resposta sem ciclo ou colagem multipla nao altera status', () => {
  const a = ambienteResposta(); a.estado.abas.Fila[1][0]='';
  a.ctx.onEdit(eventoToque(a.ctx,'FALSE',true,{col:7}));
  assert.equal(a.estado.abas.Fila[1][3],'Em andamento');
  const b = ambienteResposta(); b.ctx.onEdit(eventoToque(b.ctx,'FALSE',true,{col:7, rows:2}));
  assert.equal(b.estado.abas.Fila[1][3],'Em andamento');
});
const newsletters = (a) => a.enviados.filter((x) => x.assunto.startsWith('Newsletter da semana'));
const comNewsletter = (abas) => ({ ...abas, 'newsletter_aviso': [['gerado_em', 'discos', 'assunto', 'html'],
  ['2026-10-14 17:07', 12, 'Newsletter da semana: 12 discos prontos', '<p>pronto</p>']] });

teste('newsletter: aviso da quarta sai uma vez só, para os Emails do resumo', () => {
  const a = criarAmbiente({ agora: utc('2026-10-14T17:30:00'), abas: comNewsletter(abasBase()) });   // quarta
  a.ctx.cadaHora(); a.ctx.cadaHora();
  assert.strictEqual(newsletters(a).length, 1);
  assert.strictEqual(newsletters(a)[0].para, 'tulio@exemplo.com');
});

teste('newsletter: aviso de outro dia não é reenviado', () => {
  const a = criarAmbiente({ agora: utc('2026-10-15T10:00:00'), abas: comNewsletter(abasBase()) });   // quinta
  a.ctx.cadaHora();
  assert.strictEqual(newsletters(a).length, 0);
});

teste('email da fila mostra o rótulo humano do modelo', () => {
  const a = criarAmbiente({ agora: utc('2026-10-19T10:20:00'), abas: abasBase() });
  const r = a.ctx.rotuloModelo_;
  assert.strictEqual(r('T2_FRETE'), 'Frete grátis');
  assert.strictEqual(r('T3_CUPOM'), '10% nos discos (oferta final)');
  assert.strictEqual(r('ESGOTADO'), 'Estoque alterado');
  assert.strictEqual(r('ALERTA_GARIMPO'), 'Aviso de garimpo');
  assert.strictEqual(r('G45'), 'Garimpo de 45 dias');
  assert.strictEqual(r('VIP'), 'VIP');
  assert.strictEqual(r('T1_UNICO'), 'Lembrete');
  assert.strictEqual(r('T2_ESCASSEZ'), 'Lembrete');
  assert.strictEqual(r(''), '');
});

teste('newsletter: data convertida pela planilha em Date também é reconhecida', () => {
  const abas = comNewsletter(abasBase());
  abas.newsletter_aviso[1][0] = new Date(Date.UTC(2026, 9, 14, 20, 7));   // 17h07 em Brasília
  const a = criarAmbiente({ agora: utc('2026-10-14T17:30:00'), abas });
  a.ctx.cadaHora();
  assert.strictEqual(newsletters(a).length, 1);
});

const codigoSorteio = fs.readFileSync(path.join(__dirname, 'raspadinha', 'Sorteio.gs'), 'utf8');
const htmlPainel = fs.readFileSync(path.join(__dirname, 'painel-web', 'painel-monstro.html'), 'utf8');

function carregarSorteio(abas = {}, fetchFn = null) {
  const ctx = {
    PropertiesService: { getScriptProperties: () => ({ getProperty: () => 'planilha-teste' }) },
    SpreadsheetApp: {
      openById: () => ({
        getSheetByName: (nome) => {
          const v = abas[nome];
          if (!v) return null;
          return {
            getDataRange: () => ({ getDisplayValues: () => v.map((l) => l.map(String)) }),
            appendRow: (l) => v.push(l),
            getRange: (r, c) => ({ setValue: (val) => { v[r - 1][c - 1] = String(val); } }),
          };
        },
      }),
    },
    LockService: { getScriptLock: () => ({ tryLock: () => true, waitLock: () => {}, releaseLock: () => {} }) },
    UrlFetchApp: { fetch: (url, op) => fetchFn ? fetchFn(url, op) : ({ getResponseCode: () => 200, getContentText: () => '{}' }) },
    Logger: { log: () => {} },
    CacheService: { getScriptCache: () => ({ get: () => '{}', put: () => {} }) },
    Utilities: {
      formatDate: () => '2026-10-27',
      getUuid: () => 'uuid-fixo',
      DigestAlgorithm: { SHA_256: 'SHA_256' },
      computeDigest: () => [10, 20, 30, 40, 50, 60],
    },
    Math, Date, JSON, String, Number, Array, Object, RegExp, parseInt, console,
  };
  vm.createContext(ctx);
  vm.runInContext(codigoSorteio, ctx);
  return ctx;
}

function extrairFuncoesPainel() {
  const trechoNum = htmlPainel.slice(
    htmlPainel.indexOf('function num(x){'),
    htmlPainel.indexOf('const nf0 =')
  );
  const trechoPm = htmlPainel.slice(
    htmlPainel.indexOf('const PM_CAB ='),
    htmlPainel.indexOf('let COM_PM_FORM =')
  );
  const trecho = htmlPainel.slice(
    htmlPainel.indexOf('const rpCodigoOrigem ='),
    htmlPainel.indexOf('const RP_PADRAO =')
  );
  const brl2 = v => 'R$ ' + Number(v || 0).toFixed(2).replace('.', ',');
  const brl = brl2, int = v => String(v), brDiaC = v => String(v || '');
  const rpDia = v => String(v || '').slice(0, 10);
  const rows = v => { if (!v || v.length < 2) return []; const h = v[0]; return v.slice(1).map(r => { const o = {}; h.forEach((k, j) => o[k] = r && r[j] != null ? String(r[j]) : ''); return o; }); };
  const trechoRp = htmlPainel.slice(htmlPainel.indexOf('function rpJogadas(c){'), htmlPainel.indexOf('async function rpSalvarCamp'));
  const trechoApag = htmlPainel.slice(htmlPainel.indexOf('const rpPodeApagarStatus ='), htmlPainel.indexOf('async function rpApagar(linhas){'));
  const trechoCd = htmlPainel.slice(htmlPainel.indexOf('const cdVaiPublicar ='), htmlPainel.indexOf('function cdCard(o){'));
  const hojeSP = () => '2026-10-27';
  const ctx = { String, Array, JSON, RegExp, Math, Number, Object, parseFloat, isFinite, brl2, brl, int, brDiaC, rpDia, rows, hojeSP, D: {} };
  vm.createContext(ctx);
  vm.runInContext(trechoNum + '\n' + trechoPm + '\n' + trecho + '\n' + trechoRp + '\n' + trechoApag + '\n' + trechoCd + '\nthis.exports = { D, num, pmAddMes, pmDividirParcelas, pmValidarCronograma, pmLerCronograma, pmRateioNoMes, rpCodigoOrigem, rpOrigensLista, rpCanalDe, rpCanalJogada, rpNomeCanal, rpJogadas, rpEstado, rpStats, rpPodeApagarStatus, rpTextoConfirmarExclusao, cdVaiPublicar, cdTemPendenciaAviso };', ctx);
  return ctx.exports;
}

teste('raspadinha canal_: reconhece brevo, instagram, wpp, origem personalizada, parecido como outro e vazio como direto', () => {
  const s = carregarSorteio();
  const cp = { origens: [{ codigo: 'lista-transmissao', nome: 'Lista de transmissão' }] };
  assert.strictEqual(s.canal_({ utm_source: 'brevo' }, cp), 'email');
  assert.strictEqual(s.canal_({ utm_source: 'instagram' }, cp), 'instagram');
  assert.strictEqual(s.canal_({ utm_source: 'wpp' }, cp), 'whatsapp');
  assert.strictEqual(s.canal_({ utm_source: 'whatsapp' }, cp), 'whatsapp');
  assert.strictEqual(s.canal_({ utm_source: 'zap' }, cp), 'whatsapp');
  assert.strictEqual(s.canal_({ utm_source: 'lista-transmissao' }, cp), 'lista-transmissao');
  assert.strictEqual(s.canal_({ utm_source: 'lista-transmissao-vip' }, cp), 'outro');
  assert.strictEqual(s.canal_({ utm_source: 'lista-transmissa' }, cp), 'outro');
  assert.strictEqual(s.canal_({ utm_source: '' }, cp), 'direto');
  assert.strictEqual(s.canal_({}, cp), 'direto');
});

teste('raspadinha: gerador de código de origem e reclassificação no Painel', () => {
  const p = extrairFuncoesPainel();
  assert.strictEqual(p.rpCodigoOrigem('Lista de Transmissão'), 'lista-transmissao');
  assert.strictEqual(p.rpCodigoOrigem('Grupo da loja'), 'grupo-loja');
  const cp = { origens: [{ codigo: 'lista-transmissao', nome: 'Lista de transmissão' }] };
  assert.strictEqual(p.rpNomeCanal('whatsapp', cp), 'WhatsApp');
  assert.strictEqual(p.rpNomeCanal('lista-transmissao', cp), 'Lista de transmissão');
  assert.strictEqual(p.rpNomeCanal('outro', cp), 'Outra origem');
  assert.strictEqual(p.rpCanalJogada({ canal: 'outro', utm_source: 'wpp' }, cp), 'whatsapp');
  assert.strictEqual(p.rpCanalJogada({ canal: 'outro', utm_source: 'lista-transmissao' }, cp), 'lista-transmissao');
  assert.strictEqual(p.rpCanalJogada({ canal: 'outro', utm_source: 'desconhecido' }, cp), 'outro');
});

teste('raspadinha: bloqueio de whatsapp não permitido e liberação de origem personalizada', () => {
  const premios = JSON.stringify([{ rotulo: '10%', tipo: 'Porcentagem', valor: 10, chance: 100, maximo: '', reserva: 'Sim' }]);
  const origens = JSON.stringify([{ codigo: 'lista-transmissao', nome: 'Lista de transmissão' }]);
  const abas = {
    rasp_campanhas: [
      ['campanha', 'nome', 'status', 'inicio', 'fim', 'canais', 'validade_dias', 'pedido_minimo', 'cumulativo', 'so_clientes', 'permitir_sem_premio', 'texto_sem_premio', 'prefixo', 'titulo', 'texto', 'premios', 'atualizado_em', 'origens'],
      ['camp-1', 'Campanha 1', 'teste', '2026-10-01', '', 'email', '7', '0', 'Não', 'Não', 'Não', 'Sem prêmio', 'RASPA', 'Título', 'Texto', premios, '2026-10-27', origens],
    ],
    rasp_jogadas: [['quando', 'campanha', 'email', 'canal', 'utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'premio', 'tipo', 'valor', 'cupom', 'valido_ate', 'cupom_status', 'consentiu', 'novo_contato', 'cupom_id']],
  };
  const s = carregarSorteio(abas);
  const bloq = s.jogar_({ campanha: 'camp-1', email: 'cliente1@exemplo.com', utm_source: 'wpp' });
  assert.strictEqual(bloq.ok, false);
  assert.strictEqual(bloq.erro, 'canal');
  const okPers = s.jogar_({ campanha: 'camp-1', email: 'cliente2@exemplo.com', utm_source: 'lista-transmissao' });
  assert.strictEqual(okPers.ok, true);
  assert.strictEqual(abas.rasp_jogadas[1][3], 'lista-transmissao');
});

teste('pedidos manuais (D-080): divisão de parcelas 600 em 3x e 100 em 3x, e recusa soma diferente', () => {
  const p = extrairFuncoesPainel();
  // 1. R$ 600 em 3x divide 200/200/200
  const p600 = p.pmDividirParcelas(600, 3, '2026-10');
  assert.deepStrictEqual(JSON.parse(JSON.stringify(p600)), [
    { mes: '2026-10', valor: 200 },
    { mes: '2026-11', valor: 200 },
    { mes: '2026-12', valor: 200 },
  ]);
  // 2. R$ 100 em 3x divide 33,34/33,33/33,33
  const p100 = p.pmDividirParcelas(100, 3, '2026-10');
  assert.deepStrictEqual(JSON.parse(JSON.stringify(p100)), [
    { mes: '2026-10', valor: 33.34 },
    { mes: '2026-11', valor: 33.33 },
    { mes: '2026-12', valor: 33.33 },
  ]);
  // 3. soma diferente do total é recusada
  const invalido = p.pmValidarCronograma(600, 'parcelas', '', [
    { mes: '2026-10', valor: 200 },
    { mes: '2026-11', valor: 200 },
    { mes: '2026-12', valor: 190 },
  ]);
  assert.strictEqual(invalido.ok, false);
  const valido = p.pmValidarCronograma(100, 'parcelas', '', p100);
  assert.strictEqual(valido.ok, true);
});

teste('pedidos manuais (D-080): modo mes cai inteiro no mês escolhido, cancelado não entra e rateio com frete e taxa proporcionais', () => {
  const p = extrairFuncoesPainel();
  // 4. modo mes cai inteiro no mês escolhido
  const valMes = p.pmValidarCronograma(450, 'mes', '2026-11', []);
  assert.strictEqual(valMes.ok, true);
  const pedMes = {
    id: 'M20261015ABC',
    data_venda: '2026-10-15',
    descricao: '2 LPs rock',
    forma_pagamento: 'Pix',
    valor_total: '450.00',
    frete: '30.00',
    taxa: '0.00',
    parcelas: '1',
    modo: 'mes',
    mes_unico: '2026-11',
    cronograma: JSON.stringify(valMes.cronograma),
    situacao: 'ativo',
  };
  assert.strictEqual(p.pmRateioNoMes(pedMes, '2026-10', 3.65).length, 0);
  const rMes = p.pmRateioNoMes(pedMes, '2026-11', 3.65);
  assert.strictEqual(rMes.length, 1);
  assert.strictEqual(rMes[0].vendido, 450);
  assert.strictEqual(rMes[0].frete, 30);
  assert.strictEqual(rMes[0].taxa, 0);
  assert.strictEqual(rMes[0].base, 420);

  // 5. pedido cancelado não entra na conta
  const pedCancelado = Object.assign({}, pedMes, { situacao: 'cancelado' });
  assert.strictEqual(p.pmRateioNoMes(pedCancelado, '2026-11', 3.65).length, 0);

  // 6. base de uma parcela com frete e taxa proporcionais
  const pedParc = {
    id: 'M20261015KBA',
    data_venda: '2026-10-15',
    descricao: '3 LPs',
    forma_pagamento: 'PagBank',
    valor_total: '600.00',
    frete: '30.00',
    taxa: '18.00',
    parcelas: '3',
    modo: 'parcelas',
    mes_unico: '',
    cronograma: JSON.stringify(p.pmDividirParcelas(600, 3, '2026-10')),
    situacao: 'ativo',
  };
  const rParc = p.pmRateioNoMes(pedParc, '2026-11', 3.65);
  assert.strictEqual(rParc.length, 1);
  assert.strictEqual(rParc[0].rotuloParcela, 'parcela 2 de 3');
  assert.strictEqual(rParc[0].vendido, 200);
  assert.strictEqual(rParc[0].frete, 10);
  assert.strictEqual(rParc[0].taxa, 6);
  assert.strictEqual(rParc[0].base, 184);
});

teste('excluir cupons cancelados (D-083): apagar vira apagado, 404 vira apagado, erro vira erro ao apagar e não cancelado não é apagado', () => {
  const chamadasDelete = [];
  const abas = {
    rasp_jogadas: [
      ['quando', 'campanha', 'email', 'canal', 'utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'premio', 'tipo', 'valor', 'cupom', 'valido_ate', 'cupom_status', 'consentiu', 'novo_contato', 'cupom_id'],
      ['2026-10-20 10:00:00', 'camp-1', 'c1@exemplo.com', 'email', 'brevo', 'email', 'camp-1', '', '10%', 'Porcentagem', '10', 'RASPACANC1', '2026-10-27', 'apagar', 'Sim', 'Não', '101'],
      ['2026-10-20 10:01:00', 'camp-1', 'c2@exemplo.com', 'email', 'brevo', 'email', 'camp-1', '', '10%', 'Porcentagem', '10', 'RASPA404', '2026-10-27', 'apagar', 'Sim', 'Não', '102'],
      ['2026-10-20 10:02:00', 'camp-1', 'c3@exemplo.com', 'email', 'brevo', 'email', 'camp-1', '', '10%', 'Porcentagem', '10', 'RASPAERR', '2026-10-27', 'apagar', 'Sim', 'Não', '103'],
      ['2026-10-20 10:03:00', 'camp-1', 'c4@exemplo.com', 'email', 'brevo', 'email', 'camp-1', '', '10%', 'Porcentagem', '10', 'RASPAATIVO', '2026-10-27', 'criado', 'Sim', 'Não', '104'],
      ['2026-10-20 10:04:00', 'camp-1', 'c5@exemplo.com', 'email', 'brevo', 'email', 'camp-1', '', '10%', 'Porcentagem', '10', 'RASPAUSADO', '2026-10-27', 'apagar', 'Sim', 'Não', '105'],
      ['2026-10-20 10:05:00', 'camp-1', 'c6@exemplo.com', 'email', 'brevo', 'email', 'camp-1', '', '10%', 'Porcentagem', '10', 'RASPASEMID', '2026-10-27', 'apagar', 'Sim', 'Não', ''],
    ],
  };
  const s = carregarSorteio(abas, (url, op) => {
    const metodo = String((op && op.method) || 'get').toLowerCase();
    if (metodo === 'get' && url.includes('/coupons/105')) {
      return { getResponseCode: () => 200, getContentText: () => JSON.stringify({ id: 105, valid: true, used: 1 }) };
    }
    if (metodo === 'get' && url.includes('/coupons/')) {
      return { getResponseCode: () => 200, getContentText: () => JSON.stringify({ valid: false, used: 0 }) };
    }
    if (metodo === 'get' && url.includes('/coupons')) {
      return { getResponseCode: () => 200, getContentText: () => '[]' };
    }
    if (metodo === 'delete') {
      chamadasDelete.push(url);
      if (url.endsWith('/101')) return { getResponseCode: () => 204, getContentText: () => '' };
      if (url.endsWith('/102')) return { getResponseCode: () => 404, getContentText: () => '' };
      if (url.endsWith('/103')) return { getResponseCode: () => 403, getContentText: () => '' };
    }
    return { getResponseCode: () => 200, getContentText: () => '{}' };
  });
  s.processarCancelamentos();
  assert.strictEqual(abas.rasp_jogadas[1][13], 'apagado 2026-10-27');
  assert.strictEqual(abas.rasp_jogadas[2][13], 'apagado 2026-10-27');
  assert.strictEqual(abas.rasp_jogadas[3][13], 'erro ao apagar: Nuvemshop respondeu 403');
  assert.strictEqual(abas.rasp_jogadas[4][13], 'criado');
  assert.strictEqual(abas.rasp_jogadas[5][13], 'erro ao apagar: cupom ativo ou usado');
  assert.strictEqual(abas.rasp_jogadas[6][13], 'apagado 2026-10-27 (não existia)');
  assert.strictEqual(chamadasDelete.some(u => u.endsWith('/104') || u.endsWith('/105')), false);
});

teste('painel cupons cancelados (D-083) e publicar (D-082): conta só cancelado da campanha e métricas não mudam', () => {
  const p = extrairFuncoesPainel();
  assert.strictEqual(p.cdVaiPublicar({ publicar: '' }), true);
  assert.strictEqual(p.cdVaiPublicar({ publicar: 'sim' }), true);
  assert.strictEqual(p.cdVaiPublicar({ publicar: 'nao' }), false);
  assert.strictEqual(p.cdTemPendenciaAviso({ pendencias: 'Já existe na loja; conferir exemplar' }), true);
  assert.strictEqual(p.cdTemPendenciaAviso({ pendencias: 'sem etiqueta de preço' }), true);
  assert.strictEqual(p.cdTemPendenciaAviso({ pendencias: 'conferir vinil' }), false);
  assert.strictEqual(p.rpPodeApagarStatus('cancelado 2026-10-20'), true);
  assert.strictEqual(p.rpPodeApagarStatus('erro ao apagar: Nuvemshop respondeu 500'), true);
  assert.strictEqual(p.rpPodeApagarStatus('criado'), false);
  assert.strictEqual(p.rpPodeApagarStatus('apagado 2026-10-27'), false);

  const ped = { RASPAUSADO: { numero: '501', total: 250 } };
  p.D.rev = [['campanha', 'evento'], ['camp-a', 'abriu'], ['camp-a', 'abriu'], ['camp-a', 'abriu']];
  p.D.rjog = [
    ['campanha', 'cupom', 'cupom_status', 'valido_ate'],
    ['camp-a', 'RASPAUSADO', 'criado', '2026-10-30'],
    ['camp-a', 'RASPACANC1', 'cancelado 2026-10-20', '2026-10-25'],
    ['camp-a', 'RASPACANC2', 'cancelado 2026-10-21', '2026-10-25'],
    ['camp-a', 'RASPAVAL', 'criado', '2026-10-30'],
    ['camp-b', 'RASPAB1', 'cancelado 2026-10-20', '2026-10-25'],
  ];
  const antes = p.rpStats({ campanha: 'camp-a' }, ped);
  assert.strictEqual(antes.cancelados.length, 2);
  assert.strictEqual(antes.abriram, 3);
  assert.strictEqual(antes.rasparam, 4);
  assert.strictEqual(antes.usaram, 1);
  assert.strictEqual(antes.vendas, 250);
  assert.strictEqual(antes.reais, 4);

  // Depois que os 2 cupons cancelados viram apagado, o botão zera (0) e as métricas da campanha continuam idênticas
  p.D.rjog[2][2] = 'apagado 2026-10-27';
  p.D.rjog[3][2] = 'apagado 2026-10-27';
  const depois = p.rpStats({ campanha: 'camp-a' }, ped);
  assert.strictEqual(depois.cancelados.length, 0);
  assert.strictEqual(depois.abriram, antes.abriram);
  assert.strictEqual(depois.rasparam, antes.rasparam);
  assert.strictEqual(depois.usaram, antes.usaram);
  assert.strictEqual(depois.vendas, antes.vendas);
  assert.strictEqual(depois.reais, antes.reais);
  assert.strictEqual(p.rpEstado({ cupom: 'RASPACANC1', cupom_status: 'apagar' }, ped).t, 'excluindo…');
  assert.strictEqual(p.rpEstado({ cupom: 'RASPACANC1', cupom_status: 'apagado 2026-10-27' }, ped).t, 'excluído');
  assert.strictEqual(p.rpEstado({ cupom: 'RASPACANC1', cupom_status: 'erro ao apagar: Nuvemshop respondeu 500' }, ped).t, 'não consegui excluir');
});

console.log(`\n${n} testes do script passaram.`);
