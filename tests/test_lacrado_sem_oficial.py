"""Testes para a regra de lacrado sem foto oficial (D-102).

Garante que um disco lacrado sem nenhuma foto com papel 'oficial':
- nunca usa foto de 'referencia' (nem foto própria da equipe) no site;
- recebe a pendência 'sem foto oficial';
- nasce oculto (publicar = 'nao', sem chamada de publicação na loja).
"""
from __future__ import annotations

import io
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
from PIL import Image

from painel_monstro.config import Config
from painel_monstro.saidas import cadastro as c
from painel_monstro.saidas.planilha_google import PlanilhaGoogle
from scripts import cadastro_lote as cl
from tests.test_cadastro import Drive, Loja, linha
from tests.test_planilha_google import PlanilhaFalsa


def _jpeg_bytes(cor: str = 'navy') -> bytes:
    im = Image.new('RGB', (200, 200), cor)
    buf = io.BytesIO()
    im.save(buf, 'JPEG', quality=90)
    return buf.getvalue()


def test_foto_publicavel_em_lacrado_aceita_apenas_oficial():
    assert c.foto_publicavel({'papel': 'oficial'}, lacrado=True) is True
    for papel in ('referencia', 'capa', 'contracapa', 'etiqueta', 'codigo_barras', 'descartar'):
        assert c.foto_publicavel({'papel': papel}, lacrado=True) is False


def test_derivar_lote_lacrado_sem_foto_oficial_marca_pendencia_e_nasce_oculto(tmp_path: Path):
    (tmp_path / 'equipe.jpg').write_bytes(_jpeg_bytes('darkred'))
    dados = {
        'lote': '2026-11-06',
        'discos': [
            {
                'disco': 'D01',
                'acao': 'cadastrar',
                'formato': 'lacrado',
                'artista': 'Insanidade',
                'album': 'Enough to Be a Loser',
                'ano': 2021,
                'preco_etiqueta': 140,
                'discogs_confianca': 'alta',
                'genero': 'Hard Rock / Heavy Metal / Metal',
                'descricao': 'LP novo e lacrado.\n\n• Novo / Lacrado',
                'tags': 'Insanidade, Enough to Be a Loser, LP, LP Novo, Vinil Lacrado',
                'fotos': [{'arquivo': 'equipe.jpg', 'papel': 'capa'}],
            }
        ],
    }
    res = cl.derivar_lote(dados, pasta_local=tmp_path, detectar_recortes=False)
    rasc = res['rascunhos_dicts'][0]

    assert rasc['fotos'] == ''
    assert res['detalhes_discos'][0]['n_fotos_site'] == 0
    assert [(f[1], f[2]) for f in res['fotos']] == [('0', 'referencia')]
    assert 'sem foto oficial' in rasc['pendencias']
    assert rasc['publicar'] == 'nao'


def test_derivar_lote_lacrado_com_discogs_mas_sem_arquivo_oficial_continua_oculto(tmp_path: Path):
    (tmp_path / 'equipe.jpg').write_bytes(_jpeg_bytes('darkgreen'))
    dados = {
        'lote': '2026-11-06',
        'discos': [
            {
                'disco': 'D01',
                'acao': 'cadastrar',
                'formato': 'lacrado',
                'artista': 'Banda Exemplo',
                'album': 'Disco Exemplo',
                'preco_etiqueta': 150,
                'discogs_url': 'https://www.discogs.com/release/999999',
                'discogs_confianca': 'alta',
                'descricao': 'LP novo.\n\n• Novo / Lacrado',
                'tags': 'Banda Exemplo, Disco Exemplo, LP, LP Novo, Vinil Lacrado',
                'fotos': [{'arquivo': 'equipe.jpg', 'papel': 'referencia'}],
            }
        ],
    }
    res = cl.derivar_lote(dados, pasta_local=tmp_path, detectar_recortes=False)
    rasc = res['rascunhos_dicts'][0]

    assert rasc['fotos'] == ''
    assert 'sem foto oficial' in rasc['pendencias']
    assert rasc['publicar'] == 'nao'


def test_validar_lote_lacrado_sem_foto_oficial_aceita_rascunho_com_aviso(tmp_path: Path):
    (tmp_path / 'equipe.jpg').write_bytes(_jpeg_bytes('purple'))
    dados = {
        'lote': '2026-11-06',
        'discos': [
            {
                'disco': 'D01',
                'acao': 'cadastrar',
                'formato': 'lacrado',
                'artista': 'Vanguart',
                'album': 'Estação Liberdade',
                'ano': 2021,
                'preco': 180,
                'genero': 'Rock / Pop Nacional',
                'descricao': 'Edição em vinil novo e lacrado.\n\n• Novo / Lacrado',
                'tags': 'Vanguart, Estação Liberdade, LP, LP Novo, Vinil Lacrado',
                'fotos': [{'arquivo': 'equipe.jpg', 'papel': 'referencia'}],
            }
        ],
    }
    arq = tmp_path / 'lote.json'
    arq.write_text(json.dumps(dados, ensure_ascii=False), encoding='utf-8')
    pg = PlanilhaGoogle(PlanilhaFalsa())
    c.preparar_abas(pg)

    rel = cl.validar_lote(arq, tmp_path, planilha=pg, gerar_previas=True, base_trabalho=tmp_path / 'out')
    assert rel['ok'] is True
    assert rel['erros'] == []
    assert any('sem foto oficial' in msg.lower() for _, msg in rel['avisos'])
    rasc = rel['derivado']['rascunhos_dicts'][0]
    assert 'sem foto oficial' in rasc['pendencias']
    assert rasc['publicar'] == 'nao'


def test_passo_rotina_rascunho_lacrado_sem_foto_oficial_grava_pendencia_e_nao_publica(tmp_path: Path):
    p = PlanilhaGoogle(PlanilhaFalsa())
    l = linha(
        status='rascunho',
        titulo='LP Vanguart - Estação Liberdade (2021) - (Novo/Lacrado)',
        categorias='LP, Novo/Lacrado, Nacionais, Novidades',
        publicar='sim',
        pendencias='sem Discogs',
    )
    p.substituir(c.ABA, pd.DataFrame([l], columns=c.COLUNAS))
    fs = [
        {
            'id_disco': 'disco-teste-1',
            'ordem': '0',
            'papel': 'referencia',
            'arquivo_drive_id': 'id-ref-equipe',
            'cantos': '',
            'observacao': 'equipe.jpg',
        }
    ]
    p.substituir('cadastro_fotos', pd.DataFrame(fs, columns=c.FOTOS))
    drive = Drive()

    res = c.passo_rotina(Config(), p, SimpleNamespace(produtos=pd.DataFrame()), tmp_path, drive=drive)
    atual = dict(zip(c.COLUNAS, c.ler(p, c.ABA)[1]))

    assert res['rascunhos'] == 1
    assert 'sem foto oficial' in atual['pendencias']
    assert atual['publicar'] == 'nao'
    assert drive.baixados == []


def test_processar_linha_lacrado_sem_foto_oficial_nunca_sobe_referencia_e_nasce_oculto(tmp_path: Path):
    class LojaComLacrado(Loja):
        def categorias(self):
            return super().categorias() + [{'id': 10, 'name': {'pt': 'Novo/Lacrado'}, 'parent': 1}]

    loja = LojaComLacrado()
    drive = Drive()
    l = linha(
        status='aprovado',
        titulo='LP Insanidade - Enough to Be a Loser (2021) - (Novo/Lacrado)',
        categorias='LP, Novo/Lacrado, Novidades',
        publicar='sim',
        pendencias='sem Discogs',
    )
    fotos_equipe = [
        {'ordem': '0', 'papel': 'referencia', 'arquivo_drive_id': 'ref-equipe'},
        {'ordem': '1', 'papel': 'capa', 'arquivo_drive_id': 'capa-equipe-legada'},
    ]

    c.processar_linha(l, fotos_equipe, loja, drive, l.update, tmp_path / 'diario.json')

    assert l['status'] == 'criado'
    assert l['publicar'] == 'nao'
    assert 'sem foto oficial' in l['pendencias']
    assert drive.baixados == []
    assert [p for p in loja.posts if isinstance(p, tuple) and p[0] == 'imagem'] == []
    assert loja.puts == []
    assert loja.produtos[12]['published'] is False


def test_executar_d102_simulacao_e_aplicacao_preserva_campos_e_rascunho(tmp_path: Path):
    from scripts.trocar_fotos_lacrados_sem_discogs import executar_d102

    arqs_dir = tmp_path / 'arquivos'
    arqs_dir.mkdir()
    (arqs_dir / '2026-11-03-09 01 oficial.jpg').write_bytes(_jpeg_bytes('black'))
    (arqs_dir / '2026-11-03-26 01 oficial.jpg').write_bytes(_jpeg_bytes('gold'))

    p = PlanilhaGoogle(PlanilhaFalsa())
    c.preparar_abas(p)
    r_pub = linha(
        id='2026-11-03-09',
        status='publicado',
        produto_id='379329047',
        titulo='LP Insanidade - Enough to Be a Loser (2021) - (Novo/Lacrado)',
        categorias='LP, Novo/Lacrado, Nacionais, Novidades',
        preco='140',
        estoque='1',
        fotos='01 capa.jpg',
    )
    r_rasc = linha(
        id='2026-11-03-26',
        status='rascunho',
        produto_id='',
        titulo='LP Vanguart - Estação Liberdade (2021) - (Novo/Lacrado)',
        categorias='LP, Novo/Lacrado, Nacionais, Novidades',
        preco='180',
        estoque='1',
        fotos='01 capa.jpg',
        fotos_ajustadas='[{"ordem":1}]',
    )
    p.substituir(c.ABA, pd.DataFrame([r_pub, r_rasc], columns=c.COLUNAS))
    p.substituir(
        'cadastro_fotos',
        pd.DataFrame(
            [
                ['2026-11-03-09', '1', 'capa', 'fid-eq-09', '', '2026-11-03-09 01 capa.jpg'],
                ['2026-11-03-26', '1', 'capa', 'fid-eq-26', '', '2026-11-03-26 01 capa.jpg'],
            ],
            columns=c.FOTOS,
        ),
    )

    eventos: list[tuple] = []

    class LojaD102:
        def __init__(self):
            self.imgs = [{'id': 777, 'position': 1, 'src': 'https://exemplo.com/antiga.jpg'}]

        def produto(self, pid: int):
            assert pid == 379329047
            return {'id': pid, 'published': False, 'images': list(self.imgs)}

        def imagem(self, pid: int, jpg: bytes, pos: int, nome: str):
            eventos.append(('post_imagem', pid, pos, nome))
            nova = {'id': 888 + pos, 'position': pos, 'src': f'https://exemplo.com/{nome}'}
            self.imgs.append(nova)
            return nova

        def apagar_imagem(self, pid: int, iid: int):
            eventos.append(('delete_imagem', pid, iid))
            self.imgs = [i for i in self.imgs if i['id'] != iid]
            return True

    class DriveFalso:
        def arquivos_entrada(self):
            return [
                {'id': 'fid-of-09', 'name': '2026-11-03-09 01 oficial.jpg'},
                {'id': 'fid-of-26', 'name': '2026-11-03-26 01 oficial.jpg'},
            ]

    plano_teste = [
        {
            'id': '2026-11-03-09',
            'produto_id': 379329047,
            'modo_item': 'publicado',
            'arquivos_oficiais': ['2026-11-03-09 01 oficial.jpg'],
            'fonte': 'Fonte oficial teste',
        },
        {
            'id': '2026-11-03-26',
            'produto_id': None,
            'modo_item': 'rascunho',
            'arquivos_oficiais': ['2026-11-03-26 01 oficial.jpg'],
            'fonte': 'Site oficial Deck',
        },
    ]

    loja_falsa = LojaD102()
    rel_sim = executar_d102(
        Config(),
        aplicar=False,
        pasta_arquivos=arqs_dir,
        caminho_relatorio=tmp_path / 'sim.json',
        planilha=p,
        api_nuvem=loja_falsa,
        drive=DriveFalso(),
        plano=plano_teste,
    )
    assert rel_sim['modo'] == 'simulacao'
    assert eventos == []

    rel_ap = executar_d102(
        Config(),
        aplicar=True,
        pasta_arquivos=arqs_dir,
        caminho_relatorio=tmp_path / 'ap.json',
        planilha=p,
        api_nuvem=loja_falsa,
        drive=DriveFalso(),
        plano=plano_teste,
    )
    assert rel_ap['modo'] == 'aplicado'
    # Garante upload da nova imagem ANTES de apagar a antiga e nenhum POST de produto para o rascunho
    assert eventos == [
        ('post_imagem', 379329047, 1, '2026-11-03-09-01-oficial.jpg'),
        ('delete_imagem', 379329047, 777),
    ]

    rascs = [dict(zip(c.COLUNAS, r)) for r in c.ler(p, c.ABA)[1:]]
    assert rascs[0]['preco'] == '140' and rascs[0]['estoque'] == '1' and rascs[0]['fotos'] == '01 oficial.jpg'
    assert rascs[1]['status'] == 'rascunho' and rascs[1]['produto_id'] == '' and rascs[1]['fotos'] == '01 oficial.jpg'

    fotos_finais = [dict(zip(c.FOTOS, r)) for r in c.ler(p, 'cadastro_fotos')[1:]]
    assert (fotos_finais[0]['ordem'], fotos_finais[0]['papel']) == ('0', 'referencia')
    assert (fotos_finais[1]['ordem'], fotos_finais[1]['papel']) == ('0', 'referencia')
    assert (fotos_finais[2]['id_disco'], fotos_finais[2]['papel'], fotos_finais[2]['arquivo_drive_id']) == (
        '2026-11-03-09',
        'oficial',
        'fid-of-09',
    )
    assert (fotos_finais[3]['id_disco'], fotos_finais[3]['papel'], fotos_finais[3]['arquivo_drive_id']) == (
        '2026-11-03-26',
        'oficial',
        'fid-of-26',
    )
