"""Mostra os indicadores de hoje numa tabela.

Uso (na pasta do projeto):
    python scripts/indicadores_hoje.py            (atualiza pela API da Nuvemshop e calcula)
    python scripts/indicadores_hoje.py --csv      (usa as exportações em dados/entrada, sem internet)

Custos: lê `dados/custos.csv` (separador ";", colunas da aba custos) se o arquivo existir. Na Etapa 4 isso
passa a vir da aba `custos` da Planilha Google.
"""
from __future__ import annotations

import os
import sys

import pandas as pd

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from painel_monstro.log_publico import comando_seguro, ArgumentParserSeguro, resumo_erro
from painel_monstro.config import carregar  # noqa: E402
from painel_monstro.coletor import nuvemshop_api, planilhas_csv  # noqa: E402
from painel_monstro.motor import indicadores, regua  # noqa: E402

CAMINHO_CUSTOS = os.path.join(RAIZ, 'dados', 'custos.csv')


@comando_seguro
def main() -> int:
    if '--csv' in sys.argv:
        tabelas = planilhas_csv.coletar(os.path.join(RAIZ, 'dados', 'entrada'))
        origem = 'exportações em CSV'
    else:
        tabelas, _ = nuvemshop_api.coletar(carregar())
        origem = 'API da Nuvemshop'
    custos = indicadores.ler_custos(CAMINHO_CUSTOS)
    resultado = indicadores.calcular(tabelas, custos)

    print(f'Indicadores de {resultado.referencia - pd.Timedelta(days=1):%d/%m/%Y} (dados: {origem}; '
          f'aba custos: {len(custos)} mês(es) preenchido(s))\n')
    print(f'| {"Grupo":<26} | {"Indicador":<58} | {"Valor":>12} | Observação')
    print(f'|{"-" * 28}|{"-" * 60}|{"-" * 14}|-----------')
    for r in resultado.resumo.itertuples():
        valor = indicadores.formatar(r.valor, r.unidade) if r.estado == indicadores.OK else r.estado
        print('Indicador calculado; detalhes disponíveis somente nos dados privados.')

    classificacao, referencia = regua.rodar(tabelas, f'{referencia_mes(resultado.referencia)}')
    print(f'\nRégua de hoje (data de referência {referencia:%d/%m/%Y}):')
    print('Resumo da régua calculado; detalhes nos dados privados.')
    q = resultado.qualidade
    print(f'\nQualidade: {q["itens_sem_produto_correspondente_pct"]:.1f}% dos itens pagos não achei no catálogo atual; '
          f'{q["itens_usado_pct"]:.0f}% usados, {q["itens_lacrado_pct"]:.0f}% lacrados.')
    return 0


def referencia_mes(referencia: pd.Timestamp) -> str:
    return referencia.strftime('%Y-%m')


if __name__ == '__main__':
    sys.exit(main())
