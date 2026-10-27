"""Coletor pela API da Nuvemshop. Só leitura: usa apenas requisições GET.

- Primeira execução baixa tudo; as seguintes baixam só o que mudou (`updated_at_min`).
- Respeita o limite de requisições (balde de 40, esvazia 2 por segundo) lendo os cabeçalhos
  `x-rate-limit-*` e tentando de novo quando recebe 429.
- O token vai só no cabeçalho `Authorization` e nunca aparece em mensagens, logs ou arquivos.
- Os registros baixados ficam em `dados/api/` (fora do git), já sem os campos que o painel não usa
  (CPF, endereços completos, dados do navegador).
- Monta as mesmas 4 tabelas do coletor por planilhas (clientes, pedidos, itens, produtos).

Uso:  python -m painel_monstro.coletor.nuvemshop_api            (baixa só o que mudou)
      python -m painel_monstro.coletor.nuvemshop_api --completo (baixa tudo de novo)
"""
from __future__ import annotations

import html
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterator

import pandas as pd
import requests

from painel_monstro.log_publico import comando_seguro, ArgumentParserSeguro, resumo_erro
from painel_monstro.config import RAIZ_PROJETO, Config
from painel_monstro.coletor.planilhas_csv import Tabelas

URL_BASE = 'https://api.nuvemshop.com.br'
VERSAO_API = '2025-03'
POR_PAGINA = 200
LIMITE_CONSULTA = 10_000  # a API não entrega mais que isso numa mesma consulta
MARGEM_INCREMENTAL = timedelta(minutes=10)  # relê um pouco antes da última sincronização
FUSO_LOJA = 'America/Sao_Paulo'
PASTA_PADRAO = os.path.join(RAIZ_PROJETO, 'dados', 'api')

PAGAMENTOS = {
    'paid': 'Confirmado', 'partially_refunded': 'Parcialmente estornado', 'pending': 'Pendente',
    'authorized': 'Autorizado', 'refunded': 'Estornado', 'voided': 'Anulado', 'abandoned': 'Abandonado',
}
PAGAMENTOS_VALIDOS = ('paid', 'partially_refunded')


class ErroAPI(Exception):
    """Erro da API. A mensagem nunca leva o token."""


# ----------------------------------------------------------------------------
# Cliente HTTP
# ----------------------------------------------------------------------------
class NuvemshopAPI:
    def __init__(self, config: Config, sessao: Any = None, dormir: Callable[[float], None] = time.sleep,
                 versao: str = VERSAO_API, max_tentativas: int = 5):
        if not (config.nuvemshop_store_id and config.nuvemshop_token and config.nuvemshop_user_agent):
            raise ErroAPI('Faltam NUVEMSHOP_STORE_ID, NUVEMSHOP_TOKEN ou NUVEMSHOP_USER_AGENT no .env.')
        self._base = f'{URL_BASE}/{versao}/{config.nuvemshop_store_id}'
        self._cabecalhos = {
            'Authorization': f'Bearer {config.nuvemshop_token}',
            'User-Agent': config.nuvemshop_user_agent,
        }
        self._sessao = sessao or requests.Session()
        self._dormir = dormir
        self._max_tentativas = max_tentativas
        self._livres: int | None = None
        self._reset_ms = 1000

    def _esperar_vaga(self) -> None:
        # Balde quase cheio: espera abrir lugar (esvazia 2 por segundo).
        if self._livres is not None and self._livres <= 2:
            self._dormir(max(self._reset_ms / 1000, 0.6))
            self._livres = None

    def _guardar_limites(self, resposta: Any) -> None:
        h = resposta.headers
        try:
            self._livres = int(h['x-rate-limit-remaining'])
            self._reset_ms = int(h.get('x-rate-limit-reset', 1000))
        except (KeyError, ValueError):
            self._livres = None

    def _get(self, url: str, params: dict | None = None, vazio_se_404: bool = False) -> Any:
        """GET com controle de limite e novas tentativas. Em listas, 404 quer dizer "nada encontrado"."""
        for tentativa in range(1, self._max_tentativas + 1):
            self._esperar_vaga()
            try:
                resposta = self._sessao.get(url, headers=self._cabecalhos, params=params, timeout=60)
            except requests.RequestException as erro:
                if tentativa == self._max_tentativas:
                    raise ErroAPI(f'Falha de rede ao acessar a Nuvemshop ({type(erro).__name__}).') from None
                self._dormir(2 ** tentativa)
                continue
            self._guardar_limites(resposta)
            if resposta.status_code == 429 or resposta.status_code >= 500:
                if tentativa == self._max_tentativas:
                    raise ErroAPI(f'A Nuvemshop respondeu {resposta.status_code} depois de {tentativa} tentativas.')
                self._dormir(max(self._reset_ms / 1000, 1) if resposta.status_code == 429 else 2 ** tentativa)
                self._livres = None
                continue
            if resposta.status_code in (401, 403):
                raise ErroAPI(f'A Nuvemshop recusou o acesso ({resposta.status_code}). Confira o token e as permissões do aplicativo.')
            if resposta.status_code == 404 and vazio_se_404:
                return None
            if resposta.status_code >= 400:
                raise ErroAPI(f'A Nuvemshop respondeu {resposta.status_code}; endereço da consulta omitido.')
            return resposta
        raise ErroAPI('Não consegui falar com a Nuvemshop.')  # inalcançável, por segurança

    def total(self, caminho: str, **filtros: Any) -> int:
        resposta = self._get(f'{self._base}/{caminho}', {'per_page': 1, **filtros}, vazio_se_404=True)
        return int(resposta.headers.get('x-total-count', 0)) if resposta is not None else 0

    def listar(self, caminho: str, **params: Any) -> Iterator[dict]:
        """Todos os registros, seguindo o cabeçalho Link (próxima página)."""
        url: str | None = f'{self._base}/{caminho}'
        parametros: dict | None = {'per_page': POR_PAGINA, **params}
        primeira = True
        while url:
            resposta = self._get(url, parametros, vazio_se_404=True)
            if resposta is None:
                return
            if primeira:
                primeira = False
                if int(resposta.headers.get('x-total-count', 0)) > LIMITE_CONSULTA:
                    raise ErroAPI(f'{caminho}: mais de {LIMITE_CONSULTA} registros numa consulta só; '
                                  'é preciso dividir por período.')
            yield from resposta.json()
            url, parametros = _proxima(resposta.headers.get('Link', '')), None


def _proxima(link: str) -> str | None:
    for parte in link.split(','):
        if 'rel="next"' in parte:
            return parte[parte.index('<') + 1:parte.index('>')]
    return None


# ----------------------------------------------------------------------------
# Limpeza dos registros (privacidade e tamanho)
# ----------------------------------------------------------------------------
def _pt(valor: Any) -> Any:
    """Campos de texto vêm por idioma ({"pt": ...}); fica o português."""
    if isinstance(valor, dict):
        return valor.get('pt') or next(iter(valor.values()), None)
    return valor


def imagem_640(src: Any) -> str:
    """URL da imagem no tamanho 640 (a CDN troca o tamanho no fim do nome do arquivo: -1024-1024 vira -640-0)."""
    s = str(src or '').strip()
    return re.sub(r'-\d+-\d+(\.\w+)(\?.*)?$', lambda m: '-640-0' + m.group(1) + (m.group(2) or ''), s) if s else ''


def texto_da_descricao(valor: Any, limite: int = 600) -> str:
    """Descrição da loja (HTML, por idioma) em texto puro, até `limite` caracteres."""
    valor = _pt(valor)
    t = re.sub(r'<(script|style).*?</>', ' ', str(valor or ''), flags=re.I | re.S)
    t = re.sub(r'<br\s*/?>|</p>|</div>|</li>', ' ', t, flags=re.I)
    t = html.unescape(re.sub(r'<[^>]+>', ' ', t))
    t = re.sub(r'\s+', ' ', t.replace(' ', ' ')).strip()
    return t if len(t) <= limite else t[:limite - 1].rstrip() + '…'


def _enxugar_pedido(p: dict) -> dict:
    return {
        'id': p['id'], 'number': p.get('number'), 'created_at': p.get('created_at'), 'updated_at': p.get('updated_at'),
        'paid_at': p.get('paid_at'), 'contact_email': p.get('contact_email'), 'status': p.get('status'),
        'payment_status': p.get('payment_status'), 'shipping_status': p.get('shipping_status'),
        'subtotal': p.get('subtotal'), 'discount': p.get('discount'), 'total': p.get('total'),
        'gateway_name': p.get('gateway_name'),
        'payment_method': (p.get('payment_details') or {}).get('method'),
        'coupon': [{'code': c.get('code'), 'type': c.get('type'), 'value': c.get('value')} for c in p.get('coupon') or []],
        'shipping_option': next((((f.get('shipping') or {}).get('option') or {}).get('name')
                                 for f in p.get('fulfillments') or []), None),
        'products': [{'product_id': i.get('product_id'), 'variant_id': i.get('variant_id'), 'name': i.get('name'),
                      'price': i.get('price'), 'quantity': i.get('quantity'), 'sku': i.get('sku'), 'cost': i.get('cost')}
                     for i in p.get('products') or []],
    }


def _enxugar_cliente(c: dict) -> dict:
    endereco = c.get('default_address') or {}
    return {
        'id': c['id'], 'name': c.get('name'), 'email': c.get('email'), 'phone': c.get('phone'),
        'city': endereco.get('city'), 'province': endereco.get('province'),
        'total_spent': c.get('total_spent'), 'accepts_marketing': c.get('accepts_marketing'),
        'accepts_marketing_updated_at': c.get('accepts_marketing_updated_at'),
        'active': c.get('active'), 'created_at': c.get('created_at'), 'updated_at': c.get('updated_at'),
    }


def _enxugar_produto(p: dict) -> dict:
    return {
        'id': p['id'], 'name': _pt(p.get('name')), 'handle': _pt(p.get('handle')), 'brand': p.get('brand'),
        'published': p.get('published'), 'created_at': p.get('created_at'), 'updated_at': p.get('updated_at'),
        'categories': [_pt(c.get('name')) for c in p.get('categories') or []],
        'image': imagem_640(((p.get('images') or [{}])[0] or {}).get('src')),
        'description': texto_da_descricao(p.get('description')),
        'variants': [{'price': v.get('price'), 'promotional_price': v.get('promotional_price'), 'stock': v.get('stock'),
                      'stock_management': v.get('stock_management'), 'sku': v.get('sku'), 'cost': v.get('cost')}
                     for v in p.get('variants') or []],
    }


@dataclass(frozen=True)
class Recurso:
    caminho: str
    campos: str
    enxugar: Callable[[dict], dict]


RECURSOS = {
    'pedidos': Recurso('orders',
                       'id,number,created_at,updated_at,paid_at,contact_email,status,payment_status,shipping_status,'
                       'subtotal,discount,total,gateway_name,payment_details,coupon,fulfillments,products',
                       _enxugar_pedido),
    'clientes': Recurso('customers',
                        'id,name,email,phone,default_address,total_spent,accepts_marketing,'
                        'accepts_marketing_updated_at,active,created_at,updated_at',
                        _enxugar_cliente),
    'produtos': Recurso('products', 'id,name,handle,brand,published,categories,variants,images,description,created_at,updated_at',
                        _enxugar_produto),
}


# ----------------------------------------------------------------------------
# Sincronização (completa na primeira vez, depois só o que mudou)
# ----------------------------------------------------------------------------
def _formato_api(momento: datetime) -> str:
    return momento.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S+0000')


class Armazem:
    """Guarda os registros e a data da última sincronização em arquivos JSON."""

    def __init__(self, pasta: str = PASTA_PADRAO):
        self.pasta = pasta

    def _caminho(self, nome: str) -> str:
        return os.path.join(self.pasta, f'{nome}.json')

    def _ler(self, nome: str, padrao: Any) -> Any:
        try:
            with open(self._caminho(nome), encoding='utf-8') as arq:
                return json.load(arq)
        except FileNotFoundError:
            return padrao

    def _gravar(self, nome: str, dados: Any) -> None:
        os.makedirs(self.pasta, exist_ok=True)
        temporario = self._caminho(nome) + '.tmp'
        with open(temporario, 'w', encoding='utf-8') as arq:
            json.dump(dados, arq, ensure_ascii=False)
        os.replace(temporario, self._caminho(nome))  # troca inteira: nunca fica arquivo pela metade

    def registros(self, recurso: str) -> dict[str, dict]:
        return {str(r['id']): r for r in self._ler(recurso, [])}

    def guardar_registros(self, recurso: str, registros: dict[str, dict]) -> None:
        self._gravar(recurso, list(registros.values()))

    def estado(self) -> dict:
        return self._ler('estado', {})

    def guardar_estado(self, estado: dict) -> None:
        self._gravar('estado', estado)


def sincronizar(api: NuvemshopAPI, armazem: Armazem, recurso: str, completo: bool = False,
                agora: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> dict:
    """Atualiza um recurso. Devolve {'novos', 'atualizados', 'total', 'modo'}."""
    definicao = RECURSOS[recurso]
    estado = armazem.estado()
    guardados = armazem.registros(recurso)
    inicio = agora()  # tomado antes de baixar: o que mudar durante o download entra na próxima vez
    anterior = estado.get(recurso, {}).get('sincronizado_em')
    incremental = bool(anterior) and bool(guardados) and not completo
    if recurso == 'produtos' and any('image' not in r for r in guardados.values()):
        incremental = False  # registros guardados antes de existirem imagem e descrição: baixa tudo uma vez

    params: dict[str, Any] = {'fields': definicao.campos}
    if incremental:
        params['updated_at_min'] = _formato_api(datetime.fromisoformat(anterior) - MARGEM_INCREMENTAL)
    baixados = [definicao.enxugar(r) for r in api.listar(definicao.caminho, **params)]

    if not incremental and not baixados and guardados:
        raise ErroAPI(f'{recurso}: a Nuvemshop não devolveu nenhum registro; os dados guardados foram mantidos.')
    base = dict(guardados) if incremental else {}
    novos = sum(1 for r in baixados if str(r['id']) not in base)
    for r in baixados:
        base[str(r['id'])] = r

    # Registro apagado na loja não aparece no incremental: se a contagem não fecha, baixa tudo de novo.
    if incremental and api.total(definicao.caminho) != len(base):
        return sincronizar(api, armazem, recurso, completo=True, agora=agora)

    armazem.guardar_registros(recurso, base)
    estado[recurso] = {'sincronizado_em': inicio.astimezone(timezone.utc).isoformat(), 'total': len(base)}
    armazem.guardar_estado(estado)
    return {'novos': novos, 'atualizados': len(baixados) - novos, 'total': len(base),
            'modo': 'incremental' if incremental else 'completo'}


# ----------------------------------------------------------------------------
# Registros -> tabelas (mesmas colunas do coletor por planilhas)
# ----------------------------------------------------------------------------
def _numero(valor: Any) -> float:
    return pd.to_numeric(valor, errors='coerce')


def _data_loja(serie: pd.Series) -> pd.Series:
    """As datas da API vêm em UTC; as exportações usam o horário de Brasília."""
    return pd.to_datetime(serie, utc=True, errors='coerce').dt.tz_convert(FUSO_LOJA).dt.tz_localize(None)


def _email(serie: pd.Series) -> pd.Series:
    return serie.str.strip().str.lower()


def montar_tabelas(pedidos: list[dict], clientes: list[dict], produtos: list[dict]) -> Tabelas:
    p = pd.DataFrame(pedidos)
    p['email'] = _email(p['contact_email'])
    p['data'] = _data_loja(p['created_at'])
    p['valido'] = p['payment_status'].isin(PAGAMENTOS_VALIDOS) & (p['status'] != 'cancelled')  # cancelado não conta, mesmo se foi pago
    p['numero'] = p['number'].astype(str)
    subtotal, desconto, total = _numero(p['subtotal']), _numero(p['discount']), _numero(p['total'])
    tabela_pedidos = pd.DataFrame({
        'numero': p['numero'], 'email': p['email'], 'data': p['data'],
        'status_pedido': p['status'], 'status_pagamento': p['payment_status'].map(PAGAMENTOS).fillna(p['payment_status']),
        'valido': p['valido'], 'subtotal': subtotal, 'desconto': desconto,
        # A API não informa o frete do pedido; sai da conta total = subtotal - desconto + frete.
        'frete': (total - subtotal + desconto).round(2),
        'total': total, 'taxas': float('nan'), 'total_liquido': float('nan'),
        'cupom': [', '.join(c['code'] for c in cs if c.get('code')) or None for cs in p['coupon']],
        'forma_pagamento': p['payment_method'], 'forma_entrega': p['shipping_option'],
        # A API não informa o valor estornado (só o status do pagamento); fica vazio. Coluna nova: sempre no fim.
        'estorno': float('nan'),
    }).sort_values('data').reset_index(drop=True)

    linhas = [{'numero': str(pe['number']), 'email': em, 'data': da, 'valido': va, 'produto': i.get('name'),
               'valor': _numero(i.get('price')), 'quantidade': _numero(i.get('quantity')), 'sku': i.get('sku') or None,
               'produto_id': _numero(i.get('product_id'))}
              for pe, em, da, va in zip(pedidos, p['email'], p['data'], p['valido']) for i in pe['products']]
    tabela_itens = pd.DataFrame(linhas, columns=['numero', 'email', 'data', 'valido', 'produto', 'valor', 'quantidade', 'sku', 'produto_id'])

    validos = tabela_pedidos[tabela_pedidos['valido']].groupby('email')['data'].agg(['size', 'max'])
    c = pd.DataFrame(clientes)
    c['email'] = _email(c['email'])
    c = c.drop_duplicates('email', keep='last')
    nome = c['name'].fillna('').str.strip()
    tabela_clientes = pd.DataFrame({
        'email': c['email'], 'nome': nome, 'primeiro_nome': nome.str.split().str[0].str.title(),
        'telefone': c['phone'], 'cidade': c['city'], 'estado': c['province'],
        'total_consumido': _numero(c['total_spent']),
        'n_compras': c['email'].map(validos['size']).fillna(0).astype(int),
        'ultima_compra': c['email'].map(validos['max']).dt.normalize(),
        'aceita_marketing': c['accepts_marketing'].fillna(False).astype(bool), 'newsletter': None,
    }).reset_index(drop=True)

    linhas_prod = []
    for pr in produtos:
        vs = pr['variants'] or [{}]
        primeira = vs[0]
        ilimitado = any(not v.get('stock_management') for v in vs)
        estoque = sum(v.get('stock') or 0 for v in vs if v.get('stock_management'))
        linhas_prod.append({
            'url': pr['handle'], 'nome': pr['name'], 'categorias': ', '.join(c for c in pr['categories'] if c),
            'preco': _numero(primeira.get('price')), 'preco_promocional': _numero(primeira.get('promotional_price')),
            'estoque': float('nan') if ilimitado else float(estoque), 'estoque_ilimitado': ilimitado,
            'exibir': bool(pr['published']), 'sku': primeira.get('sku') or None, 'marca': pr.get('brand') or None,
            'custo': _numero(primeira.get('cost')), 'id': _numero(pr.get('id')),
            'criado_em': pr.get('created_at'), 'atualizado_em': pr.get('updated_at'),  # colunas novas ficam no fim
            'imagem': pr.get('image') or None, 'descricao': pr.get('description') or None,
        })
    tabela_produtos = pd.DataFrame(linhas_prod)
    return Tabelas(clientes=tabela_clientes, pedidos=tabela_pedidos, itens=tabela_itens, produtos=tabela_produtos)


def coletar(config: Config, pasta: str = PASTA_PADRAO, completo: bool = False,
            api: NuvemshopAPI | None = None) -> tuple[Tabelas, dict]:
    """Sincroniza os 3 recursos e devolve (tabelas, resumo por recurso)."""
    api = api or NuvemshopAPI(config)
    armazem = Armazem(pasta)
    resumo = {r: sincronizar(api, armazem, r, completo=completo) for r in RECURSOS}
    tabelas = montar_tabelas(*(list(armazem.registros(r).values()) for r in ('pedidos', 'clientes', 'produtos')))
    return tabelas, resumo


@comando_seguro
def main() -> int:
    import argparse
    from painel_monstro.config import carregar

    analisador = ArgumentParserSeguro(description='Baixa os dados da Nuvemshop (só leitura).')
    analisador.add_argument('--completo', action='store_true', help='baixa tudo de novo')
    args = analisador.parse_args()
    try:
        tabelas, resumo = coletar(carregar(), completo=args.completo)
    except ErroAPI as erro:
        print('Erro: ' + resumo_erro(erro))
        return 1
    for recurso, r in resumo.items():
        print(f'{recurso}: {r["modo"]}, {r["novos"]} novos, {r["atualizados"]} atualizados, {r["total"]} no total')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
