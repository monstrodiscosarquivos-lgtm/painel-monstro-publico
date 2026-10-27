"""Confere, antes de enviar ao GitHub, que nenhum dado de cliente nem segredo está no repositório.

Uso (na pasta do projeto):
    python scripts/auditar_repositorio.py

Olha os arquivos versionados e TODO o histórico do git (um segredo apagado depois continua no histórico).
Procura: valores reais do .env e da chave do Google, chaves privadas, emails, CPF, telefones, arquivos de
dados (csv, json, env, etc.) e o conteúdo das planilhas .xlsx. Só mostra onde achou e de que tipo,
nunca o valor. Termina com código 0 se está limpo e 1 se achou algo.
"""
from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
import zipfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PADROES = {
    'chave privada': re.compile(r'BEGIN (RSA |EC )?PRIVATE KEY|"private_key"\s*:'),
    'CPF': re.compile(r'\b\d{3}\.\d{3}\.\d{3}-\d{2}\b'),
    'CNPJ': re.compile(r'\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b'),
    'telefone': re.compile(r'(?<!\d)(\+?55\s?)?\(?\d{2}\)?\s?9\d{4}[-\s]?\d{4}(?!\d)'),
    'token longo': re.compile(r'\b[a-f0-9]{40}\b'),
    'chave de API': re.compile(r'\b(xkeysib-|sk-|AIza|ghp_|github_pat_)[A-Za-z0-9_\-]{10,}'),
}
EMAIL = re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+')
# Emails que podem aparecer: exemplos de teste e endereços de contas de serviço (não são segredo).
EMAIL_PERMITIDO = re.compile(r'@(exemplo\.com|e\.com|x\.com|exemplo\.com\.br|example\.(com|invalid)|projeto\.iam\.gserviceaccount\.com)$|^(nome|email|seu)@|^contato@monstrodiscos\.com\.br$', re.I)
# Valores inventados que os testes e a planilha-modelo usam. Qualquer outro CPF ou telefone é problema.
FICTICIOS = {'62999990000', '+55 62 99999-0001', '+55 11 98888-0002', '5562999990000', '+5562999990000', '62999990000', '+55 (62) 99999-0000', '+55 62 99999-0000', '5562991234567', '+5562991234567', '+55 (62) 99123-4567', '+55 62 99123-4567', '62991234567'}
# Telefones de teste da série 62 99999-000X (X de 0 a 9), em todas as formas de escrever.
FICTICIOS |= {f'{p}{n}' for n in (f'6299999000{i}' for i in range(10)) for p in ('', '55', '+55')}
FICTICIOS |= {f'{p}(62) 99999-000{i}' for i in range(10) for p in ('', '+55 ', '55 ')} | {f'+55 62 99999-000{i}' for i in range(10)}
FICTICIOS |= {f'{p}{ddd}{sep}99999-000{i}' for i in range(10) for p in ('', '+55 ', '55 ', '+55', '55') for ddd in ('62', '(62)') for sep in (' ', '')}
FICTICIOS |= {'xkeysib-CHAVE-SECRETA-DE-TESTE-123456'}  # chave inventada que um teste usou antes de ser trocada
FICTICIOS |= {'5562999991234', '556230000000', '6230000000'}  # fixtures explícitas de privacidade/telefone fixo
# Telefone comercial já publicado nos modelos promocionais, não dado de cliente.
CONTATOS_PUBLICOS_LOJA = {'5562984884142', '62984884142', '+5562984884142'}
CPF_FICTICIO = re.compile(r'^(\d)\1{2}\.\1{3}\.\1{3}-\1{2}$')  # 111.111.111-11 e parecidos
EXTENSOES_DE_DADOS =re.compile(r'\.(csv|json|env|key|pem|p12|db|sqlite|sqlite3|xls|parquet)$', re.I)
PASTAS_PROIBIDAS = re.compile(r'^(dados|credenciais)/|(^|/)\.env$')
EXCECOES_DE_ARQUIVO = {'referencia/cadastro_piloto/cantos-2026-10-15.json'}  # só nomes de fotos e coordenadas


def git(*args: str) -> bytes:
    return subprocess.run(['git', *args], cwd=RAIZ, check=True, capture_output=True).stdout


def valores_secretos() -> dict[str, str]:
    """Valores reais que nunca podem aparecer: do .env e da chave do Google. Nome do segredo -> valor."""
    achados: dict[str, str] = {}
    try:
        from dotenv import dotenv_values
        env = dotenv_values(os.path.join(RAIZ, '.env'))
    except Exception:
        env = {}
    # O ID da loja não é segredo (aparece nos endereços da API e no AGENTS.md); não entra na lista.
    for chave in ('NUVEMSHOP_TOKEN', 'BREVO_API_KEY', 'META_ADS_TOKEN', 'DISCOGS_TOKEN', 'PLANILHA_ID', 'CACHE_KEY', 'GITHUB_TOKEN', 'SEGREDO'):
        valor = (env.get(chave) or '').strip()
        if len(valor) >= 6:
            achados[chave] = valor
    caminho = os.path.join(RAIZ, (env.get('GOOGLE_SERVICE_ACCOUNT_FILE') or 'credenciais/google-service-account.json').strip())
    if os.path.exists(caminho):
        try:
            dados = json.load(open(caminho, encoding='utf-8'))
            for campo in ('private_key', 'private_key_id', 'client_id', 'client_email'):
                if dados.get(campo):
                    achados[f'chave do Google ({campo})'] = str(dados[campo])
        except (OSError, ValueError):
            pass
    return achados


def texto_do_arquivo(caminho: str, conteudo: bytes) -> str:
    """Texto pesquisável. Planilhas .xlsx são zips de XML: lê todo o texto de dentro."""
    if caminho.lower().endswith(('.xlsx', '.xlsm')):
        try:
            with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
                return '\n'.join(z.read(n).decode('utf-8', 'ignore') for n in z.namelist() if n.endswith('.xml'))
        except zipfile.BadZipFile:
            return ''
    return conteudo.decode('utf-8', 'ignore')


def examinar(caminho: str, conteudo: bytes, segredos: dict[str, str], onde: str) -> list[str]:
    problemas = []
    if PASTAS_PROIBIDAS.search(caminho):
        problemas.append(f'{onde}: {caminho}: arquivo de pasta que nunca vai para o git')
    elif (EXTENSOES_DE_DADOS.search(caminho) or caminho.lower().endswith(('.xlsx', '.xlsm'))) and caminho not in EXCECOES_DE_ARQUIVO:
        problemas.append(f'{onde}: {caminho}: arquivo de dados ({os.path.splitext(caminho)[1]})')
    texto = texto_do_arquivo(caminho, conteudo)
    for nome, valor in segredos.items():
        if valor in texto:
            problemas.append(f'{onde}: {caminho}: contém o valor real de {nome}')
    for nome, padrao in PADROES.items():
        achados = {m.group(0).strip() for m in padrao.finditer(texto)}
        achados = {a for a in achados if a not in FICTICIOS and a not in CONTATOS_PUBLICOS_LOJA and not (nome == 'CPF' and CPF_FICTICIO.match(a))}
        if achados:
            problemas.append(f'{onde}: {caminho}: parece conter {nome}')
    emails = {m.group(0) for m in EMAIL.finditer(texto)}
    ruins = [e for e in emails if not EMAIL_PERMITIDO.search(e)]
    if ruins:
        problemas.append(f'{onde}: {caminho}: {len(ruins)} email(s) que não são de exemplo')
    return problemas


def main() -> int:
    segredos = valores_secretos()
    problemas: list[str] = []

    # 1. arquivos versionados agora
    arquivos = [a.decode('utf-8') for a in git('ls-files', '-z').split(b'\0') if a]
    for caminho in arquivos:
        if re.search(r'recovery[-_ ]?codes|backup[-_ ]?codes|\.pem$|\.p12$|(^|/)id_rsa', caminho, re.I):
            problemas.append(f'arquivo atual: {caminho}: nome de arquivo de segredo (códigos de recuperação ou chave) não pode ser versionado')
            continue
        with open(os.path.join(RAIZ, caminho), 'rb') as arq:
            problemas += examinar(caminho, arq.read(), segredos, 'arquivo atual')

    # 2. todo o histórico (cada versão de cada arquivo em cada commit)
    commits = git('rev-list', '--all').decode().split()
    vistos = set()
    for commit in commits:
        for linha in git('ls-tree', '-r', '-z', commit).split(b'\0'):
            if not linha:
                continue
            meta, caminho = linha.split(b'\t', 1)
            sha = meta.split()[2].decode()
            if sha in vistos:
                continue
            vistos.add(sha)
            problemas += examinar(caminho.decode('utf-8'), git('cat-file', 'blob', sha), segredos, f'histórico {commit[:7]}')

    # 3. a mensagem dos commits também vai para o GitHub
    mensagens = git('log', '--all', '--format=%B').decode('utf-8', 'ignore')
    for nome, valor in segredos.items():
        if valor in mensagens:
            problemas.append(f'mensagem de commit: contém o valor real de {nome}')

    # 4. .gitignore cobre o essencial
    ignorados = subprocess.run(['git', 'check-ignore', '.env', 'dados/x.csv', 'credenciais/x.json', 'dados/api/pedidos.json'],
                               cwd=RAIZ, capture_output=True, text=True).stdout.split()
    for caminho in ('.env', 'dados/x.csv', 'credenciais/x.json', 'dados/api/pedidos.json'):
        if caminho not in ignorados:
            problemas.append(f'.gitignore não protege {caminho}')

    unicos = list(dict.fromkeys(problemas))
    print(f'Conferidos: {len(arquivos)} arquivos atuais, {len(vistos)} versões de arquivos no histórico ({len(commits)} commits), '
          f'{len(segredos)} valores secretos procurados.')
    if unicos:
        print(f'\nENCONTREI {len(unicos)} PROBLEMA(S). NÃO ENVIE AO GITHUB:')
        for p in unicos:
            print(f'  - {p}')
        return 1
    print('\nLIMPO: nenhum dado de cliente, segredo ou arquivo de dados no repositório.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
