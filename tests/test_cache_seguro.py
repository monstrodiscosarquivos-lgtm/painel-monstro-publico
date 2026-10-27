import base64
import io
import os
from pathlib import Path
import tarfile

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import pytest
import yaml

from painel_monstro import cache_seguro as c


def segredo():
    return base64.b64encode(os.urandom(32)).decode()


def test_chave_copiada_com_quebra_de_linha_mantem_os_32_bytes():
    key=segredo()
    assert c.chave('\r\n'+key+'\n')==c.chave(key) and len(c.chave(key))==32


def test_aes256_roundtrip_sem_texto_puro_e_nonce_aleatorio(tmp_path):
    pasta=tmp_path/'origem'; pasta.mkdir()
    pessoal=b'{"email":"cliente-ficticio@exemplo.com","nome":"Pessoa de teste"}'
    (pasta/'clientes.json').write_bytes(pessoal)
    (pasta/'sub').mkdir(); (pasta/'sub'/'estado.json').write_text('{}')
    arq=tmp_path/'cache.aes256'; key=segredo()
    assert c.criptografar(pasta,arq,key)
    antes=arq.read_bytes()
    assert pessoal not in antes and b'cliente-ficticio' not in antes and b'clientes.json' not in antes
    assert c.criptografar(pasta,arq,key) and arq.read_bytes()!=antes
    destino=tmp_path/'restaurado'
    assert c.descriptografar(arq,destino,key)
    assert (destino/'clientes.json').read_bytes()==pessoal and (destino/'sub'/'estado.json').read_text()=='{}'


@pytest.mark.parametrize('problema',['ausente','errada','invalida','adulterado','truncado'])
def test_cache_invalido_nao_extrai_nem_derruba(tmp_path,problema):
    pasta=tmp_path/'original'; pasta.mkdir(); (pasta/'x.json').write_text('conteudo-privado')
    key=segredo(); arq=tmp_path/'cache.aes256'; assert c.criptografar(pasta,arq,key)
    if problema=='ausente': key=''
    if problema=='errada': key=segredo()
    if problema=='invalida': key='nao-e-chave'
    if problema=='adulterado': arq.write_bytes(arq.read_bytes()[:-1]+b'x')
    if problema=='truncado': arq.write_bytes(c.MAGIC)
    destino=tmp_path/'vazio'
    assert not c.descriptografar(arq,destino,key) and not destino.exists()


def test_falta_chave_nao_salva_envelope_antigo_nem_expoe_logs(tmp_path,monkeypatch,capsys):
    pasta=tmp_path/'original'; pasta.mkdir(); (pasta/'x.json').write_text('Pessoa Teste cliente@exemplo.com')
    arq=tmp_path/'cache.aes256'; arq.write_bytes(b'antigo'); saida=tmp_path/'saida'
    monkeypatch.setattr(c,'PASTA',pasta); monkeypatch.setattr(c,'ARQUIVO',arq)
    monkeypatch.setenv('CACHE_KEY','chave-invalida-privada'); monkeypatch.setenv('GITHUB_OUTPUT',str(saida))
    assert c.main(['guardar'])==0 and not arq.exists() and saida.read_text()=='pronto=nao\n'
    assert c.main(['restaurar'])==0
    logs=capsys.readouterr(); assert 'chave-invalida' not in logs.out+logs.err and 'cliente@' not in logs.out+logs.err
    assert 'baixados novamente' in logs.out


@pytest.mark.parametrize('nome,tipo',[('../fora.json',tarfile.REGTYPE),('/fora.json',tarfile.REGTYPE),
    ('sub\\fora.json',tarfile.REGTYPE),('atalho',tarfile.SYMTYPE),('hardlink',tarfile.LNKTYPE)])
def test_arquivo_autenticado_ainda_rejeita_traversal_e_links(tmp_path,nome,tipo):
    m=io.BytesIO()
    with tarfile.open(fileobj=m,mode='w:gz') as tar:
        info=tarfile.TarInfo(nome); info.type=tipo
        if tipo==tarfile.REGTYPE: info.size=1; tar.addfile(info,io.BytesIO(b'x'))
        else: info.linkname='../fora'; tar.addfile(info)
    key=segredo(); nonce=os.urandom(12); arq=tmp_path/'cache.aes256'
    arq.write_bytes(c.MAGIC+nonce+AESGCM(c.chave(key)).encrypt(nonce,m.getvalue(),c.MAGIC))
    assert not c.descriptografar(arq,tmp_path/'destino',key) and not (tmp_path/'fora.json').exists()


def test_nao_sobrescreve_cache_local_se_chamado_fora_do_actions(tmp_path):
    origem=tmp_path/'origem'; origem.mkdir(); (origem/'x').write_text('remoto')
    destino=tmp_path/'destino'; destino.mkdir(); (destino/'x').write_text('local')
    arq=tmp_path/'cache.aes256'; key=segredo(); assert c.criptografar(origem,arq,key)
    assert not c.descriptografar(arq,destino,key) and (destino/'x').read_text()=='local'


@pytest.mark.parametrize('arquivo',list(Path('.github/workflows').glob('*.yml')))
def test_workflows_publicos_gatilhos_permissoes_e_cache_somente_cifrado(arquivo):
    wf=yaml.safe_load(arquivo.read_text(encoding='utf-8'))
    assert set(wf.get('on',wf.get(True)))<={'schedule','workflow_dispatch','repository_dispatch'}
    assert wf['permissions']=={'contents':'read'}
    for job in wf['jobs'].values():
        assert job.get('runs-on')=='ubuntu-latest'
        passos=job['steps']; en=[i for i,s in enumerate(passos) if 'cache_seguro guardar' in s.get('run','')]
        de=[i for i,s in enumerate(passos) if 'cache_seguro restaurar' in s.get('run','')]
        assert len(en)==len(de)==1
        rotina=next(i for i,s in enumerate(passos) if 'python -m painel_monstro.rotina' in s.get('run',''))
        assert de[0]<rotina<en[0]
        for i,s in enumerate(passos):
            assert 'upload-artifact' not in s.get('uses','')
            if 'actions/cache/' in s.get('uses',''):
                assert s['with']['path']=='dados/cache-publico/api.aes256'
                assert s['with']['key'].startswith('dados-api-aes256-v1-')
                if '/save@' in s['uses']: assert i>en[0] and "outputs.pronto == 'sim'" in s['if']
                else: assert i<de[0] and s['with']['restore-keys']=='dados-api-aes256-v1-'
            if s.get('uses','').startswith('actions/checkout@'):
                assert s['with']['persist-credentials'] is False
