"""Abas de resumo que o painel (página no claude.ai) lê (Etapa 6). Todas são do Painel e regravadas a cada rodada.

Cada aba tem uma linha por período ou ação e só números e textos simples, para o painel ser fácil de montar:
- `atual`: uma linha só com cada indicador numa coluna (para os cartões) e as metas.
- `mensal`: um mês por linha (receita, recompra, participação, custos, CPA, ROAS, margem). `mes_data` é o dia 1.
- `coortes`: clientes novos de cada mês e quantos voltam em 90 dias e em 12 meses.
- `regua_hoje`: quantos recebem e quantos ficam no controle em cada etapa, pela base de hoje.
- `regua_resultados`: resultado de cada etapa das rodadas já gravadas na aba `regua` (compra em 30 dias contra o controle).
- `carrinhos_dia`: carrinhos, valor abandonado, contatados e recuperados por dia.
- `vale_a_pena`: para cada ação, a receita a mais contra o custo (D-020). Só mostra números com pelo menos 30
  pessoas em cada grupo; antes disso o estado é "dados insuficientes".
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from painel_monstro.coletor.planilhas_csv import Tabelas
from painel_monstro.motor import regua as motor_regua
from painel_monstro.motor.indicadores import Indicadores
from painel_monstro.saidas import carrinhos_planilha as cp
from painel_monstro.saidas.planilha_google import Gravacao, PlanilhaGoogle

META_PARTICIPACAO = 35.0  # % da receita da loja online vinda de quem volta (AGENTS.md)
AMOSTRA_MINIMA = 30
REMUNERACAO_MARKETING = 0.10  # 10% de remuneração de marketing sobre a receita (AGENTS.md)
SUFICIENTE, INSUFICIENTE = 'ok', 'dados insuficientes'


ATUAL = {  # coluna da aba `atual` -> nome do indicador (cada um vira um número solto para os cartões do painel)
    'receita_quem_volta_mes': 'Receita de quem volta por mês (média 12 meses)',
    'clientes_12m': 'Clientes que compraram nos últimos 12 meses',
    'taxa_volta_mes_pct': 'Taxa de volta por mês',
    'gasto_recompra': 'Gasto por recompra',
    'participacao_pct': 'Participação de quem volta na receita (12 meses)',
    'receita_loja_mes': 'Receita da loja por mês (média 12 meses)',
    'volta_90d_pct': 'Clientes novos que voltam em 90 dias',
    'volta_12m_pct': 'Clientes novos que voltam em 12 meses',
    'ltv_12m': 'LTV de 12 meses (receita por cliente novo)',
    'descontos_fretes_pct': 'Descontos e fretes pagos ÷ receita',
    'margem_bruta_pct': 'Margem bruta (12 meses)',
    'cpa_meta': 'CPA do Meta',
    'roas_meta': 'ROAS do Meta',
    'roas_geral': 'ROAS geral',
    'custo_por_cliente_novo': 'Custo real por cliente novo',
    'ltv_sobre_custo': 'LTV ÷ custo por cliente novo',
    'custo_marketing_pct': 'Custo total de marketing ÷ receita',
    'vendas_brevo': 'Vendas atribuídas aos envios (Brevo)',
}
META_RECEITA_QUEM_VOLTA = 9000.0  # R$ por mês em 12 meses (AGENTS.md)
TETO_MARKETING_PCT = 15.0


def atual(ind: Indicadores) -> pd.DataFrame:
    """Uma linha só, com cada indicador numa coluna: os cartões do painel apontam direto para ela."""
    por_nome = ind.resumo.set_index('indicador')['valor']
    linha: dict[str, Any] = {'atualizado_em': pd.Timestamp.now(tz='America/Sao_Paulo').strftime('%Y-%m-%d %H:%M')}
    for coluna, nome in ATUAL.items():
        v = por_nome.get(nome, np.nan)
        linha[coluna] = float(v) if not isinstance(v, str) and pd.notna(v) else np.nan
    linha.update({'meta_participacao_pct': META_PARTICIPACAO, 'meta_receita_quem_volta': META_RECEITA_QUEM_VOLTA,
                  'teto_marketing_pct': TETO_MARKETING_PCT})
    return pd.DataFrame([linha])


def mensal(ind: Indicadores) -> pd.DataFrame:
    m = ind.mensal.reset_index()
    m.insert(1, 'mes_data', pd.to_datetime(m['mes'] + '-01').dt.strftime('%Y-%m-%d'))
    m['meta_participacao'] = META_PARTICIPACAO
    return m


def coortes(ind: Indicadores) -> pd.DataFrame:
    c = ind.coortes.reset_index()
    primeira = c.columns[0]
    c[primeira] = c[primeira].astype(str)
    return c


def regua_hoje(classificacao: pd.DataFrame, referencia: pd.Timestamp,
               params: motor_regua.ParametrosRegua = motor_regua.PADRAO) -> pd.DataFrame:
    r = motor_regua.resumo(classificacao, params)
    r.insert(0, 'data_referencia', referencia.strftime('%Y-%m-%d'))
    return r


def _classificacao_do_historico(hist: pd.DataFrame) -> pd.DataFrame:
    return hist.set_index('email')[['etapa', 'grupo']]


def regua_resultados(historico: pd.DataFrame, tabelas: Tabelas, hoje: pd.Timestamp,
                     params: motor_regua.ParametrosRegua = motor_regua.PADRAO) -> pd.DataFrame:
    """Resultado por etapa de cada rodada gravada. `dias` < 30 quer dizer que a janela ainda está aberta."""
    colunas = ['mes', 'etapa', 'recebeu', 'voltou', 'taxa', 'controle', 'voltou_controle', 'taxa_controle', 'incremento_pp',
              'receita', 'gasto_medio', 'dias', 'amostra_suficiente', 'estado']
    if historico is None or len(historico) == 0:
        return pd.DataFrame(columns=colunas)
    linhas = []
    historico = historico[historico['mes'].astype(str).str.fullmatch(r'\d{4}-\d{2}')]  # `teste45` tem resultado próprio
    if historico.empty:
        return pd.DataFrame(columns=colunas)
    for mes, h in historico.groupby('mes'):
        ref = pd.Timestamp(h['data_referencia'].iloc[0])
        r = motor_regua.resultado_etapas(_classificacao_do_historico(h), tabelas, ref, params)
        r.insert(0, 'mes', mes)
        r['dias'] = int(min((hoje.normalize() - ref).days, 30))
        r['gasto_medio'] = np.where(r['voltou'] > 0, r['receita'] / r['voltou'].replace(0, np.nan), np.nan)
        r['estado'] = np.where(r['dias'] < 30, 'janela aberta', np.where(r['amostra_suficiente'], SUFICIENTE, INSUFICIENTE))
        linhas.append(r)
    return pd.concat(linhas, ignore_index=True)[colunas]


def carrinhos_dia(fila: dict[str, cp.LinhaExistente]) -> pd.DataFrame:
    """Um dia por linha, pelo dia do abandono (horário de Brasília), a partir de tudo que a aba Fila já viu."""
    colunas = ['dia', 'carrinhos', 'valor_abandonado', 'contatados', 'recuperados', 'receita_recuperada', 'taxa_recuperacao']
    registros = []
    for e in fila.values():
        t = cp.para_momento(e.valores.get('Abandonado em'))
        if t is None:
            continue
        v = e.valores
        registros.append({'dia': t.strftime('%Y-%m-%d'), 'valor': cp.numero(v.get('Valor (R$)')), 'contatado': e.toques > 0,
                          'recuperado': str(v.get('Recuperado')) == 'Sim', 'receita': cp.numero(v.get('Receita recuperada (R$)'))})
    if not registros:
        return pd.DataFrame(columns=colunas)
    d = pd.DataFrame(registros)
    g = d.groupby('dia').agg(carrinhos=('valor', 'size'), valor_abandonado=('valor', 'sum'), contatados=('contatado', 'sum'),
                             recuperados=('recuperado', 'sum'), receita_recuperada=('receita', 'sum')).reset_index()
    g['taxa_recuperacao'] = np.where(g['carrinhos'] > 0, g['recuperados'] / g['carrinhos'] * 100, np.nan)
    return g.sort_values('dia')[colunas]


def _linha(acao: str, recebeu: int, voltou: int, controle: int, voltou_c: int, gasto: float, nota: str) -> dict[str, Any]:
    taxa = voltou / recebeu * 100 if recebeu else np.nan
    taxa_c = voltou_c / controle * 100 if controle else np.nan
    suficiente = recebeu >= AMOSTRA_MINIMA and controle >= AMOSTRA_MINIMA
    base = {'acao': acao, 'recebeu': recebeu, 'controle': controle, 'taxa': taxa, 'taxa_controle': taxa_c,
            'gasto_medio': gasto, 'estado': SUFICIENTE if suficiente else INSUFICIENTE, 'nota': nota}
    if suficiente and not np.isnan(gasto):
        a_mais = (taxa - taxa_c) / 100 * recebeu * gasto
        custo = max(a_mais, 0) * REMUNERACAO_MARKETING
        base.update({'receita_a_mais': round(a_mais, 2), 'custo': round(custo, 2), 'resultado': round(a_mais - custo, 2)})
    else:
        base.update({'receita_a_mais': np.nan, 'custo': np.nan, 'resultado': np.nan})
    return base


def teste45_resultado(historico: pd.DataFrame, tabelas: Tabelas, hoje: pd.Timestamp) -> dict[str, Any] | None:
    """Teste do WhatsApp de 45 dias: só email (comparação) contra email e WhatsApp, só de quem já fechou 30 dias."""
    if historico is None or len(historico) == 0:
        return None
    h = historico[historico['mes'].astype(str) == 'teste45']
    if len(h) == 0:
        return None
    v = motor_regua.pedidos_validos(tabelas)
    compras = {e: sorted(zip(g['data'], g['total'])) for e, g in v.groupby('email')}
    contagem = {'email': [0, 0, 0.0], 'whatsapp': [0, 0, 0.0]}  # pessoas, voltaram, receita
    for r in h.itertuples():
        if r.grupo not in contagem:
            continue
        inicio = pd.Timestamp(r.data_referencia)
        fim = inicio + pd.Timedelta(days=30)
        if fim > hoje:
            continue  # janela de 30 dias ainda aberta
        achados = [t for d, t in compras.get(str(r.email).lower(), []) if inicio <= d < fim]
        contagem[r.grupo][0] += 1
        if achados:
            contagem[r.grupo][1] += 1
            contagem[r.grupo][2] += float(sum(achados))
    voltou = contagem['whatsapp'][1] + contagem['email'][1]
    gasto = (contagem['whatsapp'][2] + contagem['email'][2]) / voltou if voltou else float('nan')
    return {'recebeu': contagem['whatsapp'][0], 'voltou': contagem['whatsapp'][1], 'controle': contagem['email'][0],
            'voltou_controle': contagem['email'][1], 'gasto': gasto}


def vale_a_pena(resultados: pd.DataFrame, fila: dict[str, cp.LinhaExistente], teste45: dict[str, Any] | None = None,
                atribuida: dict[str, Any] | None = None) -> pd.DataFrame:
    """Receita a mais = (taxa de quem recebeu − taxa do grupo de comparação) × pessoas × gasto médio; menos o custo.

    O custo aqui é a remuneração de marketing de 10% sobre a receita a mais. Os cupons já estão descontados da receita
    (receita de produtos depois do desconto), mas o custo de frete grátis pago pela loja ainda não entra.
    """
    colunas = ['acao', 'recebeu', 'controle', 'taxa', 'taxa_controle', 'gasto_medio', 'receita_a_mais', 'custo', 'resultado', 'estado', 'nota',
               'pedidos', 'receita_atribuida']  # as duas últimas (D-064) só têm valor na linha "Indicações e contatos manuais"
    linhas: list[dict] = []
    if len(resultados):
        ultimo = resultados[resultados['dias'] >= 30]
        if len(ultimo):
            ultimo = ultimo[ultimo['mes'] == ultimo['mes'].max()]
            for r in ultimo.itertuples():
                linhas.append(_linha(f'Régua · {r.etapa}', int(r.recebeu), int(r.voltou), int(r.controle), int(r.voltou_controle),
                                     float(r.gasto_medio) if not pd.isna(r.gasto_medio) else np.nan, f'rodada {r.mes}'))
    else:
        linhas.append({'acao': 'Régua mensal', 'recebeu': 0, 'controle': 0, 'taxa': np.nan, 'taxa_controle': np.nan, 'gasto_medio': np.nan,
                       'receita_a_mais': np.nan, 'custo': np.nan, 'resultado': np.nan, 'estado': INSUFICIENTE,
                       'nota': 'aparece 30 dias depois da primeira rodada gravada na aba regua'})
    if teste45 and (teste45['recebeu'] or teste45['controle']):
        linhas.append(_linha('WhatsApp de 45 dias', teste45['recebeu'], teste45['voltou'], teste45['controle'], teste45['voltou_controle'],
                             teste45['gasto'], 'email e WhatsApp contra só email; teste de 12/10/2026 a 18/01/2027'))
    else:
        linhas.append({'acao': 'WhatsApp de 45 dias', 'recebeu': 0, 'controle': 0, 'taxa': np.nan, 'taxa_controle': np.nan,
                       'gasto_medio': np.nan, 'receita_a_mais': np.nan, 'custo': np.nan, 'resultado': np.nan,
                       'estado': INSUFICIENTE, 'nota': 'teste de 12/10/2026 a 18/01/2027 (etapa 5.2)'})

    contatados = [e for e in fila.values() if e.toques > 0]
    comparacao = [e for e in fila.values() if str(e.valores.get('Grupo')) == 'Comparação']
    rec = lambda es: [e for e in es if str(e.valores.get('Recuperado')) == 'Sim']
    receita_media = [cp.numero(e.valores.get('Receita recuperada (R$)')) for e in rec(contatados) + rec(comparacao)]
    gasto = float(np.mean(receita_media)) if receita_media else np.nan
    linhas.append(_linha('Carrinho · WhatsApp', len(contatados), len(rec(contatados)), len(comparacao), len(rec(comparacao)), gasto,
                         'contra o grupo que só recebe o email da Nuvemshop'))
    if atribuida is not None:
        linhas.append(atribuida)
    return pd.DataFrame(linhas).reindex(columns=colunas)


def montar_resumo_email(abas: dict[str, pd.DataFrame], indicadores: pd.DataFrame, semana: list[list]) -> pd.DataFrame:
    """Aba `resumo_email`: assunto e HTML do resumo de segunda (o Apps Script só envia)."""
    from painel_monstro.saidas import resumo_email as re_
    atual_row = abas['atual'].iloc[0].to_dict() if len(abas.get('atual', [])) else {}
    agora = pd.Timestamp.now(tz='America/Sao_Paulo')
    assunto, html = re_.montar(atual_row, semana, abas['vale_a_pena'].to_dict('records') if 'vale_a_pena' in abas else [],
                               indicadores.to_dict('records'), agora.strftime('%d/%m/%Y %H:%M'), agora.to_pydatetime())
    return pd.DataFrame([{'assunto': assunto, 'html': html, 'gerado_em': agora.strftime('%Y-%m-%d %H:%M')}])


def linha_atribuida(planilha: PlanilhaGoogle, tabelas: Tabelas, fila: dict[str, cp.LinhaExistente], hoje: pd.Timestamp) -> dict[str, Any]:
    """Linha "Indicações e contatos manuais" (D-064). Aba ou parâmetro ausentes valem como vazio."""
    from painel_monstro.saidas import atribuicoes, regua_planilha
    try:
        valores = cp._valores(planilha._ss.worksheet(atribuicoes.ABA))
    except Exception:  # noqa: BLE001 - aba ainda não existe
        valores = []
    try:
        prefixo = regua_planilha._config_por_nome(planilha).get(atribuicoes.CHAVE_PREFIXO, '')
    except Exception:  # noqa: BLE001
        prefixo = ''
    do_carrinho = atribuicoes.pedidos_da_fila(fila or {}, tabelas.pedidos, cp._pedidos_do_cliente(tabelas)[1], cp.c.so_digitos)
    return atribuicoes.linha_vale_a_pena(atribuicoes.ler(valores), tabelas.pedidos, do_carrinho, prefixo, hoje)


def montar_resumos(planilha: PlanilhaGoogle, tabelas: Tabelas, ind: Indicadores, classificacao: pd.DataFrame,
                   hoje: pd.Timestamp | None = None, params_regua: motor_regua.ParametrosRegua = motor_regua.PADRAO,
                   fila: dict[str, cp.LinhaExistente] | None = None) -> list[tuple[str, pd.DataFrame]]:
    """Calcula as abas de resumo (só lê da planilha; não grava). `fila`: estado final da aba Fila desta rodada."""
    hoje = hoje if hoje is not None else pd.Timestamp.now(tz='America/Sao_Paulo').tz_localize(None)
    try:
        historico = planilha._ler_historico(planilha._ss.worksheet('regua'), motor_regua_colunas())
    except Exception:  # aba ainda não existe: nenhuma rodada gravada
        historico = pd.DataFrame()
    resultados = regua_resultados(historico, tabelas, hoje, params_regua)
    teste = teste45_resultado(historico, tabelas, hoje)
    if fila is None:
        try:
            fila = cp.ler_fila(planilha._ss.worksheet(cp.ABA_FILA))
        except Exception:
            fila = {}
    atribuida = linha_atribuida(planilha, tabelas, fila, hoje)
    return [
        ('atual', atual(ind)),
        ('mensal', mensal(ind)),
        ('coortes', coortes(ind)),
        ('regua_hoje', regua_hoje(classificacao, ind.referencia, params_regua)),
        ('regua_resultados', resultados),
        ('carrinhos_dia', carrinhos_dia(fila)),
        ('vale_a_pena', vale_a_pena(resultados, fila, teste, atribuida)),
    ]


def gravar_resumos(planilha: PlanilhaGoogle, tabelas: Tabelas, ind: Indicadores, classificacao: pd.DataFrame,
                   hoje: pd.Timestamp | None = None,
                   params_regua: motor_regua.ParametrosRegua = motor_regua.PADRAO) -> list[Gravacao]:
    """Calcula e grava as abas de resumo."""
    return [planilha.substituir(nome, df) for nome, df in montar_resumos(planilha, tabelas, ind, classificacao, hoje, params_regua)]


def motor_regua_colunas() -> list[str]:
    from painel_monstro.saidas.planilha_google import REGUA_COLUNAS
    return REGUA_COLUNAS
