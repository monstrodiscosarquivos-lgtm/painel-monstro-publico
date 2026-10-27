#!/usr/bin/env python3
"""
Régua de reativação mensal · Monstro Discos

Uso:
    python3 reativacao.py AAAA-MM            (ex: python3 reativacao.py 2026-11)

Antes de rodar, coloque as 3 exportações da Nuvemshop em Reativacao/AAAA-MM/entrada/
(clientes, vendas e produtos, em CSV, do jeito que a Nuvemshop exporta).

O script gera em Reativacao/AAAA-MM/:
    listas/etapa0-pos-compra.csv      15 a 44 dias após a 1ª compra · obrigado + novidades, sem desconto
    listas/etapa1-lembrete.csv        45 a 74 dias sem comprar  · novidades + lista de desejos, sem desconto
    listas/etapa2-convite.csv         90 a 119 dias             · cupom de frete grátis
    listas/etapa3-ultima-chamada.csv  180 a 209 dias            · cupom de 15%
    listas/vip-whatsapp.csv           VIPs com 75 a 104 dias    · mensagem pessoal no WhatsApp
    listas/controle.csv               10% sorteado que NÃO recebe nada (para medir o efeito)
    destaques-por-genero.csv          discos em estoque, mais recentes, por família de gênero
    resumo.md                         números do mês + resultado do mês anterior
    meta.json                         data de referência (usada no relatório do mês seguinte)

Como as janelas têm 30 dias e a rotina roda uma vez por mês, cada cliente cai em cada etapa uma vez só.
"""
import sys, os, json, re, glob, unicodedata
import pandas as pd

ETAPAS = [  # (arquivo, nome, dias_min, dias_max)
    ('etapa0-pos-compra', 'Etapa 0 · Pós-compra', 15, 44),   # só quem tem 1 compra
    ('etapa1-lembrete', 'Etapa 1 · Lembrete', 45, 74),
    ('etapa2-convite', 'Etapa 2 · Convite', 90, 119),
    ('etapa3-ultima-chamada', 'Etapa 3 · Última chamada', 180, 209),
]
VIP_JANELA = (75, 104)
VIP_MIN_COMPRAS, VIP_MIN_GASTO = 3, 1000
CONTROLE = 0.10
JANELA_RESULTADO = 30  # dias após o envio para contar uma compra como reativação

FAMILIAS = {
    'Rock e Prog': ['Classic Rock', 'Rock Clássico', 'Rock Progressivo', 'Psicodelico', 'Rock / Pop Internacional', 'Indie', 'New Wave', 'Folk'],
    'Brasil': ['Música Popular Brasileira', 'MPB', 'Rock / Pop Nacional', 'Regional', 'Samba', 'Sertanejo'],
    'Metal': ['Hard Rock', 'Metal'],
    'Groove': ['Disco / Funk / Soul', 'Jazz', 'Blues', 'Rap', 'Hip Hop', 'Reggae', 'Discoteca'],
}
KW = {
    'Metal': ['iron maiden', 'metallica', 'black sabbath', 'slipknot', 'sepultura', 'megadeth', 'judas priest', 'motorhead', 'motörhead', 'slayer', 'pantera', 'ozzy', ' dio ', 'saxon', 'kiss', 'ac/dc', 'helloween', 'angra', 'manowar', 'scorpions', 'deep purple', 'whitesnake', 'guns n', 'anthrax', 'korn', 'system of a down', 'rammstein', 'metal', 'venom', 'accept', 'dream theater', 'nightwish', 'blind guardian', 'rainbow', 'krisiun', 'viper', 'def leppard'],
    'Rock e Prog': ['pink floyd', ' yes ', 'genesis', 'king crimson', ' rush ', 'jethro tull', 'emerson', 'camel', 'mutantes', 'supertramp', 'alan parsons', 'marillion', 'led zeppelin', 'beatles', 'rolling stones', 'the who', 'fleetwood', 'eagles', 'creedence', 'doors', 'hendrix', 'dylan', 'queen', 'elton john', 'bowie', 'santana', 'dire straits', 'clapton', 'neil young', 'steely dan', 'kinks', 'aerosmith', 'nirvana', 'pearl jam', 'radiohead', 'pixies', 'the cure', 'smiths', 'new order', 'depeche', 'kraftwerk', 'u2', 'the cult', 'joy division', 'talking heads'],
    'Brasil': ['chico buarque', 'caetano', 'gilberto gil', 'gal costa', 'bethânia', 'bethania', 'milton nascimento', 'elis regina', 'djavan', 'belchior', 'jobim', 'vinicius', 'ivan lins', 'emílio santiago', 'fagner', 'zé ramalho', 'alceu', 'novos baianos', 'raul seixas', 'tim maia', 'jorge ben', 'benjor', 'cartola', 'paulinho da viola', 'clara nunes', 'alcione', 'beth carvalho', 'caymmi', 'luiz gonzaga', 'legião', 'titãs', 'paralamas', 'barão vermelho', 'ira!', 'ultraje', 'rita lee', 'blitz', 'cazuza', 'inocentes', 'samba', 'choro', 'bossa'],
    'Groove': ['james brown', 'stevie wonder', 'marvin gaye', 'earth, wind', 'prince', 'michael jackson', 'motown', 'aretha', 'barry white', 'donna summer', 'bee gees', 'boney m', 'miles davis', 'coltrane', 'jazz', 'blues', 'soul', 'funk', 'disco'],
}


def ler(path):
    for enc in ('utf-8-sig', 'latin1'):
        try:
            return pd.read_csv(path, sep=';', encoding=enc, dtype=str)
        except UnicodeDecodeError:
            continue
    raise SystemExit(f'Não consegui ler {path}')


def norm(s):
    return re.sub(r'\s+', ' ', str(s).strip().lower())


def sem_acento(s):
    return unicodedata.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode().lower().strip()


def familias(cat, nome):
    cat, n = str(cat), ' ' + str(nome).lower() + ' '
    out = {f for f, ks in FAMILIAS.items() if any(k.lower() in cat.lower() for k in ks)}
    out |= {f for f, ks in KW.items() if any(k in n for k in ks)}
    return out


def main():
    if len(sys.argv) < 2 or not re.fullmatch(r'\d{4}-\d{2}', sys.argv[1]):
        raise SystemExit('Uso: python3 reativacao.py AAAA-MM')
    mes = sys.argv[1]
    raiz = os.path.dirname(os.path.abspath(__file__))
    pasta = os.path.join(raiz, mes)
    entrada = os.path.join(pasta, 'entrada')
    os.makedirs(os.path.join(pasta, 'listas'), exist_ok=True)

    vendas = clientes = produtos = None
    for f in glob.glob(os.path.join(entrada, '*.csv')):
        df = ler(f)
        cols = ' '.join(df.columns)
        if 'Número do Pedido' in cols:
            vendas = df
        elif 'Total Consumido' in cols:
            clientes = df
        elif 'Identificador URL' in cols:
            produtos = df
    faltando = [n for n, d in [('vendas', vendas), ('clientes', clientes), ('produtos', produtos)] if d is None]
    if faltando:
        raise SystemExit(f'Faltam exportações em {entrada}: {", ".join(faltando)}')

    # ---------- vendas ----------
    v = vendas.copy()
    item_cols = ['Nome do Produto', 'Valor do Produto', 'Quantidade Comprada', 'SKU', 'Produto Fisico', 'Kit de produtos']
    ordem = [c for c in v.columns if c not in item_cols]
    v[ordem] = v.groupby('Número do Pedido')[ordem].transform('first')
    v = v[v['Status do Pagamento'].isin(['Confirmado', 'Parcialmente estornado'])]
    v['dt'] = pd.to_datetime(v['Data'], format='%d/%m/%Y %H:%M:%S', errors='coerce')
    v['Total'] = pd.to_numeric(v['Total'], errors='coerce')
    v['Valor do Produto'] = pd.to_numeric(v['Valor do Produto'], errors='coerce')
    v['email'] = v['E-mail'].str.strip().str.lower()
    ref = v['dt'].max().normalize() + pd.Timedelta(days=1)

    p = produtos.drop_duplicates('Identificador URL').copy()
    p['nk'] = p['Nome'].map(norm)
    catmap = dict(zip(p['nk'], p['Categorias']))
    v['fam'] = [familias(catmap.get(norm(n), ''), n) for n in v['Nome do Produto']]

    pedidos = v.drop_duplicates('Número do Pedido')
    g = pedidos.groupby('email').agg(n=('dt', 'size'), ultima=('dt', 'max'), total=('Total', 'sum'))
    g['dias'] = (ref - g['ultima']).dt.days
    fam_cnt = v.explode('fam').dropna(subset=['fam']).groupby(['email', 'fam']).size().unstack(fill_value=0)
    g['FAMILIA'] = fam_cnt.idxmax(axis=1).reindex(g.index)
    g['ULTIMOS_DISCOS'] = v.sort_values('dt').groupby('email')['Nome do Produto'].apply(lambda s: ' | '.join(s.dropna().tail(3)))

    # ---------- clientes ----------
    c = clientes.copy()
    c['email'] = c['E-mail'].str.strip().str.lower()
    c = c.drop_duplicates('email', keep='last')
    c = c[c['Marketing'] != 'Não aceita'].set_index('email')
    base = g.join(c[['Nome completo', 'Cidade', 'Estado', 'Telefone de Contato']], how='inner')
    base = base[base.index != 'contato@monstrodiscos.com.br']
    base['NOME'] = base['Nome completo'].fillna('').str.strip().str.split().str[0].str.title()
    base['VIP'] = (base.n >= VIP_MIN_COMPRAS) | (base.total >= VIP_MIN_GASTO)

    def exporta(df, etapa):
        return pd.DataFrame({
            'EMAIL': df.index, 'NOME': df.NOME.values, 'CIDADE': df.Cidade.values, 'SMS': df['Telefone de Contato'].values,
            'ETAPA': etapa, 'DIAS_SEM_COMPRAR': df.dias.values, 'N_COMPRAS': df.n.values,
            'TOTAL_GASTO': df.total.round(2).values, 'FAMILIA': df.FAMILIA.fillna('Variado').values,
            'ULTIMOS_DISCOS': df.ULTIMOS_DISCOS.values,
        })

    # ---------- destaques em estoque por família ----------
    p['estoque'] = pd.to_numeric(p['Estoque'], errors='coerce')
    vis = p[(p['Exibir na loja'] == 'SIM') & ((p['estoque'] > 0) | (p['Estoque'] == 'ND'))].copy()
    vis['fam'] = [familias(a, b) for a, b in zip(vis['Categorias'], vis['Nome'])]
    destaques = []
    for fam in FAMILIAS:
        sub = vis[vis['fam'].map(lambda s: fam in s)].head(8)
        for _, r in sub.iterrows():
            destaques.append({'FAMILIA': fam, 'PRODUTO': r['Nome'], 'PRECO': r['Preço'],
                              'URL': f"https://lojamonstro.com.br/produtos/{r['Identificador URL']}/"})
    dest = pd.DataFrame(destaques)
    dest.to_csv(os.path.join(pasta, 'destaques-por-genero.csv'), sep=';', index=False, encoding='utf-8-sig')

    # ---------- listas ----------
    seed = int(mes.replace('-', ''))
    resumo, controle = [], []
    vip = base[base.VIP & base.dias.between(*VIP_JANELA)]
    for arq, nome, a, b in ETAPAS:
        df = base[base.dias.between(a, b) & ~base.index.isin(vip.index)]
        if arq.startswith('etapa0'):
            df = df[df.n == 1]
        ctrl = df.sample(frac=CONTROLE, random_state=seed) if len(df) >= 10 else df.iloc[0:0]
        envio = df.drop(ctrl.index)
        exporta(envio.sort_values('total', ascending=False), nome).to_csv(
            os.path.join(pasta, 'listas', f'{arq}.csv'), sep=';', index=False, encoding='utf-8-sig')
        controle.append(exporta(ctrl, nome))
        resumo.append((nome, f'{a} a {b} dias', len(envio), len(ctrl)))
    vv = exporta(vip.sort_values('total', ascending=False), 'VIP · WhatsApp')
    picks = {f: dest[dest.FAMILIA == f].head(3).PRODUTO.tolist() for f in FAMILIAS}
    vv['SUGESTOES'] = [' | '.join(picks.get(f, [])) for f in vv.FAMILIA]
    vv.to_csv(os.path.join(pasta, 'listas', 'vip-whatsapp.csv'), sep=';', index=False, encoding='utf-8-sig')
    resumo.append(('VIP · WhatsApp', f'{VIP_JANELA[0]} a {VIP_JANELA[1]} dias', len(vv), 0))
    pd.concat(controle).to_csv(os.path.join(pasta, 'listas', 'controle.csv'), sep=';', index=False, encoding='utf-8-sig')

    with open(os.path.join(pasta, 'meta.json'), 'w') as fh:
        json.dump({'mes': mes, 'data_referencia': ref.strftime('%Y-%m-%d')}, fh)

    # ---------- resultado do mês anterior ----------
    ano, m = map(int, mes.split('-'))
    ant = f'{ano - 1}-12' if m == 1 else f'{ano}-{m - 1:02d}'
    rel = []
    meta_ant = os.path.join(raiz, ant, 'meta.json')
    if os.path.exists(meta_ant):
        d0 = pd.Timestamp(json.load(open(meta_ant))['data_referencia'])
        d1 = d0 + pd.Timedelta(days=JANELA_RESULTADO)
        janela = pedidos[(pedidos.dt >= d0) & (pedidos.dt < d1)]
        compr = janela.groupby('email').agg(pedidos=('dt', 'size'), receita=('Total', 'sum'))
        ctrl_ant = ler(os.path.join(raiz, ant, 'listas', 'controle.csv')) if os.path.exists(os.path.join(raiz, ant, 'listas', 'controle.csv')) else pd.DataFrame(columns=['EMAIL', 'ETAPA'])
        for f in sorted(glob.glob(os.path.join(raiz, ant, 'listas', '*.csv'))):
            if f.endswith('controle.csv'):
                continue
            lst = ler(f)
            em = lst['EMAIL'].str.lower()
            vol = compr.reindex(em).dropna()
            etapa = lst['ETAPA'].iloc[0] if len(lst) else os.path.basename(f)
            ce = ctrl_ant[ctrl_ant['ETAPA'] == etapa]['EMAIL'].str.lower()
            cv = compr.reindex(ce).dropna()
            taxa = len(vol) / len(lst) * 100 if len(lst) else 0
            taxa_c = len(cv) / len(ce) * 100 if len(ce) else None
            rel.append((etapa, len(lst), len(vol), taxa, vol.receita.sum(), len(ce), taxa_c))
        cupons = janela['Cupom de Desconto'].dropna()
        cupons = cupons[cupons.str.upper().str.startswith(('VOLTA', 'SEGUNDA', 'VIP'))].str.upper().value_counts()
    # ---------- resumo.md ----------
    L = [f'# Reativação · {mes}', '', f'Data de referência: {ref:%d/%m/%Y} (dia seguinte ao último pedido da exportação)', '',
         '| Etapa | Janela | Recebem | Controle (não recebe) |', '|---|---|---|---|']
    L += [f'| {a} | {b} | {c_} | {d} |' for a, b, c_, d in resumo]
    L += ['', f'Destaques em estoque por gênero: destaques-por-genero.csv ({len(dest)} discos).', '']
    if rel:
        L += [f'## Resultado de {ant} (compras em até {JANELA_RESULTADO} dias após o envio)', '',
              '| Etapa | Recebeu | Voltou a comprar | Taxa | Receita | Controle | Taxa controle |', '|---|---|---|---|---|---|---|']
        for e, n, k, t, r, nc, tc in rel:
            L.append(f'| {e} | {n} | {k} | {t:.1f}% | R$ {r:,.2f} | {nc} | {"-" if tc is None else f"{tc:.1f}%"} |'.replace(',', 'X').replace('.', ',').replace('X', '.'))
        if len(cupons):
            L += ['', 'Cupons da régua usados: ' + ', '.join(f'{k} ({v_})' for k, v_ in cupons.items())]
    else:
        L += [f'Sem listas de {ant} para comparar. O relatório de resultado aparece a partir do segundo mês.']
    open(os.path.join(pasta, 'resumo.md'), 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    print('\n'.join(L))


if __name__ == '__main__':
    main()
