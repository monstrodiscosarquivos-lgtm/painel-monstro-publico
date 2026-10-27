"""Coletor por planilhas: lê as 3 exportações da Nuvemshop (clientes, vendas e produtos)
e monta as tabelas clientes, pedidos, itens e produtos.

Regras (AGENTS.md):
- Pedido válido: pagamento "Confirmado" ou "Parcialmente estornado" e pedido não cancelado.
- Na exportação de vendas cada linha é um item; os campos do pedido se repetem por número do pedido
  (as linhas de itens extras vêm com os campos do pedido em branco).
- Só leitura: nenhum arquivo de entrada é alterado.
- Privacidade: CPF/CNPJ, data de nascimento e endereço completo não passam para as tabelas.
"""
from __future__ import annotations

import glob
import os
from dataclasses import dataclass

import pandas as pd

PAGAMENTOS_VALIDOS = ('Confirmado', 'Parcialmente estornado')
FORMATO_DATA = '%d/%m/%Y %H:%M:%S'

# Colunas da exportação de vendas que pertencem ao item (o resto é do pedido).
COLUNAS_ITEM = ['Nome do Produto', 'Valor do Produto', 'Quantidade Comprada', 'SKU', 'Produto Fisico', 'Kit de produtos']

# Texto que só aparece em cada tipo de exportação (mesmo critério da referência).
ASSINATURAS = {
    'vendas': 'Número do Pedido',
    'clientes': 'Total Consumido',
    'produtos': 'Identificador URL',
}


@dataclass
class Tabelas:
    clientes: pd.DataFrame
    pedidos: pd.DataFrame
    itens: pd.DataFrame
    produtos: pd.DataFrame


def ler_csv(caminho: str) -> pd.DataFrame:
    """Lê um CSV da Nuvemshop (separador ';'), tudo como texto."""
    for codificacao in ('utf-8-sig', 'latin1'):
        try:
            return pd.read_csv(caminho, sep=';', encoding=codificacao, dtype=str)
        except UnicodeDecodeError:
            continue
    raise ValueError(f'Não consegui ler {caminho}')


def encontrar_exportacoes(pasta: str) -> dict[str, pd.DataFrame]:
    """Acha as 3 exportações em `pasta` pelo conteúdo das colunas, não pelo nome do arquivo."""
    achados: dict[str, pd.DataFrame] = {}
    for caminho in sorted(glob.glob(os.path.join(pasta, '*.csv'))):
        df = ler_csv(caminho)
        colunas = ' '.join(df.columns)
        for tipo, assinatura in ASSINATURAS.items():
            if assinatura in colunas:
                achados[tipo] = df
                break
    faltando = [t for t in ASSINATURAS if t not in achados]
    if faltando:
        raise FileNotFoundError(f'Faltam exportações em {pasta}: {", ".join(faltando)}')
    return achados


def _numero(serie: pd.Series) -> pd.Series:
    return pd.to_numeric(serie, errors='coerce')


def _email(serie: pd.Series) -> pd.Series:
    return serie.str.strip().str.lower()


def _data_br(serie: pd.Series) -> pd.Series:
    return pd.to_datetime(serie, format='%d/%m/%Y', errors='coerce')


def montar_vendas(vendas: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Devolve (pedidos, itens). Pedidos: uma linha por pedido. Itens: uma linha por item."""
    v = vendas.copy()
    colunas_pedido = [c for c in v.columns if c not in COLUNAS_ITEM]
    # Campos do pedido repetidos para todas as linhas do mesmo número (first ignora vazios).
    v[colunas_pedido] = v.groupby('Número do Pedido')[colunas_pedido].transform('first')

    v['data'] = pd.to_datetime(v['Data'], format=FORMATO_DATA, errors='coerce')
    v['email'] = _email(v['E-mail'])
    cancelado = v['Status do Pedido'].fillna('').str.strip().str.lower().str.startswith('cancel')
    v['valido'] = v['Status do Pagamento'].isin(PAGAMENTOS_VALIDOS) & ~cancelado  # cancelado não conta, mesmo se foi pago

    pedidos = v.drop_duplicates('Número do Pedido').copy()
    pedidos = pd.DataFrame({
        'numero': pedidos['Número do Pedido'],
        'email': pedidos['email'],
        'data': pedidos['data'],
        'status_pedido': pedidos['Status do Pedido'],
        'status_pagamento': pedidos['Status do Pagamento'],
        'valido': pedidos['valido'],
        'subtotal': _numero(pedidos['Subtotal']),
        'desconto': _numero(pedidos['Desconto']),
        'frete': _numero(pedidos['Valor do Frete']),
        'total': _numero(pedidos['Total']),
        'taxas': _numero(pedidos['Taxas']),
        'total_liquido': _numero(pedidos['Total líquido']),
        'cupom': pedidos['Cupom de Desconto'],
        'forma_pagamento': pedidos['Forma de Pagamento'],
        'forma_entrega': pedidos['Forma de Entrega'],
        'estorno': _numero(pedidos['Estorno']) if 'Estorno' in pedidos else float('nan'),  # coluna nova: sempre no fim; exportações antigas não têm
    }).reset_index(drop=True)

    itens = v.dropna(subset=['Nome do Produto'])
    itens = pd.DataFrame({
        'numero': itens['Número do Pedido'],
        'email': itens['email'],
        'data': itens['data'],
        'valido': itens['valido'],
        'produto': itens['Nome do Produto'],
        'valor': _numero(itens['Valor do Produto']),
        'quantidade': _numero(itens['Quantidade Comprada']),
        'sku': itens['SKU'],
        'produto_id': float('nan'),  # a exportação não traz o ID do produto; só a API traz
    }).reset_index(drop=True)
    return pedidos, itens


def montar_clientes(clientes: pd.DataFrame) -> pd.DataFrame:
    """Um cliente por email (vale a última linha). Sem CPF, nascimento e endereço."""
    c = clientes.copy()
    c['email'] = _email(c['E-mail'])
    c = c.drop_duplicates('email', keep='last')
    nome = c['Nome completo'].fillna('').str.strip()
    return pd.DataFrame({
        'email': c['email'],
        'nome': nome,
        'primeiro_nome': nome.str.split().str[0].str.title(),
        'telefone': c['Telefone de Contato'],
        'cidade': c['Cidade'],
        'estado': c['Estado'],
        'total_consumido': _numero(c['Total Consumido (BRL)']),
        'n_compras': _numero(c['Número de Compras']),
        'ultima_compra': _data_br(c['Última Compra']),
        'aceita_marketing': c['Marketing'] != 'Não aceita',
        'newsletter': c['Inscrição para newsletter'],
    }).reset_index(drop=True)


def montar_produtos(produtos: pd.DataFrame) -> pd.DataFrame:
    """Um produto por identificador de URL (as variações extras são descartadas).

    Estoque "ND" (sem controle de estoque) vira `estoque` vazio e `estoque_ilimitado` verdadeiro.
    """
    p = produtos.drop_duplicates('Identificador URL').copy()
    return pd.DataFrame({
        'url': p['Identificador URL'],
        'nome': p['Nome'],
        'categorias': p['Categorias'],
        'preco': _numero(p['Preço']),
        'preco_promocional': _numero(p['Preço promocional']),
        'estoque': _numero(p['Estoque']),
        'estoque_ilimitado': p['Estoque'] == 'ND',
        'exibir': p['Exibir na loja'] == 'SIM',
        'sku': p['SKU'],
        'marca': p['Marca'],
        'custo': _numero(p['Custo']),
        'id': float('nan'),  # a exportação não traz o ID do produto; só a API traz
        'criado_em': None, 'atualizado_em': None,  # idem: datas do produto só vêm da API
        'imagem': None, 'descricao': None,  # idem: imagem e descrição só vêm da API
    }).reset_index(drop=True)


def montar_tabelas(exportacoes: dict[str, pd.DataFrame]) -> Tabelas:
    pedidos, itens = montar_vendas(exportacoes['vendas'])
    return Tabelas(
        clientes=montar_clientes(exportacoes['clientes']),
        pedidos=pedidos,
        itens=itens,
        produtos=montar_produtos(exportacoes['produtos']),
    )


def coletar(pasta: str = 'dados/entrada') -> Tabelas:
    """Lê as 3 exportações de `pasta` e devolve as 4 tabelas."""
    return montar_tabelas(encontrar_exportacoes(pasta))
