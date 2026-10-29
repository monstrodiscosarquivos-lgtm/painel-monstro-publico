"""Testes da rotina automática e do arquivo do GitHub Actions. Nenhuma chamada real; dados fictícios."""
import json
import os
import re

import gspread
import pytest

from painel_monstro import rotina
from painel_monstro.config import Config
from painel_monstro.coletor import nuvemshop_api as na
from painel_monstro.saidas import planilha_google as pg
from tests.test_nuvemshop_api import APIDeMentira, cliente as cliente_api, pedido as pedido_api, produto as produto_api
from tests.test_planilha_google import PlanilhaFalsa

TOKEN = 'token-secreto-da-rotina-123'
CHAVE_GOOGLE = {'type': 'service_account', 'client_email': 'robo@projeto.iam.gserviceaccount.com', 'private_key': 'CHAVE-PRIVADA-SECRETA'}
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW = os.path.join(RAIZ, '.github', 'workflows', 'rotina.yml')


@pytest.fixture
def config():
    return Config(nuvemshop_store_id='555', nuvemshop_token=TOKEN, nuvemshop_user_agent='Painel Teste (teste@exemplo.com)',
                  planilha_id='ID-DA-PLANILHA-123', google_service_account_json=json.dumps(CHAVE_GOOGLE))


@pytest.fixture
def mundo(config, tmp_path):
    """API de mentira com dados, planilha de mentira e a pasta de dados da rotina."""
    api_falsa = APIDeMentira()
    api_falsa.dados['orders'] = [pedido_api(i, email=f'cliente{i}@exemplo.com') for i in range(1, 4)]
    api_falsa.dados['customers'] = [cliente_api(i, f'cliente{i}@exemplo.com') for i in range(1, 4)]
    api_falsa.dados['products'] = [produto_api(i) for i in range(1, 4)]
    planilha_falsa = PlanilhaFalsa()
    return {
        'falsa': api_falsa, 'planilha_falsa': planilha_falsa,
        'api': na.NuvemshopAPI(config, sessao=api_falsa, dormir=lambda s: None),
        'planilha': pg.PlanilhaGoogle(planilha_falsa), 'pasta': str(tmp_path / 'api'),
    }


def rodar(config, mundo, **kw):
    kw.setdefault('carrinhos', False)  # a fila de carrinhos tem testes próprios
    return rotina.rodar(config, pasta_api=mundo['pasta'], api=mundo['api'], planilha=mundo['planilha'], **kw)


# ----------------------------------------------------------------------------
# Os 3 passos
# ----------------------------------------------------------------------------
def test_rotina_faz_coletor_motor_e_planilha(config, mundo, capsys):
    r = rodar(config, mundo)
    assert {k: v['total'] for k, v in r['coleta'].items()} == {'pedidos': 3, 'clientes': 3, 'produtos': 3}
    assert set(mundo['planilha_falsa'].abas) == {'custos_automaticos', 'clientes', 'pedidos', 'itens', 'produtos', 'indicadores', 'custos', 'alertas', 'Régua', 'rodada', 'resumo_email', 'meta_sumiu_180', 'meta_nao_abre', 'meta_compradores_180', 'meta_resumo', 'atual', 'mensal', 'coortes',
                                                       'regua_hoje', 'regua_resultados', 'carrinhos_dia', 'vale_a_pena',
                                                       'Configuração', 'anuncios_notas', 'anuncios_direcao', 'anuncios_resumo', 'k7_resumo'}
    g = {x.aba: x.linhas for x in r['gravacoes']}
    assert (g['clientes'], g['pedidos'], g['itens'], g['produtos']) == (3, 3, 6, 3)
    assert [e['etapa'] for e in r['etapas']][0] == 'Etapa 0 · Pós-compra'
    saida = capsys.readouterr().out
    assert saida.index('[1/5]') < saida.index('[2/5]') < saida.index('[3/5]') < saida.index('[5/5]')


def test_segunda_rotina_baixa_so_o_que_mudou_e_nao_duplica(config, mundo):
    rodar(config, mundo)
    antes = {t: a.get_all_values() for t, a in mundo['planilha_falsa'].abas.items() if t not in ('indicadores', 'custos_automaticos', 'rodada')}
    r = rodar(config, mundo)
    assert all(v['modo'] == 'incremental' and v['novos'] == 0 for v in r['coleta'].values())
    depois = {t: a.get_all_values() for t, a in mundo['planilha_falsa'].abas.items() if t not in ('indicadores', 'custos_automaticos', 'rodada')}
    assert depois == antes
    automaticos = mundo['planilha_falsa'].abas['custos_automaticos'].get_all_values()[1:]
    assert len({tuple(l[:3]) for l in automaticos}) == len(automaticos)


def test_pedido_novo_aparece_na_proxima_rotina(config, mundo):
    rodar(config, mundo)
    mundo['falsa'].dados['orders'].append(pedido_api(9, atualizado='2999-01-01T00:00:00+0000', email='novo@exemplo.com'))
    mundo['falsa'].dados['customers'].append(cliente_api(9, 'novo@exemplo.com'))
    r = rodar(config, mundo)
    assert r['coleta']['pedidos']['novos'] == 1 and r['coleta']['pedidos']['modo'] == 'incremental'
    assert len(mundo['planilha_falsa'].abas['pedidos'].get_all_values()) == 5


def test_rotina_completa_baixa_tudo_de_novo(config, mundo):
    rodar(config, mundo)
    r = rodar(config, mundo, completo=True)
    assert all(v['modo'] == 'completo' for v in r['coleta'].values())


def test_aba_custos_preenchida_alimenta_os_indicadores(config, mundo):
    rodar(config, mundo)
    mundo['planilha_falsa'].abas['custos'].update([['2026-10', 1000, 10, 3000]], 'A2')
    rodar(config, mundo)
    ind = mundo['planilha_falsa'].abas['indicadores'].tabela().set_index('indicador')
    assert ind.loc['CPA do Meta', 'estado'] == 'ok' and float(ind.loc['CPA do Meta', 'valor']) == 100


def test_se_o_coletor_falha_nada_e_gravado_na_planilha(config, mundo):
    mundo['falsa'].respostas_forcadas = [401]
    with pytest.raises(na.ErroAPI):
        rodar(config, mundo)
    assert mundo['planilha_falsa'].abas == {}


# ----------------------------------------------------------------------------
# Privacidade
# ----------------------------------------------------------------------------
def test_log_nao_mostra_cliente_token_nem_chave(config, mundo, capsys):
    rodar(config, mundo)
    saida = capsys.readouterr().out
    for proibido in (TOKEN, 'CHAVE-PRIVADA-SECRETA', 'ID-DA-PLANILHA-123', '@exemplo.com', 'maria da silva', 'Maria', '62999990000'):
        assert proibido not in saida


def test_resumo_do_github_so_tem_contagens(config, mundo, tmp_path, monkeypatch):
    destino = tmp_path / 'resumo.md'
    monkeypatch.setenv('GITHUB_STEP_SUMMARY', str(destino))
    rodar(config, mundo)
    texto = destino.read_text(encoding='utf-8')
    assert '| clientes | 3 |' in texto and '| pedidos | completo |' in texto
    for proibido in (TOKEN, 'CHAVE-PRIVADA-SECRETA', '@exemplo.com'):
        assert proibido not in texto


def test_sem_github_nao_tenta_escrever_resumo(config, mundo, monkeypatch):
    monkeypatch.delenv('GITHUB_STEP_SUMMARY', raising=False)
    rodar(config, mundo)  # não deve dar erro


# ----------------------------------------------------------------------------
# Segredos
# ----------------------------------------------------------------------------
def test_segredos_faltando_lista_so_os_nomes():
    with pytest.raises(rotina.ErroRotina) as erro:
        rotina.conferir_configuracao(Config(nuvemshop_token=TOKEN))
    texto = str(erro.value)
    assert 'NUVEMSHOP_STORE_ID' in texto and 'PLANILHA_ID' in texto and 'GOOGLE_SERVICE_ACCOUNT_JSON' in texto
    assert TOKEN not in texto and 'NUVEMSHOP_TOKEN' not in texto


def test_main_devolve_erro_sem_segredos(monkeypatch, capsys):
    monkeypatch.setattr(rotina, 'carregar', lambda: Config())
    monkeypatch.setattr('sys.argv', ['rotina'])
    assert rotina.main() == 1
    assert 'ERRO' in capsys.readouterr().out


def test_chave_do_google_vinda_de_secret_sem_arquivo(config, monkeypatch):
    recebido = {}

    class Cliente:
        def open_by_key(self, chave):
            recebido['planilha'] = chave
            return PlanilhaFalsa()

    monkeypatch.setattr(gspread, 'service_account_from_dict', lambda d, **kw: recebido.setdefault('chave', d) and Cliente())
    pg.PlanilhaGoogle.conectar(config)
    assert recebido['chave']['client_email'] == CHAVE_GOOGLE['client_email'] and recebido['planilha'] == 'ID-DA-PLANILHA-123'


def test_secret_do_google_com_json_invalido_nao_vaza_o_conteudo():
    cfg = Config(planilha_id='X', google_service_account_json='{isto nao e json PEDACO-SECRETO')
    with pytest.raises(pg.ErroPlanilha) as erro:
        pg.PlanilhaGoogle.conectar(cfg)
    assert 'PEDACO-SECRETO' not in str(erro.value)


def test_config_nao_mostra_a_chave_do_google_no_repr(config):
    assert 'CHAVE-PRIVADA-SECRETA' not in repr(config) and TOKEN not in repr(config)


# ----------------------------------------------------------------------------
# O arquivo .github/workflows/rotina.yml
# ----------------------------------------------------------------------------
@pytest.fixture(scope='module')
def fluxo():
    yaml = pytest.importorskip('yaml')
    with open(WORKFLOW, encoding='utf-8') as arq:
        texto = arq.read()
    return yaml.safe_load(texto), texto


def test_workflow_roda_de_hora_em_hora_e_tambem_a_mao(fluxo):
    dados, _ = fluxo
    gatilhos = dados.get('on', dados.get(True))  # o YAML antigo lê "on" como True
    cron = gatilhos['schedule'][0]['cron'].split()
    assert len(cron) == 5 and cron[1:] == ['*', '*', '*', '*'] and cron[0].isdigit()   # um minuto fixo, toda hora
    assert 'workflow_dispatch' in gatilhos and 'completo' in gatilhos['workflow_dispatch']['inputs']


def test_workflow_tem_permissao_minima_e_nao_roda_duas_ao_mesmo_tempo(fluxo):
    dados, _ = fluxo
    assert dados['permissions'] == {'contents': 'read'}
    assert dados['concurrency']['group'] and dados['concurrency']['cancel-in-progress'] is False
    assert dados['jobs']['rotina']['timeout-minutes'] <= 30


def test_workflow_usa_python_312_e_roda_a_rotina(fluxo):
    dados, texto = fluxo
    passos = dados['jobs']['rotina']['steps']
    assert any(p.get('with', {}).get('python-version') == '3.12' for p in passos)
    assert any('python -m painel_monstro.rotina' in p.get('run', '') for p in passos)
    assert 'dados/api' in texto


def test_workflow_so_usa_segredos_conhecidos_e_a_rotina_exige_os_mesmos(fluxo):
    _, texto = fluxo
    usados = set(re.findall(r'secrets\.([A-Z_]+)', texto))
    esperados = {'NUVEMSHOP_STORE_ID', 'NUVEMSHOP_TOKEN', 'NUVEMSHOP_USER_AGENT', 'PLANILHA_ID', 'GOOGLE_SERVICE_ACCOUNT_JSON'}
    assert usados == esperados | {'BREVO_API_KEY', 'META_ADS_TOKEN', 'META_ADS_ACCOUNT_ID', 'DISCOGS_TOKEN', 'CACHE_KEY'}  # fontes opcionais e cache cifrado
    assert set(rotina.SEGREDOS_OBRIGATORIOS) | {'GOOGLE_SERVICE_ACCOUNT_JSON'} == esperados


def test_workflow_mantem_o_brevo_em_modo_teste_por_padrao(fluxo):
    _, texto = fluxo
    assert "BREVO_MODO_TESTE: ${{ vars.BREVO_MODO_TESTE || 'sim' }}" in texto
    assert not re.search(r"BREVO_MODO_TESTE:\s*'?(nao|não|no|false|0)'?\s*$", texto, re.M | re.I)


def test_workflow_nao_imprime_segredos_nem_grava_chave_em_arquivo(fluxo):
    dados, texto = fluxo
    for passo in dados['jobs']['rotina']['steps']:
        comando = passo.get('run', '')
        assert not re.search(r'\b(echo|printenv|set -x|cat|env\b)', comando), comando
    assert 'credenciais' not in texto and '.json >' not in texto


def test_workflow_so_chama_a_nuvemshop_pelo_codigo_de_leitura():
    # A rotina inteira não pode ter chamadas que alterem a loja.
    import inspect
    codigo = inspect.getsource(na) + inspect.getsource(rotina)
    assert not re.search(r'\.(post|put|patch|delete)\(', codigo)


def test_anuncios_falha_de_gravacao_nao_derruba_rotina(config,mundo,monkeypatch):
    import pandas as pd
    monkeypatch.setattr(rotina,'passo_anuncios',lambda *a,**kw:[('anuncios_campanha_dia',pd.DataFrame([{'data':'2026-10-01'}]))])
    gravar=mundo['planilha'].substituir
    def substituir(nome,df):
        if nome.startswith('anuncios_'): raise RuntimeError('falha simulada')
        return gravar(nome,df)
    monkeypatch.setattr(mundo['planilha'],'substituir',substituir)
    r=rodar(config,mundo)
    assert r['indicadores_total']==22
    assert 'rodada' in mundo['planilha_falsa'].abas


def test_workflow_oferece_historico_meta_separado_da_nuvemshop(fluxo):
    _,texto=fluxo
    assert 'anuncios_historico:' in texto and '--anuncios-historico' in texto
    assert '$ANUNCIOS_HISTORICO' in texto
