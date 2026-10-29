import pandas as pd
import pytest

from painel_monstro.coletor.planilhas_csv import Tabelas
from painel_monstro.saidas import k7


def test_montar_resumo_k7_totais_e_privacidade():
    pedidos = pd.DataFrame([
        {'numero': '101', 'email': 'cliente1@exemplo.com', 'data': '2026-10-25 10:00', 'valido': True, 'subtotal': 50.0, 'desconto': 0.0, 'total': 50.0},
        {'numero': '102', 'email': 'cliente2@exemplo.com', 'data': '2026-10-26 15:30', 'valido': True, 'subtotal': 180.0, 'desconto': 0.0, 'total': 180.0},
        {'numero': '103', 'email': 'cliente3@exemplo.com', 'data': '2026-10-27 12:00', 'valido': False, 'subtotal': 50.0, 'desconto': 0.0, 'total': 50.0},  # cancelado/inválido
    ])

    itens = pd.DataFrame([
        # Pedido 101: 1 fita K7
        {'numero': '101', 'email': 'cliente1@exemplo.com', 'data': '2026-10-25 10:00', 'valido': True,
         'produto': 'Fita K7 Goiânia Rock City 2026', 'valor': 50.0, 'quantidade': 1, 'sku': 'K7-GRC26', 'produto_id': 375734821},
        # Pedido 102: 2 fitas K7 + 1 LP Violator
        {'numero': '102', 'email': 'cliente2@exemplo.com', 'data': '2026-10-26 15:30', 'valido': True,
         'produto': 'Fita K7 Goiânia Rock City 2026', 'valor': 50.0, 'quantidade': 2, 'sku': 'K7-GRC26', 'produto_id': 375734821},
        {'numero': '102', 'email': 'cliente2@exemplo.com', 'data': '2026-10-26 15:30', 'valido': True,
         'produto': 'LP Violator - Chemical Assault', 'valor': 80.0, 'quantidade': 1, 'sku': 'LP-VIO', 'produto_id': 99999},
        # Pedido 103 (inválido): 1 fita K7 - NÃO PODE CONTAR
        {'numero': '103', 'email': 'cliente3@exemplo.com', 'data': '2026-10-27 12:00', 'valido': False,
         'produto': 'Fita K7 Goiânia Rock City 2026', 'valor': 50.0, 'quantidade': 1, 'sku': 'K7-GRC26', 'produto_id': 375734821},
    ])

    produtos = pd.DataFrame([
        {'id': 375734821, 'nome': 'Fita K7 Goiânia Rock City 2026', 'estoque': 147, 'preco': 50.0},
        {'id': 99999, 'nome': 'LP Violator - Chemical Assault', 'estoque': 2, 'preco': 80.0},
    ])

    clientes = pd.DataFrame([
        {'email': 'cliente1@exemplo.com', 'nome': 'Cliente Um', 'telefone': '5562999991111'},
    ])

    tabelas = Tabelas(clientes=clientes, pedidos=pedidos, itens=itens, produtos=produtos)

    df_diario = pd.DataFrame([
        {'data': '2026-10-25', 'origem': 'vermute', 'meio': 'link-banda', 'campanha': 'grc2026', 'sessoes': 20, 'carrinhos': 5, 'pagamentos': 2, 'compras': 1, 'receita': 50.0},
        {'data': '2026-10-26', 'origem': 'ig', 'meio': 'cpc', 'campanha': 'grc2026', 'sessoes': 50, 'carrinhos': 10, 'pagamentos': 4, 'compras': 1, 'receita': 180.0},
        {'data': '2026-10-26', 'origem': 'google', 'meio': 'organic', 'campanha': '(organic)', 'sessoes': 100, 'carrinhos': 2, 'pagamentos': 1, 'compras': 0, 'receita': 0.0},  # outra campanha
    ])

    df_links = pd.DataFrame([
        {'campanha': 'grc2026', 'banda': 'vermute', 'sessoes': 20, 'carrinhos': 5, 'pagamentos': 2, 'compras': 1, 'receita': 50.0, 'primeira_visita': '2026-10-25', 'ultima_visita': '2026-10-25'},
        {'campanha': 'grc2026', 'banda': 'ousel', 'sessoes': 15, 'carrinhos': 2, 'pagamentos': 0, 'compras': 0, 'receita': 0.0, 'primeira_visita': '2026-10-26', 'ultima_visita': '2026-10-26'},
    ])

    df = k7.montar_resumo(tabelas, df_diario, df_links)
    assert list(df.columns) == k7.COLUNAS_K7

    # Conferir bloco totais
    totais = dict(zip(df[df['bloco'] == 'totais']['chave'], df[df['bloco'] == 'totais']['valor_1']))
    assert totais['fitas_vendidas'] == '3'  # 1 do pedido 101 + 2 do pedido 102 (pedido 103 não conta)
    assert float(totais['receita']) == 150.0  # 3 * 50.0
    assert totais['pedidos'] == '2'
    assert float(totais['ticket_medio']) == 75.0  # 150.0 / 2
    assert totais['primeira_venda'] == '2026-10-25'
    assert totais['ultima_venda'] == '2026-10-26'
    assert totais['estoque_atual'] == '147'

    # Conferir bloco por_dia
    dias = df[df['bloco'] == 'por_dia'].set_index('chave')
    assert '2026-10-25' in dias.index
    assert '2026-10-26' in dias.index
    assert dias.loc['2026-10-25', 'valor_1'] == '1'
    assert float(dias.loc['2026-10-25', 'valor_2']) == 50.0
    assert dias.loc['2026-10-25', 'valor_3'] == '20'  # sessoes ga4

    assert dias.loc['2026-10-26', 'valor_1'] == '2'
    assert float(dias.loc['2026-10-26', 'valor_2']) == 100.0
    assert dias.loc['2026-10-26', 'valor_3'] == '50'

    # Conferir bloco por_banda
    bandas = df[df['bloco'] == 'por_banda'].set_index('chave')
    assert bandas.loc['vermute', 'valor_1'] == '20'  # sessões
    assert bandas.loc['vermute', 'valor_3'] == '1'   # compras
    assert float(bandas.loc['vermute', 'valor_4']) == 50.0

    # Conferir bloco canais
    canais = df[df['bloco'] == 'canais'].set_index('chave')
    assert 'Links das bandas' in canais.index
    assert 'Anúncios no Meta' in canais.index
    assert canais.loc['Links das bandas', 'valor_2'] == '1'  # compras

    # Conferir bloco junto_com
    junto = df[df['bloco'] == 'junto_com'].set_index('chave')
    assert 'LP Violator - Chemical Assault' in junto.index
    assert junto.loc['LP Violator - Chemical Assault', 'valor_1'] == '1'

    # Teste estrito de privacidade: nenhum dado pessoal em nenhuma coluna
    for col in df.columns:
        txt = ' '.join(df[col].astype(str))
        assert '@' not in txt
        assert 'cliente' not in txt.lower()
        assert '5562' not in txt
        assert '999991111' not in txt
        # Nenhum número de pedido deve constar
        assert '101' not in df[col].values
        assert '102' not in df[col].values
        assert '103' not in df[col].values


def test_privacidade_lanca_erro_se_houver_email():
    tabelas = Tabelas(
        clientes=pd.DataFrame(),
        pedidos=pd.DataFrame([{'numero': '1', 'email': 'x@x.com', 'data': '2026-10-25', 'valido': True}]),
        itens=pd.DataFrame([
            {'numero': '1', 'email': 'x@x.com', 'data': '2026-10-25', 'valido': True,
             'produto': 'Fita K7 Goiânia Rock City 2026', 'valor': 50.0, 'quantidade': 1, 'sku': '', 'produto_id': 375734821},
            {'numero': '1', 'email': 'x@x.com', 'data': '2026-10-25', 'valido': True,
             'produto': 'Disco Extra (comprador@email.com)', 'valor': 50.0, 'quantidade': 1, 'sku': '', 'produto_id': 12345},
        ]),
        produtos=pd.DataFrame(),
    )
    with pytest.raises(ValueError, match='Dado pessoal detectado'):
        k7.montar_resumo(tabelas)
