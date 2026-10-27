# REFERÊNCIA (Cowork, lote 2026-10-26). Não roda aqui: caminhos e arquivos auxiliares eram da sessão do Cowork.
# Use só para portar as regras para scripts/cadastro_lote.py (ver docs/CADASTRO_IA_SCRIPT.md).
import cv2, numpy as np, json, sys
from PIL import Image, ImageOps
sys.path.insert(0,'.')
from grupos import G
src='/mnt/user-data/uploads/Cadastro de Discos/entrada/IMG_20261025_%s.jpg'
def linha_media(ls):
    pts=np.vstack([[l[0],l[1]] for l in ls]+[[l[2],l[3]] for l in ls]).astype(float)
    return pts
def fit(pts, vertical):
    # ajusta x = a*y + b (vertical) ou y = a*x + b
    if vertical: a,b=np.polyfit(pts[:,1],pts[:,0],1)
    else: a,b=np.polyfit(pts[:,0],pts[:,1],1)
    return a,b
def inter(v,hh):
    # x = av*y + bv ; y = ah*x + bh
    av,bv=v; ah,bh=hh
    y=(ah*bv+bh)/(1-ah*av); x=av*y+bv; return [x,y]
def detectar(t):
    im=np.array(ImageOps.exif_transpose(Image.open(src%t)).convert('RGB'))
    H,W=im.shape[:2]; s=1000/W
    sm=cv2.resize(im,(1000,int(H*s))); h,w=sm.shape[:2]
    g=cv2.GaussianBlur(cv2.cvtColor(sm,cv2.COLOR_RGB2GRAY),(3,3),0)
    e=cv2.Canny(g,10,30)
    L=cv2.HoughLinesP(e,1,np.pi/720,60,minLineLength=int(0.12*h),maxLineGap=15)
    if L is None: return None
    L=L.reshape(-1,4)
    vs,hs=[],[]
    for x1,y1,x2,y2 in L:
        dx,dy=x2-x1,y2-y1; ang=abs(np.degrees(np.arctan2(dy,dx)))
        if ang>80 and ang<100: vs.append((x1,y1,x2,y2))
        elif ang<10 or ang>170: hs.append((x1,y1,x2,y2))
    def lado(lines, key, pick):
        lines=[l for l in lines if 0.04*w < key(l) < 0.96*w] if pick in('min_x','max_x') else [l for l in lines if 0.02*h < key(l) < 0.98*h]
        if not lines: return None
        ks=np.array([key(l) for l in lines])
        alvo=ks.min() if pick.startswith('min') else ks.max()
        sel=[l for l,k in zip(lines,ks) if abs(k-alvo)<6]
        return sel
    mx=lambda l:(l[0]+l[2])/2; my=lambda l:(l[1]+l[3])/2
    # só linhas compridas no conjunto (soma de comprimento)
    def comp(sel, vert):
        return sum(abs(l[3]-l[1]) if vert else abs(l[2]-l[0]) for l in sel)
    def melhor(lines,key,pick,vert,minimo):
        ls=sorted(lines,key=key,reverse=(pick.startswith('max')))
        ls=[l for l in ls if (0.04*w<key(l)<0.96*w if vert else 0.02*h<key(l)<0.98*h)]
        for l in ls:
            k=key(l); sel=[m for m in ls if abs(key(m)-k)<6]
            if comp(sel,vert)>=minimo: return sel
        return None
    left=melhor(vs,mx,'min',True,0.35*h); right=melhor(vs,mx,'max',True,0.35*h)
    top=melhor(hs,my,'min',False,0.35*h); bot=melhor(hs,my,'max',False,0.35*h)
    if not all([left,right,top,bot]): return None
    V=[fit(linha_media(left),True),fit(linha_media(right),True)]
    Hh=[fit(linha_media(top),False),fit(linha_media(bot),False)]
    q=[inter(V[0],Hh[0]),inter(V[1],Hh[0]),inter(V[1],Hh[1]),inter(V[0],Hh[1])]
    return [[int(round(x/2)),int(round(y/2))] for x,y in q]
res={}
for gg in G:
    for t in gg: res[t]=detectar(t)
json.dump(res,open('cantos.json','w')); print(sum(v is None for v in res.values()),'sem')
