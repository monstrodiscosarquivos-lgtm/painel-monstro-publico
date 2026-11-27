"""Cálculos da Black Monstro 2026 e premissas de margem."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
import json
import re
from typing import Any
import pandas as pd


BLACK_2026_DIAS = (
    ("D0", "Quinta", "2026-11-26"),
    ("D1", "Sexta", "2026-11-27"),
    ("D2", "Sábado", "2026-11-28"),
    ("D3", "Domingo", "2026-11-29"),
    ("D4", "Segunda", "2026-11-30"),
)
BLACK_2025_DIAS = (
    ("D0", "Quinta", "2025-11-27"),
    ("D1", "Sexta", "2025-11-28"),
    ("D2", "Sábado", "2025-11-29"),
    ("D3", "Domingo", "2025-11-30"),
    ("D4", "Segunda", "2025-12-01"),
)
CUPONS_BLACK_2026 = (
    "BLACK25", "BLACK30", "BLACK35",
    "Lado A 25%", "Lado A 30%", "Lado A 35%",
    "Grupo VIP 25%", "Grupo VIP 30%", "Grupo VIP 35%",
    "ANTECIPA10", "Sem cupom",
)
CUPONS_PRIVADOS_MAP = {
    "SULCO25": "Lado A 25%",
    "SULCO30": "Lado A 30%",
    "SULCO35": "Lado A 35%",
    "GRUPO25": "Grupo VIP 25%",
    "GRUPO30": "Grupo VIP 30%",
    "GRUPO35": "Grupo VIP 35%",
}
DIAS_SEMANA_PT = ("Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo")
CAMPANHAS_BLACK_META = (
    "black26_rmk",
    "prosp_vendas_recorrente",
    "black26_loja_fisica_2811",
)
CONFIG_MARGEM_USADO = "Black: margem do usado"
CONFIG_MARGEM_LACRADO = "Black: margem do lacrado"
LIMITE_FORA_CURVA_TETO = 1500.0


@dataclass
class PremissasMargem:
    margem_usado: float = 0.60
    margem_lacrado: float = 0.40
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


def carregar_premissas_margem(
    valores_margem_premissas: list[list[str]] | None = None,
    config_params: dict[str, Any] | None = None,
) -> PremissasMargem:
    """Lê margens da Configuração ('Black: margem do usado' e 'Black: margem do lacrado'; padrão 60% e 40%)
    e aplica a aba margem_premissas por cima, se existir (margem_premissas tem prioridade)."""
    p = PremissasMargem()

    if config_params:
        cfg_lower = {str(k).strip().lower(): v for k, v in config_params.items()}
        for chave, attr in (
            (CONFIG_MARGEM_USADO.lower(), "margem_usado"),
            (CONFIG_MARGEM_LACRADO.lower(), "margem_lacrado"),
        ):
            if chave in cfg_lower:
                v = _parse_num(cfg_lower[chave])
                if v > 0:
                    setattr(p, attr, v / 100.0 if v > 1.0 else v)

    if not valores_margem_premissas or len(valores_margem_premissas) < 4:
        return p

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
        premissas = carregar_premissas_margem(None, config_params)
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


# ----------------------------------------------------------------------------
# Black 2026 · 5 blocos (aba "Black" da planilha e seção Black 2026 no Painel)
# ----------------------------------------------------------------------------
def _parse_data_cfg(valor: Any, padrao: str) -> str:
    """Aceita YYYY-MM-DD ou DD/MM/YYYY da aba Configuração; devolve YYYY-MM-DD."""
    s = str(valor or "").strip()
    if not s:
        return padrao
    m_iso = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m_iso:
        return f"{m_iso.group(1)}-{m_iso.group(2)}-{m_iso.group(3)}"
    m_br = re.match(r"^(\d{2})/(\d{2})/(\d{4})", s)
    if m_br:
        return f"{m_br.group(3)}-{m_br.group(2)}-{m_br.group(1)}"
    return padrao


def montar_calendario_black(config_params: dict[str, Any] | None = None) -> tuple[list[tuple[str, str, str]], list[tuple[str, str, str]], tuple[str, str]]:
    """Monta (dias_2026, dias_2025, (antecipa_ini, antecipa_fim)) a partir da aba Configuração."""
    cfg = config_params or {}
    cfg_lower = {str(k).strip().lower(): v for k, v in cfg.items()}
    dt_d0 = _parse_data_cfg(
        cfg_lower.get("black: acesso lado a", cfg_lower.get("black: acesso vip", "")),
        "2026-11-26",
    )
    dt_inicio = _parse_data_cfg(cfg_lower.get("black: início", cfg_lower.get("black: inicio", "")), "2026-11-27")
    dt_fim = _parse_data_cfg(cfg_lower.get("black: fim", ""), "2026-11-30")

    d0_date = date.fromisoformat(dt_d0)
    ini_date = date.fromisoformat(dt_inicio)
    fim_date = date.fromisoformat(dt_fim)
    if d0_date > ini_date:
        d0_date = ini_date
    if fim_date < ini_date:
        fim_date = ini_date

    dias_26: list[tuple[str, str, str]] = []
    dias_25: list[tuple[str, str, str]] = []
    cursor = d0_date
    while cursor <= fim_date:
        offset_inicio = (cursor - ini_date).days
        cod = f"D{offset_inicio + 1}" if offset_inicio >= 0 else f"D{offset_inicio + 1}"  # D0 para 1 dia antes do início
        if cursor < ini_date:
            cod = f"D{0 if (ini_date - cursor).days == 1 else -(ini_date - cursor).days + 1}"
        nome_dia = DIAS_SEMANA_PT[cursor.weekday()]
        dias_26.append((cod, nome_dia, cursor.isoformat()))
        d25 = cursor - timedelta(days=364)  # 52 semanas antes: mesmo dia da semana em 2025
        dias_25.append((cod, DIAS_SEMANA_PT[d25.weekday()], d25.isoformat()))
        cursor += timedelta(days=1)

    ant_ini = _parse_data_cfg(cfg_lower.get("black: início do antecipa", cfg_lower.get("black: inicio do antecipa", "")), "2026-11-12")
    ant_fim_default = (d0_date - timedelta(days=1)).isoformat()
    ant_fim = _parse_data_cfg(cfg_lower.get("black: fim do antecipa", ""), ant_fim_default)
    return dias_26, dias_25, (ant_ini, ant_fim)


def mascarar_cupom_privado(cupom: str) -> str:
    """Troca códigos privados (SULCO*/GRUPO*) por rótulos públicos ('Lado A 25%', 'Grupo VIP 25%', etc.)."""
    c = str(cupom or "").strip().upper()
    if c in CUPONS_PRIVADOS_MAP:
        return CUPONS_PRIVADOS_MAP[c]
    m_s = re.fullmatch(r"SULCO(\d+)", c)
    if m_s:
        return f"Lado A {m_s.group(1)}%"
    if c.startswith("SULCO"):
        return "Lado A"
    m_g = re.fullmatch(r"GRUPO(\d+)", c)
    if m_g:
        return f"Grupo VIP {m_g.group(1)}%"
    if c.startswith("GRUPO"):
        return "Grupo VIP"
    return cupom


def _normalizar_cupom_black(valor: Any) -> str:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return "Sem cupom"
    texto = str(valor).strip()
    if not texto or texto.upper() in ("NONE", "NAN", "SEM_CUPOM", "SEM CUPOM"):
        return "Sem cupom"
    primeiro = texto.split(",")[0].strip().upper()
    return mascarar_cupom_privado(primeiro) if primeiro else "Sem cupom"


def _preparar_pedidos_black(pedidos_df: pd.DataFrame | None) -> pd.DataFrame:
    if pedidos_df is None or pedidos_df.empty:
        return pd.DataFrame(columns=[
            "numero", "numero_str", "data_ts", "dt", "hora", "valido_bool",
            "subtotal_num", "desconto_num", "total_num", "receita_num", "cupom_norm",
        ])
    df = pedidos_df.copy()
    df["data_ts"] = pd.to_datetime(df["data"], errors="coerce")
    df["dt"] = df["data_ts"].dt.strftime("%Y-%m-%d").fillna(df["data"].astype(str).str.slice(0, 10))
    df["hora"] = df["data_ts"].dt.hour.fillna(0).astype(int)
    df["valido_bool"] = df["valido"].apply(lambda v: v is True or str(v).strip().upper() in ("TRUE", "1", "SIM"))
    df["subtotal_num"] = df["subtotal"].apply(_parse_num) if "subtotal" in df.columns else 0.0
    df["desconto_num"] = df["desconto"].apply(_parse_num) if "desconto" in df.columns else 0.0
    df["total_num"] = df["total"].apply(_parse_num) if "total" in df.columns else 0.0
    # Receita líquida de produtos (já com desconto, sem frete); fallback para total se subtotal vier zerado.
    df["receita_num"] = [
        max(0.0, s - d) if s > 0 else max(0.0, t)
        for s, d, t in zip(df["subtotal_num"], df["desconto_num"], df["total_num"])
    ]
    df["cupom_norm"] = df["cupom"].apply(_normalizar_cupom_black) if "cupom" in df.columns else "Sem cupom"
    df["numero_str"] = df["numero"].astype(str).str.strip()
    return df


def calcular_bloco_cupons(
    df_p: pd.DataFrame,
    hoje_str: str,
    dias_26: list[tuple[str, str, str]] | None = None,
    antecipa_periodo: tuple[str, str] = ("2026-11-12", "2026-11-25"),
) -> dict[str, Any]:
    """Bloco 1: Pedidos pagos por cupom (D0 a D4, por hora hoje, tabela resumo + linha Antecipa e Total geral)."""
    dias_26 = dias_26 or list(BLACK_2026_DIAS)
    datas_26 = [d[2] for d in dias_26]
    p26 = df_p[df_p["valido_bool"] & df_p["dt"].isin(datas_26)].copy()

    def _serie(cupom: str) -> str:
        return cupom if cupom in CUPONS_BLACK_2026 else "Outros"

    if not p26.empty:
        p26["serie"] = p26["cupom_norm"].map(_serie)
    else:
        p26["serie"] = pd.Series(dtype=str)

    series_presentes = [c for c in CUPONS_BLACK_2026 if not p26.empty and (p26["serie"] == c).any()]
    if not p26.empty and (p26["serie"] == "Outros").any():
        series_presentes.append("Outros")
    if not series_presentes:
        series_presentes = list(CUPONS_BLACK_2026)

    por_dia = []
    for codigo, nome_dia, dt in dias_26:
        sub = p26[p26["dt"] == dt]
        contagem = {s: int((sub["serie"] == s).sum()) for s in series_presentes}
        por_dia.append({
            "dia": codigo,
            "rotulo": f"{codigo} · {nome_dia[:3]} {dt[8:10]}/{dt[5:7]}",
            "data": dt,
            "total_pedidos": int(len(sub)),
            "cupons": contagem,
        })

    if hoje_str in datas_26:
        dia_hora = hoje_str
    elif not p26.empty:
        dia_hora = str(p26["dt"].max())
    else:
        dia_hora = datas_26[0]

    sub_hj = p26[p26["dt"] == dia_hora]
    por_hora = []
    for h in range(24):
        sh = sub_hj[sub_hj["hora"] == h]
        contagem = {s: int((sh["serie"] == s).sum()) for s in series_presentes}
        por_hora.append({
            "hora": f"{h:02d}h",
            "hora_num": h,
            "total_pedidos": int(len(sh)),
            "cupons": contagem,
        })

    tabela = []
    if not p26.empty:
        for cupom, grp in p26.groupby("cupom_norm"):
            n = int(len(grp))
            rec = float(grp["receita_num"].sum())
            desc = float(grp["desconto_num"].sum())
            tabela.append({
                "cupom": cupom,
                "pedidos": n,
                "receita": round(rec, 2),
                "ticket_medio": round(rec / n, 2) if n else 0.0,
                "desconto": round(desc, 2),
            })
        ordem_padrao = {c: i for i, c in enumerate(CUPONS_BLACK_2026)}
        tabela.sort(key=lambda r: (ordem_padrao.get(r["cupom"], 999), -r["receita"]))

    # Linha à parte: Antecipa (cupom ANTECIPA10 no período configurado; não entra nos gráficos D0..D4)
    ant_ini, ant_fim = antecipa_periodo
    p_ant = df_p[df_p["valido_bool"] & (df_p["dt"] >= ant_ini) & (df_p["dt"] <= ant_fim) & (df_p["cupom_norm"] == "ANTECIPA10")]
    n_ant = int(len(p_ant))
    rec_ant = float(p_ant["receita_num"].sum()) if n_ant else 0.0
    desc_ant = float(p_ant["desconto_num"].sum()) if n_ant else 0.0
    rot_ant = f"Antecipa ({int(ant_ini[8:10])} a {int(ant_fim[8:10])}/{ant_fim[5:7]})"
    antecipa = {
        "rotulo": rot_ant,
        "inicio": ant_ini,
        "fim": ant_fim,
        "pedidos": n_ant,
        "receita": round(rec_ant, 2),
        "ticket_medio": round(rec_ant / n_ant, 2) if n_ant else 0.0,
        "desconto": round(desc_ant, 2),
    }

    tot_bk_ped = int(len(p26))
    tot_bk_rec = float(p26["receita_num"].sum()) if tot_bk_ped else 0.0
    tot_bk_desc = float(p26["desconto_num"].sum()) if tot_bk_ped else 0.0
    geral_ped = tot_bk_ped + n_ant
    geral_rec = tot_bk_rec + rec_ant
    geral_desc = tot_bk_desc + desc_ant

    return {
        "series": series_presentes,
        "por_dia": por_dia,
        "dia_hora": dia_hora,
        "por_hora_hoje": por_hora,
        "tabela": tabela,
        "total_pedidos": tot_bk_ped,
        "total_receita": round(tot_bk_rec, 2),
        "total_desconto": round(tot_bk_desc, 2),
        "antecipa": antecipa,
        "total_geral": {
            "rotulo": "Antecipa + Black",
            "pedidos": geral_ped,
            "receita": round(geral_rec, 2),
            "ticket_medio": round(geral_rec / geral_ped, 2) if geral_ped else 0.0,
            "desconto": round(geral_desc, 2),
        },
    }


def _var_pct(v26: float | None, v25: float | None) -> float | None:
    if v26 is None or v25 is None or v25 <= 0:
        return None
    return round((v26 - v25) / v25 * 100.0, 1)


def _metricas_dia_comp(sub: pd.DataFrame) -> dict[str, Any]:
    n = int(len(sub))
    rec = float(sub["receita_num"].sum()) if n else 0.0
    desc = float(sub["desconto_num"].sum()) if n else 0.0
    com_cupom = int((sub["cupom_norm"] != "Sem cupom").sum()) if n else 0
    return {
        "pedidos": n,
        "receita": round(rec, 2),
        "ticket_medio": round(rec / n, 2) if n else 0.0,
        "desconto": round(desc, 2),
        "pct_com_cupom": round(com_cupom / n * 100.0, 1) if n else 0.0,
    }


def calcular_bloco_2026_x_2025(
    df_p: pd.DataFrame,
    hoje_str: str,
    dias_26: list[tuple[str, str, str]] | None = None,
    dias_25: list[tuple[str, str, str]] | None = None,
) -> dict[str, Any]:
    """Bloco 2: Comparação D0..D4 (2026 x 2025) e Total D0 a D4. Dias futuros de 2026 ficam em branco (None)."""
    dias_26 = dias_26 or list(BLACK_2026_DIAS)
    dias_25 = dias_25 or list(BLACK_2025_DIAS)
    validos = df_p[df_p["valido_bool"]]
    dias_out = []
    sub_26_total_list = []
    sub_25_total_list = []

    for (cod, nome, dt26), (_, _, dt25) in zip(dias_26, dias_25):
        s25 = validos[validos["dt"] == dt25]
        m25 = _metricas_dia_comp(s25)
        sub_25_total_list.append(s25)

        ocorrido = dt26 <= hoje_str
        if ocorrido:
            s26 = validos[validos["dt"] == dt26]
            m26 = _metricas_dia_comp(s26)
            sub_26_total_list.append(s26)
            variacao = {
                "pedidos_pct": _var_pct(m26["pedidos"], m25["pedidos"]),
                "receita_pct": _var_pct(m26["receita"], m25["receita"]),
                "ticket_pct": _var_pct(m26["ticket_medio"], m25["ticket_medio"]),
                "desconto_pct": _var_pct(m26["desconto"], m25["desconto"]),
                "cupom_pp": round(m26["pct_com_cupom"] - m25["pct_com_cupom"], 1),
            }
        else:
            m26 = None
            variacao = None

        dias_out.append({
            "dia": cod,
            "nome": nome,
            "data_2026": dt26,
            "data_2025": dt25,
            "ocorrido": ocorrido,
            "y2026": m26,
            "y2025": m25,
            "variacao": variacao,
        })

    df25_tot = pd.concat(sub_25_total_list, ignore_index=True) if sub_25_total_list else validos.iloc[0:0]
    m25_tot = _metricas_dia_comp(df25_tot)
    if sub_26_total_list:
        df26_tot = pd.concat(sub_26_total_list, ignore_index=True)
        m26_tot = _metricas_dia_comp(df26_tot)
        var_tot = {
            "pedidos_pct": _var_pct(m26_tot["pedidos"], m25_tot["pedidos"]),
            "receita_pct": _var_pct(m26_tot["receita"], m25_tot["receita"]),
            "ticket_pct": _var_pct(m26_tot["ticket_medio"], m25_tot["ticket_medio"]),
            "desconto_pct": _var_pct(m26_tot["desconto"], m25_tot["desconto"]),
            "cupom_pp": round(m26_tot["pct_com_cupom"] - m25_tot["pct_com_cupom"], 1),
        }
    else:
        m26_tot = None
        var_tot = None

    rotulo_total = f"Total ({dias_26[0][0]} a {dias_26[-1][0]})" if dias_26 else "Total"
    return {
        "dias": dias_out,
        "total": {
            "rotulo": rotulo_total,
            "y2026": m26_tot,
            "y2025": m25_tot,
            "variacao": var_tot,
        },
    }


def avaliar_gatilhos_meta(campanhas_meta: list[dict[str, Any]] | None, atualizado_em: str = "") -> dict[str, Any]:
    """Bloco 3: Regras de ação imediata para campanhas da Black no Meta Ads."""
    acoes: list[dict[str, str]] = []
    linhas: list[dict[str, Any]] = []

    for c in (campanhas_meta or []):
        nome = str(c.get("campanha") or "").strip()
        if not nome:
            continue
        gasto_hoje = _parse_num(c.get("gasto_hoje"))
        gasto_ontem = _parse_num(c.get("gasto_ontem"))
        gasto_3d = _parse_num(c.get("gasto_3d"))
        compras_hoje = int(round(_parse_num(c.get("compras_hoje"))))
        compras_ontem = int(round(_parse_num(c.get("compras_ontem"))))
        compras_3d = int(round(_parse_num(c.get("compras_3d"))))
        receita_hoje = _parse_num(c.get("receita_hoje"))
        receita_3d = _parse_num(c.get("receita_3d"))
        cliques_hoje = _parse_num(c.get("cliques_hoje"))
        cliques_3d = _parse_num(c.get("cliques_3d"))
        freq_hoje = _parse_num(c.get("frequencia_hoje"))
        freq_3d = _parse_num(c.get("frequencia_3d"))
        orcamento_dia = _parse_num(c.get("orcamento_dia"))

        gasto_desde_ontem = gasto_hoje + gasto_ontem
        compras_desde_ontem = compras_hoje + compras_ontem
        roas_hoje = (receita_hoje / gasto_hoje) if gasto_hoje > 0 else None
        roas_3d = (receita_3d / gasto_3d) if gasto_3d > 0 else None
        roas = roas_hoje if gasto_hoje > 0 else roas_3d
        cpc_hoje = (gasto_hoje / cliques_hoje) if cliques_hoje > 0 else None
        cpc_3d = (gasto_3d / cliques_3d) if cliques_3d > 0 else None
        cpc = cpc_hoje if cliques_hoje > 0 else cpc_3d
        frequencia = max(freq_hoje, freq_3d)

        # Gatilho 1: frequência de campanha de remarketing (nome contém rmk) acima de 4
        if "rmk" in nome.lower() and frequencia > 4.0:
            acoes.append({
                "campanha": nome,
                "regra": "frequencia_rmk",
                "nivel": "alerta",
                "frase": f"Tire R$50 de {nome} e passe para a campanha comum",
            })

        # Gatilho 2: gastou R$40 ou mais desde ontem sem compra
        if gasto_desde_ontem >= 40.0 and compras_desde_ontem == 0:
            acoes.append({
                "campanha": nome,
                "regra": "gasto_sem_compra",
                "nivel": "perigo",
                "frase": f"Reduza {nome} à metade",
            })

        # Gatilho 3: ROAS acima de 6 e gastando todo o orçamento do dia (>= 90% do orçamento)
        if roas is not None and roas > 6.0 and orcamento_dia > 0 and gasto_hoje >= orcamento_dia * 0.90:
            acoes.append({
                "campanha": nome,
                "regra": "escalar_roas",
                "nivel": "oportunidade",
                "frase": f"Aumente {nome} em 20% (1 vez por dia)",
            })

        # Gatilho 4: CPC acima de R$2,50
        if cpc is not None and cpc > 2.50:
            acoes.append({
                "campanha": nome,
                "regra": "cpc_alto",
                "nivel": "alerta",
                "frase": f"Troque o criativo de {nome}",
            })

        linhas.append({
            "campanha": nome,
            "gasto_hoje": round(gasto_hoje, 2),
            "gasto_desde_ontem": round(gasto_desde_ontem, 2),
            "gasto_3d": round(gasto_3d, 2),
            "compras_hoje": compras_hoje,
            "compras_3d": compras_3d,
            "receita_hoje": round(receita_hoje, 2),
            "receita_3d": round(receita_3d, 2),
            "roas": round(roas, 2) if roas is not None else None,
            "frequencia": round(frequencia, 2),
            "cpc": round(cpc, 2) if cpc is not None else None,
            "orcamento_dia": round(orcamento_dia, 2) if orcamento_dia > 0 else None,
        })

    if not acoes:
        acoes.append({
            "campanha": "",
            "regra": "nada",
            "nivel": "ok",
            "frase": "Não mexa em nada",
        })

    return {
        "atualizado_em": atualizado_em,
        "acoes": acoes,
        "campanhas": linhas,
    }


def _calcular_custo_subconjunto(
    pedidos_sub: pd.DataFrame,
    itens_por_pedido: dict[str, list[dict[str, Any]]],
    custo_por_pid: dict[str, float],
    custo_por_sku: dict[str, float],
    tipo_por_pid: dict[str, str],
    tipo_por_sku: dict[str, str],
    premissas: PremissasMargem,
) -> tuple[float, int, int]:
    """Devolve (custo_total, total_itens_unidades, itens_com_margem_padrao_unidades).

    Quando a variante não tem custo cadastrado na Nuvemshop, usa a margem por tipo de produto
    (usado ou novo/lacrado): custo = preço cheio * (1 - margem).
    """
    fator_usado = max(0.0, min(1.0, 1.0 - premissas.margem_usado))
    fator_lacrado = max(0.0, min(1.0, 1.0 - premissas.margem_lacrado))
    custo_total = 0.0
    total_itens = 0
    itens_padrao = 0

    for row in pedidos_sub.itertuples():
        num = str(row.numero_str)
        itens = itens_por_pedido.get(num, [])
        if not itens:
            custo_total += float(row.subtotal_num if row.subtotal_num > 0 else row.receita_num) * fator_usado
            total_itens += 1
            itens_padrao += 1
            continue
        for it in itens:
            qtd = max(1, int(round(it["qtd"])))
            custo_unit = it["custo"]
            if custo_unit <= 0 and it["pid"]:
                custo_unit = custo_por_pid.get(it["pid"], 0.0)
            if custo_unit <= 0 and it["sku"]:
                custo_unit = custo_por_sku.get(it["sku"], 0.0)
            total_itens += qtd
            if custo_unit > 0:
                custo_total += custo_unit * qtd
            else:
                tipo_p = tipo_por_pid.get(it["pid"]) or tipo_por_sku.get(it["sku"]) or "usado"
                fator = fator_lacrado if tipo_p == "lacrado" else fator_usado
                custo_total += it["valor"] * qtd * fator
                itens_padrao += qtd

    return round(custo_total, 2), total_itens, itens_padrao


def calcular_bloco_saude(
    df_p: pd.DataFrame,
    itens_df: pd.DataFrame | None,
    produtos_df: pd.DataFrame | None,
    hoje_str: str,
    premissas: PremissasMargem | None = None,
    dias_26: list[tuple[str, str, str]] | None = None,
) -> dict[str, Any]:
    """Bloco 4: Saúde da Black (margem bruta x volume) comparada às 4 semanas anteriores."""
    if premissas is None:
        premissas = PremissasMargem()
    dias_26 = dias_26 or list(BLACK_2026_DIAS)

    # Mapas de custo da variante e tipo (usado/lacrado) na Nuvemshop
    custo_por_pid: dict[str, float] = {}
    custo_por_sku: dict[str, float] = {}
    tipo_por_pid: dict[str, str] = {}
    tipo_por_sku: dict[str, str] = {}
    if produtos_df is not None and not produtos_df.empty:
        cat_col = "categorias" if "categorias" in produtos_df.columns else ("categoria" if "categoria" in produtos_df.columns else "")
        for _, r in produtos_df.iterrows():
            pid = str(r.get("id", "")).strip()
            if pid.endswith(".0"):
                pid = pid[:-2]
            sku = str(r.get("sku", "")).strip()
            pid_ok = pid if (pid and pid.lower() != "nan") else ""
            sku_ok = sku if (sku and sku.lower() != "nan") else ""
            custo_v = _parse_num(r.get("custo", r.get("cost", 0)))
            if custo_v > 0:
                if pid_ok:
                    custo_por_pid[pid_ok] = custo_v
                if sku_ok:
                    custo_por_sku[sku_ok] = custo_v
            if cat_col:
                tipo_p = classificar_tipo_produto(str(r.get(cat_col, "") or ""))
                if pid_ok:
                    tipo_por_pid[pid_ok] = tipo_p
                if sku_ok:
                    tipo_por_sku[sku_ok] = tipo_p

    # Agrupar itens por número de pedido
    itens_por_pedido: dict[str, list[dict[str, Any]]] = {}
    if itens_df is not None and not itens_df.empty:
        for _, r in itens_df.iterrows():
            num = str(r.get("numero", "")).strip()
            if not num:
                continue
            pid = str(r.get("produto_id", "")).strip()
            if pid.endswith(".0"):
                pid = pid[:-2]
            sku = str(r.get("sku", "")).strip()
            custo_it = _parse_num(r.get("custo", r.get("cost", 0)))
            itens_por_pedido.setdefault(num, []).append({
                "valor": _parse_num(r.get("valor", 0)),
                "qtd": _parse_num(r.get("quantidade", 1)) or 1.0,
                "pid": "" if pid.lower() == "nan" else pid,
                "sku": "" if sku.lower() == "nan" else sku,
                "custo": custo_it,
            })

    validos = df_p[df_p["valido_bool"]]

    # Linha de base: média das 4 semanas anteriores a cada dia D0..D4
    base_por_dia = []
    for codigo, nome, dt_black in dias_26:
        dt_ref = date.fromisoformat(dt_black)
        datas_base = [(dt_ref - timedelta(days=7 * k)).isoformat() for k in (1, 2, 3, 4)]
        sub_b = validos[validos["dt"].isin(datas_base)]
        rec_b = float(sub_b["receita_num"].sum())
        ped_b = int(len(sub_b))
        custo_b, _, _ = _calcular_custo_subconjunto(
            sub_b, itens_por_pedido, custo_por_pid, custo_por_sku, tipo_por_pid, tipo_por_sku, premissas
        )
        marg_b = rec_b - custo_b
        base_por_dia.append({
            "dia": codigo,
            "nome": nome,
            "data_black": dt_black,
            "datas_base": datas_base,
            "pedidos_dia": round(ped_b / 4.0, 2),
            "receita_dia": round(rec_b / 4.0, 2),
            "margem_dia": round(marg_b / 4.0, 2),
        })

    # Dias ocorridos da Black 2026
    dias_ocorridos = [b for b in base_por_dia if b["data_black"] <= hoje_str]
    n_dias = len(dias_ocorridos)
    datas_ocorridas = [b["data_black"] for b in dias_ocorridos]
    sub_bk = validos[validos["dt"].isin(datas_ocorridas)] if datas_ocorridas else validos.iloc[0:0]

    ped_bk = int(len(sub_bk))
    rec_bk = float(sub_bk["receita_num"].sum()) if ped_bk else 0.0
    desc_bk = float(sub_bk["desconto_num"].sum()) if ped_bk else 0.0
    custo_bk, total_itens_bk, itens_padrao_bk = _calcular_custo_subconjunto(
        sub_bk, itens_por_pedido, custo_por_pid, custo_por_sku, tipo_por_pid, tipo_por_sku, premissas
    )
    marg_bk = rec_bk - custo_bk
    pct_itens_padrao = round((itens_padrao_bk / total_itens_bk * 100.0), 1) if total_itens_bk > 0 else 0.0

    # Baseline proporcional aos dias ocorridos (para não comparar 1 dia com 4 dias)
    ped_base_tot = sum(b["pedidos_dia"] for b in dias_ocorridos)
    rec_base_tot = sum(b["receita_dia"] for b in dias_ocorridos)
    marg_base_tot = sum(b["margem_dia"] for b in dias_ocorridos)

    vol_extra_ped = ped_bk - ped_base_tot
    vol_extra_rec = rec_bk - rec_base_tot
    marg_extra = marg_bk - marg_base_tot

    if marg_base_tot <= 0:
        semaforo = "verde" if marg_bk > 0 else "amarelo"
    else:
        ratio = marg_bk / marg_base_tot
        if ratio > 1.0:
            semaforo = "verde"
        elif ratio >= 0.90:
            semaforo = "amarelo"
        else:
            semaforo = "vermelho"

    # Frase pronta: "Para compensar o desconto, precisamos de X pedidos a mais por dia; estamos com Y."
    if n_dias > 0:
        ped_base_dia = ped_base_tot / n_dias
        marg_base_dia = marg_base_tot / n_dias
        ped_bk_dia = ped_bk / n_dias
        marg_por_ped_bk = (marg_bk / ped_bk) if ped_bk > 0 else 0.0
        if marg_por_ped_bk > 0:
            ped_nec_dia = marg_base_dia / marg_por_ped_bk
            x_extra = max(0.0, ped_nec_dia - ped_base_dia)
        else:
            x_extra = 0.0
        y_extra = ped_bk_dia - ped_base_dia
    else:
        x_extra, y_extra = 0.0, 0.0

    def _fmt_num(v: float) -> str:
        s = f"{v:.1f}".replace(".", ",")
        return s[:-2] if s.endswith(",0") else s

    frase = f"Para compensar o desconto, precisamos de {_fmt_num(x_extra)} pedidos a mais por dia; estamos com {_fmt_num(y_extra)}."

    return {
        "margem_usado_pct": round(premissas.margem_usado * 100.0, 1),
        "margem_lacrado_pct": round(premissas.margem_lacrado * 100.0, 1),
        "pct_itens_padrao": pct_itens_padrao,
        "dias_ocorridos": n_dias,
        "desconto_dado": round(desc_bk, 2),
        "pedidos_black": ped_bk,
        "receita_black": round(rec_bk, 2),
        "custo_black": round(custo_bk, 2),
        "margem_black": round(marg_bk, 2),
        "pedidos_base": round(ped_base_tot, 2),
        "receita_base": round(rec_base_tot, 2),
        "margem_base": round(marg_base_tot, 2),
        "volume_extra_pedidos": round(vol_extra_ped, 2),
        "volume_extra_receita": round(vol_extra_rec, 2),
        "margem_extra": round(marg_extra, 2),
        "semaforo": semaforo,
        "precisamos_pedidos_extra_dia": round(x_extra, 1),
        "estamos_pedidos_extra_dia": round(y_extra, 1),
        "frase": frase,
        "base_por_dia": base_por_dia,
    }


def _fmt_brl_curto(v: float) -> str:
    """Formata R$ em português simples: ex. R$7.614 ou R$18,8 mil."""
    if v >= 10000.0:
        mil = v / 1000.0
        s = f"{mil:.1f}".replace(".", ",")
        if s.endswith(",0"):
            s = s[:-2]
        return f"R${s} mil"
    return "R$" + f"{round(v):,}".replace(",", ".")


def calcular_bloco_projecao(
    df_p: pd.DataFrame,
    saude: dict[str, Any],
    agora_brt: pd.Timestamp,
    dias_26: list[tuple[str, str, str]] | None = None,
    dias_25: list[tuple[str, str, str]] | None = None,
    config_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Bloco 5: Projeção robusta de D0 a D4 com isolamento de pedidos fora da curva,
    Método A só após 24h, três cenários (conservador, provável, otimista) e metas."""
    dias_26 = dias_26 or list(BLACK_2026_DIAS)
    dias_25 = dias_25 or list(BLACK_2025_DIAS)
    agora_naive = agora_brt.tz_convert("America/Sao_Paulo").tz_localize(None) if agora_brt.tzinfo is not None else agora_brt
    hoje_str = agora_naive.strftime("%Y-%m-%d")

    inicio_26 = pd.Timestamp(dias_26[0][2] + " 00:00:00")
    inicio_25 = pd.Timestamp(dias_25[0][2] + " 00:00:00")
    horas_totais = float(len(dias_26) * 24)
    horas_decorridas = max(0.0, min(horas_totais, (agora_naive - inicio_26).total_seconds() / 3600.0))

    validos = df_p[df_p["valido_bool"]]
    datas_26 = [d[2] for d in dias_26]
    p26 = validos[validos["dt"].isin(datas_26)].copy()

    # Corte de pedido fora da curva: min(3x mediana dos últimos 90 dias, R$1.500)
    corte_90d_ini = (date.fromisoformat(dias_26[0][2]) - timedelta(days=90)).isoformat()
    corte_90d_fim = (date.fromisoformat(dias_26[0][2]) - timedelta(days=1)).isoformat()
    p_90d = validos[(validos["dt"] >= corte_90d_ini) & (validos["dt"] <= corte_90d_fim)]
    mediana_90d = float(p_90d["receita_num"].median()) if not p_90d.empty else 0.0
    limite_fora_curva = round(min(3.0 * mediana_90d, LIMITE_FORA_CURVA_TETO), 2) if mediana_90d > 0 else LIMITE_FORA_CURVA_TETO

    ped_26 = int(len(p26))
    rec_26 = float(p26["receita_num"].sum()) if ped_26 else 0.0
    marg_26 = float(saude.get("margem_black", 0.0))
    taxa_margem = (marg_26 / rec_26) if rec_26 > 0 else 0.0

    p_fora = p26[p26["receita_num"] > limite_fora_curva] if not p26.empty else p26
    p_norm = p26[p26["receita_num"] <= limite_fora_curva] if not p26.empty else p26

    n_garantidos = int(len(p_fora))
    rec_garantida = float(p_fora["receita_num"].sum()) if n_garantidos else 0.0
    marg_garantida = rec_garantida * taxa_margem

    n_normal = int(len(p_norm))
    rec_normal = float(p_norm["receita_num"].sum()) if n_normal else 0.0
    marg_normal = marg_26 - marg_garantida

    # Método (a): ritmo atual por hora (somente após 24h de Black, sem fora da curva + garantidos)
    ritmo_disponivel = horas_decorridas >= 24.0
    if ritmo_disponivel:
        fator_ritmo = horas_totais / horas_decorridas
        ritmo = {
            "disponivel": True,
            "status": "ok",
            "pedidos": round(n_normal * fator_ritmo + n_garantidos, 1),
            "receita": round(rec_normal * fator_ritmo + rec_garantida, 2),
            "margem": round(marg_normal * fator_ritmo + marg_garantida, 2),
        }
    else:
        ritmo = {
            "disponivel": False,
            "status": "aguardando 24h",
            "pedidos": None,
            "receita": None,
            "margem": None,
        }

    # Base 2025 (D0 a D4: 27/11 a 01/12/2025)
    datas_25 = [d[2] for d in dias_25]
    p25 = validos[validos["dt"].isin(datas_25)].copy()
    ped_25_total = int(len(p25))
    rec_25_total = float(p25["receita_num"].sum()) if ped_25_total else 0.0

    # Método (b): curva horária de 2025 (sem fora da curva + garantidos)
    curva = {"disponivel": False, "pedidos": None, "receita": None, "margem": None}
    fracao_25_rec = 0.0
    fracao_25_ped = 0.0
    if ped_25_total > 0 and horas_decorridas > 0:
        if horas_decorridas >= horas_totais:
            fracao_25_ped = 1.0
            fracao_25_rec = 1.0
        else:
            horas_rel = (p25["data_ts"] - inicio_25).dt.total_seconds() / 3600.0
            ate_agora = p25[horas_rel <= horas_decorridas]
            fracao_25_ped = len(ate_agora) / ped_25_total
            fracao_25_rec = (float(ate_agora["receita_num"].sum()) / rec_25_total) if rec_25_total > 0 else 0.0
        curva = {
            "disponivel": fracao_25_rec > 0 or fracao_25_ped > 0,
            "pedidos": round(n_normal / fracao_25_ped + n_garantidos, 1) if fracao_25_ped > 0 else None,
            "receita": round(rec_normal / fracao_25_rec + rec_garantida, 2) if fracao_25_rec > 0 else None,
            "margem": round(marg_normal / fracao_25_rec + marg_garantida, 2) if fracao_25_rec > 0 else None,
        }

    # Três cenários (conservador, provável, otimista)
    def _cenario_campo(campo: str, acum: float) -> tuple[float | None, float | None, float | None]:
        r_val = ritmo.get(campo) if ritmo_disponivel else None
        c_val = curva.get(campo)
        candidatos = [max(acum, v) for v in (r_val, c_val) if v is not None]
        if not candidatos:
            return (round(acum, 2), round(acum, 2), round(acum, 2)) if acum > 0 else (None, None, None)
        cons = round(min(candidatos), 2 if campo != "pedidos" else 1)
        otim = round(max(candidatos), 2 if campo != "pedidos" else 1)
        prov_base = max(acum, c_val) if c_val is not None else max(acum, r_val)
        prov = round(prov_base, 2 if campo != "pedidos" else 1)
        return cons, prov, otim

    c_ped, p_ped, o_ped = _cenario_campo("pedidos", float(ped_26))
    c_rec, p_rec, o_rec = _cenario_campo("receita", rec_26)
    c_mrg, p_mrg, o_mrg = _cenario_campo("margem", marg_26)

    cenarios = {
        "conservador": {"pedidos": c_ped, "receita": c_rec, "margem": c_mrg},
        "provavel": {"pedidos": p_ped, "receita": p_rec, "margem": p_mrg},
        "otimista": {"pedidos": o_ped, "receita": o_rec, "margem": o_mrg},
    }

    # Explicação simples gerada a partir dos dados
    partes = [f"Até agora: {ped_26} pedido{'s' if ped_26 != 1 else ''} e {_fmt_brl_curto(rec_26)}."]
    if n_garantidos > 0:
        partes.append(
            f"Desses, {n_garantidos} pedido{'s' if n_garantidos != 1 else ''} grande{'s' if n_garantidos != 1 else ''} "
            f"soma{'m' if n_garantidos != 1 else ''} {_fmt_brl_curto(rec_garantida)} e já "
            f"{'estão garantidos' if n_garantidos != 1 else 'está garantido'}, mas não entram na conta da projeção."
        )
    if c_rec is not None and o_rec is not None:
        if abs(o_rec - c_rec) < 100.0:
            partes.append(f"Pelo ritmo normal, devemos fechar perto de {_fmt_brl_curto(p_rec or c_rec)}.")
        else:
            partes.append(f"Pelo ritmo normal, devemos fechar entre {_fmt_brl_curto(c_rec)} e {_fmt_brl_curto(o_rec)}.")
    if rec_25_total > 0:
        partes.append(f"A Black 2025 inteira fez {_fmt_brl_curto(rec_25_total)}.")
    explicacao = " ".join(partes)

    # Metas da Configuração: piso da Black e metas diárias de D0 a D4
    cfg = config_params or {}
    cfg_lower = {str(k).strip().lower(): v for k, v in cfg.items()}
    piso_black = _parse_num(cfg_lower.get("black: piso da black", "24000")) or 24000.0
    metas_str = str(cfg_lower.get("black: metas diárias de 26 a 30/11", cfg_lower.get("black: metas diarias de 26 a 30/11", "5000, 8000, 7000, 7000, 5000")))
    metas_vals = [_parse_num(x) for x in metas_str.split(",") if str(x).strip()]
    while len(metas_vals) < len(dias_26):
        metas_vals.append(0.0)

    metas_diarias = []
    meta_hoje_info = None
    for idx, (cod, nome, dt) in enumerate(dias_26):
        meta_d = metas_vals[idx]
        real_d = float(p26[p26["dt"] == dt]["receita_num"].sum()) if not p26.empty else 0.0
        ating_d = round((real_d / meta_d * 100.0), 1) if meta_d > 0 else 0.0
        item_m = {
            "dia": cod,
            "nome": nome,
            "data": dt,
            "meta": round(meta_d, 2),
            "realizado": round(real_d, 2),
            "atingimento_pct": ating_d,
            "ocorrido": dt <= hoje_str,
        }
        metas_diarias.append(item_m)
        if dt == hoje_str:
            meta_hoje_info = item_m

    if meta_hoje_info is None and metas_diarias:
        meta_hoje_info = metas_diarias[-1] if hoje_str > dias_26[-1][2] else metas_diarias[0]

    metas_resumo = {
        "piso_black": round(piso_black, 2),
        "realizado_total": round(rec_26, 2),
        "acima_do_piso": rec_26 >= piso_black,
        "falta_piso": round(max(0.0, piso_black - rec_26), 2),
        "meta_hoje": meta_hoje_info,
        "diarias": metas_diarias,
    }

    return {
        "horas_decorridas": round(horas_decorridas, 1),
        "horas_totais": horas_totais,
        "fracao_2025_pedidos_pct": round(fracao_25_ped * 100.0, 1),
        "fracao_2025_receita_pct": round(fracao_25_rec * 100.0, 1),
        "fora_da_curva": {
            "limite": limite_fora_curva,
            "mediana_90d": round(mediana_90d, 2),
            "pedidos": n_garantidos,
            "receita": round(rec_garantida, 2),
            "margem": round(marg_garantida, 2),
        },
        "explicacao": explicacao,
        "ritmo_atual": ritmo,
        "curva_2025": curva,
        "cenarios": cenarios,
        "faixa": {
            "pedidos": {"min": c_ped, "max": o_ped},
            "receita": {"min": c_rec, "max": o_rec},
            "margem": {"min": c_mrg, "max": o_mrg},
        },
        "metas": metas_resumo,
        "total_2025": {
            "pedidos": ped_25_total,
            "receita": round(rec_25_total, 2),
        },
        "falta_bater_2025": {
            "pedidos": max(0, ped_25_total - ped_26),
            "receita": round(max(0.0, rec_25_total - rec_26), 2),
            "bateu_pedidos": ped_25_total > 0 and ped_26 >= ped_25_total,
            "bateu_receita": rec_25_total > 0 and rec_26 >= rec_25_total,
        },
    }


def calcular_black_2026(
    pedidos_df: pd.DataFrame | None,
    itens_df: pd.DataFrame | None,
    produtos_df: pd.DataFrame | None,
    campanhas_meta: list[dict[str, Any]] | None = None,
    config_params: dict[str, Any] | None = None,
    agora_brt: pd.Timestamp | None = None,
    meta_atualizado_em: str = "",
    premissas: PremissasMargem | None = None,
    valores_margem_premissas: list[list[str]] | None = None,
) -> dict[str, Any]:
    """Calcula os 5 blocos completos da área Black 2026 (agregados, sem dados de cliente)."""
    if agora_brt is None:
        agora_brt = pd.Timestamp.now(tz="America/Sao_Paulo")
    agora_sp = agora_brt.tz_convert("America/Sao_Paulo") if agora_brt.tzinfo is not None else agora_brt
    hoje_str = agora_sp.strftime("%Y-%m-%d")
    atualizado_em = agora_sp.strftime("%Y-%m-%d %H:%M")

    prem = premissas if premissas is not None else carregar_premissas_margem(valores_margem_premissas, config_params)
    dias_26, dias_25, antecipa_periodo = montar_calendario_black(config_params)

    df_p = _preparar_pedidos_black(pedidos_df)
    cupons = calcular_bloco_cupons(df_p, hoje_str, dias_26=dias_26, antecipa_periodo=antecipa_periodo)
    comp_2025 = calcular_bloco_2026_x_2025(df_p, hoje_str, dias_26=dias_26, dias_25=dias_25)
    meta_ads = avaliar_gatilhos_meta(campanhas_meta, atualizado_em=meta_atualizado_em or atualizado_em)
    saude = calcular_bloco_saude(df_p, itens_df, produtos_df, hoje_str, premissas=prem, dias_26=dias_26)
    projecao = calcular_bloco_projecao(df_p, saude, agora_sp, dias_26=dias_26, dias_25=dias_25, config_params=config_params)

    return {
        "atualizado_em": atualizado_em,
        "hoje_data": hoje_str,
        "periodo_inicio": dias_26[0][2],
        "periodo_fim": dias_26[-1][2],
        "margem_usado_pct": saude["margem_usado_pct"],
        "margem_lacrado_pct": saude["margem_lacrado_pct"],
        "pct_itens_padrao": saude["pct_itens_padrao"],
        "cupons": cupons,
        "comp_2025": comp_2025,
        "meta_ads": meta_ads,
        "saude": saude,
        "projecao": projecao,
    }
