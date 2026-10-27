"""Nada pode travar o fluxo (D-039): nada some da fila, saídas explicadas, aviso de não marcada, rodada que falha,
gravação só depois de calcular, dias da fila e nome do disco. Dados fictícios."""
from datetime import date

import pandas as pd
import pytest

from painel_monstro import rotina
from painel_monstro.coletor import nuvemshop_api as na
from painel_monstro.saidas import carrinhos as c
from painel_monstro.saidas import carrinhos_planilha as cp
from painel_monstro.saidas import contatos_manuais as cm
from painel_monstro.saidas import planilha_google as pgm
from painel_monstro.saidas import regua_planilha as rp
from tests import simulacao_fila as sim
from painel_monstro.config import Config
from tests.test_nuvemshop_api import APIDeMentira, agora_fixo, cliente, pedido
from tests.test_rotina import config, mundo, rodar as rodar_rotina  # noqa: F401 (fixtures)


# ----------------------------------------------------------------------------
# Nome do disco: "Álbum (Artista)"
# ----------------------------------------------------------------------------
@pytest.mark.parametrize('nome,esperado', [
    ('LP Violator - Unholy Retribution (Vinil Usado)', 'Unholy Retribution (Violator)'),          # exemplo do pedido
    ('LP Grim Reaper: Rock You To Hell - (Importado) - (Vinil Usado)', 'Rock You To Hell (Grim Reaper)'),
    ('LP Quinteto Violado – Quinteto Violado (1972) - (Vinil Usado)', 'Quinteto Violado (Quinteto Violado)'),
    ('LP Novos Baianos - O Melhor Dos Novos Baianos (1976) (Vinil usado)', 'O Melhor Dos Novos Baianos (Novos Baianos)'),
    ('LP Rita Lee - A Marca Da Zorra (Novo/Lacrado)', 'A Marca Da Zorra (Rita Lee)'),
    ('LP Compilação: Premier Mundial Track - (1973) - (Vinil Usado)', 'Premier Mundial Track (Compilação)'),
    ('LP Public Enemy: It Takes a Nation of Millions to Hold Us Back (1988/2023) - (Importado) - (Novo/Lacrado)',
     'It Takes a Nation of Millions to Hold Us Back (Public Enemy)'),
    ('LP Gilberto Gil - Gilberto Gil (1971) (Importado) (Vinil Usado)', 'Gilberto Gil (Gilberto Gil)'),
    ('LP Amy Winehouse – Live At Glastonbury 2007 (Novo/Lacrado) (Importado)', 'Live At Glastonbury (Amy Winehouse)'),
    ('The Beatles – 1 (2000) - (Novo/Lacrado) (Importado)', '1 (The Beatles)'),                    # sem prefixo de formato
    ('CD Mustang - Tá tudo mundando, mas nem sempre pra melhor (Novo/Lacrado)', 'Tá tudo mundando, mas nem sempre pra melhor (Mustang)'),
    ('Cd Jupiter Apple: Sugar Doors - A 4-Track Experience (2000)', 'Sugar Doors - A 4-Track Experience (Jupiter Apple)'),
    ('Compacto-Os Mutantes (1969)', 'Os Mutantes'),                                              # sem separador: não inventa artista
    ('Compacto The Beatles (1967) (Usado)', 'The Beatles'),
    ('LP/EP Artista: Titulo (2001)', 'Titulo (Artista)'),
    ('Mini-LP Fulano - Beltrano (Importado)', 'Beltrano (Fulano)'),
    ('Box Pink Floyd - The Wall (Novo/Lacrado)', 'The Wall (Pink Floyd)'),
    ('Fita K7 Jorge Ben –A Arte de... (Usada)', 'A Arte de... (Jorge Ben)'),
    ('LP John Lennon-Double Fantasy-1980', 'Double Fantasy (John Lennon)'),                       # hifen sem espaços
    ('LP Pink Floyd-At Pompeii MCMLXXII (Novo Lacrado)', 'At Pompeii MCMLXXII (Pink Floyd)'),
    ('LP Prince: 1999 - (1982) - (Vinil Usado)', '1999 (Prince)'),                               # álbum que é um ano: mantém
    ('LP Jimi Hendrix – Cornerstones 1967 - 1970 (1990) (Vinil usado)', 'Cornerstones (Jimi Hendrix)'),
    ('LP Cachorro Grande - Costa do Marfim (Novo/Lacrado', 'Costa do Marfim (Cachorro Grande)'),   # parêntese aberto
    ('LP Rita Lee 1980 (Vinil Usado)', 'Rita Lee'),
    ('LP The Beatles - 1962-1966 (1973) (Vinil usado)', '1962-1966 (The Beatles)'),   # título que é um período
    ('LP MPB-4: Cicatrizes - (1972) - (Vinil Usado)', 'Cicatrizes (MPB-4)'),                      # hifen no nome do artista
    ('LP Jay-Z', 'Jay-Z'),
    ('LP Bread: Baby I\'m-A Want You - (1972) - (Vinil Usado)', "Baby I'm-A Want You (Bread)"),
    ('LP Various Artists: Street Survivors (Original Motion Picture Soundtrack) - (1984)', 'Street Survivors (Various Artists)'),
])
def test_nome_do_disco(nome, esperado):
    assert c.nome_do_disco(nome) == esperado


def test_nome_do_disco_nunca_devolve_vazio_nem_formato_no_comeco():
    for n in ['LP', 'LP (Vinil Usado)', 'CD 2001', '', None]:
        assert isinstance(c.nome_do_disco(n), str)
    assert not c.nome_do_disco('LP Artista - Album (Vinil Usado)').startswith('LP')


def test_genero_reconhece_artista_sem_acento():
    from painel_monstro.motor import generos
    assert 'Brasil' in generos.familias('LP > Usado', 'LP Emilio Santiago - Aquarela Brasileira')
    assert generos.familias('LP > Novo/Lacrado > Importados', 'LP Deadpool & Wolverine - Trilha Sonora') == set()


def test_so_disco_vira_sugestao():
    assert c.eh_disco('LP Artista: Album') and c.eh_disco('CD Artista - Album') and c.eh_disco('Compacto-Os Mutantes')
    assert not c.eh_disco('Camiseta Oficial: Júpiter Maçã - Preta') and not c.eh_disco('Combo Dois Discos')
    assert not c.eh_disco('LP Chico Buarque - A Arte De Vol.1 e Vol.2 (Kit / Combo)')   # kit de discos não é sugestão


# ----------------------------------------------------------------------------
# Dias da fila
# ----------------------------------------------------------------------------
def test_leitura_dos_dias_da_fila():
    assert c.ler_dias_da_fila('seg a sáb') == frozenset(range(6))
    assert c.ler_dias_da_fila('Seg a Sab') == frozenset(range(6))
    assert c.ler_dias_da_fila('seg, qua, sex') == frozenset({0, 2, 4})
    assert c.ler_dias_da_fila('seg a sex e dom') == frozenset({0, 1, 2, 3, 4, 6})
    assert c.ler_dias_da_fila('sex a seg') == frozenset({4, 5, 6, 0})
    assert c.ler_dias_da_fila('todos') == frozenset(range(7))
    assert c.ler_dias_da_fila('') == c.DIAS_DA_FILA_PADRAO and c.ler_dias_da_fila('coisa sem sentido') == c.DIAS_DA_FILA_PADRAO


def test_prazo_nao_conta_nos_dias_fora_da_fila():
    dias = c.DIAS_DA_FILA_PADRAO
    sabado_23h = pd.Timestamp('2026-10-17 23:00', tz=c.FUSO_LOJA)
    segunda_10h = pd.Timestamp('2026-10-19 10:00', tz=c.FUSO_LOJA)
    assert c.horas_de_fila(sabado_23h, segunda_10h, dias) == 1 + 10  # 1h de sábado + 10h de segunda; domingo não conta
    assert c.horas_de_fila(sabado_23h, segunda_10h, frozenset(range(7))) == 35
    assert c.somar_horas_de_fila(sabado_23h, 24, dias) == pd.Timestamp('2026-10-19 23:00', tz=c.FUSO_LOJA)  # 1h de sábado + 23h de segunda
    assert c.somar_horas_de_fila(pd.Timestamp('2026-10-16 11:00', tz=c.FUSO_LOJA), 24, dias) == pd.Timestamp('2026-10-17 11:00', tz=c.FUSO_LOJA)


def test_carrinho_do_sabado_a_noite_espera_o_domingo_inteiro():
    from tests.test_carrinhos import ApiFalsa, produto as prod, tabelas
    quando = pd.Timestamp('2026-10-17 20:00', tz=c.FUSO_LOJA).tz_convert('UTC').strftime('%Y-%m-%dT%H:%M:%S+0000')
    cart = {'id': 1, 'created_at': quando, 'updated_at': quando, 'completed_at': None, 'contact_name': 'Ana', 'contact_email': 'a@exemplo.com',
            'contact_phone': '62999990000', 'abandoned_checkout_url': 'https://loja.exemplo/c/1', 'subtotal': '100', 'total': '100',
            'products': [{'product_id': 10, 'name': 'LP A - B', 'quantity': 1, 'price': '100'}]}
    api = ApiFalsa({10: prod()})
    seg_6h = pd.Timestamp('2026-10-19 06:00', tz=c.FUSO_LOJA).to_pydatetime()
    fila, motivos = c.montar_fila([cart], tabelas(), c.Parametros(comparacao_pct=0), seg_6h, api)
    assert fila == [] and sum(motivos.values()) == 1      # 4h de sábado + 6h de segunda = 10h, ainda cedo
    seg_9h = pd.Timestamp('2026-10-19 09:00', tz=c.FUSO_LOJA).to_pydatetime()
    fila, _ = c.montar_fila([cart], tabelas(), c.Parametros(comparacao_pct=0), seg_9h, api)
    assert len(fila) == 1                                  # 4h + 9h = 13h


# ----------------------------------------------------------------------------
# Simulação de vários dias (Mariana não marca nada; uma rodada falha)
# ----------------------------------------------------------------------------
def test_simulacao_nada_some_nada_avanca_e_a_rodada_que_falhou_nao_altera_nada():
    linha = dict(sim.rodar_simulacao())
    seg = linha['Seg 19/10 10h · primeira rodada (limite 3 por dia)']
    assert 'Carrinho A: Contatar' in seg and 'Carrinho B: Contatar' in seg and 'v1: Contatar' in seg
    assert 'p1: Fica para amanhã' in seg                                                   # excesso do limite não some
    ter = linha['Ter 20/10 10h · a Mariana não marcou nada']
    assert ter.count('[AVISO: não marcada]') == 3 and 'p2: Fica para amanhã' in ter       # pendente volta com aviso
    assert linha['Qua 21/10 10h · a Nuvemshop falhou'].endswith('IGUAL à de ontem')
    qui = linha['Qui 22/10 12h · a Mariana marcou o toque 1 do carrinho A']
    assert 'Carrinho A: Aguardar intervalo' in qui                                         # marcou: espera o intervalo
    dom = linha['Dom 25/10 · domingo (não sai fila; o pendente espera)']
    assert 'Carrinho B: Encerrado sem contato' in dom and 'p1: Contatar' in dom            # saída explicada libera a vaga


def test_aviso_e_o_mesmo_toque_e_marcar_zera_o_aviso():
    pg, t, carrinhos = sim.montar_mundo(limite=10)
    sim.rodada(pg, t, carrinhos, '2026-10-19 10:00')
    sim.rodada(pg, t, carrinhos, '2026-10-20 10:00')
    aba = pg._ss.abas['Fila']
    q = sim.quadro(pg)['Carrinho A']
    assert q['aviso'] and q['toques'] == ''                                                # não avançou o toque
    assert aba.grade[(q['pos'], cp.COL['Próximo toque'] + 1)] == 1
    obs = aba.grade[(q['pos'], cp.COL['Observações'] + 1)]
    assert 'Estava na fila de ontem e não foi marcada: confira no WhatsApp antes de enviar' in obs
    sim.rodada(pg, t, carrinhos, '2026-10-21 10:00')
    assert aba.grade[(q['pos'], cp.COL['Próximo toque'] + 1)] == 1                         # dois dias sem marcar: ainda o toque 1
    aba.grade[(q['pos'], cp.COL['Toques já enviados'] + 1)] = 1
    aba.grade[(q['pos'], cp.COL['Último envio em'] + 1)] = '2026-10-21 11:00'
    sim.rodada(pg, t, carrinhos, '2026-10-21 12:00')
    assert aba.grade[(q['pos'], cp.COL['Próximo toque'] + 1)] == 2
    assert 'Estava na fila de ontem' not in str(aba.grade.get((q['pos'], cp.COL['Observações'] + 1), ''))


def test_fila_do_dia_seguinte_leva_os_mais_antigos_primeiro_dentro_de_cada_prioridade():
    pg, t, carrinhos = sim.montar_mundo(limite=1)
    sim.rodada(pg, t, carrinhos, '2026-10-19 10:00')
    q = sim.quadro(pg)
    assert q['Carrinho B']['situacao'] == 'Contatar'                                       # B é mais antigo que A
    assert q['Carrinho A']['situacao'] == 'Fica para amanhã' and q['v1']['situacao'] == 'Fica para amanhã'


# ----------------------------------------------------------------------------
# Saídas explicadas
# ----------------------------------------------------------------------------
def test_45_dias_sai_depois_de_30_dias_e_vip_sai_fora_da_janela_e_contam_como_nao_contatados():
    pg, t, carrinhos = sim.montar_mundo(limite=40)
    sim.rodada(pg, t, [], '2026-10-19 10:00')                    # sem carrinhos
    sim.rodada(pg, t, [], '2026-10-20 10:00')                    # p2 completa 45 dias na terça
    q = sim.quadro(pg)
    assert q['p1']['situacao'] == 'Contatar' and q['v1']['situacao'] == 'Contatar' and q['p2']['situacao'] == 'Contatar'
    sim.rodada(pg, t, [], '2026-11-21 10:00')                    # p1 e p2 passaram de 30 dias; v1 de 104 dias
    q = sim.quadro(pg)
    assert all(q[k]['situacao'] == 'Encerrado sem contato' for k in ('p1', 'p2', 'v1'))
    assert q['p1']['encerrado_em'] == '2026-11-21'
    resultados = {str(l[0]).strip(): l[1] for l in pg._ss.abas['Resultados'].get_all_values() if l}
    assert resultados['Não contatados (saíram da fila sem nenhum toque)'] == 3
    assert resultados['Não contatados · 45 dias'] == 2 and resultados['Não contatados · VIP'] == 1
    semana = {str(l[0]).strip(): l[1] for l in pg._ss.abas['resumo_semana'].get_all_values() if l}
    assert semana['Não contatados (saíram da fila sem toque)'] == 3
    # continuam no grupo sorteado (o teste mede quem foi sorteado, não só quem foi contatado)
    sorteados = rp.ler_sorteios(pg)
    assert sorteados['p1@exemplo.com'] == 'whatsapp' and sorteados['p2@exemplo.com'] == 'whatsapp'
    # e não voltam a ser sorteados nem contatados depois
    sim.rodada(pg, t, [], '2026-11-23 10:00')
    assert sim.quadro(pg)['p1']['situacao'] == 'Encerrado sem contato'
    assert len(pg._ss.abas['regua'].get_all_values()) == 3       # cabeçalho + 2 sorteios


def test_quem_comprou_antes_do_contato_nao_conta_como_nao_contatado():
    pg, t, _ = sim.montar_mundo(limite=40)
    sim.rodada(pg, t, [], '2026-10-19 10:00')
    nova = {'numero': '999', 'email': 'p1@exemplo.com', 'data': pd.Timestamp('2026-10-21 15:00'), 'valido': True, 'subtotal': 50.0,
            'desconto': 0.0, 'frete': 0.0, 'total': 50.0, 'cupom': None}
    t.pedidos = pd.concat([t.pedidos, pd.DataFrame([nova])], ignore_index=True)
    sim.rodada(pg, t, [], '2026-10-22 10:00')
    assert sim.quadro(pg)['p1']['situacao'] in ('Encerrado: já comprou', 'Recuperado')


# ----------------------------------------------------------------------------
# Contatos feitos à mão (lista de VIP de outubro)
# ----------------------------------------------------------------------------
def test_vip_ja_contatado_a_mao_nao_recebe_de_novo_e_conta_para_os_30_dias(tmp_path):
    pg, t, _ = sim.montar_mundo(limite=40)
    arquivo = tmp_path / 'vip.csv'
    arquivo.write_text('EMAIL;NOME;CIDADE\nv1@exemplo.com;Vera;Goiânia\np1@exemplo.com;Paula;Goiânia\n', encoding='utf-8')
    emails = cm.ler_emails_do_csv(str(arquivo))
    r = cm.registrar(pg, emails, '2026-10-10', 'VIP', 'lista manual')
    assert r == {'lidos': 2, 'novos': 2, 'ja_registrados': 0}
    assert cm.registrar(pg, emails, '2026-10-10', 'VIP')['novos'] == 0      # repetir não duplica
    aba = pg._ss.abas['contatos_manuais']
    assert [l[:3] for l in aba.get_all_values()[1:]] == [['v1@exemplo.com', '2026-10-10', 'VIP'], ['p1@exemplo.com', '2026-10-10', 'VIP']]
    assert all(len(l) <= 4 for l in aba.get_all_values())                   # nome e cidade da lista não vão para a planilha
    sim.rodada(pg, t, [], '2026-10-19 10:00')
    q = sim.quadro(pg)
    assert 'v1' not in q                                                    # VIP já recebido: não entra de novo no ciclo
    assert q['p1']['situacao'] == 'Aguardar 30 dias'                        # 45 dias: contatado há 9 dias, espera
    sim.rodada(pg, t, [], '2026-11-09 10:00')                               # 30 dias depois de 10/10
    assert sim.quadro(pg)['p1']['situacao'] in ('Contatar', 'Encerrado sem contato')


# ----------------------------------------------------------------------------
# Coletor e gravação
# ----------------------------------------------------------------------------
def test_coletor_busca_desde_a_ultima_rodada_que_deu_certo(tmp_path):
    falsa = APIDeMentira()
    api = na.NuvemshopAPI(Config(nuvemshop_store_id='123', nuvemshop_token='token-de-teste', nuvemshop_user_agent='Teste (t@exemplo.com)'),
                          sessao=falsa, dormir=lambda s: None)
    falsa.dados['orders'] = [pedido(0)]
    falsa.dados['customers'] = [cliente(0, 'a@exemplo.com')]
    armazem = na.Armazem(str(tmp_path))
    na.sincronizar(api, armazem, 'pedidos', agora=agora_fixo('2026-10-02T12:00:00+00:00'))
    na.sincronizar(api, armazem, 'clientes', agora=agora_fixo('2026-10-02T12:00:00+00:00'))
    # segunda rodada: pedidos baixa, clientes cai (503 em todas as tentativas)
    na.sincronizar(api, armazem, 'pedidos', agora=agora_fixo('2026-10-02T13:00:00+00:00'))
    falsa.respostas_forcadas = [503] * 5
    with pytest.raises(na.ErroAPI):
        na.sincronizar(api, armazem, 'clientes', agora=agora_fixo('2026-10-02T13:00:00+00:00'))
    estado = armazem.estado()
    assert estado['pedidos']['sincronizado_em'].startswith('2026-10-02T13:00')
    assert estado['clientes']['sincronizado_em'].startswith('2026-10-02T12:00')  # não avançou: nada se perde
    falsa.chamadas.clear()
    na.sincronizar(api, armazem, 'clientes', agora=agora_fixo('2026-10-02T14:00:00+00:00'))
    assert falsa.chamadas[0][1]['updated_at_min'] == '2026-10-02T11:50:00+0000'   # desde a última que deu certo (menos 10 min)


def test_falha_numa_aba_mantem_o_conteudo_antigo_e_a_proxima_rodada_recupera(config, mundo, monkeypatch):
    rodar_rotina(config, mundo)
    pedidos = mundo['planilha_falsa'].abas['pedidos']
    antes = [list(l) for l in pedidos.get_all_values()]
    rodada_antes = mundo['planilha_falsa'].abas['rodada'].get_all_values()
    mundo['falsa'].dados['orders'].append(pedido(9, atualizado='2026-10-03T10:00:00+0000', email='cliente1@exemplo.com'))

    original = pgm.PlanilhaGoogle.substituir

    def com_falha(self, titulo, df):
        if titulo == 'pedidos':
            raise RuntimeError('o Google recusou a gravação')
        return original(self, titulo, df)
    monkeypatch.setattr(pgm.PlanilhaGoogle, 'substituir', com_falha)
    with pytest.raises(rotina.ErroRotina) as erro:
        rodar_rotina(config, mundo)
    assert 'pedidos' in str(erro.value) and 'mantido' in str(erro.value)
    assert pedidos.get_all_values() == antes                                              # conteúdo antigo intacto
    assert mundo['planilha_falsa'].abas['rodada'].get_all_values() == rodada_antes        # não marcou rodada boa
    assert len(mundo['planilha_falsa'].abas['clientes'].get_all_values()) > 1             # as outras abas foram gravadas

    monkeypatch.setattr(pgm.PlanilhaGoogle, 'substituir', original)
    rodar_rotina(config, mundo)                                                           # a rodada seguinte recupera
    assert len(pedidos.get_all_values()) == len(antes) + 1
    assert mundo['planilha_falsa'].abas['rodada'].get_all_values()[0][:3] == ['ultima_rodada_ok', 'duracao_s', 'dia_de_fila']


class ErroDoGoogle(Exception):
    def __init__(self, status):
        super().__init__(f'erro {status}')
        self.response = type('R', (), {'status_code': status})()


def test_limite_de_uso_do_google_espera_e_tenta_de_novo_sem_perder_a_gravacao():
    esperas, chamadas = [], []

    def escrever():
        chamadas.append(1)
        if len(chamadas) < 3:
            raise ErroDoGoogle(429)
        return 'gravou'
    assert rotina.com_novas_tentativas(escrever, esperas.append) == 'gravou'
    assert len(chamadas) == 3 and esperas == [20, 45]


def test_erro_que_nao_e_de_limite_nao_fica_tentando_e_sobe_na_hora():
    esperas = []

    def escrever():
        raise ErroDoGoogle(400)
    with pytest.raises(ErroDoGoogle):
        rotina.com_novas_tentativas(escrever, esperas.append)
    assert esperas == []
    resumo = rotina._resumo_do_erro(ErroDoGoogle(400))
    assert 'detalhes omitidos do log público' in resumo
    assert 'erro 400' not in resumo


def test_nada_e_gravado_se_o_calculo_da_fila_falha(config, mundo, monkeypatch):
    rodar_rotina(config, mundo)
    antes = {t: [list(l) for l in a.get_all_values()] for t, a in mundo['planilha_falsa'].abas.items()}
    mundo['falsa'].dados['orders'].append(pedido(9, atualizado='2026-10-03T10:00:00+0000', email='cliente1@exemplo.com'))

    def falha(*a, **k):
        raise na.ErroAPI('A Nuvemshop respondeu 503 depois de 5 tentativas.')
    monkeypatch.setattr(cp, 'planejar_fila', falha)
    with pytest.raises(na.ErroAPI):
        rodar_rotina(config, mundo, carrinhos=True)
    depois = {t: [list(l) for l in a.get_all_values()] for t, a in mundo['planilha_falsa'].abas.items()}
    for aba, valores in antes.items():
        assert depois[aba] == valores, f'a aba {aba} mudou numa rodada que falhou antes de gravar'


# ----------------------------------------------------------------------------
# D-053: Respondeu com 0 toques vale para a trava de 30 dias, sem inventar envio
# ----------------------------------------------------------------------------
def test_respondeu_com_zero_toques_segura_o_vip_por_30_dias_sem_virar_envio():
    from tests.test_carrinhos import carrinho
    pg, t, carrinhos = sim.montar_mundo(limite=40)
    cart_vera = carrinho(id=3, email='v1@exemplo.com', fone='62999990005',
                         created_at='2026-10-17T14:00:00+0000', updated_at='2026-10-17T14:00:00+0000')
    todos = carrinhos + [cart_vera]
    sim.rodada(pg, t, todos, '2026-10-19 10:00')
    aba = pg._ss.abas['Fila']                                    # sem conversa, o carrinho tem prioridade e o VIP espera na fila
    linha_carrinho = next(pos for pos, l in enumerate(aba.get_all_values()[1:], start=2)
                          if l[cp.COL['Carrinho']] == '3')
    aba.grade[(linha_carrinho, cp.COL['Status'] + 1)] = 'Respondeu'           # a Mariana marcou que a cliente respondeu
    sim.rodada(pg, t, todos, '2026-10-19 12:00')
    vistas = pg._ss.abas['respostas_vistas'].get_all_values()
    assert len(vistas) == 2 and vistas[1][0] == 'v1@exemplo.com' and vistas[1][2].startswith('2026-10-19')
    # o VIP da mesma pessoa espera 30 dias a partir da resposta; o contador de toques não foi tocado
    linhas = {l[cp.COL['Origem']]: l for l in aba.get_all_values()[1:] if l[cp.COL['Email']] == 'v1@exemplo.com'}
    assert linhas['VIP'][cp.COL['Situação']] == 'Aguardar 30 dias'
    assert linhas['Carrinho'][cp.COL['Toques já enviados']] in ('', '0')
    assert linhas['VIP'][cp.COL['Próximo envio a partir de']].startswith('2026-11-18')
    # outra rodada não refaz a data nem duplica a linha
    sim.rodada(pg, t, todos, '2026-10-21 10:00')
    assert len(pg._ss.abas['respostas_vistas'].get_all_values()) == 2
    # quem NÃO respondeu não é segurado: p1 (45 dias) segue Contatar
    assert sim.quadro(pg)['p1']['situacao'] in ('Contatar', 'Fica para amanhã')
