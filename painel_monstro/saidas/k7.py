"""Acompanhamento da Fita K7 Goiânia Rock City 2026 (D-092).

Gera a aba `k7_resumo` a cada rodada a partir das tabelas que a rotina já tem
(pedidos, itens, produtos, ga4_links, ga4_diario).
Formato longo: bloco, chave, valor_1, valor_2, valor_3, valor_4.
Sem dados pessoais de clientes (nome, email, telefone, cidade ou número de pedido).
"""
from __future__ import annotations

import re
from typing import Any

import pandas as pd

from painel_monstro.coletor.planilhas_csv import Tabelas

PRODUTO_K7_ID = 375734821
CAMPANHA_K7 = 'grc2026'
ABA_K7 = 'k7_resumo'
COLUNAS_K7 = ['bloco', 'chave', 'valor_1', 'valor_2', 'valor_3', 'valor_4']

BANDAS_K7 = [
    ('abajur-always-on', 'Abajur Always On'),
    ('agnoizze', 'Agnoizze'),
    ('amados-mortos', 'Amados Mortos'),
    ('banana-bipolar', 'Banana Bipolar'),
    ('cabrosa', 'Cabrosa'),
    ('can-sad', 'Can Sad'),
    ('despenca', 'Despenca'),
    ('gronga-pussanto', 'Gronga Pussanto'),
    ('idos-de-marco', 'Idos de Março'),
    ('ousel', 'Ousel'),
    ('prehistoric-music-departament', 'Prehistoric Music Departament'),
    ('sangra-dagua', "Sangra D'água"),
    ('synx', 'Synx'),
    ('uniao-clandestina', 'União Clandestina'),
    ('vermute', 'Vermute'),
]

RE_PAGO = re.compile(r'(^|[^a-z])(cpc|ppc|paid|ads?|pago|anuncio)([^a-z]|$)', re.IGNORECASE)


def classificar_canal(origem: Any, meio: Any) -> str:
    """Classifica a origem do GA4 no canal amigável, no mesmo padrão do Painel."""
    s = str(origem or '').strip().lower()
    m = str(meio or '').strip().lower()
    if m == 'link-banda':
        return 'Links das bandas'
    pago = bool(RE_PAGO.search(m))
    sem_meio = not m or m in ('(not set)', '(none)')
    if re.match(r'^(ig|fb|meta|an|msg)$', s):
        if pago or sem_meio:
            return 'Anúncios no Meta'
        return 'Instagram (sem anúncio)' if s == 'ig' else 'Facebook (sem anúncio)'
    if 'instagram' in s:
        return 'Anúncios no Meta' if pago else 'Instagram (sem anúncio)'
    if 'facebook' in s:
        return 'Anúncios no Meta' if pago else 'Facebook (sem anúncio)'
    if 'google' in s:
        return 'Google Ads' if pago else 'Google (busca)'
    if s == '(direct)':
        return 'Direto (sem origem)'
    if re.search(r'brevo|sendibm|sendinblue', s) or m == 'email':
        return 'Email (Brevo)'
    if re.search(r'whatsapp|^wa$|wa\.me|l\.wl\.co', s):
        return 'WhatsApp'
    if s in ('th', 'threads'):
        return 'Threads'
    if re.search(r'bing|yahoo|duckduckgo|ecosia', s):
        return 'Outros buscadores'
    return 'Outros sites e apps'


def _eh_item_k7(item: pd.Series) -> bool:
    pid = str(item.get('produto_id', '')).split('.')[0].strip()
    if pid == str(PRODUTO_K7_ID):
        return True
    nome = str(item.get('produto', '')).lower()
    return 'goiânia rock city 2026' in nome or 'goiania rock city 2026' in nome


def montar_resumo(tabelas: Tabelas, df_diario: pd.DataFrame | None = None,
                  df_links: pd.DataFrame | None = None) -> pd.DataFrame:
    """Monta a tabela `k7_resumo` no formato longo."""
    linhas: list[list[str]] = []

    # 1. Itens e pedidos válidos
    itens_validos = tabelas.itens[tabelas.itens['valido'].astype(bool)].copy() if len(tabelas.itens) else pd.DataFrame(columns=tabelas.itens.columns)
    if len(itens_validos):
        mascara_k7 = itens_validos.apply(_eh_item_k7, axis=1)
        itens_k7 = itens_validos[mascara_k7]
    else:
        mascara_k7 = pd.Series([], dtype=bool)
        itens_k7 = pd.DataFrame(columns=tabelas.itens.columns)

    # Estoque atual do produto em produtos
    estoque_atual = None
    if len(tabelas.produtos):
        pids = tabelas.produtos['id'].astype(str).str.split('.').str[0].str.strip()
        prods_k7 = tabelas.produtos[pids == str(PRODUTO_K7_ID)]
        if len(prods_k7):
            e = prods_k7.iloc[0].get('estoque')
            if pd.notna(e):
                estoque_atual = int(e)

    # Totais
    fitas_vendidas = int(pd.to_numeric(itens_k7['quantidade'], errors='coerce').fillna(0).sum()) if len(itens_k7) else 0
    subtotais_item = pd.to_numeric(itens_k7['valor'], errors='coerce').fillna(0) * pd.to_numeric(itens_k7['quantidade'], errors='coerce').fillna(0) if len(itens_k7) else pd.Series([], dtype=float)
    receita_fita = round(float(subtotais_item.sum()), 2) if len(subtotais_item) else 0.0
    num_pedidos = int(itens_k7['numero'].nunique()) if len(itens_k7) else 0
    ticket_medio = round(receita_fita / num_pedidos, 2) if num_pedidos > 0 else 0.0

    primeira_venda = ''
    ultima_venda = ''
    if len(itens_k7):
        datas = pd.to_datetime(itens_k7['data'], errors='coerce').dropna().sort_values()
        if len(datas):
            primeira_venda = datas.iloc[0].strftime('%Y-%m-%d')
            ultima_venda = datas.iloc[-1].strftime('%Y-%m-%d')

    linhas.append(['totais', 'fitas_vendidas', str(fitas_vendidas), '', '', ''])
    linhas.append(['totais', 'receita', str(receita_fita), '', '', ''])
    linhas.append(['totais', 'pedidos', str(num_pedidos), '', '', ''])
    linhas.append(['totais', 'ticket_medio', str(ticket_medio), '', '', ''])
    linhas.append(['totais', 'primeira_venda', primeira_venda, '', '', ''])
    linhas.append(['totais', 'ultima_venda', ultima_venda, '', '', ''])
    linhas.append(['totais', 'estoque_atual', str(estoque_atual) if estoque_atual is not None else '', '', '', ''])

    # 2. Por dia
    vendas_por_dia: dict[str, dict[str, float]] = {}
    if len(itens_k7):
        datas_k7 = pd.to_datetime(itens_k7['data'], errors='coerce').dt.strftime('%Y-%m-%d')
        for dia, qtd, val in zip(datas_k7, itens_k7['quantidade'], itens_k7['valor']):
            if not dia or pd.isna(dia):
                continue
            q = float(qtd or 0)
            v = float(val or 0) * q
            if dia not in vendas_por_dia:
                vendas_por_dia[dia] = {'fitas': 0, 'receita': 0.0}
            vendas_por_dia[dia]['fitas'] += int(q)
            vendas_por_dia[dia]['receita'] = round(vendas_por_dia[dia]['receita'] + v, 2)

    sessoes_por_dia: dict[str, int] = {}
    if df_diario is not None and len(df_diario):
        diario_k7 = df_diario[df_diario['campanha'].astype(str).str.strip() == CAMPANHA_K7]
        for _, row in diario_k7.iterrows():
            d = str(row.get('data', ''))[:10]
            if d:
                sess = int(pd.to_numeric(row.get('sessoes', 0), errors='coerce') or 0)
                sessoes_por_dia[d] = sessoes_por_dia.get(d, 0) + sess

    todos_dias = sorted(set(vendas_por_dia.keys()) | set(sessoes_por_dia.keys()), reverse=True)
    for d in todos_dias:
        vp = vendas_por_dia.get(d, {'fitas': 0, 'receita': 0.0})
        sess = sessoes_por_dia.get(d, 0)
        linhas.append(['por_dia', d, str(int(vp['fitas'])), str(round(vp['receita'], 2)), str(sess), ''])

    # 3. Por banda
    dados_bandas: dict[str, dict[str, float]] = {}
    for cod_banda, _ in BANDAS_K7:
        dados_bandas[cod_banda] = {'sessoes': 0, 'carrinhos': 0, 'compras': 0, 'receita': 0.0}

    if df_links is not None and len(df_links):
        links_k7 = df_links[df_links['campanha'].astype(str).str.strip() == CAMPANHA_K7]
        for _, row in links_k7.iterrows():
            b = str(row.get('banda', '')).strip()
            if not b:
                continue
            if b not in dados_bandas:
                dados_bandas[b] = {'sessoes': 0, 'carrinhos': 0, 'compras': 0, 'receita': 0.0}
            dados_bandas[b]['sessoes'] += int(pd.to_numeric(row.get('sessoes', 0), errors='coerce') or 0)
            dados_bandas[b]['carrinhos'] += int(pd.to_numeric(row.get('carrinhos', 0), errors='coerce') or 0)
            dados_bandas[b]['compras'] += int(pd.to_numeric(row.get('compras', 0), errors='coerce') or 0)
            dados_bandas[b]['receita'] = round(dados_bandas[b]['receita'] + float(pd.to_numeric(row.get('receita', 0), errors='coerce') or 0), 2)

    bandas_ord = sorted(dados_bandas.items(), key=lambda x: (x[1]['compras'], x[1]['sessoes'], x[1]['receita']), reverse=True)
    for b, vals in bandas_ord:
        linhas.append(['por_banda', b, str(int(vals['sessoes'])), str(int(vals['carrinhos'])),
                       str(int(vals['compras'])), str(round(vals['receita'], 2))])

    # 4. Canais
    dados_canais: dict[str, dict[str, float]] = {}
    if df_diario is not None and len(df_diario):
        diario_k7 = df_diario[df_diario['campanha'].astype(str).str.strip() == CAMPANHA_K7]
        for _, row in diario_k7.iterrows():
            canal = classificar_canal(row.get('origem'), row.get('meio'))
            if canal not in dados_canais:
                dados_canais[canal] = {'sessoes': 0, 'compras': 0, 'receita': 0.0}
            dados_canais[canal]['sessoes'] += int(pd.to_numeric(row.get('sessoes', 0), errors='coerce') or 0)
            dados_canais[canal]['compras'] += int(pd.to_numeric(row.get('compras', 0), errors='coerce') or 0)
            dados_canais[canal]['receita'] = round(dados_canais[canal]['receita'] + float(pd.to_numeric(row.get('receita', 0), errors='coerce') or 0), 2)

    canais_ord = sorted(dados_canais.items(), key=lambda x: (x[1]['compras'], x[1]['sessoes']), reverse=True)
    for c, vals in canais_ord:
        linhas.append(['canais', c, str(int(vals['sessoes'])), str(int(vals['compras'])), str(round(vals['receita'], 2)), ''])

    # 5. Junto com (os 10 produtos mais comprados no mesmo pedido da fita)
    if len(itens_k7):
        pedidos_com_k7 = set(itens_k7['numero'].astype(str))
        outros_itens = itens_validos[itens_validos['numero'].astype(str).isin(pedidos_com_k7) & ~mascara_k7]
        if len(outros_itens):
            qtds = pd.to_numeric(outros_itens['quantidade'], errors='coerce').fillna(1)
            junto = outros_itens.assign(qtd=qtds).groupby('produto')['qtd'].sum().sort_values(ascending=False).head(10)
            for prod_nome, qtd_total in junto.items():
                linhas.append(['junto_com', str(prod_nome), str(int(qtd_total)), '', '', ''])

    df = pd.DataFrame(linhas, columns=COLUNAS_K7)

    # Verificação estrita de segurança: sem email, telefone ou número de pedidos
    for col in df.columns:
        valores_texto = df[col].astype(str)
        if valores_texto.str.contains('@', regex=False).any():
            raise ValueError(f'Dado pessoal detectado em k7_resumo: @ na coluna {col}')
        if valores_texto.str.contains(r'55\d{10,11}', regex=True).any():
            raise ValueError(f'Dado pessoal detectado em k7_resumo: telefone na coluna {col}')

    return df
