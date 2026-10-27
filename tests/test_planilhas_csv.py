"""Testes do coletor por planilhas. Todos os dados aqui são fictícios."""
import pandas as pd
import pytest

from painel_monstro.coletor import planilhas_csv as pc

VENDAS_CSV = """Número do Pedido;E-mail;Data;Status do Pedido;Status do Pagamento;Subtotal;Desconto;Valor do Frete;Total;Taxas;Total líquido;Cupom de Desconto;Forma de Pagamento;Forma de Entrega;Nome do Produto;Valor do Produto;Quantidade Comprada;SKU;Produto Fisico;Kit de produtos
1;  Ana@Exemplo.com ;01/03/2026 10:00:00;Aberto;Confirmado;150.50;10.00;20.00;160.50;3.00;157.50;VOLTA10MAR;Pix;Correios;Disco A;100;1;A1;SIM;NÃO
1;;;;;;;;;;;;;;Disco B;50.50;1;B1;SIM;NÃO
2;ana@exemplo.com;10/04/2026 18:30:00;Aberto;Pendente;80.00;0.00;10.00;90.00;0;0;;Boleto;Correios;Disco C;80;1;C1;SIM;NÃO
3;bruno@exemplo.com;15/04/2026 09:00:00;Aberto;Parcialmente estornado;200;0;0;200;4;196;;Cartão;Retirada;Disco D;200;1;D1;SIM;NÃO
4;carla@exemplo.com;20/04/2026 09:00:00;Cancelado;Vencido;70;0;0;70;0;0;;Boleto;Retirada;Disco E;70;1;E1;SIM;NÃO
5;dora@exemplo.com;25/04/2026 09:00:00;Cancelado;Confirmado;90;0;0;90;0;0;;Pix;Retirada;Disco F;90;1;F1;SIM;NÃO
"""

CLIENTES_CSV = """Nome completo;CPF/CNPJ;E-mail;Telefone de Contato;Endereço;Cidade;Estado;Data de nascimento;Total Consumido (BRL);Número de Compras;Última Compra;Inscrição para newsletter;Marketing
ana souza lima;111.111.111-11;Ana@Exemplo.com;62999990000;Rua Fictícia 1;Goiânia;GO;01/01/1990;100.00;1;01/03/2026;Sim;Aceita
Ana Souza;111.111.111-11;ana@exemplo.com;62999990000;Rua Fictícia 1;Goiânia;GO;01/01/1990;260.00;2;10/04/2026;Sim;Aceita
bruno;222.222.222-22;bruno@exemplo.com;;Rua Fictícia 2;Anápolis;GO;;200.00;1;15/04/2026;Não;Não aceita
"""

PRODUTOS_CSV = """Identificador URL;Nome;Categorias;Preço;Preço promocional;Estoque;SKU;Exibir na loja;Marca;Custo
disco-a;Disco A;Jazz;100.00;;3;A1;SIM;Selo X;40.00
disco-a;Disco A;Jazz;100.00;;3;A1-V2;SIM;Selo X;40.00
disco-b;Disco B;Rock;50.50;45.00;ND;B1;NÃO;;
disco-c;Disco C;Rock;80.00;;0;C1;SIM;;
"""


@pytest.fixture
def pasta(tmp_path):
    # A Nuvemshop exporta em latin1; os nomes dos arquivos não importam.
    for nome, conteudo in [('a.csv', VENDAS_CSV), ('b.csv', CLIENTES_CSV), ('c.csv', PRODUTOS_CSV)]:
        (tmp_path / nome).write_bytes(conteudo.encode('latin1'))
    return tmp_path


@pytest.fixture
def tabelas(pasta):
    return pc.coletar(str(pasta))


def test_identifica_as_exportacoes_pelo_conteudo(pasta):
    achados = pc.encontrar_exportacoes(str(pasta))
    assert set(achados) == {'vendas', 'clientes', 'produtos'}
    assert 'Número do Pedido' in achados['vendas'].columns


def test_falta_de_exportacao_da_erro_claro(tmp_path):
    (tmp_path / 'v.csv').write_bytes(VENDAS_CSV.encode('latin1'))
    with pytest.raises(FileNotFoundError, match='clientes, produtos'):
        pc.coletar(str(tmp_path))


def test_le_utf8_com_bom(tmp_path):
    (tmp_path / 'x.csv').write_bytes(('﻿' + PRODUTOS_CSV).encode('utf-8'))
    df = pc.ler_csv(str(tmp_path / 'x.csv'))
    assert 'Identificador URL' in df.columns
    assert 'Preço' in df.columns


def test_pedidos_uma_linha_por_numero(tabelas):
    assert list(tabelas.pedidos['numero']) == ['1', '2', '3', '4', '5']


def test_itens_uma_linha_por_item_e_herdam_campos_do_pedido(tabelas):
    itens = tabelas.itens
    assert len(itens) == 6
    disco_b = itens[itens['produto'] == 'Disco B'].iloc[0]
    assert disco_b['numero'] == '1'
    assert disco_b['email'] == 'ana@exemplo.com'
    assert bool(disco_b['valido']) is True
    assert disco_b['valor'] == 50.5


def test_pedido_valido_so_confirmado_ou_parcialmente_estornado(tabelas):
    validos = dict(zip(tabelas.pedidos['numero'], tabelas.pedidos['valido']))
    assert validos == {'1': True, '2': False, '3': True, '4': False, '5': False}


def test_pedido_pago_mas_cancelado_nao_conta(tabelas):
    p5 = tabelas.pedidos.set_index('numero').loc['5']
    assert p5['status_pagamento'] == 'Confirmado' and bool(p5['valido']) is False
    assert not tabelas.itens[tabelas.itens['numero'] == '5']['valido'].any()


def test_email_normalizado_e_valores_numericos(tabelas):
    p1 = tabelas.pedidos.iloc[0]
    assert p1['email'] == 'ana@exemplo.com'
    assert p1['total'] == 160.5
    assert p1['frete'] == 20.0
    assert p1['desconto'] == 10.0
    assert p1['total_liquido'] == 157.5
    assert p1['cupom'] == 'VOLTA10MAR'
    assert p1['data'] == pd.Timestamp('2026-03-01 10:00:00')


def test_clientes_um_por_email_vale_a_ultima_linha(tabelas):
    c = tabelas.clientes
    assert list(c['email']) == ['ana@exemplo.com', 'bruno@exemplo.com']
    ana = c.iloc[0]
    assert ana['n_compras'] == 2
    assert ana['total_consumido'] == 260.0
    assert ana['primeiro_nome'] == 'Ana'
    assert ana['ultima_compra'] == pd.Timestamp('2026-04-10')


def test_marketing_nao_aceita(tabelas):
    c = tabelas.clientes.set_index('email')
    assert bool(c.loc['ana@exemplo.com', 'aceita_marketing']) is True
    assert bool(c.loc['bruno@exemplo.com', 'aceita_marketing']) is False


def test_dados_sensiveis_nao_entram_nas_tabelas(tabelas):
    proibidas = {'cpf', 'cpf/cnpj', 'endereço', 'endereco', 'data de nascimento', 'nascimento'}
    for df in (tabelas.clientes, tabelas.pedidos, tabelas.itens, tabelas.produtos):
        assert not proibidas & {c.lower() for c in df.columns}


def test_produtos_sem_duplicar_variacoes(tabelas):
    assert list(tabelas.produtos['url']) == ['disco-a', 'disco-b', 'disco-c']


def test_estoque_nd_e_ilimitado_e_exibir(tabelas):
    p = tabelas.produtos.set_index('url')
    assert p.loc['disco-a', 'estoque'] == 3
    assert bool(p.loc['disco-a', 'estoque_ilimitado']) is False
    assert pd.isna(p.loc['disco-b', 'estoque'])
    assert bool(p.loc['disco-b', 'estoque_ilimitado']) is True
    assert bool(p.loc['disco-b', 'exibir']) is False
    assert p.loc['disco-b', 'preco_promocional'] == 45.0
    assert p.loc['disco-a', 'custo'] == 40.0
    assert p.loc['disco-c', 'estoque'] == 0


def test_estorno_fica_no_fim_e_vazio_quando_a_exportacao_nao_traz(tabelas):
    assert list(tabelas.pedidos.columns)[-1] == 'estorno'
    assert tabelas.pedidos['estorno'].isna().all()


def test_estorno_lido_da_exportacao(tmp_path):
    csv = VENDAS_CSV.split(chr(10))
    csv[0] += ';Estorno'
    for k in range(1, len(csv)):
        if csv[k].strip():
            csv[k] += ';25.5' if csv[k].startswith('3;') else ';'
    (tmp_path / 'a.csv').write_bytes(chr(10).join(csv).encode('latin1'))
    (tmp_path / 'b.csv').write_bytes(CLIENTES_CSV.encode('latin1'))
    (tmp_path / 'c.csv').write_bytes(PRODUTOS_CSV.encode('latin1'))
    p = pc.coletar(str(tmp_path)).pedidos
    p = p.set_index(p['numero'].astype(str))
    assert p.loc['3', 'estorno'] == 25.5
    assert pd.isna(p.iloc[0]['estorno'])
