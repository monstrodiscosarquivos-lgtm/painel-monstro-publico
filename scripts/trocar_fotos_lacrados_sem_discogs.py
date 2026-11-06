"""Troca de fotos dos 4 lacrados sem Discogs na loja e atualização do rascunho Vanguart (D-102).

Autorização única do Túlio (D-102):
- Nos 4 publicados (2026-11-03-09, 10, 15 e 16): troca somente as imagens na Nuvemshop
  pelas imagens oficiais aprovadas nas folhas de prévia, enviando todas as novas antes
  de apagar as antigas. Não altera nome, preço, estoque, descrição, categorias ou visibilidade.
- No rascunho 2026-11-03-26 (Vanguart): atualiza as fotos do rascunho com a capa oficial da Deck
  e marca a foto da equipe como referencia, mantendo status = 'rascunho' sem criar produto.
- Modo simulação por padrão; execução real somente com --aplicar.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from painel_monstro.config import Config, RAIZ_PROJETO, carregar  # noqa: E402
from painel_monstro.coletor.nuvemshop_api import NuvemshopAPI  # noqa: E402
from painel_monstro.saidas.cadastro import DriveFotos, ErroCadastro, FOTOS, LojaCadastro, ler  # noqa: E402
from painel_monstro.saidas.planilha_google import PlanilhaGoogle, _letra  # noqa: E402

PLANO_D102: list[dict[str, Any]] = [
    {
        'id': '2026-11-03-09',
        'produto_id': 379329047,
        'modo_item': 'publicado',
        'arquivos_oficiais': ['2026-11-03-09 01 oficial.jpg'],
        'fonte': 'Distribuição oficial Monstro Discos / Apple Music',
    },
    {
        'id': '2026-11-03-10',
        'produto_id': 379329295,
        'modo_item': 'publicado',
        'arquivos_oficiais': ['2026-11-03-10 01 oficial.jpg'],
        'fonte': 'Bandcamp oficial da banda (chaossynopsis.bandcamp.com)',
    },
    {
        'id': '2026-11-03-15',
        'produto_id': 379327716,
        'modo_item': 'publicado',
        'arquivos_oficiais': ['2026-11-03-15 01 oficial.jpg'],
        'fonte': 'Distribuição oficial Deezer 1400x1400 / selos Undershows e Kill Again',
    },
    {
        'id': '2026-11-03-16',
        'produto_id': 379327765,
        'modo_item': 'publicado',
        'arquivos_oficiais': [
            '2026-11-03-16 01 oficial.jpg',
            '2026-11-03-16 02 oficial.jpg',
        ],
        'fonte': 'Poeira Maldita (capa) e Brado Records (contracapa recortada)',
    },
    {
        'id': '2026-11-03-26',
        'produto_id': None,
        'modo_item': 'rascunho',
        'arquivos_oficiais': ['2026-11-03-26 01 oficial.jpg'],
        'fonte': 'Site oficial da gravadora Deck (deckdisc.com.br)',
    },
]


def executar_d102(
    config: Config,
    aplicar: bool = False,
    pasta_arquivos: Path | None = None,
    caminho_relatorio: Path | None = None,
    planilha: Any = None,
    api_nuvem: Any = None,
    drive: Any = None,
    plano: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    raiz = Path(RAIZ_PROJETO)
    dir_arqs = pasta_arquivos or (raiz / 'dados' / 'correcao_lacrados_previas' / 'arquivos')
    itens_plano = plano if plano is not None else PLANO_D102

    p = planilha or PlanilhaGoogle.conectar(config)
    loja = api_nuvem if hasattr(api_nuvem, 'imagem') else LojaCadastro(api_nuvem or NuvemshopAPI(config))

    dados_rasc = ler(p, 'cadastro_rascunhos')
    cab_r = dados_rasc[0]
    idx_r_id = cab_r.index('id')
    idx_r_status = cab_r.index('status')
    idx_r_pid = cab_r.index('produto_id')
    idx_r_fotos = cab_r.index('fotos')
    idx_r_ajust = cab_r.index('fotos_ajustadas')

    dados_fotos = ler(p, 'cadastro_fotos')
    cab_f = dados_fotos[0]
    if cab_f != FOTOS:
        raise ErroCadastro('Cabeçalho de cadastro_fotos fora do padrão esperado.')

    cfg_aba = {r[0]: r[1] for r in ler(p, 'Configuração') if len(r) > 1}
    entrada_id = cfg_aba.get('Cadastro: pasta de entrada Drive (ID)', '').strip()
    drv = drive
    if drv is None and aplicar:
        drv = DriveFotos(config, entrada_id)

    indice_drive: dict[str, str] = {}
    if drv is not None:
        for arq_d in (drv.arquivos_entrada() if hasattr(drv, 'arquivos_entrada') else []):
            nome_d = str(arq_d.get('name') or '')
            if nome_d and arq_d.get('id') and nome_d not in indice_drive:
                indice_drive[nome_d] = str(arq_d['id'])

    mapa_rasc: dict[str, tuple[int, dict[str, str]]] = {}
    for num_l, r in enumerate(dados_rasc[1:], 2):
        if r and len(r) > idx_r_id and r[idx_r_id]:
            mapa_rasc[r[idx_r_id]] = (num_l, dict(zip(cab_r, r)))

    relatorio_itens: list[dict[str, Any]] = []
    updates_fotos: list[dict[str, Any]] = []
    novas_linhas_fotos: list[list[str]] = []
    updates_rasc: list[dict[str, Any]] = []

    for item in itens_plano:
        did = item['id']
        modo_item = item['modo_item']
        pid = item.get('produto_id')
        arqs = item['arquivos_oficiais']

        if did not in mapa_rasc:
            raise ErroCadastro(f'ID {did} não encontrado em cadastro_rascunhos.')
        linha_num_r, rasc_dict = mapa_rasc[did]

        bytes_oficiais: list[tuple[str, bytes]] = []
        for nome_arq in arqs:
            cam = dir_arqs / nome_arq
            if not cam.is_file():
                raise ErroCadastro(f'Arquivo oficial ausente: {cam}')
            bytes_oficiais.append((nome_arq, cam.read_bytes()))

        detalhe: dict[str, Any] = {
            'id': did,
            'modo_item': modo_item,
            'produto_id': pid,
            'titulo': rasc_dict.get('titulo', ''),
            'fonte': item.get('fonte', ''),
            'arquivos_novos': [n for n, _ in bytes_oficiais],
            'status': 'simulado',
        }

        if modo_item == 'publicado':
            if str(rasc_dict.get('produto_id', '')).strip() != str(pid):
                raise ErroCadastro(f'produto_id divergente em {did}: esperado {pid}, lido {rasc_dict.get("produto_id")}')
            prod_antes = loja.produto(int(pid))
            imgs_antigas = prod_antes.get('images') or []
            detalhe['published_antes'] = prod_antes.get('published')
            detalhe['imagens_antigas'] = [
                {'id': im['id'], 'position': im.get('position'), 'src': im.get('src')}
                for im in imgs_antigas
            ]

            if aplicar:
                subidas = []
                for pos, (nome_arq, conteudo_jpg) in enumerate(bytes_oficiais, 1):
                    res_img = loja.imagem(int(pid), conteudo_jpg, pos, nome_arq.replace(' ', '-'))
                    subidas.append(res_img)
                    time.sleep(0.4)
                detalhe['novas_subidas_ids'] = [im.get('id') for im in subidas]

                apagadas = []
                for old_im in imgs_antigas:
                    loja.apagar_imagem(int(pid), old_im['id'])
                    apagadas.append(old_im['id'])
                    time.sleep(0.3)
                detalhe['antigas_apagadas_ids'] = apagadas

                prod_depois = loja.produto(int(pid))
                detalhe['published_depois'] = prod_depois.get('published')
                detalhe['imagens_depois_count'] = len(prod_depois.get('images') or [])
                detalhe['status'] = 'aplicado_loja'
        else:
            if rasc_dict.get('status') != 'rascunho' or str(rasc_dict.get('produto_id', '')).strip():
                raise ErroCadastro(f'{did} deveria estar em rascunho sem produto_id.')
            if aplicar:
                detalhe['status'] = 'aplicado_rascunho'

        # Planeja atualizações em cadastro_fotos e cadastro_rascunhos
        existentes_did = [
            (num_f, dict(zip(cab_f, f)))
            for num_f, f in enumerate(dados_fotos[1:], 2)
            if len(f) > 0 and f[0] == did
        ]
        for num_f, f_dict in existentes_did:
            if f_dict.get('papel') != 'oficial':
                updates_fotos.append({'range': f'B{num_f}', 'values': [['0', 'referencia']]})

        obs_existentes = {f_dict.get('observacao', '') for _, f_dict in existentes_did}
        for pos, (nome_arq, _) in enumerate(bytes_oficiais, 1):
            if nome_arq not in obs_existentes:
                fid = indice_drive.get(nome_arq, '')
                novas_linhas_fotos.append([did, str(pos), 'oficial', fid, '', nome_arq])

        nomes_curtos = ' | '.join(f'{pos:02d} oficial.jpg' for pos in range(1, len(bytes_oficiais) + 1))
        col_fotos = _letra(idx_r_fotos + 1)
        updates_rasc.append({'range': f'{col_fotos}{linha_num_r}', 'values': [[nomes_curtos]]})
        if modo_item == 'rascunho':
            col_ajust = _letra(idx_r_ajust + 1)
            updates_rasc.append({'range': f'{col_ajust}{linha_num_r}', 'values': [['[]']]})

        relatorio_itens.append(detalhe)

    if aplicar:
        aba_f = p._ss.worksheet('cadastro_fotos')
        if updates_fotos:
            if hasattr(aba_f, 'batch_update'):
                aba_f.batch_update(updates_fotos, raw=True)
            else:
                for u in updates_fotos:
                    aba_f.update(u['values'], u['range'], raw=True)
        if novas_linhas_fotos:
            atuais_f = ler(p, 'cadastro_fotos')
            ultima_f = len([l for l in atuais_f if any(str(c).strip() for c in l)])
            tot_f = ultima_f + len(novas_linhas_fotos)
            if aba_f.row_count < tot_f:
                aba_f.resize(rows=tot_f)
            aba_f.update(novas_linhas_fotos, f'A{ultima_f + 1}', raw=True)

        aba_r = p._ss.worksheet('cadastro_rascunhos')
        if updates_rasc:
            if hasattr(aba_r, 'batch_update'):
                aba_r.batch_update(updates_rasc, raw=True)
            else:
                for u in updates_rasc:
                    aba_r.update(u['values'], u['range'], raw=True)

    relatorio = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'modo': 'aplicado' if aplicar else 'simulacao',
        'itens': relatorio_itens,
        'fotos_marcadas_referencia': len(updates_fotos),
        'fotos_oficiais_adicionadas': len(novas_linhas_fotos),
    }

    cam_rel = caminho_relatorio or (raiz / 'dados' / 'troca_fotos_lacrados_d102.json')
    cam_rel.parent.mkdir(parents=True, exist_ok=True)
    cam_rel.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2), encoding='utf-8')
    return relatorio


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Troca de fotos dos lacrados sem Discogs (D-102).')
    parser.add_argument('--aplicar', action='store_true', help='Executa a troca real na Nuvemshop e na planilha.')
    args = parser.parse_args(argv)

    cfg = carregar()
    rel = executar_d102(cfg, aplicar=args.aplicar)
    print(f"Modo: {rel['modo']} | Itens: {len(rel['itens'])} | Referencias: {rel['fotos_marcadas_referencia']} | Oficiais novas: {rel['fotos_oficiais_adicionadas']}")
    for it in rel['itens']:
        print(f"  - {it['id']} ({it['modo_item']}): {it['status']} | novas={len(it['arquivos_novos'])}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
