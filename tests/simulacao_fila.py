"""Simulação de vários dias da fila única, com a Mariana sem marcar nada e uma rodada que falha.

Serve de teste (ver tests/test_fluxo_sem_travas.py) e de demonstração:
    python -m tests.simulacao_fila
Usa só dados inventados e uma planilha de mentira em memória.
"""
from __future__ import annotations

import pandas as pd

from painel_monstro.coletor.nuvemshop_api import ErroAPI
from painel_monstro.saidas import carrinhos_planilha as cp
from painel_monstro.saidas import regua_planilha as rp
from painel_monstro.saidas.planilha_google import PlanilhaGoogle
from tests.test_carrinhos import ApiFalsa, carrinho, produto
from tests.test_carrinhos_planilha import PlanilhaFalsa
from tests.test_fila_unica import loja_padrao, mundo

BRT = 'America/Sao_Paulo'


def momento(texto: str) -> pd.Timestamp:
    """'2026-10-19 10:00' em horário de Brasília, como UTC."""
    return pd.Timestamp(texto, tz=BRT).tz_convert('UTC')


class ApiDaSimulacao(ApiFalsa):
    def __init__(self, produtos, carrinhos, falhar=False):
        super().__init__(produtos)
        self._carrinhos, self._falhar = carrinhos, falhar

    def listar(self, caminho, **kw):
        if self._falhar:
            raise ErroAPI('A Nuvemshop respondeu 503 depois de 5 tentativas.')
        return iter(self._carrinhos)


def montar_mundo(limite: int = 3):
    pg = PlanilhaGoogle(PlanilhaFalsa())
    cp.garantir_abas(pg)
    rp.preparar_abas(pg)
    cfg = pg._ss.abas['Configuração']
    linhas = {str(l[0]): i + 1 for i, l in enumerate(cfg.get_all_values())}
    cfg.grade[(linhas['Limite de mensagens por dia'], 2)] = limite
    cfg.grade[(linhas['Teste 45 dias: grupo de controle (%)'], 2)] = 0
    cfg.grade[(linhas['Teste 45 dias: só email (%)'], 2)] = 0
    cfg.grade[(linhas['Teste 45 dias: email e WhatsApp (%)'], 2)] = 100
    clientes = [('a@exemplo.com', 'Ana Alves', '62999990001', True), ('b@exemplo.com', 'Beto Braga', '62999990002', True),
                ('p1@exemplo.com', 'Paula Um', '62999990003', True), ('p2@exemplo.com', 'Paulo Dois', '62999990004', True),
                ('v1@exemplo.com', 'Vera Vip', '62999990005', True)]
    compras = [('p1@exemplo.com', '2026-09-04', 'LP Gilberto Gil: Refazenda - (1975) - (Vinil Usado)', 900, 80.0),
               ('p2@exemplo.com', '2026-09-05', 'LP Caetano Veloso - Transa (Vinil Usado)', 901, 90.0)]
    compras += [('v1@exemplo.com', d, f'LP Jorge Ben - Disco {i}', 800 + i, 200.0) for i, d in enumerate(['2026-01-10', '2026-03-10', '2026-08-05'])]
    t = mundo(clientes, compras, loja_padrao())
    # carrinho A abandonado no sábado 17/10 às 11h; carrinho B na sexta 16/10 às 10h
    cart_a = carrinho(id=1, email='a@exemplo.com', fone='62999990001', created_at='2026-10-17T14:00:00+0000', updated_at='2026-10-17T14:00:00+0000')
    cart_b = carrinho(id=2, email='b@exemplo.com', fone='62999990002', created_at='2026-10-16T13:00:00+0000', updated_at='2026-10-16T13:00:00+0000')
    return pg, t, [cart_a, cart_b]


def rodada(pg, t, carrinhos, quando: str, falhar: bool = False):
    api = ApiDaSimulacao({10: produto(), 501: produto(1), 502: produto(1), 503: produto(1)}, carrinhos, falhar)
    return cp.atualizar_fila(pg, api, t, momento(quando), fila_unica=True)


def quadro(pg) -> dict[str, dict]:
    """Estado de cada linha da aba Fila, por origem e dono (sem nome nem telefone)."""
    aba = pg._ss.abas['Fila']
    saida = {}
    for pos, l in enumerate(aba.get_all_values()[1:], start=2):
        d = {n: (l[i] if i < len(l) else '') for i, n in enumerate(cp.NOMES)}
        quem = {'1': 'Carrinho A', '2': 'Carrinho B'}.get(d['Carrinho']) or d['Email'].split('@')[0]
        saida[quem] = {'pos': pos, 'origem': d['Origem'], 'situacao': d['Situação'], 'toques': d['Toques já enviados'],
                       'aviso': 'Estava na fila de ontem' in str(d['Observações']), 'encerrado_em': d['Encerrado em']}
    return saida


def resumo_do_quadro(q: dict) -> str:
    partes = []
    for quem, d in q.items():
        extra = ' [AVISO: não marcada]' if d['aviso'] else ''
        partes.append(f'{quem}: {d["situacao"]}{extra}')
    return '; '.join(partes)


def rodar_simulacao(imprimir: bool = False) -> list[tuple[str, str]]:
    """Segunda 19/10 a segunda 26/10. A Mariana marca só o carrinho A, na quinta."""
    pg, t, carrinhos = montar_mundo(limite=3)
    linha_do_tempo: list[tuple[str, str]] = []

    def registrar(titulo: str) -> None:
        linha_do_tempo.append((titulo, resumo_do_quadro(quadro(pg))))
        if imprimir:
            print(f'{titulo}\n    {linha_do_tempo[-1][1]}')

    rodada(pg, t, carrinhos, '2026-10-19 10:00')
    registrar('Seg 19/10 10h · primeira rodada (limite 3 por dia)')
    rodada(pg, t, carrinhos, '2026-10-20 10:00')
    registrar('Ter 20/10 10h · a Mariana não marcou nada')
    antes = pg._ss.abas['Fila'].get_all_values()
    try:
        rodada(pg, t, carrinhos, '2026-10-21 10:00', falhar=True)
        linha_do_tempo.append(('Qua 21/10 10h · a Nuvemshop falhou', 'ERRO: a rodada não falhou como esperado'))
    except ErroAPI:
        depois = pg._ss.abas['Fila'].get_all_values()
        linha_do_tempo.append(('Qua 21/10 10h · a Nuvemshop falhou', 'a rodada parou antes de gravar; a planilha ficou ' +
                               ('IGUAL à de ontem' if antes == depois else 'ALTERADA')))
        if imprimir:
            print(f'{linha_do_tempo[-1][0]}\n    {linha_do_tempo[-1][1]}')
    rodada(pg, t, carrinhos, '2026-10-22 10:00')
    registrar('Qui 22/10 10h · rodada de volta ao normal (recalcula tudo do zero)')
    aba = pg._ss.abas['Fila']
    q = quadro(pg)
    aba.grade[(q['Carrinho A']['pos'], cp.COL['Toques já enviados'] + 1)] = 1
    aba.grade[(q['Carrinho A']['pos'], cp.COL['Último envio em'] + 1)] = '2026-10-22 11:00'
    rodada(pg, t, carrinhos, '2026-10-22 12:00')
    registrar('Qui 22/10 12h · a Mariana marcou o toque 1 do carrinho A')
    rodada(pg, t, carrinhos, '2026-10-24 10:00')
    registrar('Sáb 24/10 10h · mais dois dias sem marcar o resto')
    rodada(pg, t, carrinhos, '2026-10-25 10:00')
    registrar('Dom 25/10 · domingo (não sai fila; o pendente espera)')
    rodada(pg, t, carrinhos, '2026-10-26 10:00')
    registrar('Seg 26/10 10h · carrinho B passou de 7 dias (sem contar o domingo)')
    return linha_do_tempo


if __name__ == '__main__':
    rodar_simulacao(imprimir=True)
