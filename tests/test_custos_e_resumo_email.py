"""Aba custos (mês como texto ou data, margens como 40 ou 0,4) e o email de resumo de segunda."""
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from painel_monstro.motor.indicadores import ler_custos
from painel_monstro.saidas import resumo_email as re_


@pytest.mark.parametrize('mes', [
    '2026-10', '2026-10-01', '2026-10-15 00:00:00', '01/10/2026', '10/2026', 'out/2026', 'Outubro 2026', 'out 2026',
    pd.Timestamp('2026-10-01'), datetime(2026, 10, 1), 46296.0, 46296,  # 46296 = 01/10/2026 na contagem de dias do Google Sheets
])
def test_mes_da_aba_custos_em_qualquer_formato(mes):
    df = pd.DataFrame({'mes': [mes], 'investimento_meta': [1000]})
    assert list(ler_custos(df)['mes']) == ['2026-10']


@pytest.mark.parametrize('margem,esperado', [(40, 0.40), ('40', 0.40), ('0,4', 0.4), (0.4, 0.4), ('40%', 0.40), ('0,45', 0.45), (45, 0.45), ('45,5', 0.455)])
def test_margem_como_percentual_ou_fracao(margem, esperado):
    df = pd.DataFrame({'mes': ['2026-10'], 'margem_usados': [margem], 'margem_lacrados': [margem]})
    c = ler_custos(df)
    assert c['margem_usados'].iloc[0] == pytest.approx(esperado)
    assert c['margem_lacrados'].iloc[0] == pytest.approx(esperado)


def test_valores_em_reais_e_meses_juntos():
    df = pd.DataFrame({'mes': [46296, '2026-11'], 'investimento_meta': ['R$ 1.234,50', 800], 'embalagem': ['2,5', 3]})
    c = ler_custos(df)
    assert list(c['mes']) == ['2026-10', '2026-11']
    assert c['investimento_meta'].tolist() == [1234.5, 800.0] and c['embalagem'].tolist() == [2.5, 3.0]


def test_mes_invalido_e_ignorado():
    df = pd.DataFrame({'mes': ['abril', '', None, 7.0], 'investimento_meta': [1, 2, 3, 4]})
    assert len(ler_custos(df)) == 0


# ----------------------------------------------------------------------------
# Email de resumo
# ----------------------------------------------------------------------------
ATUAL = {'receita_quem_volta_mes': 6250.5, 'clientes_12m': 1068, 'taxa_volta_mes_pct': 2.33, 'gasto_recompra': 250.86,
         'participacao_pct': 28.1, 'volta_90d_pct': 7.15, 'custo_marketing_pct': float('nan'),
         'meta_receita_quem_volta': 9000, 'meta_participacao_pct': 35, 'teto_marketing_pct': 15}
SEMANA = [['indicador', 'valor'], ['Período', '13/10 a 19/10'], ['Mensagens enviadas (marcadas pela Mariana)', 12],
          ['Não contatados (saíram da fila sem toque)', 3]]
VALE = [{'acao': 'Carrinho · WhatsApp', 'estado': 'dados insuficientes'},
        {'acao': 'Régua · Etapa 1', 'estado': 'ok', 'receita_a_mais': 1200.0, 'resultado': 1080.0}]
INDICADORES = [{'estado': 'ok'}, {'estado': 'falta custos'}, {'estado': 'falta custos'}, {'estado': 'falta dados'}]


def test_resumo_traz_objetivo_semana_vale_a_pena_e_pendencias():
    assunto, html = re_.montar(ATUAL, SEMANA, VALE, INDICADORES, '19/10/2026 07:07', datetime(2026, 10, 19, 8, 0))
    assert assunto == 'Resumo da semana do Painel Monstro (19/10/2026)'
    assert 'R$ 6.250,50' in html and 'meta R$ 9.000,00' in html and 'faltam R$ 2.749,50' in html
    assert '28,1%' in html and 'faltam 6,9 pontos' in html
    assert '1.068' in html and '2,33%' in html
    assert 'Mensagens enviadas' in html and '13/10 a 19/10' in html and 'Não contatados' in html
    assert 'receita a mais R$ 1.200,00' in html and 'dados insuficientes ainda' in html
    assert '2 indicador(es) aguardam a aba' in html and 'aguardando a aba custos' in html


def test_resumo_nao_tem_dado_de_cliente_nem_travessao():
    _, html = re_.montar(ATUAL, SEMANA, VALE, INDICADORES, '', datetime(2026, 10, 19))
    assert '@' not in html and '—' not in html and '–' not in html
    assert '<script' not in html


def test_resumo_escapa_html_e_aceita_dados_faltando():
    assunto, html = re_.montar({}, [['indicador', 'valor'], ['<b>x</b>', 1]], [{'acao': '<i>y</i>', 'estado': 'ok'}], [], '', datetime(2026, 10, 19))
    assert '&lt;b&gt;x&lt;/b&gt;' in html and '&lt;i&gt;y&lt;/i&gt;' in html
    assert 'sem dado' in html and 'meta R$ 9.000,00' in html


def test_meta_batida():
    _, html = re_.montar({**ATUAL, 'receita_quem_volta_mes': 9500, 'participacao_pct': 36}, [], [], [], '', datetime(2026, 10, 19))
    assert html.count('meta batida') == 2
