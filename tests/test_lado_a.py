"""Testes do passo Lado A no Brevo (Black Monstro 2026).

Adiciona clientes com pedido pago e cupom ANTECIPA10 à lista do Lado A no Brevo.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any
from urllib.parse import unquote

import pandas as pd
import pytest

from painel_monstro.config import Config
from painel_monstro.coletor.planilhas_csv import Tabelas
from painel_monstro.saidas import brevo as bv

CHAVE = 'chave-falsa-lado-a-123456789'


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


class SessaoBrevoFalsa:
    """Sessão que simula a API do Brevo v3."""

    def __init__(self, contatos_iniciais: dict[str, dict] | None = None):
        self.contatos = dict(contatos_iniciais or {})
        self.chamadas = []

    def request(self, metodo: str, url: str, headers=None, params=None, json=None, timeout=None):
        caminho = url.replace(bv.URL_BASE, '')
        chamada = {'metodo': metodo, 'caminho': caminho, 'params': params, 'json': json}
        self.chamadas.append(chamada)

        # GET /contacts/{email}
        if metodo == 'GET' and caminho.startswith('/contacts/'):
            email = unquote(caminho.replace('/contacts/', '').split('?')[0]).lower()
            if email in self.contatos:
                return Resposta(200, self.contatos[email])
            return Resposta(404, {'message': 'Contact does not exist'})

        # POST /contacts (criar contato)
        if metodo == 'POST' and caminho == '/contacts':
            email = json['email'].lower()
            self.contatos[email] = {
                'email': email,
                'attributes': json.get('attributes', {}),
                'listIds': json.get('listIds', []),
                'emailBlacklisted': False,
            }
            return Resposta(201, {'id': 100 + len(self.contatos)})

        # PUT /contacts/{email} (atualizar atributos)
        if metodo == 'PUT' and caminho.startswith('/contacts/'):
            email = unquote(caminho.replace('/contacts/', '').split('?')[0]).lower()
            if email in self.contatos:
                self.contatos[email].setdefault('attributes', {}).update(json.get('attributes', {}))
                return Resposta(204, {})
            return Resposta(404, {'message': 'Contact does not exist'})

        # POST /contacts/lists/{listId}/contacts/add
        if metodo == 'POST' and '/contacts/add' in caminho:
            partes = caminho.split('/')
            lista_id = int(partes[3])
            emails = json.get('emails', [])
            for em in emails:
                em_l = em.lower()
                if em_l in self.contatos:
                    ids = self.contatos[em_l].setdefault('listIds', [])
                    if lista_id not in ids:
                        ids.append(lista_id)
            return Resposta(201, {'contacts': {'success': emails, 'failure': []}})

        return Resposta(200, {})


class PlanilhaMock:
    """Planilha que simula abas para testes do passo Lado A."""

    def __init__(self, abas: dict[str, list[list[Any]]] | None = None):
        self.abas: dict[str, list[list[Any]]] = {k: [list(r) for r in v] for k, v in (abas or {}).items()}
        self._ss = self

    def worksheet(self, nome: str):
        if nome not in self.abas:
            raise KeyError(nome)
        return AbaMock(self, nome)

    def mesclar(self, titulo: str, df: pd.DataFrame, chave: list[str]):
        if titulo not in self.abas or len(self.abas[titulo]) == 0:
            cabecalho = list(df.columns)
            linhas = df.astype(str).values.tolist()
            self.abas[titulo] = [cabecalho] + linhas
            return
        existentes = self.abas[titulo]
        cabecalho = existentes[0]
        linhas_existentes = existentes[1:]
        indices_chave = [cabecalho.index(c) for c in chave]
        novos_por_chave = {tuple(str(row[c]) for c in chave): [str(x) for x in row] for _, row in df.iterrows()}
        resultado = []
        for l in linhas_existentes:
            k = tuple(str(l[i]) for i in indices_chave)
            if k not in novos_por_chave:
                resultado.append(l)
        resultado.extend(novos_por_chave.values())
        self.abas[titulo] = [cabecalho] + resultado


class AbaMock:
    def __init__(self, planilha: PlanilhaMock, nome: str):
        self.planilha = planilha
        self.nome = nome

    def get_all_values(self):
        return self.planilha.abas.get(self.nome, [])


def _criar_tabelas(pedidos: list[dict], clientes: list[dict] | None = None) -> Tabelas:
    df_p = pd.DataFrame(pedidos)
    df_c = pd.DataFrame(clientes or [])
    return Tabelas(
        pedidos=df_p,
        clientes=df_c,
        itens=pd.DataFrame(),
        produtos=pd.DataFrame(),
    )


# ----------------------------------------------------------------------------
# 1. Período
# ----------------------------------------------------------------------------
def test_lado_a_fora_do_periodo_nao_executa():
    planilha = PlanilhaMock({
        'Configuração': [
            ['parâmetro', 'valor'],
            ['Black: início do Antecipa', '2026-11-10'],
            ['Black: acesso Lado A', '2026-11-26'],
        ]
    })
    tabelas = _criar_tabelas([
        {'numero': '101', 'email': 'cliente1@exemplo.com', 'nome': 'Ana Silva', 'valido': True, 'cupom': 'ANTECIPA10', 'data': '2026-11-09'}
    ])
    cfg = Config(brevo_api_key=CHAVE, brevo_modo_teste=False)

    # Antes do início (09/11)
    res_antes = bv.passo_lado_a(cfg, planilha, tabelas, hoje=date(2026, 11, 9))
    assert res_antes['status'] == 'fora_do_periodo'
    assert res_antes['adicionados'] == 0

    # Depois do fim (26/11)
    res_depois = bv.passo_lado_a(cfg, planilha, tabelas, hoje=date(2026, 11, 26))
    assert res_depois['status'] == 'fora_do_periodo'
    assert res_depois['adicionados'] == 0


def test_lado_a_dentro_do_periodo_executa():
    sessao = SessaoBrevoFalsa()
    b = bv.Brevo(CHAVE, modo_teste=False, sessao=sessao)
    planilha = PlanilhaMock()
    tabelas = _criar_tabelas([
        {'numero': '101', 'email': 'cliente1@exemplo.com', 'nome': 'Ana Silva', 'valido': True, 'cupom': 'ANTECIPA10', 'data': '2026-11-11'}
    ])
    cfg = Config(brevo_api_key=CHAVE, brevo_modo_teste=False)

    res = bv.passo_lado_a(cfg, planilha, tabelas, hoje=date(2026, 11, 11), brevo_cliente=b)
    assert res['status'] == 'ok'
    assert res['adicionados'] == 1
    assert 'cliente1@exemplo.com' in sessao.contatos
    assert 33 in sessao.contatos['cliente1@exemplo.com']['listIds']
    assert sessao.contatos['cliente1@exemplo.com']['attributes']['FIRSTNAME'] == 'Ana'


# ----------------------------------------------------------------------------
# 2. Cupons e pedidos válidos
# ----------------------------------------------------------------------------
@pytest.mark.parametrize('cupom_valido', ['ANTECIPA10', 'antecipa10', 'Antecipa10', 'OUTRO, ANTECIPA10', 'antecipa10, fretegratis'])
def test_lado_a_reconhece_variacoes_do_cupom(cupom_valido):
    sessao = SessaoBrevoFalsa()
    b = bv.Brevo(CHAVE, modo_teste=False, sessao=sessao)
    planilha = PlanilhaMock()
    tabelas = _criar_tabelas([
        {'numero': '102', 'email': 'cliente2@exemplo.com', 'nome': 'Beto Costa', 'valido': True, 'cupom': cupom_valido, 'data': '2026-11-12'}
    ])
    cfg = Config(brevo_api_key=CHAVE, brevo_modo_teste=False)

    res = bv.passo_lado_a(cfg, planilha, tabelas, hoje=date(2026, 11, 12), brevo_cliente=b)
    assert res['status'] == 'ok'
    assert res['adicionados'] == 1
    assert 33 in sessao.contatos['cliente2@exemplo.com']['listIds']


def test_lado_a_ignora_pedidos_invalidos_ou_outro_cupom():
    sessao = SessaoBrevoFalsa()
    b = bv.Brevo(CHAVE, modo_teste=False, sessao=sessao)
    planilha = PlanilhaMock()
    tabelas = _criar_tabelas([
        {'numero': '103', 'email': 'invalido@exemplo.com', 'nome': 'Carlos', 'valido': False, 'cupom': 'ANTECIPA10', 'data': '2026-11-12'},
        {'numero': '104', 'email': 'outro_cupom@exemplo.com', 'nome': 'Daniela', 'valido': True, 'cupom': 'VOLTA10', 'data': '2026-11-12'},
    ])
    cfg = Config(brevo_api_key=CHAVE, brevo_modo_teste=False)

    res = bv.passo_lado_a(cfg, planilha, tabelas, hoje=date(2026, 11, 12), brevo_cliente=b)
    assert res['status'] == 'nenhum_candidato'
    assert res['adicionados'] == 0
    assert len(sessao.contatos) == 0


# ----------------------------------------------------------------------------
# 3. Idempotência e gravação em lado_a_enviados
# ----------------------------------------------------------------------------
def test_lado_a_grava_em_lado_a_enviados_e_nao_repete():
    sessao = SessaoBrevoFalsa()
    b = bv.Brevo(CHAVE, modo_teste=False, sessao=sessao)
    planilha = PlanilhaMock()
    tabelas = _criar_tabelas([
        {'numero': '105', 'email': 'cliente5@exemplo.com', 'nome': 'Eduardo Jorge', 'valido': True, 'cupom': 'ANTECIPA10', 'data': '2026-11-12'}
    ])
    cfg = Config(brevo_api_key=CHAVE, brevo_modo_teste=False)

    # Primeira execução
    res1 = bv.passo_lado_a(cfg, planilha, tabelas, hoje=date(2026, 11, 12), brevo_cliente=b)
    assert res1['status'] == 'ok'
    assert res1['adicionados'] == 1
    assert 'lado_a_enviados' in planilha.abas
    assert len(planilha.abas['lado_a_enviados']) == 2  # cabeçalho + 1 linha
    assert planilha.abas['lado_a_enviados'][1] == ['cliente5@exemplo.com', '105', '2026-11-12']

    # Segunda execução (mesmo cliente)
    res2 = bv.passo_lado_a(cfg, planilha, tabelas, hoje=date(2026, 11, 12), brevo_cliente=b)
    assert res2['status'] == 'nenhum_candidato'
    assert res2['adicionados'] == 0
    # Não chamou a API novamente
    assert len([c for c in sessao.chamadas if c['metodo'] == 'POST']) == 2  # criar contato + add lista da 1ª vez


def test_lado_a_quando_contato_ja_tem_lista_no_brevo():
    sessao = SessaoBrevoFalsa({
        'existente@exemplo.com': {
            'email': 'existente@exemplo.com',
            'attributes': {'FIRSTNAME': 'Fabio'},
            'listIds': [33],
            'emailBlacklisted': False,
        }
    })
    b = bv.Brevo(CHAVE, modo_teste=False, sessao=sessao)
    planilha = PlanilhaMock()
    tabelas = _criar_tabelas([
        {'numero': '106', 'email': 'existente@exemplo.com', 'nome': 'Fabio Lima', 'valido': True, 'cupom': 'ANTECIPA10', 'data': '2026-11-13'}
    ])
    cfg = Config(brevo_api_key=CHAVE, brevo_modo_teste=False)

    res = bv.passo_lado_a(cfg, planilha, tabelas, hoje=date(2026, 11, 13), brevo_cliente=b)
    assert res['status'] == 'ok'
    assert res['adicionados'] == 0  # já estava na lista
    # Foi registrado na aba lado_a_enviados
    assert 'lado_a_enviados' in planilha.abas
    assert planilha.abas['lado_a_enviados'][1][0] == 'existente@exemplo.com'


# ----------------------------------------------------------------------------
# 4. Respeito a Bloqueio, aceita_marketing e emailBlacklisted
# ----------------------------------------------------------------------------
def test_lado_a_respeita_bloqueio_e_descadastros():
    sessao = SessaoBrevoFalsa({
        'descadastrado@exemplo.com': {
            'email': 'descadastrado@exemplo.com',
            'attributes': {'FIRSTNAME': 'Geraldo'},
            'listIds': [],
            'emailBlacklisted': True,
        }
    })
    b = bv.Brevo(CHAVE, modo_teste=False, sessao=sessao)
    planilha = PlanilhaMock({
        'Bloqueio': [
            ['Telefone', 'Email', 'Data', 'Motivo'],
            ['62999990001', 'bloqueado@exemplo.com', '2026-10-01', 'Não quer'],
        ]
    })
    tabelas = _criar_tabelas(
        pedidos=[
            {'numero': '107', 'email': 'bloqueado@exemplo.com', 'nome': 'Helena', 'valido': True, 'cupom': 'ANTECIPA10', 'data': '2026-11-13'},
            {'numero': '108', 'email': 'sem_marketing@exemplo.com', 'nome': 'Igor', 'valido': True, 'cupom': 'ANTECIPA10', 'data': '2026-11-13'},
            {'numero': '109', 'email': 'descadastrado@exemplo.com', 'nome': 'Geraldo', 'valido': True, 'cupom': 'ANTECIPA10', 'data': '2026-11-13'},
            {'numero': '110', 'email': 'liberado@exemplo.com', 'nome': 'Julia Reis', 'valido': True, 'cupom': 'ANTECIPA10', 'data': '2026-11-13'},
        ],
        clientes=[
            {'email': 'sem_marketing@exemplo.com', 'nome': 'Igor', 'aceita_marketing': False},
            {'email': 'liberado@exemplo.com', 'nome': 'Julia Reis', 'aceita_marketing': True},
        ]
    )
    cfg = Config(brevo_api_key=CHAVE, brevo_modo_teste=False)

    res = bv.passo_lado_a(cfg, planilha, tabelas, hoje=date(2026, 11, 13), brevo_cliente=b)
    assert res['status'] == 'ok'
    assert res['adicionados'] == 1
    assert 'liberado@exemplo.com' in sessao.contatos
    assert 'bloqueado@exemplo.com' not in sessao.contatos
    assert 'sem_marketing@exemplo.com' not in sessao.contatos
    assert 33 not in sessao.contatos['descadastrado@exemplo.com']['listIds']


# ----------------------------------------------------------------------------
# 5. Modo teste
# ----------------------------------------------------------------------------
def test_lado_a_em_modo_teste_nao_escreve_nada():
    sessao = SessaoBrevoFalsa()
    b = bv.Brevo(CHAVE, modo_teste=True, sessao=sessao)
    planilha = PlanilhaMock()
    tabelas = _criar_tabelas([
        {'numero': '111', 'email': 'teste_modo@exemplo.com', 'nome': 'Katia', 'valido': True, 'cupom': 'ANTECIPA10', 'data': '2026-11-13'}
    ])
    cfg = Config(brevo_api_key=CHAVE, brevo_modo_teste=True)

    res = bv.passo_lado_a(cfg, planilha, tabelas, hoje=date(2026, 11, 13), brevo_cliente=b)
    assert res['status'] == 'modo_teste'
    assert res['adicionados'] == 0
    assert res['candidatos'] == 1
    assert len(sessao.contatos) == 0
    assert 'lado_a_enviados' not in planilha.abas


# ----------------------------------------------------------------------------
# 6. ID customizado na aba Configuração
# ----------------------------------------------------------------------------
def test_lado_a_le_id_da_lista_da_configuracao():
    sessao = SessaoBrevoFalsa()
    b = bv.Brevo(CHAVE, modo_teste=False, sessao=sessao)
    planilha = PlanilhaMock({
        'Configuração': [
            ['parâmetro', 'valor'],
            ['Black: ID da lista Lado A no Brevo', '42'],
        ]
    })
    tabelas = _criar_tabelas([
        {'numero': '112', 'email': 'lista42@exemplo.com', 'nome': 'Lucas', 'valido': True, 'cupom': 'ANTECIPA10', 'data': '2026-11-14'}
    ])
    cfg = Config(brevo_api_key=CHAVE, brevo_modo_teste=False)

    res = bv.passo_lado_a(cfg, planilha, tabelas, hoje=date(2026, 11, 14), brevo_cliente=b)
    assert res['status'] == 'ok'
    assert res['adicionados'] == 1
    assert 42 in sessao.contatos['lista42@exemplo.com']['listIds']


# ----------------------------------------------------------------------------
# 7. Erro no Brevo registra em alertas e não derruba
# ----------------------------------------------------------------------------
def test_lado_a_erro_no_brevo_registra_alerta_e_continua():
    class SessaoComErro:
        def request(self, metodo, url, headers=None, params=None, json=None, timeout=None):
            return Resposta(500, {'message': 'Erro interno simulado'})

    b = bv.Brevo(CHAVE, modo_teste=False, sessao=SessaoComErro())
    planilha = PlanilhaMock()
    tabelas = _criar_tabelas([
        {'numero': '113', 'email': 'erro@exemplo.com', 'nome': 'Marcos', 'valido': True, 'cupom': 'ANTECIPA10', 'data': '2026-11-14'}
    ])
    cfg = Config(brevo_api_key=CHAVE, brevo_modo_teste=False)

    res = bv.passo_lado_a(cfg, planilha, tabelas, hoje=date(2026, 11, 14), brevo_cliente=b)
    assert res['status'] == 'erro'
    assert res['adicionados'] == 0
    assert 'alertas' in planilha.abas
    assert any(linha[0] == 'lado_a_brevo' and linha[3] == 'sim' for linha in planilha.abas['alertas'])


# ----------------------------------------------------------------------------
# 8. Integração com a rotina
# ----------------------------------------------------------------------------
def test_lado_a_integrado_na_rotina(monkeypatch):
    from painel_monstro import rotina

    chamado = []

    def mock_passo_lado_a(config, planilha, tabelas, hoje=None, **kw):
        chamado.append({'hoje': hoje})
        return {'status': 'ok', 'adicionados': 1}

    monkeypatch.setattr(bv, 'passo_lado_a', mock_passo_lado_a)

    # Simula chamada direta como a rotina faz
    cfg = Config(brevo_api_key=CHAVE, brevo_modo_teste=True)
    planilha = PlanilhaMock()
    tabelas = _criar_tabelas([])

    res = bv.passo_lado_a(cfg, planilha, tabelas, hoje=date(2026, 11, 15))
    assert len(chamado) == 1
    assert res['status'] == 'ok'
    assert res['adicionados'] == 1
