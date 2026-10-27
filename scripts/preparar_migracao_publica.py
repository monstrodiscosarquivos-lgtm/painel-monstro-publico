"""Cópia local auditada, sem histórico, remote ou publicação automática (D-079)."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.auditar_publicacao import RAIZ, auditar


def git(raiz,*args):
    return subprocess.run(['git',*args],cwd=raiz,check=True,capture_output=True)


def preparar(destino,raiz=RAIZ):
    raiz=Path(raiz).resolve(); destino=Path(destino).absolute()
    permitido=raiz/'migracao-publica'
    if not destino.resolve().is_relative_to(permitido) or destino==permitido:
        raise ValueError('Destino precisa ser uma pasta nova dentro de migracao-publica/.')
    if destino.exists() or any(p.is_symlink() for p in (destino,*destino.parents)):
        raise ValueError('Destino já existe ou contém atalho; não sobrescrever.')
    arquivos,problemas=auditar(raiz,raiz)
    if problemas: raise ValueError('Auditoria bloqueou a cópia; corrigir antes de preparar.')
    destino.mkdir(parents=True)
    for caminho in arquivos:
        alvo=destino/caminho
        alvo.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(raiz/caminho,alvo)
    git(destino,'init','-b','main')
    git(destino,'add','--all')
    # Não herdar email/identidade pessoal nem hooks do repositório antigo.
    git(destino,'-c','user.name=Equipe Monstro Discos','-c','user.email=publicacao@exemplo.com',
        '-c','core.hooksPath=/dev/null','-c','commit.gpgsign=false','commit','-m','etapa 10: versão pública limpa e protegida (D-079)')
    assert git(destino,'rev-list','--all','--count').stdout.strip()==b'1'
    assert not git(destino,'remote').stdout.strip()
    _,problemas=auditar(destino,raiz)
    if problemas: raise ValueError('Revisão final bloqueou a cópia. Não enviar.')
    return git(destino,'rev-parse','--short','HEAD').stdout.decode().strip()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destino',default=str(RAIZ/'migracao-publica/painel-monstro-publico'))
    args=parser.parse_args()
    try:
        commit=preparar(args.destino)
    except Exception:
        print('Cópia não liberada. Confira a auditoria e use destino novo, sem atalhos.')
        return 1
    print('Cópia local preparada com um único commit: '+commit+'. Sem remote e sem push.')
    return 0


if __name__=='__main__': raise SystemExit(main())
