"""Saída pública: erros sem conteúdo externo, argumentos ou traceback.

Não tenta reconhecer nomes por expressão regular: texto de exceções, respostas
HTTP e mensagens de clientes nunca é uma fonte autorizada para o log.
"""
import argparse
from functools import wraps
import logging
import sys
import warnings


def resumo_erro(erro: BaseException) -> str:
    """Classifica sem chamar str/repr, nem ler resposta, URL ou atributos."""
    if isinstance(erro, (TimeoutError, ConnectionError)):
        return 'falha de conexão'
    if isinstance(erro, PermissionError):
        return 'acesso recusado'
    return 'falha na operação; detalhes omitidos do log público'


class ArgumentParserSeguro(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        kwargs['prog'] = 'painel-monstro'
        super().__init__(*args, **kwargs)

    def error(self, message):
        # argparse inclui os valores inválidos e argumentos desconhecidos.
        self.exit(2, 'Argumentos inválidos. Consulte --help.\n')


def comando_seguro(funcao):
    """Protege a fronteira do CLI, inclusive erros imprevistos e bibliotecas.

    Não instala hooks globais ao importar. Restaura logging/warnings ao terminar.
    Erros esperados já tratados pelo comando também devem usar resumo_erro.
    """
    @wraps(funcao)
    def executar(*args, **kwargs):
        anterior = logging.root.manager.disable
        try:
            # Bibliotecas HTTP/Google podem registrar URLs, corpos e credenciais.
            logging.disable(sys.maxsize)
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                return funcao(*args, **kwargs)
        except SystemExit as erro:
            if erro.code is None or type(erro.code) is int:
                return erro.code or 0
            print('ERRO: ' + resumo_erro(erro))
            return 1
        except KeyboardInterrupt:
            print('Operação interrompida.')
            return 130
        except Exception as erro:
            print('ERRO: ' + resumo_erro(erro))
            return 1
        finally:
            logging.disable(anterior)
    return executar
