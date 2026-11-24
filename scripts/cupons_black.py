"""Cupons da Black Monstro 2026 na Nuvemshop (D-109).

Lê os códigos na aba Configuração ("Black: cupons") e deixa cada cupom com a mesma regra:
- loja toda (usados e novos), menos as categorias de pré-venda e de livros (e as subcategorias delas);
- 25% acima de R$200, 30% acima de R$400, 35% acima de R$700 (pelo número no fim do código);
- BLACK..  : de 27 a 30/11 (aberto ao público);
- os outros (Lado A): só em 26/11. Esses códigos são mascarados no log, porque o repositório é público.
ANTECIPA.. não é mexido.

Uso:  python -m scripts.cupons_black              (só confere e mostra o que faria)
      python -m scripts.cupons_black --aplicar    (cria ou corrige os cupons)
"""
from __future__ import annotations

import re
import sys
import unicodedata

from painel_monstro.config import carregar
from painel_monstro.coletor.nuvemshop_api import NuvemshopAPI
from painel_monstro.saidas.planilha_google import PlanilhaGoogle

FAIXAS = {25: 200, 30: 400, 35: 700}          # % -> pedido mínimo (R$)
BLACK = ('2026-11-27', '2026-11-30')
LADO_A = ('2026-11-26', '2026-11-26')
EXCLUIR = re.compile(r'pre[\s-]*venda|livro', re.I)


def _sem_acento(t: str) -> str:
    return unicodedata.normalize('NFKD', t or '').encode('ascii', 'ignore').decode()


def _nome(cat: dict) -> str:
    n = cat.get('name') or {}
    return (n.get('pt') or next(iter(n.values()), '')) if isinstance(n, dict) else str(n)


def codigos_da_planilha(cfg) -> list[str]:
    plan = PlanilhaGoogle.conectar(cfg)
    linhas = plan._ss.worksheet('Configuração').get_all_values()
    valor = next((r[1] for r in linhas if r and r[0].strip() == 'Black: cupons' and len(r) > 1), '')
    return [c.strip().upper() for c in valor.split(',') if c.strip()]


def plano(codigos: list[str]) -> list[dict]:
    saida = []
    for c in codigos:
        if c.startswith('ANTECIPA'):
            continue
        m = re.search(r'(\d+)$', c)
        if not m or int(m.group(1)) not in FAIXAS:
            print(f'Aviso: não sei a faixa do cupom {c}; ficou de fora.')
            continue
        pct = int(m.group(1))
        ini, fim = BLACK if c.startswith('BLACK') else LADO_A
        saida.append({'code': c, 'pct': pct, 'min': FAIXAS[pct], 'ini': ini, 'fim': fim,
                      'grupo': 'Black' if c.startswith('BLACK') else 'Lado A'})
    return saida


def categorias(api: NuvemshopAPI) -> tuple[list[int], list[str]]:
    todas = list(api.listar('categories', fields='id,name,parent'))
    por_id = {c['id']: c for c in todas}
    fora = {c['id'] for c in todas if EXCLUIR.search(_sem_acento(_nome(c)))}
    mudou = True
    while mudou:  # leva junto as subcategorias
        mudou = False
        for c in todas:
            if c['id'] not in fora and c.get('parent') in fora:
                fora.add(c['id']); mudou = True
    nomes_fora = sorted(_nome(por_id[i]) for i in fora)
    return sorted(c['id'] for c in todas if c['id'] not in fora), nomes_fora


def buscar(api: NuvemshopAPI, codigo: str) -> dict | None:
    r = api._get(f'{api._base}/coupons', {'q': codigo, 'per_page': 50}, vazio_se_404=True)
    if r is None:
        return None
    return next((c for c in r.json() if str(c.get('code', '')).upper() == codigo), None)


def corpo(p: dict, cats: list[int]) -> dict:
    return {'code': p['code'], 'type': 'percentage', 'value': f"{p['pct']:.2f}", 'valid': True,
            'min_price': p['min'], 'start_date': p['ini'], 'end_date': p['fim'],
            'categories': cats, 'combines_with_other_discounts': False,
            'includes_shipping': False, 'first_consumer_purchase': False}


def resumo(c: dict | None) -> str:
    if not c:
        return 'não existe'
    cats = c.get('categories') or []
    return (f"{c.get('value')}% · mínimo R${c.get('min_price')} · {c.get('start_date')} a {c.get('end_date')} · "
            f"{'ativo' if c.get('valid') else 'INATIVO'} · categorias: {len(cats) if cats else 'todas'} · usos: {c.get('used', 0)}")


def enviar(api: NuvemshopAPI, metodo: str, url: str, dados: dict) -> tuple[int, str]:
    api._esperar_vaga()
    r = api._sessao.request(metodo, url, headers={**api._cabecalhos, 'Content-Type': 'application/json'},
                            json=dados, timeout=60)
    api._guardar_limites(r)
    return r.status_code, (r.text[:300] if r.status_code >= 400 else '')


def main() -> int:
    aplicar = '--aplicar' in sys.argv
    cfg = carregar()
    planos = plano(codigos_da_planilha(cfg))
    for p in planos:  # repositório público: os códigos do Lado A não aparecem no log
        if p['grupo'] == 'Lado A':
            print(f"::add-mask::{p['code']}")
    api = NuvemshopAPI(cfg)
    cats, fora = categorias(api)
    print(f'Categorias incluídas: {len(cats)}. Excluídas: {", ".join(fora) or "NENHUMA (confira os nomes!)"}')
    if not fora:
        print('Parei: não achei categoria de pré-venda nem de livros.')
        return 1
    erros = 0
    for p in planos:
        atual = buscar(api, p['code'])
        print(f"\n{p['grupo']} {p['code']}: agora = {resumo(atual)}")
        print(f"  alvo = {p['pct']}% · mínimo R${p['min']} · {p['ini']} a {p['fim']} · loja toda menos pré-venda e livros")
        if not aplicar:
            continue
        if atual:
            st, txt = enviar(api, 'PUT', f"{api._base}/coupons/{atual['id']}", corpo(p, cats))
        else:
            st, txt = enviar(api, 'POST', f'{api._base}/coupons', corpo(p, cats))
        ok = st in (200, 201)
        erros += 0 if ok else 1
        print(f"  {'OK' if ok else 'ERRO'} ({st}) {txt}")
        if ok:
            print(f"  conferido = {resumo(buscar(api, p['code']))}")
    if not aplicar:
        print('\nNada foi alterado. Rode com --aplicar para gravar.')
    return 1 if erros else 0


if __name__ == '__main__':
    raise SystemExit(main())
