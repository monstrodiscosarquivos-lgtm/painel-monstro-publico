import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

PAINEL_HTML_PATH = Path(__file__).resolve().parent.parent / "apps-script" / "painel-web" / "Painel.html"


def _add_mes(ym: str, delta: int) -> str:
    y, m = map(int, ym.split("-"))
    tot = y * 12 + (m - 1) + delta
    return f"{tot // 12:04d}-{tot % 12 + 1:02d}"


def _mock_init_js(mock_data: dict) -> str:
    return f"""
    window._writes = [];
    window.PM = {{ nivel: 'especial', nome: 'Tulio', email: 'tulio@exemplo.com' }};
    const mockData = {json.dumps(mock_data)};

    window.google = {{
      script: {{
        run: {{
          withSuccessHandler: function(onSuccess) {{
            return {{
              withFailureHandler: function(onFailure) {{
                return {{
                  ler: function(ranges) {{
                    const dados = {{}};
                    (ranges || []).forEach(r => {{
                      dados[r] = mockData[r] || [];
                    }});
                    setTimeout(() => onSuccess({{ ok: true, dados: dados }}), 10);
                  }},
                  gravar: function(range, values) {{
                    window._writes.push({{ range: range, values: values }});
                    setTimeout(() => onSuccess({{ ok: true }}), 10);
                  }}
                }};
              }}
            }};
          }}
        }}
      }}
    }};
    """


def _abrir_painel(p, init_js: str, tmp_path: Path):
    try:
        browser = p.chromium.launch(channel="msedge", headless=True)
    except Exception:
        try:
            browser = p.chromium.launch(channel="chrome", headless=True)
        except Exception:
            browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    errors = []
    page.on("pageerror", lambda err: errors.append(str(err)))
    page.add_init_script(init_js)
    html_tmp = tmp_path / "Painel.html"
    html_tmp.write_text(
        PAINEL_HTML_PATH.read_text(encoding="utf-8").replace(
            '"__PM_CONTEXTO__"',
            json.dumps({"nivel": "especial", "nome": "Tulio", "email": "tulio@exemplo.com"}),
        ),
        encoding="utf-8",
    )
    page.goto(html_tmp.as_uri())
    return browser, page, errors


def test_painel_resultados_roas_roi_e_ltv(tmp_path):
    """Testa ROAS real, ROI estimado (Configuração e margem_premissas) e LTV seguindo o período escolhido."""
    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    d_cur = (hoje - timedelta(days=2)).isoformat()
    d_ant_7 = (hoje - timedelta(days=9)).isoformat()
    d_old_20 = (hoje - timedelta(days=20)).isoformat()
    d_custom_1 = (hoje - timedelta(days=45)).isoformat()
    d_custom_2 = (hoje - timedelta(days=40)).isoformat()

    ped_num = [["numero"], ["1001"], ["1002"], ["1003"], ["1004"]]
    ped_mail = [["email"], ["cli1@exemplo.com"], ["cli2@exemplo.com"], ["cli1@exemplo.com"], ["cli3@exemplo.com"]]
    ped_body = [
        ["data", "status_pedido", "status_pagamento", "valido", "subtotal", "desconto", "frete", "total", "taxas", "total_liquido", "cupom", "forma_pagamento", "forma_entrega", "estorno"],
        [f"{d_cur} 10:00:00", "open", "Confirmado", "TRUE", "1000,00", "0,00", "0,00", "1000,00", "0,00", "1000,00", "", "pix", "Correios", "0"],
        [f"{d_ant_7} 10:00:00", "open", "Confirmado", "TRUE", "500,00", "0,00", "0,00", "500,00", "0,00", "500,00", "", "pix", "Correios", "0"],
        [f"{d_old_20} 10:00:00", "open", "Confirmado", "TRUE", "200,00", "0,00", "0,00", "200,00", "0,00", "200,00", "", "pix", "Correios", "0"],
        [f"{d_custom_1} 10:00:00", "open", "Confirmado", "TRUE", "400,00", "0,00", "0,00", "400,00", "0,00", "400,00", "", "pix", "Correios", "0"],
    ]
    itens = [
        ["data", "valido", "produto", "valor", "quantidade", "sku", "produto_id"],
        [f"{d_cur} 10:00:00", "TRUE", "LP Disco Usado A", "600,00", "1", "SKU1", "501"],
        [f"{d_cur} 10:00:00", "TRUE", "LP Disco Lacrado B", "400,00", "1", "SKU2", "502"],
        [f"{d_ant_7} 10:00:00", "TRUE", "LP Disco Usado A", "500,00", "1", "SKU1", "501"],
        [f"{d_old_20} 10:00:00", "TRUE", "LP Disco Usado A", "200,00", "1", "SKU1", "501"],
        [f"{d_custom_1} 10:00:00", "TRUE", "LP Disco Lacrado B", "400,00", "1", "SKU2", "502"],
    ]
    prod_id = [["id"], ["501"], ["502"]]
    prod_a = [
        ["nome", "categorias", "preco", "preco_promocional", "estoque", "estoque_ilimitado", "exibir"],
        ["LP Disco Usado A", "LP, Usados", "600,00", "", "1", "false", "true"],
        ["LP Disco Lacrado B", "LP, Novos e Lacrados", "400,00", "", "2", "false", "true"],
    ]
    acd = [
        ["data", "campanha_id", "campanha", "tipo", "status", "orcamento_dia", "investido", "investido_real", "impressoes", "alcance", "frequencia", "cliques_link", "ctr_link", "cpm", "carrinhos", "finalizacoes", "compras", "receita", "roas_real", "cpa_real"],
        [d_cur, "c1", "Vendas Geral", "vendas", "ACTIVE", "100", "100", "110", "1000", "800", "1,25", "50", "5", "100", "5", "2", "1", "1000", "9,09", "110"],
        [d_ant_7, "c1", "Vendas Geral", "vendas", "ACTIVE", "100", "100", "110", "1000", "800", "1,25", "50", "5", "100", "5", "2", "1", "500", "4,55", "110"],
        [d_old_20, "c1", "Vendas Geral", "vendas", "ACTIVE", "100", "100", "110", "1000", "800", "1,25", "50", "5", "100", "5", "2", "1", "200", "1,82", "110"],
        [d_custom_1, "c1", "Vendas Geral", "vendas", "ACTIVE", "100", "200", "220", "1000", "800", "1,25", "50", "5", "100", "5", "2", "1", "400", "1,82", "220"],
    ]
    cfg = [
        ["Parâmetro", "Valor", "Descrição"],
        ["Anúncios: fator de imposto", "1,1", ""],
        ["Anúncios: ROAS verde a partir de", "8", ""],
        ["Anúncios: ROAS amarelo a partir de", "5", ""],
        ["Anúncios: ROAS de equilíbrio", "2,5", ""],
        ["Black: margem do usado", "60", ""],
        ["Black: margem do lacrado", "20", ""],
    ]

    mock_data = {
        "pedidos!A1:A8000": ped_num,
        "pedidos!B1:B8000": ped_mail,
        "pedidos!C1:R8000": ped_body,
        "itens!C1:I9000": itens,
        "produtos!L1:L7000": prod_id,
        "produtos!B1:H7000": prod_a,
        "anuncios_campanha_dia!A1:T3000": acd,
        "Configuração!A1:C80": cfg,
    }

    with sync_playwright() as p:
        browser, page, errors = _abrir_painel(p, _mock_init_js(mock_data), tmp_path)
        page.click("#tab-res")
        page.wait_for_selector("#view-res", state="visible")
        page.wait_for_timeout(300)

        # Seleciona 7 dias: fat=1000, inv=100*1.1=110 => ROAS = 9,1x (p-ok >= 8)
        # Lucro bruto estimado = 600*0.60 + 400*0.20 = 360 + 80 = 440; ROI = (440 - 110)/110 = +300,0%
        page.click('#rs-per button[data-v="7d"]')
        page.wait_for_timeout(200)
        kpi_txt = page.locator("#rs-kpi").inner_text()
        assert "ROAS REAL" in kpi_txt
        assert "9,1x" in kpi_txt
        assert "ROI ESTIMADO" in kpi_txt
        assert "+300,0%" in kpi_txt
        assert "estimativa pelas margens" in kpi_txt
        assert page.locator("#rs-kpi .pill.p-ok").count() >= 2

        # Em 7 dias, cli1 comprou primeiro ha 20 dias (d_old_20), entao 0 clientes novos no periodo de 7d
        ltv_7d = page.locator("#rs-ltv").inner_text()
        assert "ninguém fez a primeira compra nesse período" in ltv_7d

        # Troca para 30 dias: cli1 (1a compra em d_old_20) e cli2 (d_ant_7) entraram no periodo => 2 clientes novos
        page.click('#rs-per button[data-v="30d"]')
        page.wait_for_timeout(200)
        ltv_30d = page.locator("#rs-ltv").inner_text()
        assert "2" in ltv_30d
        assert "primeira compra no período" in ltv_30d
        # Em 30 dias: fat=1700, inv=330 => ROAS = 5,2x (amarelo p-wait, entre 5 e 8)
        assert "5,2x" in page.locator("#rs-kpi").inner_text()
        assert page.locator("#rs-kpi .pill.p-wait").count() >= 1

        # Troca para Escolher datas (d_custom_1..d_custom_2): fat=400, inv=220 => ROAS=1,8x (p-bad), lucro=80 => ROI=-63,6%
        page.click('#rs-per button[data-v="custom"]')
        page.fill("#rs-de", d_custom_1)
        page.fill("#rs-ate", d_custom_2)
        page.locator("#rs-ate").dispatch_event("change")
        page.wait_for_timeout(200)
        kpi_custom = page.locator("#rs-kpi").inner_text()
        assert "1,8x" in kpi_custom
        assert "-63,6%" in kpi_custom
        assert "1" in page.locator("#rs-ltv").inner_text()

        assert errors == []
        browser.close()

    # Tambem confere fallback pela aba margem_premissas quando Configuracao nao tem "Black: margem..."
    mock_fallback = dict(mock_data)
    mock_fallback["Configuração!A1:C80"] = [
        ["Parâmetro", "Valor", "Descrição"],
        ["Anúncios: fator de imposto", "1,1", ""],
    ]
    mock_fallback["margem_premissas!A1:F60"] = [
        ["#", "Pergunta", "Sua estimativa", "Sugestão inicial", "Como estimar", "Valor usado"],
        ["1", "Discos usados: margem média", "", "60%", "", "50,0%"],
        ["2", "Lacrados nacionais: margem média", "", "15%", "", "25,0%"],
    ]
    with sync_playwright() as p:
        browser, page, errors = _abrir_painel(p, _mock_init_js(mock_fallback), tmp_path)
        page.click("#tab-res")
        page.wait_for_selector("#view-res", state="visible")
        page.click('#rs-per button[data-v="7d"]')
        page.wait_for_timeout(200)
        # 600*0.50 + 400*0.25 = 400; ROI = (400 - 110)/110 = +263,6%
        assert "+263,6%" in page.locator("#rs-kpi").inner_text()
        assert errors == []
        browser.close()


def test_painel_anuncios_seletor_periodo(tmp_path):
    """Testa seletor de período na aba Anúncios, recálculo pelos dados diários e aviso de 7d nos anúncios."""
    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    ym_atual = hoje.strftime("%Y-%m")
    ym_ant = _add_mes(ym_atual, -1)

    # Cria entradas diarias:
    # - ontem (dentro de 7d, 14d, 30d)
    # - 10 dias atras (fora de 7d, dentro de 14d e 30d)
    # - 25 dias atras (fora de 14d, dentro de 30d)
    # - dia 05 do mes passado (dentro de mesant)
    d1 = (hoje - timedelta(days=1)).isoformat()
    d10 = (hoje - timedelta(days=10)).isoformat()
    d25 = (hoje - timedelta(days=25)).isoformat()
    d_mesant = f"{ym_ant}-05"

    acd = [
        ["data", "campanha_id", "campanha", "tipo", "status", "orcamento_dia", "investido", "investido_real", "impressoes", "alcance", "frequencia", "cliques_link", "ctr_link", "cpm", "carrinhos", "finalizacoes", "compras", "receita", "roas_real", "cpa_real"],
        [d1, "11", "Campanha A", "vendas", "ACTIVE", "50", "100", "110", "2000", "1500", "1,33", "80", "4", "50", "6", "3", "2", "600", "5,45", "55"],
        [d10, "11", "Campanha A", "vendas", "ACTIVE", "50", "200", "220", "4000", "3000", "1,33", "160", "4", "50", "10", "5", "4", "1200", "5,45", "55"],
        [d25, "22", "Campanha B", "vendas", "PAUSED", "30", "300", "330", "5000", "3500", "1,43", "120", "2,4", "60", "8", "4", "3", "900", "2,73", "110"],
        [d_mesant, "22", "Campanha B", "vendas", "PAUSED", "30", "400", "440", "6000", "4000", "1,50", "150", "2,5", "66", "12", "6", "5", "2000", "4,55", "88"],
    ]
    aads = [
        ["anuncio_id", "anuncio", "campanha_id", "campanha", "conjunto", "tipo", "status", "thumb", "investido_7d", "compras_7d", "receita_7d", "ctr_7d", "ctr_campanha_7d", "frequencia_7d", "investido_30d", "compras_30d", "receita_30d", "cansado", "motivo"],
        ["901", "Criativo Unico", "11", "Campanha A", "Conjunto 1", "vendas", "ACTIVE", "", "100", "2", "600", "4,0", "4,0", "1,3", "300", "6", "1800", "não", ""],
    ]
    cfg = [
        ["Parâmetro", "Valor", "Descrição"],
        ["Anúncios: fator de imposto", "1,1", ""],
    ]
    mock_data = {
        "anuncios_campanha_dia!A1:T3000": acd,
        "anuncios_anuncios!A1:S300": aads,
        "anuncios_resumo!A1:B20": [["chave", "valor"], ["atualizado_em", f"{hoje.isoformat()} 08:00"], ["estado", "ok"]],
        "Configuração!A1:C80": cfg,
    }

    with sync_playwright() as p:
        browser, page, errors = _abrir_painel(p, _mock_init_js(mock_data), tmp_path)
        page.click("#tab-ads")
        page.wait_for_selector("#view-ads", state="visible")
        page.wait_for_timeout(300)

        # Padrao e 7 dias: so d1 (2 compras, R$ 100 investidos)
        assert page.locator('#ad-per button[data-v="7d"]').get_attribute("aria-pressed") == "true"
        tiles_7d = page.locator("#ad-tiles").inner_text()
        assert "COMPRAS · 7 DIAS" in tiles_7d
        assert "R$ 100" in tiles_7d
        assert "2 no período anterior" not in tiles_7d  # no 7d anterior, 10 dias atras tem 4 compras!
        assert "4 no período anterior" in tiles_7d

        # Troca para 14 dias: d1 + d10 = 6 compras, R$ 300
        page.click('#ad-per button[data-v="14d"]')
        page.wait_for_timeout(200)
        tiles_14d = page.locator("#ad-tiles").inner_text()
        assert "COMPRAS · 14 DIAS" in tiles_14d
        assert "R$ 300" in tiles_14d
        assert "3 no período anterior" in tiles_14d  # d25 esta entre 15 e 28 dias atras

        # Troca para 30 dias: d1 + d10 + d25 = 9 compras, R$ 600; Campanha B aparece com R$ 300 investidos
        page.click('#ad-per button[data-v="30d"]')
        page.wait_for_timeout(200)
        tiles_30d = page.locator("#ad-tiles").inner_text()
        assert "COMPRAS · 30 DIAS" in tiles_30d
        assert "R$ 600" in tiles_30d
        camps_30d = page.locator("#ad-camps").inner_text()
        assert "Campanha B" in camps_30d
        assert "R$ 300 investidos em 30 dias" in camps_30d

        # Troca para Mes passado: pega d_mesant (5 compras, R$ 400)
        page.click('#ad-per button[data-v="mesant"]')
        page.wait_for_timeout(200)
        tiles_ma = page.locator("#ad-tiles").inner_text()
        assert "R$ 400" in tiles_ma
        assert "Campanha B" in page.locator("#ad-camps").inner_text()

        # Troca para Escolher datas (d10..d10): 4 compras, R$ 200
        page.click('#ad-per button[data-v="custom"]')
        page.fill("#ad-de", d10)
        page.fill("#ad-ate", d10)
        page.locator("#ad-ate").dispatch_event("change")
        page.wait_for_timeout(200)
        assert "R$ 200" in page.locator("#ad-tiles").inner_text()

        # Secao de anuncios individuais deixa claro que permanece em 7 dias
        ads_sec = page.locator("#ad-ads").locator("..").inner_text()
        assert "Sempre nos últimos 7 dias" in ads_sec
        assert "Criativo Unico" in ads_sec

        assert errors == []
        browser.close()


def test_painel_comissao_lista_todos_meses(tmp_path):
    """Garante que #cm-mes lista todos os meses com pedidos mesmo com mais de 18 pedidos no mês atual."""
    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    ym_atual = hoje.strftime("%Y-%m")
    ym_1 = _add_mes(ym_atual, -1)
    ym_2 = _add_mes(ym_atual, -2)
    ym_3 = _add_mes(ym_atual, -3)

    ped_num = [["numero"]]
    ped_mail = [["email"]]
    ped_body = [["data", "status_pedido", "status_pagamento", "valido", "subtotal", "desconto", "frete", "total", "taxas", "total_liquido", "cupom", "forma_pagamento", "forma_entrega", "estorno"]]

    # 25 pedidos no mes atual (antes causava slice(0, 18) descartando todos os meses anteriores)
    for i in range(1, 26):
        ped_num.append([str(2000 + i)])
        ped_mail.append([f"c{i}@exemplo.com"])
        ped_body.append([f"{ym_atual}-02 10:00:00", "open", "Confirmado", "TRUE", "100,00", "0,00", "0,00", "100,00", "0,00", "100,00", "", "pix", "Correios", "0"])

    # Pedidos em 3 meses anteriores
    for idx, (ym, val) in enumerate([(ym_1, "250,00"), (ym_2, "400,00"), (ym_3, "750,00")], 1):
        ped_num.append([str(3000 + idx)])
        ped_mail.append([f"ant{idx}@exemplo.com"])
        ped_body.append([f"{ym}-15 12:00:00", "open", "Confirmado", "TRUE", val, "0,00", "0,00", val, "0,00", val, "", "pix", "Correios", "0"])

    mock_data = {
        "pedidos!A1:A8000": ped_num,
        "pedidos!B1:B8000": ped_mail,
        "pedidos!C1:R8000": ped_body,
        "Configuração!A1:C80": [["Parâmetro", "Valor", "Descrição"], ["Comissão: percentual (%)", "10", ""]],
    }

    with sync_playwright() as p:
        browser, page, errors = _abrir_painel(p, _mock_init_js(mock_data), tmp_path)
        page.click("#tab-com")
        page.wait_for_selector("#view-com", state="visible")
        page.wait_for_timeout(300)

        opcoes = page.locator("#cm-mes option").all_inner_texts()
        valores = [page.locator("#cm-mes option").nth(i).get_attribute("value") for i in range(len(opcoes))]
        assert set(valores) == {ym_atual, ym_1, ym_2, ym_3}

        # Seleciona o mes de 3 meses atras (pedido 3003, R$ 750) e confere recalculo
        page.select_option("#cm-mes", ym_3)
        page.wait_for_timeout(200)
        assert "3003" in page.locator("#cm-ped").inner_text()
        big_txt = page.locator("#cm-big").inner_text().replace("\xa0", " ")
        assert "R$ 750,00" in big_txt
        assert "R$ 75,00" in big_txt

        assert errors == []
        browser.close()
