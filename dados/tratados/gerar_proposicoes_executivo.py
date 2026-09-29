#!/usr/bin/env python3
"""Consolida proposicoes e Executivo com tramitacao e votacao (C9).

Le os brutos ja coletados e os tratados existentes. Nao pede nada ao SAPL.
Nao inventa dado: ausencia de votacao ou de tramitacao recebe rotulo
explicito. Ausencia nao e voto. Campo de rede nunca vai para dado tratado.

Entradas:
    dados/brutos/lote_20260926/materialegislativa_ano*_p*.json (ficha)
    dados/brutos/lote_20260926/tipomaterialegislativa_p1.json (siglas)
    dados/brutos/lote_20260929_tramitacao/ (historico, status e unidades)
    dados/tratados/temas_materias.json (tema por materia)
    dados/tratados/autoria_materias.json (autores vereadores)
    dados/tratados/vereadores.json (nomes dos vereadores)
    dados/tratados/atuacao_vereadores_<ano>.json (votacoes ordinarias)

Saidas (chamado por gerar_dados_tela.py):
    dados/tratados/proposicoes_<ano>.json e proposicoes_legislatura.json
    dados/tratados/executivo_<ano>.json e executivo_legislatura.json
    complemento da atuacao_vereadores_legislatura.json por vereador:
    lista de REQ, MOC e IND de autoria dele e votos em PLEX.
    Os arquivos atuacao_vereadores_<ano>.json nao sao tocados.

Uso:
    python dados/tratados/gerar_proposicoes_executivo.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

DIR_SCRIPT = Path(__file__).resolve().parent
DIR_RAIZ = DIR_SCRIPT.parent.parent
DIR_BRUTOS = DIR_SCRIPT.parent / "brutos"
if str(DIR_RAIZ / "coletor") not in sys.path:
    sys.path.insert(0, str(DIR_RAIZ / "coletor"))

from config_cidade import (  # noqa: E402
    anos_recorte,
    carregar_config,
    endereco_sapl,
    link_materia,
    link_sessao,
    piso_status_decodificados,
    tipos_executivo,
    tipos_proposicoes,
)

SCRIPT_REL = "dados/tratados/gerar_proposicoes_executivo.py"
ROTULO_SEM_VOTACAO = "sem votacao registrada no SAPL"
ROTULO_SEM_TRAMITACAO = "sem tramitacao registrada no SAPL"
ROTULO_VETADA_SEM_ESTRUTURA = "sem indicacao estruturada no SAPL, ver ementa"


def rel(caminho: Path) -> str:
    try:
        return caminho.resolve().relative_to(DIR_RAIZ.resolve()).as_posix()
    except ValueError:
        return caminho.name


def carregar_json(caminho: Path):
    return json.loads(caminho.read_text(encoding="utf-8"))


def escrever_lf(caminho: Path, dados) -> None:
    texto = json.dumps(dados, ensure_ascii=False, indent=2) + "\n"
    if "\r" in texto:
        raise SystemExit(f"{rel(caminho)} ficaria com fim de linha CR.")
    caminho.write_bytes(texto.replace("\r\n", "\n").encode("utf-8"))


def recusar_ip(obj, caminho: str = "") -> None:
    if isinstance(obj, dict):
        if "ip" in obj:
            raise SystemExit(f"Campo ip em dado tratado: {caminho or 'raiz'}")
        for chave, valor in obj.items():
            recusar_ip(valor, f"{caminho}.{chave}")
    elif isinstance(obj, list):
        for indice, valor in enumerate(obj):
            recusar_ip(valor, f"{caminho}[{indice}]")


def pasta_tramitacao() -> Path:
    candidatas = sorted(
        caminho
        for caminho in DIR_BRUTOS.glob("lote_*_tramitacao")
        if caminho.is_dir() and (caminho / "indice.json").exists()
    )
    if not candidatas:
        raise SystemExit("Nenhuma pasta de tramitacao em dados/brutos. Nada para consolidar.")
    return candidatas[-1]


def carregar_tipos_materia() -> dict[int, dict]:
    """Id do tipo para sigla e descricao, lido do bruto, sem sigla fixa."""
    for caminho in sorted(DIR_BRUTOS.glob("lote_*/tipomaterialegislativa_p*.json")):
        dados = carregar_json(caminho)
        saida = {}
        for item in dados.get("results") or []:
            saida[int(item["id"])] = {
                "sigla": str(item.get("sigla") or ""),
                "descricao": str(item.get("descricao") or ""),
            }
        if saida:
            return saida
    raise SystemExit("Tabela tipomaterialegislativa ausente nos brutos.")


def carregar_fichas() -> dict[int, dict]:
    """Ficha da materia por id, a partir dos brutos de materialegislativa."""
    fichas: dict[int, dict] = {}
    for caminho in sorted(DIR_BRUTOS.glob("lote_*/materialegislativa_ano*_p*.json")):
        dados = carregar_json(caminho)
        for item in dados.get("results") or []:
            mid = int(item["id"])
            fichas[mid] = {
                "id": mid,
                "numero": item.get("numero"),
                "ano": item.get("ano"),
                "tipo_id": int(item["tipo"]) if item.get("tipo") is not None else None,
                "ementa": item.get("ementa") or "",
                "em_tramitacao": item.get("em_tramitacao"),
                "resultado_ficha_sapl": item.get("resultado") or "",
                "data_apresentacao": item.get("data_apresentacao"),
            }
    if not fichas:
        raise SystemExit("Nenhuma ficha de materialegislativa nos brutos.")
    return fichas


def carregar_temas() -> dict[int, str]:
    dados = carregar_json(DIR_SCRIPT / "temas_materias.json")
    return {int(m["id"]): m.get("tema") for m in dados.get("materias", [])}


def carregar_autoria() -> dict[int, list[dict]]:
    dados = carregar_json(DIR_SCRIPT / "autoria_materias.json")
    indice: dict[int, list[dict]] = {}
    for materia in dados.get("materias") or []:
        indice[int(materia["materia_id"])] = materia.get("autorias") or []
    return indice


def carregar_vereadores() -> dict[int, dict]:
    dados = carregar_json(DIR_SCRIPT / "vereadores.json")
    return {int(v["id_sapl"]): v for v in dados.get("vereadores") or []}


def carregar_status_unidades(pasta: Path) -> tuple[dict[int, dict], dict[int, str]]:
    status: dict[int, dict] = {}
    for caminho in sorted(pasta.glob("statustramitacao_p*.json")):
        dados = carregar_json(caminho)
        for item in dados.get("results") or []:
            status[int(item["id"])] = {
                "sigla": str(item.get("sigla") or ""),
                "descricao": str(item.get("descricao") or ""),
                "indicador": str(item.get("indicador") or ""),
            }
    unidades: dict[int, str] = {}
    for caminho in sorted(pasta.glob("unidadetramitacao_p*.json")):
        dados = carregar_json(caminho)
        for item in dados.get("results") or []:
            unidades[int(item["id"])] = str(item.get("__str__") or "")
    return status, unidades


def carregar_historico(pasta: Path) -> dict[int, list[dict]]:
    """Historico por materia, so com campos seguros (sem rede, sem usuario)."""
    historico: dict[int, list[dict]] = {}
    for caminho in sorted(pasta.glob("tramitacao_materia*_p*.json")):
        if "_t" in caminho.name and "_p" in caminho.name and "_t" in caminho.name.split("_p")[-1]:
            continue
        dados = carregar_json(caminho)
        for item in dados.get("results") or []:
            mid = int(item["materia"])
            historico.setdefault(mid, []).append(
                {
                    "id": int(item["id"]),
                    "data_tramitacao": item.get("data_tramitacao"),
                    "data_encaminhamento": item.get("data_encaminhamento"),
                    "data_fim_prazo": item.get("data_fim_prazo"),
                    "status_id": int(item["status"]) if item.get("status") is not None else None,
                    "unidade_origem_id": (
                        int(item["unidade_tramitacao_local"])
                        if item.get("unidade_tramitacao_local") is not None
                        else None
                    ),
                    "unidade_destino_id": (
                        int(item["unidade_tramitacao_destino"])
                        if item.get("unidade_tramitacao_destino") is not None
                        else None
                    ),
                    "texto": item.get("texto") or "",
                    "urgente": bool(item.get("urgente")),
                    "turno": item.get("turno") or "",
                    "resumo_sapl": item.get("__str__") or "",
                }
            )
    return historico


def escolher_ultima(itens: list[dict]) -> dict | None:
    """Ultima situacao: maior data_tramitacao, desempate pelo maior id."""
    if not itens:
        return None

    def chave(item: dict):
        return (item.get("data_tramitacao") or "", int(item.get("id") or 0))

    return sorted(itens, key=chave)[-1]


def decodificar_status(status_id: int | None, tabela: dict[int, dict]) -> dict:
    if status_id is None:
        return {
            "id": None,
            "sigla": None,
            "descricao": None,
            "situacao": "nao informado no SAPL",
        }
    info = tabela.get(int(status_id))
    if info is None:
        return {
            "id": int(status_id),
            "sigla": None,
            "descricao": None,
            "situacao": "nao informado no SAPL",
        }
    indicador = (info.get("indicador") or "").strip().upper()
    if indicador == "F":
        situacao = "fim"
    elif indicador == "R":
        situacao = "em curso"
    else:
        situacao = "nao informado no SAPL"
    return {
        "id": int(status_id),
        "sigla": info.get("sigla") or None,
        "descricao": info.get("descricao") or None,
        "situacao": situacao,
    }


def montar_ultima_tramitacao(
    materia_id: int, historico: dict[int, list[dict]], status: dict[int, dict], unidades: dict[int, str]
) -> tuple[dict | None, str | None]:
    itens = historico.get(int(materia_id)) or []
    ultima = escolher_ultima(itens)
    if ultima is None:
        return None, ROTULO_SEM_TRAMITACAO
    decodificado = decodificar_status(ultima.get("status_id"), status)
    origem_id = ultima.get("unidade_origem_id")
    destino_id = ultima.get("unidade_destino_id")
    return {
        "data": ultima.get("data_tramitacao"),
        "status_id": decodificado["id"],
        "status_sigla": decodificado["sigla"],
        "status_descricao": decodificado["descricao"],
        "situacao": decodificado["situacao"],
        "unidade_origem_id": origem_id,
        "unidade_origem": unidades.get(int(origem_id)) if origem_id is not None else None,
        "unidade_destino_id": destino_id,
        "unidade_destino": unidades.get(int(destino_id)) if destino_id is not None else None,
        "texto": ultima.get("texto") or "",
        "urgente": bool(ultima.get("urgente")),
        "resumo_sapl": ultima.get("resumo_sapl") or "",
    }, None


def carregar_votacoes(anos: list[int]) -> dict[int, list[dict]]:
    """Votacoes ordinarias por materia, a partir da atuacao por ano."""
    por_materia: dict[int, list[dict]] = {}
    for ano in anos:
        caminho = DIR_SCRIPT / f"atuacao_vereadores_{ano}.json"
        dados = carregar_json(caminho)
        for votacao in dados.get("votacoes") or []:
            mid = votacao.get("materia_id")
            if mid is None:
                continue
            por_materia.setdefault(int(mid), []).append(votacao)
    return por_materia


def escolher_votacao(registros: list[dict]) -> dict | None:
    if not registros:
        return None

    def chave(item: dict):
        return (
            item.get("data_sessao") or "",
            item.get("data_hora") or "",
            int(item.get("id") or 0),
        )

    return sorted(registros, key=chave)[-1]


def montar_votacao(materia_id: int, votacoes: dict[int, list[dict]]) -> tuple[dict | None, str | None]:
    registros = votacoes.get(int(materia_id)) or []
    escolhida = escolher_votacao(registros)
    if escolhida is None:
        return None, ROTULO_SEM_VOTACAO
    totais = escolhida.get("totais_oficiais") or {}
    return {
        "data_sessao": escolhida.get("data_sessao"),
        "sessao_id": escolhida.get("sessao_id"),
        "registro_votacao_id": escolhida.get("id"),
        "resultado_texto_sapl": escolhida.get("resultado_texto_sapl"),
        "situacao_oficial_sapl": escolhida.get("situacao_oficial_sapl"),
        "frase_resultado_sapl": escolhida.get("frase_resultado_sapl"),
        "totais_oficiais": {
            "numero_votos_sim": totais.get("numero_votos_sim"),
            "numero_votos_nao": totais.get("numero_votos_nao"),
            "numero_abstencoes": totais.get("numero_abstencoes"),
        },
        "voto_individual_registrado": bool(escolhida.get("voto_individual_registrado")),
        "link_sessao": escolhida.get("link_sessao"),
        "link_materia": escolhida.get("link_materia"),
    }, None


def autores_vereadores(
    materia_id: int, autoria: dict[int, list[dict]], vereadores: dict[int, dict]
) -> list[dict]:
    saida = []
    for item in autoria.get(int(materia_id)) or []:
        pid = item.get("parlamentar_id_sapl")
        if pid is None:
            continue
        pessoa = vereadores.get(int(pid))
        saida.append(
            {
                "parlamentar_id_sapl": int(pid),
                "nome_parlamentar": (pessoa or {}).get("nome_parlamentar") or item.get("nome_no_sapl") or "",
                "nome_no_sapl": item.get("nome_no_sapl") or "",
                "primeiro_autor": item.get("primeiro_autor"),
            }
        )
    return saida


def montar_item_base(
    materia_id: int,
    sigla: str,
    fichas: dict[int, dict],
    tipos: dict[int, dict],
    temas: dict[int, str],
    autoria: dict[int, list[dict]],
    vereadores: dict[int, dict],
    historico: dict[int, list[dict]],
    status: dict[int, dict],
    unidades: dict[int, str],
    votacoes: dict[int, list[dict]],
    cfg: dict,
) -> dict:
    ficha = fichas.get(int(materia_id)) or {}
    numero = ficha.get("numero")
    ano = ficha.get("ano")
    rotulo_tipo = f"{sigla} {numero}/{ano}"
    ultima, rotulo_tram = montar_ultima_tramitacao(int(materia_id), historico, status, unidades)
    votacao, rotulo_vot = montar_votacao(int(materia_id), votacoes)
    item = {
        "id": int(materia_id),
        "tipo_sigla": sigla,
        "tipo": rotulo_tipo,
        "numero": str(numero) if numero is not None else None,
        "ano": str(ano) if ano is not None else None,
        "ementa": ficha.get("ementa") or "",
        "tema": temas.get(int(materia_id)),
        "autores": autores_vereadores(int(materia_id), autoria, vereadores),
        "em_tramitacao": ficha.get("em_tramitacao"),
        "ultima_tramitacao": ultima,
        "ultima_tramitacao_rotulo": rotulo_tram,
        "votacao": votacao,
        "votacao_rotulo": rotulo_vot,
        "link_sapl": link_materia(int(materia_id), cfg),
    }
    return item


def dividir_periodos(lista: list[dict], sessoes: list[dict]) -> tuple[list, list, list]:
    """Sessao, mes e todo, com a mesma regra de datas de gerar_dados_tela.

    Itens sem votacao ficam so no todo. Nada e estimado.
    """
    if not lista:
        return [], [], []
    datas = sorted({s["data"] for s in sessoes if s.get("data")})
    ultima_data = datas[-1] if datas else None
    sessao_ids_ultima = {s["id"] for s in sessoes if s.get("data") == ultima_data}
    sessao = [
        m
        for m in lista
        if (m.get("votacao") or {}).get("sessao_id") in sessao_ids_ultima
    ]
    if ultima_data:
        y, mo, _ = map(int, ultima_data.split("-"))
        mes_ant = mo - 1
        ano_ant = y
        if mes_ant < 1:
            mes_ant = 12
            ano_ant -= 1
    else:
        ano_ant, mes_ant = 0, 0

    def no_mes(m: dict) -> bool:
        data = (m.get("votacao") or {}).get("data_sessao")
        if not data:
            return False
        return int(data.split("-")[0]) == ano_ant and int(data.split("-")[1]) == mes_ant

    mes = [m for m in lista if no_mes(m)]
    return sessao, mes, list(lista)


def sessoes_do_ano(ano: int) -> list[dict]:
    caminho = DIR_SCRIPT / f"atuacao_vereadores_{ano}.json"
    dados = carregar_json(caminho)
    return dados.get("sessoes") or []


def gerar_arquivos(cfg: dict) -> dict:
    anos = anos_recorte(cfg)
    tipos_materia = carregar_tipos_materia()
    fichas = carregar_fichas()
    temas = carregar_temas()
    autoria = carregar_autoria()
    vereadores = carregar_vereadores()
    pasta = pasta_tramitacao()
    status, unidades = carregar_status_unidades(pasta)
    decodificados = len(status)
    piso = piso_status_decodificados(cfg)
    if decodificados < piso:
        raise SystemExit(
            f"Status decodificados: {decodificados}. O piso minimo e {piso}."
        )
    historico = carregar_historico(pasta)
    votacoes = carregar_votacoes(anos)
    siglas_prop = tipos_proposicoes(cfg)
    siglas_exec = tipos_executivo(cfg)

    por_sigla: dict[str, list[int]] = {}
    for mid, ficha in fichas.items():
        tipo_id = ficha.get("tipo_id")
        sigla = (tipos_materia.get(int(tipo_id)) or {}).get("sigla") if tipo_id is not None else ""
        if sigla:
            por_sigla.setdefault(str(sigla), []).append(int(mid))

    resumo: dict = {"anos": anos, "por_tipo": {}, "status_decodificados": decodificados}
    for ano in anos:
        for grupo, siglas in (("proposicoes", siglas_prop), ("executivo", siglas_exec)):
            chave = f"{grupo}_{ano}"
            itens = []
            for sigla in siglas:
                for mid in por_sigla.get(str(sigla), []):
                    ficha = fichas.get(int(mid)) or {}
                    if str(ficha.get("ano")) != str(ano):
                        continue
                    item = montar_item_base(
                        int(mid), str(sigla), fichas, tipos_materia, temas,
                        autoria, vereadores, historico, status, unidades, votacoes, cfg,
                    )
                    if grupo == "executivo":
                        if str(sigla) == "PLEX":
                            item["votos_nominais"] = votos_nominais_plex(int(mid), votacoes, vereadores)
                            if not item["votos_nominais"]:
                                item["votos_nominais_rotulo"] = ROTULO_SEM_VOTACAO
                            else:
                                item["votos_nominais_rotulo"] = None
                        else:
                            item["materia_vetada_id"] = None
                            item["materia_vetada_rotulo"] = ROTULO_VETADA_SEM_ESTRUTURA
                    itens.append(item)
            itens.sort(key=lambda m: (m.get("tipo_sigla") or "", m.get("numero") or "", m.get("id") or 0))
            sessoes = sessoes_do_ano(int(ano))
            sessao, mes, todo = dividir_periodos(itens, sessoes)
            for bloco in (sessao, mes, todo):
                for item in bloco:
                    recusar_ip(item)
            conteudo = {
                "meta": {
                    "gerado_por": SCRIPT_REL,
                    "ano": int(ano),
                    "grupo": grupo,
                    "total": len(todo),
                    "fonte_tramitacao": rel(pasta),
                    "status_decodificados": decodificados,
                },
                "sessao": sessao,
                "mes": mes,
                "todo": todo,
            }
            destino = DIR_SCRIPT / f"{grupo}_{ano}.json"
            escrever_lf(destino, conteudo)
            resumo["por_tipo"].setdefault(grupo, {})[str(ano)] = len(todo)
            print(f"{grupo} {ano}: todo={len(todo)} sessao={len(sessao)} mes={len(mes)}")

    for grupo, siglas in (("proposicoes", siglas_prop), ("executivo", siglas_exec)):
        itens = []
        for sigla in siglas:
            for mid in por_sigla.get(str(sigla), []):
                item = montar_item_base(
                    int(mid), str(sigla), fichas, tipos_materia, temas,
                    autoria, vereadores, historico, status, unidades, votacoes, cfg,
                )
                if grupo == "executivo":
                    if str(sigla) == "PLEX":
                        item["votos_nominais"] = votos_nominais_plex(int(mid), votacoes, vereadores)
                        if not item["votos_nominais"]:
                            item["votos_nominais_rotulo"] = ROTULO_SEM_VOTACAO
                        else:
                            item["votos_nominais_rotulo"] = None
                    else:
                        item["materia_vetada_id"] = None
                        item["materia_vetada_rotulo"] = ROTULO_VETADA_SEM_ESTRUTURA
                itens.append(item)
        itens.sort(key=lambda m: (str(m.get("ano") or ""), m.get("tipo_sigla") or "", m.get("numero") or ""))
        todas_sessoes = []
        for ano in anos:
            todas_sessoes.extend(sessoes_do_ano(int(ano)))
        sessao, mes, todo = dividir_periodos(itens, todas_sessoes)
        for bloco in (sessao, mes, todo):
            for item in bloco:
                recusar_ip(item)
        conteudo = {
            "meta": {
                "gerado_por": SCRIPT_REL,
                "anos": anos,
                "escopo": "legislatura",
                "grupo": grupo,
                "total": len(todo),
                "fonte_tramitacao": rel(pasta),
                "status_decodificados": decodificados,
            },
            "sessao": sessao,
            "mes": mes,
            "todo": todo,
        }
        destino = DIR_SCRIPT / f"{grupo}_legislatura.json"
        escrever_lf(destino, conteudo)
        resumo["por_tipo"].setdefault(grupo, {})["legislatura"] = len(todo)
        print(f"{grupo} legislatura: todo={len(todo)}")
    return resumo


def votos_nominais_plex(materia_id: int, votacoes: dict[int, list[dict]], vereadores: dict[int, dict]) -> list[dict]:
    registros = votacoes.get(int(materia_id)) or []
    escolhida = escolher_votacao(registros)
    if escolhida is None:
        return []
    estados = escolhida.get("estados_por_vereador") or []
    saida = []
    for linha in estados:
        pid = linha.get("id_sapl")
        if pid is None:
            continue
        pessoa = vereadores.get(int(pid)) or {}
        saida.append(
            {
                "parlamentar_id_sapl": int(pid),
                "nome_parlamentar": pessoa.get("nome_parlamentar") or linha.get("nome_parlamentar") or "",
                "estado": linha.get("estado"),
                "rotulo": linha.get("rotulo"),
                "voto_texto_sapl": linha.get("voto_texto_sapl"),
                "data_sessao": escolhida.get("data_sessao"),
                "sessao_id": escolhida.get("sessao_id"),
                "link_sessao": escolhida.get("link_sessao"),
            }
        )
    saida.sort(key=lambda x: x.get("nome_parlamentar") or "")
    return saida


def complementar_legislatura(cfg: dict) -> None:
    """Acrescenta por vereador REQ, MOC, IND de autoria e votos em PLEX.

    Nao toca nos arquivos por ano. So reescreve o da legislatura.
    """
    anos = anos_recorte(cfg)
    tipos_materia = carregar_tipos_materia()
    fichas = carregar_fichas()
    temas = carregar_temas()
    autoria = carregar_autoria()
    vereadores = carregar_vereadores()
    votacoes = carregar_votacoes(anos)
    siglas_prop_autoria = [s for s in tipos_proposicoes(cfg) if s != "PLEG"]
    destino = DIR_SCRIPT / "atuacao_vereadores_legislatura.json"
    if not destino.exists():
        raise SystemExit(f"Arquivo nao encontrado: {destino.name}")
    consolidado = carregar_json(destino)

    for vereador in consolidado.get("vereadores") or []:
        pid = int(vereador["id_sapl"])
        lista_prop = []
        for mid, autores in autoria.items():
            if not any(
                a.get("parlamentar_id_sapl") is not None and int(a["parlamentar_id_sapl"]) == pid
                for a in autores
            ):
                continue
            ficha = fichas.get(int(mid)) or {}
            tipo_id = ficha.get("tipo_id")
            sigla = (tipos_materia.get(int(tipo_id)) or {}).get("sigla") if tipo_id is not None else ""
            if str(sigla) not in siglas_prop_autoria:
                continue
            lista_prop.append(
                {
                    "id": int(mid),
                    "tipo_sigla": str(sigla),
                    "numero": str(ficha.get("numero")) if ficha.get("numero") is not None else None,
                    "ano": str(ficha.get("ano")) if ficha.get("ano") is not None else None,
                    "ementa": ficha.get("ementa") or "",
                    "tema": temas.get(int(mid)),
                    "link_sapl": link_materia(int(mid), cfg),
                }
            )
        lista_prop.sort(key=lambda x: (x.get("ano") or "", x.get("tipo_sigla") or "", x.get("numero") or ""))
        por_tipo: dict[str, int] = {}
        for item in lista_prop:
            por_tipo[item["tipo_sigla"]] = por_tipo.get(item["tipo_sigla"], 0) + 1
        vereador["proposicoes_req_moc_ind"] = {
            "total": len(lista_prop),
            "por_tipo": por_tipo,
            "lista": lista_prop,
        }
        votos_plex = []
        for nominal in (vereador.get("votos") or {}).get("nominais") or []:
            mid = nominal.get("materia_id")
            if mid is None:
                continue
            ficha = fichas.get(int(mid)) or {}
            tipo_id = ficha.get("tipo_id")
            sigla = (tipos_materia.get(int(tipo_id)) or {}).get("sigla") if tipo_id is not None else ""
            if str(sigla) != "PLEX":
                continue
            votos_plex.append(
                {
                    "materia_id": int(mid),
                    "tipo_sigla": "PLEX",
                    "estado": nominal.get("estado"),
                    "rotulo": nominal.get("rotulo"),
                    "voto_texto_sapl": nominal.get("voto_texto_sapl"),
                    "data_sessao": nominal.get("data_sessao"),
                    "sessao_id": nominal.get("sessao_id"),
                    "link_sessao": nominal.get("link_sessao"),
                    "link_materia": nominal.get("link_materia"),
                }
            )
        votos_plex.sort(key=lambda x: (x.get("data_sessao") or "", x.get("materia_id") or 0))
        vereador["votos_plex"] = votos_plex
    recusar_ip(consolidado)
    meta = consolidado.get("meta") or {}
    meta["proposicoes_executivo_por"] = SCRIPT_REL
    consolidado["meta"] = meta
    escrever_lf(destino, consolidado)
    print(f"Legislatura complementada: {len(consolidado.get('vereadores') or [])} vereadores.")


def main() -> int:
    cfg = carregar_config()
    base = endereco_sapl(cfg)
    print(f"Consolidacao de proposicoes e Executivo (C9). Fonte: {base}")
    gerar_arquivos(cfg)
    complementar_legislatura(cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
