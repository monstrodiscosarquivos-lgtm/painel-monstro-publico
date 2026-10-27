"""Carrinho abandonado (AGENTS.md, "Carrinho abandonado"; D-011 a D-013, D-015, D-018, D-020).

Pega os carrinhos da Nuvemshop (só leitura), aplica os filtros, escolhe o modelo de mensagem do próximo
toque e monta a mensagem e o link do WhatsApp. O envio é sempre manual (Mariana); o código nunca manda nada.

Tudo que o Túlio pode mudar vem de `Parametros` (aba `Configuração`) e dos modelos (aba `Mensagens`); os
valores aqui são só o padrão inicial, iguais aos de `dados/referencia-privada/Carrinhos-Monstro-ferramenta.xlsx`.

Uso (mostra a fila de hoje no terminal, sem gravar na planilha):
    python -m painel_monstro.saidas.carrinhos --hoje
"""
from __future__ import annotations

import hashlib
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import pandas as pd

from painel_monstro.log_publico import comando_seguro, ArgumentParserSeguro, resumo_erro
from painel_monstro.coletor.nuvemshop_api import ErroAPI, NuvemshopAPI, _pt
from painel_monstro.coletor.planilhas_csv import Tabelas
from painel_monstro.motor.regua import PADRAO as REGUA

CAMPOS_CHECKOUT = ('id,created_at,updated_at,completed_at,contact_name,contact_email,contact_phone,'
                   'abandoned_checkout_url,subtotal,total,products,contact_accepts_marketing')

MODELOS_PADRAO = {
    'T1': 'Oi, {nome}! Aqui é a {assinatura}. Vi que ficou um carrinho seu por aqui com {itens}. Separei pra não correr risco de sumir do estoque. Quer fechar? É só continuar por aqui: {link_carrinho}',
    'T1_UNICO': 'Oi, {nome}! Aqui é a {assinatura}. Seu carrinho com {itens} ficou esperando. São usados e temos só um de cada, então separei pra você. Quer garantir? É só por aqui: {link_carrinho}',
    'T1_RECORRENTE': 'Oi, {nome}! Aqui é a {assinatura}, que bom te ver de novo por aqui. Vi que {itens} ficou no seu carrinho. Se quiser, é só finalizar por aqui: {link_carrinho}',
    'T2_FRETE': 'Oi, {nome}! Voltando aqui sobre seu carrinho com {itens}. Pra te dar um empurrãozinho, liberei o frete grátis: é só usar o cupom {cupom} no checkout, {prazo}. Segue o link com tudo pronto: {link_carrinho}',
    'T2_ESCASSEZ': 'Oi, {nome}! Sobre {itens} que ficou no seu carrinho: é exemplar único e costuma sair rápido. Não quis deixar você perder. Garante por aqui: {link_carrinho}',
    'T2_LEMBRETE': 'Oi, {nome}! Voltando sobre seu carrinho com {itens}. Se precisar de ajuda para finalizar ou tiver alguma dúvida sobre os discos, me chama. Você pode continuar por aqui: {link_carrinho}',
    'T3_CUPOM': 'Oi, {nome}! Última passada aqui. Pro seu carrinho com {itens}, consigo 10% de desconto nos discos com o cupom {cupom}, {prazo}. Depois disso não consigo segurar. É só finalizar por aqui: {link_carrinho}',
    'ESGOTADO': 'Oi, {nome}! Aqui é a {assinatura}. Vi que ficou um carrinho seu por aqui, mas um dos discos ({itens}) acabou de sair: era exemplar único. Se quiser, separo outros parecidos pra você. Posso te mandar uns?',
    'G45': 'Oi, {nome}! Aqui é a {assinatura}. Faz um tempinho que você levou {ultimo_disco} aqui na Monstro. Chegou um que tem tudo a ver com o seu gosto: {sugestao}. Dá uma olhada: {link_sugestao}\n\nE me conta: tem algum disco que você anda caçando? Se aparecer, te aviso primeiro.',
    'VIP': 'Oi, {nome}! Aqui é a {assinatura}. Passando pra agradecer por você ser cliente de casa aqui na Monstro. Separei três discos que lembram o que você costuma levar:\n{sugestoes}\nSe quiser que eu guarde algum ou procure um disco específico, é só me falar.',
    'ALERTA_GARIMPO': 'Oi, {nome}! Aqui é a {assinatura}. Chegou o disco que você pediu pra gente procurar: {sugestao}. Te aviso primeiro, como combinado: {link_sugestao}',
}
MODELOS_COM_CUPOM = ('T2_FRETE', 'T3_CUPOM')
MARCADORES = ('nome', 'itens', 'valor', 'link_carrinho', 'cupom', 'prazo', 'assinatura', 'loja')


@dataclass(frozen=True)
class Parametros:
    """Aba `Configuração`: o Túlio muda na planilha, sem mexer no código."""
    assinatura: str = 'Mariana, da Monstro Discos'
    comecar_depois_de_horas: float = 12
    parar_depois_de_dias: float = 7
    intervalo_entre_toques_horas: float = 24
    maximo_de_toques: int = 3
    minimo_frete_gratis: float = 200
    maximo_custo_frete: float = 30
    frete_limite_garantido: bool = False
    minimo_cupom: float = 200
    cupom_frete: str = 'VOLTAFRETEOUT'
    cupom_desconto: str = 'VOLTA10OUT'
    prazo: str = 'válido até amanhã às 23h59'
    site: str = 'https://lojamonstro.com.br'
    valor_minimo_do_carrinho: float = 0
    comparacao_pct: float = 10
    cupom_precisa_de_aprovacao: bool = False
    modelos: dict = field(default_factory=lambda: dict(MODELOS_PADRAO))
    dias_da_fila: frozenset = frozenset({0, 1, 2, 3, 4, 5})  # seg a sáb (0 = segunda)


@dataclass
class LinhaDaFila:
    carrinho: str
    abandonado_em: pd.Timestamp
    cliente: str
    primeiro_nome: str
    telefone: str
    email: str
    itens: str
    valor: float
    link: str
    estoque: str  # OK, Parcial ou Esgotado
    estoque_conferido_em: pd.Timestamp
    horas: float
    toques_enviados: int
    proximo_toque: int
    modelo: str
    cupom: str
    situacao: str  # Contatar, Aguardar aprovação, Aguardar intervalo, Grupo de comparação, Telefone inválido
    mensagem: str
    link_whatsapp: str
    observacoes: str
    proximo_envio: pd.Timestamp | None = None  # só depois do primeiro toque
    origem: str = 'Carrinho'  # Carrinho, Garimpo, VIP ou 45 dias (fila única)
    grupo: str = ''  # grupo de medição, quando não é o padrão


# ----------------------------------------------------------------------------
# Peças pequenas (texto, telefone, sorteio)
# ----------------------------------------------------------------------------
def so_digitos(texto: Any) -> str:
    return re.sub(r'\D', '', str(texto or ''))


def telefone_whatsapp(texto: Any) -> str:
    """Telefone só com dígitos e com 55 na frente; vazio quando não dá para usar (DDD + 8 ou 9 dígitos)."""
    d = so_digitos(texto)
    if d.startswith('55') and len(d) in (12, 13):
        d = d[2:]
    if len(d) not in (10, 11) or d[0] == '0':
        return ''
    if len(d) == 11 and d[2] != '9':
        return ''
    return '55' + d


def nome_do_item(nome: str) -> str:
    """Tira o "- (Vinil Usado)" do fim do nome do produto, que não ajuda na conversa."""
    limpo = re.sub(r'\s*-?\s*\((?:Vinil Usado|Novo/Lacrado|Importado|Usado|\d{4})\)', '', nome or '').strip(' -')
    return limpo or (nome or '').strip()


# ----------------------------------------------------------------------------
# Nome do disco na mensagem: "Álbum (Artista)"
# ----------------------------------------------------------------------------
_PREFIXO_DO_FORMATO = re.compile(r'^(?:\[[^\]]*\]\s*)?(?:LP/EP|Mini-LP|LP|CD|DVD|Box|Compacto-?|EP|Fita(?:\s+K7)?|K7)(?=[\s:\-–]|$)[\s:\-–]*', re.I)
_SEPARADORES = (': ', ' - ', ' – ', ' — ')
_FORMATOS_DE_DISCO = re.compile(r'^(?:\[[^\]]*\]\s*)?(?:LP/EP|Mini-LP|LP|CD|DVD|Box|Compacto|EP|Fita|K7)\b', re.I)


def eh_disco(nome: Any) -> bool:
    """Produto que é disco (LP, CD, compacto, fita...) e não camiseta, combo ou outro item da loja."""
    n = str(nome or '').strip()
    if re.match(r'^(Camiseta|Combo|Ecobag|Poster|Pôster|Moletom|Boné|Cartão|Vale|Gift)\b', n, re.I) or re.search(r'\b(kit|combo)\b', n, re.I):
        return False
    return bool(_FORMATOS_DE_DISCO.match(n)) or bool(re.search(r'\s[-–]\s', n))


def nome_do_disco(nome: Any) -> str:
    """Nome para a mensagem, como "Álbum (Artista)".

    Tira o formato do começo (LP, CD, Box, Compacto...), tudo entre parênteses e o ano do fim.
    "LP Violator - Unholy Retribution (Vinil Usado)" vira "Unholy Retribution (Violator)".
    Sem separador entre artista e álbum, devolve o nome limpo, sem inventar artista.
    """
    n = re.sub(r'\s+', ' ', str(nome or '')).strip()
    n = _PREFIXO_DO_FORMATO.sub('', n, count=1)
    n = re.sub(r'\([^)]*\)', ' ', n)                 # tudo entre parênteses (ano, Vinil Usado, Importado...)
    n = re.sub(r'\([^)]*$', ' ', n)                  # parêntese que ficou aberto no fim do nome
    n = re.sub(r'\s+', ' ', n).strip(' -–—:')
    n = re.sub(r'(?:\s*[-–—]\s*)+$', '', n).strip()  # hifens que sobraram no fim
    achado = [(n.find(s), s) for s in _SEPARADORES if n.find(s) > 0]
    if not achado:
        # hifen sem espaços ("John Lennon-Double Fantasy", "Jorge Ben –A Arte de"): só se as duas pontas forem nomes de verdade
        m = re.match(r'^(.+?)(\s*)[-–—](\s*)(.+)$', n)
        artista, album = ('', n)
        if m:
            a, b = m.group(1).strip(), m.group(4).strip()
            com_espaco = bool(m.group(2) or m.group(3))
            if len(a) >= (2 if com_espaco else 4) and len(b) >= 3:
                artista, album = a, b
    else:
        pos, sep = min(achado)
        artista, album = n[:pos].strip(), n[pos + len(sep):].strip(' -–—:')
    album = _sem_ano_no_fim(album)
    artista = artista.strip()
    if not artista or not album:
        return _sem_ano_no_fim(n) or n
    return f'{album} ({artista})'


def _sem_ano_no_fim(texto: str) -> str:
    """Tira o ano do fim ("Album-1980", "Album - 1980"), mas nunca deixa o nome vazio (álbum "1999" fica)."""
    t = texto.strip()
    if re.fullmatch(r'(?:19|20)\d{2}\s*[-–—/]\s*(?:19|20)\d{2}', t):
        return t  # título que é um período ("1962-1966"), não um ano solto
    sem = re.sub(r'(?:\s*[-–—]\s*|\s+)(?:19|20)\d{2}(?:\s*[-–—/]\s*(?:19|20)\d{2})?$', '', t).strip(' -–—')
    return sem if sem else t


# ----------------------------------------------------------------------------
# Dias da fila (seg a sáb): só nesses dias a fila sai e o prazo entre toques conta
# ----------------------------------------------------------------------------
DIAS_DA_FILA_PADRAO = frozenset({0, 1, 2, 3, 4, 5})  # segunda a sábado
_NOMES_DOS_DIAS = ('seg', 'ter', 'qua', 'qui', 'sex', 'sab', 'dom')
FUSO_LOJA = 'America/Sao_Paulo'


def ler_dias_da_fila(texto: Any) -> frozenset[int]:
    """"seg a sáb", "seg, qua, sex", "todos"... em números de dia (0 = segunda). Texto ilegível volta ao padrão."""
    import unicodedata
    t = unicodedata.normalize('NFKD', str(texto or '')).encode('ascii', 'ignore').decode().lower().strip()
    if not t:
        return DIAS_DA_FILA_PADRAO
    if 'todo' in t or 'diari' in t:
        return frozenset(range(7))
    dias: set[int] = set()
    anterior = None
    intervalo = False
    for token in re.findall(r'seg|ter|qua|qui|sex|sab|dom|\ba\b|ate|-', t):
        if token in _NOMES_DOS_DIAS:
            i = _NOMES_DOS_DIAS.index(token)
            if intervalo and anterior is not None:
                j = anterior
                while True:
                    dias.add(j)
                    if j == i:
                        break
                    j = (j + 1) % 7
                intervalo = False
            else:
                dias.add(i)
            anterior = i
        else:
            intervalo = True
    return frozenset(dias) if dias else DIAS_DA_FILA_PADRAO


def horas_de_fila(inicio: pd.Timestamp, fim: pd.Timestamp, dias: frozenset[int]) -> float:
    """Horas entre `inicio` e `fim` sem contar os dias fora da fila (calendário de Brasília)."""
    a, b = pd.Timestamp(inicio).tz_convert(FUSO_LOJA), pd.Timestamp(fim).tz_convert(FUSO_LOJA)
    if b <= a:
        return 0.0
    if len(dias) >= 7:
        return (b - a).total_seconds() / 3600
    total = 0.0
    dia = a.normalize()
    while dia <= b:
        proximo = (dia + pd.Timedelta(hours=36)).normalize()  # meia-noite seguinte, mesmo na troca de horário
        if dia.weekday() in dias:
            total += (min(b, proximo) - max(a, dia)).total_seconds() / 3600
        dia = proximo
    return max(total, 0.0)


def somar_horas_de_fila(inicio: pd.Timestamp, horas: float, dias: frozenset[int]) -> pd.Timestamp:
    """Momento em que passam `horas` contadas só nos dias da fila."""
    cursor = pd.Timestamp(inicio).tz_convert(FUSO_LOJA)
    if len(dias) >= 7 or not dias:
        return cursor + pd.Timedelta(hours=horas)
    restante = float(horas)
    for _ in range(1000):
        proximo = (cursor.normalize() + pd.Timedelta(hours=36)).normalize()
        if cursor.weekday() in dias:
            disponivel = (proximo - cursor).total_seconds() / 3600
            if restante <= disponivel:
                return cursor + pd.Timedelta(hours=restante)
            restante -= disponivel
        cursor = proximo
    return cursor


def texto_dos_itens(nomes: list[str], maximo: int = 3) -> str:
    """Lista em português ("A, B e C"); passando de `maximo`, mostra os primeiros e "e mais N discos"."""
    nomes = [nome_do_item(n) for n in nomes if n]
    if len(nomes) > maximo:
        return ', '.join(nomes[:maximo - 1]) + f' e mais {len(nomes) - maximo + 1} discos'
    if len(nomes) <= 1:
        return ''.join(nomes)
    return ', '.join(nomes[:-1]) + ' e ' + nomes[-1]


def reais(valor: float) -> str:
    return 'R$ ' + f'{valor:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def no_grupo_de_comparacao(carrinho_id: Any, pct: float, semente: str = 'carrinho') -> bool:
    """Sorteio reproduzível: o mesmo carrinho cai sempre no mesmo grupo (D-020)."""
    h = int(hashlib.sha256(f'{semente}:{carrinho_id}'.encode()).hexdigest(), 16)
    return (h % 10_000) < pct * 100


def montar_mensagem(modelo_texto: str, dados: dict[str, str]) -> tuple[str, list[str]]:
    """Troca os marcadores. Marcador desconhecido fica como está e volta na lista de avisos."""
    desconhecidos: list[str] = []

    def troca(m: re.Match) -> str:
        nome = m.group(1)
        if nome in dados:
            return dados[nome]
        desconhecidos.append(m.group(0))
        return m.group(0)

    return re.sub(r'\{([a-z_]+)\}', troca, modelo_texto), desconhecidos


def link_do_whatsapp(telefone: str, mensagem: str) -> str:
    return f'https://wa.me/{telefone}?text={quote(mensagem, safe="")}' if telefone else ''


# ----------------------------------------------------------------------------
# Nuvemshop (só leitura)
# ----------------------------------------------------------------------------
def buscar_carrinhos(api: NuvemshopAPI) -> list[dict]:
    """Carrinhos abandonados que a API ainda guarda (cerca de 30 dias), só os campos que usamos."""
    campos = CAMPOS_CHECKOUT.split(',')
    return [{k: c.get(k) for k in campos} | {'products': [{k: i.get(k) for k in ('product_id', 'variant_id', 'name', 'price', 'quantity')}
                                                         for i in c.get('products') or []]}
            for c in api.listar('checkouts')]


def estoque_do_produto(api: NuvemshopAPI, produto_id: Any) -> tuple[bool, dict]:
    """(tem estoque agora?, dados) de um produto, direto na API. Produto que sumiu conta como esgotado."""
    resposta = api._get(f'{api._base}/products/{produto_id}', {'fields': 'id,published,categories,variants'}, vazio_se_404=True)
    if resposta is None:
        return False, {}
    produto = resposta.json()
    variantes = produto.get('variants') or []
    if not produto.get('published', True) or not variantes:
        return False, produto
    ok = any((not v.get('stock_management')) or (v.get('stock') or 0) > 0 for v in variantes)
    return ok, produto


def conferir_estoque(api: NuvemshopAPI, itens: list[dict], cache: dict | None = None) -> tuple[str, dict]:
    """OK se todos os itens têm estoque, Parcial se só alguns, Esgotado se nenhum. Devolve também os produtos."""
    cache = cache if cache is not None else {}
    tem = []
    for i in itens:
        pid = i.get('product_id')
        if pid not in cache:
            cache[pid] = estoque_do_produto(api, pid)
        tem.append(cache[pid][0])
    if all(tem):
        return 'OK', cache
    return ('Esgotado' if not any(tem) else 'Parcial'), cache


# ----------------------------------------------------------------------------
# Regras de decisão
# ----------------------------------------------------------------------------
def _instante(valor: Any) -> pd.Timestamp:
    return pd.to_datetime(valor, utc=True)


def escolher_modelo(proximo_toque: int, valor: float, estoque: str, params: Parametros, *, unico_usado: bool,
                    ja_comprou: bool, vip: bool, custo_frete: float | None = None) -> str:
    """Modelo pelo próximo toque (AGENTS.md). VIP e cliente frequente nunca recebem modelo com cupom."""
    if estoque != 'OK':
        return 'ESGOTADO'
    if proximo_toque <= 1:
        return 'T1_UNICO' if unico_usado else ('T1_RECORRENTE' if ja_comprou else 'T1')
    if proximo_toque == 2:
        modelo = 'T2_FRETE' if (valor >= params.minimo_frete_gratis and custo_frete is not None
                                and 0 < custo_frete <= params.maximo_custo_frete) else (
                                'T3_CUPOM' if valor >= params.minimo_cupom else 'T2_ESCASSEZ')
    else:
        modelo = 'T3_CUPOM' if valor >= params.minimo_cupom else 'T2_ESCASSEZ'
    return 'T2_ESCASSEZ' if (vip and modelo in MODELOS_COM_CUPOM) else modelo


def custo_frete_da_loja(checkout: dict, api: NuvemshopAPI) -> tuple[float | None, str]:
    """Só usa shipping_cost_owner documentado; nunca estima pelo frete do cliente."""
    dados = checkout
    if checkout.get('shipping_cost_owner') in (None, ''):
        try:
            r = api._get(f'{api._base}/checkouts/{checkout["id"]}')
            dados = r.json() if r is not None else {}
        except Exception:
            return None, 'consulta do custo do frete indisponível'
    if dados.get('currency') != 'BRL':
        return None, 'moeda do frete não confirmada em BRL'
    if dados.get('shipping_pickup_type') == 'pickup':
        return None, 'retirada na loja não recebe benefício de frete'
    custo = pd.to_numeric(dados.get('shipping_cost_owner'), errors='coerce')
    if pd.isna(custo) or not (0 < float(custo) < float('inf')):
        return None, 'custo do frete da loja ausente, inválido ou já gratuito'
    return float(custo), ''


def cotar_frete_do_carrinho(checkout: dict, api: NuvemshopAPI) -> tuple[float | None, str]:
    """Preço cotado ao cliente, só GET; não guarda JWT nem altera opção/endereço."""
    base = api._base.rsplit('/', 2)
    url = f'{base[0]}/unstable/{base[-1]}/carts/{checkout["id"]}/shipping/quotations'
    try:
        resposta = api._get(url)
        dados = resposta.json() if resposta is not None else {}
        opcoes = dados.get('options', [])
        custos = []
        for o in opcoes:
            preco = o.get('price') or {}
            if o.get('type') != 'ship' or preco.get('currency') != 'BRL':
                continue
            v = pd.to_numeric(preco.get('value'), errors='coerce')
            if pd.notna(v) and 0 <= float(v) < float('inf'):
                custos.append(float(v))
        if not custos:
            return None, 'sem opção de entrega cotada em BRL; retirada não conta'
        menor = min(custos)
        if menor == 0:
            return None, 'entrega já gratuita: não oferecer novo benefício de frete'
        return menor, f'frete cotado ao cliente (entrega mais barata): {reais(menor)}'
    except Exception:
        return None, 'cotação de frete indisponível: sem oferta de frete grátis'


def montar_fila(carrinhos: list[dict], tabelas: Tabelas, params: Parametros, agora: datetime, api: NuvemshopAPI,
                bloqueio: set[str] | None = None, estado: dict[str, dict] | None = None) -> tuple[list[LinhaDaFila], Counter]:
    """Aplica os filtros do AGENTS.md e devolve (fila, motivos de quem ficou de fora).

    `bloqueio`: emails e telefones (só dígitos) que não querem receber. `estado`: por carrinho, o que a
    Mariana já registrou (`toques`, `ultimo_envio`, `status`); fica vazio na primeira vez.
    """
    agora_ts = pd.Timestamp(agora).tz_convert('UTC') if pd.Timestamp(agora).tzinfo else pd.Timestamp(agora, tz='UTC')
    bloqueio = {b.lower() if '@' in b else so_digitos(b) for b in (bloqueio or set()) if b}
    estado = estado or {}
    motivos: Counter = Counter()

    clientes = tabelas.clientes.drop_duplicates('email', keep='last').set_index('email')
    tel_para_email = {telefone_whatsapp(t): e for e, t in clientes['telefone'].items() if telefone_whatsapp(t)}
    validos = tabelas.pedidos[tabelas.pedidos['valido'].astype(bool)]
    compras_por_email: dict[str, list[pd.Timestamp]] = {}
    for email_pedido, data in zip(validos['email'], pd.to_datetime(validos['data'])):
        momento = pd.Timestamp(data).tz_localize('America/Sao_Paulo', nonexistent='shift_forward', ambiguous=True)
        compras_por_email.setdefault(email_pedido, []).append(momento)

    # Um por cliente (o mais recente), contando por email e, na falta dele, pelo telefone.
    candidatos: dict[str, dict] = {}
    for c in carrinhos:
        if c.get('completed_at'):
            motivos['carrinho já virou pedido'] += 1
            continue
        email = (c.get('contact_email') or '').strip().lower()
        fone = telefone_whatsapp(c.get('contact_phone'))
        chave = email or fone or f'id:{c["id"]}'
        c = {**c, '_email': email, '_fone': fone, '_quando': _instante(c.get('updated_at') or c.get('created_at'))}
        if chave in candidatos:
            motivos['cliente com carrinho mais novo'] += 1
            if c['_quando'] <= candidatos[chave]['_quando']:
                continue
        candidatos[chave] = c

    fila: list[LinhaDaFila] = []
    produtos_cache: dict = {}
    for c in sorted(candidatos.values(), key=lambda x: x['_quando'], reverse=True):
        email, fone, quando = c['_email'], c['_fone'], c['_quando']
        email_cliente = email or tel_para_email.get(fone, '')
        horas = (agora_ts - quando).total_seconds() / 3600
        horas_uteis = horas_de_fila(quando, agora_ts, params.dias_da_fila)  # dias fora da fila não contam prazo
        if horas_uteis < params.comecar_depois_de_horas:
            motivos['ainda cedo (o email da Nuvemshop sai primeiro)'] += 1
            continue
        if horas_uteis > params.parar_depois_de_dias * 24:
            motivos['carrinho velho demais'] += 1
            continue
        if (email and email in bloqueio) or (fone and fone in bloqueio):
            motivos['na aba Bloqueio'] += 1
            continue
        cadastro = clientes.loc[email_cliente] if email_cliente in clientes.index else None
        if cadastro is not None and not bool(cadastro['aceita_marketing']):
            motivos['não aceita marketing'] += 1
            continue
        compras = compras_por_email.get(email_cliente, [])
        if any(t >= quando for t in compras):
            motivos['já comprou depois do carrinho'] += 1
            continue
        valor = float(pd.to_numeric(c.get('total') or c.get('subtotal'), errors='coerce') or 0)
        if valor < params.valor_minimo_do_carrinho:
            motivos['abaixo do valor mínimo'] += 1
            continue

        itens = c.get('products') or []
        estoque, produtos_cache = conferir_estoque(api, itens, produtos_cache)
        conferido = pd.Timestamp(agora_ts)
        categorias = [' '.join(str(_pt((x or {}).get('name'))) for x in (produtos_cache[i.get('product_id')][1].get('categories') or [])) for i in itens]
        # "Exemplar único usado": categoria usado, no máximo 1 em estoque e o nome não diz que é novo ou lacrado.
        unico_usado = bool(itens) and all(
            'usado' in k.lower() and not re.search(r'novo|lacrad', str(i.get('name') or ''), re.I)
            and sum(v.get('stock') or 0 for v in produtos_cache[i.get('product_id')][1].get('variants') or []) <= 1
            for i, k in zip(itens, categorias))
        tem_consignado = any(re.search(r'consign|etiqueta\s+prata', k + ' ' + str(i.get('name') or ''), re.I)
                            for i, k in zip(itens, categorias))
        n_compras = len(compras)
        vip = n_compras >= REGUA.vip_min_compras or (cadastro is not None and float(cadastro['total_consumido']) >= REGUA.vip_min_gasto)

        ja = estado.get(str(c['id']), {})
        toques = int(ja.get('toques') or 0)
        if 'T3_CUPOM' in (ja.get('modelos_enviados') or []):
            motivos['oferta final de 10% já enviada'] += 1
            continue
        if toques >= params.maximo_de_toques or ja.get('status') in ('Recuperado', 'Não quer', 'Contato inválido', 'Respondeu'):
            motivos['encerrado (toques esgotados, recuperado ou não quer)'] += 1
            continue
        proximo = toques + 1
        escolhido = ja.get('modelo_escolhido') or ''
        valor_produtos = pd.to_numeric(c.get('subtotal'), errors='coerce') - pd.to_numeric(c.get('discount') or 0, errors='coerce')
        custo_frete, aviso_frete = None, ''
        if (proximo == 2 or escolhido == 'T2_FRETE') and estoque == 'OK' and valor_produtos >= params.minimo_frete_gratis and not vip:
            custo_frete, aviso_frete = cotar_frete_do_carrinho(c, api)
            if custo_frete is not None:
                aviso_frete += f'; teto para oferecer: {reais(params.maximo_custo_frete)}'
        modelo = escolher_modelo(proximo, valor_produtos, estoque, params, unico_usado=unico_usado,
                                ja_comprou=n_compras > 0, vip=vip, custo_frete=custo_frete)
        if escolhido and estoque == 'OK' and escolhido in params.modelos:
            modelo = escolhido  # a Mariana trocou o modelo na planilha (item esgotado nunca troca)
        # Escolha manual do modelo não pode contornar o teto ou a ausência de cotação.
        if modelo == 'T2_FRETE' and (custo_frete is None or
                not (0 < custo_frete <= params.maximo_custo_frete) or not valor_produtos >= params.minimo_frete_gratis or vip):
            modelo = 'T3_CUPOM' if valor_produtos >= params.minimo_cupom and not vip else 'T2_ESCASSEZ'
        beneficio_consignado = modelo in MODELOS_COM_CUPOM and tem_consignado
        if modelo == 'T3_CUPOM' and (not valor_produtos >= params.minimo_cupom or vip):
            modelo = 'T2_ESCASSEZ'
        if beneficio_consignado:
            modelo = 'T2_ESCASSEZ'
        if modelo == 'T2_ESCASSEZ' and not unico_usado:
            modelo = 'T2_LEMBRETE'
        cupom = params.cupom_frete if modelo == 'T2_FRETE' else (params.cupom_desconto if modelo == 'T3_CUPOM' else '')

        nome_completo = (c.get('contact_name') or '').strip()
        primeiro = (nome_completo.split() or [''])[0].title()
        observacoes: list[str] = []
        if aviso_frete:
            observacoes.append(aviso_frete)
        if beneficio_consignado:
            observacoes.append('benefício não oferecido: carrinho contém consignado de etiqueta prata')
        link_carrinho = '' if modelo == 'ESGOTADO' else (c.get('abandoned_checkout_url') or '')
        texto_modelo = params.modelos.get(modelo, '')
        dados = {'nome': primeiro or 'tudo bem', 'itens': texto_dos_itens([i.get('name') for i in itens]), 'valor': reais(valor),
                 'link_carrinho': link_carrinho, 'cupom': cupom, 'prazo': params.prazo, 'assinatura': params.assinatura,
                 'loja': params.site}
        mensagem, desconhecidos = montar_mensagem(texto_modelo, dados)
        if desconhecidos:
            observacoes.append('marcador desconhecido: ' + ', '.join(sorted(set(desconhecidos))))
        if not texto_modelo:
            observacoes.append(f'modelo {modelo} não existe na aba Mensagens')
        if proximo == 2 and modelo == 'T3_CUPOM':
            observacoes.append('10% antecipados no segundo envio; último toque deste ciclo')
        if modelo == 'T2_FRETE':
            # Condição legível: benefício só para a entrega econômica cotada.
            mensagem += ' O frete grátis vale para a opção de entrega mais econômica cotada para este carrinho.'

        situacao = 'Contatar'
        if not fone:
            situacao = 'Telefone inválido'
            observacoes.append('telefone inválido: sem link do WhatsApp')
        elif no_grupo_de_comparacao(c['id'], params.comparacao_pct):
            situacao = 'Grupo de comparação'
            observacoes.append('só recebe o email da Nuvemshop (mede o que o WhatsApp acrescenta)')
        elif cupom and params.cupom_precisa_de_aprovacao:
            situacao = 'Aguardar aprovação'
        ultimo = ja.get('ultimo_envio')
        proximo_envio = (somar_horas_de_fila(ultimo, params.intervalo_entre_toques_horas, params.dias_da_fila)
                         if ultimo is not None else None)
        if situacao == 'Contatar' and proximo_envio is not None and agora_ts < proximo_envio:
            situacao = 'Aguardar intervalo'
        fila.append(LinhaDaFila(
            carrinho=str(c['id']), abandonado_em=quando, cliente=nome_completo, primeiro_nome=primeiro, telefone=fone,
            email=email, itens=dados['itens'], valor=valor, link=c.get('abandoned_checkout_url') or '', estoque=estoque,
            estoque_conferido_em=conferido, horas=round(horas, 1), toques_enviados=toques, proximo_toque=proximo,
            modelo=modelo, cupom=cupom, situacao=situacao, mensagem=mensagem,
            link_whatsapp=link_do_whatsapp(fone, mensagem) if situacao in ('Contatar', 'Aguardar aprovação', 'Aguardar intervalo') else '',
            observacoes='; '.join(observacoes), proximo_envio=proximo_envio))
    return fila, motivos


# ----------------------------------------------------------------------------
# Linha de comando: mostra a fila de hoje, sem gravar nada
# ----------------------------------------------------------------------------
def _mascarar(telefone: str) -> str:
    return f'{telefone[:4]}*****{telefone[-2:]}' if len(telefone) >= 8 else telefone


@comando_seguro
def main(argv: list[str] | None = None) -> int:
    import argparse
    import os
    from painel_monstro.config import RAIZ_PROJETO, carregar
    from painel_monstro.coletor import nuvemshop_api as nuvem

    parser = ArgumentParserSeguro(description='Mostra a fila de carrinhos de hoje (não grava na planilha).')
    parser.add_argument('--hoje', action='store_true', help='mostra a fila de hoje')
    parser.add_argument('--exemplos', type=int, default=6, help='quantas mensagens mostrar completas')
    args = parser.parse_args(argv)
    if not args.hoje:
        parser.print_help()
        return 0
    config = carregar()
    api = NuvemshopAPI(config)
    armazem = nuvem.Armazem()
    tabelas = nuvem.montar_tabelas(*(list(armazem.registros(r).values()) for r in ('pedidos', 'clientes', 'produtos')))
    try:
        carrinhos = buscar_carrinhos(api)
        fila, motivos = montar_fila(carrinhos, tabelas, Parametros(), datetime.now(timezone.utc), api)
    except ErroAPI as erro:
        print('ERRO: ' + resumo_erro(erro))
        return 1
    print(f'Carrinhos que a Nuvemshop guarda: {len(carrinhos)}')
    for motivo, n in motivos.most_common():
        print(f'  Fora da fila: {n} carrinhos')
    print(f'Na fila: {len(fila)}')
    por_situacao = Counter(l.situacao for l in fila)
    por_modelo = Counter(l.modelo for l in fila)
    print('Contagem por situação disponível no arquivo privado.')
    print('Contagem por modelo disponível no arquivo privado.')
    pasta = os.path.join(RAIZ_PROJETO, 'dados', 'carrinhos')
    os.makedirs(pasta, exist_ok=True)
    caminho = os.path.join(pasta, 'fila-de-hoje.csv')
    pd.DataFrame([l.__dict__ for l in fila]).to_csv(caminho, index=False, encoding='utf-8-sig', sep=';')
    print('Fila completa gravada em arquivo privado fora do git.')
    mostradas = 0
    for l in fila:
        if l.situacao != 'Contatar' or mostradas >= args.exemplos:
            continue
        mostradas += 1
        print('Prévia individual omitida do log público; conferir arquivo privado.')
        print('Mensagem disponível somente no arquivo privado.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
