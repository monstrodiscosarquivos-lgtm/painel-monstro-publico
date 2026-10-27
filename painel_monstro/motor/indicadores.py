"""Indicadores do painel (AGENTS.md, "Indicadores do painel" e "Regras de negócio").

Tudo sai das 4 tabelas do coletor (`Tabelas`) mais a aba `custos`, que o Túlio preenche:

    mes (AAAA-MM) | investimento_meta | compras_meta | receita_meta | custo_brevo | receita_brevo
    margem_usados | margem_lacrados | embalagem | frete_pago_loja

- `investimento_meta`, `compras_meta`, `receita_meta`: gasto no Meta no mês e o que o Meta atribui a ele.
- `custo_brevo`: mensalidade do Brevo no mês. `receita_brevo`: vendas que o Brevo atribui aos envios.
- `margem_usados` e `margem_lacrados`: margem média (45 ou 0,45 para 45%), valem também para os meses
  anteriores e seguintes até aparecer outro valor.
- `embalagem`: custo de embalagem por pedido, com a mesma regra.
- `frete_pago_loja`: frete que a loja pagou no mês (R$), por exemplo em campanha de frete grátis.
  Vazio conta como zero (D-027).

Indicador sem os dados de que precisa aparece como "falta dados", com o motivo, e nunca como zero.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

import numpy as np
import pandas as pd

from painel_monstro.coletor.planilhas_csv import Tabelas
from painel_monstro.motor.regua import pedidos_validos

CUSTOS_COLUNAS = ['mes', 'investimento_meta', 'compras_meta', 'receita_meta', 'custo_brevo', 'receita_brevo',
                  'margem_usados', 'margem_lacrados', 'embalagem', 'frete_pago_loja']
OK, FALTA_CUSTOS, FALTA_DADOS = 'ok', 'falta custos', 'falta dados'


@dataclass(frozen=True)
class ParametrosIndicadores:
    remuneracao_marketing: float = 0.10  # 10% do valor vendido
    taxa_pagamento: float = 0.021        # média das taxas de pagamento sobre o total cobrado
    teto_custo_marketing: float = 0.15   # objetivo: custo total de marketing até 15% da receita
    meta_participacao_recompra: float = 0.35
    janela_dias: int = 365


PADRAO = ParametrosIndicadores()


# ----------------------------------------------------------------------------
# Aba custos
# ----------------------------------------------------------------------------
def _numero_br(valor) -> float:
    """Aceita 1234.5, "1.234,50", "R$ 1.234,50" e "45%"."""
    if valor is None or (isinstance(valor, float) and np.isnan(valor)):
        return float('nan')
    if isinstance(valor, (int, float, np.number)):
        return float(valor)
    texto = re.sub(r'[R$%\s]', '', str(valor))
    if not texto:
        return float('nan')
    if ',' in texto:
        texto = texto.replace('.', '').replace(',', '.')
    try:
        return float(texto)
    except ValueError:
        return float('nan')


_MESES_PT = {'jan': 1, 'fev': 2, 'mar': 3, 'abr': 4, 'mai': 5, 'jun': 6, 'jul': 7, 'ago': 8, 'set': 9, 'out': 10, 'nov': 11, 'dez': 12}


def _mes(valor) -> str | None:
    """Mês da aba `custos`: aceita "2026-10", data (2026-10-01, 01/10/2026, célula de data da planilha), "10/2026" e "out/2026"."""
    if valor is None or (isinstance(valor, float) and np.isnan(valor)):
        return None
    if isinstance(valor, (pd.Timestamp, np.datetime64)):
        return pd.Timestamp(valor).strftime('%Y-%m')
    if isinstance(valor, (int, float, np.number)) and not isinstance(valor, bool):
        if 20000 < float(valor) < 100000:  # número de série de uma célula de data do Google Sheets
            return (pd.Timestamp('1899-12-30') + pd.Timedelta(days=float(valor))).strftime('%Y-%m')
        return None
    texto = str(valor).strip()
    if re.fullmatch(r'\d{4}-\d{2}', texto):
        return texto
    achou = re.fullmatch(r'(\d{4})-(\d{2})-\d{2}(?:[ T].*)?', texto)
    if achou:
        return f'{achou.group(1)}-{achou.group(2)}'
    achou = re.fullmatch(r'([a-zçãé]{3})[a-zçãé]*[\s/.\-]+(?:de\s+)?(\d{4})', texto.lower())
    if achou and achou.group(1) in _MESES_PT:
        return f'{achou.group(2)}-{_MESES_PT[achou.group(1)]:02d}'
    achou = re.fullmatch(r'(\d{1,2})/(\d{4})', texto)
    if achou:
        return f'{achou.group(2)}-{int(achou.group(1)):02d}'
    achou = re.fullmatch(r'\d{1,2}/(\d{1,2})/(\d{4})', texto)
    if achou:
        return f'{achou.group(2)}-{int(achou.group(1)):02d}'
    return None


def ler_custos(origem: pd.DataFrame | str | None) -> pd.DataFrame:
    """Normaliza a aba `custos` (DataFrame ou caminho de um CSV com ';'). Vazio se não houver nada."""
    if origem is None:
        return pd.DataFrame(columns=CUSTOS_COLUNAS)
    if isinstance(origem, str):
        try:
            origem = pd.read_csv(origem, sep=';', dtype=str, encoding='utf-8-sig')
        except FileNotFoundError:
            return pd.DataFrame(columns=CUSTOS_COLUNAS)
    c = origem.copy()
    c.columns = [unicodedata.normalize('NFKD', str(x)).encode('ascii', 'ignore').decode().strip().lower().replace(' ', '_')
                 for x in c.columns]
    for coluna in CUSTOS_COLUNAS:
        if coluna not in c.columns:
            c[coluna] = np.nan
    c['mes'] = c['mes'].map(_mes)
    c = c[c['mes'].notna()].drop_duplicates('mes', keep='last').sort_values('mes')
    for coluna in CUSTOS_COLUNAS[1:]:
        c[coluna] = c[coluna].map(_numero_br)
    for coluna in ('margem_usados', 'margem_lacrados'):
        c[coluna] = c[coluna].where(~(c[coluna] > 1), c[coluna] / 100)  # 45 vira 0,45
    return c[CUSTOS_COLUNAS].reset_index(drop=True)


# ----------------------------------------------------------------------------
# Tipo de disco e custo do disco
# ----------------------------------------------------------------------------
def tipo_do_disco(categorias: str | None) -> str:
    """"usado", "lacrado" (Novo/Lacrado) ou "outro", pelas categorias do produto na loja."""
    c = (categorias or '').lower()
    if 'usado' in c:
        return 'usado'
    if 'lacrado' in c or 'novo' in c:
        return 'lacrado'
    return 'outro'


def _normalizar(texto) -> str:
    return re.sub(r'\s+', ' ', str(texto).strip().lower())


def _id(serie: pd.Series) -> pd.Series:
    """IDs como texto ("123"), para casar itens e produtos sem problema de decimais."""
    return pd.to_numeric(serie, errors='coerce').astype('Int64').astype('string')


def _produto_de_cada_item(it: pd.DataFrame, produtos: pd.DataFrame) -> pd.DataFrame:
    """Categorias e custo cadastrado do produto de cada item.

    Casa pelo ID do produto, que vem da API. Só quando o item não tem ID (exportação em CSV) casa pelo
    nome. Item de produto que saiu da loja não é encontrado (`encontrado` falso).
    """
    saida = pd.DataFrame({'encontrado': False, 'categorias': pd.Series(None, index=it.index, dtype=object),
                          'custo_cadastrado': np.nan}, index=it.index)
    id_item = _id(it['produto_id']) if 'produto_id' in it.columns else pd.Series(pd.NA, index=it.index, dtype='string')
    com_id = id_item.notna()

    if 'id' in produtos.columns and com_id.any():
        p = produtos[produtos['id'].notna()].assign(chave=lambda d: _id(d['id'])).drop_duplicates('chave').set_index('chave')
        achou = id_item.isin(p.index) & com_id
        saida.loc[achou, 'encontrado'] = True
        saida.loc[achou, 'categorias'] = id_item[achou].map(p['categorias'])
        saida.loc[achou, 'custo_cadastrado'] = id_item[achou].map(p['custo']).astype(float)

    sem_id = ~com_id
    if sem_id.any():
        p = produtos.assign(chave=produtos['nome'].map(_normalizar)).drop_duplicates('chave').set_index('chave')
        nome = it.loc[sem_id, 'produto'].map(_normalizar)
        achou = nome.isin(p.index)
        saida.loc[nome.index[achou], 'encontrado'] = True
        saida.loc[nome.index[achou], 'categorias'] = nome[achou].map(p['categorias'])
        saida.loc[nome.index[achou], 'custo_cadastrado'] = nome[achou].map(p['custo']).astype(float)
    return saida


def itens_com_custo(tabelas: Tabelas, custos: pd.DataFrame) -> pd.DataFrame:
    """Itens de pedidos pagos com tipo do disco e custo do disco.

    Custo do disco = campo Custo do produto, se for maior que zero; senão preço × (1 − margem média do
    tipo no mês, da aba custos). Sem margem informada, o custo fica vazio (nunca zero).
    """
    it = tabelas.itens.loc[tabelas.itens['valido'].astype(bool)].copy()
    produto = _produto_de_cada_item(it, tabelas.produtos)
    it['encontrado'] = produto['encontrado']
    it['tipo'] = [tipo_do_disco(c) if isinstance(c, str) else 'outro' for c in produto['categorias']]
    it['mes'] = pd.to_datetime(it['data']).dt.strftime('%Y-%m')
    it['receita_item'] = it['valor'] * it['quantidade']

    margens = _por_mes(custos, ['margem_usados', 'margem_lacrados'], sorted(it['mes'].unique()), ffill=True)
    m_usado = it['mes'].map(margens['margem_usados'])
    m_lacrado = it['mes'].map(margens['margem_lacrados'])
    margem = np.where(it['tipo'] == 'lacrado', m_lacrado, m_usado)  # "outro" segue a margem de usados
    cadastrado = produto['custo_cadastrado']
    por_margem = it['receita_item'] * (1 - margem)
    it['custo_disco'] = np.where(cadastrado > 0, cadastrado * it['quantidade'], por_margem)
    return it

def _por_mes(custos: pd.DataFrame, colunas: list[str], meses, ffill: bool) -> pd.DataFrame:
    """Valores da aba custos para cada mês; com `ffill`, o valor informado vale também para os meses
    seguintes e anteriores até aparecer outro (margens e embalagem)."""
    base = pd.DataFrame(index=pd.Index(meses, name='mes'), columns=colunas, dtype=float)
    if len(custos):
        c = custos.set_index('mes')[colunas]
        todos = sorted(set(meses) | set(c.index))
        c = c.reindex(todos)
        if ffill:
            c = c.ffill().bfill()  # o valor informado vale para trás também, até alguém mudar
        base = c.reindex(meses)
    return base.astype(float)


# ----------------------------------------------------------------------------
# Série mensal
# ----------------------------------------------------------------------------
def pedidos_com_recompra(tabelas: Tabelas) -> pd.DataFrame:
    """Pedidos pagos, em ordem de data, com `ordem` (0 = primeira compra do cliente) e `recompra`."""
    v = pedidos_validos(tabelas).sort_values(['data', 'numero']).copy()
    v['ordem'] = v.groupby('email').cumcount()
    v['recompra'] = v['ordem'] > 0
    v['mes'] = v['data'].dt.strftime('%Y-%m')
    v['receita_produtos'] = v['subtotal'].fillna(0) - v['desconto'].fillna(0)  # sem frete, já com desconto
    return v


def tabela_mensal(tabelas: Tabelas, custos: pd.DataFrame, params: ParametrosIndicadores = PADRAO) -> pd.DataFrame:
    """Uma linha por mês com receita, recompra, novos clientes, custos e margem."""
    v = pedidos_com_recompra(tabelas)
    m = pd.DataFrame({
        'pedidos': v.groupby('mes').size(),
        'receita_total': v.groupby('mes')['total'].sum(),
        'receita_recompra': v[v['recompra']].groupby('mes')['receita_produtos'].sum(),
        'pedidos_recompra': v[v['recompra']].groupby('mes').size(),
        'clientes_novos': v[~v['recompra']].groupby('mes').size(),
        'subtotal': v.groupby('mes')['subtotal'].sum(),
        'desconto': v.groupby('mes')['desconto'].sum(),
    }).fillna(0.0)
    m.index.name = 'mes'
    m['receita_produtos'] = m['subtotal'] - m['desconto']
    m['participacao_recompra'] = m['receita_recompra'] / m['receita_produtos'] * 100
    m['desconto_pct'] = m['desconto'] / m['subtotal'] * 100

    # Custos da venda (AGENTS.md: 10% de marketing + taxas + frete pago pela loja + desconto + custo do disco)
    meses = list(m.index)
    c_mes = _por_mes(custos, ['investimento_meta', 'compras_meta', 'receita_meta', 'custo_brevo', 'receita_brevo', 'frete_pago_loja'], meses, ffill=False)
    c_fixo = _por_mes(custos, ['embalagem'], meses, ffill=True)
    m = m.join(c_mes)
    m['taxas_pagamento'] = m['receita_total'] * params.taxa_pagamento
    m['remuneracao_marketing'] = m['receita_produtos'] * params.remuneracao_marketing
    m['embalagem'] = c_fixo['embalagem'] * m['pedidos']
    itens = itens_com_custo(tabelas, custos)
    custo_disco = itens.groupby('mes')['custo_disco'].apply(lambda s: s.sum() if s.notna().all() else float('nan'))
    m['custo_disco'] = custo_disco.reindex(meses)
    m['frete_pago_loja'] = m['frete_pago_loja'].fillna(0.0)  # vazio conta como zero
    m['margem_bruta'] = (m['subtotal'] - m['desconto'] - m['taxas_pagamento'] - m['remuneracao_marketing']
                         - m['custo_disco'] - m['embalagem'].fillna(0) - m['frete_pago_loja'].fillna(0))
    m['margem_bruta_pct'] = m['margem_bruta'] / m['receita_produtos'] * 100

    inv = m['investimento_meta'].replace(0, np.nan)
    m['cpa_meta'] = m['investimento_meta'] / m['compras_meta'].replace(0, np.nan)
    m['roas_meta'] = m['receita_meta'] / inv
    m['roas_geral'] = m['receita_produtos'] / inv
    m['custo_por_cliente_novo'] = m['investimento_meta'] / m['clientes_novos'].replace(0, np.nan)
    m['custo_marketing'] = (m['investimento_meta'] + m['custo_brevo'].fillna(0) + m['remuneracao_marketing']
                            + m['desconto'] + m['frete_pago_loja'].fillna(0))
    m.loc[m['investimento_meta'].isna(), 'custo_marketing'] = np.nan
    m['custo_marketing_pct'] = m['custo_marketing'] / m['receita_produtos'] * 100
    m['descontos_e_fretes_pct'] = (m['desconto'] + m['frete_pago_loja'].fillna(0)) / m['receita_produtos'] * 100
    pendentes = m.index.isin(custos.attrs.get('fretes_pendentes', []))
    m.loc[pendentes, ['frete_pago_loja', 'margem_bruta', 'margem_bruta_pct', 'custo_marketing',
                     'custo_marketing_pct', 'descontos_e_fretes_pct']] = np.nan
    return m


# ----------------------------------------------------------------------------
# Coortes (clientes novos)
# ----------------------------------------------------------------------------
def coortes(tabelas: Tabelas, referencia: pd.Timestamp, params: ParametrosIndicadores = PADRAO) -> pd.DataFrame:
    """Uma linha por mês da primeira compra: quantos voltam em 90 dias e em 12 meses, e o LTV de 12 meses."""
    v = pedidos_com_recompra(tabelas)
    primeira = v[v['ordem'] == 0].set_index('email')['data'].rename('primeira')
    segunda = v[v['ordem'] == 1].set_index('email')['data'].rename('segunda')
    c = pd.concat([primeira, segunda], axis=1)
    v = v.join(primeira, on='email')
    dentro_de_12m = v[v['data'] < v['primeira'] + pd.Timedelta(days=365)]
    c['receita_12m'] = dentro_de_12m.groupby('email')['receita_produtos'].sum()
    c['volta_90d'] = (c['segunda'] - c['primeira']) <= pd.Timedelta(days=90)
    c['volta_12m'] = (c['segunda'] - c['primeira']) < pd.Timedelta(days=365)
    c['madura_90d'] = c['primeira'] + pd.Timedelta(days=90) <= referencia
    c['madura_12m'] = c['primeira'] + pd.Timedelta(days=365) <= referencia
    c['coorte'] = c['primeira'].dt.strftime('%Y-%m')

    def resumir(g: pd.DataFrame) -> pd.Series:
        m90, m12 = g[g['madura_90d']], g[g['madura_12m']]
        return pd.Series({
            'clientes': len(g),
            'voltam_90d_pct': m90['volta_90d'].mean() * 100 if len(m90) == len(g) and len(g) else np.nan,
            'voltam_12m_pct': m12['volta_12m'].mean() * 100 if len(m12) == len(g) and len(g) else np.nan,
            'ltv_12m': m12['receita_12m'].mean() if len(m12) == len(g) and len(g) else np.nan,
        })
    return c.groupby('coorte').apply(resumir, include_groups=False)


def _janela(c: pd.DataFrame, referencia: pd.Timestamp, de_dias: int, ate_dias: int) -> pd.DataFrame:
    """Clientes cuja primeira compra foi entre `ate_dias` e `de_dias` antes da data de referência."""
    return c[(c['primeira'] <= referencia - pd.Timedelta(days=ate_dias)) & (c['primeira'] > referencia - pd.Timedelta(days=de_dias))]


# ----------------------------------------------------------------------------
# Resumo: os indicadores de hoje
# ----------------------------------------------------------------------------
@dataclass
class Indicadores:
    referencia: pd.Timestamp
    resumo: pd.DataFrame
    mensal: pd.DataFrame
    coortes: pd.DataFrame
    qualidade: dict


def calcular(tabelas: Tabelas, custos: pd.DataFrame | str | None = None, referencia: pd.Timestamp | None = None,
             resultado_regua: pd.DataFrame | None = None, params: ParametrosIndicadores = PADRAO) -> Indicadores:
    custos = ler_custos(custos)
    v_todos = pedidos_com_recompra(tabelas)
    referencia = referencia if referencia is not None else v_todos['data'].max().normalize() + pd.Timedelta(days=1)
    v = v_todos[v_todos['data'] < referencia]
    mensal = tabela_mensal(tabelas, custos, params)

    inicio = referencia - pd.Timedelta(days=params.janela_dias)
    v12 = v[v['data'] >= inicio]
    rec12 = v12[v12['recompra']]
    meses_janela = params.janela_dias / 365 * 12
    linhas: list[dict] = []

    def add(grupo, indicador, valor, unidade, nota='', estado=OK):
        if estado == OK and not isinstance(valor, str) and pd.isna(valor):
            estado = FALTA_DADOS  # nunca mostrar número inventado
        linhas.append({'grupo': grupo, 'indicador': indicador, 'valor': valor, 'unidade': unidade, 'nota': nota, 'estado': estado})

    # --- Receita de quem volta
    clientes12 = v12['email'].nunique()
    taxa = len(rec12) / meses_janela / clientes12 * 100 if clientes12 else np.nan
    gasto = rec12['receita_produtos'].mean() if len(rec12) else np.nan
    add('Quem volta', 'Receita de quem volta por mês (média 12 meses)', rec12['receita_produtos'].sum() / meses_janela, 'R$',
        'produtos sem frete, já com desconto; meta do projeto: R$ 9 mil por mês')
    add('Quem volta', 'Clientes que compraram nos últimos 12 meses', clientes12, 'clientes', 'inclui quem não aceita marketing')
    add('Quem volta', 'Taxa de volta por mês', taxa, '%', 'recompras ÷ 12 ÷ clientes dos últimos 12 meses')
    add('Quem volta', 'Gasto por recompra', gasto, 'R$', 'média dos produtos de cada pedido de recompra (sem frete)')
    participacao = rec12['receita_produtos'].sum() / v12['receita_produtos'].sum() * 100 if len(v12) else np.nan
    add('Quem volta', 'Participação de quem volta na receita (12 meses)', participacao, '%',
        f'meta do projeto: {params.meta_participacao_recompra * 100:.0f}%')
    add('Quem volta', 'Receita da loja por mês (média 12 meses)', v12['receita_produtos'].sum() / meses_janela, 'R$',
        'produtos sem frete, já com desconto')

    # --- Clientes novos e LTV
    c = coortes(tabelas, referencia, params)
    primeiro = v[v['ordem'] == 0].set_index('email')['data'].rename('primeira')
    segunda = v[v['ordem'] == 1].set_index('email')['data'].rename('segunda')
    cl = pd.concat([primeiro, segunda], axis=1)
    cl['receita_12m'] = v[v['data'] < v['email'].map(primeiro) + pd.Timedelta(days=365)].groupby('email')['receita_produtos'].sum()
    novos90 = _janela(cl, referencia, 90 + params.janela_dias, 90)
    volta90 = ((novos90['segunda'] - novos90['primeira']) <= pd.Timedelta(days=90)).mean() * 100 if len(novos90) else np.nan
    add('Clientes novos', 'Clientes novos que voltam em 90 dias', volta90, '%',
        f'{len(novos90)} clientes novos de {(referencia - pd.Timedelta(days=90 + params.janela_dias)).strftime("%m/%Y")} a {(referencia - pd.Timedelta(days=90)).strftime("%m/%Y")}')
    maduros = _janela(cl, referencia, 365 + params.janela_dias, 365)
    volta12 = ((maduros['segunda'] - maduros['primeira']) < pd.Timedelta(days=365)).mean() * 100 if len(maduros) else np.nan
    add('Clientes novos', 'Clientes novos que voltam em 12 meses', volta12, '%', f'{len(maduros)} clientes das coortes de 12 a 24 meses atrás')
    ltv = maduros['receita_12m'].mean() if len(maduros) else np.nan
    add('Clientes novos', 'LTV de 12 meses (receita por cliente novo)', ltv, 'R$', 'média das coortes de 12 a 24 meses atrás')

    # --- Margem e descontos (últimos 12 meses fechados + mês atual)
    janela_meses = mensal[mensal.index >= inicio.strftime('%Y-%m')]
    receita_j = janela_meses['receita_produtos'].sum()
    descontos_e_fretes = janela_meses['desconto'].sum() + janela_meses['frete_pago_loja'].fillna(0).sum()
    frete_pendente = janela_meses['frete_pago_loja'].isna().any()
    add('Margem e custos', 'Descontos e fretes pagos ÷ receita',
        descontos_e_fretes / receita_j * 100 if receita_j and not frete_pendente else np.nan, '%',
        'frete pago pela loja: manual ou automático; consulta pendente exige conferência', FALTA_CUSTOS if frete_pendente else OK)
    if janela_meses['margem_bruta'].notna().all() and len(janela_meses):
        pct = janela_meses['margem_bruta'].sum() / janela_meses['receita_produtos'].sum() * 100
        add('Margem e custos', 'Margem bruta (12 meses)', pct, '%', 'sobre a receita de produtos')
    else:
        add('Margem e custos', 'Margem bruta (12 meses)', np.nan, '%', 'preencher margem_usados e margem_lacrados na aba custos', FALTA_CUSTOS)

    # --- Meta e custos do último mês preenchido
    preenchidos = mensal[mensal['investimento_meta'].notna()]
    if len(preenchidos):
        ult = preenchidos.iloc[-1]
        mes = preenchidos.index[-1]
        add('Meta e custo de aquisição', 'Mês de referência dos indicadores abaixo', mes, '', 'último mês com investimento_meta na aba custos')
        ltv_c = ltv
        add('Meta e custo de aquisição', 'CPA do Meta', ult['cpa_meta'], 'R$', f'investimento ÷ compras atribuídas ({mes})',
            OK if pd.notna(ult['cpa_meta']) else FALTA_CUSTOS)
        add('Meta e custo de aquisição', 'ROAS do Meta', ult['roas_meta'], 'x', f'receita atribuída ÷ investimento ({mes})',
            OK if pd.notna(ult['roas_meta']) else FALTA_CUSTOS)
        add('Meta e custo de aquisição', 'ROAS geral', ult['roas_geral'], 'x', f'receita de produtos ÷ mídia total ({mes})')
        add('Meta e custo de aquisição', 'Custo real por cliente novo', ult['custo_por_cliente_novo'], 'R$', f'investimento ÷ clientes novos ({mes})',
            OK if pd.notna(ult['custo_por_cliente_novo']) else FALTA_DADOS)
        razao = ltv_c / ult['custo_por_cliente_novo'] if pd.notna(ult['custo_por_cliente_novo']) and ult['custo_por_cliente_novo'] > 0 else np.nan
        add('Meta e custo de aquisição', 'LTV ÷ custo por cliente novo', razao, 'x', 'LTV de 12 meses das coortes maduras ÷ custo do mês',
            OK if pd.notna(razao) else FALTA_DADOS)
        add('Meta e custo de aquisição', 'Custo total de marketing ÷ receita', ult['custo_marketing_pct'], '%',
            f'Meta + Brevo + 10% de remuneração + descontos + frete pago ({mes}); teto {params.teto_custo_marketing * 100:.0f}%')
    else:
        for nome, un in [('CPA do Meta', 'R$'), ('ROAS do Meta', 'x'), ('ROAS geral', 'x'), ('Custo real por cliente novo', 'R$'),
                         ('LTV ÷ custo por cliente novo', 'x'), ('Custo total de marketing ÷ receita', '%')]:
            add('Meta e custo de aquisição', nome, np.nan, un, 'a aba custos ainda não tem investimento_meta', FALTA_CUSTOS)
    brevo_meses = mensal[mensal['receita_brevo'].notna()]
    if len(brevo_meses):
        add('Brevo', 'Vendas atribuídas aos envios (Brevo)', brevo_meses.iloc[-1]['receita_brevo'], 'R$', brevo_meses.index[-1])
    else:
        add('Brevo', 'Vendas atribuídas aos envios (Brevo)', np.nan, 'R$', 'falta receita_brevo manual ou automática', FALTA_CUSTOS)

    # --- Régua
    if resultado_regua is not None and len(resultado_regua):
        for _, r in resultado_regua.iterrows():
            nota = f'recebeu {int(r["recebeu"])}, controle {int(r["controle"])}; taxa {r["taxa"]:.1f}% contra {r["taxa_controle"]:.1f}%'
            if r['amostra_suficiente']:
                add('Régua', f'Incremento · {r["etapa"]}', r['incremento_pp'], 'pontos %', nota)
            else:
                add('Régua', f'Incremento · {r["etapa"]}', np.nan, 'pontos %', nota + ' (menos de 30 por grupo)', FALTA_DADOS)
    else:
        add('Régua', 'Incremento de cada etapa da régua', np.nan, 'pontos %',
            'aparece 30 dias depois do primeiro envio; precisa da lista enviada e do controle do mês', FALTA_DADOS)

    # --- Dependem de etapas futuras
    add('Brevo', 'Abertura, emails inválidos e descadastros', np.nan, '%', 'vem da API do Brevo (etapa 7)', FALTA_DADOS)
    add('Garimpo', 'Pedidos, avisos e vendas por aviso', np.nan, '', 'vem do garimpo (etapa 5.2)', FALTA_DADOS)
    add('Carrinhos', 'Carrinhos por dia, valor abandonado, contatados e recuperação', np.nan, '', 'vem do carrinho abandonado (etapa 5.1)', FALTA_DADOS)

    sem_tipo = itens_com_custo(tabelas, custos)
    qualidade = {
        'itens_pagos': len(sem_tipo),
        'itens_sem_produto_correspondente_pct': float((~sem_tipo['encontrado']).mean() * 100) if len(sem_tipo) else 0.0,
        'itens_usado_pct': float((sem_tipo['tipo'] == 'usado').mean() * 100) if len(sem_tipo) else 0.0,
        'itens_lacrado_pct': float((sem_tipo['tipo'] == 'lacrado').mean() * 100) if len(sem_tipo) else 0.0,
    }
    return Indicadores(referencia=referencia, resumo=pd.DataFrame(linhas), mensal=mensal, coortes=c, qualidade=qualidade)


def formatar(valor, unidade: str) -> str:
    """Texto para mostrar: R$ 6.981, 27,7%, 3,2x, 1.065."""
    if valor is None or (isinstance(valor, float) and np.isnan(valor)):
        return '—'
    if isinstance(valor, str):
        return valor

    def br(x: float, casas: int) -> str:
        return f'{x:,.{casas}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    if unidade == 'R$':
        return f'R$ {br(valor, 0 if abs(valor) >= 100 else 2)}'
    if unidade in ('%', 'pontos %'):
        return f'{br(valor, 1)}{"%" if unidade == "%" else " p.p."}'
    if unidade == 'x':
        return f'{br(valor, 2)}x'
    return br(valor, 0)
