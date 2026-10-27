"""Atribuição manual de pedidos ao trabalho de LTV (D-064).

A aba `atribuicoes` (numero_pedido, origem, observacao, registrado_em) é escrita pelo painel do Cowork; a rotina só lê.
Origens: Indicação, WhatsApp manual, Outro. A linha "Indicações e contatos manuais" da aba `vale_a_pena` soma, no mês,
os pedidos pagos e válidos atribuídos. **Não é receita a mais**: não há grupo de controle, é receita atribuída.

- Pedido atribuído que já foi reconhecido por qualquer ciclo da Fila (Carrinho, Garimpo, VIP ou 45 dias; mesmo email ou
  telefone, dentro da janela de 7 dias do ciclo) conta só na Fila; a nota da linha diz quantos foram ignorados por isso.
- Opcional: a linha da Configuração "Prefixo de cupom de indicação" (vazia por padrão) faz pedidos com cupom que começa
  com esse prefixo entrarem sozinhos como Indicação.
- Mesma regra de receita do carrinho: subtotal menos desconto (produtos, sem frete).
"""
from __future__ import annotations

from typing import Any

import pandas as pd

ABA = 'atribuicoes'
COLUNAS = ['numero_pedido', 'origem', 'observacao', 'registrado_em']
ORIGENS = ('Indicação', 'WhatsApp manual', 'Outro')
ACAO = 'Indicações e contatos manuais'
ESTADO = 'sem controle'
CHAVE_PREFIXO = 'Prefixo de cupom de indicação'
JANELA_DIAS = 7  # igual à recuperação do carrinho


def _numero(valor: Any) -> str:
    t = str(valor if valor is not None else '').strip().lstrip('#')
    if t.endswith('.0') and t[:-2].isdigit():
        t = t[:-2]
    return t


def ler(valores: list[list[Any]] | None) -> pd.DataFrame:
    """Linhas da aba `atribuicoes` (com cabeçalho). Origem desconhecida vira Outro; linha sem número é ignorada."""
    if not valores or len(valores) < 2:
        return pd.DataFrame(columns=COLUNAS)
    cab = [str(c).strip() for c in valores[0]]
    if 'numero_pedido' not in cab:
        return pd.DataFrame(columns=COLUNAS)
    linhas = []
    for l in valores[1:]:
        d = {c: (l[i] if i < len(l) else '') for i, c in enumerate(cab) if c}
        n = _numero(d.get('numero_pedido'))
        if not n:
            continue
        o = str(d.get('origem') or '').strip()
        o = next((x for x in ORIGENS if x.lower() == o.lower()), 'Outro')
        linhas.append({'numero_pedido': n, 'origem': o, 'observacao': str(d.get('observacao') or ''),
                       'registrado_em': str(d.get('registrado_em') or '')})
    # Um pedido, uma atribuição: vale a última linha registrada
    return pd.DataFrame(linhas, columns=COLUNAS).drop_duplicates('numero_pedido', keep='last').reset_index(drop=True)


def pedidos_da_fila(fila: dict, pedidos: pd.DataFrame, tel_para_email: dict[str, str], so_digitos) -> dict[str, str]:
    """Número do pedido -> Origem da linha da Fila (Carrinho, Garimpo, VIP, 45 dias) que o reconheceu.

    É o primeiro pedido pago do mesmo email ou telefone em até 7 dias do primeiro toque (ou do abandono, no grupo de comparação).
    """
    p = pedidos[pedidos['valido'].astype(bool)].copy()
    p['_t'] = pd.to_datetime(p['data'])
    por_email = {e: g.sort_values('_t') for e, g in p.groupby('email')}
    achados: dict[str, str] = {}
    for e in fila.values():
        v = e.valores
        if str(v.get('Recuperado')) != 'Sim':
            continue
        inicio = pd.to_datetime(str(v.get('Primeiro toque em') or v.get('Abandonado em') or ''), errors='coerce')
        if pd.isna(inicio):
            continue
        if getattr(inicio, 'tzinfo', None) is not None:
            inicio = inicio.tz_localize(None)
        email = str(v.get('Email') or '').strip().lower() or tel_para_email.get(so_digitos(v.get('Telefone')), '')
        g = por_email.get(email)
        if g is None:
            continue
        no_prazo = g[(g['_t'] >= inicio) & (g['_t'] <= inicio + pd.Timedelta(days=JANELA_DIAS))]
        if len(no_prazo):
            achados.setdefault(_numero(no_prazo.iloc[0]['numero']), str(v.get('Origem') or 'Carrinho').strip() or 'Carrinho')
    return achados


pedidos_do_carrinho = pedidos_da_fila  # nome antigo


def linha_vale_a_pena(atribuicoes: pd.DataFrame, pedidos: pd.DataFrame, da_fila: dict[str, str] | set[str], prefixo: str,
                      hoje: pd.Timestamp) -> dict[str, Any]:
    """Linha pronta da aba `vale_a_pena` (sem grupo de controle) com os pedidos e a receita atribuídos no mês de `hoje`."""
    p = pedidos[pedidos['valido'].astype(bool)].copy()
    p['numero'] = p['numero'].map(_numero)
    mes = hoje.strftime('%Y-%m')
    p = p[pd.to_datetime(p['data']).dt.strftime('%Y-%m') == mes]
    origem = dict(zip(atribuicoes['numero_pedido'], atribuicoes['origem']))
    prefixo = str(prefixo or '').strip().lower()
    if prefixo:  # cupom que começa com o prefixo entra como Indicação, se ainda não houver atribuição manual
        for n, cupom in zip(p['numero'], p['cupom']):
            codigos = [c.strip().lower() for c in str(cupom).split(',')] if pd.notna(cupom) else []
            if n not in origem and any(c.startswith(prefixo) for c in codigos):
                origem[n] = 'Indicação'
    atribuidos = p[p['numero'].isin(origem)]
    da_fila = dict.fromkeys(da_fila, 'Fila') if not isinstance(da_fila, dict) else da_fila
    na_fila = atribuidos[atribuidos['numero'].isin(da_fila)]
    contam = atribuidos[~atribuidos['numero'].isin(da_fila)]
    receita = round(float((contam['subtotal'].astype(float) - contam['desconto'].astype(float)).sum()), 2)
    por_origem = contam['numero'].map(origem).value_counts()
    detalhe = ', '.join(f'{o}: {int(por_origem[o])}' for o in ORIGENS if o in por_origem.index)
    nota = (f'receita atribuída, não é receita a mais (sem grupo de controle); mês {mes}'
            + (f'; {detalhe}' if detalhe else '')
            + (f'; {len(na_fila)} ignorado(s) por já estarem na Fila ('
               + ', '.join(f'{o}: {int(k)}' for o, k in na_fila['numero'].map(da_fila).value_counts().items()) + ')'
               if len(na_fila) else ''))
    n = len(contam)
    return {'acao': ACAO, 'recebeu': n, 'controle': float('nan'), 'taxa': float('nan'), 'taxa_controle': float('nan'),
            'gasto_medio': round(receita / n, 2) if n else float('nan'), 'receita_a_mais': float('nan'), 'custo': float('nan'),
            'resultado': float('nan'), 'estado': ESTADO, 'nota': nota, 'pedidos': n, 'receita_atribuida': receita,
            'ignorados_na_fila': len(na_fila)}
