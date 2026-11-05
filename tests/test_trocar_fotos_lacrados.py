import io
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from PIL import Image

from scripts.trocar_fotos_lacrados import (
    ordenar_imagens_discogs,
    padronizar_jpeg,
    filtrar_alvos_lacrados,
    executar_troca_fotos,
    MAX_IMAGENS_DISCOGS,
)


def _criar_jpeg(largura: int, altura: int, cor=(200, 100, 50)) -> bytes:
    im = Image.new('RGB', (largura, altura), cor)
    buf = io.BytesIO()
    im.save(buf, 'JPEG')
    return buf.getvalue()


def test_ordenar_imagens_discogs():
    assert ordenar_imagens_discogs([]) == []
    imgs = [
        {'type': 'secondary', 'uri': 'https://img.discogs/2.jpg'},
        {'type': 'primary', 'uri': 'https://img.discogs/1.jpg'},
        {'type': 'secondary', 'uri': 'https://img.discogs/3.jpg'},
        {'type': 'secondary', 'uri': 'https://img.discogs/4.jpg'},
        {'type': 'secondary', 'uri': 'https://img.discogs/5.jpg'},
    ]
    res = ordenar_imagens_discogs(imgs, limite=MAX_IMAGENS_DISCOGS)
    assert len(res) == 4
    assert res[0]['type'] == 'primary'
    assert res[0]['uri'] == 'https://img.discogs/1.jpg'


def test_padronizar_jpeg():
    raw = _criar_jpeg(3000, 1500)
    proc = padronizar_jpeg(raw, max_dimensao=2000, qualidade=85)
    with Image.open(io.BytesIO(proc)) as im:
        assert im.format == 'JPEG'
        assert max(im.size) == 2000
        assert im.size == (2000, 1000)


def test_filtrar_alvos_lacrados():
    linhas = [
        {'id': '2026-11-03-01', 'produto_id': '101', 'discogs_id': '111', 'titulo': 'Pata de Elefante'},
        {'id': '2026-11-03-02', 'produto_id': '102', 'discogs_id': '222', 'titulo': 'Belchior'},
        {'id': '2026-11-03-03', 'produto_id': '103', 'discogs_id': '333', 'titulo': 'Karina Buhr'},
        {'id': '2026-11-03-09', 'produto_id': '', 'discogs_id': '', 'titulo': 'Sem pid'},
        {'id': '2026-11-03-10', 'produto_id': '', 'discogs_id': '444', 'titulo': 'Sem pid 2'},
        {'id': '2026-11-03-31', 'produto_id': '131', 'discogs_id': '999', 'titulo': 'Black Sabbath'},
        {'id': '2026-10-28-08', 'produto_id': '208', 'discogs_id': '888', 'titulo': 'Outro lote'},
    ]
    alvos = filtrar_alvos_lacrados(linhas, lote='2026-11-03', id_minimo='2026-11-03-03')
    ids = [a['id'] for a in alvos]
    assert ids == ['2026-11-03-03', '2026-11-03-31']

    # Teste de exclusão
    alvos_exc = filtrar_alvos_lacrados(linhas, lote='2026-11-03', id_minimo='2026-11-03-03', ids_excluir={'2026-11-03-31'})
    assert [a['id'] for a in alvos_exc] == ['2026-11-03-03']


def test_executar_troca_fotos_simulacao(tmp_path):
    linhas_rasc = [
        ['id', 'produto_id', 'discogs_id', 'titulo'],
        ['2026-11-03-03', '378914467', '14249845', 'LP Karina Buhr - Desmanche (2019)'],
    ]
    linhas_fotos = [
        ['id_disco', 'ordem', 'papel', 'arquivo_drive_id', 'cantos', 'observacao'],
        ['2026-11-03-03', '1', 'capa', '', '', '01 capa.jpg'],
        ['2026-11-03-03', '2', 'contracapa', '', '', '02 contracapa.jpg'],
    ]

    ws_rasc = SimpleNamespace(get_all_values=lambda: linhas_rasc)
    ws_fotos = SimpleNamespace(get_all_values=lambda: linhas_fotos)
    planilha_mock = SimpleNamespace(
        _ss=SimpleNamespace(worksheet=lambda nome: ws_rasc if nome == 'cadastro_rascunhos' else ws_fotos),
    )

    chamadas_post = []
    chamadas_del = []

    loja_mock = SimpleNamespace(
        produto=lambda pid: {
            'id': pid,
            'images': [{'id': 1001, 'position': 1, 'src': 'http://loja/1001.jpg'}],
        },
        imagem=lambda pid, jpeg, ordem, nome: chamadas_post.append((pid, ordem, nome)),
        apagar_imagem=lambda pid, iid: chamadas_del.append((pid, iid)),
    )

    dg_mock = SimpleNamespace(
        get=lambda path: {
            'images': [
                {'type': 'secondary', 'uri': 'http://discogs/2.jpg'},
                {'type': 'primary', 'uri': 'http://discogs/1.jpg'},
            ]
        },
        sessao=SimpleNamespace(get=lambda *a, **k: None),
    )

    rel_arq = tmp_path / 'relatorio_simulacao.json'
    res = executar_troca_fotos(
        config=SimpleNamespace(),
        aplicar=False,
        lote='2026-11-03',
        id_minimo='2026-11-03-03',
        caminho_relatorio=rel_arq,
        planilha=planilha_mock,
        api_nuvem=loja_mock,
        cliente_discogs=dg_mock,
    )

    assert res['modo'] == 'simulacao'
    assert res['total_produtos'] == 1
    assert len(chamadas_post) == 0
    assert len(chamadas_del) == 0
    assert rel_arq.exists()

    det = res['produtos'][0]
    assert det['id'] == '2026-11-03-03'
    assert len(det['imagens_antigas']) == 1
    assert len(det['imagens_novas_selecionadas']) == 2
    assert det['imagens_novas_selecionadas'][0]['type'] == 'primary'


def test_executar_troca_fotos_aplicar(tmp_path):
    linhas_rasc = [
        ['id', 'produto_id', 'discogs_id', 'titulo'],
        ['2026-11-03-03', '378914467', '14249845', 'LP Karina Buhr - Desmanche (2019)'],
    ]
    linhas_fotos = [
        ['id_disco', 'ordem', 'papel', 'arquivo_drive_id', 'cantos', 'observacao'],
        ['2026-11-03-03', '1', 'capa', '', '', '01 capa.jpg'],
        ['2026-11-03-03', '2', 'contracapa', '', '', '02 contracapa.jpg'],
    ]

    batch_atualizacoes = []

    def obter_aba(nome):
        return SimpleNamespace(
            get_all_values=lambda: linhas_rasc if nome == 'cadastro_rascunhos' else linhas_fotos,
            batch_update=lambda b, raw=True: batch_atualizacoes.extend(b),
        )

    planilha_mock = SimpleNamespace(
        _ler_aba=lambda nome: linhas_rasc if nome == 'cadastro_rascunhos' else linhas_fotos,
        _ss=SimpleNamespace(worksheet=obter_aba),
    )

    ordem_eventos = []

    def mock_imagem(pid, jpeg, ordem, nome):
        ordem_eventos.append(('POST', pid, ordem, nome))
        return {'id': 2000 + ordem}

    def mock_apagar(pid, iid):
        ordem_eventos.append(('DELETE', pid, iid))
        return True

    loja_mock = SimpleNamespace(
        produto=lambda pid: {
            'id': pid,
            'images': [{'id': 1001, 'position': 1}],
        },
        imagem=mock_imagem,
        apagar_imagem=mock_apagar,
    )

    jpeg_falso = _criar_jpeg(200, 200)

    class FakeResp:
        def __init__(self, content):
            self.content = content
        def raise_for_status(self):
            pass

    dg_mock = SimpleNamespace(
        get=lambda path: {
            'images': [
                {'type': 'primary', 'uri': 'http://discogs/capa.jpg'},
                {'type': 'secondary', 'uri': 'http://discogs/verso.jpg'},
            ]
        },
        sessao=SimpleNamespace(get=lambda url, **kw: FakeResp(jpeg_falso)),
    )

    rel_arq = tmp_path / 'relatorio_aplicado.json'
    res = executar_troca_fotos(
        config=SimpleNamespace(),
        aplicar=True,
        lote='2026-11-03',
        id_minimo='2026-11-03-03',
        caminho_relatorio=rel_arq,
        planilha=planilha_mock,
        api_nuvem=loja_mock,
        cliente_discogs=dg_mock,
    )

    assert res['modo'] == 'aplicado'
    assert len(ordem_eventos) == 3
    # Confere que os dois POSTs aconteceram ANTES do DELETE
    assert ordem_eventos[0][0] == 'POST' and ordem_eventos[0][2] == 1
    assert ordem_eventos[1][0] == 'POST' and ordem_eventos[1][2] == 2
    assert ordem_eventos[2][0] == 'DELETE' and ordem_eventos[2][2] == 1001

    # Confere que a planilha recebeu atualização para 'referencia'
    assert len(batch_atualizacoes) == 2
    for b in batch_atualizacoes:
        assert b['values'] == [['referencia']]
