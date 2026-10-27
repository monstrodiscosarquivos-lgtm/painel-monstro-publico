"""Etapa 9: relatórios agregados de anúncios, exclusivamente GET com ads_read.

Não lê públicos, contatos ou pedidos individuais do Meta. Abas publicadas só depois
de toda a coleta terminar; falha mantém dados anteriores e atualiza apenas o aviso.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections import Counter
from datetime import date, timedelta
import hashlib
import json
import math
from pathlib import Path
import re
import time

import gspread
import pandas as pd
import requests

from painel_monstro.saidas.carrinhos import eh_disco

INICIO = date(2025, 7, 1)
FUSO = 'America/Sao_Paulo'
HORA = 'hourly_stats_aggregated_by_advertiser_time_zone'
COMPRA = 'offsite_conversion.fb_pixel_purchase'
CARRINHO = 'offsite_conversion.fb_pixel_add_to_cart'
FINALIZACAO = 'offsite_conversion.fb_pixel_initiate_checkout'
ATRIBUICAO = {'use_account_attribution_setting': 'true', 'action_report_time': 'conversion'}
COLUNAS = {
    'anuncios_campanha_dia': 'data campanha_id campanha tipo status orcamento_dia investido investido_real impressoes alcance frequencia cliques_link ctr_link cpm carrinhos finalizacoes compras receita roas_real cpa_real'.split(),
    'anuncios_hoje': 'data hora campanha_id campanha tipo investido cliques_link carrinhos finalizacoes compras receita'.split(),
    'anuncios_anuncios': 'anuncio_id anuncio campanha_id campanha conjunto tipo status thumb investido_7d compras_7d receita_7d ctr_7d ctr_campanha_7d frequencia_7d investido_30d compras_30d receita_30d cansado motivo'.split(),
    'anuncios_semana': 'semana_inicio escopo investido investido_real variacao_investimento_pct mudou_verba compras receita roas_real cpa_real compras_por_100 cliques_link conversao_clique_pct carrinhos finalizacoes discos_criados discos_voltaram discos_entraram pedidos_site receita_site leitura'.split(),
    'anuncios_alertas': 'nivel campanha anuncio regra detalhe desde'.split(),
    'anuncios_resumo': ['chave', 'valor'],
    'anuncios_notas': 'campanha_id tipo data_evento nota registrado_em'.split(),
    'anuncios_direcao': ['data', 'prioridade', 'texto'],
}
CONFIG = [
    ('fator de imposto', 1.1383, 'Multiplicador do investimento para custo real, incluindo imposto.'),
    ('ROAS de equilíbrio', 2.85, 'ROAS real da conta abaixo deste valor gera alerta vermelho.'),
    ('ROAS verde a partir de', 9, 'Referência visual para o painel e a direção do Cowork.'),
    ('ROAS amarelo a partir de', 6, 'Referência visual para o painel e a direção do Cowork.'),
    ('teto do custo por venda (R$)', 37, 'Teto de CPA real nos últimos 7 dias.'),
    ('frequência máxima', 3, 'Frequência de 7 dias acima deste valor em prospecção indica cansaço.'),
    ('queda de CTR para anúncio cansado (%)', 40, 'Queda relativa ao CTR da campanha, com mais de R$30 gastos.'),
    ('entrega mínima do orçamento (%)', 70, 'Gasto de ontem comparado ao orçamento diário atual.'),
    ('dias de gasto sem venda', 3, 'Dias consecutivos de gasto positivo sem compra em vendas.'),
    ('mudança de verba que marca a semana (%)', 30, 'Variação absoluta semanal que marca mudou_verba.'),
]


def numero(v, padrao=0.0):
    try:
        n = float(str(v).replace(',', '.'))
        return n if math.isfinite(n) and n >= 0 else padrao
    except (TypeError, ValueError):
        return padrao


def razao(a, b):
    return a / b if b else None


@dataclass(frozen=True)
class Parametros:
    fator: float = 1.1383
    equilibrio: float = 2.85
    verde: float = 9
    amarelo: float = 6
    teto_cpa: float = 37
    frequencia: float = 3
    queda_ctr: float = 40
    entrega: float = 70
    dias_sem_venda: int = 3
    mudanca_verba: float = 30

    @classmethod
    def ler(cls, linhas):
        valores = {r[0]: r[1] for r in linhas if len(r) > 1}
        ns = [numero(valores.get('Anúncios: ' + nome), valor) for nome, valor, _ in CONFIG]
        if ns[0] <= 0:
            ns[0] = CONFIG[0][1]
        ns[8] = max(1, int(ns[8]))
        return cls(*ns)


def tipo(nome, manual=''):
    if manual in ('evento', 'remarketing', 'sazonal', 'vendas'):
        return manual
    n = str(nome).lower()
    if any(x in n for x in ('_local', '[evento]', 'alcance')):
        return 'evento'
    if 'rmk' in n or 'remarketing' in n:
        return 'remarketing'
    if any(x in n for x in ('black', 'natal', 'sazonal')):
        return 'sazonal'
    return 'vendas'


class ErroAnuncios(Exception):
    """Mensagem segura: nunca propaga resposta, URL ou exceção de rede do Meta."""


class MetaLeitura:
    def __init__(self, config, sessao=None):
        conta = config.meta_ads_account_id.removeprefix('act_')
        if not conta.isdigit() or not config.meta_ads_token or not re.fullmatch(r'v\d+\.\d+', config.meta_ads_api_version):
            raise ErroAnuncios('Configurar acesso de leitura ao Meta nos Secrets.')
        self.base = f'https://graph.facebook.com/{config.meta_ads_api_version}/act_{conta}'
        self.headers = {'Authorization': 'Bearer ' + config.meta_ads_token}
        self.sessao = sessao or requests.Session()
        self.inicio = time.monotonic()

    def _get(self, recurso, params):
        if time.monotonic() - self.inicio > 420:
            raise ErroAnuncios('Tempo da coleta atingido; histórico retoma na próxima execução.')
        try:
            r = self.sessao.get(self.base + recurso, params=params, headers=self.headers,
                                timeout=30, allow_redirects=False)
            uso = json.loads(r.headers.get('x-business-use-case-usage', '{}'))
            taxas = [numero(v) for itens in uso.values() for item in itens
                     for k, v in item.items() if k in ('call_count', 'total_cputime', 'total_time')]
            if max(taxas, default=0) > 75:
                raise ErroAnuncios('Uso da API Meta acima de 75%; coleta interrompida, tentar na próxima rodada.')
            if r.status_code != 200:
                raise ErroAnuncios('Meta indisponível ou sem permissão ads_read; dados anteriores mantidos.')
            d = r.json()
            if not isinstance(d, dict) or 'error' in d:
                raise ValueError()
            return d
        except ErroAnuncios:
            raise
        except Exception:
            raise ErroAnuncios('Falha de rede ou resposta inválida do Meta; dados anteriores mantidos.') from None

    def lista(self, recurso, **params):
        params = {'limit': 500, **params}
        linhas, vistos = [], set()
        while True:
            d = self._get(recurso, params)
            if not isinstance(d.get('data'), list):
                raise ErroAnuncios('Relatório Meta incompleto; dados anteriores mantidos.')
            linhas.extend(d['data'])
            paging = d.get('paging') or {}
            if not paging.get('next'):
                return linhas
            after = (paging.get('cursors') or {}).get('after')
            if not after or after in vistos:
                raise ErroAnuncios('Paginação Meta incompleta; dados anteriores mantidos.')
            vistos.add(after)
            # Não segue a URL next: pode conter token ou apontar a outro host.
            params = {**params, 'after': after}

    def insights(self, inicio, fim, nivel='campaign', horario=False, diario=True):
        fields = ['date_start', 'campaign_id', 'campaign_name', 'spend', 'inline_link_clicks',
                  'actions', 'action_values', 'account_currency', 'impressions']
        if not horario:
            fields += ['reach', 'frequency', 'cpm', 'inline_link_click_ctr']
        if nivel == 'ad':
            fields += ['ad_id', 'ad_name', 'adset_name']
        p = dict(fields=','.join(fields), level=nivel,
                 time_range=json.dumps({'since': str(inicio), 'until': str(fim)}), **ATRIBUICAO)
        if diario:
            p['time_increment'] = 1
        if horario:
            p['breakdowns'] = HORA
        linhas = self.lista('/insights', **p)
        if any(l.get('account_currency') != 'BRL' for l in linhas):
            raise ErroAnuncios('Relatório Meta fora de BRL; dados anteriores mantidos.')
        return [normalizar(l) for l in linhas]


def normalizar(l):
    """Lista explícita de métricas e identificação de publicidade; descarta extras."""
    def acao(campo, chave):
        return numero(next((a.get('value') for a in l.get(campo, []) if a.get('action_type') == chave), 0))
    return dict(data=str(l['date_start']), campanha_id=str(l['campaign_id']), campanha=l.get('campaign_name', ''),
                anuncio_id=str(l.get('ad_id', '')), anuncio=l.get('ad_name', ''), conjunto=l.get('adset_name', ''),
                hora=l.get(HORA, ''), investido=numero(l.get('spend')), impressoes=numero(l.get('impressions')),
                alcance=numero(l.get('reach')), frequencia=numero(l.get('frequency')),
                cliques_link=numero(l.get('inline_link_clicks')), ctr_link=numero(l.get('inline_link_click_ctr')),
                cpm=numero(l.get('cpm')), carrinhos=acao('actions', CARRINHO), finalizacoes=acao('actions', FINALIZACAO),
                compras=acao('actions', COMPRA), receita=acao('action_values', COMPRA))


def salvar(caminho, d):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix('.tmp')
    temporario.write_text(json.dumps(d, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    # Antivírus no Windows pode segurar brevemente o arquivo; não perder uma rodada por isso.
    for espera in (.05, .1, .2, .4, None):
        try:
            temporario.replace(caminho)
            break
        except PermissionError:
            if espera is None: raise
            time.sleep(espera)


def mesclar(anteriores, novas, inicio, fim):
    """Substitui inclusive dias/linhas que deixaram de aparecer por reatribuição."""
    ficam = [l for l in anteriores if not str(inicio) <= l['data'] <= str(fim)]
    por_chave = {(l['data'], l['campanha_id']): l for l in ficam + novas}
    return [por_chave[k] for k in sorted(por_chave)]


def historico(cliente, pasta, hoje, identidade, completo=False):
    caminho = Path(pasta) / 'anuncios_historico.json'
    try:
        cache = json.loads(caminho.read_text(encoding='utf-8'))
    except (FileNotFoundError, ValueError):
        cache = {}
    if cache.get('identidade') != identidade:
        cache = {}
    # Um backfill interrompido retoma dos meses completos, sem publicar histórico parcial.
    trabalho = cache.get('reconstrucao') if completo else None
    if trabalho is None:
        trabalho = {'meses': [], 'linhas': []} if completo else cache
    linhas, meses = trabalho.get('linhas', []), trabalho.get('meses', [])
    cursor = INICIO
    while cursor <= hoje:
        proximo = (pd.Timestamp(cursor) + pd.offsets.MonthBegin(1)).date()
        fim = min(proximo - timedelta(days=1), hoje)
        chave = cursor.strftime('%Y-%m')
        if chave not in meses:
            novas = cliente.insights(cursor, fim)
            linhas = mesclar(linhas, novas, cursor, fim)
            meses = [*meses, chave]
            trabalho = {'meses': meses, 'linhas': linhas}
            if completo:
                cache['reconstrucao'] = trabalho
            else:
                cache.update(trabalho)
            cache['identidade'] = identidade
            if not completo:
                cache['atualizado_ate'] = str(fim)
            salvar(caminho, cache)
        cursor = proximo
    inicio = max(INICIO, hoje - timedelta(days=6))
    # Se o cache ficou sem rodar mais de sete dias, inclui também a lacuna.
    ultimo = cache.get('atualizado_ate') if not completo else None
    if ultimo:
        inicio = min(inicio, date.fromisoformat(ultimo) + timedelta(days=1))
    linhas = mesclar(linhas, cliente.insights(inicio, hoje), inicio, hoje)
    salvar(caminho, {'identidade': identidade, 'meses': meses, 'linhas': linhas, 'atualizado_ate': str(hoje)})
    return linhas


SOMAS = 'investido impressoes cliques_link carrinhos finalizacoes compras receita'.split()


def somar(linhas):
    return {k: sum(numero(l.get(k)) for l in linhas) for k in SOMAS}


def metricas(linha, p):
    r = dict(linha)
    r['investido_real'] = r['investido'] * p.fator
    r['roas_real'] = razao(r['receita'], r['investido_real'])
    r['cpa_real'] = razao(r['investido_real'], r['compras'])
    return r


def leitura(compras, roas, anteriores):
    if len(anteriores) < 4 or roas is None or any(l['roas_real'] is None for l in anteriores[-4:]):
        return ''
    media_compras = sum(l['compras'] for l in anteriores[-4:]) / 4
    media_roas = sum(l['roas_real'] for l in anteriores[-4:]) / 4
    if compras == media_compras or roas == media_roas:
        return ''  # empate não é acima nem abaixo; não inventa direção
    return { (True, True): 'semana boa', (True, False): 'escalando',
             (False, True): 'travado', (False, False): 'problema'}[(compras > media_compras, roas > media_roas)]


def dia_local(v):
    t = pd.to_datetime(v, errors='coerce')
    if pd.isna(t):
        return None
    if t.tzinfo is not None:
        t = t.tz_convert(FUSO)
    return t.date()


def semanas(diario, produtos, pedidos, hoje, p):
    saida = []
    discos = [r for r in produtos.to_dict('records') if eh_disco(r.get('nome'))]
    validos = [r for r in pedidos.to_dict('records') if r.get('valido') in (True, 1, 'True', 'TRUE')]
    criacoes, retornos, pedidos_dia, receitas_dia = Counter(), Counter(), Counter(), Counter()
    for x in discos:
        criado, voltou = dia_local(x.get('criado_em')), dia_local(x.get('no_estoque_desde'))
        if criado:
            criacoes[criado] += 1
        if voltou and voltou >= date(2026, 10, 14) and criado and voltou > criado:
            retornos[voltou] += 1
    for x in validos:
        d = dia_local(x.get('data'))
        if d:
            pedidos_dia[d] += 1
            receitas_dia[d] += numero(x.get('subtotal')) - numero(x.get('desconto'))
    for escopo in ('conta', 'vendas'):
        anteriores = []
        inicio = date(2025, 7, 7)
        while inicio <= hoje:
            fim = inicio + timedelta(days=6)
            grupo = [r for r in diario if str(inicio) <= r['data'] <= str(fim)
                     and (escopo == 'conta' or r['tipo'] == 'vendas')]
            r = metricas(somar(grupo), p)
            anterior = anteriores[-1]['investido'] if anteriores else 0
            var = (r['investido'] / anterior - 1) * 100 if anterior else None
            dias = [inicio + timedelta(days=i) for i in range(7)]
            criados = sum(criacoes[d] for d in dias)
            # Não contar criação como retorno; histórico de retorno não existia antes de 14/10.
            voltaram = sum(retornos[d] for d in dias) if fim >= date(2026, 10, 14) else None
            r.update(semana_inicio=str(inicio), escopo=escopo, variacao_investimento_pct=var,
                     mudou_verba='sim' if var is not None and abs(var) >= p.mudanca_verba else 'não',
                     compras_por_100=razao(r['compras'] * 100, r['investido_real']),
                     conversao_clique_pct=razao(r['compras'] * 100, r['cliques_link']),
                     discos_criados=criados, discos_voltaram=voltaram,
                     discos_entraram=criados + voltaram if voltaram is not None else None,
                     pedidos_site=sum(pedidos_dia[d] for d in dias), receita_site=sum(receitas_dia[d] for d in dias),
                     leitura=leitura(r['compras'], r['roas_real'], anteriores))
            saida.append(r)
            anteriores.append(r)
            inicio += timedelta(days=7)
    return saida


def orcamento(campanha, conjuntos):
    if numero(campanha.get('daily_budget')):
        return numero(campanha['daily_budget']) / 100
    # Orçamento vitalício não é uma promessa de gasto diário. Não inventar divisão.
    valores = [numero(s.get('daily_budget')) / 100 for s in conjuntos
               if str(s.get('campaign_id')) == str(campanha['id']) and s.get('effective_status') == 'ACTIVE']
    return sum(valores) or None


def montar(diario, horas, anuncios_dia, anuncios_7d, estrutura, conjuntos, anuncios, notas, tabelas, hoje, p):
    por_id = {str(c['id']): c for c in estrutura}
    nts = {str(l.get('campanha_id')): l for l in notas}
    def classificar(cid, nome):
        return tipo(nome, nts.get(cid, {}).get('tipo', ''))
    diarios = []
    for l in diario:
        s = por_id.get(l['campanha_id'], {})
        diarios.append(metricas({**l, 'tipo': classificar(l['campanha_id'], l['campanha']),
                                'status': s.get('effective_status', ''),
                                'orcamento_dia': orcamento(s, conjuntos) if s else None}, p))
    hora_linhas = [{**l, 'tipo': classificar(l['campanha_id'], l['campanha'])} for l in horas]
    corte = str(hoje - timedelta(days=6))
    semana = [r for r in diarios if corte <= r['data'] <= str(hoje)]
    por_campanha = {cid: somar([r for r in semana if r['campanha_id'] == cid])
                    for cid in {r['campanha_id'] for r in semana}}
    catalogo = {str(a['id']): a for a in anuncios}
    por_ad7 = {r['anuncio_id']: r for r in anuncios_7d}
    ids = {r['anuncio_id'] for r in anuncios_dia if r['investido'] > 0} | {k for k, a in catalogo.items() if a.get('effective_status') == 'ACTIVE'}
    ad_linhas = []
    for aid in sorted(ids):
        ad = catalogo.get(aid, {})
        dias = [r for r in anuncios_dia if r['anuncio_id'] == aid]
        base = dias[-1] if dias else {}
        cid = str(ad.get('campaign_id') or base.get('campanha_id', ''))
        camp = por_id.get(cid, {})
        nome_camp = camp.get('name') or base.get('campanha', '')
        tipo_camp = classificar(cid, nome_camp)
        sete = por_ad7.get(aid, somar([]))
        trinta = somar(dias)
        ctr = razao(sete['cliques_link'] * 100, sete['impressoes'])
        camp7 = por_campanha.get(cid, somar([]))
        ctr_camp = razao(camp7['cliques_link'] * 100, camp7['impressoes'])
        freq = sete.get('frequencia')
        motivos = []
        if tipo_camp == 'vendas' and freq is not None and freq > p.frequencia:
            motivos.append('frequência acima do limite')
        if sete['investido'] > 30 and ctr is not None and ctr_camp and ctr < ctr_camp * (1 - p.queda_ctr / 100):
            motivos.append('CTR abaixo da campanha')
        thumb = (ad.get('creative') or {}).get('thumbnail_url', '')
        ad_linhas.append(dict(anuncio_id=aid, anuncio=ad.get('name') or base.get('anuncio', ''), campanha_id=cid,
                              campanha=nome_camp, conjunto=(ad.get('adset') or {}).get('name') or base.get('conjunto', ''),
                              tipo=tipo_camp, status=ad.get('effective_status', ''),
                              thumb=thumb if str(thumb).startswith('https://') else '',
                              investido_7d=sete['investido'], compras_7d=sete['compras'], receita_7d=sete['receita'],
                              ctr_7d=ctr, ctr_campanha_7d=ctr_camp, frequencia_7d=freq,
                              investido_30d=trinta['investido'], compras_30d=trinta['compras'], receita_30d=trinta['receita'],
                              cansado='sim' if motivos else 'não', motivo='; '.join(motivos)))
    alertas = alertar(diarios, ad_linhas, estrutura, nts, hoje, p, horas=horas, conjuntos=conjuntos)
    return {'anuncios_campanha_dia': diarios, 'anuncios_hoje': hora_linhas, 'anuncios_anuncios': ad_linhas,
            'anuncios_semana': semanas(diarios, tabelas.produtos, tabelas.pedidos, hoje, p),
            'anuncios_alertas': alertas}


def alertar(diario, anuncios, estrutura, notas, hoje, p, horas=(), conjuntos=()):
    alertas = []
    ontem = hoje - timedelta(days=1)
    sete = [r for r in diario if str(hoje - timedelta(days=6)) <= r['data'] <= str(hoje)]
    def add(nivel, campanha, regra, detalhe, desde, anuncio=''):
        alertas.append(dict(nivel=nivel, campanha=campanha, anuncio=anuncio, regra=regra, detalhe=detalhe, desde=str(desde)))
    for cid in sorted({r['campanha_id'] for r in diario} | {str(s['id']) for s in estrutura}):
        grupo = sorted([r for r in diario if r['campanha_id'] == cid], key=lambda r: r['data'])
        s = next((x for x in estrutura if str(x['id']) == cid), {})
        atual = grupo[-1] if grupo else dict(campanha=s.get('name', ''),
                    tipo=tipo(s.get('name', ''), notas.get(cid, {}).get('tipo', '')),
                    orcamento_dia=orcamento(s, conjuntos) if s else None)
        nome = atual['campanha']
        ontem_linhas = [r for r in grupo if r['data'] == str(ontem)]
        gasto_ontem = sum(r['investido'] for r in ontem_linhas)
        inicio = dia_local(s.get('start_time'))
        fim = dia_local(s.get('stop_time'))
        budget = atual.get('orcamento_dia')
        if s.get('effective_status') == 'ACTIVE' and inicio is not None and inicio <= ontem and (fim is None or fim >= ontem) and budget and gasto_ontem < budget * p.entrega / 100:
            add('amarelo', nome, 'Entrega cortada', 'Gasto de ontem abaixo do mínimo do orçamento diário atual.', ontem)
        # Só dias completos; um dia sem gasto interrompe a sequência.
        sem_venda = True
        for n in range(1, p.dias_sem_venda + 1):
            ds = somar([r for r in grupo if r['data'] == str(hoje - timedelta(days=n))])
            sem_venda &= ds['investido'] > 0 and ds['compras'] == 0
        if atual['tipo'] == 'vendas' and sem_venda:
            add('vermelho', nome, 'Gasto sem venda', f'{p.dias_sem_venda} dias completos consecutivos com gasto e sem compra.', hoje - timedelta(days=p.dias_sem_venda))
        g7 = metricas(somar([r for r in sete if r['campanha_id'] == cid]), p)
        if g7['cpa_real'] is not None and g7['cpa_real'] > p.teto_cpa:
            add('amarelo', nome, 'Custo por venda acima do teto', 'CPA real dos últimos 7 dias acima do teto configurado.', hoje)
        evento = dia_local(notas.get(cid, {}).get('data_evento')) or fim
        gasto_depois = bool(evento and evento < hoje and any(r['data'] == str(hoje) and r['investido'] > 0 for r in grupo))
        stop = pd.to_datetime(s.get('stop_time'), errors='coerce')
        if not pd.isna(stop) and not notas.get(cid, {}).get('data_evento'):
            stop = stop.tz_localize(FUSO) if stop.tzinfo is None else stop.tz_convert(FUSO)
            for h in horas:
                hora = re.match(r'^(\d{2}):', str(h.get('hora', '')))
                if h['campanha_id'] == cid and h['data'] == str(hoje) and h['investido'] > 0 and hora:
                    inicio_hora = pd.Timestamp(h['data'], tz=FUSO) + pd.Timedelta(hours=int(hora[1]))
                    gasto_depois |= inicio_hora >= stop
        if atual['tipo'] == 'evento' and gasto_depois:
            add('vermelho', nome, 'Evento já passou', 'Evento encerrado com gasto hoje.', hoje)
        if atual['tipo'] == 'remarketing' and g7['carrinhos'] >= 10 and g7['finalizacoes'] < g7['carrinhos'] * .15:
            add('amarelo', nome, 'Catálogo suspeito', '10 ou mais carrinhos e menos de 15% de finalizações em 7 dias.', hoje)
    for a in anuncios:
        if a['cansado'] == 'sim':
            add('amarelo', a['campanha'], 'Anúncio cansado', a['motivo'], hoje, a['anuncio'])
    conta = metricas(somar(sete), p)
    if conta['roas_real'] is not None and conta['roas_real'] < p.equilibrio:
        add('vermelho', '', 'ROAS abaixo do equilíbrio', 'ROAS real da conta nos últimos 7 dias abaixo do equilíbrio.', hoje)
    return alertas


def ler(planilha, nome):
    try:
        return planilha._ss.worksheet(nome).get_all_values()
    except gspread.exceptions.WorksheetNotFound:
        return []


def preparar_abas(planilha):
    for nome in ('anuncios_notas', 'anuncios_direcao'):
        if not ler(planilha, nome):
            planilha.garantir_cabecalho(nome, COLUNAS[nome], {})
    linhas = ler(planilha, 'Configuração')
    existentes = {r[0] for r in linhas if r}
    novas = [['Anúncios: ' + nome, valor, ajuda] for nome, valor, ajuda in CONFIG if 'Anúncios: ' + nome not in existentes]
    if novas:
        aba, _ = planilha._aba('Configuração', len(linhas) + len(novas) + 1, 3)
        if not linhas:
            linhas = [['Parâmetro', 'Valor', 'Ajuda']]
        # Escreve somente linhas novas no fim, nunca os valores editados pelo Túlio.
        if aba.row_count < len(linhas) + len(novas):
            aba.resize(rows=len(linhas) + len(novas))
        if not existentes:
            aba.update(linhas, 'A1', raw=True)
        aba.update(novas, f'A{len(linhas) + 1}', raw=True)


def resumo(agora, diario, estado='ok', aviso=''):
    return pd.DataFrame([['atualizado_em', agora.strftime('%Y-%m-%d %H:%M')],
                         ['dias_no_historico', len({r['data'] for r in diario})],
                         ['ultima_data', max((r['data'] for r in diario), default='')],
                         ['estado', estado], ['aviso', aviso]], columns=COLUNAS['anuncios_resumo'])


def passo_anuncios(config, planilha, tabelas, pasta_api, agora=None, sessao=None, completo=False):
    """Falha de coleta não publica nenhuma tabela de métricas nem dados parciais."""
    agora = pd.Timestamp(agora) if agora is not None else pd.Timestamp.now(tz=FUSO)
    hoje = agora.tz_convert(FUSO).date() if agora.tzinfo else agora.date()
    try:
        preparar_abas(planilha)
        p = Parametros.ler(ler(planilha, 'Configuração'))
        cliente = MetaLeitura(config, sessao)
        conta = cliente._get('', {'fields': 'currency,timezone_name'})
        if conta.get('currency') != 'BRL':
            raise ErroAnuncios('A conta Meta precisa estar em BRL; dados anteriores mantidos.')
        if conta.get('timezone_name') != FUSO:
            raise ErroAnuncios('Fuso da conta Meta diferente de Brasília; conferir antes de comparar dias e horas.')
        identidade = hashlib.sha256((cliente.base + '|conversion|account|v1').encode()).hexdigest()
        diario = historico(cliente, pasta_api, hoje, identidade, completo)
        estrutura = cliente.lista('/campaigns', fields='id,name,effective_status,daily_budget,lifetime_budget,start_time,stop_time')
        conjuntos = cliente.lista('/adsets', fields='id,name,campaign_id,effective_status,daily_budget,lifetime_budget,start_time,end_time')
        catalogo = cliente.lista('/ads', fields='id,name,campaign_id,effective_status,adset{name},creative{thumbnail_url}')
        ads = cliente.insights(hoje - timedelta(days=29), hoje, 'ad')
        # Alcance/frequência não são somáveis entre dias: relatório agregado próprio de 7 dias.
        ads7 = cliente.insights(hoje - timedelta(days=6), hoje, 'ad', diario=False)
        horas = cliente.insights(hoje - timedelta(days=2), hoje, horario=True)
        nt = ler(planilha, 'anuncios_notas')
        notas = [dict(zip(nt[0], r)) for r in nt[1:]] if nt else []
        dados = montar(diario, horas, ads, ads7, estrutura, conjuntos, catalogo, notas, tabelas, hoje, p)
        antigos = ler(planilha, 'anuncios_alertas')
        alertas_antes = [dict(zip(antigos[0], r)) for r in antigos[1:]] if antigos else []
        por_alerta = {(r.get('campanha'), r.get('anuncio'), r.get('regra')): r.get('desde') for r in alertas_antes}
        for r in dados['anuncios_alertas']:
            r['desde'] = por_alerta.get((r['campanha'], r['anuncio'], r['regra'])) or r['desde']
        paginas = [(nome, pd.DataFrame(linhas, columns=COLUNAS[nome])) for nome, linhas in dados.items()]
        paginas.append(('anuncios_resumo', resumo(agora, diario)))
        return paginas
    except Exception as erro:
        aviso = str(erro) if isinstance(erro, ErroAnuncios) else 'Coleta de anúncios indisponível; dados anteriores mantidos.'
        print('      Anúncios: coleta indisponível; dados anteriores mantidos.')
        # Mantém data da última atualização boa, quantidade e data dos dados anteriores.
        try:
            antigas = ler(planilha, 'anuncios_resumo')
            antes = {r[0]: r[1] for r in antigas[1:] if len(r) > 1}
        except Exception:
            antes = {}
        linhas = [[k, antes.get(k, '')] for k in ('atualizado_em', 'dias_no_historico', 'ultima_data')]
        linhas += [['estado', 'aviso'], ['aviso', aviso]]
        return [('anuncios_resumo', pd.DataFrame(linhas, columns=COLUNAS['anuncios_resumo']))]
