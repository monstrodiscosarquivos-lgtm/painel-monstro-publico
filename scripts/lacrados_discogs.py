"""Lacrados (D-093): busca cada disco no Discogs e baixa as imagens da edição para a pasta de entrada.

Disco lacrado não pode ser aberto para foto; por decisão do Túlio (28/10/2026) as imagens vêm do Discogs.
Uso (na pasta do repositório público, com o .venv da pasta principal):
    ..\\..\\.venv\\Scripts\\python scripts\\lacrados_discogs.py dados\\lacrados\\2026-10-29.csv
Entrada: CSV com `;` e colunas artista;disco;preco;qtd;dica.
Saída: JSON ao lado do CSV (mesmo nome) com a edição escolhida e 3 candidatas por disco,
e as imagens (até 3 por disco) em CADASTRO_PASTA_LOCAL, com o nome original do Discogs (R-<id>-...jpg).
Não grava nada na planilha nem na loja.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from painel_monstro.config import carregar  # noqa: E402
from painel_monstro.coletor.discogs import Discogs, ErroDiscogs, normalizar  # noqa: E402

MAX_IMAGENS = 3


def _pontos(r: dict, artista: str, disco: str, dica: str) -> float:
    titulo = normalizar(r.get('title', ''))
    p = 0.0
    if normalizar(disco) and normalizar(disco) in titulo:
        p += 10
    if normalizar(artista.split('&')[0]) in titulo:
        p += 5
    formatos = ' '.join(r.get('format') or [])
    if 'LP' in formatos or 'Vinyl' in formatos:
        p += 3
    texto = normalizar(' '.join([r.get('title', ''), formatos, ' '.join(r.get('label') or []), r.get('catno', '')]))
    for palavra in (dica or '').split():
        if len(palavra) > 2 and normalizar(palavra) in texto:
            p += 4
    try:
        p += (int(r.get('year') or 0) - 1950) / 20  # edições mais novas primeiro: lacrado costuma ser reedição recente
    except ValueError:
        pass
    return p


def resumo_release(rel: dict) -> dict:
    fmts = rel.get('formats') or []
    return {
        'discogs_id': rel.get('id'), 'discogs_url': f"https://www.discogs.com/release/{rel.get('id')}",
        'titulo': rel.get('title'), 'artistas': [a.get('name') for a in rel.get('artists') or []],
        'ano': rel.get('year'), 'pais': rel.get('country'),
        'selos': [{'nome': l.get('name'), 'catno': l.get('catno')} for l in rel.get('labels') or []],
        'formatos': [{'nome': f.get('name'), 'qtd': f.get('qty'), 'descricoes': f.get('descriptions'), 'texto': f.get('text')} for f in fmts],
        'generos': rel.get('genres'), 'estilos': rel.get('styles'),
        'faixas': [f"{t.get('position', '')} {t.get('title', '')}".strip() for t in rel.get('tracklist') or [] if t.get('type_', 'track') == 'track'],
        'codigos': [i.get('value') for i in rel.get('identifiers') or [] if i.get('type') == 'Barcode'][:2],
        'notas': (rel.get('notes') or '')[:600],
    }


def main(caminho_csv: str) -> int:
    cfg = carregar()
    pasta = Path(cfg.cadastro_pasta_local or '')
    if not cfg.discogs_token or not pasta.is_dir():
        print('Falta DISCOGS_TOKEN ou CADASTRO_PASTA_LOCAL no .env.')
        return 1
    dg = Discogs(cfg.discogs_token)
    linhas = list(csv.DictReader(open(caminho_csv, encoding='utf-8'), delimiter=';'))
    saida = []
    for n, l in enumerate(linhas, 1):
        artista, disco, dica = l['artista'].strip(), l['disco'].strip(), (l.get('dica') or '').strip()
        item = {'n': n, 'artista': artista, 'disco': disco, 'preco': l.get('preco'), 'qtd': l.get('qtd'), 'dica': dica}
        try:
            rs = []
            for consulta in ({'artist': artista.replace('?', ''), 'release_title': disco}, {'q': f'{artista} {disco}'.replace('?', '')}):
                rs = dg.get('/database/search', type='release', format='Vinyl', per_page=50, **consulta).get('results', [])
                if rs:
                    break
            rs.sort(key=lambda r: _pontos(r, artista, disco, dica), reverse=True)
            item['candidatas'] = [{'id': r['id'], 'titulo': r.get('title'), 'ano': r.get('year'), 'pais': r.get('country'),
                                   'formato': r.get('format'), 'selo': (r.get('label') or [''])[0], 'catno': r.get('catno')} for r in rs[:3]]
            if not rs:
                item['erro'] = 'não achei no Discogs'
            else:
                rel = dg.get(f"/releases/{rs[0]['id']}")
                item['escolhida'] = resumo_release(rel)
                imgs = sorted(rel.get('images') or [], key=lambda i: i.get('type') != 'primary')[:MAX_IMAGENS]
                item['imagens'] = []
                for img in imgs:
                    nome = img['uri'].split('/')[-1].split('?')[0]
                    if not nome.lower().endswith(('.jpg', '.jpeg', '.png')):
                        nome = f"R-{rel['id']}-{len(item['imagens']) + 1}.jpg"
                    destino = pasta / nome
                    if not destino.exists():
                        r = dg.sessao.get(img['uri'], timeout=60, headers={'User-Agent': 'PainelMonstro/1.0 +https://lojamonstro.com.br'})
                        r.raise_for_status()
                        destino.write_bytes(r.content)
                    item['imagens'].append(nome)
        except (ErroDiscogs, OSError, KeyError) as erro:
            item['erro'] = str(erro)[:200]
        saida.append(item)
        print(f"{n:02d} {artista} - {disco}: " + (item.get('erro') or f"{item['escolhida']['discogs_url']} ({len(item['imagens'])} imagens)"))
    destino_json = Path(caminho_csv).with_suffix('.json')
    destino_json.write_text(json.dumps(saida, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'Pronto: {destino_json}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1]))
