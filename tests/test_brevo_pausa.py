"""Etapa 7.1: chave de pausa, pausa programada, etapas ligadas e cupom por contato. Sessão de mentira, dados fictícios."""
from datetime import date

import pandas as pd
import pytest

from painel_monstro.motor import regua
from painel_monstro.saidas import brevo as bv
from tests.test_brevo import ATRIBUTOS, LISTAS, Resposta, Sessao, classificado, clientes_de_teste, contato, rotas_basicas

HOJE = date(2026, 10, 10)
CONFIG_TUDO_LIGADO = {
    'Régua no Brevo': 'Ligada', 'Pausa programada de': '', 'Pausa programada até': '',
    'Etapa 0 no Brevo': 'Ligada', 'Etapa 1 no Brevo': 'Ligada', 'Etapa 2 no Brevo': 'Ligada', 'Etapa 3 no Brevo': 'Ligada',
}
CUPONS = {'ETAPA_2': ('VOLTAFRETE<MÊS>', 10), 'ETAPA_3': ('VOLTA10<MÊS>', 7)}
CODIGO_DA_LISTA = {n: c for c, n in zip(bv.CODIGOS_DAS_ETAPAS, bv.LISTAS_PADRAO)}


# ----------------------------------------------------------------------------
# Leitura da configuração (nomes exatos; o mais seguro quando não entende)
# ----------------------------------------------------------------------------
def test_politica_padrao_do_enunciado():
    p = bv.ler_politica({'Régua no Brevo': 'Ligada', 'Pausa programada de': '20/11/2026', 'Pausa programada até': '30/11/2026',
                         'Etapa 0 no Brevo': 'Ligada', 'Etapa 1 no Brevo': 'Desligada', 'Etapa 2 no Brevo': 'Desligada',
                         'Etapa 3 no Brevo': 'Desligada'})
    assert p.ligada and p.avisos == () and p.etapas_ligadas == {'ETAPA_0'} and p.etapas_texto() == 'Etapa 0'
    assert p.pausa_de == date(2026, 11, 20) and p.pausa_ate == date(2026, 11, 30)
    assert p.estado(date(2026, 10, 10)) == 'Ligada'
    assert p.estado(date(2026, 11, 19)) == 'Ligada'
    assert p.estado(date(2026, 11, 20)) == 'Em pausa programada até 30/11'   # as duas pontas contam
    assert p.estado(date(2026, 11, 30)) == 'Em pausa programada até 30/11'
    assert p.estado(date(2026, 12, 1)) == 'Ligada'                         # volta no dia seguinte


@pytest.mark.parametrize('valor', ['ligada', 'LIGADA', 'Ligada', ' ligada ', 'Ligado'])
def test_maiusculas_minusculas_e_espacos(valor):
    p = bv.ler_politica({**CONFIG_TUDO_LIGADO, 'Régua no Brevo': valor})
    assert p.ligada and not p.avisos


def test_chave_pausada_vale_mesmo_fora_da_pausa_programada():
    p = bv.ler_politica({**CONFIG_TUDO_LIGADO, 'Régua no Brevo': 'Pausada'})
    assert not p.ligada and p.pausada(HOJE) and p.estado(HOJE) == 'Pausada' and not p.avisos


@pytest.mark.parametrize('de,ate', [('20/11/2026', '30/11/2026'), ('2026-11-20', '2026-11-30'), (46346.0, 46356.0),
                                    (pd.Timestamp('2026-11-20'), pd.Timestamp('2026-11-30'))])
def test_datas_em_qualquer_formato(de, ate):
    p = bv.ler_politica({**CONFIG_TUDO_LIGADO, 'Pausa programada de': de, 'Pausa programada até': ate})
    assert (p.pausa_de, p.pausa_ate) == (date(2026, 11, 20), date(2026, 11, 30)) and not p.avisos


def test_sem_pausa_programada_quando_em_branco():
    p = bv.ler_politica(CONFIG_TUDO_LIGADO)
    assert p.pausa_de is None and p.pausa_ate is None and not p.em_pausa_programada(HOJE) and not p.avisos


@pytest.mark.parametrize('de,ate', [('lixo', '30/11/2026'), ('20/11/2026', ''), ('', '30/11/2026'), ('30/11/2026', '20/11/2026'),
                                    ('31/02/2026', '03/03/2026')])
def test_pausa_programada_invalida_deixa_a_regua_pausada_com_aviso(de, ate):
    p = bv.ler_politica({**CONFIG_TUDO_LIGADO, 'Pausa programada de': de, 'Pausa programada até': ate})
    assert not p.ligada and p.pausada(HOJE) and any('Pausa programada inválida' in a for a in p.avisos)


def test_linhas_ausentes_ou_invalidas_viram_o_mais_seguro_com_aviso():
    p = bv.ler_politica({})
    assert not p.ligada and p.etapas_ligadas == frozenset() and p.estado(HOJE) == 'Pausada'
    assert len(p.avisos) == 5 and all('ausente' in a for a in p.avisos)
    p = bv.ler_politica({**CONFIG_TUDO_LIGADO, 'Régua no Brevo': 'talvez', 'Etapa 2 no Brevo': 'quase'})
    assert not p.ligada and p.etapas_ligadas == {'ETAPA_0', 'ETAPA_1', 'ETAPA_3'}
    assert any('Régua no Brevo' in a and 'inválido' in a for a in p.avisos) and any('Etapa 2 no Brevo' in a for a in p.avisos)


def test_leitura_de_data_da_planilha_e_do_texto():
    assert bv.ler_data('') == (None, True) and bv.ler_data(None) == (None, True)
    assert bv.ler_data('01/10/2026') == (date(2026, 10, 1), True)
    assert bv.ler_data(46296) == (date(2026, 10, 1), True)
    assert bv.ler_data('amanhã')[1] is False and bv.ler_data(5)[1] is False


# ----------------------------------------------------------------------------
# Plano com a política
# ----------------------------------------------------------------------------
def alvo_e_contatos():
    t = clientes_de_teste()
    a = bv.alvo_dos_clientes(classificado(t), t, regua.PADRAO)
    # pos (etapa 0), lembrete (1), convite (2), ultima (3) existem no Brevo sem atributos nem listas
    contatos = {e: contato(e) for e in ('pos@exemplo.com', 'lembrete@exemplo.com', 'convite@exemplo.com', 'ultima@exemplo.com')}
    return a, contatos


def planejar(politica, contatos=None, hoje=HOJE, atributos=ATRIBUTOS):
    a, c = alvo_e_contatos()
    return bv.planejar(a, contatos if contatos is not None else c, LISTAS, atributos, bv.LISTAS_PADRAO, politica, hoje,
                       CODIGO_DA_LISTA, CUPONS)


def test_so_a_etapa_0_ligada_no_primeiro_dia():
    p = planejar(bv.ler_politica({**CONFIG_TUDO_LIGADO, 'Etapa 1 no Brevo': 'Desligada', 'Etapa 2 no Brevo': 'Desligada',
                                  'Etapa 3 no Brevo': 'Desligada'}))
    assert list(p.entrar_na_lista) == ['Painel · Etapa 0 Pós-compra']
    assert p.resumo['barrados por etapa desligada'] == 3 and p.resumo['entram em lista'] == 1
    # os atributos dos barrados continuam atualizando
    assert {'lembrete@exemplo.com', 'convite@exemplo.com', 'ultima@exemplo.com'} <= set(p.atualizar)
    assert 'CUPOM' not in p.atualizar['convite@exemplo.com']          # cupom só quando ENTRA na lista


def test_regua_pausada_congela_listas_mas_atributos_seguem():
    politica = bv.ler_politica({**CONFIG_TUDO_LIGADO, 'Régua no Brevo': 'Pausada'})
    # lembrete já está na lista da etapa 0 por engano de dados antigos: pausada não tira nem põe ninguém
    c = {e: contato(e) for e in ('pos@exemplo.com', 'convite@exemplo.com')}
    c['lembrete@exemplo.com'] = contato('lembrete@exemplo.com', 'ETAPA_0', 20, [101])
    p = planejar(politica, c)
    assert p.entrar_na_lista == {} and p.sair_da_lista == {}
    assert p.resumo['congelados pela pausa (não entram nem saem)'] >= 3
    assert set(p.atualizar) >= {'pos@exemplo.com', 'lembrete@exemplo.com', 'convite@exemplo.com'}
    assert all('CUPOM' not in a for a in p.atualizar.values())


def test_pausa_programada_congela_nos_dias_e_volta_depois():
    politica = bv.ler_politica({**CONFIG_TUDO_LIGADO, 'Pausa programada de': '20/11/2026', 'Pausa programada até': '30/11/2026'})
    dentro = planejar(politica, hoje=date(2026, 11, 25))
    assert dentro.entrar_na_lista == {} and dentro.sair_da_lista == {}
    depois = planejar(politica, hoje=date(2026, 12, 1))
    assert len(depois.entrar_na_lista) == 4                              # ao religar, entra só quem ainda não está


def test_ao_religar_entra_so_quem_ainda_nao_esta_na_lista():
    a, c = alvo_e_contatos()
    c['pos@exemplo.com'] = contato('pos@exemplo.com', 'ETAPA_0', 20, [101])   # já está na lista da etapa 0
    p = planejar(bv.ler_politica(CONFIG_TUDO_LIGADO), c)
    assert 'Painel · Etapa 0 Pós-compra' not in p.entrar_na_lista and 'pos@exemplo.com' not in p.atualizar


def test_etapa_desligada_nao_impede_a_saida_normal():
    # a pessoa está na lista da etapa 3 e voltou a comprar (não é mais alvo dela); etapa 3 desligada não segura a saída
    politica = bv.ler_politica({**CONFIG_TUDO_LIGADO, 'Etapa 3 no Brevo': 'Desligada'})
    c = {'pos@exemplo.com': contato('pos@exemplo.com', 'ETAPA_3', 190, [104])}
    p = planejar(politica, c)
    assert p.sair_da_lista == {'Painel · Etapa 3 Última chamada': ['pos@exemplo.com']}


# ----------------------------------------------------------------------------
# Cupom por contato
# ----------------------------------------------------------------------------
def test_cupom_e_validade_so_para_quem_entra_nas_etapas_2_e_3():
    p = planejar(bv.ler_politica(CONFIG_TUDO_LIGADO))
    assert p.atualizar['convite@exemplo.com']['CUPOM'] == 'VOLTAFRETEOUT'
    assert p.atualizar['convite@exemplo.com']['CUPOM_ATE'] == '20/10'           # 10/10 + 10 dias
    assert p.atualizar['ultima@exemplo.com']['CUPOM'] == 'VOLTA10OUT'
    assert p.atualizar['ultima@exemplo.com']['CUPOM_ATE'] == '17/10'            # 10/10 + 7 dias
    assert 'CUPOM' not in p.atualizar['pos@exemplo.com'] and 'CUPOM' not in p.atualizar['lembrete@exemplo.com']
    assert p.resumo['entram com cupom do mês'] == 2


def test_cupom_troca_o_mes_pelo_mes_atual():
    assert bv.cupom_do_mes('VOLTAFRETE<MÊS>', date(2026, 11, 3)) == 'VOLTAFRETENOV'
    assert bv.cupom_do_mes('VOLTA10<mes>', date(2026, 1, 31)) == 'VOLTA10JAN'
    assert bv.cupom_do_mes('FIXO', date(2026, 5, 1)) == 'FIXO' and bv.cupom_do_mes('', date(2026, 5, 1)) == ''


def test_quem_ja_esta_na_lista_nao_ganha_cupom_novo():
    a, c = alvo_e_contatos()
    c['convite@exemplo.com'] = contato('convite@exemplo.com', 'ETAPA_2', 100, [103])
    p = planejar(bv.ler_politica(CONFIG_TUDO_LIGADO), c)
    assert 'convite@exemplo.com' not in p.atualizar


def test_etapa_com_cupom_sem_configuracao_entra_sem_cupom_e_avisa():
    a, c = alvo_e_contatos()
    p = bv.planejar(a, c, LISTAS, ATRIBUTOS, bv.LISTAS_PADRAO, bv.ler_politica(CONFIG_TUDO_LIGADO), HOJE, CODIGO_DA_LISTA, {})
    assert 'CUPOM' not in p.atualizar['convite@exemplo.com'] and any('sem cupom' in a for a in p.avisos)


def test_atributos_novos_aparecem_como_faltando_ate_serem_criados():
    p = planejar(bv.ler_politica(CONFIG_TUDO_LIGADO), atributos={'ETAPA', 'DIAS_SEM_COMPRAR', 'FAMILIA', 'VIP', 'CONTROLE'})
    assert set(p.atributos_ausentes) == {'CUPOM', 'CUPOM_ATE'}


# ----------------------------------------------------------------------------
# Aplicação: atributos ANTES da lista, em chamadas separadas
# ----------------------------------------------------------------------------
def test_atributos_gravados_antes_de_entrar_na_lista_e_em_chamadas_separadas():
    t = clientes_de_teste()
    contatos = [contato(e) for e in ('convite@exemplo.com', 'ultima@exemplo.com', 'pos@exemplo.com')]
    s = Sessao(rotas_basicas(contatos, LISTAS, ATRIBUTOS))
    politica = bv.ler_politica(CONFIG_TUDO_LIGADO)
    r = bv.planejar_do_dia('chave-falsa-do-teste-123456789', classificado(t), t, regua.PADRAO, False, s, '2026-10-10 10:00',
                           None, politica, HOJE, CUPONS)
    assert r.status == 'ok'
    ordem = [(c['metodo'], c['caminho']) for c in s.escritas]
    for email, lista in (('convite@exemplo.com', 103), ('ultima@exemplo.com', 104)):
        i_put = next(i for i, c in enumerate(s.escritas) if c['metodo'] == 'PUT' and email.replace('@', '%40') in c['caminho'])
        i_add = next(i for i, c in enumerate(s.escritas) if c['caminho'] == f'/contacts/lists/{lista}/contacts/add')
        assert i_put < i_add, 'o atributo tem de estar gravado antes de o contato entrar na lista'
    put = next(c for c in s.escritas if c['metodo'] == 'PUT' and 'convite%40exemplo.com' in c['caminho'])
    assert put['json']['attributes']['CUPOM'] == 'VOLTAFRETEOUT' and put['json']['attributes']['CUPOM_ATE'] == '20/10'
    assert not [c for c in s.escritas if c['caminho'] == '/contacts/import' and c['json'].get('listIds')]
    assert ordem.count(('POST', '/contacts/import')) <= 1


def plano_com(n_entram=3, n_atualizam=6):
    """Plano de mentira: n_entram contatos entram na lista da etapa 0 e n_atualizam só têm atributo novo."""
    p = bv.Plano()
    entram = [f'entra{i}@exemplo.com' for i in range(n_entram)]
    soatrib = [f'so{i}@exemplo.com' for i in range(n_atualizam)]
    for e in entram + soatrib:
        p.atualizar[e] = {'ETAPA': 'ETAPA_0', 'DIAS_SEM_COMPRAR': 20}
    p.entrar_na_lista['Painel · Etapa 0 Pós-compra'] = entram
    return p, entram, soatrib


def brevo_vivo(rotas=None):
    s = Sessao({('GET', '/contacts/attributes'): {'attributes': [{'name': a} for a in ATRIBUTOS]}, **(rotas or {})})
    return bv.Brevo('chave-falsa-do-teste-123456789', modo_teste=False, sessao=s), s


def test_aplicar_nunca_usa_importacao_em_lote_que_exige_lista_e_e_assincrona():
    b, s = brevo_vivo()
    p, entram, soatrib = plano_com()
    feitos = bv.aplicar(b, p, LISTAS, dormir=lambda t: None)
    assert not [c for c in s.escritas if c['caminho'] == '/contacts/import']
    assert feitos['atributos'] == 9 and feitos['entraram'] == 3 and feitos['falhas'] == 0 and feitos['pendentes'] == 0
    puts = [c for c in s.escritas if c['metodo'] == 'PUT']
    # quem vai entrar na lista é atualizado primeiro
    assert all(entra.split('@')[0] in puts[i]['caminho'] for i, entra in enumerate(sorted(entram)))


def test_pausa_entre_as_chamadas_respeita_o_limite_de_10_por_segundo():
    b, s = brevo_vivo()
    esperas = []
    p, _, _ = plano_com(0, 5)
    bv.aplicar(b, p, LISTAS, dormir=esperas.append)
    assert len(esperas) == 5 and all(e >= 0.1 for e in esperas)


def test_orcamento_de_tempo_deixa_o_resto_para_a_rodada_seguinte_sem_pôr_ninguem_na_lista_antes_do_atributo():
    b, s = brevo_vivo()
    p, entram, soatrib = plano_com(3, 6)
    tempo = {'t': 0.0}

    def relogio():
        return tempo['t']

    def dormir(_):
        tempo['t'] += 100   # cada contato "gasta" 100 s
    feitos = bv.aplicar(b, p, LISTAS, dormir=dormir, orcamento_s=250, relogio=relogio)
    assert feitos['atributos'] == 3 and feitos['pendentes'] >= 6
    adicionados = [e for c in s.escritas if c['caminho'].endswith('/contacts/add') for e in c['json']['emails']]
    assert sorted(adicionados) == sorted(entram[:3])   # os 3 que entram foram atualizados primeiro e entraram


def test_falha_em_um_contato_nao_derruba_os_outros_e_ele_nao_entra_na_lista():
    ruim = 'entra1%40exemplo.com'
    b, s = brevo_vivo({('PUT', f'/contacts/{ruim}?identifierType=email_id'): Resposta(404, {'message': 'Contact not found'})})
    p, entram, _ = plano_com(3, 2)
    feitos = bv.aplicar(b, p, LISTAS, dormir=lambda t: None)
    assert feitos['falhas'] == 1 and feitos['pendentes'] == 1 and feitos['atributos'] == 4
    adicionados = [e for c in s.escritas if c['caminho'].endswith('/contacts/add') for e in c['json']['emails']]
    assert 'entra1@exemplo.com' not in adicionados and len(adicionados) == 2


def test_chave_recusada_no_meio_interrompe_tudo():
    b, s = brevo_vivo({('PUT', '/contacts/entra0%40exemplo.com?identifierType=email_id'): Resposta(401, {'message': 'Key not found'})})
    p, _, _ = plano_com(2, 2)
    with pytest.raises(bv.ErroBrevo) as e:
        bv.aplicar(b, p, LISTAS, dormir=lambda t: None)
    assert e.value.tipo == 'chave_invalida'
    assert not [c for c in s.escritas if '/lists/' in c['caminho']]


def test_modo_teste_recusa_aplicar_o_plano():
    b = bv.Brevo('chave-falsa-do-teste-123456789', modo_teste=True, sessao=Sessao())
    with pytest.raises(bv.BrevoModoTeste):
        bv.aplicar(b, bv.Plano(), LISTAS)


def test_pausada_nao_escreve_nenhuma_lista_mesmo_fora_do_modo_teste():
    t = clientes_de_teste()
    s = Sessao(rotas_basicas([contato('pos@exemplo.com')], LISTAS, ATRIBUTOS))
    politica = bv.ler_politica({**CONFIG_TUDO_LIGADO, 'Régua no Brevo': 'Pausada'})
    bv.planejar_do_dia('chave-falsa-do-teste-123456789', classificado(t), t, regua.PADRAO, False, s, 'x', None, politica, HOJE, CUPONS)
    assert not [c for c in s.escritas if '/lists/' in c['caminho']]
    assert any(c['metodo'] == 'PUT' for c in s.escritas)   # atributos seguem
