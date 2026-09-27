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
        dados = ler_json(caminho)
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
    primeiro = coletor.pedir(caminho, params, f"{prefixo}_p1.json")
    exigir_filtro(primeiro, sid, recurso)

    def baixar(pagina: int):
        params["page"] = pagina
        seguinte = coletor.pedir(caminho, params, f"{prefixo}_p{pagina}.json")
        exigir_filtro(seguinte, sid, recurso)
        return seguinte

    continuar_apos_primeira(primeiro, prefixo, baixar)
    return prefixo


def conferir_prefixo(pasta: Path, prefixo: str, sid: int, recurso: str) -> dict:
    linhas = []
    total = None
    numero = 1
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
            break
        dados = ler_json(caminho)
        if numero == 1:
            paginacao = dados.get("pagination") or {}
            if paginacao.get("total_entries") is not None:
                total = int(paginacao["total_entries"])
        for item in dados.get("results") or []:
            if isinstance(item, dict):
                linhas.append(item)
        paginacao = dados.get("pagination") or {}
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
    bate = total is not None and total == distintos and len(ids) == distintos
    motivo = None
    if not bate:
        if total is None:
            motivo = "sem total_entries"
        elif len(ids) != distintos:
            motivo = "id repetido"
        else:
            motivo = "total_entries diferente dos ids distintos"
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
    tmp.write_text(texto, encoding="utf-8")
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
