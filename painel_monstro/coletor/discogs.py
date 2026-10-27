"""Dados de edição, sem imagens nem dados de compradores do Discogs."""
import re
import time
import unicodedata

import requests


def normalizar(texto):
    return re.sub(r'[^a-z0-9]', '', unicodedata.normalize('NFKD', str(texto)).encode('ascii', 'ignore').decode().lower())


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

    def buscar(self, titulo, catalogo='', url=''):
        if url:
            m = re.fullmatch(r'https://(?:www\.)?discogs\.com/(?:[a-z]{2}(?:_[A-Z]{2})?/)?release/(\d+)(?:-[^?#]*)?/?', url.strip().split('?')[0])
            if not m:
                raise ErroDiscogs('URL Discogs inválida: precisa ser uma edição release.')
            rid = int(m[1])
        else:
            resultados = self.get('/database/search', type='release', country='Brazil', format='Vinyl',
                                  **({'catno': catalogo} if catalogo else {'q': titulo}))
            if not resultados.get('results') and catalogo:
                resultados = self.get('/database/search', type='release', country='Brazil', format='Vinyl', q=titulo)
            rs = resultados.get('results', [])
            # Considerar o total da paginação: uma página com 1 item não significa 1 resultado global.
            total = int((resultados.get('pagination') or {}).get('items', len(rs)))
            exatos = [r for r in rs if catalogo and normalizar(r.get('catno', '')) == normalizar(catalogo)]
            escolhido = rs[0] if total == 1 and len(rs) == 1 else (exatos[0] if len(exatos) == 1 else None)
            if escolhido is None:
                return {'discogs_confianca': 'baixa'}
            rid = int(escolhido['id'])
        release = self.get(f'/releases/{rid}')
        faixas = [' '.join(x for x in (t.get('position'), t.get('title'), '(' + t['duration'] + ')' if t.get('duration') else '') if x)
                  for t in release.get('tracklist', []) if t.get('type_', 'track') == 'track']
        creditos = '; '.join(f"{c.get('role', '')}: {c.get('name', '')}" for c in release.get('extraartists', [])
                             if re.search(r'produc|vocal|guitar|bass|drum|keyboards|cover|design|artwork', c.get('role', ''), re.I))[:400]
        dados = dict(discogs_id=str(rid), discogs_url=f'https://www.discogs.com/release/{rid}',
                     discogs_confianca='alta', faixas='\n'.join(faixas), creditos=creditos)
        try:
            stats = self.get(f'/marketplace/stats/{rid}', curr_abbr='BRL')
            menor = stats.get('lowest_price') or {}
            dados.update(discogs_menor_preco=menor.get('value', '') if menor.get('currency') == 'BRL' else '',
                         discogs_a_venda=stats.get('num_for_sale', ''))
        except ErroDiscogs:
            pass  # A falta de preço de mercado não invalida a identificação da edição.
        return dados
