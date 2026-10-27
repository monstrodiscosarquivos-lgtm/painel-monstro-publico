"""Raspadinha online: sorteio dos prêmios, grupo de controle, cupom único e link de cada cliente (D-062).

Regras (todas ajustáveis na aba `Raspadinha` da Planilha Google):
- O prêmio é sorteado AQUI, antes do envio, nunca na página. A página só mostra o que veio no link.
- Os prêmios saem de um "saco" com a quantidade de cartelas de cada um, como as cartelas físicas: quando acabam,
  quem sobrou na lista fica sem cartela (motivo "acabaram as cartelas").
- Cada cliente sorteado recebe um cupom único, de uso único, só com letras e números (a Nuvemshop não aceita
  hífen no código). O código é aleatório e difícil de adivinhar.
- Grupo de controle (padrão 10%) não recebe nada, para medir o que a raspadinha vende a mais (D-006, D-020).
- Limite de um benefício por cliente a cada N dias (padrão 90, D-005): conta cupom usado em pedido, etapa da régua
  com benefício e raspadinhas anteriores.
- Quem não aceita marketing na Nuvemshop fica de fora. O email da loja também.
- O sorteio usa semente fixa pelo nome da campanha: rodar de novo com os mesmos dados dá o mesmo resultado.
"""
from __future__ import annotations

import base64
import json
import random
import re
import zlib
from dataclasses import dataclass, field
from datetime import date, timedelta
from urllib.parse import quote

import pandas as pd

from painel_monstro.motor.regua import EMAIL_DA_LOJA

ALFABETO_CUPOM = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'  # sem 0/O, 1/I/L, para ninguém errar ao digitar
CHAVE_LINK = b'monstro-raspadinha'  # só embaralha o link para não estragar a surpresa; segurança é o cupom único

TIPOS = {'porcentagem': 'percentage', 'frete grátis': 'shipping', 'frete gratis': 'shipping', 'valor em r$': 'absolute',
         'valor': 'absolute', 'percentage': 'percentage', 'shipping': 'shipping', 'absolute': 'absolute'}

GRUPO_ENVIO, GRUPO_CONTROLE, GRUPO_FORA = 'envio', 'controle', 'fora'

ENVIOS_COLUNAS = ['campanha', 'email', 'primeiro_nome', 'grupo', 'motivo', 'premio', 'tipo', 'valor', 'cupom',
                  'valido_ate', 'link', 'cupom_criado', 'criado_em', 'pedido', 'receita', 'usado_em']
ENVIOS_CHAVE = ['campanha', 'email']


@dataclass(frozen=True)
class Premio:
    nome: str          # o que aparece no selo, ex. "15%" ou "FRETE GRÁTIS"
    tipo: str          # percentage, shipping ou absolute (como a API da Nuvemshop)
    valor: float       # 15 para 15%; 0 para frete grátis; 20 para R$20
    quantidade: int    # cartelas desse prêmio


@dataclass(frozen=True)
class ParametrosRaspadinha:
    campanha: str = ''
    modo: str = 'Teste'                      # Teste: não cria cupom. Real: cria (e só com --criar-cupons)
    prefixo: str = 'RASPA'
    tamanho_codigo: int = 6
    validade_dias: int = 15
    pedido_minimo: float = 0.0
    cumulativo: bool = False                 # vale junto com outras promoções?
    publico: str = 'Lista colada'            # ou "Todos que aceitam marketing"
    controle: float = 0.10
    minimo_para_controle: int = 10
    dias_entre_beneficios: int = 90
    url_pagina: str = ''
    premios: tuple[Premio, ...] = field(default_factory=lambda: (
        Premio('10%', 'percentage', 10, 60), Premio('15%', 'percentage', 15, 25),
        Premio('20%', 'percentage', 20, 5), Premio('FRETE GRÁTIS', 'shipping', 0, 10)))

    @property
    def real(self) -> bool:
        return self.modo.strip().lower() == 'real'


def limpar_prefixo(prefixo: str) -> str:
    """Só letras e números, maiúsculas (exigência da Nuvemshop)."""
    sem_acento = prefixo.upper().translate(str.maketrans('ÁÀÂÃÉÊÍÓÔÕÚÇ', 'AAAAEEIOOOUC'))
    return re.sub(r'[^A-Z0-9]', '', sem_acento)


def semente(campanha: str) -> int:
    return zlib.crc32(campanha.strip().lower().encode('utf-8'))


def gerar_codigo(rng: random.Random, prefixo: str, tamanho: int) -> str:
    return limpar_prefixo(prefixo) + ''.join(rng.choice(ALFABETO_CUPOM) for _ in range(tamanho))


def detalhe_do_premio(p: Premio) -> tuple[str, str]:
    """Texto grande e texto pequeno do selo."""
    if p.tipo == 'shipping':
        return 'FRETE', 'GRÁTIS'
    if p.tipo == 'absolute':
        return f'R${p.valor:g}', 'DE DESCONTO'
    return p.nome if p.nome.strip() else f'{p.valor:g}%', 'DE DESCONTO'


def texto_do_premio(p: Premio) -> str:
    if p.tipo == 'shipping':
        return 'frete grátis'
    if p.tipo == 'absolute':
        return f'R$ {p.valor:g} de desconto'
    return f'{p.valor:g}% de desconto'


# ----------------------------------------------------------------------------- link
def codificar_link(dados: dict) -> str:
    bruto = json.dumps(dados, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    mexido = bytes(b ^ CHAVE_LINK[i % len(CHAVE_LINK)] for i, b in enumerate(bruto))
    return base64.urlsafe_b64encode(mexido).decode('ascii').rstrip('=')


def decodificar_link(token: str) -> dict:
    mexido = base64.urlsafe_b64decode(token + '=' * (-len(token) % 4))
    bruto = bytes(b ^ CHAVE_LINK[i % len(CHAVE_LINK)] for i, b in enumerate(mexido))
    return json.loads(bruto.decode('utf-8'))


def montar_link(url_pagina: str, cupom: str, premio: Premio, valido_ate: date, primeiro_nome: str) -> str:
    grande, pequeno = detalhe_do_premio(premio)
    token = codificar_link({'c': cupom, 'g': grande, 'p': pequeno, 't': texto_do_premio(premio),
                            'v': valido_ate.strftime('%d/%m'), 'd': valido_ate.isoformat(), 'n': (primeiro_nome or '').strip()[:30]})
    base = url_pagina.strip() or 'https://SEU-ENDERECO/raspadinha/'
    return f'{base}{"&" if "?" in base else "?"}t={quote(token)}'


# ----------------------------------------------------------------------------- benefícios recentes
def ultimos_beneficios(pedidos: pd.DataFrame, regua_historico: pd.DataFrame | None = None,
                       envios_anteriores: pd.DataFrame | None = None,
                       etapas_com_beneficio: tuple[str, ...] = ('Etapa 2 · Convite', 'Etapa 3 · Última chamada')) -> pd.Series:
    """email -> data do último benefício: cupom usado num pedido válido, etapa com benefício da régua ou raspadinha anterior."""
    datas: list[pd.Series] = []
    if pedidos is not None and len(pedidos) and 'cupom' in pedidos:
        p = pedidos[pedidos['valido'].astype(bool) & pedidos['cupom'].notna() & (pedidos['cupom'].astype(str).str.strip() != '')]
        datas.append(pd.Series(pd.to_datetime(p['data']).dt.normalize().to_numpy(), index=p['email'].str.lower()))
    if regua_historico is not None and len(regua_historico):
        r = regua_historico[regua_historico['etapa'].isin(etapas_com_beneficio) & (regua_historico['grupo'] == 'envio')]
        datas.append(pd.Series(pd.to_datetime(r['data_referencia'], errors='coerce').to_numpy(), index=r['email'].astype(str).str.lower()))
    if envios_anteriores is not None and len(envios_anteriores):
        e = envios_anteriores[envios_anteriores['grupo'] == GRUPO_ENVIO]
        datas.append(pd.Series(pd.to_datetime(e['criado_em'], errors='coerce').dt.normalize().to_numpy(),
                               index=e['email'].astype(str).str.lower()))
    if not datas:
        return pd.Series(dtype='datetime64[ns]')
    todas = pd.concat(datas).dropna()
    return todas.groupby(level=0).max()


# ----------------------------------------------------------------------------- sorteio
def sortear(publico: pd.DataFrame, params: ParametrosRaspadinha, hoje: date,
            beneficios: pd.Series | None = None, nao_aceitam: set[str] | None = None) -> pd.DataFrame:
    """Uma linha por pessoa do público, com grupo, prêmio, cupom e link.

    `publico`: colunas `email` e `primeiro_nome`. `nao_aceitam`: emails que não aceitam marketing.
    """
    if not params.campanha.strip():
        raise ValueError('Dê um nome para a campanha na aba Raspadinha (linha "Campanha").')
    if not limpar_prefixo(params.prefixo):
        raise ValueError('O prefixo do cupom precisa ter pelo menos uma letra ou número.')
    pessoas = publico.copy()
    pessoas['email'] = pessoas['email'].astype(str).str.strip().str.lower()
    pessoas = pessoas[pessoas['email'].str.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+')]
    pessoas = pessoas.drop_duplicates('email').sort_values('email').reset_index(drop=True)
    pessoas['primeiro_nome'] = pessoas.get('primeiro_nome', pd.Series('', index=pessoas.index)).fillna('').astype(str)
    pessoas['grupo'], pessoas['motivo'] = '', ''

    fora = pessoas['email'] == EMAIL_DA_LOJA
    pessoas.loc[fora, ['grupo', 'motivo']] = [GRUPO_FORA, 'email da loja']
    if nao_aceitam:
        f = (pessoas['grupo'] == '') & pessoas['email'].isin(nao_aceitam)
        pessoas.loc[f, ['grupo', 'motivo']] = [GRUPO_FORA, 'não aceita marketing']
    if beneficios is not None and len(beneficios) and params.dias_entre_beneficios > 0:
        ultimo = pessoas['email'].map(beneficios)
        recente = ultimo.notna() & ((pd.Timestamp(hoje) - pd.to_datetime(ultimo)).dt.days < params.dias_entre_beneficios)
        f = (pessoas['grupo'] == '') & recente
        pessoas.loc[f, ['grupo', 'motivo']] = [GRUPO_FORA, f'benefício nos últimos {params.dias_entre_beneficios} dias']

    rng = random.Random(semente(params.campanha))
    aptos = pessoas.index[pessoas['grupo'] == ''].tolist()
    if len(aptos) >= params.minimo_para_controle and params.controle > 0:
        controle = set(rng.sample(aptos, round(len(aptos) * params.controle)))
    else:
        controle = set()
    pessoas.loc[list(controle), ['grupo', 'motivo']] = [GRUPO_CONTROLE, 'grupo de controle (não recebe)']

    saco = [p for p in params.premios for _ in range(max(int(p.quantidade), 0))]
    rng.shuffle(saco)
    recebem = [i for i in aptos if i not in controle]
    rng.shuffle(recebem)
    valido_ate = hoje + timedelta(days=params.validade_dias)
    usados: set[str] = set()
    linhas = {c: [''] * len(pessoas) for c in ('premio', 'tipo', 'valor', 'cupom', 'valido_ate', 'link')}
    for n, i in enumerate(recebem):
        if n >= len(saco):
            pessoas.loc[i, ['grupo', 'motivo']] = [GRUPO_FORA, 'acabaram as cartelas']
            continue
        premio = saco[n]
        codigo = gerar_codigo(rng, params.prefixo, params.tamanho_codigo)
        while codigo in usados:
            codigo = gerar_codigo(rng, params.prefixo, params.tamanho_codigo)
        usados.add(codigo)
        pessoas.loc[i, 'grupo'] = GRUPO_ENVIO
        linhas['premio'][i] = premio.nome
        linhas['tipo'][i] = premio.tipo
        linhas['valor'][i] = premio.valor
        linhas['cupom'][i] = codigo
        linhas['valido_ate'][i] = valido_ate.isoformat()
        linhas['link'][i] = montar_link(params.url_pagina, codigo, premio, valido_ate, pessoas.loc[i, 'primeiro_nome'])
    for c, v in linhas.items():
        pessoas[c] = v
    pessoas['campanha'] = params.campanha.strip()
    pessoas['cupom_criado'] = ['não (modo teste)' if g == GRUPO_ENVIO else '' for g in pessoas['grupo']]
    pessoas['criado_em'] = hoje.isoformat()
    for c in ('pedido', 'receita', 'usado_em'):
        pessoas[c] = ''
    return pessoas[ENVIOS_COLUNAS]


def resumo_do_sorteio(envios: pd.DataFrame) -> pd.DataFrame:
    """Contagem por grupo/motivo e por prêmio, para mostrar antes de criar os cupons."""
    linhas = [{'item': f'{g} · {m}' if m and g != GRUPO_ENVIO else g, 'pessoas': int(n)}
              for (g, m), n in envios.groupby(['grupo', 'motivo']).size().items()]
    linhas += [{'item': f'prêmio {p}', 'pessoas': int(n)} for p, n in envios[envios['grupo'] == GRUPO_ENVIO].groupby('premio').size().items()]
    return pd.DataFrame(linhas, columns=['item', 'pessoas'])


# ----------------------------------------------------------------------------- uso e resultado
def payload_cupom(linha: pd.Series, params: ParametrosRaspadinha, hoje: date) -> dict:
    """Corpo do POST /coupons da Nuvemshop para uma linha de envio."""
    corpo = {'code': linha['cupom'], 'type': linha['tipo'], 'max_uses': 1, 'valid': True,
             'start_date': hoje.isoformat(), 'end_date': str(linha['valido_ate']),
             'combines_with_other_discounts': bool(params.cumulativo), 'includes_shipping': False}
    if linha['tipo'] in ('percentage', 'absolute'):
        corpo['value'] = f'{float(linha["valor"]):.2f}'
    if params.pedido_minimo > 0:
        corpo['min_price'] = round(float(params.pedido_minimo), 2)
    return corpo


def marcar_uso(envios: pd.DataFrame, pedidos: pd.DataFrame) -> pd.DataFrame:
    """Preenche `pedido`, `receita` (produtos menos desconto) e `usado_em` de quem usou o cupom num pedido válido."""
    saida = envios.copy()
    # A planilha mistura vazio e número; pandas 3 infere texto para uma coluna vazia.
    # Mantém vazios sem provocar regravação e aceita número quando houver uso real.
    saida['receita'] = saida['receita'].astype(object)
    if pedidos is None or not len(pedidos) or 'cupom' not in pedidos:
        return saida
    p = pedidos[pedidos['valido'].astype(bool) & pedidos['cupom'].notna()].copy()
    p['_codigos'] = p['cupom'].astype(str).str.upper().str.split(r'\s*,\s*')
    p = p.explode('_codigos')
    por_codigo = p.drop_duplicates('_codigos').set_index('_codigos')
    for i, cupom in saida['cupom'].items():
        cupom = str(cupom).strip().upper()
        if cupom and cupom in por_codigo.index:
            ped = por_codigo.loc[cupom]
            saida.loc[i, 'pedido'] = str(ped['numero'])
            saida.loc[i, 'receita'] = round(float(ped['subtotal']) - float(ped['desconto']), 2)
            saida.loc[i, 'usado_em'] = pd.Timestamp(ped['data']).strftime('%Y-%m-%d')
    return saida


def resultado(envios: pd.DataFrame, pedidos: pd.DataFrame, hoje: date, janela_dias: int = 30, amostra_minima: int = 30) -> pd.DataFrame:
    """Por campanha e grupo: pessoas, quem comprou em `janela_dias`, taxa, receita, cupons usados e desconto dado.
    Diferença envio menos controle só aparece com `amostra_minima` pessoas em cada grupo (D-020)."""
    colunas = ['campanha', 'grupo', 'pessoas', 'compraram', 'taxa_compra', 'receita', 'cupons_usados', 'receita_com_cupom',
               'desconto_dos_cupons', 'janela_fechada', 'diferenca_vs_controle']
    if envios is None or not len(envios):
        return pd.DataFrame(columns=colunas)
    validos = pedidos[pedidos['valido'].astype(bool)].copy() if pedidos is not None and len(pedidos) else pd.DataFrame(columns=['email', 'data'])
    validos['email'] = validos['email'].astype(str).str.lower()
    validos['data'] = pd.to_datetime(validos['data'])
    linhas = []
    for campanha, env in envios[envios['grupo'].isin([GRUPO_ENVIO, GRUPO_CONTROLE])].groupby('campanha'):
        inicio = pd.to_datetime(env['criado_em'], errors='coerce').min()
        fim = inicio + pd.Timedelta(days=janela_dias)
        janela = validos[(validos['data'] >= inicio) & (validos['data'] < fim)]
        taxas = {}
        for grupo, g in env.groupby('grupo'):
            compras = janela[janela['email'].isin(set(g['email']))]
            compraram = compras['email'].nunique()
            receita = round(float((compras['subtotal'] - compras['desconto']).sum()), 2) if len(compras) else 0.0
            usados = g[g['pedido'].astype(str).str.strip() != '']
            codigos = set(usados['cupom'].astype(str).str.upper())
            com_cupom = janela[janela['cupom'].fillna('').astype(str).str.upper().apply(
                lambda c: bool(codigos & set(re.split(r'\s*,\s*', c))) if c else False)] if codigos and 'cupom' in janela else janela.iloc[0:0]
            taxa = compraram / len(g) if len(g) else 0.0
            taxas[grupo] = (taxa, len(g))
            linhas.append({'campanha': campanha, 'grupo': grupo, 'pessoas': len(g), 'compraram': compraram,
                           'taxa_compra': round(taxa, 4), 'receita': receita, 'cupons_usados': len(usados),
                           'receita_com_cupom': round(float((com_cupom['subtotal'] - com_cupom['desconto']).sum()), 2) if len(com_cupom) else 0.0,
                           'desconto_dos_cupons': round(float(com_cupom['desconto'].sum()), 2) if len(com_cupom) else 0.0,
                           'janela_fechada': 'sim' if pd.Timestamp(hoje) >= fim else 'não', 'diferenca_vs_controle': ''})
        if GRUPO_ENVIO in taxas and GRUPO_CONTROLE in taxas:
            (te, ne), (tc, nc) = taxas[GRUPO_ENVIO], taxas[GRUPO_CONTROLE]
            dif = f'{(te - tc) * 100:+.1f} pontos' if min(ne, nc) >= amostra_minima else 'dados insuficientes'
            for l in linhas:
                if l['campanha'] == campanha and l['grupo'] == GRUPO_ENVIO:
                    l['diferenca_vs_controle'] = dif
    return pd.DataFrame(linhas, columns=colunas)
