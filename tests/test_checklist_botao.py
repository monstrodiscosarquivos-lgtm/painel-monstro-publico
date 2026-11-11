import json
from pathlib import Path
from playwright.sync_api import sync_playwright
P = Path(__file__).resolve().parent.parent / "apps-script" / "painel-web" / "Painel.html"

def test_botao_checklist_abre_e_imprime():
    mock = {
        "cadastro_rascunhos!A1:AZ3000": [
            ["id", "titulo", "preco", "status", "produto_id", "conferido_em", "conferido_por", "marcado_vinil", "atualizado_em"],
            ["2026-11-10-a-01", "LP Belchior - Alucinacao (1976) - (Vinil Usado)", "150", "criado", "101", "", "", "", "2026-11-10 10:00"],
        ],
        "cadastro_fotos!A1:F3000": [["id_disco", "ordem", "papel", "arquivo_drive_id", "cantos", "observacao"]],
    }
    init = """
    window._print = 0; window.print = function(){ window._print++; };
    window.PM = { nivel: 'especial', nome: 'Tulio', email: 'tulio@exemplo.com' };
    const mockData = %s;
    window.google = { script: { run: { withSuccessHandler: function(ok){ return { withFailureHandler: function(){ return {
      ler: function(ranges){ const d = {}; (ranges||[]).forEach(r => d[r] = mockData[r] || []); setTimeout(() => ok({ok:true, dados:d}), 10); },
      gravar: function(){ setTimeout(() => ok({ok:true}), 10); } }; } }; } } } };
    """ % json.dumps(mock)
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(); pg.add_init_script(init)
        pg.goto(P.as_uri()); pg.click("#tab-cad"); pg.wait_for_selector("#view-cad", state="visible"); pg.wait_for_timeout(500)
        pg.click("#cd-btn-abrir-checklist")
        assert pg.locator("#cd-modal-checklist").is_visible()
        pg.click("#cd-modal-chk-cancelar")
        assert not pg.locator("#cd-modal-checklist").is_visible()
        pg.click("#cd-btn-abrir-checklist"); pg.click("#cd-modal-chk-gerar"); pg.wait_for_timeout(300)
        assert pg.evaluate("window._print") == 1
        assert "Belchior" in pg.locator("#cd-print-area").inner_text()
        b.close()
