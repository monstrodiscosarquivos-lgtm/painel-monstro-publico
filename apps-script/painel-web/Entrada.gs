/**
 * Painel Monstro · ENTRADA (D-069). Projeto do Apps Script na conta Gmail da Monstro.
 *
 * Implantar como app da Web: Executar como "Usuário que acessa o app da Web";
 * Quem pode acessar "Qualquer pessoa com Conta do Google".
 * Roda com a conta de quem abre só para saber QUEM é (o email). Não lê a planilha:
 * pede tudo ao COFRE, que roda com a conta da Monstro e confere a aba Acessos.
 *
 * Propriedades do script (Configurações do projeto > Propriedades do script):
 *   COFRE_URL = endereço /exec da implantação do cofre
 *   SEGREDO   = o mesmo segredo mostrado pelo prepararCofre() no projeto do cofre
 */

function doGet() {
  var email = Session.getActiveUser().getEmail();
  var r = cofre_({ acao: 'quem' });
  if (!r.ok) return aviso_(r.erro === 'sem_acesso'
    ? 'O email ' + (email || '(não identificado)') + ' ainda não tem acesso ao Painel. Peça ao Túlio para incluir você na aba Acessos.'
    : 'O Painel está indisponível agora (' + r.erro + '). Tente de novo em alguns minutos.');
  var ctx = JSON.stringify({ email: email, nome: r.nome || '', nivel: r.nivel, planilhaId: r.planilha_id || '' });
  var html = HtmlService.createHtmlOutputFromFile('Painel').getContent().replace('"__PM_CONTEXTO__"', ctx);
  return HtmlService.createHtmlOutput(html).setTitle('Painel Monstro')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

/** Chamado pela página: lê várias faixas da planilha de uma vez. */
function ler(ranges) { return cofre_({ acao: 'ler', ranges: ranges }); }

/** Chamado pela página: grava uma faixa (o cofre confere se o nível permite). */
function gravar(range, values) { return cofre_({ acao: 'gravar', range: range, values: values }); }

function cofre_(corpo) {
  var p = PropertiesService.getScriptProperties();
  var url = p.getProperty('COFRE_URL'), segredo = p.getProperty('SEGREDO');
  if (!url || !segredo) return { ok: false, erro: 'faltam COFRE_URL e SEGREDO nas propriedades da entrada' };
  corpo.email = Session.getActiveUser().getEmail();   // definido aqui no servidor, nunca pela página
  corpo.segredo = segredo;
  var resp, opcoes = { method: 'post', contentType: 'application/json', payload: JSON.stringify(corpo), muteHttpExceptions: true };
  for (var t = 0; ; t++) {   // falha de rede passageira: tenta de novo 1 vez, 1 segundo depois
    try { resp = UrlFetchApp.fetch(url, opcoes); break; }
    catch (e) {
      if (t >= 1) return { ok: false, erro: 'cofre indisponível: ' + String(e && e.message || e).slice(0, 120) };
      Utilities.sleep(1000);
    }
  }
  var txt = resp.getContentText();
  try { return JSON.parse(txt); } catch (e) {
    // Resposta que não é do cofre: endereço errado, implantação apagada ou acesso diferente de "Qualquer pessoa"
    var titulo = (txt.match(/<title>([^<]*)<\/title>/i) || [])[1] || txt.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').slice(0, 80);
    return { ok: false, erro: 'cofre respondeu ' + resp.getResponseCode() + ': ' + titulo };
  }
}

function aviso_(texto) {
  var t = HtmlService.createHtmlOutput(
    '<div style="font:16px/1.5 sans-serif;max-width:520px;margin:15vh auto;padding:0 20px;color:#1b1817">' +
    '<h1 style="font-size:22px">Painel Monstro</h1><p>' + texto.replace(/</g, '&lt;') + '</p></div>');
  return t.setTitle('Painel Monstro').addMetaTag('viewport', 'width=device-width, initial-scale=1');
}
