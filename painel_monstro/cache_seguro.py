"""D-079: só o envelope AES-256-GCM pode entrar no cache público do Actions.

CACHE_KEY: 32 bytes aleatórios codificados em base64, exclusivamente no Secret.
Falhas descartam o cache remoto, nunca expõem mensagem de exceção ou conteúdo.
Não chama API e não altera dados fora das pastas explícitas de cache.
"""
from __future__ import annotations

import argparse
import base64
import io
import os
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import tempfile

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b'PAINEL-CACHE-AES256-GCM-v1\x00'
ARQUIVO = Path('dados/cache-publico/api.aes256')
PASTA = Path('dados/api')
MAX_BYTES = 512 * 1024 * 1024
MAX_ARQUIVOS = 10000


def chave(valor: str) -> bytes:
    k = base64.b64decode(valor.strip(), validate=True)
    if len(k) != 32:
        raise ValueError('CACHE_KEY precisa de 32 bytes em base64')
    return k


def criptografar(pasta: Path, arquivo: Path, segredo: str) -> bool:
    """Em falha remove envelope antigo para jamais salvar cache não confirmado."""
    try:
        arquivo.unlink(missing_ok=True)
        k = chave(segredo)
        if not pasta.is_dir() or pasta.is_symlink():
            return False
        memoria = io.BytesIO()
        arquivos = sorted(pasta.rglob('*'))
        if len(arquivos) > MAX_ARQUIVOS:
            return False
        total = 0
        with tarfile.open(fileobj=memoria, mode='w:gz') as tar:
            for p in arquivos:
                if p.is_symlink():
                    raise ValueError('atalhos não entram no cache')
                if p.is_dir():
                    continue
                if not p.is_file():
                    raise ValueError('arquivo especial')
                total += p.stat().st_size
                if total > MAX_BYTES:
                    raise ValueError('cache grande demais')
                tar.add(p, arcname=p.relative_to(pasta).as_posix(), recursive=False)
        nonce = os.urandom(12)
        envelope = MAGIC + nonce + AESGCM(k).encrypt(nonce, memoria.getvalue(), MAGIC)
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_bytes(envelope)
        return True
    except Exception:
        try:
            arquivo.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def descriptografar(arquivo: Path, pasta: Path, segredo: str) -> bool:
    """Autentica tudo antes de extrair. Sem chave/cache válido, o checkout segue vazio.

    Não apaga um cache local pré-existente: o Actions começa num checkout limpo;
    fora dele, recusa sobrescrever arquivos locais.
    """
    temporaria = None
    try:
        k = chave(segredo)
        if arquivo.stat().st_size > MAX_BYTES or pasta.is_symlink():
            return False
        if pasta.exists() and any(pasta.iterdir()):
            return False
        envelope = arquivo.read_bytes()
        if not envelope.startswith(MAGIC):
            return False
        pos = len(MAGIC)
        dados = AESGCM(k).decrypt(envelope[pos:pos+12], envelope[pos+12:], MAGIC)
        pasta.parent.mkdir(parents=True, exist_ok=True)
        temporaria = Path(tempfile.mkdtemp(prefix='cache-restaurando-', dir=pasta.parent))
        total = 0
        nomes = set()
        with tarfile.open(fileobj=io.BytesIO(dados), mode='r:gz') as tar:
            for n, membro in enumerate(tar, 1):
                nome = PurePosixPath(membro.name)
                if (n > MAX_ARQUIVOS or not membro.isfile() or nome.is_absolute()
                        or '..' in nome.parts or '\\' in membro.name or ':' in membro.name
                        or membro.name in nomes or membro.size < 0):
                    raise ValueError('cache inválido')
                nomes.add(membro.name)
                total += membro.size
                if total > MAX_BYTES:
                    raise ValueError('cache grande demais')
                destino = temporaria.joinpath(*nome.parts)
                destino.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(membro) as origem, destino.open('wb') as saida:
                    shutil.copyfileobj(origem, saida)
        if pasta.exists():
            pasta.rmdir()  # somente diretório vazio, nunca remoção recursiva de cache local
        temporaria.replace(pasta)
        temporaria = None
        return True
    except Exception:
        return False
    finally:
        if temporaria is not None:
            try:
                shutil.rmtree(temporaria)  # diretório único criado acima, dentro da pasta de cache
            except OSError:
                pass  # nunca expor caminhos/dados em traceback de limpeza


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Cache autenticado para Actions público')
    parser.add_argument('acao', choices=['restaurar', 'guardar'])
    args = parser.parse_args(argv)
    segredo = os.environ.get('CACHE_KEY', '')
    if args.acao == 'restaurar':
        ok = descriptografar(ARQUIVO, PASTA, segredo)
        print('Cache autenticado restaurado.' if ok else 'Cache indisponível; os dados serão baixados novamente.')
    else:
        ok = criptografar(PASTA, ARQUIVO, segredo)
        print('Cache criptografado preparado.' if ok else 'Cache não será salvo; próxima rodada baixa novamente.')
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as out:
                out.write('pronto=' + ('sim' if ok else 'nao') + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
