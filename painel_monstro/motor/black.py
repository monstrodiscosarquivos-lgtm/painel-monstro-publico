"""Cálculos da Black Monstro 2026 e premissas de margem."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, date
import json
import re
from typing import Any
import pandas as pd


@dataclass
class PremissasMargem:
    margem_usado: float = 0.60
    margem_lacrado: float = 0.15
    custos_sobre_venda: float = 0.124  # 12.4% (taxas + remuneração)
    custo_pedido: float = 8.0  # embalagem + frete por pedido
    aliquota_imposto: float = 0.063


def _parse_num(val: Any) -> float:
    if val is None or val == "":
        return 0.0
    s = str(val).strip().replace("R$", "").replace("%", "").strip()
    if not s:
        return 0.0
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except Exception:
        return 0.0


def carregar_premissas_margem(valores_margem_premissas: list[list[str]] | None = None) -> PremissasMargem:
    """Extrai premissas da coluna F da aba margem_premissas se fornecida."""
    if not valores_margem_premissas or len(valores_margem_premissas) < 4:
        return PremissasMargem()

    p = PremissasMargem()
    try:
        # Linha 5: item 1 (Usados)
        # Linha 6: item 2 (Lacrados nacionais)
        # Linha 12: item 8 (Taxa pagamento)
        # Linha 13: item 9 (Remuneração marketing)
        # Linha 16: item 12 (Imposto)
        # Linha 34: Custos sobre a venda total
        # Linha 35: Custo por pedido
        for r in valores_margem_premissas:
            if len(r) < 6:
                continue
            item_num = str(r[0]).strip()
            item_desc = str(r[1]).strip().lower()
            val_f = str(r[5]).strip()

            if item_num == "1" or "discos usados" in item_desc:
                v = _parse_num(val_f)
                if v > 0:
                    p.margem_usado = v / 100.0 if v > 1.0 else v
            elif item_num == "2" or "lacrados nacionais" in item_desc:
                v = _parse_num(val_f)
                if v > 0:
                    p.margem_lacrado = v / 100.0 if v > 1.0 else v
            elif "custos sobre a venda" in item_desc:
                v = _parse_num(val_f)
                if v > 0:
                    p.custos_sobre_venda = v / 100.0 if v > 1.0 else v
            elif "custo por pedido" in item_desc:
                v = _parse_num(val_f)
                if v > 0:
                    p.custo_pedido = v
            elif item_num == "12" or "alíquota efetiva" in item_desc:
                v = _parse_num(val_f)
                if v > 0:
                    p.aliquota_imposto = v / 100.0 if v > 1.0 else v
    except Exception:
        pass
    return p


def classificar_tipo_produto(categorias: str) -> str:
    """Classifica um produto como 'usado' ou 'lacrado' pela categoria."""
    cat_lower = str(categorias or "").lower()
    if "usad" in cat_lower:
        return "usado"
    if "novo" in cat_lower or "lacrad" in cat_lower:
        return "lacrado"
    return "usado"


def calcular_black(
    pedidos_df: pd.DataFrame,
    itens_df: pd.DataFrame,
    produtos_df: pd.DataFrame,
    anuncios_campanha_dia_df: pd.DataFrame | None = None,
    cadastro_rascunhos_df: pd.DataFrame | None = None,
    config_params: dict[str, str] | None = None,
    premissas: PremissasMargem | None = None,
    vip_inscritos_total: int = 0,
    vip_entradas_por_dia: dict[str, int] | None = None,
    emails_vip: set[str] | None = None,
    hoje_str: str = "2026-11-11",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Calcula as tabelas black_dia e black_resumo."""
    if premissas is None:
        premissas = PremissasMargem()
    if config_params is None:
        config_params = {}
    if vip_entradas_por_dia is None:
        vip_entradas_por_dia = {}
    if emails_vip is None:
        emails_vip = set()

    # Parâmetros de data
    dt_antecipa = config_params.get("Black: início do Antecipa", "2026-11-10").strip()
    dt_vip = config_params.get("Black: acesso Lado A", config_params.get("Black: acesso VIP", "2026-11-26")).strip()
    dt_inicio = config_params.get("Black: início", "2026-11-27").strip()
    dt_fim = config_params.get("Black: fim", "2026-11-30").strip()

    meta_mes = _parse_num(config_params.get("Black: meta do mês", "50000"))
    meta_esticada = _parse_num(config_params.get("Black: meta esticada do mês", "60000"))
    meta_antecipa_dia = _parse_num(config_params.get("Black: meta diária do Antecipa", "870"))
    metas_finais_str = config_params.get("Black: metas diárias de 26 a 30/11", "5000, 8000, 7000, 7000, 5000")
    piso_black = _parse_num(config_params.get("Black: piso da Black", "24000"))
    metas_finais = [_parse_num(x) for x in metas_finais_str.split(",") if x.strip()]
    while len(metas_finais) < 5:
        metas_finais.append(0.0)

    metas_por_dia = {}
    # Datas de 2026-11-10 até 2026-11-30
    datas_periodo = [d.strftime("%Y-%m-%d") for d in pd.date_range("2026-11-10", "2026-11-30")]
    for d in datas_periodo:
        if d < "2026-11-26":
            metas_por_dia[d] = meta_antecipa_dia
        elif d == "2026-11-26":
            metas_por_dia[d] = metas_finais[0]
        elif d == "2026-11-27":
            metas_por_dia[d] = metas_finais[1]
        elif d == "2026-11-28":
            metas_por_dia[d] = metas_finais[2]
        elif d == "2026-11-29":
            metas_por_dia[d] = metas_finais[3]
        elif d == "2026-11-30":
            metas_por_dia[d] = metas_finais[4]
        else:
            metas_por_dia[d] = 0.0

    # Cupons oficiais
    cupons_str = config_params.get("Black: cupons", "ANTECIPA10, LADOA15, LADOA20, LADOA30, BLACK15, BLACK20, BLACK30")
    cupons_oficiais = {c.strip().upper() for c in cupons_str.split(",") if c.strip()}
    prefixo_ads = config_params.get("Black: prefixo das campanhas de anúncio", "black26_").strip().lower()

    # Mapeamento produto_id -> categoria
    prod_cat_map = {}
    if produtos_df is not None and not produtos_df.empty:
        id_col = "id" if "id" in produtos_df.columns else produtos_df.columns[0]
        cat_col = "categorias" if "categorias" in produtos_df.columns else "categoria"
        for _, r in produtos_df.iterrows():
            pid = str(r.get(id_col, "")).strip()
            cat = str(r.get(cat_col, "")).strip()
            if pid:
                prod_cat_map[pid] = cat

    # Mapeamento produto_id -> lote_black
    lote_black_map = {}
    rascunhos_por_lote_count = {}
    if cadastro_rascunhos_df is not None and not cadastro_rascunhos_df.empty:
        col_lote = "lote_black" if "lote_black" in cadastro_rascunhos_df.columns else ""
        col_pid = "produto_id" if "produto_id" in cadastro_rascunhos_df.columns else ""
        if col_lote and col_pid:
            for _, r in cadastro_rascunhos_df.iterrows():
                lb = str(r.get(col_lote, "")).strip()
                pid = str(r.get(col_pid, "")).strip()
                if lb in ["26/11", "27/11", "28/11", "29/11"]:
                    rascunhos_por_lote_count[lb] = rascunhos_por_lote_count.get(lb, 0) + 1
                    if pid:
                        lote_black_map[pid] = lb

    # Processar Pedidos 2026 válidos
    df_p = pedidos_df.copy() if pedidos_df is not None else pd.DataFrame()
    if not df_p.empty:
        df_p["dt"] = df_p["data"].astype(str).str.slice(0, 10)
        df_p["valido_bool"] = df_p["valido"].astype(str).str.upper() == "TRUE"
        df_p["total_num"] = df_p["total"].apply(_parse_num)
        df_p["subtotal_num"] = df_p["subtotal"].apply(_parse_num)
        df_p["desconto_num"] = df_p["desconto"].apply(_parse_num)
        df_p["cupom_clean"] = df_p["cupom"].astype(str).str.strip().str.upper()
    else:
        df_p = pd.DataFrame(columns=["numero", "email", "data", "dt", "valido_bool", "total_num", "subtotal_num", "desconto_num", "cupom_clean"])

    # Pedidos do período da Black 2026
    p_periodo = df_p[(df_p["dt"] >= "2026-11-10") & (df_p["dt"] <= "2026-11-30") & df_p["valido_bool"]]

    # Processar Itens
    df_i = itens_df.copy() if itens_df is not None else pd.DataFrame()
    if not df_i.empty:
        df_i["dt"] = df_i["data"].astype(str).str.slice(0, 10)
        df_i["valido_bool"] = df_i["valido"].astype(str).str.upper() == "TRUE"
        df_i["valor_num"] = df_i["valor"].apply(_parse_num)
        df_i["qtd_num"] = df_i["quantidade"].apply(lambda x: int(float(_parse_num(x))) if _parse_num(x) else 1)
        df_i["pid_str"] = df_i["produto_id"].astype(str).str.strip()
        df_i["tipo_prod"] = df_i["pid_str"].map(lambda pid: classificar_tipo_produto(prod_cat_map.get(pid, "")))
    else:
        df_i = pd.DataFrame(columns=["numero", "produto", "dt", "valido_bool", "valor_num", "qtd_num", "pid_str", "tipo_prod"])

    # Itens válidos do período
    numeros_validos_periodo = set(p_periodo["numero"])
    i_periodo = df_i[df_i["numero"].isin(numeros_validos_periodo)]

    # Anúncios
    df_ads = anuncios_campanha_dia_df.copy() if anuncios_campanha_dia_df is not None else pd.DataFrame()
    ads_por_dia = {}
    if not df_ads.empty:
        df_ads["dt"] = df_ads["data"].astype(str).str.slice(0, 10)
        df_ads["investido_num"] = df_ads["investido_real"].apply(_parse_num)
        df_ads["receita_num"] = df_ads["receita"].apply(_parse_num)
        df_ads["campanha_clean"] = df_ads["campanha"].astype(str).str.lower().str.strip()

        # Filtro: prefixo da Black (ex. black26_) OU prosp_vendas_recorrente
        mask_camp = df_ads["campanha_clean"].str.startswith(prefixo_ads) | (df_ads["campanha_clean"] == "prosp_vendas_recorrente")
        ads_black = df_ads[mask_camp & (df_ads["dt"] >= "2026-11-10") & (df_ads["dt"] <= "2026-11-30")]

        for dt, g in ads_black.groupby("dt"):
            inv = g["investido_num"].sum()
            rec = g["receita_num"].sum()
            ads_por_dia[dt] = {
                "investido": inv,
                "receita": rec,
                "roas": (rec / inv) if inv > 0 else 0.0,
            }

    # 1. Montar black_dia (linhas para cada dia de 10 a 30/11)
    linhas_dia = []
    fat_acum = 0.0
    ped_acum = 0
    meta_acum = 0.0
    sobra_acum = 0.0

    for d in datas_periodo:
        # Fase
        if d < "2026-11-26":
            fase = "Antecipa"
        elif d == "2026-11-26":
            fase = "Lado A"
        elif d <= "2026-11-29":
            fase = "Black"
        else:
            fase = "Cyber"

        ped_dia = p_periodo[p_periodo["dt"] == d]
        n_ped = len(ped_dia)
        fat_dia = ped_dia["total_num"].sum()
        subt_dia = ped_dia["subtotal_num"].sum()
        desc_dia = ped_dia["desconto_num"].sum()
        ticket_dia = (fat_dia / n_ped) if n_ped > 0 else 0.0

        meta_d = metas_por_dia.get(d, 0.0)
        pct_meta = (fat_dia / meta_d * 100.0) if meta_d > 0 else 0.0

        # Lucro estimado
        # Custo do disco nos itens deste dia
        itens_d = i_periodo[i_periodo["dt"] == d]
        # Usados: margem 60% -> custo = venda * (1 - 0.60) = venda * 0.40
        # Lacrados: margem 15% -> custo = venda * (1 - 0.15) = venda * 0.85
        custo_disco_dia = 0.0
        venda_usado = 0.0
        venda_lacrado = 0.0
        for _, it in itens_d.iterrows():
            val = it["valor_num"] * it["qtd_num"]
            if it["tipo_prod"] == "usado":
                venda_usado += val
                custo_disco_dia += val * (1.0 - premissas.margem_usado)
            else:
                venda_lacrado += val
                custo_disco_dia += val * (1.0 - premissas.margem_lacrado)

        # Custos sobre a venda
        custos_venda_dia = fat_dia * premissas.custos_sobre_venda
        # Custo por pedido
        custo_ped_dia = n_ped * premissas.custo_pedido
        # Anúncios do dia
        ad_info = ads_por_dia.get(d, {"investido": 0.0, "receita": 0.0, "roas": 0.0})
        gasto_ad_dia = ad_info["investido"]

        sobra_dia = fat_dia - custo_disco_dia - custos_venda_dia - gasto_ad_dia

        # Se for no futuro (data > hoje_str) e não houver pedidos, zera sobra
        if d > hoje_str and n_ped == 0:
            sobra_dia = 0.0

        fat_acum += fat_dia
        ped_acum += n_ped
        meta_acum += meta_d
        sobra_acum += sobra_dia

        linhas_dia.append({
            "data": d,
            "fase": fase,
            "faturamento": round(fat_dia, 2),
            "pedidos": n_ped,
            "ticket_medio": round(ticket_dia, 2),
            "meta_dia": round(meta_d, 2),
            "atingimento_pct": round(pct_meta, 1),
            "faturamento_acum": round(fat_acum, 2),
            "meta_acum": round(meta_acum, 2),
            "custo_disco": round(custo_disco_dia, 2),
            "custos_venda": round(custos_venda_dia, 2),
            "gasto_anuncio": round(gasto_ad_dia, 2),
            "sobra_dia": round(sobra_dia, 2),
            "sobra_acum": round(sobra_acum, 2),
            "roas_anuncio": round(ad_info["roas"], 2),
        })

    df_black_dia = pd.DataFrame(linhas_dia)

    # 2. Análise por cupom
    cupons_stats = {}
    for _, p in p_periodo.iterrows():
        c = p["cupom_clean"] or "SEM_CUPOM"
        if c not in cupons_stats:
            cupons_stats[c] = {"pedidos": 0, "faturamento": 0.0, "desconto": 0.0}
        cupons_stats[c]["pedidos"] += 1
        cupons_stats[c]["faturamento"] += p["total_num"]
        cupons_stats[c]["desconto"] += p["desconto_num"]

    cupons_lista = []
    for c, st in cupons_stats.items():
        tm = (st["faturamento"] / st["pedidos"]) if st["pedidos"] > 0 else 0.0
        cupons_lista.append({
            "cupom": c,
            "pedidos": st["pedidos"],
            "faturamento": round(st["faturamento"], 2),
            "desconto": round(st["desconto"], 2),
            "ticket_medio": round(tm, 2),
            "oficial": c in cupons_oficiais,
        })
    cupons_lista.sort(key=lambda x: x["faturamento"], reverse=True)

    # 3. Lista VIP e conversão em 26/11
    vip_compradores_26 = 0
    if emails_vip:
        p_26 = p_periodo[p_periodo["dt"] == "2026-11-26"]
        compradores_26 = set(p_26["email"].astype(str).str.lower().str.strip())
        vip_compradores_26 = len(compradores_26.intersection(emails_vip))

    # 4. Comparação com 2025 (Black 2025: 28 a 30/11/2025)
    bf25 = df_p[(df_p["dt"] >= "2025-11-28") & (df_p["dt"] <= "2025-11-30") & df_p["valido_bool"]]
    bf25_pedidos = len(bf25)
    bf25_faturamento = bf25["total_num"].sum()
    bf25_ticket = (bf25_faturamento / bf25_pedidos) if bf25_pedidos > 0 else 0.0

    # Black 2026 correspondente: 27 a 30/11/2026 (sexta a segunda)
    bf26 = p_periodo[(p_periodo["dt"] >= "2026-11-27") & (p_periodo["dt"] <= "2026-11-30")]
    bf26_pedidos = len(bf26)
    bf26_faturamento = bf26["total_num"].sum()
    bf26_ticket = (bf26_faturamento / bf26_pedidos) if bf26_pedidos > 0 else 0.0

    # 5. Top 20 discos vendidos no período
    top_discos = []
    if not i_periodo.empty:
        g_prod = i_periodo.groupby("produto").agg({"qtd_num": "sum", "valor_num": "sum"}).reset_index()
        g_prod["faturamento"] = g_prod["qtd_num"] * g_prod["valor_num"]
        g_prod = g_prod.sort_values(by="qtd_num", ascending=False).head(20)
        for _, r in g_prod.iterrows():
            top_discos.append({
                "produto": r["produto"],
                "quantidade": int(r["qtd_num"]),
                "faturamento": round(float(r["faturamento"]), 2),
            })

    # 6. Desempenho Lote Black
    lotes_black_stats = {}
    for lb in ["26/11", "27/11", "28/11", "29/11"]:
        total_cad = rascunhos_por_lote_count.get(lb, 0)
        lotes_black_stats[lb] = {
            "lote": lb,
            "cadastrados": total_cad,
            "vendidos": 0,
            "faturamento": 0.0,
            "restantes": total_cad,
        }

    # Cruzar com itens vendidos que tenham pid mapeado para lote_black
    for _, it in i_periodo.iterrows():
        pid = it["pid_str"]
        if pid in lote_black_map:
            lb = lote_black_map[pid]
            if lb in lotes_black_stats:
                qtd = it["qtd_num"]
                val = it["valor_num"] * qtd
                lotes_black_stats[lb]["vendidos"] += qtd
                lotes_black_stats[lb]["faturamento"] += val
                lotes_black_stats[lb]["restantes"] = max(0, lotes_black_stats[lb]["cadastrados"] - lotes_black_stats[lb]["vendidos"])

    lotes_lista = [lotes_black_stats[lb] for lb in ["26/11", "27/11", "28/11", "29/11"]]

    # 7. Alertas
    alertas = []
    # Alerta Antecipa em 17/11 (abaixo de R$ 650 por dia)
    if hoje_str >= "2026-11-17":
        dias_ant = [d for d in datas_periodo if d < "2026-11-26" and d <= hoje_str]
        fat_ant = df_black_dia[df_black_dia["data"].isin(dias_ant)]["faturamento"].sum()
        media_ant = (fat_ant / len(dias_ant)) if dias_ant else 0.0
        if media_ant < 650.0:
            alertas.append({
                "tipo": "antecipa_ritmo",
                "nivel": "alerta",
                "mensagem": f"Antecipa abaixo do ritmo (média de R$ {media_ant:.2f}/dia, piso R$ 650/dia): reforçar email, WhatsApp e novidades, sem aumentar o desconto.",
                "media_atual": round(media_ant, 2),
            })

    # Alerta Ticket médio na Black (< 230)
    if hoje_str >= "2026-11-26":
        linha_hj = df_black_dia[df_black_dia["data"] == hoje_str]
        if not linha_hj.empty:
            tm_hj = float(linha_hj["ticket_medio"].iloc[0])
            n_ped_hj = int(linha_hj["pedidos"].iloc[0])
            if n_ped_hj > 0 and tm_hj < 230.0:
                alertas.append({
                    "tipo": "ticket_baixo",
                    "nivel": "aviso",
                    "mensagem": f"Ticket médio de hoje (R$ {tm_hj:.2f}) está abaixo de R$ 230: estimular kits e frete grátis.",
                    "ticket_medio": round(tm_hj, 2),
                })

    # Resumo Geral
    # Placar de hoje
    linha_hoje = df_black_dia[df_black_dia["data"] == hoje_str]
    hoje_fat = float(linha_hoje["faturamento"].iloc[0]) if not linha_hoje.empty else 0.0
    hoje_ped = int(linha_hoje["pedidos"].iloc[0]) if not linha_hoje.empty else 0
    hoje_ticket = float(linha_hoje["ticket_medio"].iloc[0]) if not linha_hoje.empty else 0.0
    hoje_meta = float(linha_hoje["meta_dia"].iloc[0]) if not linha_hoje.empty else 0.0
    hoje_atingimento = (hoje_fat / hoje_meta * 100.0) if hoje_meta > 0 else 0.0

    resumo = {
        "atualizado_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "hoje_data": hoje_str,
        "hoje_faturamento": round(hoje_fat, 2),
        "hoje_pedidos": hoje_ped,
        "hoje_ticket_medio": round(hoje_ticket, 2),
        "hoje_meta": round(hoje_meta, 2),
        "hoje_atingimento_pct": round(hoje_atingimento, 1),
        "periodo_faturamento": round(fat_acum, 2),
        "periodo_pedidos": ped_acum,
        "periodo_ticket_medio": round((fat_acum / ped_acum) if ped_acum > 0 else 0.0, 2),
        "meta_mes": round(meta_mes, 2),
        "meta_esticada": round(meta_esticada, 2),
        "piso_black": round(piso_black, 2),
        "atingimento_mes_pct": round(float(fat_acum / meta_mes * 100.0) if meta_mes > 0 else 0.0, 1),
        "atingimento_esticada_pct": round(float(fat_acum / meta_esticada * 100.0) if meta_esticada > 0 else 0.0, 1),
        "acima_do_piso": bool(fat_acum >= piso_black),
        "diferenca_piso": round(float(fat_acum - piso_black), 2),
        "sobra_total": round(sobra_acum, 2),
        "cupons": cupons_lista,
        "lado_a": {
            "total_inscritos": vip_inscritos_total,
            "entradas_por_dia": vip_entradas_por_dia,
            "compraram_dia_26": vip_compradores_26,
        },
        "vip": {
            "total_inscritos": vip_inscritos_total,
            "entradas_por_dia": vip_entradas_por_dia,
            "compraram_dia_26": vip_compradores_26,
        },
        "comparacao_2025": {
            "bf25_pedidos": bf25_pedidos,
            "bf25_faturamento": round(bf25_faturamento, 2),
            "bf25_ticket": round(bf25_ticket, 2),
            "bf26_pedidos": bf26_pedidos,
            "bf26_faturamento": round(bf26_faturamento, 2),
            "bf26_ticket": round(bf26_ticket, 2),
        },
        "top_discos": top_discos,
        "lotes_black": lotes_lista,
        "alertas": alertas,
        "premissas_usadas": {
            "margem_usado": premissas.margem_usado,
            "margem_lacrado": premissas.margem_lacrado,
            "custos_sobre_venda": premissas.custos_sobre_venda,
            "custo_pedido": premissas.custo_pedido,
        },
    }

    return df_black_dia, resumo
