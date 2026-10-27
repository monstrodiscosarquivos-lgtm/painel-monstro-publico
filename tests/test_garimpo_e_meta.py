"""Etapa 8: lista de garimpo (Google Forms + aba desejos) e públicos do Meta. Dados fictícios."""
import os
from datetime import date

import pandas as pd
import pytest

from painel_monstro import rotina
from painel_monstro.config import Config
from painel_monstro.saidas import carrinhos as c
from painel_monstro.saidas import carrinhos_planilha as cp
from painel_monstro.saidas import fila_unica as fu
from painel_monstro.saidas import garimpo, meta
from painel_monstro.saidas.planilha_google import PlanilhaGoogle
from tests.ajuda import cliente, dias_atras, pedido, tabelas
from tests.test_carrinhos import ApiFalsa
from tests.test_carrinhos_planilha import AbaFalsa, PlanilhaFalsa
from tests.test_fila_unica import AGORA_UTC, PARAMS, api_ok, loja_padrao

CAB_FORMULARIO = ['Carimbo de data/hora', 'Seu nome e WhatsApp com DDD', 'Artista ou banda', 'Qual disco você procura?']


# ----------------------------------------------------------------------------
# Garimpo
# ----------------------------------------------------------------------------
@pytest.mark.parametrize('texto,nome,fone', [
    ('Ana Souza 62 99999-0000', 'Ana Souza', '5562999990000'),
    ('(62) 99999-0001 Bruno', 'Bruno', '5562999990001'),
    ('+55 62 99999-0002', '', '5562999990002'),
    ('Só o nome', 'Só o nome', ''),
    ('', '', ''),
    ('Cida, 62999990003', 'Cida', '5562999990003'),
])
def test_separa_nome_e_whatsapp_do_formulario(texto, nome, fone):
    assert garimpo.separar_contato(texto) == (nome, fone)


def test_junta_formulario_e_aba_desejos():
    abas = {
        'Respostas ao formulário 1': [CAB_FORMULARIO,
                                      ['11/10/2026 14:30:12', 'Ana Souza 62 99999-0000', 'Iron Maiden', 'Powerslave'],
                                      ['', '', '', '']],
        'desejos': [['email', 'telefone', 'nome', 'desejo', 'data', 'status'],
                    ['b@exemplo.com', '62999990001', 'Beto', 'Caetano Veloso Transa', '2026-10-05', 'Avisado']],
        'Fila': [['Carrinho'], ['1']],
    }
    d = garimpo.juntar_desejos(abas)
    assert len(d) == 2 and list(d.columns) == garimpo.COLUNAS
    f = d[d['origem'] == 'formulario'].iloc[0]
    assert (f['nome'], f['telefone'], f['desejo']) == ('Ana Souza', '5562999990000', 'Iron Maiden Powerslave')
    m = d[d['origem'] == 'manual'].iloc[0]
    assert m['email'] == 'b@exemplo.com' and m['status'] == 'Avisado'


def test_aba_do_formulario_com_outro_nome_de_aba():
    assert garimpo.eh_aba_do_formulario('Respostas ao formulário 1') and garimpo.eh_aba_do_formulario('Form Responses 1')
    assert not garimpo.eh_aba_do_formulario('desejos') and not garimpo.eh_aba_do_formulario('Fila')


def desejo(contato='Ana 62 99999-0000', artista='Iron Maiden', disco='', data='2026-10-01 10:00'):
    d = garimpo.juntar_desejos({'Respostas ao formulário 1': [CAB_FORMULARIO, [data, contato, artista, disco]]})
    return d


def test_aviso_quando_chega_disco_do_artista_pedido_e_entra_na_fila_unica():
    t = tabelas([pedido(1, 'a@exemplo.com', dias_atras(2))])
    produtos = pd.DataFrame(loja_padrao(), columns=['url', 'nome', 'categorias', 'estoque', 'estoque_ilimitado', 'exibir', 'custo', 'id', 'criado_em'])
    linhas = fu.alertas_garimpo(desejo(), produtos, PARAMS, AGORA_UTC, {}, set(), api_ok())
    assert len(linhas) == 1
    l = linhas[0]
    assert l.origem == 'Garimpo' and l.modelo == 'ALERTA_GARIMPO' and l.situacao == 'Contatar'
    assert 'B (Iron Maiden)' in l.mensagem and 'Te aviso primeiro' in l.mensagem and '{' not in l.mensagem
    assert l.link_whatsapp.startswith('https://wa.me/5562999990000?text=') and l.carrinho.startswith('GAR-')


def test_disco_que_ja_estava_na_loja_antes_do_pedido_nao_avisa():
    produtos = pd.DataFrame(loja_padrao(), columns=['url', 'nome', 'categorias', 'estoque', 'estoque_ilimitado', 'exibir', 'custo', 'id', 'criado_em'])
    # o Iron Maiden entrou em 05/10; o pedido é de 09/10
    assert fu.alertas_garimpo(desejo(data='2026-10-09 10:00'), produtos, PARAMS, AGORA_UTC, {}, set(), api_ok()) == []


def test_um_pedido_gera_um_aviso_so_mesmo_com_outros_discos_do_mesmo_artista():
    base = loja_padrao() + [['lp-b2', 'LP Iron Maiden: B2 - (1984) - (Vinil Usado)', 'LP > Usado > Metal', 1, False, True, 10.0, 505, '2026-10-06T10:00:00+0000']]
    produtos = pd.DataFrame(base, columns=['url', 'nome', 'categorias', 'estoque', 'estoque_ilimitado', 'exibir', 'custo', 'id', 'criado_em'])
    api = ApiFalsa({501: api_ok().produtos[501], 502: api_ok().produtos[502], 503: api_ok().produtos[503], 505: api_ok().produtos[502]})
    primeira = fu.alertas_garimpo(desejo(), produtos, PARAMS, AGORA_UTC, {}, set(), api)
    assert len(primeira) == 1
    # a Mariana marcou o toque desse aviso: o pedido está atendido e outro disco do artista não gera outro aviso
    ja = {primeira[0].carrinho: {'toques': 1, 'status': ''}}
    assert fu.alertas_garimpo(desejo(), produtos, PARAMS, AGORA_UTC, ja, set(), api) == []


def test_pedido_sem_telefone_aparece_para_a_mariana_achar_pelo_nome():
    produtos = pd.DataFrame(loja_padrao(), columns=['url', 'nome', 'categorias', 'estoque', 'estoque_ilimitado', 'exibir', 'custo', 'id', 'criado_em'])
    linhas = fu.alertas_garimpo(desejo(contato='Dona Cida'), produtos, PARAMS, AGORA_UTC, {}, set(), api_ok())
    assert len(linhas) == 1 and linhas[0].situacao == 'Telefone inválido' and 'pelo nome' in linhas[0].observacoes


def test_cliente_bloqueado_nao_recebe_aviso():
    produtos = pd.DataFrame(loja_padrao(), columns=['url', 'nome', 'categorias', 'estoque', 'estoque_ilimitado', 'exibir', 'custo', 'id', 'criado_em'])
    assert fu.alertas_garimpo(desejo(), produtos, PARAMS, AGORA_UTC, {}, {'5562999990000'}, api_ok()) == []


class PlanilhaComAbas(PlanilhaFalsa):
    def worksheets(self):
        return list(self.abas.values())


def test_ler_desejos_junta_a_aba_desejos_e_a_do_formulario():
    ss = PlanilhaComAbas()
    for nome, linhas in {'desejos': [['email', 'telefone', 'nome', 'desejo', 'data', 'status'], ['', '62999990001', 'Beto', 'Caetano Transa', '2026-10-05', '']],
                         'Respostas ao formulário 1': [CAB_FORMULARIO, ['11/10/2026 10:00:00', 'Ana 62 99999-0000', 'Pink Floyd', 'Animals']],
                         'Fila': [['Carrinho']]}.items():
        aba = ss.add_worksheet(nome, 10, 10)
        for i, l in enumerate(linhas, start=1):
            for j, v in enumerate(l, start=1):
                if v != '':
                    aba.grade[(i, j)] = v
    d = cp.ler_desejos(PlanilhaGoogle(ss))
    assert sorted(d['origem']) == ['formulario', 'manual'] and len(d) == 2


# ----------------------------------------------------------------------------
# Públicos do Meta
# ----------------------------------------------------------------------------
HOJE = pd.Timestamp('2026-10-10')


def base_meta():
    pedidos = [
        pedido(1, 'sumiu@exemplo.com', dias_atras(250)), pedido(2, 'quase@exemplo.com', dias_atras(170)),
        pedido(3, 'recente@exemplo.com', dias_atras(30)), pedido(4, 'nao.aceita@exemplo.com', dias_atras(300)),
        pedido(5, 'sumiu2@exemplo.com', dias_atras(400)), pedido(6, 'hoje@exemplo.com', dias_atras(1)),
        pedido(7, 'sai@exemplo.com', dias_atras(220)),
    ]
    clientes = [cliente(e) for e in ('sumiu@exemplo.com', 'quase@exemplo.com', 'recente@exemplo.com', 'sumiu2@exemplo.com', 'hoje@exemplo.com', 'sai@exemplo.com')]
    clientes.append(cliente('nao.aceita@exemplo.com', aceita=False))
    for cl in clientes:
        cl['telefone'] = '62999990000'
    return tabelas(pedidos, clientes=clientes)


def test_sumiu_180_so_quem_aceita_marketing_e_nao_se_descadastrou():
    listas = meta.montar(base_meta(), HOJE, nao_abrem=set(), descadastrados={'sai@exemplo.com'})
    assert sorted(listas['sumiu_180']['email']) == ['sumiu2@exemplo.com', 'sumiu@exemplo.com']
    assert list(listas['sumiu_180'].columns) == ['email', 'phone', 'fn', 'ct']
    assert (listas['sumiu_180']['phone'] == '5562999990000').all()


def test_compradores_dos_ultimos_180_dias_para_excluir():
    listas = meta.montar(base_meta(), HOJE)
    assert sorted(listas['compradores_180']['email']) == ['hoje@exemplo.com', 'quase@exemplo.com', 'recente@exemplo.com']


def test_nao_abre_vem_do_segmento_do_brevo_sem_descadastrados_e_sem_quem_nao_aceita():
    segmento = {'sumiu@exemplo.com', 'nao.aceita@exemplo.com', 'so.no.brevo@exemplo.com', 'sai@exemplo.com', 'invalido'}
    listas = meta.montar(base_meta(), HOJE, nao_abrem=segmento, descadastrados={'sai@exemplo.com'})
    assert sorted(listas['nao_abre']['email']) == ['so.no.brevo@exemplo.com', 'sumiu@exemplo.com']
    assert len(meta.montar(base_meta(), HOJE, nao_abrem=None)['nao_abre']) == 0   # segmento não configurado


def test_resumo_avisa_quando_falta_o_segmento():
    listas = meta.montar(base_meta(), HOJE, nao_abrem=None)
    r = meta.resumo(listas, '2026-10', '2026-10-10 10:00', segmento_configurado=False)
    assert 'aviso' in set(r['indicador'])
    r2 = meta.resumo(listas, '2026-10', '2026-10-10 10:00', segmento_configurado=True)
    assert 'aviso' not in set(r2['indicador'])


def test_csv_vai_para_pasta_fora_do_git(tmp_path):
    listas = meta.montar(base_meta(), HOJE)
    caminhos = meta.gravar_csv(listas, '2026-10', raiz=str(tmp_path))
    assert len(caminhos) == 3 and all(os.path.exists(p) and os.sep + 'dados' + os.sep + 'meta' + os.sep in p for p in caminhos)
    ignorado = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.gitignore'), encoding='utf-8').read()
    assert 'dados/' in ignorado


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


def test_rotina_monta_os_publicos_uma_vez_por_mes(monkeypatch):
    agora = pd.Timestamp('2026-10-10 10:00', tz='America/Sao_Paulo')
    monkeypatch.setattr(rotina.pd.Timestamp, 'now', classmethod(lambda cls, tz=None: agora))
    t = base_meta()
    config = Config()
    paginas = rotina.passo_meta(config, PlanilhaMinima({}), t)
    assert [n for n, _ in paginas] == ['meta_sumiu_180', 'meta_nao_abre', 'meta_compradores_180', 'meta_resumo']
    resumo = dict(paginas[-1][1].values.tolist())
    assert resumo['mes'] == '2026-10' and 'aviso' in resumo
    # mesmo mês e mesmo segmento: não refaz
    feito = [['indicador', 'valor'], ['mes', '2026-10'], ['segmento', '']]
    assert rotina.passo_meta(config, PlanilhaMinima({'meta_resumo': feito}), t) == []
    # mês seguinte: refaz
    outro = [['indicador', 'valor'], ['mes', '2026-09'], ['segmento', '']]
    assert len(rotina.passo_meta(config, PlanilhaMinima({'meta_resumo': outro}), t)) == 4


# ----------------------------------------------------------------------------
# Formato pedido (LP, CD...): pergunta "Formato" do formulário ou palavra no próprio pedido
# ----------------------------------------------------------------------------
COLS_PRODUTOS = ['url', 'nome', 'categorias', 'estoque', 'estoque_ilimitado', 'exibir', 'custo', 'id', 'criado_em']


def _loja_com_cd():
    base = loja_padrao() + [['cd-b', 'CD Iron Maiden - B (cd usado)', 'CD > Usado > Metal', 1, False, True, 10.0, 506, '2026-10-06T10:00:00+0000']]
    return pd.DataFrame(base, columns=COLS_PRODUTOS)


def _api_com_cd():
    a = api_ok()
    return ApiFalsa({**a.produtos, 506: a.produtos[502]})


def _pedido_com_formato(formato, disco=''):
    cab = CAB_FORMULARIO + ['Formato']
    return garimpo.juntar_desejos({'Respostas ao formulário 1': [cab, ['2026-10-01 10:00', 'Ana 62 99999-0000', 'Iron Maiden', disco, formato]]})


@pytest.mark.parametrize('formato,disco,esperado', [
    ('CD', '', 'cd-b'), ('LP (vinil)', '', 'lp-b'), ('Qualquer formato', 'CD', 'lp-b'),
    ('', 'CD B', 'cd-b'), ('', 'vinil', 'lp-b'), ('', '', 'lp-b')])
def test_formato_do_pedido_escolhe_lp_ou_cd(formato, disco, esperado):
    linhas = fu.alertas_garimpo(_pedido_com_formato(formato, disco), _loja_com_cd(), PARAMS, AGORA_UTC, {}, set(), _api_com_cd())
    assert len(linhas) == 1 and linhas[0].link.endswith(f'/produtos/{esperado}/')


def test_pedido_de_cd_nao_avisa_quando_so_chega_lp():
    linhas = fu.alertas_garimpo(_pedido_com_formato('CD'), pd.DataFrame(loja_padrao(), columns=COLS_PRODUTOS), PARAMS, AGORA_UTC, {}, set(), api_ok())
    assert linhas == []


def test_formato_do_produto_e_do_pedido():
    assert garimpo.formato_do_produto('Cd Helloween - Chameleon (CD Usado)') == 'cd'
    assert garimpo.formato_do_produto('LP Violator - Unholy Retribution') == 'lp'
    assert garimpo.formato_do_produto('Camiseta Monstro') == 'camiseta'
    assert garimpo.formato_do_pedido('', 'CD Jupiter Apple - Uma Tarde na Fruteira') == 'cd'
    assert garimpo.formato_do_pedido('Fita K7', '') == 'k7'
    assert garimpo.formato_do_pedido('Qualquer formato', 'LP Abbey Road') == ''


def test_nome_e_whatsapp_em_perguntas_separadas_e_respostas_antigas_juntas():
    cab = ['Carimbo de data/hora', 'Seu nome e WhatsApp com DDD', 'Artista ou banda', 'Qual disco você procura?', 'Formato',
           'Seu nome', 'Seu WhatsApp com DDD']
    d = garimpo.juntar_desejos({'Respostas ao formulário 1': [cab,
        ['01/10/2026 10:00:00', 'Cliente Ficticio Um (62) 99999-0007', 'Júpiter Maçã', 'Uma Tarde na Fruteira', 'CD'],
        ['02/10/2026 10:00:00', '', 'Violator', 'Unholy Retribution', 'CD', 'Cliente Ficticio Dois', '(62) 99999-0008']]})
    assert d[['nome', 'telefone', 'formato']].values.tolist() == [['Cliente Ficticio Um', '5562999990007', 'CD'],
                                                                  ['Cliente Ficticio Dois', '5562999990008', 'CD']]


def test_disco_que_voltou_ao_estoque_depois_do_pedido_avisa():
    base = [['lp-b', 'LP Iron Maiden: B - (1982) - (Vinil Usado)', 'LP > Usado > Metal', 1, False, True, 10.0, 502, '2022-01-05T10:00:00+0000', '2026-10-10']]
    produtos = pd.DataFrame(base, columns=COLS_PRODUTOS + ['no_estoque_desde'])
    assert len(fu.alertas_garimpo(desejo(data='2026-10-09 10:00'), produtos, PARAMS, AGORA_UTC, {}, set(), api_ok())) == 1
    produtos.loc[0, 'no_estoque_desde'] = '2026-10-08'   # já estava em estoque quando pediu
    assert fu.alertas_garimpo(desejo(data='2026-10-09 10:00'), produtos, PARAMS, AGORA_UTC, {}, set(), api_ok()) == []


def test_camiseta_nao_avisa_disco_e_disco_nao_avisa_camiseta():
    from painel_monstro.saidas.garimpo import formato_do_pedido, formato_do_produto
    assert formato_do_pedido('Camiseta', 'Ramones') == 'camiseta'
    assert formato_do_pedido('', 'camiseta do Ramones') == 'camiseta'
    assert formato_do_produto('Camiseta Ramones - Logo (P)') == 'camiseta'
    assert formato_do_produto('LP Ramones - Ramones (Vinil Usado)') == 'lp'


def test_palavras_do_desejo_d085():
    from painel_monstro.saidas.garimpo import palavras_do_desejo

    def casa(desejo, nome):
        import unicodedata
        n = unicodedata.normalize('NFKD', nome).encode('ascii', 'ignore').decode().lower()
        return all(w in n for w in palavras_do_desejo(desejo))

    pedido = 'Jon Bon Jovi LP Jon Bon Jovi: Blaze Of Glory / Young Guns II (1990) (Vinil usado)'
    assert casa(pedido, 'LP Jon Bon Jovi - Blaze of Glory (1990) - (Vinil Usado)')
    graf = 'Graforréia Xilarmônica LP Graforréia Xilarmônica - Coisa de Louco II (Vinil Vermelho Splatter) (Série Ouro)'
    assert not casa(graf, 'LP Graforréia Xilarmônica - Coisa de Louco II (Azul Splatter)')
    assert casa(graf, 'LP Graforréia Xilarmônica - Coisa de Louco II (Vinil Vermelho Splatter) (Série Ouro)')
    assert not casa('Nenhum de Nós 1992', 'LP Nenhum de Nós - Cardume (1989) - (Vinil Usado)')
    assert not casa('Júpiter Maçã Uma Tarde na Fruteira (Versão Espanha)', 'LP Júpiter Maçã - Uma Tarde na Fruteira (Versão Brasil)')
    assert casa('rita lee', 'LP Rita Lee e Roberto de Carvalho 1990 (Novo/Lacrado)')
