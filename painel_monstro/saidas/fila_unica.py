"""Fila única de WhatsApp (AGENTS.md, "Fila única de WhatsApp e medição"; D-014 a D-022).

Junta numa lista só as origens que viram mensagem de WhatsApp para a Mariana:
  Carrinho (cliente puxou o assunto), Garimpo (aviso de que chegou o disco pedido), VIP aos 75 dias e
  Garimpo aos 45 dias ("45 dias", dentro do teste de 12/10/2026 a 18/01/2027).

Regras:
- Prioridade e limite diário vêm da aba `Configuração` (padrão: Carrinho, Garimpo, VIP, 45 dias; 40 por dia).
  O que passar do limite fica para o dia seguinte, começando pela menor prioridade.
- 1 WhatsApp a cada 30 dias por pessoa. Carrinho e aviso de garimpo passam por cima dessa trava (o cliente
  puxou o assunto), mas contam: quem recebeu um deles não recebe o VIP nem o de 45 dias nos 30 dias seguintes.
- Quem não aceita marketing ou está na aba `Bloqueio` fica de fora de todas as origens.
- Teste de 45 dias: quem completa 45 dias de última compra dentro do período é sorteado uma única vez
  (10% nada, 30% só email, 60% email e WhatsApp); o grupo fica na aba `regua`.
- Sugestão (G45 e VIP): um disco em estoque da família de gênero do cliente, conferido na API na hora.
- Nada é enviado por aqui: a Mariana envia à mão.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd

from painel_monstro.log_publico import comando_seguro, ArgumentParserSeguro, resumo_erro
from painel_monstro.coletor.planilhas_csv import Tabelas
from painel_monstro.motor import generos
from painel_monstro.motor import regua as motor_regua
from painel_monstro.motor.indicadores import _produto_de_cada_item
from painel_monstro.saidas import carrinhos as c
from painel_monstro.saidas import garimpo
from painel_monstro.saidas.regua_planilha import FilaUnica, Teste45

FUSO = 'America/Sao_Paulo'
ORIGEM_CARRINHO, ORIGEM_GARIMPO, ORIGEM_VIP, ORIGEM_45 = 'Carrinho', 'Garimpo', 'VIP', '45 dias'
ORIGENS_QUE_PASSAM_POR_CIMA = (ORIGEM_CARRINHO, ORIGEM_GARIMPO)
TENTATIVAS_DE_SUGESTAO = 5


# ----------------------------------------------------------------------------
# Sorteio e identificadores (sem dado pessoal nos códigos)
# ----------------------------------------------------------------------------
def _pct(texto: str) -> float:
    return int(hashlib.sha256(texto.encode('utf-8')).hexdigest(), 16) % 10_000 / 100


def codigo(*partes: Any) -> str:
    return hashlib.sha1('|'.join(str(p) for p in partes).encode('utf-8')).hexdigest()[:8]


def sorteio_45(email: str, teste: Teste45) -> str:
    """"controle", "email" ou "whatsapp". Reproduzível: o mesmo email cai sempre no mesmo grupo."""
    x = _pct(f'teste45:{email.strip().lower()}')
    if x < teste.controle_pct:
        return 'controle'
    if x < teste.controle_pct + teste.email_pct:
        return 'email'
    return 'whatsapp'


# ----------------------------------------------------------------------------
# Sugestão de disco
# ----------------------------------------------------------------------------
def disponiveis(produtos: pd.DataFrame) -> pd.DataFrame:
    """Produtos à venda agora (exibidos e com estoque) com as famílias de gênero de cada um."""
    if produtos is None or len(produtos) == 0:
        return pd.DataFrame(columns=['id', 'nome', 'url', 'familias', 'criado_em'])
    p = produtos
    estoque = pd.to_numeric(p['estoque'], errors='coerce').fillna(0)
    ilimitado = p['estoque_ilimitado'].fillna(False).astype(bool) if 'estoque_ilimitado' in p.columns else False
    ok = p['exibir'].fillna(False).astype(bool) & ((estoque > 0) | ilimitado) & p['url'].notna() & p['id'].notna()
    ok &= p['nome'].map(c.eh_disco)  # camiseta, combo e outros itens da loja nunca viram sugestão
    d = p.loc[ok, ['id', 'nome', 'url', 'categorias']].copy()
    d['criado_em'] = pd.to_datetime(p.loc[ok, 'criado_em'], errors='coerce', utc=True) if 'criado_em' in p.columns else pd.NaT
    d['no_estoque_desde'] = p.loc[ok, 'no_estoque_desde'].fillna('').astype(str) if 'no_estoque_desde' in p.columns else ''
    d['familias'] = [generos.familias(cat, nome) for cat, nome in zip(d['categorias'], d['nome'])]
    return d


def escolher_sugestoes(pool: pd.DataFrame, familia: str | None, ja_comprados: set[str], email: str, quantas: int = 1,
                       api: Any = None, site: str = 'https://lojamonstro.com.br') -> list[dict]:
    """Um disco em estoque da família do cliente, entre os mais recentes e que ele ainda não comprou.

    Dentro dos mais recentes a escolha é fixa por cliente (espalha o mesmo disco entre pessoas diferentes).
    Se `api` for dado, o estoque é conferido na API; sem estoque, tenta o seguinte.
    """
    if len(pool) == 0:
        return []
    ids = pool['id'].astype('Int64').astype(str)
    candidatos = pool[~ids.isin(ja_comprados)]
    if familia:
        do_genero = candidatos[[familia in f for f in candidatos['familias']]]
        candidatos = do_genero if len(do_genero) else candidatos
    else:  # família desconhecida: só discos que a loja sabe classificar (nada de trilha sonora ou item sem gênero)
        com_genero = candidatos[[len(f) > 0 for f in candidatos['familias']]]
        candidatos = com_genero if len(com_genero) else candidatos
    if len(candidatos) == 0:
        return []
    candidatos = candidatos.sort_values('criado_em', ascending=False, na_position='last').head(TENTATIVAS_DE_SUGESTAO * 2 + quantas)
    inicio = int(_pct(f'sugestao:{email}') * 100) % len(candidatos)
    ordem = list(range(inicio, len(candidatos))) + list(range(0, inicio))
    achados: list[dict] = []
    for k in ordem:
        r = candidatos.iloc[k]
        if api is not None:
            tem, _ = c.estoque_do_produto(api, int(r['id']))
            if not tem:
                continue
        achados.append({'id': str(int(r['id'])), 'nome': c.nome_do_disco(str(r['nome'])), 'link': f'{site}/produtos/{r["url"]}/'})
        if len(achados) >= quantas:
            break
    return achados


def escolher_sugestao(pool: pd.DataFrame, familia: str | None, ja_comprados: set[str], email: str, api: Any = None,
                      site: str = 'https://lojamonstro.com.br') -> dict | None:
    """Uma sugestão só (ou None). Ver `escolher_sugestoes`."""
    achadas = escolher_sugestoes(pool, familia, ja_comprados, email, 1, api, site)
    return achadas[0] if achadas else None


def _dados_do_cliente(tabelas: Tabelas, emails: list[str]) -> dict[str, dict]:
    """Último disco, discos já comprados e família de gênero de cada cliente."""
    it = tabelas.itens
    it = it[it['valido'].astype(bool) & it['email'].isin(emails)].copy()
    if len(it) == 0:
        return {}
    produto = _produto_de_cada_item(it, tabelas.produtos)
    it['categorias'] = produto['categorias']
    it['momento'] = pd.to_datetime(it['data'])
    saida: dict[str, dict] = {}
    for email, g in it.groupby('email'):
        g = g.sort_values(['momento', 'valor'], ascending=[False, False])
        fams = [generos.familias(cat, nome) for cat, nome in zip(g['categorias'], g['produto'])]
        comprados = {str(int(x)) for x in pd.to_numeric(g['produto_id'], errors='coerce').dropna()} if 'produto_id' in g.columns else set()
        saida[str(email)] = {'ultimo_disco': c.nome_do_disco(str(g['produto'].iloc[0])), 'familia': generos.familia_principal(fams),
                             'comprados': comprados}
    return saida


# ----------------------------------------------------------------------------
# Geração das origens
# ----------------------------------------------------------------------------
@dataclass
class Geracao:
    linhas: list[c.LinhaDaFila] = field(default_factory=list)
    sorteios_novos: list[dict] = field(default_factory=list)
    resumo: dict = field(default_factory=dict)


def _momento_do_gatilho(dia: pd.Timestamp) -> pd.Timestamp:
    """O dia do gatilho às 8h, horário de Brasília, em UTC (a coluna "Abandonado em" da Fila)."""
    return pd.Timestamp(dia).normalize().tz_localize(FUSO) .tz_convert('UTC') + pd.Timedelta(hours=8)


def gerar(tabelas: Tabelas, params: c.Parametros, regua: motor_regua.ParametrosRegua, teste: Teste45, hoje: date,
          agora: pd.Timestamp, api: Any = None, ja_na_fila: dict[str, dict] | None = None, sorteios: dict[str, str] | None = None,
          bloqueio: set[str] | None = None, desejos: pd.DataFrame | None = None, ignorar_inicio_do_teste: bool = False,
          contatos_vip: set[str] | None = None) -> Geracao:
    """Candidatos de VIP, 45 dias e aviso de garimpo para `hoje`. Não grava nada."""
    ja_na_fila = ja_na_fila or {}
    sorteios = dict(sorteios or {})
    bloqueio = {b.lower() if '@' in b else c.so_digitos(b) for b in (bloqueio or set()) if b}
    ger = Geracao()
    if teste.fila_inicio and hoje < teste.fila_inicio:
        ger.resumo = {'antes do início da fila única': 1}
        return ger  # até lá a fila só tem carrinhos
    referencia = pd.Timestamp(hoje) + pd.Timedelta(days=1)
    base = motor_regua.base_clientes(tabelas, referencia, regua)
    base = base.assign(ultima_dia=base['ultima'].dt.normalize())
    resumo = {'45 dias sorteados': 0, '45 dias controle': 0, '45 dias só email': 0, '45 dias com WhatsApp': 0, 'VIP': 0,
              'sem telefone válido': 0, 'sem sugestão em estoque': 0, 'bloqueados': 0, 'garimpo': 0}

    candidatos: list[tuple[str, str, pd.Series, pd.Timestamp, str]] = []  # (origem, id, cliente, gatilho, grupo)
    dentro_do_teste = (not teste.fim) or hoje <= teste.fim
    for email, r in base.iterrows():
        dias = int(r['dias'])
        gatilho45 = r['ultima_dia'] + pd.Timedelta(days=45)
        if dentro_do_teste and 45 <= dias <= 74:
            # Só entra no teste quem completa 45 dias a partir do início. Na simulação (antes do início), vale quem completa hoje.
            elegivel = gatilho45.date() >= teste.inicio or (ignorar_inicio_do_teste and gatilho45.date() == hoje)
            if elegivel:
                grupo = sorteios.get(email)
                if grupo is None:
                    grupo = sorteio_45(email, teste)
                    sorteios[email] = grupo
                    ger.sorteios_novos.append({'email': email, 'grupo': grupo, 'dia': hoje, 'dias': dias, 'n': int(r['n']),
                                               'total': float(r['total']), 'vip': bool(r['vip'])})
                    resumo['45 dias sorteados'] += 1
                    resumo[{'controle': '45 dias controle', 'email': '45 dias só email', 'whatsapp': '45 dias com WhatsApp'}[grupo]] += 1
                if grupo == 'whatsapp' and dias <= 45 + teste.dias_para_contatar:
                    candidatos.append((ORIGEM_45, f'G45-{codigo(email, r["ultima_dia"].date())}', r.rename(email), gatilho45,
                                       'Teste 45 dias · email e WhatsApp'))
        vip_ok = bool(r['vip']) and regua.vip.dias_min <= dias <= regua.vip.dias_max
        if vip_ok and email.lower() in (contatos_vip or set()):
            vip_ok = False  # já recebeu o WhatsApp de VIP à mão neste ciclo
        if vip_ok:
            gatilho = r['ultima_dia'] + pd.Timedelta(days=regua.vip.dias_min)
            candidatos.append((ORIGEM_VIP, f'VIP-{codigo(email, r["ultima_dia"].date())}', r.rename(email), gatilho, 'VIP'))

    pool = disponiveis(tabelas.produtos)
    dados = _dados_do_cliente(tabelas, [str(r[2].name) for r in candidatos])
    for origem, id_, r, gatilho, grupo in candidatos:
        email = str(r.name)
        previo = ja_na_fila.get(id_, {})
        if int(previo.get('toques') or 0) > 0 or previo.get('status') in ('Não quer', 'Recuperado', 'Contato inválido', 'Respondeu'):
            continue  # já foi contatado (ou não quer): a linha só fica como histórico
        fone = c.telefone_whatsapp(r.get('telefone'))
        if email in bloqueio or (fone and fone in bloqueio):
            resumo['bloqueados'] += 1
            continue
        d = dados.get(email, {})
        quantas = 3 if origem == ORIGEM_VIP else 1
        sugs = escolher_sugestoes(pool, d.get('familia'), d.get('comprados', set()), email, quantas, api, params.site)
        sug = sugs[0] if sugs else None
        if sug is None:
            resumo['sem sugestão em estoque'] += 1
        modelo = 'G45' if origem == ORIGEM_45 else 'VIP'
        primeiro = str(r.get('primeiro_nome') or '').strip().title()
        dados_msg = {'nome': primeiro or 'tudo bem', 'itens': d.get('ultimo_disco', ''), 'valor': '', 'link_carrinho': '', 'cupom': '',
                     'prazo': '', 'assinatura': params.assinatura, 'loja': params.site,
                     'ultimo_disco': d.get('ultimo_disco', 'um disco'),
                     'sugestao': sug['nome'] if sug else 'uns discos novos que chegaram', 'link_sugestao': sug['link'] if sug else params.site,
                     'sugestoes': '\n'.join(f'{s["nome"]}: {s["link"]}' for s in sugs) if sugs else f'Os discos novos estão aqui: {params.site}'}
        texto, desconhecidos = c.montar_mensagem(params.modelos.get(modelo, ''), dados_msg)
        obs = []
        if desconhecidos:
            obs.append('marcador desconhecido: ' + ', '.join(sorted(set(desconhecidos))))
        if not params.modelos.get(modelo):
            obs.append(f'modelo {modelo} não existe na aba Mensagens')
        situacao = 'Contatar'
        if not fone:
            situacao = 'Telefone inválido'
            obs.append('telefone inválido: sem link do WhatsApp')
            resumo['sem telefone válido'] += 1
        if sug is None:
            obs.append('sem disco em estoque da família do cliente: a mensagem usa o texto geral')
        ger.linhas.append(c.LinhaDaFila(
            carrinho=id_, abandonado_em=_momento_do_gatilho(gatilho), cliente=str(r.get('primeiro_nome') or ''), primeiro_nome=primeiro,
            telefone=fone, email=email, itens=d.get('ultimo_disco', ''), valor=0.0, link=sug['link'] if sug else '', estoque='OK',
            estoque_conferido_em=agora, horas=round((agora - _momento_do_gatilho(gatilho)).total_seconds() / 3600, 1),
            toques_enviados=0, proximo_toque=1, modelo=modelo, cupom='', situacao=situacao, mensagem=texto,
            link_whatsapp=c.link_do_whatsapp(fone, texto) if fone else '', observacoes='; '.join(obs), origem=origem, grupo=grupo))
        if origem == ORIGEM_VIP:
            resumo['VIP'] += 1

    if desejos is not None and len(desejos):
        for linha in alertas_garimpo(desejos, tabelas.produtos, params, agora, ja_na_fila, bloqueio, api):
            ger.linhas.append(linha)
            resumo['garimpo'] += 1
    ger.resumo = resumo
    return ger


def alertas_garimpo(desejos: pd.DataFrame, produtos: pd.DataFrame, params: c.Parametros, agora: pd.Timestamp,
                    ja_na_fila: dict[str, dict], bloqueio: set[str], api: Any = None) -> list[c.LinhaDaFila]:
    """Aviso quando entra em estoque um disco que combina com o que o cliente pediu (aba `desejos`).

    Colunas esperadas: email, telefone, nome, desejo, data, status (e formato, opcional). O disco serve quando todas as
    palavras (3 letras ou mais, fora as de formato) do desejo aparecem no nome, o formato bate (se o pedido disser
    LP, CD etc.) e ele entrou na loja depois do pedido.
    """
    import re
    import unicodedata

    def limpar(t: Any) -> str:
        return re.sub(r'\s+', ' ', unicodedata.normalize('NFKD', str(t)).encode('ascii', 'ignore').decode().lower()).strip()

    pool = disponiveis(produtos)
    if len(pool) == 0:
        return []
    nomes = [limpar(n) for n in pool['nome']]
    saida: list[c.LinhaDaFila] = []
    for r in desejos.to_dict('records'):
        if str(r.get('status') or '').strip().lower() in ('avisado', 'encerrado', 'cancelado'):
            continue
        email = str(r.get('email') or '').strip().lower()
        fone = c.telefone_whatsapp(r.get('telefone'))
        if (email and email in bloqueio) or (fone and fone in bloqueio):
            continue
        palavras = [w for w in limpar(r.get('desejo')).split() if len(w) >= 3 and w not in garimpo.FORMATOS]
        formato = garimpo.formato_do_pedido(r.get('formato'), r.get('desejo'))
        quando = cp_momento(r.get('data'))
        contato = email or fone or str(r.get('nome') or '').strip().lower()
        if not palavras or not contato:
            continue
        # um pedido gera um aviso só: depois que a Mariana marcou o primeiro toque, o pedido está atendido
        pedido = garimpo.codigo_do_pedido(contato, r.get('desejo'))
        if any(k.startswith(f'GAR-{pedido}-') and int(v.get('toques') or 0) > 0 for k, v in ja_na_fila.items()):
            continue
        for k, nome in enumerate(nomes):
            if not all(w in nome for w in palavras):
                continue
            if formato and garimpo.formato_do_produto(pool['nome'].iloc[k]) != formato:
                continue
            # serve disco novo na loja ou disco que VOLTOU ao estoque depois do pedido (D-072)
            criado = pool['criado_em'].iloc[k]
            voltou = str(pool['no_estoque_desde'].iloc[k] if 'no_estoque_desde' in pool.columns else '')[:10]
            if quando is not None and pd.notna(criado) and criado < quando and not (voltou and voltou >= pd.Timestamp(quando).tz_convert('America/Sao_Paulo').strftime('%Y-%m-%d')):
                continue
            id_ = f'GAR-{pedido}-{int(pool["id"].iloc[k])}'
            if api is not None and not c.estoque_do_produto(api, int(pool['id'].iloc[k]))[0]:
                continue
            nome_cliente = str(r.get('nome') or '').strip().split()[0:1]
            primeiro = (nome_cliente[0] if nome_cliente else '').title()
            sug = c.nome_do_disco(str(pool['nome'].iloc[k]))
            link = f'{params.site}/produtos/{pool["url"].iloc[k]}/'
            dados = {'nome': primeiro or 'tudo bem', 'itens': sug, 'valor': '', 'link_carrinho': '', 'cupom': '', 'prazo': '',
                     'assinatura': params.assinatura, 'loja': params.site, 'ultimo_disco': '', 'sugestao': sug, 'link_sugestao': link,
                     'sugestoes': f'{sug}: {link}'}
            texto, _ = c.montar_mensagem(params.modelos.get('ALERTA_GARIMPO', ''), dados)
            saida.append(c.LinhaDaFila(
                carrinho=id_, abandonado_em=agora, cliente=primeiro, primeiro_nome=primeiro, telefone=fone, email=email, itens=sug,
                valor=0.0, link=link, estoque='OK', estoque_conferido_em=agora, horas=0.0, toques_enviados=0, proximo_toque=1,
                modelo='ALERTA_GARIMPO', cupom='', situacao='Contatar' if fone else 'Telefone inválido', mensagem=texto,
                link_whatsapp=c.link_do_whatsapp(fone, texto) if fone else '',
                observacoes='' if fone else 'sem telefone válido no pedido: procure o contato pelo nome na aba desejos',
                origem=ORIGEM_GARIMPO, grupo='Aviso de garimpo'))
            break
    return saida


def cp_momento(valor: Any) -> pd.Timestamp | None:
    from painel_monstro.saidas.carrinhos_planilha import para_momento
    t = para_momento(valor)
    return None if t is None else t.tz_convert('UTC')


# ----------------------------------------------------------------------------
# Regras da fila única
# ----------------------------------------------------------------------------
def aplicar_regras(linhas: list[c.LinhaDaFila], ultimo_contato: dict[str, pd.Timestamp], enviados_hoje: int,
                   cfg: FilaUnica, agora: pd.Timestamp) -> dict[str, int]:
    """Decide a situação final de cada linha: uma mensagem por pessoa, 30 dias, prioridade e limite do dia.

    `ultimo_contato`: chave (email ou telefone) -> momento do último WhatsApp já enviado.
    Muda `situacao` das linhas e devolve contagens.
    """
    rank = {o: i for i, o in enumerate(cfg.prioridade)}
    pendentes = [l for l in linhas if l.situacao in ('Contatar', 'Aguardar aprovação')]

    def chaves(l: c.LinhaDaFila) -> list[str]:
        return [k for k in (l.email.lower() if l.email else '', c.so_digitos(l.telefone)) if k]

    contagem = {'outra mensagem na fila': 0, 'trava de 30 dias': 0, 'fica para amanhã': 0, 'contatar': 0}
    # 1. uma mensagem por pessoa: a de maior prioridade
    melhor: dict[str, c.LinhaDaFila] = {}
    for l in sorted(pendentes, key=lambda x: (rank.get(x.origem, 99), x.abandonado_em)):
        if any(k in melhor for k in chaves(l)):
            l.situacao = 'Já tem outra mensagem na fila'
            contagem['outra mensagem na fila'] += 1
            continue
        for k in chaves(l):
            melhor[k] = l
    # 2. trava de 30 dias (carrinho e aviso de garimpo passam por cima)
    for l in pendentes:
        if l.situacao not in ('Contatar', 'Aguardar aprovação') or l.origem in ORIGENS_QUE_PASSAM_POR_CIMA:
            continue
        ultimos = [ultimo_contato[k] for k in chaves(l) if k in ultimo_contato]
        if ultimos and (agora - max(ultimos)).days < cfg.dias_entre_whatsapp:
            l.situacao = 'Aguardar 30 dias'
            l.proximo_envio = max(ultimos) + pd.Timedelta(days=cfg.dias_entre_whatsapp)
            contagem['trava de 30 dias'] += 1
    # 3. limite diário, pela prioridade
    ativos = sorted([l for l in pendentes if l.situacao == 'Contatar'], key=lambda x: (rank.get(x.origem, 99), x.abandonado_em))
    vagas = max(cfg.limite_por_dia - enviados_hoje, 0)
    for i, l in enumerate(ativos):
        if i >= vagas:
            l.situacao = 'Fica para amanhã'
            contagem['fica para amanhã'] += 1
        else:
            contagem['contatar'] += 1
    return contagem


# ----------------------------------------------------------------------------
# Linha de comando: mostra a fila de um dia sem gravar nada
# ----------------------------------------------------------------------------
def _mascarar(telefone: str) -> str:
    return f'{telefone[:4]}*****{telefone[-2:]}' if len(telefone) >= 8 else telefone


def proximo_dia_de_fila(a_partir_de: date, dias: frozenset[int]) -> date:
    from datetime import timedelta
    d = a_partir_de
    for _ in range(8):
        if d.weekday() in dias:
            return d
        d += timedelta(days=1)
    return a_partir_de


@comando_seguro
def main(argv: list[str] | None = None) -> int:
    """`python -m painel_monstro.saidas.fila_unica --dia 2026-10-12`: a fila de um dia às 10h, sem gravar nada."""
    import argparse
    import sys
    from collections import Counter

    from painel_monstro.config import carregar
    from painel_monstro.coletor import nuvemshop_api as nuvem
    from painel_monstro.saidas import carrinhos_planilha as cpl
    from painel_monstro.saidas import regua_planilha as rp
    from painel_monstro.saidas.planilha_google import PlanilhaGoogle

    analisador = ArgumentParserSeguro(description='Mostra a fila única de um dia, sem gravar nada na planilha.')
    analisador.add_argument('--dia', help='AAAA-MM-DD (padrão: o próximo dia de fila)')
    analisador.add_argument('--exemplos', type=int, default=2, help='quantas mensagens mostrar de cada origem')
    analisador.add_argument('--sem-atualizar', action='store_true', help='usa os dados já baixados, sem falar com a Nuvemshop')
    args = analisador.parse_args(argv)

    config = carregar()
    planilha = PlanilhaGoogle.conectar(config)
    api = nuvem.NuvemshopAPI(config)
    if args.sem_atualizar:
        a = nuvem.Armazem()
        tabelas = nuvem.montar_tabelas(*(list(a.registros(r).values()) for r in ('pedidos', 'clientes', 'produtos')))
    else:
        tabelas, _ = nuvem.coletar(config, api=api)
    params = cpl.ler_parametros(planilha)
    hoje_brt = pd.Timestamp.now(tz=FUSO).date()
    dia = date.fromisoformat(args.dia) if args.dia else proximo_dia_de_fila(hoje_brt, params.dias_da_fila)
    agora_brt = pd.Timestamp(dia).tz_localize(FUSO) + pd.Timedelta(hours=10)
    plano = cpl.planejar_fila(planilha, api, tabelas, agora_brt.tz_convert('UTC'), fila_unica=True, somente_leitura=True)
    cfg = rp.ler_fila_unica(planilha)
    teste = rp.ler_teste45(planilha)

    nomes_dos_dias = ['segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado', 'domingo']
    print(f'Fila simulada para {nomes_dos_dias[dia.weekday()]}, {dia:%d/%m/%Y}, às 10h (nada foi gravado na planilha).')
    if dia.weekday() not in params.dias_da_fila:
        print('  Atenção: esse dia não é dia de fila; nenhum email sairia e o pendente passa para o próximo dia de fila.')
    print(f'Limite do dia: {cfg.limite_por_dia}; intervalo: {cfg.dias_entre_whatsapp} dias')
    print(f'Teste de 45 dias: {teste.inicio:%d/%m/%Y} a {teste.fim:%d/%m/%Y} '
          f'({teste.controle_pct:.0f}% nada, {teste.email_pct:.0f}% só email, {teste.whatsapp_pct:.0f}% email e WhatsApp); '
          f'quem completa 45 dias fica {teste.dias_para_contatar} dias na fila.')
    por_origem = Counter((l.origem, l.situacao) for l in plano.linhas)
    for origem in cfg.prioridade:
        partes = {s: n for (o, s), n in por_origem.items() if o == origem}
        print(f'  Pessoas por origem: {sum(partes.values())}')
    cont = plano.contagens
    print('  sorteios de hoje:', {k: v for k, v in cont['fila_unica'].items() if k.startswith('45 dias')})
    print('  regras:', {k: v for k, v in cont['fila_unica'].items() if k in ('outra mensagem na fila', 'trava de 30 dias', 'fica para amanhã', 'contatar')})
    print('  avisos:', {k: v for k, v in cont['fila_unica'].items() if k in ('sem telefone válido', 'sem sugestão em estoque', 'bloqueados')})
    print('Motivos de exclusão disponíveis somente na planilha privada.')
    sem_contato = [f for f in plano.finais if str(f.valores.get('Situação')) == 'Encerrado sem contato']
    print(f'  encerrados sem contato (todos os dias): {len(sem_contato)}')
    for origem in cfg.prioridade:
        for l in [x for x in plano.linhas if x.origem == origem and x.situacao == 'Contatar'][:args.exemplos]:
            print('Prévia individual omitida do log público; conferir a planilha privada.')
            texto = l.mensagem.replace(l.link, '<link>') if l.link else l.mensagem
            print('Mensagem disponível somente na planilha privada.')
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
