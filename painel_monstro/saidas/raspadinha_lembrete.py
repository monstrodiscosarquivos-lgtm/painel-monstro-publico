"""Lembrete da raspadinha no Brevo (D-071, guia em docs/RASPADINHA.md).

Quem raspou, ganhou cupom e ainda não usou recebe um lembrete alguns dias antes de o cupom vencer (padrão: 2).
Como na régua (D-052), o Painel não envia email: grava os atributos RASP_* no contato e coloca o contato na lista
"Painel · Raspadinha lembrete". Quem envia é a automação do Brevo, que dispara na entrada da lista.

Regras:
- Só cupom de verdade (cupom_status = criado). Cupom TESTE, sem prêmio e erro nunca entram.
- Só quem não usou: o código não aparece em nenhum pedido da loja.
- Só na janela: de N dias antes até o último dia da validade, e nunca no mesmo dia em que a pessoa raspou.
- Só das 9h às 20h (Brasília), para o email não chegar de madrugada.
- Um lembrete por cupom (aba rasp_lembretes guarda quem recebeu e quem ficou de fora, e por quê).
- Contato descadastrado no Brevo nunca é tocado. Quem ainda não está no Brevo só é criado se marcou, na página,
  que aceita receber novidades; sem esse aceite fica de fora.
- Depois que o cupom vence, o contato sai da lista, para poder entrar de novo numa próxima campanha.
- Linha "Raspadinha: lembrete no Brevo (dias antes de vencer)" na aba Configuração: 0 desliga; vazio usa 2.
- Brevo em modo teste: só conta quem receberia; nada é escrito no Brevo nem na aba.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Callable

import pandas as pd

from painel_monstro.saidas import brevo as bv

LISTA = 'Painel · Raspadinha lembrete'
ABA = 'rasp_lembretes'
COLUNAS = ['cupom', 'email', 'campanha', 'premio', 'valido_ate', 'status', 'quando']
ATRIBUTOS = {'RASP_CUPOM': 'text', 'RASP_PREMIO': 'text', 'RASP_VALIDADE': 'text', 'RASP_CAMPANHA': 'text', 'RASP_MINIMO': 'text'}
CHAVE_DIAS = 'Raspadinha: lembrete no Brevo (dias antes de vencer)'
DIAS_PADRAO = 2
HORA_INICIO, HORA_FIM = 9, 20
ENVIADO = 'enviado'
SAIU = 'enviado · saiu da lista'
PULADO_DESCADASTRADO = 'fora: descadastrado no Brevo'
PULADO_SEM_ACEITE = 'fora: não está no Brevo e não aceitou novidades'
LIMITE = 150


def _norm(texto: Any) -> str:
    return unicodedata.normalize('NFKD', str(texto or '')).encode('ascii', 'ignore').decode().lower().strip()


def ler_dias(config: dict[str, Any]) -> int:
    """Dias antes do vencimento. Vazio ou ausente = 2; 0 desliga; valor ilegível desliga (o mais seguro)."""
    c = {_norm(k): v for k, v in (config or {}).items()}
    valor = str(c.get(_norm(CHAVE_DIAS), '') or '').strip()
    if valor == '':
        return DIAS_PADRAO
    try:
        return max(0, min(int(float(valor.replace(',', '.'))), 30))
    except ValueError:
        return 0


def tabela(valores: list[list[Any]]) -> list[dict[str, str]]:
    """Linhas de uma aba (primeira linha = cabeçalho) como dicionários de texto."""
    if not valores:
        return []
    cab = [str(c).strip() for c in valores[0]]
    return [dict(zip(cab, [str(c) for c in l] + [''] * (len(cab) - len(l)))) for l in valores[1:] if any(str(c).strip() for c in l)]


def ler_data(texto: Any) -> date | None:
    t = str(texto or '').strip()
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})', t)
    try:
        if m:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        m = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', t)
        if m:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None
    return None


def cupons_usados(pedidos: pd.DataFrame | None) -> set[str]:
    """Códigos que aparecem em algum pedido (pago ou não: a Nuvemshop já consome o cupom de uso único)."""
    if pedidos is None or 'cupom' not in getattr(pedidos, 'columns', []):
        return set()
    usados: set[str] = set()
    for valor in pedidos['cupom'].dropna():
        usados.update(c.strip().upper() for c in str(valor).split(',') if c.strip())
    return usados


def _numero(valor: Any) -> float:
    texto = str(valor or '').strip().replace('R$', '').replace(' ', '')
    if ',' in texto:
        texto = texto.replace('.', '').replace(',', '.')
    try:
        return float(texto)
    except ValueError:
        return 0.0


def _br(n: float) -> str:
    return str(int(n)) if float(n).is_integer() else f'{n:.2f}'.replace('.', ',')


def texto_premio(tipo: Any, valor: Any) -> str:
    if str(tipo).strip() == 'Frete grátis':
        return 'frete grátis'
    if str(tipo).strip() == 'Valor em R$':
        return f'R$ {_br(_numero(valor))} de desconto'
    return f'{_numero(valor):g}'.replace('.', ',') + '% de desconto'


def texto_minimo(valor: Any) -> str:
    n = _numero(valor)
    return f'em compras a partir de R$ {_br(n)}' if n > 0 else ''


@dataclass
class Candidato:
    cupom: str
    email: str
    campanha: str
    nome_campanha: str
    premio: str
    valido_ate: date
    minimo: str
    aceitou: bool

    def atributos(self) -> dict[str, str]:
        return {'RASP_CUPOM': self.cupom, 'RASP_PREMIO': self.premio, 'RASP_VALIDADE': self.valido_ate.strftime('%d/%m'),
                'RASP_CAMPANHA': self.nome_campanha, 'RASP_MINIMO': self.minimo}

    def linha(self, status: str, quando: str) -> list[str]:
        return [self.cupom, self.email, self.campanha, self.premio, self.valido_ate.isoformat(), status, quando]


def candidatos(jogadas: list[dict], campanhas: list[dict], usados: set[str], ja_registrados: set[str],
               hoje: date, dias: int) -> list[Candidato]:
    """Quem deve receber o lembrete hoje."""
    por_id = {str(c.get('campanha', '')).strip(): c for c in campanhas}
    vistos: set[str] = set()
    saida: list[Candidato] = []
    for j in jogadas:
        if str(j.get('cupom_status', '')).strip() != 'criado':
            continue
        cupom = str(j.get('cupom', '')).strip().upper()
        email = str(j.get('email', '')).strip().lower()
        ate, jogou = ler_data(j.get('valido_ate')), ler_data(j.get('quando'))
        if not cupom or cupom in vistos or cupom in ja_registrados or cupom in usados or '@' not in email:
            continue
        if ate is None or jogou is None or jogou >= hoje or not (ate - timedelta(days=dias) <= hoje <= ate):
            continue
        vistos.add(cupom)
        campanha = str(j.get('campanha', '')).strip()
        c = por_id.get(campanha, {})
        saida.append(Candidato(cupom, email, campanha, str(c.get('nome') or c.get('titulo') or campanha).strip(),
                               texto_premio(j.get('tipo'), j.get('valor')), ate, texto_minimo(c.get('pedido_minimo')),
                               _norm(j.get('consentiu')) == 'sim'))
    return saida


@dataclass
class Resultado:
    status: str
    enviados: int = 0
    fora: int = 0
    sairam: int = 0
    falhas: int = 0
    receberiam: int = 0
    linhas: list[list[str]] = field(default_factory=list)

    def texto(self) -> str:
        partes = [self.status]
        if self.status == 'ok':
            partes = [f'{self.enviados} entraram na lista', f'{self.fora} ficaram de fora', f'{self.sairam} saíram (cupom vencido)']
            if self.falhas:
                partes.append(f'{self.falhas} falhas (tenta de novo na próxima rodada)')
        elif self.receberiam:
            partes.append(f'{self.receberiam} receberiam')
        return ', '.join(partes)


def executar(brevo: bv.Brevo, cands: list[Candidato], registro: list[dict], hoje: date, quando: str) -> Resultado:
    """Grava no Brevo e devolve as linhas novas ou alteradas da aba rasp_lembretes."""
    vencidos = [r for r in registro if r.get('status') == ENVIADO and (ler_data(r.get('valido_ate')) or hoje) < hoje]
    if not cands and not vencidos:
        return Resultado('nada a fazer hoje')
    if brevo.modo_teste:
        return Resultado('modo teste (nada foi escrito no Brevo)', receberiam=len(cands))
    listas = {l.get('name'): l.get('id') for l in brevo.listas()}
    lista_id = listas.get(LISTA)
    if lista_id is None:
        return Resultado(f'falta criar a lista "{LISTA}" no Brevo', receberiam=len(cands))
    existentes = {a.get('name') for a in brevo.atributos()}
    for nome, tipo in ATRIBUTOS.items():
        if nome not in existentes:
            brevo.criar_atributo(nome, tipo)
    r = Resultado('ok')
    entraram: set[str] = set()
    for c in cands:
        try:
            contato = brevo.contato(c.email)
            if contato is not None and contato.get('emailBlacklisted'):
                r.fora += 1
                r.linhas.append(c.linha(PULADO_DESCADASTRADO, quando))
                continue
            if contato is None:
                if not c.aceitou:
                    r.fora += 1
                    r.linhas.append(c.linha(PULADO_SEM_ACEITE, quando))
                    continue
                brevo.criar_contato(c.email, c.atributos())
            else:
                brevo.atualizar_contato(c.email, c.atributos())
                if lista_id in (contato.get('listIds') or []):   # já estava: sai e entra, para a automação disparar de novo
                    brevo.remover_da_lista(lista_id, [c.email])
            brevo.adicionar_a_lista(lista_id, [c.email])
            entraram.add(c.email)
            r.enviados += 1
            r.linhas.append(c.linha(ENVIADO, quando))
        except bv.ErroBrevo as erro:
            if erro.tipo in ('chave_invalida', 'bloqueio_ip'):
                raise
            r.falhas += 1
    ativos = {str(x.get('email', '')).lower() for x in registro
              if x.get('status') == ENVIADO and (ler_data(x.get('valido_ate')) or hoje) >= hoje} | entraram
    remover = sorted({str(x.get('email', '')).lower() for x in vencidos} - ativos)
    for i in range(0, len(remover), LIMITE):
        try:
            brevo.remover_da_lista(lista_id, remover[i:i + LIMITE])
        except bv.ErroBrevo as erro:   # quem já não está na lista faz o Brevo reclamar; não é problema
            if erro.tipo in ('chave_invalida', 'bloqueio_ip'):
                raise
    for x in vencidos:
        r.linhas.append([str(x.get(k, '')) for k in COLUNAS[:5]] + [SAIU, quando])
        r.sairam += 1
    return r


def passo_rotina(config: Any, planilha: Any, tabelas: Any, agora: pd.Timestamp, ler: Callable[[str], list[list]],
                 valores_config: dict[str, Any], sessao: Any = None) -> Resultado:
    """Uma vez por rodada (a rotina roda de hora em hora). Nunca derruba a rotina: quem chama trata as falhas."""
    dias = ler_dias(valores_config)
    if dias == 0:
        return Resultado('desligado na Configuração')
    if not (HORA_INICIO <= agora.hour < HORA_FIM):
        return Resultado('fora do horário (9h às 20h)')
    if not getattr(config, 'brevo_api_key', ''):
        return Resultado('sem chave do Brevo')
    jogadas = tabela(ler('rasp_jogadas'))
    if not jogadas:
        return Resultado('ninguém raspou ainda')
    registro = tabela(ler(ABA))
    hoje = agora.date()
    ja = {str(x.get('cupom', '')).strip().upper() for x in registro}
    cands = candidatos(jogadas, tabela(ler('rasp_campanhas')), cupons_usados(getattr(tabelas, 'pedidos', None)), ja, hoje, dias)
    b = bv.Brevo(config.brevo_api_key, config.brevo_modo_teste, sessao)
    r = executar(b, cands, registro, hoje, agora.strftime('%Y-%m-%d %H:%M'))
    if r.linhas:
        planilha.mesclar(ABA, pd.DataFrame(r.linhas, columns=COLUNAS), ['cupom'])
    return r
