"""Black Monstro 2026: pré-venda e livros cada um só na sua categoria.

Os cupons BLACK e SULCO excluem as categorias de pré-venda e de livros, mas um produto que
também está em outra categoria continua pegando o desconto. Este script:
- deixa os produtos que ainda são pré-venda (PRE_VENDA) SÓ na categoria de endereço /pre-venda1/;
- tira das categorias de pré-venda os que já viraram venda normal (SAIR_DA_PRE), mantendo as outras;
- deixa todos os produtos da categoria /livros-1via9/ SÓ nela (e nas subcategorias dela, se houver).

Mexe apenas no campo categories (PUT /products/{id} só com ele). Preço, estoque, nome, fotos e
visibilidade ficam como estão. Produto com "pré-venda" ou "[PRÉ]" no nome que não está na lista
só aparece no --conferir: o Túlio decide.

Uso:  python -m scripts.categorias_black --conferir   (só mostra; não altera nada)
      python -m scripts.categorias_black --aplicar    (guarda o original em dados/ e aplica)
      python -m scripts.categorias_black --restaurar  (volta só os de PRE_VENDA; os de SAIR_DA_PRE ficam)
"""
from __future__ import annotations

import json
import re
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path

from painel_monstro.config import RAIZ_PROJETO, carregar
from painel_monstro.coletor.nuvemshop_api import NuvemshopAPI

HANDLE_PRE_VENDA = 'pre-venda1'
HANDLE_LIVROS = 'livros-1via9'
PRE_VENDA = {  # ainda são pré-venda: ficam SÓ na /pre-venda1/
    378604732: 'LP Pata de Elefante laranja',
    375734821: 'K7 Goiânia Rock City 2026',
}
SAIR_DA_PRE = {  # já viraram venda normal: saem das categorias de pré-venda e mantêm as outras
    340663484: 'LP Violator',
    333688340: 'LP Skylab IV',
    333690274: 'CD Skylab IV',
    333697528: 'K7 Skylab IV',
    333684358: 'Combo Skylab IV',
}
NOME_PRE = re.compile(r'pre[\s-]*venda|\[\s*pre\s*\]', re.I)
BACKUP = Path(RAIZ_PROJETO) / 'dados' / 'categorias_black_backup.json'


def _sem_acento(t: str) -> str:
    return unicodedata.normalize('NFKD', t or '').encode('ascii', 'ignore').decode()


def _pt(v) -> str:
    if isinstance(v, dict):
        return str(v.get('pt') or next(iter(v.values()), '') or '')
    return str(v or '')


def _ids(cats) -> list[int]:
    return [int(c['id'] if isinstance(c, dict) else c) for c in (cats or [])]


def _rotulo(ids, por_id) -> str:
    if not ids:
        return '(nenhuma)'
    return '; '.join(f"{_pt(por_id[i]['name']) if i in por_id else '?'} [{i}]" for i in ids)


def _descendentes(raiz: int, todas: list[dict]) -> set[int]:
    grupo, mudou = {raiz}, True
    while mudou:
        mudou = False
        for c in todas:
            if c['id'] not in grupo and c.get('parent') in grupo:
                grupo.add(c['id']); mudou = True
    return grupo


def _enviar(api: NuvemshopAPI, metodo: str, url: str, dados: dict | None = None):
    for tentativa in range(1, 6):
        api._esperar_vaga()
        r = api._sessao.request(metodo, url, headers={**api._cabecalhos, 'Content-Type': 'application/json'},
                                json=dados, timeout=60)
        api._guardar_limites(r)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(2 ** tentativa)
            continue
        return r
    return r


def _produto(api: NuvemshopAPI, pid: int) -> dict | None:
    r = api._get(f'{api._base}/products/{pid}', {'fields': 'id,name,categories,published'}, vazio_se_404=True)
    return r.json() if r is not None else None


def montar_plano(api: NuvemshopAPI):
    todas = list(api.listar('categories', fields='id,name,handle,parent'))
    por_id = {c['id']: c for c in todas}
    achar = lambda h: next((c['id'] for c in todas if _pt(c.get('handle')).strip('/').lower() == h), None)
    pre_id, livros_id = achar(HANDLE_PRE_VENDA), achar(HANDLE_LIVROS)
    if not pre_id or not livros_id:
        raise SystemExit(f'Parei: não achei a categoria /{HANDLE_PRE_VENDA}/ ou /{HANDLE_LIVROS}/ na loja.')
    livros_grupo = _descendentes(livros_id, todas)
    # todas as categorias de pré-venda (pelo nome) e as subcategorias delas
    pre_grupo = set().union(*(_descendentes(c['id'], todas) for c in todas
                              if c['id'] == pre_id or NOME_PRE.search(_sem_acento(_pt(c.get('name'))))))

    produtos = {p['id']: p for p in api.listar('products', fields='id,name,categories,published')}
    for pid in {**PRE_VENDA, **SAIR_DA_PRE}:  # garante os da lista mesmo se não vierem na listagem
        if pid not in produtos:
            p = _produto(api, pid)
            if p:
                produtos[pid] = p

    plano, avisos, faltando = [], [], []
    for grupo, lista in (('Pré-venda', PRE_VENDA), ('Sai da pré-venda', SAIR_DA_PRE)):
        for pid, apelido in lista.items():
            p = produtos.get(pid)
            if not p:
                faltando.append(f'{pid} ({apelido})'); continue
            antes = _ids(p.get('categories'))
            depois = [pre_id] if lista is PRE_VENDA else [c for c in antes if c not in pre_grupo]
            if not depois:
                faltando.append(f'{pid} ({apelido}): ficaria sem nenhuma categoria, não mexo')
                continue
            plano.append({'id': pid, 'grupo': grupo, 'nome': _pt(p.get('name')), 'antes': antes, 'depois': depois})
    for pid, p in produtos.items():
        atuais = _ids(p.get('categories'))
        if pid in PRE_VENDA or pid in SAIR_DA_PRE:
            continue
        if set(atuais) & livros_grupo:
            plano.append({'id': pid, 'grupo': 'Livros', 'nome': _pt(p.get('name')),
                          'antes': atuais, 'depois': [c for c in atuais if c in livros_grupo]})
        if NOME_PRE.search(_sem_acento(_pt(p.get('name')))):
            avisos.append((pid, _pt(p.get('name')), atuais, 'nome com pré-venda/[PRÉ], fora da lista'))
        elif set(atuais) & pre_grupo:
            avisos.append((pid, _pt(p.get('name')), atuais, 'está numa categoria de pré-venda, fora da lista'))
    return por_id, pre_id, livros_id, livros_grupo, pre_grupo, plano, avisos, faltando


def conferir(api: NuvemshopAPI):
    por_id, pre_id, livros_id, livros_grupo, pre_grupo, plano, avisos, faltando = montar_plano(api)
    print(f'Categoria pré-venda (destino): {_rotulo([pre_id], por_id)}')
    print(f'Categorias de pré-venda que saem dos produtos já à venda: {_rotulo(sorted(pre_grupo), por_id)}')
    print(f'Categoria livros:    {_rotulo([livros_id], por_id)}'
          + (f' + subcategorias {_rotulo(sorted(livros_grupo - {livros_id}), por_id)}' if len(livros_grupo) > 1 else ''))
    for grupo in ('Pré-venda', 'Sai da pré-venda', 'Livros'):
        itens = [x for x in plano if x['grupo'] == grupo]
        muda = [x for x in itens if sorted(x['antes']) != sorted(x['depois'])]
        print(f'\n=== {grupo}: {len(itens)} produtos, {len(muda)} vão mudar ===')
        for x in itens:
            igual = sorted(x['antes']) == sorted(x['depois'])
            print(f"\n{x['id']} · {x['nome']}")
            print(f"  agora: {_rotulo(x['antes'], por_id)}")
            print(f"  vai ficar: {'(já está certo, não mexo)' if igual else _rotulo(x['depois'], por_id)}")
    if faltando:
        print('\nATENÇÃO (não mexo): ' + ', '.join(faltando))
    print(f'\n=== Para o Túlio decidir (NÃO vou mexer): {len(avisos)} ===')
    for pid, nome, atuais, motivo in avisos:
        print(f'{pid} · {nome}\n  agora: {_rotulo(atuais, por_id)}\n  motivo: {motivo}')
    return por_id, plano


def aplicar(api: NuvemshopAPI) -> int:
    por_id, plano = conferir(api)
    muda = [x for x in plano if sorted(x['antes']) != sorted(x['depois'])]
    backup = json.loads(BACKUP.read_text(encoding='utf-8')) if BACKUP.exists() else {}
    agora = datetime.now().isoformat(timespec='seconds')
    for x in muda:  # nunca sobrescreve um original já guardado (rodar 2 vezes é seguro)
        backup.setdefault(str(x['id']), {'nome': x['nome'], 'grupo': x['grupo'], 'categorias': x['antes'],
                                         'guardado_em': agora})
    BACKUP.parent.mkdir(parents=True, exist_ok=True)
    BACKUP.write_text(json.dumps(backup, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'\nBackup em {BACKUP.relative_to(RAIZ_PROJETO)} ({len(backup)} produtos). Aplicando {len(muda)}...')
    return _gravar(api, [(x['id'], x['nome'], x['depois']) for x in muda])


def restaurar(api: NuvemshopAPI) -> int:
    if not BACKUP.exists():
        print('Não há backup em dados/categorias_black_backup.json. Nada a restaurar.')
        return 1
    backup = json.loads(BACKUP.read_text(encoding='utf-8'))
    # Só os que ainda são pré-venda voltam. Os de SAIR_DA_PRE já são venda normal: ficam como estão
    # (o original deles continua guardado no backup só como registro).
    voltar = {k: v for k, v in backup.items() if int(k) in PRE_VENDA}
    for k, v in backup.items():
        if k not in voltar:
            print(f"  fica como está (não volta): {k} · {v['nome']}")
    print(f'Restaurando {len(voltar)} produtos do backup...')
    erros = _gravar(api, [(int(k), v['nome'], v['categorias']) for k, v in voltar.items()])
    if not erros:
        destino = BACKUP.with_name(f"categorias_black_backup.restaurado-{datetime.now():%Y%m%d-%H%M%S}.json")
        BACKUP.rename(destino)
        print(f'Tudo restaurado. Backup arquivado em {destino.relative_to(RAIZ_PROJETO)}.')
    return erros


def _gravar(api: NuvemshopAPI, itens) -> int:
    erros = 0
    for pid, nome, cats in itens:
        r = _enviar(api, 'PUT', f'{api._base}/products/{pid}', {'categories': cats})
        conferido = _produto(api, pid) if r.status_code < 400 else None
        ok = conferido is not None and sorted(_ids(conferido.get('categories'))) == sorted(cats)
        erros += 0 if ok else 1
        detalhe = '' if ok else f' (resposta {r.status_code}: {r.text[:200]})'
        print(f"  {'OK  ' if ok else 'ERRO'} {pid} · {nome} -> {cats}{detalhe}")
    print(f'\nConcluído: {len(itens) - erros} certos, {erros} com erro.')
    return 1 if erros else 0


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    modos = [m for m in ('--conferir', '--aplicar', '--restaurar') if m in sys.argv]
    if len(modos) != 1:
        print(__doc__)
        return 2
    api = NuvemshopAPI(carregar())
    if modos[0] == '--conferir':
        conferir(api)
        print('\nNada foi alterado.')
        return 0
    return aplicar(api) if modos[0] == '--aplicar' else restaurar(api)


if __name__ == '__main__':
    raise SystemExit(main())
