"""D-067: rascunho revisado gera exemplar novo, oculto e com estoque 1 (usado sempre 1; lacrado usa a coluna `estoque`, D-073).

Cliente de escrita separado do coletor GET. Nunca altera produto existente.
POST ambíguo não é repetido; reconcilia pelo SKU estável e mantém trava durável.
"""
import base64
import hashlib
import html
import json
import math
from pathlib import Path
import re
import statistics
import time
import unicodedata
import uuid

import gspread
import pandas as pd
import requests
from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

from painel_monstro.config import RAIZ_PROJETO
from painel_monstro.coletor.discogs import Discogs, ErroDiscogs
from painel_monstro.coletor.nuvemshop_api import NuvemshopAPI, _pt
from painel_monstro.saidas import fotos
from painel_monstro.saidas.planilha_google import _letra

ABA='cadastro_rascunhos'
BASE='id lote pasta status titulo marca categorias ficha descricao capa vinil preco preco_referencia peso_kg altura_cm largura_cm comprimento_cm discogs_url discogs_confianca pendencias fotos seo_titulo seo_descricao tags produto_id link_loja observacao_tulio atualizado_em'.split()
EXTRAS='discogs_id faixas creditos discogs_menor_preco discogs_a_venda faixas_na_descricao preco_origem cadastro_execucao fotos_ajustadas estoque publicar'.split()
COLUNAS=BASE+EXTRAS
FOTOS='id_disco ordem papel arquivo_drive_id cantos observacao'.split()


class ErroCadastro(Exception):
    pass


class PendenciaFotos(ErroCadastro):
    """Bloqueia o disco sem mudar sua aprovação nem apagar pendências manuais."""


def pendencias_sem_busca_fotos(texto):
    return '\n'.join(l for l in str(texto or '').splitlines() if not l.startswith('Fotos por nome: '))


def sem_aviso_fotos(texto):
    """Tira os avisos automáticos 'conferir fotos/Drive...' (repetidos por versões antigas da rotina)."""
    return re.sub(r'^(?:;\s*)+|(?:;\s*)+$','',re.sub(r'(?:;\s*)?conferir fotos/Drive(?: \([^)]*\))?','',str(texto or ''))).strip()


def numero(v):
    try:
        s=str(v).strip().replace('R$','').replace(' ','')
        if ',' in s: s=s.replace('.','').replace(',','.')
        n=float(s)
        if math.isfinite(n) and n>0: return n
    except (ValueError,TypeError): pass
    return None


def texto_normal(v):
    return re.sub(r'[^a-z0-9]+',' ',unicodedata.normalize('NFKD',str(v or '')).encode('ascii','ignore').decode().lower()).strip()


def descricao_html(texto):
    blocos=[]; linhas=[]; lista=[]
    def fechar():
        if linhas: blocos.append('<p>'+'<br>'.join(linhas)+'</p>'); linhas.clear()
        if lista: blocos.append('<ul>'+''.join('<li>'+x+'</li>' for x in lista)+'</ul>'); lista.clear()
    for l in str(texto or '').splitlines():
        l=l.strip()
        if not l: fechar()
        elif l.startswith('• '):
            if linhas: fechar()
            lista.append(html.escape(l[2:]))
        else:
            if lista: fechar()
            linhas.append(html.escape(l))
    fechar()
    return ''.join(blocos)


def mapa_categorias(categorias, nomes):
    por_id={int(c['id']):c for c in categorias}
    def caminho(c, vistos=()):
        if c['id'] in vistos: raise ErroCadastro('árvore de categorias inválida')
        pai=por_id.get(int(c.get('parent') or 0))
        return (caminho(pai,(*vistos,c['id']))+' > ' if pai else '')+str(_pt(c.get('name')))
    caminhos={cid:caminho(c) for cid,c in por_id.items()}
    ids=[]
    lista=[x.strip() for x in str(nomes).split(',') if x.strip()]
    # Nome repetido na árvore (Usado e Novo/Lacrado existem em LP, CD, Fitas Cassete...): vale o ramo do formato
    # do produto (primeira categoria da linha), primeiro "Formato > Usado", depois qualquer "Formato > ...".
    ramos=[texto_normal(lista[0])+' usado ' if lista else '',texto_normal(lista[0])+' ' if lista else '','lp usado ']
    for nome in lista:
        exatos=[cid for cid,path in caminhos.items() if texto_normal(path)==texto_normal(nome)]
        # Nome escrito igualzinho vale primeiro ("Pré Venda" e "Pré-Venda" são categorias diferentes na loja)
        literais=[cid for cid,c in por_id.items() if nome.lower() in (str(_pt(c.get('name'))).strip().lower(), caminhos[cid].lower())]
        matches=literais or exatos or [cid for cid,c in por_id.items() if texto_normal(_pt(c.get('name')))==texto_normal(nome)]
        for ramo in ramos:
            if len(matches)<=1 or not ramo.strip(): continue
            no_ramo=[cid for cid in matches if (texto_normal(caminhos[cid])+' ').startswith(ramo)]
            if no_ramo: matches=no_ramo
        if len(matches)!=1:
            raise ErroCadastro('categoria '+nome+(' não existe' if not matches else ' é ambígua'))
        if matches[0] not in ids: ids.append(matches[0])
    if not ids: raise ErroCadastro('sem categorias')
    return ids


def identidade_titulo(titulo):
    t=re.sub(r'\([^)]*(?:usad|lacrad|novo)[^)]*\)','',str(titulo),flags=re.I)
    t=re.sub(r'^\s*(?:LP|CD|K7|Compacto|Fita)\s+','',t,flags=re.I)
    t=re.sub(r'\(\d{4}\)','',t)
    partes=re.split(r'\s[-–—]\s',t,maxsplit=1)
    return tuple(texto_normal(x.strip(' -')) for x in partes) if len(partes)==2 else ('',texto_normal(t))


def preco_referencia(titulo, produtos, hoje):
    artista,album=identidade_titulo(titulo)
    exatos=[]; por_artista=[]
    for p in produtos.to_dict('records'):
        preco=numero(p.get('preco'))
        if not preco: continue
        a,b=identidade_titulo(p.get('nome',''))
        if a==artista and b==album: exatos.append(preco)
        d=pd.to_datetime(p.get('criado_em'),errors='coerce',utc=True)
        if a==artista and artista and 'usad' in str(p.get('nome','')+' '+str(p.get('categorias',''))).lower() and pd.notna(d) and d>=pd.Timestamp(hoje,tz='UTC')-pd.DateOffset(months=24):
            por_artista.append(preco)
    valores=exatos or por_artista
    return statistics.median(valores) if valores else ''


def peso_padrao(linha):
    n=texto_normal(' '.join(str(linha.get(k,'')) for k in ('titulo','ficha','descricao')))
    if re.match(r'^cd\b',n): return .20
    if re.match(r'^(fita|k7)\b',n): return .17
    if re.match(r'^compacto\b',n): return .20
    if re.search(r'lp duplo|2\s*lp|disco duplo',n): return .80
    if any(x in n for x in ('capa dupla','encarte grosso','gatefold')): return .55
    return .50


def sku_da_linha(id_disco):
    return 'CAD'+hashlib.sha256(str(id_disco).encode()).hexdigest()[:24].upper()


def corpo_produto(linha, categorias):
    if linha.get('status')!='aprovado': raise ErroCadastro('linha não aprovada')
    if not str(linha.get('id','')).strip(): raise ErroCadastro('sem id estável')
    preco=numero(linha.get('preco'))
    if not preco: raise ErroCadastro('sem preço')
    if not str(linha.get('titulo','')).strip(): raise ErroCadastro('sem título')
    for k in ('altura_cm','largura_cm','comprimento_cm'):
        if linha.get(k) and (numero(linha[k]) is None or numero(linha[k])<1):
            raise ErroCadastro('medidas devem estar em centímetros, nunca 0,32')
    descricao=str(linha.get('descricao',''))
    if str(linha.get('faixas_na_descricao','')).strip().lower()=='sim' and linha.get('faixas'):
        lados={}
        for faixa in str(linha['faixas']).splitlines():
            m=re.match(r'^([A-Z])\d*\s+(.+)',faixa)
            if m: lados.setdefault(m[1],[]).append(m[2])
        if lados: descricao+='\n\n'+' / '.join('Lado '+l+': '+'; '.join(fs) for l,fs in lados.items())
    return {'name':{'pt':linha['titulo']},'brand':linha.get('marca',''),
            'description':{'pt':descricao_html(descricao)},'published':False,
            'categories':mapa_categorias(categorias,linha.get('categorias','')),
            'seo_title':{'pt':str(linha.get('seo_titulo',''))[:70]},
            'seo_description':{'pt':str(linha.get('seo_descricao',''))[:320]},'tags':linha.get('tags',''),
            'variants':[{'price':f'{preco:.2f}','stock_management':True,'stock':estoque_da_linha(linha),'sku':sku_da_linha(linha['id']),
                         'weight':numero(linha.get('peso_kg')) or peso_padrao(linha),
                         'height':numero(linha.get('altura_cm')) or 2.5,
                         'width':numero(linha.get('largura_cm')) or 32,
                         'depth':numero(linha.get('comprimento_cm')) or 32}]}


def estoque_da_linha(linha):
    """Usado é sempre exemplar único (1). Lacrado/novo usa a coluna `estoque` (vazio = 1, máximo 999). D-073."""
    if re.search(r'usad', str(linha.get('categorias',''))+' '+str(linha.get('titulo','')), re.I): return 1
    n=numero(linha.get('estoque'))
    return max(1,min(int(n),999)) if n else 1


def deve_publicar(linha):
    """D-082: padrão é publicar ('sim' ou vazio); só 'nao'/'não' mantém oculto."""
    return texto_normal(linha.get('publicar',''))!='nao'


class LojaCadastro:
    """Somente POST nos dois endpoints autorizados; nenhuma atualização de produto."""
    def __init__(self, api): self.api=api
    def buscar(self, sku):
        r=self.api._get(self.api._base+'/products/sku/'+sku,vazio_se_404=True)
        return r.json() if r is not None else None
    def produto(self,pid): return self.api._get(self.api._base+'/products/'+str(int(pid))).json()
    def categorias(self): return list(self.api.listar('categories'))
    def _post(self,caminho,corpo):
        if not (caminho=='products' or re.fullmatch(r'products/\d+/images',caminho)):
            raise ErroCadastro('escrita fora do cadastro bloqueada')
        self.api._esperar_vaga()
        try:
            r=self.api._sessao.post(self.api._base+'/'+caminho,headers=self.api._cabecalhos,
                                    json=corpo,timeout=60,allow_redirects=False)
            self.api._guardar_limites(r)
            if r.status_code not in (200,201): raise ErroCadastro('POST não confirmado; reconciliar antes de tentar novamente')
            return r.json()
        except ErroCadastro: raise
        except Exception: raise ErroCadastro('POST não confirmado; reconciliar antes de tentar novamente') from None
    def criar(self,corpo):
        if corpo.get('published') is not False or 'visibility' in corpo: raise ErroCadastro('produto deve nascer oculto')
        return self._post('products',corpo)
    def imagem(self,pid,jpeg,ordem,nome):
        return self._post(f'products/{int(pid)}/images',{'attachment':base64.b64encode(jpeg).decode(),
                                                      'filename':nome,'position':ordem})
    def _put(self,caminho,corpo):
        if not re.fullmatch(r'products/\d+',caminho) or not isinstance(corpo,dict) or list(corpo.keys())!=['published'] or corpo.get('published') is not True:
            raise ErroCadastro('PUT fora da publicação do cadastro bloqueado')
        self.api._esperar_vaga()
        try:
            r=self.api._sessao.put(self.api._base+'/'+caminho,headers=self.api._cabecalhos,
                                   json=corpo,timeout=60,allow_redirects=False)
            self.api._guardar_limites(r)
            if r.status_code not in (200,201): raise ErroCadastro('PUT não confirmado')
            return r.json()
        except ErroCadastro: raise
        except Exception: raise ErroCadastro('PUT não confirmado') from None
    def publicar(self,pid,corpo=None):
        return self._put(f'products/{int(pid)}',{'published':True} if corpo is None else corpo)


class DriveFotos:
    """Pastas privadas da loja, conta de serviço existente, sem link público."""
    def __init__(self,config,pasta_id='',sessao=None):
        if sessao: self.s=sessao
        else:
            scopes=['https://www.googleapis.com/auth/drive']
            if config.google_service_account_json:
                cred=service_account.Credentials.from_service_account_info(json.loads(config.google_service_account_json),scopes=scopes)
            else:
                cred=service_account.Credentials.from_service_account_file(str(Path(RAIZ_PROJETO)/config.google_service_account_file),scopes=scopes)
            self.s=AuthorizedSession(cred)
        self.entrada=pasta_id
        if not self.entrada:
            rs=self.listar("name = 'Cadastro de Discos' and mimeType = 'application/vnd.google-apps.folder'")
            if len(rs)!=1: raise ErroCadastro('configurar Cadastro: pasta de entrada Drive (ID) e acesso de Editor')
            entradas=self.listar(f"'{rs[0]['id']}' in parents and name = 'entrada' and mimeType = 'application/vnd.google-apps.folder'")
            if len(entradas)!=1: raise ErroCadastro('pasta entrada ausente ou ambígua')
            self.entrada=entradas[0]['id']
        meta=self.request('GET','/drive/v3/files/'+self.entrada,params={'fields':'parents,mimeType'}).json()
        if meta.get('mimeType')!='application/vnd.google-apps.folder' or len(meta.get('parents',[]))!=1:
            raise ErroCadastro('pasta de entrada sem raiz única acessível')
        self.raiz=meta['parents'][0]
    def request(self,metodo,caminho,**kw):
        try:
            r=self.s.request(metodo,'https://www.googleapis.com'+caminho,timeout=60,**kw)
            if r.status_code not in (200,201):
                try: motivo=(r.json().get('error',{}).get('errors') or [{}])[0].get('reason','')
                except Exception: motivo=''
                raise ErroCadastro(f'Drive {r.status_code}'+(f' {motivo}' if motivo else '')+'; conferir permissão e espaço da conta de serviço')
            return r
        except ErroCadastro: raise
        except Exception: raise ErroCadastro('Drive indisponível') from None
    def listar(self,q):
        rs=[]; token=None
        while True:
            d=self.request('GET','/drive/v3/files',params={'q':q+' and trashed = false','fields':'files(id,name,parents),nextPageToken',
                   'pageSize':100,'pageToken':token or ''}).json()
            rs+=d.get('files',[]); token=d.get('nextPageToken')
            if not token: return rs
    def pasta(self,pai,nome):
        if not re.fullmatch(r'[\w .-]+',nome): raise ErroCadastro('nome de pasta inválido')
        rs=self.listar(f"'{pai}' in parents and name = '{nome}' and mimeType = 'application/vnd.google-apps.folder'")
        if len(rs)>1: raise ErroCadastro('pasta Drive duplicada')
        return rs[0]['id'] if rs else self.request('POST','/drive/v3/files',json={'name':nome,'parents':[pai],
                                                     'mimeType':'application/vnd.google-apps.folder'}).json()['id']
    def baixar(self,fid):
        if not re.fullmatch(r'[\w-]+',fid): raise ErroCadastro('arquivo Drive inválido')
        meta=self.request('GET','/drive/v3/files/'+fid,params={'fields':'mimeType,parents'}).json()
        if not str(meta.get('mimeType','')).startswith('image/'): raise ErroCadastro('original não é imagem')
        # Só os originais da entrada informada, nunca caminho local J: ou arquivo de outra pasta.
        pais=meta.get('parents',[])
        if self.entrada not in pais: raise ErroCadastro('foto fora da pasta de entrada')
        return self.request('GET','/drive/v3/files/'+fid,params={'alt':'media'}).content
    def guardar(self,id_disco,nome,jpeg):
        destino=self.pasta(self.pasta(self.raiz,'site'),id_disco)
        rs=self.listar(f"'{destino}' in parents and name = '{nome}'")
        if rs: return rs[0]['id']
        limite='cadastro_'+uuid.uuid4().hex
        metadata=json.dumps({'name':nome,'parents':[destino]}).encode('utf-8')
        corpo=(f'--{limite}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n'.encode()+metadata+
               f'\r\n--{limite}\r\nContent-Type: image/jpeg\r\n\r\n'.encode()+jpeg+
               f'\r\n--{limite}--\r\n'.encode())
        r=self.request('POST','/upload/drive/v3/files',params={'uploadType':'multipart'},
                       headers={'Content-Type':f'multipart/related; boundary={limite}'},data=corpo)
        return r.json()['id']


def ler(planilha,nome):
    try: return planilha._ss.worksheet(nome).get_all_values()
    except gspread.exceptions.WorksheetNotFound: return []


def preparar_abas(planilha):
    linhas=ler(planilha,ABA)
    if not linhas: planilha.garantir_cabecalho(ABA,COLUNAS,{})
    else:
        if linhas[0][:len(BASE)]!=BASE: raise ErroCadastro('cabeçalhos do cadastro fora da ordem')
        novos=[c for c in EXTRAS if c not in linhas[0]]
        if novos:
            aba=planilha._ss.worksheet(ABA)
            if aba.col_count<len(linhas[0])+len(novos): aba.resize(cols=len(linhas[0])+len(novos))
            aba.update([novos],_letra(len(linhas[0])+1)+'1',raw=True)
    if not ler(planilha,'cadastro_fotos'): planilha.garantir_cabecalho('cadastro_fotos',FOTOS,{})
    elif ler(planilha,'cadastro_fotos')[0]!=FOTOS: raise ErroCadastro('cabeçalhos das fotos fora da ordem')
    c=ler(planilha,'Configuração'); nomes={r[0] for r in c if r}
    novas=[r for r in [['Cadastro: pasta de entrada Drive (ID)','','ID da pasta entrada compartilhada; cópias em site/<id> da pasta pai. Não usa caminho local.'],
                       ['Cadastro: publicar direto','Não','D-067: trava atual exige produto sempre oculto; esta chave não libera publicação.']]
           if r[0] not in nomes]
    if novas:
        aba,_=planilha._aba('Configuração',len(c)+len(novas)+2,3)
        if not c: aba.update([['Parâmetro','Valor','Ajuda']],'A1',raw=True); c=[['Parâmetro','Valor','Ajuda']]
        if aba.row_count<len(c)+len(novas): aba.resize(rows=len(c)+len(novas))
        aba.update(novas,f'A{len(c)+1}',raw=True)


def salvar_estado(caminho,estado):
    caminho.parent.mkdir(parents=True,exist_ok=True)
    t=caminho.with_suffix('.tmp'); t.write_text(json.dumps(estado,ensure_ascii=False),encoding='utf-8')
    for tentativa in range(5):
        try:
            t.replace(caminho)
            return
        except PermissionError:
            if tentativa==4: raise
            time.sleep(.05*2**tentativa)


def resolver_fotos(planilha,drive,fs):
    """Única escrita em cadastro_fotos: completa IDs vazios por nome exato na entrada.

    Resolve o disco inteiro antes de gravar. Não baixa/substitui arquivos e não
    escolhe o primeiro homônimo. Relê a linha para preservar edições do Cowork.
    """
    faltantes=[f for f in fs if not str(f.get('arquivo_drive_id','')).strip()]
    if not faltantes: return fs
    if not getattr(drive,'entrada',''):
        raise PendenciaFotos('configurar o ID da pasta de entrada')
    try:
        arquivos=drive.listar(f"'{drive.entrada}' in parents")
    except Exception:
        raise PendenciaFotos('não foi possível consultar a pasta de entrada') from None
    indice={}
    for arquivo in arquivos:
        indice.setdefault(arquivo.get('name',''),[]).append(arquivo)
    resolvidas=[]; problemas=[]
    for f in faltantes:
        nome=f.get('observacao','')  # não normalizar nome, espaços ou maiúsculas
        encontrados=indice.get(nome,[]) if nome.strip() else []
        if not nome.strip(): problemas.append('nome ausente em observacao')
        elif not encontrados: problemas.append(f'arquivo não encontrado: {nome}')
        elif len(encontrados)!=1: problemas.append(f'nome repetido na entrada: {nome}')
        elif not encontrados[0].get('id'): problemas.append(f'arquivo sem ID: {nome}')
        else: resolvidas.append((f,encontrados[0]['id']))
    if problemas: raise PendenciaFotos('; '.join(problemas))
    atuais=ler(planilha,'cadastro_fotos')
    if not atuais or atuais[0]!=FOTOS: raise PendenciaFotos('cabeçalhos das fotos alterados')
    mudancas=[]
    for original,fid in resolvidas:
        matches=[(n,dict(zip(FOTOS,r))) for n,r in enumerate(atuais[1:],2)
                 if dict(zip(FOTOS,r)).get('id_disco')==original.get('id_disco')
                 and dict(zip(FOTOS,r)).get('ordem')==original.get('ordem')]
        if len(matches)!=1 or any(str(matches[0][1].get(k,''))!=str(original.get(k,'')) for k in FOTOS):
            raise PendenciaFotos('linha de foto alterada ou repetida; conferir antes de tentar novamente')
        mudancas.append({'range':f'D{matches[0][0]}','values':[[fid]]})
    planilha._ss.worksheet('cadastro_fotos').batch_update(mudancas,raw=True)
    ids={id(f):fid for f,fid in resolvidas}
    return [{**f,'arquivo_drive_id':ids[id(f)]} if id(f) in ids else f for f in fs]


def ajustar_fotos(id_disco,fs,drive):
    fotos_site=sorted([f for f in fs if not f.get('papel','').strip().lower().startswith('etiqueta')],key=lambda f:float(f['ordem']))
    if not fotos_site: raise ErroCadastro('sem fotos do disco')
    ordens=[int(f['ordem']) for f in fotos_site]
    if len(set(ordens))!=len(ordens) or any(x<=0 for x in ordens): raise ErroCadastro('ordem de fotos inválida ou duplicada')
    ajustadas=[]; refs=[]
    for i,f in enumerate(fotos_site,1):
        jpg=fotos.processar(drive.baixar(f['arquivo_drive_id']),f.get('papel',''),f.get('cantos',''))
        nome=f'{i:03d}-'+hashlib.sha256(jpg).hexdigest()[:16]+'.jpg'
        try: fid=drive.guardar(id_disco,nome,jpg)
        except Exception as erro:
            # A cópia ajustada no Drive é só arquivo; a loja recebe a imagem direto (attachment).
            # Conta de serviço sem cota no Drive pessoal não pode impedir o cadastro.
            print('Cadastro: cópia ajustada não guardada no Drive; detalhes na planilha.'); fid=''
        refs.append({'ordem':i,'papel':f.get('papel',''),'arquivo_drive_id':fid})
        ajustadas.append((i,nome,jpg))
    return ajustadas,refs


def processar_linha(linha,fs,loja,drive,gravar,caminho,confirmar=lambda:True):
    """gravar persiste por ID na planilha; se falhar após POST, o diário impede duplicação."""
    if linha.get('status')!='aprovado': return
    if not linha.get('id'): raise ErroCadastro('sem id estável')
    estado=json.loads(linha.get('cadastro_execucao') or '{}')
    if not estado and caminho.exists(): estado=json.loads(caminho.read_text(encoding='utf-8'))
    def persistir():
        salvar_estado(caminho,estado)
        gravar({'cadastro_execucao':json.dumps(estado,ensure_ascii=False)})
    pid=str(linha.get('produto_id') or estado.get('produto_id') or '')
    if linha.get('produto_id') and estado.get('produto_id') and str(linha['produto_id'])!=str(estado['produto_id']):
        raise ErroCadastro('produto_id diverge do cadastro original; interrompido')
    if pid and not estado:
        return  # ID existente nunca recebe imagens nem atualização por este fluxo.
    corpo=corpo_produto(linha,loja.categorias())
    ajustadas,refs=ajustar_fotos(linha['id'],fs,drive)
    gravar({'fotos_ajustadas':json.dumps(refs,ensure_ascii=False)})
    manifesto=[nome for _,nome,_ in ajustadas]
    if estado.get('manifesto') and estado['manifesto']!=manifesto:
        raise ErroCadastro('fotos alteradas depois da criação; conferir manualmente')
    if not pid:
        achado=loja.buscar(sku_da_linha(linha['id']))
        if achado:
            if estado.get('post_iniciado'):
                pid=str(achado['id'])
            else: raise ErroCadastro('SKU já existe; conferir cadastro antes de vincular')
        elif estado.get('post_iniciado'):
            raise ErroCadastro('POST anterior incerto; conferir na loja, não reenviar')
        else:
            estado={'post_iniciado':True,'sku':sku_da_linha(linha['id']),'imagens':[],'manifesto':manifesto}
            persistir()  # planilha + cache ANTES do POST; sobrevive à perda do cache do Actions
            if not confirmar(): raise ErroCadastro('aprovação alterada antes do POST')
            produto=loja.criar(corpo); pid=str(produto['id'])
        estado['produto_id']=pid; persistir()
    gravar({'produto_id':pid})
    produto=loja.produto(pid)
    if not any(v.get('sku')==sku_da_linha(linha['id']) for v in (produto.get('variants') or [produto])):
        raise ErroCadastro('produto não pertence a este cadastro; interrompido')
    link_loja=f'https://lojamonstro.com.br/produtos/'+str(_pt(produto.get('handle')) or '')
    pendencias_limpas=pendencias_sem_busca_fotos(linha.get('pendencias',''))
    if produto.get('published') is True:
        if not estado.get('publicacao_pedida'): raise ErroCadastro('produto está visível; interrompido para conferência')
        estado['publicado']=True; persistir()
        gravar({'link_loja':link_loja,'status':'publicado','pendencias':pendencias_limpas})
        return
    gravar({'link_loja':f'https://lojamonstro.com.br/produtos/'+str(_pt(produto.get('handle')) or '')})
    # ID precisa estar confirmado na planilha antes da primeira imagem.
    for pos,nome,jpg in ajustadas:
        if nome in estado.get('imagens',[]): continue
        if estado.get('imagem_pendente'):
            raise ErroCadastro('imagem anterior incerta; conferir manualmente, não reenviar')
        if not confirmar(): raise ErroCadastro('aprovação alterada antes das imagens')
        estado['imagem_pendente']=nome; persistir()
        loja.imagem(pid,jpg,pos,nome)
        estado.setdefault('imagens',[]).append(nome); estado.pop('imagem_pendente',None); persistir()
    if not deve_publicar(linha):
        gravar({'status':'criado','pendencias':pendencias_limpas})
        return
    aviso_pub='Não consegui deixar visível; publique à mão na Nuvemshop'
    if estado.get('publicacao_pedida'):
        pends='; '.join(filter(None,[pendencias_limpas,aviso_pub if aviso_pub not in pendencias_limpas else '']))
        gravar({'status':'criado','pendencias':pends})
        return
    estado['publicacao_pedida']=True; persistir()
    try:
        loja.publicar(pid)
    except Exception:
        pends='; '.join(filter(None,[pendencias_limpas,aviso_pub if aviso_pub not in pendencias_limpas else '']))
        gravar({'status':'criado','pendencias':pends})
        return
    estado['publicado']=True; persistir()
    gravar({'status':'publicado','link_loja':link_loja,'pendencias':pendencias_limpas})


def passo_rotina(config,planilha,tabelas,pasta_api,api=None,drive=None,discogs=None):
    """Enriquece rascunhos e processa só aprovados; erro de uma linha não derruba a loja."""
    resumo={'criados':0,'erros':0,'rascunhos':0}
    if not ler(planilha,ABA): return resumo
    preparar_abas(planilha)
    v=ler(planilha,ABA); cab=v[0]
    fs=ler(planilha,'cadastro_fotos'); fotos_lista=[dict(zip(fs[0],r)) for r in fs[1:]] if fs else []
    c={r[0]:r[1] for r in ler(planilha,'Configuração') if len(r)>1}
    repetidos=[str(r[0]) for r in v[1:] if r and r[0]]
    def gravador(did):
        def gravar(mudancas):
            # Reencontra o ID e relê status. Não sobrescreve uma edição/reordenação feita no painel.
            atuais=ler(planilha,ABA); matches=[i for i,r in enumerate(atuais[1:],2) if r and r[0]==did]
            if len(matches)!=1: raise ErroCadastro('id duplicado ou removido na planilha')
            n=matches[0]; row=dict(zip(atuais[0],atuais[n-1]))
            if 'status' in mudancas and row.get('status') not in ('aprovado','criado'):
                raise ErroCadastro('status alterado pelo operador; preservado')
            if 'produto_id' in mudancas and row.get('produto_id') and str(row['produto_id'])!=str(mudancas['produto_id']):
                raise ErroCadastro('produto_id alterado; interrompido')
            aba=planilha._ss.worksheet(ABA)
            for k,val in {**mudancas,'atualizado_em':pd.Timestamp.now(tz='America/Sao_Paulo').strftime('%Y-%m-%d %H:%M')}.items():
                aba.update([[val]],f'{_letra(atuais[0].index(k)+1)}{n}',raw=True)
        return gravar
    cliente_discogs=discogs or Discogs(config.discogs_token)
    for r in v[1:]:
        l=dict(zip(cab,r)); did=str(l.get('id',''))
        if not did or l.get('status') not in ('rascunho','aprovado','criado'): continue
        gravar=gravador(did)
        try:
            if repetidos.count(did)!=1: raise ErroCadastro('id duplicado na planilha')
            if l['status']=='criado' and l.get('produto_id'):
                loja=LojaCadastro(api or NuvemshopAPI(config))
                if loja.produto(l['produto_id']).get('published') is True: gravar({'status':'publicado'})
                continue
            minhas_fotos=[f for f in fotos_lista if f.get('id_disco')==did]
            if any(not str(f.get('arquivo_drive_id','')).strip() for f in minhas_fotos):
                entrada=c.get('Cadastro: pasta de entrada Drive (ID)','').strip()
                if not entrada: raise PendenciaFotos('configurar o ID da pasta de entrada')
                try:
                    drive=drive or DriveFotos(config,entrada)
                except Exception:
                    raise PendenciaFotos('não foi possível acessar a pasta de entrada') from None
                minhas_fotos=resolver_fotos(planilha,drive,minhas_fotos)
            if l['status']=='rascunho':
                dados={'preco_referencia':preco_referencia(l.get('titulo',''),tabelas.produtos,pd.Timestamp.now().date())}
                if pendencias_sem_busca_fotos(l.get('pendencias',''))!=l.get('pendencias',''):
                    dados['pendencias']=pendencias_sem_busca_fotos(l.get('pendencias',''))
                if numero(l.get('preco')): dados['preco_origem']='etiqueta'
                elif 'conferir preço' not in dados.get('pendencias',l.get('pendencias','')):
                    dados['pendencias']='; '.join(filter(None,[dados.get('pendencias',l.get('pendencias','')),'conferir preço']))
                for k,val in dict(peso_kg=peso_padrao(l),altura_cm=2.5,largura_cm=32,comprimento_cm=32).items():
                    if not numero(l.get(k)): dados[k]=val
                if not l.get('discogs_id') and config.discogs_token:
                    cat=re.search(r'(?:cat[aá]logo|catno)\s*[:=]\s*([^\n;]+)',l.get('ficha',''),re.I)
                    try: dados.update(cliente_discogs.buscar(l.get('titulo',''),cat[1] if cat else '',l.get('discogs_url','')))
                    except ErroDiscogs: dados['discogs_confianca']='baixa'
                if minhas_fotos:
                    atual=dados.get('pendencias',l.get('pendencias',''))
                    try:
                        drive=drive or DriveFotos(config,c.get('Cadastro: pasta de entrada Drive (ID)',''))
                        _,refs=ajustar_fotos(did,minhas_fotos,drive)
                        dados['fotos_ajustadas']=json.dumps(refs,ensure_ascii=False)
                        if sem_aviso_fotos(atual)!=atual: dados['pendencias']=sem_aviso_fotos(atual)
                    except Exception as erro:
                        motivo=str(erro) if isinstance(erro,ErroCadastro) else type(erro).__name__
                        print('Cadastro: fotos não ajustadas; detalhes na planilha.')
                        aviso=f'conferir fotos/Drive ({motivo})'
                        if aviso not in atual:   # um aviso só, com o motivo; não repetir a cada rodada
                            dados['pendencias']='; '.join(filter(None,[sem_aviso_fotos(atual),aviso]))
                gravar(dados); resumo['rascunhos']+=1
                continue
            if not numero(l.get('preco')): raise ErroCadastro('sem preço')
            loja=LojaCadastro(api or NuvemshopAPI(config))
            if not l.get('produto_id') or l.get('cadastro_execucao') or (Path(pasta_api)/('cadastro_'+sku_da_linha(did)+'.json')).exists():
                drive=drive or DriveFotos(config,c.get('Cadastro: pasta de entrada Drive (ID)',''))
                # Revalida a aprovação imediatamente antes das escritas externas.
                atuais=ler(planilha,ABA); atual=next(dict(zip(atuais[0],r)) for r in atuais[1:] if r and r[0]==did)
                if atual.get('status')!='aprovado': continue
                if atual!=l: continue  # houve edição depois do início da rodada; esperar a próxima
                def confirmar():
                    rows=ler(planilha,ABA)
                    matches=[dict(zip(rows[0],r)) for r in rows[1:] if r and r[0]==did]
                    fs_atuais=ler(planilha,'cadastro_fotos')
                    fotos_atuais=[dict(zip(fs_atuais[0],r)) for r in fs_atuais[1:] if r and r[0]==did] if fs_atuais else []
                    return fotos_atuais==minhas_fotos and len(matches)==1 and matches[0].get('status')=='aprovado' and all(
                        str(matches[0].get(k,''))==str(l.get(k,'')) for k in COLUNAS if k not in ('produto_id','link_loja','atualizado_em','cadastro_execucao','fotos_ajustadas'))
                processar_linha(l,minhas_fotos,loja,drive,gravar,
                                 Path(pasta_api)/('cadastro_'+sku_da_linha(did)+'.json'),confirmar)
                resumo['criados']+=1
        except PendenciaFotos as erro:
            resumo['erros']+=1
            anterior=pendencias_sem_busca_fotos(l.get('pendencias',''))
            try: gravar({'pendencias':'\n'.join(filter(None,[anterior,'Fotos por nome: '+str(erro)]))})
            except Exception: pass
        except Exception as erro:
            resumo['erros']+=1
            motivo=str(erro) if isinstance(erro,ErroCadastro) else 'falha de processamento; conferir antes de tentar novamente'
            try: gravar({'status':'erro: '+motivo})
            except Exception: pass
    return resumo
