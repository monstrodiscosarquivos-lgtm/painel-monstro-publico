import json
import os
import re
import subprocess
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright

PAINEL_HTML_PATH = Path(__file__).resolve().parent.parent / "apps-script" / "painel-web" / "Painel.html"


def test_painel_black_mobile_playwright():
    """Testa a aba Black e Custos/Margens no Painel.html em viewport mobile (390px, iPhone)."""
    assert PAINEL_HTML_PATH.exists(), f"Painel.html nao encontrado em {PAINEL_HTML_PATH}"
    html_file = PAINEL_HTML_PATH.as_posix()
    file_url = f"file:///{html_file}"

    mock_black_resumo = [
        ["chave", "valor", "detalhes"],
        ["atualizado_em", "2026-11-11 10:58:17", ""],
        ["hoje_data", "2026-11-11", ""],
        ["hoje_faturamento", "1250.00", ""],
        ["hoje_pedidos", "5", ""],
        ["hoje_ticket_medio", "250.00", ""],
        ["hoje_meta", "930.00", ""],
        ["hoje_atingimento_pct", "134.4", ""],
        ["periodo_faturamento", "2480.00", ""],
        ["periodo_pedidos", "10", ""],
        ["periodo_ticket_medio", "248.00", ""],
        ["meta_mes", "50000.00", ""],
        ["meta_esticada", "60000.00", ""],
        ["piso_black", "24000.00", ""],
        ["atingimento_mes_pct", "5.0", ""],
        ["atingimento_esticada_pct", "4.1", ""],
        ["acima_do_piso", "0", ""],
        ["diferenca_piso", "-21520.00", ""],
        ["sobra_total", "620.00", ""],
        ["cupons_json", json.dumps([
            {"cupom": "ANTECIPA10", "pedidos": 3, "faturamento": 750.0, "desconto": 75.0, "ticket_medio": 250.0, "oficial": True},
            {"cupom": "SEM_CUPOM", "pedidos": 7, "faturamento": 1730.0, "desconto": 0.0, "ticket_medio": 247.14, "oficial": False}
        ]), "Lista de cupons"],
        ["lado_a_json", json.dumps({"total_inscritos": 42, "entradas_por_dia": {"2026-11-10": 10}, "compraram_dia_26": 0}), "Lado A"],
        ["vip_json", json.dumps({"total_inscritos": 42, "entradas_por_dia": {"2026-11-10": 10}, "compraram_dia_26": 0}), "Lado A (alias)"],
        ["comparacao_2025_json", json.dumps({
            "bf25_pedidos": 64, "bf25_faturamento": 19711.48, "bf25_ticket": 307.99,
            "bf26_pedidos": 0, "bf26_faturamento": 0.0, "bf26_ticket": 0.0
        }), "Comparativo 2025 vs 2026"],
        ["top_discos_json", json.dumps([
            {"produto": "LP Belchior - Alucinacao (Novo/Lacrado)", "quantidade": 2, "faturamento": 440.0},
            {"produto": "LP Secos & Molhados - Secos & Molhados", "quantidade": 1, "faturamento": 150.0}
        ]), "Top discos"],
        ["lotes_black_json", json.dumps([
            {"lote": "26/11", "cadastrados": 15, "vendidos": 0, "faturamento": 0.0, "restantes": 15},
            {"lote": "27/11", "cadastrados": 20, "vendidos": 0, "faturamento": 0.0, "restantes": 20},
            {"lote": "28/11", "cadastrados": 10, "vendidos": 0, "faturamento": 0.0, "restantes": 10},
            {"lote": "29/11", "cadastrados": 5, "vendidos": 0, "faturamento": 0.0, "restantes": 5}
        ]), "Lotes Black"],
        ["alertas_json", json.dumps([]), "Alertas"]
    ]

    mock_black_dia = [
        ["data", "fase", "faturamento", "pedidos", "ticket_medio", "meta_dia", "atingimento_pct", "faturamento_acum", "meta_acum", "custo_disco", "custos_venda", "gasto_anuncio", "sobra_dia", "sobra_acum", "roas_anuncio"],
        ["2026-11-10", "Antecipa", "1230,00", "5", "246,00", "930", "132,3", "1230,00", "930", "630,00", "230,00", "50,00", "320,00", "320,00", "24,6"],
        ["2026-11-11", "Antecipa", "1250,00", "5", "250,00", "930", "134,4", "2480,00", "1860", "640,00", "235,00", "55,00", "300,00", "620,00", "22,7"]
    ]

    mock_margem = [
        ["#", "Pergunta", "Sua estimativa", "Sugestão inicial", "Como estimar", "Valor usado"],
        ["MARGEM DA LOJA ONLINE · premissas", "", "", "", "", ""],
        ["", "", "", "", "", ""],
        ["#", "Pergunta", "Sua estimativa", "Sugestão inicial", "Como estimar", "Valor usado"],
        ["1", "Discos usados: margem média", "", "60%", "Margem = 1 - custo/venda", "60,0%"],
        ["2", "Lacrados nacionais: margem média", "", "15%", "Preço menos custo", "15,0%"],
        ["3", "Lacrados importados: margem média", "", "15%", "Preço menos custo com impostos", "15,0%"],
        ["4", "Lançamentos do selo Monstro: margem média", "", "40%", "Custo fabricação", "40,0%"],
        ["5", "Livros: margem média", "", "30%", "Preço menos custo", "30,0%"],
        ["6", "Embalagem por pedido (R$)", "", "4", "Caixa e plástico", "4"],
        ["7", "Frete pago pela loja por pedido (R$)", "", "4", "Média de frete", "4"],
        ["8", "Taxa média de pagamento (%)", "", "2,40%", "Taxas Nuvem Pago", "2,4%"],
        ["9", "Remuneração de marketing (%)", "", "10%", "Comissão vendas", "10,0%"],
        ["10", "Regime tributário da loja", "", "Simples Nacional", "Simples comércio", "Simples Nacional"],
        ["11", "Faturamento últimos 12m (R$)", "", "433752", "Soma físico + online", "433752"],
        ["12", "Alíquota efetiva de imposto (%)", "", "6,3%", "DAS Simples", "6,3%"],
        ["13", "O contador separa discos e livros?", "", "Não sei", "Imunidade constitucional", "Não sei"],
        ["", "Custos fixos", "", "", "", ""],
        ["14", "Plano da Nuvemshop (R$ por mês)", "", "449", "Fatura Escala", "449"],
        ["15", "Brevo e outras ferramentas (R$)", "", "154", "Brevo setembro", "154"],
        ["16", "Aluguel da loja com IPTU (R$)", "", "3600", "Contrato aluguel", "3600"],
        ["17", "Energia com ar (R$)", "", "700", "Equatorial média", "700"],
        ["18", "Água (R$)", "", "100", "Saneago", "100"],
        ["19", "Internet e telefone (R$)", "", "150", "Plano internet", "150"],
        ["20", "Funcionários salários (R$)", "", "6000", "2 funcionários", "6000"],
        ["21", "Encargos sobre salários (%)", "", "30%", "FGTS, 13, férias", "30%"],
        ["22", "Contador (R$)", "", "400", "Mensalidade contador", "400"],
        ["23", "Outros custos fixos (R$)", "", "", "Limpeza e taxas", ""],
        ["24", "Faturamento médio loja física (R$)", "", "10000", "Físico", "10000"],
        ["25", "Parte dos custos fixos loja online (%)", "", "72%", "Divisão faturamento", "72%"],
        ["", "", "", "", "", ""],
        ["RESULTADO (calculado)", "", "", "", "", ""],
        ["", "Alíquota efetiva usada", "", "", "", "6,3%"],
        ["", "Custos sobre a venda", "", "", "", "18,7%"],
        ["", "Custo por pedido", "", "", "", "8"],
        ["", "", "", "", "", ""],
        ["Desconto", "Usado: sobra a cada R$ 100", "Usado: vendas para empatar", "Lacrado nacional", "Selo Monstro", "Livro"],
        ["0%", "R$ 41,30", "1,0x", "-R$ 3,70", "R$ 21,30", "R$ 11,30"],
        ["10%", "R$ 33,17", "1,2x", "-R$ 11,83", "R$ 13,17", "R$ 3,17"],
        ["20%", "R$ 25,04", "1,6x", "-R$ 19,96", "R$ 5,04", "-R$ 4,96"],
        ["25%", "R$ 20,97", "2,0x", "-R$ 24,03", "R$ 0,97", "-R$ 9,03"],
        ["30%", "R$ 16,91", "2,4x", "-R$ 28,09", "-R$ 3,09", "-R$ 13,09"],
        ["", "", "", "", "", ""],
        ["A sobra é antes do custo por pedido e anúncio.", "", "", "", "", ""],
        ["", "", "", "", "", ""],
        ["CUSTOS FIXOS E PONTO DE EQUILÍBRIO", "", "", "", "", ""],
        ["", "Custos fixos da loja inteira por mês (R$)", "", "", "", "R$ 13.353"],
        ["", "Parte atribuída à loja online (%)", "", "", "", "72%"],
        ["", "Custos fixos da loja online por mês (R$)", "", "", "", "R$ 9.659"],
        ["", "Sobra média por real vendido", "", "", "", "26,6%"],
        ["", "Faturamento online para pagar custos fixos (R$)", "", "", "", "R$ 36.356"],
        ["", "Faturamento online médio últimos 12m (R$)", "", "", "", "R$ 26.146"]
    ]

    mock_cad = [
        ["id", "titulo", "preco", "status", "produto_id", "conferido_em", "conferido_por", "marcado_vinil", "atualizado_em", "lote_black"],
        ["2026-11-01-01", "LP Secos & Molhados", "150", "rascunho", "101", "", "", "", "2026-11-05 18:30", "26/11"],
        ["2026-11-02-01", "LP Belchior - Alucinacao", "220", "publicado", "102", "2026-11-06 12:00", "tulio", "", "2026-11-02 12:00", "27/11"]
    ]

    mock_data = {
        "black_resumo!A1:C50": mock_black_resumo,
        "black_dia!A1:O30": mock_black_dia,
        "margem_premissas!A1:F60": mock_margem,
        "cadastro_rascunhos!A1:AZ3000": mock_cad,
        "cadastro_fotos!A1:F3000": [["id_foto", "ordem", "papel", "arquivo_drive_id"]],
        "Configuração!A1:C80": [["Parâmetro", "Valor", "Descrição"]]
    }

    init_js = f"""
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

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="msedge", headless=True)
        except Exception:
            try:
                browser = p.chromium.launch(channel="chrome", headless=True)
            except Exception:
                browser = p.chromium.launch(headless=True)
        # Mobile viewport 390x844 (iPhone 12/13/14)
        context = browser.new_context(viewport={"width": 390, "height": 844})
        page = context.new_page()
        page.on("console", lambda msg: print(f"PAGE CONSOLE: {msg.type} {msg.text}"))
        page.on("pageerror", lambda err: print(f"PAGE ERROR: {err}"))
        page.add_init_script(init_js)
        page.goto(file_url)

        # 1. Verifica botao da aba Black e clica nele
        tab_black = page.locator("#tab-black")
        assert tab_black.count() == 1
        tab_black.click()
        page.wait_for_timeout(300)

        # 2. Confirma que #view-black esta visivel e #view-painel escondida
        assert page.locator("#view-black").is_visible()
        assert not page.locator("#view-painel").is_visible()

        # 3. Verifica Placar da Black
        placar = page.locator("#black-placar")
        assert placar.is_visible()
        text_placar = placar.inner_text().upper()
        assert "HOJE (2026-11-11)" in text_placar
        assert "R$ 1.250" in text_placar
        assert "ACUMULADO BLACK" in text_placar
        assert "R$ 2.480" in text_placar
        assert "R$ 620" in text_placar

        # 4. Verifica grafico de faturamento diario
        assert page.locator("#black-chart svg").count() >= 1

        # 5. Verifica tabela Por Cupom
        cupons_tbl = page.locator("#black-cupons table")
        assert cupons_tbl.is_visible()
        assert "ANTECIPA10" in cupons_tbl.inner_text()

        # 6. Verifica tabela de Sobra
        sobra_tbl = page.locator("#black-sobra table")
        assert sobra_tbl.is_visible()
        assert "Antecipa" in sobra_tbl.inner_text()

        # 7. Verifica comparacao 2025
        comp_tbl = page.locator("#black-comp25 table")
        assert comp_tbl.is_visible()
        assert "19.711" in comp_tbl.inner_text()
        assert "64" in comp_tbl.inner_text()

        # 8. Verifica Lotes Black e Top Discos
        lotes_tbl = page.locator("#black-lotes table")
        assert lotes_tbl.is_visible()
        assert "26/11" in lotes_tbl.inner_text()
        top_tbl = page.locator("#black-top table")
        assert top_tbl.is_visible()
        assert "Belchior" in top_tbl.inner_text()

        # 9. Vai para aba Configurações e testa Custos e Margens
        page.locator("#tab-config").click()
        page.wait_for_timeout(300)
        assert page.locator("#view-config").is_visible()

        sec_margem = page.locator("#sec-margem")
        assert sec_margem.is_visible()
        assert "Custos e margens" in sec_margem.inner_text()

        # Input da pergunta 1 (Discos usados)
        inp1 = page.locator("#mp-r5")
        assert inp1.is_visible()
        inp1.fill("65%")
        page.locator("#mp-save").click()
        page.wait_for_timeout(300)

        # Confirma que write foi disparado para margem_premissas!C5
        writes = page.evaluate("window._writes")
        mp_writes = [w for w in writes if "margem_premissas!C5" in w.get("range", "")]
        assert len(mp_writes) >= 1
        assert mp_writes[0]["values"] == [["65%"]]

        # 10. Vai para aba Cadastro e verifica filtro Black e card
        page.locator("#tab-cad").click()
        page.wait_for_timeout(300)
        assert page.locator("#view-cad").is_visible()

        # Botao de filtro Black 26/11 (Lado A)
        btn_b26 = page.locator("#cd-filtro button[data-v='black_26']")
        assert btn_b26.count() == 1
        assert "Black 26/11 (Lado A) (1)" in btn_b26.inner_text()

        # Clica no filtro Black 26/11
        btn_b26.click()
        page.wait_for_timeout(200)

        # Confirma que card exibiu a pill Lote Black: 26/11
        card = page.locator("#cd-lista .fcard").first
        assert "Lote Black: 26/11" in card.inner_text()

        browser.close()
