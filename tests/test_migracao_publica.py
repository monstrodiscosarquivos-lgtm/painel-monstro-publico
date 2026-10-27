from pathlib import Path
import subprocess

import pytest

from scripts import preparar_migracao_publica as m
from scripts import auditar_publicacao as a
from scripts import auditar_repositorio as historico


def repo(tmp_path):
    raiz=tmp_path/'origem'; raiz.mkdir()
    m.git(raiz,'init','-b','main')
    (raiz/'codigo.py').write_text('print("exemplo")\n')
    (raiz/'dados').mkdir(); (raiz/'dados'/'privado.txt').write_text('não copiar')
    (raiz/'.env').write_text('CHAVE=apenas-local')
    (raiz/'nao-rastreado.txt').write_text('não copiar')
    m.git(raiz,'add','codigo.py')
    for n in range(2):
        (raiz/'codigo.py').write_text(f'print("exemplo {n}")\n')
        m.git(raiz,'add','codigo.py')
        m.git(raiz,'-c','user.name=Autor Ficticio','-c','user.email=autor@exemplo.com',
              '-c','commit.gpgsign=false','commit','-m','exemplo')
    return raiz


def test_exportador_so_copia_versionados_sem_historico_remote_ou_identidade_pessoal(tmp_path):
    raiz=repo(tmp_path); destino=raiz/'migracao-publica'/'limpo'
    assert m.git(raiz,'rev-list','--all','--count').stdout.strip()==b'2'
    commit=m.preparar(destino,raiz)
    assert commit and m.git(destino,'rev-list','--all','--count').stdout.strip()==b'1'
    assert not m.git(destino,'remote').stdout.strip()
    assert set(a.arquivos_versionados(destino))=={'codigo.py'}
    assert not (destino/'.env').exists() and not (destino/'dados').exists()
    assert not (destino/'nao-rastreado.txt').exists()
    assert b'publicacao@exemplo.com' in m.git(destino,'log','-1','--format=%ae').stdout
    assert m.git(raiz,'rev-list','--all','--count').stdout.strip()==b'2'


def test_exportador_bloqueia_email_pessoal_sem_criar_destino(tmp_path):
    raiz=repo(tmp_path); (raiz/'codigo.py').write_text('email="pessoa@'+'gmail.com"')
    destino=raiz/'migracao-publica'/'limpo'
    with pytest.raises(ValueError,match='Auditoria'): m.preparar(destino,raiz)
    assert not destino.exists()


def test_exportador_nao_sobrescreve_destino_ou_sai_da_pasta(tmp_path):
    raiz=repo(tmp_path)
    with pytest.raises(ValueError,match='Destino'): m.preparar(tmp_path/'outro',raiz)
    destino=raiz/'migracao-publica'/'ja-existe'; destino.mkdir(parents=True)
    with pytest.raises(ValueError,match='existe'): m.preparar(destino,raiz)


def test_auditor_identifica_nome_completo_do_cache_privado_sem_imprimir_nome(tmp_path,capsys):
    raiz=repo(tmp_path); cache=raiz/'dados/api'; cache.mkdir()
    (cache/'clientes.json').write_text('[{"name":"Pessoa Ficticia Confidencial","email":"pessoa@exemplo.com"}]')
    (raiz/'codigo.py').write_text('cliente="Pessoa Ficticia Confidencial"')
    arquivos,problemas=a.auditar(raiz,raiz)
    assert arquivos==['codigo.py'] and any('dado de cliente' in x for x in problemas)
    assert all('Pessoa Ficticia Confidencial' not in x for x in problemas)
    assert not capsys.readouterr().out


def test_auditor_de_email_confere_o_endereco_completo_e_nao_so_sufixo():
    assert historico.EMAIL.findall('nome pessoa@'+'gmail.com fim')==['pessoa@'+'gmail.com']
    assert any('email' in p for p in historico.examinar('exemplo.py',b'pessoa@'+b'gmail.com',{},'teste'))
    assert not historico.examinar('exemplo.py',b'cliente@exemplo.com',{},'teste')
