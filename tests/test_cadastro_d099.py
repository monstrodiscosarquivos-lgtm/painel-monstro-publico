import io
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from PIL import Image
from painel_monstro.saidas.cadastro import (foto_publicavel, publicar_sem_alerta, somar_estoque, ErroCadastro, LojaCadastro)
from painel_monstro.saidas.fotos import distancia_capas
from painel_monstro.coletor.discogs import Discogs
from scripts.cadastro_lote import pasta_sessao, ErroLote


def imagem(cor):
    im=Image.new('RGB',(100,100),cor)
    for i in range(20,80): im.putpixel((i,i),(255,255,255))
    b=io.BytesIO(); im.save(b,'JPEG'); return b.getvalue()


def test_papeis_privados():
    for p in ('etiqueta','referencia','codigo_barras','descartar'):
        assert not foto_publicavel({'papel':p})
    assert foto_publicavel({'papel':'oficial'})


def test_hash_reduzido():
    assert distancia_capas(imagem('red'),imagem('red'))==0
    import numpy as np
    a=Image.fromarray(np.random.default_rng(1).integers(0,255,(100,100,3),dtype=np.uint8))
    b=io.BytesIO();a.save(b,'JPEG')
    assert distancia_capas(imagem('red'),b.getvalue())>18


def test_publicacao_exige_todas_condicoes():
    l=dict(preco=120,preco_origem='etiqueta',discogs_confianca='alta',pendencias='')
    assert publicar_sem_alerta(l,True)
    for chave,valor in [('pendencias','alerta'),('preco_origem','planilha'),('discogs_confianca','baixa'),('preco','')]:
        assert not publicar_sem_alerta({**l,chave:valor},True)
    assert not publicar_sem_alerta(l,False)
    assert not publicar_sem_alerta(l,True,False)


def test_soma_idempotente_e_so_stock(tmp_path):
    chamadas=[]; gravados=[]
    loja=SimpleNamespace(produto=lambda p: {'variants':[{'id':99,'stock':2,'stock_management':True}]},estoque=lambda *a:chamadas.append(a))
    l=dict(status='somar_estoque',produto_id='101',estoque='3',categorias='LP, Novo/Lacrado')
    arq=tmp_path/'diario.json'
    somar_estoque(l,loja,gravados.append,arq)
    somar_estoque(l,loja,gravados.append,arq)
    assert chamadas==[('101',99,5)]
    diario=json.loads(arq.read_text());assert diario['antes']==2 and diario['depois']==5
    assert gravados[-1]['status']=='estoque_somado'
    arq.unlink()
    somar_estoque({**l,'cadastro_execucao':json.dumps(diario)},loja,gravados.append,arq)
    assert len(chamadas)==1


def test_soma_incerta_infinito_e_confirmacao(tmp_path):
    def falhar(*a):raise TimeoutError()
    loja=SimpleNamespace(produto=lambda p: {'variants':[{'id':9,'stock':2,'stock_management':True}]},estoque=falhar)
    l=dict(status='somar_estoque',produto_id='101',estoque='3',categorias='Novo/Lacrado')
    arq=tmp_path/'d.json'
    with pytest.raises(TimeoutError):somar_estoque(l,loja,lambda d:None,arq)
    with pytest.raises(ErroCadastro,match='incerta'):somar_estoque(l,loja,lambda d:None,arq)
    arq.unlink()
    with pytest.raises(ErroCadastro,match='confirmação'):somar_estoque(l,loja,lambda d:None,arq,lambda:False)
    assert not arq.exists()
    loja.produto=lambda p:{'variants':[{'stock_management':False,'stock':None}]}
    with pytest.raises(ErroCadastro,match='infinito'):somar_estoque(l,loja,lambda d:None,arq)


def test_barcode_primeiro_ambiguo():
    d=Discogs('ficticio'); chamadas=[]
    def get(path,**params):
        chamadas.append((path,params));return {'results':[{'id':1},{'id':2}],'pagination':{'items':2}}
    d.get=get
    assert d.buscar('Disco',barcode='123')['discogs_confianca']=='baixa'
    assert chamadas==[('/database/search',{'type':'release','barcode':'123'})]


def test_sessao_nao_escapa(tmp_path):
    assert pasta_sessao(tmp_path,'entrada/sessao')==tmp_path/'sessao'
    with pytest.raises(ErroLote):pasta_sessao(tmp_path,'../fora')
    with pytest.raises(ErroLote):pasta_sessao(tmp_path,'processadas/sessao')


def test_lacrado_referencia_capa_rotulo_e_publicacao(tmp_path):
    from scripts.cadastro_lote import derivar_lote
    for nome in ('tulio.jpg','oficial.jpg'):(tmp_path/nome).write_bytes(imagem('red'))
    d=dict(lote='2026-11-05',discos=[dict(acao='cadastrar',formato='lacrado',artista='Banda Fictícia',album='Álbum Fictício',preco_etiqueta=100,discogs_url='https://www.discogs.com/release/1',discogs_confianca='alta',fotos=[dict(arquivo='tulio.jpg',papel='capa'),dict(arquivo='oficial.jpg',papel='oficial')])])
    r=derivar_lote(d,pasta_local=tmp_path,detectar_recortes=False)
    assert [f[2] for f in r['fotos']]==['referencia','oficial']
    assert r['rascunhos_dicts'][0]['publicar']=='sim'
    d['discos'][0]['rotulo_titulo']='Outro disco'
    r=derivar_lote(d,pasta_local=tmp_path,detectar_recortes=False)
    assert 'rótulo do vinil é de outro disco' in r['rascunhos_dicts'][0]['pendencias']
    assert r['rascunhos_dicts'][0]['publicar']=='nao'


def test_arquivar_so_depois_de_gravar_sem_apagar(tmp_path):
    from tests.test_cadastro_lote import _nova_planilha, _lote_base_valido
    from scripts.cadastro_lote import gravar_lote
    entrada=tmp_path/'entrada';entrada.mkdir()
    sessao=entrada/'sessao';sessao.mkdir()
    dados=_lote_base_valido(sessao)
    arq=tmp_path/'lote.json';arq.write_text(json.dumps(dados),encoding='utf-8')
    pg=_nova_planilha()
    sim=gravar_lote(arq,sessao,pg,base_trabalho=tmp_path/'trabalho')
    assert len(list(sessao.glob('*.jpg')))==4
    real=gravar_lote(arq,sessao,pg,confirmar=True,base_trabalho=tmp_path/'trabalho')
    assert not list(sessao.glob('*.jpg'))
    assert len(list((entrada/'processadas'/dados['lote']).glob('*.jpg')))==4
    assert real['gravados']==sim['gravados']


def test_usado_com_cantos_recorta_antes_de_comparar_capa_e_aceita_rotulo(tmp_path):
    from scripts.cadastro_lote import derivar_lote
    import numpy as np
    rng = np.random.default_rng(7)
    arte = rng.integers(30, 220, (200, 200, 3), dtype=np.uint8)
    im_of = Image.fromarray(arte)
    im_of.save(tmp_path / 'oficial.jpg', 'JPEG', quality=95)
    # Foto própria 500x700 com fundo cinza escuro e a capa no centro (x=150..350, y=250..450)
    fundo = np.full((700, 500, 3), 60, dtype=np.uint8)
    fundo[250:450, 150:350] = arte
    Image.fromarray(fundo).save(tmp_path / 'capa_tapete.jpg', 'JPEG', quality=95)
    Image.fromarray(arte).save(tmp_path / 'rotulo.jpg', 'JPEG', quality=95)
    # Sem cantos, o tapete domina o pHash (>18); com cantos, recorta a capa e bate (<=18)
    assert distancia_capas((tmp_path / 'capa_tapete.jpg').read_bytes(), (tmp_path / 'oficial.jpg').read_bytes()) > 18
    d = dict(
        lote='2026-11-05',
        discos=[dict(
            acao='cadastrar', formato='usado', artista='Banda', album='Disco',
            ano=1985, gravadora='Rock Discos', catalogo='RK-001', pais='Brasil',
            capa='VG+', vinil='VG+', preco_etiqueta=130, genero='Classic Rock',
            faixas='Lado A:\n1. Faixa 1\nLado B:\n1. Faixa 2',
            descricao='Texto clássico da banda.\n\n• Capa VG+\n• Vinil VG+', tags='Banda, Disco, LP, LP Usado, Vinil Usado',
            discogs_url='https://www.discogs.com/release/1', discogs_confianca='alta',
            capa_discogs_arquivo='oficial.jpg', rotulo_titulo='Disco',
            fotos=[
                dict(arquivo='capa_tapete.jpg', papel='capa', cantos=[[150, 250], [350, 250], [350, 450], [150, 450]]),
                dict(arquivo='rotulo.jpg', papel='rótulo'),
            ],
        )],
    )
    r = derivar_lote(d, pasta_local=tmp_path, detectar_recortes=True)
    assert r['rascunhos_dicts'][0]['pendencias'] == ''
    assert r['rascunhos_dicts'][0]['publicar'] == 'sim'
    assert [f[2] for f in r['fotos']] == ['capa', 'rótulo']
def test_ordem_explicita_em_foto_permite_capa_interna_depois_do_disco(tmp_path):
    from scripts.cadastro_lote import derivar_lote
    for nome in ('capa.jpg', 'disco.jpg', 'interna.jpg'):
        Image.new('RGB', (500, 500), (120, 120, 120)).save(tmp_path / nome, 'JPEG')
    d = dict(
        lote='2026-11-05',
        discos=[dict(
            acao='cadastrar', formato='usado', artista='Vários', album='Caixa Tripla',
            capa='VG+', vinil='VG+', preco_etiqueta=350, genero='Classic Rock',
            descricao='Caixa com 3 LPs.\n\n• Caixa com 3 LPs\n• Capa VG+\n• Vinil VG+',
            tags='Vários, Caixa Tripla, LP, LP Usado, Vinil Usado',
            fotos=[
                dict(arquivo='capa.jpg', papel='capa', cantos=[[10, 10], [490, 10], [490, 490], [10, 490]]),
                dict(arquivo='disco.jpg', papel='disco', cantos=[[10, 10], [490, 10], [490, 490], [10, 490]]),
                dict(arquivo='interna.jpg', papel='capa interna', ordem=9, cantos=[[10, 10], [490, 10], [490, 490], [10, 490]]),
            ],
        )],
    )
    r = derivar_lote(d, pasta_local=tmp_path, detectar_recortes=True)
    assert [(f[1], f[2]) for f in r['fotos']] == [('1', 'capa'), ('2', 'disco'), ('3', 'capa interna')]
    assert r['rascunhos_dicts'][0]['fotos'] == '01 capa.jpg | 02 disco.jpg | 03 capa interna.jpg'
