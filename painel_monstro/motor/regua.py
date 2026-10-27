"""Motor da régua mensal de reativação (AGENTS.md, "Régua mensal").

Para cada cliente com pelo menos uma compra paga e que aceita marketing, calcula há quantos dias ele
comprou pela última vez e em que etapa cai, e sorteia o grupo de controle. Dá os mesmos números da
`referencia/reativacao.py`.

Regras:
- Dias sem comprar = data de referência (dia seguinte ao último pedido) menos a data da última compra
  paga. Comprou, o relógio zera: a última compra passa a ser a nova.
- Etapa 0 só para quem tem 1 compra. VIP (3+ compras ou R$1.000+ gastos) com 75 a 104 dias vai só para
  o WhatsApp e sai das etapas normais.
- 10% de cada etapa vai para o controle (não recebe nada), sorteado com semente fixa por mês, e só
  quando a etapa tem pelo menos 10 pessoas.
- Máximo de um benefício (cupom) a cada 90 dias por cliente, quando se informa o histórico.
- Quem não aceita marketing fica de fora de tudo.
- Resultado de cada etapa = taxa de compra em 30 dias de quem recebeu menos a do controle.

As janelas e ofertas ficam em `ParametrosRegua`, para depois virem da aba `Régua` (D-017).
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from painel_monstro.coletor.planilhas_csv import Tabelas

EMAIL_DA_LOJA = 'contato@monstrodiscos.com.br'
SEM_ETAPA = 'Sem etapa'
DESCANSO = 'Descanso'


@dataclass(frozen=True)
class Etapa:
    nome: str
    dias_min: int
    dias_max: int
    so_primeira_compra: bool = False
    tem_controle: bool = True
    beneficio: bool = False  # cupom ou frete grátis: entra no limite de 1 benefício a cada 90 dias


@dataclass(frozen=True)
class ParametrosRegua:
    etapas: tuple[Etapa, ...] = (
        Etapa('Etapa 0 · Pós-compra', 15, 44, so_primeira_compra=True),
        Etapa('Etapa 1 · Lembrete', 45, 74),
        Etapa('Etapa 2 · Convite', 90, 119, beneficio=True),
        Etapa('Etapa 3 · Última chamada', 180, 209, beneficio=True),
    )
    vip: Etapa = Etapa('VIP · WhatsApp', 75, 104, tem_controle=False)
    vip_min_compras: int = 3
    vip_min_gasto: float = 1000.0
    controle: float = 0.10
    minimo_para_controle: int = 10
    descanso_a_partir_de: int = 210
    janela_resultado: int = 30
    dias_entre_beneficios: int = 90
    amostra_minima: int = 30  # D-020: abaixo disso o resultado é "dados insuficientes"
    emails_excluidos: tuple[str, ...] = (EMAIL_DA_LOJA,)


PADRAO = ParametrosRegua()


def pedidos_validos(tabelas: Tabelas) -> pd.DataFrame:
    return tabelas.pedidos.loc[tabelas.pedidos['valido'].astype(bool)]


def data_referencia(tabelas: Tabelas) -> pd.Timestamp:
    """Dia seguinte ao último pedido pago."""
    return pedidos_validos(tabelas)['data'].max().normalize() + pd.Timedelta(days=1)


def base_clientes(tabelas: Tabelas, referencia: pd.Timestamp | None = None,
                  params: ParametrosRegua = PADRAO) -> pd.DataFrame:
    """Um cliente por linha (índice = email): compras, gasto, última compra, dias sem comprar e VIP.

    Só entram clientes com compra paga que aceitam marketing.
    """
    referencia = referencia if referencia is not None else data_referencia(tabelas)
    validos = pedidos_validos(tabelas)
    validos = validos[validos['data'] < referencia]  # nada depois da data de referência
    g = validos.groupby('email').agg(n=('data', 'size'), ultima=('data', 'max'), total=('total', 'sum'))
    g['dias'] = (referencia - g['ultima']).dt.days
    clientes = tabelas.clientes[tabelas.clientes['aceita_marketing']].drop_duplicates('email', keep='last').set_index('email')
    base = g.join(clientes[['primeiro_nome', 'cidade', 'telefone']], how='inner')
    base = base[~base.index.isin(params.emails_excluidos)]
    base['vip'] = (base['n'] >= params.vip_min_compras) | (base['total'] >= params.vip_min_gasto)
    return base


def _sorteio(df: pd.DataFrame, semente: int, params: ParametrosRegua) -> pd.DataFrame:
    if len(df) < params.minimo_para_controle:
        return df.iloc[0:0]
    return df.sample(frac=params.controle, random_state=semente)


def classificar(base: pd.DataFrame, mes: str, referencia: pd.Timestamp, params: ParametrosRegua = PADRAO,
                ultimos_beneficios: pd.Series | None = None) -> pd.DataFrame:
    """Etapa e grupo de cada cliente da base.

    `mes` ("AAAA-MM") define a semente do sorteio do controle. `ultimos_beneficios` (opcional) é uma
    série email -> data do último benefício enviado, para o limite de 90 dias.
    Devolve a base com as colunas `etapa` e `grupo` ("envio", "controle" ou vazio para quem não recebe).
    """
    semente = int(mes.replace('-', ''))
    saida = base.copy()
    saida['etapa'] = SEM_ETAPA
    saida['grupo'] = ''
    saida.loc[saida['dias'] >= params.descanso_a_partir_de, 'etapa'] = DESCANSO

    vip = base[base['vip'] & base['dias'].between(params.vip.dias_min, params.vip.dias_max)]
    saida.loc[vip.index, ['etapa', 'grupo']] = [params.vip.nome, 'envio']

    excluidos_beneficio = 0
    for etapa in params.etapas:
        df = base[base['dias'].between(etapa.dias_min, etapa.dias_max) & ~base.index.isin(vip.index)]
        if etapa.so_primeira_compra:
            df = df[df['n'] == 1]
        if etapa.beneficio and ultimos_beneficios is not None:
            recente = ultimos_beneficios.reindex(df.index)
            fora = recente.notna() & ((referencia - recente).dt.days < params.dias_entre_beneficios)
            excluidos_beneficio += int(fora.sum())
            df = df[~fora]
        controle = _sorteio(df, semente, params) if etapa.tem_controle else df.iloc[0:0]
        saida.loc[df.index, ['etapa', 'grupo']] = [etapa.nome, 'envio']
        saida.loc[controle.index, 'grupo'] = 'controle'
    saida.attrs['excluidos_por_limite_de_beneficio'] = excluidos_beneficio
    return saida


def resumo(classificacao: pd.DataFrame, params: ParametrosRegua = PADRAO) -> pd.DataFrame:
    """Quantos recebem e quantos ficam no controle em cada etapa."""
    linhas = []
    for etapa in (*params.etapas, params.vip):
        c = classificacao[classificacao['etapa'] == etapa.nome]
        linhas.append({'etapa': etapa.nome, 'janela': f'{etapa.dias_min} a {etapa.dias_max} dias',
                       'recebem': int((c['grupo'] == 'envio').sum()), 'controle': int((c['grupo'] == 'controle').sum())})
    return pd.DataFrame(linhas)


def lista_da_etapa(classificacao: pd.DataFrame, etapa: str, grupo: str = 'envio') -> pd.DataFrame:
    """Clientes de uma etapa e grupo, do que mais gastou para o que menos gastou."""
    c = classificacao[(classificacao['etapa'] == etapa) & (classificacao['grupo'] == grupo)]
    return c.sort_values('total', ascending=False)


def resultado_etapas(classificacao_anterior: pd.DataFrame, tabelas: Tabelas, referencia_anterior: pd.Timestamp,
                     params: ParametrosRegua = PADRAO) -> pd.DataFrame:
    """Resultado de cada etapa da rodada anterior: compras em até 30 dias depois da data de referência.

    `incremento_pp` = taxa de compra de quem recebeu menos a do controle, em pontos percentuais.
    `amostra_suficiente` é falso quando algum dos dois grupos tem menos de 30 pessoas (D-020).
    """
    fim = referencia_anterior + pd.Timedelta(days=params.janela_resultado)
    v = pedidos_validos(tabelas)
    janela = v[(v['data'] >= referencia_anterior) & (v['data'] < fim)]
    compras = janela.groupby('email').agg(pedidos=('data', 'size'), receita=('total', 'sum'))

    linhas = []
    for etapa in (*params.etapas, params.vip):
        recebeu = classificacao_anterior[(classificacao_anterior['etapa'] == etapa.nome) & (classificacao_anterior['grupo'] == 'envio')]
        controle = classificacao_anterior[(classificacao_anterior['etapa'] == etapa.nome) & (classificacao_anterior['grupo'] == 'controle')]
        voltou = compras.reindex(recebeu.index).dropna()
        voltou_c = compras.reindex(controle.index).dropna()
        taxa = len(voltou) / len(recebeu) * 100 if len(recebeu) else float('nan')
        taxa_c = len(voltou_c) / len(controle) * 100 if len(controle) else float('nan')
        linhas.append({
            'etapa': etapa.nome, 'recebeu': len(recebeu), 'voltou': len(voltou), 'taxa': taxa,
            'receita': float(voltou['receita'].sum()), 'controle': len(controle), 'voltou_controle': len(voltou_c),
            'taxa_controle': taxa_c, 'incremento_pp': taxa - taxa_c,
            'amostra_suficiente': len(recebeu) >= params.amostra_minima and len(controle) >= params.amostra_minima,
        })
    return pd.DataFrame(linhas)


def rodar(tabelas: Tabelas, mes: str, params: ParametrosRegua = PADRAO,
          ultimos_beneficios: pd.Series | None = None) -> tuple[pd.DataFrame, pd.Timestamp]:
    """Atalho: data de referência, base de clientes e classificação do mês."""
    referencia = data_referencia(tabelas)
    base = base_clientes(tabelas, referencia, params)
    return classificar(base, mes, referencia, params, ultimos_beneficios), referencia
