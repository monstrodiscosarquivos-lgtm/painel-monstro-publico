import json
import os
import re
import subprocess
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright

PAINEL_HTML_PATH = Path(__file__).resolve().parent.parent / "apps-script" / "painel-web" / "Painel.html"


def test_painel_html_truncamento_comentarios():
    """Confirma que remover tudo apos // em cada linha de script nao quebra a sintaxe do Painel."""
    assert PAINEL_HTML_PATH.exists(), f"Painel.html nao encontrado em {PAINEL_HTML_PATH}"
    html = PAINEL_HTML_PATH.read_text(encoding="utf-8")

    scripts = re.findall(r"<script\b[^>]*>(.*?)</script>", html, re.DOTALL)
    assert len(scripts) > 0, "Nenhuma tag script encontrada no Painel.html"
    full_js = "\n".join(scripts)

    # Remove tudo apos // em cada linha
    stripped_lines = [re.sub(r"//.*$", "", line) for line in full_js.splitlines()]
    stripped_js = "\n".join(stripped_lines)

    p = subprocess.run(["node", "--check"], input=stripped_js, text=True, capture_output=True, encoding="utf-8")
    assert p.returncode == 0, f"Erro de sintaxe no JavaScript com // removidos:\n{p.stderr}"


def test_painel_conferencia_playwright():
    """Abre Painel.html no navegador via Playwright com mock do google.script.run e testa a conferencia."""
    html_file = PAINEL_HTML_PATH.as_posix()
    file_url = f"file:///{html_file}"

    mock_data = {
        "produtos!L1:L7000": [["id"], ["101"], ["102"], ["103"], ["104"]],
        "produtos!A1:A7000": [["url"], ["secos-molhados"], ["belchior-alucinacao"], ["elis-regina"], ["livro-rock"]],
        "produtos!B1:H7000": [
            ["nome", "categorias", "preco", "custo", "estoque", "tags", "exibir"],
            ["LP Secos & Molhados - Secos & Molhados", "LP, Usado", "150,00", "", "1", "", "true"],
            ["LP Belchior - Alucinacao (Novo/Lacrado)", "LP, Novos e Lacrados", "220,00", "", "2", "", "true"],
            ["LP Elis Regina - Elis", "LP, Usado", "90,00", "", "1", "", "true"],
            ["Livro Rock Gaucho", "Livros", "80,00", "", "3", "", "true"],
        ],
        "produtos!M1:M7000": [["criado_em"], ["2026-11-01 10:00:00"], ["2026-11-02 12:00:00"], ["2026-10-15 09:00:00"], ["2026-11-03 14:00:00"]],
        "produtos!O1:O7000": [["imagem"], ["https://img.nuvemshop.com/101.jpg"], ["https://img.nuvemshop.com/102.jpg"], [""], [""]],
        "cadastro_rascunhos!A1:AO500": [
            ["id", "titulo", "preco", "status", "produto_id", "conferido_em", "conferido_por", "marcado_vinil", "atualizado_em"],
            ["2026-11-01-01", "LP Secos & Molhados - Secos & Molhados", "150", "publicado", "101", "2026-11-05 18:30", "tulio", "", "2026-11-05 18:30"],
            ["2026-11-02-01", "LP Belchior - Alucinacao (Novo/Lacrado)", "220", "publicado", "102", "", "", "", "2026-11-02 12:00"],
        ],
        "cadastro_fotos!A1:F3000": [["id_foto", "ordem", "papel", "arquivo_drive_id", "tamanho_bytes", "hash"]],
    }

    init_js = f"""
    window._writes = [];
    window.PM = {{ nivel: 'especial', nome: 'Tulio', email: 'tulio@monstro.com' }};
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

        context = browser.new_context()
        page = context.new_page()
        page.add_init_script(init_js)
        page.goto(file_url)

        # 1. Navegar ate a aba Cadastro
        page.click("#tab-cad")
        page.wait_for_selector("#view-cad", state="visible")

        # 2. Clicar no botao de filtro Conferencia
        btn_conf = page.locator('button[data-v="conferencia"]')
        btn_conf.wait_for(state="visible")
        btn_conf.click()

        # 3. Verificar que a tabela de conferencia abriu
        table_conf = page.locator("table.cd-conf-tbl")
        table_conf.wait_for(state="visible")
        assert table_conf.is_visible()

        # 4. Verificar itens exibidos no filtro padrao (pendentes, sem livros, com estoque)
        # 101 ja conferido; 102 pendente; 103 pendente sem rascunho; 104 livro (excluido) -> total 2
        rows = page.locator("#cd-conf-tbody tr")
        page.wait_for_timeout(300)
        assert rows.count() == 2

        # 5. Testar busca instantanea sem botao
        page.fill("#cd-conf-busca", "belchior")
        page.wait_for_timeout(200)
        assert rows.count() == 1
        assert "Belchior" in rows.first.inner_text()

        # Limpar busca
        page.fill("#cd-conf-busca", "")
        page.wait_for_timeout(200)
        assert rows.count() == 2

        # 6. Testar troca de filtro de conferencia para todos
        page.select_option("#cd-conf-f-conf", "todos")
        page.wait_for_timeout(200)
        # Agora aparecem 101 (conferido), 102 e 103 -> total 3 (livro 104 segue fora)
        assert rows.count() == 3

        # 7. Testar marcar item individual como conferido via checkbox
        chk_belchior = page.locator('input.cd-conf-toggle-item[data-chave="102"]')
        assert chk_belchior.count() == 1
        assert not chk_belchior.is_checked()

        chk_belchior.click()
        page.wait_for_timeout(300)
        assert chk_belchior.is_checked()

        # Conferir que gravou na planilha com timestamp e usuario
        writes = page.evaluate("window._writes")
        assert len(writes) >= 2
        assert any("2026" in str(w["values"]) for w in writes)
        assert any(w["range"] == "cadastro_rascunhos!G3" and len(w["values"][0][0]) > 0 for w in writes)

        # 8. Testar desmarcar item individual
        chk_belchior.click()
        page.wait_for_timeout(300)
        assert not chk_belchior.is_checked()
        writes_after = page.evaluate("window._writes")
        assert len(writes_after) > len(writes)

        # 9. Testar selecao em massa
        chk_sel_all = page.locator("#cd-conf-sel-todos")
        chk_sel_all.click()
        page.wait_for_timeout(200)
        # Botao de acao em massa deve aparecer
        btn_marcar_massa = page.locator("#cd-conf-bulk-marcar")
        assert btn_marcar_massa.is_visible()
        btn_marcar_massa.click()
        page.wait_for_timeout(400)

        # 10. Testar impressao da lista sem popup
        btn_print = page.locator("#cd-conf-btn-imprimir")
        assert btn_print.is_visible()
        btn_print.click()
        page.wait_for_timeout(200)
        print_area = page.locator("#cd-print-area")
        assert print_area.inner_text() != ""
        assert "Monstro Discos" in print_area.inner_text()

        browser.close()
