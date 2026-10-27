"""Testes das abas de resumo para o Looker Studio (dados fictícios)."""
import numpy as np
import pandas as pd

from painel_monstro.motor import indicadores, regua
from painel_monstro.saidas import carrinhos_planilha as cp
from painel_monstro.saidas import resumos_painel as rp
from tests.ajuda import dias_atras, pedido, tabelas


def base():
    pedidos = [pedido(1, 'a@exemplo.com', '2026-05-10', 100), pedido(2, 'a@exemplo.com', '2026-07-10', 200),
               pedido(3, 'b@exemplo.com', '2026-07-15', 150), pedido(4, 'c@exemplo.com', '2026-09-20', 80)]
    return tabelas(pedidos)


def test_mensal_tem_mes_em_data_e_meta():
    t = base()
    ind = indicadores.calcular(t, None)
    m = rp.mensal(ind)
    assert list(m['mes'])[:2] == ['2026-05', '2026-07']
    assert m['mes_data'].iloc[0] == '2026-05-01'
    assert (m['meta_participacao'] == 35).all()
    assert 'participacao_recompra' in m.columns and 'receita_recompra' in m.columns


def test_regua_hoje_conta_envio_e_controle():
    t = base()
    classificacao, ref = regua.rodar(t, '2026-10')
    r = rp.regua_hoje(classificacao, ref)
    assert list(r.columns)[:2] == ['data_referencia', 'etapa'] and {'recebem', 'controle'} <= set(r.columns)
    assert len(r) == 5


def historico(n_envio=40, n_controle=40, mes='2026-08', ref='2026-08-10'):
    linhas = [{'mes': mes, 'data_referencia': ref, 'email': f'e{i}@exemplo.com', 'etapa': 'Etapa 1 · Lembrete', 'grupo': 'envio'} for i in range(n_envio)]
    linhas += [{'mes': mes, 'data_referencia': ref, 'email': f'c{i}@exemplo.com', 'etapa': 'Etapa 1 · Lembrete', 'grupo': 'controle'} for i in range(n_controle)]
    return pd.DataFrame(linhas)


def tabelas_com_compras(compraram_envio, compraram_controle):
    ped = [pedido(i, f'e{i}@exemplo.com', '2026-08-20', 200) for i in range(compraram_envio)]
    ped += [pedido(1000 + i, f'c{i}@exemplo.com', '2026-08-20', 200) for i in range(compraram_controle)]
    ped.append(pedido(9999, 'z@exemplo.com', '2026-09-30', 10))
    return tabelas(ped)


def test_resultado_da_regua_com_amostra_suficiente():
    r = rp.regua_resultados(historico(), tabelas_com_compras(10, 4), pd.Timestamp('2026-10-08'))
    linha = r[r['etapa'] == 'Etapa 1 · Lembrete'].iloc[0]
    assert (linha['recebeu'], linha['voltou'], linha['controle'], linha['voltou_controle']) == (40, 10, 40, 4)
    assert linha['incremento_pp'] == 15.0 and linha['estado'] == 'ok' and linha['gasto_medio'] == 200


def test_resultado_com_janela_aberta_ou_amostra_pequena():
    r = rp.regua_resultados(historico(), tabelas_com_compras(10, 4), pd.Timestamp('2026-08-20'))
    assert r.iloc[0]['estado'] == 'janela aberta' and r.iloc[0]['dias'] == 10
    r = rp.regua_resultados(historico(10, 10), tabelas_com_compras(5, 1), pd.Timestamp('2026-10-08'))
    assert r[r['etapa'] == 'Etapa 1 · Lembrete'].iloc[0]['estado'] == 'dados insuficientes'


def test_sem_historico_da_regua_aba_vazia_e_vale_a_pena_insuficiente():
    r = rp.regua_resultados(pd.DataFrame(), base(), pd.Timestamp('2026-10-08'))
    assert len(r) == 0
    v = rp.vale_a_pena(r, {})
    assert (v['estado'] == 'dados insuficientes').all() and v['receita_a_mais'].isna().all()
    assert 'Carrinho · WhatsApp' in set(v['acao'])


def test_vale_a_pena_calcula_receita_a_mais_e_custo():
    r = rp.regua_resultados(historico(), tabelas_com_compras(10, 4), pd.Timestamp('2026-10-08'))
    v = rp.vale_a_pena(r, {})
    linha = v[v['acao'] == 'Régua · Etapa 1 · Lembrete'].iloc[0]
    # (25% - 10%) x 40 pessoas x R$200 = R$1.200 a mais; custo de 10% = R$120
    assert linha['receita_a_mais'] == 1200.0 and linha['custo'] == 120.0 and linha['resultado'] == 1080.0


def test_historico_so_do_teste45_retorna_aba_vazia_com_cabecalhos():
    hoje = pd.Timestamp('2026-10-12')
    h = historico(mes='teste45', ref='2026-10-12')
    original = h.copy(deep=True)
    r = rp.regua_resultados(h, base(), hoje)
    assert r.empty
    assert list(r.columns) == list(rp.regua_resultados(pd.DataFrame(), base(), hoje).columns)
    pd.testing.assert_frame_equal(h, original)
    assert (rp.vale_a_pena(r, {})['estado'] == 'dados insuficientes').all()


def test_historico_misto_mantem_resultado_mensal_sem_incluir_teste45():
    mensal = historico()
    misto = pd.concat([mensal, historico(mes='teste45', ref='2026-10-12')], ignore_index=True)
    t = tabelas_com_compras(10, 4)
    hoje = pd.Timestamp('2026-10-12')
    pd.testing.assert_frame_equal(rp.regua_resultados(misto, t, hoje), rp.regua_resultados(mensal, t, hoje))


def fila_falsa(n_whats, n_comp, rec_whats, rec_comp):
    fila = {}
    def linha(i, grupo, toques, recuperado):
        v = {'Carrinho': str(i), 'Abandonado em': f'2026-10-0{1 + i % 5} 10:00', 'Valor (R$)': 100, 'Grupo': grupo,
             'Toques já enviados': toques, 'Recuperado': 'Sim' if recuperado else '', 'Receita recuperada (R$)': 150 if recuperado else ''}
        return cp.LinhaExistente(i + 2, v)
    for i in range(n_whats):
        fila[f'w{i}'] = linha(i, 'WhatsApp', 1, i < rec_whats)
    for i in range(n_comp):
        fila[f'c{i}'] = linha(100 + i, 'Comparação', 0, i < rec_comp)
    return fila


def test_carrinho_vale_a_pena_so_com_30_em_cada_grupo():
    r = pd.DataFrame()
    v = rp.vale_a_pena(r, fila_falsa(100, 20, 30, 4))
    assert v[v['acao'] == 'Carrinho · WhatsApp'].iloc[0]['estado'] == 'dados insuficientes'
    v = rp.vale_a_pena(r, fila_falsa(100, 40, 30, 4))
    c = v[v['acao'] == 'Carrinho · WhatsApp'].iloc[0]
    assert c['estado'] == 'ok' and round(c['taxa'], 1) == 30.0 and round(c['taxa_controle'], 1) == 10.0
    assert c['receita_a_mais'] == round((30 - 10) / 100 * 100 * 150, 2)


def test_carrinhos_por_dia():
    d = rp.carrinhos_dia(fila_falsa(10, 5, 3, 1))
    assert d['carrinhos'].sum() == 15 and d['recuperados'].sum() == 4 and d['receita_recuperada'].sum() == 600
    assert list(d.columns)[0] == 'dia' and rp.carrinhos_dia({}).empty


def test_aba_atual_tem_uma_linha_com_indicadores_e_metas():
    ind = indicadores.calcular(base(), None)
    a = rp.atual(ind)
    assert len(a) == 1
    assert a['meta_participacao_pct'].iloc[0] == 35 and a['meta_receita_quem_volta'].iloc[0] == 9000
    assert a['clientes_12m'].iloc[0] >= 0 and np.isnan(a['cpa_meta'].iloc[0])  # sem aba custos
