"""Testes da newsletter semanal. Dados fictícios."""
import pandas as pd

from painel_monstro.coletor import nuvemshop_api as na
from painel_monstro.saidas import newsletter as nl

QUARTA_17 = pd.Timestamp('2026-10-14 17:07')  # 14/10/2026 é quarta


def _produtos():
    return pd.DataFrame([
        {'url': 'lp-a', 'nome': 'LP Artista Um - Album Um (1977) (Vinil usado)', 'categorias': 'LP > Usado > Jazz', 'preco': 80.0,
         'estoque': 1.0, 'exibir': True, 'criado_em': '2026-10-12T10:00:00+0000', 'imagem': 'http://x/a-640-0.jpg', 'descricao': 'Bom'},
        {'url': 'lp-b', 'nome': 'LP Artista Dois: Album Dois - (Novo/Lacrado)', 'categorias': 'LP > Novo/Lacrado', 'preco': 200.0,
         'estoque': 2.0, 'exibir': True, 'criado_em': '2026-01-01T10:00:00+0000', 'imagem': None, 'descricao': None},
        {'url': 'lp-c', 'nome': 'LP Velho - Antigo (Vinil usado)', 'categorias': 'LP > Usado', 'preco': 50.0,
         'estoque': 1.0, 'exibir': True, 'criado_em': '2026-01-01T10:00:00+0000', 'imagem': None, 'descricao': None},
        {'url': 'lp-d', 'nome': 'LP Sem Estoque - X (Vinil usado)', 'categorias': 'LP > Usado', 'preco': 50.0,
         'estoque': 0.0, 'exibir': True, 'criado_em': '2026-10-13T10:00:00+0000', 'imagem': None, 'descricao': None},
        {'url': 'lp-e', 'nome': 'LP Oculto - Y (Vinil usado)', 'categorias': 'LP > Usado', 'preco': 50.0,
         'estoque': 1.0, 'exibir': False, 'criado_em': '2026-10-13T10:00:00+0000', 'imagem': None, 'descricao': None},
        {'url': 'camiseta-z', 'nome': 'Camiseta Monstro', 'categorias': 'Camisetas', 'preco': 70.0,
         'estoque': 5.0, 'exibir': True, 'criado_em': '2026-10-13T10:00:00+0000', 'imagem': None, 'descricao': None},
    ])


def test_texto_da_descricao_sem_html_e_limite():
    t = na.texto_da_descricao({'pt': '<p style="x">Disco &amp; capa<br>ótimo</p>' + '<p>' + 'a' * 700 + '</p>'})
    assert '<' not in t and t.startswith('Disco & capa ótimo') and len(t) == 600


def test_imagem_640():
    assert na.imagem_640('https://c/p/x-1024-1024.jpeg') == 'https://c/p/x-640-0.jpeg'
    assert na.imagem_640(None) == ''


def test_separar_nome_e_tipo():
    assert nl.separar_nome('LP Artista Um - Album Um (1977) (Vinil usado)') == ('Artista Um', 'Album Um', '1977')
    assert nl.separar_nome('LP Artista Dois: Album Dois - (Novo/Lacrado)') == ('Artista Dois', 'Album Dois', '')
    assert nl.tipo_do_disco('x (Novo/Lacrado)', '') == 'lacrado'
    assert nl.tipo_do_disco('x (Vinil usado)', 'LP > Usado') == 'usado'


def test_primeira_vez_vale_o_dia_da_criacao_e_volta_ao_estoque_vale_hoje():
    p = nl.marcar_estoque(_produtos(), [], '2026-10-14').set_index('url')
    assert p.loc['lp-a', 'no_estoque_desde'] == '2026-10-12'
    assert p.loc['lp-d', 'no_estoque_desde'] == ''
    anterior = [['url', 'estoque', 'no_estoque_desde'], ['lp-a', '1', '2026-10-12'], ['lp-c', '0', ''], ['lp-b', '2', '2026-01-01']]
    p2 = nl.marcar_estoque(_produtos(), anterior, '2026-10-14').set_index('url')
    assert p2.loc['lp-a', 'no_estoque_desde'] == '2026-10-12'   # continua
    assert p2.loc['lp-c', 'no_estoque_desde'] == '2026-10-14'   # voltou
    assert p2.loc['lp-b', 'no_estoque_desde'] == '2026-01-01'


def test_semana_filtra_estoque_exibir_historico_e_disco():
    p = nl.marcar_estoque(_produtos(), [], '2026-10-14')
    p.loc[p['url'] == 'lp-b', 'no_estoque_desde'] = '2026-10-10'
    s = nl.montar_semana(p, None, QUARTA_17)
    assert list(s.columns) == nl.COLUNAS
    assert list(s['url']) == ['https://lojamonstro.com.br/produtos/lp-a/', 'https://lojamonstro.com.br/produtos/lp-b/']
    a = s.iloc[0]
    assert (a['artista'], a['album'], a['ano'], a['tipo'], a['familia']) == ('Artista Um', 'Album Um', '1977', 'usado', 'Groove')
    assert a['imagem'] == 'http://x/a-640-0.jpg' and a['descricao'] == 'Bom'
    historico = [['url', 'data_envio'], ['https://lojamonstro.com.br/produtos/lp-a/', '2026-10-07']]
    s2 = nl.montar_semana(p, historico, QUARTA_17)
    assert list(s2['url']) == ['https://lojamonstro.com.br/produtos/lp-b/']


def test_so_gera_quarta_depois_das_17h_uma_vez():
    assert nl.deve_gerar(QUARTA_17, '')
    assert not nl.deve_gerar(pd.Timestamp('2026-10-14 16:07'), '')
    assert not nl.deve_gerar(pd.Timestamp('2026-10-15 17:07'), '')
    assert not nl.deve_gerar(QUARTA_17, '2026-10-14 17:07')


def test_passo_rotina_grava_semana_e_aviso():
    p = nl.marcar_estoque(_produtos(), [], '2026-10-14')
    paginas = dict(nl.passo_rotina(lambda nome: [], p, QUARTA_17))
    assert set(paginas) == {'newsletter_semana', 'newsletter_aviso'}
    assert paginas['newsletter_aviso'].iloc[0]['assunto'] == f'Newsletter da semana: {len(paginas["newsletter_semana"])} discos prontos'
    assert nl.passo_rotina(lambda nome: [], p, pd.Timestamp('2026-10-15 17:07')) == []


def test_aviso_grava_gerado_em_como_texto_e_sem_conversao():
    from painel_monstro.saidas.planilha_google import tabela_para_celulas
    celulas = tabela_para_celulas(nl.aviso(3, QUARTA_17))
    assert celulas[0][0] == 'gerado_em'
    assert celulas[1][0] == '2026-10-14 17:07' and isinstance(celulas[1][0], str)
