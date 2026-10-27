"""Newsletter semanal: discos novos ou que voltaram ao estoque nos últimos 7 dias.

Toda quarta, a partir das 17h (Brasília), a rotina monta a aba `newsletter_semana` e uma linha de aviso na aba
`newsletter_aviso`, que o script do Google manda por email para os "Emails do resumo". Nada vai ao Brevo.

- `no_estoque_desde` (coluna nova da aba `produtos`): dia em que o produto entrou ou voltou ao estoque. A rotina
  guarda esse dia olhando a aba `produtos` da rodada anterior; na primeira vez vale o dia em que o produto foi criado.
- A aba `newsletter_historico` (url, data_envio) é do Cowork: o que já foi enviado fica de fora.
- Só dados de produto. Nenhum dado de cliente.
"""
from __future__ import annotations

import html
import re
from typing import Any

import pandas as pd

from painel_monstro.coletor.nuvemshop_api import imagem_640, texto_da_descricao  # noqa: F401 - reexportados
from painel_monstro.motor import generos
from painel_monstro.saidas import carrinhos as c

SITE = 'https://lojamonstro.com.br'
DIAS = 7
HORA = 17
QUARTA = 2  # segunda = 0

COLUNAS = ['url', 'nome', 'artista', 'album', 'ano', 'tipo', 'preco', 'imagem', 'familia', 'descricao']
COLUNAS_AVISO = ['gerado_em', 'discos', 'assunto', 'html']

_PREFIXO = re.compile(r'^\s*(LP|CD|DVD|K7|Fita|Compacto|Box|Vinil|Single|EP)\b[\s:.-]*', re.I)


def separar_nome(nome: Any) -> tuple[str, str, str]:
    """(artista, album, ano) a partir de "LP Artista - Álbum (1989) (Vinil usado)".

    Sem separador entre artista e álbum, o artista fica vazio e o álbum recebe o nome limpo.
    """
    n = re.sub(r'\s+', ' ', str(nome or '')).strip()
    ano = next(iter(re.findall(r'\((\d{4})\)', n)), '')
    n = _PREFIXO.sub('', n, count=1)
    n = re.sub(r'\([^)]*\)', ' ', n)
    n = re.sub(r'\([^)]*$', ' ', n)
    n = re.sub(r'\s+', ' ', n).strip(' -–—:')
    n = re.sub(r'(?:\s*[-–—]\s*)+$', '', n).strip()
    partes = re.split(r'\s[-–—]\s|:\s', n, maxsplit=1)
    if len(partes) == 2 and partes[0].strip() and partes[1].strip():
        return partes[0].strip(), partes[1].strip(' -–—:'), ano
    return '', n, ano


def tipo_do_disco(nome: Any, categorias: Any) -> str:
    txt = f'{nome or ""} {categorias or ""}'.lower()
    if 'lacrad' in txt or 'novo' in txt:
        return 'lacrado'
    if 'usad' in txt or 'udado' in txt:
        return 'usado'
    return ''


def _em_estoque(estoque: Any) -> bool:
    v = pd.to_numeric(estoque, errors='coerce')
    return bool(pd.notna(v) and v > 0)


def _dia(valor: Any) -> str:
    t = pd.to_datetime(valor, errors='coerce', utc=True)
    return '' if pd.isna(t) else t.strftime('%Y-%m-%d')


def marcar_estoque(produtos: pd.DataFrame, anterior: list[list[str]], hoje: str) -> pd.DataFrame:
    """Acrescenta `no_estoque_desde` (AAAA-MM-DD) à tabela de produtos. `anterior` = linhas da aba `produtos` da rodada passada."""
    produtos = produtos.copy()
    antes: dict[str, tuple[bool, str]] = {}
    tinha_coluna = bool(anterior) and 'no_estoque_desde' in anterior[0]
    if tinha_coluna:
        cab = anterior[0]
        i_url, i_est, i_desde = cab.index('url'), cab.index('estoque'), cab.index('no_estoque_desde')
        for linha in anterior[1:]:
            if len(linha) > max(i_url, i_est, i_desde):
                antes[str(linha[i_url])] = (_em_estoque(str(linha[i_est]).replace(',', '.')), str(linha[i_desde]))
    datas = []
    for url, estoque, criado in zip(produtos['url'], produtos['estoque'], produtos.get('criado_em', [None] * len(produtos))):
        if not _em_estoque(estoque):
            datas.append('')
            continue
        era_em_estoque, desde = antes.get(str(url), (False, ''))
        if era_em_estoque and desde:
            datas.append(desde)                    # continua em estoque: mantém o dia
        elif str(url) in antes:
            datas.append(hoje)                     # estava sem estoque e voltou
        else:
            datas.append(_dia(criado) or hoje)     # primeira vez que o Painel vê: vale o dia da criação
    produtos['no_estoque_desde'] = datas
    return produtos


def _chave_url(valor: Any) -> str:
    partes = [p for p in str(valor or '').strip().lower().split('?')[0].split('/') if p]
    return partes[-1] if partes else ''


def montar_semana(produtos: pd.DataFrame, historico: list[list[str]] | None, hoje: pd.Timestamp,
                  site: str = SITE, dias: int = DIAS) -> pd.DataFrame:
    """Discos em estoque, exibidos, que entraram ou voltaram nos últimos `dias`, menos o que está no histórico."""
    if produtos is None or len(produtos) == 0 or 'no_estoque_desde' not in produtos.columns:
        return pd.DataFrame(columns=COLUNAS)
    ja = set()
    if historico and len(historico) > 1 and 'url' in historico[0]:
        i = historico[0].index('url')
        ja = {_chave_url(l[i]) for l in historico[1:] if len(l) > i and l[i]}
    corte = (hoje.normalize() - pd.Timedelta(days=dias)).strftime('%Y-%m-%d')
    p = produtos
    ok = (p['estoque'].map(_em_estoque) & p['exibir'].fillna(False).astype(bool) & p['url'].notna()
          & (p['no_estoque_desde'].fillna('').astype(str) >= corte) & p['nome'].map(c.eh_disco)
          & ~p['url'].map(_chave_url).isin(ja))
    linhas = []
    for r in p[ok].sort_values('no_estoque_desde', ascending=False, kind='stable').itertuples():
        artista, album, ano = separar_nome(r.nome)
        fam = generos.familia_principal([generos.familias(getattr(r, 'categorias', None), r.nome)])
        linhas.append({
            'url': f'{site}/produtos/{r.url}/', 'nome': r.nome, 'artista': artista, 'album': album, 'ano': ano,
            'tipo': tipo_do_disco(r.nome, getattr(r, 'categorias', None)), 'preco': r.preco,
            'imagem': getattr(r, 'imagem', '') or '', 'familia': fam or '', 'descricao': getattr(r, 'descricao', '') or '',
        })
    return pd.DataFrame(linhas, columns=COLUNAS)


def deve_gerar(agora: pd.Timestamp, ultimo_gerado: str) -> bool:
    """Quarta-feira, 17h em diante, uma vez por dia."""
    return agora.weekday() == QUARTA and agora.hour >= HORA and str(ultimo_gerado)[:10] != agora.strftime('%Y-%m-%d')


def aviso(n: int, agora: pd.Timestamp) -> pd.DataFrame:
    assunto = f'Newsletter da semana: {n} discos prontos'
    corpo = (f'<div style="font-family:Arial,sans-serif;font-size:14px"><p><b>{html.escape(assunto)}</b></p>'
             f'<p>A aba <b>newsletter_semana</b> da Planilha Google está pronta ({agora:%d/%m/%Y}). '
             f'Nada foi enviado pelo Brevo.</p></div>')
    return pd.DataFrame([{'gerado_em': agora.strftime('%Y-%m-%d %H:%M'), 'discos': n, 'assunto': assunto, 'html': corpo}],
                        columns=COLUNAS_AVISO)


def passo_rotina(ler_aba, produtos: pd.DataFrame, agora: pd.Timestamp, site: str = SITE) -> list[tuple[str, pd.DataFrame]]:
    """Páginas a gravar. `ler_aba(nome)` devolve as linhas da aba (lista vazia se não existe). Fora da quarta às 17h, nada."""
    antigo = ler_aba('newsletter_aviso')
    ultimo = antigo[1][0] if len(antigo) > 1 and antigo[1] else ''
    if not deve_gerar(agora, ultimo):
        return []
    semana = montar_semana(produtos, ler_aba('newsletter_historico'), agora, site)
    return [('newsletter_semana', semana), ('newsletter_aviso', aviso(len(semana), agora))]
