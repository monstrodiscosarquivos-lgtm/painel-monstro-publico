"""Testes da régua mensal. Dados fictícios."""
import pandas as pd
import pytest

from painel_monstro.motor import regua
from tests.ajuda import REFERENCIA, cliente, dias_atras, pedido, tabelas

MES = '2026-10'


def base_de(linhas):
    """Base de clientes pronta: cada linha é (email, dias, n_compras, total_gasto)."""
    return pd.DataFrame({'n': [n for _, _, n, _ in linhas], 'total': [float(t) for _, _, _, t in linhas],
                         'dias': [d for _, d, _, _ in linhas],
                         'ultima': [REFERENCIA - pd.Timedelta(days=d) for _, d, _, _ in linhas],
                         'vip': [(n >= 3) or (t >= 1000) for _, _, n, t in linhas]},
                        index=pd.Index([e for e, *_ in linhas], name='email'))


def etapa_de(dias, n=2, total=100):
    base = base_de([('x@exemplo.com', dias, n, total)])
    return regua.classificar(base, MES, REFERENCIA).loc['x@exemplo.com']


# ----------------------------------------------------------------- janelas
@pytest.mark.parametrize('dias,etapa', [
    (14, regua.SEM_ETAPA), (15, 'Etapa 0 · Pós-compra'), (44, 'Etapa 0 · Pós-compra'),
    (45, 'Etapa 1 · Lembrete'), (74, 'Etapa 1 · Lembrete'),
    (75, regua.SEM_ETAPA), (89, regua.SEM_ETAPA),
    (90, 'Etapa 2 · Convite'), (119, 'Etapa 2 · Convite'),
    (120, regua.SEM_ETAPA), (179, regua.SEM_ETAPA),
    (180, 'Etapa 3 · Última chamada'), (209, 'Etapa 3 · Última chamada'),
    (210, regua.DESCANSO), (600, regua.DESCANSO),
])
def test_janelas_de_cada_etapa(dias, etapa):
    # n=1 para a etapa 0 valer; as outras etapas não olham o número de compras
    assert etapa_de(dias, n=1)['etapa'] == etapa


def test_cliente_dentro_da_janela_recebe_e_fora_nao():
    assert etapa_de(30, n=1)['grupo'] == 'envio'
    assert etapa_de(100, n=1)['grupo'] == 'envio'
    assert etapa_de(130, n=1)['grupo'] == ''
    assert etapa_de(400, n=1)['grupo'] == ''


def test_etapa_0_so_para_quem_tem_uma_compra():
    assert etapa_de(20, n=1)['etapa'] == 'Etapa 0 · Pós-compra'
    assert etapa_de(20, n=2)['etapa'] == regua.SEM_ETAPA


def test_etapas_seguintes_aceitam_quem_comprou_varias_vezes():
    assert etapa_de(50, n=2)['etapa'] == 'Etapa 1 · Lembrete'
    assert etapa_de(100, n=2)['etapa'] == 'Etapa 2 · Convite'


# ----------------------------------------------------------------- VIP
def test_vip_por_tres_compras_ou_mil_reais():
    assert etapa_de(80, n=3, total=100)['etapa'] == 'VIP · WhatsApp'
    assert etapa_de(80, n=1, total=1000)['etapa'] == 'VIP · WhatsApp'
    assert etapa_de(80, n=2, total=999.99)['etapa'] == regua.SEM_ETAPA  # não é VIP e 80 dias não tem etapa


def test_vip_so_na_janela_de_75_a_104_dias():
    assert etapa_de(74, n=3)['etapa'] == 'Etapa 1 · Lembrete'
    assert etapa_de(75, n=3)['etapa'] == 'VIP · WhatsApp'
    assert etapa_de(104, n=3)['etapa'] == 'VIP · WhatsApp'
    assert etapa_de(105, n=3)['etapa'] == 'Etapa 2 · Convite'


def test_vip_sai_da_etapa_2_mas_nao_vira_controle():
    for dias in (90, 100, 104):
        r = etapa_de(dias, n=3)
        assert r['etapa'] == 'VIP · WhatsApp' and r['grupo'] == 'envio'
    # não-VIP no mesmo intervalo continua na etapa 2
    assert etapa_de(100, n=2, total=200)['etapa'] == 'Etapa 2 · Convite'


def test_vip_nunca_tem_controle_mesmo_com_muitos():
    base = base_de([(f'v{i}@exemplo.com', 80, 3, 500) for i in range(40)])
    c = regua.classificar(base, MES, REFERENCIA)
    assert (c['etapa'] == 'VIP · WhatsApp').all() and (c['grupo'] == 'envio').all()


# ----------------------------------------------------------------- controle
def grupo_de_40():
    return base_de([(f'c{i:02d}@exemplo.com', 50, 2, 100 + i) for i in range(40)])


def test_controle_e_10_por_cento_de_cada_etapa():
    c = regua.classificar(grupo_de_40(), MES, REFERENCIA)
    assert (c['grupo'] == 'controle').sum() == 4
    assert (c['grupo'] == 'envio').sum() == 36
    assert (c['etapa'] == 'Etapa 1 · Lembrete').all()


def test_controle_e_reproduzivel_com_a_mesma_semente_do_mes():
    a = regua.classificar(grupo_de_40(), MES, REFERENCIA)
    b = regua.classificar(grupo_de_40(), MES, REFERENCIA)
    assert list(a[a['grupo'] == 'controle'].index) == list(b[b['grupo'] == 'controle'].index)


def test_controle_muda_de_um_mes_para_outro():
    a = regua.classificar(grupo_de_40(), '2026-10', REFERENCIA)
    b = regua.classificar(grupo_de_40(), '2026-11', REFERENCIA)
    assert set(a[a['grupo'] == 'controle'].index) != set(b[b['grupo'] == 'controle'].index)


def test_etapa_com_menos_de_10_pessoas_nao_tem_controle():
    base = base_de([(f'p{i}@exemplo.com', 50, 2, 100) for i in range(9)])
    c = regua.classificar(base, MES, REFERENCIA)
    assert (c['grupo'] == 'envio').all()


def test_exatamente_10_pessoas_ja_tem_controle():
    base = base_de([(f'p{i}@exemplo.com', 50, 2, 100) for i in range(10)])
    c = regua.classificar(base, MES, REFERENCIA)
    assert (c['grupo'] == 'controle').sum() == 1


def test_cada_cliente_cai_em_no_maximo_uma_etapa():
    base = base_de([(f'd{d}n{n}@exemplo.com', d, n, t) for d in range(1, 260) for n, t in ((1, 50), (3, 300))])
    c = regua.classificar(base, MES, REFERENCIA)
    assert c.index.is_unique and len(c) == len(base)
    nas_listas = [regua.lista_da_etapa(c, e.nome, g).index for e in (*regua.PADRAO.etapas, regua.PADRAO.vip) for g in ('envio', 'controle')]
    todos = [email for lista in nas_listas for email in lista]
    assert len(todos) == len(set(todos))


def test_resumo_conta_quem_recebe_e_o_controle():
    c = regua.classificar(grupo_de_40(), MES, REFERENCIA)
    r = regua.resumo(c).set_index('etapa')
    assert (r.loc['Etapa 1 · Lembrete', 'recebem'], r.loc['Etapa 1 · Lembrete', 'controle']) == (36, 4)
    assert r.loc['Etapa 0 · Pós-compra', 'recebem'] == 0


def test_lista_da_etapa_vem_do_maior_gasto_para_o_menor():
    c = regua.classificar(grupo_de_40(), MES, REFERENCIA)
    lista = regua.lista_da_etapa(c, 'Etapa 1 · Lembrete')
    assert list(lista['total']) == sorted(lista['total'], reverse=True)
    assert set(lista.index).isdisjoint(regua.lista_da_etapa(c, 'Etapa 1 · Lembrete', 'controle').index)


# ----------------------------------------------------------------- limite de benefício
def test_um_beneficio_a_cada_90_dias():
    base = base_de([(f'e{i}@exemplo.com', 100, 2, 100) for i in range(5)])
    ultimos = pd.Series({'e0@exemplo.com': REFERENCIA - pd.Timedelta(days=89),   # recebeu cupom há 89 dias: fora
                         'e1@exemplo.com': REFERENCIA - pd.Timedelta(days=90)})  # há 90 dias: pode receber
    c = regua.classificar(base, MES, REFERENCIA, ultimos_beneficios=ultimos)
    assert c.loc['e0@exemplo.com', 'etapa'] == regua.SEM_ETAPA
    assert c.loc['e1@exemplo.com', 'etapa'] == 'Etapa 2 · Convite'
    assert c.attrs['excluidos_por_limite_de_beneficio'] == 1


def test_limite_de_beneficio_nao_vale_para_etapas_sem_cupom():
    base = base_de([('e@exemplo.com', 50, 2, 100)])
    ultimos = pd.Series({'e@exemplo.com': REFERENCIA - pd.Timedelta(days=10)})
    c = regua.classificar(base, MES, REFERENCIA, ultimos_beneficios=ultimos)
    assert c.loc['e@exemplo.com', 'etapa'] == 'Etapa 1 · Lembrete'


# ----------------------------------------------------------------- base de clientes (uma compra zera o relógio)
def test_dias_contam_da_ultima_compra_e_uma_compra_zera_o_relogio():
    t = tabelas([
        pedido(1, 'volta@exemplo.com', dias_atras(100)), pedido(2, 'volta@exemplo.com', dias_atras(10)),  # comprou de novo
        pedido(3, 'parada@exemplo.com', dias_atras(100)),
        pedido(4, 'ultimo@exemplo.com', dias_atras(1)),
    ])
    base = regua.base_clientes(t, regua.data_referencia(t))
    assert base.loc['volta@exemplo.com', 'dias'] == 10
    assert base.loc['parada@exemplo.com', 'dias'] == 100
    c = regua.classificar(base, MES, regua.data_referencia(t))
    assert c.loc['volta@exemplo.com', 'etapa'] == regua.SEM_ETAPA   # 10 dias: ainda sem etapa
    assert c.loc['parada@exemplo.com', 'etapa'] == 'Etapa 2 · Convite'


def test_comprar_de_novo_tira_o_cliente_da_etapa():
    antes = tabelas([pedido(1, 'a@exemplo.com', dias_atras(100)), pedido(2, 'ref@exemplo.com', dias_atras(1))])
    depois = tabelas([pedido(1, 'a@exemplo.com', dias_atras(100)), pedido(2, 'a@exemplo.com', dias_atras(5)),
                      pedido(3, 'ref@exemplo.com', dias_atras(1))])
    f = lambda t: regua.classificar(regua.base_clientes(t, regua.data_referencia(t)), MES, regua.data_referencia(t))  # noqa: E731
    assert f(antes).loc['a@exemplo.com', 'etapa'] == 'Etapa 2 · Convite'
    assert f(depois).loc['a@exemplo.com', 'etapa'] == regua.SEM_ETAPA


def test_pedido_nao_pago_nao_zera_o_relogio():
    t = tabelas([pedido(1, 'a@exemplo.com', dias_atras(100)), pedido(2, 'a@exemplo.com', dias_atras(5), valido=False),
                 pedido(3, 'ref@exemplo.com', dias_atras(1))])
    base = regua.base_clientes(t, regua.data_referencia(t))
    assert base.loc['a@exemplo.com', 'dias'] == 100 and base.loc['a@exemplo.com', 'n'] == 1


def test_data_de_referencia_e_o_dia_seguinte_ao_ultimo_pedido_pago():
    t = tabelas([pedido(1, 'a@exemplo.com', '2026-10-05 18:46:44'),
                 pedido(2, 'b@exemplo.com', '2026-10-08 09:00:00', valido=False)])
    assert regua.data_referencia(t) == pd.Timestamp('2026-10-06')


def test_quem_nao_aceita_marketing_fica_de_fora_de_tudo():
    t = tabelas([pedido(1, 'nao@exemplo.com', dias_atras(100)), pedido(2, 'sim@exemplo.com', dias_atras(100)),
                 pedido(3, 'ref@exemplo.com', dias_atras(1))],
                clientes=[cliente('nao@exemplo.com', aceita=False), cliente('sim@exemplo.com'), cliente('ref@exemplo.com')])
    base = regua.base_clientes(t, regua.data_referencia(t))
    assert 'nao@exemplo.com' not in base.index and 'sim@exemplo.com' in base.index


def test_cliente_sem_compra_paga_e_email_da_loja_ficam_de_fora():
    t = tabelas([pedido(1, 'so_pendente@exemplo.com', dias_atras(100), valido=False), pedido(2, regua.EMAIL_DA_LOJA, dias_atras(100)),
                 pedido(3, 'ok@exemplo.com', dias_atras(100)), pedido(4, 'ref@exemplo.com', dias_atras(1))])
    base = regua.base_clientes(t, regua.data_referencia(t))
    assert 'so_pendente@exemplo.com' not in base.index and regua.EMAIL_DA_LOJA not in base.index and 'ok@exemplo.com' in base.index


def test_vip_na_base_por_compras_ou_gasto():
    t = tabelas([pedido(1, 'tres@exemplo.com', dias_atras(300), 50), pedido(2, 'tres@exemplo.com', dias_atras(200), 50),
                 pedido(3, 'tres@exemplo.com', dias_atras(80), 50),
                 pedido(4, 'rico@exemplo.com', dias_atras(80), 1200),
                 pedido(5, 'comum@exemplo.com', dias_atras(80), 300),
                 pedido(6, 'ref@exemplo.com', dias_atras(1))])
    base = regua.base_clientes(t, regua.data_referencia(t))
    assert base['vip'].to_dict() == {'tres@exemplo.com': True, 'rico@exemplo.com': True, 'comum@exemplo.com': False, 'ref@exemplo.com': False}


# ----------------------------------------------------------------- resultado de cada etapa
def classificacao_anterior(recebem, controle):
    linhas = [(e, 'Etapa 1 · Lembrete', 'envio') for e in recebem] + [(e, 'Etapa 1 · Lembrete', 'controle') for e in controle]
    return pd.DataFrame(linhas, columns=['email', 'etapa', 'grupo']).set_index('email')


def test_resultado_e_taxa_de_compra_em_30_dias_menos_a_do_controle():
    recebem = [f'r{i}@exemplo.com' for i in range(40)]
    controle = [f'c{i}@exemplo.com' for i in range(40)]
    ref = pd.Timestamp('2026-09-01')
    pedidos = ([pedido(i, e, '2026-09-10', 100) for i, e in enumerate(recebem[:10])]       # 10 de 40 voltaram: 25%
               + [pedido(100 + i, e, '2026-09-10', 100) for i, e in enumerate(controle[:4])])  # 4 de 40: 10%
    r = regua.resultado_etapas(classificacao_anterior(recebem, controle), tabelas(pedidos), ref).set_index('etapa').loc['Etapa 1 · Lembrete']
    assert (r['recebeu'], r['voltou'], r['controle'], r['voltou_controle']) == (40, 10, 40, 4)
    assert r['taxa'] == pytest.approx(25.0) and r['taxa_controle'] == pytest.approx(10.0)
    assert r['incremento_pp'] == pytest.approx(15.0)
    assert r['receita'] == pytest.approx(1000.0)
    assert bool(r['amostra_suficiente']) is True


def test_resultado_so_conta_compras_na_janela_de_30_dias_e_pagas():
    ref = pd.Timestamp('2026-09-01')
    recebem = ['a@exemplo.com', 'b@exemplo.com', 'c@exemplo.com', 'd@exemplo.com']
    pedidos = [pedido(1, 'a@exemplo.com', '2026-08-31 23:59'),        # antes da referência
               pedido(2, 'b@exemplo.com', '2026-10-01 00:00'),        # 30 dias exatos depois: fora
               pedido(3, 'c@exemplo.com', '2026-09-30 23:59'),        # dentro
               pedido(4, 'd@exemplo.com', '2026-09-15', valido=False)]  # não pago
    r = regua.resultado_etapas(classificacao_anterior(recebem, []), tabelas(pedidos), ref).set_index('etapa').loc['Etapa 1 · Lembrete']
    assert r['voltou'] == 1


def test_resultado_com_menos_de_30_por_grupo_e_amostra_insuficiente():
    ref = pd.Timestamp('2026-09-01')
    recebem = [f'r{i}@exemplo.com' for i in range(29)]
    controle = [f'c{i}@exemplo.com' for i in range(30)]
    r = regua.resultado_etapas(classificacao_anterior(recebem, controle), tabelas([pedido(1, 'r0@exemplo.com', '2026-09-02')]), ref)
    assert bool(r.set_index('etapa').loc['Etapa 1 · Lembrete', 'amostra_suficiente']) is False


def test_rodar_ponta_a_ponta():
    ped = [pedido(i, f'c{i}@exemplo.com', dias_atras(50)) for i in range(20)] + [pedido(99, 'ref@exemplo.com', dias_atras(1))]
    classificacao, ref = regua.rodar(tabelas(ped), MES)
    assert ref == REFERENCIA
    r = regua.resumo(classificacao).set_index('etapa').loc['Etapa 1 · Lembrete']
    assert (r['recebem'], r['controle']) == (18, 2)
