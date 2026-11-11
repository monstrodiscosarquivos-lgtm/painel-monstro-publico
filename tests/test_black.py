"""Testes dos cálculos da Black Monstro 2026 e comparação com 2025."""
import pandas as pd
import pytest
from painel_monstro.motor import black as motor_black
from painel_monstro.saidas import black as saida_black


def test_classificar_tipo_produto():
    assert motor_black.classificar_tipo_produto("LP, Usado, Rock") == "usado"
    assert motor_black.classificar_tipo_produto("LP, Novo/Lacrado, MPB") == "lacrado"
    assert motor_black.classificar_tipo_produto("Compacto, Novo/Lacrado") == "lacrado"
    assert motor_black.classificar_tipo_produto("Livros") == "usado"  # fallback seguro


def test_carregar_premissas_margem():
    mock_margem = [
        ["#", "Pergunta", "Sua estimativa", "Sugestão inicial", "Como estimar", "Valor usado"],
        ["1", "Discos usados: margem média", "", "60%", "", "60,0%"],
        ["2", "Lacrados nacionais: margem média", "", "15%", "", "15,0%"],
        ["", "Custos sobre a venda (taxa + remuneração + imposto)", "", "", "", "18,7%"],
        ["", "Custo por pedido (embalagem + frete), em R$", "", "", "", "8"],
    ]
    p = motor_black.carregar_premissas_margem(mock_margem)
    assert abs(p.margem_usado - 0.60) < 0.001
    assert abs(p.margem_lacrado - 0.15) < 0.001
    assert abs(p.custos_sobre_venda - 0.187) < 0.001


def test_comparacao_2025_conferencia_real():
    """Valida a regra de negócio da Black 2025: 28 a 30/11/2025 = 64 pedidos e R$ ~19,7 mil."""
    pedidos = [
        {"numero": str(100 + i), "email": f"u{i}@exemplo.com", "data": "2025-11-28 10:00:00", "valido": "TRUE", "total": "307,99", "subtotal": "350,00", "desconto": "42,01", "cupom": "BLACKMONSTRO"}
        for i in range(64)
    ]
    df_p = pd.DataFrame(pedidos)
    df_i = pd.DataFrame()
    df_prod = pd.DataFrame()

    df_dia, resumo = motor_black.calcular_black(
        pedidos_df=df_p,
        itens_df=df_i,
        produtos_df=df_prod,
        hoje_str="2026-11-11"
    )

    comp25 = resumo["comparacao_2025"]
    assert comp25["bf25_pedidos"] == 64
    assert abs(comp25["bf25_faturamento"] - 19711.36) < 1.0


def test_calculo_black_dias_e_metas():
    pedidos = [
        {"numero": "1", "email": "a@exemplo.com", "data": "2026-11-10 14:00:00", "valido": "TRUE", "total": "1000,00", "subtotal": "1000,00", "desconto": "0", "cupom": "ANTECIPA10"},
        {"numero": "2", "email": "b@exemplo.com", "data": "2026-11-26 15:00:00", "valido": "TRUE", "total": "5000,00", "subtotal": "5000,00", "desconto": "0", "cupom": "LADOA20"},
    ]
    itens = [
        {"numero": "1", "data": "2026-11-10", "valido": "TRUE", "produto": "LP Teste 1", "valor": "500,00", "quantidade": "2", "produto_id": "10"},
        {"numero": "2", "data": "2026-11-26", "valido": "TRUE", "produto": "LP Teste 2", "valor": "5000,00", "quantidade": "1", "produto_id": "20"},
    ]
    produtos = [
        {"id": "10", "categorias": "LP, Usado"},
        {"id": "20", "categorias": "LP, Novo/Lacrado"},
    ]
    rascunhos = [
        {"produto_id": "20", "lote_black": "26/11"},
    ]

    config_params = {
        "Black: meta do mês": "50000",
        "Black: meta esticada do mês": "60000",
        "Black: meta diária do Antecipa": "870",
        "Black: metas diárias de 26 a 30/11": "5000, 8000, 7000, 7000, 5000",
        "Black: piso da Black": "24000",
        "Black: cupons": "ANTECIPA10, LADOA15, LADOA20, LADOA30, BLACK15, BLACK20, BLACK30",
    }

    df_dia, resumo = motor_black.calcular_black(
        pedidos_df=pd.DataFrame(pedidos),
        itens_df=pd.DataFrame(itens),
        produtos_df=pd.DataFrame(produtos),
        cadastro_rascunhos_df=pd.DataFrame(rascunhos),
        config_params=config_params,
        emails_vip={"b@exemplo.com"},
        hoje_str="2026-11-26"
    )

    assert len(df_dia) == 21  # 10 a 30 de novembro
    # Dia 10 (Antecipa)
    dia_10 = df_dia[df_dia["data"] == "2026-11-10"].iloc[0]
    assert dia_10["fase"] == "Antecipa"
    assert dia_10["meta_dia"] == 870.0
    assert dia_10["faturamento"] == 1000.0

    # Dia 26 (Lado A)
    dia_26 = df_dia[df_dia["data"] == "2026-11-26"].iloc[0]
    assert dia_26["fase"] == "Lado A"
    assert dia_26["meta_dia"] == 5000.0
    assert dia_26["faturamento"] == 5000.0

    # Metas e piso
    assert resumo["meta_mes"] == 50000.0
    assert resumo["meta_esticada"] == 60000.0
    assert resumo["piso_black"] == 24000.0
    assert resumo["acima_do_piso"] is False  # 6000 acumulado < 24000

    # Cupons
    cupons = {c["cupom"]: c for c in resumo["cupons"]}
    assert "ANTECIPA10" in cupons
    assert cupons["ANTECIPA10"]["faturamento"] == 1000.0
    assert "LADOA20" in cupons
    assert cupons["LADOA20"]["faturamento"] == 5000.0

    # Lado A / VIP comprador em 26/11
    assert resumo["lado_a"]["compraram_dia_26"] == 1
    assert resumo["vip"]["compraram_dia_26"] == 1

    # Lotes black
    lotes = {l["lote"]: l for l in resumo["lotes_black"]}
    assert lotes["26/11"]["vendidos"] == 1
    assert lotes["26/11"]["faturamento"] == 5000.0

    # Preparar saídas
    mat_dia = saida_black.preparar_black_dia(df_dia)
    mat_res = saida_black.preparar_black_resumo(resumo)
    assert len(mat_dia) == 22
    assert len(mat_res) > 18
