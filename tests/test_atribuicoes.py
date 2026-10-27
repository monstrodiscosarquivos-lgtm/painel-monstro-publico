"""Testes da atribuição manual de pedidos (D-064). Dados fictícios."""
import pandas as pd

from painel_monstro.saidas import atribuicoes as at
from painel_monstro.saidas import carrinhos as c
from painel_monstro.saidas import resumos_painel as rp
from painel_monstro.saidas.carrinhos_planilha import LinhaExistente

HOJE = pd.Timestamp('2026-10-14')


def _pedidos():
    return pd.DataFrame([
        {'numero': '1001', 'email': 'a@x.com', 'data': '2026-10-02 10:00', 'valido': True, 'subtotal': 100.0, 'desconto': 10.0, 'cupom': None},
        {'numero': '1002', 'email': 'b@x.com', 'data': '2026-10-05 10:00', 'valido': True, 'subtotal': 200.0, 'desconto': 0.0, 'cupom': 'AMIGO-ANA'},
        {'numero': '1003', 'email': 'c@x.com', 'data': '2026-10-06 10:00', 'valido': True, 'subtotal': 50.0, 'desconto': 0.0, 'cupom': None},
        {'numero': '1004', 'email': 'd@x.com', 'data': '2026-10-07 10:00', 'valido': False, 'subtotal': 80.0, 'desconto': 0.0, 'cupom': None},
        {'numero': '0999', 'email': 'e@x.com', 'data': '2026-09-20 10:00', 'valido': True, 'subtotal': 70.0, 'desconto': 0.0, 'cupom': None},
    ])


def _aba(*linhas):
    return [at.COLUNAS, *[list(l) for l in linhas]]


def test_ler_normaliza_origem_numero_e_ultima_linha_vale():
    df = at.ler(_aba(['#1001', 'indicação', 'amigo', '2026-10-03'], ['1002.0', 'Qualquer coisa', '', ''], ['', 'Outro', '', ''],
                     ['1001', 'WhatsApp manual', 'corrigido', '2026-10-04']))
    assert list(df['numero_pedido']) == ['1002', '1001']
    assert dict(zip(df['numero_pedido'], df['origem'])) == {'1001': 'WhatsApp manual', '1002': 'Outro'}
    assert len(at.ler([])) == 0 and len(at.ler([['x']])) == 0


def test_soma_do_mes_so_pedidos_validos_e_receita_de_produtos():
    atrib = at.ler(_aba(['1001', 'Indicação'], ['1003', 'WhatsApp manual'], ['1004', 'Outro'], ['0999', 'Outro'], ['5555', 'Outro']))
    r = at.linha_vale_a_pena(atrib, _pedidos(), set(), '', HOJE)
    assert r['acao'] == 'Indicações e contatos manuais' and r['estado'] == 'sem controle'
    assert r['pedidos'] == 2 and r['receita_atribuida'] == 140.0   # 90 + 50; inválido, de setembro e inexistente ficam fora
    assert pd.isna(r['receita_a_mais']) and pd.isna(r['controle'])
    assert 'não é receita a mais' in r['nota']


def test_pedido_ja_reconhecido_pela_fila_conta_so_na_fila_e_a_nota_diz_quantos():
    atrib = at.ler(_aba(['1001', 'Indicação'], ['1002', 'Indicação'], ['1003', 'Outro']))
    r = at.linha_vale_a_pena(atrib, _pedidos(), {'1001': 'Carrinho', '1002': 'VIP'}, '', HOJE)
    assert r['pedidos'] == 1 and r['receita_atribuida'] == 50.0
    assert '2 ignorado(s) por já estarem na Fila' in r['nota'] and 'Carrinho: 1' in r['nota'] and 'VIP: 1' in r['nota']
    assert 'ignorado' not in at.linha_vale_a_pena(atrib, _pedidos(), {}, '', HOJE)['nota']


def test_prefixo_de_cupom_entra_sozinho_e_vazio_nao_entra():
    vazia = at.ler([])
    assert at.linha_vale_a_pena(vazia, _pedidos(), set(), '', HOJE)['pedidos'] == 0
    r = at.linha_vale_a_pena(vazia, _pedidos(), set(), 'amigo-', HOJE)
    assert r['pedidos'] == 1 and r['receita_atribuida'] == 200.0 and 'Indicação: 1' in r['nota']
    # atribuição manual do mesmo pedido prevalece sobre o prefixo
    r2 = at.linha_vale_a_pena(at.ler(_aba(['1002', 'Outro'])), _pedidos(), set(), 'amigo-', HOJE)
    assert 'Outro: 1' in r2['nota'] and r2['pedidos'] == 1


def test_pedidos_da_fila_usa_o_primeiro_pedido_em_ate_7_dias_do_primeiro_toque():
    fila = {
        '1': LinhaExistente(2, {'Recuperado': 'Sim', 'Email': 'a@x.com', 'Telefone': '', 'Primeiro toque em': '2026-10-01 09:00'}),
        '2': LinhaExistente(3, {'Recuperado': 'Não', 'Email': 'b@x.com', 'Primeiro toque em': '2026-10-01 09:00'}),
        '3': LinhaExistente(4, {'Recuperado': 'Sim', 'Email': '', 'Telefone': '55 62 99999-0000', 'Primeiro toque em': '2026-10-04 09:00'}),
    }
    fila['3'].valores['Origem'] = 'Garimpo'
    achados = at.pedidos_da_fila(fila, _pedidos(), {'5562999990000': 'c@x.com'}, c.so_digitos)
    assert achados == {'1001': 'Carrinho', '1003': 'Garimpo'}


def test_vale_a_pena_ganha_linha_e_colunas_no_fim_sem_mudar_as_existentes():
    resultados = pd.DataFrame(columns=['mes', 'etapa', 'recebeu', 'voltou', 'controle', 'voltou_controle', 'gasto_medio', 'dias'])
    linha = at.linha_vale_a_pena(at.ler(_aba(['1003', 'Outro'])), _pedidos(), set(), '', HOJE)
    df = rp.vale_a_pena(resultados, {}, None, linha)
    assert list(df.columns)[:11] == ['acao', 'recebeu', 'controle', 'taxa', 'taxa_controle', 'gasto_medio', 'receita_a_mais',
                                      'custo', 'resultado', 'estado', 'nota']
    assert list(df.columns)[11:] == ['pedidos', 'receita_atribuida']
    assert df.iloc[-1]['acao'] == 'Indicações e contatos manuais' and df.iloc[-1]['receita_atribuida'] == 50.0
    assert df.iloc[:-1]['pedidos'].isna().all()
    sem = rp.vale_a_pena(resultados, {}, None)
    assert at.ACAO not in set(sem['acao'])
