"""Custos automáticos em aba própria. Nunca escreve na aba manual `custos`.

Atualiza o mês anterior diariamente; conserva meses anteriores no cache privado.
Manual informado tem precedência. Falhas não geram zero nem interrompem a rotina.
"""
from __future__ import annotations

import json
import math
import os
import re

import pandas as pd
import requests

from painel_monstro.coletor import nuvemshop_api as na
from painel_monstro.saidas.brevo import Brevo

COLUNAS = ['mes', 'fonte', 'campo', 'valor', 'estado', 'atualizado_em', 'observacao']


def limites(mes):
    inicio = pd.Timestamp(mes + '-01', tz=na.FUSO_LOJA)
    fim = inicio + pd.offsets.MonthBegin(1) - pd.Timedelta(seconds=1)
    return inicio, fim


def numero(valor):
    n = float(valor)
    if not math.isfinite(n) or n < 0:
        raise ValueError('Valor ausente ou inválido.')
    return n


def frete_do_mes(api, pedidos, registros):
    """Frete grátis em pedidos válidos. Retirada não é despesa de entrega.

O dono confirmou que nos demais pedidos o cliente cobre o frete inteiro.
"""
    total = 0.0
    for p in pedidos.itertuples():
        cobrado = numero(p.frete)
        if cobrado > 0:
            continue
        original = registros.get(str(p.numero))
        if not original:
            raise ValueError('Pedido sem detalhe no cache; falta conferir o frete.')
        entregas = api._get(api._base + '/orders/' + str(original['id']) + '/fulfillment-orders').json()
        if not isinstance(entregas, list) or not entregas:
            raise ValueError('Entrega sem custo disponível.')
        for entrega in entregas:
            s = entrega.get('shipping') or {}
            if s.get('type') == 'pickup':
                continue
            if s.get('type') != 'ship':
                raise ValueError('Tipo de entrega não reconhecido.')
            merchant = s.get('merchant_cost') or {}
            consumer = s.get('consumer_cost') or {}
            if merchant.get('currency') != 'BRL' or consumer.get('currency') != 'BRL':
                raise ValueError('Frete sem moeda BRL confirmada.')
            custo = numero(merchant.get('value'))
            cliente = numero(consumer.get('value'))
            if custo == 0:
                raise ValueError('Entrega gratuita com custo zero: conferir custo da etiqueta.')
            total += max(custo - cliente, 0)
    return round(total, 2)


def meta_do_mes(config, mes, sessao=None):
    """GET Insights no nível da conta, atribuição configurada na conta, por data de conversão."""
    conta = config.meta_ads_account_id.removeprefix('act_')
    if not conta.isdigit() or not re.fullmatch(r'v\d+\.\d+', config.meta_ads_api_version):
        raise ValueError('Configuração Meta inválida.')
    inicio, fim = limites(mes)
    s = sessao or requests.Session()
    try:
        r = s.get(f'https://graph.facebook.com/{config.meta_ads_api_version}/act_{conta}/insights',
                  headers={'Authorization': 'Bearer ' + config.meta_ads_token}, timeout=40,
                  params={'fields': 'spend,actions,action_values,account_currency', 'level': 'account',
                          'time_range': json.dumps({'since': inicio.strftime('%Y-%m-%d'), 'until': fim.strftime('%Y-%m-%d')}),
                          'use_account_attribution_setting': 'true', 'action_report_time': 'conversion'})
        if r.status_code != 200:
            raise ValueError('Meta indisponível ou sem permissão de leitura.')
        d = r.json()
    except requests.RequestException:
        raise ValueError('Falha de rede ao consultar Meta.') from None
    linhas = d.get('data')
    if not isinstance(linhas, list) or len(linhas) != 1 or d.get('paging', {}).get('next'):
        raise ValueError('Meta sem relatório único completo; conferir conta e período.')
    l = linhas[0]
    if l.get('account_currency') != 'BRL':
        raise ValueError('A conta Meta precisa estar em BRL.')
    def compra(campo):
        a = {x['action_type']: x['value'] for x in l.get(campo, [])}
        # Usa somente compras do site; não soma purchase e omni_purchase sobrepostos.
        return numero(a.get('offsite_conversion.fb_pixel_purchase', 0))
    return {'investimento_meta': numero(l['spend']), 'compras_meta': compra('actions'),
            'receita_meta': compra('action_values')}


def combinar(manual, automaticos):
    c = manual.copy().set_index('mes')
    for linha in automaticos.to_dict('records'):
        if linha['estado'] != 'ok' or pd.isna(linha['valor']):
            continue
        mes, campo = linha['mes'], linha['campo']
        if mes not in c.index:
            c.loc[mes] = float('nan')
        if pd.isna(c.at[mes, campo]):
            c.at[mes, campo] = linha['valor']
    resultado = c.sort_index().reset_index()
    resultado.attrs['fretes_pendentes'] = [l['mes'] for l in automaticos.to_dict('records')
        if l['campo'] == 'frete_pago_loja' and l['estado'] != 'ok'
        and (l['mes'] not in c.index or pd.isna(c.at[l['mes'], 'frete_pago_loja']))]
    return resultado


def preparar(config, manual, tabelas, pasta_api, api=None, agora=None, cliente_brevo=None):
    agora = agora or pd.Timestamp.now(tz=na.FUSO_LOJA)
    meses = [(agora - pd.DateOffset(months=1)).strftime('%Y-%m')]
    caminho = os.path.join(pasta_api, 'custos_automaticos.json')
    try:
        with open(caminho, encoding='utf-8') as f:
            linhas = json.load(f)
    except (FileNotFoundError, ValueError):
        linhas = []
    fontes = []
    if config.brevo_api_key:
        cliente = cliente_brevo or Brevo(config.brevo_api_key, modo_teste=True, max_tentativas=1)
        fontes.append(('Brevo', ['receita_brevo'], lambda m: {'receita_brevo': cliente.receita_periodo(*(x.isoformat() for x in limites(m)))}))
    if config.meta_ads_token and config.meta_ads_account_id:
        fontes.append(('Meta', ['investimento_meta', 'compras_meta', 'receita_meta'], lambda m: meta_do_mes(config, m)))
    else:
        def sem_meta(m):
            raise ValueError('Falta configurar acesso ao Meta.')
        fontes.append(('Meta', ['investimento_meta', 'compras_meta', 'receita_meta'], sem_meta))
    if api is not None:
        registros = {str(p['number']): p for p in na.Armazem(pasta_api).registros('pedidos').values()}
        def consultar_frete(m):
            p = tabelas.pedidos
            p = p[p['valido'] & (pd.to_datetime(p['data']).dt.strftime('%Y-%m') == m)]
            return {'frete_pago_loja': frete_do_mes(api, p, registros)}
        fontes.append(('Nuvemshop', ['frete_pago_loja'], consultar_frete))
    if not fontes:
        return manual, []
    for mes in meses:
        for fonte, campos, consultar in fontes:
            anteriores = [l for l in linhas if l['mes'] == mes and l['fonte'] == fonte]
            if anteriores and all(l['estado'] == 'ok' and l['atualizado_em'][:10] == agora.strftime('%Y-%m-%d') for l in anteriores):
                continue
            try:
                valores = consultar(mes)
                estado, nota = 'ok', 'Leitura automática; valor manual, se informado, tem prioridade.'
            except Exception:
                valores = {}
                estado = 'pendente'
                nota = ('Falta leitura de fulfillment orders ou custo da entrega; preencher manualmente.' if fonte == 'Nuvemshop'
                        else 'Consulta indisponível ou resposta incompleta; preencher manualmente.')
                if fonte == 'Meta' and not (config.meta_ads_token and config.meta_ads_account_id):
                    nota = 'Configurar META_ADS_ACCOUNT_ID e META_ADS_TOKEN com ads_read.'
            linhas = [l for l in linhas if not (l['mes'] == mes and l['fonte'] == fonte)]
            for campo in campos:
                linhas.append(dict(mes=mes, fonte=fonte, campo=campo, valor=valores.get(campo), estado=estado,
                                   atualizado_em=agora.isoformat(), observacao=nota))
    os.makedirs(pasta_api, exist_ok=True)
    with open(caminho + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(linhas, f, ensure_ascii=False)
    os.replace(caminho + '.tmp', caminho)
    df = pd.DataFrame(linhas, columns=COLUNAS).sort_values(['mes', 'fonte', 'campo']).reset_index(drop=True)
    return combinar(manual, df), [('custos_automaticos', df)]
