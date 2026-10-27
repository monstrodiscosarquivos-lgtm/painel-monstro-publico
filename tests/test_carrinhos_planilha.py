"""Testes das abas de carrinho na Planilha Google (planilha de mentira em memória, dados fictícios)."""
import re

import gspread
import pandas as pd
import pytest

from painel_monstro.saidas import carrinhos as c
from painel_monstro.saidas import carrinhos_planilha as cp
from painel_monstro.saidas.planilha_google import PlanilhaGoogle
from tests.test_carrinhos import AGORA, ApiFalsa, carrinho, produto, tabelas


class AbaFalsa:
    def __init__(self, title, rows, cols):
        self.title, self.row_count, self.col_count, self.grade = title, rows, cols, {}
        self.id = 1
        self.spreadsheet = self
        self.escritas_raw, self.escritas_formula = [], []

    @staticmethod
    def _pos(texto):
        m = re.fullmatch(r'([A-Z]+)(\d+)', texto)
        n = 0
        for ch in m.group(1):
            n = n * 26 + ord(ch) - 64
        return int(m.group(2)), n

    def get_all_values(self, value_render_option=None):
        if not self.grade:
            return []
        lm, cm = max(l for l, _ in self.grade), max(k for _, k in self.grade)
        return [[self.grade.get((l, k), '') for k in range(1, cm + 1)] for l in range(1, lm + 1)]

    def update(self, values, range_name=None, raw=True):
        l0, c0 = self._pos(range_name)
        for i, linha in enumerate(values):
            for j, v in enumerate(linha):
                if v == '':
                    self.grade.pop((l0 + i, c0 + j), None)
                else:
                    self.grade[(l0 + i, c0 + j)] = v

    def batch_update(self, dados, value_input_option='RAW'):
        if isinstance(dados, dict):  # pedido de formatação: ignora
            return
        for d in dados:
            (self.escritas_formula if value_input_option == 'USER_ENTERED' else self.escritas_raw).append(d['range'])
            if value_input_option == 'USER_ENTERED':
                l0, c0 = self._pos(d['range'])
                self.grade[(l0, c0)] = d['values'][0][0]
            else:
                self.update(d['values'], d['range'])

    def append_rows(self, linhas, value_input_option='RAW'):
        proxima = max([l for l, _ in self.grade], default=0) + 1
        for i, linha in enumerate(linhas):
            self.update([linha], f'A{proxima + i}')

    def batch_clear(self, ranges):
        for r in ranges:
            a, b = r.split(':')
            (l1, c1), (l2, c2) = self._pos(a), self._pos(b)
            for k in [k for k in self.grade if l1 <= k[0] <= l2 and c1 <= k[1] <= c2]:
                del self.grade[k]

    def resize(self, rows=None, cols=None):
        self.row_count, self.col_count = rows or self.row_count, cols or self.col_count

    def update_note(self, cell, content):
        pass

    def format(self, ranges, formato):
        pass

    def freeze(self, rows=None, cols=None):
        pass


class PlanilhaFalsa:
    def __init__(self):
        self.abas = {}

    def worksheet(self, titulo):
        if titulo not in self.abas:
            raise gspread.exceptions.WorksheetNotFound(titulo)
        return self.abas[titulo]

    def add_worksheet(self, title, rows, cols):
        self.abas[title] = AbaFalsa(title, rows, cols)
        return self.abas[title]


@pytest.fixture
def pg_():
    return PlanilhaGoogle(PlanilhaFalsa())


def celula(aba, nome, linha):
    return aba.grade.get((linha, cp.COL[nome] + 1), '')


def escrever(aba, linha, **valores):
    for nome, v in valores.items():
        aba.grade[(linha, cp.COL[nome] + 1)] = v


def ciclo(pg_, carrinhos_api=None, tab=None, api=None, momento=AGORA):
    class ApiCheckouts(ApiFalsa):
        def listar(self, caminho, **kw):
            return iter(carrinhos_api or [])
    return cp.atualizar_fila(pg_, api or ApiCheckouts({10: produto()}), tab or tabelas(), momento)


def test_cria_as_abas_com_os_valores_padrao_e_nao_mexe_depois(pg_):
    cp.garantir_abas(pg_)
    assert set(pg_._ss.abas) >= {'Configuração', 'Mensagens', 'Fila', 'Bloqueio'}
    pg_._ss.abas['Configuração'].grade[(2, 2)] = 'Outra, da Monstro'  # o Túlio editou
    cp.garantir_abas(pg_)
    assert pg_._ss.abas['Configuração'].grade[(2, 2)] == 'Outra, da Monstro'
    assert cp.ler_parametros(pg_).assinatura == 'Outra, da Monstro'


def test_le_parametros_com_virgula_e_sim_nao(pg_):
    cp.garantir_abas(pg_)
    aba = pg_._ss.abas['Configuração']
    linhas = {l[0]: i + 1 for i, l in enumerate(aba.get_all_values())}
    aba.grade[(linhas['Carrinho mínimo para cupom de desconto (R$)'], 2)] = '250,50'
    aba.grade[(linhas['Cupom precisa de aprovação do Léo?'], 2)] = 'Sim'
    aba.grade[(linhas['Máximo de toques'], 2)] = 2
    aba.grade[(linhas['Site da loja'], 2)] = ''  # vazio volta ao padrão
    p = cp.ler_parametros(pg_)
    assert p.minimo_cupom == 250.5 and p.cupom_precisa_de_aprovacao is True and p.maximo_de_toques == 2
    assert p.site == 'https://lojamonstro.com.br'


def test_modelo_editado_na_aba_mensagens_vale(pg_):
    cp.garantir_abas(pg_)
    aba = pg_._ss.abas['Mensagens']
    linha = next(i + 1 for i, l in enumerate(aba.get_all_values()) if l[0] == 'T1')
    aba.grade[(linha, 3)] = 'Salve, {nome}! {link_carrinho}'
    assert cp.ler_parametros(pg_).modelos['T1'] == 'Salve, {nome}! {link_carrinho}'


def test_primeira_rodada_grava_a_fila(pg_):
    r = ciclo(pg_, [carrinho()])
    aba = pg_._ss.abas['Fila']
    assert r['na_fila'] == 1 and r['novas_linhas'] == 1
    assert celula(aba, 'Carrinho', 2) == '1' and celula(aba, 'Situação', 2) == 'Contatar'
    assert celula(aba, 'Modelo usado', 2) == 'T1_UNICO'
    assert celula(aba, 'Abrir WhatsApp', 2).startswith('https://wa.me/5562999990000?text=')
    assert celula(aba, 'Abrir com minha edição', 2).startswith('=IF(')
    assert '="";"";' in celula(aba, 'Abrir com minha edição', 2)
    assert celula(aba, 'Toques já enviados', 2) == ''  # coluna da Mariana fica vazia


def test_coluna_movida_interrompe_gravacao_sem_alterar_fila(pg_):
    cp.garantir_abas(pg_)
    aba = pg_._ss.abas['Fila']
    aba.grade[(1, 14)], aba.grade[(1, 37)] = aba.grade[(1, 37)], aba.grade[(1, 14)]
    antes = dict(aba.grade)
    with pytest.raises(ValueError, match='movidas'):
        cp.garantir_abas(pg_)
    with pytest.raises(ValueError, match='gravação cancelada'):
        cp._gravar_fila(aba, {}, {2: {'Situação': 'Contatar'}}, [])
    assert aba.grade == antes


def test_caixas_vazias_no_fim_nao_criam_linhas_de_contato_no_fim_da_grade(pg_):
    cp.garantir_abas(pg_)
    aba = pg_._ss.abas['Fila']
    aba.grade[(200, cp.COL['Enviei agora'] + 1)] = False
    cp._gravar_fila(aba, {}, {}, [{'Carrinho': '1', 'Cliente': 'Teste'}])
    assert celula(aba, 'Carrinho', 2) == '1'


def test_segunda_rodada_nao_duplica_e_nao_toca_nas_colunas_da_mariana(pg_):
    ciclo(pg_, [carrinho()])
    aba = pg_._ss.abas['Fila']
    escrever(aba, 2, **{'Toques já enviados': 1, 'Último envio em': '2026-10-08 10:00', 'Status': 'Respondeu',
                        'Mensagem editada': 'minha versão', 'Enviei agora': True})
    aba.escritas_raw.clear()
    aba.grade[(2, cp.COL['Abrir com minha edição'] + 1)] = '=IF(O2="","","antiga")'
    ciclo(pg_, [carrinho()], momento=AGORA + pd.Timedelta(hours=30))
    assert '="";"";' in celula(aba, 'Abrir com minha edição', 2)
    assert celula(aba, 'Enviei agora', 2) is True
    assert len([l for l in aba.get_all_values()[1:] if l[0]]) == 1
    mariana = {cp.COL[n] + 1 for n, d in cp.DONO.items() if d == 'M'}
    gravadas = {cp._pos_coluna(r) if hasattr(cp, '_pos_coluna') else aba._pos(r)[1] for r in aba.escritas_raw}
    assert not (gravadas & mariana), 'o Painel escreveu numa coluna da Mariana'
    assert celula(aba, 'Toques já enviados', 2) == 1 and celula(aba, 'Mensagem editada', 2) == 'minha versão'
    assert celula(aba, 'Toques vistos', 2) == 1 and celula(aba, 'Modelos enviados', 2) == 'T1_UNICO'
    assert celula(aba, 'Primeiro toque em', 2) == '2026-10-08 10:00'


def test_segundo_toque_muda_o_modelo_e_espera_o_intervalo(pg_):
    ciclo(pg_, [carrinho(total='300.00')])
    aba = pg_._ss.abas['Fila']
    escrever(aba, 2, **{'Toques já enviados': 1, 'Último envio em': '2026-10-08 12:00'})  # 15h UTC = 12h em Brasília
    ciclo(pg_, [carrinho(total='300.00')], momento=AGORA + pd.Timedelta(hours=1))
    assert celula(aba, 'Próximo toque', 2) == 2 and celula(aba, 'Situação', 2) == 'Aguardar intervalo'
    ciclo(pg_, [carrinho(total='300.00')], momento=AGORA + pd.Timedelta(hours=26))
    assert celula(aba, 'Modelo usado', 2) == 'T3_CUPOM' and celula(aba, 'Situação', 2) == 'Contatar'


def test_modelo_escolhido_pela_mariana_vale(pg_):
    ciclo(pg_, [carrinho()])
    escrever(pg_._ss.abas['Fila'], 2, **{'Modelo escolhido': 'T1'})
    ciclo(pg_, [carrinho()])
    assert celula(pg_._ss.abas['Fila'], 'Modelo usado', 2) == 'T1'
    escrever(pg_._ss.abas['Fila'], 2, **{'Modelo escolhido': 'T3_CUPOM'})
    ciclo(pg_, [carrinho()], api=None)


def test_recuperado_quando_compra_em_ate_7_dias(pg_):
    ciclo(pg_, [carrinho()])
    escrever(pg_._ss.abas['Fila'], 2, **{'Toques já enviados': 1, 'Último envio em': '2026-10-08 12:00'})
    tab = tabelas([('a@exemplo.com', '', True, 100)], [('a@exemplo.com', pd.Timestamp('2026-10-09 10:00'), True)])
    tab.pedidos['subtotal'], tab.pedidos['desconto'], tab.pedidos['cupom'] = 150.0, 10.0, 'VOLTA10OUT'
    ciclo(pg_, [carrinho()], tab, momento=AGORA + pd.Timedelta(hours=40))
    aba = pg_._ss.abas['Fila']
    assert celula(aba, 'Recuperado', 2) == 'Sim' and celula(aba, 'Receita recuperada (R$)', 2) == 140.0
    assert celula(aba, 'Cupom do pedido', 2) == 'VOLTA10OUT' and celula(aba, 'Situação', 2) == 'Recuperado'
    resultados = pg_._ss.abas['Resultados'].get_all_values()
    assert ['Recuperados (de quem foi contatado)', 1, '', ''] in resultados


def test_contato_invalido_nao_conta_toque_nem_recusa_e_nao_volta(pg_):
    ciclo(pg_, [carrinho()])
    aba = pg_._ss.abas['Fila']
    escrever(aba, 2, **{'Status': 'Contato inválido', 'Mensagem editada': 'texto personalizado'})
    ciclo(pg_, [carrinho()], momento=AGORA + pd.Timedelta(hours=30))
    assert celula(aba, 'Situação', 2) == 'Encerrado: contato inválido'
    assert celula(aba, 'Abrir WhatsApp', 2) == ''
    assert celula(aba, 'Toques já enviados', 2) == ''
    assert celula(aba, 'Último envio em', 2) == ''
    assert celula(aba, 'Status', 2) == 'Contato inválido'
    assert 'Contato inválido' in celula(aba, 'Abrir com minha edição', 2)
    assert len(pg_._ss.abas['Bloqueio'].get_all_values()) == 1
    resultados = pg_._ss.abas['Resultados'].get_all_values()
    assert ['Pediram para não receber', 0, '', ''] in resultados
    assert ['Contatados (pelo menos 1 toque)', 0, '', ''] in resultados
    assert ['Contatos inválidos (não são recusas)', 1, '', ''] in resultados


def test_compra_depois_de_7_dias_nao_conta():
    inicio = pd.Timestamp('2026-10-01 10:00', tz='America/Sao_Paulo')
    pedidos = {'a@exemplo.com': [(pd.Timestamp('2026-10-09 10:00', tz='America/Sao_Paulo'), 100.0, '')]}
    assert cp.detectar_recuperacao(inicio, 'a@exemplo.com', '', pedidos, {}) is None
    assert cp.detectar_recuperacao(None, 'a@exemplo.com', '', pedidos, {}) is None
    pedidos = {'a@exemplo.com': [(pd.Timestamp('2026-10-05 10:00', tz='America/Sao_Paulo'), 100.0, 'X')]}
    assert cp.detectar_recuperacao(inicio, 'a@exemplo.com', '', pedidos, {}) == (100.0, 'X')
    assert cp.detectar_recuperacao(inicio, '', '5562999990000', pedidos, {'5562999990000': 'a@exemplo.com'}) == (100.0, 'X')


def test_nao_quer_vai_para_o_bloqueio_e_some_da_fila(pg_):
    ciclo(pg_, [carrinho()])
    escrever(pg_._ss.abas['Fila'], 2, **{'Status': 'Não quer', 'Toques já enviados': 1})
    r = ciclo(pg_, [carrinho()])
    assert r['bloqueios_novos'] == 1
    assert '5562999990000' in [l[0] for l in pg_._ss.abas['Bloqueio'].get_all_values()]
    assert celula(pg_._ss.abas['Fila'], 'Situação', 2) == 'Encerrado'
    r = ciclo(pg_, [carrinho()])
    assert r['bloqueios_novos'] == 0


def test_carrinho_que_saiu_da_api_sem_contato_vira_encerrado_sem_contato(pg_):
    ciclo(pg_, [carrinho()])
    ciclo(pg_, [])
    aba = pg_._ss.abas['Fila']
    assert celula(aba, 'Situação', 2) == 'Encerrado sem contato' and celula(aba, 'Encerrado em', 2) == '2026-10-08'


def test_texto_de_cliente_nunca_vira_formula():
    assert cp.texto_seguro('=HYPERLINK("x")') == "'=HYPERLINK(\"x\")"
    assert cp.texto_seguro('+55') == "'+55"
    assert cp.texto_seguro('Ana') == 'Ana'


def test_datas_da_planilha():
    assert cp.para_momento('') is None and cp.para_momento('lixo') is None
    assert cp.em_texto(cp.para_momento('2026-10-08 10:30')) == '2026-10-08 10:30'
    assert cp.em_texto(cp.para_momento(46303.5)) == '2026-10-08 12:00'  # 46303 = 08/10/2026 no calendário do Sheets
    assert cp.em_texto(cp.para_momento('08/10/2026 09:00')) == '2026-10-08 09:00'


def test_resposta_suspende_toques_sem_apagar_envio_e_compra_tem_prioridade(pg_):
    ciclo(pg_, [carrinho()])
    aba = pg_._ss.abas['Fila']
    escrever(aba, 2, **{'Toques já enviados': 1, 'Último envio em': '2026-10-08 12:00',
                        'Status': 'Respondeu', 'Respondeu agora': True})
    ciclo(pg_, [carrinho()], momento=AGORA + pd.Timedelta(hours=40))
    assert celula(aba, 'Situação', 2) == 'Em conversa'
    assert celula(aba, 'Abrir WhatsApp', 2) == ''
    assert celula(aba, 'Toques já enviados', 2) == 1
    assert celula(aba, 'Respondeu agora', 2) is True
    tab = tabelas([('a@exemplo.com', '', True, 100)],
                  [('a@exemplo.com', pd.Timestamp('2026-10-09 10:00'), True)])
    tab.pedidos['subtotal'], tab.pedidos['desconto'] = 150.0, 10.0
    ciclo(pg_, [carrinho()], tab, momento=AGORA + pd.Timedelta(hours=40))
    assert celula(aba, 'Situação', 2) == 'Recuperado'
    assert celula(aba, 'Receita recuperada (R$)', 2) == 140.0
    assert celula(aba, 'Status', 2) == 'Respondeu'


def test_visualizacoes_pessoais_atualizam_intervalo_sem_filtro_compartilhado():
    class SS:
        def __init__(self):
            self.requests = []
        def fetch_sheet_metadata(self):
            return {'sheets': [{'properties': {'sheetId': 7}, 'filterViews': [{'filterViewId': 101001}]}]}
        def batch_update(self, payload):
            self.requests = payload['requests']
    class Aba:
        id, row_count = 7, 400
        spreadsheet = SS()
    aba = Aba()
    cp.garantir_visualizacoes(aba)
    requests = aba.spreadsheet.requests
    assert 'updateFilterView' in requests[0]
    assert 'addFilterView' in requests[1]
    assert all('setBasicFilter' not in r for r in requests)
    assert requests[0]['updateFilterView']['filter']['range']['endRowIndex'] == 400
    assert requests[0]['updateFilterView']['filter']['criteria']['17']['condition']['values'][0]['userEnteredValue'] == 'Contatar'
    formula = requests[1]['addFilterView']['filter']['criteria']['10']['condition']['values'][0]['userEnteredValue']
    assert '$K2>0' in formula and '$AC2<>"Sim"' in formula


def test_desconto_antecipado_encerra_com_dois_envios_reais(pg_):
    ciclo(pg_,[carrinho(total='300')])
    aba=pg_._ss.abas['Fila']
    escrever(aba,2,**{'Toques já enviados':1,'Último envio em':'2026-10-08 12:00'})
    ciclo(pg_,[carrinho(total='300')],momento=AGORA+pd.Timedelta(hours=26))
    assert celula(aba,'Modelo usado',2)=='T3_CUPOM'
    assert celula(aba,'Próximo toque',2)==2
    escrever(aba,2,**{'Toques já enviados':2,'Último envio em':'2026-10-09 14:00'})
    ciclo(pg_,[carrinho(total='300')],momento=AGORA+pd.Timedelta(hours=52))
    assert celula(aba,'Situação',2)=='Encerrado'
    assert celula(aba,'Toques já enviados',2)==2
    assert celula(aba,'Modelos enviados',2).endswith('T3_CUPOM')
