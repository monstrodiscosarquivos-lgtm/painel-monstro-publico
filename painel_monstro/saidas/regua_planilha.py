"""Régua e fila única na Planilha Google: aba `Régua`, parâmetros novos da `Configuração`, modelos novos da
`Mensagens` e o registro do teste do WhatsApp de 45 dias na aba `regua` (D-016, D-017, D-022).

Regras:
- Nada que o Túlio já tenha editado é sobrescrito. Aba que existe só ganha o que falta, no fim: linhas novas na
  `Configuração` e na `Mensagens`, colunas novas (se um dia houver) sempre depois das existentes.
- A aba `Régua` tem as janelas e ofertas de cada etapa; o motor lê dela a cada execução. Não troque o nome das
  etapas: o histórico da aba `regua` e o painel usam esses nomes.
- O grupo de cada cliente no teste de 45 dias fica na aba `regua` (mes = `teste45`) e nunca é sorteado de novo.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from typing import Any

import gspread
import pandas as pd

from painel_monstro.motor.regua import DESCANSO, Etapa, ParametrosRegua
from painel_monstro.saidas import carrinhos as c
from painel_monstro.saidas import carrinhos_planilha as cp
from painel_monstro.saidas.planilha_google import ABA_REGUA, REGUA_COLUNAS, Gravacao, PlanilhaGoogle, _letra

ABA_REGUA_PARAMETROS = 'Régua'
DESEJOS_COLUNAS = ['email', 'telefone', 'nome', 'desejo', 'data', 'status']
MES_DO_TESTE = 'teste45'
ETAPA_DO_TESTE = 'Garimpo 45 dias'
GRUPOS_DO_TESTE = ('controle', 'email', 'whatsapp')  # nada / só email / email e WhatsApp

# Parâmetros novos da aba Configuração (entram no fim; valores padrão de D-016 e D-022)
CONFIG_NOVA = [
    ('Fila única: início', '2026-10-12', 'Antes desta data a fila só tem carrinhos; VIP, 45 dias e aviso de garimpo começam nela'),
    ('Teste WhatsApp 45 dias: início', '2026-10-12', 'Quem completa 45 dias de última compra a partir desse dia entra no sorteio'),
    ('Teste WhatsApp 45 dias: fim', '2027-01-18', 'Depois dessa data ninguém novo é sorteado; a decisão é tomada nesse dia'),
    ('Teste 45 dias: grupo de controle (%)', 10, 'Não recebe nada além da newsletter'),
    ('Teste 45 dias: só email (%)', 30, 'Recebe os emails da régua, sem WhatsApp'),
    ('Teste 45 dias: email e WhatsApp (%)', 60, 'Recebe os emails da régua e o WhatsApp de garimpo'),
    ('Dias para contatar depois de completar 45 dias', 30, 'Quem completou 45 dias fica na fila por esse prazo. Se a Mariana não chegar, a linha vira "Encerrado sem contato"'),
    ('Email de alerta (rotina parada)', '', 'Recebe um aviso se nenhuma rodada do Painel der certo em 3 horas. Vazio = o dono da planilha'),
    ('Brevo: ID do segmento não abre email', '', 'Número do segmento do Brevo com quem não abre email (Contatos > Segmentos). Vazio = a lista do Meta de quem não abre fica vazia'),
    ('Régua no Brevo', 'Ligada', 'Ligada ou Pausada. Pausada: os atributos continuam atualizando e as listas ficam congeladas (ninguém entra nem sai).'),
    ('Pausa programada de', '20/11/2026', 'Início da pausa automática (em branco = sem pausa). Aceita dd/mm/aaaa.'),
    ('Pausa programada até', '30/11/2026', 'Último dia da pausa; a régua volta no dia seguinte. Aceita dd/mm/aaaa.'),
    ('Etapa 0 no Brevo', 'Ligada', '15 a 44 dias, só quem tem 1 compra. Ligada ou Desligada. Ligue a automação no Brevo ANTES de ligar aqui.'),
    ('Etapa 1 no Brevo', 'Desligada', '45 a 74 dias. Ligada ou Desligada. Ligue a automação no Brevo ANTES de ligar aqui.'),
    ('Etapa 2 no Brevo', 'Desligada', '90 a 119 dias. Ligada ou Desligada. O cupom do mês na Nuvemshop precisa valer até 10 dias depois do fim do mês. Ligue a automação no Brevo ANTES de ligar aqui.'),
    ('Etapa 3 no Brevo', 'Desligada', '180 a 209 dias. Ligada ou Desligada. O cupom do mês na Nuvemshop precisa valer até 7 dias depois do fim do mês. Ligue a automação no Brevo ANTES de ligar aqui.'),
    ('Emails do resumo', '', 'Recebem o resumo da semana toda segunda às 8h. Separe por vírgula. Vazio = o dono da planilha'),
    ('Horas sem rodada para alertar', 3, 'Quantas horas sem nenhuma rodada bem-sucedida antes de mandar o alerta'),
    ('Prefixo de cupom de indicação', '', 'Pedidos com cupom que começa com este texto entram sozinhos como Indicação em "Indicações e contatos manuais". Vazio = ninguém entra sozinho'),
]

MODELOS_NOVOS = {m: (cp.MENSAGENS_QUANDO[m], c.MODELOS_PADRAO[m]) for m in ('G45', 'G45_GERAL', 'VIP', 'ALERTA_GARIMPO')}  # textos em carrinhos.py
MARCADORES_NOVOS = [
    ('{ultimo_disco}', 'Último disco que o cliente comprou (G45)'),
    ('{sugestao}', 'Um disco em estoque da família de gênero do cliente'),
    ('{link_sugestao}', 'Link do disco sugerido na loja'),
    ('{sugestoes}', 'Três discos sugeridos, um por linha, cada um com o link (VIP)'),
]

REGUA_TABELA = [  # etapa, de, até, só 1ª compra, tem controle, dá benefício, oferta, cupom, validade em dias
    ('Etapa 0 · Pós-compra', 15, 44, 'Sim', 'Sim', 'Não', 'Obrigado + novidades do gênero, sem desconto', '', '', 'Painel · Etapa 0 Pós-compra'),
    ('Etapa 1 · Lembrete', 45, 74, 'Não', 'Sim', 'Não', 'Novidades + "o que você está caçando?", sem desconto', '', '', 'Painel · Etapa 1 Lembrete'),
    ('VIP · WhatsApp', 75, 104, 'Não', 'Não', 'Não', 'Mensagem pessoal, sem cupom (VIP = 3+ compras ou R$1.000+ gastos)', '', '', ''),
    ('Etapa 2 · Convite', 90, 119, 'Não', 'Sim', 'Sim', 'Frete grátis acima de R$150', 'VOLTAFRETE<MÊS>', 10, 'Painel · Etapa 2 Convite'),
    ('Etapa 3 · Última chamada', 180, 209, 'Não', 'Sim', 'Sim', '10% em toda a loja', 'VOLTA10<MÊS>', 7, 'Painel · Etapa 3 Última chamada'),
    (DESCANSO, 210, '', '', '', '', 'Só newsletter e datas grandes', '', '', ''),
]
REGUA_CABECALHO = ['Etapa', 'Dias a partir de', 'Dias até', 'Só quem tem 1 compra', 'Tem controle', 'Dá benefício (cupom ou frete)',
                   'Oferta', 'Cupom', 'Validade (dias)', 'Lista no Brevo']
REGUA_PARAMETROS = [  # nome na planilha, campo de ParametrosRegua, padrão, o que significa
    ('VIP: mínimo de compras', 'vip_min_compras', 3, 'VIP = esse número de compras ou o gasto mínimo abaixo'),
    ('VIP: gasto mínimo (R$)', 'vip_min_gasto', 1000, 'VIP = o mínimo de compras acima ou esse total gasto'),
    ('Controle de cada etapa (%)', 'controle', 10, 'Parte de cada etapa que não recebe nada, para medir o resultado'),
    ('Mínimo de pessoas na etapa para ter controle', 'minimo_para_controle', 10, 'Etapa menor que isso não tem controle'),
    ('Dias entre benefícios', 'dias_entre_beneficios', 90, 'Máximo de um cupom ou frete grátis nesse prazo por cliente'),
    ('Janela do resultado (dias)', 'janela_resultado', 30, 'Compra em até esse prazo depois do envio conta para a etapa'),
    ('Mínimo de pessoas por grupo para medir', 'amostra_minima', 30, 'Abaixo disso o painel mostra "dados insuficientes"'),
]


@dataclass(frozen=True)
class Teste45:
    inicio: date = date(2026, 10, 12)
    fim: date = date(2027, 1, 18)
    controle_pct: float = 10
    email_pct: float = 30
    whatsapp_pct: float = 60
    dias_para_contatar: int = 30
    fila_inicio: date = date(2026, 10, 12)  # VIP, 45 dias e garimpo só entram a partir daqui


@dataclass(frozen=True)
class FilaUnica:
    prioridade: tuple[str, ...] = ('Carrinho', 'Garimpo', 'VIP', '45 dias')
    limite_por_dia: int = 40
    dias_entre_whatsapp: int = 30


def _sim(valor: Any, padrao: bool = False) -> bool:
    texto = str(valor).strip().lower()
    return padrao if texto == '' else texto in ('sim', 's', 'true', '1', 'yes')


def _data(valor: Any, padrao: date) -> date:
    t = cp.para_momento(valor)
    return padrao if t is None else t.date()


# ----------------------------------------------------------------------------
# Criar o que falta (nunca altera o que já existe)
# ----------------------------------------------------------------------------
def _nomes_da_coluna_a(aba: Any) -> set[str]:
    return {str(l[0]).strip() for l in aba.get_all_values() if l and str(l[0]).strip()}


def completar_configuracao(planilha: PlanilhaGoogle) -> int:
    aba = planilha._ss.worksheet(cp.ABA_CONFIG)
    existentes = _nomes_da_coluna_a(aba)
    todos = [(n, v, d) for n, _, v, d in cp.CONFIG] + CONFIG_NOVA  # o que faltar na Configuração entra no fim
    faltam = [[n, v, d] for n, v, d in todos if n not in existentes]
    if faltam:
        aba.append_rows(faltam, value_input_option='RAW')
    return len(faltam)


def completar_mensagens(planilha: PlanilhaGoogle) -> int:
    aba = planilha._ss.worksheet(cp.ABA_MENSAGENS)
    existentes = _nomes_da_coluna_a(aba)
    linhas: list[list[Any]] = []
    novos = {m: v for m, v in MODELOS_NOVOS.items() if m not in existentes}
    if novos:
        linhas += [[], ['Modelos da fila única (45 dias, VIP e aviso de garimpo)', '', '']]
        linhas += [[m, quando, texto] for m, (quando, texto) in novos.items()]
    marcadores = [m for m in MARCADORES_NOVOS if m[0] not in existentes]
    if marcadores:
        linhas += [[], ['Marcadores novos', '', '']] + [[a, b, ''] for a, b in marcadores]
    if linhas:
        aba.append_rows(linhas, value_input_option='RAW')
    return len(novos)


def garantir_aba_regua(planilha: PlanilhaGoogle) -> Gravacao:
    aba, criada = planilha._aba(ABA_REGUA_PARAMETROS, 30, len(REGUA_CABECALHO))
    if not criada:  # aba já existia sem a coluna "Lista no Brevo": ela entra no fim, sem mexer no resto
        cab = [str(x).strip() for x in (aba.get_all_values() or [[]])[0]]
        if cab and 'Lista no Brevo' not in cab:
            col = len(cab) + 1
            if aba.col_count < col:
                aba.resize(cols=col)
            listas = {l[0]: l[-1] for l in REGUA_TABELA}
            todas = aba.get_all_values()
            letra = _letra(col)
            aba.update([['Lista no Brevo']], f'{letra}1', raw=True)
            for i, linha in enumerate(todas[1:], start=2):
                nome = str(linha[0]).strip() if linha else ''
                if nome in listas:
                    aba.update([[listas[nome]]], f'{letra}{i}', raw=True)
    if criada:
        linhas: list[list[Any]] = [REGUA_CABECALHO] + [list(l) for l in REGUA_TABELA]
        linhas += [[], ['Parâmetro', 'Valor', 'O que significa'] + [''] * (len(REGUA_CABECALHO) - 3)]
        linhas += [[n, v, d] + [''] * (len(REGUA_CABECALHO) - 3) for n, _, v, d in REGUA_PARAMETROS]
        planilha._escrever(aba, linhas)
        cp._formatar_cabecalho(aba, len(REGUA_CABECALHO))
    return Gravacao(ABA_REGUA_PARAMETROS, len(REGUA_TABELA), len(REGUA_CABECALHO), 'criada' if criada else 'mantida')


def preparar_abas(planilha: PlanilhaGoogle) -> list[Gravacao]:
    """Cria a aba Régua e completa Configuração e Mensagens. Chamar depois de `carrinhos_planilha.garantir_abas`."""
    feitos = [garantir_aba_regua(planilha)]
    n = completar_configuracao(planilha)
    feitos.append(Gravacao(cp.ABA_CONFIG, n, 3, 'completada' if n else 'mantida'))
    m = completar_mensagens(planilha)
    feitos.append(Gravacao(cp.ABA_MENSAGENS, m, 3, 'completada' if m else 'mantida'))
    from painel_monstro.saidas import contatos_manuais as manuais
    feitos.append(planilha.garantir_cabecalho(cp.ABA_CONTATOS_MANUAIS, cp.CONTATOS_MANUAIS_COLUNAS, manuais.NOTAS))
    feitos.append(planilha.garantir_cabecalho('desejos', DESEJOS_COLUNAS, {
        'email': 'Email do cliente que pediu o disco.', 'telefone': 'WhatsApp do cliente.', 'nome': 'Nome do cliente.',
        'desejo': 'O que ele procura (artista e disco). O aviso sai quando um disco com essas palavras entra em estoque.',
        'data': 'Quando ele pediu (AAAA-MM-DD). Só vale disco que chegou depois.',
        'status': 'Deixe vazio. Escreva "Avisado" para parar de avisar.'}))
    return feitos


# ----------------------------------------------------------------------------
# Leitura
# ----------------------------------------------------------------------------
def ler_regua(planilha: PlanilhaGoogle) -> ParametrosRegua:
    """Janelas, ofertas e critérios da aba `Régua`. Valor ausente ou ilegível volta ao padrão."""
    from painel_monstro.motor.regua import PADRAO
    try:
        aba = planilha._ss.worksheet(ABA_REGUA_PARAMETROS)
    except gspread.exceptions.WorksheetNotFound:
        return PADRAO
    valores = cp._valores(aba)
    if not valores:
        return PADRAO
    cab = [str(x).strip() for x in valores[0]]
    linhas = []
    i = 1
    while i < len(valores) and any(str(x).strip() for x in valores[i]):
        linhas.append(dict(zip(cab, valores[i])))
        i += 1
    por_nome = {str(l.get('Etapa', '')).strip(): l for l in linhas}
    padrao_por_nome = {e.nome: e for e in (*PADRAO.etapas, PADRAO.vip)}

    def etapa(nome: str) -> Etapa:
        base = padrao_por_nome[nome]
        l = por_nome.get(nome)
        if not l:
            return base
        return Etapa(nome=nome,
                     dias_min=int(cp.numero(l.get('Dias a partir de'), base.dias_min)),
                     dias_max=int(cp.numero(l.get('Dias até'), base.dias_max)),
                     so_primeira_compra=_sim(l.get('Só quem tem 1 compra'), base.so_primeira_compra),
                     tem_controle=_sim(l.get('Tem controle'), base.tem_controle),
                     beneficio=_sim(l.get('Dá benefício (cupom ou frete)'), base.beneficio))

    campos: dict[str, Any] = {'etapas': tuple(etapa(e.nome) for e in PADRAO.etapas), 'vip': etapa(PADRAO.vip.nome)}
    if DESCANSO in por_nome:
        campos['descanso_a_partir_de'] = int(cp.numero(por_nome[DESCANSO].get('Dias a partir de'), PADRAO.descanso_a_partir_de))
    parametros = {str(l[0]).strip(): l[1] if len(l) > 1 else '' for l in valores[i + 1:] if l and str(l[0]).strip()}
    for nome, campo, padrao, _ in REGUA_PARAMETROS:
        bruto = parametros.get(nome, '')
        if bruto in ('', None):
            continue
        v = cp.numero(bruto, float(padrao))
        campos[campo] = v / 100 if campo == 'controle' else (float(v) if campo == 'vip_min_gasto' else int(v))
    return replace(PADRAO, **campos)


def ler_listas_brevo(planilha: PlanilhaGoogle) -> dict[str, str]:
    """Nome da lista do Brevo de cada etapa (coluna "Lista no Brevo" da aba Régua), por código de etapa."""
    from painel_monstro.saidas import brevo
    padrao = dict(zip(brevo.CODIGOS_DAS_ETAPAS, brevo.LISTAS_PADRAO))
    try:
        valores = cp._valores(planilha._ss.worksheet(ABA_REGUA_PARAMETROS))
    except gspread.exceptions.WorksheetNotFound:
        return padrao
    if not valores:
        return padrao
    cab = [str(x).strip() for x in valores[0]]
    if 'Lista no Brevo' not in cab:
        return padrao
    nomes = [e.nome for e in motor_regua_padrao().etapas]
    por_etapa = {}
    for l in valores[1:]:
        if not l or not str(l[0]).strip():
            break
        por_etapa[str(l[0]).strip()] = str(l[cab.index('Lista no Brevo')]).strip() if len(l) > cab.index('Lista no Brevo') else ''
    saida = dict(padrao)
    for codigo, nome in zip(brevo.CODIGOS_DAS_ETAPAS, nomes):
        if por_etapa.get(nome):
            saida[codigo] = por_etapa[nome]
    return saida


def ler_cupons_regua(planilha: PlanilhaGoogle) -> dict[str, tuple[str, int]]:
    """Cupom (com <MÊS>) e validade em dias de cada etapa, da aba Régua, por código de etapa (ETAPA_2 e ETAPA_3 usam)."""
    from painel_monstro.saidas import brevo
    try:
        valores = cp._valores(planilha._ss.worksheet(ABA_REGUA_PARAMETROS))
    except Exception:  # noqa: BLE001 - aba ausente ou planilha de teste
        valores = []
    if not valores:
        return {}
    cab = [str(x).strip() for x in valores[0]]
    if 'Cupom' not in cab or 'Validade (dias)' not in cab:
        return {}
    nomes = [e.nome for e in motor_regua_padrao().etapas]
    por_nome = {}
    for l in valores[1:]:
        if not l or not str(l[0]).strip():
            break
        cupom = str(l[cab.index('Cupom')]).strip() if len(l) > cab.index('Cupom') else ''
        validade = int(cp.numero(l[cab.index('Validade (dias)')], 0)) if len(l) > cab.index('Validade (dias)') else 0
        por_nome[str(l[0]).strip()] = (cupom, validade)
    return {codigo: por_nome[nome] for codigo, nome in zip(brevo.CODIGOS_DAS_ETAPAS, nomes) if nome in por_nome and por_nome[nome][0]}


def motor_regua_padrao():
    from painel_monstro.motor.regua import PADRAO
    return PADRAO


def _config_por_nome(planilha: PlanilhaGoogle) -> dict[str, Any]:
    aba = planilha._ss.worksheet(cp.ABA_CONFIG)
    return {str(l[0]).strip(): l[1] if len(l) > 1 else '' for l in cp._valores(aba)[1:] if l and str(l[0]).strip()}


def ler_teste45(planilha: PlanilhaGoogle) -> Teste45:
    cfg = _config_por_nome(planilha)
    p = Teste45()

    def num(nome: str, padrao: float) -> float:
        return cp.numero(cfg.get(nome, ''), padrao)
    return Teste45(
        inicio=_data(cfg.get('Teste WhatsApp 45 dias: início'), p.inicio), fim=_data(cfg.get('Teste WhatsApp 45 dias: fim'), p.fim),
        controle_pct=num('Teste 45 dias: grupo de controle (%)', p.controle_pct), email_pct=num('Teste 45 dias: só email (%)', p.email_pct),
        whatsapp_pct=num('Teste 45 dias: email e WhatsApp (%)', p.whatsapp_pct),
        dias_para_contatar=int(num('Dias para contatar depois de completar 45 dias', p.dias_para_contatar)),
        fila_inicio=_data(cfg.get('Fila única: início'), p.fila_inicio))


def ler_fila_unica(planilha: PlanilhaGoogle) -> FilaUnica:
    cfg = _config_por_nome(planilha)
    p = FilaUnica()
    ordem = tuple(x.strip() for x in str(cfg.get('Ordem de prioridade da fila') or '').split(',') if x.strip())
    return FilaUnica(prioridade=ordem or p.prioridade,
                     limite_por_dia=int(cp.numero(cfg.get('Limite de mensagens por dia'), p.limite_por_dia)))


# ----------------------------------------------------------------------------
# Registro do sorteio do teste de 45 dias (aba regua, mes = teste45)
# ----------------------------------------------------------------------------
def ler_sorteios(planilha: PlanilhaGoogle) -> dict[str, str]:
    """email -> grupo ("controle", "email" ou "whatsapp") de quem já foi sorteado."""
    try:
        aba = planilha._ss.worksheet(ABA_REGUA)
    except gspread.exceptions.WorksheetNotFound:
        return {}
    h = planilha._ler_historico(aba, REGUA_COLUNAS)
    h = h[h['mes'].astype(str) == MES_DO_TESTE]
    return {str(e).strip().lower(): str(g) for e, g in zip(h['email'], h['grupo'])}


def gravar_sorteios(planilha: PlanilhaGoogle, novos: list[dict[str, Any]]) -> int:
    """Acrescenta sorteios novos no fim da aba regua; nunca troca nem apaga linha existente."""
    if not novos:
        return 0
    aba, criada = planilha._aba(ABA_REGUA, 100, len(REGUA_COLUNAS))
    if criada or not aba.get_all_values():
        aba.update([REGUA_COLUNAS], 'A1', raw=True)
    ja = ler_sorteios(planilha)
    linhas = [[n.get(col, '') for col in REGUA_COLUNAS] for n in novos if str(n['email']).strip().lower() not in ja]
    if linhas:
        aba.append_rows(linhas, value_input_option='RAW')
    return len(linhas)


def linha_do_sorteio(email: str, grupo: str, dia: date, dias: int, n_compras: int, total: float, vip: bool) -> dict[str, Any]:
    return {'mes': MES_DO_TESTE, 'data_referencia': dia.strftime('%Y-%m-%d'), 'email': email.strip().lower(),
            'etapa': ETAPA_DO_TESTE, 'grupo': grupo, 'dias_sem_comprar': dias, 'n_compras': n_compras,
            'total_gasto': round(float(total), 2), 'vip': bool(vip)}
