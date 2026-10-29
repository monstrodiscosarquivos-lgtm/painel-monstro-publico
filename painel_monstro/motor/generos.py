"""Famílias de gênero (AGENTS.md, "Famílias de gênero"): Rock e Prog, Brasil, Metal e Groove.

Definidas pelas categorias do produto e, na falta, por palavras-chave de artistas. As listas vêm de
`referencia/reativacao.py` e devem ficar compatíveis com ela.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any

import pandas as pd

FAMILIAS = {
    'Rock e Prog': ['Classic Rock', 'Rock Clássico', 'Rock Progressivo', 'Psicodelico', 'Rock / Pop Internacional', 'Indie', 'New Wave', 'Folk'],
    'Brasil': ['Música Popular Brasileira', 'MPB', 'Rock / Pop Nacional', 'Regional', 'Samba', 'Sertanejo'],
    'Metal': ['Hard Rock', 'Metal'],
    'Groove': ['Disco / Funk / Soul', 'Jazz', 'Blues', 'Rap', 'Hip Hop', 'Reggae', 'Discoteca'],
}

SUBCATEGORIAS = {
    'Hard Rock / Heavy Metal / Metal': ['hard rock', 'heavy metal', 'metal'],
    'MPB - Música Popular Brasileira': ['mpb', 'musica popular brasileira'],
    'Rock / Pop Nacional': ['rock / pop nacional', 'rock nacional', 'pop nacional', 'rock br'],
    'Samba / Pagode': ['samba', 'pagode'],
    'Jazz / Blues': ['jazz', 'blues'],
    'Sertanejo': ['sertanejo'],
    'Classic Rock': ['classic rock', 'rock classico'],
    'Rock Progressivo / Psicodelico': ['rock progressivo', 'prog rock', 'psicodelico'],
    'Indie / Rock Alternativo': ['indie', 'rock alternativo'],
    'Rock / Pop Internacional': ['rock / pop internacional'],
    'Disco / Funk / Soul': ['disco / funk / soul', 'funk / soul', 'funk', 'soul', 'disco'],
    'Discoteca / Eletronico / Dance / House': ['discoteca', 'eletronico', 'dance', 'house'],
    'Folk / Country': ['folk', 'country'],
    'New Wave / Synth Pop': ['new wave', 'synth pop'],
    'Rap / Hip Hop': ['rap', 'hip hop'],
    'Reggae / Dub': ['reggae', 'dub'],
    'Regional': ['regional'],
}

KW = {
    'Metal': ['iron maiden', 'metallica', 'black sabbath', 'slipknot', 'sepultura', 'megadeth', 'judas priest', 'motorhead', 'motörhead', 'slayer', 'pantera', 'ozzy', ' dio ', 'saxon', 'kiss', 'ac/dc', 'helloween', 'angra', 'manowar', 'scorpions', 'deep purple', 'whitesnake', 'guns n', 'anthrax', 'korn', 'system of a down', 'rammstein', 'metal', 'venom', 'accept', 'dream theater', 'nightwish', 'blind guardian', 'rainbow', 'krisiun', 'viper', 'def leppard', 'violator', 'korzus', 'torture squad', 'dorsal atlantica', 'dorsal atlântica', 'nervosa', 'crypta', 'shaman'],
    'Rock e Prog': ['pink floyd', ' yes ', 'genesis', 'king crimson', ' rush ', 'jethro tull', 'emerson', 'camel', 'mutantes', 'supertramp', 'alan parsons', 'marillion', 'led zeppelin', 'beatles', 'rolling stones', 'the who', 'fleetwood', 'eagles', 'creedence', 'doors', 'hendrix', 'dylan', 'queen', 'elton john', 'bowie', 'santana', 'dire straits', 'clapton', 'neil young', 'steely dan', 'kinks', 'aerosmith', 'nirvana', 'pearl jam', 'radiohead', 'pixies', 'the cure', 'smiths', 'new order', 'depeche', 'kraftwerk', 'u2', 'the cult', 'joy division', 'talking heads'],
    'Brasil': ['chico buarque', 'caetano', 'gilberto gil', 'gal costa', 'bethânia', 'bethania', 'milton nascimento', 'elis regina', 'djavan', 'belchior', 'jobim', 'vinicius', 'ivan lins', 'emílio santiago', 'fagner', 'zé ramalho', 'alceu', 'novos baianos', 'raul seixas', 'tim maia', 'jorge ben', 'benjor', 'cartola', 'paulinho da viola', 'clara nunes', 'alcione', 'beth carvalho', 'caymmi', 'luiz gonzaga', 'legião', 'titãs', 'paralamas', 'barão vermelho', 'ira!', 'ultraje', 'rita lee', 'blitz', 'cazuza', 'inocentes', 'samba', 'choro', 'bossa'],
    'Groove': ['james brown', 'stevie wonder', 'marvin gaye', 'earth, wind', 'prince', 'michael jackson', 'motown', 'aretha', 'barry white', 'donna summer', 'bee gees', 'boney m', 'miles davis', 'coltrane', 'jazz', 'blues', 'soul', 'funk', 'disco'],
}


def _sem_acento(texto: str) -> str:
    """Minúsculas e sem acento, para casar "Emilio" com "Emílio"."""
    import unicodedata
    return unicodedata.normalize('NFKD', str(texto)).encode('ascii', 'ignore').decode().lower()


def familias(categorias, nome) -> set[str]:
    """Famílias de um produto pelas categorias da loja e pelo nome (artista)."""
    cat = _sem_acento('' if categorias is None or (isinstance(categorias, float) and pd.isna(categorias)) else str(categorias))
    n = ' ' + _sem_acento('' if nome is None or (isinstance(nome, float) and pd.isna(nome)) else str(nome)) + ' '
    achadas = {f for f, ks in FAMILIAS.items() if any(_sem_acento(k) in cat for k in ks)}
    achadas |= {f for f, ks in KW.items() if any(_sem_acento(k) in n for k in ks)}
    return achadas


def familia_principal(lista_de_familias: list[set[str]]) -> str | None:
    """A família que mais aparece nos discos de um cliente (empate: a primeira na ordem de FAMILIAS)."""
    cont: Counter = Counter()
    for fs in lista_de_familias:
        cont.update(fs)
    if not cont:
        return None
    ordem = list(FAMILIAS)
    return sorted(cont, key=lambda f: (-cont[f], ordem.index(f)))[0]


def subcategorias(categorias: Any) -> set[str]:
    """Subcategorias de gênero de um produto pelas categorias da loja."""
    cat = _sem_acento('' if categorias is None or (isinstance(categorias, float) and pd.isna(categorias)) else str(categorias))
    achadas = set()
    for sub, ks in SUBCATEGORIAS.items():
        if any(_sem_acento(k) in cat for k in ks):
            achadas.add(sub)
    return achadas


def subcategoria_principal(lista_de_subcategorias: list[set[str]]) -> str | None:
    """A subcategoria que mais aparece nos discos de um cliente."""
    cont: Counter = Counter()
    for subs in lista_de_subcategorias:
        cont.update(subs)
    if not cont:
        return None
    ordem = list(SUBCATEGORIAS)
    return sorted(cont, key=lambda s: (-cont[s], ordem.index(s) if s in ordem else 999))[0]


def generos_por_kw(nome: Any) -> set[str]:
    """Famílias achadas pelas palavras-chave de artistas no nome."""
    n = ' ' + _sem_acento('' if nome is None or (isinstance(nome, float) and pd.isna(nome)) else str(nome)) + ' '
    return {f for f, ks in KW.items() if any(_sem_acento(k) in n for k in ks)}


def tem_genero_confiavel(categorias: Any, nome: Any) -> bool:
    """True se o produto tem subcategoria de gênero OU artista nas listas KW."""
    return bool(subcategorias(categorias)) or bool(generos_por_kw(nome))


def artista_do_disco(nome: Any) -> str:
    """Extrai o nome do artista limpo e sem acento."""
    n = _sem_acento(str(nome or ''))
    n = re.sub(r'^(?:lp/ep|mini-lp|lp|cd|dvd|box|compacto-?|ep|fita(?:\s+k7)?|k7)[\s:\-–]*', '', n).strip()
    n = re.sub(r'\([^)]*\)', ' ', n).strip(' -–—:')
    for sep in (': ', ' - ', ' – ', ' — '):
        if sep in n:
            return n.split(sep)[0].strip()
    return n.strip()
