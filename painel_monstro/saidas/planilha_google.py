"""Grava as tabelas do Painel na Planilha Google (o banco de dados do projeto) e lê a aba `custos`.

Cada tabela vai para uma aba, sem duplicar:
- Abas do Painel (`clientes`, `pedidos`, `itens`, `produtos`, `indicadores`): a aba é regravada inteira numa
  só atualização, e o que sobrar de uma versão maior é apagado. Rodar duas vezes dá o mesmo resultado.
  Não escreva nessas abas: o que for digitado nelas é substituído na próxima rodada.
- `regua` (histórico das rodadas mensais): linhas de um mês já gravado não são trocadas, a menos que se
  force; os outros meses ficam como estão.
- `custos` e `alertas` são do Túlio: o Painel só cria o cabeçalho quando a aba está vazia e nunca mexe nos dados.

Tudo é gravado como valor (modo RAW): um texto que comece com "=" nunca vira fórmula.
A chave da conta de serviço e o ID da planilha vêm do `.env`; nada disso é impresso.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

import gspread
import numpy as np
import pandas as pd
from gspread.http_client import BackOffHTTPClient
from gspread.utils import ValueRenderOption

from painel_monstro.log_publico import comando_seguro, ArgumentParserSeguro, resumo_erro
from painel_monstro.config import RAIZ_PROJETO, Config
from painel_monstro.coletor.planilhas_csv import Tabelas
from painel_monstro.motor import regua as motor_regua
from painel_monstro.motor.indicadores import CUSTOS_COLUNAS, ler_custos

LOTE_DE_LINHAS = 5000  # linhas por requisição de gravação

ABAS_DO_PAINEL = ('clientes', 'pedidos', 'itens', 'produtos', 'indicadores')
ABA_REGUA, ABA_CUSTOS, ABA_ALERTAS = 'regua', 'custos', 'alertas'

REGUA_COLUNAS = ['mes', 'data_referencia', 'email', 'etapa', 'grupo', 'dias_sem_comprar', 'n_compras', 'total_gasto', 'vip']
REGUA_CHAVE = ['mes']  # a rodada de um mês é trocada inteira, nunca pela metade

ALERTAS_COLUNAS = ['indicador', 'condicao', 'limite', 'ativo', 'observacao']
ALERTAS_NOTAS = {
    'indicador': 'Nome do indicador, igual ao da aba indicadores (coluna indicador).',
    'condicao': 'Escreva "menor que" ou "maior que". O alerta dispara quando o valor do indicador cruza o limite.',
    'limite': 'Número do limite, sem R$ nem %. Ex.: 15 para 15%.',
    'ativo': 'sim ou não.',
    'observacao': 'Livre: por que esse limite, o que fazer quando disparar.',
}
CUSTOS_NOTAS = {
    'mes': 'Mês no formato AAAA-MM. Ex.: 2026-10. Uma linha por mês.',
    'investimento_meta': 'R$ gastos no Meta (Facebook e Instagram) no mês.',
    'compras_meta': 'Número de compras que o Meta atribui ao mês.',
    'receita_meta': 'R$ de receita que o Meta atribui ao mês.',
    'custo_brevo': 'R$ da mensalidade do Brevo no mês.',
    'receita_brevo': 'R$ de vendas que o Brevo atribui aos envios do mês.',
    'margem_usados': 'Margem média dos discos usados, em %. Ex.: 55. Vale para os meses sem valor próprio (repete o último).',
    'margem_lacrados': 'Margem média dos discos lacrados, em %. Ex.: 25. Mesma regra dos usados.',
    'embalagem': 'R$ de embalagem por pedido. Mesma regra das margens.',
    'frete_pago_loja': 'R$ de frete que a loja pagou no mês (campanha de frete grátis). Vazio conta como zero.',
}


class ErroPlanilha(Exception):
    """Erro ao falar com a Planilha Google. A mensagem nunca leva chave nem ID."""


@dataclass
class Gravacao:
    aba: str
    linhas: int
    colunas: int
    acao: str  # criada, substituida, mesclada, ignorada, mantida, cabecalho_criado, cabecalho_diferente


# ----------------------------------------------------------------------------
# Conversão da tabela em células
# ----------------------------------------------------------------------------
def _celula(valor: Any) -> Any:
    if valor is None or valor is pd.NA or valor is pd.NaT:
        return ''
    if isinstance(valor, (bool, np.bool_)):
        return bool(valor)
    if isinstance(valor, (int, np.integer)):
        return int(valor)
    if isinstance(valor, (float, np.floating)):
        if np.isnan(valor) or np.isinf(valor):
            return ''
        return int(valor) if float(valor).is_integer() and abs(valor) < 1e15 else float(valor)
    if isinstance(valor, pd.Timestamp):
        return valor.strftime('%Y-%m-%d %H:%M:%S')
    return str(valor)


def tabela_para_celulas(df: pd.DataFrame) -> list[list[Any]]:
    """Cabeçalho + linhas, só com tipos que a API aceita. Data sem hora vira AAAA-MM-DD."""
    df = df.copy()
    for coluna in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[coluna]):
            so_data = (df[coluna].dropna() == df[coluna].dropna().dt.normalize()).all()
            df[coluna] = df[coluna].dt.strftime('%Y-%m-%d' if so_data else '%Y-%m-%d %H:%M:%S')
    linhas = [[_celula(v) for v in linha] for linha in df.astype(object).itertuples(index=False, name=None)]
    return [[str(c) for c in df.columns], *linhas]


def _letra(n: int) -> str:
    """Número da coluna (1 = A) em letras."""
    texto = ''
    while n > 0:
        n, resto = divmod(n - 1, 26)
        texto = chr(65 + resto) + texto
    return texto


# ----------------------------------------------------------------------------
# Planilha
# ----------------------------------------------------------------------------
class PlanilhaGoogle:
    def __init__(self, planilha: Any):
        """`planilha` é um gspread.Spreadsheet (ou algo com a mesma interface, nos testes)."""
        self._ss = planilha

    @classmethod
    def conectar(cls, config: Config) -> 'PlanilhaGoogle':
        if not config.planilha_id or not (config.google_service_account_file or config.google_service_account_json):
            raise ErroPlanilha('Faltam PLANILHA_ID e GOOGLE_SERVICE_ACCOUNT_FILE (ou GOOGLE_SERVICE_ACCOUNT_JSON) no .env ou nos Secrets.')
        chave: dict | None = None
        caminho = ''
        if config.google_service_account_json:  # rotina no GitHub: a chave vem de um Secret, sem arquivo no disco
            try:
                chave = json.loads(config.google_service_account_json)
            except ValueError:
                raise ErroPlanilha('O Secret GOOGLE_SERVICE_ACCOUNT_JSON não é um JSON válido. Cole o conteúdo inteiro do arquivo da chave.') from None
        else:
            caminho = config.google_service_account_file
            if not os.path.isabs(caminho):
                caminho = os.path.join(RAIZ_PROJETO, caminho)
            if not os.path.exists(caminho):
                raise ErroPlanilha(f'Não achei o arquivo da conta de serviço do Google em {config.google_service_account_file}.')
        email = chave.get('client_email', 'o email da conta de serviço') if chave else email_da_conta(caminho)
        try:
            # BackOffHTTPClient: se o Google limitar o uso (429), espera e repete só aquela requisição, sem refazer o resto
            cliente = (gspread.service_account_from_dict(chave, http_client=BackOffHTTPClient) if chave
                       else gspread.service_account(filename=caminho, http_client=BackOffHTTPClient))
            return cls(cliente.open_by_key(config.planilha_id))
        except gspread.exceptions.SpreadsheetNotFound:
            raise ErroPlanilha(f'A planilha não foi encontrada. Compartilhe-a como Editor com {email}.') from None
        except PermissionError as erro:  # o gspread troca o 403 do Google por PermissionError
            causa = str(erro.__cause__ or '')
            link = re.search(r'https://console\.developers\.google\.com/apis/api/[^\s]+', causa)
            if 'has not been used' in causa or 'disabled' in causa:
                api = 'Google Drive' if 'drive.googleapis' in causa else 'Google Sheets'
                raise ErroPlanilha(f'A API {api} não está ativada no projeto do Google Cloud. Ative em '
                                   f'{link.group(0).rstrip(".") if link else "console.cloud.google.com, APIs e serviços, Biblioteca"}'
                                   ' e tente de novo depois de 2 minutos.') from None
            raise ErroPlanilha(f'O Google recusou o acesso. Compartilhe a planilha como Editor com {email}.') from None
        except gspread.exceptions.APIError as erro:
            codigo = getattr(getattr(erro, 'response', None), 'status_code', '?')
            if codigo in (403, 404):
                raise ErroPlanilha(f'O Google recusou o acesso ({codigo}). Compartilhe a planilha como Editor com '
                                   f'{email} e confira se as APIs Google Sheets e Google Drive estão ativadas.') from None
            raise ErroPlanilha(f'O Google respondeu erro {codigo} ao abrir a planilha.') from None

    # --- abas
    def _aba(self, titulo: str, linhas: int = 100, colunas: int = 10) -> tuple[Any, bool]:
        try:
            return self._ss.worksheet(titulo), False
        except gspread.exceptions.WorksheetNotFound:
            return self._ss.add_worksheet(title=titulo, rows=max(linhas, 2), cols=max(colunas, 1)), True

    @staticmethod
    def _escrever(aba: Any, valores: list[list[Any]]) -> None:
        """Grava `valores` a partir de A1 e apaga o que sobrou de uma versão maior."""
        antigas = aba.get_all_values()
        linhas_antes = len(antigas)
        colunas_antes = max((len(l) for l in antigas), default=0)
        linhas, colunas = len(valores), max(len(l) for l in valores)
        if aba.row_count < linhas or aba.col_count < colunas:
            aba.resize(rows=max(aba.row_count, linhas), cols=max(aba.col_count, colunas))
        for inicio in range(0, linhas, LOTE_DE_LINHAS):
            aba.update(valores[inicio:inicio + LOTE_DE_LINHAS], f'A{inicio + 1}', raw=True)
        sobras = []
        if linhas_antes > linhas:
            sobras.append(f'A{linhas + 1}:{_letra(max(colunas, colunas_antes))}{linhas_antes}')
        if colunas_antes > colunas:
            sobras.append(f'{_letra(colunas + 1)}1:{_letra(colunas_antes)}{min(linhas, linhas_antes)}')
        if sobras:
            aba.batch_clear(sobras)

    def substituir(self, titulo: str, df: pd.DataFrame) -> Gravacao:
        """Regrava a aba inteira com `df`. Tabela sem linhas grava só o cabeçalho."""
        valores = tabela_para_celulas(df)
        aba, criada = self._aba(titulo, len(valores), len(valores[0]))
        self._escrever(aba, valores)
        return Gravacao(titulo, len(valores) - 1, len(valores[0]), 'criada' if criada else 'substituida')

    def _ler_historico(self, aba: Any, colunas: list[str]) -> pd.DataFrame:
        valores = aba.get_all_values(value_render_option=ValueRenderOption.unformatted)
        if len(valores) < 1 or not any(valores[0]):
            return pd.DataFrame(columns=colunas)
        cabecalho = [str(c) for c in valores[0]]
        desconhecidas = set(cabecalho) - set(colunas)
        if desconhecidas:
            raise ErroPlanilha(f'A aba {aba.title} tem colunas que o Painel não conhece: {sorted(desconhecidas)}. Nada foi alterado.')
        linhas = [l + [''] * (len(cabecalho) - len(l)) for l in valores[1:] if any(str(c) != '' for c in l)]
        return pd.DataFrame(linhas, columns=cabecalho).reindex(columns=colunas)

    def mesclar(self, titulo: str, df: pd.DataFrame, chave: list[str]) -> Gravacao:
        """Troca todas as linhas que têm a mesma chave de alguma linha de `df` e mantém as outras (histórico)."""
        aba, criada = self._aba(titulo, len(df) + 1, len(df.columns))
        antigo = self._ler_historico(aba, list(df.columns)) if not criada else pd.DataFrame(columns=df.columns)
        novas = set(map(tuple, df[chave].astype(str).to_numpy()))
        ficam = antigo[[tuple(l) not in novas for l in antigo[chave].astype(str).to_numpy()]] if len(antigo) else antigo
        junto = pd.concat([ficam, df], ignore_index=True)
        self._escrever(aba, tabela_para_celulas(junto))
        return Gravacao(titulo, len(junto), len(junto.columns), 'mesclada')

    # --- régua (histórico mensal)
    def meses_da_regua(self) -> set[str]:
        aba, criada = self._aba(ABA_REGUA, 2, len(REGUA_COLUNAS))
        if criada:
            return set()
        return set(self._ler_historico(aba, REGUA_COLUNAS)['mes'].astype(str))

    def gravar_regua(self, mes: str, classificacao: pd.DataFrame, referencia: pd.Timestamp,
                     params: motor_regua.ParametrosRegua = motor_regua.PADRAO, forcar: bool = False) -> Gravacao:
        """Grava a rodada de `mes`. Uma rodada já gravada não é trocada sem `forcar`: quem recebeu e quem ficou
        no controle não pode mudar depois do envio."""
        if mes in self.meses_da_regua() and not forcar:
            return Gravacao(ABA_REGUA, 0, len(REGUA_COLUNAS), 'ignorada')
        nomes = [e.nome for e in (*params.etapas, params.vip)]
        c = classificacao[classificacao['etapa'].isin(nomes) & (classificacao['grupo'] != '')]
        df = pd.DataFrame({
            'mes': mes, 'data_referencia': referencia.strftime('%Y-%m-%d'), 'email': c.index, 'etapa': c['etapa'].to_numpy(),
            'grupo': c['grupo'].to_numpy(), 'dias_sem_comprar': c['dias'].to_numpy(), 'n_compras': c['n'].to_numpy(),
            'total_gasto': c['total'].round(2).to_numpy(), 'vip': c['vip'].to_numpy(),
        })[REGUA_COLUNAS]
        return self.mesclar(ABA_REGUA, df, REGUA_CHAVE)

    # --- abas do Túlio
    def garantir_cabecalho(self, titulo: str, colunas: list[str], notas: dict[str, str]) -> Gravacao:
        """Cria a aba com o cabeçalho se estiver vazia. Nunca mexe em aba que já tem conteúdo."""
        aba, criada = self._aba(titulo, 200, len(colunas))
        atual = [] if criada else aba.get_all_values()
        if any(any(str(c).strip() for c in linha) for linha in atual):
            igual = [str(c).strip() for c in atual[0]][:len(colunas)] == colunas
            return Gravacao(titulo, max(len(atual) - 1, 0), len(colunas), 'mantida' if igual else 'cabecalho_diferente')
        if aba.col_count < len(colunas):
            aba.resize(cols=len(colunas))
        aba.update([colunas], 'A1', raw=True)
        for i, coluna in enumerate(colunas, start=1):
            try:
                aba.update_note(f'{_letra(i)}1', notas.get(coluna, ''))
            except Exception:  # nota é só ajuda; nunca derruba a gravação
                break
        try:
            aba.format('1:1', {'textFormat': {'bold': True}})
            aba.freeze(rows=1)
        except Exception:
            pass
        return Gravacao(titulo, 0, len(colunas), 'cabecalho_criado')

    def ler_custos(self) -> pd.DataFrame:
        """A aba `custos` já normalizada (vazia se só tem o cabeçalho)."""
        try:
            aba = self._ss.worksheet(ABA_CUSTOS)
        except gspread.exceptions.WorksheetNotFound:
            return ler_custos(None)
        valores = aba.get_all_values(value_render_option=ValueRenderOption.unformatted)
        if len(valores) < 2:
            return ler_custos(None)
        cabecalho = [str(c) for c in valores[0]]
        linhas = [l + [''] * (len(cabecalho) - len(l)) for l in valores[1:] if any(str(c) != '' for c in l)]
        df = pd.DataFrame(linhas, columns=cabecalho).replace('', np.nan)
        return ler_custos(df)


def email_da_conta(caminho: str) -> str:
    """Email da conta de serviço (não é segredo: é com ele que se compartilha a planilha)."""
    try:
        with open(caminho, encoding='utf-8') as arq:
            return json.load(arq).get('client_email', 'o email da conta de serviço')
    except (OSError, ValueError):
        return 'o email da conta de serviço'


# ----------------------------------------------------------------------------
# Rodada completa
# ----------------------------------------------------------------------------
def resumo_indicadores(indicadores) -> pd.DataFrame:
    r = indicadores.resumo.copy()
    r['valor'] = [v if isinstance(v, str) or pd.isna(v) else float(v) for v in r['valor']]
    r['atualizado_em'] = pd.Timestamp.now(tz='America/Sao_Paulo').strftime('%Y-%m-%d %H:%M')  # horário de Brasília, em qualquer servidor
    return r[['grupo', 'indicador', 'valor', 'unidade', 'estado', 'nota', 'atualizado_em']]


def gravar_tudo(planilha: PlanilhaGoogle, tabelas: Tabelas, indicadores_calculados=None) -> list[Gravacao]:
    """Grava as 4 tabelas, os indicadores e garante as abas custos e alertas."""
    from painel_monstro.motor.indicadores import calcular

    resultado = [planilha.substituir(nome, getattr(tabelas, nome)) for nome in ('clientes', 'pedidos', 'itens', 'produtos')]
    resultado.append(planilha.garantir_cabecalho(ABA_CUSTOS, CUSTOS_COLUNAS, CUSTOS_NOTAS))
    resultado.append(planilha.garantir_cabecalho(ABA_ALERTAS, ALERTAS_COLUNAS, ALERTAS_NOTAS))
    ind = indicadores_calculados or calcular(tabelas, planilha.ler_custos())
    resultado.append(planilha.substituir('indicadores', resumo_indicadores(ind)))
    return resultado


@comando_seguro
def main() -> int:
    import argparse
    from painel_monstro.config import carregar
    from painel_monstro.coletor import nuvemshop_api

    analisador = ArgumentParserSeguro(description='Grava as tabelas do Painel na Planilha Google.')
    analisador.add_argument('--regua', metavar='AAAA-MM', help='grava também a rodada da régua desse mês (uma vez só)')
    analisador.add_argument('--forcar-regua', action='store_true', help='troca a rodada da régua que já foi gravada')
    args = analisador.parse_args()

    config = carregar()
    try:
        planilha = PlanilhaGoogle.conectar(config)
        tabelas, _ = nuvemshop_api.coletar(config)
        gravacoes = gravar_tudo(planilha, tabelas)
        if args.regua:
            classificacao, referencia = motor_regua.rodar(tabelas, args.regua)
            gravacoes.append(planilha.gravar_regua(args.regua, classificacao, referencia, forcar=args.forcar_regua))
    except (ErroPlanilha, nuvemshop_api.ErroAPI) as erro:
        print('Erro: ' + resumo_erro(erro))
        return 1
    print(f'{"aba":<12} {"linhas":>8}  {"colunas":>7}  o que aconteceu')
    for g in gravacoes:
        print(f'{g.aba:<12} {g.linhas:>8}  {g.colunas:>7}  {g.acao.replace("_", " ")}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
