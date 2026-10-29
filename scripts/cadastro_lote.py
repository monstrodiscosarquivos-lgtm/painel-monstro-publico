"""D-078: identificação e gravação de rascunhos de discos por agente local.

Regras fixas (docs/CADASTRO_IA_SCRIPT.md):
- Só duas escritas: acrescentar linhas no fim de cadastro_rascunhos e de cadastro_fotos,
  e renomear fotos dentro da pasta de entrada local (ou atualizar observacao em renomear-lote).
- Nunca alterar/apagar linha existente, mexer em outras abas, apagar/mover foto ou chamar Nuvemshop.
- Status sempre rascunho. Modo simulação por padrão (gravar e renomear-lote exigem --confirmar).
"""
from __future__ import annotations

from datetime import datetime
import io
import json
import math
from pathlib import Path
import re
import sys
from typing import Any

import cv2
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from painel_monstro.config import Config, RAIZ_PROJETO, carregar
from painel_monstro.log_publico import ArgumentParserSeguro, comando_seguro, resumo_erro
from painel_monstro.saidas import cadastro as cad, fotos as mod_fotos
from painel_monstro.saidas.cadastro import (
    ABA,
    COLUNAS,
    FOTOS,
    identidade_titulo,
    ler,
    numero,
    peso_padrao,
    preparar_abas,
    texto_normal,
)
from painel_monstro.saidas.planilha_google import PlanilhaGoogle, _letra

ORDEM_PAPEIS = {
    'capa': 1,
    'contracapa': 2,
    'encarte frente': 3,
    'encarte verso': 4,
    'encarte aberto': 5,
    'capa interna': 6,
    'capa interna verso': 7,
    'disco': 8,
    'disco lado B': 9,
}
PAPEIS_VALIDOS = {'etiqueta', 'descartar', *ORDEM_PAPEIS}
NOTAS_GOLDMINE = {'M', 'NM', 'VG+', 'VG', 'G+', 'G', 'F'}
GENEROS_ACEITOS = {
    'Classic Rock',
    'Disco / Funk / Soul',
    'Discoteca / Eletronico / Dance / House',
    'Folk / Country',
    'Hard Rock / Heavy Metal / Metal',
    'Indie / Rock Alternativo',
    'Jazz / Blues',
    'MPB - Música Popular Brasileira',
    'New Age - Ambient',
    'New Wave / Synth Pop',
    'Pop',
    'Rap / Hip Hop',
    'Reggae / Dub',
    'Regional',
    'Rock / Pop Internacional',
    'Rock / Pop Nacional',
    'Rock Progressivo / Psicodelico',
    'Samba / Pagode',
    'Sertanejo',
    'Trilha Sonora / Novela',
}
PALAVRAS_EXAGERO = ('imperdível', 'imperdivel', 'raríssimo', 'rarissimo', 'obra-prima', 'obra prima')
PADRAO_ID_ARQUIVO = re.compile(r'^\d{4}-\d{2}-\d{2}-\d+ ')
EXTENSOES_IMAGEM = {'.jpg', '.jpeg', '.png'}

PENDENCIA_SEM_CAPA = (
    'A capa só foi fotografada no plástico com a etiqueta de preço: essa foto vai para o site. '
    'Refotografar sem plástico se quiser.'
)
PENDENCIA_SEM_PRECO = 'Sem etiqueta de preço nas fotos: definir o preço antes de aprovar.'
PENDENCIA_INCERTA = 'Identificação incerta: conferir artista, álbum e edição.'


class ErroLote(Exception):
    pass


def lote_padrao() -> str:
    return pd.Timestamp.now(tz='America/Sao_Paulo').strftime('%Y-%m-%d')


def pasta_entrada(config: Config, pasta_override: Path | str | None = None) -> Path:
    caminho = Path(pasta_override or config.cadastro_pasta_local or '')
    if not str(caminho).strip() or not caminho.exists():
        raise ErroLote('Pasta de entrada local (CADASTRO_PASTA_LOCAL) não configurada ou inexistente.')
    return caminho


def pasta_do_lote(lote: str, base_trabalho: Path | str | None = None) -> Path:
    raiz = Path(base_trabalho) if base_trabalho else Path(RAIZ_PROJETO) / 'dados' / 'cadastro_ia'
    return raiz / lote


# ----------------------------------------------------------------------------
# Leitura de EXIF / horário e comando `folhas`
# ----------------------------------------------------------------------------
def extrair_data_foto(caminho: Path) -> datetime:
    try:
        with Image.open(caminho) as im:
            exif = im.getexif()
            candidatos = []
            if exif:
                if 36867 in exif:
                    candidatos.append(exif[36867])
                try:
                    ifd = exif.get_ifd(0x8769)
                    if ifd and 36867 in ifd:
                        candidatos.append(ifd[36867])
                    if ifd and 36868 in ifd:
                        candidatos.append(ifd[36868])
                except Exception:
                    pass
                if 306 in exif:
                    candidatos.append(exif[306])
            for texto in candidatos:
                s = str(texto).strip().rstrip('\x00')
                if len(s) >= 19:
                    try:
                        return datetime.strptime(s[:19], '%Y:%m:%d %H:%M:%S')
                    except ValueError:
                        pass
    except Exception:
        pass
    m = re.search(r'(\d{4})[-_]?(\d{2})[-_]?(\d{2})[-_ ]+(\d{2})(\d{2})(\d{2})', caminho.stem)
    if m:
        try:
            return datetime(*(int(g) for g in m.groups()))
        except ValueError:
            pass
    m_hora = re.search(r'(?<!\d)(\d{2})(\d{2})(\d{2})(?!\d)', caminho.stem)
    if m_hora:
        try:
            h, mi, s = (int(g) for g in m_hora.groups())
            if 0 <= h < 24 and 0 <= mi < 60 and 0 <= s < 60:
                base = datetime.fromtimestamp(caminho.stat().st_mtime)
                return base.replace(hour=h, minute=mi, second=s, microsecond=0)
        except (ValueError, OSError):
            pass
    try:
        return datetime.fromtimestamp(caminho.stat().st_mtime)
    except OSError:
        return datetime(2026, 1, 1, 0, 0, 0)


def fotos_cadastradas(planilha: PlanilhaGoogle) -> set[str]:
    linhas = ler(planilha, 'cadastro_fotos')
    if not linhas:
        return set()
    cab = linhas[0]
    idx = cab.index('observacao') if 'observacao' in cab else 5
    return {str(r[idx]).strip() for r in linhas[1:] if len(r) > idx and str(r[idx]).strip()}


def listar_fotos_novas(pasta_local: Path, planilha: PlanilhaGoogle) -> list[tuple[Path, datetime]]:
    ja_cadastradas = fotos_cadastradas(planilha)
    itens: list[tuple[Path, datetime]] = []
    for arq in pasta_local.iterdir():
        if not arq.is_file() or arq.suffix.lower() not in EXTENSOES_IMAGEM:
            continue
        if arq.name in ja_cadastradas:
            continue
        if PADRAO_ID_ARQUIVO.match(arq.name):
            continue
        itens.append((arq, extrair_data_foto(arq)))
    itens.sort(key=lambda par: (par[1], par[0].name))
    return itens


def gerar_folhas(
    pasta_local: Path,
    planilha: PlanilhaGoogle,
    lote: str | None = None,
    base_trabalho: Path | str | None = None,
) -> dict[str, Any]:
    lote = lote or lote_padrao()
    novas = listar_fotos_novas(pasta_local, planilha)
    destino_lote = pasta_do_lote(lote, base_trabalho)
    pasta_folhas = destino_lote / 'folhas'
    pasta_folhas.mkdir(parents=True, exist_ok=True)

    linhas_txt = []
    for idx, (arq, dt) in enumerate(novas, 1):
        linhas_txt.append(f'{idx:02d}\t{dt.strftime("%H:%M:%S")}\t{arq.name}')
    arq_txt = destino_lote / 'fotos.txt'
    arq_txt.write_text('\n'.join(linhas_txt) + ('\n' if linhas_txt else ''), encoding='utf-8')

    cols, rows = 4, 3
    por_folha = cols * rows
    w_folha = 1600
    w_cel = w_folha // cols
    h_cel = 340
    h_folha = h_cel * rows

    arquivos_folhas: list[Path] = []
    for f_idx, inicio in enumerate(range(0, len(novas), por_folha), 1):
        bloco = novas[inicio:inicio + por_folha]
        folha = Image.new('RGB', (w_folha, h_folha), (248, 248, 248))
        draw = ImageDraw.Draw(folha)
        for pos, (arq, dt) in enumerate(bloco):
            num_global = inicio + pos + 1
            col = pos % cols
            row = pos // cols
            x0, y0 = col * w_cel, row * h_cel
            x1, y1 = x0 + w_cel, y0 + h_cel

            draw.rectangle([x0, y0, x1 - 1, y1 - 1], outline=(210, 210, 210), width=1)
            if num_global > 1:
                dt_ant = novas[num_global - 2][1]
                if (dt - dt_ant).total_seconds() > 60:
                    # Linha mais grossa antes da miniatura quando houve intervalo > 60s
                    draw.line([(x0 + 3, y0 + 2), (x0 + 3, y1 - 2)], fill=(210, 50, 30), width=6)

            try:
                with Image.open(arq) as im_orig:
                    im = ImageOps.exif_transpose(im_orig).convert('RGB')
                im.thumbnail((w_cel - 20, h_cel - 44), Image.LANCZOS)
                px = x0 + (w_cel - im.width) // 2
                py = y0 + 34 + (h_cel - 40 - im.height) // 2
                folha.paste(im, (px, py))
            except Exception:
                draw.text((x0 + 16, y0 + h_cel // 2), 'erro ao abrir', fill=(180, 0, 0))

            rotulo = f'{num_global:02d} · {dt.strftime("%H:%M:%S")}'
            draw.rectangle([x0 + 8, y0 + 6, x1 - 8, y0 + 30], fill=(30, 30, 30))
            draw.text((x0 + 14, y0 + 10), rotulo, fill=(255, 255, 255))

        caminho_folha = pasta_folhas / f'folha_{f_idx:02d}.jpg'
        folha.save(caminho_folha, 'JPEG', quality=88)
        arquivos_folhas.append(caminho_folha)

    return {
        'lote': lote,
        'fotos': len(novas),
        'folhas': len(arquivos_folhas),
        'fotos_txt': arq_txt,
        'arquivos_folhas': arquivos_folhas,
    }


# ----------------------------------------------------------------------------
# Comando `recorte`
# ----------------------------------------------------------------------------
def recortar_foto(
    arquivo: str,
    esq: float,
    topo: float,
    dir_: float,
    base: float,
    pasta_local: Path,
    lote: str | None = None,
    base_trabalho: Path | str | None = None,
) -> Path:
    if not (0 <= esq < dir_ <= 1 and 0 <= topo < base <= 1):
        raise ErroLote('Frações de recorte devem estar entre 0 e 1 (esq < dir e topo < base).')
    lote = lote or lote_padrao()
    caminho = Path(arquivo)
    if not caminho.is_file():
        caminho = pasta_local / arquivo
    if not caminho.is_file():
        raise ErroLote(f'Arquivo não encontrado: {arquivo}')

    with Image.open(caminho) as im_orig:
        im = ImageOps.exif_transpose(im_orig).convert('RGB')
    w, h = im.size
    caixa = (
        int(round(esq * w)),
        int(round(topo * h)),
        max(int(round(esq * w)) + 1, int(round(dir_ * w))),
        max(int(round(topo * h)) + 1, int(round(base * h))),
    )
    recorte = im.crop(caixa)
    maior = max(recorte.size)
    if maior > 1600:
        fator = 1600 / maior
        recorte = recorte.resize(
            (max(1, int(round(recorte.width * fator))), max(1, int(round(recorte.height * fator)))),
            Image.LANCZOS,
        )

    pasta_zoom = pasta_do_lote(lote, base_trabalho) / 'zoom'
    pasta_zoom.mkdir(parents=True, exist_ok=True)
    n = 1
    while True:
        saida = pasta_zoom / f'{caminho.stem}_{n}.jpg'
        if not saida.exists():
            break
        n += 1
    recorte.save(saida, 'JPEG', quality=90)
    return saida


# ----------------------------------------------------------------------------
# Detecção de cantos (capa/encartes) e círculo (disco)
# ----------------------------------------------------------------------------
def _linha_media(ls: list[tuple[int, int, int, int]]) -> np.ndarray:
    return np.vstack([[l[0], l[1]] for l in ls] + [[l[2], l[3]] for l in ls]).astype(float)


def _fit_reta(pts: np.ndarray, vertical: bool) -> tuple[float, float]:
    if vertical:
        a, b = np.polyfit(pts[:, 1], pts[:, 0], 1)
    else:
        a, b = np.polyfit(pts[:, 0], pts[:, 1], 1)
    return float(a), float(b)


def _intersecao(v: tuple[float, float], hh: tuple[float, float]) -> list[float]:
    av, bv = v
    ah, bh = hh
    denom = 1.0 - ah * av
    if abs(denom) < 1e-9:
        return [-1.0, -1.0]
    y = (ah * bv + bh) / denom
    x = av * y + bv
    return [float(x), float(y)]


def ordenar_cantos(pts: np.ndarray) -> np.ndarray:
    """Ordena 4 pontos 2D em: sup. esq., sup. dir., inf. dir., inf. esq."""
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    sup_esq = pts[np.argmin(s)]
    inf_dir = pts[np.argmax(s)]
    sup_dir = pts[np.argmin(d)]
    inf_esq = pts[np.argmax(d)]
    return np.array([sup_esq, sup_dir, inf_dir, inf_esq], dtype=float)


def aplicar_margem_cantos(box_ordenado: np.ndarray, margem_pct: float, w_max: int, h_max: int) -> list[list[int]]:
    """Expande 4 cantos para fora a partir do centro por margem_pct (ex.: 0.01 = 1%)."""
    centro = box_ordenado.mean(axis=0)
    exp = box_ordenado + (box_ordenado - centro) * margem_pct
    exp[:, 0] = np.clip(exp[:, 0], 0, w_max)
    exp[:, 1] = np.clip(exp[:, 1], 0, h_max)
    return [[int(round(x)), int(round(y))] for x, y in exp]


def detectar_cantos_fundo_branco_capa(rgb: np.ndarray, papel: str = 'capa') -> list | None:
    """Detecção por fundo branco para capas/encartes (D-091)."""
    H, W = rgb.shape[:2]
    if W <= 0 or H <= 0:
        return None
    h_500 = max(1, int(round(500.0 * H / W)))
    sm = cv2.resize(rgb, (500, h_500))
    cinza = cv2.cvtColor(sm, cv2.COLOR_RGB2GRAY)

    cantos_bg = np.concatenate([cinza[:15, :15].ravel(), cinza[:15, -15:].ravel(), cinza[-15:, :15].ravel(), cinza[-15:, -15:].ravel()])
    bg_mean = float(np.mean(cantos_bg))
    if bg_mean < 160:
        return None

    limiares = [235]
    if bg_mean < 235:
        limiares.extend([int(bg_mean - 10), int(bg_mean - 15), int(bg_mean - 20), int(bg_mean - 25), 200, 190, 180, 170, 160])

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
    p_norm = papel.strip().lower()
    papel_duplo = any(k in p_norm for k in ['encarte aberto', 'capa interna'])

    for t in limiares:
        if t <= 50:
            continue
        mask = (cinza < t).astype(np.uint8) * 255
        mask_c = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        cnts, _ = cv2.findContours(mask_c, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not cnts:
            continue
        c = max(cnts, key=cv2.contourArea)
        area = cv2.contourArea(c)
        frac = area / (500 * h_500)
        if frac > 0.88 or frac < 0.08:
            continue
        x, y, bw, bh = cv2.boundingRect(c)
        if x <= 4 or y <= 4 or (x + bw) >= 496 or (y + bh) >= h_500 - 4:
            continue
        rect = cv2.minAreaRect(c)
        rw, rh = rect[1]
        if rw <= 0 or rh <= 0:
            continue
        prop = max(rw, rh) / min(rw, rh)

        eh_duplo = False
        if papel_duplo:
            if not (0.80 <= prop <= 2.3):
                continue
            if prop >= 1.6:
                eh_duplo = True
        else:
            limite_prop = 1.6 if 'encarte' in p_norm else 1.15
            if not (0.85 <= prop <= limite_prop):
                continue

        box = cv2.boxPoints(rect)
        ord_box = ordenar_cantos(box)
        final_box = aplicar_margem_cantos(ord_box, 0.01, 500, h_500)
        res = final_box + [2] if eh_duplo else final_box
        if cantos_validos_na_imagem(res, W, H):
            return res
    return None


def detectar_cantos_fundo_branco_disco(rgb: np.ndarray) -> list | None:
    """Detecção de disco em quadrado com 2% de folga sobre fundo claro (D-091)."""
    H, W = rgb.shape[:2]
    if W <= 0 or H <= 0:
        return None
    h_500 = max(1, int(round(500.0 * H / W)))
    sm = cv2.resize(rgb, (500, h_500))
    cinza = cv2.cvtColor(sm, cv2.COLOR_RGB2GRAY)

    cantos_bg = np.concatenate([cinza[:15, :15].ravel(), cinza[:15, -15:].ravel(), cinza[-15:, :15].ravel(), cinza[-15:, -15:].ravel()])
    if np.mean(cantos_bg) < 160:
        return None

    menor_lado = min(500, h_500)
    is_portrait = (h_500 > 550 or H > W * 1.1)
    diam_min = 0.50 * menor_lado if is_portrait else 0.30 * menor_lado

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    for t in [110, 125, 95, 80, 140, 160]:
        mask = (cinza < t).astype(np.uint8) * 255
        mask_c = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        cnts, _ = cv2.findContours(mask_c, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not cnts:
            continue
        c = max(cnts, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(c)
        diam = max(w, h)
        if diam < diam_min:
            continue
        if min(w, h) / max(w, h) < 0.75:
            continue
        cx = x + w / 2.0
        cy = y + h / 2.0
        lado = max(w, h) * 1.02
        x0 = max(0, int(round(cx - lado / 2.0)))
        y0 = max(0, int(round(cy - lado / 2.0)))
        x1 = min(500, int(round(cx + lado / 2.0)))
        y1 = min(h_500, int(round(cy + lado / 2.0)))
        can = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
        if cantos_validos_na_imagem(can, W, H):
            return can
    return None


def _hough_cantos_capa(rgb: np.ndarray, papel: str = 'capa') -> list | None:
    H, W = rgb.shape[:2]
    if W <= 0 or H <= 0:
        return None
    s = 1000.0 / W
    sm = cv2.resize(rgb, (1000, max(1, int(H * s))))
    h, w = sm.shape[:2]
    g = cv2.GaussianBlur(cv2.cvtColor(sm, cv2.COLOR_RGB2GRAY), (3, 3), 0)
    e = cv2.Canny(g, 10, 30)
    L = cv2.HoughLinesP(e, 1, np.pi / 720, 60, minLineLength=int(0.12 * h), maxLineGap=15)
    if L is None:
        return None
    L = L.reshape(-1, 4)
    vs, hs = [], []
    for x1, y1, x2, y2 in L:
        dx, dy = x2 - x1, y2 - y1
        ang = abs(np.degrees(np.arctan2(dy, dx)))
        if 80 < ang < 100:
            vs.append((int(x1), int(y1), int(x2), int(y2)))
        elif ang < 10 or ang > 170:
            hs.append((int(x1), int(y1), int(x2), int(y2)))

    mx = lambda l: (l[0] + l[2]) / 2.0
    my = lambda l: (l[1] + l[3]) / 2.0

    def comp(sel, vert: bool) -> float:
        return float(sum(abs(l[3] - l[1]) if vert else abs(l[2] - l[0]) for l in sel))

    def melhor(lines, key, pick: str, vert: bool, minimo: float):
        ls = sorted(lines, key=key, reverse=pick.startswith('max'))
        ls = [l for l in ls if (0.04 * w < key(l) < 0.96 * w if vert else 0.02 * h < key(l) < 0.98 * h)]
        for l in ls:
            k = key(l)
            sel = [m for m in ls if abs(key(m) - k) < 6]
            if comp(sel, vert) >= minimo:
                return sel
        return None

    left = melhor(vs, mx, 'min', True, 0.35 * h)
    right = melhor(vs, mx, 'max', True, 0.35 * h)
    top = melhor(hs, my, 'min', False, 0.35 * h)
    bot = melhor(hs, my, 'max', False, 0.35 * h)
    if not all([left, right, top, bot]):
        return None

    V = [_fit_reta(_linha_media(left), True), _fit_reta(_linha_media(right), True)]
    Hh = [_fit_reta(_linha_media(top), False), _fit_reta(_linha_media(bot), False)]
    q = [_intersecao(V[0], Hh[0]), _intersecao(V[1], Hh[0]), _intersecao(V[1], Hh[1]), _intersecao(V[0], Hh[1])]
    can = [[int(round(x / 2.0)), int(round(y / 2.0))] for x, y in q]

    if not cantos_validos_na_imagem(can, W, H):
        return None

    w_q = ((can[1][0] - can[0][0]) + (can[2][0] - can[3][0])) / 2.0
    h_q = ((can[3][1] - can[0][1]) + (can[2][1] - can[1][1])) / 2.0
    if w_q <= 0 or h_q <= 0:
        return None
    prop = (can[1][0] - can[0][0]) / max(can[3][1] - can[0][1], 1)

    p_norm = papel.strip().lower()
    if p_norm in ('encarte aberto', 'capa interna', 'capa interna verso'):
        if 1.8 <= prop <= 2.2:
            return can + [2]
        if 0.9 <= prop <= 1.12:
            return can
        return None
    if not (0.85 <= prop <= 1.15):
        return None
    return can


def detectar_cantos_capa(rgb: np.ndarray, papel: str = 'capa') -> list | None:
    # D-091: em fotos em pé (H > W) ou fundo claro, detecção por fundo branco usada primeiro
    H, W = rgb.shape[:2]
    if H > W:
        can_fb = detectar_cantos_fundo_branco_capa(rgb, papel)
        if can_fb is not None:
            return can_fb
        return _hough_cantos_capa(rgb, papel)
    else:
        can_h = _hough_cantos_capa(rgb, papel)
        if can_h is not None:
            return can_h
        return detectar_cantos_fundo_branco_capa(rgb, papel)


def _hough_cantos_disco(rgb: np.ndarray) -> list | None:
    H, W = rgb.shape[:2]
    if W <= 0 or H <= 0:
        return None
    escala = 800.0 / W
    menor = cv2.resize(rgb, (800, max(1, int(H * escala))))
    cinza = cv2.medianBlur(cv2.cvtColor(menor, cv2.COLOR_RGB2GRAY), 5)
    cs = cv2.HoughCircles(
        cinza,
        cv2.HOUGH_GRADIENT,
        dp=1.5,
        minDist=400,
        param1=100,
        param2=40,
        minRadius=int(0.10 * 800),
        maxRadius=int(0.22 * 800),
    )
    if cs is None:
        return None
    cx, cy, r = cs[0][0] * (500.0 / 800.0)
    diam_escala = 2 * r
    h_500 = 500.0 * H / W
    menor_lado = min(500.0, h_500)
    if H > W and diam_escala < 0.50 * menor_lado:
        return None

    d = r * 1.04
    x0 = max(0, int(round(cx - d)))
    y0 = max(0, int(round(cy - d)))
    x1 = min(int(500), int(round(cx + d)))
    y1 = min(int(h_500), int(round(cy + d)))
    can = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
    return can if cantos_validos_na_imagem(can, W, H) else None


def detectar_cantos_disco(rgb: np.ndarray) -> list | None:
    # D-091: em fotos em pé (H > W), detecção por fundo branco usada primeiro
    H, W = rgb.shape[:2]
    if H > W:
        can_fb = detectar_cantos_fundo_branco_disco(rgb)
        if can_fb is not None:
            return can_fb
        return _hough_cantos_disco(rgb)
    else:
        can_h = _hough_cantos_disco(rgb)
        if can_h is not None:
            return can_h
        return detectar_cantos_fundo_branco_disco(rgb)


def cantos_validos_na_imagem(pontos: Any, w: int, h: int) -> bool:
    if not isinstance(pontos, list) or not (4 <= len(pontos) <= 6):
        return False
    proporcao = pontos[4] if len(pontos) > 4 else 1
    if proporcao not in (1, 2):
        return False
    giro = pontos[5] if len(pontos) > 5 else ''
    if giro not in ('', 'cw', 'ccw'):
        return False
    try:
        src = np.asarray(pontos[:4], dtype=np.float32) * (w / 500.0)
    except (ValueError, TypeError):
        return False
    if src.shape != (4, 2) or not np.isfinite(src).all():
        return False
    if (src < 0).any() or (src[:, 0] > w).any() or (src[:, 1] > h).any():
        return False
    if not cv2.isContourConvex(src.astype(np.int32)) or abs(cv2.contourArea(src)) < 1:
        return False
    return True


def calcular_cantos_foto(caminho: Path, papel: str, foto_cfg: dict[str, Any]) -> tuple[list | None, bool]:
    """Devolve (cantos, falhou_automatico)."""
    p = papel.strip().lower()
    if p == 'etiqueta' or p == 'descartar':
        return None, False
    if 'cantos' in foto_cfg and foto_cfg['cantos'] is not None:
        return foto_cfg['cantos'], False
    if str(foto_cfg.get('recorte', '')).strip().lower() == 'inteira':
        return None, False
    if not caminho.is_file():
        return None, True
    with Image.open(caminho) as im_orig:
        rgb = np.array(ImageOps.exif_transpose(im_orig).convert('RGB'))
    if p.startswith('disco'):
        can = detectar_cantos_disco(rgb)
    else:
        can = detectar_cantos_capa(rgb, p)
    return can, can is None


# ----------------------------------------------------------------------------
# Derivação de linhas e validação (conferir / gravar)
# ----------------------------------------------------------------------------
def _contem_travessao(obj: Any) -> bool:
    if isinstance(obj, str):
        return '—' in obj
    if isinstance(obj, dict):
        return any(_contem_travessao(v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return any(_contem_travessao(v) for v in obj)
    return False


def _artista_normalizado(artista: str) -> str:
    art = str(artista or '').strip()
    if art.lower().startswith('vários') or art.lower().startswith('varios') or art.lower() == 'vários artistas':
        return 'Vários'
    return art


def _proximo_numero_lote(lote: str, rascunhos_existentes: list[list[str]]) -> int:
    padrao = re.compile(rf'^{re.escape(lote)}-(\d+)$')
    maior = 0
    for r in rascunhos_existentes[1:]:
        if not r:
            continue
        m = padrao.match(str(r[0]).strip())
        if m:
            maior = max(maior, int(m.group(1)))
    return maior + 1


def _produtos_repetidos(titulo: str, linhas_produtos: list[list[str]]) -> list[dict[str, Any]]:
    if len(linhas_produtos) < 2:
        return []
    cab = linhas_produtos[0]
    alvo = identidade_titulo(titulo)
    if not alvo[1]:
        return []
    achados = []
    for r in linhas_produtos[1:]:
        d = dict(zip(cab, r))
        est = numero(d.get('estoque'))
        if not est or est <= 0:
            continue
        if identidade_titulo(d.get('nome', '')) == alvo:
            achados.append({'nome': d.get('nome', ''), 'estoque': int(est), 'url': str(d.get('url', '')).strip('/')})
    return achados


def _rascunhos_repetidos(titulo: str, linhas_rasc: list[list[str]]) -> list[dict[str, Any]]:
    if len(linhas_rasc) < 2:
        return []
    cab = linhas_rasc[0]
    alvo = identidade_titulo(titulo)
    if not alvo[1]:
        return []
    achados = []
    for r in linhas_rasc[1:]:
        d = dict(zip(cab, r))
        status = str(d.get('status', '')).strip().lower()
        if status.startswith('descartado'):
            continue
        if identidade_titulo(d.get('titulo', '')) == alvo:
            achados.append({'id': d.get('id', ''), 'titulo': d.get('titulo', ''), 'status': d.get('status', '')})
    return achados


def derivar_lote(
    dados_lote: dict[str, Any],
    planilha: PlanilhaGoogle | None = None,
    pasta_local: Path | None = None,
    usar_nomes_novos: bool = True,
    detectar_recortes: bool = True,
    agora: datetime | None = None,
) -> dict[str, Any]:
    lote = str(dados_lote.get('lote') or '').strip()
    discos_brutos = dados_lote.get('discos')
    discos = discos_brutos if isinstance(discos_brutos, list) else []
    linhas_rasc = ler(planilha, ABA) if planilha else []
    linhas_fotos = ler(planilha, 'cadastro_fotos') if planilha else []
    linhas_produtos = ler(planilha, 'produtos') if planilha else []

    n = _proximo_numero_lote(lote, linhas_rasc) - 1
    agora_str = (agora or pd.Timestamp.now(tz='America/Sao_Paulo')).strftime('%Y-%m-%d %H:%M')

    rascunhos_dicts: list[dict[str, str]] = []
    rascunhos_rows: list[list[str]] = []
    fotos_rows: list[list[str]] = []
    renomeacoes: list[dict[str, Any]] = []
    pulados: list[dict[str, str]] = []
    detalhes_discos: list[dict[str, Any]] = []

    for o in discos:
        if not isinstance(o, dict):
            continue
        acao = str(o.get('acao') or '').strip()
        if acao == 'pular':
            pulados.append({'disco': str(o.get('disco', '')), 'motivo': str(o.get('motivo', '')).strip()})
            continue
        if acao != 'cadastrar':
            continue

        n += 1
        id_ = f'{lote}-{n:02d}'
        art = _artista_normalizado(o.get('artista', ''))
        alb = str(o.get('album', '')).strip()
        ano = o.get('ano')
        anos = f' ({ano})' if ano else ''
        sufixo = '(Vinil Usado, Duplo)' if o.get('duplo') else '(Vinil Usado)'
        titulo = f'LP {art} - {alb}{anos} - {sufixo}'

        fotos_brutas = o.get('fotos')
        todas_fotos = [dict(f) for f in (fotos_brutas if isinstance(fotos_brutas, list) else []) if isinstance(f, dict)]
        fs = [dict(f) for f in todas_fotos if f.get('papel') != 'descartar']
        descartadas = [dict(f) for f in todas_fotos if f.get('papel') == 'descartar']

        pend = [str(o.get('pendencias', '')).strip()] if str(o.get('pendencias', '')).strip() else []

        if not any(f.get('papel') == 'capa' for f in fs):
            et = [f for f in fs if f.get('papel') == 'etiqueta']
            if et:
                et[0]['papel'] = 'capa'
                if PENDENCIA_SEM_CAPA not in pend:
                    pend.append(PENDENCIA_SEM_CAPA)

        preco_val = o.get('preco_etiqueta')
        tem_preco = preco_val not in (None, '', 0) and not isinstance(preco_val, bool)
        if not tem_preco and PENDENCIA_SEM_PRECO not in pend:
            pend.append(PENDENCIA_SEM_PRECO)

        repetidos_loja = _produtos_repetidos(titulo, linhas_produtos)
        for rep in repetidos_loja:
            msg_rep = (
                f'JÁ EXISTE NA LOJA COM ESTOQUE {rep["estoque"]}: '
                f'lojamonstro.com.br/produtos/{rep["url"]}/ . '
                'Confirmar se é outro exemplar; se for o mesmo disco, descartar este rascunho.'
            )
            if msg_rep not in pend:
                pend.append(msg_rep)

        if str(o.get('confianca', '')).strip().lower() == 'baixa' and PENDENCIA_INCERTA not in pend:
            pend.append(PENDENCIA_INCERTA)

        etiquetas = [f for f in fs if f.get('papel') == 'etiqueta']
        site = [f for f in fs if f.get('papel') != 'etiqueta']
        site.sort(key=lambda f: (ORDEM_PAPEIS.get(f.get('papel', ''), 7.5), str(f.get('arquivo', ''))))

        for idx_et, f in enumerate(etiquetas, 1):
            arq_orig = str(f.get('arquivo', ''))
            suf = '' if idx_et == 1 else f' {idx_et}'
            nome_novo = f'{id_} 00 etiqueta{suf}.jpg'
            obs = nome_novo if usar_nomes_novos else arq_orig
            fotos_rows.append([id_, '0', 'etiqueta', '', '', obs])
            renomeacoes.append({'disco': o.get('disco', ''), 'id_disco': id_, 'antigo': arq_orig, 'novo': nome_novo, 'feito': False})

        nomes_site = []
        fotos_site_info = []
        for k, f in enumerate(site, 1):
            p = str(f.get('papel', ''))
            arq_orig = str(f.get('arquivo', ''))
            nome_curto = f'{k:02d} {p}.jpg'
            nome_novo = f'{id_} {nome_curto}'
            nomes_site.append(nome_curto)

            can = None
            falhou_auto = False
            if detectar_recortes and pasta_local is not None:
                can, falhou_auto = calcular_cantos_foto(pasta_local / arq_orig, p, f)
            elif 'cantos' in f and f['cantos'] is not None:
                can = f['cantos']

            obs = nome_novo if usar_nomes_novos else arq_orig
            fotos_rows.append([id_, str(k), p, '', json.dumps(can) if can else '', obs])
            renomeacoes.append({'disco': o.get('disco', ''), 'id_disco': id_, 'antigo': arq_orig, 'novo': nome_novo, 'feito': False})
            fotos_site_info.append({
                'ordem': k,
                'papel': p,
                'arquivo': arq_orig,
                'nome_novo': nome_novo,
                'cantos': can,
                'falhou_recorte': falhou_auto,
            })

        for idx_d, f in enumerate(descartadas, 1):
            arq_orig = str(f.get('arquivo', ''))
            nome_novo = f'{id_} descartada {idx_d}.jpg'
            renomeacoes.append({'disco': o.get('disco', ''), 'id_disco': id_, 'antigo': arq_orig, 'novo': nome_novo, 'feito': False})

        if o.get('duplo'):
            peso = '0,8'
        elif o.get('gatefold') or any(str(f.get('papel', '')).startswith(('encarte', 'capa interna')) for f in site):
            peso = '0,55'
        else:
            peso = '0,5'

        cat = f'LP, Usado, {str(o.get("genero", "")).strip()}, Novidades'
        partes_ficha = [
            str(x).strip()
            for x in [o.get('gravadora', ''), o.get('catalogo', ''), o.get('pais', ''), str(ano) if ano else '']
            if str(x or '').strip()
        ]
        ficha = (', '.join(partes_ficha) + '.') if partes_ficha else ''
        if o.get('ano_prensagem') and str(o.get('ano_prensagem')).strip() != str(ano or '').strip():
            ficha += f' Prensagem {str(o["ano_prensagem"]).strip()}.'
        if o.get('duplo'):
            ficha += ' Disco duplo.'
        if o.get('gatefold'):
            ficha += ' Capa dupla (gatefold).'
        if o.get('acompanha'):
            itens_ac = [str(x).strip() for x in o['acompanha'] if str(x).strip()]
            if itens_ac:
                ficha += ' Acompanha: ' + '; '.join(itens_ac) + '.'
        if o.get('marcas') and str(o.get('marcas')).strip():
            ficha += ' Marcas: ' + str(o['marcas']).strip().rstrip('.') + '.'
        if o.get('bolinha') and str(o.get('bolinha')).strip():
            ficha += f' Bolinha {str(o["bolinha"]).strip()} na etiqueta.'
        ficha = ficha.strip()

        desc = str(o.get('descricao', '')).strip()
        primeira = re.split(r'(?<=\.)\s', desc.split('\n')[0])[0] if desc else ''
        seo_t = f'LP {art} {alb}{anos} - Vinil Usado' + (' Duplo' if o.get('duplo') else '')
        seo_d = (primeira if len(primeira) <= 120 else primeira[:117].rsplit(' ', 1)[0] + '…') + ' Vinil usado, exemplar único.'
        preco_str = str(preco_val) if tem_preco else ''

        linha_dict = {col: '' for col in COLUNAS}
        linha_dict.update({
            'id': id_,
            'lote': lote,
            'pasta': f'{n:02d} {art} - {alb}{anos}',
            'status': 'rascunho',
            'titulo': titulo,
            'marca': art,
            'categorias': cat,
            'ficha': ficha,
            'descricao': desc,
            'capa': str(o.get('capa', '')).strip(),
            'vinil': str(o.get('vinil', '')).strip(),
            'preco': preco_str,
            'peso_kg': peso,
            'altura_cm': '2,5',
            'largura_cm': '32',
            'comprimento_cm': '32',
            'pendencias': ' | '.join(pend),
            'fotos': ' | '.join(nomes_site),
            'seo_titulo': seo_t,
            'seo_descricao': seo_d,
            'tags': str(o.get('tags', '')).strip(),
            'atualizado_em': agora_str,
            'preco_origem': 'etiqueta' if preco_str else '',
            'estoque': '1',
        })
        rascunhos_dicts.append(linha_dict)
        rascunhos_rows.append([linha_dict.get(c, '') for c in COLUNAS])
        detalhes_discos.append({
            'disco': str(o.get('disco', '')),
            'id': id_,
            'titulo': titulo,
            'categorias': cat,
            'preco': preco_str,
            'capa': linha_dict['capa'],
            'vinil': linha_dict['vinil'],
            'n_fotos_site': len(site),
            'pendencias': linha_dict['pendencias'],
            'fotos_site': fotos_site_info,
            'repetidos_loja': repetidos_loja,
            'repetidos_painel': _rascunhos_repetidos(titulo, linhas_rasc),
        })

    return {
        'lote': lote,
        'rascunhos_dicts': rascunhos_dicts,
        'rasc': rascunhos_rows,
        'fotos': fotos_rows,
        'renomeacoes': renomeacoes,
        'pulados': pulados,
        'detalhes_discos': detalhes_discos,
    }


def validar_lote(
    caminho_json: Path | str,
    pasta_local: Path,
    planilha: PlanilhaGoogle,
    gerar_previas: bool = True,
    base_trabalho: Path | str | None = None,
) -> dict[str, Any]:
    caminho_json = Path(caminho_json)
    erros: list[tuple[str, str]] = []
    avisos: list[tuple[str, str]] = []

    try:
        dados = json.loads(caminho_json.read_text(encoding='utf-8'))
    except Exception:
        erros.append(('arquivo', 'JSON inválido.'))
        dados = {}

    if not isinstance(dados, dict):
        erros.append(('arquivo', 'Raiz do JSON deve ser um objeto.'))
        dados = {}

    lote = str(dados.get('lote') or '').strip()
    if not lote:
        erros.append(('arquivo', 'Campo lote ausente ou vazio.'))

    discos = dados.get('discos')
    if not isinstance(discos, list):
        erros.append(('arquivo', 'Lista discos ausente ou inválida.'))
        discos = []

    ja_cadastradas = fotos_cadastradas(planilha)
    codigos_vistos: set[str] = set()
    fotos_vistas: dict[str, str] = {}

    for idx, o in enumerate(discos, 1):
        if not isinstance(o, dict):
            erros.append((f'item_{idx}', 'Entrada de disco inválida.'))
            continue
        cod = str(o.get('disco') or '').strip()
        rotulo_d = cod or f'item_{idx}'
        if not cod:
            erros.append((rotulo_d, 'Código disco ausente.'))
        elif cod in codigos_vistos:
            erros.append((rotulo_d, f'Código disco repetido: {cod}.'))
        else:
            codigos_vistos.add(cod)

        if _contem_travessao(o):
            erros.append((rotulo_d, 'Travessão (—) encontrado no texto do disco.'))

        acao = str(o.get('acao') or '').strip()
        if acao not in ('cadastrar', 'pular'):
            erros.append((rotulo_d, f'Ação inválida: {acao!r} (use cadastrar ou pular).'))
        elif acao == 'pular' and not str(o.get('motivo') or '').strip():
            erros.append((rotulo_d, 'Disco com ação pular sem motivo.'))

        fs = o.get('fotos')
        if not isinstance(fs, list):
            erros.append((rotulo_d, 'Lista fotos inválida.'))
            fs = []

        papeis_uteis = []
        for f in fs:
            if not isinstance(f, dict):
                erros.append((rotulo_d, 'Item de foto inválido.'))
                continue
            arq = str(f.get('arquivo') or '').strip()
            papel = str(f.get('papel') or '').strip()
            if not arq:
                erros.append((rotulo_d, 'Foto sem nome de arquivo.'))
                continue
            if arq in fotos_vistas and fotos_vistas[arq] != rotulo_d:
                erros.append((rotulo_d, f'Foto usada em dois discos ({fotos_vistas[arq]} e {rotulo_d}): {arq}.'))
            else:
                fotos_vistas[arq] = rotulo_d

            if arq in ja_cadastradas:
                erros.append((rotulo_d, f'Foto já está em cadastro_fotos: {arq}.'))

            caminho_arq = pasta_local / arq
            if not caminho_arq.is_file():
                erros.append((rotulo_d, f'Arquivo inexistente na pasta: {arq}.'))

            if papel not in PAPEIS_VALIDOS:
                erros.append((rotulo_d, f'Papel fora da lista permitida ({papel!r}) em {arq}.'))
            elif papel != 'descartar':
                papeis_uteis.append(papel)

            if 'cantos' in f and f['cantos'] is not None:
                if caminho_arq.is_file():
                    try:
                        with Image.open(caminho_arq) as im_orig:
                            im_g = ImageOps.exif_transpose(im_orig)
                            w_im, h_im = im_g.size
                    except Exception:
                        w_im, h_im = 500, 500
                else:
                    w_im, h_im = 500, 500
                if not cantos_validos_na_imagem(f['cantos'], w_im, h_im):
                    erros.append((rotulo_d, f'Cantos manuais inválidos (não formam quadrilátero convexo na imagem) em {arq}.'))

        if acao != 'cadastrar':
            continue

        if not any(p in ('capa', 'contracapa', 'etiqueta') for p in papeis_uteis):
            erros.append((rotulo_d, 'Disco a cadastrar sem nenhuma foto de capa, contracapa ou etiqueta.'))

        if 'prata' in str(o.get('bolinha') or '').lower():
            erros.append((rotulo_d, 'Bolinha prata (disco consignado) não pode ter ação cadastrar.'))

        genero = str(o.get('genero') or '').strip()
        if genero not in GENEROS_ACEITOS:
            erros.append((rotulo_d, f'Gênero fora da lista do manual: {genero!r}.'))

        capa = str(o.get('capa') or '').strip()
        if capa not in NOTAS_GOLDMINE:
            erros.append((rotulo_d, f'Nota de capa fora de M NM VG+ VG G+ G F: {capa!r}.'))

        vinil = str(o.get('vinil') or '').strip()
        if vinil not in NOTAS_GOLDMINE:
            erros.append((rotulo_d, f'Nota de vinil fora de M NM VG+ VG G+ G F: {vinil!r}.'))

        preco_et = o.get('preco_etiqueta')
        if preco_et is not None:
            if isinstance(preco_et, bool) or not isinstance(preco_et, (int, float)) or not math.isfinite(preco_et) or preco_et <= 0:
                erros.append((rotulo_d, f'preco_etiqueta deve ser número positivo ou null: {preco_et!r}.'))

        for campo in ('artista', 'album', 'descricao', 'tags'):
            if not str(o.get(campo) or '').strip():
                erros.append((rotulo_d, f'Campo obrigatório vazio: {campo}.'))

        desc = str(o.get('descricao') or '')
        linhas_desc = [l.strip() for l in desc.splitlines()]
        if capa in NOTAS_GOLDMINE and f'• Capa {capa}' not in linhas_desc:
            erros.append((rotulo_d, f'Descrição sem o tópico exato "• Capa {capa}".'))
        if vinil in NOTAS_GOLDMINE and f'• Vinil {vinil}' not in linhas_desc:
            erros.append((rotulo_d, f'Descrição sem o tópico exato "• Vinil {vinil}".'))

        tags_lista = [t.strip() for t in str(o.get('tags') or '').split(',') if t.strip()]
        if not ({'LP', 'LP Usado', 'Vinil Usado'} <= set(tags_lista)):
            erros.append((rotulo_d, 'Tags sem LP, LP Usado, Vinil Usado.'))

        desc_lower = desc.lower()
        exageros = [p for p in PALAVRAS_EXAGERO if p in desc_lower]
        if exageros:
            avisos.append((rotulo_d, f'Palavra de exagero na descrição: {", ".join(exageros)}.'))
        if str(o.get('confianca') or '').strip().lower() == 'baixa':
            avisos.append((rotulo_d, 'Avaliação com confiança baixa: conferir identificação.'))

    derivado = derivar_lote(
        dados if isinstance(dados, dict) else {},
        planilha=planilha,
        pasta_local=pasta_local,
        usar_nomes_novos=True,
        detectar_recortes=True,
    )

    # Verifica colisão de nomes novos na pasta local
    for ren in derivado['renomeacoes']:
        if ren['novo'] != ren['antigo'] and (pasta_local / ren['novo']).exists():
            erros.append((str(ren.get('disco', 'lote')), f'Nome novo já existe na pasta: {ren["novo"]}.'))

    for det in derivado['detalhes_discos']:
        cod = det['disco']
        for rep in det['repetidos_loja']:
            avisos.append((
                cod,
                f'Repetido na loja: {rep["nome"]} (estoque {rep["estoque"]}) - lojamonstro.com.br/produtos/{rep["url"]}/',
            ))
        for rep_p in det['repetidos_painel']:
            avisos.append((
                cod,
                f'Repetido no Painel: {rep_p["id"]} ({rep_p["status"]}) - {rep_p["titulo"]}',
            ))
        for f_info in det['fotos_site']:
            if f_info['falhou_recorte']:
                avisos.append((cod, f'Recorte automático falhou (a foto sai inteira): {f_info["arquivo"]} ({f_info["papel"]}).'))

    lote_dir = pasta_do_lote(lote or lote_padrao(), base_trabalho)
    lote_dir.mkdir(parents=True, exist_ok=True)

    previas_geradas: list[Path] = []
    if gerar_previas:
        pasta_previas = lote_dir / 'previas'
        pasta_previas.mkdir(parents=True, exist_ok=True)
        for det in derivado['detalhes_discos']:
            caminho_previa = _gerar_previa_disco(det, pasta_local, pasta_previas)
            if caminho_previa:
                previas_geradas.append(caminho_previa)

    relatorio_md = _montar_relatorio_conferencia(lote, derivado, erros, avisos)
    caminho_relatorio = lote_dir / 'conferencia.md'
    caminho_relatorio.write_text(relatorio_md, encoding='utf-8')

    return {
        'ok': len(erros) == 0,
        'erros': erros,
        'avisos': avisos,
        'derivado': derivado,
        'relatorio': caminho_relatorio,
        'previas': previas_geradas,
    }


def _fonte_padrao(tamanho: int = 16) -> Any:
    for nome in ('arial.ttf', 'DejaVuSans.ttf', 'segoeui.ttf'):
        try:
            return ImageFont.truetype(nome, tamanho)
        except Exception:
            continue
    return ImageFont.load_default()


def _gerar_previa_disco(det: dict[str, Any], pasta_local: Path, pasta_previas: Path) -> Path | None:
    fotos_site = det.get('fotos_site') or []
    if not fotos_site:
        return None
    miniaturas: list[tuple[str, Image.Image]] = []
    for f in fotos_site:
        arq = pasta_local / f['arquivo']
        if not arq.is_file():
            continue
        try:
            cantos_str = json.dumps(f['cantos']) if f.get('cantos') else ''
            jpg_bytes = mod_fotos.processar(arq.read_bytes(), f['papel'], cantos_str)
            im = Image.open(io.BytesIO(jpg_bytes)).convert('RGB')
            im.thumbnail((360, 360), Image.LANCZOS)
            miniaturas.append((f'{f["ordem"]:02d} {f["papel"]}', im))
        except Exception:
            continue
    if not miniaturas:
        return None

    cols = min(4, len(miniaturas))
    rows = math.ceil(len(miniaturas) / cols)
    w_cel, h_cel = 380, 410
    w_total = max(800, cols * w_cel)
    h_topo = 54
    h_total = h_topo + rows * h_cel

    folha = Image.new('RGB', (w_total, h_total), (245, 245, 245))
    draw = ImageDraw.Draw(folha)
    fonte_cab = _fonte_padrao(16)
    fonte_leg = _fonte_padrao(14)
    draw.rectangle([0, 0, w_total, h_topo], fill=(25, 25, 25))
    cabecalho = f'{det["disco"]} ({det["id"]}) · {det["titulo"]}'
    draw.text((16, 18), cabecalho[:110], fill=(255, 255, 255), font=fonte_cab)

    for idx, (legenda, im) in enumerate(miniaturas):
        c_idx = idx % cols
        r_idx = idx // cols
        x0 = c_idx * w_cel
        y0 = h_topo + r_idx * h_cel
        draw.text((x0 + 14, y0 + 10), legenda, fill=(30, 30, 30), font=fonte_leg)
        px = x0 + (w_cel - im.width) // 2
        py = y0 + 36 + (h_cel - 46 - im.height) // 2
        folha.paste(im, (px, py))

    saida = pasta_previas / f'{det["disco"]}.jpg'
    folha.save(saida, 'JPEG', quality=88)
    return saida


def _montar_relatorio_conferencia(
    lote: str,
    derivado: dict[str, Any],
    erros: list[tuple[str, str]],
    avisos: list[tuple[str, str]],
) -> str:
    linhas = [f'# Conferência do lote {lote or "(sem lote)"}', '']
    linhas.append(f'- Discos para cadastrar: {len(derivado["detalhes_discos"])}')
    linhas.append(f'- Discos pulados: {len(derivado["pulados"])}')
    linhas.append(f'- Fotos em cadastro_fotos: {len(derivado["fotos"])}')
    linhas.append(f'- Erros: {len(erros)}')
    linhas.append(f'- Avisos: {len(avisos)}')
    linhas.append('')

    linhas.append('## Erros')
    if not erros:
        linhas.append('Nenhum erro encontrado.')
    else:
        for d, msg in erros:
            linhas.append(f'- **{d}**: {msg}')
    linhas.append('')

    linhas.append('## Avisos')
    if not avisos:
        linhas.append('Nenhum aviso.')
    else:
        for d, msg in avisos:
            linhas.append(f'- **{d}**: {msg}')
    linhas.append('')

    if derivado['pulados']:
        linhas.append('## Discos pulados')
        for p in derivado['pulados']:
            linhas.append(f'- **{p["disco"]}**: {p["motivo"]}')
        linhas.append('')

    linhas.append('## Tabela de rascunhos')
    linhas.append('| Disco | ID | Título | Categorias | Preço | Capa/Vinil | Fotos site | Pendências |')
    linhas.append('|---|---|---|---|---|---|---|---|')
    for det in derivado['detalhes_discos']:
        preco_txt = f'R$ {det["preco"]}' if det['preco'] else 'sem preço'
        pend_txt = det['pendencias'].replace('|', ';') if det['pendencias'] else '-'
        linhas.append(
            f'| {det["disco"]} | {det["id"]} | {det["titulo"]} | {det["categorias"]} | '
            f'{preco_txt} | {det["capa"]}/{det["vinil"]} | {det["n_fotos_site"]} | {pend_txt} |'
        )
    linhas.append('')
    linhas.append('pronto para gravar' if not erros else 'corrigir antes de gravar')
    texto = '\n'.join(linhas) + '\n'
    return texto.replace('—', '-')


# ----------------------------------------------------------------------------
# Comando `gravar` (com plano.json e retomada idempotente)
# ----------------------------------------------------------------------------
def _escrever_aba_abaixo(planilha: PlanilhaGoogle, nome_aba: str, colunas_esperadas: list[str], novas_linhas: list[list[str]]) -> int:
    if not novas_linhas:
        return 0
    atuais = ler(planilha, nome_aba)
    if not atuais:
        planilha.garantir_cabecalho(nome_aba, colunas_esperadas, {})
        atuais = ler(planilha, nome_aba)
    cab = atuais[0]
    if any(c not in cab for c in colunas_esperadas):
        raise ErroLote(f'Cabeçalho de {nome_aba} não contém todas as colunas esperadas.')
    ultima = len([l for l in atuais if any(str(c).strip() for c in l)])
    aba = planilha._ss.worksheet(nome_aba)
    total_necessario = ultima + len(novas_linhas)
    if aba.row_count < total_necessario:
        aba.resize(rows=total_necessario)
    if aba.col_count < len(cab):
        aba.resize(cols=len(cab))
    aba.update(novas_linhas, f'A{ultima + 1}', raw=True)
    return len(novas_linhas)


def gravar_lote(
    caminho_json: Path | str,
    pasta_local: Path,
    planilha: PlanilhaGoogle,
    confirmar: bool = False,
    base_trabalho: Path | str | None = None,
) -> dict[str, Any]:
    caminho_json = Path(caminho_json)
    dados_brutos = json.loads(caminho_json.read_text(encoding='utf-8'))
    lote = str(dados_brutos.get('lote') or '').strip() or lote_padrao()
    lote_dir = pasta_do_lote(lote, base_trabalho)
    caminho_plano = lote_dir / 'plano.json'

    # Se houver um plano pela metade (interrompido após renomear) e confirmar=True, retoma dali
    retomando = False
    if confirmar and caminho_plano.exists():
        plano_salvo = json.loads(caminho_plano.read_text(encoding='utf-8'))
        if not plano_salvo.get('concluido'):
            plano = plano_salvo
            retomando = True

    if not retomando:
        conf = validar_lote(caminho_json, pasta_local, planilha, gerar_previas=False, base_trabalho=base_trabalho)
        if not conf['ok']:
            raise ErroLote('Conferência encontrou erros; corrigir antes de gravar.')
        derivado = conf['derivado']
        if not confirmar:
            return {
                'modo': 'simulacao',
                'gravados': [d['id'] for d in derivado['rascunhos_dicts']],
                'pulados': derivado['pulados'],
                'renomeacoes': derivado['renomeacoes'],
                'escritas_planilha': 0,
            }
        lote_dir.mkdir(parents=True, exist_ok=True)
        plano = {
            'lote': lote,
            'concluido': False,
            'rascunhos_dicts': derivado['rascunhos_dicts'],
            'fotos': derivado['fotos'],
            'renomeacoes': derivado['renomeacoes'],
            'pulados': derivado['pulados'],
        }
        caminho_plano.write_text(json.dumps(plano, ensure_ascii=False, indent=2), encoding='utf-8')

    # Passo 2: renomear arquivos locais, anotando cada um no plano
    for item in plano['renomeacoes']:
        if item.get('feito'):
            continue
        src = pasta_local / item['antigo']
        dst = pasta_local / item['novo']
        if item['antigo'] != item['novo']:
            if dst.exists() and not src.exists():
                item['feito'] = True
            elif dst.exists() and src.exists():
                raise ErroLote(f'Destino já existe na pasta: {item["novo"]}')
            elif src.exists():
                src.rename(dst)
                item['feito'] = True
            else:
                raise ErroLote(f'Arquivo de origem não encontrado para renomear: {item["antigo"]}')
        else:
            item['feito'] = True
        caminho_plano.write_text(json.dumps(plano, ensure_ascii=False, indent=2), encoding='utf-8')

    # Passo 3: acrescentar linhas em cadastro_rascunhos e depois em cadastro_fotos, sem duplicar IDs já presentes
    preparar_abas(planilha)
    atuais_rasc = ler(planilha, ABA)
    cab_rasc = atuais_rasc[0]
    if any(c not in cab_rasc for c in COLUNAS):
        raise ErroLote('Cabeçalho de cadastro_rascunhos incompleto.')
    ids_existentes_rasc = {str(r[0]).strip() for r in atuais_rasc[1:] if r and str(r[0]).strip()}

    novas_rasc = [
        [d.get(col, '') for col in cab_rasc]
        for d in plano['rascunhos_dicts']
        if d['id'] not in ids_existentes_rasc
    ]
    n_rasc = _escrever_aba_abaixo(planilha, ABA, COLUNAS, novas_rasc)

    atuais_fotos = ler(planilha, 'cadastro_fotos')
    chaves_existentes_fotos = {
        (str(r[0]).strip(), str(r[1]).strip(), str(r[5]).strip())
        for r in atuais_fotos[1:]
        if len(r) >= 6
    }
    novas_fotos = [
        f for f in plano['fotos']
        if (str(f[0]).strip(), str(f[1]).strip(), str(f[5]).strip()) not in chaves_existentes_fotos
    ]
    n_fotos = _escrever_aba_abaixo(planilha, 'cadastro_fotos', FOTOS, novas_fotos)

    # Passo 4: marcar plano como concluído
    plano['concluido'] = True
    caminho_plano.write_text(json.dumps(plano, ensure_ascii=False, indent=2), encoding='utf-8')

    return {
        'modo': 'confirmado',
        'gravados': [d['id'] for d in plano['rascunhos_dicts']],
        'pulados': plano['pulados'],
        'renomeacoes': plano['renomeacoes'],
        'escritas_planilha': n_rasc + n_fotos,
    }


# ----------------------------------------------------------------------------
# Comando extra: `renomear-lote LOTE [--confirmar]`
# ----------------------------------------------------------------------------
def renomear_lote_antigo(
    lote: str,
    pasta_local: Path,
    planilha: PlanilhaGoogle,
    confirmar: bool = False,
) -> dict[str, Any]:
    linhas = ler(planilha, 'cadastro_fotos')
    if not linhas or linhas[0] != FOTOS:
        raise ErroLote('Cabeçalho de cadastro_fotos inválido ou ausente.')

    prefixo = f'{lote}-'
    plano_ren: list[dict[str, Any]] = []
    for num_linha, r in enumerate(linhas[1:], 2):
        d = dict(zip(FOTOS, r))
        id_disco = str(d.get('id_disco', '')).strip()
        obs = str(d.get('observacao', '')).strip()
        if not id_disco.startswith(prefixo) or not obs.startswith('IMG_'):
            continue
        ordem_int = int(float(d.get('ordem') or 0))
        papel = str(d.get('papel', '')).strip()
        if ordem_int == 0 or papel == 'etiqueta':
            novo = f'{id_disco} 00 etiqueta.jpg'
        else:
            novo = f'{id_disco} {ordem_int:02d} {papel}.jpg'
        if novo != obs and (pasta_local / novo).exists():
            raise ErroLote(f'Nome novo já existe na pasta: {novo}')
        if not (pasta_local / obs).exists():
            raise ErroLote(f'Arquivo local não encontrado: {obs}')
        plano_ren.append({'linha': num_linha, 'id_disco': id_disco, 'antigo': obs, 'novo': novo})

    if confirmar and plano_ren:
        mudancas = []
        for item in plano_ren:
            src = pasta_local / item['antigo']
            dst = pasta_local / item['novo']
            if src != dst:
                src.rename(dst)
            mudancas.append({'range': f'F{item["linha"]}', 'values': [[item['novo']]]})
        aba = planilha._ss.worksheet('cadastro_fotos')
        if hasattr(aba, 'batch_update'):
            aba.batch_update(mudancas, raw=True)
        else:
            for m in mudancas:
                aba.update(m['values'], m['range'], raw=True)

    return {'lote': lote, 'modo': 'confirmado' if confirmar else 'simulacao', 'itens': plano_ren}


# ----------------------------------------------------------------------------
# Comando extra: `recortar-lote LOTE [--confirmar]` (D-091)
# ----------------------------------------------------------------------------
def _gerar_folhas_previas(
    arquivos_previas: list[tuple[str, Path]],
    pasta_folhas: Path,
    lote: str,
) -> list[Path]:
    pasta_folhas.mkdir(parents=True, exist_ok=True)
    cols, rows = 3, 4
    por_folha = cols * rows
    w_folha = 1800
    w_cel = w_folha // cols
    h_cel = 350
    h_folha = 60 + h_cel * rows

    arquivos: list[Path] = []
    total = len(arquivos_previas)
    total_folhas = math.ceil(total / por_folha) if total > 0 else 1
    fonte_tit = _fonte_padrao(18)

    for f_idx, inicio in enumerate(range(0, total, por_folha), 1):
        bloco = arquivos_previas[inicio:inicio + por_folha]
        folha = Image.new('RGB', (w_folha, h_folha), (240, 240, 240))
        draw = ImageDraw.Draw(folha)

        draw.rectangle([0, 0, w_folha, 50], fill=(20, 20, 20))
        tit = f'Lote {lote} · Folha de prévias {f_idx} de {total_folhas} (discos {bloco[0][0]} a {bloco[-1][0]})'
        draw.text((20, 15), tit, fill=(255, 255, 255), font=fonte_tit)

        for pos, (id_disco, arq_previa) in enumerate(bloco):
            col = pos % cols
            row = pos // cols
            x0, y0 = col * w_cel, 60 + row * h_cel
            x1, y1 = x0 + w_cel, y0 + h_cel
            draw.rectangle([x0 + 4, y0 + 4, x1 - 4, y1 - 4], outline=(200, 200, 200), width=1)
            try:
                with Image.open(arq_previa) as im:
                    im_rgb = im.convert('RGB')
                im_rgb.thumbnail((w_cel - 16, h_cel - 16), Image.LANCZOS)
                px = x0 + (w_cel - im_rgb.width) // 2
                py = y0 + (h_cel - im_rgb.height) // 2
                folha.paste(im_rgb, (px, py))
            except Exception:
                draw.text((x0 + 10, y0 + 10), f'Erro ao abrir {id_disco}', fill=(200, 0, 0))

        caminho_folha = pasta_folhas / f'folha_previa_{f_idx:02d}.jpg'
        folha.save(caminho_folha, 'JPEG', quality=88)
        arquivos.append(caminho_folha)
    return arquivos


def recortar_lote_fotos(
    lote: str,
    pasta_local: Path,
    planilha: PlanilhaGoogle,
    confirmar: bool = False,
    base_trabalho: Path | str | None = None,
) -> dict[str, Any]:
    linhas_fotos = ler(planilha, 'cadastro_fotos')
    if not linhas_fotos or linhas_fotos[0] != FOTOS:
        raise ErroLote('Cabeçalho de cadastro_fotos inválido ou ausente.')

    linhas_rasc = ler(planilha, ABA)
    titulos_por_id: dict[str, str] = {}
    if linhas_rasc:
        cab_r = linhas_rasc[0]
        idx_id = cab_r.index('id') if 'id' in cab_r else 0
        idx_tit = cab_r.index('titulo') if 'titulo' in cab_r else 4
        for r in linhas_rasc[1:]:
            if len(r) > max(idx_id, idx_tit):
                titulos_por_id[str(r[idx_id]).strip()] = str(r[idx_tit]).strip()

    prefixo = f'{lote}-'
    fotos_recalculadas: list[dict[str, Any]] = []
    discos_agrupados: dict[str, list[dict[str, Any]]] = {}

    for num_linha, r in enumerate(linhas_fotos[1:], 2):
        d = dict(zip(FOTOS, r))
        id_disco = str(d.get('id_disco', '')).strip()
        if not id_disco.startswith(prefixo):
            continue
        ordem_str = str(d.get('ordem', '')).strip()
        papel = str(d.get('papel', '')).strip().lower()
        if ordem_str == '0' or papel in ('etiqueta', 'descartar'):
            continue

        obs = str(d.get('observacao', '')).strip()
        caminho_arq = pasta_local / obs if obs else None
        cantos_atuais_str = str(d.get('cantos', '')).strip()

        cantos_novos = None
        falhou = True
        if caminho_arq and caminho_arq.is_file():
            cantos_novos, falhou = calcular_cantos_foto(caminho_arq, papel, {'arquivo': obs, 'papel': papel})

        info_foto = {
            'linha': num_linha,
            'id_disco': id_disco,
            'ordem': int(float(ordem_str or 1)),
            'papel': papel,
            'arquivo': obs,
            'cantos_antigos': cantos_atuais_str,
            'cantos_novos': cantos_novos,
            'falhou': falhou,
        }
        fotos_recalculadas.append(info_foto)
        if id_disco not in discos_agrupados:
            discos_agrupados[id_disco] = []
        discos_agrupados[id_disco].append(info_foto)

    pasta_lote_dir = pasta_do_lote(lote, base_trabalho)
    pasta_previas = pasta_lote_dir / 'previas'
    pasta_previas.mkdir(parents=True, exist_ok=True)
    previas_discos: list[tuple[str, Path]] = []

    for id_disco, f_lista in sorted(discos_agrupados.items()):
        f_lista.sort(key=lambda x: x['ordem'])
        detalhes = {
            'disco': id_disco,
            'id': id_disco,
            'titulo': titulos_por_id.get(id_disco, id_disco),
            'fotos_site': [
                {
                    'ordem': f['ordem'],
                    'papel': f['papel'],
                    'arquivo': f['arquivo'],
                    'cantos': f['cantos_novos'],
                }
                for f in f_lista
            ],
        }
        arq_previa = _gerar_previa_disco(detalhes, pasta_local, pasta_previas)
        if arq_previa:
            previas_discos.append((id_disco, arq_previa))

    pasta_folhas = pasta_lote_dir / 'folhas_previas'
    arquivos_folhas = _gerar_folhas_previas(previas_discos, pasta_folhas, lote)

    n_recortados = sum(1 for f in fotos_recalculadas if f['cantos_novos'] is not None)
    n_inteiras = sum(1 for f in fotos_recalculadas if f['cantos_novos'] is None)

    if confirmar:
        linhas_fotos_atuais = ler(planilha, 'cadastro_fotos')
        if not linhas_fotos_atuais or linhas_fotos_atuais[0] != FOTOS:
            raise ErroLote('Cabeçalho de cadastro_fotos inválido ao gravar cantos.')

        mudancas_fotos = []
        for item in fotos_recalculadas:
            lin = item['linha']
            if lin > len(linhas_fotos_atuais):
                raise ErroLote(f'Linha {lin} fora do alcance em cadastro_fotos.')
            atual = dict(zip(FOTOS, linhas_fotos_atuais[lin - 1]))
            if (
                atual.get('id_disco', '').strip() != item['id_disco']
                or str(atual.get('ordem', '')).strip() != str(item['ordem'])
                or atual.get('observacao', '').strip() != item['arquivo']
            ):
                raise ErroLote(
                    f'Concorrência: linha {lin} em cadastro_fotos não corresponde a '
                    f'{item["id_disco"]} ordem {item["ordem"]}. Abortando gravação.'
                )
            valor_cantos = json.dumps(item['cantos_novos']) if item['cantos_novos'] else ''
            mudancas_fotos.append({'range': f'E{lin}', 'values': [[valor_cantos]]})

        aba_fotos = planilha._ss.worksheet('cadastro_fotos')
        if hasattr(aba_fotos, 'batch_update'):
            aba_fotos.batch_update(mudancas_fotos, raw=True)
        else:
            for m in mudancas_fotos:
                aba_fotos.update(m['values'], m['range'], raw=True)

        mudancas_rasc = []
        if linhas_rasc:
            cab_rasc = linhas_rasc[0]
            if 'fotos_ajustadas' not in cab_rasc:
                raise ErroLote('Coluna fotos_ajustadas não encontrada em cadastro_rascunhos.')
            idx_ajustadas = cab_rasc.index('fotos_ajustadas')
            letra_ajustadas = _letra(idx_ajustadas + 1)
            for num_lin, r in enumerate(linhas_rasc[1:], 2):
                if r and str(r[0]).strip().startswith(prefixo):
                    mudancas_rasc.append({'range': f'{letra_ajustadas}{num_lin}', 'values': [['']]})

            if mudancas_rasc:
                aba_rasc = planilha._ss.worksheet(ABA)
                if hasattr(aba_rasc, 'batch_update'):
                    aba_rasc.batch_update(mudancas_rasc, raw=True)
                else:
                    for m in mudancas_rasc:
                        aba_rasc.update(m['values'], m['range'], raw=True)

    return {
        'lote': lote,
        'modo': 'confirmado' if confirmar else 'simulacao',
        'discos': len(discos_agrupados),
        'fotos_processadas': len(fotos_recalculadas),
        'recortadas': n_recortados,
        'inteiras': n_inteiras,
        'previas': len(previas_discos),
        'folhas_previas': len(arquivos_folhas),
        'pasta_previas': pasta_previas,
        'pasta_folhas': pasta_folhas,
        'arquivos_folhas': arquivos_folhas,
    }


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------
@comando_seguro
def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParserSeguro(description='Cadastro de discos por lote local (D-078).')
    sub = parser.add_subparsers(dest='comando', required=True)

    p_folhas = sub.add_parser('folhas')
    p_folhas.add_argument('--lote', default='')

    p_rec = sub.add_parser('recorte')
    p_rec.add_argument('arquivo')
    p_rec.add_argument('esq', type=float)
    p_rec.add_argument('topo', type=float)
    p_rec.add_argument('dir', type=float)
    p_rec.add_argument('base', type=float)
    p_rec.add_argument('--lote', default='')

    p_conf = sub.add_parser('conferir')
    p_conf.add_argument('json_lote')

    p_grav = sub.add_parser('gravar')
    p_grav.add_argument('json_lote')
    p_grav.add_argument('--confirmar', action='store_true')

    p_ren = sub.add_parser('renomear-lote')
    p_ren.add_argument('lote')
    p_ren.add_argument('--confirmar', action='store_true')

    p_rec_lote = sub.add_parser('recortar-lote')
    p_rec_lote.add_argument('lote')
    p_rec_lote.add_argument('--confirmar', action='store_true')

    args = parser.parse_args(argv)
    cfg = carregar()
    pasta = pasta_entrada(cfg)

    if args.comando == 'recorte':
        saida = recortar_foto(args.arquivo, args.esq, args.topo, args.dir, args.base, pasta, args.lote or None)
        print(f'Recorte salvo em: {saida}')
        return 0

    planilha = PlanilhaGoogle.conectar(cfg)

    if args.comando == 'folhas':
        res = gerar_folhas(pasta, planilha, args.lote or None)
        print(f'{res["fotos"]} foto(s) nova(s), {res["folhas"]} folha(s) gerada(s) em {res["fotos_txt"].parent}.')
        return 0

    if args.comando == 'conferir':
        res = validar_lote(args.json_lote, pasta, planilha, gerar_previas=True)
        d = res['derivado']
        print(
            f'Conferência: {len(d["detalhes_discos"])} para cadastrar, {len(d["pulados"])} pulado(s), '
            f'{len(res["erros"])} erro(s), {len(res["avisos"])} aviso(s).'
        )
        print(f'Relatório: {res["relatorio"]}')
        print('pronto para gravar' if res['ok'] else 'corrigir antes de gravar')
        return 0 if res['ok'] else 1

    if args.comando == 'gravar':
        res = gravar_lote(args.json_lote, pasta, planilha, confirmar=args.confirmar)
        if res['modo'] == 'simulacao':
            print(
                f'Simulação: {len(res["gravados"])} disco(s) seriam gravados, '
                f'{len(res["pulados"])} pulado(s), {len(res["renomeacoes"])} foto(s) seriam renomeadas.'
            )
        else:
            print(
                f'Gravado: {len(res["gravados"])} disco(s) ({", ".join(res["gravados"])}), '
                f'{len(res["pulados"])} pulado(s), {len(res["renomeacoes"])} foto(s) renomeada(s).'
            )
        return 0

    if args.comando == 'renomear-lote':
        res = renomear_lote_antigo(args.lote, pasta, planilha, confirmar=args.confirmar)
        print(f'{res["modo"]}: {len(res["itens"])} foto(s) do lote {res["lote"]}.')
        return 0

    if args.comando == 'recortar-lote':
        res = recortar_lote_fotos(args.lote, pasta, planilha, confirmar=args.confirmar)
        if res['modo'] == 'simulacao':
            print(
                f'Simulação recortar-lote: {res["discos"]} disco(s), {res["fotos_processadas"]} foto(s) processada(s) '
                f'({res["recortadas"]} com recorte novo, {res["inteiras"]} inteiras). '
                f'{res["previas"]} prévias e {res["folhas_previas"]} folha(s) de prévias geradas em {res["pasta_folhas"]}. '
                'Nenhuma alteração gravada na planilha. Use --confirmar após revisão.'
            )
        else:
            print(
                f'Gravado recortar-lote: cantos de {res["fotos_processadas"]} foto(s) atualizados em cadastro_fotos '
                f'e coluna fotos_ajustadas limpa em cadastro_rascunhos para o lote {res["lote"]}.'
            )
        return 0

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
