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
