"""Lista de garimpo (Etapa 8): pedidos de disco que viram aviso de WhatsApp quando o disco chega.

Os pedidos vêm de dois lugares da Planilha Google, lidos juntos a cada rodada:
- aba `desejos`: digitada à mão (por exemplo, a Mariana anota o que o cliente respondeu no WhatsApp);
- aba criada pelo Google Forms ("Respostas ao formulário 1"): o formulário público de garimpo.

Colunas aceitas (o cabeçalho é reconhecido pelo texto, não pela posição):
  data: "Carimbo de data/hora" ou `data`; contato: "Seu nome" e "Seu WhatsApp com DDD" (ou a pergunta antiga, junta,
  "Seu nome e WhatsApp com DDD"; na aba desejos, `telefone`, `nome`, `email`);
  artista: "Artista ou banda"; disco: "Qual disco você procura?"; formato (opcional): "Formato" (LP, CD, Compacto, Fita K7, DVD,
  Camiseta ou Qualquer formato); `status`: escreva "Avisado" para parar de avisar. Sem a pergunta Formato, vale o que estiver escrito no
  pedido ("CD ...", "LP ...", "vinil"); sem nada, qualquer formato serve.

O aviso (modelo ALERTA_GARIMPO) entra na fila única de WhatsApp (`fila_unica.alertas_garimpo`): nunca é enviado
sozinho. Um pedido gera no máximo um aviso (depois que a Mariana marca o primeiro toque, o pedido é considerado atendido).
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

import pandas as pd

from painel_monstro.saidas import carrinhos as c

PREFIXO_DAS_ABAS_DO_FORMULARIO = ('respostas ao formul', 'form responses', 'respostas do formul')
COLUNAS = ['email', 'telefone', 'nome', 'desejo', 'data', 'status', 'origem', 'formato']
# Palavra do pedido ou do nome do produto -> formato. O nome do produto começa pelo formato ("LP ...", "CD ...").
FORMATOS = {'lp': 'lp', 'lps': 'lp', 'vinil': 'lp', 'vinis': 'lp', 'vinyl': 'lp', 'cd': 'cd', 'cds': 'cd', 'compacto': 'compacto',
            'compactos': 'compacto', 'k7': 'k7', 'fita': 'k7', 'fitas': 'k7', 'cassete': 'k7', 'dvd': 'dvd', 'box': 'box',
            'camiseta': 'camiseta', 'camisetas': 'camiseta', 'camisa': 'camiseta', 'camisas': 'camiseta', 'merch': 'camiseta'}
QUALQUER = ('qualquer', 'tanto faz', 'todos')


def _palavras(texto: Any) -> list[str]:
    return re.findall(r'[a-z0-9]+', _sem_acento(texto))


def formato_do_produto(nome: Any) -> str:
    """Formato pelo começo do nome do produto: "LP Violator ..." -> "lp". Vazio se não reconhecer."""
    p = _palavras(nome)
    return FORMATOS.get(p[0], '') if p else ''


def formato_do_pedido(formato: Any, desejo: Any) -> str:
    """Formato pedido: a resposta da pergunta Formato vale primeiro; sem ela, a primeira palavra de formato do texto
    ("CD Jupiter Apple ..." -> "cd"). "Qualquer formato" ou nada = vazio (qualquer um serve)."""
    f = _sem_acento(formato)
    if f:
        if any(q in f for q in QUALQUER):
            return ''
        for w in _palavras(f):
            if w in FORMATOS:
                return FORMATOS[w]
    for w in _palavras(desejo):
        if w in FORMATOS:
            return FORMATOS[w]
    return ''


def _sem_acento(texto: Any) -> str:
    return unicodedata.normalize('NFKD', str(texto or '')).encode('ascii', 'ignore').decode().lower().strip()


def eh_aba_do_formulario(titulo: str) -> bool:
    return _sem_acento(titulo).startswith(tuple(_sem_acento(p) for p in PREFIXO_DAS_ABAS_DO_FORMULARIO))


def separar_contato(texto: Any) -> tuple[str, str]:
    """"Ana 62 99999-0000" -> (nome "Ana", telefone "5562999990000"). Sem telefone válido, o telefone vem vazio."""
    bruto = str(texto or '').strip()
    achados = re.findall(r'\+?\(?\d[\d\s().\-]{8,}\d', bruto)
    telefone = ''
    for trecho in achados:
        t = c.telefone_whatsapp(trecho)
        if t:
            telefone = t
            break
    nome = bruto
    for trecho in achados:
        nome = nome.replace(trecho, ' ')
    nome = re.sub(r'[\s,;:/\-–|]+', ' ', nome).strip()
    return nome, telefone


def _coluna(cab: list[str], *procuradas: str, exceto: tuple[str, ...] = ()) -> int | None:
    for i, h in enumerate(cab):
        if any(p in h for p in procuradas) and not any(e in h for e in exceto):
            return i
    return None


def _de_aba_manual(linhas: list[list[Any]]) -> list[dict]:
    if len(linhas) < 2:
        return []
    cab = [_sem_acento(h) for h in linhas[0]]
    achou = {n: (cab.index(n) if n in cab else None) for n in ('email', 'telefone', 'nome', 'desejo', 'data', 'status', 'formato')}
    saida = []
    for l in linhas[1:]:
        if not any(str(x).strip() for x in l):
            continue
        g = {n: (l[i] if i is not None and i < len(l) else '') for n, i in achou.items()}
        g['origem'] = 'manual'
        saida.append(g)
    return saida


def _de_aba_do_formulario(linhas: list[list[Any]]) -> list[dict]:
    if len(linhas) < 2:
        return []
    cab = [_sem_acento(h) for h in linhas[0]]
    i_data = _coluna(cab, 'carimbo', 'timestamp', 'data')
    i_artista = _coluna(cab, 'artista', 'banda')
    i_disco = _coluna(cab, 'disco', 'album', 'procura', exceto=('artista', 'banda'))
    # Contato: pode vir junto ("Seu nome e WhatsApp com DDD", formulário antigo) ou separado ("Seu nome" e "Seu WhatsApp
    # com DDD", D-072). Lê todas as colunas de contato e usa o primeiro nome e o primeiro telefone válidos que achar.
    i_contatos = [i for i, h in enumerate(cab) if any(p in h for p in ('whatsapp', 'telefone', 'celular', 'contato', 'nome'))
                  and not any(e in h for e in ('artista', 'banda', 'disco'))]
    i_email = _coluna(cab, 'email', 'e-mail')
    i_status = _coluna(cab, 'status')
    i_formato = _coluna(cab, 'formato')
    saida = []
    for l in linhas[1:]:
        if not any(str(x).strip() for x in l):
            continue

        def pega(i):
            return str(l[i]).strip() if i is not None and i < len(l) else ''
        nome, telefone = '', ''
        for i in i_contatos:
            n, t = separar_contato(pega(i))
            nome, telefone = nome or n, telefone or t
        saida.append({'email': pega(i_email).lower(), 'telefone': telefone, 'nome': nome,
                      'desejo': f'{pega(i_artista)} {pega(i_disco)}'.strip(),
                      'data': l[i_data] if i_data is not None and i_data < len(l) else '', 'status': pega(i_status), 'origem': 'formulario',
                      'formato': pega(i_formato)})
    return saida


def juntar_desejos(abas: dict[str, list[list[Any]]]) -> pd.DataFrame:
    """Junta a aba `desejos` e as abas do Google Forms numa tabela só (COLUNAS)."""
    registros: list[dict] = []
    for titulo, linhas in abas.items():
        if titulo == 'desejos':
            registros += _de_aba_manual(linhas)
        elif eh_aba_do_formulario(titulo):
            registros += _de_aba_do_formulario(linhas)
    if not registros:
        return pd.DataFrame(columns=COLUNAS)
    return pd.DataFrame(registros).reindex(columns=COLUNAS).fillna('')


def codigo_do_pedido(contato: str, desejo: str) -> str:
    """Código estável do pedido (sem dado pessoal): o mesmo cliente pedindo a mesma coisa é um pedido só."""
    from painel_monstro.saidas.fila_unica import codigo
    texto = re.sub(r'\s+', ' ', _sem_acento(desejo))
    return codigo(_sem_acento(contato), texto)
