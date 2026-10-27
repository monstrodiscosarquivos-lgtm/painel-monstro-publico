import cv2, numpy as np, json, os, sys
from PIL import Image, ImageOps
def load(p):
    im=ImageOps.exif_transpose(Image.open(p)).convert('RGB'); return cv2.cvtColor(np.array(im),cv2.COLOR_RGB2BGR)
def warp(img,c,out=1600):
    pts=np.array(c[:4],dtype='float32')*(img.shape[1]/500.0)
    ratio=c[4] if len(c)>4 and isinstance(c[4],(int,float)) else 1
    W,H=int(out),int(out/ratio)
    # margem de 0,6% para não comer a borda
    ctr=pts.mean(0); pts=ctr+(pts-ctr)*1.006
    M=cv2.getPerspectiveTransform(pts,np.array([[0,0],[W,0],[W,H],[0,H]],dtype='float32'))
    r=cv2.warpPerspective(img,M,(W,H),borderMode=cv2.BORDER_REPLICATE)
    if 'cw' in c: r=cv2.rotate(r,cv2.ROTATE_90_CLOCKWISE)
    if 'ccw' in c: r=cv2.rotate(r,cv2.ROTATE_90_COUNTERCLOCKWISE)
    return r
def disco(img,out=1600):
    h,w=img.shape[:2]; sc=800/w; sm=cv2.resize(img,None,fx=sc,fy=sc); g=cv2.medianBlur(cv2.cvtColor(sm,cv2.COLOR_BGR2GRAY),5)
    cs=cv2.HoughCircles(g,cv2.HOUGH_GRADIENT,dp=1.5,minDist=400,param1=100,param2=40,minRadius=int(0.35*sm.shape[1]),maxRadius=int(0.52*sm.shape[1]))
    if cs is None: return quadrado(img,out)
    x,y,r=cs[0][0]/sc; r*=1.04; s=int(min(2*r,w,h)); x0=int(max(0,min(w-s,x-s/2))); y0=int(max(0,min(h-s,y-s/2)))
    return cv2.resize(img[y0:y0+s,x0:x0+s],(out,out),interpolation=cv2.INTER_AREA)
def quadrado(img,out=1600):
    h,w=img.shape[:2]; s=min(h,w); y=(h-s)//2; x=(w-s)//2
    return cv2.resize(img[y:y+s,x:x+s],(out,out),interpolation=cv2.INTER_AREA)
def inteira(img,out=1600):
    h,w=img.shape[:2]; f=out/max(h,w); return cv2.resize(img,(int(w*f),int(h*f)),interpolation=cv2.INTER_AREA)
if __name__=='__main__':
    src,dst,dados,cantos=sys.argv[1:5]
    d=json.load(open(dados)); C=json.load(open(cantos))
    for x in d:
        od=os.path.join(dst,x['pasta'],'site'); os.makedirs(od,exist_ok=True)
        for i,(f,papel) in enumerate(x['fotos'],1):
            img=load(os.path.join(src,f))
            if f in C: r=warp(img,C[f])
            elif papel.startswith('disco'): r=disco(img)
            elif papel.startswith('rotulo'): r=quadrado(img)
            else: r=inteira(img)
            o=os.path.join(od,f"{i:02d} {papel}.jpg"); cv2.imwrite(o,r,[cv2.IMWRITE_JPEG_QUALITY,86])
    print('ok')
