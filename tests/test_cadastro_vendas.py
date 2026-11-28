"""Testes da análise semanal 'Cadastro de discos x vendas' e otimizações da rotina (dados fictícios)."""
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
from playwright.sync_api import sync_playwright

from painel_monstro.config import Config
from painel_monstro.motor import cadastro_vendas as motor_cv
from painel_monstro.saidas import cadastro as saida_cadastro, cadastro_vendas as saida_cv
from painel_monstro.saidas.planilha_google import PlanilhaGoogle
from tests.test_cadastro import Drive, linha as linha_cad
from tests.test_planilha_google import PlanilhaFalsa

PAINEL_HTML_PATH = Path(__file__).resolve().parent.parent / "apps-script" / "painel-web" / "Painel.html"


def test_cadastro_vendas_serie_idade_tempo_correlacao_e_regressao():
    """Cenário sintético de 12 semanas onde cadastros em t-1 aumentam vendas em t (fora de promoção)."""
    produtos = []
    pedidos = []
    itens = []
    ads = []

    base_seg = pd.Timestamp("2026-01-05")  # segunda-feira
    cad_por_sem = [10, 30, 12, 35, 14, 40, 15, 32, 18, 38, 20, 42]
    pid_seq = 1
    ped_seq = 1

    for w, n_cad in enumerate(cad_por_sem):
        seg = base_seg + pd.Timedelta(days=7 * w)
        promo = (w == 4 or w == 9)  # semana 4 por cupom, semana 9 manual via Configuração
        gasto = 100.0 + (w % 4) * 15.0 + (20.0 if promo else 0.0)
        ads.append({"data": seg.strftime("%Y-%m-%d"), "investido_real": gasto})

        for j in range(n_cad):
            tipo = "Novo/Lacrado" if j % 4 == 0 else "Usado"
            est = 3 if tipo == "Novo/Lacrado" else 1
            produtos.append({
                "id": str(pid_seq),
                "nome": f"LP Banda {pid_seq} - Album {pid_seq} ({tipo})",
                "categorias": f"LP, {tipo}",
                "estoque": est,
                "estoque_ilimitado": False,
                "criado_em": (seg + pd.Timedelta(days=j % 5)).strftime("%Y-%m-%d 10:00:00"),
                "sku": f"SKU{pid_seq}",
            })
            pid_seq += 1

        # Pedidos da semana respondem fortemente ao cadastro da semana anterior (+1 pedido a cada ~3 cadastros anteriores) + bônus promoção
        cad_ant = cad_por_sem[w - 1] if w > 0 else 10
        n_ped = 5 + round(cad_ant / 3.0) + (8 if promo else 0)
        cup = "CRIANCA15" if w == 4 else ""

        for k in range(n_ped):
            # Alterna vendas entre disco recém-cadastrado (<7d / 8..30d) e disco antigo (>90d)
            if k % 2 == 0:
                ref_prod = produtos[-1]  # recém-cadastrado na mesma semana (<=7d, novo/lacrado ou usado)
            else:
                ref_prod = produtos[0]  # cadastrado na semana 0
            dt_v = (seg + pd.Timedelta(days=6)).strftime("%Y-%m-%d 14:00:00")
            num = f"P{ped_seq}"
            pedidos.append({
                "numero": num,
                "email": f"pessoa{ped_seq}@exemplo.com",
                "data": dt_v,
                "valido": True,
                "subtotal": 200.0,
                "desconto": 20.0 if cup else 0.0,
                "total": 180.0 if cup else 200.0,
                "cupom": cup,
            })
            itens.append({
                "numero": num,
                "data": dt_v,
                "valido": True,
                "produto": ref_prod["nome"],
                "valor": 200.0,
                "quantidade": 1,
                "sku": ref_prod["sku"],
                "produto_id": ref_prod["id"],
            })
            ped_seq += 1

    # Também inclui livro (não entra em discos_cadastrados) e pedido cancelado (não entra em pedidos)
    produtos.append({"id": "9999", "nome": "Livro Historia do Rock", "categorias": "Livros", "estoque": 5, "criado_em": "2026-01-06 10:00:00", "sku": "LIV1"})
    pedidos.append({"numero": "PCANC", "email": "canc@exemplo.com", "data": "2026-01-12 10:00:00", "valido": False, "subtotal": 500.0, "desconto": 0.0, "total": 500.0, "cupom": ""})

    dados = motor_cv.calcular_cadastro_vendas(
        produtos_df=pd.DataFrame(produtos),
        pedidos_df=pd.DataFrame(pedidos),
        itens_df=pd.DataFrame(itens),
        anuncios_campanha_dia_df=pd.DataFrame(ads),
        config_params={motor_cv.CHAVE_SEMANAS_PROMO: "09/03/2026 a 15/03/2026"},
        agora_brt=pd.Timestamp("2026-03-30 10:00:00", tz="America/Sao_Paulo"),  # semana 12 ainda aberta, semanas 0..11 completas
    )

    assert dados["semanas_completas"] == 12
    assert dados["semanas"][0]["discos_cadastrados"] == 10  # livro não contou
    assert dados["semanas"][4]["promocao"] == 1 and "CRIANCA15" in dados["semanas"][4]["motivo_promocao"]
    assert dados["semanas"][9]["promocao"] == 1 and "Configuração" in dados["semanas"][9]["motivo_promocao"]
    assert dados["semanas_promocao"] == 2

    # Venda de disco novo (<30d > 0) e tempo até vender separado usado vs novo
    assert dados["ultimas_12"]["pct_rec_menos_30d"] > 40.0
    assert dados["tempo_venda"]["usado_estoque_1"]["n"] > 0
    assert dados["tempo_venda"]["novo_lacrado"]["n"] > 0

    # Correlação em t+1 forte e positiva (e ainda maior sem semanas de promoção)
    cor_todas_t1 = dados["correlacao"]["todas"][1]
    cor_sem_t1 = dados["correlacao"]["sem_promocao"][1]
    assert cor_todas_t1["lag"] == 1 and cor_todas_t1["pearson_pedidos"] > 0.7
    assert cor_sem_t1["n"] < cor_todas_t1["n"]
    assert cor_sem_t1["pearson_pedidos"] > 0.9
    assert cor_sem_t1["spearman_pedidos"] > 0.85

    # Regressão múltipla detecta efeito positivo significativo na semana seguinte (+10 discos -> ~+3.3 pedidos)
    reg_ped = dados["regressao"]["pedidos"]
    assert reg_ped["disponivel"] is True
    assert reg_ped["efeito_10_seguinte"] > 2.0
    assert reg_ped["ic_10_seguinte"][0] < reg_ped["efeito_10_seguinte"] < reg_ped["ic_10_seguinte"][1]
    assert "indicativo" in reg_ped["aviso"]
    assert "Nas últimas 12 semanas" in dados["resumo_frase"]

    # Saída da aba agregada não contém nenhum dado de cliente
    df_aba = saida_cv.preparar_aba_cadastro_vendas(dados)
    texto_aba = df_aba.to_string()
    assert "@exemplo.com" not in texto_aba
    assert set(df_aba["chave"]) >= {"resumo_frase", "semanas_json", "correlacao_json", "regressao_json", "tempo_venda_json"}


def test_cadastro_passo_rotina_pula_gravacao_quando_rascunho_nao_mudou(tmp_path):
    """Evita dezenas de chamadas ao Google Sheets quando o rascunho já está igual na planilha."""
    p = PlanilhaGoogle(PlanilhaFalsa())
    l = linha_cad(id="disco-unchanged", status="rascunho", preco="100", preco_referencia="",
                  pendencias="", peso_kg="0.4", altura_cm="2.5", largura_cm="32", comprimento_cm="32")
    p.substituir(saida_cadastro.ABA, pd.DataFrame([l]))
    aba = p._ss.worksheet(saida_cadastro.ABA)
    chamadas = []
    orig_update = aba.update

    def contar_update(*a, **kw):
        chamadas.append(a)
        return orig_update(*a, **kw)

    aba.update = contar_update
    saida_cadastro.passo_rotina(Config(), p, SimpleNamespace(produtos=pd.DataFrame()), tmp_path, api=object(), drive=Drive())
    assert chamadas == []


def test_painel_cadastro_x_vendas_playwright():
    assert PAINEL_HTML_PATH.exists()
    dados = motor_cv.calcular_cadastro_vendas(
        produtos_df=pd.DataFrame([
            {"id": "1", "nome": "LP Teste - Disco 1 (Usado)", "categorias": "LP, Usado", "estoque": 1, "criado_em": "2026-01-05 10:00:00", "sku": "S1"},
            {"id": "2", "nome": "LP Teste - Disco 2 (Novo/Lacrado)", "categorias": "LP, Novo/Lacrado", "estoque": 2, "criado_em": "2026-01-12 10:00:00", "sku": "S2"},
        ]),
        pedidos_df=pd.DataFrame([
            {"numero": "10", "email": "a@exemplo.com", "data": "2026-01-14 12:00:00", "valido": True, "subtotal": 200.0, "desconto": 0.0, "total": 200.0, "cupom": ""},
        ]),
        itens_df=pd.DataFrame([
            {"numero": "10", "data": "2026-01-14 12:00:00", "valido": True, "produto": "LP Teste - Disco 1 (Usado)", "valor": 200.0, "quantidade": 1, "sku": "S1", "produto_id": "1"},
        ]),
        agora_brt=pd.Timestamp("2026-02-02 10:00:00", tz="America/Sao_Paulo"),
    )
    df_aba = saida_cv.preparar_aba_cadastro_vendas(dados)
    mock_cv = [["chave", "valor", "detalhes"]] + df_aba.astype(str).values.tolist()
    mock_data = {
        "Cadastro x vendas!A1:C30": mock_cv,
        "Configuração!A1:C80": [["Parâmetro", "Valor", "Ajuda"]],
    }
    init_js = f"""
    window.PM = {{ nivel: 'especial', nome: 'Teste', email: 't@exemplo.com' }};
    const mockData = {json.dumps(mock_data)};
    window.google = {{
      script: {{
        run: {{
          withSuccessHandler: function(onSuccess) {{
            return {{
              withFailureHandler: function() {{
                return {{
                  ler: function(ranges) {{
                    const dados = {{}};
                    (ranges || []).forEach(r => {{ dados[r] = mockData[r] || []; }});
                    setTimeout(() => onSuccess({{ ok: true, dados }}), 10);
                  }},
                  gravar: function() {{ setTimeout(() => onSuccess({{ ok: true }}), 10); }}
                }};
              }}
            }};
          }}
        }}
      }}
    }};
    """
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(channel="msedge", headless=True)
        except Exception:
            browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1100, "height": 850})
        page.add_init_script(init_js)
        page.goto(f"file:///{PAINEL_HTML_PATH.as_posix()}")
        page.locator("#tab-cadvendas").click()
        page.wait_for_timeout(300)
        assert page.locator("#view-cadvendas").is_visible()
        assert "Nas últimas" in page.locator("#cv-resumo").inner_text()
        assert page.locator("#cv-serie-chart svg").count() == 1
        assert "usado (exemplar único)" in page.locator("#cv-tempo-cards").inner_text().lower()
        assert "t+1" in page.locator("#cv-corr-tbl").inner_text()
        browser.close()
