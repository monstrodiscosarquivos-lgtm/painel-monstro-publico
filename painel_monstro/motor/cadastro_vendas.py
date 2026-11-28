"""Análise semanal: cadastrar mais discos faz vender mais? (desde julho/2025).

Trabalha apenas com agregados por semana (segunda a domingo), sem nenhum dado de cliente.
Responde:
1. Série semanal (cadastros de discos, pedidos, itens vendidos, receita, gasto Meta e promoção).
2. Venda de disco novo: % dos itens e da receita por idade do cadastro (<=7, 8-30, 31-90, >90 dias).
3. Tempo até vender: mediana de dias entre cadastro e venda (usado estoque 1 vs novo/lacrado).
4. Correlação (Pearson e Spearman) entre cadastros na semana t e vendas em t, t+1 e t+2 (com e sem promoção).
5. Regressão simples: vendas ~ cadastros_t + cadastros_t-1 + promocao + gasto_meta, com efeito de +10 discos e IC 95%.
6. Resumo de uma frase no topo.
"""
from __future__ import annotations

from datetime import date, timedelta
import math
import re
from typing import Any

import numpy as np
import pandas as pd

from painel_monstro.motor.black import _cupons_da_config, _parse_num
from painel_monstro.saidas.carrinhos import eh_disco

INICIO_ANALISE = date(2025, 6, 30)  # segunda-feira da semana de 01/07/2025
CHAVE_SEMANAS_PROMO = "Semanas com promoção"
AVISO_CAUSALIDADE = "correlação não é causa; com poucas semanas o resultado é indicativo"

# prefixos/palavras de cupons sazonais ou promocionais (exclui reativação mensal VOLTA e uso único)
PALAVRAS_CUPOM_PROMO = (
    "BLACK", "ANTECIPA", "LADOA", "CRIANCA", "MUSICA", "NATAL", "CARNAVAL",
    "PASCOA", "MAES", "PAIS", "NAMORAD", "PROMO", "SALDAO", "OUTLET", "FEIRA", "DISCO", "VINIL",
)
PREFIXOS_CUPOM_CONTINUO = ("VOLTA", "RASPA", "BEMVINDO", "FRETEGRATIS")

_T_CRIT_95 = {
    1: 12.7062, 2: 4.3027, 3: 3.1824, 4: 2.7764, 5: 2.5706, 6: 2.4469,
    7: 2.3646, 8: 2.3060, 9: 2.2622, 10: 2.2281, 11: 2.2010, 12: 2.1788,
    13: 2.1604, 14: 2.1448, 15: 2.1314, 16: 2.1199, 17: 2.1098, 18: 2.1009,
    19: 2.0930, 20: 2.0860, 21: 2.0796, 22: 2.0739, 23: 2.0687, 24: 2.0639,
    25: 2.0595, 26: 2.0555, 27: 2.0518, 28: 2.0484, 29: 2.0452, 30: 2.0423,
}


def _t_crit_95(df: int) -> float:
    if df <= 0:
        return 1.96
    if df in _T_CRIT_95:
        return _T_CRIT_95[df]
    z = 1.95996398454
    return z + (z ** 3 + z) / (4.0 * df) + (5.0 * z ** 5 + 16.0 * z ** 3 + 3.0 * z) / (96.0 * df ** 2)


def _para_data(valor: Any) -> date | None:
    if valor is None or valor == "" or (isinstance(valor, float) and math.isnan(valor)):
        return None
    ts = pd.to_datetime(valor, errors="coerce")
    if pd.isna(ts):
        return None
    if getattr(ts, "tzinfo", None) is not None:
        ts = ts.tz_convert("America/Sao_Paulo")
    return ts.date()


def _segunda(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _eh_produto_disco(nome: Any, categorias: Any) -> bool:
    cat = str(categorias or "").lower()
    if "livro" in cat and "lp" not in cat and "cd" not in cat and "vinil" not in cat:
        return False
    return eh_disco(nome) or bool(re.search(r"\b(lp|vinil|cd|cassete|k7|compacto|box)\b", cat))


def _tipo_disco(nome: Any, categorias: Any) -> str:
    texto = f"{nome or ''} {categorias or ''}".lower()
    if "novo" in texto or "lacrad" in texto:
        return "novo"
    return "usado"


def parsear_semanas_promocao(valor: Any) -> set[date]:
    """Lê datas ou intervalos da linha 'Semanas com promoção' e devolve segundas-feiras marcadas."""
    texto = str(valor or "").strip()
    if not texto:
        return set()
    semanas: set[date] = set()

    def _parse_token(tok: str) -> date | None:
        t = tok.strip()
        m_iso = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", t)
        if m_iso:
            try:
                return date(int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3)))
            except ValueError:
                return None
        m_br = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", t)
        if m_br:
            try:
                return date(int(m_br.group(3)), int(m_br.group(2)), int(m_br.group(1)))
            except ValueError:
                return None
        return None

    for parte in re.split(r"[,;\n]+", texto):
        p = parte.strip()
        if not p:
            continue
        m_rng = re.match(r"^(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})\s*(?:a|ate|até|-)\s*(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})$", p, re.I)
        if m_rng:
            d1, d2 = _parse_token(m_rng.group(1)), _parse_token(m_rng.group(2))
            if d1 and d2:
                if d1 > d2:
                    d1, d2 = d2, d1
                cur = _segunda(d1)
                fim = _segunda(d2)
                while cur <= fim:
                    semanas.add(cur)
                    cur += timedelta(days=7)
            continue
        dt = _parse_token(p)
        if dt:
            semanas.add(_segunda(dt))
    return semanas


def _eh_cupom_promocao(codigo: str, cupons_black: set[str]) -> bool:
    c = str(codigo or "").strip().upper()
    if not c or c in ("SEM_CUPOM", "SEM CUPOM", "NONE", "NAN"):
        return False
    if any(c.startswith(p) for p in PREFIXOS_CUPOM_CONTINUO):
        return False
    if c in cupons_black:
        return True
    return any(pal in c for pal in PALAVRAS_CUPOM_PROMO)


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    ax = np.asarray(xs, dtype=float)
    ay = np.asarray(ys, dtype=float)
    dx = ax - ax.mean()
    dy = ay - ay.mean()
    sx = float(np.sqrt(np.sum(dx * dx)))
    sy = float(np.sqrt(np.sum(dy * dy)))
    if sx <= 1e-12 or sy <= 1e-12:
        return None
    return round(float(np.sum(dx * dy) / (sx * sy)), 4)


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    rx = pd.Series(xs, dtype=float).rank(method="average").to_numpy()
    ry = pd.Series(ys, dtype=float).rank(method="average").to_numpy()
    return _pearson(rx.tolist(), ry.tolist())


def correlacoes_por_defasagem(
    semanas: list[dict[str, Any]],
    sem_promocao: bool = False,
) -> list[dict[str, Any]]:
    """Pearson e Spearman entre cadastros na semana t e vendas em t, t+1 e t+2 (semanas completas)."""
    completas = {date.fromisoformat(s["semana_inicio"]): s for s in semanas if s.get("completa")}
    ordenadas = sorted(completas.keys())
    saida = []
    for lag in (0, 1, 2):
        xs: list[float] = []
        peds: list[float] = []
        recs: list[float] = []
        pontos: list[dict[str, Any]] = []
        for s_t in ordenadas:
            s_y = s_t + timedelta(days=7 * lag)
            if s_y not in completas:
                continue
            w_t = completas[s_t]
            w_y = completas[s_y]
            if sem_promocao and (w_t["promocao"] or w_y["promocao"]):
                continue
            x = float(w_t["discos_cadastrados"])
            yp = float(w_y["pedidos"])
            yr = float(w_y["receita"])
            xs.append(x)
            peds.append(yp)
            recs.append(yr)
            pontos.append({
                "semana_t": w_t["semana_inicio"],
                "semana_y": w_y["semana_inicio"],
                "cadastros": int(w_t["discos_cadastrados"]),
                "pedidos": int(w_y["pedidos"]),
                "receita": round(float(w_y["receita"]), 2),
                "promocao": int(w_t["promocao"] or w_y["promocao"]),
            })
        saida.append({
            "lag": lag,
            "rotulo": "t (mesma semana)" if lag == 0 else f"t+{lag} ({lag} semana{'s' if lag > 1 else ''} depois)",
            "n": len(xs),
            "pearson_pedidos": _pearson(xs, peds),
            "spearman_pedidos": _spearman(xs, peds),
            "pearson_receita": _pearson(xs, recs),
            "spearman_receita": _spearman(xs, recs),
            "pontos": pontos,
        })
    return saida


def ajustar_regressao(semanas: list[dict[str, Any]], alvo: str = "pedidos") -> dict[str, Any]:
    """OLS: vendas_t ~ 1 + cadastros_t + cadastros_{t-1} + promocao_t + gasto_meta_t."""
    completas = {date.fromisoformat(s["semana_inicio"]): s for s in semanas if s.get("completa")}
    ordenadas = sorted(completas.keys())
    linhas = []
    for s_t in ordenadas:
        s_ant = s_t - timedelta(days=7)
        if s_ant not in completas:
            continue
        w_t = completas[s_t]
        w_ant = completas[s_ant]
        linhas.append({
            "y": float(w_t[alvo]),
            "cad_t": float(w_t["discos_cadastrados"]),
            "cad_ant": float(w_ant["discos_cadastrados"]),
            "promocao": float(w_t["promocao"]),
            "gasto_meta": float(w_t["gasto_meta"]),
        })

    n = len(linhas)
    base_vazia = {
        "alvo": alvo, "disponivel": False, "n": n, "r2": None,
        "efeito_10_semana": None, "ic_10_semana": None,
        "efeito_10_seguinte": None, "ic_10_seguinte": None,
        "efeito_10_combinado": None, "ic_10_combinado": None,
        "efeito_promocao": None, "efeito_meta_100": None,
        "aviso": AVISO_CAUSALIDADE,
    }
    if n < 6:
        return base_vazia

    df = pd.DataFrame(linhas)
    y = df["y"].to_numpy(dtype=float)
    cand_cols = ["cad_t", "cad_ant", "promocao", "gasto_meta"]
    ativas = [c for c in cand_cols if float(df[c].std()) > 1e-9]
    if "cad_t" not in ativas and "cad_ant" not in ativas:
        return base_vazia

    X_cols = [np.ones(n, dtype=float)] + [df[c].to_numpy(dtype=float) for c in ativas]
    X = np.column_stack(X_cols)
    k = X.shape[1]
    if n - k < 2:
        return base_vazia

    # Se duas colunas forem colineares (ex.: gasto_meta proporcional a promocao), descarta covariáveis colineares de menor prioridade.
    for col_drop in ("gasto_meta", "promocao", "cad_t"):
        if int(np.linalg.matrix_rank(X)) >= k or len(ativas) <= 1:
            break
        if col_drop in ativas and not (col_drop == "cad_ant" and "cad_t" not in ativas):
            ativas = [c for c in ativas if c != col_drop]
            X = np.column_stack([np.ones(n, dtype=float)] + [df[c].to_numpy(dtype=float) for c in ativas])
            k = X.shape[1]
    if ("cad_t" not in ativas and "cad_ant" not in ativas) or n - k < 2 or int(np.linalg.matrix_rank(X)) < k:
        return base_vazia

    beta, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    df_res = n - k
    sse = float(np.sum(resid * resid))
    sst = float(np.sum((y - y.mean()) ** 2))
    r2 = round(max(0.0, 1.0 - sse / sst), 3) if sst > 1e-12 else None
    s2 = sse / df_res
    cov = s2 * np.linalg.pinv(X.T @ X)
    t_val = _t_crit_95(df_res)

    idx = {nome: i + 1 for i, nome in enumerate(ativas)}

    def _efeito(nome: str, mult: float = 10.0) -> tuple[float | None, list[float] | None]:
        if nome not in idx:
            return None, None
        i = idx[nome]
        b = float(beta[i]) * mult
        se = float(math.sqrt(max(0.0, float(cov[i, i])))) * mult
        return round(b, 2), [round(b - t_val * se, 2), round(b + t_val * se, 2)]

    ef_sem, ic_sem = _efeito("cad_t", 10.0)
    ef_seg, ic_seg = _efeito("cad_ant", 10.0)
    if "cad_t" in idx and "cad_ant" in idx:
        i1, i2 = idx["cad_t"], idx["cad_ant"]
        b_comb = (float(beta[i1]) + float(beta[i2])) * 10.0
        var_comb = float(cov[i1, i1] + cov[i2, i2] + 2.0 * cov[i1, i2])
        se_comb = float(math.sqrt(max(0.0, var_comb))) * 10.0
        ef_comb = round(b_comb, 2)
        ic_comb = [round(b_comb - t_val * se_comb, 2), round(b_comb + t_val * se_comb, 2)]
    else:
        ef_comb, ic_comb = None, None

    ef_promo, _ = _efeito("promocao", 1.0)
    ef_meta, _ = _efeito("gasto_meta", 100.0)

    return {
        "alvo": alvo,
        "disponivel": True,
        "n": n,
        "df": df_res,
        "r2": r2,
        "efeito_10_semana": ef_sem,
        "ic_10_semana": ic_sem,
        "efeito_10_seguinte": ef_seg,
        "ic_10_seguinte": ic_seg,
        "efeito_10_combinado": ef_comb,
        "ic_10_combinado": ic_comb,
        "efeito_promocao": ef_promo,
        "efeito_meta_100": ef_meta,
        "aviso": AVISO_CAUSALIDADE,
    }


def calcular_cadastro_vendas(
    produtos_df: pd.DataFrame | None,
    pedidos_df: pd.DataFrame | None,
    itens_df: pd.DataFrame | None,
    anuncios_campanha_dia_df: pd.DataFrame | None = None,
    config_params: dict[str, Any] | None = None,
    agora_brt: pd.Timestamp | None = None,
) -> dict[str, Any]:
    """Calcula a análise completa semanal 'Cadastro de discos x vendas' desde julho/2025 (sem dados de cliente)."""
    if agora_brt is None:
        agora_sp = pd.Timestamp.now(tz="America/Sao_Paulo")
    else:
        ts = pd.Timestamp(agora_brt)
        agora_sp = ts.tz_convert("America/Sao_Paulo") if ts.tzinfo is not None else ts.tz_localize("America/Sao_Paulo")
    hoje_date = agora_sp.date()
    atualizado_em = agora_sp.strftime("%Y-%m-%d %H:%M")

    cfg = config_params or {}
    cfg_lower = {str(k).strip().lower(): v for k, v in cfg.items()}
    manuais_promo = parsear_semanas_promocao(cfg_lower.get(CHAVE_SEMANAS_PROMO.lower(), ""))
    cupons_black = set(_cupons_da_config(cfg))

    # 1. Produtos (indexados por produto_id e sku)
    prod_por_id: dict[str, dict[str, Any]] = {}
    prod_por_sku: dict[str, dict[str, Any]] = {}
    criacoes_por_sem: dict[date, int] = {}
    primeira_data: date | None = None

    if produtos_df is not None and not produtos_df.empty:
        for pr in produtos_df.to_dict("records"):
            nome = pr.get("nome", "")
            cats = pr.get("categorias", pr.get("categoria", ""))
            if not _eh_produto_disco(nome, cats):
                continue
            pid = str(pr.get("id", "")).strip()
            if pid.endswith(".0"):
                pid = pid[:-2]
            if pid.lower() == "nan":
                pid = ""
            sku = str(pr.get("sku", "")).strip()
            if sku.lower() == "nan":
                sku = ""
            criado = _para_data(pr.get("criado_em"))
            if criado and (primeira_data is None or criado < primeira_data):
                primeira_data = criado
            if criado:
                sem_c = _segunda(criado)
                criacoes_por_sem[sem_c] = criacoes_por_sem.get(sem_c, 0) + 1
            est_raw = pr.get("estoque")
            est = int(round(_parse_num(est_raw))) if str(est_raw or "").strip() not in ("", "nan", "None") else 1
            ilim = pr.get("estoque_ilimitado") in (True, 1, "True", "TRUE", "true", "sim", "Sim")
            tipo = _tipo_disco(nome, cats)
            info = {"criado": criado, "tipo": tipo, "estoque": est, "ilimitado": ilim}
            if pid:
                prod_por_id[pid] = info
            if sku:
                prod_por_sku[sku] = info

    # 2. Pedidos válidos
    ped_map: dict[str, dict[str, Any]] = {}
    ped_por_sem: dict[date, dict[str, Any]] = {}
    if pedidos_df is not None and not pedidos_df.empty:
        for p in pedidos_df.to_dict("records"):
            v = p.get("valido")
            if not (v is True or str(v).strip().upper() in ("TRUE", "1", "SIM")):
                continue
            dt = _para_data(p.get("data"))
            if dt is None:
                continue
            if primeira_data is None or dt < primeira_data:
                primeira_data = dt
            num = str(p.get("numero", "")).strip()
            if num.endswith(".0"):
                num = num[:-2]
            sub = _parse_num(p.get("subtotal"))
            desc = _parse_num(p.get("desconto"))
            tot = _parse_num(p.get("total"))
            receita = max(0.0, sub - desc) if sub > 0 else max(0.0, tot)
            cup = str(p.get("cupom") or "").strip().upper()
            sem = _segunda(dt)
            ped_map[num] = {"dt": dt, "sem": sem, "receita": receita}
            st = ped_por_sem.setdefault(sem, {"pedidos": 0, "receita": 0.0, "cupons_promo": set()})
            st["pedidos"] += 1
            st["receita"] += receita
            for cp in [x.strip() for x in cup.split(",") if x.strip()]:
                if _eh_cupom_promocao(cp, cupons_black):
                    st["cupons_promo"].add(cp)

    # 3. Itens vendidos + idade do disco no momento da venda + tempo até vender
    itens_por_pedido: dict[str, list[dict[str, Any]]] = {}
    if itens_df is not None and not itens_df.empty:
        for it in itens_df.to_dict("records"):
            num = str(it.get("numero", "")).strip()
            if num.endswith(".0"):
                num = num[:-2]
            if num not in ped_map:
                continue
            pid = str(it.get("produto_id", "")).strip()
            if pid.endswith(".0"):
                pid = pid[:-2]
            if pid.lower() == "nan":
                pid = ""
            sku = str(it.get("sku", "")).strip()
            if sku.lower() == "nan":
                sku = ""
            qtd = max(1, int(round(_parse_num(it.get("quantidade")) or 1)))
            val = _parse_num(it.get("valor"))
            itens_por_pedido.setdefault(num, []).append({
                "pid": pid, "sku": sku, "qtd": qtd, "bruto": max(0.0, val * qtd),
            })

    faixas_nomes = ("0_7", "8_30", "31_90", "mais_90")
    itens_sem: dict[date, dict[str, Any]] = {}
    dias_venda_usado_sem: dict[date, list[int]] = {}
    dias_venda_novo_sem: dict[date, list[int]] = {}

    for num, ped in ped_map.items():
        sem = ped["sem"]
        dt_venda = ped["dt"]
        its = itens_por_pedido.get(num, [])
        st_i = itens_sem.setdefault(sem, {
            "total_itens": 0,
            "itens_com_cad": 0, "rec_com_cad": 0.0,
            "qtd": {f: 0 for f in faixas_nomes},
            "rec": {f: 0.0 for f in faixas_nomes},
        })
        soma_bruto = sum(x["bruto"] for x in its)
        fator_liq = (ped["receita"] / soma_bruto) if soma_bruto > 0 else 1.0

        for x in its:
            qtd = x["qtd"]
            rec_item = (x["bruto"] * fator_liq) if soma_bruto > 0 else (ped["receita"] / max(1, len(its)))
            st_i["total_itens"] += qtd
            info = prod_por_id.get(x["pid"]) or prod_por_sku.get(x["sku"])
            if not info or info["criado"] is None:
                continue
            dias = max(0, (dt_venda - info["criado"]).days)
            if dias <= 7:
                fx = "0_7"
            elif dias <= 30:
                fx = "8_30"
            elif dias <= 90:
                fx = "31_90"
            else:
                fx = "mais_90"
            st_i["itens_com_cad"] += qtd
            st_i["rec_com_cad"] += rec_item
            st_i["qtd"][fx] += qtd
            st_i["rec"][fx] += rec_item

            if info["tipo"] == "usado" and not info["ilimitado"] and info["estoque"] <= 1:
                dias_venda_usado_sem.setdefault(sem, []).extend([dias] * qtd)
            elif info["tipo"] == "novo":
                dias_venda_novo_sem.setdefault(sem, []).extend([dias] * qtd)

    # 4. Meta Ads gasto por semana
    meta_por_sem: dict[date, float] = {}
    if anuncios_campanha_dia_df is not None and not anuncios_campanha_dia_df.empty:
        for r in anuncios_campanha_dia_df.to_dict("records"):
            dt_ad = _para_data(r.get("data"))
            if dt_ad is None:
                continue
            val = _parse_num(r.get("investido_real")) or _parse_num(r.get("investido"))
            sem_ad = _segunda(dt_ad)
            meta_por_sem[sem_ad] = meta_por_sem.get(sem_ad, 0.0) + val

    # 5. Grade semanal (segunda a domingo) desde julho/2025 (ou início dos dados se posterior)
    sem_fim_atual = _segunda(hoje_date)
    if primeira_data is None:
        sem_inicio = INICIO_ANALISE
    else:
        sem_inicio = max(INICIO_ANALISE, _segunda(primeira_data))
        if sem_inicio > sem_fim_atual:
            sem_inicio = sem_fim_atual

    semanas: list[dict[str, Any]] = []
    cur = sem_inicio
    while cur <= sem_fim_atual:
        fim_cur = cur + timedelta(days=6)
        completa = fim_cur < hoje_date
        cad = criacoes_por_sem.get(cur, 0)
        ps = ped_por_sem.get(cur, {"pedidos": 0, "receita": 0.0, "cupons_promo": set()})
        is_ = itens_sem.get(cur, {"total_itens": 0, "itens_com_cad": 0, "rec_com_cad": 0.0,
                                   "qtd": {f: 0 for f in faixas_nomes}, "rec": {f: 0.0 for f in faixas_nomes}})
        itens_tot = is_["total_itens"]
        i_cad = is_["itens_com_cad"]
        r_cad = is_["rec_com_cad"]

        motivos = []
        if cur in manuais_promo:
            motivos.append("manual (Configuração)")
        if ps["cupons_promo"]:
            motivos.append("cupom: " + ", ".join(sorted(ps["cupons_promo"])[:3]))
        promo_flag = 1 if motivos else 0

        du = dias_venda_usado_sem.get(cur, [])
        dn = dias_venda_novo_sem.get(cur, [])

        pct_i = {f: round(is_["qtd"][f] / i_cad * 100.0, 1) if i_cad > 0 else None for f in faixas_nomes}
        pct_r = {f: round(is_["rec"][f] / r_cad * 100.0, 1) if r_cad > 0 else None for f in faixas_nomes}

        semanas.append({
            "semana_inicio": cur.isoformat(),
            "semana_fim": fim_cur.isoformat(),
            "completa": completa,
            "discos_cadastrados": int(cad),
            "pedidos": int(ps["pedidos"]),
            "itens_vendidos": int(itens_tot),
            "receita": round(float(ps["receita"]), 2),
            "gasto_meta": round(float(meta_por_sem.get(cur, 0.0)), 2),
            "promocao": promo_flag,
            "motivo_promocao": "; ".join(motivos),
            "pct_itens_0_7": pct_i["0_7"],
            "pct_itens_8_30": pct_i["8_30"],
            "pct_itens_31_90": pct_i["31_90"],
            "pct_itens_mais_90": pct_i["mais_90"],
            "pct_rec_0_7": pct_r["0_7"],
            "pct_rec_8_30": pct_r["8_30"],
            "pct_rec_31_90": pct_r["31_90"],
            "pct_rec_mais_90": pct_r["mais_90"],
            "mediana_dias_usado": round(float(np.median(du)), 1) if du else None,
            "mediana_dias_novo": round(float(np.median(dn)), 1) if dn else None,
            "_raw_qtd": is_["qtd"],
            "_raw_rec": is_["rec"],
            "_raw_i_cad": i_cad,
            "_raw_r_cad": r_cad,
            "_raw_du": du,
            "_raw_dn": dn,
        })
        cur += timedelta(days=7)

    # 6. Agregados das últimas 12 semanas completas e tempo até vender
    completas_list = [s for s in semanas if s["completa"]]
    ultimas_12 = completas_list[-12:] if len(completas_list) >= 1 else semanas[-12:]
    tot_i_12 = sum(s["_raw_i_cad"] for s in ultimas_12)
    tot_r_12 = sum(s["_raw_r_cad"] for s in ultimas_12)
    faixas_12 = {}
    for f in faixas_nomes:
        q_f = sum(s["_raw_qtd"][f] for s in ultimas_12)
        r_f = sum(s["_raw_rec"][f] for s in ultimas_12)
        faixas_12[f] = {
            "pct_itens": round(q_f / tot_i_12 * 100.0, 1) if tot_i_12 > 0 else None,
            "pct_receita": round(r_f / tot_r_12 * 100.0, 1) if tot_r_12 > 0 else None,
        }
    rec_menos_30_12 = (
        round((sum(s["_raw_rec"]["0_7"] + s["_raw_rec"]["8_30"] for s in ultimas_12) / tot_r_12) * 100.0, 1)
        if tot_r_12 > 0 else None
    )
    itens_menos_30_12 = (
        round((sum(s["_raw_qtd"]["0_7"] + s["_raw_qtd"]["8_30"] for s in ultimas_12) / tot_i_12) * 100.0, 1)
        if tot_i_12 > 0 else None
    )

    todos_du = [d for s in completas_list for d in s["_raw_du"]] or [d for s in semanas for d in s["_raw_du"]]
    todos_dn = [d for s in completas_list for d in s["_raw_dn"]] or [d for s in semanas for d in s["_raw_dn"]]
    du_12 = [d for s in ultimas_12 for d in s["_raw_du"]]
    dn_12 = [d for s in ultimas_12 for d in s["_raw_dn"]]

    def _stats_dias(vals: list[int]) -> dict[str, Any]:
        if not vals:
            return {"n": 0, "mediana": None, "p25": None, "p75": None}
        arr = np.asarray(vals, dtype=float)
        return {
            "n": int(len(vals)),
            "mediana": round(float(np.median(arr)), 1),
            "p25": round(float(np.percentile(arr, 25)), 1),
            "p75": round(float(np.percentile(arr, 75)), 1),
        }

    tempo_venda = {
        "usado_estoque_1": _stats_dias(todos_du),
        "novo_lacrado": _stats_dias(todos_dn),
        "ultimas_12_semanas": {
            "usado_estoque_1": _stats_dias(du_12),
            "novo_lacrado": _stats_dias(dn_12),
        },
    }

    # 7. Correlações (todas vs sem promoção) e regressão múltipla
    correlacao = {
        "todas": correlacoes_por_defasagem(semanas, sem_promocao=False),
        "sem_promocao": correlacoes_por_defasagem(semanas, sem_promocao=True),
    }
    regressao = {
        "pedidos": ajustar_regressao(semanas, alvo="pedidos"),
        "receita": ajustar_regressao(semanas, alvo="receita"),
    }

    # 8. Resumo em uma frase no topo
    n_sem_comp = len(completas_list)
    reg_ped = regressao["pedidos"]
    ef_seg = reg_ped.get("efeito_10_seguinte")
    if rec_menos_30_12 is not None:
        parte1 = f"Nas últimas {len(ultimas_12)} semanas, {rec_menos_30_12:.0f}% da receita veio de discos cadastrados há menos de 30 dias."
    else:
        parte1 = f"Série desde {semanas[0]['semana_inicio']} com {len(semanas)} semana(s) registradas."
    if reg_ped.get("disponivel") and ef_seg is not None:
        sinal = "+" if ef_seg >= 0 else ""
        parte2 = f"Cada 10 discos cadastrados se associam a {sinal}{ef_seg:.1f} pedidos na semana seguinte (controlando promoção e Meta)."
    else:
        parte2 = f"Ainda com {n_sem_comp} semana(s) completa(s) para estimar o efeito por regressão."
    resumo_frase = f"{parte1} {parte2}"

    # Remove campos auxiliares privados antes de devolver
    semanas_limpas = [{k: v for k, v in s.items() if not k.startswith("_")} for s in semanas]

    return {
        "atualizado_em": atualizado_em,
        "inicio": semanas_limpas[0]["semana_inicio"] if semanas_limpas else INICIO_ANALISE.isoformat(),
        "total_semanas": len(semanas_limpas),
        "semanas_completas": n_sem_comp,
        "semanas_promocao": int(sum(s["promocao"] for s in semanas_limpas)),
        "resumo_frase": resumo_frase,
        "ultimas_12": {
            "n_semanas": len(ultimas_12),
            "itens_analisados": int(tot_i_12),
            "receita_analisada": round(float(tot_r_12), 2),
            "pct_itens_menos_30d": itens_menos_30_12,
            "pct_rec_menos_30d": rec_menos_30_12,
            "faixas": faixas_12,
        },
        "tempo_venda": tempo_venda,
        "correlacao": correlacao,
        "regressao": regressao,
        "semanas": semanas_limpas,
    }
