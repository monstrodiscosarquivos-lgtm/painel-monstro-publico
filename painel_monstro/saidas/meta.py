"""Públicos do Meta (Etapa 8): três listas por mês para subir no Gerenciador de Anúncios.

- `meta_sumiu_180`: quem sumiu há mais de 180 dias (reativação). Só quem aceita marketing e tem email.
- `meta_nao_abre`: quem não abre email, pelo segmento do Brevo indicado em "Brevo: ID do segmento não abre email".
  Fora quem se descadastrou. Sem o ID do segmento, a lista fica vazia e o resumo avisa.
- `meta_compradores_180`: quem comprou nos últimos 180 dias, para EXCLUIR dos anúncios de prospecção (D-008).

As listas ficam em abas da Planilha Google (privada) e, se pedido, em CSV dentro de `dados/meta/AAAA-MM/`
(pasta fora do git). Nenhum dado de cliente vai para o repositório. Colunas: `email`, `phone` (com 55), `fn`
(primeiro nome), `ct` (cidade), que o Meta reconhece e que ele mesmo codifica ao importar.

Uso (CSV local, para subir no Meta):
    python -m painel_monstro.saidas.meta --mes 2026-10 --csv
"""
from __future__ import annotations

import os
import re
import sys
from typing import Any

import pandas as pd

from painel_monstro.log_publico import comando_seguro, ArgumentParserSeguro, resumo_erro
from painel_monstro.coletor.planilhas_csv import Tabelas
from painel_monstro.motor import regua as motor_regua
from painel_monstro.saidas import carrinhos as c

COLUNAS = ['email', 'phone', 'fn', 'ct']
ABAS = {'sumiu_180': 'meta_sumiu_180', 'nao_abre': 'meta_nao_abre', 'compradores_180': 'meta_compradores_180'}
ABA_RESUMO = 'meta_resumo'
CONFIG_SEGMENTO = 'Brevo: ID do segmento não abre email'
DIAS_SUMIU = 180
DIAS_COMPRADORES = 180


def _linhas(df: pd.DataFrame, emails: list[str]) -> pd.DataFrame:
    """email, phone, fn, ct de cada email, a partir da tabela `clientes`."""
    base = df.drop_duplicates('email', keep='last').set_index('email') if len(df) else pd.DataFrame()
    saida = []
    for e in emails:
        r = base.loc[e] if len(base) and e in base.index else None
        saida.append({'email': e,
                      'phone': c.telefone_whatsapp(r['telefone']) if r is not None else '',
                      'fn': str(r['primeiro_nome']).strip() if r is not None and pd.notna(r['primeiro_nome']) else '',
                      'ct': str(r['cidade']).strip() if r is not None and pd.notna(r['cidade']) else ''})
    return pd.DataFrame(saida, columns=COLUNAS)


def _emails_validos(serie) -> list[str]:
    visto: list[str] = []
    for e in serie:
        e = str(e).strip().lower()
        if re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', e) and e not in visto and e != motor_regua.EMAIL_DA_LOJA:
            visto.append(e)
    return visto


def montar(tabelas: Tabelas, hoje: pd.Timestamp, nao_abrem: set[str] | None = None, descadastrados: set[str] | None = None,
           dias_sumiu: int = DIAS_SUMIU, dias_compradores: int = DIAS_COMPRADORES) -> dict[str, pd.DataFrame]:
    """As três listas. `nao_abrem`: emails do segmento do Brevo (None = segmento não configurado)."""
    descadastrados = {e.lower() for e in (descadastrados or set())}
    referencia = pd.Timestamp(hoje).normalize() + pd.Timedelta(days=1)
    clientes = tabelas.clientes
    base = motor_regua.base_clientes(tabelas, referencia)          # só quem aceita marketing e comprou alguma vez
    sumiu = [e for e in _emails_validos(base.index[base['dias'] > dias_sumiu]) if e not in descadastrados]

    pedidos = motor_regua.pedidos_validos(tabelas)
    recentes = pedidos[pedidos['data'] >= referencia - pd.Timedelta(days=dias_compradores)]
    compradores = _emails_validos(recentes['email'])

    if nao_abrem is None:
        nao = []
    else:
        aceita = set(clientes.loc[clientes['aceita_marketing'].astype(bool), 'email'].astype(str).str.lower())
        conhecidos = set(clientes['email'].astype(str).str.lower())
        # quem não está na Nuvemshop (só no Brevo) entra; quem está e não aceita marketing, não
        nao = [e for e in _emails_validos(sorted(nao_abrem)) if e not in descadastrados and (e in aceita or e not in conhecidos)]
    return {'sumiu_180': _linhas(clientes, sumiu), 'nao_abre': _linhas(clientes, nao), 'compradores_180': _linhas(clientes, compradores)}


def resumo(listas: dict[str, pd.DataFrame], mes: str, gerado_em: str, segmento_configurado: bool) -> pd.DataFrame:
    linhas = [['mes', mes], ['gerado_em', gerado_em]]
    rotulos = {'sumiu_180': 'Sumiu há mais de 180 dias (reativação)', 'nao_abre': 'Não abre email (segmento do Brevo)',
               'compradores_180': 'Compradores dos últimos 180 dias (excluir da prospecção)'}
    for chave, df in listas.items():
        linhas.append([rotulos[chave], len(df)])
        linhas.append([f'  com telefone · {rotulos[chave].split(" (")[0]}', int((df['phone'] != '').sum())])
    if not segmento_configurado:
        linhas.append(['aviso', 'Preencha "Brevo: ID do segmento não abre email" na aba Configuração para montar a lista de quem não abre.'])
    return pd.DataFrame(linhas, columns=['indicador', 'valor'])


def gravar_csv(listas: dict[str, pd.DataFrame], mes: str, raiz: str | None = None) -> list[str]:
    """CSV em dados/meta/AAAA-MM/ (fora do git), prontos para o Gerenciador de Anúncios."""
    from painel_monstro.config import RAIZ_PROJETO
    pasta = os.path.join(raiz or RAIZ_PROJETO, 'dados', 'meta', mes)
    os.makedirs(pasta, exist_ok=True)
    caminhos = []
    for chave, df in listas.items():
        caminho = os.path.join(pasta, f'{ABAS[chave]}.csv')
        df.to_csv(caminho, index=False, encoding='utf-8')
        caminhos.append(caminho)
    return caminhos


@comando_seguro
def main(argv: list[str] | None = None) -> int:
    import argparse
    from painel_monstro.config import carregar
    from painel_monstro.coletor import nuvemshop_api as nuvem
    from painel_monstro.saidas import brevo as bv
    from painel_monstro.saidas import regua_planilha as rp
    from painel_monstro.saidas.planilha_google import PlanilhaGoogle

    a = ArgumentParserSeguro(description='Monta os públicos do Meta do mês (e, com --csv, grava em dados/meta/).')
    a.add_argument('--mes', default=pd.Timestamp.now(tz=nuvem.FUSO_LOJA).strftime('%Y-%m'))
    a.add_argument('--csv', action='store_true', help='grava os CSV em dados/meta/AAAA-MM/ (fora do git)')
    args = a.parse_args(argv)
    config = carregar()
    arm = nuvem.Armazem()
    tabelas = nuvem.montar_tabelas(*(list(arm.registros(r).values()) for r in ('pedidos', 'clientes', 'produtos')))
    nao_abrem, descadastrados = None, set()
    segmento = ''
    try:
        planilha = PlanilhaGoogle.conectar(config)
        segmento = str(rp._config_por_nome(planilha).get(CONFIG_SEGMENTO, '')).strip()
    except Exception as erro:  # noqa: BLE001
        print(f'Aviso: não consegui ler a planilha ({resumo_erro(erro)}); sem o segmento do Brevo.')
    if segmento and config.brevo_api_key:
        try:
            b = bv.Brevo(config.brevo_api_key, True)
            membros = list(b.contatos_do_segmento(int(float(segmento))))
            nao_abrem = {str(m.get('email', '')).lower() for m in membros if not m.get('emailBlacklisted')}
            descadastrados = {str(m.get('email', '')).lower() for m in membros if m.get('emailBlacklisted')}
        except (bv.ErroBrevo, ValueError) as erro:
            print('Aviso: não consegui ler o segmento do Brevo; detalhes omitidos.')
    listas = montar(tabelas, pd.Timestamp.now(tz=nuvem.FUSO_LOJA).tz_localize(None), nao_abrem, descadastrados)
    for chave, df in listas.items():
        print(f'{ABAS[chave]}: {len(df)} contatos ({int((df["phone"] != "").sum())} com telefone)')
    if args.csv:
        for caminho in gravar_csv(listas, args.mes):
            print('Público gravado em arquivo privado fora do git.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
