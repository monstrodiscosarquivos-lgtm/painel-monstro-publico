"""Testes dos indicadores. Dados fictícios, com contas feitas à mão.

Pedidos pagos do exemplo (subtotal, desconto, total com frete):
  1  A  10/01  100   0  120      4  C  20/02   80   0   80
  2  B  20/01  200  20  190      5  A  10/03   50   5   55
  3  A  15/02  150   0  160      (6  B  12/03  pendente, não conta)
"""
import numpy as np
import pandas as pd
import pytest

from painel_monstro.motor import indicadores as ind
from tests.ajuda import cliente, pedido, tabelas

REF = pd.Timestamp('2026-04-01')


@pytest.fixture
def t():
    pedidos = [
        pedido(1, 'a@x.com', '2026-01-10', total=120, subtotal=100, desconto=0),
        pedido(2, 'b@x.com', '2026-01-20', total=190, subtotal=200, desconto=20),
        pedido(3, 'a@x.com', '2026-02-15', total=160, subtotal=150, desconto=0),
        pedido(4, 'c@x.com', '2026-02-20', total=80, subtotal=80, desconto=0),
        pedido(5, 'a@x.com', '2026-03-10', total=55, subtotal=50, desconto=5),
        pedido(6, 'b@x.com', '2026-03-12', total=70, subtotal=70, desconto=0, valido=False),
    ]
    it = lambda n, e, d, nome, v: {'numero': str(n), 'email': e, 'data': pd.Timestamp(d), 'valido': True, 'produto': nome, 'valor': float(v), 'quantidade': 1, 'sku': None}  # noqa: E731
    itens = [it(1, 'a@x.com', '2026-01-10', 'Disco Usado', 100), it(2, 'b@x.com', '2026-01-20', 'Disco Lacrado', 200),
             it(3, 'a@x.com', '2026-02-15', 'Disco Usado', 150), it(4, 'c@x.com', '2026-02-20', 'Disco Usado', 80),
             it(5, 'a@x.com', '2026-03-10', 'Disco Usado', 50)]
    produtos = [{'url': 'u', 'nome': 'Disco Usado', 'categorias': 'LP > Usado > Rock', 'custo': np.nan},
                {'url': 'l', 'nome': 'Disco Lacrado', 'categorias': 'LP > Novo/Lacrado > Importados', 'custo': np.nan}]
    return tabelas(pedidos, itens=itens, produtos=produtos)


CUSTOS = pd.DataFrame([{'mes': '2026-01', 'investimento_meta': 100, 'compras_meta': 4, 'receita_meta': 500, 'custo_brevo': 10,
                        'receita_brevo': 300, 'margem_usados': 50, 'margem_lacrados': 20, 'embalagem': 3}])


# ----------------------------------------------------------------- aba custos
def test_ler_custos_aceita_formatos_brasileiros():
    c = ind.ler_custos(pd.DataFrame({'Mês': ['01/2026', '2026-02', '15/03/2026'], 'Investimento Meta': ['R$ 1.234,50', '800', None],
                                     'Margem usados': ['45%', '0,5', 40], 'Embalagem': ['2,50', '', '3']}))
    assert list(c['mes']) == ['2026-01', '2026-02', '2026-03']
    assert c['investimento_meta'].iloc[0] == pytest.approx(1234.5) and c['investimento_meta'].iloc[1] == 800
    assert pd.isna(c['investimento_meta'].iloc[2])
    assert list(c['margem_usados']) == pytest.approx([0.45, 0.5, 0.40])
    assert c['embalagem'].iloc[0] == 2.5 and pd.isna(c['embalagem'].iloc[1])
    assert list(c.columns) == ind.CUSTOS_COLUNAS


def test_ler_custos_vazio_ou_inexistente_da_tabela_vazia(tmp_path):
    assert len(ind.ler_custos(None)) == 0
    assert len(ind.ler_custos(str(tmp_path / 'nao-existe.csv'))) == 0
    assert list(ind.ler_custos(None).columns) == ind.CUSTOS_COLUNAS


def test_ler_custos_de_csv(tmp_path):
    arq = tmp_path / 'custos.csv'
    arq.write_text('mes;investimento_meta;margem_lacrados\n2026-01;"1.500,00";25\n', encoding='utf-8')
    c = ind.ler_custos(str(arq))
    assert c['investimento_meta'].iloc[0] == 1500 and c['margem_lacrados'].iloc[0] == 0.25


# ----------------------------------------------------------------- tipo e custo do disco
@pytest.mark.parametrize('categorias,tipo', [
    ('LP > Usado > Rock', 'usado'), ('CD > CDs Usados - Rock', 'usado'), ('Fitas Cassete > Usado', 'usado'),
    ('LP > Novo/Lacrado > Nacionais', 'lacrado'), ('Compacto > Novo/Lacrado', 'lacrado'),
    ('Merchandise > Camiseta', 'outro'), ('', 'outro'), (None, 'outro'),
])
def test_tipo_do_disco_pelas_categorias(categorias, tipo):
    assert ind.tipo_do_disco(categorias) == tipo


def test_custo_do_disco_pela_margem_do_tipo(t):
    i = ind.itens_com_custo(t, ind.ler_custos(CUSTOS)).set_index('numero')
    assert i.loc['1', 'custo_disco'] == pytest.approx(50)     # usado, margem 50%
    assert i.loc['2', 'custo_disco'] == pytest.approx(160)    # lacrado, margem 20%
    assert list(i['tipo']) == ['usado', 'lacrado', 'usado', 'usado', 'usado']


def itens_por_id():
    mk = lambda n, nome, pid: {'numero': str(n), 'email': 'a@x.com', 'data': pd.Timestamp('2026-01-10'), 'valido': True, 'produto': nome,  # noqa: E731
                               'valor': 100.0, 'quantidade': 1, 'sku': None, 'produto_id': pid}
    itens = [mk(1, 'Nome antigo do disco', 11),      # nome diferente do catálogo, mas o ID casa: lacrado
             mk(2, 'Disco Usado Mesmo Nome', 99),    # ID fora do catálogo, mesmo com nome igual ao de um produto: não casa
             mk(3, 'Sem ID na exportação', np.nan)]  # sem ID: casa pelo nome
    produtos = [{'url': 'a', 'nome': 'Nome novo do disco', 'categorias': 'LP > Novo/Lacrado', 'custo': np.nan, 'id': 11},
                {'url': 'b', 'nome': 'Disco Usado Mesmo Nome', 'categorias': 'LP > Usado', 'custo': np.nan, 'id': 12},
                {'url': 'c', 'nome': 'Sem ID na exportação', 'categorias': 'LP > Usado', 'custo': np.nan, 'id': np.nan}]
    return tabelas([pedido(1, 'a@x.com', '2026-01-10')], itens=itens, produtos=produtos)


def test_itens_casam_pelo_id_do_produto_e_so_sem_id_pelo_nome():
    i = ind.itens_com_custo(itens_por_id(), ind.ler_custos(CUSTOS)).set_index('numero')
    assert i.loc['1', 'encontrado'] and i.loc['1', 'tipo'] == 'lacrado' and i.loc['1', 'custo_disco'] == pytest.approx(80)
    assert not i.loc['2', 'encontrado'] and i.loc['2', 'tipo'] == 'outro'   # usa a margem de usados (50%)
    assert i.loc['2', 'custo_disco'] == pytest.approx(50)
    assert i.loc['3', 'encontrado'] and i.loc['3', 'tipo'] == 'usado'


def test_qualidade_conta_itens_sem_produto_no_catalogo():
    r = ind.calcular(itens_por_id(), CUSTOS, referencia=pd.Timestamp('2026-02-01'))
    assert r.qualidade['itens_pagos'] == 3
    assert r.qualidade['itens_sem_produto_correspondente_pct'] == pytest.approx(100 / 3)


def test_custo_cadastrado_no_produto_vale_mais_que_a_margem(t):
    t.produtos.loc[t.produtos['nome'] == 'Disco Usado', 'custo'] = 30.0
    i = ind.itens_com_custo(t, ind.ler_custos(CUSTOS)).set_index('numero')
    assert i.loc['1', 'custo_disco'] == 30 and i.loc['2', 'custo_disco'] == pytest.approx(160)


def test_sem_margem_o_custo_fica_vazio_e_nunca_zero(t):
    i = ind.itens_com_custo(t, ind.ler_custos(None))
    assert i['custo_disco'].isna().all()


def test_margem_informada_vale_para_todos_os_meses(t):
    custos = ind.ler_custos(pd.DataFrame([{'mes': '2026-03', 'margem_usados': 50, 'margem_lacrados': 20}]))
    i = ind.itens_com_custo(t, custos)
    assert i['custo_disco'].notna().all()


# ----------------------------------------------------------------- série mensal
def test_mensal_receita_recompra_e_clientes_novos(t):
    m = ind.tabela_mensal(t, ind.ler_custos(None))
    assert list(m.index) == ['2026-01', '2026-02', '2026-03']
    assert list(m['pedidos']) == [2, 2, 1]
    assert list(m['receita_produtos']) == [280, 230, 45]
    assert list(m['receita_recompra']) == [0, 150, 45]     # A voltou em fevereiro e março
    assert list(m['clientes_novos']) == [2, 1, 0]
    assert m.loc['2026-02', 'participacao_recompra'] == pytest.approx(150 / 230 * 100)
    assert m.loc['2026-03', 'participacao_recompra'] == pytest.approx(100)


def test_mensal_margem_bruta_com_as_regras_do_agents(t):
    m = ind.tabela_mensal(t, ind.ler_custos(CUSTOS)).loc['2026-01']
    taxas, remuneracao, disco, embalagem = 310 * 0.021, 280 * 0.10, 50 + 160, 3 * 2
    assert m['taxas_pagamento'] == pytest.approx(taxas)
    assert m['remuneracao_marketing'] == pytest.approx(remuneracao)
    assert m['custo_disco'] == pytest.approx(disco)
    assert m['embalagem'] == pytest.approx(embalagem)
    # subtotal 300 - desconto 20 - taxas - 10% - disco - embalagem
    assert m['margem_bruta'] == pytest.approx(300 - 20 - taxas - remuneracao - disco - embalagem)
    assert m['margem_bruta_pct'] == pytest.approx(m['margem_bruta'] / 280 * 100)


def test_mensal_frete_pago_pela_loja_entra_na_margem_quando_informado(t):
    custos = CUSTOS.copy()
    custos['frete_pago_loja'] = 40
    com = ind.tabela_mensal(t, ind.ler_custos(custos)).loc['2026-01']
    sem = ind.tabela_mensal(t, ind.ler_custos(CUSTOS)).loc['2026-01']
    assert sem['margem_bruta'] - com['margem_bruta'] == pytest.approx(40)
    assert sem['frete_pago_loja'] == 0  # vazio conta como zero (D-027)
    assert com['custo_marketing'] - sem['custo_marketing'] == pytest.approx(40)


def test_frete_pago_pela_loja_vazio_conta_como_zero_nos_indicadores(t):
    r = ind.calcular(t, CUSTOS, referencia=REF)
    assert linha(r, 'Descontos e fretes pagos ÷ receita')['valor'] == pytest.approx(25 / 555 * 100)  # só descontos: 20 + 5
    custos = CUSTOS.copy()
    custos['frete_pago_loja'] = 30
    r = ind.calcular(t, custos, referencia=REF)
    assert linha(r, 'Descontos e fretes pagos ÷ receita')['valor'] == pytest.approx(55 / 555 * 100)


def test_mensal_meta_e_custos(t):
    m = ind.tabela_mensal(t, ind.ler_custos(CUSTOS)).loc['2026-01']
    assert m['cpa_meta'] == pytest.approx(25)               # 100 / 4
    assert m['roas_meta'] == pytest.approx(5)               # 500 / 100
    assert m['roas_geral'] == pytest.approx(2.8)            # receita de produtos 280 / 100
    assert m['custo_por_cliente_novo'] == pytest.approx(50)  # 100 / 2 novos
    assert m['custo_marketing'] == pytest.approx(100 + 10 + 28 + 20)  # Meta + Brevo + 10% + descontos
    assert m['custo_marketing_pct'] == pytest.approx(158 / 280 * 100)
    assert m['descontos_e_fretes_pct'] == pytest.approx(20 / 280 * 100)


def test_mes_sem_custos_fica_vazio_e_nao_zero(t):
    m = ind.tabela_mensal(t, ind.ler_custos(CUSTOS))
    for coluna in ('cpa_meta', 'roas_meta', 'roas_geral', 'custo_por_cliente_novo', 'custo_marketing', 'custo_marketing_pct'):
        assert pd.isna(m.loc['2026-02', coluna]), coluna


def test_pedido_nao_pago_nao_entra_em_nada(t):
    m = ind.tabela_mensal(t, ind.ler_custos(None))
    assert m.loc['2026-03', 'pedidos'] == 1 and m.loc['2026-03', 'receita_total'] == 55


# ----------------------------------------------------------------- coortes
def test_coortes_voltam_em_90_dias_e_ltv_de_12_meses(t):
    c = ind.coortes(t, pd.Timestamp('2027-03-01'))
    jan, fev = c.loc['2026-01'], c.loc['2026-02']
    assert jan['clientes'] == 2 and jan['voltam_90d_pct'] == pytest.approx(50) and jan['voltam_12m_pct'] == pytest.approx(50)
    assert jan['ltv_12m'] == pytest.approx((100 + 150 + 45 + 180) / 2)   # A: 295, B: 180
    assert fev['clientes'] == 1 and fev['voltam_90d_pct'] == 0 and fev['ltv_12m'] == pytest.approx(80)


def test_coorte_que_ainda_nao_amadureceu_fica_vazia(t):
    c = ind.coortes(t, pd.Timestamp('2026-04-01'))
    assert c['voltam_90d_pct'].isna().all() or c.loc['2026-01', 'voltam_90d_pct'] == pytest.approx(50)  # janeiro já tem 90 dias
    assert pd.isna(c.loc['2026-01', 'ltv_12m']) and pd.isna(c.loc['2026-01', 'voltam_12m_pct'])


# ----------------------------------------------------------------- resumo
def linha(res, indicador):
    return res.resumo.set_index('indicador').loc[indicador]


def test_resumo_quem_volta(t):
    r = ind.calcular(t, None, referencia=REF)
    assert linha(r, 'Receita de quem volta por mês (média 12 meses)')['valor'] == pytest.approx((150 + 45) / 12)
    assert linha(r, 'Clientes que compraram nos últimos 12 meses')['valor'] == 3
    assert linha(r, 'Taxa de volta por mês')['valor'] == pytest.approx(2 / 12 / 3 * 100)
    assert linha(r, 'Gasto por recompra')['valor'] == pytest.approx(97.5)
    assert linha(r, 'Participação de quem volta na receita (12 meses)')['valor'] == pytest.approx(195 / 555 * 100)


def test_resumo_sem_custos_mostra_falta_custos_e_nunca_zero(t):
    r = ind.calcular(t, None, referencia=REF)
    for nome in ('CPA do Meta', 'ROAS do Meta', 'ROAS geral', 'Custo real por cliente novo', 'LTV ÷ custo por cliente novo',
                 'Custo total de marketing ÷ receita', 'Vendas atribuídas aos envios (Brevo)', 'Margem bruta (12 meses)'):
        l = linha(r, nome)
        assert l['estado'] == ind.FALTA_CUSTOS and pd.isna(l['valor']), nome


def test_resumo_com_custos_calcula_meta_brevo_e_margem(t):
    r = ind.calcular(t, CUSTOS, referencia=REF)
    assert linha(r, 'CPA do Meta')['valor'] == pytest.approx(25)
    assert linha(r, 'ROAS do Meta')['valor'] == pytest.approx(5)
    assert linha(r, 'ROAS geral')['valor'] == pytest.approx(2.8)
    assert linha(r, 'Custo real por cliente novo')['valor'] == pytest.approx(50)
    assert linha(r, 'Vendas atribuídas aos envios (Brevo)')['valor'] == 300
    assert linha(r, 'Custo total de marketing ÷ receita')['valor'] == pytest.approx(158 / 280 * 100)
    assert linha(r, 'Margem bruta (12 meses)')['estado'] == ind.OK
    assert (r.resumo['estado'] == ind.OK).sum() > (ind.calcular(t, None, referencia=REF).resumo['estado'] == ind.OK).sum()


def test_resumo_itens_de_etapas_futuras_ficam_como_falta_dados(t):
    r = ind.calcular(t, None, referencia=REF)
    for nome in ('Incremento de cada etapa da régua', 'Abertura, emails inválidos e descadastros'):
        assert linha(r, nome)['estado'] == ind.FALTA_DADOS


def test_incremento_da_regua_entra_quando_ha_resultado(t):
    resultado = pd.DataFrame([
        {'etapa': 'Etapa 1 · Lembrete', 'recebeu': 40, 'voltou': 10, 'taxa': 25.0, 'receita': 1000.0, 'controle': 40, 'voltou_controle': 4,
         'taxa_controle': 10.0, 'incremento_pp': 15.0, 'amostra_suficiente': True},
        {'etapa': 'Etapa 2 · Convite', 'recebeu': 10, 'voltou': 5, 'taxa': 50.0, 'receita': 500.0, 'controle': 2, 'voltou_controle': 0,
         'taxa_controle': 0.0, 'incremento_pp': 50.0, 'amostra_suficiente': False},
    ])
    r = ind.calcular(t, None, referencia=REF, resultado_regua=resultado)
    assert linha(r, 'Incremento · Etapa 1 · Lembrete')['valor'] == 15 and linha(r, 'Incremento · Etapa 1 · Lembrete')['estado'] == ind.OK
    pequeno = linha(r, 'Incremento · Etapa 2 · Convite')
    assert pequeno['estado'] == ind.FALTA_DADOS and pd.isna(pequeno['valor'])


def test_janela_de_12_meses_ignora_compras_antigas():
    pedidos = [pedido(1, 'a@x.com', '2024-01-01', total=100), pedido(2, 'a@x.com', '2026-03-01', total=100),
               pedido(3, 'b@x.com', '2026-03-05', total=100)]
    r = ind.calcular(tabelas(pedidos), None, referencia=REF)
    assert linha(r, 'Clientes que compraram nos últimos 12 meses')['valor'] == 2
    assert linha(r, 'Receita de quem volta por mês (média 12 meses)')['valor'] == pytest.approx(100 / 12)  # A é recompra mesmo com a 1ª em 2024


# ----------------------------------------------------------------- formatação
@pytest.mark.parametrize('valor,unidade,texto', [
    (6251.4, 'R$', 'R$ 6.251'), (25.0, 'R$', 'R$ 25,00'), (27.66, '%', '27,7%'), (2.8, 'x', '2,80x'),
    (1065, 'clientes', '1.065'), (15.0, 'pontos %', '15,0 p.p.'), (float('nan'), 'R$', '—'), ('2026-01', '', '2026-01'),
])
def test_formatar(valor, unidade, texto):
    assert ind.formatar(valor, unidade) == texto
