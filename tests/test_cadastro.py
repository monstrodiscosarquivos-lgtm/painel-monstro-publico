"""Cadastro/frete: somente loja, Drive e imagens fictícios; nunca escreve na loja real."""
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from PIL import Image
from openpyxl import Workbook

from painel_monstro.config import Config, carregar
from painel_monstro.coletor.discogs import Discogs, normalizar
from painel_monstro.coletor.utm import extrair
from painel_monstro.saidas import cadastro as c, fotos
from painel_monstro.saidas.planilha_google import PlanilhaGoogle
from tests.test_planilha_google import PlanilhaFalsa
from scripts import corrigir_frete as frete


def categorias():
    return [dict(id=1,name={'pt':'LP'},parent=None),dict(id=2,name={'pt':'Usado'},parent=1),
            dict(id=3,name={'pt':'Rock'},parent=2),dict(id=4,name={'pt':'Novidades'},parent=None),
            dict(id=5,name={'pt':'CD'},parent=None),dict(id=6,name={'pt':'Rock'},parent=5),
            dict(id=7,name={'pt':'Usado'},parent=5),dict(id=8,name={'pt':'MPB'},parent=2),dict(id=9,name={'pt':'MPB'},parent=7)]


def linha(**kw):
    return {**{k:'' for k in c.COLUNAS},'id':'disco-teste-1','status':'aprovado',
            'titulo':'LP Artista Exemplo - Álbum (1980) - (Vinil Usado)','categorias':'Rock, Novidades',
            'preco':'120','descricao':'Descrição própria\n\n• Item um\n• Item dois',**kw}


def jpeg(w=500,h=600,exif=None):
    im=Image.new('RGB',(w,h),'white'); b=io.BytesIO()
    im.save(b,'JPEG',**({'exif':exif} if exif else {})); return b.getvalue()


def test_html_paragrafos_listas_escape_e_br():
    assert c.descricao_html('A & B\nsegunda\n\n• <tag>\n• dois\n\nFim') == '<p>A &amp; B<br>segunda</p><ul><li>&lt;tag&gt;</li><li>dois</li></ul><p>Fim</p>'
    assert c.descricao_html('<script>ruim</script>')=='<p>&lt;script&gt;ruim&lt;/script&gt;</p>'


def test_categorias_subcategorias_de_lp_usado_e_novidades():
    assert c.mapa_categorias(categorias(),'Rock, Novidades')==[3,4]
    assert c.mapa_categorias(categorias(),'LP > Usado > Rock, Rock')==[3]
    with pytest.raises(c.ErroCadastro,match='categoria Jazz não existe'): c.mapa_categorias(categorias(),'Jazz')
    # "Usado" existe em LP e em CD: vale o formato da primeira categoria (erro real do Passarim, 16/10/2026)
    assert c.mapa_categorias(categorias(),'LP, Usado, MPB, Novidades')==[1,2,8,4]
    assert c.mapa_categorias(categorias(),'CD, Usado, MPB')==[5,7,9]
    with pytest.raises(c.ErroCadastro,match='sem categorias'): c.mapa_categorias(categorias(),'')


@pytest.mark.parametrize('titulo,ficha,peso', [('LP A - B','','0.5'),('LP A - B','capa dupla','.55'),
    ('LP A - B','2 LP','.8'),('Compacto A - B','','.2'),('CD A - B','','.2'),('Fita K7 A - B','','.17')])
def test_peso_medidas_oculto_estoque_um(titulo,ficha,peso):
    r=c.corpo_produto(linha(titulo=titulo,ficha=ficha),categorias())
    assert r['published'] is False and 'visibility' not in r
    v=r['variants'][0]; assert v['weight']==float(peso) and v['stock']==1
    assert (v['height'],v['width'],v['depth'])==(2.5,32,32)
    assert r['name']['pt']==titulo


@pytest.mark.parametrize('mudanca,erro', [({'preco':''},'sem preço'),({'preco':'nan'},'sem preço'),
    ({'status':'rascunho'},'não aprovada'),({'largura_cm':'.32'},'centímetros'),({'id':''},'id estável')])
def test_corpo_travas(mudanca,erro):
    with pytest.raises(c.ErroCadastro,match=erro): c.corpo_produto(linha(**mudanca),categorias())


def test_faixas_so_entram_na_descricao_com_sim():
    l=linha(faixas='A1 Uma faixa (3:36)\nB1 Outra faixa (4:10)')
    assert 'Lado A' not in c.corpo_produto(l,categorias())['description']['pt']
    l['faixas_na_descricao']='sim'
    assert 'Lado A: Uma faixa (3:36) / Lado B: Outra faixa (4:10)' in c.corpo_produto(l,categorias())['description']['pt']


class Loja:
    def __init__(self): self.posts=[]; self.puts=[]; self.produtos={}; self.falha=False; self.falha_imagem=False; self.falha_put=False; self.eventos=[]
    def categorias(self): return categorias()
    def buscar(self,sku): return next((v for v in self.produtos.values() if v['sku']==sku),None)
    def criar(self,corpo):
        self.posts.append(corpo); self.eventos.append('post')
        p=dict(id=12,published=False,handle={'pt':'disco-ficticio'},sku=corpo['variants'][0]['sku'])
        self.produtos[12]=p
        if self.falha: raise c.ErroCadastro('POST não confirmado')
        return p
    def produto(self,pid): return self.produtos[int(pid)]
    def imagem(self,pid,jpg,pos,nome):
        self.eventos.append('imagem')
        if self.falha_imagem: raise c.ErroCadastro('imagem incerta')
        self.posts.append(('imagem',pos,nome))
    def publicar(self,pid,corpo=None):
        self.eventos.append('put'); self.puts.append((int(pid),corpo or {'published':True}))
        if self.falha_put: raise c.ErroCadastro('PUT não confirmado')
        self.produtos[int(pid)]['published']=True
        return self.produtos[int(pid)]


class Drive:
    def __init__(self): self.baixados=[]; self.copias=[]
    def baixar(self,fid): self.baixados.append(fid); return jpeg()
    def guardar(self,did,nome,conteudo): self.copias.append((did,nome)); return 'copia-ficticia'


def lista_fotos():
    return [dict(ordem='9',papel='etiqueta',arquivo_drive_id='etiqueta'),
            dict(ordem='2',papel='contracapa',arquivo_drive_id='verso'),
            dict(ordem='1',papel='capa',arquivo_drive_id='frente')]


def test_idempotente_id_gravado_antes_das_fotos_etiqueta_fora(tmp_path):
    loja=Loja(); drive=Drive(); l=linha()
    def gravar(d):
        l.update(d)
        if 'produto_id' in d: loja.eventos.append('id_gravado')
    caminho=tmp_path/'cadastro.json'
    c.processar_linha(l,lista_fotos(),loja,drive,gravar,caminho)
    assert l['status']=='publicado' and l['produto_id']=='12'
    assert drive.baixados==['frente','verso']
    assert loja.eventos.index('id_gravado')<loja.eventos.index('imagem')
    assert len([p for p in loja.posts if isinstance(p,dict)])==1
    l['status']='aprovado'
    c.processar_linha(l,lista_fotos(),loja,drive,gravar,caminho)
    assert len(loja.posts)==3  # um produto e duas fotos, nunca repete


def test_resposta_perdida_recupera_sku_sem_segundo_post_mesmo_sem_cache(tmp_path):
    loja=Loja(); loja.falha=True; l=linha(); drive=Drive(); caminho=tmp_path/'cadastro.json'
    with pytest.raises(c.ErroCadastro): c.processar_linha(l,lista_fotos(),loja,drive,l.update,caminho)
    assert 'post_iniciado' in l['cadastro_execucao'] and not l['produto_id']
    caminho.unlink()  # simula expiração do cache do Actions, diário na planilha continua
    loja.falha=False
    c.processar_linha(l,lista_fotos(),loja,drive,l.update,caminho)
    assert l['status']=='publicado' and len([p for p in loja.posts if isinstance(p,dict)])==1


def test_ambiguidade_nao_encontrada_bloqueia_repost_e_imagem_incerta(tmp_path):
    l=linha(cadastro_execucao=json.dumps({'post_iniciado':True}))
    loja=Loja()
    with pytest.raises(c.ErroCadastro,match='incerto'): c.processar_linha(l,lista_fotos(),loja,Drive(),l.update,tmp_path/'x.json')
    assert not loja.posts
    l=linha(); loja=Loja(); loja.falha_imagem=True
    with pytest.raises(c.ErroCadastro): c.processar_linha(l,lista_fotos(),loja,Drive(),l.update,tmp_path/'b.json')
    loja.falha_imagem=False
    with pytest.raises(c.ErroCadastro,match='imagem anterior incerta'): c.processar_linha(l,lista_fotos(),loja,Drive(),l.update,tmp_path/'b.json')
    assert len([p for p in loja.posts if isinstance(p,dict)])==1


def test_sem_aprovacao_id_existente_ou_aprovacao_revogada_nunca_post(tmp_path):
    loja=Loja()
    for l in [linha(status='rascunho'),linha(produto_id='999')]:
        c.processar_linha(l,lista_fotos(),loja,Drive(),l.update,tmp_path/'x.json')
    l=linha()
    with pytest.raises(c.ErroCadastro,match='aprovação alterada'):
        c.processar_linha(l,lista_fotos(),loja,Drive(),l.update,tmp_path/'y.json',confirmar=lambda:False)
    assert loja.posts==[]


@pytest.mark.parametrize('cantos,esperado', [('',(1333,1600)),
    ('[[10,10],[490,10],[490,490],[10,490]]',(1600,1600)),
    ('[[10,10],[490,10],[490,490],[10,490],2]',(1600,800)),
    ('[[10,10],[490,10],[490,490],[10,490],2,"ccw"]',(800,1600))])
def test_fotos_com_sem_cantos_proporcao_e_giro(cantos,esperado):
    original=jpeg(); saida=fotos.processar(original,'capa',cantos)
    im=Image.open(io.BytesIO(saida)); assert im.size==esperado and im.format=='JPEG'
    assert original==jpeg()  # nenhuma alteração dos bytes originais


def test_exif_rotulo_disco_fallback_e_circulo(monkeypatch):
    exif=Image.Exif(); exif[274]=6
    im=Image.open(io.BytesIO(fotos.processar(jpeg(exif=exif),'capa')))
    assert im.width==1600 and im.height==1333
    monkeypatch.setattr(fotos.cv2,'HoughCircles',lambda *a,**kw:None)
    assert Image.open(io.BytesIO(fotos.processar(jpeg(),'disco'))).size==(1600,1600)
    assert Image.open(io.BytesIO(fotos.processar(jpeg(),'rótulo'))).size==(1600,1600)
    import numpy as np
    monkeypatch.setattr(fotos.cv2,'HoughCircles',lambda *a,**kw:np.array([[[250,250,200]]],dtype='float32'))
    assert Image.open(io.BytesIO(fotos.processar(jpeg(),'disco'))).size==(1600,1600)


@pytest.mark.parametrize('cantos',list(json.loads(Path('referencia/cadastro_piloto/cantos-2026-10-15.json').read_text()).values()))
def test_todos_cantos_do_piloto_equivalentes_sem_copiar_fotos(cantos):
    from referencia.cadastro_piloto import processar as piloto
    original=jpeg(500,900)
    # Usa figura sintética com gradiente para conferir perspectiva, margens e giro, não uma foto real.
    import numpy as np
    im=Image.fromarray(np.indices((900,500)).sum(axis=0).astype('uint8'))
    b=io.BytesIO(); im.convert('RGB').save(b,'JPEG'); original=b.getvalue()
    rgb=np.array(Image.open(io.BytesIO(original)).convert('RGB'))
    esperado=piloto.warp(fotos.cv2.cvtColor(rgb,fotos.cv2.COLOR_RGB2BGR),cantos)
    ok,bytes_ref=fotos.cv2.imencode('.jpg',esperado,[fotos.cv2.IMWRITE_JPEG_QUALITY,86])
    assert ok and fotos.processar(original,'capa',cantos)==bytes_ref.tobytes()


class Resp:
    def __init__(self,d,headers=None,status=200): self.d=d; self.headers=headers or {}; self.status_code=status
    def json(self): return self.d
class Sessao:
    def __init__(self,rs): self.rs=iter(rs); self.chamadas=[]
    def get(self,url,**kw): self.chamadas.append((url,kw)); return next(self.rs)


@pytest.mark.parametrize('resultados,confirma',[([],False),([{'id':3}],True),([{'id':3},{'id':4}],False),
    ([{'id':3,'catno':'ABC-1'},{'id':4,'catno':'XYZ'}],True)])
def test_discogs_zero_um_varios_e_catalogo(resultados,confirma):
    rs=[Resp({'results':resultados})]
    if not resultados: rs.append(Resp({'results':[]}))
    if confirma: rs += [Resp({'tracklist':[{'position':'A1','title':'Faixa','duration':'3:36'}],
                                  'extraartists':[{'role':'Producer','name':'Exemplo'}]}),
                        Resp({'lowest_price':{'currency':'BRL','value':50},'num_for_sale':2})]
    s=Sessao(rs); d=Discogs('token-ficticio',s,dormir=lambda _:None,relogio=lambda:0).buscar('A - B','ABC-1')
    assert d['discogs_confianca']==('alta' if confirma else 'baixa')
    assert 'images' not in d
    if confirma: assert d['faixas']=='A1 Faixa (3:36)' and d['discogs_menor_preco']==50


def test_discogs_url_limite_e_paginacao_nao_confunde_um_resultado():
    s=Sessao([Resp({'tracklist':[]},headers={'X-Discogs-Ratelimit-Remaining':'0'}),Resp({})]); esperas=[]
    d=Discogs('token-ficticio',s,dormir=esperas.append,relogio=lambda:0).buscar('',url='https://www.discogs.com/release/123-Exemplo')
    assert d['discogs_id']=='123' and esperas==[0,60]
    s=Sessao([Resp({'results':[{'id':3}],'pagination':{'items':40}})])
    assert Discogs('x',s,dormir=lambda _:None).buscar('Título')['discogs_confianca']=='baixa'


def test_preco_mediana_titulo_acentos_e_fallback_24_meses():
    ps=pd.DataFrame([dict(nome='LP Artista Exemplo - Álbum (Vinil Usado)',preco=100,criado_em='2026-01-01'),
                     dict(nome='LP Artista Exemplo - Album (1980) - (Vinil Usado)',preco=200,criado_em='2025-01-01'),
                     dict(nome='LP Artista Exemplo - Outro (Vinil Usado)',preco=300,criado_em='2020-01-01')])
    assert c.preco_referencia(linha()['titulo'],ps,pd.Timestamp('2026-10-15').date())==150
    assert c.preco_referencia('LP Artista Exemplo - Desconhecido',ps,pd.Timestamp('2026-10-15').date())==150
    assert c.preco_referencia('LP Outro Artista - Álbum',ps,pd.Timestamp('2026-10-15').date())==''
    assert c.corpo_produto(linha(preco_referencia=999),categorias())['variants'][0]['price']=='120.00'


@pytest.mark.parametrize('url,ref,origem',[('?utm_source=brevo','','email'),('?utm_medium=email','','email'),
    ('?fbclid=segredo','','meta_ads'),('?utm_source=instagram&utm_medium=cpc','','meta_ads'),
    ('?utm_source=instagram','','instagram_organico'),('?gclid=segredo','','google'),
    ('?utm_source=whatsapp','','whatsapp'),('','','direto/organico')])
def test_parser_utm_isolado(url,ref,origem):
    assert extrair('https://exemplo.com/'+url,ref)['origem']==origem
    d=extrair('https://exemplo.com/?email=a@exemplo.com&token=segredo&utm_content=a%40exemplo.com')
    assert d['utm_content']=='' and 'token' not in d and 'email' not in d


def test_headers_nao_reordenam_piloto_e_colunas_so_no_fim():
    p=PlanilhaGoogle(PlanilhaFalsa())
    p.substituir(c.ABA,pd.DataFrame([{k:linha(status='rascunho').get(k,'') for k in c.BASE}],columns=c.BASE))
    antes=p._ss.worksheet(c.ABA).get_all_values()[1]
    c.preparar_abas(p); c.preparar_abas(p)
    v=p._ss.worksheet(c.ABA).get_all_values()
    assert v[0]==c.COLUNAS and v[1][:len(c.BASE)]==antes
    assert p._ss.worksheet('cadastro_fotos').get_all_values()==[c.FOTOS]


def test_rascunho_sem_preco_pendencia_mas_nunca_aprova_ou_troca_etiqueta():
    p=PlanilhaGoogle(PlanilhaFalsa())
    p.substituir(c.ABA,pd.DataFrame([linha(status='rascunho',preco='')],columns=c.COLUNAS))
    res=c.passo_rotina(Config(),p,SimpleNamespace(produtos=pd.DataFrame()),'dados/api-ficticia')
    l=dict(zip(c.COLUNAS,p._ss.worksheet(c.ABA).get_all_values()[1]))
    assert l['status']=='rascunho' and l['preco']=='' and 'conferir preço' in l['pendencias']
    assert res['rascunhos']==1


def test_frete_parser_so_sim_e_medidas_sem_preco(tmp_path):
    wb=Workbook(); ws=wb.active
    ws.append(['Produto','Link','Autoriza? (Sim/Não)',*frete.CAMPOS.values()])
    ws.append(['Exemplo','https://lojamonstro.com.br/produtos/exemplo/','Não',.5,2.5,32,32])
    ws.append(['Exemplo','https://lojamonstro.com.br/produtos/outro/','Sim',.55,2.5,32,32])
    arq=tmp_path/'ficticia.xlsx'; wb.save(arq)
    r=frete.ler_propostas(arq)
    assert len(r)==1 and r[0]['handle']=='outro' and set(r[0]['proposta'])==set(frete.CAMPOS)
    with pytest.raises(ValueError,match='autorização'): frete.executar(None,[],tmp_path/'x',aplicar=True)


def test_token_discogs_secreto_e_frete_fora_do_workflow(tmp_path):
    e=tmp_path/'env'; e.write_text('DISCOGS_TOKEN=segredo-discogs-ficticio',encoding='utf-8')
    cfg=carregar(str(e))
    assert cfg.discogs_token=='segredo-discogs-ficticio' and cfg.discogs_token not in repr(cfg)
    workflow=Path('.github/workflows/rotina.yml').read_text()
    assert 'DISCOGS_TOKEN: ${{ secrets.DISCOGS_TOKEN }}' in workflow
    assert 'corrigir_frete' not in workflow and '--aplicar' not in workflow


def test_rascunho_tem_previa_sem_criar_produto(tmp_path):
    p=PlanilhaGoogle(PlanilhaFalsa())
    p.substituir(c.ABA,pd.DataFrame([linha(status='rascunho')],columns=c.COLUNAS))
    fs=[dict(id_disco='disco-teste-1',**f) for f in lista_fotos()]
    p.substituir('cadastro_fotos',pd.DataFrame(fs,columns=c.FOTOS))
    drive=Drive()
    res=c.passo_rotina(Config(),p,SimpleNamespace(produtos=pd.DataFrame()),tmp_path,drive=drive)
    l=dict(zip(c.COLUNAS,p._ss.worksheet(c.ABA).get_all_values()[1]))
    assert l['status']=='rascunho' and not l['produto_id'] and res['criados']==0
    assert len(json.loads(l['fotos_ajustadas']))==2 and 'etiqueta' not in drive.baixados


def test_frete_simulacao_e_aplicacao_ficticias_so_quatro_campos(tmp_path,monkeypatch):
    # Redireciona raiz do relatório para tmp_path, sem credenciais ou rede.
    monkeypatch.setattr(frete,'__file__',str(tmp_path/'scripts'/'corrigir_frete.py'))
    calls=[]
    class Api:
        _base='https://exemplo.com'; _cabecalhos={}
        def _get(self,url): return Resp([dict(id=5,weight=.2,height=.32,width=.32,depth=.32,price=999,stock=8)])
        def _esperar_vaga(self): pass
        def _guardar_limites(self,r): pass
        def put(self,url,**kw):
            assert (tmp_path/'dados'/'relatorio.json').exists()
            calls.append(kw['json']); return Resp(kw['json'])
    api=Api(); api._sessao=api
    propostas=[dict(produto_id='12',proposta=dict(weight=.5,height=2.5,width=32,depth=32))]
    destino=tmp_path/'dados'/'relatorio.json'
    frete.executar(api,propostas,destino)
    assert calls==[] and json.loads(destino.read_text())[0]['antes']['height']==.32
    frete.executar(api,propostas,destino,True,frete.FRASE)
    assert len(calls)==1 and set(calls[0])==set(frete.CAMPOS)


def test_cliente_escrita_impede_publicar_e_endpoints_alheios():
    loja=c.LojaCadastro(None)
    with pytest.raises(c.ErroCadastro,match='oculto'): loja.criar({'published':True})
    with pytest.raises(c.ErroCadastro,match='bloqueada'): loja._post('customers',{})


def test_drive_upload_copia_privada_multipart_related(monkeypatch):
    drive=object.__new__(c.DriveFotos); drive.raiz='raiz'
    monkeypatch.setattr(drive,'pasta',lambda pai,nome: nome)
    monkeypatch.setattr(drive,'listar',lambda q: [])
    calls=[]
    def request(metodo,caminho,**kw):
        calls.append((metodo,caminho,kw)); return Resp({'id':'copia'})
    monkeypatch.setattr(drive,'request',request)
    assert drive.guardar('disco-ficticio','foto.jpg',b'JPEG-FICTICIO')=='copia'
    metodo,url,kw=calls[0]
    assert metodo=='POST' and url=='/upload/drive/v3/files'
    assert kw['headers']['Content-Type'].startswith('multipart/related; boundary=')
    assert b'JPEG-FICTICIO' in kw['data'] and b'"parents": ["disco-ficticio"]' in kw['data']


class DriveNomes(Drive):
    entrada='entrada-ficticia'
    def __init__(self,arquivos): super().__init__(); self.arquivos=arquivos; self.buscas=[]
    def listar(self,q): self.buscas.append(q); return self.arquivos


def planilha_fotos_por_nome(fs,status='rascunho',**campos):
    p=PlanilhaGoogle(PlanilhaFalsa())
    p.substituir(c.ABA,pd.DataFrame([linha(status=status,**campos)],columns=c.COLUNAS))
    fs=[{'id_disco':'disco-teste-1',**f} for f in fs]
    p.substituir('cadastro_fotos',pd.DataFrame(fs,columns=c.FOTOS).fillna(''))
    aba=p._ss.worksheet('cadastro_fotos')
    def batch_update(mudancas,raw=True):
        for m in mudancas: aba.update(m['values'],m['range'],raw=raw)
    aba.batch_update=batch_update
    return p,[dict(zip(c.FOTOS,r)) for r in c.ler(p,'cadastro_fotos')[1:]]


def test_resolver_nome_exato_salva_so_id_e_preserva_ids_preenchidos():
    p,fs=planilha_fotos_por_nome([
        dict(ordem='1',papel='capa',observacao="Capa d'Álbum.JPG",cantos='[]'),
        dict(ordem='2',papel='contracapa',arquivo_drive_id='id-existente',observacao='não mudar'),
        dict(ordem='3',papel='etiqueta',observacao='Etiqueta.JPG')])
    antes=c.ler(p,'cadastro_fotos')
    drive=DriveNomes([dict(id='id-capa',name="Capa d'Álbum.JPG"),dict(id='id-etiqueta',name='Etiqueta.JPG')])
    resultado=c.resolver_fotos(p,drive,fs)
    depois=c.ler(p,'cadastro_fotos')
    assert [f['arquivo_drive_id'] for f in resultado]==['id-capa','id-existente','id-etiqueta']
    assert drive.buscas==["'entrada-ficticia' in parents"]
    assert p._ss.worksheet('cadastro_fotos').chamadas_update[-2:]==['D2','D4']
    for original,atual in zip(antes[1:],depois[1:]):
        assert original[:3]+original[4:]==atual[:3]+atual[4:]
    c.resolver_fotos(p,drive,resultado)
    assert len(drive.buscas)==1  # preenchido nunca é buscado/substituído de novo


@pytest.mark.parametrize('nome,arquivos,motivo',[
    ('foto.JPG',[],'não encontrado'),
    ('foto.JPG',[dict(id='1',name='foto.JPG'),dict(id='2',name='foto.JPG')],'repetido'),
    ('foto.JPG',[dict(id='1',name='FOTO.JPG')],'não encontrado'),
    (' foto.JPG',[dict(id='1',name='foto.JPG')],'não encontrado'),
    ('',[],'nome ausente'),
])
@pytest.mark.parametrize('status',['rascunho','aprovado'])
def test_nome_ausente_ou_repetido_vira_pendencia_sem_produto(tmp_path,nome,arquivos,motivo,status):
    p,fs=planilha_fotos_por_nome([dict(ordem='1',papel='capa',observacao=nome)],status,
                              pendencias='conferir vinil')
    drive=DriveNomes(arquivos)
    p.substituir('Configuração',pd.DataFrame([['Cadastro: pasta de entrada Drive (ID)',drive.entrada,'']],columns=['Parâmetro','Valor','Ajuda']))
    res=c.passo_rotina(Config(),p,SimpleNamespace(produtos=pd.DataFrame()),tmp_path,drive=drive)
    atual=dict(zip(c.COLUNAS,c.ler(p,c.ABA)[1]))
    assert atual['status']==status and not atual['produto_id'] and not atual['cadastro_execucao']
    assert motivo in atual['pendencias'] and 'conferir vinil' in atual['pendencias']
    assert res['erros']==1 and res['criados']==0 and drive.baixados==[] and drive.copias==[]
    assert not c.ler(p,'cadastro_fotos')[1][3]


def test_nao_grava_parcial_se_outra_foto_do_disco_esta_ausente():
    p,fs=planilha_fotos_por_nome([dict(ordem='1',papel='capa',observacao='ok.JPG'),
                               dict(ordem='2',papel='etiqueta',observacao='ausente.JPG')])
    antes=c.ler(p,'cadastro_fotos')
    with pytest.raises(c.PendenciaFotos,match='ausente.JPG'):
        c.resolver_fotos(p,DriveNomes([dict(id='encontrado',name='ok.JPG')]),fs)
    assert c.ler(p,'cadastro_fotos')==antes


def test_resolucao_preserva_edicao_concorrente():
    p,fs=planilha_fotos_por_nome([dict(ordem='1',papel='capa',observacao='foto.JPG')])
    p._ss.worksheet('cadastro_fotos').update([['outro-id-manual']],'D2')
    with pytest.raises(c.PendenciaFotos,match='alterada'):
        c.resolver_fotos(p,DriveNomes([dict(id='id-encontrado',name='foto.JPG')]),fs)
    assert c.ler(p,'cadastro_fotos')[1][3]=='outro-id-manual'


@pytest.mark.parametrize('status',['rascunho','aprovado'])
def test_resolve_na_rotina_antes_de_previa_ou_produto_e_remove_so_pendencia_propria(tmp_path,monkeypatch,status):
    p,fs=planilha_fotos_por_nome([dict(ordem='1',papel='capa',observacao='foto.JPG')],status,
                              pendencias='conferir vinil\nFotos por nome: arquivo não encontrado: foto.JPG')
    drive=DriveNomes([dict(id='id-encontrado',name='foto.JPG')]); loja=Loja()
    monkeypatch.setattr(c,'LojaCadastro',lambda _:loja)
    p.substituir('Configuração',pd.DataFrame([['Cadastro: pasta de entrada Drive (ID)',drive.entrada,'']],columns=['Parâmetro','Valor','Ajuda']))
    res=c.passo_rotina(Config(),p,SimpleNamespace(produtos=pd.DataFrame()),tmp_path,api=object(),drive=drive)
    atual=dict(zip(c.COLUNAS,c.ler(p,c.ABA)[1]))
    assert c.ler(p,'cadastro_fotos')[1][3]=='id-encontrado' and drive.baixados==['id-encontrado']
    assert atual['pendencias']=='conferir vinil'
    if status=='rascunho': assert atual['status']=='rascunho' and loja.posts==[]
    else: assert atual['status']=='publicado' and res['criados']==1 and loja.posts[0]['published'] is False


def test_busca_na_entrada_percorre_paginas_e_exclui_lixeira():
    drive=object.__new__(c.DriveFotos); chamadas=[]
    respostas=iter([Resp({'files':[dict(id='1',name='foto.JPG')],'nextPageToken':'pagina-2'}),
                    Resp({'files':[dict(id='2',name='foto.JPG')]})])
    def request(metodo,url,**kw): chamadas.append(kw['params']); return next(respostas)
    drive.request=request
    arquivos=drive.listar("'entrada-ficticia' in parents")
    assert len(arquivos)==2 and all(x['q']=="'entrada-ficticia' in parents and trashed = false" for x in chamadas)
    assert chamadas[1]['pageToken']=='pagina-2'


class DriveSemCota(Drive):
    def guardar(self,did,nome,conteudo): raise c.ErroCadastro('Drive 403 storageQuotaExceeded; conferir permissão e espaço da conta de serviço')


def test_copia_no_drive_e_opcional_a_loja_recebe_as_fotos_mesmo_assim(capsys):
    ajustadas,refs=c.ajustar_fotos('disco-1',lista_fotos(),DriveSemCota())
    assert [p for p,_,_ in ajustadas]==[1,2] and all(jpg for _,_,jpg in ajustadas)
    assert [r['arquivo_drive_id'] for r in refs]==['','']
    saida = capsys.readouterr().out
    assert 'cópia ajustada não guardada no Drive' in saida
    assert 'storageQuotaExceeded' not in saida


def test_aviso_de_fotos_aparece_uma_vez_e_some_quando_resolve():
    assert c.sem_aviso_fotos('Faltam fotos.; conferir fotos/Drive; conferir fotos/Drive (Drive 403 x)')=='Faltam fotos.'
    assert c.sem_aviso_fotos('conferir fotos/Drive; conferir fotos/Drive')==''
    assert c.sem_aviso_fotos('A; B')=='A; B'


@pytest.mark.parametrize('titulo,cats,estoque,esperado', [
    ('LP Green Day - Dookie (Novo/Lacrado)', 'LP, Novo/Lacrado', '3', 3),
    ('LP Green Day - Dookie (Novo/Lacrado)', 'LP, Novo/Lacrado', '', 1),
    ('LP A - B (Vinil Usado)', 'LP, Usado, Rock', '5', 1),          # usado é sempre exemplar único
    ('LP A - B (Novo/Lacrado)', 'LP, Novo/Lacrado', '5000', 999)])
def test_estoque_lacrado_usa_coluna_e_usado_e_sempre_um(titulo, cats, estoque, esperado):
    l = linha(titulo=titulo)
    l.update(categorias=cats, estoque=estoque)
    assert c.estoque_da_linha(l) == esperado


def test_novo_lacrado_repetido_vale_o_ramo_do_formato():
    # Erro real da fita Goiânia Rock City 2026 (21/10/2026): Novo/Lacrado existe em LP e em Fitas Cassete
    cats = [dict(id=1,name={'pt':'LP'},parent=None),dict(id=2,name={'pt':'Novo/Lacrado'},parent=1),
            dict(id=10,name={'pt':'Fitas Cassete'},parent=None),dict(id=11,name={'pt':'Novo/Lacrado'},parent=10),
            dict(id=12,name={'pt':'Usado'},parent=10),dict(id=13,name={'pt':'Usado'},parent=1),dict(id=20,name={'pt':'Pré Venda'},parent=None),
            dict(id=21,name={'pt':'Pré-Venda'},parent=None)]
    assert c.mapa_categorias(cats,'Fitas Cassete, Novo/Lacrado, Pré Venda')==[10,11,20]
    assert c.mapa_categorias(cats,'LP, Novo/Lacrado')==[1,2]
    assert c.mapa_categorias(cats,'Fitas Cassete, Usado')==[10,12]
    assert c.mapa_categorias(cats,'LP, Novo/Lacrado, Pré-Venda, Pré Venda')==[1,2,21,20]


@pytest.mark.parametrize('val',['','sim','SIM'])
def test_publicar_vazio_ou_sim_publica_so_depois_da_ultima_imagem(tmp_path,val):
    loja=Loja(); drive=Drive(); l=linha(publicar=val)
    def gravar(d):
        l.update(d)
        if 'produto_id' in d: loja.eventos.append('id_gravado')
    c.processar_linha(l,lista_fotos(),loja,drive,gravar,tmp_path/f'cad-{val or "vazio"}.json')
    assert l['status']=='publicado' and l['link_loja'].endswith('/disco-ficticio')
    assert loja.eventos==['post','id_gravado','imagem','imagem','put']
    assert loja.puts==[(12,{'published':True})]
    est=json.loads(l['cadastro_execucao'])
    assert est.get('publicacao_pedida') is True and est.get('publicado') is True


@pytest.mark.parametrize('val',['nao','não','NAO'])
def test_publicar_nao_mantem_oculto_sem_put(tmp_path,val):
    loja=Loja(); drive=Drive(); l=linha(publicar=val)
    c.processar_linha(l,lista_fotos(),loja,drive,l.update,tmp_path/f'cad-{val}.json')
    assert l['status']=='criado' and loja.puts==[] and 'put' not in loja.eventos
    assert loja.produtos[12]['published'] is False


def test_falha_no_put_mantem_criado_registra_pendencia_e_nao_repete(tmp_path):
    loja=Loja(); loja.falha_put=True; drive=Drive(); l=linha(publicar='sim')
    caminho=tmp_path/'cad-falha.json'
    c.processar_linha(l,lista_fotos(),loja,drive,l.update,caminho)
    assert l['status']=='criado' and len(loja.puts)==1
    assert 'Não consegui deixar visível; publique à mão na Nuvemshop' in l['pendencias']
    est=json.loads(l['cadastro_execucao'])
    assert est.get('publicacao_pedida') is True and not est.get('publicado')
    # Se tentar rodar de novo sem confirmar na loja, não repete o PUT
    loja.falha_put=False; l['status']='aprovado'
    c.processar_linha(l,lista_fotos(),loja,drive,l.update,caminho)
    assert l['status']=='criado' and len(loja.puts)==1
    assert l['pendencias'].count('Não consegui deixar visível; publique à mão na Nuvemshop')==1


def test_retomada_com_publicacao_pedida_nao_trava_se_ja_visivel_e_sem_ela_trava(tmp_path):
    # Com publicacao_pedida e produto já visível na Nuvemshop: reconhece e conclui como publicado sem novo PUT
    loja=Loja(); loja.produtos[12]=dict(id=12,published=True,handle={'pt':'disco-ficticio'},sku=c.sku_da_linha('disco-teste-1'))
    est={'produto_id':'12','publicacao_pedida':True,'imagens':{'1':True,'2':True}}
    l=linha(produto_id='12',cadastro_execucao=json.dumps(est))
    c.processar_linha(l,lista_fotos(),loja,Drive(),l.update,tmp_path/'retomada.json')
    assert l['status']=='publicado' and loja.puts==[]
    assert json.loads(l['cadastro_execucao']).get('publicado') is True
    # Sem publicacao_pedida: produto visível continua travando por segurança
    l2=linha(produto_id='12',cadastro_execucao=json.dumps({'produto_id':'12'}))
    with pytest.raises(c.ErroCadastro,match='visível; interrompido'):
        c.processar_linha(l2,lista_fotos(),loja,Drive(),l2.update,tmp_path/'trava.json')


def test_put_so_aceita_published_true_em_products_id():
    puts=[]
    class ApiFalsa:
        _base='https://api.tiendanube.com/v1/123'; _cabecalhos={}
        def _esperar_vaga(self): pass
        def _guardar_limites(self,r): pass
        def put(self,url,**kw):
            puts.append((url,kw.get('json'))); return Resp({'id':12,'published':True})
    api=ApiFalsa(); api._sessao=api
    loja=c.LojaCadastro(api)
    assert loja.publicar(12)=={'id':12,'published':True}
    assert puts==[('https://api.tiendanube.com/v1/123/products/12',{'published':True})]
    with pytest.raises(c.ErroCadastro,match='bloqueado'):
        loja.publicar(12,{'published':False})
    with pytest.raises(c.ErroCadastro,match='bloqueado'):
        loja.publicar(12,{'published':True,'price':'10'})
    with pytest.raises(c.ErroCadastro,match='bloqueado'):
        loja._put('orders/12',{'published':True})
    with pytest.raises(c.ErroCadastro,match='bloqueado'):
        loja._put('products/12/variants/1',{'published':True})

