"""Lê as configurações e os segredos do `.env` local ou das variáveis de ambiente (GitHub Secrets).

Variável de ambiente vale mais que o `.env`. Segredos nunca são impressos: o `repr` da
configuração esconde os campos secretos.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import dotenv_values

RAIZ_PROJETO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARQUIVO_ENV = os.path.join(RAIZ_PROJETO, '.env')


@dataclass(frozen=True)
class Config:
    nuvemshop_store_id: str = ''
    nuvemshop_token: str = field(default='', repr=False)
    nuvemshop_user_agent: str = ''
    brevo_api_key: str = field(default='', repr=False)
    google_service_account_file: str = ''
    google_service_account_json: str = field(default='', repr=False)  # conteúdo da chave, vindo de um Secret do GitHub
    planilha_id: str = ''
    brevo_modo_teste: bool = True
    meta_ads_account_id: str = ''
    meta_ads_token: str = field(default='', repr=False)
    meta_ads_api_version: str = 'v24.0'
    discogs_token: str = field(default='', repr=False)


def carregar(caminho_env: str = ARQUIVO_ENV) -> Config:
    valores = dict(dotenv_values(caminho_env)) if os.path.exists(caminho_env) else {}
    valores.update({k: v for k, v in os.environ.items() if k in _CHAVES})

    def pegar(chave: str) -> str:
        return (valores.get(chave) or '').strip()

    return Config(
        nuvemshop_store_id=pegar('NUVEMSHOP_STORE_ID'),
        nuvemshop_token=pegar('NUVEMSHOP_TOKEN'),
        nuvemshop_user_agent=pegar('NUVEMSHOP_USER_AGENT'),
        brevo_api_key=pegar('BREVO_API_KEY'),
        google_service_account_file=pegar('GOOGLE_SERVICE_ACCOUNT_FILE'),
        google_service_account_json=pegar('GOOGLE_SERVICE_ACCOUNT_JSON'),
        planilha_id=pegar('PLANILHA_ID'),
        meta_ads_account_id=pegar('META_ADS_ACCOUNT_ID'),
        meta_ads_token=pegar('META_ADS_TOKEN'),
        meta_ads_api_version=pegar('META_ADS_API_VERSION') or 'v24.0',
        discogs_token=pegar('DISCOGS_TOKEN'),
        # Seguro por padrão: só desliga com "nao" escrito de propósito.
        brevo_modo_teste=pegar('BREVO_MODO_TESTE').lower() not in ('nao', 'não', 'no', 'false', '0'),
    )


_CHAVES = {
    'NUVEMSHOP_STORE_ID', 'NUVEMSHOP_TOKEN', 'NUVEMSHOP_USER_AGENT', 'BREVO_API_KEY',
    'GOOGLE_SERVICE_ACCOUNT_FILE', 'GOOGLE_SERVICE_ACCOUNT_JSON', 'PLANILHA_ID', 'BREVO_MODO_TESTE',
    'META_ADS_ACCOUNT_ID', 'META_ADS_TOKEN', 'META_ADS_API_VERSION',
    'DISCOGS_TOKEN',
}
