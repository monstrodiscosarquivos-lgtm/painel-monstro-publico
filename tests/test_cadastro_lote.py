from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from painel_monstro.saidas.cadastro import COLUNAS as COLUNAS_CADASTRO, FOTOS as COLUNAS_FOTOS, ler, preparar_abas
from painel_monstro.saidas.planilha_google import PlanilhaGoogle
from scripts import cadastro_lote as cl
from tests.test_planilha_google import PlanilhaFalsa


def _nova_planilha(
    rascunhos: list[list[str]] | None = None,
    fotos: list[list[str]] | None = None,
    produtos: list[list[str]] | None = None,
) -> PlanilhaGoogle:
    pg = PlanilhaGoogle(PlanilhaFalsa())
    preparar_abas(pg)
    if rascunhos:
        aba_r, _ = pg._aba('cadastro_rascunhos', len(rascunhos) + 5, len(COLUNAS_CADASTRO))
        aba_r.update(rascunhos, 'A1', raw=True)
    if fotos:
        aba_f, _ = pg._aba('cadastro_fotos', len(fotos) + 5, len(COLUNAS_FOTOS))
        aba_f.update(fotos, 'A1', raw=True)
    if produtos:
        aba_p, _ = pg._aba('produtos', len(produtos) + 5, max(len(r) for r in produtos))
        aba_p.update(produtos, 'A1', raw=True)
    # Limpa o histórico de chamadas de setup para medir só o que o comando faz
    for aba in pg._ss.abas.values():
        aba.chamadas_update.clear()
    return pg


def _criar_foto_sintetica_capa(caminho: Path, tamanho=(800, 800)) -> None:
    """Cria uma imagem de capa retangular com borda escura sobre fundo branco."""
    img = Image.new('RGB', tamanho, (250, 250, 250))
    draw = ImageDraw.Draw(img)
    w, h = tamanho
    lado = int(min(w, h) * 0.7)
    x0 = (w - lado) // 2
    y0 = (h - lado) // 2
    x1, y1 = x0 + lado, y0 + lado
    draw.rectangle([x0, y0, x1, y1], fill=(225, 220, 210), outline=(35, 35, 35), width=6)
    draw.rectangle([x0 + 40, y0 + 40, x1 - 40, y1 - 40], fill=(80, 110, 150), outline=(25, 25, 25), width=3)
    img.save(caminho, 'JPEG', quality=92)


def _criar_foto_sintetica_disco(caminho: Path, tamanho=(800, 800)) -> None:
    """Cria uma imagem de vinil circular escuro sobre fundo claro (raio dentro de 10%-22% da largura)."""
    img = Image.new('RGB', tamanho, (240, 240, 240))
    draw = ImageDraw.Draw(img)
    w, h = tamanho
    cx, cy = w // 2, h // 2
    if h > w:
        r = int(w * 0.40)
    else:
        r = 140
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(20, 20, 22), outline=(10, 10, 10), width=4)
    draw.ellipse([cx - 45, cy - 45, cx + 45, cy + 45], fill=(200, 60, 50))
    img.save(caminho, 'JPEG', quality=92)


def _lote_base_valido(pasta_fotos: Path) -> dict:
    for nome in ('f1.jpg', 'f2.jpg', 'f3.jpg', 'f4.jpg'):
        if nome == 'f3.jpg':
            _criar_foto_sintetica_disco(pasta_fotos / nome)
        else:
            _criar_foto_sintetica_capa(pasta_fotos / nome)
    return {
        'lote': '2026-10-27',
        'discos': [
            {
                'disco': 'D01',
                'acao': 'cadastrar',
                'artista': 'Sepultura',
                'album': 'Arise',
                'ano': 1991,
                'gravadora': 'Roadrunner',
                'catalogo': 'RR 9328-1',
                'pais': 'Brasil',
                'duplo': False,
                'gatefold': False,
                'acompanha': ['encarte com letras'],
                'genero': 'Hard Rock / Heavy Metal / Metal',
                'capa': 'VG+',
                'vinil': 'VG+',
                'preco_etiqueta': 180,
                'bolinha': 'amarela',
                'confianca': 'alta',
                'marcas': '',
                'pendencias': '',
                'descricao': (
                    'Clássico do thrash metal brasileiro lançado em 1991 pela Roadrunner.\n\n'
                    'Edição nacional de época com encarte original.\n\n'
                    '• Capa VG+\n'
                    '• Vinil VG+\n'
                    '• Com encarte'
                ),
                'tags': 'Sepultura, Arise, Heavy Metal, Thrash Metal, LP, LP Usado, Vinil Usado, 1991, Roadrunner',
                'fotos': [
                    {'arquivo': 'f1.jpg', 'papel': 'capa'},
                    {'arquivo': 'f2.jpg', 'papel': 'contracapa'},
                    {'arquivo': 'f3.jpg', 'papel': 'disco'},
                    {'arquivo': 'f4.jpg', 'papel': 'etiqueta'},
                ],
            }
        ],
    }


def _salvar_lote(pasta: Path, dados: dict, nome: str = 'lote.json') -> Path:
    arq = pasta / nome
    arq.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding='utf-8')
    return arq


# ----------------------------------------------------------------------------
# 1. Regressão de derivação contra referência 2026-10-26
# ----------------------------------------------------------------------------
CAMINHO_EXEMPLO_REF = (
    Path(__file__).resolve().parent.parent
    / 'dados'
    / 'referencia-privada'
    / 'cadastro_ia'
    / 'exemplo_lote_2026-10-26.json'
)
CAMINHO_GRAVADAS_REF = (
    Path(__file__).resolve().parent.parent
    / 'dados'
    / 'referencia-privada'
    / 'cadastro_ia'
    / 'linhas_gravadas_2026-10-26.json'
)


@pytest.mark.skipif(
    not (CAMINHO_EXEMPLO_REF.exists() and CAMINHO_GRAVADAS_REF.exists()),
    reason='Arquivos de referência privada do lote 2026-10-26 não encontrados.',
)
def test_regressao_derivacao_lote_2026_10_26():
    dados_lote = json.loads(CAMINHO_EXEMPLO_REF.read_text(encoding='utf-8'))
    ref_gravadas = json.loads(CAMINHO_GRAVADAS_REF.read_text(encoding='utf-8'))

    planilha = _nova_planilha()
    derivado = cl.derivar_lote(
        dados_lote,
        planilha=planilha,
        pasta_local=None,
        usar_nomes_novos=False,
        detectar_recortes=False,
    )

    linhas_r = derivado['rasc']
    linhas_f = derivado['fotos']
    ref_r = ref_gravadas['rasc']
    ref_f = ref_gravadas['fotos']
    assert len(linhas_r) == len(ref_r) == 35
    assert len(linhas_f) == len(ref_f) == 141

    colunas_comparadas = [
        'id',
        'pasta',
        'titulo',
        'marca',
        'categorias',
        'ficha',
        'descricao',
        'capa',
        'vinil',
        'preco',
        'peso_kg',
        'fotos',
        'seo_titulo',
        'seo_descricao',
        'tags',
        'preco_origem',
        'estoque',
    ]
    indices = {col: COLUNAS_CADASTRO.index(col) for col in colunas_comparadas}

    for idx_linha, (gerada, esperada) in enumerate(zip(linhas_r, ref_r)):
        for col, i_col in indices.items():
            assert gerada[i_col] == esperada[i_col], (
                f'Diferença no rascunho #{idx_linha + 1} ({esperada[0]}) coluna {col}: '
                f'{gerada[i_col]!r} != {esperada[i_col]!r}'
            )

    for idx_foto, (f_gerada, f_esperada) in enumerate(zip(linhas_f, ref_f)):
        assert f_gerada[0] == f_esperada[0], f'id_disco diferente na foto #{idx_foto}'
        assert f_gerada[1] == f_esperada[1], f'ordem diferente na foto #{idx_foto}'
        assert f_gerada[2] == f_esperada[2], f'papel diferente na foto #{idx_foto}'
        assert f_gerada[5] == f_esperada[5], f'observacao (nome antigo) diferente na foto #{idx_foto}'


# ----------------------------------------------------------------------------
# 2. Validações do `conferir` (cada erro da lista + avisos)
# ----------------------------------------------------------------------------
def test_validacao_lote_valido_sem_erros(tmp_path):
    dados = _lote_base_valido(tmp_path)
    arq = _salvar_lote(tmp_path, dados)
    planilha = _nova_planilha()
    rel = cl.validar_lote(arq, tmp_path, planilha=planilha, gerar_previas=True, base_trabalho=tmp_path / 'out')
    assert rel['erros'] == []
    assert rel['ok'] is True
    assert len(rel['previas']) == 1
    assert rel['previas'][0].exists()
    assert 'pronto para gravar' in rel['relatorio'].read_text(encoding='utf-8')


@pytest.mark.parametrize(
    'mutacao, trecho_erro',
    [
        (lambda d: d.update({'lote': ''}), 'Campo lote ausente ou vazio'),
        (lambda d: d.update({'discos': 'invalido'}), 'Lista discos ausente ou inválida'),
        (lambda d: d['discos'][0].update({'disco': ''}), 'Código disco ausente'),
        (
            lambda d: d['discos'].append(copy.deepcopy(d['discos'][0])),
            'Código disco repetido',
        ),
        (
            lambda d: d['discos'][0]['fotos'].append({'arquivo': 'nao_existe.jpg', 'papel': 'encarte frente'}),
            'Arquivo inexistente na pasta: nao_existe.jpg',
        ),
        (
            lambda d: d['discos'].append(
                {
                    **copy.deepcopy(d['discos'][0]),
                    'disco': 'D02',
                }
            ),
            'Foto usada em dois discos',
        ),
        (
            lambda d: d['discos'][0]['fotos'][0].update({'papel': 'poster'}),
            'Papel fora da lista permitida',
        ),
        (
            lambda d: d['discos'][0].update(
                {'fotos': [{'arquivo': 'f3.jpg', 'papel': 'disco'}]}
            ),
            'Disco a cadastrar sem nenhuma foto de capa, contracapa ou etiqueta',
        ),
        (
            lambda d: d['discos'][0].update({'acao': 'arquivar'}),
            'Ação inválida',
        ),
        (
            lambda d: d['discos'][0].update({'acao': 'pular', 'motivo': ''}),
            'Disco com ação pular sem motivo',
        ),
        (
            lambda d: d['discos'][0].update({'genero': 'Gospel'}),
            'Gênero fora da lista do manual',
        ),
        (
            lambda d: d['discos'][0].update({'capa': 'EX+'}),
            'Nota de capa fora de M NM VG+ VG G+ G F',
        ),
        (
            lambda d: d['discos'][0].update({'vinil': 'BOM'}),
            'Nota de vinil fora de M NM VG+ VG G+ G F',
        ),
        (
            lambda d: d['discos'][0].update({'preco_etiqueta': -10}),
            'preco_etiqueta deve ser número positivo ou null',
        ),
        (
            lambda d: d['discos'][0].update({'artista': ''}),
            'Campo obrigatório vazio: artista',
        ),
        (
            lambda d: d['discos'][0].update({'album': '   '}),
            'Campo obrigatório vazio: album',
        ),
        (
            lambda d: d['discos'][0].update({'descricao': ''}),
            'Campo obrigatório vazio: descricao',
        ),
        (
            lambda d: d['discos'][0].update({'tags': ''}),
            'Campo obrigatório vazio: tags',
        ),
        (
            lambda d: d['discos'][0].update({'descricao': d['discos'][0]['descricao'] + ' — texto'}),
            'Travessão (—) encontrado',
        ),
        (
            lambda d: d['discos'][0].update({'descricao': 'Texto sem bullets\n• Vinil VG+'}),
            'Descrição sem o tópico exato "• Capa VG+"',
        ),
        (
            lambda d: d['discos'][0].update({'descricao': 'Texto\n• Capa VG+'}),
            'Descrição sem o tópico exato "• Vinil VG+"',
        ),
        (
            lambda d: d['discos'][0].update({'tags': 'Sepultura, Arise, Heavy Metal, LP Usado, Vinil Usado'}),
            'Tags sem LP, LP Usado, Vinil Usado',
        ),
        (
            lambda d: d['discos'][0].update({'bolinha': 'prata'}),
            'Bolinha prata (disco consignado) não pode ter ação cadastrar',
        ),
        (
            lambda d: d['discos'][0]['fotos'][0].update({'cantos': [[0, 0], [600, 0], [600, 600], [0, 600]]}),
            'Cantos manuais inválidos',
        ),
    ],
)
def test_validacao_cada_erro_conferir(tmp_path, mutacao, trecho_erro):
    dados = _lote_base_valido(tmp_path)
    mutacao(dados)
    arq = _salvar_lote(tmp_path, dados)
    planilha = _nova_planilha()
    rel = cl.validar_lote(arq, tmp_path, planilha=planilha, gerar_previas=False, base_trabalho=tmp_path / 'out')
    assert rel['ok'] is False
    msgs = [msg for _, msg in rel['erros']]
    assert any(trecho_erro in m for m in msgs), f'Esperava {trecho_erro!r} em {msgs}'


def test_validacao_foto_ja_cadastrada_em_cadastro_fotos(tmp_path):
    dados = _lote_base_valido(tmp_path)
    arq = _salvar_lote(tmp_path, dados)
    planilha = _nova_planilha(
        fotos=[
            list(COLUNAS_FOTOS),
            ['2026-10-26-01', '1', 'capa', 'id_drv', '', 'f1.jpg'],
        ]
    )
    rel = cl.validar_lote(arq, tmp_path, planilha=planilha, gerar_previas=False, base_trabalho=tmp_path / 'out')
    assert rel['ok'] is False
    msgs = [msg for _, msg in rel['erros']]
    assert any('Foto já está em cadastro_fotos: f1.jpg' in m for m in msgs)


def test_validacao_json_invalido_no_conferir(tmp_path):
    arq = tmp_path / 'invalido.json'
    arq.write_text('{invalido', encoding='utf-8')
    rel = cl.validar_lote(arq, tmp_path, planilha=_nova_planilha(), gerar_previas=False, base_trabalho=tmp_path / 'out')
    assert rel['ok'] is False
    assert any('JSON inválido' in msg for _, msg in rel['erros'])


def test_avisos_repetido_loja_painel_exagero_confianca_baixa(tmp_path):
    dados = _lote_base_valido(tmp_path)
    dados['discos'][0]['confianca'] = 'baixa'
    dados['discos'][0]['preco_etiqueta'] = None
    dados['discos'][0]['descricao'] = (
        'Uma obra-prima indispensável do metal.\n\n• Capa VG+\n• Vinil VG+\n• Com encarte'
    )
    arq = _salvar_lote(tmp_path, dados)

    rascunhos = [list(COLUNAS_CADASTRO)]
    linha_existente = [''] * len(COLUNAS_CADASTRO)
    linha_existente[0] = '2026-10-20-01'
    linha_existente[1] = '2026-10-20'
    linha_existente[3] = 'rascunho'
    linha_existente[4] = 'LP Sepultura - Arise (1991) - (Vinil Usado)'
    rascunhos.append(linha_existente)

    produtos = [
        [
            'id_produto',
            'nome',
            'artista',
            'categoria_principal',
            'familia_genero',
            'tipo',
            'preco',
            'custo',
            'estoque',
            'data_entrada_estoque',
            'em_estoque',
            'url',
        ],
        [
            '999',
            'LP Sepultura - Arise (1991) - (Vinil Usado)',
            'Sepultura',
            'Metal',
            'Metal',
            'usado',
            '180',
            '90',
            '2',
            '2026-10-01',
            'sim',
            'lp-sepultura-arise-1991',
        ],
    ]
    planilha = _nova_planilha(rascunhos=rascunhos, produtos=produtos)
    rel = cl.validar_lote(arq, tmp_path, planilha=planilha, gerar_previas=False, base_trabalho=tmp_path / 'out')
    assert rel['erros'] == []
    assert rel['ok'] is True
    avisos_txt = '\n'.join(msg for _, msg in rel['avisos'])
    assert 'Repetido na loja' in avisos_txt
    assert 'Repetido no Painel' in avisos_txt
    assert 'Palavra de exagero' in avisos_txt
    assert 'confiança baixa' in avisos_txt


# ----------------------------------------------------------------------------
# 3. IDs continuando a numeração existente e Nomes novos / colisão
# ----------------------------------------------------------------------------
def test_ids_continuam_numeracao_do_lote_existente(tmp_path):
    dados = _lote_base_valido(tmp_path)
    rascunhos = [list(COLUNAS_CADASTRO)]
    for i in (1, 2):
        r = [''] * len(COLUNAS_CADASTRO)
        r[0] = f'2026-10-27-{i:02d}'
        r[1] = '2026-10-27'
        rascunhos.append(r)
    planilha = _nova_planilha(rascunhos=rascunhos)
    derivado = cl.derivar_lote(dados, planilha=planilha, pasta_local=tmp_path, usar_nomes_novos=True, detectar_recortes=False)
    assert derivado['rasc'][0][0] == '2026-10-27-03'
    assert all(f[0] == '2026-10-27-03' for f in derivado['fotos'])


def test_nomes_novos_gerados_e_colisao_gera_erro(tmp_path):
    dados = _lote_base_valido(tmp_path)
    _criar_foto_sintetica_capa(tmp_path / 'f5.jpg')
    dados['discos'][0]['fotos'].append({'arquivo': 'f5.jpg', 'papel': 'descartar'})

    planilha = _nova_planilha()
    derivado = cl.derivar_lote(dados, planilha=planilha, pasta_local=tmp_path, usar_nomes_novos=True, detectar_recortes=False)
    mapa = {item['antigo']: item['novo'] for item in derivado['renomeacoes']}
    assert mapa['f1.jpg'] == '2026-10-27-01 01 capa.jpg'
    assert mapa['f2.jpg'] == '2026-10-27-01 02 contracapa.jpg'
    assert mapa['f3.jpg'] == '2026-10-27-01 03 disco.jpg'
    assert mapa['f4.jpg'] == '2026-10-27-01 00 etiqueta.jpg'
    assert mapa['f5.jpg'] == '2026-10-27-01 descartada 1.jpg'

    # Cria arquivo colidente com um dos nomes novos
    (tmp_path / '2026-10-27-01 01 capa.jpg').write_bytes(b'colisao')
    arq_lote = _salvar_lote(tmp_path, dados)
    rel = cl.validar_lote(arq_lote, tmp_path, planilha=planilha, gerar_previas=False, base_trabalho=tmp_path / 'out')
    assert rel['ok'] is False
    assert any('Nome novo já existe na pasta' in msg for _, msg in rel['erros'])
    with pytest.raises(cl.ErroLote, match='Conferência encontrou erros'):
        cl.gravar_lote(arq_lote, tmp_path, planilha=planilha, confirmar=False, base_trabalho=tmp_path / 'out')


# ----------------------------------------------------------------------------
# 4. Simulação vs Gravação com retomada de plano
# ----------------------------------------------------------------------------
def test_simulacao_gravar_nao_escreve_nem_renomeia(tmp_path):
    dados = _lote_base_valido(tmp_path)
    arq_lote = _salvar_lote(tmp_path, dados)
    planilha = _nova_planilha()

    res = cl.gravar_lote(arq_lote, tmp_path, planilha=planilha, confirmar=False, base_trabalho=tmp_path / 'out')
    assert res['modo'] == 'simulacao'
    assert planilha._ss.abas['cadastro_rascunhos'].chamadas_update == []
    assert planilha._ss.abas['cadastro_fotos'].chamadas_update == []
    assert (tmp_path / 'f1.jpg').exists()
    assert not (tmp_path / '2026-10-27-01 01 capa.jpg').exists()


def test_plano_interrompido_apos_renomear_retoma_sem_duplicar(tmp_path):
    dados = _lote_base_valido(tmp_path)
    arq_lote = _salvar_lote(tmp_path, dados)
    planilha = _nova_planilha()
    base_trab = tmp_path / 'out'

    derivado = cl.derivar_lote(dados, planilha=planilha, pasta_local=tmp_path, usar_nomes_novos=True, detectar_recortes=True)
    for item in derivado['renomeacoes']:
        os.replace(tmp_path / item['antigo'], tmp_path / item['novo'])
        item['feito'] = True

    dir_lote = base_trab / '2026-10-27'
    dir_lote.mkdir(parents=True, exist_ok=True)
    plano = {
        'lote': '2026-10-27',
        'concluido': False,
        'rascunhos_dicts': derivado['rascunhos_dicts'],
        'fotos': derivado['fotos'],
        'renomeacoes': derivado['renomeacoes'],
        'pulados': derivado['pulados'],
    }
    (dir_lote / 'plano.json').write_text(json.dumps(plano, ensure_ascii=False), encoding='utf-8')

    # Retoma a gravação a partir do plano interrompido
    res1 = cl.gravar_lote(arq_lote, tmp_path, planilha=planilha, confirmar=True, base_trabalho=base_trab)
    assert res1['modo'] == 'confirmado'
    assert len(ler(planilha, 'cadastro_rascunhos')) == 2  # cabeçalho + 1 disco
    assert len(ler(planilha, 'cadastro_fotos')) == 5  # cabeçalho + 4 fotos

    # Se rodar de novo com concluido=False, confere IDs existentes e não duplica linhas na planilha
    plano_reaberto = json.loads((dir_lote / 'plano.json').read_text(encoding='utf-8'))
    plano_reaberto['concluido'] = False
    (dir_lote / 'plano.json').write_text(json.dumps(plano_reaberto, ensure_ascii=False), encoding='utf-8')

    res2 = cl.gravar_lote(arq_lote, tmp_path, planilha=planilha, confirmar=True, base_trabalho=base_trab)
    assert res2['escritas_planilha'] == 0
    assert len(ler(planilha, 'cadastro_rascunhos')) == 2
    assert len(ler(planilha, 'cadastro_fotos')) == 5


def test_renomear_lote_simulacao_e_confirmar(tmp_path):
    _criar_foto_sintetica_capa(tmp_path / 'IMG_001.jpg')
    _criar_foto_sintetica_capa(tmp_path / 'IMG_002.jpg')
    planilha = _nova_planilha(
        fotos=[
            list(COLUNAS_FOTOS),
            ['2026-10-26-01', '1', 'capa', 'drv1', '[[0,0],[500,0],[500,500],[0,500]]', 'IMG_001.jpg'],
            ['2026-10-26-01', '0', 'etiqueta', 'drv2', '', 'IMG_002.jpg'],
        ]
    )
    sim = cl.renomear_lote_antigo('2026-10-26', tmp_path, planilha=planilha, confirmar=False)
    assert sim['modo'] == 'simulacao'
    assert len(sim['itens']) == 2
    assert (tmp_path / 'IMG_001.jpg').exists()
    assert planilha._ss.abas['cadastro_fotos'].chamadas_update == []

    real = cl.renomear_lote_antigo('2026-10-26', tmp_path, planilha=planilha, confirmar=True)
    assert real['modo'] == 'confirmado'
    assert (tmp_path / '2026-10-26-01 01 capa.jpg').exists()
    assert (tmp_path / '2026-10-26-01 00 etiqueta.jpg').exists()
    linhas_f = ler(planilha, 'cadastro_fotos')
    assert linhas_f[1][5] == '2026-10-26-01 01 capa.jpg'
    assert linhas_f[2][5] == '2026-10-26-01 00 etiqueta.jpg'


# ----------------------------------------------------------------------------
# 5. Detecção de cantos e círculo em imagem sintética + folhas + recorte
# ----------------------------------------------------------------------------
def test_deteccao_cantos_capa_e_circulo_disco_sinteticos(tmp_path):
    arq_capa = tmp_path / 'capa.jpg'
    arq_disco = tmp_path / 'disco.jpg'
    _criar_foto_sintetica_capa(arq_capa, tamanho=(800, 800))
    _criar_foto_sintetica_disco(arq_disco, tamanho=(800, 800))

    with Image.open(arq_capa) as im_c:
        arr_c = np.array(im_c.convert('RGB'))
    cantos_capa = cl.detectar_cantos_capa(arr_c)
    assert cl.cantos_validos_na_imagem(cantos_capa, 800, 800)
    assert 55 <= cantos_capa[0][0] <= 95
    assert 50 <= cantos_capa[0][1] <= 90
    assert 405 <= cantos_capa[2][0] <= 445
    assert 410 <= cantos_capa[2][1] <= 450

    with Image.open(arq_disco) as im_d:
        arr_d = np.array(im_d.convert('RGB'))
    cantos_disco = cl.detectar_cantos_disco(arr_d)
    assert cl.cantos_validos_na_imagem(cantos_disco, 800, 800)
    # Círculo r=140 centrado em 400,400 -> ~[155..345] na escala de 500px
    assert 140 <= cantos_disco[0][0] <= 180
    assert 140 <= cantos_disco[0][1] <= 180
    assert 320 <= cantos_disco[2][0] <= 360
    assert 320 <= cantos_disco[2][1] <= 360


def test_comandos_folhas_e_recorte(tmp_path):
    _criar_foto_sintetica_capa(tmp_path / 'nova1.jpg')
    _criar_foto_sintetica_capa(tmp_path / 'ja_cadastrada.jpg')
    _criar_foto_sintetica_capa(tmp_path / '2026-10-15-01 01 capa.jpg')  # já no padrão ID, deve ser ignorada
    planilha = _nova_planilha(
        fotos=[
            list(COLUNAS_FOTOS),
            ['2026-10-26-01', '1', 'capa', 'drv1', '', 'ja_cadastrada.jpg'],
        ]
    )
    res_folhas = cl.gerar_folhas(
        pasta_local=tmp_path,
        planilha=planilha,
        lote='2026-10-27',
        base_trabalho=tmp_path / 'out',
    )
    assert res_folhas['fotos'] == 1
    assert res_folhas['folhas'] == 1
    assert res_folhas['fotos_txt'].exists()

    res_recorte = cl.recortar_foto(
        'nova1.jpg',
        0.1,
        0.1,
        0.9,
        0.9,
        pasta_local=tmp_path,
        lote='2026-10-27',
        base_trabalho=tmp_path / 'out',
    )
    assert res_recorte.exists()


def test_sintetico_foto_em_pe_fundo_branco_disco_grande():
    """D-091: foto em pé (portrait), fundo branco, disco grande com rótulo central."""
    w, h = 500, 900
    im = Image.new('RGB', (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(im)
    # Disco escuro grande (400x400 px, diâmetro 80% da largura)
    draw.ellipse([50, 250, 450, 650], fill=(22, 22, 25))
    # Rótulo central vermelho pequeno (100x100 px, diâmetro 20% da largura)
    draw.ellipse([200, 400, 300, 500], fill=(205, 50, 40))
    rgb = np.array(im)

    cantos = cl.detectar_cantos_disco(rgb)
    assert cantos is not None
    assert cl.cantos_validos_na_imagem(cantos, w, h)
    # Quadrado com 2% de folga em volta do disco (400 * 1.02 ~ 408 px)
    assert 40 <= cantos[0][0] <= 52
    assert 240 <= cantos[0][1] <= 252
    assert 448 <= cantos[2][0] <= 460
    assert 648 <= cantos[2][1] <= 660


def test_sintetico_capa_clara_fundo_branco_sombra_leve():
    """D-091: capa clara sobre fundo branco com sombra leve em foto em pé."""
    w, h = 500, 900
    im = Image.new('RGB', (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(im)
    # Sombra leve deslocada (cinza ~230)
    draw.rectangle([54, 254, 446, 646], fill=(230, 230, 230))
    # Capa clara (cinza ~215)
    draw.rectangle([50, 250, 440, 640], fill=(215, 215, 210))
    draw.text((100, 300), 'TITULO DO DISCO', fill=(50, 50, 50))
    rgb = np.array(im)

    cantos = cl.detectar_cantos_capa(rgb, 'capa')
    assert cantos is not None
    assert cl.cantos_validos_na_imagem(cantos, w, h)
    # Ordem: sup. esq., sup. dir., inf. dir., inf. esq.
    assert cantos[0][0] < cantos[1][0]  # x sup esq < x sup dir
    assert cantos[0][1] < cantos[3][1]  # y sup esq < y inf esq
    assert cantos[3][0] < cantos[2][0]  # x inf esq < x inf dir
    assert cantos[1][1] < cantos[2][1]  # y sup dir < y inf dir
    # Margem de 1% aplicada em volta do retângulo de 390x390 px (~394 px)
    assert 44 <= cantos[0][0] <= 52
    assert 244 <= cantos[0][1] <= 252
    assert 440 <= cantos[2][0] <= 452
    assert 640 <= cantos[2][1] <= 652


def test_sintetico_disco_pequeno_rotulo_rejeitado():
    """D-091: nunca aceitar círculo com diâmetro menor que 50% do menor lado."""
    w, h = 500, 900
    im = Image.new('RGB', (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(im)
    # Apenas um círculo pequeno escuro (120x120 px, 24% do menor lado)
    draw.ellipse([190, 390, 310, 510], fill=(30, 30, 30))
    rgb = np.array(im)

    cantos = cl.detectar_cantos_disco(rgb)
    assert cantos is None


def test_comando_recortar_lote_simulacao_e_confirmado(tmp_path):
    """D-091: recortar-lote gera prévias e só grava cantos e limpa fotos_ajustadas com --confirmar."""
    pasta_fotos = tmp_path / 'entrada'
    pasta_fotos.mkdir()

    # Cria uma foto de capa e uma de disco em pé
    arq_capa = pasta_fotos / '2026-10-28-03 01 capa.jpg'
    arq_disco = pasta_fotos / '2026-10-28-03 02 disco.jpg'
    _criar_foto_sintetica_capa(arq_capa, tamanho=(500, 800))
    _criar_foto_sintetica_disco(arq_disco, tamanho=(500, 800))

    planilha = _nova_planilha(
        rascunhos=[
            list(cl.COLUNAS),
            ['2026-10-28-03', '2026-10-28', '03 Teste', 'rascunho', 'LP Teste', 'Marca', 'LP', 'Ficha', 'Desc', 'VG+', 'VG+', '100', '0,5', '2,5', '32', '32', '', '01 capa.jpg | 02 disco.jpg', 'SEO', 'SEO D', 'Tags', '2026-10-28 10:00', 'etiqueta', '', '', '', '', '', '', '', '', '', '', '', '', '', 'sim', ''],
        ],
        fotos=[
            list(COLUNAS_FOTOS),
            ['2026-10-28-03', '1', 'capa', 'drv1', '', '2026-10-28-03 01 capa.jpg'],
            ['2026-10-28-03', '2', 'disco', 'drv2', '', '2026-10-28-03 02 disco.jpg'],
            ['2026-10-28-03', '0', 'etiqueta', 'drv3', '', '2026-10-28-03 00 etiqueta.jpg'],
        ]
    )

    # 1. Simulação
    res_sim = cl.recortar_lote_fotos(
        '2026-10-28',
        pasta_fotos,
        planilha,
        confirmar=False,
        base_trabalho=tmp_path / 'out',
    )
    assert res_sim['modo'] == 'simulacao'
    assert res_sim['discos'] == 1
    assert res_sim['fotos_processadas'] == 2
    assert res_sim['previas'] == 1
    assert res_sim['folhas_previas'] >= 1
    assert (tmp_path / 'out' / '2026-10-28' / 'previas' / '2026-10-28-03.jpg').exists()
    assert (tmp_path / 'out' / '2026-10-28' / 'folhas_previas' / 'folha_previa_01.jpg').exists()
    # Planilha intacta em simulação
    assert planilha._ss.abas['cadastro_fotos'].chamadas_update == []
    assert planilha._ss.abas[cl.ABA].chamadas_update == []

    # 2. Confirmado
    res_conf = cl.recortar_lote_fotos(
        '2026-10-28',
        pasta_fotos,
        planilha,
        confirmar=True,
        base_trabalho=tmp_path / 'out',
    )
    assert res_conf['modo'] == 'confirmado'
    linhas_f = ler(planilha, 'cadastro_fotos')
    # Linha da capa atualizada na coluna cantos (índice 4)
    assert linhas_f[1][4] != ''
    # Linha da etiqueta não tocada
    assert linhas_f[3][4] == ''
    # fotos_ajustadas limpa em cadastro_rascunhos
    linhas_r = ler(planilha, cl.ABA)
    idx_aj = cl.COLUNAS.index('fotos_ajustadas')
    assert linhas_r[1][idx_aj] == ''


# ----------------------------------------------------------------------------
# 6. Teste com fotos reais (meta >= 90% dos cantos contra referência)
# ----------------------------------------------------------------------------
PASTA_REAL = os.getenv('CADASTRO_PASTA_LOCAL', '').strip() or r'J:\Meu Drive\Cadastro de Discos\entrada'


@pytest.mark.skipif(
    not (
        Path(PASTA_REAL).exists()
        and CAMINHO_EXEMPLO_REF.exists()
        and CAMINHO_GRAVADAS_REF.exists()
        and any(Path(PASTA_REAL).glob('IMG_20261025_*.jpg'))
    ),
    reason='Pasta real CADASTRO_PASTA_LOCAL ou fotos do lote 2026-10-26 não disponíveis localmente.',
)
def test_fotos_reais_meta_90_porcento_cantos():
    ref_gravadas = json.loads(CAMINHO_GRAVADAS_REF.read_text(encoding='utf-8'))

    ref_cantos: list[tuple[str, str, list]] = []
    for row in ref_gravadas['fotos']:
        papel = row[2]
        cantos_str = row[4]
        arq = row[5]
        if cantos_str:
            ref_cantos.append((arq, papel, json.loads(cantos_str)))

    pasta = Path(PASTA_REAL)
    total = 0
    dentro_10px = 0
    for arq, papel, esperado in ref_cantos:
        caminho = pasta / arq
        if not caminho.exists():
            continue
        cantos, falhou = cl.calcular_cantos_foto(caminho, papel, {'arquivo': arq, 'papel': papel})
        total += 1
        if not falhou and cantos is not None:
            diffs = [
                max(abs(cantos[i][0] - esperado[i][0]), abs(cantos[i][1] - esperado[i][1]))
                for i in range(4)
            ]
            if max(diffs) <= 10:
                dentro_10px += 1

    assert total > 0
    taxa = dentro_10px / total
    assert taxa >= 0.90, f'Taxa de acerto em fotos reais ({taxa:.1%}) abaixo da meta de 90%'
