"""Email de resumo da segunda às 8h (Etapa 6).

O Painel monta o assunto e o HTML a cada rodada e grava na aba `resumo_email`; o script do Google
(`apps-script/fila-por-email.gs`) manda esse texto toda segunda às 8h para os endereços do campo
"Emails do resumo" da aba `Configuração`. Só números agregados: nenhum nome, email ou telefone de cliente.

Texto para pessoas: sem travessão no meio de frases (regra do AGENTS.md).
"""
from __future__ import annotations

import math
from datetime import datetime
from html import escape
from typing import Any

META_RECEITA = 9000.0
META_PARTICIPACAO = 35.0
TETO_MARKETING = 15.0


def _num(valor: Any) -> float | None:
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else v


def brl(valor: Any) -> str:
    v = _num(valor)
    if v is None:
        return 'sem dado'
    return 'R$ ' + f'{v:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def pct(valor: Any, casas: int = 1) -> str:
    v = _num(valor)
    return 'sem dado' if v is None else f'{v:.{casas}f}'.replace('.', ',') + '%'


def inteiro(valor: Any) -> str:
    v = _num(valor)
    return 'sem dado' if v is None else f'{v:,.0f}'.replace(',', '.')


def _linha(rotulo: str, valor: str, nota: str = '') -> str:
    return (f'<tr><td style="padding:4px 14px 4px 0">{escape(rotulo)}</td><td style="padding:4px 0"><b>{escape(valor)}</b></td>'
            f'<td style="padding:4px 0 4px 14px;color:#666">{escape(nota)}</td></tr>')


def montar(atual: dict, semana: list[list[Any]], vale: list[dict], indicadores: list[dict], ultima_rodada: str = '',
           agora: datetime | None = None) -> tuple[str, str]:
    """(assunto, html) do resumo. Todos os argumentos vêm das abas `atual`, `resumo_semana`, `vale_a_pena`, `indicadores` e `rodada`."""
    agora = agora or datetime.now()
    assunto = f'Resumo da semana do Painel Monstro ({agora:%d/%m/%Y})'
    meta_rec = _num(atual.get('meta_receita_quem_volta')) or META_RECEITA
    meta_part = _num(atual.get('meta_participacao_pct')) or META_PARTICIPACAO
    teto = _num(atual.get('teto_marketing_pct')) or TETO_MARKETING
    rec = _num(atual.get('receita_quem_volta_mes'))
    part = _num(atual.get('participacao_pct'))

    p: list[str] = ['<div style="font-family:Arial,sans-serif;font-size:14px;color:#222;max-width:640px">']
    p.append('<h2 style="margin:0 0 4px">Resumo da semana</h2>')
    p.append(f'<p style="margin:0 0 14px;color:#666">Painel Monstro, {agora:%d/%m/%Y}' +
             (f' · última rodada boa: {escape(str(ultima_rodada))}' if ultima_rodada else '') + '</p>')

    p.append('<h3>Objetivo: receita de quem volta</h3><table>')
    falta_rec = '' if rec is None else (f'faltam {brl(meta_rec - rec)} para a meta' if rec < meta_rec else 'meta batida')
    p.append(_linha('Receita de quem volta por mês', brl(rec), f'meta {brl(meta_rec)}; {falta_rec}' if falta_rec else f'meta {brl(meta_rec)}'))
    falta_part = '' if part is None else (f'faltam {meta_part - part:.1f} pontos'.replace('.', ',') if part < meta_part else 'meta batida')
    p.append(_linha('Participação na receita (12 meses)', pct(part), f'meta {pct(meta_part, 0)}; {falta_part}' if falta_part else f'meta {pct(meta_part, 0)}'))
    p.append(_linha('Clientes dos últimos 12 meses', inteiro(atual.get('clientes_12m'))))
    p.append(_linha('Taxa de volta por mês', pct(atual.get('taxa_volta_mes_pct'), 2)))
    p.append(_linha('Gasto por recompra', brl(atual.get('gasto_recompra'))))
    p.append(_linha('Clientes novos que voltam em 90 dias', pct(atual.get('volta_90d_pct'))))
    mkt = _num(atual.get('custo_marketing_pct'))
    p.append(_linha('Custo total de marketing sobre a receita', pct(mkt) if mkt is not None else 'aguardando a aba custos',
                    f'teto {pct(teto, 0)}'))
    p.append('</table>')

    if semana:
        p.append('<h3>A fila de WhatsApp na semana</h3><table>')
        for l in semana:
            if len(l) >= 2 and str(l[0]).strip() and str(l[0]).strip().lower() != 'indicador':
                p.append(_linha(str(l[0]).strip(), str(l[1])))
        p.append('</table>')

    if vale:
        p.append('<h3>Vale a pena?</h3><table>')
        for v in vale:
            estado = str(v.get('estado') or '')
            if estado == 'sem controle':
                texto = (f'{inteiro(v.get("pedidos"))} pedido(s), {brl(v.get("receita_atribuida"))} no mês '
                         '(receita atribuída, sem grupo de controle)')
            elif estado == 'ok':
                a_mais, resultado = _num(v.get('receita_a_mais')), _num(v.get('resultado'))
                texto = f'receita a mais {brl(a_mais)}, resultado {brl(resultado)}'
            else:
                texto = 'dados insuficientes ainda (precisa de pelo menos 30 pessoas em cada grupo)'
            p.append(_linha(str(v.get('acao') or ''), texto))
        p.append('</table>')

    faltam = [i for i in indicadores if str(i.get('estado')) in ('falta custos', 'falta dados')]
    if faltam:
        sem_custos = [i for i in faltam if str(i.get('estado')) == 'falta custos']
        p.append('<h3>O que está faltando</h3><ul style="margin-top:4px">')
        if sem_custos:
            p.append(f'<li>{len(sem_custos)} indicador(es) aguardam a aba <b>custos</b> (investimento no Meta, margens, custo do Brevo). '
                     'Preencha uma linha por mês.</li>')
        outros = len(faltam) - len(sem_custos)
        if outros:
            p.append(f'<li>{outros} indicador(es) ainda não têm dados (começam a aparecer depois das primeiras rodadas da régua e da Etapa 7).</li>')
        p.append('</ul>')

    p.append('<p style="color:#888;font-size:12px;margin-top:18px">Enviado automaticamente toda segunda às 8h. '
             'Os números são das abas da planilha, atualizadas de hora em hora.</p></div>')
    return assunto, ''.join(p)
