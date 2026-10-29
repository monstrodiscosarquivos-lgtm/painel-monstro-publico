"""Gera Painel.html (app da Web do Apps Script) a partir de painel-monstro.html (artifact do Claude).
Uso: python montar_painel_web.py caminho/painel-monstro.html caminho/Painel.html
O painel em si não muda: um adaptador troca a conexão do Claude (window.claude) por chamadas ao Apps Script."""
import sys

ADAPTADOR = r'''<script>
window.PM = "__PM_CONTEXTO__";
(function(){
  var PM = window.PM || {}, regs = [], timer = null;
  function chamar(fn){ var a = [].slice.call(arguments, 1); return new Promise(function(ok, falha){
    var r = google.script.run.withSuccessHandler(ok).withFailureHandler(falha); r[fn].apply(r, a); }); }
  function semAcesso(){ document.body.innerHTML = '<div style="font:16px/1.5 sans-serif;max-width:520px;margin:15vh auto;padding:0 20px"><h1 style="font-size:22px">Painel Monstro</h1><p>Seu acesso foi retirado ou expirou. Peça ao Túlio para conferir a aba Acessos.</p></div>'; }
  // Mostra no topo o motivo de uma falha de leitura (para o Túlio mandar o print)
  function avisar(txt){
    var d = document.getElementById('pm-erro');
    if (!d){ d = document.createElement('div'); d.id = 'pm-erro'; d.style.cssText = 'margin:12px 16px;padding:10px 14px;border-radius:10px;background:#5a1d1d;color:#fff;font:14px/1.4 sans-serif'; document.body.insertBefore(d, document.body.firstChild); }
    if (txt){ d.textContent = 'Não consegui ler parte da planilha: ' + txt; d.style.display = ''; } else d.style.display = 'none';
  }
  // Lê em lotes de 8 faixas, no máximo 3 lotes ao mesmo tempo (muitos pedidos juntos fazem o Google recusar alguns).
  // Lote que falha tenta de novo sozinho (2 s e 5 s depois); se ainda falhar, é dividido ao meio. Só avisa se nada der certo.
  var esperar = function(ms){ return new Promise(function(ok){ setTimeout(ok, ms); }); };
  async function lerLote(lote, tent){
    var resp = null, erro = '';
    try { resp = await chamar('ler', lote); } catch(e){ erro = (e && e.message) || String(e); }
    if (resp && (resp.ok || resp.erro === 'sem_acesso')) return resp;
    erro = erro || (resp && resp.erro) || 'sem resposta';
    if (tent < 2){ await esperar(tent ? 5000 : 2000); return lerLote(lote, tent + 1); }
    if (tent === 2 && lote.length > 1){   // divide uma vez só: se o cofre estiver fora do ar, não insiste
      var meio = Math.ceil(lote.length / 2), a = await lerLote(lote.slice(0, meio), 3), b = await lerLote(lote.slice(meio), 3);
      if (a.erro === 'sem_acesso' || b.erro === 'sem_acesso') return {ok: false, erro: 'sem_acesso'};
      var dados = {}; [a, b].forEach(function(r, k){ (k ? lote.slice(meio) : lote.slice(0, meio)).forEach(function(x){ dados[x] = r.ok ? r.dados[x] : undefined; }); });
      return {ok: true, dados: dados, parcial: !(a.ok && b.ok), erro: a.ok ? b.erro : a.erro};
    }
    return {ok: false, erro: erro};
  }
  async function buscar(lista){
    if (!lista.length) return;
    var ranges = lista.map(function(r){ return r.range; }).filter(function(v, i, a){ return a.indexOf(v) === i; }), dados = {}, falhas = [];
    var lotes = []; for (var i = 0; i < ranges.length; i += 8) lotes.push(ranges.slice(i, i + 8));
    var fila = lotes.slice(), negado = false;
    async function trabalhador(){
      while (fila.length && !negado){
        var lote = fila.shift(), resp = await lerLote(lote, 0);
        if (resp.erro === 'sem_acesso' && !resp.ok){ negado = true; semAcesso(); return; }
        if (resp.ok){ lote.forEach(function(r){ dados[r] = resp.dados[r]; }); if (resp.parcial) falhas.push(resp.erro || 'parte não respondeu'); }
        else { falhas.push(resp.erro); lote.forEach(function(r){ dados[r] = undefined; }); }
      }
    }
    await Promise.all([trabalhador(), trabalhador(), trabalhador()]);
    if (negado) return;
    avisar(falhas.length ? falhas[0] : '');
    lista.forEach(function(r){
      var v = dados[r.range];
      if (v === undefined) r.cb({type:'error', error:{code:'tool_error'}});
      else if (v === null) r.cb({type:'error', error:{code:'sem_permissao'}});
      else r.cb({type:'data', result:{payload:{values: v || []}}});
    });
  }
  function agendar(){ clearTimeout(timer); timer = setTimeout(function(){ buscar(regs); }, 0); }
  var conexao = {
    watchTool: function(s, t, a, cb){ regs.push({range: a.range, cb: cb}); agendar(); return function(){}; },
    callTool: async function(s, t, a){
      if (t === 'update_values'){
        var r = await chamar('gravar', a.range, a.values);
        if (!r || !r.ok) throw new Error(r && r.erro === 'sem_permissao' ? 'seu acesso não permite alterar esta parte' : 'não consegui gravar agora (' + (r && r.erro || 'sem resposta') + ')');
        return {};
      }
      var l = await chamar('ler', [a.range]); return {payload:{values: (l && l.dados && l.dados[a.range]) || []}};
    },
    invalidate: async function(){ agendar(); }
  };
  setInterval(function(){ buscar(regs); }, 600000);
  window.claude = { use: async function(){ return conexao; } };
  if (PM.nivel === 'k7'){
    try { localStorage.setItem('pm-view', 'k7'); } catch(e){}
    if (!/^#k7$/.test(location.hash)) history.replaceState(null, '', '#k7');
    document.write('<style>.tabs{display:none!important}</style>');
  } else if (PM.nivel !== 'especial'){
    try { var v = localStorage.getItem('pm-view'); if (v === 'com') localStorage.setItem('pm-view', 'painel'); } catch(e){}
    if (/^#comissao$/.test(location.hash)) history.replaceState(null, '', '#');
    document.write('<style>#tab-com,#view-com{display:none!important}</style>');
  }
  document.addEventListener('DOMContentLoaded', function(){
    var m = document.querySelector('header .meta');
    if (m){ var s = document.createElement('span'); s.className = 'pm-quem';
      s.textContent = (PM.nome || PM.email || '') + (PM.nivel === 'especial' ? ' · acesso especial' : (PM.nivel === 'k7' ? ' · acesso K7' : ''));
      s.style.cssText = 'font-size:12px;color:var(--muted)'; m.insertBefore(s, m.firstChild); }
  });
})();
</script>'''

def montar(origem, destino):
    corpo = open(origem, encoding='utf-8').read()
    assert 'window.claude?.use?.("mcp")' in corpo, 'painel sem o ponto de conexão esperado'
    html = ('<!doctype html>\n<html lang="pt-BR"><head><meta charset="utf-8">\n'
            + ADAPTADOR + '\n</head><body>\n' + corpo + '\n</body></html>\n')
    open(destino, 'w', encoding='utf-8').write(html)

if __name__ == '__main__':
    montar(sys.argv[1], sys.argv[2])
