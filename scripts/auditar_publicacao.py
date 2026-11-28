"""D-079: audita só arquivos de git ls-files, sem imprimir dados encontrados.

Combina regras do auditor histórico com comparação literal de nomes completos,
emails e telefones disponíveis no cache privado local. Não substitui revisão
manual: primeiros nomes e endereços sem base comparativa exigem leitura humana.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import auditar_repositorio as antigo

RAIZ = Path(__file__).resolve().parents[1]


def arquivos_versionados(raiz):
    resultado=subprocess.run(['git','ls-files','-z'],cwd=raiz,check=True,capture_output=True)
    return [p.decode('utf-8') for p in resultado.stdout.split(b'\0') if p]


def termos_clientes(raiz_privada):
    arquivo=Path(raiz_privada)/'dados/api/clientes.json'
    if not arquivo.exists(): return {}
    clientes=json.loads(arquivo.read_text(encoding='utf-8'))
    termos={}
    for cliente in clientes:
        for campo in ('name','email','phone'):
            valor=str(cliente.get(campo) or '').strip()
            if valor.lower()=='contato@monstrodiscos.com.br': continue  # contato institucional público da loja
            if campo=='name' and valor.casefold()=='monstro discos': continue  # cadastro da própria loja, não cliente
            if campo=='name' and (len(valor.split())<2 or len(valor)<7): continue
            if len(valor)<7: continue
            termos[valor.casefold()]=campo
    return termos


def cupons_privados_env(valor=None):
    """Lê códigos ou prefixos privados da variável opcional CUPONS_PRIVADOS (sem expô-los nos erros)."""
    bruto = os.environ.get('CUPONS_PRIVADOS', '') if valor is None else valor
    codigos = []
    for parte in re.split(r'[,;\n]+', bruto or ''):
        item = parte.split('=', 1)[0].strip()
        if len(item) >= 3:
            codigos.append(item.casefold())
    return list(dict.fromkeys(codigos))


def auditar(raiz=RAIZ,raiz_privada=RAIZ):
    raiz=Path(raiz); segredos=antigo.valores_secretos()
    termos=termos_clientes(raiz_privada); cupons_privados=cupons_privados_env(); problemas=[]
    arquivos=arquivos_versionados(raiz)
    for caminho in arquivos:
        p=raiz/caminho
        if p.is_symlink() or not p.resolve().is_relative_to(raiz.resolve()):
            problemas.append(f'{caminho}: link ou caminho externo proibido'); continue
        conteudo=p.read_bytes()
        problemas+=antigo.examinar(caminho,conteudo,segredos,'versão pública')
        texto=antigo.texto_do_arquivo(caminho,conteudo)
        for n,linha in enumerate(texto.splitlines(),1):
            comparavel=linha.casefold()
            if any(termo in comparavel for termo in termos):
                problemas.append(f'{caminho}:{n}: coincide com dado de cliente do cache privado')
            if cupons_privados and any(cod in comparavel for cod in cupons_privados):
                problemas.append(f'{caminho}:{n}: contém código de cupom privado')
            if re.search(r'https://docs\.google\.com/spreadsheets/d/[A-Za-z0-9_-]{25,}',linha):
                problemas.append(f'{caminho}:{n}: endereço concreto de planilha privada')
            if re.search(r'https://drive\.google\.com/(?:drive/folders|file/d)/[A-Za-z0-9_-]{25,}',linha):
                problemas.append(f'{caminho}:{n}: endereço concreto de arquivo/pasta privada')
        if caminho.startswith(('.git/','dados/','credenciais/')) or Path(caminho).name=='.env':
            problemas.append(f'{caminho}: arquivo privado')
    return arquivos,list(dict.fromkeys(problemas))


def main():
    arquivos,problemas=auditar()
    print(f'Arquivos versionados conferidos: {len(arquivos)}. Problemas: {len(problemas)}.')
    for p in problemas: print(p)  # caminho/tipo, nunca valores de cliente ou chaves
    return int(bool(problemas))


if __name__=='__main__': raise SystemExit(main())
