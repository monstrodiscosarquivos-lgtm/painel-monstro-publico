"""Registro de WhatsApps enviados à mão, fora da fila (D-040).

Exemplo: a lista de VIP de outubro que a Mariana recebeu em arquivo. Cada contato vira uma linha na aba
`contatos_manuais` (email, data, origem, observação), que a fila única lê para respeitar a regra de
1 WhatsApp a cada 30 dias e para não mandar o VIP de novo no mesmo ciclo.

Só o registro do contato vai para a planilha: nome, telefone e o resto da lista de origem nunca são copiados
(nem para o repositório).

Uso:
    python -m painel_monstro.saidas.contatos_manuais --csv "C:\\caminho\\vip-whatsapp.csv" --data 2026-10-10 --origem VIP
    (acrescente --gravar para valer; sem ele só mostra o que faria)
"""
from __future__ import annotations

import argparse
import sys
from typing import Any

import pandas as pd

from painel_monstro.log_publico import comando_seguro, ArgumentParserSeguro, resumo_erro
from painel_monstro.saidas import carrinhos_planilha as cp
from painel_monstro.saidas.planilha_google import Gravacao, PlanilhaGoogle

NOTAS = {
    'email': 'Email do cliente que recebeu o WhatsApp à mão.',
    'data': 'Dia do envio (AAAA-MM-DD). A trava de 30 dias conta a partir daqui.',
    'origem': 'De onde veio a mensagem: VIP, 45 dias, Carrinho ou Garimpo. VIP aqui impede um segundo VIP no mesmo ciclo.',
    'observacao': 'Livre (por exemplo, o nome do arquivo da lista).',
}


def registrar(planilha: PlanilhaGoogle, emails: list[str], data: str, origem: str, observacao: str = '') -> dict[str, int]:
    """Acrescenta os emails que ainda não estão registrados com a mesma data e origem. Nunca apaga nada."""
    pd.Timestamp(data)  # data inválida levanta erro antes de gravar
    planilha.garantir_cabecalho(cp.ABA_CONTATOS_MANUAIS, cp.CONTATOS_MANUAIS_COLUNAS, NOTAS)
    aba = planilha._ss.worksheet(cp.ABA_CONTATOS_MANUAIS)
    ja = {(str(l[0]).strip().lower(), str(l[1]).strip()[:10], str(l[2]).strip())
          for l in aba.get_all_values()[1:] if len(l) >= 3 and str(l[0]).strip()}
    limpos = []
    for e in emails:
        e = str(e).strip().lower()
        if '@' in e and e not in limpos:
            limpos.append(e)
    novos = [[e, data, origem, observacao] for e in limpos if (e, data, origem) not in ja]
    if novos:
        aba.append_rows(novos, value_input_option='RAW')
    return {'lidos': len(limpos), 'novos': len(novos), 'ja_registrados': len(limpos) - len(novos)}


def ler_emails_do_csv(caminho: str, coluna: str = 'EMAIL') -> list[str]:
    """Só a coluna de email do arquivo; o resto nunca é lido para a memória do programa além do necessário."""
    for codificacao in ('utf-8-sig', 'latin1'):
        try:
            df = pd.read_csv(caminho, sep=';', encoding=codificacao, dtype=str, usecols=[coluna])
            return [str(x) for x in df[coluna].dropna()]
        except UnicodeDecodeError:
            continue
    raise SystemExit(f'Não consegui ler o arquivo {caminho}.')


@comando_seguro
def main(argv: list[str] | None = None) -> int:
    from painel_monstro.config import carregar

    a = ArgumentParserSeguro(description='Registra contatos de WhatsApp feitos à mão (só o registro, sem dados da lista).')
    a.add_argument('--csv', required=True, help='arquivo CSV (separador ponto e vírgula) com uma coluna de emails')
    a.add_argument('--coluna', default='EMAIL')
    a.add_argument('--data', required=True, help='dia do envio, AAAA-MM-DD')
    a.add_argument('--origem', default='VIP')
    a.add_argument('--observacao', default='lista manual')
    a.add_argument('--gravar', action='store_true', help='grava na planilha (sem isso só mostra a contagem)')
    args = a.parse_args(argv)
    emails = ler_emails_do_csv(args.csv, args.coluna)
    validos = {e.strip().lower() for e in emails if '@' in e}
    print(f'{len(validos)} email(s) na lista; detalhes somente na planilha privada.')
    if not args.gravar:
        print('Nada foi gravado (use --gravar para registrar na planilha).')
        return 0
    r = registrar(PlanilhaGoogle.conectar(carregar()), emails, args.data, args.origem, args.observacao)
    print(f'Registrados {r["novos"]} novo(s); {r["ja_registrados"]} já estavam na aba {cp.ABA_CONTATOS_MANUAIS}.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
