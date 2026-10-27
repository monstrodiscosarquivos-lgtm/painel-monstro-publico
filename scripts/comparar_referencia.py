"""Compara o coletor novo com a referencia/reativacao.py, lado a lado.

Uso (na pasta do projeto):
    python scripts/comparar_referencia.py 2026-10

A referência é copiada junto com as exportações para dados/comparacao/ (fora do git) e executada lá,
para não criar arquivos dentro de referencia/. Os volumes das etapas novas vêm do motor
(painel_monstro/motor/regua.py).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from painel_monstro.log_publico import comando_seguro, ArgumentParserSeguro, resumo_erro
from painel_monstro.coletor import planilhas_csv  # noqa: E402
from painel_monstro.motor import regua  # noqa: E402


def rodar_referencia(mes: str) -> str:
    """Copia a referência e as exportações para dados/comparacao e roda. Devolve a pasta do mês."""
    base = os.path.join(RAIZ, 'dados', 'comparacao')
    pasta_mes = os.path.join(base, mes)
    if os.path.isdir(pasta_mes):
        shutil.rmtree(pasta_mes)
    os.makedirs(os.path.join(pasta_mes, 'entrada'))
    shutil.copy(os.path.join(RAIZ, 'referencia', 'reativacao.py'), base)
    for arq in os.listdir(os.path.join(RAIZ, 'dados', 'entrada')):
        if arq.lower().endswith('.csv'):
            shutil.copy(os.path.join(RAIZ, 'dados', 'entrada', arq), os.path.join(pasta_mes, 'entrada'))
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    env.pop('PYTHONPATH', None)
    subprocess.run([sys.executable, '-I', os.path.join(base, 'reativacao.py'), mes],
                   check=True, capture_output=True, env=env)
    return pasta_mes


def numeros_referencia(pasta_mes: str) -> dict:
    """Totais calculados com os mesmos passos de pandas da referência (linhas 100 a 117 dela)
    e volumes das etapas lidos das listas que a referência gerou."""
    sys.path.insert(0, os.path.dirname(pasta_mes))
    import importlib
    ref = importlib.import_module('reativacao')
    vendas = ref.ler(os.path.join(pasta_mes, 'entrada', 'vendas.csv'))
    item_cols = ['Nome do Produto', 'Valor do Produto', 'Quantidade Comprada', 'SKU', 'Produto Fisico', 'Kit de produtos']
    ordem = [c for c in vendas.columns if c not in item_cols]
    v = vendas.copy()
    v[ordem] = v.groupby('Número do Pedido')[ordem].transform('first')
    v = v[v['Status do Pagamento'].isin(['Confirmado', 'Parcialmente estornado'])]
    v['email'] = v['E-mail'].str.strip().str.lower()
    pedidos = v.drop_duplicates('Número do Pedido')

    listas = os.path.join(pasta_mes, 'listas')
    controle = ref.ler(os.path.join(listas, 'controle.csv'))
    volumes = {}
    nomes = {'Etapa 0 · Pós-compra': 'etapa0-pos-compra', 'Etapa 1 · Lembrete': 'etapa1-lembrete',
             'Etapa 2 · Convite': 'etapa2-convite', 'Etapa 3 · Última chamada': 'etapa3-ultima-chamada'}
    for nome, arq in nomes.items():
        volumes[nome] = (len(ref.ler(os.path.join(listas, arq + '.csv'))), int((controle['ETAPA'] == nome).sum()))
    volumes['VIP · WhatsApp'] = (len(ref.ler(os.path.join(listas, 'vip-whatsapp.csv'))), 0)
    nomes['VIP · WhatsApp'] = 'vip-whatsapp'
    pessoas = {nome: (set(ref.ler(os.path.join(listas, arq + '.csv'))['EMAIL'].str.lower()),
                      set(controle[controle['ETAPA'] == nome]['EMAIL'].str.lower()))
               for nome, arq in nomes.items()}
    return {'pedidos_pagos': len(pedidos), 'compradores': pedidos['email'].nunique(), 'volumes': volumes, 'pessoas': pessoas}


def numeros_novos(mes: str) -> dict:
    t = planilhas_csv.coletar(os.path.join(RAIZ, 'dados', 'entrada'))
    validos = t.pedidos[t.pedidos['valido']]
    classificacao, _ = regua.rodar(t, mes)
    volumes = {r.etapa: (r.recebem, r.controle) for r in regua.resumo(classificacao).itertuples()}
    pessoas = {nome: (set(regua.lista_da_etapa(classificacao, nome).index),
                      set(regua.lista_da_etapa(classificacao, nome, 'controle').index)) for nome in volumes}
    return {'pedidos_pagos': len(validos), 'compradores': validos['email'].nunique(), 'volumes': volumes, 'pessoas': pessoas,
            'tabelas': {k: len(getattr(t, k)) for k in ('clientes', 'pedidos', 'itens', 'produtos')}}


@comando_seguro
def main() -> int:
    if len(sys.argv) < 2 or not re.fullmatch(r'\d{4}-\d{2}', sys.argv[1]):
        print('Uso: python scripts/comparar_referencia.py AAAA-MM')
        return 2
    mes = sys.argv[1]
    pasta_mes = rodar_referencia(mes)
    ref, novo = numeros_referencia(pasta_mes), numeros_novos(mes)

    linhas = [('Pedidos pagos', ref['pedidos_pagos'], novo['pedidos_pagos']),
              ('Compradores únicos', ref['compradores'], novo['compradores'])]
    for nome, (r, c) in ref['volumes'].items():
        n_r, n_c = novo['volumes'][nome]
        linhas.append((f'{nome} · recebem', r, n_r))
        linhas.append((f'{nome} · controle', c, n_c))

    print(f'| {"Item":<38} | {"Referência":>10} | {"Novo":>10} | Bate? |')
    print(f'|{"-" * 40}|{"-" * 12}|{"-" * 12}|-------|')
    tudo_bate = True
    for nome, r, n in linhas:
        bate = r == n
        tudo_bate &= bate
        print(f'| {nome:<38} | {r:>10} | {n:>10} | {"sim" if bate else "NÃO"}   |')
    print()
    mesmas = all(ref['pessoas'][n] == novo['pessoas'][n] for n in ref['pessoas'])
    print('Mesmas pessoas em cada lista e em cada controle:', 'sim' if mesmas else 'NÃO')
    tudo_bate &= mesmas
    print('Tabelas montadas (linhas):', ', '.join(f'{k}={v}' for k, v in novo['tabelas'].items()))
    print('RESULTADO:', 'tudo bate' if tudo_bate else 'HÁ DIFERENÇAS')
    return 0 if tudo_bate else 1


if __name__ == '__main__':
    sys.exit(main())
