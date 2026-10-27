"""Adaptação fiel de referencia/cadastro_piloto/processar.py, sem apagar originais."""
import io
import json

import cv2
import numpy as np
from PIL import Image, ImageOps


def processar(conteudo, papel='', cantos=''):
    imagem = ImageOps.exif_transpose(Image.open(io.BytesIO(conteudo))).convert('RGB')
    w, h = imagem.size
    pontos = json.loads(cantos) if isinstance(cantos, str) and cantos.strip() else (cantos or [])
    if pontos and not (4 <= len(pontos) <= 6):
        raise ValueError('cantos deve conter quatro pontos, proporção e giro opcionais')
    proporcao = float(pontos[4]) if len(pontos) > 4 else 1
    if proporcao not in (1, 2):
        raise ValueError('proporção deve ser 1 ou 2')
    giro = pontos[5] if len(pontos) > 5 else ''
    if giro not in ('', 'cw', 'ccw'):
        raise ValueError('giro inválido')
    papel = papel.strip().lower()
    rgb = np.array(imagem)
    if pontos:
        src = np.asarray(pontos[:4], dtype=np.float32) * (w / 500)
        if src.shape != (4, 2) or not np.isfinite(src).all() or (src < 0).any() or (src[:, 0] > w).any() or (src[:, 1] > h).any():
            raise ValueError('cantos fora da imagem')
        if not cv2.isContourConvex(src.astype(np.int32)) or abs(cv2.contourArea(src)) < 1:
            raise ValueError('cantos precisam formar um quadrilátero convexo')
        W,H=1600,int(1600/proporcao)
        destino=np.array([[0,0],[W,0],[W,H],[0,H]],dtype=np.float32)
        centro=src.mean(axis=0); src=centro+(src-centro)*1.006
        rgb=cv2.warpPerspective(rgb,cv2.getPerspectiveTransform(src,destino),(W,H),borderMode=cv2.BORDER_REPLICATE)
        if giro=='cw': rgb=cv2.rotate(rgb,cv2.ROTATE_90_CLOCKWISE)
        if giro=='ccw': rgb=cv2.rotate(rgb,cv2.ROTATE_90_COUNTERCLOCKWISE)
    elif papel.startswith(('disco','rótulo','rotulo')):
        lado=min(w,h); x=(w-lado)//2; y=(h-lado)//2
        if papel.startswith('disco'):
            escala=800/w
            menor=cv2.resize(rgb,None,fx=escala,fy=escala)
            cinza=cv2.medianBlur(cv2.cvtColor(menor,cv2.COLOR_RGB2GRAY),5)
            cs=cv2.HoughCircles(cinza,cv2.HOUGH_GRADIENT,dp=1.5,minDist=400,param1=100,param2=40,
                minRadius=int(.35*menor.shape[1]),maxRadius=int(.52*menor.shape[1]))
            if cs is not None:
                cx,cy,r=cs[0][0]/escala; r*=1.04; lado=int(min(2*r,w,h))
                x=int(max(0,min(w-lado,cx-lado/2))); y=int(max(0,min(h-lado,cy-lado/2)))
        rgb=cv2.resize(rgb[y:y+lado,x:x+lado],(1600,1600),interpolation=cv2.INTER_AREA)
    else:
        f=1600/max(w,h)
        rgb=cv2.resize(rgb,(int(w*f),int(h*f)),interpolation=cv2.INTER_AREA)
    ok,saida=cv2.imencode('.jpg',cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR),[cv2.IMWRITE_JPEG_QUALITY,86])
    if not ok: raise ValueError('não foi possível codificar JPEG')
    return saida.tobytes()
