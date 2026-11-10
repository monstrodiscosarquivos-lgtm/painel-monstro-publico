"""Dados de edição, sem imagens nem dados de compradores do Discogs."""
import re
import time
import unicodedata

import requests


def normalizar(texto):
    return re.sub(r'[^a-z0-9]', '', unicodedata.normalize('NFKD', str(texto)).encode('ascii', 'ignore').decode().lower())


def eh_album_homonimo(artista: str, album: str) -> bool:
    """Identifica álbuns homônimos, autointitulados ou coletâneas com nomes genéricos."""
    art = normalizar(artista)
    alb = normalizar(album)
    if not art or not alb:
        return False
    if art == alb or alb in art or art in alb:
        return True
    alb_texto = unicodedata.normalize('NFKD', str(album)).encode('ascii', 'ignore').decode().lower().strip()
    if re.search(r'\b(vol\b|vol\.|volume)\s*(\d+|[ivxlcdm]+)?\b', alb_texto):
        return True
    genericos = [
        'os maiores sucessos', 'grandes sucessos', 'sucessos', 'selecao de ouro',
        'super sucessos', 'disco de ouro', 'coletanea', 'as melhores', 'ao vivo',
        'serie ouro', 'serie autografos de sucesso', 'sucessos de ouro', 'preferencia nacional',
        'sucessos inesqueciveis', 'melhores momentos', 'grandes sucessos de'
    ]
    for g in genericos:
        if alb_texto == g or alb_texto.startswith(g + ' ') or alb_texto.endswith(' ' + g):
            return True
    return False


class ErroDiscogs(Exception):
    pass


class Discogs:
    def __init__(self, token, sessao=None, dormir=time.sleep, relogio=time.monotonic):
        self.token = token
        self.sessao = sessao or requests.Session()
        self.dormir, self.relogio = dormir, relogio
        self.proxima = 0

    def get(self, caminho, **params):
        if not self.token:
            raise ErroDiscogs('Falta DISCOGS_TOKEN nos Secrets.')
        self.dormir(max(0, self.proxima - self.relogio()))
        try:
            r = self.sessao.get('https://api.discogs.com' + caminho, params=params, timeout=30,
                                allow_redirects=False, headers={'Authorization': 'Discogs token=' + self.token,
                                'User-Agent': 'PainelMonstro/1.0 +https://lojamonstro.com.br'})
            self.proxima = self.relogio() + 1.1
            if int(r.headers.get('X-Discogs-Ratelimit-Remaining', '60')) <= 1:
                self.proxima = self.relogio() + 60
            if r.status_code == 429:
                self.proxima = self.relogio() + max(60, float(r.headers.get('Retry-After', '60')))
            if r.status_code != 200:
                raise ErroDiscogs('Discogs indisponível ou sem permissão; tentar novamente.')
            return r.json()
        except ErroDiscogs:
            raise
        except Exception:
            raise ErroDiscogs('Falha ao consultar Discogs.') from None

    def buscar(self, titulo, catalogo='', url='', barcode='', artista='', album=''):
        if not (artista and album):
            m = re.match(r'^(?:LP|Livro)?\s*(.+?)\s+-\s+(.+?)(?:\s+\(\d{4}\))?(?:\s+-\s+.*)?$', titulo)
            if m:
                artista = artista or m.group(1).strip()
                album = album or m.group(2).strip()
        eh_hom = eh_album_homonimo(artista, album) if (artista and album) else False

        if barcode:
            resultados = self.get('/database/search', type='release', barcode=barcode)
            rs = resultados.get('results', [])
            total = int((resultados.get('pagination') or {}).get('items', len(rs)))
            exatos = [r for r in rs if catalogo and normalizar(r.get('catno', '')) == normalizar(catalogo)]
            escolhido = rs[0] if total == 1 and len(rs) == 1 else (exatos[0] if len(exatos) == 1 else None)
            if escolhido is None:
                return {'discogs_confianca': 'baixa'}
            url = 'https://www.discogs.com/release/' + str(int(escolhido['id']))
        if url:
            m = re.fullmatch(r'https://(?:www\.)?discogs\.com/(?:[a-z]{2}(?:_[A-Z]{2})?/)?release/(\d+)(?:-[^?#]*)?/?', url.strip().split('?')[0])
            if not m:
                raise ErroDiscogs('URL Discogs inválida: precisa ser uma edição release.')
            rid = int(m[1])
        else:
            if eh_hom and not catalogo:
                return {'discogs_confianca': 'baixa'}
            resultados = self.get('/database/search', type='release', country='Brazil', format='Vinyl',
                                  **({'catno': catalogo} if catalogo else {'q': titulo}))
            if not resultados.get('results') and catalogo:
                resultados = self.get('/database/search', type='release', country='Brazil', format='Vinyl', q=titulo)
            rs = resultados.get('results', [])
            # Considerar o total da paginação: uma página com 1 item não significa 1 resultado global.
            total = int((resultados.get('pagination') or {}).get('items', len(rs)))
            exatos = [r for r in rs if catalogo and normalizar(r.get('catno', '')) == normalizar(catalogo)]
            if catalogo:
                escolhido = exatos[0] if len(exatos) == 1 else (rs[0] if total == 1 and len(rs) == 1 and not eh_hom else None)
            elif not eh_hom:
                escolhido = rs[0] if total == 1 and len(rs) == 1 else None
            else:
                escolhido = None
            if escolhido is None:
                return {'discogs_confianca': 'baixa'}
            rid = int(escolhido['id'])
        release = self.get(f'/releases/{rid}')
        if catalogo:
            cat_norm = normalizar(catalogo)
            cat_labels = [normalizar(l.get('catno', '')) for l in release.get('labels', [])]
            cat_ident = [normalizar(ident.get('value', '')) for ident in release.get('identifiers', []) if ident.get('type') in ('Cat#', 'Catalog Number')]
            if cat_labels and cat_norm not in cat_labels and (not cat_ident or cat_norm not in cat_ident):
                if eh_hom:
                    return {'discogs_confianca': 'baixa'}
        elif eh_hom:
            return {'discogs_confianca': 'baixa'}

        faixas = [' '.join(x for x in (t.get('position'), t.get('title'), '(' + t['duration'] + ')' if t.get('duration') else '') if x)
                  for t in release.get('tracklist', []) if t.get('type_', 'track') == 'track']
        creditos = '; '.join(f"{c.get('role', '')}: {c.get('name', '')}" for c in release.get('extraartists', [])
                             if re.search(r'produc|vocal|guitar|bass|drum|keyboards|cover|design|artwork', c.get('role', ''), re.I))[:400]
        dados = dict(discogs_id=str(rid), discogs_url=f'https://www.discogs.com/release/{rid}',
                     discogs_confianca='alta', faixas='\n'.join(faixas), creditos=creditos)
        if release.get('year'):
            dados['discogs_ano'] = str(release['year'])
        try:
            stats = self.get(f'/marketplace/stats/{rid}', curr_abbr='BRL')
            menor = stats.get('lowest_price') or {}
            dados.update(discogs_menor_preco=menor.get('value', '') if menor.get('currency') == 'BRL' else '',
                         discogs_a_venda=stats.get('num_for_sale', ''))
        except ErroDiscogs:
            pass  # A falta de preço de mercado não invalida a identificação da edição.
        return dados
