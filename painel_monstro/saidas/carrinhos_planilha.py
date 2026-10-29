"""Carrinho abandonado na Planilha Google: abas Configuração, Mensagens, Fila, Bloqueio e Resultados.

Regras (AGENTS.md, "Carrinho abandonado"; D-013, D-015, D-020):
- `Configuração` e `Mensagens` são do Túlio: o Painel só cria com os valores padrão quando a aba não existe e
  lê os dois a cada execução. Nunca sobrescreve o que está lá.
- `Fila`: o Painel preenche as colunas dele (carrinho, cliente, itens, valor, link, estoque, situação, mensagem...)
  e NUNCA toca nas colunas da Mariana (Toques já enviados, Último envio em, Status, Modelo escolhido, Mensagem
  editada). As linhas não mudam de lugar: carrinho novo entra no fim da aba.
- `Bloqueio`: o Painel só acrescenta (quando o Status vira "Não quer"); nunca apaga.
- `Resultados`: o Painel regrava inteira (recuperação por modelo e grupo de comparação).
- Tudo vai como valor, nunca como fórmula, exceto a coluna "Abrir com minha edição", que usa a mensagem editada
  da Mariana e por isso precisa ser fórmula.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import gspread
import pandas as pd
from gspread.utils import ValueRenderOption

from painel_monstro.coletor.nuvemshop_api import FUSO_LOJA
from painel_monstro.coletor.planilhas_csv import Tabelas
from painel_monstro.saidas import carrinhos as c
from painel_monstro.saidas.planilha_google import Gravacao, PlanilhaGoogle, _letra

ABA_CONFIG, ABA_MENSAGENS, ABA_FILA, ABA_BLOQUEIO, ABA_RESULTADOS = 'Configuração', 'Mensagens', 'Fila', 'Bloqueio', 'Resultados'
JANELA_RECUPERACAO_DIAS = 7  # recuperado = pedido pago em até 7 dias depois do primeiro toque (AGENTS.md)

# (nome na planilha, campo de Parametros, valor padrão, o que significa)
CONFIG = [
    ('Assinatura', 'assinatura', 'Mariana, da Monstro Discos', 'Como a mensagem se apresenta ({assinatura})'),
    ('Começar a contatar depois de (horas)', 'comecar_depois_de_horas', 12, 'O email automático da Nuvemshop sai em 6 horas; o WhatsApp entra depois'),
    ('Parar de contatar depois de (dias)', 'parar_depois_de_dias', 7, 'Carrinho mais velho que isso sai da fila'),
    ('Intervalo entre toques (horas)', 'intervalo_entre_toques_horas', 24, 'Tempo mínimo entre um contato e o próximo'),
    ('Máximo de toques', 'maximo_de_toques', 3, 'Depois disso, não contatar mais'),
    ('Carrinho mínimo para frete grátis (R$)', 'minimo_frete_gratis', 200, 'Valor dos produtos após desconto, sem frete; abaixo disso não oferece frete grátis'),
    ('Carrinho mínimo para cupom de desconto (R$)', 'minimo_cupom', 200, 'No 3º toque, abaixo disso não há cupom'),
    ('Cupom de frete grátis', 'cupom_frete', 'VOLTAFRETEOUT', 'Trocar todo mês ({cupom} no modelo T2_FRETE)'),
    ('Cupom de desconto', 'cupom_desconto', 'VOLTA10OUT', '10% só em usados, trocar todo mês ({cupom} no modelo T3_CUPOM)'),
    ('Validade da oferta', 'prazo', 'válido até amanhã às 23h59', 'Texto que entra no lugar de {prazo}'),
    ('Site da loja', 'site', 'https://lojamonstro.com.br', 'Texto que entra no lugar de {loja}'),
    ('Valor mínimo do carrinho (R$)', 'valor_minimo_do_carrinho', 0, 'Carrinho abaixo disso não entra na fila (0 = todos entram)'),
    ('Dias da fila', 'dias_da_fila', 'seg a sáb', 'Dias em que a fila sai. Nos outros dias o que estava pendente passa para o próximo dia de fila e o prazo entre toques não conta. Ex.: "seg a sáb", "seg, qua, sex", "todos"'),
    ('Horários da fila', None, '10h e 17h', 'Quando o Painel manda a fila do dia por email'),
    ('Emails que recebem a fila', None, '', 'Separe por vírgula. O Túlio cobre quando a Mariana não estiver'),
    ('Limite de mensagens por dia', None, 40, 'Começa amplo. O que passar fica para o dia seguinte, começando pela menor prioridade'),
    ('Cupom precisa de aprovação do Léo?', 'cupom_precisa_de_aprovacao', 'Não', 'Não = a regra de valor mínimo já vale como aprovação. Sim = a linha de cupom espera o Léo'),
    ('Grupo de comparação do carrinho (%)', 'comparacao_pct', 10, 'Carrinhos sorteados que só recebem o email da Nuvemshop, para medir quanto o WhatsApp recupera a mais'),
    ('Ordem de prioridade da fila', None, 'Carrinho, Garimpo, VIP, 45 dias', 'Quem aparece primeiro na fila do dia'),
    ('Custo máximo do frete grátis (R$)', 'maximo_custo_frete', 30, 'Teto do preço cotado ao cliente pela API para decidir a mensagem; não é custo final de etiqueta'),
    ('Limite do frete garantido no checkout?', 'frete_limite_garantido', 'Não', 'Legado D-055, sem efeito nas mensagens desde D-056. Cotação decide a oferta; não garante teto do cupom no checkout'),
]
MENSAGENS_QUANDO = {
    'T1': '1º toque, padrão', 'T1_UNICO': '1º toque, discos usados de exemplar único',
    'T1_RECORRENTE': '1º toque, cliente que já comprou antes', 'T2_FRETE': '2º toque, carrinho acima do mínimo de frete grátis',
    'T2_ESCASSEZ': '2º toque, carrinho abaixo do mínimo (sem oferta)', 'T3_CUPOM': '3º toque, carrinho acima do mínimo de cupom',
    'T2_LEMBRETE': 'Lembrete sem benefício, sem afirmar exemplar único',
    'ESGOTADO': 'Algum disco do carrinho esgotou (não manda o link)',
    'G45': 'WhatsApp de garimpo aos 45 dias (sem cupom)',
    'G45_GERAL': 'WhatsApp aos 45 dias sem recomendação específica (quando o produto comprado não tem gênero confiável)',
    'VIP': 'WhatsApp pessoal para cliente VIP aos 75 dias (sem cupom)',
    'ALERTA_GARIMPO': 'Aviso de que chegou o disco que o cliente pediu',
}
MARCADORES_AJUDA = [
    ('{nome}', 'Primeiro nome do cliente'), ('{itens}', 'Discos do carrinho, em texto'), ('{valor}', 'Valor do carrinho'),
    ('{link_carrinho}', 'Link para o cliente retomar a compra'), ('{cupom}', 'Cupom da oferta do modelo'),
    ('{prazo}', 'Validade da oferta (aba Configuração)'), ('{assinatura}', 'Quem assina (aba Configuração)'),
    ('{loja}', 'Site da loja (aba Configuração)'),
    ('{ultimo_disco}', 'Último disco que o cliente comprou, como "Álbum (Artista)" (G45)'),
    ('{sugestao}', 'Um disco em estoque da família de gênero do cliente, como "Álbum (Artista)"'),
    ('{link_sugestao}', 'Link do disco sugerido na loja'),
    ('{sugestoes}', 'Três discos sugeridos, um por linha, cada um com o link (VIP)'),
]

# Colunas da Fila: (nome, dono). "Painel" é regravada a cada execução; "Mariana" nunca é tocada.
FILA = [
    ('Carrinho', 'P'), ('Abandonado em', 'P'), ('Cliente', 'P'), ('Email', 'P'), ('Telefone', 'P'), ('Itens', 'P'), ('Valor (R$)', 'P'),
    ('Link do carrinho', 'P'), ('Estoque', 'P'), ('Estoque conferido em', 'P'),
    ('Toques já enviados', 'M'), ('Último envio em', 'M'), ('Status', 'M'), ('Modelo escolhido', 'M'), ('Mensagem editada', 'M'),
    ('Horas desde o abandono', 'P'), ('Próximo toque', 'P'), ('Situação', 'P'), ('Modelo usado', 'P'), ('Cupom', 'P'),
    ('Mensagem pronta', 'P'), ('Abrir WhatsApp', 'P'), ('Abrir com minha edição', 'F'), ('Próximo envio a partir de', 'P'),
    ('Primeiro toque em', 'P'), ('Toques vistos', 'P'), ('Modelos enviados', 'P'), ('Grupo', 'P'), ('Recuperado', 'P'),
    ('Receita recuperada (R$)', 'P'), ('Cupom do pedido', 'P'), ('Observações', 'P'), ('Origem', 'P'),
    ('Encerrado em', 'P'), ('Na fila desde', 'P'), ('Recuperado em', 'P'),
    ('Enviei agora', 'M'),
    ('Respondeu agora', 'M'), ('Contato inválido agora', 'M'), ('Não quer agora', 'M'),
]
NOMES = [n for n, _ in FILA]
COL = {n: i for i, n in enumerate(NOMES)}
DONO = dict(FILA)
STATUS_OPCOES = ['Em andamento', 'Respondeu', 'Recuperado', 'Não quer', 'Contato inválido']
BLOQUEIO_COLUNAS = ['Telefone', 'Email', 'Data', 'Motivo']


def garantir_visualizacoes(aba: Any) -> None:
    """Filtros pessoais, dinâmicos e sem ordenação física de linhas (D-051)."""
    ss = aba.spreadsheet
    if not hasattr(ss, 'fetch_sheet_metadata'):  # planilha simulada nos testes
        return
    meta = ss.fetch_sheet_metadata()
    sheet = next(s for s in meta['sheets'] if s['properties']['sheetId'] == aba.id)
    existentes = {v['filterViewId']: v for v in sheet.get('filterViews', [])}
    visoes = [(101001, 'Para enviar', {'17': {'condition': {'type': 'TEXT_EQ', 'values': [{'userEnteredValue': 'Contatar'}]}}}),
              (101002, 'Acompanhar respostas', {'10': {'condition': {'type': 'CUSTOM_FORMULA', 'values': [
                  {'userEnteredValue': '=AND($A2<>"";$K2>0;$AC2<>"Sim";$M2<>"Não quer";$M2<>"Contato inválido";$M2<>"Recuperado")'}]}}}),
              (101003, 'Histórico e busca', {'0': {'condition': {'type': 'NOT_BLANK'}}})]
    requests = []
    for vid, titulo, criterios in visoes:
        filtro = {'filterViewId': vid, 'title': titulo, 'range': {'sheetId': aba.id,
                  'startRowIndex': 0, 'endRowIndex': aba.row_count, 'startColumnIndex': 0, 'endColumnIndex': len(NOMES)},
                  'criteria': criterios}
        requests.append({'updateFilterView': {'filter': filtro, 'fields': 'title,range,criteria'}} if vid in existentes
                        else {'addFilterView': {'filter': filtro}})
    ss.batch_update({'requests': requests})


# ----------------------------------------------------------------------------
# Conversões
# ----------------------------------------------------------------------------
def texto_seguro(valor: Any) -> Any:
    """Nada que venha de cliente pode virar fórmula na planilha."""
    if isinstance(valor, str) and valor[:1] in ('=', '+', '-', '@'):
        return "'" + valor
    return valor


def para_momento(valor: Any) -> pd.Timestamp | None:
    """Data da planilha (número de série do Sheets ou texto) em horário de Brasília, ou None."""
    if valor in ('', None):
        return None
    try:
        if isinstance(valor, (int, float)):
            t = pd.Timestamp('1899-12-30') + pd.Timedelta(days=float(valor))
        else:
            t = pd.to_datetime(str(valor).strip(), dayfirst='/' in str(valor), errors='raise')
    except (ValueError, TypeError):
        return None
    if pd.isna(t):
        return None
    return t.tz_localize(FUSO_LOJA, nonexistent='shift_forward', ambiguous=True) if t.tzinfo is None else t.tz_convert(FUSO_LOJA)


def em_texto(momento: pd.Timestamp | None) -> str:
    return '' if momento is None else pd.Timestamp(momento).tz_convert(FUSO_LOJA).strftime('%Y-%m-%d %H:%M')


def numero(valor: Any, padrao: float = 0.0) -> float:
    if valor in ('', None):
        return padrao
    if isinstance(valor, (int, float)):
        return float(valor)
    try:
        return float(str(valor).replace('R$', '').replace('.', '').replace(',', '.').strip()) if ',' in str(valor) else float(str(valor).strip())
    except ValueError:
        return padrao


# ----------------------------------------------------------------------------
# Configuração, Mensagens e Bloqueio
# ----------------------------------------------------------------------------
def _valores(aba: Any) -> list[list[Any]]:
    return aba.get_all_values(value_render_option=ValueRenderOption.unformatted)


def _formatar_cabecalho(aba: Any, largura: int) -> None:
    try:
        aba.format('1:1', {'textFormat': {'bold': True}})
        aba.freeze(rows=1)
    except Exception:  # só enfeite
        pass


def garantir_abas(planilha: PlanilhaGoogle) -> list[Gravacao]:
    """Cria o que falta com os valores padrão. Aba que já existe não é alterada."""
    feitos = []
    aba, criada = planilha._aba(ABA_CONFIG, len(CONFIG) + 2, 3)
    if criada:
        planilha._escrever(aba, [['Parâmetro', 'Valor', 'O que significa']] + [[n, v, d] for n, _, v, d in CONFIG])
        _formatar_cabecalho(aba, 3)
    else:
        atuais = {str(l[0]).strip() for l in _valores(aba) if l}
        novos = [[n, v, d] for n, _, v, d in CONFIG[-2:] if n not in atuais]
        if novos:
            aba.append_rows(novos, value_input_option='RAW')
    feitos.append(Gravacao(ABA_CONFIG, len(CONFIG), 3, 'criada' if criada else 'mantida'))

    aba, criada = planilha._aba(ABA_MENSAGENS, 20, 3)
    if criada:
        linhas = [['Modelo', 'Quando usar', 'Mensagem (edite à vontade, mantendo os marcadores entre chaves)']]
        linhas += [[m, MENSAGENS_QUANDO[m], c.MODELOS_PADRAO[m]] for m in c.MODELOS_PADRAO]
        linhas += [[], ['Marcadores'], *[[a, b] for a, b in MARCADORES_AJUDA]]
        planilha._escrever(aba, [l + [''] * (3 - len(l)) for l in linhas])
        _formatar_cabecalho(aba, 3)
    else:
        atuais = {str(l[0]).strip() for l in _valores(aba) if l}
        if 'T2_LEMBRETE' not in atuais:
            aba.append_rows([['T2_LEMBRETE', MENSAGENS_QUANDO['T2_LEMBRETE'], c.MODELOS_PADRAO['T2_LEMBRETE']]], value_input_option='RAW')
        if 'G45_GERAL' not in atuais:
            aba.append_rows([['G45_GERAL', MENSAGENS_QUANDO['G45_GERAL'], c.MODELOS_PADRAO['G45_GERAL']]], value_input_option='RAW')
    feitos.append(Gravacao(ABA_MENSAGENS, len(c.MODELOS_PADRAO), 3, 'criada' if criada else 'mantida'))

    feitos.append(planilha.garantir_cabecalho(ABA_BLOQUEIO, BLOQUEIO_COLUNAS, {
        'Telefone': 'Pode ser com ou sem formatação.', 'Email': 'Email de quem não quer receber.',
        'Motivo': 'Por que está na lista (o Painel escreve "Não quer (Fila)").'}))

    aba, criada = planilha._aba(ABA_FILA, 200, len(NOMES))
    if criada or not any(any(str(x).strip() for x in l) for l in aba.get_all_values()):
        if aba.col_count < len(NOMES):
            aba.resize(cols=len(NOMES))
        aba.update([NOMES], 'A1', raw=True)
        _formatar_fila(aba)
        feitos.append(Gravacao(ABA_FILA, 0, len(NOMES), 'criada'))
    else:
        atual = [str(x).strip() for x in (aba.get_all_values() or [[]])[0]]
        while atual and not atual[-1]:
            atual.pop()
        if atual != NOMES[:len(atual)]:
            raise ValueError('As colunas da Fila foram movidas ou renomeadas. Nada foi escrito na Fila; restaurar o modelo antes de continuar.')
        if len(atual) < len(NOMES) and atual == NOMES[:len(atual)]:  # coluna nova entra no fim, sem mexer nas outras
            if aba.col_count < len(NOMES):
                aba.resize(cols=len(NOMES))
            aba.update([NOMES[len(atual):]], f'{_letra(len(atual) + 1)}1', raw=True)
            _formatar_fila(aba)
        feitos.append(Gravacao(ABA_FILA, max(len(aba.get_all_values()) - 1, 0), len(NOMES), 'mantida'))
    garantir_visualizacoes(aba)
    return feitos


def _formatar_fila(aba: Any) -> None:
    """Cabeçalho em negrito, colunas da Mariana em amarelo e Status com lista de opções. Só enfeite."""
    try:
        aba.format('1:1', {'textFormat': {'bold': True}})
        aba.freeze(rows=1)  # preserva as colunas que a equipe escolheu congelar
        j, k = COL['Toques já enviados'] + 1, COL['Mensagem editada'] + 1
        aba.format(f'{_letra(j)}1:{_letra(k)}1', {'backgroundColor': {'red': 1, 'green': 0.95, 'blue': 0.6}})
        aba.spreadsheet.batch_update({'requests': [{'setDataValidation': {
            'range': {'sheetId': aba.id, 'startRowIndex': 1, 'endRowIndex': aba.row_count, 'startColumnIndex': COL['Status'], 'endColumnIndex': COL['Status'] + 1},
            'rule': {'condition': {'type': 'ONE_OF_LIST', 'values': [{'userEnteredValue': s} for s in STATUS_OPCOES]}, 'showCustomUi': True, 'strict': False}}},
            {'setDataValidation': {'range': {'sheetId': aba.id, 'startRowIndex': 1, 'endRowIndex': aba.row_count,
                'startColumnIndex': COL['Enviei agora'], 'endColumnIndex': len(NOMES)},
                'rule': {'condition': {'type': 'BOOLEAN'}, 'showCustomUi': True, 'strict': True}}}]})
    except Exception:
        pass


def ler_parametros(planilha: PlanilhaGoogle) -> c.Parametros:
    """Lê as abas Configuração e Mensagens. Valor ausente ou ilegível volta ao padrão."""
    aba = planilha._ss.worksheet(ABA_CONFIG)
    por_nome = {str(l[0]).strip(): l[1] if len(l) > 1 else '' for l in _valores(aba)[1:] if l and str(l[0]).strip()}
    padrao = c.Parametros()
    campos: dict[str, Any] = {}
    for nome, campo, valor_padrao, _ in CONFIG:
        if campo is None:
            continue
        bruto = por_nome.get(nome, '')
        if bruto in ('', None):
            continue
        atual = getattr(padrao, campo)
        if isinstance(atual, bool):
            campos[campo] = str(bruto).strip().lower() in ('sim', 's', 'true', '1')
        elif campo == 'dias_da_fila':
            campos[campo] = c.ler_dias_da_fila(bruto)
        elif isinstance(atual, (int, float)):
            campos[campo] = numero(bruto, atual)
            if campo == 'maximo_de_toques':
                campos[campo] = int(campos[campo])
        else:
            campos[campo] = str(bruto).strip()
    modelos = dict(c.MODELOS_PADRAO)
    try:
        for l in _valores(planilha._ss.worksheet(ABA_MENSAGENS))[1:]:
            if len(l) >= 3 and re.fullmatch(r'[A-Z0-9_]+', str(l[0]).strip()) and str(l[2]).strip():
                modelos[str(l[0]).strip()] = str(l[2]).strip()
    except gspread.exceptions.WorksheetNotFound:
        pass
    return c.Parametros(**campos, modelos=modelos)


def ler_bloqueio(planilha: PlanilhaGoogle) -> set[str]:
    try:
        aba = planilha._ss.worksheet(ABA_BLOQUEIO)
    except gspread.exceptions.WorksheetNotFound:
        return set()
    achados: set[str] = set()
    for l in _valores(aba)[1:]:
        for valor in l[:2]:
            texto = str(valor).strip()
            if texto:
                achados.add(texto.lower() if '@' in texto else c.so_digitos(texto))
    return {a for a in achados if a}


# ----------------------------------------------------------------------------
# Fila
# ----------------------------------------------------------------------------
@dataclass
class LinhaExistente:
    posicao: int  # linha na planilha (1 = cabeçalho)
    valores: dict[str, Any]

    @property
    def toques(self) -> int:
        return int(numero(self.valores.get('Toques já enviados')))

    @property
    def ultimo_envio(self) -> pd.Timestamp | None:
        return para_momento(self.valores.get('Último envio em'))

    @property
    def status(self) -> str:
        return str(self.valores.get('Status') or '').strip()


def ler_fila(aba: Any) -> dict[str, LinhaExistente]:
    valores = _valores(aba)
    if not valores:
        return {}
    cab = [str(x).strip() for x in valores[0]]
    saida: dict[str, LinhaExistente] = {}
    for i, l in enumerate(valores[1:], start=2):
        d = {cab[j]: l[j] if j < len(l) else '' for j in range(len(cab)) if cab[j]}
        chave = str(d.get('Carrinho', '')).strip()
        if chave.endswith('.0'):
            chave = chave[:-2]
        if chave:
            saida[chave] = LinhaExistente(i, d)
    return saida


def estado_da_fila(existentes: dict[str, LinhaExistente]) -> dict[str, dict]:
    estado = {}
    for k, e in existentes.items():
        modelos = [m for m in str(e.valores.get('Modelos enviados') or '').split(' > ') if m]
        # A caixa já pode ter sido marcada antes de a rotina contabilizar o modelo.
        if e.toques > int(numero(e.valores.get('Toques vistos'))):
            modelos.append(str(e.valores.get('Modelo usado') or '?'))
        estado[k] = {'toques': e.toques, 'ultimo_envio': e.ultimo_envio, 'status': e.status,
                     'modelo_escolhido': str(e.valores.get('Modelo escolhido') or '').strip(),
                     'modelos_enviados': modelos}
    return estado


def _pedidos_do_cliente(tabelas: Tabelas) -> tuple[dict[str, list[tuple[pd.Timestamp, float, str]]], dict[str, str]]:
    """Pedidos pagos por email (momento, receita de produtos, cupom) e telefone → email."""
    p = tabelas.pedidos[tabelas.pedidos['valido'].astype(bool)]
    por_email: dict[str, list] = {}
    for email, data, subtotal, desconto, cupom in zip(p['email'], pd.to_datetime(p['data']), p['subtotal'], p['desconto'], p['cupom']):
        momento = pd.Timestamp(data).tz_localize(FUSO_LOJA, nonexistent='shift_forward', ambiguous=True)
        por_email.setdefault(email, []).append((momento, round(float(subtotal) - float(desconto), 2), '' if pd.isna(cupom) else str(cupom)))
    tel = {c.telefone_whatsapp(t): e for e, t in tabelas.clientes.drop_duplicates('email', keep='last').set_index('email')['telefone'].items()
           if c.telefone_whatsapp(t)}
    return por_email, tel


def detectar_recuperacao(inicio: pd.Timestamp | None, email: str, fone: str, pedidos: dict, tel_para_email: dict) -> tuple[float, str] | None:
    """Primeiro pedido pago do mesmo email ou telefone em até 7 dias depois de `inicio`: (receita, cupom)."""
    if inicio is None:
        return None
    dono = (email or '').lower() or tel_para_email.get(fone, '')
    fim = inicio + pd.Timedelta(days=JANELA_RECUPERACAO_DIAS)
    achados = sorted(p for p in pedidos.get(dono, []) if inicio <= p[0] <= fim)
    return (achados[0][1], achados[0][2]) if achados else None


AVISO_NAO_MARCADA = 'Estava na fila de ontem e não foi marcada: confira no WhatsApp antes de enviar'
MOTIVO_DA_SAIDA = {
    'Encerrado sem contato': 'Saiu da fila sem nenhum contato: passou da janela de dias. Continua na régua normalmente.',
    'Encerrado: já comprou': 'O cliente comprou antes de ser contatado.',
    'Encerrado: bloqueado': 'O cliente pediu para não receber ou não aceita marketing.',
}
SITUACOES_FINAIS = ('Encerrado', 'Encerrado sem contato', 'Encerrado: já comprou', 'Encerrado: bloqueado', 'Recuperado', 'Encerrado: contato inválido')


def _linha_para_gravar(l: c.LinhaDaFila | None, ex: LinhaExistente | None, params: c.Parametros,
                       rec: tuple[float, str] | None, saida: str = '') -> dict[str, Any]:
    """Valores das colunas do Painel para uma linha. `l` é None quando a linha saiu da fila; `saida` diz por quê."""
    v: dict[str, Any] = {}
    if l is not None:
        v.update({
            'Carrinho': l.carrinho, 'Abandonado em': em_texto(l.abandonado_em), 'Cliente': texto_seguro(l.cliente), 'Email': texto_seguro(l.email),
            'Telefone': l.telefone, 'Itens': texto_seguro(l.itens), 'Valor (R$)': l.valor, 'Link do carrinho': l.link,
            'Estoque': l.estoque, 'Estoque conferido em': em_texto(l.estoque_conferido_em),
            'Horas desde o abandono': l.horas, 'Próximo toque': l.proximo_toque, 'Situação': l.situacao,
            'Modelo usado': l.modelo, 'Cupom': l.cupom, 'Mensagem pronta': l.mensagem, 'Abrir WhatsApp': l.link_whatsapp,
            'Próximo envio a partir de': em_texto(l.proximo_envio), 'Origem': l.origem,
            'Grupo': l.grupo or ('Comparação' if l.situacao == 'Grupo de comparação' else 'WhatsApp'),
            'Observações': texto_seguro(l.observacoes)})
    elif ex is not None:
        v['Situação'] = saida or 'Fora da fila'
        v['Observações'] = MOTIVO_DA_SAIDA.get(v['Situação'], '')  # limpa avisos antigos
    if rec is not None:
        v.update({'Recuperado': 'Sim', 'Receita recuperada (R$)': rec[0], 'Cupom do pedido': rec[1], 'Situação': 'Recuperado'})
    return v


@dataclass
class PlanoFila:
    """Tudo o que a rodada vai gravar na fila, já calculado. Nada foi escrito ainda (D-039)."""
    aba: Any
    existentes: dict[str, LinhaExistente]
    gravar: dict[int, dict[str, Any]]
    novas: list[dict[str, Any]]
    bloqueios_novos: list[list[Any]]
    sorteios: list[dict[str, Any]]
    finais: list[LinhaExistente]
    resultados: list[list[Any]]
    resumo_semana: list[list[Any]]
    contagens: dict[str, Any]
    linhas: list[c.LinhaDaFila] = field(default_factory=list)  # candidatas desta rodada, já com a situação final
    respostas_novas: list[list[Any]] = field(default_factory=list)  # quem passou a Respondeu agora (D-053)


def _motivo_de_saida(ex: LinhaExistente, params: c.Parametros, pedidos: dict, tel_para_email: dict, bloqueio: set[str],
                     agora_ts: pd.Timestamp) -> str:
    """Por que uma linha que estava na fila deixou de ser candidata (D-039)."""
    if ex.status == 'Contato inválido':
        return 'Encerrado: contato inválido'
    anterior = str(ex.valores.get('Situação') or '')
    if anterior in SITUACOES_FINAIS:
        return anterior
    if ex.toques >= 1:
        return 'Encerrado'  # recebeu pelo menos um toque e a janela acabou
    email = str(ex.valores.get('Email') or '').strip().lower()
    fone = c.so_digitos(ex.valores.get('Telefone'))
    quando = para_momento(ex.valores.get('Abandonado em'))
    if quando is not None and detectar_recuperacao(quando, email, fone, pedidos, tel_para_email) is not None:
        return 'Encerrado: já comprou'
    if (email and email in bloqueio) or (fone and fone in bloqueio) or ex.status == 'Não quer':
        return 'Encerrado: bloqueado'
    return 'Encerrado sem contato'


def planejar_fila(planilha: PlanilhaGoogle, api: Any, tabelas: Tabelas, agora: datetime | pd.Timestamp | None = None,
                  fila_unica: bool = False, somente_leitura: bool = False) -> PlanoFila:
    """Calcula a fila inteira (lê planilhas e a API, grava nada, fora criar abas que faltam).

    `somente_leitura` também não cria abas que faltam (usado para mostrar a fila de um dia sem tocar na planilha).
    """
    agora_ts = pd.Timestamp(agora) if agora is not None else pd.Timestamp.now(tz='UTC')
    agora_ts = agora_ts.tz_localize('UTC') if agora_ts.tzinfo is None else agora_ts
    if not somente_leitura:
        garantir_abas(planilha)
    if fila_unica:
        from painel_monstro.saidas import fila_unica as fu, regua_planilha as rp
        if not somente_leitura:
            rp.preparar_abas(planilha)
    params = ler_parametros(planilha)
    bloqueio = ler_bloqueio(planilha)
    aba = planilha._ss.worksheet(ABA_FILA)
    existentes = ler_fila(aba)
    hoje = agora_ts.tz_convert(FUSO_LOJA).date()
    dia_de_fila = hoje.weekday() in params.dias_da_fila

    # Quem a Mariana marcou como "Não quer" entra no Bloqueio (só acrescenta).
    bloqueios_novos = []
    for e in existentes.values():
        if e.status == 'Contato inválido':
            tel = c.so_digitos(e.valores.get('Telefone'))
            if tel:
                bloqueio.add(tel)  # só WhatsApp; não grava recusa nem bloqueia o email
        if e.status == 'Não quer':
            tel, email = c.so_digitos(e.valores.get('Telefone')), str(e.valores.get('Email') or '').strip().lower()
            if tel and tel not in bloqueio:
                bloqueio.add(tel)
                bloqueios_novos.append([tel, email, hoje.strftime('%Y-%m-%d'), 'Não quer (Fila)'])

    carrinhos = c.buscar_carrinhos(api)
    fila, motivos = c.montar_fila(carrinhos, tabelas, params, agora_ts.to_pydatetime(), api, bloqueio, estado_da_fila(existentes))
    resumo_unica: dict[str, Any] = {}
    sorteios: list[dict[str, Any]] = []
    respostas_novas: list[list[Any]] = []
    if fila_unica:
        ja = {k: {'toques': e.toques, 'status': e.status} for k, e in existentes.items()}
        manuais = ler_contatos_manuais(planilha)
        ger = fu.gerar(tabelas, params, rp.ler_regua(planilha), rp.ler_teste45(planilha), hoje, agora_ts, api, ja,
                       rp.ler_sorteios(planilha), bloqueio, ler_desejos(planilha),
                       contatos_vip={m['email'] for m in manuais if m['origem'] == 'VIP'})
        sorteios = [rp.linha_do_sorteio(s['email'], s['grupo'], s['dia'], s['dias'], s['n'], s['total'], s['vip']) for s in ger.sorteios_novos]
        todas = fila + ger.linhas
        ultimo: dict[str, pd.Timestamp] = {}
        enviados_hoje = 0
        clientes_por_email = tabelas.clientes.drop_duplicates('email', keep='last').set_index('email')['telefone'].to_dict()

        def registrar(chaves: list[str], quando: pd.Timestamp) -> None:
            for k in chaves:
                if k and (k not in ultimo or quando > ultimo[k]):
                    ultimo[k] = quando
        for e in existentes.values():
            u = e.ultimo_envio
            if e.toques > 0 and u is not None:
                registrar([str(e.valores.get('Email') or '').strip().lower(), c.so_digitos(e.valores.get('Telefone'))], u)
                if u.tz_convert(FUSO_LOJA).date() == hoje:
                    enviados_hoje += 1
        # D-053: quem tem Status Respondeu e 0 toques conversou com a loja (o cliente escreveu primeiro). Nenhum envio é
        # inventado nos contadores; a conversa só vale para a trava de 30 dias, a partir do dia em que o Painel a viu.
        vistas = ler_respostas_vistas(planilha)
        for e in existentes.values():
            if e.status != 'Respondeu' or e.toques > 0:
                continue
            email_r = str(e.valores.get('Email') or '').strip().lower()
            fone_r = c.so_digitos(e.valores.get('Telefone'))
            chaves_r = [k for k in (email_r, fone_r) if k]
            quando_r = next((vistas[k] for k in chaves_r if k in vistas), None)
            if quando_r is None:
                quando_r = agora_ts
                respostas_novas.append([email_r, fone_r, agora_ts.tz_convert(FUSO_LOJA).strftime('%Y-%m-%d %H:%M')])
                for k in chaves_r:
                    vistas[k] = quando_r
            registrar(chaves_r, quando_r)
        for m in manuais:  # contatos feitos à mão (lista de VIP de outubro etc.) valem para a regra de 30 dias
            registrar([m['email'], c.telefone_whatsapp(clientes_por_email.get(m['email']))], m['quando'])
        resumo_unica = {**ger.resumo, **fu.aplicar_regras(todas, ultimo, enviados_hoje, rp.ler_fila_unica(planilha),
                                                             agora_ts.tz_convert(FUSO_LOJA))}
        fila = todas
    por_id = {l.carrinho: l for l in fila}
    pedidos, tel_para_email = _pedidos_do_cliente(tabelas)
    email_do_carrinho = {str(x['id']): (x.get('contact_email') or '').strip().lower() for x in carrinhos}

    gravar: dict[int, dict[str, Any]] = {}  # posição na planilha -> colunas do Painel
    novas: list[dict[str, Any]] = []
    finais: list[LinhaExistente] = []
    for chave in list(existentes) + [k for k in por_id if k not in existentes]:
        ex, l = existentes.get(chave), por_id.get(chave)
        base_t = None
        if ex is not None:
            if ex.toques > 0:
                base_t = para_momento(ex.valores.get('Primeiro toque em')) or ex.ultimo_envio or agora_ts.tz_convert(FUSO_LOJA)
            elif str(ex.valores.get('Grupo')) == 'Comparação' or (l is not None and l.situacao == 'Grupo de comparação'):
                base_t = para_momento(ex.valores.get('Abandonado em'))
        elif l is not None and l.situacao == 'Grupo de comparação':
            base_t = l.abandonado_em
        email = str((l.email if l else (ex.valores.get('Email') if ex else '')) or email_do_carrinho.get(chave, '')).strip().lower()
        fone = c.so_digitos(l.telefone if l else (ex.valores.get('Telefone') if ex else ''))
        ja_recuperado = ex is not None and str(ex.valores.get('Recuperado')) == 'Sim'
        rec = detectar_recuperacao(base_t, email, fone, pedidos, tel_para_email) if not ja_recuperado else None
        saida = _motivo_de_saida(ex, params, pedidos, tel_para_email, bloqueio, agora_ts) if (l is None and ex is not None) else ''
        v = _linha_para_gravar(l, ex, params, rec, saida)
        # A compra identificada tem prioridade; resposta pausa só o ciclo atual.
        if ex is not None and ex.status == 'Respondeu' and rec is None and not ja_recuperado:
            v['Situação'] = 'Em conversa'
            v['Abrir WhatsApp'] = ''
            v['Próximo envio a partir de'] = ''
            v['Observações'] = 'Cliente respondeu. Próximos toques deste ciclo suspensos; atendimento manual.'
        if ex is not None and ex.status == 'Contato inválido':
            v['Situação'] = 'Encerrado: contato inválido'
            v['Abrir WhatsApp'] = ''
            v['Observações'] = 'Número informado como inexistente no WhatsApp. Corrigir o telefone e revisar o status antes de retomar.'
        if rec is not None:
            v['Recuperado em'] = hoje.strftime('%Y-%m-%d')
        if ex is not None:
            vistos = int(numero(ex.valores.get('Toques vistos')))
            marcou_agora = ex.toques > vistos
            if marcou_agora:  # a Mariana enviou mais um toque desde a última vez: guarda qual modelo era
                enviados = [m for m in str(ex.valores.get('Modelos enviados') or '').split(' > ') if m]
                enviados += [str(ex.valores.get('Modelo usado') or '?')] * (ex.toques - vistos)
                v['Modelos enviados'] = ' > '.join(enviados)
                v['Toques vistos'] = ex.toques
                v['Na fila desde'] = ''  # o toque foi marcado: recomeça a contagem do próximo
                if vistos == 0 and not str(ex.valores.get('Primeiro toque em') or '').strip():
                    v['Primeiro toque em'] = em_texto(ex.ultimo_envio or agora_ts)
            if ex.status in ('Recuperado',) and 'Situação' in v:
                v['Situação'] = 'Recuperado'
            # Nunca some em silêncio e nunca avança o toque sem a marcação: a linha pendente volta com aviso.
            final_sit = v.get('Situação', str(ex.valores.get('Situação') or ''))
            desde = str(ex.valores.get('Na fila desde') or '').strip()
            if final_sit == 'Contatar' and not marcou_agora:
                if not desde and dia_de_fila:
                    v['Na fila desde'] = hoje.strftime('%Y-%m-%d')
                elif desde and desde < hoje.strftime('%Y-%m-%d') and dia_de_fila:
                    aviso = AVISO_NAO_MARCADA
                    v['Observações'] = texto_seguro((v.get('Observações') + '; ' if v.get('Observações') else '') + aviso)
            if final_sit in ('Encerrado sem contato', 'Encerrado: já comprou', 'Encerrado: bloqueado', 'Encerrado', 'Encerrado: contato inválido') \
                    and not str(ex.valores.get('Encerrado em') or '').strip():
                v['Encerrado em'] = hoje.strftime('%Y-%m-%d')
            if l is not None and str(ex.valores.get('Encerrado em') or '').strip():
                v['Encerrado em'] = ''  # voltou a ser candidata
            gravar[ex.posicao] = v
            finais.append(LinhaExistente(ex.posicao, {**ex.valores, **{k: x for k, x in v.items() if DONO.get(k) in ('P', 'F')}}))
        else:
            if str(v.get('Situação')) == 'Contatar' and dia_de_fila:
                v['Na fila desde'] = hoje.strftime('%Y-%m-%d')
            novas.append(v)
            finais.append(LinhaExistente(0, {**{n: '' for n in NOMES}, **v, 'Toques vistos': 0}))

    resultados = calcular_resultados(finais)
    semana = resumo_da_semana(finais, hoje)
    contagens = {'carrinhos': len(carrinhos), 'na_fila': len(fila), 'contatar': sum(1 for l in fila if l.situacao == 'Contatar'),
                 'novas_linhas': len(novas), 'bloqueios_novos': len(bloqueios_novos), 'motivos': dict(motivos),
                 'fila_unica': resumo_unica, 'dia_de_fila': dia_de_fila,
                 'sem_contato': sum(1 for f in finais if str(f.valores.get('Situação')) == 'Encerrado sem contato')}
    return PlanoFila(aba, existentes, gravar, novas, bloqueios_novos, sorteios, finais, resultados, semana, contagens, fila,
                     respostas_novas)


def gravar_plano(planilha: PlanilhaGoogle, plano: PlanoFila) -> dict[str, Any]:
    """Escreve o plano. Se uma gravação falhar, a exceção sobe e o que ainda não foi escrito fica como estava:
    a rodada seguinte recalcula tudo do zero (as contas só dependem do que já está na planilha e na Nuvemshop)."""
    from painel_monstro.saidas import regua_planilha as rp
    if plano.sorteios:
        rp.gravar_sorteios(planilha, plano.sorteios)
    if plano.bloqueios_novos:
        planilha._ss.worksheet(ABA_BLOQUEIO).append_rows(plano.bloqueios_novos, value_input_option='RAW')
    if plano.respostas_novas:
        planilha.garantir_cabecalho(ABA_RESPOSTAS_VISTAS, RESPOSTAS_VISTAS_COLUNAS, {
            'email': 'Email da linha da Fila com Status Respondeu e 0 toques.', 'telefone': 'Telefone (só dígitos).',
            'visto_em': 'Quando o Painel viu a resposta pela primeira vez. A trava de 30 dias conta a partir daqui (D-053).'})
        planilha._ss.worksheet(ABA_RESPOSTAS_VISTAS).append_rows(plano.respostas_novas, value_input_option='RAW')
    escritas = _gravar_fila(plano.aba, plano.existentes, plano.gravar, plano.novas)
    aba_r, _ = planilha._aba(ABA_RESULTADOS, len(plano.resultados) + 5, 4)
    planilha._escrever(aba_r, [l + [''] * (4 - len(l)) for l in plano.resultados])
    aba_s, _ = planilha._aba('resumo_semana', len(plano.resumo_semana) + 3, 2)
    planilha._escrever(aba_s, [l + [''] * (2 - len(l)) for l in plano.resumo_semana])
    return {**plano.contagens, 'celulas': escritas}


def atualizar_fila(planilha: PlanilhaGoogle, api: Any, tabelas: Tabelas, agora: datetime | pd.Timestamp | None = None,
                   fila_unica: bool = False) -> dict:
    """Calcula e grava num passo só (a rotina usa `planejar_fila` e `gravar_plano` separados)."""
    return gravar_plano(planilha, planejar_fila(planilha, api, tabelas, agora, fila_unica))


def ler_desejos(planilha: PlanilhaGoogle) -> pd.DataFrame:
    """Pedidos de disco: aba `desejos` (à mão) e abas do Google Forms ("Respostas ao formulário..."), juntas.

    Vazia ou ausente: nenhum aviso. Ver `garimpo.py` para os cabeçalhos reconhecidos.
    """
    from painel_monstro.saidas import garimpo
    try:
        titulos = [w.title for w in planilha._ss.worksheets()]
    except AttributeError:  # planilha de mentira dos testes
        titulos = ['desejos']
    abas: dict[str, list[list[Any]]] = {}
    for t in titulos:
        if t == 'desejos' or garimpo.eh_aba_do_formulario(t):
            try:
                abas[t] = _valores(planilha._ss.worksheet(t))
            except gspread.exceptions.WorksheetNotFound:
                continue
    return garimpo.juntar_desejos(abas)


ABA_CONTATOS_MANUAIS = 'contatos_manuais'
ABA_RESPOSTAS_VISTAS = 'respostas_vistas'
RESPOSTAS_VISTAS_COLUNAS = ['email', 'telefone', 'visto_em']


def ler_respostas_vistas(planilha: PlanilhaGoogle) -> dict[str, pd.Timestamp]:
    """email e telefone (só dígitos) -> quando o Painel viu a resposta (aba `respostas_vistas`). Ausente: vazio."""
    try:
        valores = _valores(planilha._ss.worksheet(ABA_RESPOSTAS_VISTAS))
    except gspread.exceptions.WorksheetNotFound:
        return {}
    saida: dict[str, pd.Timestamp] = {}
    for l in valores[1:]:
        quando = para_momento(l[2]) if len(l) > 2 else None
        if quando is None:
            continue
        for k in (str(l[0]).strip().lower() if l else '', c.so_digitos(l[1]) if len(l) > 1 else ''):
            if k and (k not in saida or quando < saida[k]):
                saida[k] = quando.tz_convert('UTC')
    return saida
CONTATOS_MANUAIS_COLUNAS = ['email', 'data', 'origem', 'observacao']


def ler_contatos_manuais(planilha: PlanilhaGoogle) -> list[dict[str, Any]]:
    """WhatsApps enviados à mão fora da fila (por exemplo, a lista de VIP de outubro): contam para os 30 dias."""
    try:
        valores = _valores(planilha._ss.worksheet(ABA_CONTATOS_MANUAIS))
    except gspread.exceptions.WorksheetNotFound:
        return []
    saida = []
    for l in valores[1:]:
        email = str(l[0]).strip().lower() if l else ''
        quando = para_momento(l[1]) if len(l) > 1 else None
        if email and quando is not None:
            saida.append({'email': email, 'quando': quando, 'origem': str(l[2]).strip() if len(l) > 2 else ''})
    return saida


def _gravar_fila(aba: Any, existentes: dict[str, LinhaExistente], gravar: dict[int, dict], novas: list[dict]) -> int:
    """Escreve só as colunas do Painel, célula por faixa; linhas novas vão para o fim. Nunca toca nas da Mariana."""
    cab = [str(x).strip() for x in (aba.get_all_values() or [[]])[0]]
    while cab and not cab[-1]:
        cab.pop()
    if cab != NOMES:
        raise ValueError('As colunas da Fila não estão na ordem do modelo; gravação cancelada.')
    pedidos_de_escrita = []
    for pos, v in gravar.items():
        for nome, valor in v.items():
            if DONO.get(nome) == 'P':
                pedidos_de_escrita.append({'range': f'{_letra(COL[nome] + 1)}{pos}', 'values': [[valor]]})
    proxima = max([1] + [e.posicao for e in existentes.values()]) + 1
    if novas and aba.row_count < proxima + len(novas):
        aba.resize(rows=proxima + len(novas) + 50)
        _formatar_fila(aba)
        garantir_visualizacoes(aba)
    for k, v in enumerate(novas):
        pos = proxima + k
        for nome, valor in v.items():
            if DONO.get(nome) == 'P':
                pedidos_de_escrita.append({'range': f'{_letra(COL[nome] + 1)}{pos}', 'values': [[valor]]})
        pedidos_de_escrita.append({'range': f'{_letra(COL["Toques vistos"] + 1)}{pos}', 'values': [[0]]})
    if pedidos_de_escrita:
        for i in range(0, len(pedidos_de_escrita), 500):
            aba.batch_update(pedidos_de_escrita[i:i + 500], value_input_option='RAW')
    # Repara também linhas existentes; a coluna de fórmula pertence ao Painel.
    formulas = []
    ed, tel, saida = _letra(COL['Mensagem editada'] + 1), _letra(COL['Telefone'] + 1), _letra(COL['Abrir com minha edição'] + 1)
    status = _letra(COL['Status'] + 1)
    posicoes = sorted({e.posicao for e in existentes.values()} | set(range(proxima, proxima + len(novas))))
    for pos in posicoes:
        formulas.append({'range': f'{saida}{pos}', 'values': [[
            f'=IF({status}{pos}="Contato inválido";"";IF({ed}{pos}="";"";HYPERLINK("https://wa.me/"&{tel}{pos}&"?text="&ENCODEURL({ed}{pos});"Abrir com minha edição")))']]})
    if formulas:
        for i in range(0, len(formulas), 500):
            aba.batch_update(formulas[i:i + 500], value_input_option='USER_ENTERED')
    return len(pedidos_de_escrita)


def _taxa(a: int, b: int) -> str:
    return f'{(a / b * 100):.1f}%' if b else ''


def calcular_resultados(linhas: list[LinhaExistente]) -> list[list[Any]]:
    """Aba Resultados: contagens por modelo, grupo de comparação e quem saiu da fila sem contato."""
    def rec(e: LinhaExistente) -> bool:
        return str(e.valores.get('Recuperado')) == 'Sim'
    contatados = [e for e in linhas if e.toques > 0]
    comparacao = [e for e in linhas if str(e.valores.get('Grupo')) == 'Comparação']
    sem_contato = [e for e in linhas if str(e.valores.get('Situação')) == 'Encerrado sem contato']
    receita = round(sum(numero(e.valores.get('Receita recuperada (R$)')) for e in contatados if rec(e)), 2)
    saida: list[list[Any]] = [
        ['Resultado da fila', '', '', ''], [], ['Carrinhos na fila', len(linhas)], ['Contatados (pelo menos 1 toque)', len(contatados)],
        ['Responderam', sum(1 for e in linhas if e.status == 'Respondeu')],
        ['Recuperados (de quem foi contatado)', sum(1 for e in contatados if rec(e))],
        ['Taxa de recuperação', _taxa(sum(1 for e in contatados if rec(e)), len(contatados))],
        ['Receita recuperada (R$)', receita], ['Pediram para não receber', sum(1 for e in linhas if e.status == 'Não quer')], [],
        ['Grupo de comparação (só email da Nuvemshop)', len(comparacao)],
        ['Recuperados no grupo de comparação', sum(1 for e in comparacao if rec(e))],
        ['Taxa no grupo de comparação', _taxa(sum(1 for e in comparacao if rec(e)), len(comparacao))],
        ['Resultado só vale com pelo menos 30 pessoas em cada grupo (D-020).'], [],
        ['Não contatados (saíram da fila sem nenhum toque)', len(sem_contato)]]
    por_origem: dict[str, int] = {}
    for e in sem_contato:
        o = str(e.valores.get('Origem') or 'Carrinho')
        por_origem[o] = por_origem.get(o, 0) + 1
    for o, n in sorted(por_origem.items()):
        saida.append([f'  Não contatados · {o}', n])
    saida += [['  Eles continuam no grupo sorteado do teste e seguem a régua normalmente.'], [],
              ['Por primeiro modelo enviado', 'Contatados', 'Recuperados', 'Taxa']]
    por_modelo: dict[str, list] = {}
    for e in contatados:
        m = (str(e.valores.get('Modelos enviados') or '').split(' > ') or ['?'])[0] or '?'
        por_modelo.setdefault(m, []).append(e)
    for m, es in sorted(por_modelo.items()):
        r = sum(1 for e in es if rec(e))
        saida.append([m, len(es), r, _taxa(r, len(es))])
    saida.extend([[], ['Contatos inválidos (não são recusas)', sum(1 for e in linhas if e.status == 'Contato inválido')]])
    return saida


def resumo_da_semana(linhas: list[LinhaExistente], hoje: Any) -> list[list[Any]]:
    """Os 7 dias até hoje: o que foi enviado, o que ficou sem contato e o que voltou (aba `resumo_semana`)."""
    inicio = pd.Timestamp(hoje) - pd.Timedelta(days=6)
    fim = pd.Timestamp(hoje)

    def dia(valor: Any) -> pd.Timestamp | None:
        t = para_momento(valor)
        return None if t is None else pd.Timestamp(t.tz_convert(FUSO_LOJA).date())

    def na_semana(valor: Any) -> bool:
        d = dia(valor)
        return d is not None and inicio <= d <= fim
    enviados = [e for e in linhas if e.toques > 0 and na_semana(e.valores.get('Último envio em'))]
    sem = [e for e in linhas if str(e.valores.get('Situação')) == 'Encerrado sem contato' and na_semana(e.valores.get('Encerrado em'))]
    recuperados = [e for e in linhas if str(e.valores.get('Recuperado')) == 'Sim' and na_semana(e.valores.get('Recuperado em'))]
    saida: list[list[Any]] = [['indicador', 'valor'], ['Período', f'{inicio:%d/%m} a {fim:%d/%m}'],
                              ['Mensagens enviadas (marcadas pela Mariana)', len(enviados)]]
    for origem in ('Carrinho', 'Garimpo', 'VIP', '45 dias'):
        saida.append([f'  Enviadas · {origem}', sum(1 for e in enviados if str(e.valores.get('Origem') or 'Carrinho') == origem)])
    saida.append(['Não contatados (saíram da fila sem toque)', len(sem)])
    for origem in ('Carrinho', 'Garimpo', 'VIP', '45 dias'):
        saida.append([f'  Não contatados · {origem}', sum(1 for e in sem if str(e.valores.get('Origem') or 'Carrinho') == origem)])
    saida += [['Recuperados', len(recuperados)],
              ['Receita recuperada (R$)', round(sum(numero(e.valores.get('Receita recuperada (R$)')) for e in recuperados), 2)]]
    return saida
