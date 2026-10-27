import pytest

from painel_monstro.saidas import ga4

_rel_original = ga4.relatorio


class Resp:
    def __init__(self, dados, status=200):
        self.dados, self.status_code, self.text = dados, status, str(dados)

    def json(self):
        return self.dados


def linha(dims, mets):
    return {'dimensionValues': [{'value': v} for v in dims], 'metricValues': [{'value': str(v)} for v in mets]}


class SessaoFalsa:
    def __init__(self):
        self.chamadas = []

    def post(self, url, json, timeout):
        self.chamadas.append((url, json))
        if 'dimensionFilter' in json:
            if json['offset']:
                return Resp({'rowCount': 3, 'rows': []})
            return Resp({'rowCount': 3, 'rows': [
                linha(['20261025', 'grc2026', 'vermute'], [10, 3, 2, 1, 89.9]),
                linha(['20261027', 'grc2026', 'vermute'], [5, 1, 1, 1, 89.9]),
                linha(['20261026', 'grc2026', 'ousel'], [7, 0, 0, 0, 0])]})
        # diário em duas páginas, para testar a paginação
        if json['offset'] == 0:
            return Resp({'rowCount': 3, 'rows': [linha(['20261020', 'ig', 'social', '(not set)'], [100, 5, 3, 2, 300.5]),
                                                 linha(['20261021', 'google', 'organic', '(organic)'], [50, 1, 1, 1, 70])]})
        return Resp({'rowCount': 3, 'rows': [linha(['20261021', 'brevo', 'email', 'news'], [9, 0, 0, 0, 0])]})


def _rel(s, p, c, limite=10000):
    return _rel_original(s, p, c, limite=2)


def test_passo_rotina_monta_as_duas_abas(monkeypatch):
    monkeypatch.setattr(ga4, 'relatorio', _rel)
    s = SessaoFalsa()
    paginas = dict(ga4.passo_rotina(object(), '', sessao=s))
    d = paginas['ga4_diario']
    assert list(d.columns) == ga4.COLUNAS_DIARIO
    assert len(d) == 3 and d.iloc[0]['data'] == '2026-10-21'
    assert '360685758' in s.chamadas[0][0]
    lk = paginas['ga4_links']
    v = lk[lk.banda == 'vermute'].iloc[0]
    assert (v.sessoes, v.compras, v.receita, v.primeira_visita, v.ultima_visita) == (15, 2, 179.8, '2026-10-25', '2026-10-27')
    assert lk.iloc[0].banda == 'vermute'  # mais compras primeiro




def test_erro_do_google_vira_erro_ga4():
    class Ruim:
        def post(self, *a, **k):
            return Resp({'error': 'x'}, 403)
    with pytest.raises(ga4.ErroGA4):
        ga4.passo_rotina(object(), '123', sessao=Ruim())


def test_links_vazio_tem_colunas():
    assert list(ga4.montar_links([]).columns) == ga4.COLUNAS_LINKS
