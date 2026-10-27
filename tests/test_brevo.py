"""Etapa 7: régua no Brevo, sempre em modo teste. Sessão de mentira, dados fictícios, nenhuma chamada real."""
import json

import pandas as pd
import pytest

from painel_monstro.config import Config
from painel_monstro.motor import regua
from painel_monstro.saidas import brevo as bv
from tests.ajuda import REFERENCIA, dias_atras, pedido, tabelas

CHAVE = 'chave-falsa-do-teste-123456789'


class Resposta:
    def __init__(self, status=200, corpo=None, cabecalhos=None):
        self.status_code = status
        self._corpo = corpo
        self.headers = cabecalhos or {}
        self.content = b'' if corpo is None else json.dumps(corpo).encode()
        self.text = '' if corpo is None else json.dumps(corpo)

    def json(self):
        if self._corpo is None:
            raise ValueError('sem corpo')
        return self._corpo


class Sessao:
    """Imita a API do Brevo. `rotas`: (METODO, caminho) -> corpo ou lista de respostas."""

    def __init__(self, rotas=None):
        self.rotas = rotas or {}
        self.chamadas = []

    def request(self, metodo, url, headers=None, params=None, json=None, timeout=None):
        caminho = url.replace(bv.URL_BASE, '')
        self.chamadas.append({'metodo': metodo, 'caminho': caminho, 'params': params, 'json': json, 'headers': headers or {}})
        r = self.rotas.get((metodo, caminho))
        if callable(r):
            r = r(params, json)
        if isinstance(r, list):
            r = r.pop(0) if len(r) > 1 else r[0]
        if isinstance(r, Resposta):
            return r
        return Resposta(200, r if r is not None else {})

    @property
    def escritas(self):
        return [c for c in self.chamadas if c['metodo'] != 'GET']


def rotas_basicas(contatos=None, listas=None, atributos=None):
    return {
        ('GET', '/account'): {'companyName': 'Loja de Teste', 'plan': [{'type': 'subscription'}]},
        ('GET', '/contacts/lists'): {'lists': [{'id': i, 'name': n} for n, i in (listas or {}).items()]},
        ('GET', '/contacts/attributes'): {'attributes': [{'name': a} for a in (atributos or [])]},
        ('GET', '/contacts'): lambda p, j: {'contacts': (contatos or [])[p['offset']:p['offset'] + p['limit']]},
    }


# ----------------------------------------------------------------------------
# Cliente HTTP
# ----------------------------------------------------------------------------
def test_chave_vai_so_no_cabecalho_e_nunca_aparece_no_repr_nem_nos_erros():
    s = Sessao(rotas_basicas())
    b = bv.Brevo(CHAVE, sessao=s)
    assert b.conta()['companyName'] == 'Loja de Teste'
    assert s.chamadas[0]['headers']['api-key'] == CHAVE
    assert CHAVE not in repr(b) and CHAVE not in str(b.__dict__.get('modo_teste'))
    s2 = Sessao({('GET', '/account'): Resposta(400, {'message': f'chave {CHAVE} estranha'})})
    with pytest.raises(bv.ErroBrevo) as erro:
        bv.Brevo(CHAVE, sessao=s2).conta()
    assert CHAVE not in str(erro.value) and CHAVE not in erro.value.detalhe


@pytest.mark.parametrize('mensagem,tipo', [
    ('We have detected you are using an unrecognised IP address 1.2.3.4. Please add it to your authorised IPs', 'bloqueio_ip'),
    ('Key not found', 'chave_invalida'),
    ('API Key is not enabled', 'chave_invalida'),
])
def test_chave_recusada_ou_ip_bloqueado(mensagem, tipo):
    s = Sessao({('GET', '/account'): Resposta(401, {'code': 'unauthorized', 'message': mensagem})})
    with pytest.raises(bv.ErroBrevo) as erro:
        bv.Brevo(CHAVE, sessao=s).conta()
    assert erro.value.tipo == tipo
    assert '1.2.3.4' not in str(erro.value)


def test_limite_de_requisicoes_espera_e_tenta_de_novo():
    esperas = []
    s = Sessao({('GET', '/account'): [Resposta(429, {'message': 'too many'}, {'retry-after': '3'}), Resposta(200, {'companyName': 'ok'})]})
    r = bv.Brevo(CHAVE, sessao=s, dormir=esperas.append).conta()
    assert r['companyName'] == 'ok' and esperas and esperas[0] >= 3


def test_sem_chave_nao_tenta():
    with pytest.raises(bv.ErroBrevo):
        bv.Brevo('')
    assert bv.ler_conta('', True).status == 'sem chave'


def test_em_modo_teste_toda_escrita_e_recusada_antes_de_sair_da_maquina():
    s = Sessao(rotas_basicas())
    b = bv.Brevo(CHAVE, modo_teste=True, sessao=s)
    for chamada in (lambda: b.atualizar_contato('a@exemplo.com', {'ETAPA': 'ETAPA_0'}), lambda: b.adicionar_a_lista(1, ['a@exemplo.com']),
                    lambda: b.remover_da_lista(1, ['a@exemplo.com']), lambda: b.criar_atributo('ETAPA', 'text')):
        with pytest.raises(bv.BrevoModoTeste):
            chamada()
    assert s.escritas == []


def test_contatos_paginados():
    todos = [{'email': f'c{i}@exemplo.com'} for i in range(2500)]
    s = Sessao(rotas_basicas(contatos=todos))
    achados = list(bv.Brevo(CHAVE, sessao=s).contatos())
    assert len(achados) == 2500
    assert [c['params']['offset'] for c in s.chamadas if c['caminho'] == '/contacts'] == [0, 1000, 2000]


# ----------------------------------------------------------------------------
# Alvo
# ----------------------------------------------------------------------------
def clientes_de_teste():
    pedidos, n = [], 0

    def novo(email, *dias):
        nonlocal n
        for d in dias:
            n += 1
            pedidos.append(pedido(n, email, dias_atras(d), total=100.0))
    novo('pos@exemplo.com', 20)                        # etapa 0
    novo('lembrete@exemplo.com', 50)                   # etapa 1
    novo('convite@exemplo.com', 100, 400)              # etapa 2 (2 compras)
    novo('ultima@exemplo.com', 190)                    # etapa 3
    novo('descanso@exemplo.com', 300)
    novo('recente@exemplo.com', 1)                     # sem etapa (e fixa a data de referência em 10/10)
    novo('vip@exemplo.com', 80, 200, 300)              # VIP na janela de 75 a 104
    return tabelas(pedidos)


def alvo_de(t):
    classificacao, _ = regua.rodar(t, '2026-10')
    return bv.alvo_dos_clientes(classificacao, t, regua.PADRAO)


def test_alvo_tem_etapa_dias_familia_vip_e_lista():
    a = alvo_de(clientes_de_teste())
    assert a.loc['pos@exemplo.com', 'ETAPA'] == 'ETAPA_0' and a.loc['pos@exemplo.com', 'DIAS_SEM_COMPRAR'] == 20
    assert a.loc['lembrete@exemplo.com', 'ETAPA'] == 'ETAPA_1' and a.loc['convite@exemplo.com', 'ETAPA'] == 'ETAPA_2'
    assert a.loc['ultima@exemplo.com', 'ETAPA'] == 'ETAPA_3' and a.loc['descanso@exemplo.com', 'ETAPA'] == 'DESCANSO'
    assert a.loc['recente@exemplo.com', 'ETAPA'] == 'SEM_ETAPA'
    assert a.loc['vip@exemplo.com', 'ETAPA'] == 'VIP' and bool(a.loc['vip@exemplo.com', 'VIP']) is True
    assert a.loc['vip@exemplo.com', 'lista'] == '' and a.loc['descanso@exemplo.com', 'lista'] == ''   # VIP e descanso: sem lista de email
    assert a.loc['pos@exemplo.com', 'FAMILIA'] == 'Variado'
    assert set(a.columns) == {'ETAPA', 'DIAS_SEM_COMPRAR', 'FAMILIA', 'VIP', 'CONTROLE', 'lista'}


def test_controle_nunca_entra_em_lista_e_o_sorteio_e_estavel_e_de_uns_10_por_cento():
    pedidos = [pedido(i, f'c{i}@exemplo.com', dias_atras(50)) for i in range(600)] + [pedido(9999, 'hoje@exemplo.com', dias_atras(1))]
    t = tabelas(pedidos)
    a = alvo_de(t)
    a = a[a['ETAPA'] == 'ETAPA_1']
    controle = a[a['CONTROLE']]
    assert len(a) == 600 and 0.06 < len(controle) / len(a) < 0.14
    assert (controle['lista'] == '').all() and (a[~a['CONTROLE']]['lista'] == 'Painel · Etapa 1 Lembrete').all()
    # estável: o mesmo cliente com a mesma última compra cai sempre no mesmo grupo, seja qual for o dia
    assert bv.em_controle('x@exemplo.com', 'ETAPA_1', '2026-08-20', 0.1) == bv.em_controle('X@exemplo.com ', 'ETAPA_1', pd.Timestamp('2026-08-20'), 0.1)
    # comprou de novo: ciclo novo, sorteio novo
    mudou = sum(bv.em_controle(f'c{i}@exemplo.com', 'ETAPA_1', '2026-08-20', 0.1) != bv.em_controle(f'c{i}@exemplo.com', 'ETAPA_1', '2026-09-20', 0.1)
                for i in range(600))
    assert mudou > 0


def test_quem_nao_aceita_marketing_nao_vira_alvo():
    from tests.ajuda import cliente
    pedidos = [pedido(1, 'sim@exemplo.com', dias_atras(50)), pedido(2, 'nao@exemplo.com', dias_atras(50)), pedido(3, 'hoje@exemplo.com', dias_atras(1))]
    t = tabelas(pedidos, clientes=[cliente('sim@exemplo.com'), cliente('nao@exemplo.com', aceita=False), cliente('hoje@exemplo.com')])
    assert sorted(alvo_de(t).index) == ['hoje@exemplo.com', 'sim@exemplo.com']


# ----------------------------------------------------------------------------
# Plano
# ----------------------------------------------------------------------------
LISTAS = {'Painel · Etapa 0 Pós-compra': 101, 'Painel · Etapa 1 Lembrete': 102, 'Painel · Etapa 2 Convite': 103, 'Painel · Etapa 3 Última chamada': 104}
ATRIBUTOS = {'ETAPA', 'DIAS_SEM_COMPRAR', 'FAMILIA', 'VIP', 'CONTROLE', 'CUPOM', 'CUPOM_ATE'}


def contato(email, etapa=None, dias=None, listas=(), bloqueado=False, controle=False):
    attrs = {}
    if etapa:
        attrs = {'ETAPA': etapa, 'DIAS_SEM_COMPRAR': dias, 'FAMILIA': 'Variado', 'VIP': False, 'CONTROLE': controle}
    return {'email': email, 'listIds': list(listas), 'emailBlacklisted': bloqueado, 'attributes': attrs}


def test_plano_diferencas_listas_e_protecoes():
    a = alvo_de(clientes_de_teste())
    contatos = {
        'pos@exemplo.com': contato('pos@exemplo.com'),                                   # contato sem atributos: atualiza e entra na lista
        'lembrete@exemplo.com': contato('lembrete@exemplo.com', 'ETAPA_0', 20, [101]),   # mudou de etapa: sai da 0, entra na 1
        'convite@exemplo.com': contato('convite@exemplo.com', 'ETAPA_2', 100, [103]),    # já está igual: nada a fazer
        'ultima@exemplo.com': contato('ultima@exemplo.com', bloqueado=True),             # descadastrado: nunca mexe
        'vip@exemplo.com': contato('vip@exemplo.com', 'ETAPA_1', 70, [102]),             # virou VIP: sai da lista de email
        # recente, descanso: não existem no Brevo (não são criados)
    }
    p = bv.planejar(a, contatos, LISTAS, ATRIBUTOS)
    assert 'convite@exemplo.com' not in p.atualizar and 'ultima@exemplo.com' not in p.atualizar
    assert p.atualizar['pos@exemplo.com'] == {'ETAPA': 'ETAPA_0', 'DIAS_SEM_COMPRAR': 20, 'FAMILIA': 'Variado', 'VIP': False, 'CONTROLE': False}
    assert p.entrar_na_lista['Painel · Etapa 0 Pós-compra'] == ['pos@exemplo.com']
    assert p.entrar_na_lista['Painel · Etapa 1 Lembrete'] == ['lembrete@exemplo.com']
    assert sorted(p.sair_da_lista['Painel · Etapa 0 Pós-compra']) == ['lembrete@exemplo.com']
    assert p.sair_da_lista['Painel · Etapa 1 Lembrete'] == ['vip@exemplo.com']
    assert p.resumo['descadastrados (não mexe)'] == 1 and p.resumo['não estão no Brevo (não são criados)'] == 2
    assert {m['email'] for m in p.mudancas} == {'pos@exemplo.com', 'lembrete@exemplo.com', 'vip@exemplo.com'}


def test_plano_aponta_listas_e_atributos_que_faltam():
    a = alvo_de(clientes_de_teste())
    p = bv.planejar(a, {}, {'Painel · Etapa 1 Lembrete': 102}, {'NOME'})
    assert 'Painel · Etapa 0 Pós-compra' in p.listas_ausentes and 'Painel · Etapa 1 Lembrete' not in p.listas_ausentes
    assert set(p.atributos_ausentes) == ATRIBUTOS


# ----------------------------------------------------------------------------
# Rodada do dia
# ----------------------------------------------------------------------------
def classificado(t):
    return regua.rodar(t, '2026-10')[0]


def test_dia_em_modo_teste_le_tudo_e_nao_escreve_nada():
    t = clientes_de_teste()
    contatos = [contato('pos@exemplo.com'), contato('lembrete@exemplo.com', 'ETAPA_0', 20, [101])]
    s = Sessao(rotas_basicas(contatos, LISTAS, ATRIBUTOS))
    r = bv.planejar_do_dia(CHAVE, classificado(t), t, regua.PADRAO, True, s, '2026-10-10 10:00')
    assert r.status == 'ok (modo teste)' and r.leitura_ok_em == '2026-10-10 10:00'
    assert r.plano.resumo['atributos a atualizar'] == 2
    assert s.escritas == [], 'em modo teste nada pode ser escrito'
    assert all(c['metodo'] == 'GET' for c in s.chamadas)


def test_fora_do_modo_teste_aplica_o_plano_em_lotes_e_cria_o_que_falta():
    t = clientes_de_teste()
    contatos = [contato('pos@exemplo.com'), contato('lembrete@exemplo.com', 'ETAPA_0', 20, [101])]
    s = Sessao(rotas_basicas(contatos, LISTAS, {'NOME'}))
    r = bv.planejar_do_dia(CHAVE, classificado(t), t, regua.PADRAO, False, s, '2026-10-10 10:00')   # só em teste de unidade
    assert r.status == 'ok'
    criados = sorted(c['caminho'].split('/')[-1] for c in s.escritas if '/attributes/' in c['caminho'])
    assert criados == sorted(ATRIBUTOS)
    # quem vai entrar numa lista tem os atributos gravados na hora (PUT) ANTES de entrar (a automação dispara na entrada)
    puts = [c for c in s.escritas if c['metodo'] == 'PUT']
    assert sorted(c['caminho'].split('?')[0].split('/')[-1].replace('%40', '@') for c in puts) == ['lembrete@exemplo.com', 'pos@exemplo.com']
    assert any(c['caminho'] == '/contacts/lists/101/contacts/add' and c['json'] == {'emails': ['pos@exemplo.com']} for c in s.escritas)
    assert any(c['caminho'] == '/contacts/lists/101/contacts/remove' and c['json'] == {'emails': ['lembrete@exemplo.com']} for c in s.escritas)
    assert any(c['caminho'] == '/contacts/lists/102/contacts/add' for c in s.escritas)
    assert not [c for c in s.escritas if c['caminho'] == '/contacts/import' and c['json'].get('listIds')]  # nunca atributo e lista juntos
    # nada para contatos descadastrados nem para quem não existe no Brevo
    enviados = json.dumps([c['json'] for c in s.escritas])
    assert 'ultima@exemplo.com' not in enviados and 'descanso@exemplo.com' not in enviados


def test_erro_do_brevo_vira_status_e_nao_derruba():
    t = clientes_de_teste()
    s = Sessao({('GET', '/account'): Resposta(401, {'message': 'unrecognised IP address'})})
    r = bv.planejar_do_dia(CHAVE, classificado(t), t, regua.PADRAO, True, s, '2026-10-10 10:00')
    assert r.status == 'erro: bloqueio_ip' and r.plano is None and r.leitura_ok_em == ''
    s = Sessao({('GET', '/account'): Resposta(401, {'message': 'Key not found'})})
    assert bv.ler_conta(CHAVE, True, s).status == 'erro: chave_invalida'


# ----------------------------------------------------------------------------
# Passo da rotina
# ----------------------------------------------------------------------------
class AbaMinima:
    def __init__(self, linhas):
        self.linhas = linhas

    def get_all_values(self, *a, **k):
        return self.linhas


class PlanilhaMinima:
    def __init__(self, abas):
        self._abas = abas
        self._ss = self

    def worksheet(self, nome):
        if nome not in self._abas:
            raise KeyError(nome)
        return AbaMinima(self._abas[nome])


def passo(monkeypatch, planilha_abas, chave=CHAVE, modo_teste=True, sessao=None, hora=10):
    from painel_monstro import rotina
    t = clientes_de_teste()
    config = Config(brevo_api_key=chave, brevo_modo_teste=modo_teste)
    agora = pd.Timestamp(f'2026-10-10 {hora:02d}:00', tz='America/Sao_Paulo')
    monkeypatch.setattr(rotina.pd.Timestamp, 'now', classmethod(lambda cls, tz=None: agora))
    monkeypatch.setattr(rotina.regua_planilha, 'ler_listas_brevo', lambda p: dict(zip(bv.CODIGOS_DAS_ETAPAS, bv.LISTAS_PADRAO)))
    return rotina.passo_brevo(config, PlanilhaMinima(planilha_abas), t, classificado(t), regua.PADRAO, sessao)


def test_passo_sem_chave_pula(monkeypatch):
    r, paginas = passo(monkeypatch, {}, chave='')
    assert r.status == 'sem chave' and paginas == []


def test_passo_calcula_o_plano_uma_vez_por_dia_e_le_a_conta_nas_outras_rodadas(monkeypatch):
    s = Sessao(rotas_basicas([contato('pos@exemplo.com')], LISTAS, ATRIBUTOS))
    r, paginas = passo(monkeypatch, {}, sessao=s)
    nomes = [n for n, _ in paginas]
    assert nomes == ['brevo_plano', 'brevo_mudancas']
    plano = dict(paginas[0][1].values.tolist())
    assert plano['modo'].startswith('TESTE') and plano['gerado_em'] == '2026-10-10 10:00'
    assert s.escritas == []
    # segunda rodada do mesmo dia: só a leitura da conta (mantém a chave viva), sem plano novo
    s2 = Sessao(rotas_basicas([contato('pos@exemplo.com')], LISTAS, ATRIBUTOS))
    gravado = {'brevo_plano': [['indicador', 'valor'], ['gerado_em', '2026-10-10 10:00'], ['configuracao', '||||||']],
               'brevo_mudancas': [['email', 'etapa_antes']]}
    # mudou a configuração (chave, pausa ou etapas): o plano é refeito na hora, não só no dia seguinte
    s_cfg = Sessao(rotas_basicas([contato('pos@exemplo.com')], LISTAS, ATRIBUTOS))
    r_cfg, pag_cfg = passo(monkeypatch, {**gravado, 'brevo_plano': [['gerado_em', '2026-10-10 10:00'], ['configuracao', 'Ligada||||||']]},
                           sessao=s_cfg, hora=14)
    assert [n for n, _ in pag_cfg] == ['brevo_plano', 'brevo_mudancas']
    # trocar o modo (teste <-> real) também refaz o plano na hora
    s_modo = Sessao(rotas_basicas([contato('pos@exemplo.com')], LISTAS, ATRIBUTOS))
    r_modo, pag_modo = passo(monkeypatch, {**gravado, 'brevo_plano': [['gerado_em', '2026-10-10 10:00'], ['modo', 'REAL'], ['configuracao', '||||||']]},
                             sessao=s_modo, hora=14)
    assert [n for n, _ in pag_modo] == ['brevo_plano', 'brevo_mudancas']
    r2, paginas2 = passo(monkeypatch, gravado, sessao=s2, hora=14)
    assert paginas2 == [] and r2.status == 'ok (modo teste)'
    assert [c['caminho'] for c in s2.chamadas] == ['/account']
    # se a aba brevo_mudancas ficou vazia (gravação falhou), o plano do dia é refeito na rodada seguinte
    s3 = Sessao(rotas_basicas([contato('pos@exemplo.com')], LISTAS, ATRIBUTOS))
    r3, paginas3 = passo(monkeypatch, {'brevo_plano': gravado['brevo_plano'], 'brevo_mudancas': []}, sessao=s3, hora=14)
    assert [n for n, _ in paginas3] == ['brevo_plano', 'brevo_mudancas']


def test_passo_mantem_a_ultima_leitura_boa_quando_o_brevo_falha(monkeypatch):
    s = Sessao({('GET', '/account'): Resposta(401, {'message': 'Key not found'})})
    rodada = [['ultima_rodada_ok', 'brevo_ultima_leitura_ok'], ['2026-10-09 23:07', '2026-10-09 23:07']]
    r, paginas = passo(monkeypatch, {'rodada': rodada, 'brevo_plano': [['gerado_em', '2026-10-10 06:07']]}, sessao=s)
    assert r.status == 'erro: chave_invalida' and r.leitura_ok_em == '2026-10-09 23:07' and paginas == []


def test_antes_das_6h_nao_monta_plano(monkeypatch):
    s = Sessao(rotas_basicas([], LISTAS, ATRIBUTOS))
    r, paginas = passo(monkeypatch, {}, sessao=s, hora=3)
    assert paginas == [] and r.status == 'ok (modo teste)'
