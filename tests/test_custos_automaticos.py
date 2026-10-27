"""Custos automáticos: só dados fictícios, nenhuma chamada real."""
import json
from types import SimpleNamespace

import pandas as pd
import pytest

from painel_monstro.config import Config
from painel_monstro.motor.indicadores import ler_custos
from painel_monstro.saidas import custos_automaticos as ca
from painel_monstro.saidas.brevo import Brevo, ErroBrevo
from tests.ajuda import pedido, tabelas


class BrevoFalso:
    def __init__(self):
        self.chamadas = []

    def receita_periodo(self, inicio, fim):
        self.chamadas.append((inicio, fim))
        return 1234.56


def test_brevo_total_sem_somar_fontes_e_resposta_incompleta(monkeypatch):
    b = Brevo('falsa')
    chamadas = []
    def pedir(metodo, caminho, params):
        chamadas.append((metodo, caminho, params))
        return {'totals': {'revenue': 1534.60000000004}, 'results': [{'revenue': 1534.6}]}
    monkeypatch.setattr(b, '_pedir', pedir)
    assert b.receita_periodo('inicio', 'fim') == 1534.6
    assert chamadas[0][0] == 'GET'
    monkeypatch.setattr(b, '_pedir', lambda *a: {})
    with pytest.raises(ErroBrevo):
        b.receita_periodo('inicio', 'fim')


def test_manual_preservado_e_margens_nao_normalizadas_duas_vezes():
    manual = ler_custos(pd.DataFrame([{'mes': '2026-09', 'receita_brevo': 900, 'margem_usados': 55}]))
    antes = manual.copy()
    auto = pd.DataFrame([dict(mes='2026-09', campo='receita_brevo', valor=1234, estado='ok'),
                         dict(mes='2026-10', campo='receita_brevo', valor=1500, estado='ok'),
                         dict(mes='2026-09', campo='frete_pago_loja', valor=None, estado='pendente')])
    c = ca.combinar(manual, auto).set_index('mes')
    assert c.loc['2026-09', 'receita_brevo'] == 900
    assert c.loc['2026-09', 'margem_usados'] == .55
    assert c.loc['2026-10', 'receita_brevo'] == 1500
    assert pd.isna(c.loc['2026-09', 'frete_pago_loja'])
    pd.testing.assert_frame_equal(manual, antes)


def test_receita_brevo_aparece_sem_meta_e_frete_pendente_nao_inventa_margem():
    from painel_monstro.motor import indicadores
    t = tabelas([pedido(1, 'a@exemplo.com', '2026-09-10', 100)])
    auto = pd.DataFrame([dict(mes='2026-09', campo='receita_brevo', valor=50, estado='ok'),
                         dict(mes='2026-09', campo='frete_pago_loja', valor=None, estado='pendente')])
    c = ca.combinar(ler_custos(None), auto)
    ind = indicadores.calcular(t, c, referencia=pd.Timestamp('2026-10-12'))
    resumo = ind.resumo.set_index('indicador')
    assert resumo.loc['Vendas atribuídas aos envios (Brevo)', 'valor'] == 50
    assert pd.isna(ind.mensal.loc['2026-09', 'frete_pago_loja'])
    assert pd.isna(resumo.loc['Descontos e fretes pagos ÷ receita', 'valor'])


def test_frete_mes_ignora_cancelados_e_outra_data(tmp_path):
    t = tabelas([pedido(1, 'a@exemplo.com', '2026-09-10', 100),
                 pedido(2, 'b@exemplo.com', '2026-10-10', 100)])
    t.pedidos.loc[t.pedidos['numero'].astype(str) == '1', 'valido'] = False
    t.pedidos['frete'] = 0
    class SemChamadas:
        def _get(self, *args):
            raise AssertionError('Não consultar pedido cancelado ou de outro mês.')
    _, paginas = ca.preparar(Config(), ler_custos(None), t, str(tmp_path), api=SemChamadas(),
                             agora=pd.Timestamp('2026-10-12'))
    df = paginas[0][1].set_index('campo')
    assert df.loc['frete_pago_loja', 'valor'] == 0
    assert df.loc['frete_pago_loja', 'estado'] == 'ok'


def test_cache_diario_mes_anterior_atual_e_reconsulta_dia_seguinte(tmp_path):
    b = BrevoFalso()
    c = Config(brevo_api_key='falsa')
    t = tabelas([pedido(1, 'a@exemplo.com', '2026-09-01', 100)])
    agora = pd.Timestamp('2026-10-12', tz='America/Sao_Paulo')
    args = (c, ler_custos(None), t, str(tmp_path))
    custos, paginas = ca.preparar(*args, agora=agora, cliente_brevo=b)
    assert list(custos['mes']) == ['2026-09']
    assert len(b.chamadas) == 1
    assert b.chamadas[0] == ('2026-09-01T00:00:00-03:00', '2026-09-30T23:59:59-03:00')
    ca.preparar(*args, agora=agora, cliente_brevo=b)
    assert len(b.chamadas) == 1
    ca.preparar(*args, agora=agora + pd.Timedelta(days=1), cliente_brevo=b)
    assert len(b.chamadas) == 2
    assert paginas[0][0] == 'custos_automaticos'
    assert 'falsa' not in (tmp_path / 'custos_automaticos.json').read_text()


def test_falha_brevo_nao_vira_zero(tmp_path):
    class Falha:
        def receita_periodo(self, *args):
            raise ValueError('erro com segredo que não deve aparecer')
    c, paginas = ca.preparar(Config(brevo_api_key='falsa'), ler_custos(None), tabelas([pedido(1, 'a@exemplo.com', '2026-09-01', 100)]), str(tmp_path),
                            agora=pd.Timestamp('2026-10-12'), cliente_brevo=Falha())
    assert c.empty
    df = paginas[0][1]
    assert (df['estado'] == 'pendente').all() and df['valor'].isna().all()
    assert 'segredo' not in df.to_json()


class API:
    _base = 'https://exemplo.com'

    def __init__(self, entregas):
        self.entregas = entregas

    def _get(self, url):
        return SimpleNamespace(json=lambda: self.entregas)


def entrega(tipo='ship', custo=25, cliente=0):
    return {'shipping': {'type': tipo, 'merchant_cost': {'value': custo, 'currency': 'BRL'},
                         'consumer_cost': {'value': cliente, 'currency': 'BRL'}}}


def test_frete_gratis_exclui_retirada_e_pedido_pago_pelo_cliente():
    pedidos = pd.DataFrame([dict(numero='1', frete=0), dict(numero='2', frete=15)])
    assert ca.frete_do_mes(API([entrega(), entrega('pickup')]), pedidos, {'1': {'id': 5}}) == 25
    assert ca.frete_do_mes(API([entrega('pickup')]), pedidos, {'1': {'id': 5}}) == 0


@pytest.mark.parametrize('entregas', [[], [{}], [entrega(custo=None)], [entrega(custo=0)]])
def test_frete_incompleto_nao_vira_zero(entregas):
    with pytest.raises((ValueError, TypeError)):
        ca.frete_do_mes(API(entregas), pd.DataFrame([dict(numero='1', frete=0)]), {'1': {'id': 5}})


def test_meta_nao_soma_categorias_de_compra_sobrepostas():
    class Sessao:
        def get(self, url, **kwargs):
            assert 'access_token' not in kwargs['params']
            assert kwargs['params']['action_report_time'] == 'conversion'
            return SimpleNamespace(status_code=200, json=lambda: {'data': [{'spend': '100', 'account_currency': 'BRL',
                'actions': [{'action_type': 'purchase', 'value': '8'}, {'action_type': 'offsite_conversion.fb_pixel_purchase', 'value': '8'}],
                'action_values': [{'action_type': 'purchase', 'value': '500'}, {'action_type': 'offsite_conversion.fb_pixel_purchase', 'value': '500'}]}]})
    c = Config(meta_ads_account_id='123', meta_ads_token='falso')
    assert ca.meta_do_mes(c, '2026-09', Sessao()) == dict(investimento_meta=100, compras_meta=8, receita_meta=500)
