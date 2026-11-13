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
EXTRAS='discogs_id faixas creditos discogs_menor_preco discogs_a_venda faixas_na_descricao preco_origem cadastro_execucao fotos_ajustadas estoque publicar marcado_vinil capa_discogs_url conferido_em conferido_por subir_loja atualizar_preco'.split()
COLUNAS=BASE+EXTRAS
# D-104: colunas que a Conferência do Painel grava; não contam como edição do disco durante a rodada.
COLUNAS_CONFERENCIA=('conferido_em','conferido_por','subir_loja','marcado_vinil','lote_black','atualizado_em','atualizar_preco')
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
    if re.search(r'\blivro\b', n) or 'livros' in texto_normal(str(linha.get('categorias',''))): return .60
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
    variante={'price':f'{preco:.2f}','sku':sku_da_linha(linha['id']),
              'weight':numero(linha.get('peso_kg')) or peso_padrao(linha),
              'height':numero(linha.get('altura_cm')) or 2.5,
              'width':numero(linha.get('largura_cm')) or 32,
              'depth':numero(linha.get('comprimento_cm')) or 32}
    if eh_estoque_infinito(linha):
        variante['stock_management']=False
    else:
        variante['stock_management']=True
        variante['stock']=estoque_da_linha(linha)
    return {'name':{'pt':linha['titulo']},'brand':linha.get('marca',''),
            'description':{'pt':descricao_html(descricao)},'published':False,
            'categories':mapa_categorias(categorias,linha.get('categorias','')),
            'seo_title':{'pt':str(linha.get('seo_titulo',''))[:70]},
            'seo_description':{'pt':str(linha.get('seo_descricao',''))[:320]},'tags':linha.get('tags',''),
            'variants':[variante]}


def eh_estoque_infinito(linha):
    """Retorna True se for novo/lacrado/sob demanda com estoque infinito. Usado é sempre 1 (D-073, D-096)."""
    if re.search(r'usad', str(linha.get('categorias',''))+' '+str(linha.get('titulo','')), re.I): return False
    val=str(linha.get('estoque','')).strip().lower()
    return bool(re.search(r'^(infinito|∞|sob[- ]?demanda)$', val, re.I))


def estoque_da_linha(linha):
    """Usado é sempre exemplar único (1). Lacrado/novo usa a coluna `estoque` (vazio = 1, máximo 999). D-073, D-096."""
    if re.search(r'usad', str(linha.get('categorias',''))+' '+str(linha.get('titulo','')), re.I): return 1
    if eh_estoque_infinito(linha): return None
    n=numero(linha.get('estoque'))
    return max(1,min(int(n),999)) if n else 1


PENDENCIA_SEM_FOTO_OFICIAL = 'sem foto oficial'


def eh_lacrado(linha):
    texto = f"{linha.get('categorias', '')} {linha.get('titulo', '')}"
    return bool(re.search(r'lacrad', texto, re.I)) and not bool(re.search(r'\busad', texto, re.I))


def tem_foto_oficial(fs):
    return any(str(f.get('papel', '')).strip().lower() == 'oficial' for f in fs)


def _incluir_pendencia(texto, item):
    atual = str(texto or '').strip()
    partes = [p.strip() for p in re.split(r'[;|]', atual) if p.strip()]
    if item in partes:
        return atual
    return f'{atual}; {item}' if atual else item


def foto_publicavel(f, lacrado=False):
    papel = str(f.get('papel', '')).strip().lower()
    if lacrado:
        return papel == 'oficial'
    return papel not in ('etiqueta', 'referencia', 'codigo_barras', 'descartar')


def publicar_sem_alerta(linha, capa_confere=False, habilitado=True, tem_oficial=True):
    if eh_lacrado(linha) and not tem_oficial:
        return False
    pend = str(linha.get('pendencias', '')).strip()
    travas = (
        'edição não confirmada',
        'descrição incompleta',
        'destaque fora das faixas',
        'possível disco fotografado duas vezes',
    )
    if any(t in pend for t in travas):
        return False
    return bool(habilitado and not pend
                and capa_confere and linha.get('preco_origem') == 'etiqueta'
                and numero(linha.get('preco')) and texto_normal(linha.get('discogs_confianca')) == 'alta')


def somar_estoque(linha, loja, gravar, caminho, confirmar=lambda: True):
    """Intenção durável antes do PUT. Resposta incerta exige conferência manual."""
    if linha.get('status') != 'somar_estoque' or not re.search(r'lacrad|novo', str(linha.get('categorias', '')), re.I):
        raise ErroCadastro('soma exige lacrado confirmado no Painel')
    pid = str(int(linha['produto_id']))
    qtd = numero(linha.get('estoque'))
    if qtd is None or not qtd.is_integer() or qtd > 999:
        raise ErroCadastro('quantidade inválida para soma')
    estado = json.loads(caminho.read_text(encoding='utf-8')) if caminho.exists() else (json.loads(linha['cadastro_execucao']) if linha.get('cadastro_execucao') else {})
    if estado:
        if estado.get('produto_id') != pid or estado.get('quantidade') != int(qtd):
            raise ErroCadastro('diário de estoque diverge da confirmação')
        if estado.get('concluido'):
            gravar({'status': 'estoque_somado'})
            return
        raise ErroCadastro('soma anterior incerta; conferir antes de tentar novamente')
    produto = loja.produto(pid)
    vs = produto.get('variants', [])
    if len(vs) != 1:
        raise ErroCadastro('produto sem variante única; conferir')
    v = vs[0]
    if v.get('stock_management') is not True or v.get('stock') is None:
        raise ErroCadastro('estoque infinito; nenhuma alteração feita')
    antes = int(v['stock'])
    if antes < 0 or not confirmar():
        raise ErroCadastro('confirmação alterada ou estoque inválido')
    estado = dict(produto_id=pid, variante_id=v['id'], quantidade=int(qtd), antes=antes,
                  depois=antes+int(qtd), concluido=False)
    salvar_estado(caminho, estado)
    gravar({'cadastro_execucao': json.dumps(estado)})
    loja.estoque(pid, v['id'], estado['depois'])
    estado['concluido'] = True
    salvar_estado(caminho, estado)
    gravar({'cadastro_execucao': json.dumps(estado), 'status': 'estoque_somado'})


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
        if not ((re.fullmatch(r'products/\d+',caminho) and corpo == {'published': True}) or (re.fullmatch(r'products/\d+/variants/\d+',caminho) and isinstance(corpo,dict) and list(corpo)==['stock'] and type(corpo['stock']) is int and corpo['stock']>=0) or (re.fullmatch(r'products/\d+/variants/\d+',caminho) and isinstance(corpo,dict) and list(corpo)==['price'] and re.fullmatch(r'\d+\.\d{2}',str(corpo['price'])) and float(corpo['price'])>0)):
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
    def estoque(self,pid,vid,quantidade):
        return self._put(f'products/{int(pid)}/variants/{int(vid)}', {'stock': quantidade})
    def preco(self,pid,vid,valor):
        # D-104: correção de preço pedida na Conferência do Painel (só o preço da variante).
        return self._put(f'products/{int(pid)}/variants/{int(vid)}', {'price': f'{float(valor):.2f}'})
    def publicar(self,pid,corpo=None):
        return self._put(f'products/{int(pid)}',{'published':True} if corpo is None else corpo)
    def apagar_imagem(self,pid,iid):
        self.api._esperar_vaga()
        try:
            r=self.api._sessao.delete(f'{self.api._base}/products/{int(pid)}/images/{int(iid)}',
                                      headers=self.api._cabecalhos,timeout=60,allow_redirects=False)
            self.api._guardar_limites(r)
            if r.status_code not in (200,204): raise ErroCadastro(f'DELETE imagem não confirmado (HTTP {r.status_code})')
            return True
        except ErroCadastro: raise
        except Exception: raise ErroCadastro('DELETE imagem não confirmado') from None


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
            d=self.request('GET','/drive/v3/files',params={'q':q+' and trashed = false','fields':'files(id,name,parents,mimeType),nextPageToken',
                   'pageSize':100,'pageToken':token or ''}).json()
            rs+=d.get('files',[]); token=d.get('nextPageToken')
            if not token: return rs
    def pasta(self,pai,nome):
        if not re.fullmatch(r'[\w .-]+',nome): raise ErroCadastro('nome de pasta inválido')
        rs=self.listar(f"'{pai}' in parents and name = '{nome}' and mimeType = 'application/vnd.google-apps.folder'")
        if len(rs)>1: raise ErroCadastro('pasta Drive duplicada')
        return rs[0]['id'] if rs else self.request('POST','/drive/v3/files',json={'name':nome,'parents':[pai],
                                                     'mimeType':'application/vnd.google-apps.folder'}).json()['id']
    def arquivos_entrada(self):
        pendentes=[self.entrada]; vistos=set(); arquivos=[]
        while pendentes:
            pai=pendentes.pop()
            if pai in vistos: continue
            vistos.add(pai)
            for f in self.listar(f"'{pai}' in parents"):
                if f.get('mimeType')=='application/vnd.google-apps.folder': pendentes.append(f['id'])
                else: arquivos.append(f)
        return arquivos
    def baixar(self,fid):
        if not re.fullmatch(r'[\w-]+',fid): raise ErroCadastro('arquivo Drive inválido')
        meta=self.request('GET','/drive/v3/files/'+fid,params={'fields':'mimeType,parents'}).json()
        if not str(meta.get('mimeType','')).startswith('image/'): raise ErroCadastro('original não é imagem')
        # Só os originais da entrada informada, nunca caminho local J: ou arquivo de outra pasta.
        pais=meta.get('parents',[])
        if self.entrada not in pais and fid not in {f['id'] for f in self.arquivos_entrada()}: raise ErroCadastro('foto fora da pasta de entrada')
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
                       ['Cadastro: publicar direto quando não houver alerta','Sim','D-099: exige capa conferida, preço da etiqueta e nenhuma pendência.']]
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
        arquivos=drive.arquivos_entrada() if hasattr(drive,'arquivos_entrada') else drive.listar(f"'{drive.entrada}' in parents")
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
                 and all(dict(zip(FOTOS,r)).get(k)==original.get(k) for k in ('ordem','papel','observacao'))]
        if len(matches)!=1 or any(str(matches[0][1].get(k,''))!=str(original.get(k,'')) for k in FOTOS):
            raise PendenciaFotos('linha de foto alterada ou repetida; conferir antes de tentar novamente')
        mudancas.append({'range':f'D{matches[0][0]}','values':[[fid]]})
    planilha._ss.worksheet('cadastro_fotos').batch_update(mudancas,raw=True)
    ids={id(f):fid for f,fid in resolvidas}
    return [{**f,'arquivo_drive_id':ids[id(f)]} if id(f) in ids else f for f in fs]


LIMITE_PREVIAS_POR_RODADA=20


def previas_prontas(linha,fs):
    """D-090: rascunho que já teve as fotos ajustadas uma vez não refaz a cada rodada.

    A prévia só serve para a revisão; o produto recebe as fotos de novo na criação. Refaz se a quantidade de
    fotos do site mudou (foto trocada, incluída ou retirada).
    """
    try: refs=json.loads(linha.get('fotos_ajustadas') or '[]')
    except ValueError: return False
    site=[f for f in fs if foto_publicavel(f, eh_lacrado(linha))]
    return isinstance(refs,list) and len(refs)>0 and len(refs)==len(site)


def ajustar_fotos(id_disco,fs,drive,lacrado=False):
    fotos_site=sorted([f for f in fs if foto_publicavel(f, lacrado)],key=lambda f:float(f['ordem']))
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
    lacrado=eh_lacrado(linha)
    sem_oficial=lacrado and not tem_foto_oficial(fs)
    if sem_oficial:
        ajustadas,refs=[],[]
    else:
        ajustadas,refs=ajustar_fotos(linha['id'],fs,drive,lacrado=lacrado)
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
            # D-106: confere a aprovação ANTES de marcar o POST como iniciado; se a linha mudou, nada fica travado.
            if not confirmar(): raise ErroCadastro('aprovação alterada antes do POST')
            estado={'post_iniciado':True,'sku':sku_da_linha(linha['id']),'imagens':[],'manifesto':manifesto}
            persistir()  # planilha + cache ANTES do POST; sobrevive à perda do cache do Actions
            produto=loja.criar(corpo); pid=str(produto['id'])
        estado['produto_id']=pid; persistir()
    gravar({'produto_id':pid})
    produto=loja.produto(pid)
    if not any(v.get('sku')==sku_da_linha(linha['id']) for v in (produto.get('variants') or [produto])):
        raise ErroCadastro('produto não pertence a este cadastro; interrompido')
    link_loja=f'https://lojamonstro.com.br/produtos/'+str(_pt(produto.get('handle')) or '')
    pendencias_limpas=pendencias_sem_busca_fotos(linha.get('pendencias',''))
    if sem_oficial:
        pendencias_limpas=_incluir_pendencia(pendencias_limpas, PENDENCIA_SEM_FOTO_OFICIAL)
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
    if sem_oficial or not deve_publicar(linha):
        mud={'status':'criado','pendencias':pendencias_limpas}
        if sem_oficial: mud['publicar']='nao'
        gravar(mud)
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


def _data_do_lote(did):
    m=re.match(r'^(\d{4})-(\d{2})-(\d{2})',str(did)) or re.match(r'^(\d{2})(\d{2})(\d{2})N?[a-z]-',str(did))
    if not m: return None
    a,mes,d=m.groups()
    try: return pd.Timestamp(int(a) if len(a)==4 else 2000+int(a),int(mes),int(d),tz='America/Sao_Paulo')
    except ValueError: return None


def produto_feito_no_site(linha,produtos,ids_vinculados):
    """D-106: produto criado à mão na Nuvemshop para este rascunho (mesmo artista e álbum, SKU que não é do robô,
    criado a partir do dia do lote e ainda não ligado a outra linha). Devolve o registro só se houver exatamente um."""
    if produtos is None or getattr(produtos,'empty',True): return None
    artista,album=identidade_titulo(linha.get('titulo',''))
    if not album: return None
    desde=_data_do_lote(linha.get('id',''))
    candidatos=[]
    for p in produtos.to_dict('records'):
        pid=numero(p.get('id'))
        if not pid or str(int(pid)) in ids_vinculados: continue
        if str(p.get('sku') or '').startswith('CAD'): continue
        if identidade_titulo(p.get('nome',''))!=(artista,album): continue
        criado=pd.to_datetime(p.get('criado_em'),errors='coerce',utc=True)
        if desde is None or pd.isna(criado) or criado<desde.tz_convert('UTC')-pd.Timedelta(days=1): continue
        if eh_lacrado(linha)!=bool(re.search(r'lacrad|novo',str(p.get('nome',''))+' '+str(p.get('categorias','')),re.I)): continue
        candidatos.append(p)
    return candidatos[0] if len(candidatos)==1 else None


def conciliar_com_site(planilha,produtos):
    """D-106: liga ao produto já existente os rascunhos que o Túlio criou à mão na loja, para o robô não duplicar.
    Também marca o produto excluído na loja. Nunca oculta, apaga ou altera produto na Nuvemshop."""
    v=ler(planilha,ABA)
    if not v or produtos is None or getattr(produtos,'empty',True): return 0
    cab=v[0]; aba=planilha._ss.worksheet(ABA)
    ids_loja={str(int(n)) for n in (numero(x) for x in produtos.get('id',[])) if n}
    ids_vinculados={str(r[cab.index('produto_id')]).strip() for r in v[1:] if len(r)>cab.index('produto_id') and str(r[cab.index('produto_id')]).strip()}
    feitos=0
    for n,r in enumerate(v[1:],2):
        l=dict(zip(cab,r)); did=str(l.get('id','')).strip(); st=str(l.get('status','')).strip()
        if not did or st.startswith('descartado') or st=='somar_estoque': continue
        pid=str(l.get('produto_id','')).strip()
        if pid and pid in ids_loja: continue
        if pid and not str(l.get('subir_loja','')).startswith('erro'): continue   # produto recém-criado pode não estar na coleta ainda
        if not pid and (l.get('cadastro_execucao') or st not in ('rascunho','aprovado') and not st.startswith('erro')): continue
        achado=produto_feito_no_site(l,produtos,ids_vinculados)
        mud={}
        if achado:
            novo=str(int(numero(achado['id'])))
            visivel=bool(achado.get('exibir'))
            mud={'produto_id':novo,'link_loja':'https://lojamonstro.com.br/produtos/'+str(achado.get('url') or ''),
                 'status':'publicado' if visivel else 'criado',
                 'pendencias':'; '.join(filter(None,[str(l.get('pendencias','')).strip(),f'Ligado ao produto criado no site (ID {novo}); o robô não criou outro.']))}
            if str(l.get('subir_loja','')).strip(): mud['subir_loja']='feito' if visivel else 'pedido'
            ids_vinculados.add(novo)
        elif pid and str(l.get('subir_loja','')).startswith('erro'):
            mud={'subir_loja':'erro: produto não existe mais na loja; descarte ou recadastre'}
            if l.get('subir_loja')==mud['subir_loja']: mud={}
        if not mud: continue
        atual=ler(planilha,ABA)
        linhas=[i for i,x in enumerate(atual[1:],2) if x and x[0]==did]
        if len(linhas)!=1: continue
        agora=dict(zip(atual[0],atual[linhas[0]-1]))
        if str(agora.get('produto_id','')).strip()!=pid: continue
        for k,val in {**mud,'atualizado_em':pd.Timestamp.now(tz='America/Sao_Paulo').strftime('%Y-%m-%d %H:%M')}.items():
            if k in atual[0]: aba.update([[val]],f'{_letra(atual[0].index(k)+1)}{linhas[0]}',raw=True)
        feitos+=1
    return feitos


def passo_rotina(config,planilha,tabelas,pasta_api,api=None,drive=None,discogs=None):
    """Enriquece rascunhos e processa só aprovados; erro de uma linha não derruba a loja."""
    resumo={'criados':0,'erros':0,'rascunhos':0}
    if not ler(planilha,ABA): return resumo
    preparar_abas(planilha)
    try: resumo['conciliados']=conciliar_com_site(planilha,getattr(tabelas,'produtos',None))
    except Exception: resumo['conciliados']=0   # conciliação nunca derruba o cadastro
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
            conferido_vira_aprovado=(mudancas.get('status')=='aprovado' and row.get('status')=='rascunho' and row.get('subir_loja')=='pedido')
            if 'status' in mudancas and row.get('status') not in ('aprovado','criado','publicado','somar_estoque') and not conferido_vira_aprovado:
                raise ErroCadastro('status alterado pelo operador; preservado')
            if 'produto_id' in mudancas and row.get('produto_id') and str(row['produto_id'])!=str(mudancas['produto_id']):
                raise ErroCadastro('produto_id alterado; interrompido')
            aba=planilha._ss.worksheet(ABA)
            for k,val in {**mudancas,'atualizado_em':pd.Timestamp.now(tz='America/Sao_Paulo').strftime('%Y-%m-%d %H:%M')}.items():
                aba.update([[val]],f'{_letra(atuais[0].index(k)+1)}{n}',raw=True)
        return gravar
    cliente_discogs=discogs or Discogs(config.discogs_token)
    previas_feitas=0  # D-090: prévias (baixar e ajustar fotos) por rodada têm limite
    for r in v[1:]:
        l=dict(zip(cab,r)); did=str(l.get('id',''))
        if not did: continue
        if l.get('status') not in ('rascunho','aprovado','criado','publicado','somar_estoque') and l.get('subir_loja') != 'pedido': continue
        gravar=gravador(did)
        try:
            if repetidos.count(did)!=1: raise ErroCadastro('id duplicado na planilha')
            # D-104: preço corrigido na Conferência de um disco que já existe na Nuvemshop.
            if l.get('atualizar_preco')=='pedido':
                pid_p=str(l.get('produto_id') or '').strip(); valor=numero(l.get('preco'))
                if not pid_p: gravar({'atualizar_preco':''})
                elif not valor or valor<=0: gravar({'atualizar_preco':'erro: preço inválido'})
                else:
                    loja_p=LojaCadastro(api or NuvemshopAPI(config))
                    try:
                        vs=loja_p.produto(pid_p).get('variants') or []
                        if len(vs)!=1: raise ErroCadastro('produto com mais de uma variante')
                        loja_p.preco(pid_p,vs[0]['id'],valor)
                        gravar({'atualizar_preco':'feito'})
                    except Exception as erro_preco:
                        try: gravar({'atualizar_preco':'erro: '+str(erro_preco)[:80]})
                        except Exception: pass
                l['atualizar_preco']=''
            # D-104: conferido na loja física vale como aprovação. Sem preço, não cria nada.
            if l.get('status')=='rascunho' and l.get('subir_loja')=='pedido':
                if not numero(l.get('preco')):
                    gravar({'subir_loja':'erro: sem preço'})
                    continue
                gravar({'status':'aprovado'})
                l['status']='aprovado'
            if l['status']=='somar_estoque':
                def confirmar_soma():
                    rows=ler(planilha,ABA)
                    matches=[dict(zip(rows[0],r)) for r in rows[1:] if r and r[0]==did]
                    return len(matches)==1 and all(matches[0].get(k,'')==l.get(k,'') for k in ('status','produto_id','estoque','categorias'))
                somar_estoque(l,LojaCadastro(api or NuvemshopAPI(config)),gravar,
                              Path(pasta_api)/('estoque_'+sku_da_linha(did)+'.json'),confirmar_soma)
                continue
            if l['status']=='criado' and l.get('produto_id'):
                loja=LojaCadastro(api or NuvemshopAPI(config))
                if loja.produto(l['produto_id']).get('published') is True: gravar({'status':'publicado'})
                if l.get('subir_loja') != 'pedido':
                    continue

            # D-103: Processamento de subir_loja = "pedido"
            if l.get('subir_loja') == 'pedido':
                pid_str = str(l.get('produto_id') or '').strip()
                if pid_str:
                    loja = LojaCadastro(api or NuvemshopAPI(config))
                    try:
                        p_info = loja.produto(pid_str)
                        if p_info.get('published') is True:
                            gravar({'subir_loja': 'feito', 'status': 'publicado'})
                        else:
                            loja.publicar(pid_str)
                            gravar({'subir_loja': 'feito', 'status': 'publicado'})
                    except Exception as erro_pub:
                        motivo_curto = str(erro_pub)[:80]
                        try:
                            gravar({'subir_loja': f'erro: {motivo_curto}'})
                        except Exception:
                            pass
                    continue
            # Sem produto_id ainda (rascunho ou aprovado): segue o fluxo normal e publica depois de criado.
            if l.get('status') not in ('rascunho','aprovado','criado','somar_estoque'): continue
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
                lacrado=eh_lacrado(l)
                sem_oficial=lacrado and not tem_foto_oficial(minhas_fotos)
                dados={'preco_referencia':preco_referencia(l.get('titulo',''),tabelas.produtos,pd.Timestamp.now().date())}
                if pendencias_sem_busca_fotos(l.get('pendencias',''))!=l.get('pendencias',''):
                    dados['pendencias']=pendencias_sem_busca_fotos(l.get('pendencias',''))
                if not numero(l.get('preco')) and 'conferir preço' not in dados.get('pendencias',l.get('pendencias','')):
                    dados['pendencias']='; '.join(filter(None,[dados.get('pendencias',l.get('pendencias','')),'conferir preço']))
                if sem_oficial:
                    dados['pendencias']=_incluir_pendencia(dados.get('pendencias',l.get('pendencias','')),PENDENCIA_SEM_FOTO_OFICIAL)
                    dados['publicar']='nao'
                    if l.get('fotos_ajustadas'): dados['fotos_ajustadas']='[]'
                for k,val in dict(peso_kg=peso_padrao(l),altura_cm=2.5,largura_cm=32,comprimento_cm=32).items():
                    if not numero(l.get(k)): dados[k]=val
                if not l.get('discogs_id') and config.discogs_token:
                    cat=re.search(r'(?:cat[aá]logo|catno)\s*[:=]\s*([^\n;]+)',l.get('ficha',''),re.I)
                    try: dados.update(cliente_discogs.buscar(l.get('titulo',''),cat[1] if cat else '',l.get('discogs_url','')))
                    except ErroDiscogs: dados['discogs_confianca']='baixa'
                if minhas_fotos and not sem_oficial and not previas_prontas(l,minhas_fotos) and previas_feitas<LIMITE_PREVIAS_POR_RODADA:
                    previas_feitas+=1
                    atual=dados.get('pendencias',l.get('pendencias',''))
                    try:
                        drive=drive or DriveFotos(config,c.get('Cadastro: pasta de entrada Drive (ID)',''))
                        _,refs=ajustar_fotos(did,minhas_fotos,drive,lacrado=lacrado)
                        dados['fotos_ajustadas']=json.dumps(refs,ensure_ascii=False)
                        if sem_aviso_fotos(atual)!=atual: dados['pendencias']=sem_aviso_fotos(atual)
                    except Exception as erro:
                        motivo=str(erro) if isinstance(erro,ErroCadastro) else type(erro).__name__
                        print('Cadastro: fotos não ajustadas; detalhes na planilha.')
                        aviso=f'conferir fotos/Drive ({motivo})'
                        if aviso not in atual:   # um aviso só, com o motivo; não repetir a cada rodada
                            dados['pendencias']='; '.join(filter(None,[sem_aviso_fotos(atual),aviso]))
                if l.get('discogs_url') and config.discogs_token and minhas_fotos and previas_feitas<LIMITE_PREVIAS_POR_RODADA:
                    previas_feitas+=1
                    pend=dados.get('pendencias',l.get('pendencias',''))
                    aviso=''
                    try:
                        rid=re.search(r'/release/(\d+)',l['discogs_url'])
                        if not rid: raise ErroCadastro('edição Discogs inválida')
                        release=cliente_discogs.get('/releases/'+rid[1])
                        imagens=sorted(release.get('images',[]),key=lambda x:x.get('type')!='primary')
                        from urllib.parse import urlparse
                        url=imagens[0]['uri']
                        parsed=urlparse(url)
                        if parsed.scheme!='https' or parsed.hostname!='i.discogs.com': raise ErroCadastro('imagem inválida')
                        resposta=requests.get(url,timeout=30,allow_redirects=False)
                        if resposta.status_code!=200: raise ErroCadastro('imagem indisponível')
                        propria=next(f for f in minhas_fotos if f.get('papel') in ('capa','referencia'))
                        drive=drive or DriveFotos(config,c.get('Cadastro: pasta de entrada Drive (ID)',''))
                        conteudo=drive.baixar(propria['arquivo_drive_id'])
                        if propria.get('cantos'): conteudo=fotos.processar(conteudo,'capa',propria['cantos'])
                        if fotos.distancia_capas(conteudo,resposta.content)>18:
                            aviso='capa não confere com o Discogs'
                        dados['capa_discogs_url']=url
                    except Exception:
                        aviso='conferir capa com o Discogs: imagem indisponível'
                    if aviso:
                        if aviso not in pend: dados['pendencias']='; '.join(filter(None,[pend,aviso]))
                        dados['publicar']='nao'
                gravar(dados); resumo['rascunhos']+=1
                continue
            if not numero(l.get('preco')): raise ErroCadastro('sem preço')
            loja=LojaCadastro(api or NuvemshopAPI(config))
            if not l.get('produto_id') or l.get('cadastro_execucao') or (Path(pasta_api)/('cadastro_'+sku_da_linha(did)+'.json')).exists():
                drive=drive or DriveFotos(config,c.get('Cadastro: pasta de entrada Drive (ID)',''))
                # Revalida a aprovação imediatamente antes das escritas externas.
                atuais=ler(planilha,ABA); atual=next(dict(zip(atuais[0],r)) for r in atuais[1:] if r and r[0]==did)
                if atual.get('status')!='aprovado': continue
                if any(str(atual.get(k,''))!=str(l.get(k,'')) for k in set(atual)|set(l) if k not in COLUNAS_CONFERENCIA and k!='status'): continue  # houve edição depois do início da rodada; esperar a próxima
                def confirmar():
                    rows=ler(planilha,ABA)
                    matches=[dict(zip(rows[0],r)) for r in rows[1:] if r and r[0]==did]
                    fs_atuais=ler(planilha,'cadastro_fotos')
                    fotos_atuais=[dict(zip(fs_atuais[0],r)) for r in fs_atuais[1:] if r and r[0]==did] if fs_atuais else []
                    return fotos_atuais==minhas_fotos and len(matches)==1 and matches[0].get('status')=='aprovado' and all(
                        str(matches[0].get(k,''))==str(l.get(k,'')) for k in COLUNAS if k not in ('produto_id','link_loja','cadastro_execucao','fotos_ajustadas')+COLUNAS_CONFERENCIA)
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
