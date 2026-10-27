"""Testes da raspadinha online (D-062). Dados fictícios; planilha e Nuvemshop de mentira."""
from datetime import date

import pandas as pd
import pytest

from painel_monstro.config import Config
from painel_monstro.motor import raspadinha as r
from painel_monstro.motor.regua import EMAIL_DA_LOJA
from painel_monstro.saidas import planilha_google as pg
from painel_monstro.saidas import raspadinha as sr
from tests.ajuda import cliente, pedido, tabelas
from tests.test_planilha_google import PlanilhaFalsa
from tests.test_nuvemshop_api import Resposta

HOJE = date(2026, 10, 14)


def publico(n):
    return pd.DataFrame({'email': [f'p{i:03d}@exemplo.com' for i in range(n)], 'primeiro_nome': ['Ana'] * n})


def params(**kw):
    base = dict(campanha='Teste outubro', url_pagina='https://exemplo.github.io/raspadinha/')
    base.update(kw)
    return r.ParametrosRaspadinha(**base)


# ----------------------------------------------------------------- cupom e link
def test_codigo_so_letras_e_numeros_com_prefixo():
    import random
    c = r.gerar_codigo(random.Random(1), 'Raspa-Out!', 6)
    assert c.startswith('RASPAOUT') and c.isalnum() and len(c) == 14
    assert not set(c[8:]) & set('01ILO')


def test_link_ida_e_volta_esconde_o_premio():
    p = r.Premio('30%', 'percentage', 30, 1)
    link = r.montar_link('https://x.github.io/raspadinha/', 'RASPAABC234', p, date(2026, 10, 29), 'Túlio')
    token = link.split('?t=')[1]
    assert '30' not in token and 'RASPA' not in token
    from urllib.parse import unquote
    d = r.decodificar_link(unquote(token))
    assert d == {'c': 'RASPAABC234', 'g': '30%', 'p': 'DE DESCONTO', 't': '30% de desconto', 'v': '29/10', 'd': '2026-10-29', 'n': 'Túlio'}


def test_frete_gratis_no_selo():
    assert r.detalhe_do_premio(r.Premio('FRETE GRÁTIS', 'shipping', 0, 1)) == ('FRETE', 'GRÁTIS')


# ----------------------------------------------------------------- sorteio
def test_sorteio_reproduzivel_e_com_controle_de_10_por_cento():
    a = r.sortear(publico(100), params(), HOJE)
    b = r.sortear(publico(100), params(), HOJE)
    pd.testing.assert_frame_equal(a, b)
    assert (a['grupo'] == 'controle').sum() == 10
    assert (a['grupo'] == 'envio').sum() == 90
    envio = a[a['grupo'] == 'envio']
    assert envio['cupom'].is_unique and envio['cupom'].str.isalnum().all()
    assert set(envio['valido_ate']) == {'2026-10-29'}


def test_quantidades_viram_um_saco_de_cartelas_e_acabam():
    p = params(premios=(r.Premio('50%', 'percentage', 50, 2), r.Premio('10%', 'percentage', 10, 3)), controle=0)
    s = r.sortear(publico(8), p, HOJE)
    assert s.loc[s['grupo'] == 'envio', 'premio'].value_counts().to_dict() == {'10%': 3, '50%': 2}
    assert (s['motivo'] == 'acabaram as cartelas').sum() == 3


def test_publico_pequeno_nao_tem_controle():
    s = r.sortear(publico(9), params(), HOJE)
    assert (s['grupo'] == 'controle').sum() == 0


def test_fora_quem_nao_aceita_a_loja_e_beneficio_recente():
    pub = publico(3)
    pub.loc[3] = [EMAIL_DA_LOJA, 'Loja']
    benef = pd.Series({'p001@exemplo.com': pd.Timestamp('2026-09-01'), 'p002@exemplo.com': pd.Timestamp('2026-05-01')})
    s = r.sortear(pub, params(controle=0), HOJE, benef, nao_aceitam={'p000@exemplo.com'}).set_index('email')
    assert s.loc['p000@exemplo.com', 'motivo'] == 'não aceita marketing'
    assert s.loc['p001@exemplo.com', 'motivo'].startswith('benefício nos últimos 90')
    assert s.loc['p002@exemplo.com', 'grupo'] == 'envio'  # benefício há mais de 90 dias
    assert s.loc[EMAIL_DA_LOJA, 'grupo'] == 'fora'


def test_trava_zero_desliga_o_limite():
    benef = pd.Series({'p000@exemplo.com': pd.Timestamp('2026-10-13')})
    s = r.sortear(publico(1), params(controle=0, dias_entre_beneficios=0), HOJE, benef)
    assert s['grupo'].tolist() == ['envio']


def test_campanha_sem_nome_nao_sorteia():
    with pytest.raises(ValueError):
        r.sortear(publico(3), params(campanha=' '), HOJE)


def test_ultimos_beneficios_junta_as_tres_fontes():
    ped = pd.DataFrame([{**pedido(1, 'a@exemplo.com', '2026-09-20'), 'cupom': 'VOLTA10SET'},
                        {**pedido(2, 'b@exemplo.com', '2026-09-21'), 'cupom': None}])
    regua_h = pd.DataFrame([{'email': 'b@exemplo.com', 'etapa': 'Etapa 2 · Convite', 'grupo': 'envio', 'data_referencia': '2026-10-01'},
                            {'email': 'c@exemplo.com', 'etapa': 'Etapa 1 · Lembrete', 'grupo': 'envio', 'data_referencia': '2026-10-01'}])
    ant = pd.DataFrame([{'email': 'd@exemplo.com', 'grupo': 'envio', 'criado_em': '2026-08-01'},
                        {'email': 'e@exemplo.com', 'grupo': 'controle', 'criado_em': '2026-08-01'}])
    u = r.ultimos_beneficios(ped, regua_h, ant)
    assert set(u.index) == {'a@exemplo.com', 'b@exemplo.com', 'd@exemplo.com'}


# ----------------------------------------------------------------- cupom na Nuvemshop, uso e resultado
def test_payload_do_cupom_de_uso_unico():
    linha = pd.Series({'cupom': 'RASPAABC234', 'tipo': 'percentage', 'valor': 15, 'valido_ate': '2026-10-29'})
    c = r.payload_cupom(linha, params(pedido_minimo=100), HOJE)
    assert c == {'code': 'RASPAABC234', 'type': 'percentage', 'max_uses': 1, 'valid': True, 'start_date': '2026-10-14',
                 'end_date': '2026-10-29', 'combines_with_other_discounts': False, 'includes_shipping': False,
                 'value': '15.00', 'min_price': 100.0}
    frete = r.payload_cupom(pd.Series({'cupom': 'X', 'tipo': 'shipping', 'valor': 0, 'valido_ate': '2026-10-29'}), params(), HOJE)
    assert 'value' not in frete and 'min_price' not in frete


def _envios_com_compras():
    env = r.sortear(publico(40), params(), HOJE)
    um = env[env['grupo'] == 'envio'].iloc[0]
    ctl = env[env['grupo'] == 'controle'].iloc[0]
    ped = pd.DataFrame([{**pedido(10, um['email'], '2026-10-16', total=120, subtotal=150, desconto=30), 'cupom': um['cupom']},
                        {**pedido(11, ctl['email'], '2026-10-18', total=80), 'cupom': None},
                        {**pedido(12, um['email'], '2026-12-30', total=80), 'cupom': None}])
    return env, ped, um


def test_marcar_uso_do_cupom():
    env, ped, um = _envios_com_compras()
    m = r.marcar_uso(env, ped).set_index('email')
    assert m.loc[um['email'], 'pedido'] == '10' and m.loc[um['email'], 'receita'] == 120.0
    assert m.loc[um['email'], 'usado_em'] == '2026-10-16'


def test_resultado_por_grupo_com_amostra_minima():
    env, ped, _ = _envios_com_compras()
    res = r.resultado(r.marcar_uso(env, ped), ped, date(2026, 11, 20)).set_index('grupo')
    assert res.loc['envio', 'compraram'] == 1 and res.loc['envio', 'cupons_usados'] == 1
    assert res.loc['envio', 'desconto_dos_cupons'] == 30.0
    assert res.loc['controle', 'compraram'] == 1
    assert res.loc['envio', 'diferenca_vs_controle'] == 'dados insuficientes'  # controle com 4 pessoas
    assert res.loc['envio', 'janela_fechada'] == 'sim'


# ----------------------------------------------------------------- planilha
@pytest.fixture
def planilha():
    return pg.PlanilhaGoogle(PlanilhaFalsa())


def _tabelas():
    cli = [cliente('p000@exemplo.com', nome='Bia'), cliente('p001@exemplo.com', aceita=False)]
    ped = [{**pedido(1, 'p000@exemplo.com', '2026-01-10'), 'cupom': None}]
    return tabelas(ped, clientes=cli)


def test_cria_abas_com_padrao_e_le_os_parametros(planilha):
    assert sr.garantir_abas(planilha) == [sr.ABA_CONFIG, sr.ABA_LISTA]
    assert sr.garantir_abas(planilha) == []  # não recria
    p = sr.ler_parametros(planilha._ss.worksheet(sr.ABA_CONFIG).get_all_values())
    assert p.modo == 'Teste' and p.controle == pytest.approx(0.10) and p.dias_entre_beneficios == 90
    assert [x.nome for x in p.premios] == ['10%', '15%', '20%', 'FRETE GRÁTIS']
    assert p.premios[3].tipo == 'shipping'


def test_modo_ilegivel_vira_teste_e_porcentagem_aceita_virgula():
    valores = [sr.CAB_PREMIOS, ['30%', 'Porcentagem', '30', '5'], [], sr.CAB_PARAMETROS,
               ['Campanha', 'Black'], ['Modo', 'talvez'], ['Grupo de controle (%)', '12,5'], ['Endereço da página', 'https://a.github.io/r']]
    p = sr.ler_parametros(valores)
    assert p.modo == 'Teste' and p.controle == pytest.approx(0.125) and p.url_pagina == 'https://a.github.io/r/'


def test_sem_premio_da_erro():
    with pytest.raises(sr.ErroRaspadinha):
        sr.ler_parametros([sr.CAB_PREMIOS, ['10%', 'Porcentagem', 10, 0]])


def _preparar_campanha(planilha, n=30, campanha='Teste outubro'):
    sr.garantir_abas(planilha)
    cfg = planilha._ss.worksheet(sr.ABA_CONFIG)
    linha = next(i for i, l in enumerate(cfg.get_all_values(), start=1) if l and l[0] == 'Campanha')
    cfg.update([[campanha]], f'B{linha}', raw=True)
    lista = planilha._ss.worksheet(sr.ABA_LISTA)
    lista.resize(rows=n + 5)
    lista.update([[f'p{i:03d}@exemplo.com'] for i in range(n)], 'A2', raw=True)
    return sr.preparar(planilha, _tabelas(), HOJE)


def test_preparar_sorteia_uma_vez_so(planilha):
    feito = _preparar_campanha(planilha)
    assert feito['novo']
    env = feito['envios'].set_index('email')
    assert env.loc['p001@exemplo.com', 'motivo'] == 'não aceita marketing'
    assert env.loc['p000@exemplo.com', 'primeiro_nome'] == 'Bia'
    de_novo = sr.preparar(planilha, _tabelas(), HOJE)
    assert not de_novo['novo']
    gravado = sr.ler_tabela(planilha, sr.ABA_ENVIOS, r.ENVIOS_COLUNAS)
    assert len(gravado) == 30


def test_criar_cupons_exige_modo_real(planilha):
    _preparar_campanha(planilha)
    with pytest.raises(sr.ErroRaspadinha, match='Modo = Teste'):
        sr.criar_cupons(planilha, object(), HOJE)


class CuponsFalsos:
    def __init__(self):
        self.criados = []

    def criar(self, corpo):
        self.criados.append(corpo['code'])
        return 'sim'


def test_criar_cupons_em_modo_real_marca_e_nao_repete(planilha, tmp_path):
    _preparar_campanha(planilha)
    cfg = planilha._ss.worksheet(sr.ABA_CONFIG)
    linha = next(i for i, l in enumerate(cfg.get_all_values(), start=1) if l and l[0] == 'Modo')
    cfg.update([['Real']], f'B{linha}', raw=True)
    falsos = CuponsFalsos()
    feito = sr.criar_cupons(planilha, falsos, HOJE)
    n = (feito['envios']['grupo'] == 'envio').sum()
    assert len(falsos.criados) == n and feito['contagem'] == {'sim': n}
    assert sr.criar_cupons(planilha, falsos, HOJE)['contagem'] == {}  # segunda vez não cria de novo
    with pytest.raises(sr.ErroRaspadinha, match='já tem cupons'):
        sr.preparar(planilha, _tabelas(), HOJE, forcar=True)
    caminho, total = sr.gerar_csv(feito['envios'], 'Teste outubro', True, pasta=str(tmp_path))
    csv = pd.read_csv(caminho)
    assert total == n and list(csv.columns) == ['EMAIL', 'FIRSTNAME', 'RASPA_LINK', 'RASPA_ATE']


def test_passo_rotina_sem_campanha_nao_grava(planilha):
    assert sr.passo_rotina(planilha, _tabelas(), HOJE) == []


def test_passo_rotina_com_campanha_devolve_resultado(planilha):
    _preparar_campanha(planilha)
    abas = dict(sr.passo_rotina(planilha, _tabelas(), HOJE))
    assert sr.ABA_RESULTADOS in abas and sr.ABA_ENVIOS not in abas  # ninguém usou cupom: envios não mudam


# ----------------------------------------------------------------- Nuvemshop de mentira
class SessaoCupons:
    def __init__(self, status_post, existentes=()):
        self.status_post, self.existentes, self.posts = status_post, existentes, []

    def post(self, url, headers=None, json=None, timeout=None):
        self.posts.append((url, json, headers))
        return Resposta(self.status_post, {})

    def get(self, url, headers=None, params=None, timeout=None):
        return Resposta(200, [{'code': c} for c in self.existentes])


CFG = Config(nuvemshop_store_id='123', nuvemshop_token='segredo', nuvemshop_user_agent='Painel (a@exemplo.com)')


def test_cria_cupom_com_post_e_token_so_no_cabecalho():
    s = SessaoCupons(201)
    assert sr.CuponsNuvemshop(CFG, sessao=s, dormir=lambda _: None).criar({'code': 'RASPAX'}) == 'sim'
    url, corpo, cab = s.posts[0]
    assert url.endswith('/123/coupons') and corpo == {'code': 'RASPAX'} and cab['Authorization'] == 'Bearer segredo'


def test_cupom_que_ja_existe_nao_vira_erro():
    s = SessaoCupons(422, existentes=('RASPAX',))
    assert sr.CuponsNuvemshop(CFG, sessao=s, dormir=lambda _: None).criar({'code': 'RASPAX'}) == 'já existia'


def test_sem_permissao_para_criar_para_tudo():
    with pytest.raises(sr.ErroRaspadinha, match='permissão'):
        sr.CuponsNuvemshop(CFG, sessao=SessaoCupons(403), dormir=lambda _: None).criar({'code': 'RASPAX'})


def test_pagina_publica_usa_a_mesma_chave_do_link():
    import os
    from painel_monstro.config import RAIZ_PROJETO
    html = open(os.path.join(RAIZ_PROJETO, 'raspadinha_pagina', 'index.html'), encoding='utf-8').read()
    assert f"var CHAVE = '{r.CHAVE_LINK.decode()}'" in html
    import re
    script = html.split('<script>')[1].split('</script>')[0]
    # Nenhum email de cliente escrito na página (as regras de validação de email não contam).
    assert 'lojamonstro.com.br' in html and not re.search(r'[\w.+-]+@[\w-]+\.[a-z]{2,}', script)


def test_pagina_da_campanha_sorteia_no_servidor_e_guarda_o_resultado():
    # D-070: a página nunca sorteia; pede ao Apps Script (SORTEIO) e guarda o resultado no aparelho.
    import os
    from painel_monstro.config import RAIZ_PROJETO
    html = open(os.path.join(RAIZ_PROJETO, 'raspadinha_pagina', 'index.html'), encoding='utf-8').read()
    script = html.split('<script>')[1].split('</script>')[0]
    assert "var SORTEIO = " in script and "acao:'jogar'" in script and "acao:'config'" in script
    assert "'rasp_res_' + id" in script and 'Math.random() <' not in script.split('function iniciar')[0]
    gs = open(os.path.join(RAIZ_PROJETO, 'apps-script', 'raspadinha', 'Sorteio.gs'), encoding='utf-8').read()
    assert "max_uses: 1" in gs and 'LockService' in gs and "getProperty('NUVEMSHOP_TOKEN')" in gs
    assert 'Logger.log(token' not in gs and 'Bearer ' + "'" not in gs.replace("'Bearer ' + token", '')
    assert "'origens'" in gs and "function canal_(c, cp)" in gs
    import subprocess
    res = subprocess.run(['node', os.path.join(RAIZ_PROJETO, 'apps-script', 'teste_local.js')], capture_output=True, text=True, encoding='utf-8', check=True)
    assert 'raspadinha canal_: reconhece brevo, instagram, wpp, origem personalizada, parecido como outro e vazio como direto' in res.stdout
    assert 'raspadinha: gerador de código de origem e reclassificação no Painel' in res.stdout
