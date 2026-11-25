"""Régua automática no Brevo (Etapa 7). SEMPRE em modo teste até o Túlio escrever "pode desligar o modo teste".

O que faz, uma vez por dia:
  1. Calcula, para cada cliente, a etapa da régua, os dias sem comprar, a família de gênero, se é VIP e se está
     no grupo de controle, e a lista do Brevo em que ele deve estar (nenhuma, se for controle ou VIP).
  2. Compara com o que já está no Brevo e monta o plano: atributos a atualizar, listas a acrescentar e a tirar.
  3. Em modo teste só MOSTRA o plano (abas `brevo_plano` e `brevo_mudancas`). Fora do modo teste aplica o plano.

O Painel nunca dispara email: ele só atualiza atributos e listas; quem envia são as automações do Brevo.

Segurança:
- Em modo teste, qualquer escrita levanta `BrevoModoTeste` (barreira dentro do cliente, não só na rotina).
- A chave só vai no cabeçalho `api-key` e nunca aparece em mensagens, logs nem arquivos.
- Contato descadastrado no Brevo (`emailBlacklisted`) e quem não aceita marketing na Nuvemshop nunca são tocados.
- Só atualiza contatos que já existem no Brevo: não cria contato novo (consentimento é do Brevo).
- O Brevo desativa a chave depois de 90 dias sem chamada bem-sucedida: a rotina lê a conta a cada rodada.
"""
from __future__ import annotations

import hashlib
import re
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Callable, Iterator
from urllib.parse import quote

import pandas as pd
import requests

from painel_monstro.coletor.planilhas_csv import Tabelas
from painel_monstro.motor import generos
from painel_monstro.motor import regua as motor_regua

URL_BASE = 'https://api.brevo.com/v3'
POR_PAGINA = 1000
ATRIBUTOS = {'ETAPA': 'text', 'DIAS_SEM_COMPRAR': 'float', 'FAMILIA': 'text', 'VIP': 'boolean', 'CONTROLE': 'boolean',
             'CUPOM': 'text', 'CUPOM_ATE': 'text'}  # CUPOM e CUPOM_ATE só são gravados quando o contato ENTRA na lista da Etapa 2 ou 3
MESES = ('JAN', 'FEV', 'MAR', 'ABR', 'MAI', 'JUN', 'JUL', 'AGO', 'SET', 'OUT', 'NOV', 'DEZ')
CODIGOS_DAS_ETAPAS = ['ETAPA_0', 'ETAPA_1', 'ETAPA_2', 'ETAPA_3']   # na ordem de ParametrosRegua.etapas
CODIGO_VIP, CODIGO_DESCANSO, CODIGO_SEM_ETAPA = 'VIP', 'DESCANSO', 'SEM_ETAPA'
LISTAS_PADRAO = ['Painel · Etapa 0 Pós-compra', 'Painel · Etapa 1 Lembrete', 'Painel · Etapa 2 Convite', 'Painel · Etapa 3 Última chamada']
LIMITE_REMOVER = 150  # emails por chamada de remoção de lista


class ErroBrevo(Exception):
    """Falha ao falar com o Brevo. `tipo`: chave_invalida, bloqueio_ip, limite, rede ou outro. Nunca contém a chave."""

    def __init__(self, tipo: str, detalhe: str):
        super().__init__(detalhe)
        self.tipo, self.detalhe = tipo, detalhe


class BrevoModoTeste(Exception):
    """Tentativa de escrever no Brevo com o modo teste ligado."""


class Brevo:
    def __init__(self, chave: str, modo_teste: bool = True, sessao: Any = None, dormir: Callable[[float], None] = time.sleep,
                 max_tentativas: int = 4):
        if not chave:
            raise ErroBrevo('chave_invalida', 'Falta BREVO_API_KEY no .env ou nos Secrets.')
        self._chave = chave
        self.modo_teste = modo_teste
        self._sessao = sessao or requests.Session()
        self._dormir = dormir
        self._max = max_tentativas

    def __repr__(self) -> str:  # a chave nunca aparece
        return f'Brevo(modo_teste={self.modo_teste})'

    # --- HTTP
    def _limpar(self, texto: Any) -> str:
        return str(texto).replace(self._chave, '***')[:300]

    def _pedir(self, metodo: str, caminho: str, params: dict | None = None, corpo: Any = None) -> Any:
        url = URL_BASE + caminho
        cabecalhos = {'api-key': self._chave, 'accept': 'application/json'}
        if corpo is not None:
            cabecalhos['content-type'] = 'application/json'
        for tentativa in range(1, self._max + 1):
            try:
                r = self._sessao.request(metodo, url, headers=cabecalhos, params=params, json=corpo, timeout=90)
            except requests.RequestException as erro:
                if tentativa == self._max:
                    raise ErroBrevo('rede', f'Falha de rede ao falar com o Brevo ({type(erro).__name__}).') from None
                self._dormir(2 ** tentativa)
                continue
            if r.status_code == 429 or r.status_code >= 500:
                if tentativa == self._max:
                    raise ErroBrevo('limite' if r.status_code == 429 else 'outro', f'O Brevo respondeu {r.status_code} depois de {tentativa} tentativas.')
                self._dormir(max(float(r.headers.get('retry-after', 0) or 0), 2 ** tentativa))
                continue
            if r.status_code in (401, 403):
                try:
                    msg = str(r.json().get('message', ''))
                except ValueError:
                    msg = r.text
                baixa = msg.lower()
                if 'ip' in baixa and any(p in baixa for p in ('unrecogni', 'authori', 'whitelist', 'not allowed', 'blocked', 'address')):
                    raise ErroBrevo('bloqueio_ip', 'O Brevo bloqueou o acesso por endereço de IP. Desative o bloqueio de IP das chaves de API no Brevo.')
                raise ErroBrevo('chave_invalida', 'O Brevo recusou a chave (inválida, desativada ou sem permissão).')
            if r.status_code >= 400:
                try:
                    msg = r.json().get('message', '')
                except ValueError:
                    msg = r.text
                raise ErroBrevo('outro', f'O Brevo respondeu {r.status_code}; conteúdo da resposta omitido.')
            if r.status_code == 204 or not r.content:
                return {}
            try:
                return r.json()
            except ValueError:
                return {}
        raise ErroBrevo('outro', 'Não consegui falar com o Brevo.')  # inalcançável

    # --- leituras (sempre permitidas)
    def receita_periodo(self, inicio: str, fim: str) -> float:
        """Receita atribuída pelo Brevo no período (campanhas e automações), sem somar fontes duplicadas."""
        import math
        d = self._pedir('GET', '/ecommerce/attribution/metrics', {'periodFrom': inicio, 'periodTo': fim})
        try:
            valor = float(d['totals']['revenue'])
        except (KeyError, TypeError, ValueError):
            raise ErroBrevo('outro', 'Relatório de receita sem total válido.') from None
        if not math.isfinite(valor) or valor < 0:
            raise ErroBrevo('outro', 'Relatório de receita com total inválido.')
        return round(valor, 2)

    def conta(self) -> dict:
        """Dados da conta. É a "leitura simples" que mantém a chave viva (90 dias sem chamada a desativam)."""
        return self._pedir('GET', '/account')

    def listas(self) -> list[dict]:
        saida, offset = [], 0
        while True:
            d = self._pedir('GET', '/contacts/lists', {'limit': 50, 'offset': offset})
            pagina = d.get('lists') or []
            saida += pagina
            if len(pagina) < 50:
                return saida
            offset += 50

    def atributos(self) -> list[dict]:
        return self._pedir('GET', '/contacts/attributes').get('attributes') or []

    def contatos(self) -> Iterator[dict]:
        offset = 0
        while True:
            d = self._pedir('GET', '/contacts', {'limit': POR_PAGINA, 'offset': offset})
            pagina = d.get('contacts') or []
            yield from pagina
            if len(pagina) < POR_PAGINA:
                return
            offset += POR_PAGINA

    def contatos_do_segmento(self, segmento_id: int) -> Iterator[dict]:
        """Contatos de um segmento criado no Brevo (leitura)."""
        offset = 0
        while True:
            d = self._pedir('GET', '/contacts', {'limit': POR_PAGINA, 'offset': offset, 'segmentId': segmento_id})
            pagina = d.get('contacts') or []
            yield from pagina
            if len(pagina) < POR_PAGINA:
                return
            offset += POR_PAGINA

    def contato(self, email: str) -> dict | None:
        """Um contato pelo email, ou None se ele não existe no Brevo."""
        try:
            return self._pedir('GET', f'/contacts/{quote(email, safe="")}', {'identifierType': 'email_id'})
        except ErroBrevo as erro:
            if erro.tipo == 'outro' and erro.detalhe.startswith('O Brevo respondeu 404'):
                return None
            raise

    # --- escritas (recusadas em modo teste)
    def _escrever(self, metodo: str, caminho: str, corpo: Any) -> Any:
        if self.modo_teste:
            raise BrevoModoTeste('Modo teste ligado: nada é escrito no Brevo.')
        return self._pedir(metodo, caminho, corpo=corpo)

    def criar_atributo(self, nome: str, tipo: str) -> Any:
        return self._escrever('POST', f'/contacts/attributes/normal/{nome}', {'type': tipo})

    def remover_da_lista(self, lista_id: int, emails: list[str]) -> Any:
        return self._escrever('POST', f'/contacts/lists/{lista_id}/contacts/remove', {'emails': emails})

    def atualizar_contato(self, email: str, atributos: dict[str, Any]) -> Any:
        """Atualiza os atributos de UM contato na hora (a importação em lote é assíncrona e a automação dispara na entrada na lista)."""
        return self._escrever('PUT', f'/contacts/{quote(email, safe="")}?identifierType=email_id', {'attributes': atributos})

    def criar_contato(self, email: str, atributos: dict[str, Any]) -> Any:
        """Cria um contato. Só usado para quem aceitou receber novidades na página da raspadinha (D-071)."""
        return self._escrever('POST', '/contacts', {'email': email, 'attributes': atributos, 'updateEnabled': False})

    def adicionar_a_lista(self, lista_id: int, emails: list[str]) -> Any:
        return self._escrever('POST', f'/contacts/lists/{lista_id}/contacts/add', {'emails': emails})


# ----------------------------------------------------------------------------
# Alvo: o que cada cliente deveria ter no Brevo
# ----------------------------------------------------------------------------
def em_controle(email: str, codigo_etapa: str, ultima_compra: Any, percentual: float) -> bool:
    """Sorteio do controle: estável por cliente e por ciclo (muda só quando ele compra de novo), nunca diário."""
    chave = f'brevo:{codigo_etapa}:{str(email).strip().lower()}:{pd.Timestamp(ultima_compra).date()}'
    return int(hashlib.sha256(chave.encode()).hexdigest(), 16) % 10_000 < percentual * 10_000


def alvo_dos_clientes(classificacao: pd.DataFrame, tabelas: Tabelas, params: motor_regua.ParametrosRegua = motor_regua.PADRAO,
                      listas_por_codigo: dict[str, str] | None = None) -> pd.DataFrame:
    """Uma linha por cliente (índice = email) com ETAPA, DIAS_SEM_COMPRAR, FAMILIA, VIP, CONTROLE e `lista`.

    Só entram clientes que aceitam marketing (a base da régua já filtra). Controle e VIP não entram em lista de email.
    """
    listas_por_codigo = listas_por_codigo or dict(zip(CODIGOS_DAS_ETAPAS, LISTAS_PADRAO))
    codigo_da_etapa = {e.nome: CODIGOS_DAS_ETAPAS[i] for i, e in enumerate(params.etapas[:len(CODIGOS_DAS_ETAPAS)])}
    codigo_da_etapa[params.vip.nome] = CODIGO_VIP
    codigo_da_etapa[motor_regua.DESCANSO] = CODIGO_DESCANSO
    tem_controle = {codigo_da_etapa[e.nome]: e.tem_controle for e in params.etapas[:len(CODIGOS_DAS_ETAPAS)]}

    it = tabelas.itens[tabelas.itens['valido'].astype(bool)]
    familias_do_cliente: dict[str, str] = {}
    if len(it):
        from painel_monstro.motor.indicadores import _produto_de_cada_item
        produto = _produto_de_cada_item(it, tabelas.produtos)
        pares = list(zip(it['email'], produto['categorias'].reindex(it.index), it['produto']))
        por_email: dict[str, list[set[str]]] = {}
        for email, cat, nome in pares:
            por_email.setdefault(str(email), []).append(generos.familias(cat, nome))
        familias_do_cliente = {e: (generos.familia_principal(f) or 'Variado') for e, f in por_email.items()}

    linhas = []
    for email, r in classificacao.iterrows():
        codigo = codigo_da_etapa.get(str(r['etapa']), CODIGO_SEM_ETAPA)
        controle = False
        lista = ''
        if codigo in CODIGOS_DAS_ETAPAS:
            if tem_controle.get(codigo) and str(r['grupo']) in ('envio', 'controle'):
                controle = em_controle(email, codigo, r['ultima'], params.controle)
            lista = '' if controle else listas_por_codigo.get(codigo, '')
        linhas.append({'email': str(email).strip().lower(), 'ETAPA': codigo, 'DIAS_SEM_COMPRAR': int(r['dias']),
                       'FAMILIA': familias_do_cliente.get(str(email), 'Variado'), 'VIP': bool(r['vip']),
                       'CONTROLE': bool(controle), 'lista': lista})
    return pd.DataFrame(linhas).set_index('email') if linhas else pd.DataFrame(
        columns=['ETAPA', 'DIAS_SEM_COMPRAR', 'FAMILIA', 'VIP', 'CONTROLE', 'lista'])


# ----------------------------------------------------------------------------
# Política da régua: chave de pausa, pausa programada e etapas ligadas (aba Configuração, D-052)
# ----------------------------------------------------------------------------
CHAVE_REGUA = 'Régua no Brevo'
CHAVE_PAUSA_DE = 'Pausa programada de'
CHAVE_PAUSA_ATE = 'Pausa programada até'
CHAVES_DAS_ETAPAS = {'ETAPA_0': 'Etapa 0 no Brevo', 'ETAPA_1': 'Etapa 1 no Brevo', 'ETAPA_2': 'Etapa 2 no Brevo', 'ETAPA_3': 'Etapa 3 no Brevo'}


def _norm(texto: Any) -> str:
    return unicodedata.normalize('NFKD', str(texto or '')).encode('ascii', 'ignore').decode().lower().strip()


def ler_data(valor: Any) -> tuple[date | None, bool]:
    """(data, valida). Vazio = (None, True). Aceita dd/mm/aaaa, aaaa-mm-dd, data da planilha (número de série) e Timestamp."""
    if valor is None or (isinstance(valor, float) and valor != valor) or str(valor).strip() == '':
        return None, True
    if isinstance(valor, (pd.Timestamp, datetime)):
        return valor.date(), True
    if isinstance(valor, date):
        return valor, True
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        if 20000 < float(valor) < 100000:  # número de série das células de data do Google Sheets
            return (datetime(1899, 12, 30) + timedelta(days=float(valor))).date(), True
        return None, False
    texto = str(valor).strip()
    m = re.fullmatch(r'(\d{1,2})/(\d{1,2})/(\d{4})', texto)
    try:
        if m:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1))), True
        m = re.fullmatch(r'(\d{4})-(\d{2})-(\d{2})(?:[ T].*)?', texto)
        if m:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))), True
    except ValueError:
        return None, False
    return None, False


@dataclass(frozen=True)
class PoliticaRegua:
    """Quando a régua pode mexer nas listas do Brevo. O que não for entendido vira o mais seguro (pausada/desligada)."""
    ligada: bool = False
    pausa_de: date | None = None
    pausa_ate: date | None = None
    etapas_ligadas: frozenset = frozenset()
    avisos: tuple = ()

    def em_pausa_programada(self, hoje: date) -> bool:
        return self.pausa_de is not None and self.pausa_ate is not None and self.pausa_de <= hoje <= self.pausa_ate

    def pausada(self, hoje: date) -> bool:
        return (not self.ligada) or self.em_pausa_programada(hoje)

    def estado(self, hoje: date) -> str:
        if not self.ligada:
            return 'Pausada'
        if self.em_pausa_programada(hoje):
            return f'Em pausa programada até {self.pausa_ate:%d/%m}'
        return 'Ligada'

    def etapas_texto(self) -> str:
        nomes = [f'Etapa {c[-1]}' for c in CODIGOS_DAS_ETAPAS if c in self.etapas_ligadas]
        return ', '.join(nomes) if nomes else 'nenhuma'


def ler_politica(config: dict[str, Any]) -> PoliticaRegua:
    """Lê as linhas da aba Configuração (nomes exatos, sem diferenciar maiúsculas, minúsculas e acentos)."""
    c = {_norm(k): v for k, v in config.items()}
    avisos: list[str] = []

    def chave(nome: str) -> Any:
        return c.get(_norm(nome), None)

    valor = _norm(chave(CHAVE_REGUA))
    if valor in ('ligada', 'ligado'):
        ligada = True
    elif valor in ('pausada', 'pausado'):
        ligada = False
    else:
        ligada = False
        avisos.append(f'"{CHAVE_REGUA}" ' + ('ausente' if chave(CHAVE_REGUA) is None else f'com valor inválido ({chave(CHAVE_REGUA)})') +
                      ': régua tratada como Pausada.')
    de, ok_de = ler_data(chave(CHAVE_PAUSA_DE))
    ate, ok_ate = ler_data(chave(CHAVE_PAUSA_ATE))
    if not (ok_de and ok_ate) or (de is None) != (ate is None) or (de and ate and de > ate):
        avisos.append('Pausa programada inválida (datas ilegíveis, só uma das duas preenchida ou fim antes do início): régua tratada como Pausada.')
        ligada, de, ate = False, None, None
    etapas = set()
    for codigo, nome in CHAVES_DAS_ETAPAS.items():
        v = _norm(chave(nome))
        if v in ('ligada', 'ligado', 'sim'):
            etapas.add(codigo)
        elif v in ('desligada', 'desligado', 'nao'):
            pass
        else:
            avisos.append(f'"{nome}" ' + ('ausente' if chave(nome) is None else f'com valor inválido ({chave(nome)})') + ': etapa tratada como Desligada.')
    return PoliticaRegua(ligada, de, ate, frozenset(etapas), tuple(avisos))


def mes_abreviado(dia: date) -> str:
    return MESES[dia.month - 1]


def cupom_do_mes(modelo: str, dia: date) -> str:
    """"VOLTAFRETE<MÊS>" em outubro vira "VOLTAFRETEOUT"."""
    return re.sub(r'<\s*M[ÊE]S\s*>', mes_abreviado(dia), str(modelo or ''), flags=re.I).strip()


# ----------------------------------------------------------------------------
# Plano: alvo contra o que existe no Brevo
# ----------------------------------------------------------------------------
@dataclass
class Plano:
    atualizar: dict[str, dict[str, Any]] = field(default_factory=dict)     # email -> atributos novos
    entrar_na_lista: dict[str, list[str]] = field(default_factory=dict)    # nome da lista -> emails
    sair_da_lista: dict[str, list[str]] = field(default_factory=dict)      # nome da lista -> emails
    mudancas: list[dict[str, Any]] = field(default_factory=list)           # só o que muda de etapa, lista ou controle
    resumo: dict[str, Any] = field(default_factory=dict)
    listas_ausentes: list[str] = field(default_factory=list)
    atributos_ausentes: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def planejar(alvo: pd.DataFrame, contatos: dict[str, dict], listas: dict[str, int], atributos_existentes: set[str],
             listas_da_regua: list[str] | None = None, politica: PoliticaRegua | None = None, hoje: date | None = None,
             codigo_da_lista: dict[str, str] | None = None, cupons: dict[str, tuple[str, int]] | None = None) -> Plano:
    """`contatos`: email -> contato do Brevo (id, listIds, emailBlacklisted, attributes). `listas`: nome -> id.

    `politica` (None = tudo ligado, só para testes de unidade): régua pausada congela as listas (ninguém entra nem sai);
    etapa desligada impede entrada na lista dela (a saída segue a regra normal). Os atributos sempre atualizam.
    `cupons`: código da etapa -> (modelo do cupom com <MÊS>, validade em dias); só quem ENTRA na lista da Etapa 2 ou 3
    ganha CUPOM e CUPOM_ATE.
    """
    hoje = hoje or date.today()
    listas_da_regua = list(listas_da_regua or LISTAS_PADRAO)
    codigo_da_lista = codigo_da_lista or dict(zip(LISTAS_PADRAO, CODIGOS_DAS_ETAPAS))
    ids_da_regua = {listas[n]: n for n in listas_da_regua if n in listas}
    p = Plano()
    p.listas_ausentes = [n for n in listas_da_regua if n not in listas]
    p.atributos_ausentes = [a for a in ATRIBUTOS if a not in atributos_existentes]
    pausada = politica.pausada(hoje) if politica is not None else False
    r = {'clientes na régua': len(alvo), 'não estão no Brevo (não são criados)': 0, 'descadastrados (não mexe)': 0,
         'atributos a atualizar': 0, 'entram em lista': 0, 'saem de lista': 0, 'controle (sem lista)': int(alvo['CONTROLE'].sum()) if len(alvo) else 0,
         'congelados pela pausa (não entram nem saem)': 0, 'barrados por etapa desligada': 0, 'entram com cupom do mês': 0}
    for email, linha in alvo.iterrows():
        c = contatos.get(email)
        if c is None:
            r['não estão no Brevo (não são criados)'] += 1
            continue
        if c.get('emailBlacklisted'):
            r['descadastrados (não mexe)'] += 1
            continue
        atuais = c.get('attributes') or {}
        novos = {'ETAPA': linha['ETAPA'], 'DIAS_SEM_COMPRAR': int(linha['DIAS_SEM_COMPRAR']), 'FAMILIA': linha['FAMILIA'],
                 'VIP': bool(linha['VIP']), 'CONTROLE': bool(linha['CONTROLE'])}
        diferentes = {k: v for k, v in novos.items() if atuais.get(k) != v}
        atuais_listas = {ids_da_regua[i] for i in (c.get('listIds') or []) if i in ids_da_regua}
        desejada = {linha['lista']} if linha['lista'] else set()
        entrar, sair = desejada - atuais_listas, atuais_listas - desejada
        if pausada:
            r['congelados pela pausa (não entram nem saem)'] += len(entrar) + len(sair)
            entrar, sair = set(), set()
        elif politica is not None:
            liberadas = {n for n in entrar if codigo_da_lista.get(n) in politica.etapas_ligadas}
            r['barrados por etapa desligada'] += len(entrar) - len(liberadas)
            entrar = liberadas
        for nome in entrar:  # cupom do mês, só na entrada nas etapas com cupom
            codigo = codigo_da_lista.get(nome, '')
            if codigo in ('ETAPA_2', 'ETAPA_3'):
                modelo, validade = (cupons or {}).get(codigo, ('', 0))
                if modelo and validade:
                    diferentes['CUPOM'] = cupom_do_mes(modelo, hoje)
                    diferentes['CUPOM_ATE'] = (hoje + timedelta(days=int(validade))).strftime('%d/%m')
                    r['entram com cupom do mês'] += 1
                else:
                    p.avisos.append(f'Etapa {codigo[-1]}: sem cupom ou sem validade na aba Régua; o contato entra sem CUPOM.')
        if diferentes:
            p.atualizar[email] = diferentes
            r['atributos a atualizar'] += 1
        for nome in entrar:
            p.entrar_na_lista.setdefault(nome, []).append(email)
            r['entram em lista'] += 1
        for nome in sair:
            p.sair_da_lista.setdefault(nome, []).append(email)
            r['saem de lista'] += 1
        mudou_etapa = atuais.get('ETAPA') != novos['ETAPA'] or atuais.get('CONTROLE') != novos['CONTROLE']
        if mudou_etapa or entrar or sair:
            p.mudancas.append({'email': email, 'etapa_antes': atuais.get('ETAPA') or '', 'etapa_depois': novos['ETAPA'],
                               'controle': novos['CONTROLE'], 'entra_na_lista': ', '.join(sorted(entrar)),
                               'sai_da_lista': ', '.join(sorted(sair))})
    p.avisos = sorted(set(p.avisos))
    p.resumo = r
    return p


PAUSA_ENTRE_ATUALIZACOES_S = 0.12      # o Brevo aceita 10 chamadas por segundo nas rotas de contatos
ORCAMENTO_DE_ATUALIZACOES_S = 420       # tempo máximo gastando em atualizar contatos por rodada; o resto fica para a próxima


def aplicar(brevo: Brevo, plano: Plano, listas: dict[str, int], dormir: Callable[[float], None] = time.sleep,
            orcamento_s: float = ORCAMENTO_DE_ATUALIZACOES_S, relogio: Callable[[], float] = time.monotonic) -> dict[str, int]:
    """Escreve o plano no Brevo. Recusa em modo teste. Só roda quando o Túlio liberar (D-052).

    Ordem (a automação do Brevo dispara na ENTRADA na lista, então os atributos têm de estar prontos antes):
      1) cria os atributos que faltam;
      2) atualiza os atributos contato por contato, na hora (PUT; a importação em lote do Brevo é assíncrona e exige lista),
         primeiro quem vai entrar numa lista;
      3) só então coloca nas listas quem teve os atributos gravados (chamada separada);
      4) tira das listas.
    Falha em UM contato não derruba os outros (ele tenta de novo na rodada seguinte). Chave inválida ou bloqueio de IP interrompem.
    O que não coube no orçamento de tempo fica como `pendentes` e é feito na rodada seguinte.
    """
    if brevo.modo_teste:
        raise BrevoModoTeste('Modo teste ligado: nada é escrito no Brevo.')
    feitos = {'atributos': 0, 'entraram': 0, 'sairam': 0, 'atributos_criados': 0, 'falhas': 0, 'pendentes': 0}
    existentes = {a['name'] for a in brevo.atributos()}
    for nome, tipo in ATRIBUTOS.items():
        if nome not in existentes:
            brevo.criar_atributo(nome, tipo)
            feitos['atributos_criados'] += 1
    entrando = {e for nome, emails in plano.entrar_na_lista.items() if nome in listas for e in emails}
    fila = sorted(e for e in plano.atualizar if e in entrando) + sorted(e for e in plano.atualizar if e not in entrando)
    prontos = {e for e in entrando if e not in plano.atualizar}   # entram sem atributo novo a gravar
    inicio = relogio()
    for i, email in enumerate(fila):
        if relogio() - inicio > orcamento_s:
            feitos['pendentes'] = len(fila) - i
            break
        try:
            brevo.atualizar_contato(email, plano.atualizar[email])
            feitos['atributos'] += 1
            prontos.add(email)
        except ErroBrevo as erro:
            if erro.tipo in ('chave_invalida', 'bloqueio_ip'):
                raise
            feitos['falhas'] += 1
        dormir(PAUSA_ENTRE_ATUALIZACOES_S)
    feitos['pendentes'] += feitos['falhas']   # quem falhou também fica para a rodada seguinte
    for nome, emails in plano.entrar_na_lista.items():
        if nome not in listas:
            continue
        a_incluir = [e for e in emails if e in prontos]
        for i in range(0, len(a_incluir), LIMITE_REMOVER):
            brevo.adicionar_a_lista(listas[nome], a_incluir[i:i + LIMITE_REMOVER])
        feitos['entraram'] += len(a_incluir)
    for nome, emails in plano.sair_da_lista.items():
        if nome not in listas:
            continue
        for i in range(0, len(emails), LIMITE_REMOVER):
            brevo.remover_da_lista(listas[nome], emails[i:i + LIMITE_REMOVER])
        feitos['sairam'] += len(emails)
    return feitos


# ----------------------------------------------------------------------------
# Rodada diária (usada pela rotina)
# ----------------------------------------------------------------------------
@dataclass
class ResultadoBrevo:
    status: str = 'sem chave'          # ok (modo teste), ok, erro: ..., sem chave
    detalhe: str = ''
    plano: Plano | None = None
    leitura_ok_em: str = ''            # momento da última chamada bem-sucedida (Brasília)
    conta: dict | None = None
    aplicado: dict | None = None       # o que foi escrito no Brevo (só fora do modo teste)


def ler_conta(chave: str, modo_teste: bool = True, sessao: Any = None, agora: str = '') -> ResultadoBrevo:
    """Só a leitura simples da conta: mantém a chave viva e avisa cedo de chave inválida ou bloqueio de IP."""
    if not chave:
        return ResultadoBrevo('sem chave', 'BREVO_API_KEY não configurada')
    try:
        conta = Brevo(chave, modo_teste, sessao).conta()
    except ErroBrevo as erro:
        return ResultadoBrevo(f'erro: {erro.tipo}', erro.detalhe)
    return ResultadoBrevo('ok (modo teste)' if modo_teste else 'ok', '', None, agora, conta)


def planejar_do_dia(chave: str, classificacao: pd.DataFrame, tabelas: Tabelas, params: motor_regua.ParametrosRegua,
                    modo_teste: bool = True, sessao: Any = None, agora: str = '',
                    listas_por_codigo: dict[str, str] | None = None, politica: PoliticaRegua | None = None,
                    hoje: date | None = None, cupons: dict[str, tuple[str, int]] | None = None,
                    dormir: Callable[[float], None] = time.sleep) -> ResultadoBrevo:
    """Lê o Brevo (listas, atributos, contatos) e calcula o plano. Em modo teste, não escreve nada."""
    r = ler_conta(chave, modo_teste, sessao, agora)
    if not r.status.startswith('ok'):
        return r
    try:
        b = Brevo(chave, modo_teste, sessao)
        listas = {l['name']: l['id'] for l in b.listas()}
        atributos = {a['name'] for a in b.atributos()}
        contatos = {str(c.get('email', '')).strip().lower(): c for c in b.contatos()}
        alvo = alvo_dos_clientes(classificacao, tabelas, params, listas_por_codigo)
        nomes_das_listas = list((listas_por_codigo or dict(zip(CODIGOS_DAS_ETAPAS, LISTAS_PADRAO))).values())
        por_codigo = listas_por_codigo or dict(zip(CODIGOS_DAS_ETAPAS, LISTAS_PADRAO))
        r.plano = planejar(alvo, contatos, listas, atributos, nomes_das_listas, politica, hoje,
                           {nome: codigo for codigo, nome in por_codigo.items()}, cupons)
        if politica is not None:
            r.plano.avisos = list(politica.avisos) + r.plano.avisos
        if not modo_teste:
            r.aplicado = aplicar(b, r.plano, listas, dormir)
    except ErroBrevo as erro:
        return ResultadoBrevo(f'erro: {erro.tipo}', erro.detalhe, None, r.leitura_ok_em, r.conta)
    return r


# ----------------------------------------------------------------------------
# Black Monstro 2026 · Lado A no Brevo (D-096)
# ----------------------------------------------------------------------------
ABA_LADO_A_ENVIADOS = 'lado_a_enviados'
COLUNAS_LADO_A = ['email', 'numero_pedido', 'data']
CHAVE_LISTA_LADO_A = 'Black: ID da lista Lado A no Brevo'
ID_LISTA_LADO_A_PADRAO = 33
CUPOM_ANTECIPA = 'ANTECIPA10'
DATA_INICIO_ANTECIPA_PADRAO = date(2026, 11, 10)
DATA_FIM_ANTECIPA_PADRAO = date(2026, 11, 25)


def _parse_data_config(valor: Any, padrao: date) -> date:
    if not valor:
        return padrao
    t = str(valor).strip()
    m = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})', t)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    m = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{4})', t)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass
    m = re.match(r'^(\d{1,2})/(\d{1,2})$', t)
    if m:
        try:
            return date(padrao.year, int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass
    return padrao


def _tem_cupom_antecipa(valor_cupom: Any) -> bool:
    if pd.isna(valor_cupom):
        return False
    partes = [c.strip().upper() for c in str(valor_cupom).split(',') if c.strip()]
    return CUPOM_ANTECIPA in partes


def _ler_config_planilha(planilha: Any) -> dict[str, str]:
    if hasattr(planilha, '_ss') and hasattr(planilha._ss, 'worksheet'):
        try:
            valores = planilha._ss.worksheet('Configuração').get_all_values()
            return {str(r[0]).strip(): str(r[1]).strip() for r in valores if len(r) >= 2 and str(r[0]).strip()}
        except Exception:
            return {}
    return {}


def _ler_lado_a_enviados(planilha: Any) -> set[str]:
    if hasattr(planilha, '_ss') and hasattr(planilha._ss, 'worksheet'):
        try:
            valores = planilha._ss.worksheet(ABA_LADO_A_ENVIADOS).get_all_values()
            if len(valores) > 1:
                return {str(l[0]).strip().lower() for l in valores[1:] if l and str(l[0]).strip()}
        except Exception:
            pass
    return set()


def _ler_bloqueio_emails(planilha: Any) -> set[str]:
    try:
        from painel_monstro.saidas import carrinhos_planilha
        b = carrinhos_planilha.ler_bloqueio(planilha)
        return {x.lower() for x in b if '@' in x}
    except Exception:
        pass
    if hasattr(planilha, '_ss') and hasattr(planilha._ss, 'worksheet'):
        try:
            valores = planilha._ss.worksheet('Bloqueio').get_all_values()
            achados = set()
            for linha in valores[1:]:
                for col in linha[:2]:
                    txt = str(col).strip().lower()
                    if '@' in txt:
                        achados.add(txt)
            return achados
        except Exception:
            pass
    return set()


def _registrar_alerta_brevo(planilha: Any, erro_msg: str, hoje: date) -> None:
    try:
        from painel_monstro.log_publico import resumo_erro
        msg = resumo_erro(erro_msg) if not isinstance(erro_msg, str) else erro_msg
        df_alerta = pd.DataFrame([{
            'indicador': 'lado_a_brevo',
            'condicao': 'erro',
            'limite': '',
            'ativo': 'sim',
            'observacao': f'{hoje.isoformat()}: {msg}'[:300],
        }], columns=['indicador', 'condicao', 'limite', 'ativo', 'observacao'])
        if hasattr(planilha, 'mesclar'):
            planilha.mesclar('alertas', df_alerta, ['indicador'])
    except Exception:
        pass


def passo_lado_a(
    config: Any,
    planilha: Any,
    tabelas: Any,
    hoje: date | None = None,
    sessao: Any = None,
    brevo_cliente: Brevo | None = None,
) -> dict[str, Any]:
    """Adiciona clientes com pedido pago e cupom ANTECIPA10 à lista do Lado A no Brevo.

    Regras:
      1. Só roda entre 'Black: início do Antecipa' e 25/11 (lidos da aba Configuração).
      2. Pedidos válidos com o cupom ANTECIPA10 (sem diferenciar maiúsculas/minúsculas).
      3. Adiciona à lista do Brevo cujo ID está na linha 'Black: ID da lista Lado A no Brevo' (padrão: 33).
      4. Idempotente: quem já está na lista ou em 'lado_a_enviados' não é reenviado nem duplicado.
      5. Respeita quem se descadastrou (emailBlacklisted no Brevo), está na aba Bloqueio ou recusou marketing.
      6. Erro no Brevo registra na aba alertas e não derruba a rotina.
    """
    if hoje is None:
        hoje = datetime.now().date()
    elif hasattr(hoje, 'date') and not isinstance(hoje, date):
        hoje = hoje.date()

    cfg = _ler_config_planilha(planilha)

    # 1. Período do Antecipa (10 a 25/11)
    dt_inicio = _parse_data_config(cfg.get('Black: início do Antecipa'), DATA_INICIO_ANTECIPA_PADRAO)
    if 'Black: fim do Antecipa' in cfg:
        dt_fim = _parse_data_config(cfg.get('Black: fim do Antecipa'), DATA_FIM_ANTECIPA_PADRAO)
    elif 'Black: acesso Lado A' in cfg:
        dt_acesso = _parse_data_config(cfg.get('Black: acesso Lado A'), date(2026, 11, 26))
        dt_fim = dt_acesso - timedelta(days=1)
    else:
        dt_fim = DATA_FIM_ANTECIPA_PADRAO

    if not (dt_inicio <= hoje <= dt_fim):
        return {
            'status': 'fora_do_periodo',
            'adicionados': 0,
            'detalhe': f'Hoje ({hoje.isoformat()}) fora do período do Antecipa ({dt_inicio.isoformat()} a {dt_fim.isoformat()}).',
        }

    # 2. ID da lista no Brevo
    lista_id = ID_LISTA_LADO_A_PADRAO
    for k, v in cfg.items():
        if _norm(k) in (_norm(CHAVE_LISTA_LADO_A), _norm('Black: ID da lista VIP no Brevo')):
            try:
                lista_id = int(float(str(v).strip()))
                break
            except ValueError:
                pass

    # 3. Pedidos e clientes
    pedidos = getattr(tabelas, 'pedidos', None)
    if pedidos is None or len(pedidos) == 0:
        return {'status': 'sem_pedidos', 'adicionados': 0, 'detalhe': 'Nenhum pedido para analisar.'}

    ja_enviados = _ler_lado_a_enviados(planilha)
    bloqueados = _ler_bloqueio_emails(planilha)

    nao_aceitam = set()
    nomes_clientes = {}
    clientes_df = getattr(tabelas, 'clientes', None)
    if clientes_df is not None and len(clientes_df):
        for _, cl in clientes_df.iterrows():
            em = str(cl.get('email') or '').strip().lower()
            if not em:
                continue
            aceita = cl.get('aceita_marketing')
            if aceita is False or str(aceita).strip().lower() in ('false', 'nao', 'não', '0'):
                nao_aceitam.add(em)
            nm = str(cl.get('nome') or '').strip()
            if nm and em not in nomes_clientes:
                nomes_clientes[em] = nm

    candidatos: dict[str, dict[str, str]] = {}
    for _, row in pedidos.iterrows():
        v = row.get('valido')
        if not (v is True or str(v).strip().lower() in ('true', '1', 'sim')):
            continue
        if not _tem_cupom_antecipa(row.get('cupom')):
            continue
        email = str(row.get('email') or '').strip().lower()
        if not email or '@' not in email:
            continue
        if email in ja_enviados or email in bloqueados or email in nao_aceitam:
            continue
        nome = str(row.get('nome') or '').strip() or nomes_clientes.get(email, '')
        num_pedido = str(row.get('numero') or row.get('numero_pedido') or '').strip()
        data_pedido = str(row.get('data') or '').strip()[:10] or hoje.strftime('%Y-%m-%d')
        candidatos[email] = {
            'email': email,
            'nome': nome,
            'numero_pedido': num_pedido,
            'data': data_pedido,
        }

    if not candidatos:
        return {'status': 'nenhum_candidato', 'adicionados': 0, 'detalhe': 'Nenhum cliente elegível com cupom ANTECIPA10.'}

    # 4. Brevo
    if brevo_cliente is None:
        chave = getattr(config, 'brevo_api_key', None) or (config.get('brevo_api_key') if isinstance(config, dict) else '') or ''
        if not chave:
            return {'status': 'sem_chave', 'adicionados': 0, 'detalhe': 'BREVO_API_KEY não configurada.'}
        modo_teste = getattr(config, 'brevo_modo_teste', None) if not isinstance(config, dict) else config.get('brevo_modo_teste')
        if modo_teste is None:
            modo_teste = True
        try:
            brevo_cliente = Brevo(chave, modo_teste=modo_teste, sessao=sessao)
        except ErroBrevo as erro:
            _registrar_alerta_brevo(planilha, str(erro.detalhe), hoje)
            return {'status': 'erro', 'adicionados': 0, 'erro': str(erro)}

    if brevo_cliente.modo_teste:
        return {
            'status': 'modo_teste',
            'adicionados': 0,
            'candidatos': len(candidatos),
            'detalhe': f'{len(candidatos)} cliente(s) receberiam (modo teste ativo; nada foi escrito).',
        }

    adicionados = 0
    novos_registros = []
    try:
        for email, cand in candidatos.items():
            contato = brevo_cliente.contato(email)
            if contato is not None and contato.get('emailBlacklisted'):
                continue

            primeiro_nome = cand['nome'].split()[0].title() if cand['nome'] else ''

            if contato is None:
                atributos = {'FIRSTNAME': primeiro_nome} if primeiro_nome else {}
                brevo_cliente.criar_contato(email, atributos)
                brevo_cliente.adicionar_a_lista(lista_id, [email])
                adicionados += 1
                novos_registros.append({
                    'email': email,
                    'numero_pedido': cand['numero_pedido'],
                    'data': cand['data'],
                })
            else:
                list_ids = contato.get('listIds') or []
                if lista_id not in list_ids:
                    if primeiro_nome and not (contato.get('attributes') or {}).get('FIRSTNAME'):
                        brevo_cliente.atualizar_contato(email, {'FIRSTNAME': primeiro_nome})
                    brevo_cliente.adicionar_a_lista(lista_id, [email])
                    adicionados += 1
                novos_registros.append({
                    'email': email,
                    'numero_pedido': cand['numero_pedido'],
                    'data': cand['data'],
                })

        if novos_registros and hasattr(planilha, 'mesclar'):
            df_gravar = pd.DataFrame(novos_registros, columns=COLUNAS_LADO_A)
            planilha.mesclar(ABA_LADO_A_ENVIADOS, df_gravar, ['email'])

        return {
            'status': 'ok',
            'adicionados': adicionados,
            'total_registrados': len(novos_registros),
            'detalhe': f'{adicionados} adicionado(s) à lista {lista_id} no Brevo.',
        }
    except Exception as erro:
        _registrar_alerta_brevo(planilha, str(erro), hoje)
        return {'status': 'erro', 'adicionados': adicionados, 'erro': str(erro)}

