"""Rotina automática do Painel: coletor pela API, motor e planilha, nessa ordem.

    python -m painel_monstro.rotina              (só o que mudou desde a última vez)
    python -m painel_monstro.rotina --completo   (baixa tudo de novo da Nuvemshop)

1. Coletor: baixa da Nuvemshop o que mudou (só leitura) e monta as tabelas.
2. Motor: calcula a régua de hoje e os indicadores (lendo a aba `custos` da planilha).
3. Planilha: grava tudo na Planilha Google sem duplicar.
4. Carrinhos: atualiza a aba `Fila` (carrinhos abandonados, mensagem e link do WhatsApp) e a aba `Resultados`.

Se o passo 1 ou 2 falhar, nada é gravado na planilha. O log mostra só contagens: nunca nome, email,
telefone, token ou chave. No GitHub, o resumo também vai para a página da execução
($GITHUB_STEP_SUMMARY).
"""
from __future__ import annotations

import os
import sys
import time

import pandas as pd

from painel_monstro.log_publico import comando_seguro, ArgumentParserSeguro, resumo_erro
from painel_monstro.config import Config, carregar
from painel_monstro.coletor import nuvemshop_api
from painel_monstro.motor import indicadores, regua
from painel_monstro.saidas import anuncios, brevo, cadastro, ga4, carrinhos_planilha, custos_automaticos, meta, newsletter, planilha_google, raspadinha, raspadinha_lembrete, regua_planilha, resumos_painel

SEGREDOS_OBRIGATORIOS = {
    'NUVEMSHOP_STORE_ID': 'nuvemshop_store_id',
    'NUVEMSHOP_TOKEN': 'nuvemshop_token',
    'NUVEMSHOP_USER_AGENT': 'nuvemshop_user_agent',
    'PLANILHA_ID': 'planilha_id',
}


class ErroRotina(Exception):
    """Falha da rotina, com mensagem pronta para o log (sem segredos)."""


def conferir_configuracao(config: Config) -> None:
    faltando = [nome for nome, campo in SEGREDOS_OBRIGATORIOS.items() if not getattr(config, campo)]
    if not (config.google_service_account_json or config.google_service_account_file):
        faltando.append('GOOGLE_SERVICE_ACCOUNT_JSON')
    if faltando:
        raise ErroRotina('Faltam estes segredos (só os nomes): ' + ', '.join(faltando))


def rodar(config: Config | None = None, completo: bool = False, pasta_api: str = nuvemshop_api.PASTA_PADRAO,
          api: nuvemshop_api.NuvemshopAPI | None = None, planilha: planilha_google.PlanilhaGoogle | None = None,
          carrinhos: bool = True, dormir=time.sleep, anuncios_historico: bool = False) -> dict:
    """Executa os passos (coletor, motor, planilha e, se `carrinhos`, a fila de carrinhos) e devolve um resumo com contagens (para log e testes)."""
    config = config or carregar()
    conferir_configuracao(config)
    inicio = time.monotonic()

    # 1. Coletor
    tabelas, coleta = nuvemshop_api.coletar(config, pasta=pasta_api, completo=completo, api=api)
    print('[1/5] Coletor (Nuvemshop, só leitura)')
    for recurso, r in coleta.items():
        print(f'      {recurso}: {r["modo"]}, {r["novos"]} novos, {r["atualizados"]} atualizados, {r["total"]} no total')

    # 2. Motor
    planilha = planilha or planilha_google.PlanilhaGoogle.conectar(config)
    custos = planilha.ler_custos()
    api = api or nuvemshop_api.NuvemshopAPI(config)
    custos, paginas_custos = custos_automaticos.preparar(config, custos, tabelas, pasta_api, api=api)
    for _, dados_custos in paginas_custos:
        for fonte, linhas_custos in dados_custos.groupby('fonte'):
            pendentes = int((linhas_custos['estado'] != 'ok').sum())
            print(f'      Custos {fonte}: {len(linhas_custos) - pendentes} valores disponíveis, {pendentes} pendentes')
    mes = pd.Timestamp.now(tz=nuvemshop_api.FUSO_LOJA).strftime('%Y-%m')  # o servidor do GitHub usa UTC
    regua_planilha.garantir_aba_regua(planilha)  # janelas e ofertas editáveis (D-017); o motor lê dela
    params_regua = regua_planilha.ler_regua(planilha)
    classificacao, referencia = regua.rodar(tabelas, mes, params_regua)
    etapas = regua.resumo(classificacao, params_regua)
    calculados = indicadores.calcular(tabelas, custos, referencia=referencia)
    ok = int((calculados.resumo['estado'] == indicadores.OK).sum())
    print(f'[2/5] Motor: régua de hoje (referência {referencia:%d/%m/%Y}) e {len(calculados.resumo)} indicadores '
          f'({ok} calculados, {len(calculados.resumo) - ok} aguardando dados); aba custos com {len(custos)} mês(es)')
    for e in etapas.itertuples():
        print(f'      {e.etapa}: {e.recebem} recebem, {e.controle} no controle')

    # Data em que cada produto entrou ou voltou ao estoque (newsletter semanal); lê a aba `produtos` da rodada anterior
    hoje_brt = pd.Timestamp.now(tz=nuvemshop_api.FUSO_LOJA)
    tabelas.produtos = newsletter.marcar_estoque(tabelas.produtos, _ler_aba(planilha, 'produtos'), hoje_brt.strftime('%Y-%m-%d'))

    # 3. Calcula tudo antes de escrever qualquer aba (D-039): se algo falhar aqui, a planilha fica como estava.
    pagina_das_tabelas = [(nome, getattr(tabelas, nome)) for nome in ('clientes', 'pedidos', 'itens', 'produtos')]
    pagina_das_tabelas.append(('indicadores', planilha_google.resumo_indicadores(calculados)))
    cabecalhos = [planilha.garantir_cabecalho(planilha_google.ABA_CUSTOS, planilha_google.CUSTOS_COLUNAS, planilha_google.CUSTOS_NOTAS),
                  planilha.garantir_cabecalho(planilha_google.ABA_ALERTAS, planilha_google.ALERTAS_COLUNAS, planilha_google.ALERTAS_NOTAS)]
    plano_fila = None
    if carrinhos:
        api = api or nuvemshop_api.NuvemshopAPI(config)
        plano_fila = carrinhos_planilha.planejar_fila(planilha, api, tabelas, fila_unica=True)
    fila_final = {str(i): e for i, e in enumerate(plano_fila.finais)} if plano_fila is not None else None
    pagina_dos_resumos = resumos_painel.montar_resumos(planilha, tabelas, calculados, classificacao, params_regua=params_regua, fila=fila_final)
    pagina_dos_resumos.extend(paginas_custos)
    pagina_dos_resumos.append(('resumo_email', resumos_painel.montar_resumo_email(
        dict(pagina_dos_resumos), calculados.resumo, plano_fila.resumo_semana if plano_fila is not None else [])))
    resultado_brevo, paginas_brevo = passo_brevo(config, planilha, tabelas, classificacao, params_regua)
    pagina_dos_resumos.extend(paginas_brevo)
    pagina_dos_resumos.extend(passo_meta(config, planilha, tabelas))
    # Raspadinha (D-062): uso dos cupons e resultado contra o controle; sem campanha não grava nada
    pagina_dos_resumos.extend(raspadinha.passo_rotina(planilha, tabelas, pd.Timestamp.now(tz=nuvemshop_api.FUSO_LOJA).date()))
    # Newsletter semanal: quarta, a partir das 17h (Brasília); fora disso não grava nada
    pagina_dos_resumos.extend(newsletter.passo_rotina(lambda nome: _ler_aba(planilha, nome), tabelas.produtos, hoje_brt))
    paginas_anuncios = passo_anuncios(config, planilha, tabelas, pasta_api, completo=anuncios_historico)
    # GA4 (D-076): origem das visitas e vendas, e links das bandas. Falha aqui nunca derruba a rotina.
    try:
        try:
            prop_ga4 = str(regua_planilha._config_por_nome(planilha).get(ga4.CONFIG_PROPRIEDADE, '')).strip()
        except Exception:  # noqa: BLE001
            prop_ga4 = ''
        paginas_ga4 = ga4.passo_rotina(config, prop_ga4)
        pagina_dos_resumos.extend(paginas_ga4)
        print(f'      GA4: {len(paginas_ga4[0][1])} linhas por dia e origem, {len(paginas_ga4[1][1])} links de banda')
    except Exception as erro:  # noqa: BLE001
        print(f'      GA4: indisponível ({_resumo_do_erro(erro)}); as abas ga4_* ficam como estavam.')
    print('[3/5] Tudo calculado; gravando na Planilha Google')

    # 4. Grava, aba por aba. Falha numa aba mantém o conteúdo antigo dela; a rodada seguinte recalcula e tenta de novo.
    gravacoes: list = list(cabecalhos)
    erros: list[str] = []

    def tentar(nome: str, escrever) -> None:
        try:
            resultado = com_novas_tentativas(escrever, dormir)
            if hasattr(resultado, 'aba'):
                gravacoes.append(resultado)
        except Exception as erro:  # noqa: BLE001 - qualquer falha de gravação vira aviso, sem derrubar as outras abas
            erros.append(f'{nome} ({_resumo_do_erro(erro)})')
    for nome, df in pagina_das_tabelas:
        tentar(nome, lambda n=nome, d=df: planilha.substituir(n, d))
    for g in gravacoes:
        print(f'      {g.aba}: {g.linhas} linhas ({g.acao.replace("_", " ")})')
    fila = None
    if plano_fila is not None:
        try:
            fila = carrinhos_planilha.gravar_plano(planilha, plano_fila)
            print(f'[4/5] Carrinhos: {fila["carrinhos"]} na Nuvemshop, {fila["na_fila"]} na fila ({fila["contatar"]} para contatar), '
                  f'{fila["novas_linhas"]} linhas novas, {fila["sem_contato"]} encerradas sem contato'
                  + ('' if fila['dia_de_fila'] else ' · hoje não é dia de fila'))
        except Exception as erro:  # noqa: BLE001
            erros.append(f'Fila ({_resumo_do_erro(erro)})')
            fila = {**plano_fila.contagens, 'celulas': 0}
    antes = len(gravacoes)
    for nome, df in pagina_dos_resumos:
        tentar(nome, lambda n=nome, d=df: planilha.substituir(n, d))
    # Anúncios são independentes: falha na consulta ou gravação nunca invalida a rotina da loja.
    for nome, df in paginas_anuncios:
        try:
            gravacoes.append(com_novas_tentativas(lambda n=nome, d=df: planilha.substituir(n, d), dormir))
        except Exception:
            print('      Anúncios: gravação indisponível; a próxima rodada tenta novamente.')
    try:
        cad = cadastro.passo_rotina(config, planilha, tabelas, pasta_api, api=api)
        print(f'      Cadastro: {cad["rascunhos"]} rascunhos, {cad["criados"]} criados, {cad["erros"]} pendências')
    except Exception:
        print('      Cadastro: indisponível; conferir a planilha. Demais etapas preservadas.')
    # Lembrete da raspadinha (D-071): quem ganhou cupom e não usou entra na lista do Brevo 2 dias antes de vencer
    try:
        try:
            valores_config = regua_planilha._config_por_nome(planilha)
        except Exception:  # noqa: BLE001 - sem aba Configuração vale o padrão
            valores_config = {}
        rl = raspadinha_lembrete.passo_rotina(config, planilha, tabelas, hoje_brt, lambda n: _ler_aba(planilha, n), valores_config)
        print('      Raspadinha: lembrete processado; conferir resultado na planilha.')
    except Exception as erro:  # noqa: BLE001 - nunca derruba a rotina
        print(f'      Raspadinha · lembrete no Brevo: indisponível ({_resumo_do_erro(erro)}); a próxima rodada tenta de novo.')
    print('[5/5] Resumos para o painel e para o email de segunda')
    print('      Brevo: etapa processada; conferir resultado na planilha.')
    for g in gravacoes[antes:]:
        print(f'      {g.aba}: {g.linhas} linhas')

    if erros:
        raise ErroRotina('Não consegui gravar: ' + ', '.join(erros) + '. O conteúdo antigo dessas abas foi mantido e a próxima rodada tenta de novo.')
    # Só uma rodada completa marca a hora de "última rodada bem-sucedida" (o alerta do Apps Script confere essa hora).
    agora_brt = pd.Timestamp.now(tz=nuvemshop_api.FUSO_LOJA)
    planilha.substituir('rodada', pd.DataFrame([{'ultima_rodada_ok': agora_brt.strftime('%Y-%m-%d %H:%M'),
                                                  'duracao_s': round(time.monotonic() - inicio, 1),
                                                  'dia_de_fila': bool(fila['dia_de_fila']) if fila else '',
                                                  'brevo_status': resultado_brevo.status, 'brevo_detalhe': resultado_brevo.detalhe,
                                                  'brevo_ultima_leitura_ok': resultado_brevo.leitura_ok_em}]))
    gravacoes = [g for g in gravacoes]

    resumo = {'fila': fila, 'coleta': coleta, 'etapas': etapas.to_dict('records'), 'gravacoes': gravacoes,
              'indicadores_calculados': ok, 'indicadores_total': len(calculados.resumo),
              'segundos': round(time.monotonic() - inicio, 1)}
    print(f'Pronto em {resumo["segundos"]} s.')
    escrever_resumo_do_github(resumo)
    return resumo


ESPERAS_DO_GOOGLE = (20, 45, 90)  # segundos entre as tentativas quando o Google limita o uso (erro 429) ou oscila (5xx)


def _status_http(erro: Exception) -> int | None:
    resposta = getattr(erro, 'response', None)
    return getattr(resposta, 'status_code', None)


def _resumo_do_erro(erro: Exception) -> str:
    """Resumo fixo do erro, sem conteúdo externo."""
    return resumo_erro(erro)


def com_novas_tentativas(escrever, dormir=time.sleep):
    """Roda `escrever()`. Se o Google responder 429 ou 5xx, espera e tenta de novo (até 4 vezes no total)."""
    for tentativa, espera in enumerate((*ESPERAS_DO_GOOGLE, None)):
        try:
            return escrever()
        except Exception as erro:  # noqa: BLE001
            if espera is None or _status_http(erro) not in (429, 500, 502, 503, 504):
                raise
            print(f'      o Google pediu para esperar ({_status_http(erro)}); tentando de novo em {espera} s')
            dormir(espera)


def _ler_aba(planilha: planilha_google.PlanilhaGoogle, nome: str) -> list[list]:
    try:
        return planilha._ss.worksheet(nome).get_all_values()
    except Exception:  # noqa: BLE001 - aba ainda não existe
        return []


def passo_brevo(config: Config, planilha: planilha_google.PlanilhaGoogle, tabelas, classificacao, params_regua,
                sessao=None) -> tuple[brevo.ResultadoBrevo, list[tuple[str, pd.DataFrame]]]:
    """Etapa 7: lê a conta do Brevo a cada rodada (mantém a chave viva) e, uma vez por dia, calcula o plano da régua.

    Em modo teste (o padrão) nada é escrito no Brevo. Falha do Brevo nunca derruba a rodada: o status vai para a aba
    `rodada` e o script do Google manda o alerta que já existe para falhas.
    """
    agora = pd.Timestamp.now(tz=nuvemshop_api.FUSO_LOJA)
    texto_agora = agora.strftime('%Y-%m-%d %H:%M')
    rodada = _ler_aba(planilha, 'rodada')
    anterior = dict(zip(rodada[0], rodada[1])) if len(rodada) > 1 else {}
    ultima_boa = str(anterior.get('brevo_ultima_leitura_ok') or '')
    if not config.brevo_api_key:
        return brevo.ResultadoBrevo('sem chave', 'BREVO_API_KEY não configurada', None, ultima_boa), []
    gerado = next((l[1] for l in _ler_aba(planilha, 'brevo_plano') if l and l[0] == 'gerado_em' and len(l) > 1), '')
    mudancas_gravadas = any(str(c).strip() for l in _ler_aba(planilha, 'brevo_mudancas')[:1] for c in l)  # tem ao menos o cabeçalho
    try:
        valores_config = regua_planilha._config_por_nome(planilha)
    except Exception:  # noqa: BLE001 - aba Configuração ainda não existe: tudo cai no mais seguro (pausada/desligada)
        valores_config = {}
    politica = brevo.ler_politica(valores_config)
    hoje = agora.date()
    assinatura = '|'.join(str(valores_config.get(k, '')) for k in
                          [brevo.CHAVE_REGUA, brevo.CHAVE_PAUSA_DE, brevo.CHAVE_PAUSA_ATE, *brevo.CHAVES_DAS_ETAPAS.values()])
    anterior_assinatura = next((str(l[1]) for l in _ler_aba(planilha, 'brevo_plano') if l and l[0] == 'configuracao' and len(l) > 1), '')
    # Plano: uma vez por dia, e de novo quando alguém muda a chave, a pausa ou as etapas na aba Configuração
    pendentes_antes = next((str(l[1]) for l in _ler_aba(planilha, 'brevo_plano') if l and l[0] == 'pendentes de aplicar' and len(l) > 1), '0')
    modo_atual = 'TESTE (nada foi escrito no Brevo)' if config.brevo_modo_teste else 'REAL'
    modo_antes = next((str(l[1]) for l in _ler_aba(planilha, 'brevo_plano') if l and l[0] == 'modo' and len(l) > 1), '')
    # Fora do modo teste, o que não coube no tempo da rodada anterior é feito na seguinte, sem esperar o dia seguinte;
    # e trocar o modo (teste <-> real) refaz o plano na hora, para o dia de virada não esperar até amanhã
    refazer = (str(gerado)[:10] != agora.strftime('%Y-%m-%d') or not mudancas_gravadas or assinatura != anterior_assinatura
               or (not config.brevo_modo_teste and pendentes_antes not in ('', '0')) or (modo_antes and modo_antes != modo_atual))
    if agora.hour >= 6 and refazer:
        r = brevo.planejar_do_dia(config.brevo_api_key, classificacao, tabelas, params_regua, config.brevo_modo_teste,
                                  sessao, texto_agora, regua_planilha.ler_listas_brevo(planilha), politica, hoje,
                                  regua_planilha.ler_cupons_regua(planilha))
    else:
        r = brevo.ler_conta(config.brevo_api_key, config.brevo_modo_teste, sessao, texto_agora)
    if not r.leitura_ok_em:
        r.leitura_ok_em = ultima_boa  # a última chamada que deu certo (a chave vence depois de 90 dias sem uma)
    paginas: list[tuple[str, pd.DataFrame]] = []
    if r.plano is not None:
        p = r.plano
        linhas = [['gerado_em', texto_agora], ['modo', modo_atual]]
        novas_chaves = ('congelados pela pausa (não entram nem saem)', 'barrados por etapa desligada', 'entram com cupom do mês')
        linhas += [[k, v] for k, v in p.resumo.items() if k not in novas_chaves]
        linhas += [[f'entram em "{n}"', len(e)] for n, e in sorted(p.entrar_na_lista.items())]
        linhas += [[f'saem de "{n}"', len(e)] for n, e in sorted(p.sair_da_lista.items())]
        linhas += [['listas que faltam no Brevo', ', '.join(p.listas_ausentes) or 'nenhuma'],
                   ['atributos que faltam no Brevo', ', '.join(p.atributos_ausentes) or 'nenhum']]
        # linhas da 7.1 sempre no fim: as de cima não mudam de posição (o painel lê por nome, mas não custa nada)
        linhas += [['Régua no Brevo', politica.estado(hoje)], ['Etapas ligadas', politica.etapas_texto()],
                   ['configuracao', assinatura]]
        linhas += [[k, p.resumo[k]] for k in novas_chaves]
        ap = r.aplicado or {}
        linhas += [['aplicado no Brevo', 'nada (modo teste)' if config.brevo_modo_teste else
                    f"{ap.get('atributos', 0)} atributos, {ap.get('entraram', 0)} entradas em lista, {ap.get('sairam', 0)} saídas, "
                    f"{ap.get('falhas', 0)} falhas"],
                   ['pendentes de aplicar', ap.get('pendentes', 0)]]
        linhas += [[f'aviso {i + 1}', a] for i, a in enumerate(p.avisos or list(politica.avisos))]
        paginas.append(('brevo_plano', pd.DataFrame(linhas, columns=['indicador', 'valor'])))
        colunas = ['email', 'etapa_antes', 'etapa_depois', 'controle', 'entra_na_lista', 'sai_da_lista']
        paginas.append(('brevo_mudancas', pd.DataFrame(p.mudancas[:2000], columns=colunas)))
    return r, paginas


def passo_meta(config: Config, planilha: planilha_google.PlanilhaGoogle, tabelas, sessao=None) -> list[tuple[str, pd.DataFrame]]:
    """Públicos do Meta, uma vez por mês (e de novo se o segmento do Brevo mudar). Só aba da planilha: nada vai ao repositório."""
    agora = pd.Timestamp.now(tz=nuvem_fuso())
    mes = agora.strftime('%Y-%m')
    try:
        segmento = str(regua_planilha._config_por_nome(planilha).get(meta.CONFIG_SEGMENTO, '')).strip()
    except Exception:  # noqa: BLE001 - a aba Configuração ainda não existe
        segmento = ''
    feito = {l[0]: (l[1] if len(l) > 1 else '') for l in _ler_aba(planilha, meta.ABA_RESUMO) if l}
    if str(feito.get('mes')) == mes and str(feito.get('segmento', '')) == segmento:
        return []
    nao_abrem, descadastrados = None, set()
    if segmento and config.brevo_api_key:
        try:
            b = brevo.Brevo(config.brevo_api_key, config.brevo_modo_teste, sessao)
            membros = list(b.contatos_do_segmento(int(float(segmento))))
            nao_abrem = {str(m.get('email', '')).lower() for m in membros if not m.get('emailBlacklisted')}
            descadastrados = {str(m.get('email', '')).lower() for m in membros if m.get('emailBlacklisted')}
        except (brevo.ErroBrevo, ValueError) as erro:
            print('      Meta: segmento indisponível; a lista de quem não abre fica vazia neste mês.')
    listas = meta.montar(tabelas, agora.tz_localize(None), nao_abrem, descadastrados)
    paginas = [(meta.ABAS[k], df) for k, df in listas.items()]
    r = meta.resumo(listas, mes, agora.strftime('%Y-%m-%d %H:%M'), nao_abrem is not None)
    r.loc[len(r)] = ['segmento', segmento]
    paginas.append((meta.ABA_RESUMO, r))
    return paginas


def nuvem_fuso() -> str:
    return nuvemshop_api.FUSO_LOJA


def passo_anuncios(config, planilha, tabelas, pasta_api, **kw):
    """Passo isolado da Etapa 9, sem confundir com os públicos meta_* da Etapa 8."""
    return anuncios.passo_anuncios(config, planilha, tabelas, pasta_api, **kw)


def escrever_resumo_do_github(resumo: dict) -> None:
    """Quadro com o resultado na página da execução do GitHub Actions (só contagens)."""
    caminho = os.environ.get('GITHUB_STEP_SUMMARY')
    if not caminho:
        return
    linhas = ['## Rotina do Painel Monstro', '', '| Aba | Linhas | O que aconteceu |', '|---|---:|---|']
    linhas += [f'| {g.aba} | {g.linhas} | {g.acao.replace("_", " ")} |' for g in resumo['gravacoes']]
    linhas += ['', '| Dados da Nuvemshop | Modo | Novos | Atualizados | Total |', '|---|---|---:|---:|---:|']
    linhas += [f'| {r_} | {v["modo"]} | {v["novos"]} | {v["atualizados"]} | {v["total"]} |' for r_, v in resumo['coleta'].items()]
    if resumo.get('fila'):
        f = resumo['fila']
        linhas += ['', f'Carrinhos: {f["carrinhos"]} na Nuvemshop, {f["na_fila"]} na fila ({f["contatar"]} para contatar), '
                       f'{f["novas_linhas"]} linhas novas.']
    linhas += ['', f'Indicadores calculados: {resumo["indicadores_calculados"]} de {resumo["indicadores_total"]}. '
                   f'Duração: {resumo["segundos"]} s.']
    with open(caminho, 'a', encoding='utf-8') as arq:
        arq.write('\n'.join(linhas) + '\n')


def rodar_cadastro(config: Config | None = None, pasta_api: str = nuvemshop_api.PASTA_PADRAO,
                   api: nuvemshop_api.NuvemshopAPI | None = None, planilha: planilha_google.PlanilhaGoogle | None = None) -> dict:
    """Rodada curta (D-068): só o cadastro de discos aprovados, disparada pelo vigia do Apps Script.

    Atualiza a coleta da Nuvemshop de forma incremental (preço de referência e diário do cadastro usam a mesma pasta
    e o mesmo cache da rotina completa) e roda apenas cadastro.passo_rotina. Não grava a aba `rodada`: o alerta de
    rotina parada continua medindo só a rotina completa."""
    config = config or carregar()
    conferir_configuracao(config)
    inicio = time.monotonic()
    tabelas, _ = nuvemshop_api.coletar(config, pasta=pasta_api, completo=False, api=api)
    planilha = planilha or planilha_google.PlanilhaGoogle.conectar(config)
    api = api or nuvemshop_api.NuvemshopAPI(config)
    cad = cadastro.passo_rotina(config, planilha, tabelas, pasta_api, api=api)
    cad['segundos'] = round(time.monotonic() - inicio, 1)
    print(f'Cadastro: {cad["rascunhos"]} rascunhos, {cad["criados"]} criados, {cad["erros"]} pendências '
          f'({cad["segundos"]} s).')
    return cad


@comando_seguro
def main() -> int:
    import argparse

    analisador = ArgumentParserSeguro(description='Rotina do Painel: coletor, motor e planilha.')
    analisador.add_argument('--completo', action='store_true', help='baixa tudo de novo da Nuvemshop')
    analisador.add_argument('--anuncios-historico', action='store_true', help='rebaixa histórico de anúncios desde julho/2025')
    analisador.add_argument('--so-cadastro', action='store_true', help='rodada curta: só cria os discos aprovados (D-068)')
    args = analisador.parse_args()
    try:
        if args.so_cadastro:
            rodar_cadastro()
        else:
            rodar(completo=args.completo, anuncios_historico=args.anuncios_historico)
    except (ErroRotina, nuvemshop_api.ErroAPI, planilha_google.ErroPlanilha) as erro:
        print('ERRO: ' + resumo_erro(erro))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
