"""Google Analytics 4 (D-076): origem das visitas e das vendas, e as vendas pelos links das bandas.

Lê a Data API do GA4 com a mesma conta de serviço da planilha (só leitura). A conta precisa
estar como Leitor na propriedade, e a "Google Analytics Data API" ativada no projeto do Google Cloud.

Grava duas abas:
- `ga4_diario`: últimos 90 dias, por dia, origem, meio e campanha (sessões, carrinhos, pagamentos iniciados,
  compras, receita). O painel soma pelo período escolhido.
- `ga4_links`: tudo que veio por links com utm_medium=link-banda desde 2026, por campanha e banda.

O GA4 conta pela sessão: uma compra entra na banda se a pessoa comprou na visita que começou pelo link.
Se ela voltar depois por outro caminho e comprar, a compra fica com esse outro caminho.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from painel_monstro.config import RAIZ_PROJETO

PROPRIEDADE_PADRAO = '360685758'
CONFIG_PROPRIEDADE = 'GA4: ID da propriedade'
ESCOPO = 'https://www.googleapis.com/auth/analytics.readonly'
ABA_DIARIO = 'ga4_diario'
ABA_LINKS = 'ga4_links'
MEIO_LINKS = 'link-banda'
LINKS_DESDE = '2026-01-01'
METRICAS = [('sessions', 'sessoes'), ('addToCarts', 'carrinhos'), ('checkouts', 'pagamentos'),
            ('ecommercePurchases', 'compras'), ('purchaseRevenue', 'receita')]
COLUNAS_DIARIO = ['data', 'origem', 'meio', 'campanha'] + [c for _, c in METRICAS]
COLUNAS_LINKS = ['campanha', 'banda'] + [c for _, c in METRICAS] + ['primeira_visita', 'ultima_visita']


class ErroGA4(Exception):
    pass


def sessao_ga4(config):
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2 import service_account
    if config.google_service_account_json:
        cred = service_account.Credentials.from_service_account_info(json.loads(config.google_service_account_json), scopes=[ESCOPO])
    else:
        cred = service_account.Credentials.from_service_account_file(str(Path(RAIZ_PROJETO) / config.google_service_account_file), scopes=[ESCOPO])
    return AuthorizedSession(cred)


def relatorio(sessao, propriedade: str, corpo: dict, limite: int = 10000) -> list[dict]:
    """runReport com paginação. Devolve uma lista de dicionários {dimensão: valor, métrica: número}."""
    dims = [d['name'] for d in corpo['dimensions']]
    mets = [m['name'] for m in corpo['metrics']]
    saida, offset = [], 0
    while True:
        r = sessao.post(f'https://analyticsdata.googleapis.com/v1beta/properties/{propriedade}:runReport',
                        json={**corpo, 'limit': limite, 'offset': offset}, timeout=90)
        if r.status_code != 200:
            raise ErroGA4(f'GA4 respondeu {r.status_code}; conteúdo da resposta omitido.')
        d = r.json()
        for row in d.get('rows', []):
            o = {k: row['dimensionValues'][i]['value'] for i, k in enumerate(dims)}
            for i, k in enumerate(mets):
                v = float(row['metricValues'][i]['value'] or 0)
                o[k] = round(v, 2) if k == 'purchaseRevenue' else int(v)
            saida.append(o)
        offset += limite
        if offset >= int(d.get('rowCount', 0) or 0):
            return saida


def _data(s: str) -> str:
    s = str(s)
    return f'{s[:4]}-{s[4:6]}-{s[6:8]}' if len(s) == 8 and s.isdigit() else s


def montar_diario(linhas: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame([{'data': _data(o['date']), 'origem': o['sessionSource'], 'meio': o['sessionMedium'],
                        'campanha': o['sessionCampaignName'], **{c: o[m] for m, c in METRICAS}} for o in linhas],
                      columns=COLUNAS_DIARIO)
    return df.sort_values(['data', 'sessoes'], ascending=[False, False]).reset_index(drop=True)


def montar_links(linhas: list[dict]) -> pd.DataFrame:
    if not linhas:
        return pd.DataFrame(columns=COLUNAS_LINKS)
    df = pd.DataFrame([{'campanha': o['sessionCampaignName'], 'banda': o['sessionSource'], 'data': _data(o['date']),
                        **{c: o[m] for m, c in METRICAS}} for o in linhas])
    g = df.groupby(['campanha', 'banda'], as_index=False).agg(
        **{c: (c, 'sum') for _, c in METRICAS}, primeira_visita=('data', 'min'), ultima_visita=('data', 'max'))
    g['receita'] = g['receita'].round(2)
    return g.sort_values(['campanha', 'compras', 'sessoes'], ascending=[True, False, False])[COLUNAS_LINKS].reset_index(drop=True)


def _metricas():
    return [{'name': m} for m, _ in METRICAS]


def passo_rotina(config, propriedade: str = '', sessao=None) -> list[tuple[str, pd.DataFrame]]:
    """Consulta o GA4 e devolve as páginas para gravar. Erro vira ErroGA4 (a rotina segue sem estas abas)."""
    propriedade = str(propriedade or PROPRIEDADE_PADRAO).strip()
    sessao = sessao or sessao_ga4(config)
    diario = relatorio(sessao, propriedade, {
        'dateRanges': [{'startDate': '89daysAgo', 'endDate': 'today'}],
        'dimensions': [{'name': n} for n in ('date', 'sessionSource', 'sessionMedium', 'sessionCampaignName')],
        'metrics': _metricas(), 'keepEmptyRows': False})
    links = relatorio(sessao, propriedade, {
        'dateRanges': [{'startDate': LINKS_DESDE, 'endDate': 'today'}],
        'dimensions': [{'name': n} for n in ('date', 'sessionCampaignName', 'sessionSource')],
        'metrics': _metricas(),
        'dimensionFilter': {'filter': {'fieldName': 'sessionMedium', 'stringFilter': {'matchType': 'EXACT', 'value': MEIO_LINKS}}}})
    return [(ABA_DIARIO, montar_diario(diario)), (ABA_LINKS, montar_links(links))]
