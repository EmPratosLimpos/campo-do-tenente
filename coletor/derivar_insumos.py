"""Gera os insumos do pipeline a partir somente da pasta do lote.

Nao baixa nada e nao altera os brutos. O campo ip e removido na saida.
Votacao sem votoparlamentar fica com o rotulo
"voto individual nao registrado no SAPL".
O texto "Não Votou" e copiado como veio.

Ligacao da votacao com a sessao:
registrovotacao.ordem -> ordemdia.id -> ordemdia.sessao_plenaria
Se nao houver ordem, expediente -> expedientemateria.sessao_plenaria.
O campo sessao_plenaria, se aparecer em registro ou voto, e ignorado.

Rodar:  python coletor/derivar_insumos.py
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from config_cidade import (  # noqa: E402
    anos_recorte,
    carregar_config,
    id_legislatura_atual,
    id_tipo_sessao_ordinaria,
)

BRUTOS = RAIZ / "dados" / "brutos"
ROTULO_SEM_VOTO = "voto individual nao registrado no SAPL"
TEXTO_NAO_VOTOU = "Não Votou"
AVISO_LACUNA_2025 = "As sessoes ordinarias 1 a 16 de 2025 nao existem no SAPL."

PACOTE = (
    "ordemdia",
    "registrovotacao",
    "votoparlamentar",
    "sessaoplenariapresenca",
    "presencaordemdia",
    "justificativaausencia",
    "integrantemesa",
)

COLUNAS_MATERIA = [
    "ID",
    "Número",
    "Ano",
    "Tipo de Matéria Legislativa/Sigla",
    "Tipo de Matéria Legislativa/Descrição",
    "Ementa",
    "Autorias",
    "Texto Original",
]


def sem_ip(valor):
    if isinstance(valor, dict):
        return {chave: sem_ip(item) for chave, item in valor.items() if chave != "ip"}
    if isinstance(valor, list):
        return [sem_ip(item) for item in valor]
    return valor


def contem_ip(valor) -> bool:
    if isinstance(valor, dict):
        if "ip" in valor:
            return True
        return any(contem_ip(item) for item in valor.values())
    if isinstance(valor, list):
        return any(contem_ip(item) for item in valor)
    return False


def fonte(pasta_lote: Path, nome: str) -> str:
    return f"dados/brutos/{pasta_lote.name}/{nome}"


def ler_json(caminho: Path):
    return json.loads(caminho.read_text(encoding="utf-8"))


def gravar_json(caminho: Path, dado) -> None:
    if contem_ip(dado):
        raise SystemExit(f"Saida ainda contem ip: {caminho.name}")
    caminho.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(dado, ensure_ascii=False, indent=2) + "\n"
    tmp = caminho.with_suffix(caminho.suffix + ".tmp")
    tmp.write_text(texto, encoding="utf-8")
    tmp.replace(caminho)


RECURSOS_COLETA_POR_SESSAO = (
    "sessaoplenariapresenca",
    "presencaordemdia",
    "ordemdia",
    "justificativaausencia",
)
ARQUIVO_AVISOS_LEITURA = "avisos_leitura.json"


def base_do_prefixo(prefixo: str) -> str:
    if prefixo.endswith("_por_id"):
        return prefixo[: -len("_por_id")]
    return prefixo


def gravar_aviso_faltante(pasta: Path, aviso: dict) -> None:
    """Registra no lote que a lista tem menos ids distintos do que total_entries."""
    caminho = pasta / ARQUIVO_AVISOS_LEITURA
    existentes = []
    if caminho.exists():
        try:
            lidos = ler_json(caminho)
        except (OSError, ValueError):
            lidos = []
        if isinstance(lidos, list):
            existentes = [
                item
                for item in lidos
                if not (isinstance(item, dict) and item.get("prefixo") == aviso["prefixo"])
            ]
    existentes.append(aviso)
    gravar_json(caminho, existentes)
    print(
        f"AVISO: {aviso['prefixo']}: total_entries {aviso['total_entries']}, "
        f"ids distintos {aviso['ids_distintos']}, faltam {aviso['faltantes']}."
    )


def ler_paginas(pasta: Path, prefixo: str) -> tuple[list, list[str]]:
    resultados = []
    nomes = []
    total_esperado = None
    numero = 1
    while numero <= 500:
        caminho = pasta / f"{prefixo}_p{numero}.json"
        if not caminho.exists():
            if numero == 1:
                raise SystemExit(f"Arquivo ausente no lote: {prefixo}_p1.json")
            break
        dados = ler_json(caminho)
        if not isinstance(dados, dict) or not isinstance(dados.get("results"), list):
            raise SystemExit(f"{caminho.name}: sem lista results.")
        nomes.append(caminho.name)
        resultados.extend(dados["results"])
        paginacao = dados.get("pagination") or {}
        if numero == 1 and paginacao.get("total_entries") is not None:
            total_esperado = int(paginacao["total_entries"])
        total_paginas = paginacao.get("total_pages")
        tem_proxima = bool(
            paginacao.get("next_page") or (paginacao.get("links") or {}).get("next")
        )
        if total_paginas is not None and numero >= int(total_paginas):
            break
        if not tem_proxima:
            break
        numero += 1
    else:
        raise SystemExit(f"{prefixo}: paginacao passou de 500 paginas.")
    if total_esperado is not None and total_esperado != len(resultados):
        raise SystemExit(
            f"{prefixo}: o lote informa {total_esperado} registros "
            f"e a leitura achou {len(resultados)}. Nao completo lacuna."
        )
    vistos = set()
    unicos = []
    for linha in resultados:
        identificador = linha.get("id") if isinstance(linha, dict) else None
        if identificador is not None and identificador in vistos:
            continue
        if identificador is not None:
            vistos.add(identificador)
        unicos.append(linha)
    if (
        total_esperado is not None
        and len(vistos) < int(total_esperado)
        and not str(prefixo).startswith("sessao_")
    ):
        distintos = len(vistos)
        faltantes = int(total_esperado) - distintos
        gravar_aviso_faltante(
            pasta,
            {
                "prefixo": prefixo,
                "total_entries": int(total_esperado),
                "ids_distintos": distintos,
                "faltantes": faltantes,
            },
        )
        if base_do_prefixo(prefixo) not in RECURSOS_COLETA_POR_SESSAO:
            raise SystemExit(
                f"{prefixo}: {distintos} ids distintos para total_entries "
                f"{int(total_esperado)}. Faltam {faltantes} registros. "
                "Este recurso nao tem coleta por sessao. Parei."
            )
    return unicos, nomes


def escolher_prefixo(pasta: Path, base: str) -> str:
    alternativo = f"{base}_por_id"
    if not (pasta / f"{alternativo}_p1.json").exists():
        return base
    if _quantidade_unica(pasta, alternativo) > _quantidade_unica(pasta, base):
        return alternativo
    return base


def _quantidade_unica(pasta: Path, prefixo: str) -> int:
    ids = set()
    numero = 1
    while True:
        caminho = pasta / f"{prefixo}_p{numero}.json"
        if not caminho.exists():
            break
        try:
            dados = ler_json(caminho)
        except (OSError, ValueError):
            break
        for linha in dados.get("results") or []:
            if isinstance(linha, dict) and linha.get("id") is not None:
                ids.add(linha["id"])
        numero += 1
    return len(ids)


def _total_da_primeira_pagina(pasta: Path, prefixo: str):
    dados = ler_json(pasta / f"{prefixo}_p1.json")
    paginacao = dados.get("pagination") or {}
    if paginacao.get("total_entries") is None:
        return None
    return int(paginacao["total_entries"])


def ler_recurso_por_sessao(pasta: Path, ids_sessao: set[int], recurso: str):
    """Le as paginas filtradas por sessao. Cada pagina ja veio pronta do SAPL."""
    linhas = []
    nomes = []
    divergencias = []
    for sid in sorted(ids_sessao):
        prefixo = f"sessao_{sid}_{recurso}"
        parte, nomes_parte = ler_paginas(pasta, prefixo)
        total = _total_da_primeira_pagina(pasta, prefixo)
        distintos = len(
            {
                int(item["id"])
                for item in parte
                if isinstance(item, dict) and item.get("id") is not None
            }
        )
        if total is None or total != distintos:
            divergencias.append(
                {
                    "sessao_id": sid,
                    "recurso": recurso,
                    "total_entries": total,
                    "ids_distintos": distintos,
                }
            )
        linhas.extend(parte)
        nomes.extend(nomes_parte)
    return linhas, nomes, divergencias


def _mapa_sessao(linhas: list) -> dict[int, int | None]:
    mapa = {}
    for item in linhas:
        if not isinstance(item, dict) or item.get("id") is None:
            continue
        sid = item.get("sessao_plenaria")
        mapa[int(item["id"])] = int(sid) if sid is not None else None
    return mapa


def mesclar_com_porsessao(
    antigas: list, novas: list, ids_ordinarias: set[int]
) -> tuple[list, dict]:
    """A lista por sessao vale para as ordinarias. Id antigo que nao voltou permanece."""
    mapa_antigo = _mapa_sessao(antigas)
    mapa_novo = _mapa_sessao(novas)
    antigos_na_ordinaria = {
        identificador
        for identificador, sid in mapa_antigo.items()
        if sid is not None and sid in ids_ordinarias
    }
    sumiram = sorted(antigos_na_ordinaria - set(mapa_novo))
    acrescentados = sorted(set(mapa_novo) - set(mapa_antigo))
    novas_por_id = indice_por_id(novas)
    saida = []
    vistos = set()
    for item in novas:
        if not isinstance(item, dict) or item.get("id") is None:
            continue
        sid = item.get("sessao_plenaria")
        if sid is None or int(sid) not in ids_ordinarias:
            continue
        identificador = int(item["id"])
        if identificador in vistos:
            continue
        vistos.add(identificador)
        saida.append(item)
    for item in antigas:
        if not isinstance(item, dict) or item.get("id") is None:
            saida.append(item)
            continue
        identificador = int(item["id"])
        if identificador in vistos:
            continue
        vistos.add(identificador)
        saida.append(item)
    cobertura = {
        "ids_lote_antigo": len(mapa_antigo),
        "ids_lote_antigo_nas_ordinarias": len(antigos_na_ordinaria),
        "ids_por_sessao": len(mapa_novo),
        "ids_novos": len(acrescentados),
        "ids_novos_lista": acrescentados,
        "ids_que_sumiram": sumiram,
    }
    return saida, cobertura


def recursos_com_faltante(pasta: Path) -> list[str]:
    caminho = pasta / ARQUIVO_AVISOS_LEITURA
    if not caminho.exists():
        return []
    try:
        dados = ler_json(caminho)
    except (OSError, ValueError):
        return []
    if not isinstance(dados, list):
        return []
    achados = []
    for item in dados:
        if not isinstance(item, dict):
            continue
        base = base_do_prefixo(str(item.get("prefixo") or ""))
        if base in RECURSOS_COLETA_POR_SESSAO and base not in achados:
            achados.append(base)
    return achados


def exigir_pasta_por_sessao(incompletas: list[str], pasta_porsessao: Path | None) -> None:
    if incompletas and pasta_porsessao is None:
        raise SystemExit(
            "Ids distintos menores que total_entries em "
            + ", ".join(incompletas)
            + ". Esses recursos dependem da coleta por sessao e essa pasta nao foi encontrada. Parei."
        )


def aplicar_fonte_incompleta(
    recurso: str,
    antigas: list,
    pasta_porsessao: Path,
    ids_ordinarias: set[int],
    incompleta: bool,
) -> tuple[list, list[str], dict]:
    """A coleta por sessao e a fonte quando a lista geral perdeu ids."""
    novas, nomes_novos, divergencias = ler_recurso_por_sessao(
        pasta_porsessao, ids_ordinarias, recurso
    )
    mescladas, cobertura = mesclar_com_porsessao(antigas, novas, ids_ordinarias)
    cobertura["sessoes_com_divergencia"] = divergencias
    if incompleta:
        cobertura["fonte"] = "coleta_por_sessao"
    return mescladas, nomes_novos, cobertura


def ler_ordens_avulsas(pasta: Path) -> tuple[list, list[str]]:
    linhas = []
    nomes = []
    for caminho in sorted(pasta.glob("ordemdia_id_*.json")):
        dados = ler_json(caminho)
        if isinstance(dados, dict) and dados.get("id") is not None and "results" not in dados:
            linhas.append(dados)
            nomes.append(caminho.name)
    return linhas, nomes


def ler_paginas_se_existir(pasta: Path, prefixo: str) -> tuple[list, list[str]]:
    if not (pasta / f"{prefixo}_p1.json").exists():
        return [], []
    return ler_paginas(pasta, prefixo)


def indice_por_id(linhas: list) -> dict[int, dict]:
    indice = {}
    for linha in linhas:
        if isinstance(linha, dict) and linha.get("id") is not None:
            indice[int(linha["id"])] = linha
    return indice


def ano_de_data(data: str | None) -> int | None:
    if isinstance(data, str) and len(data) >= 4 and data[:4].isdigit():
        return int(data[:4])
    return None


def sessao_por_ordem_ou_expediente(registro: dict, ordem: dict, expediente: dict):
    """Ignora sessao_plenaria no proprio registro."""
    if registro.get("ordem") is not None:
        item = ordem.get(int(registro["ordem"]))
        if item is None:
            return None
        return item.get("sessao_plenaria")
    if registro.get("expediente") is not None:
        item = expediente.get(int(registro["expediente"]))
        if item is None:
            return None
        return item.get("sessao_plenaria")
    return None


def sessao_do_voto(voto: dict, ordem: dict, expediente: dict, sessao_do_registro: dict):
    if voto.get("ordem") is not None:
        item = ordem.get(int(voto["ordem"]))
        if item is not None and item.get("sessao_plenaria") is not None:
            return item.get("sessao_plenaria")
    if voto.get("expediente") is not None:
        item = expediente.get(int(voto["expediente"]))
        if item is not None and item.get("sessao_plenaria") is not None:
            return item.get("sessao_plenaria")
    if voto.get("votacao") is not None:
        return sessao_do_registro.get(int(voto["votacao"]))
    return None


def e_nao_votou(valor) -> bool:
    return valor == TEXTO_NAO_VOTOU


def gravar_pacote(caminho: Path, linhas: list) -> None:
    limpos = [sem_ip(linha) for linha in linhas]
    gravar_json(caminho, {"results": limpos, "total": len(limpos)})


def lacuna_ordinarias(ano: int, ordinarias: list[dict]) -> dict:
    numeros = [int(item["numero"]) for item in ordinarias if item.get("numero") is not None]
    if not numeros:
        return {
            "numeros_ausentes_no_sapl": [],
            "primeira_ordinaria_no_sapl": None,
            "aviso": "Nenhuma sessao ordinaria deste ano no SAPL.",
        }
    presentes = set(numeros)
    ausentes = [numero for numero in range(1, max(numeros) + 1) if numero not in presentes]
    primeira = min(ordinarias, key=lambda item: (item.get("data_inicio") or "", int(item.get("numero") or 0)))
    aviso = None
    if ano == 2025 and set(range(1, 17)).issubset(ausentes):
        aviso = AVISO_LACUNA_2025
        outros = [numero for numero in ausentes if numero > 16]
        if outros:
            aviso += " Tambem nao constam os numeros " + ", ".join(str(numero) for numero in outros) + "."
    elif ausentes:
        aviso = (
            "Nao constam no SAPL as ordinarias de numero "
            + ", ".join(str(numero) for numero in ausentes)
            + "."
        )
    return {
        "numeros_ausentes_no_sapl": ausentes,
        "primeira_ordinaria_no_sapl": {
            "id": int(primeira["id"]),
            "numero": int(primeira["numero"]),
            "data_inicio": primeira.get("data_inicio"),
        },
        "aviso": aviso,
    }


def derivar(
    pasta_lote: Path,
    pasta_saida: Path,
    anos: list[int],
    tipo_ordinaria: int,
    legislatura_id: int,
    pasta_porsessao: Path | None = None,
) -> dict:
    pasta_saida.mkdir(parents=True, exist_ok=True)
    sessoes = []
    nomes_sessao = {}
    for ano in anos:
        linhas, nomes = ler_paginas(pasta_lote, f"sessaoplenaria_ano{ano}")
        nomes_sessao[ano] = nomes
        for linha in linhas:
            item = dict(linha)
            item["_ano_arquivo"] = ano
            sessoes.append(item)

    ordem_linhas, nomes_ordem = ler_paginas(pasta_lote, escolher_prefixo(pasta_lote, "ordemdia"))
    avulsas, nomes_avulsas = ler_ordens_avulsas(pasta_lote)
    ids_ordem = {int(item["id"]) for item in ordem_linhas if item.get("id") is not None}
    for item in avulsas:
        if int(item["id"]) not in ids_ordem:
            ordem_linhas.append(item)
    nomes_ordem = list(nomes_ordem) + nomes_avulsas
    expediente_linhas, nomes_expediente = ler_paginas(pasta_lote, "expedientemateria")
    registros, nomes_registro = ler_paginas(pasta_lote, "registrovotacao")
    votos, nomes_voto = ler_paginas(pasta_lote, "votoparlamentar")
    presencas, nomes_presenca = ler_paginas(
        pasta_lote, escolher_prefixo(pasta_lote, "sessaoplenariapresenca")
    )
    presencas_ordem, nomes_presenca_ordem = ler_paginas(
        pasta_lote, escolher_prefixo(pasta_lote, "presencaordemdia")
    )
    justificativas, nomes_justificativa = ler_paginas(pasta_lote, "justificativaausencia")
    mesa, nomes_mesa = ler_paginas(pasta_lote, "integrantemesa")
    parlamentares, nomes_parlamentar = ler_paginas(pasta_lote, "parlamentar")
    mandatos, nomes_mandato = ler_paginas(pasta_lote, "mandato")
    partidos, nomes_partido = ler_paginas(pasta_lote, "partido")
    filiacoes, nomes_filiacao = ler_paginas(pasta_lote, "filiacao")
    tipos_materia, nomes_tipo_materia = ler_paginas(pasta_lote, "tipomaterialegislativa")
    tipos_afastamento, nomes_afastamento = ler_paginas_se_existir(pasta_lote, "tipoafastamento")
    tipos_resultado, _nomes_resultado = ler_paginas_se_existir(pasta_lote, "tiporesultadovotacao")

    ordem = indice_por_id(ordem_linhas)
    expediente = indice_por_id(expediente_linhas)
    por_parlamentar = indice_por_id(parlamentares)
    nome_afastamento = {
        int(item["id"]): item.get("nome") or item.get("descricao")
        for item in tipos_afastamento
        if isinstance(item, dict) and item.get("id") is not None
    }
    nome_resultado = {
        int(item["id"]): item.get("nome")
        for item in tipos_resultado
        if isinstance(item, dict) and item.get("id") is not None
    }
    tipo_materia = indice_por_id(tipos_materia)

    sessao_por_id = {}
    anomalias_ano = []
    for sessao in sessoes:
        sid = int(sessao["id"])
        ano_arquivo = int(sessao["_ano_arquivo"])
        ano_data = ano_de_data(sessao.get("data_inicio"))
        if ano_data is not None and ano_data != ano_arquivo:
            anomalias_ano.append(
                {"sessao_id": sid, "ano_arquivo": ano_arquivo, "data_inicio": sessao.get("data_inicio")}
            )
        sessao_por_id[sid] = sessao

    ids_recorte = set(sessao_por_id)
    ids_ordinarias = {
        int(sessao["id"])
        for sessao in sessoes
        if int(sessao.get("tipo") or 0) == int(tipo_ordinaria)
    }
    incompletas = recursos_com_faltante(pasta_lote)
    exigir_pasta_por_sessao(incompletas, pasta_porsessao)
    cobertura_porsessao = None
    pasta_fonte_listas = pasta_lote
    if pasta_porsessao is not None:
        pasta_fonte_listas = pasta_porsessao
        cobertura_porsessao = {
            "pasta": f"dados/brutos/{pasta_porsessao.name}",
            "recursos": {},
        }
        blocos = {
            "ordemdia": ordem_linhas,
            "sessaoplenariapresenca": presencas,
            "presencaordemdia": presencas_ordem,
            "justificativaausencia": justificativas,
        }
        for recurso, antigas in blocos.items():
            mescladas, nomes_novos, cobertura = aplicar_fonte_incompleta(
                recurso,
                antigas,
                pasta_porsessao,
                ids_ordinarias,
                recurso in incompletas,
            )
            cobertura_porsessao["recursos"][recurso] = cobertura
            if recurso == "ordemdia":
                ordem_linhas, nomes_ordem = mescladas, nomes_novos
            elif recurso == "sessaoplenariapresenca":
                presencas, nomes_presenca = mescladas, nomes_novos
            elif recurso == "presencaordemdia":
                presencas_ordem, nomes_presenca_ordem = mescladas, nomes_novos
            else:
                justificativas, nomes_justificativa = mescladas, nomes_novos

    sessao_do_registro = {}
    registros_sem_sessao = []
    for registro in registros:
        sid = sessao_por_ordem_ou_expediente(registro, ordem, expediente)
        if sid is None:
            registros_sem_sessao.append(int(registro["id"]))
            continue
        sessao_do_registro[int(registro["id"])] = int(sid)

    votos_sem_sessao = []
    votos_por_sessao: dict[int, list] = {sid: [] for sid in ids_recorte}
    votos_por_votacao: dict[int, list] = {}
    for voto in votos:
        if voto.get("votacao") is not None:
            votos_por_votacao.setdefault(int(voto["votacao"]), []).append(voto)
        sid = sessao_do_voto(voto, ordem, expediente, sessao_do_registro)
        if sid is None or int(sid) not in ids_recorte:
            votos_sem_sessao.append(int(voto.get("id") or 0))
            continue
        votos_por_sessao[int(sid)].append(voto)

    registros_por_sessao: dict[int, list] = {sid: [] for sid in ids_recorte}
    registros_fora = []
    for registro in registros:
        sid = sessao_do_registro.get(int(registro["id"]))
        if sid is None or sid not in ids_recorte:
            if int(registro["id"]) not in registros_sem_sessao:
                registros_fora.append(int(registro["id"]))
            continue
        registros_por_sessao[sid].append(registro)

    def agrupar(linhas: list) -> dict[int, list]:
        grupos = {sid: [] for sid in ids_recorte}
        for linha in linhas:
            sid = linha.get("sessao_plenaria")
            if sid is None or int(sid) not in ids_recorte:
                continue
            grupos[int(sid)].append(linha)
        return grupos

    ordem_por_sessao = agrupar(ordem_linhas)
    presenca_por_sessao = agrupar(presencas)
    presenca_ordem_por_sessao = agrupar(presencas_ordem)
    justificativa_por_sessao = agrupar(justificativas)
    mesa_por_sessao = agrupar(mesa)

    for sid in sorted(ids_recorte):
        gravar_pacote(pasta_saida / f"sessao_{sid}_ordemdia.json", ordem_por_sessao[sid])
        gravar_pacote(pasta_saida / f"sessao_{sid}_registrovotacao.json", registros_por_sessao[sid])
        gravar_pacote(pasta_saida / f"sessao_{sid}_votoparlamentar.json", votos_por_sessao[sid])
        gravar_pacote(
            pasta_saida / f"sessao_{sid}_sessaoplenariapresenca.json",
            presenca_por_sessao[sid],
        )
        gravar_pacote(
            pasta_saida / f"sessao_{sid}_presencaordemdia.json",
            presenca_ordem_por_sessao[sid],
        )
        gravar_pacote(
            pasta_saida / f"sessao_{sid}_justificativaausencia.json",
            justificativa_por_sessao[sid],
        )
        gravar_pacote(pasta_saida / f"sessao_{sid}_integrantemesa.json", mesa_por_sessao[sid])

    contagens = {}
    for ano in anos:
        do_ano = []
        for sessao in sessoes:
            if int(sessao["_ano_arquivo"]) != ano:
                continue
            if int(sessao.get("tipo") or 0) != int(tipo_ordinaria):
                continue
            do_ano.append(sessao)
        do_ano.sort(key=lambda item: (item.get("data_inicio") or "", int(item.get("numero") or 0), int(item["id"])))
        sessoes_saida = []
        total_votacoes = 0
        com_voto = 0
        sem_voto = 0
        n_nao_votou = 0
        n_votacoes_com_nao_votou = 0
        n_votacoes_um_nao_votou = 0
        n_presenca = 0
        n_presenca_ordem = 0
        n_justificativa = 0
        for sessao in do_ano:
            sid = int(sessao["id"])
            detalhes = []
            for registro in registros_por_sessao[sid]:
                individuais = votos_por_votacao.get(int(registro["id"]), [])
                n_nv = sum(1 for voto in individuais if e_nao_votou(voto.get("voto")))
                item = {
                    "id": int(registro["id"]),
                    "ordem": registro.get("ordem"),
                    "expediente": registro.get("expediente"),
                    "materia": registro.get("materia"),
                    "numero_votos_sim": registro.get("numero_votos_sim"),
                    "numero_votos_nao": registro.get("numero_votos_nao"),
                    "numero_abstencoes": registro.get("numero_abstencoes"),
                    "tipo_resultado_votacao": registro.get("tipo_resultado_votacao"),
                    "resultado_nome": nome_resultado.get(int(registro["tipo_resultado_votacao"]))
                    if registro.get("tipo_resultado_votacao") is not None
                    else None,
                    "n_votos_individuais": len(individuais),
                    "n_nao_votou": n_nv,
                }
                if len(individuais) == 0:
                    item["voto_individual"] = ROTULO_SEM_VOTO
                    sem_voto += 1
                else:
                    item["voto_individual"] = "registrado"
                    com_voto += 1
                if n_nv:
                    n_votacoes_com_nao_votou += 1
                if n_nv == 1:
                    n_votacoes_um_nao_votou += 1
                n_nao_votou += n_nv
                detalhes.append(item)
            total_votacoes += len(detalhes)
            n_presenca += len(presenca_por_sessao[sid])
            n_presenca_ordem += len(presenca_ordem_por_sessao[sid])
            n_justificativa += len(justificativa_por_sessao[sid])
            sessoes_saida.append(
                {
                    "id": sid,
                    "numero": int(sessao["numero"]) if sessao.get("numero") is not None else None,
                    "data": sessao.get("data_inicio"),
                    "rotulo": sessao.get("__str__") or "",
                    "tipo": int(sessao.get("tipo")),
                    "n_votacoes": len(detalhes),
                    "n_votacoes_com_voto_individual": sum(
                        1 for item in detalhes if item["voto_individual"] == "registrado"
                    ),
                    "n_votacoes_sem_voto_individual": sum(
                        1 for item in detalhes if item["voto_individual"] == ROTULO_SEM_VOTO
                    ),
                    "n_nao_votou": sum(item["n_nao_votou"] for item in detalhes),
                    "n_presencas_sessao": len(presenca_por_sessao[sid]),
                    "n_presencas_ordem_dia": len(presenca_ordem_por_sessao[sid]),
                    "n_justificativas": len(justificativa_por_sessao[sid]),
                    "votacoes": detalhes,
                }
            )
        lacuna = lacuna_ordinarias(ano, do_ano)
        contagem = {
            "ano": ano,
            "id_tipo_sessao_ordinaria": int(tipo_ordinaria),
            "total_sessoes_ordinarias": len(sessoes_saida),
            "total_votacoes": total_votacoes,
            "votacoes_com_voto_individual": com_voto,
            "votacoes_sem_voto_individual": sem_voto,
            "rotulo_sem_voto_individual": ROTULO_SEM_VOTO,
            "n_nao_votou": n_nao_votou,
            "n_votacoes_com_nao_votou": n_votacoes_com_nao_votou,
            "n_votacoes_com_exatamente_um_nao_votou": n_votacoes_um_nao_votou,
            "n_presencas_sessao": n_presenca,
            "n_presencas_ordem_dia": n_presenca_ordem,
            "n_justificativas": n_justificativa,
            "lacuna_sessoes_ordinarias": lacuna,
            "arquivos_de_origem": [fonte(pasta_lote, nome) for nome in nomes_sessao[ano]],
            "sessoes": sessoes_saida,
        }
        gravar_json(pasta_saida / f"contagem_votacoes_ordinarias_{ano}.json", contagem)
        contagens[str(ano)] = {
            "sessoes_ordinarias": len(sessoes_saida),
            "votacoes": total_votacoes,
            "votacoes_com_voto_individual": com_voto,
            "votacoes_sem_voto_individual": sem_voto,
            "n_nao_votou": n_nao_votou,
            "n_votacoes_com_nao_votou": n_votacoes_com_nao_votou,
            "n_votacoes_com_exatamente_um_nao_votou": n_votacoes_um_nao_votou,
            "n_presencas_sessao": n_presenca,
            "n_presencas_ordem_dia": n_presenca_ordem,
            "n_justificativas": n_justificativa,
            "lacuna_sessoes_ordinarias": lacuna,
            "arquivo": f"dados/brutos/contagem_votacoes_ordinarias_{ano}.json",
        }

    materias_por_ano = {}
    for ano in anos:
        linhas, nomes = ler_paginas(pasta_lote, f"materialegislativa_ano{ano}")
        caminho_csv = pasta_saida / f"materias-{ano}-resposta-original.csv"
        with caminho_csv.open("w", encoding="utf-8-sig", newline="") as handle:
            escritor = csv.DictWriter(handle, fieldnames=COLUNAS_MATERIA, delimiter=";")
            escritor.writeheader()
            for materia in linhas:
                tipo = tipo_materia.get(int(materia["tipo"])) if materia.get("tipo") is not None else None
                escritor.writerow(
                    {
                        "ID": materia.get("id"),
                        "Número": materia.get("numero"),
                        "Ano": materia.get("ano"),
                        "Tipo de Matéria Legislativa/Sigla": (tipo or {}).get("sigla") or "",
                        "Tipo de Matéria Legislativa/Descrição": (tipo or {}).get("descricao") or "",
                        "Ementa": materia.get("ementa") or "",
                        "Autorias": "",
                        "Texto Original": materia.get("texto_original") or "",
                    }
                )
        por_tipo: dict[str, int] = {}
        for materia in linhas:
            tipo = tipo_materia.get(int(materia["tipo"])) if materia.get("tipo") is not None else None
            sigla = (tipo or {}).get("sigla") or "sem_tipo"
            por_tipo[sigla] = por_tipo.get(sigla, 0) + 1
        materias_por_ano[str(ano)] = {
            "total": len(linhas),
            "por_sigla": dict(sorted(por_tipo.items())),
            "arquivos": [fonte(pasta_lote, nome) for nome in nomes],
            "autorias": (
                "O JSON traz autores como identificadores numericos, sem nome. "
                "A coluna Autorias ficou vazia. Nomes nao foram inventados."
            ),
        }

    gravar_json(
        pasta_saida / "api_parlamentares_partido.json",
        {"results": [sem_ip(item) for item in partidos], "total": len(partidos)},
    )
    gravar_json(
        pasta_saida / "api_parlamentares_filiacao.json",
        {"results": [sem_ip(item) for item in filiacoes], "total": len(filiacoes)},
    )
    if tipos_afastamento:
        gravar_json(
            pasta_saida / "api_parlamentares_tipoafastamento.json",
            {
                "results": [sem_ip(item) for item in tipos_afastamento],
                "total": len(tipos_afastamento),
            },
        )

    mandatos_leg = []
    for mandato in mandatos:
        if int(mandato.get("legislatura") or 0) != int(legislatura_id):
            continue
        pid = int(mandato["parlamentar"])
        pessoa = por_parlamentar.get(pid) or {}
        tipo_id = mandato.get("tipo_afastamento")
        mandatos_leg.append(
            {
                "mandato_id": int(mandato["id"]),
                "parlamentar_id": pid,
                "nome_parlamentar": pessoa.get("nome_parlamentar") or "",
                "titular": bool(mandato.get("titular")),
                "data_inicio_mandato": mandato.get("data_inicio_mandato"),
                "data_fim_mandato": mandato.get("data_fim_mandato"),
                "tipo_afastamento_id": int(tipo_id) if tipo_id is not None else None,
                "tipo_afastamento_nome": nome_afastamento.get(int(tipo_id)) if tipo_id is not None else None,
            }
        )
    mandatos_leg.sort(key=lambda item: item["mandato_id"])
    gravar_json(
        pasta_saida / "mandatos_legislatura_atual.json",
        {
            "legislatura_id": int(legislatura_id),
            "arquivos_de_origem": [fonte(pasta_lote, nome) for nome in nomes_mandato],
            "mandatos": mandatos_leg,
        },
    )

    ids_mandato = {item["parlamentar_id"] for item in mandatos_leg}
    cadastro = {}
    sem_cadastro = []
    for pid in sorted(ids_mandato):
        pessoa = por_parlamentar.get(pid)
        if pessoa is None:
            sem_cadastro.append(pid)
            continue
        cadastro[str(pid)] = sem_ip(
            {
                "id": pid,
                "nome_completo": pessoa.get("nome_completo") or "",
                "nome_parlamentar": pessoa.get("nome_parlamentar") or "",
                "__str__": pessoa.get("__str__") or "",
                "ativo": pessoa.get("ativo"),
                "link_detail_backend": pessoa.get("link_detail_backend") or "",
                "fotografia": pessoa.get("fotografia") or "",
            }
        )
    gravar_json(pasta_saida / "sessao_cadastro_parlamentares.json", cadastro)

    resumo = {
        "pasta_lote": f"dados/brutos/{pasta_lote.name}",
        "cobertura_porsessao": cobertura_porsessao,
        "rotulo_sem_voto_individual": ROTULO_SEM_VOTO,
        "texto_nao_votou_preservado": TEXTO_NAO_VOTOU,
        "contagens": contagens,
        "materias": materias_por_ano,
        "mandatos_legislatura": {
            "legislatura_id": int(legislatura_id),
            "n": len(mandatos_leg),
            "arquivo": "dados/brutos/mandatos_legislatura_atual.json",
            "arquivos_de_origem": [fonte(pasta_lote, nome) for nome in nomes_mandato],
        },
        "arquivos_de_origem": {
            "ordemdia": [fonte(pasta_fonte_listas, nome) for nome in nomes_ordem],
            "expedientemateria": [fonte(pasta_lote, nome) for nome in nomes_expediente],
            "registrovotacao": [fonte(pasta_lote, nome) for nome in nomes_registro],
            "votoparlamentar": [fonte(pasta_lote, nome) for nome in nomes_voto],
            "sessaoplenariapresenca": [fonte(pasta_fonte_listas, nome) for nome in nomes_presenca],
            "presencaordemdia": [fonte(pasta_fonte_listas, nome) for nome in nomes_presenca_ordem],
            "justificativaausencia": [fonte(pasta_fonte_listas, nome) for nome in nomes_justificativa],
            "integrantemesa": [fonte(pasta_lote, nome) for nome in nomes_mesa],
            "parlamentar": [fonte(pasta_lote, nome) for nome in nomes_parlamentar],
            "partido": [fonte(pasta_lote, nome) for nome in nomes_partido],
            "filiacao": [fonte(pasta_lote, nome) for nome in nomes_filiacao],
            "tipomaterialegislativa": [fonte(pasta_lote, nome) for nome in nomes_tipo_materia],
            "tipoafastamento": [fonte(pasta_lote, nome) for nome in nomes_afastamento],
        },
        "registros_sem_ligacao_de_sessao": registros_sem_sessao,
        "registros_fora_do_recorte": registros_fora,
        "votos_sem_sessao_no_recorte": votos_sem_sessao,
        "sessoes_com_ano_divergente": anomalias_ano,
        "parlamentares_de_mandato_ausentes_no_cadastro": sem_cadastro,
        "nota_autoria": (
            "Autorias no CSV ficaram vazias porque o lote nao traz o nome do autor, "
            "so o identificador numerico em materialegislativa.autores."
        ),
    }
    gravar_json(pasta_saida / "resumo_insumos.json", resumo)
    return resumo


def pasta_lote_mais_recente(brutos: Path) -> Path:
    candidatas = []
    for caminho in brutos.glob("lote_*"):
        if not caminho.is_dir() or "porsessao" in caminho.name or caminho.name.endswith("_autoria"):
            continue
        indice = caminho / "indice.json"
        if not indice.exists():
            continue
        try:
            dados = json.loads(indice.read_text(encoding="utf-8"))
            pedidos = int(dados.get("total_pedidos") or 0)
        except (OSError, ValueError, TypeError):
            pedidos = 0
        candidatas.append((pedidos, caminho.name, caminho))
    if not candidatas:
        raise SystemExit("Nenhuma pasta dados/brutos/lote_<data>. Rode o coletor antes.")
    candidatas.sort()
    return candidatas[-1][2]


def pasta_porsessao_mais_recente(brutos: Path) -> Path | None:
    candidatas = [
        caminho
        for caminho in brutos.glob("lote_*_porsessao")
        if caminho.is_dir() and (caminho / "indice.json").exists()
    ]
    if not candidatas:
        return None
    return sorted(candidatas)[-1]


def main() -> None:
    cfg = carregar_config()
    pasta = pasta_lote_mais_recente(BRUTOS)
    por_sessao = pasta_porsessao_mais_recente(BRUTOS)
    resumo = derivar(
        pasta,
        BRUTOS,
        anos_recorte(cfg),
        id_tipo_sessao_ordinaria(cfg),
        id_legislatura_atual(cfg),
        pasta_porsessao=por_sessao,
    )
    print(f"Insumos gerados a partir de dados/brutos/{pasta.name}")
    for ano, bloco in resumo["contagens"].items():
        print(
            f"  {ano}: {bloco['sessoes_ordinarias']} ordinarias, "
            f"{bloco['votacoes']} votacoes, "
            f"{bloco['votacoes_sem_voto_individual']} sem voto individual, "
            f"{bloco['n_nao_votou']} Nao Votou"
        )


if __name__ == "__main__":
    main()
