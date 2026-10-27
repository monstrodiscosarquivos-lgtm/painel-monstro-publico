"""Famílias de gênero (AGENTS.md, "Famílias de gênero"): Rock e Prog, Brasil, Metal e Groove.

Definidas pelas categorias do produto e, na falta, por palavras-chave de artistas. As listas vêm de
`referencia/reativacao.py` e devem ficar iguais a ela.
"""
from __future__ import annotations

from collections import Counter

import pandas as pd

FAMILIAS = {
    'Rock e Prog': ['Classic Rock', 'Rock Clássico', 'Rock Progressivo', 'Psicodelico', 'Rock / Pop Internacional', 'Indie', 'New Wave', 'Folk'],
    'Brasil': ['Música Popular Brasileira', 'MPB', 'Rock / Pop Nacional', 'Regional', 'Samba', 'Sertanejo'],
    'Metal': ['Hard Rock', 'Metal'],
    'Groove': ['Disco / Funk / Soul', 'Jazz', 'Blues', 'Rap', 'Hip Hop', 'Reggae', 'Discoteca'],
}
KW = {
    'Metal': ['iron maiden', 'metallica', 'black sabbath', 'slipknot', 'sepultura', 'megadeth', 'judas priest', 'motorhead', 'motörhead', 'slayer', 'pantera', 'ozzy', ' dio ', 'saxon', 'kiss', 'ac/dc', 'helloween', 'angra', 'manowar', 'scorpions', 'deep purple', 'whitesnake', 'guns n', 'anthrax', 'korn', 'system of a down', 'rammstein', 'metal', 'venom', 'accept', 'dream theater', 'nightwish', 'blind guardian', 'rainbow', 'krisiun', 'viper', 'def leppard'],
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
