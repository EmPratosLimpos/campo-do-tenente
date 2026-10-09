#!/usr/bin/env python3
"""Atualiza os dados da semana a partir do SAPL.

Ordem: lote pequeno, sessoes ordinarias novas mais a ultima ja coletada,
autoria, tramitacao das materias novas ou ainda em tramitacao,
classificacao de temas novos por consenso (D-047), derivacao,
vereadores, presidencia, autoria tratada, atuacao por ano, temas, dados da
tela, sanidade, hash, testes e regras.

As listas grandes (presencas, ordem do dia, registrovotacao,
votoparlamentar, justificativa e mesa) nao sao mais baixadas em lote.
Elas saem da coleta por sessao, das ordinarias novas e sempre da ultima
ja coletada para pegar lancamento atrasado. Listas pequenas que fecham
(sessaoplenaria do ano, materias do ano, autoria) continuam em lote.
A primeira coleta completa de muitas sessoes precisa ser feita em partes,
fora da rotina semanal, por causa do teto de pedidos por execucao.

Um pedido por vez. Pausa de PAUSA_SAPL_SEGUNDOS (2,5 s). No maximo
400 pedidos nesta execucao. Anos saem de config_cidade.json. O ano
corrente so entra depois de um pedido ao SAPL confirmar ao menos uma
sessao ordinaria nesse ano. Sem sessao, o recorte nao muda.

Modo simulado (--simulado): nao abre rede. Usa os brutos ja salvos.
Se nao houver dado novo, nao regrava os tratados.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ / "coletor") not in sys.path:
    sys.path.insert(0, str(RAIZ / "coletor"))
if str(RAIZ / "scripts") not in sys.path:
    sys.path.insert(0, str(RAIZ / "scripts"))

import coletar_lote  # noqa: E402
from coletar_autoria import PARAMS_AUTORIA_ESTAVEL, PLANO, conferir_autoria  # noqa: E402
from coletar_lote import (  # noqa: E402
    PAGE_SIZE,
    ColetorLote,
    OrcamentoEsgotado,
    PedidoPendente,
    continuar_apos_primeira,
    plano_de_coleta,
)
from coletar_por_sessao import (  # noqa: E402
    CAMINHO_MESA,
    RECURSO_MESA,
    RECURSO_REGISTRO,
    RECURSO_VOTO,
    RECURSOS,
    coletar_sessao_completa,
    conferir_prefixo,
    gravar_conferencia,
    sessoes_ordinarias,
    total_entries_da_pagina,
)
from config_cidade import (  # noqa: E402
    ARQUIVO_CONFIG,
    PAUSA_SAPL_SEGUNDOS,
    anos_recorte,
    carregar_config,
    endereco_sapl,
    id_tipo_sessao_ordinaria,
)
from derivar_insumos import (  # noqa: E402
    BRUTOS,
    pasta_lote_mais_recente,
    pasta_porsessao_mais_recente,
)

TETO_EXECUCAO = 400
ESPERA_PENDENTES_SEGUNDOS = 300
CHANGELOG = RAIZ / "CHANGELOG.md"
RESUMO_INSUMOS = BRUTOS / "resumo_insumos.json"


def esperar_antes_da_repeticao(segundos: int = ESPERA_PENDENTES_SEGUNDOS) -> None:
    """Espera de 5 minutos entre a coleta e a repeticao dos pendentes.

    Funcao separada para os testes mockarem sem esperar de verdade.
    A pausa de 2,5 s entre pedidos continua valendo dentro da repeticao.
    """
    time.sleep(segundos)


def nova_fila_pendentes() -> list:
    """Fila de pedidos que falharam e serao repetidos uma vez ao fim."""
    return []


def arquivo_bom(pasta: Path, arquivo: str) -> bool:
    """Arquivo salvo que pode ser usado: existe, nao esta vazio e e JSON valido."""
    caminho = pasta / arquivo
    if not caminho.is_file() or caminho.stat().st_size == 0:
        return False
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return False
    return isinstance(dados, dict)


PREFIXOS_LISTA_DESCOBERTA = ("sessaoplenaria_ano", "materialegislativa_ano")


def e_lista_descoberta(arquivo: str | None) -> bool:
    """Lista que descobre a sessao nova. Falha nela bloqueia a publicacao."""
    if not arquivo:
        return False
    nome = str(arquivo).split("/")[-1]
    return nome.startswith(PREFIXOS_LISTA_DESCOBERTA)


def e_indice_api(arquivo: str | None) -> bool:
    """Indice da API. Sem ele o plano do lote nao existe, por isso bloqueia."""
    if not arquivo:
        return False
    return str(arquivo).split("/")[-1] == "api_indice.json"


def maior_data_inicio(sessoes: list[dict]) -> str:
    """Maior data_inicio da lista de sessoes, ou vazio quando nao ha data."""
    datas = [str(item.get("data_inicio") or "") for item in sessoes or []]
    datas = [item for item in datas if item]
    return max(datas) if datas else ""


def conferir_lista_nao_regrediu(antes: list[dict], depois: list[dict]) -> None:
    """A lista de sessoes nao pode voltar no tempo depois da coleta.

    Se a maior data_inicio depois da coleta for menor que a de antes,
    a lista veio incompleta e nada pode ser publicado.
    """
    maxima_antes = maior_data_inicio(antes)
    maxima_depois = maior_data_inicio(depois)
    if maxima_antes and maxima_depois and maxima_depois < maxima_antes:
        raise SystemExit(
            "Lista de sessoes regrediu depois da coleta "
            f"(antes {maxima_antes}, agora {maxima_depois}). Nada foi publicado."
        )


def repetir_pendentes(pendentes: list, ids_novas: list[int], simulado: bool = False) -> list[str]:
    """Espera 5 minutos e repete uma vez cada pendente, um por vez.

    Cada repeticao conta no teto de 400 e respeita a pausa de 2,5 s,
    nunca em paralelo. Resposta vazia ou invalida nunca e gravada, por
    isso o arquivo bom anterior segue intacto. Devolve os avisos de
    itens antigos que seguiram com o arquivo salvo. Se, depois da
    repeticao, ainda faltar algo da sessao do alvo (nova mais a ultima
    em revisao), da lista de descoberta (sessoes ou materias do ano),
    do indice da API, ou qualquer item sem arquivo anterior, levanta
    SystemExit com a lista do que faltou e nada e publicado.
    """
    avisos: list[str] = []
    if not pendentes:
        return avisos
    print(
        f"{len(pendentes)} pedidos pendentes. "
        "Espero 5 minutos e repito uma vez cada um."
    )
    if not simulado:
        esperar_antes_da_repeticao()
    restantes = []
    for item in pendentes:
        print(f"repetindo: {item['descricao']}")
        try:
            item["refazer"]()
        except PedidoPendente as exc:
            restantes.append(item)
            print(f"  continua pendente: {item['descricao']} ({exc.motivo})")
    novas = {int(item) for item in ids_novas}
    faltando_nova: list[str] = []
    faltando_descoberta: list[str] = []
    faltando_indice: list[str] = []
    faltando_sem_arquivo: list[str] = []
    for item in restantes:
        sid = item.get("sessao_id")
        arquivo = item.get("arquivo")
        if e_lista_descoberta(arquivo):
            faltando_descoberta.append(item["descricao"])
            continue
        if e_indice_api(arquivo):
            faltando_indice.append(item["descricao"])
            continue
        if sid is not None and int(sid) in novas:
            faltando_nova.append(item["descricao"])
            continue
        pasta = item.get("pasta")
        if pasta is not None and arquivo is not None and arquivo_bom(pasta, arquivo):
            avisos.append(item["descricao"])
            print(f"  aviso: {item['descricao']}. Sigo com o arquivo ja salvo.")
            continue
        if sid is not None and pasta is not None and sessao_tem_arquivo(pasta, int(sid)):
            avisos.append(item["descricao"])
            print(f"  aviso: {item['descricao']}. Sigo com os arquivos ja salvos da sessao.")
            continue
        faltando_sem_arquivo.append(item["descricao"])
    if faltando_nova or faltando_descoberta or faltando_indice or faltando_sem_arquivo:
        partes = []
        if faltando_descoberta:
            partes.append(
                "da lista de descoberta (sessoes ou materias do ano): "
                + "; ".join(faltando_descoberta)
            )
        if faltando_indice:
            partes.append("do indice da API: " + "; ".join(faltando_indice))
        if faltando_nova:
            partes.append("da sessao nova: " + "; ".join(faltando_nova))
        if faltando_sem_arquivo:
            partes.append("sem arquivo anterior: " + "; ".join(faltando_sem_arquivo))
        raise SystemExit(
            "Faltou dado depois da repeticao. Nada foi publicado. Faltando "
            + ". ".join(partes)
        )
    return avisos

GERADORES = (
    "dados/tratados/gerar_tabela_vereadores.py",
    "dados/tratados/gerar_presidencia_sessoes.py",
    "dados/tratados/gerar_autoria_materias.py",
    "dados/tratados/gerar_atuacao_vereadores.py",
    "dados/tratados/gerar_temas_votacoes.py",
    "dados/tratados/gerar_dados_tela.py",
)

PREFIXOS_GRANDES_POR_SESSAO = frozenset(
    {
        "sessaoplenariapresenca",
        "presencaordemdia",
        "ordemdia",
        "registrovotacao",
        "votoparlamentar",
        "justificativaausencia",
        "integrantemesa",
    }
)


class OrcamentoExecucao:
    """Conta os pedidos novos desta execucao, somando lote, sessao e autoria."""

    def __init__(self, teto: int = TETO_EXECUCAO):
        if isinstance(teto, bool) or not isinstance(teto, int) or teto < 1 or teto > TETO_EXECUCAO:
            raise ValueError(
                f"O teto por execucao fica entre 1 e {TETO_EXECUCAO} pedidos."
            )
        self.teto = teto
        self.pedidos = 0


def anos_da_execucao(cfg: dict, hoje: date) -> list[int]:
    """Anos ja gravados no config. O ano corrente nao entra sozinho."""
    if not isinstance(hoje, date):
        raise SystemExit("Data da execucao invalida.")
    return sorted(anos_recorte(cfg))


def ano_corrente_candidato(cfg: dict, hoje: date) -> int | None:
    """Ano de hoje se estiver na legislatura e ainda nao estiver no recorte."""
    anos = list(anos_recorte(cfg))
    inicio = int(cfg["sapl"]["legislatura_inicio"])
    fim = int(cfg["sapl"]["legislatura_fim"])
    if inicio <= hoje.year <= fim and hoje.year not in anos:
        return int(hoje.year)
    return None


def ha_sessao_ordinaria(dados: dict, tipo_ordinaria: int) -> bool:
    if not isinstance(dados, dict):
        return False
    resultados = dados.get("results")
    if isinstance(resultados, list) and resultados:
        return any(
            isinstance(item, dict) and int(item.get("tipo") or 0) == int(tipo_ordinaria)
            for item in resultados
        )
    paginacao = dados.get("pagination") or {}
    total = paginacao.get("total_entries")
    if total is None and isinstance(dados.get("count"), int) and not isinstance(dados.get("count"), bool):
        total = dados.get("count")
    return isinstance(total, int) and not isinstance(total, bool) and total >= 1


def confirmar_sessao_ordinaria_no_ano(coletor: ColetorLote, ano: int, tipo_ordinaria: int) -> bool:
    """Um pedido ao SAPL, com a pausa do coletor. Nao pagina."""
    dados = coletor.pedir(
        "/api/sessao/sessaoplenaria/",
        {
            "data_inicio__year": int(ano),
            "tipo": int(tipo_ordinaria),
            "page": 1,
            "page_size": 1,
        },
        f"sonda_ordinaria_ano{int(ano)}.json",
        refrescar=True,
    )
    return ha_sessao_ordinaria(dados, tipo_ordinaria)


def incluir_ano_se_confirmado(cfg: dict, hoje: date, simulado: bool, confirmar) -> tuple[list[int], bool]:
    """Acrescenta o ano corrente so quando o SAPL tem sessao ordinaria.

    No modo simulado nao ha pedido. Sem sessao, o recorte segue como esta.
    """
    anos = anos_da_execucao(cfg, hoje)
    candidato = ano_corrente_candidato(cfg, hoje)
    if candidato is None:
        return anos, False
    if simulado:
        print(
            f"Ano {candidato} esta na legislatura. "
            "Modo simulado nao consulta o SAPL. O ano nao entrou no recorte."
        )
        return anos, False
    if confirmar(candidato):
        print(f"Ano {candidato} confirmado no SAPL e incluido no recorte.")
        return sorted(anos + [candidato]), True
    print(f"Ano {candidato} sem sessao ordinaria no SAPL. O recorte nao mudou.")
    return anos, False


def gravar_anos_no_config(anos: list[int]) -> None:
    dados = json.loads(ARQUIVO_CONFIG.read_text(encoding="utf-8"))
    dados["recorte"]["anos"] = [int(ano) for ano in anos]
    texto = json.dumps(dados, ensure_ascii=False, indent=2) + "\n"
    ARQUIVO_CONFIG.write_bytes(texto.encode("utf-8"))


def pasta_autoria_mais_recente(brutos: Path) -> Path:
    candidatas = [
        caminho
        for caminho in brutos.glob("lote_*_autoria")
        if caminho.is_dir()
        and (caminho / "indice.json").exists()
        and (caminho / "autor_p1.json").exists()
    ]
    if not candidatas:
        raise SystemExit("Nenhuma pasta de autoria em dados/brutos. Nada foi baixado.")
    return sorted(candidatas)[-1]


def preparar_coletor(cfg: dict, pasta: Path, orcamento: OrcamentoExecucao, simulado: bool) -> ColetorLote:
    coletor = ColetorLote(cfg, pasta, teto=orcamento.teto)
    coletor.orcamento_execucao = orcamento
    coletor.simulado = simulado
    coletor.teto = coletor.pedidos + orcamento.teto
    coletor.adiar_falha = True
    return coletor


def sessao_tem_arquivo(pasta: Path, sid: int) -> bool:
    return all(
        (pasta / f"sessao_{sid}_{recurso}_p1.json").is_file()
        for _caminho, recurso in RECURSOS
    )


def sessoes_novas(pasta_porsessao: Path | None, sessoes: list[dict]) -> list[dict]:
    """Ordinarias que ainda nao tem arquivo na pasta por sessao."""
    if pasta_porsessao is None:
        return list(sessoes)
    return [
        sessao
        for sessao in sessoes
        if not sessao_tem_arquivo(pasta_porsessao, int(sessao["id"]))
    ]


def ultima_sessao_coletada(
    pasta_porsessao: Path | None, sessoes: list[dict]
) -> dict | None:
    """Ultima ordinaria ja coletada, para pegar lancamento atrasado no SAPL."""
    if pasta_porsessao is None:
        return None
    coletadas = [
        sessao
        for sessao in sessoes
        if sessao_tem_arquivo(pasta_porsessao, int(sessao["id"]))
    ]
    if not coletadas:
        return None
    return sorted(
        coletadas,
        key=lambda item: (
            str(item.get("data_inicio") or ""),
            int(item.get("numero") or 0),
            int(item["id"]),
        ),
    )[-1]


PEDIDOS_MINIMOS_POR_SESSAO = len(RECURSOS) + 1


def custo_minimo_sessoes(n_sessoes: int) -> int:
    """Piso de pedidos da coleta por sessao: 4 recursos mais a mesa.

    Registros por ordem e votos por registro custam a mais e variam
    por sessao, por isso o retorno e minimo, nunca teto.
    """
    return max(0, int(n_sessoes)) * PEDIDOS_MINIMOS_POR_SESSAO


def sessoes_alvo_para_coleta(
    sessoes: list[dict], pasta_porsessao: Path | None
) -> tuple[list[dict], list[dict]]:
    """Novas mais sempre a ultima ja coletada para revisao de lancamento atrasado.

    Mesmo sem sessao nova, a ultima e refeita para pegar lancamento
    atrasado no SAPL. Sem nenhuma coletada, o alvo sao as novas.
    """
    novas = sessoes_novas(pasta_porsessao, sessoes)
    ultima = ultima_sessao_coletada(pasta_porsessao, sessoes)
    if ultima is None:
        return novas, list(novas)
    ids_novas = {int(item["id"]) for item in novas}
    alvo = list(novas)
    if int(ultima["id"]) not in ids_novas:
        alvo.append(ultima)
    alvo = sorted(
        alvo,
        key=lambda item: (
            str(item.get("data_inicio") or ""),
            int(item.get("numero") or 0),
            int(item["id"]),
        ),
    )
    return novas, alvo


def plano_sem_listas_grandes(anos: list[int], indice: dict) -> list[dict]:
    """Plano em lote sem as listas grandes que agora saem por sessao."""
    plano = plano_de_coleta(anos, indice)
    return [
        item
        for item in plano
        if str(item.get("prefixo") or "") not in PREFIXOS_GRANDES_POR_SESSAO
        and not str(item.get("prefixo") or "").endswith("_por_id")
    ]


def atualizar_paginas(
    coletor: ColetorLote,
    caminho: str,
    params: dict,
    prefixo: str,
    simulado: bool,
    pendentes: list | None = None,
) -> None:
    """Reconfere a primeira pagina. So repete as seguintes se ela mudou ou faltar arquivo.

    Com fila de pendentes, o pedido que falhar depois das tentativas
    extras nao para a coleta: entra na fila e e repetido uma vez ao fim.
    """
    params = dict(params)
    params["page_size"] = PAGE_SIZE
    params["page"] = 1
    try:
        primeiro = coletor.pedir(caminho, params, f"{prefixo}_p1.json", refrescar=not simulado)
    except PedidoPendente as exc:
        if pendentes is None:
            raise
        pendentes.append(
            {
                "descricao": f"{prefixo} pagina 1 ({exc.motivo})",
                "sessao_id": None,
                "pasta": coletor.pasta,
                "arquivo": f"{prefixo}_p1.json",
                "refazer": lambda: atualizar_paginas(
                    coletor, caminho, params, prefixo, simulado, None
                ),
            }
        )
        return
    if not isinstance(primeiro, dict):
        raise SystemExit(f"{prefixo}: resposta sem objeto JSON")
    pagina1_igual = simulado or bool(coletor.ultimo_igual)

    def baixar(pagina: int):
        params["page"] = pagina
        arquivo = f"{prefixo}_p{pagina}.json"
        existe = (coletor.pasta / arquivo).is_file()
        refrescar = (not simulado) and existe and (not pagina1_igual)
        try:
            dados = coletor.pedir(caminho, params, arquivo, refrescar=refrescar)
        except PedidoPendente as exc:
            if pendentes is None:
                raise
            retrato = dict(params)
            pendentes.append(
                {
                    "descricao": f"{prefixo} pagina {pagina} ({exc.motivo})",
                    "sessao_id": None,
                    "pasta": coletor.pasta,
                    "arquivo": arquivo,
                    "refazer": lambda: coletor.pedir(
                        caminho, dict(retrato), arquivo, refrescar=True
                    ),
                }
            )
            return None
        if not isinstance(dados, dict):
            raise SystemExit(f"{prefixo}: resposta sem objeto JSON")
        return dados

    continuar_apos_primeira(primeiro, prefixo, baixar)


def estimar_sondas(pasta_lote: Path, anos: list[int]) -> tuple[int, int]:
    """Pedidos numa semana sem sessao nova. As listas grandes nao entram.

    O primeiro numero e a conferencia das listas pequenas ja salvas
    mais a lista inteira de autoria com o=id (hoje 13 paginas) e os 3
    catalogos de autor. A autoria e sempre refeita por inteiro, pois
    correcao antiga no SAPL so aparece na lista completa.
    O segundo e zero, mantido para compatibilidade: nao ha mais leitura
    ordering=id em lote, pois as listas grandes saem por sessao.
    """
    indice_path = pasta_lote / "api_indice.json"
    if not indice_path.is_file():
        return 0, 0
    indice = json.loads(indice_path.read_text(encoding="utf-8"))
    plano = plano_sem_listas_grandes(anos, indice)
    try:
        pasta_autoria = pasta_autoria_mais_recente(BRUTOS)
        paginas_autoria = len(list(pasta_autoria.glob("autoria_p*.json")))
    except SystemExit:
        paginas_autoria = 0
    if paginas_autoria < 1:
        paginas_autoria = 13
    conferencia = 1 + len(plano) + 3 + paginas_autoria
    return conferencia, 0


def baixar_lote(coletor: ColetorLote, anos: list[int], simulado: bool, pendentes: list | None = None) -> None:
    """Lote pequeno: catalogos, sessoes do ano, materias do ano e expediente.

    As listas grandes de presenca, ordem, voto, justificativa e mesa ficam
    de fora. Elas sao coletadas por sessao, so das novas e da ultima.
    O indice da API entra na fila de pendentes como os vizinhos. Se ele
    continuar falhando depois da repeticao, a publicacao e bloqueada.
    """
    try:
        indice = coletor.pedir("/api/", None, "api_indice.json", refrescar=not simulado)
    except PedidoPendente as exc:
        if pendentes is None:
            raise
        pendentes.append(
            {
                "descricao": f"indice da API ({exc.motivo})",
                "sessao_id": None,
                "pasta": coletor.pasta,
                "arquivo": "api_indice.json",
                "refazer": lambda: baixar_lote(coletor, anos, simulado, None),
            }
        )
        return
    if not isinstance(indice, dict):
        raise SystemExit("Indice da API nao e um objeto JSON.")
    plano = plano_sem_listas_grandes(anos, indice)
    for item in plano:
        print(item["prefixo"])
        atualizar_paginas(coletor, item["caminho"], item["params"], item["prefixo"], simulado, pendentes)


def coletar_sessoes_novas(
    coletor: ColetorLote,
    sessoes: list[dict],
    pendentes: list | None = None,
    ids_novas: set[int] | list[int] | None = None,
) -> None:
    """Coleta por sessao dos pacotes grandes, com mesa, registros e votos.

    Com fila de pendentes, a sessao que falhar por rede ou recusa do
    SAPL nao para as outras: entra na fila e e refeita por inteiro uma
    vez ao fim. A recusa por vazio suspeito continua parando, pois
    indica filtro mudado no SAPL.

    A decisao de sessao nova e tomada uma vez aqui (id em ids_novas) e
    reaproveitada na repeticao, em vez de olhar o disco de novo. Sem
    ids_novas, cada sessao decide pelo disco, so para uso isolado.
    """
    novas = {int(item) for item in ids_novas} if ids_novas is not None else None
    for sessao in sessoes:
        sid = int(sessao["id"])
        print(f"sessao {sid} numero {sessao.get('numero')} {sessao.get('data_inicio')}")
        if novas is None:
            e_nova = None
        else:
            e_nova = sid in novas
        try:
            if e_nova is None:
                resumo = coletar_sessao_completa(coletor, sid)
            else:
                resumo = coletar_sessao_completa(coletor, sid, e_nova)
        except PedidoPendente as exc:
            if pendentes is None:
                raise
            if e_nova is None:
                refazer = lambda sid=sid: coletar_sessao_completa(coletor, sid)
            else:
                refazer = lambda sid=sid, e_nova=e_nova: coletar_sessao_completa(
                    coletor, sid, e_nova
                )
            pendentes.append(
                {
                    "descricao": f"sessao {sid} ({exc.motivo})",
                    "sessao_id": sid,
                    "pasta": coletor.pasta,
                    "arquivo": None,
                    "e_nova": e_nova,
                    "refazer": refazer,
                }
            )
            continue
        print(
            f"  ordem {resumo['n_ordem']}, "
            f"registros {resumo['n_registros']}, votos {resumo['n_votos']}"
        )


def coletar_autoria(coletor: ColetorLote, anos: list[int], simulado: bool, pendentes: list | None = None) -> None:
    """Autoria estavel: lista inteira com o=id, toda semana.

    A lista sem ordenacao mistura as paginas entre um pedido e outro
    (ids repetidos e faltando). Com o=id ela vem em ordem crescente e
    repete igual. Por isso toda a lista e refeita aqui (hoje 13 paginas),
    e nao so a primeira pagina: uma correcao antiga no SAPL so aparece
    na lista inteira. Os catalogos pequenos (autor, tipoautor, cargomesa)
    seguem no esquema de reconferir a pagina 1. O filtro por ano e
    ignorado pelo SAPL e nao e mais pedido.

    Depois de baixar, os ids unicos tem que somar total_entries. Se nao
    fechar (duplicado ou faltando), os arquivos novos sao descartados,
    valem os antigos e o item entra na fila de pendentes para repetir
    uma vez ao fim, com aviso no CHANGELOG. Resposta vazia ou invalida
    nunca substitui arquivo bom (o proprio coletor ja recusa).
    """
    for caminho, prefixo in PLANO:
        if prefixo == "autoria":
            continue
        print(prefixo)
        atualizar_paginas(coletor, caminho, {}, prefixo, simulado, pendentes)
    print("autoria")
    coletar_autoria_estavel(coletor, simulado, pendentes)


def coletar_autoria_estavel(coletor: ColetorLote, simulado: bool, pendentes: list | None = None) -> None:
    prefixo = "autoria"
    caminho = "/api/materia/autoria/"
    antigos: dict[str, bytes] = {}
    numero = 1
    while (coletor.pasta / f"{prefixo}_p{numero}.json").is_file():
        antigos[f"{prefixo}_p{numero}.json"] = (coletor.pasta / f"{prefixo}_p{numero}.json").read_bytes()
        numero += 1

    def restaurar() -> None:
        atual = 1
        while (coletor.pasta / f"{prefixo}_p{atual}.json").is_file():
            atual += 1
        for pos in range(1, atual):
            nome = f"{prefixo}_p{pos}.json"
            if nome in antigos:
                (coletor.pasta / nome).write_bytes(antigos[nome])
            else:
                (coletor.pasta / nome).unlink()

    def adiar(descricao: str, arquivo: str, motivo: str, refazer) -> None:
        if pendentes is None:
            raise PedidoPendente(caminho, dict(PARAMS_AUTORIA_ESTAVEL), arquivo, motivo)
        pendentes.append(
            {
                "descricao": descricao,
                "sessao_id": None,
                "pasta": coletor.pasta,
                "arquivo": arquivo,
                "refazer": refazer,
            }
        )

    if simulado:
        return
    params = dict(PARAMS_AUTORIA_ESTAVEL)
    params["page_size"] = PAGE_SIZE
    params["page"] = 1
    try:
        primeiro = coletor.pedir(caminho, params, f"{prefixo}_p1.json", refrescar=True)
    except PedidoPendente as exc:
        restaurar()
        adiar(
            f"autoria pagina 1 ({exc.motivo})",
            f"{prefixo}_p1.json",
            exc.motivo,
            lambda: coletar_autoria_estavel(coletor, simulado, None),
        )
        return
    except SystemExit as exc:
        restaurar()
        if coletar_lote.motivo_bloqueante(str(exc)):
            raise
        adiar(
            f"autoria pagina 1 ({exc})",
            f"{prefixo}_p1.json",
            str(exc),
            lambda: coletar_autoria_estavel(coletor, simulado, None),
        )
        return
    if not isinstance(primeiro, dict):
        restaurar()
        adiar(
            "autoria pagina 1 (resposta sem objeto JSON)",
            f"{prefixo}_p1.json",
            "resposta sem objeto JSON",
            lambda: coletar_autoria_estavel(coletor, simulado, None),
        )
        return

    def baixar(pagina: int):
        params["page"] = pagina
        arquivo = f"{prefixo}_p{pagina}.json"
        try:
            return coletor.pedir(caminho, dict(params), arquivo, refrescar=True)
        except PedidoPendente as exc:
            restaurar()
            raise PedidoPendente(
                caminho, dict(PARAMS_AUTORIA_ESTAVEL), arquivo, exc.motivo
            ) from exc
        except SystemExit as exc:
            restaurar()
            raise

    try:
        continuar_apos_primeira(primeiro, prefixo, baixar)
    except (PedidoPendente, SystemExit) as exc:
        restaurar()
        if isinstance(exc, SystemExit) and coletar_lote.motivo_bloqueante(str(exc)):
            raise
        motivo = exc.motivo if isinstance(exc, PedidoPendente) else str(exc)
        adiar(
            f"autoria ({motivo})",
            f"{prefixo}_p1.json",
            motivo,
            lambda: coletar_autoria_estavel(coletor, simulado, None),
        )
        return
    ok, detalhe = conferir_autoria(coletor.pasta, prefixo)
    if not ok:
        print(f"  autoria com o=id nao fecha ({detalhe}). Valem os arquivos antigos.")
        restaurar()
        adiar(
            f"autoria nao fecha ({detalhe})",
            f"{prefixo}_p1.json",
            detalhe,
            lambda: coletar_autoria_estavel(coletor, simulado, None),
        )
        return
    print(f"  autoria confere: {detalhe}.")


def retrato_autoria(pasta: Path, prefixo: str = "autoria") -> dict[str, bytes]:
    """Copia dos arquivos da autoria antes da coleta, para restaurar depois."""
    retrato: dict[str, bytes] = {}
    numero = 1
    while (pasta / f"{prefixo}_p{numero}.json").is_file():
        nome = f"{prefixo}_p{numero}.json"
        retrato[nome] = (pasta / nome).read_bytes()
        numero += 1
    return retrato


def restaurar_autoria(pasta: Path, retrato: dict[str, bytes], prefixo: str = "autoria") -> None:
    """Devolve a autoria ao estado anterior. Pagina nova alem do retrato e apagada."""
    atual = 1
    while (pasta / f"{prefixo}_p{atual}.json").is_file():
        atual += 1
    for pos in range(1, atual):
        nome = f"{prefixo}_p{pos}.json"
        if nome in retrato:
            (pasta / nome).write_bytes(retrato[nome])
        else:
            (pasta / nome).unlink()


def conferir_autoria_apos_repeticao(pasta: Path, retrato: dict[str, bytes]) -> str | None:
    """Confere a autoria depois da repeticao. Se nao fechar, restaura e devolve o aviso.

    Devolve None quando confere, ou o texto do aviso para o CHANGELOG quando
    a lista ficou misturada. Nunca mistura pagina nova no meio das antigas:
    ou a lista inteira e nova e confere, ou valem as antigas.
    """
    ok, detalhe = conferir_autoria(pasta)
    if ok:
        return None
    restaurar_autoria(pasta, retrato)
    return f"autoria nao fecha depois da repeticao ({detalhe}). Valem os arquivos antigos."


def pasta_tramitacao_mais_recente(brutos: Path) -> Path | None:
    candidatas = [
        caminho
        for caminho in brutos.glob("lote_*_tramitacao")
        if caminho.is_dir() and (caminho / "indice.json").exists()
    ]
    if not candidatas:
        return None
    return sorted(candidatas)[-1]


def fichas_em_tramitacao(pasta_lote: Path) -> dict[int, bool]:
    """Id da materia para em_tramitacao, lido da ficha no lote mais recente."""
    mapa: dict[int, bool] = {}
    for caminho in sorted(pasta_lote.glob("materialegislativa_ano*_p*.json")):
        dados = ler_json(caminho)
        if not isinstance(dados, dict):
            continue
        for item in dados.get("results") or []:
            if isinstance(item, dict) and item.get("id") is not None:
                mapa[int(item["id"])] = bool(item.get("em_tramitacao"))
    return mapa


def coletar_tramitacao(
    coletor: ColetorLote,
    pasta_lote: Path,
    simulado: bool,
    pendentes: list | None = None,
) -> None:
    """Tramitacao so das materias novas ou com em_tramitacao verdadeiro.

    Mesma pausa e teto da execucao, um pedido por vez. Tipos lidos do
    config, nunca fixos aqui. Catalogos de status e unidades sao
    reconferidos pagina a pagina. Com fila de pendentes, a materia que
    falhar por rede ou recusa entra na fila e e refeita uma vez ao fim.
    """
    from coletar_tramitacao import (
        carregar_materias_alvo,
        conferir_tramitacao,
        tem_proxima_pagina as tem_proxima,
        numero_da_proxima as numero_proxima,
    )

    cfg = carregar_config()
    alvos = carregar_materias_alvo(cfg)
    fichas = fichas_em_tramitacao(pasta_lote)

    def baixar_materia(mid: int, arquivo: str, existe: bool) -> None:
        primeira = coletor.pedir(
            "/api/materia/tramitacao/",
            {"materia": mid},
            arquivo,
            refrescar=existe,
        )
        conferir_tramitacao(primeira, mid, arquivo)
        if not isinstance(primeira, dict):
            return
        pagina = int((primeira.get("pagination") or {}).get("page") or 1)
        atual = primeira
        while tem_proxima(atual):
            pagina = numero_proxima(atual, pagina)
            proximo = f"tramitacao_materia{mid}_p{pagina}.json"
            try:
                atual = coletor.pedir(
                    "/api/materia/tramitacao/",
                    {"materia": mid, "page": pagina},
                    proximo,
                    refrescar=(coletor.pasta / proximo).is_file(),
                )
                conferir_tramitacao(atual, mid, proximo)
            except SystemExit as exc:
                print(f"  Falhou {proximo}, sigo: {exc}")
                break

    for materia in alvos:
        mid = int(materia["id"])
        arquivo = f"tramitacao_materia{mid}_p1.json"
        existe = (coletor.pasta / arquivo).is_file()
        if existe and not fichas.get(mid, False):
            continue
        if simulado:
            print(f"  {arquivo} ausente ou em tramitacao. Modo simulado nao baixa.")
            continue
        print(f"tramitacao materia {mid}")
        try:
            baixar_materia(mid, arquivo, existe)
        except PedidoPendente as exc:
            if pendentes is None:
                raise
            pendentes.append(
                {
                    "descricao": f"tramitacao materia {mid} ({exc.motivo})",
                    "sessao_id": None,
                    "pasta": coletor.pasta,
                    "arquivo": arquivo,
                    "refazer": lambda mid=mid, arquivo=arquivo: baixar_materia(
                        mid, arquivo, (coletor.pasta / arquivo).is_file()
                    ),
                }
            )
            continue
        except SystemExit as exc:
            print(f"  Falhou a materia {mid}, sigo: {exc}")
            continue
    for caminho, prefixo in (
        ("/api/materia/statustramitacao/", "statustramitacao"),
        ("/api/materia/unidadetramitacao/", "unidadetramitacao"),
    ):
        print(prefixo)
        atualizar_paginas(coletor, caminho, {}, prefixo, simulado, pendentes)


def rodar(argumentos: list[str]) -> None:
    print(">", " ".join(argumentos))
    resultado = subprocess.run([sys.executable, *argumentos], cwd=RAIZ)
    if resultado.returncode != 0:
        raise SystemExit(resultado.returncode)


def ler_json(caminho: Path) -> dict:
    """Le um bruto como dicionario, sem nunca estourar JSONDecodeError.

    Arquivo ausente, vazio ou ilegivel devolve dicionario vazio. Resposta
    vazia do SAPL nunca e dado, por isso vazio aqui significa ausente.
    """
    if not caminho.is_file():
        return {}
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return {}
    return dados if isinstance(dados, dict) else {}


def linhas_contagem(antes: dict, depois: dict) -> list[str]:
    rotulos = (
        ("sessoes_ordinarias", "sessões ordinárias"),
        ("votacoes", "votações"),
        ("n_presencas_sessao", "presenças na sessão"),
        ("n_justificativas", "justificativas de ausência"),
    )
    linhas = []
    anos = sorted(set(antes) | set(depois), key=lambda item: int(item))
    for ano in anos:
        bloco_antes = antes.get(ano) or {}
        bloco_depois = depois.get(ano) or {}
        if not isinstance(bloco_depois, dict) or not bloco_depois:
            continue
        partes = []
        for chave, rotulo in rotulos:
            if chave not in bloco_depois:
                continue
            novo = bloco_depois.get(chave)
            velho = bloco_antes.get(chave) if isinstance(bloco_antes, dict) else None
            if velho is None or velho == novo:
                continue
            partes.append(f"{rotulo} de {velho} para {novo}")
        if partes:
            linhas.append(f"{ano}: " + ", ".join(partes) + ".")
    return linhas


def ler_hashes(anos: list[int]) -> dict[str, str]:
    saida = {}
    for ano in anos:
        caminho = RAIZ / "dados" / "tratados" / f"atuacao_vereadores_{ano}.json.sha256"
        if caminho.is_file():
            saida[str(ano)] = caminho.read_text(encoding="utf-8").strip()
    return saida


def linhas_hash(antes: dict, depois: dict) -> list[str]:
    linhas = []
    for ano in sorted(depois, key=lambda item: int(item)):
        if antes.get(ano) == depois.get(ano):
            continue
        linhas.append(f"Hash SHA-256 de atuacao_vereadores_{ano}.json: {depois[ano]}.")
    return linhas


def linhas_sessoes(sessoes: list[dict]) -> list[str]:
    if not sessoes:
        return ["Nenhuma sessão ordinária nova."]
    linhas = []
    for item in sessoes:
        numero = item.get("numero")
        data = item.get("data_inicio") or "data não informada no SAPL"
        if numero is None:
            linhas.append(
                f"Sessão ordinária sem número no SAPL, data {data} (registro {item['id']})."
            )
        else:
            linhas.append(
                f"Sessão ordinária {numero}, data {data} (registro {item['id']})."
            )
    return linhas


def montar_entrada(
    data_iso: str,
    fonte: str,
    pedidos: int,
    sessoes: list[dict],
    contagens: list[str],
    hashes: list[str],
    avisos: list[str] | None = None,
    temas: list[str] | None = None,
) -> str:
    linhas = [
        f"## {data_iso}: atualização semanal dos dados",
        "",
        "**O que mudou nos dados**",
    ]
    for linha in linhas_sessoes(sessoes):
        linhas.append(f"- {linha}")
    if contagens:
        for linha in contagens:
            linhas.append(f"- {linha}")
    else:
        linhas.append("- As contagens acompanhadas permaneceram iguais.")
    if hashes:
        for linha in hashes:
            linhas.append(f"- {linha}")
    else:
        linhas.append("- Nenhum hash de atuação mudou.")
    for linha in temas or []:
        linhas.append(f"- {linha}")
    for aviso in avisos or []:
        linhas.append(f"- Coleta com aviso: {aviso}. Valeu o arquivo ja salvo.")
    linhas.append(f"- Pedidos ao SAPL nesta execução: {pedidos}.")
    linhas.extend(
        [
            "",
            "**O que mudou na tela**",
            "- Nenhuma. A tela só muda depois que o mantenedor aprovar.",
            "",
            "**De onde veio**",
            f"- SAPL consultado: {fonte}.",
            f"- Coleta de {data_iso}.",
        ]
    )
    return "\n".join(linhas) + "\n"


def inserir_entrada(texto: str, entrada: str) -> str:
    marca = "\n---\n"
    pos = texto.find(marca)
    if pos < 0:
        raise SystemExit("CHANGELOG.md sem o separador esperado. Nada foi reescrito.")
    ponto = pos + len(marca)
    return texto[:ponto] + "\n" + entrada.strip() + "\n\n" + texto[ponto:].lstrip("\n")


def gravar_changelog(entrada: str) -> None:
    texto = CHANGELOG.read_text(encoding="utf-8")
    novo = inserir_entrada(texto, entrada)
    if "\r" in novo:
        raise SystemExit("CHANGELOG.md ficaria com fim de linha CR. Nao gravei.")
    CHANGELOG.write_bytes(novo.encode("utf-8"))


def bloqueio_de_rede(*_args, **_kwargs):
    raise SystemExit("Modo simulado: pedido de rede bloqueado.")


def separar_divergencias_por_alvo(
    divergencias: list[dict], ids_novas: list[int] | set[int], ids_alvo: list[int] | set[int]
) -> tuple[list[dict], list[str]]:
    """Divergencia na sessao nova bloqueia; na revisao vira aviso no CHANGELOG.

    So o alvo da semana importa. Divergencia de sessao fora do alvo e
    ignorada aqui, pois nao foi recoletada nesta execucao.
    """
    novas = {int(item) for item in ids_novas}
    alvo = {int(item) for item in ids_alvo}
    revisao = set(alvo) - set(novas)
    bloqueantes: list[dict] = []
    avisos: list[str] = []
    for conf in divergencias or []:
        try:
            sid = int(conf.get("sessao_id"))
        except (TypeError, ValueError):
            continue
        if sid in novas:
            bloqueantes.append(conf)
        elif sid in revisao:
            recurso = conf.get("recurso")
            motivo = conf.get("motivo")
            avisos.append(f"conferencia da sessao {sid} ({recurso}): {motivo}")
    return bloqueantes, avisos


def avisos_ordem_vazia(pasta_sessao: Path, ids_novas: list[int] | set[int]) -> list[str]:
    """Sessao nova sem itens na ordem do dia: aviso, nunca recusa.

    Presenca zerada continua recusando na coleta. Ordem vazia e comum
    (sessao so com expediente) e nao pode travar a semana.
    """
    avisos: list[str] = []
    for sid in sorted({int(item) for item in ids_novas}):
        total = total_entries_da_pagina(pasta_sessao, f"sessao_{sid}_ordemdia")
        if total == 0:
            avisos.append(f"sessao {sid} sem itens na ordem do dia no SAPL")
    return avisos


def conferir_coleta_por_sessao(pasta_sessao: Path, sessoes: list[dict]) -> list[dict]:
    """Confere pagina a pagina da coleta por sessao e grava a conferencia.

    Devolve as divergencias. Prefixo sem arquivo e so pulado, pois a
    sessao pode estar na fila de pendentes para repetir ao fim.
    """
    divergencias = []
    for sessao in sessoes:
        sid = int(sessao["id"])
        for _caminho, recurso in list(RECURSOS) + [(CAMINHO_MESA, RECURSO_MESA)]:
            prefixo = f"sessao_{sid}_{recurso}"
            if not (pasta_sessao / f"{prefixo}_p1.json").is_file():
                continue
            conf = conferir_prefixo(pasta_sessao, prefixo, sid, recurso)
            if not conf["bate"]:
                divergencias.append(conf)
    gravar_conferencia(pasta_sessao, sessoes, divergencias)
    return divergencias


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Atualizacao semanal dos dados do SAPL.")
    parser.add_argument(
        "--simulado",
        action="store_true",
        help="Nao abre rede. Usa os brutos ja salvos.",
    )
    args = parser.parse_args(argv)

    if PAUSA_SAPL_SEGUNDOS < 2.5:
        raise SystemExit("A pausa do SAPL esta abaixo de 2,5 s. Nao vou continuar.")

    cfg = carregar_config()
    hoje = date.today()
    fonte = endereco_sapl(cfg)
    orcamento = OrcamentoExecucao(TETO_EXECUCAO)
    pasta_lote = pasta_lote_mais_recente(BRUTOS)
    tipo = id_tipo_sessao_ordinaria(cfg)

    coletores = []
    pendentes = nova_fila_pendentes()
    avisos_coleta: list[str] = []

    def confirmar_ano(ano: int) -> bool:
        coletor_sonda = preparar_coletor(cfg, pasta_lote, orcamento, False)
        coletor_sonda.pular_pausa = False
        try:
            confirmou = confirmar_sessao_ordinaria_no_ano(coletor_sonda, ano, tipo)
        except PedidoPendente as exc:
            print(f"Ano {ano} sem confirmacao do SAPL ({exc.motivo}). O recorte nao mudou.")
            avisos_coleta.append(
                f"sonda do ano {ano} falhou ({exc.motivo}). O recorte nao mudou."
            )
            confirmou = False
        if not confirmou:
            coletor_sonda.gravou = False
        coletores.append(coletor_sonda)
        return confirmou
    anos, config_alterada = incluir_ano_se_confirmado(cfg, hoje, args.simulado, confirmar_ano)
    if config_alterada and not args.simulado:
        gravar_anos_no_config(anos)
        cfg = carregar_config()
    estimativa, paginas_por_id_ausentes = estimar_sondas(pasta_lote, anos)

    print("Atualizacao semanal")
    print(f"Fonte: {fonte}")
    print(f"Anos: {', '.join(str(ano) for ano in anos)}")
    print("Modo: simulado" if args.simulado else "Modo: rede")
    print(f"Pausa: {PAUSA_SAPL_SEGUNDOS} s. Teto: {TETO_EXECUCAO} pedidos. Um pedido por vez.")
    print(
        f"Estimativa de pedidos numa semana sem sessao nova: {estimativa}. "
        "Listas grandes nao saem mais em lote. "
        f"Cada sessao no alvo custa no minimo {PEDIDOS_MINIMOS_POR_SESSAO} pedidos "
        f"(presencas, ordem, justificativa, mesa, registros por ordem e votos por registro custam a mais)."
    )

    original_urlopen = coletar_lote.urllib.request.urlopen
    lista_novas: list[dict] = []
    lista_alvo: list[dict] = []
    try:
        if args.simulado:
            coletar_lote.urllib.request.urlopen = bloqueio_de_rede

        coletor_lote = preparar_coletor(cfg, pasta_lote, orcamento, args.simulado)
        coletores.append(coletor_lote)
        sessoes_antes = sessoes_ordinarias(pasta_lote, tipo)
        try:
            baixar_lote(coletor_lote, anos, args.simulado, pendentes)
        except OrcamentoEsgotado as exc:
            print(f"PAROU: {exc}")
            return 2

        tipo = id_tipo_sessao_ordinaria(cfg)
        sessoes = sessoes_ordinarias(pasta_lote, tipo)
        conferir_lista_nao_regrediu(sessoes_antes, sessoes)
        pasta_sessao = pasta_porsessao_mais_recente(BRUTOS)
        if pasta_sessao is None:
            lista_novas = list(sessoes)
            lista_alvo = list(sessoes)
        else:
            lista_novas, lista_alvo = sessoes_alvo_para_coleta(sessoes, pasta_sessao)
        print(f"Sessoes ordinarias no lote: {len(sessoes)}")
        print(f"Sessoes ordinarias novas: {len(lista_novas)}")
        if lista_alvo and len(lista_alvo) > len(lista_novas):
            print(f"Sessoes para revisao de lancamento atrasado: {len(lista_alvo) - len(lista_novas)}")

        minimo_sessoes = custo_minimo_sessoes(len(lista_alvo))
        if lista_alvo and not args.simulado:
            print(
                f"Custo minimo da coleta por sessao: {minimo_sessoes} pedidos "
                f"para {len(lista_alvo)} sessoes no alvo."
            )
            if orcamento.pedidos + minimo_sessoes > orcamento.teto:
                print(
                    f"PAROU: alvo com {len(lista_alvo)} sessoes precisa de ao menos "
                    f"{minimo_sessoes} pedidos e o teto e {orcamento.teto}. "
                    "A primeira coleta completa precisa ser feita em partes, "
                    "fora da rotina semanal. Nada foi publicado."
                )
                return 2

        if lista_alvo and args.simulado:
            print("Modo simulado: sessoes sem arquivo nao foram baixadas.")
        elif lista_alvo:
            if pasta_sessao is None:
                pasta_sessao = BRUTOS / f"lote_{hoje.strftime('%Y%m%d')}_porsessao"
            coletor_sessao = preparar_coletor(cfg, pasta_sessao, orcamento, False)
            coletores.append(coletor_sessao)
            try:
                coletar_sessoes_novas(
                    coletor_sessao,
                    lista_alvo,
                    pendentes,
                    {int(item["id"]) for item in lista_novas},
                )
            except OrcamentoEsgotado as exc:
                print(f"PAROU: {exc}")
                print(
                    "A primeira coleta completa precisa ser feita em partes, "
                    "fora da rotina semanal. Nada foi publicado."
                )
                return 2
            conferir_coleta_por_sessao(pasta_sessao, sessoes)

        pasta_autoria = pasta_autoria_mais_recente(BRUTOS)
        retrato_autoria_antes = retrato_autoria(pasta_autoria)
        coletor_autoria = preparar_coletor(cfg, pasta_autoria, orcamento, args.simulado)
        coletores.append(coletor_autoria)
        try:
            coletar_autoria(coletor_autoria, anos, args.simulado, pendentes)
        except OrcamentoEsgotado as exc:
            print(f"PAROU: {exc}")
            return 2

        pasta_tramitacao = pasta_tramitacao_mais_recente(BRUTOS)
        if pasta_tramitacao is None:
            if args.simulado:
                print("Sem pasta de tramitacao. Modo simulado nao baixa.")
            else:
                pasta_tramitacao = BRUTOS / f"lote_{hoje.strftime('%Y%m%d')}_tramitacao"
                coletor_tramitacao = preparar_coletor(cfg, pasta_tramitacao, orcamento, False)
                coletores.append(coletor_tramitacao)
                try:
                    coletar_tramitacao(coletor_tramitacao, pasta_lote, False, pendentes)
                except OrcamentoEsgotado as exc:
                    print(f"PAROU: {exc}")
                    return 2
        else:
            coletor_tramitacao = preparar_coletor(cfg, pasta_tramitacao, orcamento, args.simulado)
            coletores.append(coletor_tramitacao)
            try:
                coletar_tramitacao(coletor_tramitacao, pasta_lote, args.simulado, pendentes)
            except OrcamentoEsgotado as exc:
                print(f"PAROU: {exc}")
                return 2

        try:
            avisos_coleta.extend(
                repetir_pendentes(
                    pendentes,
                    [int(item["id"]) for item in lista_alvo],
                    args.simulado,
                )
            )
        except OrcamentoEsgotado as exc:
            print(f"PAROU: {exc}")
            return 2
        if not args.simulado:
            aviso_autoria = conferir_autoria_apos_repeticao(
                pasta_autoria, retrato_autoria_antes
            )
            if aviso_autoria is not None:
                print(f"  {aviso_autoria}")
                avisos_coleta.append(aviso_autoria)
        if pasta_sessao is not None and lista_novas and not args.simulado:
            for aviso in avisos_ordem_vazia(
                pasta_sessao, [int(item["id"]) for item in lista_novas]
            ):
                print(f"  aviso: {aviso}.")
                avisos_coleta.append(aviso)
        if pasta_sessao is not None and lista_alvo and not args.simulado:
            divergencias = conferir_coleta_por_sessao(pasta_sessao, sessoes)
            bloqueantes, avisos_conf = separar_divergencias_por_alvo(
                divergencias,
                [int(item["id"]) for item in lista_novas],
                [int(item["id"]) for item in lista_alvo],
            )
            if bloqueantes:
                detalhes = "; ".join(
                    f"sessao {item['sessao_id']} {item['recurso']}: {item['motivo']}"
                    for item in bloqueantes
                )
                raise SystemExit(
                    "Conferencia da coleta por sessao divergiu na sessao nova. "
                    f"Nada foi publicado. {detalhes}"
                )
            avisos_coleta.extend(avisos_conf)
    finally:
        coletar_lote.urllib.request.urlopen = original_urlopen

    alterou = config_alterada or any(coletor.gravou for coletor in coletores)
    print(f"Pedidos nesta execucao: {orcamento.pedidos}")
    if args.simulado or not alterou:
        if not alterou:
            print("Nada mudou. Tratados nao foram regravados.")
        return 0

    import classificar_temas

    resumo_temas: dict = {"novas": [], "consenso": [], "pendentes": [], "avisos": [], "tokens_total": 0}
    sem_chave_temas = classificar_temas.ler_chave() is None
    try:
        resumo_temas = classificar_temas.classificar_novas(cfg, classificar_temas.ler_chave())
    except (SystemExit, OSError, ValueError) as exc:
        print(f"Classificador de temas pulado: {exc}")
        resumo_temas = {"novas": [], "consenso": [], "pendentes": [], "avisos": [str(exc)[:160]], "tokens_total": 0}
    print(
        f"Temas: {len(resumo_temas.get('consenso') or [])} por consenso, "
        f"{len(resumo_temas.get('pendentes') or [])} pendentes, "
        f"{int(resumo_temas.get('tokens_total') or 0)} tokens."
    )
    linhas_temas = classificar_temas.linhas_changelog_temas(resumo_temas, sem_chave_temas)
    for aviso in resumo_temas.get("avisos") or []:
        linhas_temas.append(f"Aviso do classificador de temas: {aviso}.")

    contagens_antes = ler_json(RESUMO_INSUMOS).get("contagens") or {}
    hashes_antes = ler_hashes(anos)
    rodar(["coletor/derivar_insumos.py"])
    for gerador in GERADORES:
        rodar([gerador])
    rodar(["coletor/testes_sanidade.py"])
    rodar(["-m", "unittest", "discover", "-s", "tests"])
    rodar(["coletor/gerar_hash_integridade.py"])
    rodar(["scripts/verificar_regras.py"])

    contagens_depois = ler_json(RESUMO_INSUMOS).get("contagens") or {}
    hashes_depois = ler_hashes(anos)
    entrada = montar_entrada(
        hoje.isoformat(),
        fonte,
        orcamento.pedidos,
        lista_novas,
        linhas_contagem(contagens_antes, contagens_depois),
        linhas_hash(hashes_antes, hashes_depois),
        avisos_coleta,
        linhas_temas,
    )
    gravar_changelog(entrada)
    print("CHANGELOG atualizado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
