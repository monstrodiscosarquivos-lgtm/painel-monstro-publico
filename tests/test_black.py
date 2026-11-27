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


# ----------------------------------------------------------------------------
# Testes da área Black 2026 (5 blocos + aba Black)
# ----------------------------------------------------------------------------
def test_black26_bloco1_cupons_ignora_cancelados_e_agrupa_dia_hora():
    pedidos = pd.DataFrame([
        {"numero": "1", "email": "a@exemplo.com", "data": "2026-11-27 10:15:00", "valido": True, "subtotal": 300.0, "desconto": 75.0, "total": 225.0, "cupom": "BLACK25"},
        {"numero": "2", "email": "b@exemplo.com", "data": "2026-11-27 10:45:00", "valido": True, "subtotal": 500.0, "desconto": 150.0, "total": 350.0, "cupom": "SULCO30"},
        {"numero": "3", "email": "c@exemplo.com", "data": "2026-11-27 14:20:00", "valido": True, "subtotal": 200.0, "desconto": 0.0, "total": 200.0, "cupom": None},
        {"numero": "4", "email": "d@exemplo.com", "data": "2026-11-27 15:00:00", "valido": False, "subtotal": 999.0, "desconto": 300.0, "total": 699.0, "cupom": "BLACK35"},
    ])
    dados = motor_black.calcular_black_2026(
        pedidos, None, None,
        agora_brt=pd.Timestamp("2026-11-27 16:00:00", tz="America/Sao_Paulo"),
    )
    bloco1 = dados["cupons"]
    assert bloco1["total_pedidos"] == 3
    assert bloco1["total_receita"] == 775.0  # (300-75) + (500-150) + 200
    assert bloco1["total_desconto"] == 225.0
    d1 = bloco1["por_dia"][0]
    assert d1["dia"] == "D1" and d1["total_pedidos"] == 3
    assert d1["cupons"]["BLACK25"] == 1 and d1["cupons"]["SULCO30"] == 1 and d1["cupons"]["Sem cupom"] == 1
    hora10 = bloco1["por_hora_hoje"][10]
    assert hora10["hora"] == "10h" and hora10["total_pedidos"] == 2
    tab = {r["cupom"]: r for r in bloco1["tabela"]}
    assert "BLACK35" not in tab  # cancelado ignorado
    assert tab["BLACK25"]["receita"] == 225.0 and tab["BLACK25"]["desconto"] == 75.0


def test_black26_bloco2_comparacao_2026_x_2025_dias_futuros_em_branco():
    pedidos = pd.DataFrame([
        # 2025: D1 (28/11) 2 pedidos, D2 (29/11) 1 pedido, D4 (01/12) 1 pedido
        {"numero": "2501", "email": "x@exemplo.com", "data": "2025-11-28 09:00:00", "valido": True, "subtotal": 400.0, "desconto": 100.0, "total": 300.0, "cupom": "BLACKMONSTRO"},
        {"numero": "2502", "email": "y@exemplo.com", "data": "2025-11-28 18:00:00", "valido": True, "subtotal": 200.0, "desconto": 0.0, "total": 200.0, "cupom": ""},
        {"numero": "2503", "email": "z@exemplo.com", "data": "2025-11-29 12:00:00", "valido": True, "subtotal": 300.0, "desconto": 75.0, "total": 225.0, "cupom": "BLACKMONSTRO"},
        {"numero": "2504", "email": "w@exemplo.com", "data": "2025-12-01 20:00:00", "valido": True, "subtotal": 300.0, "desconto": 75.0, "total": 225.0, "cupom": "BLACKMONSTRO"},
        # 2026: D1 (27/11) 3 pedidos
        {"numero": "2601", "email": "a@exemplo.com", "data": "2026-11-27 10:00:00", "valido": True, "subtotal": 400.0, "desconto": 100.0, "total": 300.0, "cupom": "BLACK25"},
        {"numero": "2602", "email": "b@exemplo.com", "data": "2026-11-27 11:00:00", "valido": True, "subtotal": 400.0, "desconto": 100.0, "total": 300.0, "cupom": "BLACK25"},
        {"numero": "2603", "email": "c@exemplo.com", "data": "2026-11-27 12:00:00", "valido": True, "subtotal": 200.0, "desconto": 0.0, "total": 200.0, "cupom": None},
    ])
    dados = motor_black.calcular_black_2026(
        pedidos, None, None,
        agora_brt=pd.Timestamp("2026-11-27 15:00:00", tz="America/Sao_Paulo"),
    )
    comp = dados["comp_2025"]
    d1, d2, d3, d4 = comp["dias"]
    assert d1["ocorrido"] is True
    assert d1["y2026"]["pedidos"] == 3 and d1["y2025"]["pedidos"] == 2
    assert d1["variacao"]["pedidos_pct"] == 50.0
    assert d1["y2025"]["pct_com_cupom"] == 50.0
    assert d1["y2026"]["pct_com_cupom"] == 66.7
    # D2..D4 ainda não ocorreram: 2026 e variação devem ficar None (em branco)
    for d in (d2, d3, d4):
        assert d["ocorrido"] is False
        assert d["y2026"] is None and d["variacao"] is None
    assert d2["y2025"]["pedidos"] == 1 and d4["y2025"]["pedidos"] == 1


def test_black26_bloco3_meta_ads_todos_os_gatilhos():
    campanhas = [
        {
            "campanha": "black26_rmk",
            "gasto_hoje": 30.0, "gasto_ontem": 20.0, "gasto_3d": 80.0,
            "compras_hoje": 0, "compras_ontem": 0, "compras_3d": 0,
            "receita_hoje": 0.0, "receita_3d": 0.0,
            "cliques_hoje": 10, "cliques_3d": 25,
            "frequencia_hoje": 2.1, "frequencia_3d": 4.5,
            "orcamento_dia": 50.0,
        },
        {
            "campanha": "prosp_vendas_recorrente",
            "gasto_hoje": 95.0, "gasto_ontem": 90.0, "gasto_3d": 270.0,
            "compras_hoje": 4, "compras_ontem": 3, "compras_3d": 10,
            "receita_hoje": 900.0, "receita_3d": 2200.0,
            "cliques_hoje": 80, "cliques_3d": 200,
            "frequencia_hoje": 1.3, "frequencia_3d": 1.8,
            "orcamento_dia": 100.0,
        },
    ]
    res = motor_black.avaliar_gatilhos_meta(campanhas, atualizado_em="2026-11-27 14:00")
    frases = [a["frase"] for a in res["acoes"]]
    assert "Tire R$50 de black26_rmk e passe para a campanha comum" in frases
    assert "Reduza black26_rmk à metade" in frases
    assert "Troque o criativo de black26_rmk" in frases  # CPC hoje = 30/10 = 3.00 > 2.50
    assert "Aumente prosp_vendas_recorrente em 20% (1 vez por dia)" in frases  # ROAS 9.47 > 6 e 95 >= 90% de 100

    # Caso nada dispare
    res_ok = motor_black.avaliar_gatilhos_meta([{
        "campanha": "black26_loja_fisica_2811",
        "gasto_hoje": 20.0, "gasto_ontem": 10.0, "gasto_3d": 30.0,
        "compras_hoje": 1, "compras_ontem": 1, "compras_3d": 2,
        "receita_hoje": 100.0, "receita_3d": 150.0,
        "cliques_hoje": 20, "cliques_3d": 30,
        "frequencia_hoje": 1.2, "frequencia_3d": 1.5,
        "orcamento_dia": 50.0,
    }])
    assert [a["frase"] for a in res_ok["acoes"]] == ["Não mexa em nada"]


def test_black26_bloco4_saude_custo_variante_vs_padrao_e_semaforo():
    # 4 sextas anteriores a 27/11/2026: 30/10, 06/11, 13/11, 20/11
    # Em cada sexta base: 2 pedidos de R$200 (sem desconto), custo R$100 cada -> margem base = R$200/sexta
    pedidos_base = []
    itens_base = []
    for idx, dt in enumerate(["2026-10-30", "2026-11-06", "2026-11-13", "2026-11-20"]):
        for k in range(2):
            num = f"B{idx}{k}"
            pedidos_base.append({"numero": num, "email": "base@exemplo.com", "data": f"{dt} 12:00:00", "valido": True, "subtotal": 200.0, "desconto": 0.0, "total": 200.0, "cupom": ""})
            itens_base.append({"numero": num, "valor": 200.0, "quantidade": 1, "produto_id": "101", "sku": "SKU1"})

    # Na Black D1 (27/11): 5 pedidos de R$200 com 25% desconto (receita líq R$150 cada = R$750)
    # 3 itens usam produto 101 (tem cost = 80 na Nuvemshop), 2 itens usam produto 202 (sem cost -> usa padrão 50% de 200 = 100)
    # Custo total Black = 3*80 + 2*100 = 440 -> Margem Black = 750 - 440 = 310 (> 200 base -> verde!)
    pedidos_bk = []
    itens_bk = []
    for k in range(5):
        num = f"K{k}"
        pid = "101" if k < 3 else "202"
        pedidos_bk.append({"numero": num, "email": "bk@exemplo.com", "data": "2026-11-27 11:00:00", "valido": True, "subtotal": 200.0, "desconto": 50.0, "total": 150.0, "cupom": "BLACK25"})
        itens_bk.append({"numero": num, "valor": 200.0, "quantidade": 1, "produto_id": pid, "sku": ""})

    produtos = pd.DataFrame([
        {"id": "101", "sku": "SKU1", "custo": 80.0},
        {"id": "202", "sku": "SKU2", "custo": float("nan")},
    ])
    dados = motor_black.calcular_black_2026(
        pd.DataFrame(pedidos_base + pedidos_bk),
        pd.DataFrame(itens_base + itens_bk),
        produtos,
        config_params={"Black: custo padrão %": "50"},
        agora_brt=pd.Timestamp("2026-11-27 12:00:00", tz="America/Sao_Paulo"),
    )
    saude = dados["saude"]
    assert saude["pct_itens_padrao"] == 40.0  # 2 de 5 itens sem custo
    assert saude["custo_black"] == 440.0
    assert saude["margem_black"] == 310.0
    assert saude["margem_base"] == 240.0  # 2 pedidos/dia * (200 - 80) = 240
    assert saude["semaforo"] == "verde"
    assert saude["frase"].startswith("Para compensar o desconto, precisamos de ")


def test_black26_bloco5_projecao_ritmo_e_curva_2025_e_privacidade_aba():
    pedidos = pd.DataFrame([
        # 2025: 2 pedidos nas primeiras 12h (50% da receita), 2 pedidos depois (50%) -> total 4 pedidos, R$1000
        {"numero": "251", "email": "cli1@exemplo.com", "data": "2025-11-28 08:00:00", "valido": True, "subtotal": 250.0, "desconto": 0.0, "total": 250.0, "cupom": "BLACKMONSTRO"},
        {"numero": "252", "email": "cli2@exemplo.com", "data": "2025-11-28 11:00:00", "valido": True, "subtotal": 250.0, "desconto": 0.0, "total": 250.0, "cupom": "BLACKMONSTRO"},
        {"numero": "253", "email": "cli3@exemplo.com", "data": "2025-11-29 14:00:00", "valido": True, "subtotal": 250.0, "desconto": 0.0, "total": 250.0, "cupom": "BLACKMONSTRO"},
        {"numero": "254", "email": "cli4@exemplo.com", "data": "2025-12-01 18:00:00", "valido": True, "subtotal": 250.0, "desconto": 0.0, "total": 250.0, "cupom": "BLACKMONSTRO"},
        # 2026: 3 pedidos nas primeiras 12h = R$600
        {"numero": "261", "email": "sigilo@exemplo.com", "data": "2026-11-27 09:00:00", "valido": True, "subtotal": 200.0, "desconto": 0.0, "total": 200.0, "cupom": "BLACK25"},
        {"numero": "262", "email": "sigilo@exemplo.com", "data": "2026-11-27 10:00:00", "valido": True, "subtotal": 200.0, "desconto": 0.0, "total": 200.0, "cupom": "BLACK25"},
        {"numero": "263", "email": "sigilo@exemplo.com", "data": "2026-11-27 11:30:00", "valido": True, "subtotal": 200.0, "desconto": 0.0, "total": 200.0, "cupom": "BLACK25"},
    ])
    dados = motor_black.calcular_black_2026(
        pedidos, None, None,
        agora_brt=pd.Timestamp("2026-11-27 12:00:00", tz="America/Sao_Paulo"),
    )
    proj = dados["projecao"]
    assert proj["horas_decorridas"] == 12.0
    # Ritmo: 600 / 12 * 96 = 4800; Curva 2025: 600 / 0.50 = 1200
    assert proj["ritmo_atual"]["receita"] == 4800.0
    assert proj["curva_2025"]["receita"] == 1200.0
    assert proj["faixa"]["receita"] == {"min": 1200.0, "max": 4800.0}
    assert proj["falta_bater_2025"]["receita"] == 400.0
    assert proj["falta_bater_2025"]["pedidos"] == 1

    # Aba Black nunca contém email ou dado pessoal
    df_aba = saida_black.preparar_aba_black(dados)
    texto_aba = df_aba.to_string()
    assert "sigilo@exemplo.com" not in texto_aba
    assert "cli1@exemplo.com" not in texto_aba
