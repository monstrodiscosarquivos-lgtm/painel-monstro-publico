"""Etapa 9: Meta e Planilha fictícios. Nenhuma rede nem dado de cliente real."""
from datetime import date, timedelta
import inspect
import json
from types import SimpleNamespace

import pandas as pd
import pytest
import requests

from painel_monstro.config import Config
from painel_monstro.saidas import anuncios as a, custos_automaticos as ca
from painel_monstro.saidas.planilha_google import PlanilhaGoogle
from tests.test_planilha_google import PlanilhaFalsa

HOJE = date(2026, 10, 15)
CFG = Config(meta_ads_token='segredo-meta-ficticio', meta_ads_account_id='act_555')


def bruto(d='2026-10-14', cid='1', gasto=50, compras=2, receita=300, **kw):
    return dict(date_start=d, campaign_id=cid, campaign_name='campanha vendas', spend=str(gasto),
                account_currency='BRL', impressions='1000', reach='500', frequency='2', inline_link_clicks='20',
                inline_link_click_ctr='2', cpm='50',
                actions=[{'action_type': a.COMPRA, 'value': str(compras)},
                         {'action_type': 'omni_purchase', 'value': '999'},
                         {'action_type': a.CARRINHO, 'value': '10'},
                         {'action_type': a.FINALIZACAO, 'value': '3'}],
                action_values=[{'action_type': a.COMPRA, 'value': str(receita)}], **kw)


def linha(d='2026-10-14', **kw):
    r = a.metricas(a.normalizar(bruto(d)), a.Parametros())
    r.update(tipo='vendas', status='ACTIVE', orcamento_dia=100)
    r.update(kw)
    return r


def tabelas(produtos=(), pedidos=()):
    return SimpleNamespace(produtos=pd.DataFrame(produtos), pedidos=pd.DataFrame(pedidos))


@pytest.mark.parametrize('nome,esperado', [
    ('black_local_rmkt', 'evento'), ('x_LOCAL_black', 'evento'), ('black_rmkt', 'remarketing'),
    ('Remarketing', 'remarketing'), ('Natal', 'sazonal'), ('black', 'sazonal'),
    ('sazonal outubro', 'sazonal'), ('catálogo', 'vendas'),
    ('_local', 'evento'), ('campanha_local', 'evento'), ('abc_localxyz', 'evento'),
    ('[evento] divulgação', 'evento'), ('campanha [EVENTO] outubro', 'evento'), ('outubro[evento]', 'evento'),
    ('ALCANCE', 'evento'), ('campanha alcance rmk black', 'evento'),
    ('rmk', 'remarketing'), ('campanha_RMK', 'remarketing'), ('rmk_black', 'remarketing'),
    ('local', 'vendas'), ('evento', 'vendas'), ('rm', 'vendas')])
def test_tipo_pela_ordem_e_override(nome, esperado):
    assert a.tipo(nome) == esperado
    assert a.tipo(nome, 'vendas') == 'vendas'
    assert a.tipo(nome, 'inválido') == esperado


@pytest.mark.parametrize('compras,roas,esperado', [(11, 6, 'semana boa'), (11, 4, 'escalando'),
                                                (9, 6, 'travado'), (9, 4, 'problema')])
def test_quatro_quadros_da_leitura(compras, roas, esperado):
    anteriores = [{'compras': 10, 'roas_real': 5}] * 4
    assert a.leitura(compras, roas, anteriores) == esperado
    assert a.leitura(compras, roas, anteriores[:3]) == ''
    assert a.leitura(compras, None, anteriores) == ''
    assert a.leitura(10, roas, anteriores) == ''


def test_semanas_segunda_domingo_disco_retorno_e_pedidos_validos_sem_expor_cliente():
    produtos = [dict(nome='LP Exemplo - Disco', criado_em='2025-07-07', no_estoque_desde='2026-10-14'),
                dict(nome='CD Exemplo - Novo', criado_em='2026-10-14', no_estoque_desde='2026-10-14'),
                dict(nome='Camiseta', criado_em='2025-07-07'),
                dict(nome='Combo LP Exemplo - Disco', criado_em='2025-07-07')]
    pedidos = [dict(valido=True, data='2025-07-13', subtotal=120, desconto=20, email='a@exemplo.com'),
               dict(valido=True, data='2025-07-14', subtotal=50, desconto=0),
               dict(valido=False, data='2025-07-13', subtotal=900, desconto=0)]
    ds = [linha('2025-07-06'), linha('2025-07-07'), linha('2025-07-13'),
          linha('2025-07-14', tipo='evento')]
    sem = a.semanas(ds, pd.DataFrame(produtos), pd.DataFrame(pedidos), HOJE, a.Parametros())
    conta = {r['semana_inicio']: r for r in sem if r['escopo'] == 'conta'}
    vendas = {r['semana_inicio']: r for r in sem if r['escopo'] == 'vendas'}
    assert conta['2025-07-07']['compras'] == 4  # domingo pertence à semana anterior
    assert conta['2025-07-14']['compras'] == 2 and vendas['2025-07-14']['compras'] == 0
    assert conta['2025-07-07']['discos_criados'] == 1
    assert conta['2025-07-07']['pedidos_site'] == 1 and conta['2025-07-07']['receita_site'] == 100
    assert conta['2025-07-07']['discos_voltaram'] is None
    assert conta['2026-10-05']['discos_voltaram'] is None
    assert conta['2026-10-12']['discos_voltaram'] == 1
    assert conta['2026-10-12']['discos_entraram'] == 2  # criação não é retorno
    assert 'email' not in json.dumps(sem)


def test_semanas_mudanca_verba_valores_reais_e_leitura():
    ds = [linha(str(date(2025, 7, 7) + timedelta(days=7*i)), investido=100, compras=10, receita=500)
          for i in range(4)]
    ds += [linha('2025-08-04', investido=200, compras=15, receita=600)]
    rs = a.semanas(ds, pd.DataFrame(), pd.DataFrame(), date(2025, 8, 10), a.Parametros())
    r = [r for r in rs if r['escopo']=='vendas'][-1]
    assert r['leitura'] == 'escalando' and r['mudou_verba'] == 'sim'
    assert r['variacao_investimento_pct'] == 100
    assert r['compras_por_100'] == pytest.approx(15 / 2.2766)
    assert r['conversao_clique_pct'] == 75


def regras(ds, estrutura=None, anuncios=(), notas=None):
    estrutura = estrutura if estrutura is not None else [dict(id='1', effective_status='ACTIVE', start_time='2026-10-01')]
    return {r['regra'] for r in a.alertar(ds, anuncios, estrutura, notas or {}, HOJE, a.Parametros())}


def test_entrega_cortada_dispara_e_nao_dispara():
    assert 'Entrega cortada' in regras([linha(investido=69)])
    assert 'Entrega cortada' not in regras([linha(investido=70)])
    assert 'Entrega cortada' not in regras([linha()], [dict(id='1', effective_status='PAUSED', start_time='2026-10-01')])
    assert 'Entrega cortada' not in regras([linha(orcamento_dia=None)])
    assert 'Entrega cortada' not in regras([linha()], [dict(id='1', effective_status='ACTIVE', start_time=str(HOJE))])
    assert 'Entrega cortada' in regras([], [dict(id='1',name='Sem gasto', effective_status='ACTIVE',
                                               daily_budget='10000',start_time='2026-10-01')])


def test_dias_sem_venda_dispara_e_nao_dispara():
    ds = [linha(str(HOJE - timedelta(days=n)), compras=0) for n in (1, 2, 3)]
    assert 'Gasto sem venda' in regras(ds)
    assert 'Gasto sem venda' not in regras(ds[:2])
    ds[1]['compras'] = 1
    assert 'Gasto sem venda' not in regras(ds)
    ds[1]['compras'] = 0; ds[1]['investido'] = 0
    assert 'Gasto sem venda' not in regras(ds)
    assert 'Gasto sem venda' not in regras([{**r, 'tipo':'evento'} for r in ds])


def test_cpa_e_roas_disparam_e_nao_disparam():
    assert 'Custo por venda acima do teto' in regras([linha(investido=100, compras=1)])
    assert 'Custo por venda acima do teto' not in regras([linha(investido=100, compras=4)])
    assert 'Custo por venda acima do teto' not in regras([linha(compras=0)])
    assert 'ROAS abaixo do equilíbrio' in regras([linha(investido=100, receita=200)])
    assert 'ROAS abaixo do equilíbrio' not in regras([linha(investido=100, receita=400)])
    assert 'ROAS abaixo do equilíbrio' not in regras([])


def test_evento_passou_e_catalogo_disparam_e_nao_disparam():
    estrutura = [dict(id='1', stop_time='2026-10-14T23:00:00-03:00')]
    ds = [linha(str(HOJE), tipo='evento')]
    assert 'Evento já passou' in regras(ds, estrutura)
    assert 'Evento já passou' not in regras(ds, [dict(id='1',stop_time='2026-10-16')])
    assert 'Evento já passou' not in regras(ds, estrutura, notas={'1': {'data_evento':'2026-10-16'}})
    assert 'Evento já passou' not in regras([linha(str(HOJE),tipo='evento',investido=0)], estrutura)
    assert 'Catálogo suspeito' in regras([linha(tipo='remarketing',carrinhos=10,finalizacoes=1)])
    assert 'Catálogo suspeito' not in regras([linha(tipo='remarketing',carrinhos=10,finalizacoes=1.5)])
    assert 'Catálogo suspeito' not in regras([linha(tipo='remarketing',carrinhos=9,finalizacoes=0)])
    assert 'Catálogo suspeito' not in regras([linha(tipo='vendas',carrinhos=10,finalizacoes=0)])


def test_evento_encerrado_hoje_so_alerta_com_hora_posterior():
    ds=[linha(str(HOJE),tipo='evento')]
    estrutura=[dict(id='1',stop_time='2026-10-15T12:30:00-03:00')]
    antes=[{**ds[0],'hora':'12:00:00 - 12:59:59'}]
    depois=[{**ds[0],'hora':'13:00:00 - 13:59:59'}]
    def r(h):
        return {x['regra'] for x in a.alertar(ds,[],estrutura,{},HOJE,a.Parametros(),horas=h)}
    assert 'Evento já passou' not in r(antes)
    assert 'Evento já passou' in r(depois)


def montar_ad(gasto=31, freq=4, ctr_ad=1, ctr_camp=2, tipo='vendas'):
    diario=[a.normalizar(bruto())]; diario[0]['cliques_link'] = ctr_camp * 10
    ad = a.normalizar(bruto(ad_id='2', ad_name='Imagem A', adset_name='Conjunto A'))
    sete = {**ad, 'investido': gasto, 'frequencia': freq, 'cliques_link': ctr_ad * 10}
    return a.montar(diario, [], [ad], [sete], [dict(id='1',name='vendas')], [],
                   [dict(id='2',name='Imagem A',effective_status='ACTIVE',campaign_id='1',creative={'thumbnail_url':'https://exemplo.com/imagem'})],
                   [dict(campanha_id='1',tipo=tipo)], tabelas(), HOJE, a.Parametros())


def test_anuncio_cansado_por_frequencia_ou_ctr_e_negativos():
    for dados in [montar_ad(ctr_ad=2), montar_ad(freq=2)]:
        assert dados['anuncios_anuncios'][0]['cansado'] == 'sim'
        assert 'Anúncio cansado' in {r['regra'] for r in dados['anuncios_alertas']}
    for dados in [montar_ad(freq=3,ctr_ad=2), montar_ad(tipo='remarketing',ctr_ad=2),
                  montar_ad(gasto=30,freq=2), montar_ad(freq=2,ctr_ad=1.2)]:
        assert dados['anuncios_anuncios'][0]['cansado'] == 'não'
        assert 'Anúncio cansado' not in {r['regra'] for r in dados['anuncios_alertas']}
    assert montar_ad(freq=4)['anuncios_anuncios'][0]['frequencia_7d'] == 4


class Resposta:
    def __init__(self, dados, headers=None, status=200):
        self.dados, self.headers, self.status_code = dados, headers or {}, status
    def json(self):
        return self.dados


class Sessao:
    def __init__(self, respostas):
        self.respostas = iter(respostas); self.chamadas=[]
    def get(self, url, **kw):
        self.chamadas.append((url, kw))
        r=next(self.respostas)
        if isinstance(r, Exception): raise r
        return r


def test_get_pagina_sem_seguir_url_com_token_e_atribuicao_sem_omni():
    s = Sessao([Resposta({'data':[bruto()], 'paging':{'next':'https://invalido.com/?access_token=segredo', 'cursors':{'after':'pagina2'}}}),
                Resposta({'data':[bruto('2026-10-15')]})])
    r = a.MetaLeitura(CFG,s).insights(date(2026,10,14),HOJE)
    assert len(r)==2 and r[0]['compras']==2 and r[0]['receita']==300
    assert all(x[0].startswith('https://graph.facebook.com/') and 'token=' not in x[0] for x in s.chamadas)
    assert s.chamadas[1][1]['params']['after']=='pagina2'
    assert all(x[1]['params']['action_report_time']=='conversion' and x[1]['params']['use_account_attribution_setting']=='true' for x in s.chamadas)
    assert 'omni_purchase' not in json.dumps(r)


@pytest.mark.parametrize('uso,passa',[(75,True),(75.01,False),(90,False)])
def test_limite_de_uso_interrompe_antes_de_outra_pagina(uso,passa):
    s = Sessao([Resposta({'data':[]}, {'x-business-use-case-usage':json.dumps({'555':[{'call_count':uso}]})})])
    if passa:
        assert a.MetaLeitura(CFG,s).lista('/campaigns')==[]
    else:
        with pytest.raises(a.ErroAnuncios, match='75%'): a.MetaLeitura(CFG,s).lista('/campaigns')
    assert len(s.chamadas)==1


@pytest.mark.parametrize('resposta', [Resposta({'data':[bruto(account_currency_ignorado='USD')]}),
                                    Resposta({'data':[]},status=403), requests.ConnectionError('segredo-meta-ficticio')])
def test_falhas_nao_expoem_token(resposta):
    if isinstance(resposta,Resposta) and resposta.status_code==200:
        resposta.dados['data'][0]['account_currency']='USD'
    with pytest.raises(a.ErroAnuncios) as erro:
        a.MetaLeitura(CFG,Sessao([resposta])).insights(HOJE,HOJE)
    assert CFG.meta_ads_token not in str(erro.value)


class HistoricoFalso:
    def __init__(self, falhar=None): self.chamadas=[]; self.falhar=falhar
    def insights(self,inicio,fim):
        self.chamadas.append((inicio,fim))
        if inicio==self.falhar: raise a.ErroAnuncios('limite')
        return [a.normalizar(bruto(str(inicio),gasto=50))]


def test_cache_meses_e_ultimos_sete_dias_substitui_inclusive_linha_removida(tmp_path):
    c=HistoricoFalso()
    a.historico(c,tmp_path,HOJE,'id')
    assert c.chamadas[0]==(date(2025,7,1),date(2025,7,31))
    assert c.chamadas[-1]==(date(2026,10,9),HOJE)
    c.chamadas=[]
    a.historico(c,tmp_path,HOJE,'id')
    assert c.chamadas==[(date(2026,10,9),HOJE)]
    antigas=[linha('2026-10-08'),linha('2026-10-09'),linha('2026-10-10')]
    novas=[linha('2026-10-09',investido=20)]
    r=a.mesclar(antigas,novas,date(2026,10,9),HOJE)
    assert [x['data'] for x in r]==['2026-10-08','2026-10-09'] and r[-1]['investido']==20
    assert CFG.meta_ads_token not in (tmp_path/'anuncios_historico.json').read_text()


def test_cache_repeticao_limitada_de_bloqueio_transitorio_windows(tmp_path,monkeypatch):
    from pathlib import Path
    caminho=tmp_path/'x.json'; caminho.write_text('{"anterior":true}')
    original=Path.replace; tentativas=[]
    def substituir(self,destino):
        tentativas.append(1)
        assert json.loads(caminho.read_text())=={'anterior':True}
        if len(tentativas)<3: raise PermissionError('bloqueio fictício')
        return original(self,destino)
    monkeypatch.setattr(Path,'replace',substituir); monkeypatch.setattr(a.time,'sleep',lambda _:None)
    a.salvar(caminho,{'novo':True})
    assert len(tentativas)==3 and json.loads(caminho.read_text())=={'novo':True}


def test_cache_bloqueio_permanente_preserva_anterior(tmp_path,monkeypatch):
    from pathlib import Path
    caminho=tmp_path/'x.json'; caminho.write_text('{"anterior":true}')
    def falhar(*args): raise PermissionError('permanente')
    monkeypatch.setattr(Path,'replace',falhar); monkeypatch.setattr(a.time,'sleep',lambda _:None)
    with pytest.raises(PermissionError): a.salvar(caminho,{'novo':True})
    assert json.loads(caminho.read_text())=={'anterior':True}


def test_backfill_interrompido_retoma_e_lacuna_maior_que_sete_dias(tmp_path):
    c=HistoricoFalso(date(2025,8,1))
    with pytest.raises(a.ErroAnuncios): a.historico(c,tmp_path,HOJE,'id')
    c=HistoricoFalso(); a.historico(c,tmp_path,HOJE,'id')
    assert c.chamadas[0][0]==date(2025,8,1)
    c=HistoricoFalso(); a.historico(c,tmp_path,date(2026,10,29),'id')
    assert c.chamadas==[(date(2026,10,16),date(2026,10,29))]


def test_reconstrucao_manual_interrompida_nao_apaga_cache_bom_e_retoma(tmp_path):
    a.historico(HistoricoFalso(),tmp_path,HOJE,'id')
    caminho=tmp_path/'anuncios_historico.json'
    antes=json.loads(caminho.read_text())['linhas']
    with pytest.raises(a.ErroAnuncios):
        a.historico(HistoricoFalso(date(2025,8,1)),tmp_path,HOJE,'id',completo=True)
    assert json.loads(caminho.read_text())['linhas']==antes
    c=HistoricoFalso(); a.historico(c,tmp_path,HOJE,'id',completo=True)
    assert c.chamadas[0][0]==date(2025,8,1)
    assert 'reconstrucao' not in json.loads(caminho.read_text())


def test_paginacao_incompleta_e_ciclica_nao_publica_parcial():
    for paging in [{'next':'https://exemplo.com'}, {'next':'https://exemplo.com','cursors':{'after':'repetida'}}]:
        s=Sessao([Resposta({'data':[bruto()],'paging':paging})]*2)
        with pytest.raises(a.ErroAnuncios,match='Paginação'):
            a.MetaLeitura(CFG,s).insights(HOJE,HOJE)


def test_horario_e_ad_diario_aggregate_pedem_campos_compativeis():
    s=Sessao([Resposta({'data':[]}) for _ in range(3)])
    cliente=a.MetaLeitura(CFG,s)
    cliente.insights(HOJE,HOJE,horario=True)
    cliente.insights(HOJE,HOJE,'ad')
    cliente.insights(HOJE,HOJE,'ad',diario=False)
    ps=[r[1]['params'] for r in s.chamadas]
    assert ps[0]['breakdowns']==a.HORA and 'frequency' not in ps[0]['fields']
    assert ps[1]['level']=='ad' and ps[1]['time_increment']==1
    assert 'time_increment' not in ps[2] and 'frequency' in ps[2]['fields']


def test_orcamento_campanha_conjuntos_e_vitalicio_nao_inventado():
    conjuntos=[dict(campaign_id='1',effective_status='ACTIVE',daily_budget='2500'),
               dict(campaign_id='1',effective_status='PAUSED',daily_budget='9000')]
    assert a.orcamento(dict(id='1',daily_budget='10000'),conjuntos)==100
    assert a.orcamento(dict(id='1'),conjuntos)==25
    assert a.orcamento(dict(id='1',lifetime_budget='10000'),[]) is None


def test_config_e_abas_manuais_sao_preservadas():
    p=PlanilhaGoogle(PlanilhaFalsa())
    p.substituir('Configuração',pd.DataFrame([['Anúncios: fator de imposto','1,2','ajuda própria']],columns=['Parâmetro','Valor','Ajuda']))
    for nome in ('anuncios_notas','anuncios_direcao'):
        p.substituir(nome,pd.DataFrame([['manual']*len(a.COLUNAS[nome])],columns=a.COLUNAS[nome]))
    antes={nome:a_.get_all_values() for nome,a_ in p._ss.abas.items()}
    a.preparar_abas(p); a.preparar_abas(p)
    for nome in ('anuncios_notas','anuncios_direcao'): assert p._ss.worksheet(nome).get_all_values()==antes[nome]
    config=p._ss.worksheet('Configuração').get_all_values()
    assert config[:2]==antes['Configuração'] and len(config)==11
    assert a.Parametros.ler(config).fator==1.2


def test_falha_meta_preserva_todas_abas_metricas_e_data_boa(tmp_path,capsys):
    p=PlanilhaGoogle(PlanilhaFalsa())
    for nome in a.COLUNAS:
        if nome != 'anuncios_resumo': p.substituir(nome,pd.DataFrame([['anterior']*len(a.COLUNAS[nome])],columns=a.COLUNAS[nome]))
    p.substituir('anuncios_resumo',a.resumo(pd.Timestamp('2026-10-14'),[linha()]))
    antes={n:p._ss.worksheet(n).get_all_values() for n in a.COLUNAS if n!='anuncios_resumo'}
    paginas=a.passo_anuncios(CFG,p,tabelas(),tmp_path,agora=pd.Timestamp(str(HOJE)),
                             sessao=Sessao([requests.ConnectionError(CFG.meta_ads_token)]))
    assert [n for n,_ in paginas]==['anuncios_resumo']
    for n,df in paginas: p.substituir(n,df)
    assert all(p._ss.worksheet(n).get_all_values()==linhas for n,linhas in antes.items())
    resumo=dict(paginas[0][1].values)
    assert resumo['atualizado_em']=='2026-10-14 00:00' and resumo['estado']=='aviso'
    assert CFG.meta_ads_token not in capsys.readouterr().out


def test_soma_mensal_confere_meta_do_mes_tolerancia_um_real():
    diarios=[bruto('2026-09-01',cid='1',gasto=100,compras=2,receita=500),
             bruto('2026-09-30',cid='2',gasto=60.20,compras=3,receita=600), bruto('2026-10-01',gasto=999)]
    total=bruto(gasto=160.20,compras=5,receita=1100)
    s=Sessao([Resposta({'data':[total]})])
    meta=ca.meta_do_mes(CFG,'2026-09',s)
    r=a.montar([a.normalizar(x) for x in diarios],[],[],[],[],[],[],[],tabelas(),HOJE,a.Parametros())
    df=pd.DataFrame(r['anuncios_campanha_dia'])
    mes=df[df['data'].str.startswith('2026-09')]
    for coluna,campo in [('investido','investimento_meta'),('compras','compras_meta'),('receita','receita_meta')]:
        assert abs(mes[coluna].sum()-meta[campo])<=1
    assert s.chamadas[0][1]['params']['action_report_time']==a.ATRIBUICAO['action_report_time']


def test_sem_dado_cliente_nos_campos_cache_ou_abas_e_so_get():
    r=a.normalizar({**bruto(), 'email':'privado@exemplo.com','phone':'privado','customer':{'name':'Cliente'}})
    assert not {'email','phone','customer','name'} & set(r)
    assert not {'email','telefone','cliente','endereco'} & {c for cs in a.COLUNAS.values() for c in cs}
    assert all(n.startswith('anuncios_') for n in a.COLUNAS)
    codigo=inspect.getsource(a)
    assert not any('.'+m+'(' in codigo for m in ('post','put','patch','delete'))
    assert not any('/'+p in codigo for p in ('customaudiences','leads','customers'))


def test_coleta_completa_publica_so_contratos_finais(monkeypatch,tmp_path):
    class MetaFalso:
        base='ficticia'
        def __init__(self,*args): pass
        def _get(self,*args): return dict(currency='BRL',timezone_name=a.FUSO)
        def lista(self,recurso,**kw):
            if recurso=='/campaigns': return [dict(id='1',name='Vendas',effective_status='ACTIVE',daily_budget='10000')]
            if recurso=='/ads': return [dict(id='2',name='Ativo sem gasto',campaign_id='1',effective_status='ACTIVE')]
            return []
        def insights(self,inicio,fim,nivel='campaign',horario=False,diario=True):
            if nivel=='ad': return []
            return [a.normalizar(bruto(str(inicio)))]
    monkeypatch.setattr(a,'MetaLeitura',MetaFalso)
    p=PlanilhaGoogle(PlanilhaFalsa())
    paginas=dict(a.passo_anuncios(CFG,p,tabelas(),tmp_path,agora=pd.Timestamp(str(HOJE))))
    assert set(paginas)==set(a.COLUNAS)-{'anuncios_notas','anuncios_direcao'}
    for nome,df in paginas.items(): assert list(df.columns)==a.COLUNAS[nome]
    assert dict(paginas['anuncios_resumo'].values)['estado']=='ok'
    assert paginas['anuncios_anuncios'].iloc[0]['anuncio']=='Ativo sem gasto'
