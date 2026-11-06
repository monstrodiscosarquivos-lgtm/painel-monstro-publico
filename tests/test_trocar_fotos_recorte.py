import io
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from PIL import Image

from painel_monstro.saidas.cadastro import ErroCadastro
from scripts.trocar_fotos_recorte import (
    agrupar_por_produto,
    carregar_plano_recorte,
    executar_troca_recorte,
    obter_jpeg_recortado,
)


def _criar_jpeg(largura: int = 200, altura: int = 200, cor=(180, 90, 40)) -> bytes:
    im = Image.new('RGB', (largura, altura), cor)
    buf = io.BytesIO()
    im.save(buf, 'JPEG')
    return buf.getvalue()


def test_agrupar_por_produto_e_filtros():
    itens = [
        {'id': '2026-10-28-62', 'produto_id': 378825630, 'pos': 3, 'titulo': 'LP Bebeto - Sorte'},
        {'id': '2026-10-28-62', 'produto_id': 378825630, 'pos': 1, 'titulo': 'LP Bebeto - Sorte'},
        {'id': '2026-10-28-63', 'produto_id': 378825713, 'pos': 2, 'titulo': 'LP Bebeto - Fases'},
    ]
    grupos = agrupar_por_produto(itens)
    assert len(grupos) == 2
    assert grupos[0]['id'] == '2026-10-28-62'
    assert [t['pos'] for t in grupos[0]['trocas']] == [1, 3]

    so_fases = agrupar_por_produto(itens, ids_apenas={'2026-10-28-63'})
    assert [g['id'] for g in so_fases] == ['2026-10-28-63']

    sem_sorte = agrupar_por_produto(itens, ids_excluir={'2026-10-28-62'})
    assert [g['id'] for g in sem_sorte] == ['2026-10-28-63']


def test_obter_jpeg_recortado_a_partir_da_original(tmp_path):
    orig = tmp_path / 'orig.jpg'
    orig.write_bytes(_criar_jpeg(500, 281))
    jpeg = obter_jpeg_recortado({
        'id': '2026-10-28-62',
        'pos': 1,
        'papel': 'capa',
        'caminho_orig': str(orig),
        'cantos': [[100, 20], [340, 20], [340, 260], [100, 260]],
    })
    with Image.open(io.BytesIO(jpeg)) as im:
        assert im.format == 'JPEG'
        assert im.size == (1600, 1600)


def test_executar_troca_recorte_simulacao_nao_escreve(tmp_path):
    arq_rec = tmp_path / 'rec1.jpg'
    arq_rec.write_bytes(_criar_jpeg(400, 400))
    plano = tmp_path / 'plano.json'
    plano.write_text(json.dumps([
        {
            'id': '2026-10-28-62',
            'produto_id': 378825630,
            'pos': 1,
            'image_id': 101,
            'papel': 'capa',
            'ordem_planilha': '1',
            'titulo': 'LP Bebeto - Sorte (1989) - (Vinil Usado)',
            'cantos': [[101, 23], [340, 23], [342, 263], [99, 264]],
            'caminho_recortada': str(arq_rec),
        }
    ]), encoding='utf-8')

    linhas_fotos = [
        ['id_disco', 'ordem', 'papel', 'arquivo_drive_id', 'cantos', 'observacao'],
        ['2026-10-28-62', '1', 'capa', '', '', '01 capa.jpg'],
    ]
    planilha_mock = SimpleNamespace(
        _ss=SimpleNamespace(worksheet=lambda nome: SimpleNamespace(get_all_values=lambda: linhas_fotos)),
    )

    eventos = []
    loja_mock = SimpleNamespace(
        produto=lambda pid: {
            'id': pid,
            'images': [
                {'id': 101, 'position': 1, 'src': 'http://loja/101.jpg'},
                {'id': 102, 'position': 2, 'src': 'http://loja/102.jpg'},
            ],
        },
        imagem=lambda *a: eventos.append(('POST', a)),
        apagar_imagem=lambda *a: eventos.append(('DELETE', a)),
    )

    rel_arq = tmp_path / 'rel.json'
    res = executar_troca_recorte(
        config=SimpleNamespace(raiz_projeto=tmp_path),
        aplicar=False,
        caminho_plano=plano,
        caminho_relatorio=rel_arq,
        planilha=planilha_mock,
        api_nuvem=loja_mock,
    )

    assert res['modo'] == 'simulacao'
    assert res['total_produtos'] == 1
    assert res['total_fotos_trocadas'] == 1
    assert eventos == []
    assert rel_arq.exists()


def test_executar_troca_recorte_aplicar_preserva_ordem_e_sobe_antes_de_apagar(tmp_path):
    rec1 = tmp_path / 'rec1.jpg'
    rec3 = tmp_path / 'rec3.jpg'
    rec1.write_bytes(_criar_jpeg(400, 400, (200, 50, 50)))
    rec3.write_bytes(_criar_jpeg(400, 400, (50, 200, 50)))

    plano = tmp_path / 'plano.json'
    plano.write_text(json.dumps([
        {
            'id': '2026-10-28-62',
            'produto_id': 378825630,
            'pos': 1,
            'image_id': 101,
            'papel': 'capa',
            'ordem_planilha': '1',
            'titulo': 'LP Bebeto - Sorte (1989) - (Vinil Usado)',
            'cantos': [[101, 23], [340, 23], [342, 263], [99, 264]],
            'caminho_recortada': str(rec1),
        },
        {
            'id': '2026-10-28-62',
            'produto_id': 378825630,
            'pos': 3,
            'image_id': 103,
            'papel': 'encarte frente',
            'ordem_planilha': '3',
            'titulo': 'LP Bebeto - Sorte (1989) - (Vinil Usado)',
            'cantos': [[126, 21], [355, 20], [359, 250], [127, 252]],
            'caminho_recortada': str(rec3),
        },
    ]), encoding='utf-8')

    linhas_fotos = [
        ['id_disco', 'ordem', 'papel', 'arquivo_drive_id', 'cantos', 'observacao'],
        ['2026-10-28-62', '1', 'capa', '', '', '01 capa.jpg'],
        ['2026-10-28-62', '2', 'contracapa', '', '[[0,0],[500,0],[500,500],[0,500]]', '02 contracapa.jpg'],
        ['2026-10-28-62', '3', 'encarte frente', '', '', '03 encarte.jpg'],
        ['2026-10-28-62', '4', 'disco', '', '', '04 disco.jpg'],
    ]
    batch_updates = []
    aba_fotos = SimpleNamespace(
        get_all_values=lambda: linhas_fotos,
        batch_update=lambda b, raw=True: batch_updates.extend(b),
    )
    planilha_mock = SimpleNamespace(_ss=SimpleNamespace(worksheet=lambda nome: aba_fotos))

    # Simula exatamente o deslocamento de posições da Nuvemshop (inserção na posição e remoção posterior)
    estado_imagens = [
        {'id': 101, 'position': 1, 'src': 'old_1'},
        {'id': 102, 'position': 2, 'src': 'keep_2'},
        {'id': 103, 'position': 3, 'src': 'old_3'},
        {'id': 104, 'position': 4, 'src': 'keep_4'},
    ]
    ordem_operacoes = []
    prox_id = [900]

    def mock_imagem(pid, jpeg, pos, nome):
        prox_id[0] += 1
        novo_id = prox_id[0]
        ordem_operacoes.append(('POST', pos, novo_id))
        idx_ins = max(0, min(len(estado_imagens), pos - 1))
        estado_imagens.insert(idx_ins, {'id': novo_id, 'position': pos, 'src': f'new_pos{pos}'})
        for idx_p, item_im in enumerate(estado_imagens, 1):
            item_im['position'] = idx_p
        return {'id': novo_id, 'src': f'new_pos{pos}'}

    def mock_apagar(pid, iid):
        ordem_operacoes.append(('DELETE', iid))
        estado_imagens[:] = [im for im in estado_imagens if im['id'] != iid]
        # Nunca fica sem fotos em nenhum instante!
        assert len(estado_imagens) >= 4
        for idx_p, item_im in enumerate(estado_imagens, 1):
            item_im['position'] = idx_p
        return True

    loja_mock = SimpleNamespace(
        produto=lambda pid: {'id': pid, 'images': [dict(x) for x in estado_imagens]},
        imagem=mock_imagem,
        apagar_imagem=mock_apagar,
    )

    rel_arq = tmp_path / 'rel_aplicar.json'
    res = executar_troca_recorte(
        config=SimpleNamespace(raiz_projeto=tmp_path),
        aplicar=True,
        caminho_plano=plano,
        caminho_relatorio=rel_arq,
        planilha=planilha_mock,
        api_nuvem=loja_mock,
    )

    assert res['modo'] == 'aplicado'
    # Confere que TODOS os POSTs vieram antes de QUALQUER DELETE, em ordem decrescente de pos (3, depois 1)
    assert [op[0] for op in ordem_operacoes] == ['POST', 'POST', 'DELETE', 'DELETE']
    assert ordem_operacoes[0][1] == 3
    assert ordem_operacoes[1][1] == 1

    # Confere que a ordem final das 4 imagens no produto foi preservada exatamente!
    assert [im['src'] for im in estado_imagens] == ['new_pos1', 'keep_2', 'new_pos3', 'keep_4']
    assert [im['position'] for im in estado_imagens] == [1, 2, 3, 4]

    # Confere atualização dos cantos na planilha apenas para ordens 1 e 3
    assert len(batch_updates) == 2
    assert {b['range'] for b in batch_updates} == {'E2', 'E4'}


def test_aborta_se_image_id_divergir_na_loja(tmp_path):
    arq_rec = tmp_path / 'rec1.jpg'
    arq_rec.write_bytes(_criar_jpeg(200, 200))
    plano = tmp_path / 'plano_div.json'
    plano.write_text(json.dumps([
        {
            'id': '2026-10-28-62',
            'produto_id': 378825630,
            'pos': 1,
            'image_id': 999999,
            'papel': 'capa',
            'titulo': 'LP Bebeto - Sorte',
            'cantos': [[10, 10], [200, 10], [200, 200], [10, 200]],
            'caminho_recortada': str(arq_rec),
        }
    ]), encoding='utf-8')

    planilha_mock = SimpleNamespace(
        _ss=SimpleNamespace(worksheet=lambda nome: SimpleNamespace(get_all_values=lambda: [['id_disco', 'ordem', 'papel', 'arquivo_drive_id', 'cantos', 'observacao']])),
    )
    loja_mock = SimpleNamespace(
        produto=lambda pid: {'id': pid, 'images': [{'id': 101, 'position': 1}]},
        imagem=lambda *a: None,
        apagar_imagem=lambda *a: None,
    )

    with pytest.raises(ErroCadastro, match='não encontrada'):
        executar_troca_recorte(
            config=SimpleNamespace(raiz_projeto=tmp_path),
            aplicar=True,
            caminho_plano=plano,
            caminho_relatorio=tmp_path / 'rel.json',
            planilha=planilha_mock,
            api_nuvem=loja_mock,
        )
