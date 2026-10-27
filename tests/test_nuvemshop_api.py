"""Testes do coletor da API da Nuvemshop. Nenhuma chamada real: usa uma API de mentira e dados fictícios."""
import json
import os
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote, urlparse

import pandas as pd
import pytest
import requests

from painel_monstro.config import Config
from painel_monstro.coletor import nuvemshop_api as na

TOKEN = 'token-secreto-de-teste-123'
LOJA = '555'


class Resposta:
    def __init__(self, status=200, corpo=None, cabecalhos=None):
        self.status_code = status
        self._corpo = corpo if corpo is not None else []
        self.headers = cabecalhos or {}

    def json(self):
        return self._corpo


class APIDeMentira:
    """Imita a parte da Nuvemshop que o coletor usa: GET com page, per_page, updated_at_min e Link."""

    def __init__(self):
        self.dados = {'orders': [], 'customers': [], 'products': []}
        self.chamadas = []  # (url, params, cabecalhos)
        self.respostas_forcadas = []  # status para devolver antes de responder de verdade
        self.livres = 39

    def get(self, url, headers=None, params=None, timeout=None):
        self.chamadas.append((url, dict(params) if params else None, dict(headers or {})))
        if self.respostas_forcadas:
            return Resposta(self.respostas_forcadas.pop(0), {'erro': 'x'}, {'x-rate-limit-remaining': '0', 'x-rate-limit-reset': '1000'})
        caminho = urlparse(url).path.split('/')[-1]
        consulta = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        consulta.update(params or {})
        registros = self.dados[caminho]
        minimo = consulta.get('updated_at_min')
        if minimo:
            limite = datetime.strptime(minimo, '%Y-%m-%dT%H:%M:%S%z')
            registros = [r for r in registros if datetime.strptime(r['updated_at'], '%Y-%m-%dT%H:%M:%S%z') >= limite]
        if not registros:
            return Resposta(404, {'code': 404})
        por_pagina, pagina = int(consulta.get('per_page', 30)), int(consulta.get('page', 1))
        fatia = registros[(pagina - 1) * por_pagina:pagina * por_pagina]
        cab = {'x-total-count': str(len(registros)), 'x-rate-limit-remaining': str(self.livres), 'x-rate-limit-reset': '1000'}
        if pagina * por_pagina < len(registros):
            cab['Link'] = f'<https://api.nuvemshop.com.br/2025-03/{LOJA}/{caminho}?per_page={por_pagina}&page={pagina + 1}>; rel="next"'
            if minimo:
                cab['Link'] = cab['Link'].replace('>;', f'&updated_at_min={quote(minimo)}>;')
        return Resposta(200, fatia, cab)


def pedido(i, atualizado='2026-10-01T10:00:00+0000', pagamento='paid', email='ana@exemplo.com', **extra):
    base = {
        'id': 1000 + i, 'number': 100 + i, 'created_at': '2026-10-01T13:17:36+0000', 'updated_at': atualizado,
        'paid_at': None, 'contact_email': email, 'status': 'open', 'payment_status': pagamento, 'shipping_status': 'shipped',
        'subtotal': '100.00', 'discount': '10.00', 'total': '115.00', 'gateway_name': 'Nuvem Pago',
        'payment_details': {'method': 'pix'}, 'coupon': [{'code': 'VOLTA10OUT', 'type': 'percentage', 'value': '10', 'id': 9}],
        'fulfillments': [{'shipping': {'option': {'name': 'Correios PAC'}}}],
        'products': [{'product_id': 1, 'variant_id': 2, 'name': 'Disco A', 'price': '60.00', 'quantity': 1, 'sku': 'A1'},
                     {'product_id': 3, 'variant_id': 4, 'name': 'Disco B', 'price': '40.00', 'quantity': 1, 'sku': ''}],
        # campos que nunca devem ser guardados
        'contact_identification': '111.111.111-11', 'billing_address': 'Rua Fictícia 1', 'client_details': {'browser_ip': '1.2.3.4'},
    }
    base.update(extra)
    return base


def cliente(i, email, marketing=True):
    return {'id': 500 + i, 'name': f'maria da silva {i}', 'email': email, 'phone': '62999990000', 'identification': '222',
            'default_address': {'city': 'Goiânia', 'province': 'Goiás', 'address': 'Rua Fictícia 2'},
            'total_spent': '115.00', 'accepts_marketing': marketing, 'accepts_marketing_updated_at': '2026-01-01T00:00:00+0000',
            'active': True, 'created_at': '2026-01-01T00:00:00+0000', 'updated_at': '2026-10-01T10:00:00+0000'}


def produto(i, estoque=2, gerencia=True, publicado=True):
    return {'id': 700 + i, 'name': {'pt': f'Disco {i}'}, 'handle': {'pt': f'disco-{i}'}, 'brand': 'Selo', 'published': publicado,
            'categories': [{'name': {'pt': 'Jazz'}}], 'created_at': '2026-01-01T00:00:00+0000', 'updated_at': '2026-10-01T10:00:00+0000',
            'variants': [{'price': '50.00', 'promotional_price': None, 'stock': estoque, 'stock_management': gerencia, 'sku': f'D{i}', 'cost': '20.00'}]}


@pytest.fixture
def config():
    return Config(nuvemshop_store_id=LOJA, nuvemshop_token=TOKEN, nuvemshop_user_agent='Painel Teste (teste@exemplo.com)')


@pytest.fixture
def falsa():
    return APIDeMentira()


@pytest.fixture
def esperas():
    return []


@pytest.fixture
def api(config, falsa, esperas):
    return na.NuvemshopAPI(config, sessao=falsa, dormir=esperas.append)


def agora_fixo(texto):
    return lambda: datetime.fromisoformat(texto)


# ---------------------------------------------------------------- cliente HTTP
def test_envia_token_e_user_agent_so_no_cabecalho(api, falsa):
    falsa.dados['orders'] = [pedido(1)]
    list(api.listar('orders'))
    url, params, cab = falsa.chamadas[0]
    assert cab['Authorization'] == f'Bearer {TOKEN}'
    assert cab['User-Agent'].startswith('Painel Teste')
    assert TOKEN not in url and TOKEN not in str(params)


def test_segue_as_paginas_pelo_cabecalho_link(api, falsa):
    falsa.dados['orders'] = [pedido(i) for i in range(5)]
    ids = [r['id'] for r in api.listar('orders', per_page=2)]
    assert ids == [1000, 1001, 1002, 1003, 1004]
    assert len(falsa.chamadas) == 3


def test_lista_vazia_quando_a_api_responde_404(api):
    assert list(api.listar('orders')) == []
    assert api.total('orders') == 0


def test_429_espera_e_tenta_de_novo(api, falsa, esperas):
    falsa.dados['orders'] = [pedido(1)]
    falsa.respostas_forcadas = [429, 429]
    assert len(list(api.listar('orders'))) == 1
    assert len(esperas) == 2 and all(e >= 1 for e in esperas)


def test_desiste_depois_de_varias_tentativas(api, falsa):
    falsa.respostas_forcadas = [500] * 10
    with pytest.raises(na.ErroAPI, match='500'):
        list(api.listar('orders'))


def test_balde_quase_cheio_faz_esperar(api, falsa, esperas):
    falsa.dados['orders'] = [pedido(i) for i in range(4)]
    falsa.livres = 1
    list(api.listar('orders', per_page=2))
    assert esperas and esperas[0] >= 0.6


def test_balde_com_folga_nao_espera(api, falsa, esperas):
    falsa.dados['orders'] = [pedido(i) for i in range(4)]
    list(api.listar('orders', per_page=2))
    assert esperas == []


def test_erro_de_acesso_nao_vaza_o_token(api, falsa):
    falsa.respostas_forcadas = [401]
    with pytest.raises(na.ErroAPI) as erro:
        list(api.listar('orders'))
    assert TOKEN not in str(erro.value)
    assert 'token' in str(erro.value).lower()


def test_erro_de_rede_nao_vaza_o_token(config, esperas):
    class SemRede:
        def get(self, *a, **k):
            raise requests.ConnectionError(f'falhou com Bearer {TOKEN}')

    api = na.NuvemshopAPI(config, sessao=SemRede(), dormir=esperas.append, max_tentativas=2)
    with pytest.raises(na.ErroAPI) as erro:
        list(api.listar('orders'))
    assert TOKEN not in str(erro.value) and TOKEN not in repr(erro.value.__cause__)


def test_so_le_dados_da_loja(api):
    # O cliente só chama .get da sessão; a API de mentira nem tem outros métodos.
    metodos = [m for m in ('post', 'put', 'patch', 'delete') if hasattr(api._sessao, m)]
    assert metodos == []
    assert not any(n.startswith(('criar', 'apagar', 'atualizar', 'enviar')) for n in dir(na.NuvemshopAPI))


def test_exige_credenciais():
    with pytest.raises(na.ErroAPI, match='NUVEMSHOP_TOKEN'):
        na.NuvemshopAPI(Config())


def test_token_nao_aparece_no_repr_da_configuracao(config):
    assert TOKEN not in repr(config)


# ---------------------------------------------------------------- sincronização
def test_primeira_execucao_baixa_tudo_e_guarda_so_o_necessario(api, falsa, tmp_path):
    falsa.dados['orders'] = [pedido(i) for i in range(3)]
    armazem = na.Armazem(str(tmp_path))
    r = na.sincronizar(api, armazem, 'pedidos', agora=agora_fixo('2026-10-02T12:00:00+00:00'))
    assert r == {'novos': 3, 'atualizados': 0, 'total': 3, 'modo': 'completo'}
    assert 'updated_at_min' not in falsa.chamadas[0][1]
    guardado = (tmp_path / 'pedidos.json').read_text(encoding='utf-8')
    for proibido in ('111.111.111-11', 'Rua Fictícia', '1.2.3.4', 'contact_identification', 'billing_address'):
        assert proibido not in guardado
    assert armazem.estado()['pedidos']['sincronizado_em'].startswith('2026-10-02T12:00:00')


def test_segunda_execucao_baixa_so_o_que_mudou(api, falsa, tmp_path):
    falsa.dados['orders'] = [pedido(0), pedido(1)]
    armazem = na.Armazem(str(tmp_path))
    na.sincronizar(api, armazem, 'pedidos', agora=agora_fixo('2026-10-02T12:00:00+00:00'))

    falsa.dados['orders'][0] = pedido(0, atualizado='2026-10-02T11:55:00+0000', pagamento='refunded')  # mudou
    falsa.dados['orders'].append(pedido(2, atualizado='2026-10-02T11:58:00+0000'))  # novo
    falsa.chamadas.clear()
    r = na.sincronizar(api, armazem, 'pedidos', agora=agora_fixo('2026-10-02T13:00:00+00:00'))

    assert (r['modo'], r['novos'], r['atualizados'], r['total']) == ('incremental', 1, 1, 3)
    assert falsa.chamadas[0][1]['updated_at_min'] == '2026-10-02T11:50:00+0000'  # última sincronização menos 10 min
    assert {x['id']: x['payment_status'] for x in armazem.registros('pedidos').values()}[1000] == 'refunded'


def test_incremental_sem_novidade_nao_da_erro(api, falsa, tmp_path):
    falsa.dados['orders'] = [pedido(0)]
    armazem = na.Armazem(str(tmp_path))
    na.sincronizar(api, armazem, 'pedidos', agora=agora_fixo('2026-10-02T12:00:00+00:00'))
    r = na.sincronizar(api, armazem, 'pedidos', agora=agora_fixo('2026-10-03T12:00:00+00:00'))
    assert (r['modo'], r['novos'], r['atualizados'], r['total']) == ('incremental', 0, 0, 1)


def test_registro_apagado_na_loja_refaz_o_download_completo(api, falsa, tmp_path):
    falsa.dados['customers'] = [cliente(1, 'a@x.com'), cliente(2, 'b@x.com')]
    armazem = na.Armazem(str(tmp_path))
    na.sincronizar(api, armazem, 'clientes', agora=agora_fixo('2026-10-02T12:00:00+00:00'))
    falsa.dados['customers'] = [cliente(1, 'a@x.com')]  # b foi apagado
    r = na.sincronizar(api, armazem, 'clientes', agora=agora_fixo('2026-10-03T12:00:00+00:00'))
    assert r['modo'] == 'completo' and r['total'] == 1
    assert list(armazem.registros('clientes')) == ['501']


def test_download_completo_vazio_nao_apaga_o_que_ja_existe(api, falsa, tmp_path):
    falsa.dados['orders'] = [pedido(0)]
    armazem = na.Armazem(str(tmp_path))
    na.sincronizar(api, armazem, 'pedidos', agora=agora_fixo('2026-10-02T12:00:00+00:00'))
    falsa.dados['orders'] = []
    with pytest.raises(na.ErroAPI, match='mantidos'):
        na.sincronizar(api, armazem, 'pedidos', completo=True)
    assert len(armazem.registros('pedidos')) == 1


def test_acima_do_limite_de_consulta_avisa(api, falsa):
    falsa.dados['orders'] = [pedido(0)]
    original = falsa.get

    def com_total_gigante(*a, **k):
        r = original(*a, **k)
        r.headers['x-total-count'] = '10001'
        return r

    falsa.get = com_total_gigante
    with pytest.raises(na.ErroAPI, match='dividir por período'):
        list(api.listar('orders'))


# ---------------------------------------------------------------- tabelas
@pytest.fixture
def tabelas():
    pedidos = [na._enxugar_pedido(p) for p in (
        pedido(1, pagamento='paid'),
        pedido(2, pagamento='partially_refunded', created_at='2026-10-02T02:30:00+0000'),
        pedido(3, pagamento='pending', email='bruno@exemplo.com'),
        pedido(4, pagamento='refunded', email='  CARLA@Exemplo.com '),
    )]
    clientes = [na._enxugar_cliente(c) for c in (cliente(1, 'ana@exemplo.com'), cliente(2, 'bruno@exemplo.com', marketing=False))]
    produtos = [na._enxugar_produto(p) for p in (produto(1), produto(2, gerencia=False, estoque=None), produto(3, estoque=0, publicado=False))]
    return na.montar_tabelas(pedidos, clientes, produtos)


def test_pedidos_validos_sao_paga_ou_parcialmente_estornada(tabelas):
    p = tabelas.pedidos.set_index('numero')
    assert p['valido'].to_dict() == {'101': True, '102': True, '103': False, '104': False}
    assert p.loc['101', 'status_pagamento'] == 'Confirmado'
    assert p.loc['102', 'status_pagamento'] == 'Parcialmente estornado'
    assert p.loc['104', 'status_pagamento'] == 'Estornado'


def test_pedido_pago_mas_cancelado_nao_conta():
    pedidos = [na._enxugar_pedido(p) for p in (pedido(1, pagamento='paid', status='cancelled'), pedido(2, pagamento='paid', status='closed'))]
    t = na.montar_tabelas(pedidos, [na._enxugar_cliente(cliente(1, 'ana@exemplo.com'))], [na._enxugar_produto(produto(1))])
    assert t.pedidos.set_index('numero')['valido'].to_dict() == {'101': False, '102': True}
    assert t.itens.groupby('numero')['valido'].any().to_dict() == {'101': False, '102': True}
    assert t.clientes.iloc[0]['n_compras'] == 1


def test_itens_e_produtos_guardam_o_id_do_produto(tabelas):
    assert set(tabelas.itens['produto_id']) == {1, 3}
    assert list(tabelas.produtos['id']) == [701, 702, 703]


def test_pedidos_valores_cupom_e_email(tabelas):
    p = tabelas.pedidos.set_index('numero').loc['101']
    assert (p['subtotal'], p['desconto'], p['total']) == (100.0, 10.0, 115.0)
    assert p['frete'] == 25.0  # 115 - 100 + 10
    assert p['cupom'] == 'VOLTA10OUT'
    assert p['forma_pagamento'] == 'pix' and p['forma_entrega'] == 'Correios PAC'
    assert tabelas.pedidos.set_index('numero').loc['104', 'email'] == 'carla@exemplo.com'


def test_datas_vao_para_o_horario_de_brasilia(tabelas):
    p = tabelas.pedidos.set_index('numero')
    assert p.loc['101', 'data'] == pd.Timestamp('2026-10-01 10:17:36')  # 13:17 UTC
    assert p.loc['102', 'data'] == pd.Timestamp('2026-10-01 23:30:00')  # virou o dia anterior


def test_itens_um_por_produto_do_pedido(tabelas):
    i = tabelas.itens
    assert len(i) == 8
    primeiro = i[i['numero'] == '101'].iloc[0]
    assert (primeiro['produto'], primeiro['valor'], primeiro['quantidade'], primeiro['sku']) == ('Disco A', 60.0, 1, 'A1')
    assert pd.isna(i[i['numero'] == '101'].iloc[1]['sku'])
    assert bool(i[i['numero'] == '103'].iloc[0]['valido']) is False


def test_clientes_com_compras_calculadas_dos_pedidos_pagos(tabelas):
    c = tabelas.clientes.set_index('email')
    ana = c.loc['ana@exemplo.com']
    assert ana['n_compras'] == 2  # pedidos 101 e 102 (o 102 foi no dia 01/10, 23h30)
    assert ana['ultima_compra'] == pd.Timestamp('2026-10-01')
    assert ana['primeiro_nome'] == 'Maria' and ana['cidade'] == 'Goiânia'
    assert c.loc['bruno@exemplo.com', 'n_compras'] == 0 and pd.isna(c.loc['bruno@exemplo.com', 'ultima_compra'])
    assert bool(ana['aceita_marketing']) is True and bool(c.loc['bruno@exemplo.com', 'aceita_marketing']) is False


def test_produtos_estoque_ilimitado_e_visibilidade(tabelas):
    p = tabelas.produtos.set_index('url')
    assert p.loc['disco-1', 'estoque'] == 2 and not p.loc['disco-1', 'estoque_ilimitado']
    assert pd.isna(p.loc['disco-2', 'estoque']) and p.loc['disco-2', 'estoque_ilimitado']
    assert p.loc['disco-3', 'estoque'] == 0 and not p.loc['disco-3', 'exibir']
    assert p.loc['disco-1', 'categorias'] == 'Jazz' and p.loc['disco-1', 'custo'] == 20.0


def test_tabelas_da_api_tem_as_mesmas_colunas_das_planilhas(tabelas):
    from painel_monstro.coletor import planilhas_csv as pc
    vazio = lambda colunas: pd.DataFrame({c: pd.Series([], dtype=str) for c in colunas})  # noqa: E731
    csv = pc.montar_tabelas({
        'vendas': vazio(['Número do Pedido', 'E-mail', 'Data', 'Status do Pedido', 'Status do Pagamento', 'Subtotal', 'Desconto',
                         'Valor do Frete', 'Total', 'Taxas', 'Total líquido', 'Cupom de Desconto', 'Forma de Pagamento',
                         'Forma de Entrega', 'Nome do Produto', 'Valor do Produto', 'Quantidade Comprada', 'SKU']),
        'clientes': vazio(['E-mail', 'Nome completo', 'Telefone de Contato', 'Cidade', 'Estado', 'Total Consumido (BRL)',
                           'Número de Compras', 'Última Compra', 'Marketing', 'Inscrição para newsletter']),
        'produtos': vazio(['Identificador URL', 'Nome', 'Categorias', 'Preço', 'Preço promocional', 'Estoque', 'SKU',
                           'Exibir na loja', 'Marca', 'Custo']),
    })
    for nome in ('clientes', 'pedidos', 'itens', 'produtos'):
        assert list(getattr(tabelas, nome).columns) == list(getattr(csv, nome).columns), nome


def test_coletar_ponta_a_ponta(config, falsa, esperas, tmp_path):
    falsa.dados['orders'] = [pedido(1)]
    falsa.dados['customers'] = [cliente(1, 'ana@exemplo.com')]
    falsa.dados['products'] = [produto(1)]
    api = na.NuvemshopAPI(config, sessao=falsa, dormir=esperas.append)
    t, resumo = na.coletar(config, pasta=str(tmp_path), api=api)
    assert {k: v['total'] for k, v in resumo.items()} == {'pedidos': 1, 'clientes': 1, 'produtos': 1}
    assert len(t.pedidos) == 1 and len(t.clientes) == 1 and len(t.produtos) == 1
    assert sorted(os.listdir(tmp_path)) == ['clientes.json', 'estado.json', 'pedidos.json', 'produtos.json']
    assert TOKEN not in ''.join((tmp_path / f).read_text(encoding='utf-8') for f in os.listdir(tmp_path))
    json.loads((tmp_path / 'estado.json').read_text(encoding='utf-8'))
