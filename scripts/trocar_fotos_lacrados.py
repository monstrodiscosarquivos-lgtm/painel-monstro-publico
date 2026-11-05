"""Troca de fotos de discos lacrados por imagens oficiais do Discogs (D-100).

Autorização expressa do Túlio (D-099/D-100):
Para os produtos lacrados do lote 2026-11-03 já cadastrados na loja (linhas 2026-11-03-03
em diante com produto_id), substitui as fotos atuais na Nuvemshop pelas imagens oficiais do
release no Discogs (até 4 imagens, capa primeiro).

Regras de segurança:
- Modo simulação por padrão; execução real apenas com flag explícita --aplicar.
- As imagens novas são enviadas primeiro na ordem (capa primeiro).
- Somente após o envio com sucesso de todas as imagens novas, as imagens antigas são apagadas.
- Não altera nome, preço, estoque, descrição, categorias ou qualquer outro campo do produto.
- As fotos antigas em cadastro_fotos têm seu papel atualizado para "referencia".
- Gera relatório completo antes/depois em dados/ (fora do git).
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sys
import time
from typing import Any

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from painel_monstro.config import carregar, Config  # noqa: E402
from painel_monstro.coletor.discogs import Discogs, ErroDiscogs  # noqa: E402
from painel_monstro.coletor.nuvemshop_api import NuvemshopAPI, ErroAPI  # noqa: E402
from painel_monstro.saidas.cadastro import LojaCadastro, ErroCadastro, ler  # noqa: E402
from painel_monstro.saidas.planilha_google import PlanilhaGoogle  # noqa: E402

MAX_IMAGENS_DISCOGS = 4


def ordenar_imagens_discogs(imagens: list[dict[str, Any]], limite: int = MAX_IMAGENS_DISCOGS) -> list[dict[str, Any]]:
    """Ordena imagens do release garantindo a capa (primary) em primeiro lugar."""
    if not imagens:
        return []
    ordenadas = sorted(imagens, key=lambda i: str(i.get('type') or '').lower() != 'primary')
    return ordenadas[:limite]


def padronizar_jpeg(conteudo_bytes: bytes, max_dimensao: int = 2400, qualidade: int = 92) -> bytes:
    """Garante imagem em formato JPEG limpo e de alta resolução."""
    with Image.open(io.BytesIO(conteudo_bytes)) as im:
        rgb = im.convert('RGB')
        w, h = rgb.size
        maior = max(w, h)
        if maior > max_dimensao:
            fator = max_dimensao / float(maior)
            novo_w = max(1, int(w * fator))
            novo_h = max(1, int(h * fator))
            rgb = rgb.resize((novo_w, novo_h), Image.LANCZOS)
        buffer = io.BytesIO()
        rgb.save(buffer, 'JPEG', quality=qualidade)
        return buffer.getvalue()


def filtrar_alvos_lacrados(
    linhas_rascunhos: list[dict[str, Any]],
    lote: str = '2026-11-03',
    id_minimo: str = '2026-11-03-03',
    ids_excluir: set[str] | None = None,
    ids_apenas: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Seleciona os produtos lacrados elegíveis com produto_id e discogs_id."""
    alvos = []
    prefixo = f'{lote}-'
    for r in linhas_rascunhos:
        did = str(r.get('id') or '').strip()
        pid = str(r.get('produto_id') or '').strip()
        discogs_id = str(r.get('discogs_id') or '').strip()
        if not did.startswith(prefixo):
            continue
        if did < id_minimo:
            continue
        if ids_excluir and did in ids_excluir:
            continue
        if ids_apenas and did not in ids_apenas:
            continue
        if not pid or not pid.isdigit():
            continue
        if not discogs_id or not discogs_id.isdigit():
            continue
        alvos.append(r)
    return alvos


SELECOES_CUSTOMIZADAS_PADRAO: dict[str, list[int]] = {
    '2026-11-03-08': [0, 1, 3],  # Juli Manzi: capa, 2ª e 4ª (pula a 3ª deitada)
}


def executar_troca_fotos(
    config: Config,
    aplicar: bool = False,
    lote: str = '2026-11-03',
    id_minimo: str = '2026-11-03-03',
    ids_excluir: set[str] | None = None,
    ids_apenas: set[str] | None = None,
    custom_selecoes_fotos: dict[str, list[int]] | None = None,
    caminho_relatorio: Path | None = None,
    planilha: Any = None,
    api_nuvem: Any = None,
    cliente_discogs: Any = None,
) -> dict[str, Any]:
    """Executa a simulação ou a troca real de fotos dos lacrados."""
    p = planilha or PlanilhaGoogle.conectar(config)
    dg = cliente_discogs or Discogs(config.discogs_token)
    loja = api_nuvem if hasattr(api_nuvem, 'imagem') else LojaCadastro(api_nuvem or NuvemshopAPI(config))

    dados_rasc = ler(p, 'cadastro_rascunhos')
    cab_r = dados_rasc[0]
    linhas_r = [dict(zip(cab_r, r)) for r in dados_rasc[1:]]

    dados_fotos = ler(p, 'cadastro_fotos')
    cab_f = dados_fotos[0]
    idx_f_did = cab_f.index('id_disco')
    idx_f_papel = cab_f.index('papel')

    alvos = filtrar_alvos_lacrados(
        linhas_r,
        lote=lote,
        id_minimo=id_minimo,
        ids_excluir=ids_excluir,
        ids_apenas=ids_apenas,
    )
    ids_alvo_set = {r['id'] for r in alvos}

    relatorio_itens = []
    atualizacoes_fotos_planilha = []

    selecoes_fotos = custom_selecoes_fotos if custom_selecoes_fotos is not None else SELECOES_CUSTOMIZADAS_PADRAO

    for item in alvos:
        did = item['id']
        pid = int(item['produto_id'])
        discogs_id = int(item['discogs_id'])
        titulo = item.get('titulo') or did

        # 1. Consulta produto atual na Nuvemshop
        prod_nuvem = loja.produto(pid)
        imagens_antigas = prod_nuvem.get('images') or []

        # 2. Consulta release no Discogs
        rel = dg.get(f'/releases/{discogs_id}')
        todas_imgs = rel.get('images') or []

        if did in selecoes_fotos:
            indices = selecoes_fotos[did]
            imgs_selecionadas = [todas_imgs[i] for i in indices if i < len(todas_imgs)]
        else:
            imgs_selecionadas = ordenar_imagens_discogs(todas_imgs, limite=MAX_IMAGENS_DISCOGS)

        detalhes_item = {
            'id': did,
            'produto_id': pid,
            'titulo': titulo,
            'discogs_id': discogs_id,
            'discogs_url': f'https://www.discogs.com/release/{discogs_id}',
            'total_imagens_discogs': len(todas_imgs),
            'imagens_antigas': [
                {'id': im['id'], 'position': im.get('position'), 'src': im.get('src')}
                for im in imagens_antigas
            ],
            'imagens_novas_selecionadas': [
                {'ordem': idx, 'type': im.get('type'), 'uri': im.get('uri')}
                for idx, im in enumerate(imgs_selecionadas, 1)
            ],
            'status': 'simulado',
        }

        if aplicar:
            if not imgs_selecionadas:
                detalhes_item['status'] = 'pulado_sem_imagens_discogs'
                relatorio_itens.append(detalhes_item)
                continue

            novas_subidas = []
            try:
                # 3. Baixa do Discogs e sobe na Nuvemshop em ordem (capa primeiro)
                for pos, im_info in enumerate(imgs_selecionadas, 1):
                    uri = im_info['uri']
                    r_img = dg.sessao.get(
                        uri,
                        timeout=60,
                        headers={'User-Agent': 'PainelMonstro/1.0 +https://lojamonstro.com.br'}
                    )
                    r_img.raise_for_status()
                    jpeg_bytes = padronizar_jpeg(r_img.content)
                    nome_arq = f'{did}-{pos:02d}-discogs.jpg'
                    res_post = loja.imagem(pid, jpeg_bytes, pos, nome_arq)
                    novas_subidas.append(res_post)
                    time.sleep(0.5)

                detalhes_item['novas_subidas_ids'] = [im.get('id') for im in novas_subidas]

                # 4. Somente após subir todas com sucesso, apaga as imagens antigas
                apagadas = []
                for old_im in imagens_antigas:
                    old_id = old_im['id']
                    loja.apagar_imagem(pid, old_id)
                    apagadas.append(old_id)
                    time.sleep(0.3)

                detalhes_item['antigas_apagadas_ids'] = apagadas
                detalhes_item['status'] = 'aplicado_com_sucesso'
            except Exception as erro:
                detalhes_item['status'] = f'erro: {type(erro).__name__} ({erro})'
                detalhes_item['novas_subidas_ids'] = [im.get('id') for im in novas_subidas]
                relatorio_itens.append(detalhes_item)
                raise ErroCadastro(f'Falha ao trocar fotos de {did} (pid {pid}): {erro}') from erro

        relatorio_itens.append(detalhes_item)

    # 5. Se aplicar, atualiza em cadastro_fotos o papel das fotos antigas para "referencia"
    if aplicar:
        col_letra_papel = chr(ord('A') + idx_f_papel)
        for num_linha, f in enumerate(dados_fotos[1:], 2):
            f_did = f[idx_f_did] if len(f) > idx_f_did else ''
            if f_did in ids_alvo_set:
                f_papel = f[idx_f_papel] if len(f) > idx_f_papel else ''
                if f_papel != 'referencia':
                    atualizacoes_fotos_planilha.append({
                        'range': f'{col_letra_papel}{num_linha}',
                        'values': [['referencia']],
                    })

        if atualizacoes_fotos_planilha:
            aba_fotos = p._ss.worksheet('cadastro_fotos')
            if hasattr(aba_fotos, 'batch_update'):
                aba_fotos.batch_update(atualizacoes_fotos_planilha, raw=True)
            else:
                for mudanca in atualizacoes_fotos_planilha:
                    aba_fotos.update(mudanca['values'], mudanca['range'], raw=True)

    relatorio = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'modo': 'aplicado' if aplicar else 'simulacao',
        'lote': lote,
        'total_produtos': len(alvos),
        'produtos': relatorio_itens,
        'fotos_planilha_atualizadas': len(atualizacoes_fotos_planilha),
    }

    if caminho_relatorio is None:
        raiz = Path(config.raiz_projeto if hasattr(config, 'raiz_projeto') else Path(__file__).resolve().parents[1])
        caminho_relatorio = raiz / 'dados' / f'troca_fotos_lacrados_{lote}.json'

    caminho_relatorio.parent.mkdir(parents=True, exist_ok=True)
    caminho_relatorio.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2), encoding='utf-8')

    return relatorio


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Troca fotos de produtos lacrados por imagens oficiais do Discogs.')
    parser.add_argument('--aplicar', action='store_true', help='Executa a troca real na Nuvemshop e na planilha.')
    parser.add_argument('--lote', default='2026-11-03', help='Lote a processar (padrão: 2026-11-03).')
    parser.add_argument('--id-min', default='2026-11-03-03', help='ID mínimo de disco (padrão: 2026-11-03-03).')
    parser.add_argument('--excluir', default=None, help='IDs separados por vírgula a excluir do processamento.')
    parser.add_argument('--apenas', default=None, help='IDs separados por vírgula para processar exclusivamente.')
    parser.add_argument('--relatorio', default=None, help='Caminho personalizado para salvar o relatório JSON.')

    args = parser.parse_args(argv)
    cfg = carregar()

    ids_excluir = {i.strip() for i in args.excluir.split(',')} if args.excluir else None
    ids_apenas = {i.strip() for i in args.apenas.split(',')} if args.apenas else None

    print(f'=== Troca de Fotos de Lacrados (D-100) ===')
    print(f'Modo: {"APLICAÇÃO REAL" if args.aplicar else "SIMULAÇÃO (somente leitura)"}')
    print(f'Lote: {args.lote} (ID >= {args.id_min})')
    if ids_excluir:
        print(f'Excluindo: {", ".join(sorted(ids_excluir))}')
    if ids_apenas:
        print(f'Apenas: {", ".join(sorted(ids_apenas))}')
    print('Consultando planilha, Discogs e Nuvemshop...')

    caminho_rel = Path(args.relatorio) if args.relatorio else None
    res = executar_troca_fotos(
        config=cfg,
        aplicar=args.aplicar,
        lote=args.lote,
        id_minimo=args.id_min,
        ids_excluir=ids_excluir,
        ids_apenas=ids_apenas,
        caminho_relatorio=caminho_rel,
    )

    print(f'\nTotal de produtos encontrados: {res["total_produtos"]}\n')
    print(f'{"ID":<15} | {"Produto":<42} | {"Release Discogs":<15} | {"Novas":<5} | {"Antigas":<7}')
    print('-' * 95)
    for p in res['produtos']:
        tit = p['titulo'][:40]
        novas = len(p['imagens_novas_selecionadas'])
        antigas = len(p['imagens_antigas'])
        rel_id = str(p['discogs_id'])
        print(f'{p["id"]:<15} | {tit:<42} | {rel_id:<15} | {novas:<5} | {antigas:<7}')

    print('-' * 95)
    print(f'\nRelatório salvo em: dados/troca_fotos_lacrados_{args.lote}.json')
    if not args.aplicar:
        print('Modo simulação concluído com sucesso. Nenhuma foto foi alterada na Nuvemshop nem na planilha.')
        print('Aguardando confirmação do Túlio para rodar com --aplicar.')
    else:
        print(f'Troca concluída com sucesso! {res["fotos_planilha_atualizadas"]} fotos marcadas como "referencia" na planilha.')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
