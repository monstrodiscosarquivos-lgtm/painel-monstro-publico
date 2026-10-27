# REFERÊNCIA (Cowork, lote 2026-10-26). Não roda aqui: caminhos e arquivos auxiliares eram da sessão do Cowork.
# Use só para portar as regras para scripts/cadastro_lote.py (ver docs/CADASTRO_IA_SCRIPT.md).
import json, re
L=json.load(open('todos.json')); C=json.load(open('cantos.json')); CD=json.load(open('cantos_disco.json'))
# capa da Maria Creusa: a detecção pegou só a foto; a capa tem a mesma altura e é quadrada
for t in ('115740',):
    q=C[t]; h=((q[3][1]-q[0][1])+(q[2][1]-q[1][1]))/2
    C[t]=[[int(q[1][0]-h),q[0][1]],q[1],q[2],[int(q[2][0]-h),q[3][1]]]
RUINS={'121118','121255','121653','122211','124646','125222','130006','130453','121325'}
NA_LOJA={'d09':'lp-serie-coletanea-vol-5-maria-bethania-1969-vinil-usado-rmj','d11':'lp-leandro-e-leonardo-1992-vinil-usado-1kn3w','d12':'lp-os-paralamas-do-sucesso-bora-bora','d15':'lp-roberto-carlos-canta-para-a-juventude-1971-vinil-usado','d16':'lp-maria-bethania-talisma-1980-vinil-usado','d29':'lp-biquini-cavadao-a-era-da-incerteza-1985-vinil-usado-vuyj7','d31':'lp-lulu-santos-honolulu','d32':'lp-caetano-veloso-caetano-1987-vinil-usado'}
PULAR={'d01','d20'}
ORD={'capa':1,'contracapa':2,'encarte frente':3,'encarte verso':4,'encarte aberto':5,'capa interna':6,'capa interna verso':7,'disco':8,'disco lado B':9}
rasc=[]; fotos=[]; n=0; resumo=[]
for o in L:
    if o['disco'] in PULAR: continue
    n+=1; id_='2026-10-26-%02d'%n
    art=o['artista'].strip(); alb=o['album'].strip(); ano=o.get('ano')
    if art.lower().startswith('vários') or art.lower()=='vários artistas': art='Vários'
    anos=f' ({ano})' if ano else ''
    sufixo='(Vinil Usado, Duplo)' if o.get('duplo') else '(Vinil Usado)'
    titulo=f'LP {art} - {alb}{anos} - {sufixo}'
    fs=[f for f in o['fotos'] if f['papel']!='outro']
    pend=[o.get('pendencias','').strip()] if o.get('pendencias','').strip() else []
    if not any(f['papel']=='capa' for f in fs):
        et=[f for f in fs if f['papel']=='etiqueta']
        if et: et[0]['papel']='capa'; pend.append('A capa só foi fotografada no plástico com a etiqueta de preço: essa foto vai para o site. Refotografar sem plástico se quiser.')
    if o.get('preco_etiqueta') in (None,'',0): pend.append('Sem etiqueta de preço nas fotos: definir o preço antes de aprovar.')
    if o['disco'] in NA_LOJA: pend.append(f'JÁ EXISTE NA LOJA COM ESTOQUE 1: lojamonstro.com.br/produtos/{NA_LOJA[o["disco"]]}/ . Confirmar se é outro exemplar; se for o mesmo disco, descartar este rascunho.')
    # ordem das fotos do site
    site=[f for f in fs if f['papel']!='etiqueta']
    site.sort(key=lambda f:(ORD.get(f['papel'],7.5), f['t']))
    seen={}; k=0; nomes=[]
    for f in fs:
        if f['papel']=='etiqueta':
            fotos.append([id_,'0','etiqueta','','',f'IMG_20261025_{f["t"]}.jpg'])
    for f in site:
        k+=1; p=f['papel']
        if p.startswith('disco'): can=CD.get(f['t'])
        elif f['t'] in RUINS: can=None
        else: can=C.get(f['t'])
        if can and p in ('encarte aberto','capa interna','capa interna verso') :
            q=can; w=q[1][0]-q[0][0]; h=q[3][1]-q[0][1]
            can=can+[2] if 1.8<w/max(h,1)<2.2 else (can if 0.9<w/max(h,1)<1.12 else None)
        fotos.append([id_,str(k),p,'',json.dumps(can) if can else '',f'IMG_20261025_{f["t"]}.jpg'])
        nomes.append(f'{k:02d} {p}.jpg')
    if o.get('duplo'): peso='0,8'
    elif o.get('gatefold') or any(f['papel'].startswith(('encarte','capa interna')) for f in site): peso='0,55'
    else: peso='0,5'
    cat='LP, Usado, '+o['genero'].strip()+', Novidades'
    ficha=', '.join(x for x in [o.get('gravadora',''), o.get('catalogo',''), o.get('pais',''), str(ano) if ano else '']if x)+'.'
    if o.get('ano_prensagem') and str(o.get('ano_prensagem'))!=str(ano): ficha+=f' Prensagem {o["ano_prensagem"]}.'
    if o.get('duplo'): ficha+=' Disco duplo.'
    if o.get('gatefold'): ficha+=' Capa dupla (gatefold).'
    if o.get('acompanha'): ficha+=' Acompanha: '+'; '.join(o['acompanha'])+'.'
    if o.get('marcas'): ficha+=' Marcas: '+o['marcas'].rstrip('.')+'.'
    if o.get('bolinha'): ficha+=f' Bolinha {o["bolinha"]} na etiqueta.'
    desc=o['descricao'].strip()
    primeira=re.split(r'(?<=\.)\s',desc.split('\n')[0])[0]
    seo_t=f'LP {art} {alb}{anos} - Vinil Usado'+(' Duplo' if o.get('duplo') else '')
    seo_d=(primeira if len(primeira)<=120 else primeira[:117].rsplit(' ',1)[0]+'…')+' Vinil usado, exemplar único.'
    preco=o.get('preco_etiqueta')
    row=[id_,'2026-10-26',f'{n:02d} {art} - {alb}{anos}','rascunho',titulo,art,cat,ficha,desc,o['capa'],o['vinil'],
         str(preco) if preco else '','',peso,'2,5','32','32','', '', ' | '.join(pend),' | '.join(nomes),seo_t,seo_d,o['tags'],
         '','','','2026-10-26 '+'12:00','','','','','','','etiqueta' if preco else '','','','1']
    assert len(row)==38
    rasc.append(row); resumo.append((id_,o['disco'],titulo,preco,o['capa'],o['vinil'],len(site)))
json.dump({'rasc':rasc,'fotos':fotos},open('linhas.json','w'),ensure_ascii=False)
for r in resumo: print(r)
print(len(rasc),'discos',len(fotos),'fotos')
import collections; print(collections.Counter(len(json.loads(f[4]))if f[4] else 0 for f in fotos))
