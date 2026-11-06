"""Troca pontual de fotos sem recorte na loja pela versão recortada (D-101).

Autorização única do Túlio (D-101):
Para os produtos criados pelo cadastro cujas fotos ficaram sem recorte na loja
(disco ocupando menos de cerca de 75% da imagem, com fundo sobrando), substitui
apenas as imagens sem recorte pela versão recortada em pé, mantendo a mesma ordem.

Regras de segurança:
- Modo simulação por padrão; execução real apenas com flag explícita --aplicar.
- As imagens novas de cada produto são enviadas em ordem decrescente de posição
  (position) ANTES de apagar qualquer imagem antiga, preservando a ordem final
  1..N das demais fotos sem deixar o produto sem foto em nenhum instante.
- Não altera nome, preço, estoque, descrição, categorias ou visibilidade.
- Atualiza a coluna cantos na aba cadastro_fotos quando aplicável.
- Grava relatório antes/depois em dados/ (fora do git).
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

from painel_monstro.config import Config, carregar  # noqa: E402
from painel_monstro.coletor.nuvemshop_api import NuvemshopAPI  # noqa: E402
from painel_monstro.saidas import fotos  # noqa: E402
from painel_monstro.saidas.cadastro import ErroCadastro, LojaCadastro, ler  # noqa: E402
from painel_monstro.saidas.planilha_google import PlanilhaGoogle, _letra  # noqa: E402


def carregar_plano_recorte(caminho_plano: Path) -> list[dict[str, Any]]:
    """Lê o plano calibrado de recorte (JSON em dados/)."""
    if not caminho_plano.exists():
        raise ErroCadastro(f'Plano de recorte não encontrado: {caminho_plano}')
    itens = json.loads(caminho_plano.read_text(encoding='utf-8'))
    if not isinstance(itens, list):
        raise ErroCadastro('Plano de recorte inválido: esperado lista de itens')
    return itens


def agrupar_por_produto(
    itens_plano: list[dict[str, Any]],
    ids_excluir: set[str] | None = None,
    ids_apenas: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Agrupa as fotos a trocar por produto mantendo ordem estável."""
    grupos: dict[str, dict[str, Any]] = {}
    for item in itens_plano:
        did = str(item.get('id') or '').strip()
        if not did:
            continue
        if ids_excluir and did in ids_excluir:
            continue
        if ids_apenas and did not in ids_apenas:
            continue
        pid = int(item['produto_id'])
        if did not in grupos:
            grupos[did] = {
                'id': did,
                'produto_id': pid,
                'titulo': str(item.get('titulo') or did),
                'trocas': [],
            }
        grupos[did]['trocas'].append(item)

    resultado = list(grupos.values())
    for g in resultado:
        g['trocas'].sort(key=lambda x: int(x['pos']))
    return resultado


def obter_jpeg_recortado(item_troca: dict[str, Any]) -> bytes:
    """Obtém os bytes JPEG recortados a partir do arquivo pronto ou reprocessando a original."""
    caminho_rec = item_troca.get('caminho_recortada')
    if caminho_rec and Path(caminho_rec).exists():
        return Path(caminho_rec).read_bytes()
    caminho_orig = item_troca.get('caminho_orig')
    if not caminho_orig or not Path(caminho_orig).exists():
        raise ErroCadastro(f'Foto original não encontrada para {item_troca.get("id")} pos {item_troca.get("pos")}')
    cantos = item_troca.get('cantos')
    if not cantos:
        raise ErroCadastro(f'Cantos ausentes para {item_troca.get("id")} pos {item_troca.get("pos")}')
    papel = str(item_troca.get('papel') or 'capa')
    cantos_str = cantos if isinstance(cantos, str) else json.dumps(cantos)
    return fotos.processar(Path(caminho_orig).read_bytes(), papel, cantos_str)


def executar_troca_recorte(
    config: Config,
    aplicar: bool = False,
    caminho_plano: Path | None = None,
    caminho_relatorio: Path | None = None,
    ids_excluir: set[str] | None = None,
    ids_apenas: set[str] | None = None,
    planilha: Any = None,
    api_nuvem: Any = None,
) -> dict[str, Any]:
    """Executa a simulação ou a troca real somente das fotos sem recorte."""
    raiz = Path(config.raiz_projeto if hasattr(config, 'raiz_projeto') else Path(__file__).resolve().parents[1])
    arq_plano = caminho_plano or (raiz / 'dados' / 'correcao_recorte_previas' / 'plano_recorte_d101.json')
    arq_relatorio = caminho_relatorio or (raiz / 'dados' / 'troca_fotos_recorte_d101.json')

    itens_plano = carregar_plano_recorte(arq_plano)
    grupos = agrupar_por_produto(itens_plano, ids_excluir=ids_excluir, ids_apenas=ids_apenas)

    p = planilha or PlanilhaGoogle.conectar(config)
    loja = api_nuvem if hasattr(api_nuvem, 'imagem') else LojaCadastro(api_nuvem or NuvemshopAPI(config))

    dados_fotos = ler(p, 'cadastro_fotos')
    cab_f = dados_fotos[0] if dados_fotos else []
    idx_did = cab_f.index('id_disco') if 'id_disco' in cab_f else 0
    idx_ord = cab_f.index('ordem') if 'ordem' in cab_f else 1
    idx_cantos = cab_f.index('cantos') if 'cantos' in cab_f else 4

    relatorio_produtos: list[dict[str, Any]] = []
    atualizacoes_cantos: list[dict[str, Any]] = []
    total_fotos_trocar = 0

    for grupo in grupos:
        did = grupo['id']
        pid = grupo['produto_id']
        titulo = grupo['titulo']
        trocas = grupo['trocas']
        total_fotos_trocar += len(trocas)

        prod_nuvem = loja.produto(pid)
        imgs_atuais = sorted(
            prod_nuvem.get('images') or [],
            key=lambda im: int(im.get('position') or 0),
        )

        # Valida correspondência exata das posições e IDs antigos antes de qualquer escrita
        alvos_validados: list[dict[str, Any]] = []
        for tr in trocas:
            pos = int(tr['pos'])
            esperado_iid = tr.get('image_id')
            img_antiga = None
            if esperado_iid is not None:
                for im in imgs_atuais:
                    if int(im['id']) == int(esperado_iid):
                        img_antiga = im
                        break
                if img_antiga is None:
                    raise ErroCadastro(
                        f'Imagem antiga {esperado_iid} não encontrada em {did} (pid {pid}); abortando por segurança'
                    )
            else:
                if pos < 1 or pos > len(imgs_atuais):
                    raise ErroCadastro(
                        f'Posição {pos} fora do intervalo em {did} (pid {pid}, total={len(imgs_atuais)})'
                    )
                img_antiga = imgs_atuais[pos - 1]

            jpeg_novo = obter_jpeg_recortado(tr)
            alvos_validados.append({
                'pos': pos,
                'papel': tr.get('papel', ''),
                'ordem_planilha': str(tr.get('ordem_planilha') or '').strip(),
                'cantos': tr.get('cantos'),
                'old_image_id': int(img_antiga['id']),
                'old_src': img_antiga.get('src', ''),
                'jpeg_bytes': jpeg_novo,
                'tamanho_bytes_novo': len(jpeg_novo),
            })

        detalhe_prod: dict[str, Any] = {
            'id': did,
            'produto_id': pid,
            'titulo': titulo,
            'total_imagens_produto': len(imgs_atuais),
            'posicoes_trocadas': [a['pos'] for a in alvos_validados],
            'imagens_antes': [
                {'id': im['id'], 'position': im.get('position'), 'src': im.get('src')}
                for im in imgs_atuais
            ],
            'trocas_planejadas': [
                {
                    'pos': a['pos'],
                    'papel': a['papel'],
                    'old_image_id': a['old_image_id'],
                    'old_src': a['old_src'],
                    'tamanho_bytes_novo': a['tamanho_bytes_novo'],
                    'cantos': a['cantos'],
                }
                for a in alvos_validados
            ],
            'status': 'simulado',
        }

        if aplicar:
            novas_subidas = []
            try:
                # Sobe em ordem decrescente de posição para que os deslocamentos
                # mantenham exatamente as posições finais após apagar as antigas.
                for alvo in sorted(alvos_validados, key=lambda x: x['pos'], reverse=True):
                    pos = alvo['pos']
                    nome_arq = f'{did}-{pos:02d}-recorte.jpg'
                    res_post = loja.imagem(pid, alvo['jpeg_bytes'], pos, nome_arq)
                    novas_subidas.append({'pos': pos, 'id': res_post.get('id'), 'src': res_post.get('src')})
                    time.sleep(0.35)

                detalhe_prod['novas_subidas'] = list(reversed(novas_subidas))

                # Somente depois que todas as novas subiram com sucesso, apaga as antigas substituídas
                apagadas = []
                for alvo in sorted(alvos_validados, key=lambda x: x['pos'], reverse=True):
                    old_id = alvo['old_image_id']
                    loja.apagar_imagem(pid, old_id)
                    apagadas.append(old_id)
                    time.sleep(0.25)

                detalhe_prod['antigas_apagadas_ids'] = list(reversed(apagadas))
                detalhe_prod['status'] = 'aplicado_com_sucesso'
            except Exception as erro:
                detalhe_prod['status'] = f'erro: {type(erro).__name__} ({erro})'
                detalhe_prod['novas_subidas'] = novas_subidas
                relatorio_produtos.append(detalhe_prod)
                raise ErroCadastro(f'Falha ao trocar recorte de {did} (pid {pid}): {erro}') from erro

            # Prepara atualização de cantos na aba cadastro_fotos quando houver linha correspondente
            col_cantos = _letra(idx_cantos + 1)
            for alvo in alvos_validados:
                ord_pl = alvo['ordem_planilha']
                cantos_val = alvo['cantos']
                if not ord_pl or not cantos_val:
                    continue
                cantos_json = cantos_val if isinstance(cantos_val, str) else json.dumps(cantos_val)
                for num_linha, linha_f in enumerate(dados_fotos[1:], 2):
                    f_did = linha_f[idx_did] if len(linha_f) > idx_did else ''
                    f_ord = str(linha_f[idx_ord]).strip() if len(linha_f) > idx_ord else ''
                    if f_did == did and f_ord == ord_pl:
                        atualizacoes_cantos.append({
                            'range': f'{col_cantos}{num_linha}',
                            'values': [[cantos_json]],
                        })
                        break

        relatorio_produtos.append(detalhe_prod)

    if aplicar and atualizacoes_cantos:
        aba_fotos = p._ss.worksheet('cadastro_fotos')
        if hasattr(aba_fotos, 'batch_update'):
            aba_fotos.batch_update(atualizacoes_cantos, raw=True)
        else:
            for mudanca in atualizacoes_cantos:
                aba_fotos.update(mudanca['values'], mudanca['range'], raw=True)

    relatorio = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'modo': 'aplicado' if aplicar else 'simulacao',
        'total_produtos': len(grupos),
        'total_fotos_trocadas': total_fotos_trocar,
        'fotos_planilha_cantos_atualizados': len(atualizacoes_cantos),
        'produtos': relatorio_produtos,
    }

    arq_relatorio.parent.mkdir(parents=True, exist_ok=True)
    arq_relatorio.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2), encoding='utf-8')
    return relatorio


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Substitui somente as fotos sem recorte na loja (D-101).')
    parser.add_argument('--aplicar', action='store_true', help='Executa a troca real na Nuvemshop e atualiza cantos.')
    parser.add_argument('--plano', default=None, help='Caminho personalizado para o JSON do plano de recorte.')
    parser.add_argument('--relatorio', default=None, help='Caminho personalizado para salvar o relatório JSON.')
    parser.add_argument('--excluir', default=None, help='IDs separados por vírgula a excluir.')
    parser.add_argument('--apenas', default=None, help='IDs separados por vírgula para processar exclusivamente.')

    args = parser.parse_args(argv)
    cfg = carregar()

    ids_excluir = {i.strip() for i in args.excluir.split(',') if i.strip()} if args.excluir else None
    ids_apenas = {i.strip() for i in args.apenas.split(',') if i.strip()} if args.apenas else None

    print('=== Correção de Fotos sem Recorte na Loja (D-101) ===')
    print(f'Modo: {"APLICAÇÃO REAL" if args.aplicar else "SIMULAÇÃO (somente leitura)"}')
    if ids_excluir:
        print(f'Excluindo: {", ".join(sorted(ids_excluir))}')
    if ids_apenas:
        print(f'Apenas: {", ".join(sorted(ids_apenas))}')

    res = executar_troca_recorte(
        config=cfg,
        aplicar=args.aplicar,
        caminho_plano=Path(args.plano) if args.plano else None,
        caminho_relatorio=Path(args.relatorio) if args.relatorio else None,
        ids_excluir=ids_excluir,
        ids_apenas=ids_apenas,
    )

    print(f'\nTotal de produtos: {res["total_produtos"]} | Fotos a trocar: {res["total_fotos_trocadas"]}\n')
    print(f'{"ID":<15} | {"PID":<10} | {"Fotos trocadas":<16} | {"Total no site":<13} | {"Título"}')
    print('-' * 105)
    for pr in res['produtos']:
        pos_str = ', '.join(str(x) for x in pr['posicoes_trocadas'])
        print(f'{pr["id"]:<15} | {str(pr["produto_id"]):<10} | {pos_str:<16} | {pr["total_imagens_produto"]:<13} | {pr["titulo"][:44]}')
    print('-' * 105)

    if not args.aplicar:
        print('\nSimulação concluída. Nenhuma alteração feita na Nuvemshop nem na planilha.')
        print('Aguardando confirmação do Túlio para rodar com --aplicar.')
    else:
        print(f'\nTroca concluída! Cantos atualizados na planilha: {res["fotos_planilha_cantos_atualizados"]}.')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
