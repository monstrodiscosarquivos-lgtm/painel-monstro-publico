"""Saída para a planilha da aba agregada 'Cadastro x vendas' (D-111)."""
from __future__ import annotations

import json
from typing import Any

import pandas as pd

from painel_monstro.motor import cadastro_vendas as motor_cv

ABA_CADASTRO_VENDAS = "Cadastro x vendas"


def garantir_config_promocoes(planilha: Any) -> None:
    """Acrescenta a linha 'Semanas com promoção' na aba Configuração apenas se faltar."""
    try:
        aba = planilha._ss.worksheet("Configuração")
        linhas = aba.get_all_values()
    except Exception:
        return
    existentes = {str(r[0]).strip().lower() for r in linhas if r and str(r[0]).strip()}
    if motor_cv.CHAVE_SEMANAS_PROMO.lower() in existentes:
        return
    if not linhas:
        linhas = [["Parâmetro", "Valor", "O que significa"]]
        aba.update(linhas, "A1", raw=True)
    nova = [[
        motor_cv.CHAVE_SEMANAS_PROMO,
        "",
        "Datas ou intervalos extras (ex.: 10/10/2026 a 12/10/2026) que marcam semanas como promoção além dos cupons detectados.",
    ]]
    destino = len(linhas) + 1
    if aba.row_count < destino:
        aba.resize(rows=destino)
    aba.update(nova, f"A{destino}", raw=True)


def preparar_aba_cadastro_vendas(dados: dict[str, Any]) -> pd.DataFrame:
    """Converte o resultado agregado em tabela chave/valor/detalhes (zero dados de cliente)."""
    ult = dados.get("ultimas_12", {})
    linhas = [
        ["atualizado_em", str(dados.get("atualizado_em", "")), "Última atualização (Brasília)"],
        ["inicio", str(dados.get("inicio", "")), "Segunda-feira inicial da série semanal"],
        ["total_semanas", str(dados.get("total_semanas", 0)), "Semanas na série (segunda a domingo)"],
        ["semanas_completas", str(dados.get("semanas_completas", 0)), "Semanas já encerradas usadas na correlação e regressão"],
        ["semanas_promocao", str(dados.get("semanas_promocao", 0)), "Semanas marcadas com promoção (cupom ou Configuração)"],
        ["resumo_frase", str(dados.get("resumo_frase", "")), "Resumo em uma frase para o topo do Painel"],
        ["ultimas_12_json", json.dumps(ult, ensure_ascii=False), "Faixas de idade nas últimas 12 semanas completas"],
        ["tempo_venda_json", json.dumps(dados.get("tempo_venda", {}), ensure_ascii=False), "Mediana de dias até vender (usado estoque 1 vs novo/lacrado)"],
        ["correlacao_json", json.dumps(dados.get("correlacao", {}), ensure_ascii=False), "Pearson e Spearman (t, t+1, t+2) com e sem semanas de promoção"],
        ["regressao_json", json.dumps(dados.get("regressao", {}), ensure_ascii=False), "Regressão vendas ~ cadastros_t + cadastros_t-1 + promoção + Meta"],
        ["semanas_json", json.dumps(dados.get("semanas", []), ensure_ascii=False), "Série semanal completa desde julho/2025"],
    ]
    return pd.DataFrame(linhas, columns=["chave", "valor", "detalhes"])
