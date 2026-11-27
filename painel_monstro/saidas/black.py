"""Saída para a planilha das abas black_dia e black_resumo."""
from __future__ import annotations
import json
from typing import Any
import pandas as pd


def preparar_black_dia(df_black_dia: pd.DataFrame) -> list[list[str]]:
    """Transforma o DataFrame black_dia em matriz de strings para o Google Sheets."""
    if df_black_dia.empty:
        return [["data", "fase", "faturamento", "pedidos", "ticket_medio", "meta_dia", "atingimento_pct", "faturamento_acum", "meta_acum", "custo_disco", "custos_venda", "gasto_anuncio", "sobra_dia", "sobra_acum", "roas_anuncio"]]

    cabecalho = list(df_black_dia.columns)
    linhas = [cabecalho]
    for _, row in df_black_dia.iterrows():
        linhas.append([str(row[col]) for col in cabecalho])
    return linhas


def preparar_black_resumo(resumo: dict[str, Any]) -> list[list[str]]:
    """Transforma o dicionário resumo em chave-valor / seções para a aba black_resumo."""
    linhas = [["chave", "valor", "detalhes"]]

    # Placar e métricas principais
    linhas.append(["atualizado_em", str(resumo.get("atualizado_em", "")), ""])
    linhas.append(["hoje_data", str(resumo.get("hoje_data", "")), ""])
    linhas.append(["hoje_faturamento", str(resumo.get("hoje_faturamento", 0)), ""])
    linhas.append(["hoje_pedidos", str(resumo.get("hoje_pedidos", 0)), ""])
    linhas.append(["hoje_ticket_medio", str(resumo.get("hoje_ticket_medio", 0)), ""])
    linhas.append(["hoje_meta", str(resumo.get("hoje_meta", 0)), ""])
    linhas.append(["hoje_atingimento_pct", str(resumo.get("hoje_atingimento_pct", 0)), ""])
    linhas.append(["periodo_faturamento", str(resumo.get("periodo_faturamento", 0)), ""])
    linhas.append(["periodo_pedidos", str(resumo.get("periodo_pedidos", 0)), ""])
    linhas.append(["periodo_ticket_medio", str(resumo.get("periodo_ticket_medio", 0)), ""])
    linhas.append(["meta_mes", str(resumo.get("meta_mes", 0)), ""])
    linhas.append(["meta_esticada", str(resumo.get("meta_esticada", 0)), ""])
    linhas.append(["piso_black", str(resumo.get("piso_black", 0)), ""])
    linhas.append(["atingimento_mes_pct", str(resumo.get("atingimento_mes_pct", 0)), ""])
    linhas.append(["atingimento_esticada_pct", str(resumo.get("atingimento_esticada_pct", 0)), ""])
    linhas.append(["acima_do_piso", "1" if resumo.get("acima_do_piso") else "0", ""])
    linhas.append(["diferenca_piso", str(resumo.get("diferenca_piso", 0)), ""])
    linhas.append(["sobra_total", str(resumo.get("sobra_total", 0)), ""])

    # Seções estruturadas em JSON para fácil consumo no Painel
    linhas.append(["cupons_json", json.dumps(resumo.get("cupons", []), ensure_ascii=False), "Lista de cupons e desempenho"])
    linhas.append(["lado_a_json", json.dumps(resumo.get("lado_a", {}), ensure_ascii=False), "Métricas da Lista Lado A"])
    linhas.append(["vip_json", json.dumps(resumo.get("vip", {}), ensure_ascii=False), "Métricas da Lista Lado A (alias legado)"])
    linhas.append(["comparacao_2025_json", json.dumps(resumo.get("comparacao_2025", {}), ensure_ascii=False), "Comparativo Black 2025 vs 2026"])
    linhas.append(["top_discos_json", json.dumps(resumo.get("top_discos", []), ensure_ascii=False), "Top 20 discos mais vendidos"])
    linhas.append(["lotes_black_json", json.dumps(resumo.get("lotes_black", []), ensure_ascii=False), "Desempenho Lote Black"])
    linhas.append(["alertas_json", json.dumps(resumo.get("alertas", []), ensure_ascii=False), "Alertas automáticos"])
    linhas.append(["premissas_json", json.dumps(resumo.get("premissas_usadas", {}), ensure_ascii=False), "Premissas de margem e custos"])

    return linhas


# ----------------------------------------------------------------------------
# Aba "Black" (área Black 2026 com os 5 blocos) e coleta rápida do Meta Ads
# ----------------------------------------------------------------------------
ABA_BLACK = "Black"
CAMPANHAS_BLACK = ("black26_rmk", "prosp_vendas_recorrente", "black26_loja_fisica_2811")


def preparar_aba_black(dados: dict[str, Any]) -> pd.DataFrame:
    """Converte o resultado de `calcular_black_2026` para DataFrame da aba `Black` (sem dados de cliente)."""
    linhas = [
        ["atualizado_em", str(dados.get("atualizado_em", "")), "Última atualização da aba Black (Brasília)"],
        ["hoje_data", str(dados.get("hoje_data", "")), "Data de referência"],
        ["margem_usado_pct", str(dados.get("margem_usado_pct", 60.0)), "Margem padrão (%) usada para discos usados sem custo cadastrado"],
        ["margem_lacrado_pct", str(dados.get("margem_lacrado_pct", 40.0)), "Margem padrão (%) usada para novos/lacrados sem custo cadastrado"],
        ["pct_itens_padrao", str(dados.get("pct_itens_padrao", 0.0)), "% de itens com margem padrão (usado/novo)"],
        ["cupons_json", json.dumps(dados.get("cupons", {}), ensure_ascii=False), "Bloco 1: Pedidos por cupom (dia, hora hoje e tabela)"],
        ["comp_2025_json", json.dumps(dados.get("comp_2025", {}), ensure_ascii=False), "Bloco 2: 2026 x 2025 por dia da Black (D1-D4)"],
        ["meta_ads_json", json.dumps(dados.get("meta_ads", {}), ensure_ascii=False), "Bloco 3: Meta Ads e gatilhos de ação"],
        ["saude_json", json.dumps(dados.get("saude", {}), ensure_ascii=False), "Bloco 4: Saúde da Black (margem x volume)"],
        ["projecao_json", json.dumps(dados.get("projecao", {}), ensure_ascii=False), "Bloco 5: Projeção 4 dias (ritmo atual x curva 2025)"],
    ]
    return pd.DataFrame(linhas, columns=["chave", "valor", "detalhes"])


def _eh_campanha_black(nome: str) -> bool:
    n = str(nome or "").strip().lower()
    return n in CAMPANHAS_BLACK or n.startswith("black26_")


def extrair_meta_black_de_df(df_campanha_dia: pd.DataFrame | None, hoje_str: str) -> list[dict[str, Any]]:
    """Extrai métricas das campanhas da Black a partir da aba `anuncios_campanha_dia`."""
    if df_campanha_dia is None or df_campanha_dia.empty:
        return []
    from datetime import date, timedelta
    from painel_monstro.motor.black import _parse_num

    hoje_d = date.fromisoformat(hoje_str)
    ontem_str = (hoje_d - timedelta(days=1)).isoformat()
    inicio_3d_str = (hoje_d - timedelta(days=2)).isoformat()

    df = df_campanha_dia.copy()
    df["dt"] = df["data"].astype(str).str.slice(0, 10)
    df["camp_nome"] = df["campanha"].astype(str).str.strip()
    df = df[df["camp_nome"].apply(_eh_campanha_black) & (df["dt"] >= inicio_3d_str) & (df["dt"] <= hoje_str)]
    if df.empty:
        return []

    saida = []
    for nome, g in df.groupby("camp_nome"):
        g_hoje = g[g["dt"] == hoje_str]
        g_ontem = g[g["dt"] == ontem_str]

        def _soma(sub, col):
            return float(sub[col].apply(_parse_num).sum()) if col in sub.columns and not sub.empty else 0.0

        def _max(sub, col):
            return float(sub[col].apply(_parse_num).max()) if col in sub.columns and not sub.empty else 0.0

        saida.append({
            "campanha": nome,
            "gasto_hoje": _soma(g_hoje, "investido"),
            "gasto_ontem": _soma(g_ontem, "investido"),
            "gasto_3d": _soma(g, "investido"),
            "compras_hoje": _soma(g_hoje, "compras"),
            "compras_ontem": _soma(g_ontem, "compras"),
            "compras_3d": _soma(g, "compras"),
            "receita_hoje": _soma(g_hoje, "receita"),
            "receita_3d": _soma(g, "receita"),
            "cliques_hoje": _soma(g_hoje, "cliques_link"),
            "cliques_3d": _soma(g, "cliques_link"),
            "frequencia_hoje": _max(g_hoje, "frequencia"),
            "frequencia_3d": _max(g, "frequencia"),
            "orcamento_dia": _max(g, "orcamento_dia"),
        })
    saida.sort(key=lambda x: x["campanha"])
    return saida


def coletar_meta_black_rapido(config: Any, hoje: Any, sessao: Any = None) -> list[dict[str, Any]]:
    """Coleta leve (somente GET) dos últimos 3 dias + orçamento das campanhas da Black no Meta Ads."""
    from datetime import timedelta
    from painel_monstro.saidas import anuncios

    if not (getattr(config, "meta_ads_token", "") and getattr(config, "meta_ads_account_id", "")):
        return []
    cliente = anuncios.MetaLeitura(config, sessao=sessao)
    inicio_3d = hoje - timedelta(days=2)
    ontem_str = (hoje - timedelta(days=1)).isoformat()
    hoje_str = hoje.isoformat()

    diario = cliente.insights(inicio_3d, hoje, nivel="campaign", horario=False, diario=True)
    agregado_3d = cliente.insights(inicio_3d, hoje, nivel="campaign", horario=False, diario=False)
    estrutura = cliente.lista("/campaigns", fields="id,name,effective_status,daily_budget,lifetime_budget")
    conjuntos = cliente.lista("/adsets", fields="id,campaign_id,effective_status,daily_budget")

    orc_por_id = {str(c["id"]): anuncios.orcamento(c, conjuntos) or 0.0 for c in estrutura}
    por_nome: dict[str, dict[str, Any]] = {}

    # Garante campanhas ativas da Black mesmo se ainda sem gasto hoje
    for c in estrutura:
        nome = str(c.get("name") or "").strip()
        if _eh_campanha_black(nome):
            por_nome[nome] = {
                "campanha": nome,
                "gasto_hoje": 0.0, "gasto_ontem": 0.0, "gasto_3d": 0.0,
                "compras_hoje": 0.0, "compras_ontem": 0.0, "compras_3d": 0.0,
                "receita_hoje": 0.0, "receita_3d": 0.0,
                "cliques_hoje": 0.0, "cliques_3d": 0.0,
                "frequencia_hoje": 0.0, "frequencia_3d": 0.0,
                "orcamento_dia": orc_por_id.get(str(c["id"]), 0.0),
            }

    for l in diario:
        nome = str(l.get("campanha") or "").strip()
        if not _eh_campanha_black(nome):
            continue
        item = por_nome.setdefault(nome, {
            "campanha": nome,
            "gasto_hoje": 0.0, "gasto_ontem": 0.0, "gasto_3d": 0.0,
            "compras_hoje": 0.0, "compras_ontem": 0.0, "compras_3d": 0.0,
            "receita_hoje": 0.0, "receita_3d": 0.0,
            "cliques_hoje": 0.0, "cliques_3d": 0.0,
            "frequencia_hoje": 0.0, "frequencia_3d": 0.0,
            "orcamento_dia": orc_por_id.get(str(l.get("campanha_id", "")), 0.0),
        })
        if l["data"] == hoje_str:
            item["gasto_hoje"] += l["investido"]
            item["compras_hoje"] += l["compras"]
            item["receita_hoje"] += l["receita"]
            item["cliques_hoje"] += l["cliques_link"]
            item["frequencia_hoje"] = max(item["frequencia_hoje"], l["frequencia"])
        elif l["data"] == ontem_str:
            item["gasto_ontem"] += l["investido"]
            item["compras_ontem"] += l["compras"]

    for l in agregado_3d:
        nome = str(l.get("campanha") or "").strip()
        if nome not in por_nome:
            continue
        item = por_nome[nome]
        item["gasto_3d"] = l["investido"]
        item["compras_3d"] = l["compras"]
        item["receita_3d"] = l["receita"]
        item["cliques_3d"] = l["cliques_link"]
        item["frequencia_3d"] = max(item["frequencia_3d"], l["frequencia"])

    return [por_nome[k] for k in sorted(por_nome)]
