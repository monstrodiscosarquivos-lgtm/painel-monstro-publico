"""Compara os totais da API da Nuvemshop (Etapa 2) com os das exportações em CSV (Etapa 1).

Uso (na pasta do projeto):
    python scripts/comparar_api_csv.py

Atualiza os dados da API (só o que mudou) e depois compara. Só leitura. Não imprime dados de clientes.
"""
from __future__ import annotations

import os
import sys

import pandas as pd

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from painel_monstro.log_publico import comando_seguro, ArgumentParserSeguro, resumo_erro
from painel_monstro.config import carregar  # noqa: E402
from painel_monstro.coletor import nuvemshop_api, planilhas_csv  # noqa: E402


def linha(nome, csv, api, nota=''):
    diferenca = api - csv
    print(f'| {nome:<42} | {csv:>9} | {api:>9} | {diferenca:>+9} | {nota}')


@comando_seguro
def main() -> int:
    csv = planilhas_csv.coletar(os.path.join(RAIZ, 'dados', 'entrada'))
    api, resumo = nuvemshop_api.coletar(carregar())
    for recurso, r in resumo.items():
        print(f'API {recurso}: {r["modo"]}, {r["novos"]} novos, {r["atualizados"]} atualizados')
    print()

    corte = csv.pedidos['data'].max()
    pa, pc = api.pedidos, csv.pedidos
    depois = pa[pa['data'] > corte]
    pa_ate = pa[pa['data'] <= corte]
    ate_valido = pa_ate[pa_ate['valido']]
    csv_validos = pc[pc['valido']]

    print(f'Exportações em CSV vão até {corte:%d/%m/%Y %H:%M}. Pedidos da API depois disso: {len(depois)} '
          f'({int(depois["valido"].sum())} pagos).\n')
    print(f'| {"Item":<42} | {"CSV":>9} | {"API":>9} | {"Diferença":>9} | Nota')
    print(f'|{"-" * 44}|{"-" * 11}|{"-" * 11}|{"-" * 11}|------')
    linha('Pedidos (todos os status)', len(pc), len(pa), 'API inclui pedidos novos e de outros status')
    linha('Pedidos pagos (todo o período)', len(csv_validos), int(pa['valido'].sum()), 'diferença = pedidos feitos depois da exportação')
    linha('Pedidos pagos até o fim do CSV', len(csv_validos), len(ate_valido), 'mesmo período: deve ser zero')
    linha('Compradores únicos (pagos, mesmo período)', csv_validos['email'].nunique(), ate_valido['email'].nunique())
    linha('Itens (pagos, mesmo período)', int(csv.itens['valido'].sum()),
          int(api.itens[api.itens['data'] <= corte]['valido'].sum()))
    linha('Clientes', len(csv.clientes), len(api.clientes), 'cadastros novos depois da exportação')
    linha('Clientes que aceitam marketing', int(csv.clientes['aceita_marketing'].sum()), int(api.clientes['aceita_marketing'].sum()))
    linha('Produtos', len(csv.produtos), len(api.produtos))
    linha('Produtos visíveis na loja', int(csv.produtos['exibir'].sum()), int(api.produtos['exibir'].sum()))
    linha('Receita dos pedidos pagos (R$, mesmo período)', round(csv_validos['total'].sum()), round(ate_valido['total'].sum()))

    # Pedido a pedido, no mesmo período
    c = pc.set_index('numero')
    a = pa_ate.set_index('numero')
    so_csv, so_api = c.index.difference(a.index), a.index.difference(c.index)
    comuns = c.index.intersection(a.index)
    print(f'\nPedidos só no CSV: {len(so_csv)} | só na API (até o fim do CSV): {len(so_api)} | nos dois: {len(comuns)}')
    cc, aa = c.loc[comuns], a.loc[comuns]
    for campo, igual in [
        ('pagamento válido', cc['valido'] == aa['valido']),
        ('email', cc['email'] == aa['email']),
        ('total', (cc['total'] - aa['total']).abs() < 0.01),
        ('desconto', (cc['desconto'].fillna(0) - aa['desconto'].fillna(0)).abs() < 0.01),
        ('subtotal', (cc['subtotal'] - aa['subtotal']).abs() < 0.01),
        ('frete (API calculado)', (cc['frete'].fillna(0) - aa['frete'].fillna(0)).abs() < 0.01),
        ('data/hora (diferença até 1 min)', (cc['data'] - aa['data']).abs() <= pd.Timedelta(minutes=1)),
        ('cupom', cc['cupom'].fillna('').str.upper() == aa['cupom'].fillna('').str.upper()),
    ]:
        print(f'  {campo:<34} iguais em {int(igual.sum())} de {len(comuns)}' + ('' if igual.all() else f'  ({int((~igual).sum())} diferentes)'))

    n_c = csv.itens.groupby('numero').size().reindex(comuns)
    n_a = api.itens.groupby('numero').size().reindex(comuns)
    print(f'  {"número de itens por pedido":<34} iguais em {int((n_c == n_a).sum())} de {len(comuns)}')

    # Clientes (por email) com compras: o resultado da régua depende de n_compras e total
    cl_c, cl_a = csv.clientes.set_index('email'), api.clientes.set_index('email')
    em = cl_c.index.intersection(cl_a.index)
    print(f'\nClientes só no CSV: {len(cl_c.index.difference(cl_a.index))} | só na API: {len(cl_a.index.difference(cl_c.index))} | nos dois: {len(em)}')
    mk = cl_c.loc[em, 'aceita_marketing'] == cl_a.loc[em, 'aceita_marketing']
    print(f'  aceita marketing igual em {int(mk.sum())} de {len(em)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
