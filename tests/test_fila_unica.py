"""Testes da fila única de WhatsApp (45 dias, VIP, aviso de garimpo, regras) e da aba Régua. Dados fictícios."""
from datetime import date

import numpy as np
import pandas as pd
import pytest

from painel_monstro.coletor.planilhas_csv import Tabelas
from painel_monstro.motor import regua as motor_regua
from painel_monstro.saidas import carrinhos as c
from painel_monstro.saidas import carrinhos_planilha as cp
from painel_monstro.saidas import fila_unica as fu
from painel_monstro.saidas import regua_planilha as rp
from painel_monstro.saidas.planilha_google import PlanilhaGoogle
from tests.test_carrinhos import AGORA, ApiFalsa, carrinho, produto
from tests.test_carrinhos_planilha import PlanilhaFalsa, celula

HOJE = date(2026, 10, 19)
AGORA_UTC = pd.Timestamp('2026-10-19 13:00', tz='UTC')
PARAMS = c.Parametros(comparacao_pct=0)
TESTE = rp.Teste45(inicio=date(2026, 10, 19), fim=date(2027, 1, 18))


def _pedido(i, email, dia, total=100.0):
    return {'numero': str(i), 'email': email, 'data': pd.Timestamp(dia) + pd.Timedelta(hours=15), 'valido': True,
            'subtotal': total, 'desconto': 0.0, 'frete': 0.0, 'total': total, 'cupom': None}


def mundo(clientes, compras, produtos_na_loja=None):
    """clientes: [(email, nome, telefone, aceita)], compras: [(email, 'AAAA-MM-DD', 'nome do disco', produto_id, valor)]."""
    cli = pd.DataFrame([{'email': e, 'nome': n, 'primeiro_nome': n.split()[0], 'telefone': t, 'cidade': 'Goiânia',
                         'aceita_marketing': a, 'total_consumido': 0.0} for e, n, t, a in clientes])
    ped = pd.DataFrame([_pedido(i, e, d, v) for i, (e, d, _, _, v) in enumerate(compras)])
    itens = pd.DataFrame([{'numero': str(i), 'email': e, 'data': pd.Timestamp(d) + pd.Timedelta(hours=15), 'valido': True,
                           'produto': nome, 'valor': v, 'quantidade': 1, 'sku': None, 'produto_id': pid}
                          for i, (e, d, nome, pid, v) in enumerate(compras)])
    prod = produtos_na_loja if produtos_na_loja is not None else []
    produtos = pd.DataFrame(prod, columns=['url', 'nome', 'categorias', 'estoque', 'estoque_ilimitado', 'exibir', 'custo', 'id', 'criado_em'])
    return Tabelas(clientes=cli, pedidos=ped, itens=itens, produtos=produtos)


def loja_padrao():
    return [
        ['lp-a', 'LP Jorge Ben: A - (1975) - (Vinil Usado)', 'LP > Usado > MPB', 1, False, True, 10.0, 501, '2026-10-01T10:00:00+0000'],
        ['lp-b', 'LP Iron Maiden: B - (1982) - (Vinil Usado)', 'LP > Usado > Hard Rock / Heavy Metal / Metal', 1, False, True, 10.0, 502, '2026-10-05T10:00:00+0000'],
        ['lp-c', 'LP Caetano Veloso: C - (1971) - (Vinil Usado)', 'LP > Usado > MPB', 1, False, True, 10.0, 503, '2026-10-10T10:00:00+0000'],
        ['lp-d', 'LP Esgotado: D - (1980) - (Vinil Usado)', 'LP > Usado > MPB', 0, False, True, 10.0, 504, '2026-10-12T10:00:00+0000'],
    ]


def api_ok():
    return ApiFalsa({501: produto(1), 502: produto(1), 503: produto(1), 504: produto(0)})


# ----------------------------------------------------------------------------
# Sorteio
# ----------------------------------------------------------------------------
def test_sorteio_e_reproduzivel_e_respeita_os_percentuais():
    assert fu.sorteio_45('a@exemplo.com', TESTE) == fu.sorteio_45('A@exemplo.com ', TESTE)
    grupos = [fu.sorteio_45(f'p{i}@exemplo.com', TESTE) for i in range(6000)]
    contagem = {g: grupos.count(g) / 60 for g in ('controle', 'email', 'whatsapp')}
    assert 8 < contagem['controle'] < 12 and 27 < contagem['email'] < 33 and 56 < contagem['whatsapp'] < 64
    todos_whats = rp.Teste45(controle_pct=0, email_pct=0, whatsapp_pct=100)
    assert {fu.sorteio_45(f'p{i}@exemplo.com', todos_whats) for i in range(200)} == {'whatsapp'}


# ----------------------------------------------------------------------------
# Geração: 45 dias
# ----------------------------------------------------------------------------
def com_whatsapp(email):
    """Teste em que todo mundo cai no grupo com WhatsApp (para olhar a mensagem)."""
    return rp.Teste45(inicio=date(2026, 10, 19), fim=date(2027, 1, 18), controle_pct=0, email_pct=0, whatsapp_pct=100)


def gerar(t, teste=TESTE, **kw):
    return fu.gerar(t, PARAMS, motor_regua.PADRAO, teste, kw.pop('hoje', HOJE), AGORA_UTC, kw.pop('api', api_ok()), **kw)


def test_quem_completa_45_dias_hoje_entra_no_sorteio_e_recebe_sugestao_do_genero():
    t = mundo([('a@exemplo.com', 'Ana Souza', '62999990000', True)],
              [('a@exemplo.com', '2026-09-04', 'LP Gilberto Gil: Refazenda - (1975) - (Vinil Usado)', 900, 80.0)], loja_padrao())
    g = gerar(t, com_whatsapp(None))
    assert len(g.linhas) == 1 and len(g.sorteios_novos) == 1
    l = g.linhas[0]
    assert l.origem == '45 dias' and l.modelo == 'G45' and l.cupom == '' and l.situacao == 'Contatar'
    assert 'Refazenda (Gilberto Gil)' in l.mensagem and '{' not in l.mensagem
    # família "Brasil": sugere um dos MPB em estoque, nunca o Iron Maiden nem o esgotado
    assert ('Jorge Ben' in l.mensagem) or ('Caetano Veloso' in l.mensagem)
    assert 'Iron Maiden' not in l.mensagem and 'Esgotado' not in l.mensagem
    assert '/produtos/lp-' in l.mensagem and l.link_whatsapp.startswith('https://wa.me/5562999990000?text=')
    assert l.abandonado_em.tz_convert('America/Sao_Paulo').date() == HOJE


def test_nao_sugere_disco_que_o_cliente_ja_comprou():
    t = mundo([('a@exemplo.com', 'Ana Souza', '62999990000', True)],
              [('a@exemplo.com', '2026-09-04', 'LP Jorge Ben: A', 501, 80.0), ('a@exemplo.com', '2026-09-04', 'LP Caetano Veloso: C', 503, 60.0)],
              loja_padrao())
    g = gerar(t, com_whatsapp(None))
    depois = g.linhas[0].mensagem.split('tudo a ver')[1]
    assert 'Jorge Ben' not in depois and 'Caetano' not in depois


def test_grupos_controle_e_email_nao_geram_whatsapp_mas_ficam_registrados():
    t = mundo([('a@exemplo.com', 'Ana', '62999990000', True)], [('a@exemplo.com', '2026-09-04', 'LP X', 900, 80.0)], loja_padrao())
    so_controle = rp.Teste45(controle_pct=100, email_pct=0, whatsapp_pct=0)
    g = gerar(t, so_controle)
    assert g.linhas == [] and g.sorteios_novos[0]['grupo'] == 'controle'
    so_email = rp.Teste45(controle_pct=0, email_pct=100, whatsapp_pct=0)
    g = gerar(t, so_email)
    assert g.linhas == [] and g.sorteios_novos[0]['grupo'] == 'email'


def test_antes_do_inicio_da_fila_unica_so_ha_carrinhos():
    t = mundo([('a@exemplo.com', 'Ana', '62999990000', True)], [('a@exemplo.com', '2026-09-04', 'LP X', 900, 80.0)], loja_padrao())
    antes = rp.Teste45(controle_pct=0, email_pct=0, whatsapp_pct=100, fila_inicio=date(2026, 10, 20))
    g = gerar(t, antes)
    assert g.linhas == [] and g.sorteios_novos == []
    depois = rp.Teste45(controle_pct=0, email_pct=0, whatsapp_pct=100, fila_inicio=date(2026, 10, 19))
    assert len(gerar(t, depois).linhas) == 1


def test_quem_completou_antes_do_inicio_nao_entra_no_teste():
    t = mundo([('a@exemplo.com', 'Ana', '62999990000', True)], [('a@exemplo.com', '2026-09-01', 'LP X', 900, 80.0)], loja_padrao())  # 48 dias
    g = gerar(t, com_whatsapp(None))
    assert g.linhas == [] and g.sorteios_novos == []


def test_quem_ja_foi_sorteado_nunca_e_sorteado_de_novo():
    t = mundo([('a@exemplo.com', 'Ana', '62999990000', True)], [('a@exemplo.com', '2026-09-04', 'LP X', 900, 80.0)], loja_padrao())
    g = gerar(t, com_whatsapp(None), sorteios={'a@exemplo.com': 'email'})
    assert g.linhas == [] and g.sorteios_novos == []  # ficou no grupo "só email" da primeira vez
    g = gerar(t, rp.Teste45(controle_pct=100, email_pct=0, whatsapp_pct=0), sorteios={'a@exemplo.com': 'whatsapp'})
    assert len(g.linhas) == 1 and g.sorteios_novos == []  # continua no WhatsApp mesmo com percentuais novos


def test_depois_do_fim_do_teste_ninguem_novo_entra():
    t = mundo([('a@exemplo.com', 'Ana', '62999990000', True)], [('a@exemplo.com', '2027-02-01', 'LP X', 900, 80.0)], loja_padrao())
    g = gerar(t, com_whatsapp(None), hoje=date(2027, 3, 18))
    assert g.linhas == [] and g.sorteios_novos == []


def test_nao_aceita_marketing_e_bloqueio_ficam_de_fora():
    t = mundo([('a@exemplo.com', 'Ana', '62999990000', False), ('b@exemplo.com', 'Bia', '62999990001', True)],
              [('a@exemplo.com', '2026-09-04', 'LP X', 900, 80.0), ('b@exemplo.com', '2026-09-04', 'LP X', 900, 80.0)], loja_padrao())
    g = gerar(t, com_whatsapp(None), bloqueio={'b@exemplo.com'})
    assert g.linhas == [] and g.resumo['bloqueados'] == 1


def test_sem_estoque_na_familia_usa_texto_geral_e_telefone_invalido_avisa():
    t = mundo([('a@exemplo.com', 'Ana', '123', True)], [('a@exemplo.com', '2026-09-04', 'LP X', 900, 80.0)], [])
    g = gerar(t, com_whatsapp(None))
    l = g.linhas[0]
    assert l.situacao == 'Telefone inválido' and l.link_whatsapp == '' and 'sem disco em estoque' in l.observacoes
    assert 'uns discos novos' in l.mensagem


# ----------------------------------------------------------------------------
# Geração: VIP e aviso de garimpo
# ----------------------------------------------------------------------------
def test_vip_aos_75_dias_so_para_vip():
    compras_vip = [('v@exemplo.com', d, f'LP V{i}', 900 + i, 200.0) for i, d in enumerate(['2026-01-10', '2026-03-10', '2026-08-05'])]
    t = mundo([('v@exemplo.com', 'Vera', '62999990000', True), ('n@exemplo.com', 'Nando', '62999990001', True)],
              compras_vip + [('n@exemplo.com', '2026-08-05', 'LP N', 950, 80.0)], loja_padrao())  # 75 dias: Vera é VIP (3 compras), Nando não
    g = gerar(t, rp.Teste45(inicio=date(2030, 1, 1), fim=date(2030, 2, 1)))
    assert [l.email for l in g.linhas] == ['v@exemplo.com']
    l = g.linhas[0]
    assert l.origem == 'VIP' and l.modelo == 'VIP' and l.cupom == '' and 'cupom' not in l.mensagem.lower()


def test_aviso_de_garimpo_quando_chega_disco_do_pedido():
    t = mundo([], [], loja_padrao())
    desejos = pd.DataFrame([
        {'email': 'z@exemplo.com', 'telefone': '62999990000', 'nome': 'Zeca Lima', 'desejo': 'Iron Maiden', 'data': '2026-10-01', 'status': ''},
        {'email': 'y@exemplo.com', 'telefone': '62999990001', 'nome': 'Yara', 'desejo': 'Iron Maiden', 'data': '2026-10-09', 'status': ''},  # disco chegou antes do pedido
        {'email': 'x@exemplo.com', 'telefone': '62999990002', 'nome': 'Xico', 'desejo': 'Led Zeppelin', 'data': '2026-10-01', 'status': ''},
        {'email': 'w@exemplo.com', 'telefone': '62999990003', 'nome': 'Wal', 'desejo': 'Iron Maiden', 'data': '2026-10-01', 'status': 'Avisado'},
    ])
    linhas = fu.alertas_garimpo(desejos, t.produtos, PARAMS, AGORA_UTC, {}, set(), api_ok())
    assert [l.email for l in linhas] == ['z@exemplo.com']
    assert linhas[0].origem == 'Garimpo' and linhas[0].modelo == 'ALERTA_GARIMPO' and 'B (Iron Maiden)' in linhas[0].mensagem


# ----------------------------------------------------------------------------
# Regras da fila única
# ----------------------------------------------------------------------------
def linha(origem, email, fone='5562999990000', situacao='Contatar', hora=0):
    return c.LinhaDaFila(
        carrinho=f'{origem}-{email}', abandonado_em=AGORA_UTC - pd.Timedelta(hours=hora), cliente='x', primeiro_nome='X', telefone=fone,
        email=email, itens='', valor=0.0, link='', estoque='OK', estoque_conferido_em=AGORA_UTC, horas=0, toques_enviados=0,
        proximo_toque=1, modelo='T1', cupom='', situacao=situacao, mensagem='', link_whatsapp='', observacoes='', origem=origem)


CFG = rp.FilaUnica(prioridade=('Carrinho', 'Garimpo', 'VIP', '45 dias'), limite_por_dia=3)
AGORA_BRT = AGORA_UTC.tz_convert('America/Sao_Paulo')


def test_uma_mensagem_por_pessoa_a_de_maior_prioridade():
    ls = [linha('45 dias', 'a@exemplo.com'), linha('Carrinho', 'a@exemplo.com'), linha('VIP', 'b@exemplo.com', '5562999990001')]
    fu.aplicar_regras(ls, {}, 0, rp.FilaUnica(limite_por_dia=40), AGORA_BRT)
    assert [l.situacao for l in ls] == ['Já tem outra mensagem na fila', 'Contatar', 'Contatar']


def test_trava_de_30_dias_vale_para_vip_e_45_mas_nao_para_carrinho_e_garimpo():
    ls = [linha('VIP', 'a@exemplo.com', '1'), linha('45 dias', 'b@exemplo.com', '2'), linha('Carrinho', 'c@exemplo.com', '3'),
          linha('Garimpo', 'd@exemplo.com', '4'), linha('VIP', 'e@exemplo.com', '5')]
    recente = AGORA_UTC - pd.Timedelta(days=10)
    antigo = AGORA_UTC - pd.Timedelta(days=40)
    ultimo = {'a@exemplo.com': recente, '2': recente, 'c@exemplo.com': recente, 'd@exemplo.com': recente, 'e@exemplo.com': antigo}
    fu.aplicar_regras(ls, ultimo, 0, rp.FilaUnica(limite_por_dia=40), AGORA_BRT)
    assert [l.situacao for l in ls] == ['Aguardar 30 dias', 'Aguardar 30 dias', 'Contatar', 'Contatar', 'Contatar']
    assert ls[0].proximo_envio == recente + pd.Timedelta(days=30)


def test_limite_diario_corta_a_menor_prioridade_primeiro_e_desconta_o_que_ja_foi_enviado():
    ls = [linha('45 dias', 'a@exemplo.com', '1', hora=5), linha('VIP', 'b@exemplo.com', '2', hora=5), linha('Carrinho', 'c@exemplo.com', '3', hora=1),
          linha('Carrinho', 'd@exemplo.com', '4', hora=9), linha('Garimpo', 'e@exemplo.com', '5')]
    fu.aplicar_regras(ls, {}, 0, CFG, AGORA_BRT)  # limite 3
    por_email = {l.email: l.situacao for l in ls}
    assert por_email == {'a@exemplo.com': 'Fica para amanhã', 'b@exemplo.com': 'Fica para amanhã', 'c@exemplo.com': 'Contatar',
                         'd@exemplo.com': 'Contatar', 'e@exemplo.com': 'Contatar'}
    ls2 = [linha('Carrinho', 'c@exemplo.com', '3'), linha('VIP', 'b@exemplo.com', '2')]
    fu.aplicar_regras(ls2, {}, 2, CFG, AGORA_BRT)  # 2 já enviados hoje: sobra 1 vaga
    assert [l.situacao for l in ls2] == ['Contatar', 'Fica para amanhã']


def test_prioridade_vem_da_configuracao():
    ls = [linha('Carrinho', 'a@exemplo.com', '1'), linha('VIP', 'b@exemplo.com', '2')]
    fu.aplicar_regras(ls, {}, 0, rp.FilaUnica(prioridade=('VIP', 'Carrinho'), limite_por_dia=1), AGORA_BRT)
    assert [l.situacao for l in ls] == ['Fica para amanhã', 'Contatar']


# ----------------------------------------------------------------------------
# Aba Régua e abas completadas
# ----------------------------------------------------------------------------
@pytest.fixture
def pg_():
    p = PlanilhaGoogle(PlanilhaFalsa())
    cp.garantir_abas(p)
    return p


def test_cria_regua_e_completa_configuracao_e_mensagens_sem_mexer_no_que_existe(pg_):
    cfg = pg_._ss.abas['Configuração']
    cfg.grade[(2, 2)] = 'Outra, da Monstro'
    antes = len(cfg.get_all_values())
    rp.preparar_abas(pg_)
    assert 'Régua' in pg_._ss.abas and 'desejos' in pg_._ss.abas
    nomes = [l[0] for l in cfg.get_all_values()]
    assert 'Teste 45 dias: só email (%)' in nomes and len(nomes) == antes + len(rp.CONFIG_NOVA)
    assert cfg.grade[(2, 2)] == 'Outra, da Monstro'
    modelos = [l[0] for l in pg_._ss.abas['Mensagens'].get_all_values()]
    assert {'G45', 'VIP', 'ALERTA_GARIMPO', '{ultimo_disco}', '{sugestao}', '{link_sugestao}'} <= set(modelos)
    n_cfg, n_msg = len(cfg.get_all_values()), len(pg_._ss.abas['Mensagens'].get_all_values())
    rp.preparar_abas(pg_)  # segunda vez não acrescenta nada
    assert (len(cfg.get_all_values()), len(pg_._ss.abas['Mensagens'].get_all_values())) == (n_cfg, n_msg)


def test_motor_le_as_janelas_da_aba_regua(pg_):
    rp.preparar_abas(pg_)
    assert rp.ler_regua(pg_) == motor_regua.PADRAO or rp.ler_regua(pg_).etapas == motor_regua.PADRAO.etapas
    aba = pg_._ss.abas['Régua']
    linhas = {str(l[0]): i + 1 for i, l in enumerate(aba.get_all_values())}
    aba.grade[(linhas['Etapa 2 · Convite'], 2)] = 100
    aba.grade[(linhas['Etapa 2 · Convite'], 3)] = 130
    aba.grade[(linhas['Etapa 0 · Pós-compra'], 5)] = 'Não'
    aba.grade[(linhas['Controle de cada etapa (%)'], 2)] = 20
    aba.grade[(linhas['VIP: mínimo de compras'], 2)] = 4
    p = rp.ler_regua(pg_)
    e2 = next(e for e in p.etapas if e.nome == 'Etapa 2 · Convite')
    assert (e2.dias_min, e2.dias_max) == (100, 130) and e2.beneficio is True
    assert next(e for e in p.etapas if e.nome == 'Etapa 0 · Pós-compra').tem_controle is False
    assert p.controle == 0.2 and p.vip_min_compras == 4


def test_motor_usa_a_janela_editada():
    base = pd.DataFrame({'n': [2], 'ultima': [pd.Timestamp('2026-05-01')], 'total': [100.0], 'dias': [110], 'primeiro_nome': ['A'],
                         'cidade': ['G'], 'telefone': ['1'], 'vip': [False]}, index=['a@exemplo.com'])
    ref = pd.Timestamp('2026-10-10')
    padrao = motor_regua.classificar(base, '2026-10', ref)
    assert padrao.loc['a@exemplo.com', 'etapa'] == 'Etapa 2 · Convite'  # 90 a 119
    editada = motor_regua.ParametrosRegua(etapas=tuple(
        motor_regua.Etapa(e.nome, 130, 150, e.so_primeira_compra, e.tem_controle, e.beneficio) if e.nome.startswith('Etapa 2') else e
        for e in motor_regua.PADRAO.etapas))
    assert motor_regua.classificar(base, '2026-10', ref, editada).loc['a@exemplo.com', 'etapa'] == 'Sem etapa'


def test_parametros_do_teste_vem_da_configuracao(pg_):
    rp.preparar_abas(pg_)
    assert rp.ler_teste45(pg_) == rp.Teste45()
    cfg = pg_._ss.abas['Configuração']
    linhas = {str(l[0]): i + 1 for i, l in enumerate(cfg.get_all_values())}
    cfg.grade[(linhas['Teste 45 dias: email e WhatsApp (%)'], 2)] = 50
    cfg.grade[(linhas['Teste 45 dias: só email (%)'], 2)] = 40
    cfg.grade[(linhas['Limite de mensagens por dia'], 2)] = 25
    cfg.grade[(linhas['Ordem de prioridade da fila'], 2)] = 'VIP, Carrinho'
    t = rp.ler_teste45(pg_)
    assert (t.email_pct, t.whatsapp_pct) == (40, 50)
    assert rp.ler_fila_unica(pg_) == rp.FilaUnica(prioridade=('VIP', 'Carrinho'), limite_por_dia=25)


def test_registro_do_sorteio_so_acrescenta(pg_):
    assert rp.ler_sorteios(pg_) == {}
    n = rp.gravar_sorteios(pg_, [rp.linha_do_sorteio('A@exemplo.com', 'whatsapp', HOJE, 45, 2, 150.0, False)])
    assert n == 1 and rp.ler_sorteios(pg_) == {'a@exemplo.com': 'whatsapp'}
    # mesma pessoa de novo (mesmo com outro grupo): não grava
    n = rp.gravar_sorteios(pg_, [rp.linha_do_sorteio('a@exemplo.com', 'controle', HOJE, 46, 2, 150.0, False),
                                 rp.linha_do_sorteio('b@exemplo.com', 'email', HOJE, 45, 1, 50.0, False)])
    assert n == 1 and rp.ler_sorteios(pg_) == {'a@exemplo.com': 'whatsapp', 'b@exemplo.com': 'email'}
    linhas = pg_._ss.abas['regua'].get_all_values()
    assert linhas[0][:3] == ['mes', 'data_referencia', 'email'] and linhas[1][0] == 'teste45'


# ----------------------------------------------------------------------------
# Ciclo completo na planilha
# ----------------------------------------------------------------------------
def ciclo(pg_, carrinhos, t, momento=AGORA_UTC):
    class Api(ApiFalsa):
        def listar(self, caminho, **kw):
            return iter(carrinhos)
    return cp.atualizar_fila(pg_, Api({10: produto(), 501: produto(1), 502: produto(1), 503: produto(1)}), t, momento, fila_unica=True)


def tabelas_do_ciclo():
    return mundo([('a@exemplo.com', 'Ana Souza', '62999990000', True), ('v@exemplo.com', 'Vera Lima', '62999990001', True)],
                 [('a@exemplo.com', '2026-09-04', 'LP Gilberto Gil: Refazenda - (1975) - (Vinil Usado)', 900, 80.0)]
                 + [('v@exemplo.com', d, f'LP V{i}', 800 + i, 200.0) for i, d in enumerate(['2026-01-10', '2026-03-10', '2026-08-05'])],
                 loja_padrao())


def test_ciclo_grava_origem_sorteio_e_nao_toca_na_mariana(pg_):
    cfg_ = pg_
    rp.preparar_abas(cfg_)
    linhas = {str(l[0]): i + 1 for i, l in enumerate(pg_._ss.abas['Configuração'].get_all_values())}
    pg_._ss.abas['Configuração'].grade[(linhas['Teste 45 dias: grupo de controle (%)'], 2)] = 0
    pg_._ss.abas['Configuração'].grade[(linhas['Teste 45 dias: só email (%)'], 2)] = 0
    pg_._ss.abas['Configuração'].grade[(linhas['Teste 45 dias: email e WhatsApp (%)'], 2)] = 100
    t = tabelas_do_ciclo()
    cart = carrinho(id=7, email='k@exemplo.com', fone='62999990009', created_at='2026-10-17T14:00:00+0000', updated_at='2026-10-17T14:00:00+0000')
    r = ciclo(pg_, [cart], t, pd.Timestamp('2026-10-19 13:00', tz='UTC'))
    aba = pg_._ss.abas['Fila']
    origens = {celula(aba, 'Origem', i): celula(aba, 'Situação', i) for i in range(2, 5)}
    assert origens == {'Carrinho': 'Contatar', '45 dias': 'Contatar', 'VIP': 'Contatar'}
    assert r['fila_unica']['45 dias com WhatsApp'] == 1
    assert pg_._ss.abas['regua'].get_all_values()[1][2] == 'a@exemplo.com'
    # a Mariana marca o envio do 45 dias; o ciclo seguinte não duplica nem encerra errado
    linha_45 = next(i for i in range(2, 5) if celula(aba, 'Origem', i) == '45 dias')
    aba.grade[(linha_45, cp.COL['Toques já enviados'] + 1)] = 1
    aba.grade[(linha_45, cp.COL['Último envio em'] + 1)] = '2026-10-19 11:00'
    ciclo(pg_, [cart], t, pd.Timestamp('2026-10-20 13:00', tz='UTC'))
    assert celula(aba, 'Toques já enviados', linha_45) == 1
    assert celula(aba, 'Situação', linha_45) == 'Encerrado'
    assert len([l for l in aba.get_all_values()[1:] if l[0]]) == 3  # carrinho + 45 dias + VIP
    assert len(pg_._ss.abas['regua'].get_all_values()) == 2  # só um sorteio gravado
