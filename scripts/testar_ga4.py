"""Testa o acesso da conta de serviço ao GA4 (Data API).

Uso (PowerShell, na pasta painel-monstro):
    .venv\\Scripts\\python scripts\\testar_ga4.py 360685758
"""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from painel_monstro.log_publico import comando_seguro

from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession

@comando_seguro
def main():
    PROPRIEDADE = sys.argv[1] if len(sys.argv) > 1 else '360685758'
    ARQ = 'credenciais/google-service-account.json'
    for linha in open('.env', encoding='utf-8'):
        if linha.startswith('GOOGLE_SERVICE_ACCOUNT_FILE=') and linha.split('=', 1)[1].strip():
            ARQ = linha.split('=', 1)[1].strip()

    cred = service_account.Credentials.from_service_account_file(
        ARQ, scopes=['https://www.googleapis.com/auth/analytics.readonly'])
    print('Conferir acesso da conta de serviço na propriedade do GA4.')
    print('Propriedade GA4 configurada.')
    s = AuthorizedSession(cred)
    r = s.post(
        f'https://analyticsdata.googleapis.com/v1beta/properties/{PROPRIEDADE}:runReport',
        json={
            'dateRanges': [{'startDate': '30daysAgo', 'endDate': 'today'}],
            'dimensions': [{'name': 'sessionSource'}],
            'metrics': [{'name': 'sessions'}, {'name': 'ecommercePurchases'}, {'name': 'purchaseRevenue'}],
            'orderBys': [{'metric': {'metricName': 'sessions'}, 'desc': True}],
            'limit': 10,
        }, timeout=60)

    if r.ok:
        d = r.json()
        print('\nDEU CERTO. Últimos 30 dias por origem:\n')
        print(f"{'origem':30} {'sessões':>8} {'compras':>8} {'receita':>12}")
        for row in d.get('rows', []):
            o = row['dimensionValues'][0]['value']
            v = [m['value'] for m in row['metricValues']]
            print('Linha do relatório recebida; conteúdo omitido do log público.')
        sys.exit(0)

    msg = r.text
    print('\nNÃO DEU CERTO. Código', r.status_code)
    if 'has not been used' in msg or 'is disabled' in msg or 'SERVICE_DISABLED' in msg:
        print('Motivo: a "Google Analytics Data API" não está ativada no projeto painel-monstro do Google Cloud.')
    elif r.status_code == 403:
        print('Motivo: a conta de serviço não tem acesso a esta propriedade.')
        print('Conferir acesso da conta de serviço na propriedade do GA4.')
    elif r.status_code in (400, 404):
        print('Motivo: o número da propriedade parece errado (talvez seja o ID da conta, não da propriedade).')
    print('Resposta do Google omitida do log público.')
    sys.exit(1)


if __name__ == '__main__':
    sys.exit(main())
