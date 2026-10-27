"""Testes da gravação na Planilha Google. Usa uma planilha de mentira em memória e dados fictícios."""
import json
import re

import gspread
import numpy as np
import pandas as pd
import pytest

from painel_monstro.config import Config
from painel_monstro.motor import regua
from painel_monstro.motor.indicadores import CUSTOS_COLUNAS
from painel_monstro.saidas import planilha_google as pg
from tests.ajuda import cliente, dias_atras, pedido, tabelas


# ----------------------------------------------------------------------------
# Planilha de mentira (só o que o módulo usa)
# ----------------------------------------------------------------------------
class AbaFalsa:
    def __init__(self, title, rows, cols):
        self.title, self.row_count, self.col_count = title, rows, cols
        self.grade = {}  # (linha, coluna) -> valor, a partir de 1
        self.notas, self.chamadas_update, self.formatada, self.congelada = {}, [], False, None

    def _letras(self, texto):
        m = re.fullmatch(r'([A-Z]+)(\d+)', texto)
        n = 0
        for c in m.group(1):
            n = n * 26 + ord(c) - 64
        return int(m.group(2)), n

    def get_all_values(self, value_render_option=None):
        if not self.grade:
            return []
        linhas, colunas = max(l for l, _ in self.grade), max(c for _, c in self.grade)
        return [[self.grade.get((l, c), '') for c in range(1, colunas + 1)] for l in range(1, linhas + 1)]

    def update(self, values, range_name=None, raw=True):
        assert raw is True, 'tudo deve ir como valor, nunca como fórmula'
        self.chamadas_update.append(range_name)
        l0, c0 = self._letras(range_name)
        assert l0 + len(values) - 1 <= self.row_count, 'gravou fora das linhas da aba'
        for i, linha in enumerate(values):
            assert c0 + len(linha) - 1 <= self.col_count, 'gravou fora das colunas da aba'
            for j, v in enumerate(linha):
                if v == '':
                    self.grade.pop((l0 + i, c0 + j), None)
                else:
                    self.grade[(l0 + i, c0 + j)] = v

    def batch_clear(self, ranges):
        for r in ranges:
            a, b = r.split(':')
            (l1, c1), (l2, c2) = self._letras(a), self._letras(b)
            for chave in [k for k in self.grade if l1 <= k[0] <= l2 and c1 <= k[1] <= c2]:
                del self.grade[chave]

    def resize(self, rows=None, cols=None):
        self.row_count, self.col_count = rows or self.row_count, cols or self.col_count

    def update_note(self, cell, content):
        self.notas[cell] = content

    def format(self, ranges, formato):
        self.formatada = True

    def freeze(self, rows=None, cols=None):
        self.congelada = rows

    def tabela(self):
        v = self.get_all_values()
        return pd.DataFrame(v[1:], columns=v[0]) if v else pd.DataFrame()


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
def falsa():
    return PlanilhaFalsa()


@pytest.fixture
def pg_(falsa):
    return pg.PlanilhaGoogle(falsa)


def df(n=3, extra=False):
    d = pd.DataFrame({'email': [f'p{i}@exemplo.com' for i in range(n)], 'valor': [10.5 * i for i in range(n)], 'qtd': list(range(n))})
    if extra:
        d['obs'] = 'x'
    return d


# ----------------------------------------------------------------------------
# Conversão em células
# ----------------------------------------------------------------------------
def test_celulas_tipos_e_vazios():
    d = pd.DataFrame({'texto': ['a', None], 'num': [1.5, np.nan], 'inteiro_float': [2.0, 3.0], 'bool': [True, False],
                      'id': pd.array([7, pd.NA], dtype='Int64'), 'data': pd.to_datetime(['2026-10-05', None]),
                      'hora': pd.to_datetime(['2026-10-05 18:46:44', '2026-10-06 09:00:00'])})
    v = pg.tabela_para_celulas(d)
    assert v[0] == ['texto', 'num', 'inteiro_float', 'bool', 'id', 'data', 'hora']
    assert v[1] == ['a', 1.5, 2, True, 7, '2026-10-05', '2026-10-05 18:46:44']
    assert v[2] == ['', '', 3, False, '', '', '2026-10-06 09:00:00']
    json.dumps(v)  # tudo precisa ser aceito como JSON


def test_letras_de_coluna():
    assert [pg._letra(n) for n in (1, 26, 27, 52, 53)] == ['A', 'Z', 'AA', 'AZ', 'BA']


# ----------------------------------------------------------------------------
# Abas do Painel: substituir sem duplicar
# ----------------------------------------------------------------------------
def test_cria_a_aba_e_grava_cabecalho_e_linhas(pg_, falsa):
    g = pg_.substituir('clientes', df(3))
    assert (g.aba, g.linhas, g.colunas, g.acao) == ('clientes', 3, 3, 'criada')
    t = falsa.abas['clientes'].tabela()
    assert list(t.columns) == ['email', 'valor', 'qtd'] and len(t) == 3


def test_rodar_duas_vezes_nao_duplica(pg_, falsa):
    pg_.substituir('pedidos', df(5))
    antes = falsa.abas['pedidos'].get_all_values()
    g = pg_.substituir('pedidos', df(5))
    assert g.acao == 'substituida' and falsa.abas['pedidos'].get_all_values() == antes


def test_tabela_menor_apaga_as_sobras(pg_, falsa):
    pg_.substituir('itens', df(6, extra=True))
    pg_.substituir('itens', df(2))
    v = falsa.abas['itens'].get_all_values()
    assert len(v) == 3 and all(len(l) == 3 for l in v)


def test_tabela_maior_cresce_a_aba(pg_, falsa):
    pg_.substituir('itens', df(2))
    pg_.substituir('itens', df(150, extra=True))
    assert len(falsa.abas['itens'].get_all_values()) == 151 and falsa.abas['itens'].row_count >= 151


def test_grava_em_lotes(pg_, falsa, monkeypatch):
    monkeypatch.setattr(pg, 'LOTE_DE_LINHAS', 4)
    pg_.substituir('produtos', df(10))
    assert falsa.abas['produtos'].chamadas_update == ['A1', 'A5', 'A9']
    assert len(falsa.abas['produtos'].get_all_values()) == 11


def test_tabela_vazia_grava_so_o_cabecalho(pg_, falsa):
    g = pg_.substituir('itens', df(0))
    assert g.linhas == 0 and falsa.abas['itens'].get_all_values() == [['email', 'valor', 'qtd']]


def test_texto_que_parece_formula_vai_como_texto(pg_, falsa):
    pg_.substituir('clientes', pd.DataFrame({'nome': ['=1+1', '+55 62 9999']}))
    assert falsa.abas['clientes'].get_all_values()[1] == ['=1+1']  # e o fake exige raw=True


# ----------------------------------------------------------------------------
# Régua: histórico mensal
# ----------------------------------------------------------------------------
def classificacao_de(mes, n=12, dias=50):
    ped = [pedido(i, f'c{i}@exemplo.com', dias_atras(dias)) for i in range(n)] + [pedido(99, 'ref@exemplo.com', dias_atras(1))]
    return regua.rodar(tabelas(ped), mes)


def test_regua_grava_so_quem_recebe_ou_e_controle(pg_, falsa):
    c, ref = classificacao_de('2026-10')
    g = pg_.gravar_regua('2026-10', c, ref)
    t = falsa.abas['regua'].tabela()
    assert list(t.columns) == pg.REGUA_COLUNAS
    assert g.linhas == len(t) == 12                         # os 12 clientes de 50 dias; o cliente "ref" não tem etapa
    assert set(t['grupo']) == {'envio', 'controle'} and (t['grupo'] == 'controle').sum() == 1
    assert set(t['mes']) == {'2026-10'} and set(t['data_referencia']) == {'2026-10-10'}


def test_rodada_ja_gravada_nao_e_trocada(pg_, falsa):
    c, ref = classificacao_de('2026-10')
    pg_.gravar_regua('2026-10', c, ref)
    antes = falsa.abas['regua'].get_all_values()
    c2, ref2 = classificacao_de('2026-10', n=20)
    g = pg_.gravar_regua('2026-10', c2, ref2)
    assert g.acao == 'ignorada' and falsa.abas['regua'].get_all_values() == antes


def test_forcar_troca_o_mes_inteiro_e_preserva_os_outros(pg_, falsa):
    c, ref = classificacao_de('2026-09', n=15)
    pg_.gravar_regua('2026-09', c, ref)
    c, ref = classificacao_de('2026-10', n=12)
    pg_.gravar_regua('2026-10', c, ref)
    c, ref = classificacao_de('2026-10', n=10)           # menos gente: sobras de outubro precisam sumir
    pg_.gravar_regua('2026-10', c, ref, forcar=True)
    t = falsa.abas['regua'].tabela()
    assert (t['mes'] == '2026-09').sum() == 15 and (t['mes'] == '2026-10').sum() == 10
    assert not t.duplicated(['mes', 'email']).any()


def test_meses_da_regua(pg_):
    assert pg_.meses_da_regua() == set()
    c, ref = classificacao_de('2026-10')
    pg_.gravar_regua('2026-10', c, ref)
    assert pg_.meses_da_regua() == {'2026-10'}


def test_regua_com_colunas_desconhecidas_nao_e_alterada(pg_, falsa):
    aba = falsa.add_worksheet('regua', 10, 3)
    aba.update([['mes', 'coluna_do_tulio'], ['2026-08', 'anotação']], 'A1')
    c, ref = classificacao_de('2026-10')
    with pytest.raises(pg.ErroPlanilha, match='coluna_do_tulio'):
        pg_.gravar_regua('2026-10', c, ref)
    assert aba.get_all_values()[1] == ['2026-08', 'anotação']


# ----------------------------------------------------------------------------
# Abas do Túlio: custos e alertas
# ----------------------------------------------------------------------------
def test_custos_e_alertas_nascem_com_cabecalho_e_notas(pg_, falsa):
    a = pg_.garantir_cabecalho('custos', CUSTOS_COLUNAS, pg.CUSTOS_NOTAS)
    b = pg_.garantir_cabecalho('alertas', pg.ALERTAS_COLUNAS, pg.ALERTAS_NOTAS)
    assert a.acao == b.acao == 'cabecalho_criado'
    assert falsa.abas['custos'].get_all_values() == [CUSTOS_COLUNAS]
    assert falsa.abas['alertas'].get_all_values() == [pg.ALERTAS_COLUNAS]
    assert falsa.abas['custos'].notas['A1'].startswith('Mês') and len(falsa.abas['custos'].notas) == len(CUSTOS_COLUNAS)
    assert falsa.abas['custos'].formatada and falsa.abas['custos'].congelada == 1


def test_custos_do_tulio_nunca_sao_tocados(pg_, falsa):
    pg_.garantir_cabecalho('custos', CUSTOS_COLUNAS, pg.CUSTOS_NOTAS)
    falsa.abas['custos'].update([['2026-10', 1500, 30, 4000]], 'A2')
    antes = falsa.abas['custos'].get_all_values()
    g = pg_.garantir_cabecalho('custos', CUSTOS_COLUNAS, pg.CUSTOS_NOTAS)
    assert g.acao == 'mantida' and g.linhas == 1 and falsa.abas['custos'].get_all_values() == antes


def test_aba_com_cabecalho_diferente_e_avisada_e_nao_alterada(pg_, falsa):
    aba = falsa.add_worksheet('alertas', 10, 3)
    aba.update([['qualquer', 'coisa'], ['x', 'y']], 'A1')
    g = pg_.garantir_cabecalho('alertas', pg.ALERTAS_COLUNAS, pg.ALERTAS_NOTAS)
    assert g.acao == 'cabecalho_diferente' and aba.get_all_values()[0] == ['qualquer', 'coisa']


def test_ler_custos_da_planilha(pg_, falsa):
    assert len(pg_.ler_custos()) == 0                                  # aba não existe
    pg_.garantir_cabecalho('custos', CUSTOS_COLUNAS, pg.CUSTOS_NOTAS)
    assert len(pg_.ler_custos()) == 0                                  # só cabeçalho
    falsa.abas['custos'].update([['2026-10', 1500, 30, 4000, 90, 1200, 55, 25, 2.5, '']], 'A2')
    c = pg_.ler_custos()
    assert list(c['mes']) == ['2026-10'] and c['investimento_meta'].iloc[0] == 1500
    assert c['margem_usados'].iloc[0] == pytest.approx(0.55) and pd.isna(c['frete_pago_loja'].iloc[0])


# ----------------------------------------------------------------------------
# Rodada completa
# ----------------------------------------------------------------------------
def dados():
    ped = [pedido(1, 'a@exemplo.com', dias_atras(100), 120, subtotal=100), pedido(2, 'a@exemplo.com', dias_atras(10), 80),
           pedido(3, 'b@exemplo.com', dias_atras(1), 60)]
    itens = [{'numero': '1', 'email': 'a@exemplo.com', 'data': dias_atras(100), 'valido': True, 'produto': 'Disco', 'valor': 100.0,
              'quantidade': 1, 'sku': None, 'produto_id': 5}]
    prod = [{'url': 'disco', 'nome': 'Disco', 'categorias': 'LP > Usado', 'custo': np.nan, 'id': 5}]
    return tabelas(ped, clientes=[cliente('a@exemplo.com'), cliente('b@exemplo.com')], itens=itens, produtos=prod)


def test_gravar_tudo_cria_as_abas_e_conta_as_linhas(pg_, falsa):
    g = {x.aba: x for x in pg.gravar_tudo(pg_, dados())}
    assert set(falsa.abas) == {'clientes', 'pedidos', 'itens', 'produtos', 'custos', 'alertas', 'indicadores'}
    assert (g['clientes'].linhas, g['pedidos'].linhas, g['itens'].linhas, g['produtos'].linhas) == (2, 3, 1, 1)
    assert g['custos'].acao == g['alertas'].acao == 'cabecalho_criado'
    assert g['indicadores'].linhas > 10
    assert 'produto_id' in falsa.abas['itens'].get_all_values()[0] and 'id' in falsa.abas['produtos'].get_all_values()[0]


def test_gravar_tudo_duas_vezes_da_o_mesmo_resultado(pg_, falsa):
    pg.gravar_tudo(pg_, dados())
    def foto():
        return {t: [l for l in a.get_all_values() if 'atualizado' not in str(l)] for t, a in falsa.abas.items() if t != 'indicadores'}
    primeira = foto()
    pg.gravar_tudo(pg_, dados())
    assert foto() == primeira


def test_gravar_tudo_nao_mexe_no_que_o_tulio_preencheu(pg_, falsa):
    pg.gravar_tudo(pg_, dados())
    falsa.abas['custos'].update([['2026-10', 1500, 30, 4000, 90, 1200, 55, 25, 2.5, 40]], 'A2')
    falsa.abas['alertas'].update([['CPA do Meta', 'maior que', 60, 'sim', 'teto']], 'A2')
    pg.gravar_tudo(pg_, dados())
    assert falsa.abas['custos'].get_all_values()[1][:3] == ['2026-10', 1500, 30]
    assert falsa.abas['alertas'].get_all_values()[1][0] == 'CPA do Meta'
    # e os indicadores já usam os custos preenchidos
    ind = falsa.abas['indicadores'].tabela().set_index('indicador')
    assert ind.loc['CPA do Meta', 'estado'] == 'ok' and float(ind.loc['CPA do Meta', 'valor']) == 50


def test_indicadores_sem_custos_aparecem_como_falta_custos(pg_, falsa):
    pg.gravar_tudo(pg_, dados())
    ind = falsa.abas['indicadores'].tabela().set_index('indicador')
    assert ind.loc['CPA do Meta', 'estado'] == 'falta custos' and ind.loc['CPA do Meta', 'valor'] == ''


# ----------------------------------------------------------------------------
# Conexão e segurança
# ----------------------------------------------------------------------------
def test_conectar_sem_configuracao_avisa_sem_vazar_nada():
    with pytest.raises(pg.ErroPlanilha, match='PLANILHA_ID'):
        pg.PlanilhaGoogle.conectar(Config())


def test_conectar_com_arquivo_inexistente_avisa(tmp_path):
    cfg = Config(planilha_id='ID-SECRETO-123', google_service_account_file=str(tmp_path / 'nao-existe.json'))
    with pytest.raises(pg.ErroPlanilha) as erro:
        pg.PlanilhaGoogle.conectar(cfg)
    assert 'ID-SECRETO-123' not in str(erro.value)


def _cliente_que_recusa(mensagem):
    class Cliente:
        def open_by_key(self, chave):
            try:
                raise gspread.exceptions.APIError(type('R', (), {'json': lambda s: {'error': {'code': 403, 'message': mensagem, 'status': 'PERMISSION_DENIED'}},
                                                                 'status_code': 403, 'text': mensagem})())
            except gspread.exceptions.APIError as e:
                raise PermissionError from e
    return Cliente()


def _config_com_chave(tmp_path):
    arq = tmp_path / 'chave.json'
    arq.write_text(json.dumps({'client_email': 'robo@projeto.iam.gserviceaccount.com'}), encoding='utf-8')
    return Config(planilha_id='ID-SECRETO-123', google_service_account_file=str(arq))


def test_api_do_google_desativada_da_um_aviso_com_o_link(tmp_path, monkeypatch):
    msg = ('Google Sheets API has not been used in project 1 before or it is disabled. Enable it by visiting '
           'https://console.developers.google.com/apis/api/sheets.googleapis.com/overview?project=1 then retry.')
    monkeypatch.setattr(gspread, 'service_account', lambda filename, **kw: _cliente_que_recusa(msg))
    with pytest.raises(pg.ErroPlanilha) as erro:
        pg.PlanilhaGoogle.conectar(_config_com_chave(tmp_path))
    texto = str(erro.value)
    assert 'Google Sheets não está ativada' in texto and 'sheets.googleapis.com/overview?project=1' in texto
    assert 'ID-SECRETO-123' not in texto


def test_planilha_nao_compartilhada_diz_com_quem_compartilhar(tmp_path, monkeypatch):
    monkeypatch.setattr(gspread, 'service_account', lambda filename, **kw: _cliente_que_recusa('The caller does not have permission'))
    with pytest.raises(pg.ErroPlanilha, match='robo@projeto.iam.gserviceaccount.com'):
        pg.PlanilhaGoogle.conectar(_config_com_chave(tmp_path))


def test_email_da_conta_de_servico(tmp_path):
    arq = tmp_path / 'chave.json'
    arq.write_text(json.dumps({'client_email': 'robo@projeto.iam.gserviceaccount.com', 'private_key': 'SEGREDO'}), encoding='utf-8')
    assert pg.email_da_conta(str(arq)) == 'robo@projeto.iam.gserviceaccount.com'
    assert pg.email_da_conta(str(tmp_path / 'nada.json')) == 'o email da conta de serviço'
