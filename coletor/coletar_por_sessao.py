"""Baixa presenca, ordem do dia e justificativa filtradas por sessao ordinaria.

Um pedido por vez. Pausa de PAUSA_SAPL_SEGUNDOS. Teto de 350 pedidos nesta tarefa.
Nao baixa registrovotacao nem votoparlamentar.
Nao apaga o lote anterior. Pagina ja salva com HTTP 200 no indice nao e repetida.
O bruto nao e editado.

Rodar:  python coletor/coletar_por_sessao.py
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from coletar_lote import (
    PAGE_SIZE,
    ColetorLote,
    continuar_apos_primeira,
)
from config_cidade import (
    PisoNaoDefinido,
    anos_recorte,
    carregar_config,
    exigir_piso,
    id_tipo_sessao_ordinaria,
    pisos_sanidade,
    remover_campos_pessoais,
)
from derivar_insumos import ano_de_data, ler_json

TETO_POR_SESSAO = 350
TOTAL_ALTO_DEMAIS = 200

RECURSOS = (
    ("/api/sessao/sessaoplenariapresenca/", "sessaoplenariapresenca"),
    ("/api/sessao/presencaordemdia/", "presencaordemdia"),
    ("/api/sessao/ordemdia/", "ordemdia"),
    ("/api/sessao/justificativaausencia/", "justificativaausencia"),
)

CAMINHO_MESA = "/api/sessao/integrantemesa/"
RECURSO_MESA = "integrantemesa"
CAMINHO_REGISTRO = "/api/sessao/registrovotacao/"
RECURSO_REGISTRO = "registrovotacao"
CAMINHO_VOTO = "/api/sessao/votoparlamentar/"
RECURSO_VOTO = "votoparlamentar"

RAIZ = Path(__file__).resolve().parent.parent
BRUTOS = RAIZ / "dados" / "brutos"


def pasta_lote_origem(brutos: Path, anos: list[int]) -> Path:
    """Lote mais recente que tenha a lista de sessoes de cada ano do recorte."""
    necessarios = [f"sessaoplenaria_ano{int(ano)}_p1.json" for ano in anos]
    candidatas = []
    for caminho in brutos.glob("lote_*"):
        if not caminho.is_dir():
            continue
        nome = caminho.name
        if "porsessao" in nome or nome.endswith("_autoria"):
            continue
        if nome.lower().endswith("_tramitacao") or "sondagem" in nome.lower():
            continue
        if all((caminho / nome_arquivo).is_file() for nome_arquivo in necessarios):
            candidatas.append(caminho)
    if not candidatas:
        raise SystemExit("Nao achei o lote com as sessoes plenarias. Nada foi baixado.")
    return sorted(candidatas, key=lambda item: item.name)[-1]


def sessoes_ordinarias(
    pasta_lote: Path, tipo_ordinaria: int, anos: list[int] | None = None
) -> list[dict]:
    por_id = {}
    if anos is None:
        caminhos = sorted(pasta_lote.glob("sessaoplenaria_ano*_p*.json"))
    else:
        caminhos = []
        for ano in anos:
            caminhos.extend(sorted(pasta_lote.glob(f"sessaoplenaria_ano{int(ano)}_p*.json")))
    for caminho in caminhos:
        try:
            dados = ler_json(caminho)
        except (OSError, ValueError, UnicodeDecodeError):
            print(f"AVISO: bruto ilegivel pulado em {caminho.name}. Vale o piso de sessoes.")
            continue
        if not isinstance(dados, dict):
            continue
        for item in dados.get("results") or []:
            if not isinstance(item, dict) or item.get("id") is None:
                continue
            if int(item.get("tipo") or 0) != int(tipo_ordinaria):
                continue
            por_id[int(item["id"])] = {
                "id": int(item["id"]),
                "numero": item.get("numero"),
                "data_inicio": item.get("data_inicio"),
            }
    return sorted(
        por_id.values(),
        key=lambda item: (item.get("data_inicio") or "", int(item.get("numero") or 0), item["id"]),
    )


def exigir_minimo_de_sessoes(sessoes: list[dict], cfg: dict) -> None:
    """O piso de cada ano do config e minimo. Sessao a mais nao interrompe a coleta."""
    anos = anos_recorte(cfg)
    sem_data = [int(item["id"]) for item in sessoes if ano_de_data(item.get("data_inicio")) is None]
    if sem_data:
        raise SystemExit(
            "Sessoes ordinarias sem data_inicio: "
            + ", ".join(str(item) for item in sem_data)
            + ". Nada foi baixado."
        )
    contagem = {int(ano): 0 for ano in anos}
    for sessao in sessoes:
        ano = ano_de_data(sessao.get("data_inicio"))
        if ano in contagem:
            contagem[ano] += 1
    falhas = []
    for ano in anos:
        try:
            piso = exigir_piso(
                "sessoes_ordinarias",
                pisos_sanidade(ano, cfg)["sessoes_ordinarias"],
                ano,
            )
        except PisoNaoDefinido as exc:
            raise SystemExit(str(exc)) from exc
        achadas = contagem[ano]
        if achadas < int(piso):
            falhas.append(f"{ano}: piso {int(piso)}, achei {achadas}")
    if falhas:
        raise SystemExit(
            "Sessoes ordinarias abaixo do piso de cada ano do config. Nada foi baixado. "
            + " ".join(falhas)
        )


def exigir_filtro(dados: dict, sid: int, recurso: str) -> None:
    if not isinstance(dados, dict):
        raise SystemExit(f"sessao {sid} {recurso}: resposta sem objeto JSON. Parei.")
    paginacao = dados.get("pagination") or {}
    total = paginacao.get("total_entries")
    if total is not None and int(total) > TOTAL_ALTO_DEMAIS:
        raise SystemExit(
            f"sessao {sid} {recurso}: total_entries {total} alto demais para uma sessao. "
            "O filtro sessao_plenaria parece ignorado. Parei sem apagar o que ja baixou."
        )
    for item in dados.get("results") or []:
        if not isinstance(item, dict):
            continue
        vindo = item.get("sessao_plenaria")
        if vindo is None or int(vindo) != int(sid):
            raise SystemExit(
                f"sessao {sid} {recurso}: veio sessao_plenaria {vindo}. "
                "O filtro foi ignorado. Parei sem apagar o que ja baixou."
            )


def pedir_recurso(coletor: ColetorLote, sid: int, caminho: str, recurso: str) -> str:
    prefixo = f"sessao_{sid}_{recurso}"
    params = {"sessao_plenaria": sid, "page_size": PAGE_SIZE, "page": 1}
    primeiro = coletor.pedir(caminho, params, f"{prefixo}_p1.json", refrescar=True)
    exigir_filtro(primeiro, sid, recurso)

    def baixar(pagina: int):
        params["page"] = pagina
        seguinte = coletor.pedir(caminho, params, f"{prefixo}_p{pagina}.json")
        exigir_filtro(seguinte, sid, recurso)
        return seguinte

    continuar_apos_primeira(primeiro, prefixo, baixar)
    return prefixo


def pedir_mesa_por_sessao(coletor: ColetorLote, sid: int) -> str:
    """Mesa da sessao. O filtro sessao_plenaria funciona aqui."""
    return pedir_recurso(coletor, int(sid), CAMINHO_MESA, RECURSO_MESA)


def ler_ids_ordem_da_sessao(pasta: Path, sid: int) -> list[int]:
    """Ids dos itens da ordem do dia ja coletados para a sessao."""
    ids: list[int] = []
    numero = 1
    while True:
        caminho = pasta / f"sessao_{int(sid)}_ordemdia_p{numero}.json"
        if not caminho.is_file():
            break
        try:
            dados = ler_json(caminho)
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            raise SystemExit(
                f"sessao {int(sid)} ordemdia pagina {numero} ilegivel ({exc}). Parei."
            ) from exc
        for item in dados.get("results") or []:
            if isinstance(item, dict) and item.get("id") is not None:
                ids.append(int(item["id"]))
        paginacao = dados.get("pagination") or {}
        total_paginas = paginacao.get("total_pages")
        tem_proxima = bool(
            paginacao.get("next_page") or (paginacao.get("links") or {}).get("next")
        )
        if total_paginas is not None and numero >= int(total_paginas):
            break
        if not tem_proxima:
            break
        numero += 1
    vistos = set()
    saida = []
    for identificador in ids:
        if identificador not in vistos:
            vistos.add(identificador)
            saida.append(identificador)
    return sorted(saida)


def _gravar_consolidado(pasta: Path, prefixo: str, linhas: list) -> None:
    """Consolidado por sessao no formato de pagina unica para o derivador.

    Os campos pessoais do SAPL sao removidos antes de gravar, pela mesma
    funcao que o coletor em lote usa.
    """
    cfg = carregar_config()
    unicas = []
    vistos = set()
    sem_id = []
    for item in linhas:
        if isinstance(item, dict) and item.get("id") is not None:
            identificador = int(item["id"])
            if identificador in vistos:
                continue
            vistos.add(identificador)
            unicas.append(item)
        else:
            sem_id.append(item)
    todas = unicas + sem_id
    dados = {"pagination": {}, "results": todas}
    limpo = remover_campos_pessoais(dados, cfg)
    dados["pagination"] = {
        "total_entries": len(limpo["results"]),
        "total_pages": 1,
        "page": 1,
        "links": {"next": None, "previous": None},
        "next_page": None,
    }
    texto = json.dumps(limpo, ensure_ascii=False, indent=2) + "\n"
    caminho = pasta / f"{prefixo}_p1.json"
    tmp = caminho.with_suffix(".json.tmp")
    tmp.write_bytes(texto.encode("utf-8"))
    tmp.replace(caminho)


def _ler_paginas_por_prefixo(pasta: Path, prefixo: str) -> list[dict]:
    """Le todas as paginas salvas de um prefixo por ordem ou por votacao."""
    linhas: list[dict] = []
    numero = 1
    while True:
        caminho = pasta / f"{prefixo}_p{numero}.json"
        if not caminho.is_file():
            break
        try:
            dados = ler_json(caminho)
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            raise SystemExit(
                f"{prefixo}: pagina {numero} ilegivel ({exc}). Parei."
            ) from exc
        if not isinstance(dados, dict):
            raise SystemExit(f"{prefixo}: pagina {numero} sem objeto JSON.")
        linhas.extend(list(dados.get("results") or []))
        paginacao = dados.get("pagination") or {}
        total_paginas = paginacao.get("total_pages")
        tem_proxima = bool(
            paginacao.get("next_page") or (paginacao.get("links") or {}).get("next")
        )
        if total_paginas is not None and numero >= int(total_paginas):
            break
        if not tem_proxima:
            break
        numero += 1
    return linhas


def pedir_registros_da_sessao(
    coletor: ColetorLote, sid: int, ids_ordem: list[int]
) -> list[dict]:
    """Registros de votacao pelos itens da ordem. O filtro sessao_plenaria e ignorado pelo SAPL, por isso o caminho usa ordem=<id>."""
    sid = int(sid)
    registros: list[dict] = []
    for oid in sorted({int(item) for item in ids_ordem}):
        params = {"ordem": int(oid), "page_size": PAGE_SIZE, "page": 1}
        prefixo_ordem = f"sessao_{sid}_registrovotacao_ordem_{int(oid)}"
        primeiro = coletor.pedir(CAMINHO_REGISTRO, dict(params), f"{prefixo_ordem}_p1.json", refrescar=True)
        if not isinstance(primeiro, dict):
            raise SystemExit(f"sessao {sid} registrovotacao ordem {oid}: sem objeto JSON.")

        def baixar(pagina: int, _oid: int = int(oid), _params: dict = params):
            copia = dict(_params)
            copia["page"] = pagina
            return coletor.pedir(
                CAMINHO_REGISTRO,
                copia,
                f"sessao_{sid}_registrovotacao_ordem_{_oid}_p{pagina}.json",
            )

        continuar_apos_primeira(primeiro, prefixo_ordem, baixar)
        registros.extend(_ler_paginas_por_prefixo(coletor.pasta, prefixo_ordem))
    _gravar_consolidado(coletor.pasta, f"sessao_{sid}_{RECURSO_REGISTRO}", registros)
    return registros


def pedir_votos_da_sessao(
    coletor: ColetorLote, sid: int, ids_registro: list[int]
) -> list[dict]:
    """Votos individuais por registro. O caminho usa votacao=<id>."""
    sid = int(sid)
    votos: list[dict] = []
    for vid in sorted({int(item) for item in ids_registro}):
        params = {"votacao": int(vid), "page_size": PAGE_SIZE, "page": 1}
        prefixo_voto = f"sessao_{sid}_votoparlamentar_votacao_{int(vid)}"
        primeiro = coletor.pedir(CAMINHO_VOTO, dict(params), f"{prefixo_voto}_p1.json", refrescar=True)
        if not isinstance(primeiro, dict):
            raise SystemExit(f"sessao {sid} votoparlamentar votacao {vid}: sem objeto JSON.")

        def baixar(pagina: int, _vid: int = int(vid), _params: dict = params):
            copia = dict(_params)
            copia["page"] = pagina
            return coletor.pedir(
                CAMINHO_VOTO,
                copia,
                f"sessao_{sid}_votoparlamentar_votacao_{_vid}_p{pagina}.json",
            )

        continuar_apos_primeira(primeiro, prefixo_voto, baixar)
        votos.extend(_ler_paginas_por_prefixo(coletor.pasta, prefixo_voto))
    _gravar_consolidado(coletor.pasta, f"sessao_{sid}_{RECURSO_VOTO}", votos)
    return votos


def gravar_aviso_sessao_recusada(pasta: Path, sid: int, motivo: str, detalhe: dict) -> Path:
    """Aviso estruturado quando a sessao e recusada por vazio suspeito.

    O arquivo nao entra na derivacao. Serve para o log e para a issue.
    Nada e publicado a partir de uma sessao recusada.
    """
    caminho = pasta / f"sessao_{int(sid)}_recusada.json"
    dado = {
        "sessao_id": int(sid),
        "motivo": motivo,
        "detalhe": detalhe,
    }
    texto = json.dumps(dado, ensure_ascii=False, indent=2) + "\n"
    tmp = caminho.with_suffix(".json.tmp")
    tmp.write_bytes(texto.encode("utf-8"))
    tmp.replace(caminho)
    return caminho


def recusar_sessao_vazia(
    pasta: Path,
    sid: int,
    motivo: str,
    detalhe: dict,
    restaurar: dict[str, bytes | None] | None = None,
) -> None:
    """Recusa a sessao com erro explicito. Nada e publicado.

    O argumento restaurar devolve os consolidados ao estado anterior
    a coleta, para uma revisao de lancamento atrasado nao apagar dado
    bom quando o SAPL responde vazio. Chave e o nome do arquivo,
    valor e o conteudo previo ou None quando nao existia.
    """
    for nome, conteudo in (restaurar or {}).items():
        caminho = pasta / nome
        if conteudo is None:
            if caminho.is_file():
                caminho.unlink()
        else:
            caminho.write_bytes(conteudo)
    aviso = gravar_aviso_sessao_recusada(pasta, sid, motivo, detalhe)
    print(f"sessao {int(sid)} recusada: {motivo} Aviso em {aviso.name}. Nada foi publicado.")
    raise SystemExit(
        f"sessao {int(sid)} recusada: {motivo} "
        f"Aviso em dados/brutos/{pasta.name}/{aviso.name}. Nada foi publicado."
    )


RECURSOS_PRESENCA_E_ORDEM = (
    "sessaoplenariapresenca",
    "presencaordemdia",
    "ordemdia",
)


def total_entries_da_pagina(pasta: Path, prefixo: str) -> int | None:
    """total_entries da pagina 1 salva, ou None quando ausente ou ilegivel."""
    caminho = pasta / f"{prefixo}_p1.json"
    if not caminho.is_file():
        return None
    try:
        dados = ler_json(caminho)
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    if not isinstance(dados, dict):
        return None
    total = (dados.get("pagination") or {}).get("total_entries")
    if isinstance(total, bool) or not isinstance(total, int):
        return None
    return int(total)


def coletar_sessao_completa(coletor: ColetorLote, sid: int) -> dict:
    """Coleta por sessao dos 7 pacotes grandes: presencas, ordem, justificativa, mesa, registros e votos.

    Recusa a sessao quando a ordem tem itens e vieram zero registros,
    ou quando ha registros e zero votos. Sessao nova com presenca ou
    ordem do dia com total_entries 0 tambem e recusada, pois ausencia
    ainda nao lancada nao pode virar falta sem justificativa. Vazio
    nesse ponto indica filtro mudado no SAPL ou coleta quebrada, por
    isso nada e publicado. A recusa restaura os arquivos previos e
    grava um aviso sessao_<id>_recusada.json para o log e para a issue.
    """
    sid = int(sid)
    pasta = coletor.pasta
    aviso_antigo = pasta / f"sessao_{sid}_recusada.json"
    if aviso_antigo.is_file():
        aviso_antigo.unlink()
    previos = {}
    for recurso in (RECURSO_REGISTRO, RECURSO_VOTO):
        caminho = pasta / f"sessao_{sid}_{recurso}_p1.json"
        previos[caminho.name] = caminho.read_bytes() if caminho.is_file() else None
    for _caminho, recurso in list(RECURSOS) + [(CAMINHO_MESA, RECURSO_MESA)]:
        caminho = pasta / f"sessao_{sid}_{recurso}_p1.json"
        if caminho.name not in previos:
            previos[caminho.name] = caminho.read_bytes() if caminho.is_file() else None
    e_nova = all(
        previos.get(f"sessao_{sid}_{recurso}_p1.json") is None
        for _caminho, recurso in RECURSOS
    )
    for caminho, recurso in RECURSOS:
        pedir_recurso(coletor, sid, caminho, recurso)
    pedir_mesa_por_sessao(coletor, sid)
    if e_nova:
        for recurso in RECURSOS_PRESENCA_E_ORDEM:
            total = total_entries_da_pagina(pasta, f"sessao_{sid}_{recurso}")
            if total == 0:
                recusar_sessao_vazia(
                    coletor.pasta,
                    sid,
                    (
                        f"sessao nova com {recurso} zerado (total_entries 0). "
                        "A presenca ou a ordem ainda nao foi lancada no SAPL. "
                        "Ausencia nao vira falta."
                    ),
                    {"recurso": recurso, "total_entries": 0},
                    restaurar=previos,
                )
    ids_ordem = ler_ids_ordem_da_sessao(coletor.pasta, sid)
    registros = pedir_registros_da_sessao(coletor, sid, ids_ordem)
    if ids_ordem and not registros:
        recusar_sessao_vazia(
            coletor.pasta,
            sid,
            (
                f"ordem do dia com {len(ids_ordem)} itens e zero registros de votacao. "
                "O filtro ordem pode ter mudado no SAPL."
            ),
            {"n_ordem": len(ids_ordem), "n_registros": 0},
            restaurar=previos,
        )
    ids_registro = [
        int(item["id"]) for item in registros if isinstance(item, dict) and item.get("id") is not None
    ]
    votos = pedir_votos_da_sessao(coletor, sid, ids_registro)
    if ids_registro and not votos:
        recusar_sessao_vazia(
            coletor.pasta,
            sid,
            (
                f"{len(ids_registro)} registros de votacao e zero votos parlamentares. "
                "O filtro votacao pode ter mudado no SAPL."
            ),
            {"n_registros": len(ids_registro), "n_votos": 0},
            restaurar=previos,
        )
    return {
        "sessao_id": sid,
        "n_ordem": len(ids_ordem),
        "n_registros": len(registros),
        "n_votos": len(votos),
    }


def conferir_prefixo(pasta: Path, prefixo: str, sid: int, recurso: str) -> dict:
    linhas = []
    total = None
    numero = 1
    paginas_lidas = 0
    ultima_paginacao: dict = {}
    parou_por_arquivo_ausente = False
    while True:
        caminho = pasta / f"{prefixo}_p{numero}.json"
        if not caminho.exists():
            if numero == 1:
                return {
                    "sessao_id": sid,
                    "recurso": recurso,
                    "bate": False,
                    "motivo": "arquivo ausente",
                    "total_entries": None,
                    "linhas": 0,
                    "ids_distintos": 0,
                }
            parou_por_arquivo_ausente = True
            break
        try:
            dados = ler_json(caminho)
        except (OSError, ValueError, UnicodeDecodeError):
            return {
                "sessao_id": sid,
                "recurso": recurso,
                "bate": False,
                "motivo": "arquivo ilegivel",
                "total_entries": None,
                "linhas": 0,
                "ids_distintos": 0,
            }
        paginas_lidas += 1
        ultima_paginacao = dados.get("pagination") or {}
        if numero == 1:
            if ultima_paginacao.get("total_entries") is not None:
                total = int(ultima_paginacao["total_entries"])
        for item in dados.get("results") or []:
            if isinstance(item, dict):
                linhas.append(item)
        paginacao = ultima_paginacao
        total_paginas = paginacao.get("total_pages")
        if total_paginas is not None and numero >= int(total_paginas):
            break
        if not (paginacao.get("next_page") or (paginacao.get("links") or {}).get("next")):
            break
        numero += 1
    ids = []
    for item in linhas:
        if item.get("id") is not None:
            ids.append(int(item["id"]))
    distintos = len(set(ids))
    sem_repeticao = len(ids) == distintos
    paginacao_pendente = False
    if parou_por_arquivo_ausente and (
        ultima_paginacao.get("next_page")
        or (ultima_paginacao.get("links") or {}).get("next")
    ):
        paginacao_pendente = True
    total_paginas_anunciado = ultima_paginacao.get("total_pages")
    if (
        total_paginas_anunciado is not None
        and paginas_lidas < int(total_paginas_anunciado)
    ):
        paginacao_pendente = True
    links_proximo = bool(
        ultima_paginacao.get("next_page")
        or (ultima_paginacao.get("links") or {}).get("next")
    )
    prova_fim = (
        not links_proximo
        and total_paginas_anunciado is not None
        and paginas_lidas >= int(total_paginas_anunciado)
    )
    causas = []
    if total is None:
        causas.append("sem total_entries")
        if not prova_fim:
            causas.append("sem prova de fim de paginacao")
    if not sem_repeticao:
        causas.append("id repetido")
    if paginacao_pendente:
        causas.append("paginacao pendente")
    if total is not None and total != distintos:
        causas.append("total_entries distinto de ids distintos")
    if total is not None:
        bate = total == distintos and sem_repeticao
        motivo = None
    elif prova_fim and sem_repeticao:
        bate = True
        motivo = None
    else:
        bate = False
        motivo = None
    if not bate:
        motivo = "; ".join(causas) if causas else "sem total_entries"
    return {
        "sessao_id": sid,
        "recurso": recurso,
        "bate": bate,
        "motivo": motivo,
        "total_entries": total,
        "linhas": len(ids),
        "ids_distintos": distintos,
    }


def gravar_conferencia(pasta: Path, sessoes: list[dict], divergencias: list[dict]) -> None:
    por_recurso = {}
    for _caminho, recurso in RECURSOS:
        itens = [item for item in divergencias if item["recurso"] == recurso]
        por_recurso[recurso] = {
            "sessoes_conferidas": len(sessoes),
            "sessoes_com_divergencia": len(itens),
        }
    dado = {
        "sessoes_ordinarias": len(sessoes),
        "ids_sessoes": [item["id"] for item in sessoes],
        "recursos": [nome for _caminho, nome in RECURSOS],
        "por_recurso": por_recurso,
        "divergencias": divergencias,
    }
    texto = json.dumps(dado, ensure_ascii=False, indent=2) + "\n"
    caminho = pasta / "conferencia.json"
    tmp = caminho.with_suffix(".json.tmp")
    tmp.write_bytes(texto.encode("utf-8"))
    tmp.replace(caminho)


def main() -> None:
    cfg = carregar_config()
    tipo = id_tipo_sessao_ordinaria(cfg)
    anos = anos_recorte(cfg)
    origem = pasta_lote_origem(BRUTOS, anos)
    sessoes = sessoes_ordinarias(origem, tipo, anos)
    exigir_minimo_de_sessoes(sessoes, cfg)
    pasta = BRUTOS / f"lote_{datetime.now().strftime('%Y%m%d')}_porsessao"
    coletor = ColetorLote(cfg, pasta, teto=TETO_POR_SESSAO)
    print(f"Coleta por sessao em dados/brutos/{pasta.name}")
    print(f"Origem das sessoes: dados/brutos/{origem.name}. {len(sessoes)} ordinarias.")
    for sessao in sessoes:
        sid = sessao["id"]
        print(f"sessao {sid} numero {sessao.get('numero')} {sessao.get('data_inicio')}")
        for caminho, recurso in RECURSOS:
            pedir_recurso(coletor, sid, caminho, recurso)
    divergencias = []
    for sessao in sessoes:
        sid = sessao["id"]
        for _caminho, recurso in RECURSOS:
            conf = conferir_prefixo(pasta, f"sessao_{sid}_{recurso}", sid, recurso)
            if not conf["bate"]:
                divergencias.append(conf)
    gravar_conferencia(pasta, sessoes, divergencias)
    print(f"Fim. Pedidos no indice: {coletor.pedidos}")
    print(f"Sessoes com divergencia: {len(divergencias)}")
    if divergencias:
        for item in divergencias:
            print(
                f"  sessao {item['sessao_id']} {item['recurso']}: "
                f"total {item['total_entries']} distintos {item['ids_distintos']} ({item['motivo']})"
            )


if __name__ == "__main__":
    main()
