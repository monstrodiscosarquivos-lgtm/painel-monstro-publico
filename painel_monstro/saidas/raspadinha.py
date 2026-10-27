"""Raspadinha online na Planilha Google e na Nuvemshop (D-062, guia em docs/RASPADINHA.md).

Abas:
- `Raspadinha` (do Túlio): prêmios, quantidades e regras. O Painel só cria com os valores padrão quando não existe.
- `raspadinha_lista` (do Túlio): emails do público quando o público é "Lista colada".
- `raspadinha_envios` (do Painel): uma linha por pessoa e campanha, com grupo, prêmio, cupom e link. Uma campanha,
  depois de sorteada, nunca é sorteada de novo (como a régua, D-030). Só `--forcar` refaz, e só se nenhum cupom foi criado.
- `raspadinha_resultados` (do Painel): compra em 30 dias de quem recebeu contra o controle, cupons usados e desconto dado.

Cupons: o Painel cria na Nuvemshop (POST /coupons) somente com a aba em Modo = Real E o comando com --criar-cupons.
É a única escrita do Painel na Nuvemshop, autorizada pelo Túlio em 14/10/2026 (D-062). Nada é enviado ao cliente:
o Painel gera um CSV para importar no Brevo, e o envio é feito pelo Túlio no Brevo.

Uso:
  python -m painel_monstro.saidas.raspadinha                  prepara a campanha da aba (sorteio + CSV), sem criar cupom
  python -m painel_monstro.saidas.raspadinha --criar-cupons   cria os cupons da campanha (exige Modo = Real)
  python -m painel_monstro.saidas.raspadinha --resultado      atualiza uso dos cupons e resultado contra o controle
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from datetime import date
from typing import Any, Callable

import gspread
import pandas as pd
import requests

from painel_monstro.log_publico import comando_seguro, ArgumentParserSeguro, resumo_erro
from painel_monstro.config import RAIZ_PROJETO, Config, carregar
from painel_monstro.coletor import nuvemshop_api
from painel_monstro.motor import raspadinha as r
from painel_monstro.motor.regua import pedidos_validos
from painel_monstro.saidas.planilha_google import ABA_REGUA, REGUA_COLUNAS, ErroPlanilha, PlanilhaGoogle

ABA_CONFIG = 'Raspadinha'
ABA_LISTA = 'raspadinha_lista'
ABA_ENVIOS = 'raspadinha_envios'
ABA_RESULTADOS = 'raspadinha_resultados'
PASTA_CSV = os.path.join(RAIZ_PROJETO, 'dados', 'raspadinha')

CAB_PREMIOS = ['Prêmio', 'Tipo', 'Valor', 'Quantidade de cartelas', 'O que é']
PREMIOS_PADRAO = [
    ['10%', 'Porcentagem', 10, 60, 'Texto do selo; Tipo: Porcentagem, Frete grátis ou Valor em R$'],
    ['15%', 'Porcentagem', 15, 25, ''],
    ['20%', 'Porcentagem', 20, 5, ''],
    ['FRETE GRÁTIS', 'Frete grátis', 0, 10, 'Frete grátis: deixe o valor em 0'],
]
CAB_PARAMETROS = ['Parâmetro', 'Valor', 'O que faz']
PARAMETROS = [  # nome na planilha, campo, padrão, ajuda
    ('Campanha', 'campanha', '', 'Nome único da campanha, ex. "Raspadinha novembro". Cada nome é um sorteio; para outra campanha, troque o nome'),
    ('Modo', 'modo', 'Teste', 'Teste: só sorteia e mostra o plano, não cria cupom. Real: deixa o agente criar os cupons na Nuvemshop'),
    ('Público', 'publico', 'Lista colada', '"Lista colada" (emails na aba raspadinha_lista) ou "Todos que aceitam marketing" (clientes com compra paga)'),
    ('Prefixo do cupom', 'prefixo', 'RASPA', 'Só letras e números. O resto do código é aleatório, ex. RASPAK7Q2MX'),
    ('Letras aleatórias no cupom', 'tamanho_codigo', 6, 'Quanto maior, mais difícil de adivinhar. Mínimo 5'),
    ('Validade do cupom (dias)', 'validade_dias', 15, 'Conta a partir do dia do sorteio'),
    ('Pedido mínimo (R$)', 'pedido_minimo', 0, '0 = sem mínimo'),
    ('Vale junto com outras promoções?', 'cumulativo', 'Não', 'Sim ou Não'),
    ('Grupo de controle (%)', 'controle', 10, 'Parte do público que não recebe, para medir o resultado'),
    ('Mínimo de pessoas para ter controle', 'minimo_para_controle', 10, 'Público menor que isso não tem controle'),
    ('Dias entre benefícios', 'dias_entre_beneficios', 90, 'Fica de fora quem usou cupom, recebeu cupom da régua ou outra raspadinha nesse prazo. 0 = sem trava'),
    ('Endereço da página', 'url_pagina', '', 'Endereço público da página da raspadinha (GitHub Pages), terminando em /'),
]
LISTA_CABECALHO = ['email', 'nome']


class ErroRaspadinha(Exception):
    pass


def _numero(valor: Any, padrao: float) -> float:
    texto = str(valor).strip().replace('R$', '').replace('%', '').replace(' ', '')
    if texto == '':
        return padrao
    if ',' in texto:
        texto = texto.replace('.', '').replace(',', '.')
    try:
        return float(texto)
    except ValueError:
        return padrao


def _sim(valor: Any, padrao: bool) -> bool:
    t = str(valor).strip().lower()
    return padrao if t == '' else t in ('sim', 's', 'yes', 'true', '1')


# ----------------------------------------------------------------------------- abas
def _aba(planilha: PlanilhaGoogle, titulo: str):
    try:
        return planilha._ss.worksheet(titulo)
    except gspread.exceptions.WorksheetNotFound:
        return None


def garantir_abas(planilha: PlanilhaGoogle) -> list[str]:
    """Cria `Raspadinha` e `raspadinha_lista` com o padrão, só se não existirem. Nunca altera o que já existe."""
    criadas = []
    if _aba(planilha, ABA_CONFIG) is None:
        aba = planilha._ss.add_worksheet(title=ABA_CONFIG, rows=40, cols=5)
        valores = [CAB_PREMIOS] + PREMIOS_PADRAO + [[''] * 5, CAB_PARAMETROS + ['', '']] + [[n, v, a, '', ''] for n, _, v, a in PARAMETROS]
        aba.update(valores, 'A1', raw=True)
        try:
            aba.format('1:1', {'textFormat': {'bold': True}})
            aba.format(f'{len(PREMIOS_PADRAO) + 3}:{len(PREMIOS_PADRAO) + 3}', {'textFormat': {'bold': True}})
        except Exception:  # noqa: BLE001 - formatação é só ajuda
            pass
        criadas.append(ABA_CONFIG)
    if _aba(planilha, ABA_LISTA) is None:
        planilha.garantir_cabecalho(ABA_LISTA, LISTA_CABECALHO, {'email': 'Um email por linha (cole a lista exportada do Brevo)',
                                                                 'nome': 'Primeiro nome (opcional; se vazio, usa o nome da Nuvemshop)'})
        criadas.append(ABA_LISTA)
    return criadas


def ler_parametros(valores: list[list[Any]]) -> r.ParametrosRaspadinha:
    """Lê a aba Raspadinha. Valor vazio ou ilegível volta ao padrão; Modo ilegível vira Teste (o mais seguro)."""
    premios: list[r.Premio] = []
    params: dict[str, Any] = {}
    secao = ''
    nomes = {n.lower(): (campo, padrao) for n, campo, padrao, _ in PARAMETROS}
    for linha in valores:
        celulas = [str(c).strip() for c in linha] + [''] * 5
        primeira = celulas[0]
        if primeira.lower() == 'prêmio':
            secao = 'premios'
            continue
        if primeira.lower() == 'parâmetro':
            secao = 'parametros'
            continue
        if not primeira:
            continue
        if secao == 'premios':
            tipo = r.TIPOS.get(celulas[1].lower())
            qtd = int(_numero(celulas[3], 0))
            if tipo and qtd > 0:
                premios.append(r.Premio(primeira, tipo, _numero(celulas[2], 0), qtd))
        elif secao == 'parametros' and primeira.lower() in nomes:
            campo, padrao = nomes[primeira.lower()]
            bruto = celulas[1]
            if campo in ('campanha', 'prefixo', 'url_pagina', 'publico'):
                params[campo] = bruto or padrao
            elif campo == 'modo':
                params[campo] = 'Real' if bruto.lower() == 'real' else 'Teste'
            elif campo == 'cumulativo':
                params[campo] = _sim(bruto, False)
            elif campo == 'controle':
                v = _numero(bruto, 10)
                params[campo] = v / 100 if v > 1 else v
            elif campo in ('tamanho_codigo', 'validade_dias', 'minimo_para_controle', 'dias_entre_beneficios'):
                params[campo] = int(_numero(bruto, padrao))
            else:
                params[campo] = _numero(bruto, padrao)
    if params.get('tamanho_codigo', 6) < 5:
        params['tamanho_codigo'] = 5
    url = params.get('url_pagina', '')
    if url and not url.endswith('/') and '?' not in url and not url.endswith('.html'):
        params['url_pagina'] = url + '/'
    if not premios:
        raise ErroRaspadinha('A aba Raspadinha não tem nenhum prêmio com quantidade maior que zero.')
    return r.ParametrosRaspadinha(premios=tuple(premios), **params)


def ler_tabela(planilha: PlanilhaGoogle, titulo: str, colunas: list[str]) -> pd.DataFrame:
    aba = _aba(planilha, titulo)
    if aba is None:
        return pd.DataFrame(columns=colunas)
    return planilha._ler_historico(aba, colunas)


def ler_lista(planilha: PlanilhaGoogle) -> pd.DataFrame:
    aba = _aba(planilha, ABA_LISTA)
    valores = aba.get_all_values() if aba is not None else []
    if not valores:
        return pd.DataFrame(columns=['email', 'primeiro_nome'])
    cab = [str(c).strip().lower() for c in valores[0]]
    i_email = next((i for i, c in enumerate(cab) if 'email' in c or 'e-mail' in c), None)
    i_nome = next((i for i, c in enumerate(cab) if 'nome' in c or 'firstname' in c), None)
    corpo = valores[1:]
    if i_email is None:  # sem cabeçalho: emails na coluna A
        i_email, corpo = 0, valores
    linhas = [{'email': l[i_email] if len(l) > i_email else '',
               'primeiro_nome': (l[i_nome] if i_nome is not None and len(l) > i_nome else '')} for l in corpo]
    return pd.DataFrame(linhas, columns=['email', 'primeiro_nome'])


# ----------------------------------------------------------------------------- público
def montar_publico(params: r.ParametrosRaspadinha, tabelas, lista: pd.DataFrame) -> tuple[pd.DataFrame, set[str]]:
    clientes = tabelas.clientes.copy()
    clientes['email'] = clientes['email'].astype(str).str.lower()
    nomes = clientes.drop_duplicates('email', keep='last').set_index('email')['primeiro_nome'].fillna('')
    nao_aceitam = set(clientes.loc[~clientes['aceita_marketing'].astype(bool), 'email'])
    if params.publico.strip().lower().startswith('todos'):
        compradores = set(pedidos_validos(tabelas)['email'].astype(str).str.lower())
        base = clientes[clientes['aceita_marketing'].astype(bool) & clientes['email'].isin(compradores)]
        publico = base[['email', 'primeiro_nome']].copy()
    else:
        publico = lista.copy()
        publico['email'] = publico['email'].astype(str).str.strip().str.lower()
    vazio = publico['primeiro_nome'].fillna('').astype(str).str.strip() == ''
    publico.loc[vazio, 'primeiro_nome'] = publico.loc[vazio, 'email'].map(nomes).fillna('')
    publico['primeiro_nome'] = publico['primeiro_nome'].fillna('').astype(str).str.split().str[0].fillna('').str.title()
    return publico, nao_aceitam


# ----------------------------------------------------------------------------- Nuvemshop: cupons
class CuponsNuvemshop:
    """Cria cupons na Nuvemshop. Única escrita do Painel na loja (D-062). O token nunca aparece em mensagens."""

    def __init__(self, config: Config, sessao: Any = None, dormir: Callable[[float], None] = time.sleep):
        self._api = nuvemshop_api.NuvemshopAPI(config, sessao=sessao, dormir=dormir)
        self._sessao = self._api._sessao
        self._dormir = dormir

    def existe(self, codigo: str) -> bool:
        resposta = self._api._get(f'{self._api._base}/coupons', {'q': codigo, 'per_page': 50}, vazio_se_404=True)
        if resposta is None:
            return False
        return any(str(c.get('code', '')).upper() == codigo.upper() for c in resposta.json())

    def criar(self, corpo: dict) -> str:
        """Devolve 'sim', 'já existia' ou 'erro: ...'."""
        url = f'{self._api._base}/coupons'
        for tentativa in range(1, 6):
            self._api._esperar_vaga()
            try:
                resposta = self._sessao.post(url, headers={**self._api._cabecalhos, 'Content-Type': 'application/json'},
                                             json=corpo, timeout=60)
            except requests.RequestException as erro:
                if tentativa == 5:
                    return f'erro: rede ({resumo_erro(erro)})'
                self._dormir(2 ** tentativa)
                continue
            self._api._guardar_limites(resposta)
            if resposta.status_code in (200, 201):
                return 'sim'
            if resposta.status_code == 429 or resposta.status_code >= 500:
                self._dormir(2 ** tentativa)
                self._api._livres = None
                continue
            if resposta.status_code in (401, 403):
                raise ErroRaspadinha('A Nuvemshop recusou criar cupom (permissão). Confira se o aplicativo tem permissão de escrita em cupons.')
            if resposta.status_code == 422 and self.existe(corpo['code']):
                return 'já existia'
            return f'erro: Nuvemshop respondeu {resposta.status_code}'
        return 'erro: Nuvemshop sem resposta'


# ----------------------------------------------------------------------------- CSV para o Brevo
def _nome_arquivo(campanha: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', campanha.lower().translate(str.maketrans('áàâãéêíóôõúç', 'aaaaeeiooouc'))).strip('-') or 'campanha'


def gerar_csv(envios: pd.DataFrame, campanha: str, real: bool, pasta: str = PASTA_CSV) -> tuple[str, int]:
    """CSV para importar numa lista do Brevo: EMAIL, FIRSTNAME, RASPA_LINK, RASPA_ATE. Só quem vai receber.
    Em modo real, só entra quem já tem o cupom criado na Nuvemshop."""
    e = envios[(envios['campanha'] == campanha) & (envios['grupo'] == r.GRUPO_ENVIO)]
    if real:
        e = e[e['cupom_criado'].isin(['sim', 'já existia'])]
    os.makedirs(pasta, exist_ok=True)
    caminho = os.path.join(pasta, f'{_nome_arquivo(campanha)}{"" if real else "_TESTE"}_brevo.csv')
    df = pd.DataFrame({'EMAIL': e['email'], 'FIRSTNAME': e['primeiro_nome'], 'RASPA_LINK': e['link'],
                       'RASPA_ATE': pd.to_datetime(e['valido_ate']).dt.strftime('%d/%m/%Y')})
    df.to_csv(caminho, index=False, encoding='utf-8-sig')
    return caminho, len(df)


# ----------------------------------------------------------------------------- passos
def preparar(planilha: PlanilhaGoogle, tabelas, hoje: date, forcar: bool = False) -> dict:
    garantir_abas(planilha)
    params = ler_parametros(planilha._ss.worksheet(ABA_CONFIG).get_all_values())
    envios = ler_tabela(planilha, ABA_ENVIOS, r.ENVIOS_COLUNAS)
    ja = envios[envios['campanha'] == params.campanha.strip()]
    if len(ja) and not forcar:
        return {'params': params, 'envios': ja, 'novo': False}
    if len(ja) and forcar and ja['cupom_criado'].isin(['sim', 'já existia']).any():
        raise ErroRaspadinha('Esta campanha já tem cupons criados na Nuvemshop; o sorteio não pode ser refeito. Use outro nome de campanha.')
    publico, nao_aceitam = montar_publico(params, tabelas, ler_lista(planilha))
    if not len(publico):
        raise ErroRaspadinha('O público está vazio. Cole os emails na aba raspadinha_lista ou mude o Público na aba Raspadinha.')
    regua = ler_tabela(planilha, ABA_REGUA, REGUA_COLUNAS)
    anteriores = envios[envios['campanha'] != params.campanha.strip()]
    beneficios = r.ultimos_beneficios(tabelas.pedidos, regua, anteriores)
    novos = r.sortear(publico, params, hoje, beneficios, nao_aceitam)
    if len(ja):
        planilha.substituir(ABA_ENVIOS, pd.concat([anteriores, novos], ignore_index=True)[r.ENVIOS_COLUNAS])
    else:
        planilha.mesclar(ABA_ENVIOS, novos, r.ENVIOS_CHAVE)
    return {'params': params, 'envios': novos, 'novo': True}


def criar_cupons(planilha: PlanilhaGoogle, cupons: CuponsNuvemshop, hoje: date) -> dict:
    params = ler_parametros(planilha._ss.worksheet(ABA_CONFIG).get_all_values())
    if not params.real:
        raise ErroRaspadinha('A aba Raspadinha está em Modo = Teste. Mude para Real para criar os cupons.')
    envios = ler_tabela(planilha, ABA_ENVIOS, r.ENVIOS_COLUNAS)
    campanha = params.campanha.strip()
    alvo = envios[(envios['campanha'] == campanha) & (envios['grupo'] == r.GRUPO_ENVIO)
                  & ~envios['cupom_criado'].isin(['sim', 'já existia'])]
    if not len(envios[envios['campanha'] == campanha]):
        raise ErroRaspadinha('Esta campanha ainda não foi sorteada. Rode primeiro sem --criar-cupons.')
    contagem: dict[str, int] = {}
    for i, linha in alvo.iterrows():
        estado = cupons.criar(r.payload_cupom(linha, params, hoje))
        envios.loc[i, 'cupom_criado'] = estado
        contagem[estado] = contagem.get(estado, 0) + 1
    planilha.substituir(ABA_ENVIOS, envios[r.ENVIOS_COLUNAS])
    return {'params': params, 'envios': envios[envios['campanha'] == campanha], 'contagem': contagem}


def calcular_resultado(planilha: PlanilhaGoogle, tabelas, hoje: date) -> tuple[pd.DataFrame, pd.DataFrame, bool] | None:
    """Marca quem usou o cupom e recalcula o resultado, sem gravar nada (D-039: calcula antes de escrever).
    Devolve (envios marcados, resultado, se os envios mudaram) ou None quando não há campanha."""
    if _aba(planilha, ABA_ENVIOS) is None:
        return None
    envios = ler_tabela(planilha, ABA_ENVIOS, r.ENVIOS_COLUNAS)
    if not len(envios):
        return None
    marcado = r.marcar_uso(envios, tabelas.pedidos)
    colunas = ['pedido', 'receita', 'usado_em']
    mudou = not marcado[colunas].astype(str).reset_index(drop=True).equals(envios[colunas].astype(str).reset_index(drop=True))
    return marcado[r.ENVIOS_COLUNAS], r.resultado(marcado, tabelas.pedidos, hoje), mudou


def passo_rotina(planilha: PlanilhaGoogle, tabelas, hoje: date) -> list[tuple[str, pd.DataFrame]]:
    """Para a rotina de hora em hora: só calcula e devolve as abas a gravar; nunca derruba a rodada.
    Sem campanha, devolve lista vazia e nada é gravado."""
    try:
        calculado = calcular_resultado(planilha, tabelas, hoje)
    except Exception as erro:  # noqa: BLE001
        print(f'      Raspadinha: resultado não atualizado ({resumo_erro(erro)}); a próxima rodada tenta de novo')
        return []
    if calculado is None:
        return []
    marcado, res, mudou = calculado
    return ([(ABA_ENVIOS, marcado)] if mudou else []) + [(ABA_RESULTADOS, res)]


def _mostrar(titulo: str, envios: pd.DataFrame) -> None:
    print('Resumo do sorteio (detalhes na planilha privada):')
    for l in r.resumo_do_sorteio(envios).itertuples():
        print(f'      Participantes na categoria: {l.pessoas}')


@comando_seguro
def main(argv: list[str] | None = None) -> int:
    ap = ArgumentParserSeguro(description='Raspadinha online do Painel Monstro')
    ap.add_argument('--criar-cupons', action='store_true', help='cria os cupons da campanha na Nuvemshop (exige Modo = Real)')
    ap.add_argument('--resultado', action='store_true', help='atualiza o uso dos cupons e o resultado contra o controle')
    ap.add_argument('--forcar', action='store_true', help='refaz o sorteio da campanha (só se nenhum cupom foi criado)')
    a = ap.parse_args(argv)
    config = carregar()
    hoje = pd.Timestamp.now(tz=nuvemshop_api.FUSO_LOJA).date()
    try:
        planilha = PlanilhaGoogle.conectar(config)
        if a.criar_cupons:
            feito = criar_cupons(planilha, CuponsNuvemshop(config), hoje)
            contagem = ', '.join(f'{k}: {v}' for k, v in feito['contagem'].items()) or 'nada a criar'
            print('Cupons processados; conferir resultado na planilha privada.')
            caminho, n = gerar_csv(feito['envios'], feito['params'].campanha, True)
            print(f'CSV gravado em arquivo privado ({n} contatos).')
            return 0 if not any(k.startswith('erro') for k in feito['contagem']) else 1
        tabelas, _ = nuvemshop_api.coletar(config)
        if a.resultado:
            for aba, df in passo_rotina(planilha, tabelas, hoje):
                planilha.substituir(aba, df)
                if aba == ABA_RESULTADOS:
                    print('Resultado atualizado na planilha privada.')
            return 0
        feito = preparar(planilha, tabelas, hoje, forcar=a.forcar)
        p = feito['params']
        _mostrar(f'Campanha "{p.campanha}" ({"sorteada agora" if feito["novo"] else "já sorteada antes, nada mudou"}) · modo {p.modo}', feito['envios'])
        caminho, n = gerar_csv(feito['envios'], p.campanha, False)
        print(f'CSV gravado em arquivo privado ({n} contatos).')
        if not p.url_pagina:
            print('Atenção: falta o "Endereço da página" na aba Raspadinha; os links estão com um endereço provisório.')
        return 0
    except (ErroRaspadinha, ErroPlanilha, ValueError, nuvemshop_api.ErroAPI) as erro:
        print('Não deu: ' + resumo_erro(erro))
        return 1


if __name__ == '__main__':
    sys.exit(main())
