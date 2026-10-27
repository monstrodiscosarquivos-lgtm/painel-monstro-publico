"""D-071: lembrete da raspadinha no Brevo. Sessão de mentira, nenhuma chamada real."""
from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from painel_monstro.saidas import brevo as bv
from painel_monstro.saidas import raspadinha_lembrete as rl
from tests.test_brevo import CHAVE, Resposta, Sessao

HOJE = date(2026, 10, 21)
CAB_JOG = ['quando', 'campanha', 'email', 'canal', 'utm_source', 'utm_medium', 'utm_campaign', 'utm_content',
           'premio', 'tipo', 'valor', 'cupom', 'valido_ate', 'cupom_status', 'consentiu', 'novo_contato']


def jog(email, cupom, ate='2026-10-23', quando='2026-10-16 10:00:00', status='criado', tipo='Porcentagem', valor='15', aceitou='Não'):
    return dict(zip(CAB_JOG, [quando, 'out26', email, 'email', '', '', '', '', '15%', tipo, valor, cupom, ate, status, aceitou, 'Não']))


CAMP = [{'campanha': 'out26', 'nome': 'Raspadinha de outubro', 'pedido_minimo': '100'}]


def test_janela_de_dias_e_regras_de_quem_entra():
    js = [jog('a@x.com', 'RASPA1'),                                  # vence em 2 dias: entra
          jog('b@x.com', 'RASPA2', ate='2026-10-25'),                # vence em 4 dias: ainda não
          jog('c@x.com', 'RASPA3', ate='2026-10-20'),                # já venceu
          jog('d@x.com', 'RASPA4'),                                  # usou
          jog('e@x.com', 'TESTEAB12', status='teste'),               # cupom de teste
          jog('f@x.com', '', status='sem prêmio'),
          jog('g@x.com', 'RASPA7', status='erro: 500'),
          jog('h@x.com', 'RASPA8', quando='2026-10-21 09:00:00'),    # raspou hoje
          jog('i@x.com', 'RASPA9'),                                  # já recebeu
          jog('a@x.com', 'RASPA1')]                                  # linha repetida
    c = rl.candidatos(js, CAMP, {'RASPA4'}, {'RASPA9'}, HOJE, 2)
    assert [x.cupom for x in c] == ['RASPA1']
    assert c[0].atributos() == {'RASP_CUPOM': 'RASPA1', 'RASP_PREMIO': '15% de desconto', 'RASP_VALIDADE': '23/10',
                                'RASP_CAMPANHA': 'Raspadinha de outubro', 'RASP_MINIMO': 'em compras a partir de R$ 100'}
    # no último dia ainda lembra
    assert [x.cupom for x in rl.candidatos([jog('a@x.com', 'RASPA1', ate='2026-10-21')], CAMP, set(), set(), HOJE, 2)] == ['RASPA1']


def test_textos_do_premio_e_minimo():
    assert rl.texto_premio('Frete grátis', '0') == 'frete grátis'
    assert rl.texto_premio('Valor em R$', '20') == 'R$ 20 de desconto'
    assert rl.texto_premio('Porcentagem', '12.5') == '12,5% de desconto'
    assert rl.texto_minimo('0') == '' and rl.texto_minimo('') == ''


@pytest.mark.parametrize('valor,dias', [('', 2), ('3', 3), ('0', 0), ('abc', 0), ('2,0', 2)])
def test_dias_da_configuracao(valor, dias):
    assert rl.ler_dias({rl.CHAVE_DIAS: valor}) == dias
    assert rl.ler_dias({}) == 2


def test_cupons_usados_le_pedidos_com_varios_codigos():
    p = pd.DataFrame({'cupom': ['raspa1, OUTRO', None, 'RASPA2']})
    assert rl.cupons_usados(p) == {'RASPA1', 'OUTRO', 'RASPA2'}


def _rotas(contatos, lista=True):
    r = {('GET', '/contacts/lists'): {'lists': ([{'id': 77, 'name': rl.LISTA}] if lista else [])},
         ('GET', '/contacts/attributes'): {'attributes': [{'name': 'RASP_CUPOM'}]}}
    for email, c in contatos.items():
        r[('GET', f'/contacts/{email.replace("@", "%40")}')] = c if c is not None else Resposta(404, {'message': 'Contact does not exist'})
    return r


def test_executar_atualiza_cria_com_aceite_pula_sem_aceite_e_descadastrado():
    s = Sessao(_rotas({'a@x.com': {'id': 1, 'listIds': [77]}, 'b@x.com': None, 'c@x.com': None,
                       'd@x.com': {'id': 4, 'emailBlacklisted': True}}))
    b = bv.Brevo(CHAVE, modo_teste=False, sessao=s)
    cands = rl.candidatos([jog('a@x.com', 'RA'), jog('b@x.com', 'RB', aceitou='Sim'), jog('c@x.com', 'RC'), jog('d@x.com', 'RD')],
                          CAMP, set(), set(), HOJE, 2)
    reg = [{'cupom': 'VELHO', 'email': 'z@x.com', 'campanha': 'set26', 'premio': '10% de desconto', 'valido_ate': '2026-10-01', 'status': rl.ENVIADO}]
    r = rl.executar(b, cands, reg, HOJE, '2026-10-21 10:07')
    assert (r.enviados, r.fora, r.sairam, r.falhas) == (2, 2, 1, 0)
    esc = [(c['metodo'], c['caminho'], c['json']) for c in s.escritas]
    criados = [e for e in esc if e[1].startswith('/contacts/attributes/normal/')]
    assert len(criados) == 4   # RASP_CUPOM já existia
    assert ('PUT', '/contacts/a%40x.com?identifierType=email_id', {'attributes': cands[0].atributos()}) in esc
    assert ('POST', '/contacts/lists/77/contacts/remove', {'emails': ['a@x.com']}) in esc          # sai e entra de novo
    assert ('POST', '/contacts', {'email': 'b@x.com', 'attributes': cands[1].atributos(), 'updateEnabled': False}) in esc
    entradas = [e[2]['emails'] for e in esc if e[1] == '/contacts/lists/77/contacts/add']
    assert entradas == [['a@x.com'], ['b@x.com']]
    assert ('POST', '/contacts/lists/77/contacts/remove', {'emails': ['z@x.com']}) in esc          # cupom vencido sai
    assert not any('c%40x.com' in e[1] or 'd%40x.com' in e[1] for e in esc)
    status = {l[0]: l[5] for l in r.linhas}
    assert status == {'RA': rl.ENVIADO, 'RB': rl.ENVIADO, 'RC': rl.PULADO_SEM_ACEITE, 'RD': rl.PULADO_DESCADASTRADO, 'VELHO': rl.SAIU}


def test_modo_teste_e_lista_ausente_nao_escrevem():
    cands = rl.candidatos([jog('a@x.com', 'RA')], CAMP, set(), set(), HOJE, 2)
    s = Sessao(_rotas({'a@x.com': {'id': 1}}))
    r = rl.executar(bv.Brevo(CHAVE, modo_teste=True, sessao=s), cands, [], HOJE, 'x')
    assert r.receberiam == 1 and not r.linhas and s.chamadas == []
    s2 = Sessao(_rotas({'a@x.com': {'id': 1}}, lista=False))
    r2 = rl.executar(bv.Brevo(CHAVE, modo_teste=False, sessao=s2), cands, [], HOJE, 'x')
    assert 'falta criar a lista' in r2.status and not r2.linhas and s2.escritas == []


def test_falha_num_contato_nao_derruba_e_tenta_de_novo_depois():
    rotas = _rotas({'a@x.com': {'id': 1}, 'b@x.com': {'id': 2}})
    rotas[('PUT', '/contacts/a%40x.com?identifierType=email_id')] = Resposta(400, {'message': 'ruim'})
    s = Sessao(rotas)
    cands = rl.candidatos([jog('a@x.com', 'RA'), jog('b@x.com', 'RB')], CAMP, set(), set(), HOJE, 2)
    r = rl.executar(bv.Brevo(CHAVE, modo_teste=False, sessao=s), cands, [], HOJE, 'x')
    assert (r.enviados, r.falhas) == (1, 1) and [l[0] for l in r.linhas] == ['RB']


def test_chave_invalida_interrompe():
    rotas = _rotas({'a@x.com': {'id': 1}})
    rotas[('GET', '/contacts/a%40x.com')] = Resposta(401, {'message': 'Key not found'})
    cands = rl.candidatos([jog('a@x.com', 'RA')], CAMP, set(), set(), HOJE, 2)
    with pytest.raises(bv.ErroBrevo):
        rl.executar(bv.Brevo(CHAVE, modo_teste=False, sessao=Sessao(rotas)), cands, [], HOJE, 'x')


class Planilha:
    def __init__(self):
        self.mescladas = []

    def mesclar(self, titulo, df, chave):
        self.mescladas.append((titulo, df, chave))


def _abas(jogadas):
    return {'rasp_jogadas': [CAB_JOG] + [list(j.values()) for j in jogadas],
            'rasp_campanhas': [['campanha', 'nome', 'pedido_minimo'], ['out26', 'Raspadinha de outubro', '0']],
            rl.ABA: []}


def test_passo_rotina_respeita_horario_configuracao_e_grava_a_aba():
    cfg = SimpleNamespace(brevo_api_key=CHAVE, brevo_modo_teste=False)
    abas = _abas([jog('a@x.com', 'RA')])
    agora = pd.Timestamp('2026-10-21 10:07', tz='America/Sao_Paulo')
    tab = SimpleNamespace(pedidos=pd.DataFrame({'cupom': [None]}))
    p = Planilha()
    assert rl.passo_rotina(cfg, p, tab, pd.Timestamp('2026-10-21 03:07', tz='America/Sao_Paulo'), abas.get, {}).status.startswith('fora do horário')
    assert rl.passo_rotina(cfg, p, tab, agora, abas.get, {rl.CHAVE_DIAS: '0'}).status.startswith('desligado')
    s = Sessao(_rotas({'a@x.com': {'id': 1}}))
    r = rl.passo_rotina(cfg, p, tab, agora, abas.get, {}, sessao=s)
    assert r.enviados == 1
    titulo, df, chave = p.mescladas[0]
    assert titulo == rl.ABA and chave == ['cupom'] and list(df.columns) == rl.COLUNAS
    assert df.iloc[0].tolist() == ['RA', 'a@x.com', 'out26', '15% de desconto', '2026-10-23', rl.ENVIADO, '2026-10-21 10:07']
