"""D-068: rodada curta só de cadastro, disparada pelo vigia do Apps Script. Nenhuma chamada real."""
import os
import re

import pytest

from painel_monstro import rotina
from painel_monstro.saidas import cadastro
from tests.test_rotina import CHAVE_GOOGLE, RAIZ, config, mundo  # noqa: F401  (fixtures)

WORKFLOW = os.path.join(RAIZ, '.github', 'workflows', 'cadastro.yml')
VIGIA = os.path.join(RAIZ, 'apps-script', 'vigia-cadastro.gs')
FILA = os.path.join(RAIZ, 'apps-script', 'fila-por-email.gs')


def test_rodada_curta_so_roda_o_cadastro_e_nao_grava_a_rodada(config, mundo, monkeypatch):
    chamadas = []

    def passo_falso(cfg, planilha, tabelas, pasta, api=None):
        chamadas.append((tabelas.produtos is not None, pasta))
        return {'criados': 1, 'erros': 0, 'rascunhos': 2}

    monkeypatch.setattr(cadastro, 'passo_rotina', passo_falso)
    r = rotina.rodar_cadastro(config, pasta_api=mundo['pasta'], api=mundo['api'], planilha=mundo['planilha'])
    assert r['criados'] == 1 and 'segundos' in r
    assert chamadas == [(True, mundo['pasta'])]
    assert 'rodada' not in mundo['planilha_falsa'].abas      # alerta de rotina parada mede só a rotina completa
    assert 'indicadores' not in mundo['planilha_falsa'].abas


def test_main_com_so_cadastro_chama_a_rodada_curta(monkeypatch):
    feito = []
    monkeypatch.setattr(rotina, 'rodar_cadastro', lambda: feito.append('cadastro'))
    monkeypatch.setattr(rotina, 'rodar', lambda **kw: feito.append('completa'))
    monkeypatch.setattr('sys.argv', ['rotina', '--so-cadastro'])
    assert rotina.main() == 0 and feito == ['cadastro']


@pytest.fixture(scope='module')
def fluxo():
    yaml = pytest.importorskip('yaml')
    with open(WORKFLOW, encoding='utf-8') as arq:
        texto = arq.read()
    return yaml.safe_load(texto), texto


def test_workflow_de_cadastro_dispara_pelo_vigia_e_a_mao(fluxo):
    dados, _ = fluxo
    gatilhos = dados.get('on', dados.get(True))
    assert gatilhos['repository_dispatch']['types'] == ['cadastro']
    assert 'workflow_dispatch' in gatilhos and 'schedule' not in gatilhos


def test_workflow_de_cadastro_divide_a_fila_e_o_cache_com_a_rotina(fluxo):
    dados, texto = fluxo
    assert dados['permissions'] == {'contents': 'read'}
    assert dados['concurrency'] == {'group': 'rotina-painel', 'cancel-in-progress': False}
    assert 'restore-keys: dados-api-aes256-v1-' in texto and 'cache/save@v4' in texto
    passos = dados['jobs']['cadastro']['steps']
    assert any(p.get('run', '') == 'python -m painel_monstro.rotina --so-cadastro' for p in passos)
    for passo in passos:
        assert not re.search(r'\b(echo|printenv|set -x|cat|env\b)', passo.get('run', ''))


def test_workflow_de_cadastro_usa_os_mesmos_segredos_da_rotina(fluxo):
    _, texto = fluxo
    with open(os.path.join(RAIZ, '.github', 'workflows', 'rotina.yml'), encoding='utf-8') as arq:
        da_rotina = set(re.findall(r'secrets\.([A-Z_]+)', arq.read()))
    assert set(re.findall(r'secrets\.([A-Z_]+)', texto)) == da_rotina
    assert "BREVO_MODO_TESTE: ${{ vars.BREVO_MODO_TESTE || 'sim' }}" in texto


def test_vigia_le_o_token_das_propriedades_e_so_dispara_o_cadastro():
    with open(VIGIA, encoding='utf-8') as arq:
        g = arq.read()
    assert "getProperty('GITHUB_TOKEN')" in g and 'ghp_' not in g and 'github_pat_' not in g.replace("'github_pat_'", '')
    assert "getProperty('GITHUB_REPO')" in g and "'/dispatches'" in g
    assert "event_type: 'cadastro'" in g
    assert 'deleteTrigger' in g and "f === 'vigiarCadastro' || f === 'arquivarFotos'" in g   # remove só os próprios agendamentos


def test_arquivo_de_fotos_so_move_publicados_e_descartados_e_nunca_apaga():
    with open(VIGIA, encoding='utf-8') as arq:
        g = arq.read()
    corpo = g[g.index('function arquivarFotos'):]
    assert "st === 'publicado' || st.indexOf('descartado') === 0" in corpo
    assert 'moveTo(arquivo)' in corpo and 'setTrashed' not in g and '.remove' not in corpo


def test_fila_por_email_nao_apaga_o_agendamento_do_vigia():
    with open(FILA, encoding='utf-8') as arq:
        g = arq.read()
    corpo = g[g.index('function removerAgendamentos_'):]
    corpo = corpo[:corpo.index('\n}\n')]
    assert "'cadaHora'" in corpo
