"""D-079: dados inteiramente fictícios; nenhuma chamada real."""
from collections import Counter
import importlib
from io import StringIO
import logging
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import warnings

import pandas as pd
import pytest

from painel_monstro import rotina
from painel_monstro.config import Config
from painel_monstro.log_publico import comando_seguro, resumo_erro
from painel_monstro.saidas import brevo, carrinhos, contatos_manuais, ga4
from tests.test_brevo import Resposta, Sessao
from tests.test_rotina import config, mundo  # fixtures com APIs de mentira


DADOS = ['Pessoa Ficticia Sigilosa', 'sigiloso@example.invalid', '5562999991234',
         'Rua Ficticia Sigilosa 987', '9876.54', 'token-falso-sigiloso',
         'https://example.invalid/pedido?segredo=restrito']
PRIVADO = ' | '.join(DADOS)


def conferir(texto):
    for dado in DADOS:
        assert dado not in texto
    assert 'Traceback' not in texto


@pytest.mark.parametrize('tipo', [ValueError, RuntimeError, PermissionError, TimeoutError, SystemExit])
def test_fronteira_nao_expoe_erro_avisos_logging_nem_traceback(tipo, capsys):
    anterior = logging.root.manager.disable

    @comando_seguro
    def comando():
        logging.getLogger('urllib3').critical(PRIVADO, exc_info=True)
        warnings.warn(PRIVADO)
        raise tipo(PRIVADO)

    assert comando() == 1
    capturado = capsys.readouterr()
    conferir(capturado.out + capturado.err)
    assert 'ERRO' in capturado.out
    assert logging.root.manager.disable == anterior


def test_resumo_nunca_converte_excecao_ou_atributos():
    class Hostil(Exception):
        def __str__(self):
            pytest.fail('não converter exceção em texto')

        def __repr__(self):
            pytest.fail('não converter exceção em repr')

    assert resumo_erro(Hostil(PRIVADO))


@pytest.mark.parametrize('esperado', [True, False])
def test_rotina_main_erro_esperado_e_imprevisto(monkeypatch, capsys, esperado):
    def falhar(**kw):
        raise (rotina.ErroRotina if esperado else RuntimeError)(PRIVADO)

    monkeypatch.setattr(rotina, 'rodar', falhar)
    monkeypatch.setattr(sys, 'argv', ['rotina'])
    assert rotina.main() == 1
    saida = capsys.readouterr()
    conferir(saida.out + saida.err)
    conferir(rotina._resumo_do_erro(ValueError(PRIVADO)))


@pytest.mark.parametrize('modulo', ['painel_monstro.rotina', 'painel_monstro.coletor.nuvemshop_api',
    'painel_monstro.saidas.planilha_google', 'painel_monstro.saidas.carrinhos',
    'painel_monstro.saidas.fila_unica', 'painel_monstro.saidas.meta',
    'painel_monstro.saidas.raspadinha', 'painel_monstro.saidas.contatos_manuais'])
def test_argumento_invalido_nao_reaparece_no_terminal(modulo, monkeypatch, capsys):
    monkeypatch.setattr(sys, 'argv', ['programa', '--argumento-inexistente', PRIVADO])
    assert importlib.import_module(modulo).main() == 2
    saida = capsys.readouterr()
    conferir(saida.out + saida.err)
    assert 'Argumentos inválidos' in saida.err


def test_sucesso_rotina_com_dados_e_resultado_brevo_privados(config, mundo, monkeypatch, capsys):
    for p in mundo['falsa'].dados['orders']:
        p['contact_name'] = DADOS[0]
        p['contact_phone'] = DADOS[2]
        p['shipping_address'] = {'address': DADOS[3]}
    monkeypatch.setattr(rotina, 'passo_brevo', lambda *a, **kw:
        (brevo.ResultadoBrevo(status=PRIVADO, detalhe=PRIVADO), []))
    rotina.rodar(config, pasta_api=mundo['pasta'], api=mundo['api'],
                 planilha=mundo['planilha'], carrinhos=False)
    saida = capsys.readouterr()
    conferir(saida.out + saida.err)
    assert '[1/5]' in saida.out and '[5/5]' in saida.out


def test_sucesso_previa_carrinho_preserva_csv_privado_sem_expor(monkeypatch, tmp_path, capsys):
    from painel_monstro import config as cfg
    from painel_monstro.coletor import nuvemshop_api as nuvem
    monkeypatch.setattr(cfg, 'RAIZ_PROJETO', str(tmp_path))
    monkeypatch.setattr(cfg, 'carregar', lambda: Config())
    monkeypatch.setattr(carrinhos, 'NuvemshopAPI', lambda c: object())
    monkeypatch.setattr(nuvem, 'Armazem', lambda: SimpleNamespace(registros=lambda r: {}))
    monkeypatch.setattr(nuvem, 'montar_tabelas', lambda *a: {})
    monkeypatch.setattr(carrinhos, 'buscar_carrinhos', lambda a: [{}])
    linha = SimpleNamespace(situacao='Contatar', modelo=PRIVADO, primeiro_nome=DADOS[0],
        telefone=DADOS[2], email=DADOS[1], valor=9876.54, mensagem=PRIVADO, link=DADOS[-1])
    monkeypatch.setattr(carrinhos, 'montar_fila', lambda *a: ([linha], Counter({PRIVADO: 1})))
    assert carrinhos.main(['--hoje']) == 0
    saida = capsys.readouterr()
    conferir(saida.out + saida.err)
    arquivo = tmp_path / 'dados/carrinhos/fila-de-hoje.csv'
    assert DADOS[1] in arquivo.read_text(encoding='utf-8-sig')


def test_sucesso_contatos_manuais_nao_expoe_argumentos(monkeypatch, capsys):
    monkeypatch.setattr(contatos_manuais, 'ler_emails_do_csv', lambda *a: [DADOS[1]])
    assert contatos_manuais.main(['--csv', PRIVADO, '--data', PRIVADO, '--origem', PRIVADO]) == 0
    saida = capsys.readouterr()
    conferir(saida.out + saida.err)
    assert '1 email(s)' in saida.out


def test_resposta_http_brevo_omitida():
    sessao = Sessao({('GET', '/account'): Resposta(400, {'message': PRIVADO})})
    with pytest.raises(brevo.ErroBrevo) as erro:
        brevo.Brevo('chave-falsa', sessao=sessao).conta()
    conferir(str(erro.value))
    conferir(erro.value.detalhe)
    assert '400' in str(erro.value)


def test_resposta_http_ga4_omitida():
    sessao = SimpleNamespace(post=lambda *a, **kw: SimpleNamespace(status_code=403, text=PRIVADO))
    with pytest.raises(ga4.ErroGA4) as erro:
        ga4.relatorio(sessao, '123', {'dimensions': [], 'metrics': []})
    conferir(str(erro.value))
    assert '403' in str(erro.value)


def test_processo_sem_traceback_em_stderr():
    codigo = ('from painel_monstro.log_publico import comando_seguro\n'
              '@comando_seguro\ndef main():\n'
              f'    raise RuntimeError({PRIVADO!r})\n'
              'raise SystemExit(main())\n')
    p = subprocess.run([sys.executable, '-c', codigo], capture_output=True, text=True,
                       cwd=Path(__file__).resolve().parents[1])
    assert p.returncode == 1
    conferir(p.stdout + p.stderr)
    assert p.stderr == ''


@pytest.mark.parametrize('falha', [False, True])
def test_so_cadastro_preserva_despacho_e_protege_erro(monkeypatch, capsys, falha):
    chamadas = []

    def cadastrar():
        chamadas.append('cadastro')
        if falha:
            raise RuntimeError(PRIVADO)

    def completa(**kw):
        pytest.fail('não executar rotina completa em --so-cadastro')

    monkeypatch.setattr(rotina, 'rodar_cadastro', cadastrar)
    monkeypatch.setattr(rotina, 'rodar', completa)
    monkeypatch.setattr(sys, 'argv', ['rotina', '--so-cadastro'])
    assert rotina.main() == (1 if falha else 0)
    assert chamadas == ['cadastro']
    saida = capsys.readouterr()
    conferir(saida.out + saida.err)


@pytest.mark.parametrize('status', [200, 403])
def test_script_ga4_sucesso_e_erro_sem_dados(monkeypatch, capsys, status):
    script = importlib.import_module('scripts.testar_ga4')
    monkeypatch.setattr(script, 'open', lambda *a, **kw: StringIO(''), raising=False)
    monkeypatch.setattr(script.service_account.Credentials, 'from_service_account_file',
                        lambda *a, **kw: SimpleNamespace(service_account_email=DADOS[1]))
    resposta = SimpleNamespace(ok=status == 200, status_code=status, text=PRIVADO,
        json=lambda: {'rows': [{'dimensionValues': [{'value': PRIVADO}],
                              'metricValues': [{'value': '1'}, {'value': '1'}, {'value': '9876.54'}]}]})
    monkeypatch.setattr(script, 'AuthorizedSession',
                        lambda c: SimpleNamespace(post=lambda *a, **kw: resposta))
    monkeypatch.setattr(sys, 'argv', ['testar_ga4', PRIVADO])
    assert script.main() == (0 if status == 200 else 1)
    saida = capsys.readouterr()
    conferir(saida.out + saida.err)


def test_resumo_raspadinha_sem_nome_campanha_premio_ou_valor(monkeypatch, capsys):
    from painel_monstro.saidas import raspadinha
    monkeypatch.setattr(raspadinha.r, 'resumo_do_sorteio',
                        lambda e: pd.DataFrame([{'item': PRIVADO, 'pessoas': 2}]))
    raspadinha._mostrar(PRIVADO, pd.DataFrame())
    saida = capsys.readouterr()
    conferir(saida.out + saida.err)
    assert '2' in saida.out


def test_cadastro_erro_drive_nao_expoe_identificador_ou_resposta(capsys):
    from painel_monstro.saidas import cadastro
    from tests.test_cadastro import Drive, lista_fotos

    class DrivePrivado(Drive):
        def guardar(self, *args):
            raise RuntimeError(PRIVADO)

    ajustadas, refs = cadastro.ajustar_fotos(PRIVADO, lista_fotos(), DrivePrivado())
    assert len(ajustadas) == 2 and all(not r['arquivo_drive_id'] for r in refs)
    saida = capsys.readouterr()
    conferir(saida.out + saida.err)
