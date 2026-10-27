"""Testes do módulo de carrinho abandonado, com dados fictícios e uma API de mentira."""
from datetime import datetime, timezone

import pandas as pd

from painel_monstro.coletor.planilhas_csv import Tabelas
from painel_monstro.saidas import carrinhos as c

AGORA = datetime(2026, 10, 8, 15, 0, tzinfo=timezone.utc)


class RespostaFalsa:
    def __init__(self, dados):
        self._d = dados

    def json(self):
        return self._d


class ApiFalsa:
    _base = 'https://exemplo'

    def __init__(self, produtos):
        self.produtos = produtos

    def _get(self, url, params=None, vazio_se_404=False):
        pid = int(url.rsplit('/', 1)[1])
        return RespostaFalsa(self.produtos[pid]) if pid in self.produtos else None


def produto(estoque=1, usado=True, publicado=True):
    return {'published': publicado, 'categories': [{'name': {'pt': 'LP > Usado' if usado else 'LP > Novo/Lacrado'}}],
            'variants': [{'stock_management': True, 'stock': estoque}]}


def tabelas(clientes=(), pedidos=()):
    cl = pd.DataFrame(list(clientes), columns=['email', 'telefone', 'aceita_marketing', 'total_consumido'])
    pe = pd.DataFrame([tuple(p) + (100.0, 0.0, None) for p in pedidos],
                      columns=['email', 'data', 'valido', 'subtotal', 'desconto', 'cupom'])
    return Tabelas(clientes=cl, pedidos=pe, itens=pd.DataFrame(), produtos=pd.DataFrame())


def carrinho(id=1, horas=20, email='a@exemplo.com', fone='+5562999990000', total='200.00',
             produtos=((10, 'LP Teste: Um - (1980) - (Vinil Usado)'),), **extra):
    quando = (pd.Timestamp(AGORA) - pd.Timedelta(hours=horas)).strftime('%Y-%m-%dT%H:%M:%S+0000')
    base = {'id': id, 'created_at': quando, 'updated_at': quando, 'completed_at': None, 'contact_name': 'ana  souza',
            'contact_email': email, 'contact_phone': fone, 'abandoned_checkout_url': f'https://loja.exemplo/c/{id}',
            'subtotal': total, 'total': total,
            'products': [{'product_id': p, 'name': n, 'quantity': 1, 'price': '100'} for p, n in produtos]}
    return base | extra


def rodar(carrinhos, tab=None, params=None, api=None, **kw):
    return c.montar_fila(carrinhos, tab or tabelas(), params or c.Parametros(comparacao_pct=0), AGORA,
                         api or ApiFalsa({10: produto()}), **kw)


def test_telefone_whatsapp():
    assert c.telefone_whatsapp('+55 (62) 99999-0000') == '5562999990000'
    assert c.telefone_whatsapp('62 3000-0000') == '556230000000'
    assert c.telefone_whatsapp('123') == ''
    assert c.telefone_whatsapp('') == ''
    assert c.telefone_whatsapp('11 81234-5678') == ''  # celular de 11 dígitos precisa começar com 9


def test_itens_em_portugues_e_resumo():
    assert c.texto_dos_itens(['LP A - (1977)', 'LP B - (Vinil Usado)']) == 'LP A e LP B'
    assert c.texto_dos_itens(['A', 'B', 'C']) == 'A, B e C'
    assert c.texto_dos_itens(['A', 'B', 'C', 'D', 'E']) == 'A, B e mais 3 discos'


def test_marcador_desconhecido_fica_e_avisa():
    texto, avisos = c.montar_mensagem('Oi {nome}, {coisa}', {'nome': 'Ana'})
    assert texto == 'Oi Ana, {coisa}' and avisos == ['{coisa}']


def test_fila_basica_com_link_do_whatsapp():
    fila, _ = rodar([carrinho()])
    assert len(fila) == 1
    linha = fila[0]
    assert linha.situacao == 'Contatar' and linha.modelo == 'T1_UNICO' and linha.primeiro_nome == 'Ana'
    assert linha.link in linha.mensagem and linha.link_whatsapp.startswith('https://wa.me/5562999990000?text=')
    assert '{' not in linha.mensagem


def test_janela_de_horas():
    fila, motivos = rodar([carrinho(1, horas=5, email='x@exemplo.com'), carrinho(2, horas=24 * 10, email='y@exemplo.com')])
    assert fila == [] and sum(motivos.values()) == 2


def test_um_por_cliente_fica_o_mais_recente():
    fila, _ = rodar([carrinho(1, horas=40), carrinho(2, horas=20)])
    assert [linha.carrinho for linha in fila] == ['2']


def test_ja_comprou_depois_sai_da_fila():
    tab = tabelas([('a@exemplo.com', '', True, 100)], [('a@exemplo.com', pd.Timestamp('2026-10-08 10:00'), True)])
    fila, motivos = rodar([carrinho(horas=20)], tab)
    assert fila == [] and motivos['já comprou depois do carrinho'] == 1


def test_compra_antes_do_carrinho_vira_recorrente():
    tab = tabelas([('a@exemplo.com', '', True, 100)], [('a@exemplo.com', pd.Timestamp('2026-09-01 10:00'), True)])
    fila, _ = rodar([carrinho()], tab, api=ApiFalsa({10: produto(estoque=3)}))
    assert fila[0].modelo == 'T1_RECORRENTE'


def test_nao_aceita_marketing_e_bloqueio():
    tab = tabelas([('a@exemplo.com', '', False, 0)])
    _, motivos = rodar([carrinho()], tab)
    assert motivos['não aceita marketing'] == 1
    _, motivos = rodar([carrinho()], bloqueio={'+55 62 99999-0000'})
    assert motivos['na aba Bloqueio'] == 1
    _, motivos = rodar([carrinho()], bloqueio={'A@Exemplo.com'})
    assert motivos['na aba Bloqueio'] == 1


def test_esgotado_nao_leva_o_link():
    fila, _ = rodar([carrinho()], api=ApiFalsa({10: produto(estoque=0)}))
    assert fila[0].modelo == 'ESGOTADO' and fila[0].estoque == 'Esgotado'
    assert fila[0].link not in fila[0].mensagem


def test_disco_lacrado_nunca_recebe_a_mensagem_de_exemplar_unico_usado():
    api = ApiFalsa({10: produto(estoque=1, usado=True)})  # categoria errada na loja: usado, mas o nome diz lacrado
    fila, _ = rodar([carrinho(produtos=((10, 'LP Pink Floyd: At Pompeii (Novo/Lacrado)'),))], api=api)
    assert fila[0].modelo == 'T1'


def test_estoque_parcial():
    api = ApiFalsa({10: produto(estoque=1), 11: produto(estoque=0)})
    fila, _ = rodar([carrinho(produtos=((10, 'A'), (11, 'B')))], api=api)
    assert fila[0].estoque == 'Parcial' and fila[0].modelo == 'ESGOTADO'


def test_modelo_pelo_toque_e_pelo_valor():
    p = c.Parametros()
    kw = dict(unico_usado=False, ja_comprou=False, vip=False)
    assert c.escolher_modelo(2, 160, 'OK', p, **kw) == 'T2_ESCASSEZ'
    assert c.escolher_modelo(2, 200, 'OK', c.Parametros(frete_limite_garantido=True), custo_frete=30, **kw) == 'T2_FRETE'
    assert c.escolher_modelo(2, 100, 'OK', p, **kw) == 'T2_ESCASSEZ'
    assert c.escolher_modelo(3, 250, 'OK', p, **kw) == 'T3_CUPOM'
    assert c.escolher_modelo(3, 150, 'OK', p, **kw) == 'T2_ESCASSEZ'
    assert c.escolher_modelo(1, 500, 'OK', p, **kw) == 'T1'
    assert c.escolher_modelo(3, 250, 'OK', p, unico_usado=False, ja_comprou=True, vip=True) == 'T2_ESCASSEZ'  # VIP sem cupom
    assert c.escolher_modelo(2, 250, 'Parcial', p, **kw) == 'ESGOTADO'


def test_toques_ja_enviados_levam_ao_proximo_modelo_e_ao_fim():
    fila, _ = rodar([carrinho(total='300.00')], estado={'1': {'toques': 2}})
    assert fila[0].modelo == 'T3_CUPOM' and fila[0].cupom == 'VOLTA10OUT' and fila[0].proximo_toque == 3
    fila, _ = rodar([carrinho()], estado={'1': {'toques': 3}})
    assert fila == []
    fila, _ = rodar([carrinho()], estado={'1': {'status': 'Recuperado', 'toques': 1}})
    assert fila == []


def test_cupom_com_aprovacao_espera():
    p = c.Parametros(comparacao_pct=0, cupom_precisa_de_aprovacao=True)
    fila, _ = rodar([carrinho(total='300.00')], params=p, estado={'1': {'toques': 2}})
    assert fila[0].situacao == 'Aguardar aprovação'


def test_telefone_invalido_nao_gera_link():
    fila, _ = rodar([carrinho(fone='123')])
    assert fila[0].situacao == 'Telefone inválido' and fila[0].link_whatsapp == ''


def test_grupo_de_comparacao_e_reproduzivel():
    assert c.no_grupo_de_comparacao(5, 10) == c.no_grupo_de_comparacao(5, 10)
    sorteados = sum(c.no_grupo_de_comparacao(i, 10) for i in range(5000))
    assert 400 < sorteados < 600
    assert not any(c.no_grupo_de_comparacao(i, 0) for i in range(200))
    fila, _ = rodar([carrinho(1)], params=c.Parametros(comparacao_pct=100))
    assert fila[0].situacao == 'Grupo de comparação' and fila[0].link_whatsapp == ''


def test_modelo_ausente_avisa_nas_observacoes():
    fila, _ = rodar([carrinho()], params=c.Parametros(comparacao_pct=0, modelos={}))
    assert 'não existe' in fila[0].observacoes


def test_frete_teto_limites_moeda_e_sem_estimativa_do_preco_do_cliente():
    kw = dict(unico_usado=False, ja_comprou=False, vip=False)
    p = c.Parametros(frete_limite_garantido=True)
    for valor, custo, esperado in [(199.99, 20, 'T2_ESCASSEZ'), (200,30,'T2_FRETE'),
            (200,30.01,'T3_CUPOM'), (200,None,'T3_CUPOM'), (200,0,'T3_CUPOM'),
            (200,-1,'T3_CUPOM'), (200,float('nan'),'T3_CUPOM'), (200,float('inf'),'T3_CUPOM')]:
        assert c.escolher_modelo(2,valor,'OK',p,custo_frete=custo,**kw)==esperado
    assert c.escolher_modelo(2,200,'OK',c.Parametros(),custo_frete=20,**kw)=='T2_FRETE'
    api = ApiFalsa({})
    for extra in [{'shipping_cost_customer':'10'}, {'shipping_cost_owner':'20','currency':'USD'},
                  {'shipping_cost_owner':'0','currency':'BRL'}, {'shipping_cost_owner':'nan','currency':'BRL'},
                  {'shipping_cost_owner':'20','currency':'BRL','shipping_pickup_type':'pickup'}]:
        custo, aviso = c.custo_frete_da_loja(carrinho(**extra),api)
        assert custo is None and aviso


def test_consulta_individual_de_frete_e_falha_nao_inventa_custo():
    class API:
        _base='https://exemplo'
        def _get(self,url):
            assert url=='https://exemplo/checkouts/1'
            return RespostaFalsa({'shipping_cost_owner':'25.90','currency':'BRL'})
    assert c.custo_frete_da_loja(carrinho(),API())==(25.9,'')
    class Fora(API):
        def _get(self,url):
            raise RuntimeError('rede fora')
    custo, aviso=c.custo_frete_da_loja(carrinho(),Fora())
    assert custo is None and 'indisponível' in aviso


class ApiCotacao(ApiFalsa):
    _base='https://api.nuvemshop.com.br/2025-03/555'
    def __init__(self,valor=30, falhar=False, opcoes=None):
        super().__init__({10:produto()})
        self.valor,self.falhar,self.opcoes=valor,falhar,opcoes
        self.urls=[]
    def _get(self,url,params=None,**kw):
        if '/shipping/quotations' in url:
            self.urls.append(url)
            assert url=='https://api.nuvemshop.com.br/unstable/555/carts/1/shipping/quotations'
            if self.falhar: raise RuntimeError('cotação fora')
            return RespostaFalsa({'options':self.opcoes if self.opcoes is not None else [
                {'type':'pickup','price':{'value':0,'currency':'BRL'},'assigned_token':'nao-guardar'},
                {'type':'ship','price':{'value':self.valor,'currency':'BRL'},'assigned_token':'nao-guardar'}]})
        return super()._get(url,params=params,**kw)


def test_modelo_manual_nao_contorna_teto_e_terceiro_toque_continua():
    for custo in [30.01,0,'erro']:
        fila,_=rodar([carrinho()],api=ApiCotacao(custo),estado={'1':{'toques':1,'modelo_escolhido':'T2_FRETE'}})
        assert fila[0].modelo=='T3_CUPOM'
        assert 'VOLTAFRETE' not in fila[0].mensagem
    fila,_=rodar([carrinho()],api=ApiCotacao(30),estado={'1':{'toques':1}})
    assert fila[0].modelo=='T2_FRETE' and fila[0].cupom
    assert 'mais econômica' in fila[0].mensagem
    fila,_=rodar([carrinho()],api=ApiCotacao(30),estado={'1':{'toques':2}})
    assert fila[0].modelo=='T3_CUPOM'
    fila,_=rodar([carrinho(total='220',subtotal='190')],api=ApiCotacao(20),estado={'1':{'toques':1}})
    assert fila[0].modelo=='T2_ESCASSEZ'


def test_cotacao_api_so_entrega_brl_mais_barata_sem_jwt():
    api=ApiCotacao(opcoes=[{'type':'pickup','price':{'value':0,'currency':'BRL'}},
       {'type':'ship','price':{'value':70,'currency':'BRL'}},
       {'type':'ship','price':{'value':22.8,'currency':'BRL'},'assigned_token':'nao-guardar'},
       {'type':'ship','price':{'value':1,'currency':'USD'}}])
    valor,aviso=c.cotar_frete_do_carrinho(carrinho(),api)
    assert valor==22.8 and 'cotado ao cliente' in aviso
    fila,_=rodar([carrinho()],api=api,estado={'1':{'toques':1}})
    assert fila[0].modelo=='T2_FRETE'
    assert 'nao-guardar' not in str(fila)


def test_falha_cotacao_antecipa_desconto_mas_nunca_conta_toque_ou_repete_oferta():
    fila,_=rodar([carrinho()],api=ApiCotacao(falhar=True),estado={'1':{'toques':1}})
    assert fila[0].modelo=='T3_CUPOM' and fila[0].proximo_toque==2 and fila[0].toques_enviados==1
    assert '10% antecipados' in fila[0].observacoes
    fila,motivos=rodar([carrinho()],estado={'1':{'toques':2,'modelos_enviados':['T1','T3_CUPOM']}})
    assert fila==[] and motivos['oferta final de 10% já enviada']==1


def test_primeiro_toque_e_carrinho_baixo_nao_consultam_frete():
    api=ApiCotacao()
    fila,_=rodar([carrinho()],api=api)
    assert fila[0].modelo=='T1_UNICO' and api.urls==[]
    fila,_=rodar([carrinho(total='199.99')],api=api,estado={'1':{'toques':1}})
    assert fila[0].modelo=='T2_ESCASSEZ' and api.urls==[]


def test_consignado_nao_recebe_desconto_por_protecao():
    for categoria in ['LP > Usado > Etiqueta prata']:
        api=ApiCotacao(50)
        api.produtos[10]['categories']=[{'name':{'pt':categoria}}]
        api.produtos[10]['variants'][0]['stock']=3
        for estado in [{'toques':1},{'toques':2,'modelo_escolhido':'T3_CUPOM'}]:
            fila,_=rodar([carrinho(total='300')],api=api,estado={'1':estado})
            assert fila[0].modelo=='T2_LEMBRETE' and fila[0].cupom==''
            assert '10%' not in fila[0].mensagem and 'exemplar único' not in fila[0].mensagem


def test_lacrado_e_categorias_conflitantes_recebem_desconto_geral():
    api=ApiCotacao(50)
    api.produtos[10]['categories']=[{'name':{'pt':'Usado'}},{'name':{'pt':'Novo/Lacrado'}}]
    fila,_=rodar([carrinho(total='300',produtos=((10,'LP Fictício (Novo Lacrado)'),))],
                api=api,estado={'1':{'toques':1}})
    assert fila[0].modelo=='T3_CUPOM' and fila[0].cupom
    assert 'discos usados' not in fila[0].mensagem


def test_consignado_nao_recebe_frete_por_protecao():
    api=ApiCotacao(20)
    api.produtos[10]['categories']=[{'name':{'pt':'Usado > Etiqueta prata'}}]
    fila,_=rodar([carrinho(total='300')],api=api,estado={'1':{'toques':1}})
    assert fila[0].modelo not in c.MODELOS_COM_CUPOM and fila[0].cupom==''
