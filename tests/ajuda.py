"""Montagem de dados fictícios para os testes do motor."""
from __future__ import annotations

import pandas as pd

from painel_monstro.coletor.planilhas_csv import Tabelas

REFERENCIA = pd.Timestamp('2026-10-10')  # dia seguinte ao último pedido dos exemplos


def pedido(numero, email, data, total=100.0, valido=True, subtotal=None, desconto=0.0):
    subtotal = total if subtotal is None else subtotal
    return {'numero': str(numero), 'email': email, 'data': pd.Timestamp(data), 'valido': valido,
            'subtotal': float(subtotal), 'desconto': float(desconto), 'frete': 0.0, 'total': float(total)}


def cliente(email, aceita=True, nome='Ana'):
    return {'email': email, 'nome': nome, 'primeiro_nome': nome, 'telefone': '6299', 'cidade': 'Goiânia',
            'aceita_marketing': aceita}


def tabelas(pedidos, clientes=None, itens=None, produtos=None) -> Tabelas:
    ped = pd.DataFrame(pedidos)
    emails = sorted(set(ped['email'])) if clientes is None else None
    cli = pd.DataFrame(clientes if clientes is not None else [cliente(e) for e in emails])
    colunas_itens = ['numero', 'email', 'data', 'valido', 'produto', 'valor', 'quantidade', 'sku']
    if itens and 'produto_id' in itens[0]:
        colunas_itens.append('produto_id')
    it = pd.DataFrame(itens if itens is not None else [], columns=colunas_itens)
    colunas_produtos = ['url', 'nome', 'categorias', 'custo'] + (['id'] if produtos and 'id' in produtos[0] else [])
    pro = pd.DataFrame(produtos if produtos is not None else [], columns=colunas_produtos)
    return Tabelas(clientes=cli, pedidos=ped, itens=it, produtos=pro)


def dias_atras(dias, referencia=REFERENCIA):
    """Data de uma compra que, na data de referência, tem exatamente `dias` dias sem comprar."""
    return referencia - pd.Timedelta(days=dias)
