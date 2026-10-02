"""Gera a atuacao consolidada dos vereadores, um arquivo por ano do config.

Le dados/brutos/, a tabela de vereadores, a presidencia das sessoes e a
autoria das materias. Nao pede nada ao SAPL. Nao inventa voto, falta,
numero nem autoria. Rodar de novo tem que produzir o mesmo JSON.

Uso:
    python dados/tratados/gerar_atuacao_vereadores.py
"""

from __future__ import annotations

import csv
import io
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

DIR_SCRIPT = Path(__file__).resolve().parent
DIR_RAIZ = DIR_SCRIPT.parent.parent
DIR_BRUTOS = DIR_SCRIPT.parent / "brutos"
if str(DIR_SCRIPT) not in sys.path:
    sys.path.insert(0, str(DIR_SCRIPT))
if str(DIR_RAIZ / "coletor") not in sys.path:
    sys.path.insert(0, str(DIR_RAIZ / "coletor"))

from config_cidade import (  # noqa: E402
    PisoNaoDefinido,
    anos_recorte,
    campos_pessoais,
    carregar_config,
    exigir_piso,
    link_materia,
    link_sessao,
    nome_cidade,
    pisos_sanidade,
    tipos_dois_turnos,
    uf_cidade,
)
CONFIG = carregar_config()
DOIS_TURNOS = tipos_dois_turnos(CONFIG)
TURNO_PRIMEIRO = "1o turno"
TURNO_SEGUNDO = "2o turno"
TURNO_UNICO = "turno unico"
TURNO_NAO_IDENTIFICADO = "turno nao identificado"
TURNOS_CONTADOS = (TURNO_SEGUNDO, TURNO_UNICO)
SCRIPT_REL = "dados/tratados/gerar_atuacao_vereadores.py"
ARQUIVO_VEREADORES = DIR_SCRIPT / "vereadores.json"
ARQUIVO_PRESIDENCIA = DIR_SCRIPT / "presidencia_sessoes.json"
ARQUIVO_AUTORIA = DIR_SCRIPT / "autoria_materias.json"
ARQUIVO_AFASTAMENTOS = DIR_SCRIPT / "afastamentos_manuais.json"
TIPOS_PROJETO = ("PLEG", "PLEX")
TIPO_PLL = "PLEG"
ARQUIVO_TEMAS = DIR_SCRIPT / "temas_materias.json"

ORDEM_ESTADOS = (
    "sim",
    "nao",
    "abstencao",
    "nao_votou",
    "presidente_que_nao_votou",
    "ausente_com_justificativa",
    "ausente_sem_justificativa",
    "fora_do_mandato",
    "presente_sem_voto_individual_registrado",
)
ROTULOS_ESTADO = {
    "sim": "Sim",
    "nao": "Não",
    "abstencao": "Abstenção",
    "nao_votou": "Não votou",
    "presidente_que_nao_votou": "Presidente que não votou",
    "ausente_com_justificativa": "Ausente com justificativa",
    "ausente_sem_justificativa": "Ausente sem justificativa",
    "fora_do_mandato": "Fora do mandato naquela data",
    "presente_sem_voto_individual_registrado": (
        "Presente na sessão sem voto individual registrado"
    ),
}
LICENCA_TIPOS: list[str] = []
TIPOS_JUSTIFICATIVA_SAPL: dict[int, str] = {}
VOTOS_SIM = {"Sim"}
VOTOS_NAO = {"Não", "Nao"}
VOTOS_ABSTENCAO = {"Abstenção", "Abstencao"}
VOTOS_NAO_VOTOU = {"Não Votou", "Nao Votou"}
RESULTADO_VOTACAO = re.compile(
    r"Vota(?:ção|cao):\s*(?:Aprovada por\s+)?(UNANIMIDADE|MAIORIA ABSOLUTA|REJEITAD[AO])\s*$",
    re.IGNORECASE,
)
APROVADOS = {"UNANIMIDADE", "MAIORIA ABSOLUTA"}
REJEITADOS = {"REJEITADO"}
SITUACAO_NAO_MAPEADA = "Resultado nao mapeado"
AVISO_CONFLITO_AFASTAMENTO = "conflito entre voto registrado e afastamento"
PACOTE_SESSAO = (
    "sessaoplenariapresenca",
    "presencaordemdia",
    "justificativaausencia",
    "integrantemesa",
    "votoparlamentar",
    "registrovotacao",
)


def rel(caminho: Path) -> str:
    try:
        return caminho.resolve().relative_to(DIR_RAIZ.resolve()).as_posix()
    except ValueError:
        return caminho.name


def carregar_json(caminho: Path):
    return json.loads(caminho.read_text(encoding="utf-8"))


def escrever_lf(caminho: Path, texto: str) -> None:
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    if not texto.endswith("\n"):
        texto += "\n"
    if "\r" in texto:
        raise SystemExit(f"{rel(caminho)} ainda tem quebra de linha CR.")
    caminho.write_bytes(texto.encode("utf-8"))


def recusar_campos_pessoais(obj, caminho: str = "") -> None:
    """Nenhum campo pessoal do SAPL pode chegar em dado tratado (SEG2).

    A lista vem de config_cidade.json, a mesma do coletor.
    """
    chaves = set(campos_pessoais(CONFIG))
    if isinstance(obj, dict):
        if chaves & set(obj.keys()):
            raise SystemExit(
                f"Campo pessoal em dado tratado: {caminho or 'raiz'}. "
                "A lista esta em config_cidade.json."
            )
        for chave, valor in obj.items():
            recusar_campos_pessoais(valor, f"{caminho}.{chave}")
    elif isinstance(obj, list):
        for indice, valor in enumerate(obj):
            recusar_campos_pessoais(valor, f"{caminho}[{indice}]")


def resultados_de_lista(data) -> list:
    if isinstance(data, dict) and isinstance(data.get("results"), list):
        return data["results"]
    if isinstance(data, list):
        return data
    return []


def conferir_total(caminho: Path, data) -> int:
    resultados = resultados_de_lista(data)
    if isinstance(data, dict) and "total" in data:
        total = int(data["total"])
        if total != len(resultados):
            raise SystemExit(
                f"{caminho.name}: o campo total e {total}, "
                f"mas o arquivo tem {len(resultados)} registros."
            )
    if isinstance(data, dict) and "pagination" in data:
        paginacao = data["pagination"] or {}
        total_entradas = paginacao.get("total_entries")
        if total_entradas is not None and int(total_entradas) != len(resultados):
            raise SystemExit(
                f"{caminho.name}: a paginacao diz {total_entradas} "
                f"registros, mas o arquivo tem {len(resultados)}."
            )
        if paginacao.get("next_page") or (paginacao.get("links") or {}).get("next"):
            raise SystemExit(
                f"{caminho.name}: ainda ha pagina seguinte. "
                "Nao tratar arquivo incompleto."
            )
    return len(resultados)


def extrair_resultado(texto: str | None) -> str | None:
    if not texto:
        return None
    achado = RESULTADO_VOTACAO.search(texto.strip())
    if not achado:
        return None
    token = achado.group(1).upper()
    if token.startswith("REJEITAD"):
        return "REJEITADO"
    return token


def situacao_oficial(resultado: str | None) -> str | None:
    if resultado in APROVADOS:
        return "Aprovado"
    if resultado in REJEITADOS:
        return "Rejeitado"
    return None


def situacao_da_votacao_escolhida(escolhida: dict) -> str:
    """Frase fora do mapa vira rotulo fixo. O texto oficial permanece no registro."""
    oficial = escolhida.get("situacao_oficial_sapl")
    if oficial:
        return str(oficial)
    frase = str(escolhida.get("frase_resultado_sapl") or "").strip()
    texto = str(escolhida.get("texto_registro_sapl") or "").strip()
    if frase or texto:
        return SITUACAO_NAO_MAPEADA
    raise SystemExit(
        f"Votacao {escolhida.get('id')} sem frase de resultado no SAPL."
    )


def aplicar_aviso_na_votacao(
    votacao: dict, id_sapl: int, voto_texto: str | None, extra: dict
) -> dict:
    """Guarda o conflito na votacao e tira o aviso do estado individual."""
    aviso = extra.get("aviso")
    resto = {chave: valor for chave, valor in extra.items() if chave != "aviso"}
    if aviso:
        votacao.setdefault("avisos", []).append(
            {
                "aviso": aviso,
                "id_sapl": id_sapl,
                "voto_texto_sapl": voto_texto,
            }
        )
    return resto


def situacao_por_nome(nome) -> str | None:
    """Situacao oficial pelo nome da tabela de tipos do SAPL."""
    texto = str(nome or "").strip()
    if texto.startswith("Aprovada"):
        return "Aprovado"
    if texto.startswith("Rejeit"):
        return "Rejeitado"
    return None


def deliberativa_nome(nome) -> bool:
    return situacao_por_nome(nome) is not None


def carregar_tipos_resultado() -> dict[int, str]:
    """Nome oficial de cada tipo de resultado, lido da tabela ja baixada."""
    achados = []
    for pasta in sorted(DIR_BRUTOS.glob("lote_*")):
        if not pasta.is_dir():
            continue
        for caminho in sorted(pasta.glob("tiporesultadovotacao_p*.json")):
            achados.append(caminho)
    if not achados:
        raise SystemExit("Tabela tiporesultadovotacao nao encontrada em dados/brutos.")
    caminho = achados[-1]
    dados = carregar_json(caminho)
    saida = {}
    for item in dados.get("results") or []:
        if isinstance(item, dict) and item.get("id") is not None:
            saida[int(item["id"])] = str(item.get("nome") or "").strip()
    return saida


def carregar_catalogo_tipos_materia() -> tuple[dict[str, str], str]:
    """Sigla e descricao oficiais de cada tipo de materia, lidas do SAPL.

    Fonte: dados/brutos/lote_*/tipomaterialegislativa_p*.json (tabela
    tipomaterialegislativa do SAPL). Sem dicionario fixo no codigo.
    """
    achados = []
    for pasta in sorted(DIR_BRUTOS.glob("lote_*")):
        if not pasta.is_dir():
            continue
        for caminho in sorted(pasta.glob("tipomaterialegislativa_p*.json")):
            achados.append(caminho)
    if not achados:
        raise SystemExit("Tabela tipomaterialegislativa nao encontrada em dados/brutos.")
    caminho = achados[-1]
    dados = carregar_json(caminho)
    saida: dict[str, str] = {}
    for item in dados.get("results") or []:
        if not isinstance(item, dict):
            continue
        sigla = str(item.get("sigla") or "").strip()
        descricao = str(item.get("descricao") or "").strip()
        if not sigla or not descricao:
            continue
        if sigla in saida and saida[sigla] != descricao:
            raise SystemExit(f"Tipo {sigla} com descricoes diferentes no SAPL.")
        saida[sigla] = descricao
    if not saida:
        raise SystemExit("Tabela tipomaterialegislativa sem sigla e descricao.")
    return saida, rel(caminho)


def carregar_tipos_justificativa() -> tuple[dict[int, str], str]:
    """Descricao oficial de cada tipo de justificativa de ausencia do SAPL."""
    achados = []
    for pasta in sorted(DIR_BRUTOS.glob("lote_*")):
        if not pasta.is_dir():
            continue
        for caminho in sorted(pasta.glob("tipojustificativa_p*.json")):
            achados.append(caminho)
    if not achados:
        return {}, ""
    caminho = achados[-1]
    dados = carregar_json(caminho)
    saida: dict[int, str] = {}
    for item in dados.get("results") or []:
        if isinstance(item, dict) and item.get("id") is not None:
            descricao = str(item.get("descricao") or item.get("__str__") or "").strip()
            if descricao:
                saida[int(item["id"])] = descricao
    return saida, rel(caminho)


def carregar_justificativas_detalhe() -> dict[tuple[int, int], list[dict]]:
    """Detalhe de cada justificativa por (sessao_id, parlamentar_id).

    Guarda tipo_ausencia, descricao oficial, observacao e anexo, para
    mostrar o motivo na lista de faltas com justificativa.
    """
    tipos, _fonte_tipos = carregar_tipos_justificativa()
    global TIPOS_JUSTIFICATIVA_SAPL
    TIPOS_JUSTIFICATIVA_SAPL = tipos
    saida: dict[tuple[int, int], list[dict]] = {}
    for caminho in sorted(DIR_BRUTOS.glob("sessao_*_justificativaausencia.json")):
        try:
            dados = carregar_json(caminho)
        except (OSError, ValueError):
            continue
        for linha in resultados_de_lista(dados):
            if not isinstance(linha, dict):
                continue
            sessao = linha.get("sessao_plenaria")
            parlamentar = linha.get("parlamentar")
            if sessao is None or parlamentar is None:
                continue
            tipo_id = linha.get("tipo_ausencia")
            tipo_id_int = int(tipo_id) if tipo_id is not None else None
            descricao = tipos.get(tipo_id_int) if tipo_id_int is not None else None
            if not descricao:
                descricao = str(linha.get("__str__") or "").strip() or None
            chave = (int(sessao), int(parlamentar))
            saida.setdefault(chave, []).append(
                {
                    "tipo_ausencia": tipo_id_int,
                    "descricao": descricao,
                    "observacao": str(linha.get("observacao") or "").strip() or None,
                    "upload_anexo": linha.get("upload_anexo"),
                    "justificativa_id": linha.get("id"),
                }
            )
    return saida


def resultado_rejeitado(voto: dict) -> bool:
    if str(voto.get("situacao_oficial_sapl") or "").strip() == "Rejeitado":
        return True
    return (str(voto.get("resultado_texto_sapl") or "").strip().upper().startswith("REJEIT"))


def atribuir_turnos(tipo_sigla, votos: list[dict], dois_turnos: set) -> list[str]:
    """Turno de cada votacao, na mesma ordem da lista.

    Tipo fora dos dois turnos segue turno unico. Nos dois turnos, o grupo
    da primeira data e o 1o turno e o da segunda data e o 2o turno. Data
    repetida no mesmo dia segue o turno do dia. Terceira data em diante,
    e voto depois de rejeicao no 1o turno, ficam como turno nao
    identificado. Tipo ausente tambem segue turno unico.
    """
    if tipo_sigla not in dois_turnos:
        return [TURNO_UNICO] * len(votos)
    if not votos:
        return []
    ordem = sorted(
        range(len(votos)),
        key=lambda i: (
            votos[i].get("data_sessao") or "",
            votos[i].get("sessao_id") or 0,
            votos[i].get("id") or votos[i].get("registro_votacao_id") or 0,
        ),
    )
    grupos: dict[str, list[int]] = {}
    for i in ordem:
        chave = votos[i].get("data_sessao") or f"sessao:{votos[i].get('sessao_id') or 0}"
        grupos.setdefault(chave, []).append(i)
    datas = [grupos[chave] for chave in sorted(grupos)]
    turnos = [TURNO_NAO_IDENTIFICADO] * len(votos)
    for i in datas[0]:
        turnos[i] = TURNO_PRIMEIRO
    if len(datas) >= 2:
        rejeitado_no_primeiro = any(resultado_rejeitado(votos[i]) for i in datas[0])
        for i in datas[1]:
            turnos[i] = TURNO_SEGUNDO if not rejeitado_no_primeiro else TURNO_NAO_IDENTIFICADO
    return turnos


def escolher_por_turno(pares: list) -> tuple:
    """Escolhe o registro que define a situacao nos dois turnos.

    pares: [(registro, turno)] em ordem cronologica. Retorna
    (registro, em_tramitacao). Rejeitado no 1o encerra como rejeitado.
    Com 2o turno, o 2o decide. So com 1o aprovado, segue em tramitacao.
    """
    rejeitados = [
        registro
        for registro, turno in pares
        if turno == TURNO_PRIMEIRO and resultado_rejeitado(registro)
    ]
    if rejeitados:
        return rejeitados[0], False
    segundos = [registro for registro, turno in pares if turno == TURNO_SEGUNDO]
    if segundos:
        return escolher_votacao(segundos), False
    primeiros = [registro for registro, turno in pares if turno == TURNO_PRIMEIRO]
    if primeiros:
        return escolher_votacao(primeiros), True
    return None, True


def frase_apos_votacao(texto: str | None) -> str | None:
    if not texto:
        return None
    for marca in ("Votação:", "Votacao:"):
        if marca in texto:
            frase = texto.split(marca, 1)[1].strip()
            return frase or None
    return None


def percentual(parte: int, total: int) -> float:
    if total == 0:
        raise SystemExit("Nao da para calcular porcentagem com total zero.")
    return round(parte * 100 / total, 2)


def inteiro_ou_nulo(valor):
    if valor is None or valor == "":
        return None
    return int(valor)


def data_da_coleta(ano: int) -> tuple[str, str]:
    resumo = DIR_BRUTOS / f"_resumo_coleta_vereadores_{ano}.json"
    if resumo.exists():
        dados = carregar_json(resumo)
        fim = dados.get("fim") if isinstance(dados, dict) else None
        if isinstance(fim, str) and fim.strip():
            return fim.strip(), rel(resumo) + " campo fim"
    achados = []
    for caminho in sorted(DIR_BRUTOS.rglob("indice.json")):
        dados = carregar_json(caminho)
        if not isinstance(dados, dict):
            continue
        marca = dados.get("atualizado_em")
        if isinstance(marca, str) and marca.strip():
            achados.append((marca.strip(), rel(caminho)))
    if not achados:
        raise SystemExit(
            "Nenhuma data de coleta encontrada nos indices de dados/brutos."
        )
    achados.sort()
    marca, origem = achados[-1]
    return marca, origem + " campo atualizado_em"


def dentro_do_mandato(vereador: dict, data: str) -> bool:
    mandatos = vereador.get("mandatos") or []
    if not mandatos:
        raise SystemExit(
            f"Vereador {vereador.get('id_sapl')} sem lista de mandatos."
        )
    for mandato in mandatos:
        inicio = mandato.get("data_inicio_mandato")
        fim = mandato.get("data_fim_mandato") or "9999-12-31"
        if not inicio:
            raise SystemExit(
                f"Vereador {vereador.get('id_sapl')} com mandato sem data de inicio."
            )
        if str(inicio) <= data <= str(fim):
            return True
    return False


def filtrar_banca(tabela: dict, ano: int, piso: int) -> list[dict]:
    banca = [
        item
        for item in tabela["vereadores"]
        if ano in (item.get("anos_com_mandato") or [])
    ]
    if len(banca) != piso:
        raise SystemExit(
            f"{ano}: a banca filtrada por anos_com_mandato tem {len(banca)} "
            f"vereadores. O piso exato deste ano e {piso}."
        )
    return banca


def arquivo_sessao(sessao_id: int, sufixo: str) -> Path:
    return DIR_BRUTOS / f"sessao_{sessao_id}_{sufixo}.json"


def ids_parlamentares(caminho: Path) -> set[int]:
    if not caminho.exists():
        raise SystemExit(f"Arquivo nao encontrado: {caminho.name}")
    dados = carregar_json(caminho)
    conferir_total(caminho, dados)
    ids = set()
    for linha in resultados_de_lista(dados):
        parlamentar = linha.get("parlamentar")
        if parlamentar is None:
            raise SystemExit(f"{caminho.name}: registro sem parlamentar.")
        ids.add(int(parlamentar))
    return ids


def carregar_sessoes(ano: int, piso: int) -> tuple[list[dict], dict, dict]:
    caminho = DIR_BRUTOS / f"contagem_votacoes_ordinarias_{ano}.json"
    if not caminho.exists():
        raise SystemExit(f"Arquivo nao encontrado: {rel(caminho)}")
    contagem = carregar_json(caminho)
    brutas = contagem.get("sessoes") or []
    if len(brutas) < piso:
        raise SystemExit(
            f"{ano}: a contagem lista {len(brutas)} sessoes ordinarias. "
            f"O piso minimo e {piso}."
        )
    sessoes = []
    for item in brutas:
        sessoes.append(
            {
                "id": int(item["id"]),
                "numero": item.get("numero"),
                "data": item["data"],
                "rotulo": item["rotulo"],
                "n_votacoes_contagem": int(item["n_votacoes"]),
                "link_sapl": link_sessao(int(item["id"]), CONFIG),
            }
        )
    lacuna = contagem.get("lacuna_sessoes_ordinarias")
    if not isinstance(lacuna, dict):
        raise SystemExit(
            f"{ano}: contagem sem o campo lacuna_sessoes_ordinarias."
        )
    return sessoes, lacuna, contagem


def carregar_presidentes(ano: int) -> dict[int, int]:
    if not ARQUIVO_PRESIDENCIA.exists():
        raise SystemExit(f"Arquivo nao encontrado: {rel(ARQUIVO_PRESIDENCIA)}")
    dados = carregar_json(ARQUIVO_PRESIDENCIA)
    bloco = (dados.get("por_ano") or {}).get(str(ano))
    if not isinstance(bloco, dict):
        raise SystemExit(f"{ano}: presidencia_sessoes.json sem bloco deste ano.")
    mapa = {}
    for item in bloco.get("sessoes") or []:
        sessao_id = int(item["sessao_id"])
        if item.get("lacuna") or item.get("presidente_id_sapl") is None:
            raise SystemExit(
                f"Sessao {sessao_id}: presidencia sem presidente registrado. "
                "Nao vou presumir quem presidia."
            )
        mapa[sessao_id] = int(item["presidente_id_sapl"])
    return mapa


def carregar_autoria() -> dict[int, dict]:
    if not ARQUIVO_AUTORIA.exists():
        raise SystemExit(f"Arquivo nao encontrado: {rel(ARQUIVO_AUTORIA)}")
    dados = carregar_json(ARQUIVO_AUTORIA)
    indice = {}
    for materia in dados.get("materias") or []:
        indice[int(materia["materia_id"])] = materia
    return indice


def carregar_tipos_materia(ano: int) -> dict[int, str | None]:
    """Sigla do tipo de cada materia do ano, para a regra de turnos."""
    caminho = DIR_BRUTOS / f"materias-{ano}-resposta-original.csv"
    if not caminho.exists():
        raise SystemExit(f"Arquivo nao encontrado: {rel(caminho)}")
    tipos: dict[int, str | None] = {}
    with caminho.open(encoding="utf-8-sig", newline="") as handle:
        leitor = csv.DictReader(handle, delimiter=";")
        for linha in leitor:
            sigla = (linha.get("Tipo de Matéria Legislativa/Sigla") or "").strip() or None
            tipos[int(linha["ID"])] = sigla
    return tipos


def autores_da_materia(materia_id, indice: dict[int, dict], por_id: dict[int, dict]):
    if materia_id is None:
        return None
    materia = indice.get(int(materia_id))
    if materia is None:
        raise SystemExit(
            f"Materia {materia_id} ausente em {rel(ARQUIVO_AUTORIA)}. "
            "Autoria nao sera inventada."
        )
    autores = []
    for autoria in materia.get("autorias") or []:
        bruto = autoria.get("parlamentar_id_sapl")
        parlamentar_id = int(bruto) if bruto is not None else None
        item = {
            "ordem_no_sapl": autoria.get("ordem_no_sapl"),
            "autor_id": autoria.get("autor_id"),
            "tipo_autor": autoria.get("tipo_autor") or "sem autor registrado no SAPL",
            "parlamentar_id_sapl": parlamentar_id,
            "nome_no_sapl": autoria.get("nome_no_sapl") or "",
            "cargo_no_sapl": autoria.get("cargo_no_sapl"),
            "lacuna": autoria.get("lacuna"),
        }
        if parlamentar_id is not None and parlamentar_id in por_id:
            pessoa = por_id[parlamentar_id]
            item["nome_parlamentar"] = pessoa["nome_parlamentar"]
            item["slug_codigo"] = pessoa["slug_codigo"]
        autores.append(item)
    if not autores:
        return {
            "rotulo": "sem autor registrado no SAPL",
            "autores": [],
            "autoria_conjunta": False,
            "link_sapl": link_materia(int(materia_id), CONFIG),
        }
    return {
        "rotulo": None,
        "autores": autores,
        "autoria_conjunta": len(autores) > 1,
        "link_sapl": link_materia(int(materia_id), CONFIG),
    }


def _exigir_data(valor, onde: str) -> str:
    if not isinstance(valor, str) or len(valor) != 10 or valor[4] != "-" or valor[7] != "-":
        raise SystemExit(f"{onde}: data invalida. Nada sera estimado.")
    return valor


def carregar_afastamentos() -> dict:
    vazio = {"afastamentos": [], "motivos_fora_do_mandato": [], "notas": []}
    if not ARQUIVO_AFASTAMENTOS.exists():
        return vazio
    dados = carregar_json(ARQUIVO_AFASTAMENTOS)
    if not isinstance(dados, dict):
        raise SystemExit(f"{rel(ARQUIVO_AFASTAMENTOS)} nao e um objeto.")
    for chave in vazio:
        if chave not in dados or not isinstance(dados[chave], list):
            raise SystemExit(f"{rel(ARQUIVO_AFASTAMENTOS)} sem lista {chave}.")
    for item in dados["afastamentos"]:
        _exigir_data(item.get("data_inicio"), "afastamento data_inicio")
        _exigir_data(item.get("data_fim"), "afastamento data_fim")
        if item["data_inicio"] > item["data_fim"]:
            raise SystemExit("Afastamento com data inicial depois da final.")
        if not str(item.get("tipo") or "").strip():
            raise SystemExit("Afastamento sem tipo.")
        if not str(item.get("rotulo") or "").strip():
            raise SystemExit("Afastamento sem rotulo.")
        if "parlamentar_id_sapl" not in item:
            raise SystemExit("Afastamento sem parlamentar_id_sapl.")
        if "conta_como_falta" not in item:
            raise SystemExit("Afastamento sem conta_como_falta.")
        if "fonte_oficial_encontrada" not in item:
            raise SystemExit("Afastamento sem fonte_oficial_encontrada.")
        if not str(item.get("fonte") or "").strip():
            raise SystemExit("Afastamento sem texto de fonte.")
    for item in dados["motivos_fora_do_mandato"]:
        _exigir_data(item.get("depois_de"), "motivo fora do mandato")
        if not str(item.get("motivo") or "").strip():
            raise SystemExit("Motivo de fora do mandato vazio.")
        if "parlamentar_id_sapl" not in item:
            raise SystemExit("Motivo de fora do mandato sem parlamentar_id_sapl.")
    for item in dados["notas"]:
        if "parlamentar_id_sapl" not in item or not str(item.get("texto") or "").strip():
            raise SystemExit("Nota factual incompleta.")
    return dados


def registrar_tipos_afastamento(afastamentos: list[dict]) -> None:
    """Valida afastamentos manuais. D-050: licenca conta como falta com justificativa.

    Nao cria estado proprio. A licenca entra na contagem de faltas com
    justificativa, com o motivo guardado na sessao. A formula da taxa
    (D-046) nao muda: presente dividido pelo total no mandato.
    """
    for item in afastamentos:
        if item.get("conta_como_falta"):
            continue
        tipo = str(item["tipo"])
        rotulo = str(item["rotulo"])
        if not tipo.strip() or not rotulo.strip():
            raise SystemExit("Afastamento sem tipo ou rotulo.")
    LICENCA_TIPOS.clear()


def afastamento_na_data(afastamentos: list[dict], parlamentar_id: int, data: str):
    achados = [
        item
        for item in afastamentos
        if int(item["parlamentar_id_sapl"]) == parlamentar_id
        and item["data_inicio"] <= data <= item["data_fim"]
    ]
    if len(achados) > 1:
        raise SystemExit(
            f"Mais de um afastamento para o parlamentar {parlamentar_id} em {data}."
        )
    return achados[0] if achados else None


def motivo_fora_na_data(motivos: list[dict], parlamentar_id: int, data: str):
    achados = [
        item
        for item in motivos
        if int(item["parlamentar_id_sapl"]) == parlamentar_id and data > item["depois_de"]
    ]
    if len(achados) > 1:
        raise SystemExit(
            f"Mais de um motivo de fora do mandato para {parlamentar_id} em {data}."
        )
    return achados[0] if achados else None


def fonte_da_ocorrencia(item: dict) -> dict:
    materia_id = item.get("materia_id")
    link = item.get("link_fonte")
    if not link and materia_id is not None:
        link = link_materia(int(materia_id), CONFIG)
    saida = {
        "fonte": item.get("fonte") or "",
        "link_fonte": link,
        "fonte_oficial_encontrada": bool(item.get("fonte_oficial_encontrada")),
    }
    if item.get("trecho"):
        saida["trecho"] = item["trecho"]
    if item.get("arquivo"):
        saida["arquivo"] = item["arquivo"]
    return saida


def afastamentos_publicos(lista: list[dict], parlamentar_id: int) -> list[dict]:
    saida = []
    for item in lista:
        if int(item["parlamentar_id_sapl"]) != parlamentar_id:
            continue
        publico = fonte_da_ocorrencia(item)
        publico["tipo"] = item["tipo"]
        publico["rotulo"] = item["rotulo"]
        publico["data_inicio"] = item["data_inicio"]
        publico["data_fim"] = item["data_fim"]
        publico["conta_como_falta"] = bool(item["conta_como_falta"])
        consulta = []
        for ata in item.get("consulta_atas") or []:
            materia_ata = ata.get("materia_id")
            consulta.append(
                {
                    "materia_id": materia_ata,
                    "link_fonte": (
                        link_materia(int(materia_ata), CONFIG)
                        if materia_ata is not None
                        else None
                    ),
                    "registra_licenca": bool(ata.get("registra_licenca")),
                    "registra": ata.get("registra") or "",
                    "trecho": ata.get("trecho"),
                    "arquivo": ata.get("arquivo"),
                }
            )
        publico["consulta_atas"] = consulta
        saida.append(publico)
    return saida


def complemento_fora(motivo: dict | None) -> dict:
    if not motivo:
        return {}
    materia_id = motivo.get("materia_id")
    return {
        "motivo": motivo["motivo"],
        "materia_motivo_id": int(materia_id) if materia_id is not None else None,
        "link_motivo": (
            link_materia(int(materia_id), CONFIG) if materia_id is not None else None
        ),
        "fonte_oficial_encontrada": bool(motivo.get("fonte_oficial_encontrada")),
    }


def notas_publicas(notas: list[dict]) -> dict[int, dict]:
    saida = {}
    for nota in notas:
        fontes = []
        for fonte in nota.get("fontes") or []:
            materia_id = fonte.get("materia_id")
            link = fonte.get("link_fonte")
            if not link and materia_id is not None:
                link = link_materia(int(materia_id), CONFIG)
            fontes.append(
                {
                    "fonte": fonte.get("fonte") or "",
                    "link_fonte": link,
                    "fonte_oficial_encontrada": bool(fonte.get("fonte_oficial_encontrada")),
                    "materia_id": int(materia_id) if materia_id is not None else None,
                    "trecho": fonte.get("trecho"),
                }
            )
        parlamentar_id = int(nota["parlamentar_id_sapl"])
        if parlamentar_id in saida:
            raise SystemExit(f"Mais de uma nota para o parlamentar {parlamentar_id}.")
        saida[parlamentar_id] = {"texto": nota["texto"], "fontes": fontes}
    return saida


def rotulo_da_situacao(situacao: str) -> str:
    if situacao == "fora_do_mandato":
        return "Fora do mandato naquela data"
    if situacao == "presente":
        return "Presente"
    if situacao == "falta_com_justificativa":
        return "Falta com justificativa"
    if situacao == "falta_sem_justificativa":
        return "Falta sem justificativa"
    if situacao in ROTULOS_ESTADO:
        return ROTULOS_ESTADO[situacao]
    raise SystemExit(f"Situacao de presenca desconhecida: {situacao}")


def estado_do_texto(voto: str, era_presidente: bool) -> str:
    if voto in VOTOS_SIM:
        return "sim"
    if voto in VOTOS_NAO:
        return "nao"
    if voto in VOTOS_ABSTENCAO:
        return "abstencao"
    if voto in VOTOS_NAO_VOTOU:
        if era_presidente:
            return "presidente_que_nao_votou"
        return "nao_votou"
    raise SystemExit(
        f"Texto de voto nao previsto: {voto!r}. "
        "Nao vou criar um rotulo para esconder o registro."
    )


def carregar_votos_da_sessao(sessao_id: int, registros: dict[int, dict]) -> dict[int, dict[int, str]]:
    caminho = arquivo_sessao(sessao_id, "votoparlamentar")
    dados = carregar_json(caminho)
    conferir_total(caminho, dados)
    por_votacao: dict[int, dict[int, str]] = defaultdict(dict)
    for linha in resultados_de_lista(dados):
        parlamentar = linha.get("parlamentar")
        if parlamentar is None:
            raise SystemExit(f"{caminho.name}: voto sem parlamentar.")
        voto = linha.get("voto")
        if voto is None or str(voto).strip() == "":
            raise SystemExit(
                f"{caminho.name}: voto sem valor para parlamentar {parlamentar}."
            )
        votacao_id = linha.get("votacao")
        if votacao_id is None:
            raise SystemExit(
                f"{caminho.name}: voto do parlamentar {parlamentar} sem votacao."
            )
        votacao_id = int(votacao_id)
        if votacao_id not in registros:
            raise SystemExit(
                f"{caminho.name}: votacao {votacao_id} nao esta no "
                "registrovotacao desta sessao."
            )
        por_votacao[votacao_id][int(parlamentar)] = str(voto)
    return por_votacao


def carregar_registros(sessao: dict, tipos_resultado: dict[int, str]) -> dict[int, dict]:
    caminho = arquivo_sessao(sessao["id"], "registrovotacao")
    dados = carregar_json(caminho)
    conferir_total(caminho, dados)
    registros = {}
    for linha in resultados_de_lista(dados):
        registro_id = int(linha["id"])
        materia = linha.get("materia")
        materia_id = int(materia) if materia is not None else None
        texto = linha.get("__str__") or ""
        resultado = extrair_resultado(texto)
        frase = frase_apos_votacao(texto)
        tipo_id = linha.get("tipo_resultado_votacao")
        tipo_id = int(tipo_id) if tipo_id is not None else None
        tipo_nome = tipos_resultado.get(tipo_id) if tipo_id is not None else None
        oficial = situacao_por_nome(tipo_nome)
        if oficial is None:
            oficial = situacao_oficial(resultado)
        item = {
            "id": registro_id,
            "sessao_id": sessao["id"],
            "data_sessao": sessao["data"],
            "rotulo_sessao": sessao["rotulo"],
            "materia_id": materia_id,
            "ordem": linha.get("ordem"),
            "data_hora": linha.get("data_hora") or "",
            "texto_registro_sapl": texto,
            "resultado_texto_sapl": resultado,
            "frase_resultado_sapl": frase,
            "situacao_oficial_sapl": oficial,
            "tipo_resultado_votacao_id": tipo_id,
            "tipo_resultado_nome": tipo_nome,
            "deliberativa": (
                deliberativa_nome(tipo_nome)
                if tipo_nome
                else oficial is not None
            ),
            "numero_votos_sim": inteiro_ou_nulo(linha.get("numero_votos_sim")),
            "numero_votos_nao": inteiro_ou_nulo(linha.get("numero_votos_nao")),
            "numero_abstencoes": inteiro_ou_nulo(linha.get("numero_abstencoes")),
            "link_sessao": sessao["link_sapl"],
            "link_materia": (
                link_materia(materia_id, CONFIG) if materia_id is not None else None
            ),
        }
        registros[registro_id] = item
    return registros


def motivo_afastamento_manual(afastamento: dict | None) -> dict | None:
    if not afastamento:
        return None
    fonte = fonte_da_ocorrencia(afastamento)
    return {
        "origem": "afastamento_manual",
        "tipo": afastamento.get("tipo"),
        "motivo": str(afastamento.get("rotulo") or "").strip(),
        "fonte": fonte.get("fonte") or "",
        "link_fonte": fonte.get("link_fonte"),
        "fonte_oficial_encontrada": bool(fonte.get("fonte_oficial_encontrada")),
    }


def motivo_justificativa_sapl(
    detalhe: dict | None, link_sessao: str | None
) -> dict | None:
    if not detalhe:
        return None
    motivo = str(detalhe.get("descricao") or "").strip() or "Justificativa registrada no SAPL"
    return {
        "origem": "sapl_justificativaausencia",
        "tipo_ausencia": detalhe.get("tipo_ausencia"),
        "motivo": motivo,
        "observacao": detalhe.get("observacao"),
        "upload_anexo": detalhe.get("upload_anexo"),
        "link_sessao": link_sessao,
    }


def estado_na_votacao(
    vereador: dict,
    data: str,
    voto_texto: str | None,
    presidente_id: int,
    presente: bool,
    justificado: bool,
    afastamento: dict | None,
    motivo: dict | None,
) -> tuple[str, str | None, dict]:
    if afastamento is not None and voto_texto is None:
        return "ausente_com_justificativa", None, fonte_da_ocorrencia(afastamento)
    if not dentro_do_mandato(vereador, data):
        return "fora_do_mandato", voto_texto, complemento_fora(motivo)
    if voto_texto is not None:
        era_presidente = int(vereador["id_sapl"]) == presidente_id
        extra = {}
        if afastamento is not None:
            extra["aviso"] = AVISO_CONFLITO_AFASTAMENTO
        return estado_do_texto(voto_texto, era_presidente), voto_texto, extra
    if not presente and justificado:
        return "ausente_com_justificativa", None, {}
    if not presente and not justificado:
        return "ausente_sem_justificativa", None, {}
    return "presente_sem_voto_individual_registrado", None, {}


def processar_sessoes(
    ano: int,
    banca: list[dict],
    sessoes: list[dict],
    presidentes: dict[int, int],
    indice_autoria: dict[int, dict],
    por_id: dict[int, dict],
    rotulo_sem_voto: str,
    afastamentos: list[dict],
    motivos_fora: list[dict],
    tipos_materia: dict[int, str | None],
    tipos_resultado: dict[int, str],
    justificativas_detalhe: dict | None = None,
) -> dict:
    ids_banca = {int(item["id_sapl"]) for item in banca}
    por_banca = {int(item["id_sapl"]): item for item in banca}
    presenca = {id_sapl: [] for id_sapl in ids_banca}
    fora_mandato = {id_sapl: 0 for id_sapl in ids_banca}
    nominais = {id_sapl: [] for id_sapl in ids_banca}
    registros_por_materia: dict[int, list[dict]] = defaultdict(list)
    sessoes_saida = []
    votacoes = []
    divergencias = []
    presentes_e_justificados = []
    n_com = 0
    n_sem = 0

    registros_por_sessao_id: dict[int, dict[int, dict]] = {}
    grupos_por_materia: dict[int | None, list[dict]] = defaultdict(list)
    for sessao in sessoes:
        pacote = carregar_registros(sessao, tipos_resultado)
        registros_por_sessao_id[int(sessao["id"])] = pacote
        for registro in pacote.values():
            materia = registro.get("materia_id")
            grupos_por_materia[materia].append(registro)
    turnos_por_registro: dict[tuple, str | None] = {}
    for materia_id, lista in grupos_por_materia.items():
        tipo = tipos_materia.get(int(materia_id)) if materia_id is not None else None
        deliberativos = [r for r in lista if r.get("deliberativa")]
        turnos = atribuir_turnos(tipo, deliberativos, DOIS_TURNOS)
        for registro, turno in zip(deliberativos, turnos):
            turnos_por_registro[(materia_id, int(registro["id"]))] = turno
        for registro in lista:
            if not registro.get("deliberativa"):
                turnos_por_registro[(materia_id, int(registro["id"]))] = None

    for sessao in sessoes:
        for sufixo in PACOTE_SESSAO:
            caminho = arquivo_sessao(sessao["id"], sufixo)
            if not caminho.exists():
                raise SystemExit(f"Falta o arquivo {caminho.name}.")
        if sessao["id"] not in presidentes:
            raise SystemExit(
                f"Sessao {sessao['id']} ausente em presidencia_sessoes.json."
            )
        presidente_id = presidentes[sessao["id"]]
        if presidente_id not in ids_banca:
            raise SystemExit(
                f"Sessao {sessao['id']}: presidente {presidente_id} "
                f"nao esta na banca de {ano}."
            )

        plenaria = ids_parlamentares(
            arquivo_sessao(sessao["id"], "sessaoplenariapresenca")
        )
        ordem = ids_parlamentares(arquivo_sessao(sessao["id"], "presencaordemdia"))
        justificados = ids_parlamentares(
            arquivo_sessao(sessao["id"], "justificativaausencia")
        )
        presentes = plenaria | ordem
        if plenaria != ordem:
            divergencias.append(
                {
                    "sessao_id": sessao["id"],
                    "so_plenaria": sorted(plenaria - ordem),
                    "so_ordem_dia": sorted(ordem - plenaria),
                }
            )

        fora_da_banca = sorted((presentes | justificados) - ids_banca)
        if fora_da_banca:
            raise SystemExit(
                f"Sessao {sessao['id']}: parlamentar fora da banca de {ano}: "
                f"{fora_da_banca}."
            )

        situacoes = {}
        for vereador in banca:
            id_sapl = int(vereador["id_sapl"])
            no_mandato = dentro_do_mandato(vereador, sessao["data"])
            if not no_mandato:
                fora_mandato[id_sapl] += 1
                situacoes[id_sapl] = "fora_do_mandato"
                continue
            afastamento = afastamento_na_data(afastamentos, id_sapl, sessao["data"])
            detalhe_just = None
            if justificativas_detalhe is not None:
                lista_just = justificativas_detalhe.get((int(sessao["id"]), id_sapl)) or []
                detalhe_just = lista_just[0] if lista_just else None
            if afastamento is not None:
                situacao = "falta_com_justificativa"
            elif id_sapl in presentes:
                situacao = "presente"
            elif id_sapl in justificados:
                situacao = "falta_com_justificativa"
            else:
                situacao = "falta_sem_justificativa"
            if no_mandato and id_sapl in presentes and id_sapl in justificados:
                presentes_e_justificados.append(
                    {"sessao_id": sessao["id"], "id_sapl": id_sapl}
                )
            registro = {
                "sessao_id": sessao["id"],
                "data_sessao": sessao["data"],
                "rotulo": sessao["rotulo"],
                "situacao": situacao,
                "rotulo_situacao": rotulo_da_situacao(situacao),
                "presente_sessao_plenaria": id_sapl in plenaria,
                "presente_ordem_dia": id_sapl in ordem,
                "justificativa": id_sapl in justificados,
                "era_presidente": id_sapl == presidente_id,
                "link_sessao": sessao["link_sapl"],
            }
            if afastamento is not None:
                registro.update(fonte_da_ocorrencia(afastamento))
                registro["motivo_ausencia"] = motivo_afastamento_manual(afastamento)
            elif situacao == "falta_com_justificativa":
                motivo_sapl = motivo_justificativa_sapl(detalhe_just, sessao["link_sapl"])
                if motivo_sapl is not None:
                    registro["motivo_ausencia"] = motivo_sapl
            presenca[id_sapl].append(registro)
            situacoes[id_sapl] = situacao

        registros = registros_por_sessao_id[int(sessao["id"])]
        if len(registros) != sessao["n_votacoes_contagem"]:
            raise SystemExit(
                f"Sessao {sessao['id']}: a contagem diz "
                f"{sessao['n_votacoes_contagem']} votacoes e o arquivo tem "
                f"{len(registros)}."
            )
        votos = carregar_votos_da_sessao(sessao["id"], registros)
        for registro in registros.values():
            materia_id = registro["materia_id"]
            if materia_id is not None:
                registros_por_materia[materia_id].append(registro)
            linhas = votos.get(registro["id"]) or {}
            fora = sorted(set(linhas) - ids_banca)
            if fora:
                raise SystemExit(
                    f"Sessao {sessao['id']}, votacao {registro['id']}: "
                    f"voto de parlamentar fora da banca de {ano}: {fora}."
                )
            autoria = autores_da_materia(materia_id, indice_autoria, por_id)
            turno = turnos_por_registro.get((materia_id, int(registro["id"])))
            if turno is None and registro.get("deliberativa"):
                raise SystemExit(
                    f"Sessao {sessao['id']}, votacao {registro['id']}: "
                    "votacao deliberativa sem turno."
                )
            base = {
                "id": registro["id"],
                "sessao_id": sessao["id"],
                "numero_sessao": sessao["numero"],
                "data_sessao": sessao["data"],
                "rotulo_sessao": sessao["rotulo"],
                "materia_id": materia_id,
                "ordem": registro["ordem"],
                "data_hora": registro["data_hora"],
                "texto_registro_sapl": registro["texto_registro_sapl"],
                "resultado_texto_sapl": registro["resultado_texto_sapl"],
                "frase_resultado_sapl": registro["frase_resultado_sapl"],
                "situacao_oficial_sapl": registro["situacao_oficial_sapl"],
                "turno": turno,
                "tipo_resultado_nome": registro.get("tipo_resultado_nome"),
                "totais_oficiais": {
                    "numero_votos_sim": registro["numero_votos_sim"],
                    "numero_votos_nao": registro["numero_votos_nao"],
                    "numero_abstencoes": registro["numero_abstencoes"],
                },
                "link_sessao": registro["link_sessao"],
                "link_materia": registro["link_materia"],
                "autoria": autoria,
                "presidente_id_sapl": presidente_id,
            }
            if not linhas:
                n_sem += 1
                base.update(
                    {
                        "voto_individual_registrado": False,
                        "rotulo": rotulo_sem_voto,
                        "estados_por_vereador": None,
                        "conclusao_do_painel": None,
                    }
                )
                votacoes.append(base)
                continue

            n_com += 1
            estados = []
            for vereador in banca:
                id_sapl = int(vereador["id_sapl"])
                texto = linhas.get(id_sapl)
                no_mandato = dentro_do_mandato(vereador, sessao["data"])
                afastamento = afastamento_na_data(
                    afastamentos, id_sapl, sessao["data"]
                )
                motivo = motivo_fora_na_data(motivos_fora, id_sapl, sessao["data"])
                estado, texto_contado, extra_estado = estado_na_votacao(
                    vereador,
                    sessao["data"],
                    texto,
                    presidente_id,
                    id_sapl in presentes,
                    id_sapl in justificados,
                    afastamento,
                    motivo,
                )
                extra_estado = aplicar_aviso_na_votacao(
                    base, id_sapl, texto, extra_estado
                )
                if estado not in ROTULOS_ESTADO:
                    raise SystemExit(f"Estado desconhecido: {estado}")
                linha_estado = {
                    "id_sapl": id_sapl,
                    "nome_parlamentar": vereador["nome_parlamentar"],
                    "estado": estado,
                    "rotulo": ROTULOS_ESTADO[estado],
                    "turno": turno,
                    "tipo_resultado": registro.get("tipo_resultado_nome"),
                    "voto_texto_sapl": texto_contado if estado != "fora_do_mandato" else None,
                    "voto_texto_sapl_fora_do_mandato": (
                        texto if estado == "fora_do_mandato" else None
                    ),
                }
                linha_estado.update(extra_estado)
                estados.append(linha_estado)
                if not no_mandato:
                    continue
                nominal = {
                    "votacao_id": registro["id"],
                    "sessao_id": sessao["id"],
                    "data_sessao": sessao["data"],
                    "materia_id": materia_id,
                    "estado": estado,
                    "rotulo": ROTULOS_ESTADO[estado],
                    "turno": turno,
                    "tipo_resultado": registro.get("tipo_resultado_nome"),
                    "voto_texto_sapl": linha_estado["voto_texto_sapl"],
                    "link_sessao": registro["link_sessao"],
                    "link_materia": registro["link_materia"],
                }
                nominal.update(extra_estado)
                nominais[id_sapl].append(nominal)
            if len(estados) != len(banca):
                raise SystemExit(
                    f"Votacao {registro['id']}: {len(estados)} estados "
                    f"para {len(banca)} vereadores."
                )
            base.update(
                {
                    "voto_individual_registrado": True,
                    "rotulo": None,
                    "estados_por_vereador": estados,
                    "conclusao_do_painel": None,
                }
            )
            votacoes.append(base)

        sessao_saida = dict(sessao)
        sessao_saida.update(
            {
                "presidente_id_sapl": presidente_id,
                "n_presentes": sum(
                    1 for situacao in situacoes.values() if situacao == "presente"
                ),
                "n_faltas_com_justificativa": sum(
                    1
                    for situacao in situacoes.values()
                    if situacao == "falta_com_justificativa"
                ),
                "n_faltas_sem_justificativa": sum(
                    1
                    for situacao in situacoes.values()
                    if situacao == "falta_sem_justificativa"
                ),
                "n_fora_do_mandato": sum(
                    1
                    for situacao in situacoes.values()
                    if situacao == "fora_do_mandato"
                ),
                "n_licenca": sum(
                    1 for situacao in situacoes.values() if situacao in LICENCA_TIPOS
                ),
                "n_registros_votacao": len(registros),
                "n_votacoes_com_voto_individual": sum(
                    1 for registro in registros.values() if votos.get(registro["id"])
                ),
                "n_votacoes_sem_voto_individual": sum(
                    1
                    for registro in registros.values()
                    if not votos.get(registro["id"])
                ),
            }
        )
        sessoes_saida.append(sessao_saida)

    return {
        "sessoes": sessoes_saida,
        "votacoes": votacoes,
        "presenca": presenca,
        "fora_mandato": fora_mandato,
        "nominais": nominais,
        "registros_por_materia": registros_por_materia,
        "divergencias_presenca": divergencias,
        "presentes_e_justificados": presentes_e_justificados,
        "n_votacoes_com_voto_individual": n_com,
        "n_votacoes_sem_voto_individual": n_sem,
        "por_banca": por_banca,
    }


def consolidar_presenca(lista: list[dict], nome: str, sessoes_fora: int = 0) -> dict:
    """Presenca dentro do mandato. Sessoes fora da janela nao aparecem na lista.

    D-050: so duas categorias de falta. Licenca para tratamento de saude
    e ausencia por licenca medica do SAPL contam como falta com
    justificativa, com o motivo guardado em motivo_ausencia. A formula da
    taxa (D-046) nao muda: presencas divididas pelo total no mandato.
    """
    contagem = Counter(item["situacao"] for item in lista)
    presencas = contagem.get("presente", 0)
    faltas_just = contagem.get("falta_com_justificativa", 0)
    faltas_sem = contagem.get("falta_sem_justificativa", 0)
    fora = int(sessoes_fora)
    por_afastamento: dict[str, int] = {}
    licenca = 0
    desconhecidas = {
        situacao: total
        for situacao, total in contagem.items()
        if situacao not in ("presente", "falta_com_justificativa", "falta_sem_justificativa")
    }
    if desconhecidas:
        raise SystemExit(f"{nome}: situacao de presenca desconhecida: {sorted(desconhecidas)}.")
    if contagem.get("fora_do_mandato", 0):
        raise SystemExit(
            f"{nome}: sessao fora do mandato na lista de presenca."
        )
    if presencas + faltas_just + faltas_sem + licenca != len(lista):
        raise SystemExit(f"{nome}: presenca nao fecha o numero de sessoes.")
    no_mandato = presencas + faltas_just + faltas_sem + licenca
    if no_mandato == 0:
        raise SystemExit(
            f"{nome}: nenhuma sessao dentro do mandato. Nada sera estimado."
        )
    faltas_totais = faltas_just + faltas_sem
    return {
        "sessoes_ordinarias": no_mandato,
        "sessoes_do_ano": len(lista) + fora,
        "sessoes_fora_do_mandato": fora,
        "sessoes_licenca": licenca,
        "sessoes_por_afastamento": por_afastamento,
        "presencas": presencas,
        "faltas_com_justificativa": faltas_just,
        "faltas_sem_justificativa": faltas_sem,
        "faltas_totais": faltas_totais,
        "percentual_faltas": percentual(faltas_totais, no_mandato),
        "taxa_presenca": percentual(presencas, no_mandato),
        "por_sessao": lista,
    }


def consolidar_votos(lista: list[dict], n_contado: int, nome: str) -> dict:
    """Historico so com o voto valido: 2o turno ou turno unico.

    O 1o turno, o turno nao identificado e o voto sem deliberacao nao
    viram item nem entram na contagem. Os contadores abaixo guardam
    quantos ficaram de fora, para auditoria.
    """
    validos = [item for item in lista if item.get("turno") in TURNOS_CONTADOS]
    fora = [item for item in lista if item.get("turno") not in TURNOS_CONTADOS]
    primeiro = sum(1 for item in fora if item.get("turno") == TURNO_PRIMEIRO)
    nao_identificado = sum(
        1 for item in fora if item.get("turno") == TURNO_NAO_IDENTIFICADO
    )
    nao_deliberativo = len(fora) - primeiro - nao_identificado
    contagem = Counter(item["estado"] for item in validos)
    resultado = {chave: contagem.get(chave, 0) for chave in ORDEM_ESTADOS}
    resultado["rotulos"] = {chave: ROTULOS_ESTADO[chave] for chave in ORDEM_ESTADOS}
    resultado["total_registros"] = len(validos)
    resultado["primeiro_turno_registros"] = primeiro
    resultado["turno_nao_identificado_registros"] = nao_identificado
    resultado["nao_deliberativo_registros"] = nao_deliberativo
    resultado["nominais"] = validos
    if sum(resultado[chave] for chave in ORDEM_ESTADOS) != len(validos):
        raise SystemExit(f"{nome}: a soma dos estados de voto nao fecha.")
    if len(validos) != n_contado:
        raise SystemExit(
            f"{nome}: {len(validos)} votos validos para {n_contado} votacoes "
            "de 2o turno ou turno unico dentro do mandato."
        )
    return resultado


def escolher_votacao(registros: list[dict]) -> dict:
    def chave(item: dict):
        return (
            item.get("data_sessao") or "",
            item.get("data_hora") or "",
            item.get("id") or 0,
        )

    return sorted(registros, key=chave)[-1]


def carregar_temas() -> dict[int, dict]:
    if not ARQUIVO_TEMAS.exists():
        return {}
    dados = carregar_json(ARQUIVO_TEMAS)
    indice = {}
    if isinstance(dados, dict) and isinstance(dados.get("materias"), list):
        for item in dados["materias"]:
            chave = item.get("materia_id", item.get("id"))
            if chave is None:
                raise SystemExit(f"{rel(ARQUIVO_TEMAS)} tem materia sem id.")
            indice[int(chave)] = item if isinstance(item, dict) else {"tema": item}
        return indice
    if isinstance(dados, dict):
        for chave, valor in dados.items():
            if not str(chave).isdigit():
                continue
            if isinstance(valor, str):
                indice[int(chave)] = {"tema": valor}
            elif isinstance(valor, dict):
                indice[int(chave)] = valor
            else:
                raise SystemExit(f"{rel(ARQUIVO_TEMAS)}: tema de {chave} ilegivel.")
        return indice
    raise SystemExit(f"{rel(ARQUIVO_TEMAS)} em formato nao reconhecido.")


def tema_da_materia(materia_id: int, indice: dict[int, dict]) -> tuple[str | None, bool]:
    item = indice.get(int(materia_id))
    if not item:
        return None, False
    tema = item.get("tema")
    if tema is not None:
        tema = str(tema).strip() or None
    revisada = item.get("revisada_por_humano")
    return tema, bool(revisada) if revisada is not None else False


def revisao_completa(indice: dict[int, dict]) -> bool:
    """Calcula o sinal de revisao a partir dos dados, nunca fixo.

    true somente quando toda materia com tema do arquivo de temas ja passou
    pela revisao humana. Sem materia com tema nao ha revisao que declarar.
    """
    com_tema = [
        item
        for item in indice.values()
        if isinstance(item, dict) and str(item.get("tema") or "").strip()
    ]
    if not com_tema:
        return False
    return all(bool(item.get("revisada_por_humano")) for item in com_tema)


def carregar_projetos(
    ano: int,
    piso: int,
    indice_autoria: dict[int, dict],
    por_id: dict[int, dict],
    registros_por_materia: dict,
    indice_temas: dict[int, dict],
) -> tuple[list[dict], int, int]:
    caminho = DIR_BRUTOS / f"materias-{ano}-resposta-original.csv"
    if not caminho.exists():
        raise SystemExit(f"Arquivo nao encontrado: {rel(caminho)}")
    n_pleg = 0
    n_plex = 0
    projetos = []
    with caminho.open(encoding="utf-8-sig", newline="") as handle:
        leitor = csv.DictReader(handle, delimiter=";")
        for linha in leitor:
            sigla = (linha.get("Tipo de Matéria Legislativa/Sigla") or "").strip()
            if sigla == "PLEG":
                n_pleg += 1
            elif sigla == "PLEX":
                n_plex += 1
            else:
                continue
            materia_id = int(linha["ID"])
            autoria = autores_da_materia(materia_id, indice_autoria, por_id)
            ementa = linha.get("Ementa") or ""
            tema, revisada = tema_da_materia(materia_id, indice_temas)
            registros = registros_por_materia.get(materia_id, [])
            ordenados = sorted(
                registros,
                key=lambda item: (
                    item.get("data_sessao") or "",
                    item.get("data_hora") or "",
                    item.get("id") or 0,
                ),
            )
            turnos = atribuir_turnos(
                sigla,
                [r for r in ordenados if r.get("deliberativa")],
                DOIS_TURNOS,
            )
            posicao = 0
            votacoes = []
            for registro in ordenados:
                if registro.get("deliberativa"):
                    turno = turnos[posicao]
                    posicao += 1
                else:
                    turno = None
                votacoes.append(
                    {
                        "sessao_id": registro["sessao_id"],
                        "data_sessao": registro["data_sessao"],
                        "registro_votacao_id": registro["id"],
                        "resultado_texto_sapl": registro["resultado_texto_sapl"],
                        "situacao_oficial_sapl": registro["situacao_oficial_sapl"],
                        "turno": turno,
                        "deliberativa": bool(registro.get("deliberativa")),
                        "tipo_resultado_nome": registro.get("tipo_resultado_nome"),
                        "totais_oficiais": {
                            "numero_votos_sim": registro["numero_votos_sim"],
                            "numero_votos_nao": registro["numero_votos_nao"],
                            "numero_abstencoes": registro["numero_abstencoes"],
                        },
                        "link_sessao": registro["link_sessao"],
                        "link_materia": registro["link_materia"],
                    }
                )
            projeto = {
                "id": materia_id,
                "numero": linha.get("Número"),
                "ano": linha.get("Ano"),
                "tipo_sigla": sigla,
                "tipo_descricao": (
                    linha.get("Tipo de Matéria Legislativa/Descrição") or ""
                ).strip(),
                "ementa": ementa,
                "tema": tema,
                "revisada_por_humano": revisada,
                "autoria": autoria,
                "autoria_conjunta": bool(autoria and autoria["autoria_conjunta"]),
                "link_sapl": link_materia(materia_id, CONFIG),
                "texto_original": linha.get("Texto Original") or "",
                "votacoes_ordinarias": votacoes,
            }
            if not votacoes:
                projeto["situacao"] = "Em tramitacao"
                projeto["data_sessao"] = None
                projeto["resultado_texto_sapl"] = None
                projeto["frase_resultado_sapl"] = None
                projeto["sessao_id"] = None
                projeto["nome_oficial_ultimo_registro"] = None
                projetos.append(projeto)
                continue
            por_registro = {int(r["id"]): r for r in registros}
            pares = []
            for votacao in votacoes:
                if not votacao.get("deliberativa"):
                    continue
                registro = por_registro.get(int(votacao["registro_votacao_id"]))
                if registro is None:
                    continue
                pares.append((registro, votacao["turno"]))
            ultimo = ordenados[-1]
            nome_ultimo = ultimo.get("tipo_resultado_nome")
            projeto["nome_oficial_ultimo_registro"] = nome_ultimo
            if sigla in DOIS_TURNOS:
                escolhida, em_tram = escolher_por_turno(pares)
            else:
                deliberativos = [registro for registro, _turno in pares]
                escolhida = escolher_votacao(deliberativos) if deliberativos else None
                em_tram = False
            if escolhida is None:
                projeto["situacao"] = "Em tramitacao"
                projeto["data_sessao"] = ultimo["data_sessao"]
                projeto["resultado_texto_sapl"] = ultimo["resultado_texto_sapl"]
                projeto["frase_resultado_sapl"] = ultimo["frase_resultado_sapl"]
                projeto["sessao_id"] = ultimo["sessao_id"]
            elif em_tram:
                projeto["situacao"] = "Em tramitacao"
                projeto["data_sessao"] = escolhida["data_sessao"]
                projeto["resultado_texto_sapl"] = escolhida["resultado_texto_sapl"]
                projeto["frase_resultado_sapl"] = escolhida["frase_resultado_sapl"]
                projeto["sessao_id"] = escolhida["sessao_id"]
            else:
                try:
                    projeto["situacao"] = situacao_da_votacao_escolhida(escolhida)
                except SystemExit as exc:
                    raise SystemExit(
                        f"Materia {materia_id}: {exc}"
                    ) from exc
                projeto["data_sessao"] = escolhida["data_sessao"]
                projeto["resultado_texto_sapl"] = escolhida["resultado_texto_sapl"]
                projeto["frase_resultado_sapl"] = escolhida["frase_resultado_sapl"]
                projeto["sessao_id"] = escolhida["sessao_id"]
            projetos.append(projeto)
    total = n_pleg + n_plex
    if total < piso:
        raise SystemExit(
            f"{ano}: {total} projetos de lei (Legislativo e Executivo). "
            f"O piso minimo e {piso}."
        )
    ids = [item["id"] for item in projetos]
    if len(ids) != len(set(ids)):
        raise SystemExit(f"{ano}: id repetido entre os projetos de lei.")
    return projetos, n_pleg, n_plex


def projetos_do_vereador(id_sapl: int, projetos: list[dict]) -> dict:
    lista = []
    for projeto in projetos:
        autoria = projeto["autoria"] or {"autores": []}
        if not any(
            autor.get("parlamentar_id_sapl") == id_sapl
            for autor in autoria["autores"]
        ):
            continue
        if projeto["tipo_sigla"] != TIPO_PLL:
            continue
        lista.append(
            {
                "id": projeto["id"],
                "numero": projeto["numero"],
                "ano": projeto["ano"],
                "tipo_sigla": projeto.get("tipo_sigla"),
                "tipo_descricao": projeto.get("tipo_descricao"),
                "ementa": projeto["ementa"],
                "tema": projeto["tema"],
                "revisada_por_humano": projeto["revisada_por_humano"],
                "situacao": projeto["situacao"],
                "nome_oficial_ultimo_registro": projeto.get("nome_oficial_ultimo_registro"),
                "data_sessao": projeto["data_sessao"],
                "resultado_texto_sapl": projeto["resultado_texto_sapl"],
                "frase_resultado_sapl": projeto["frase_resultado_sapl"],
                "sessao_id": projeto["sessao_id"],
                "autoria_conjunta": projeto["autoria_conjunta"],
                "link_sapl": projeto["link_sapl"],
            }
        )
    lista.sort(key=lambda item: (int(item["numero"] or 0), item["id"]))
    categorias = Counter(item["tema"] for item in lista if item["tema"])
    return {
        "total_propostos": len(lista),
        "aprovados": sum(1 for item in lista if item["situacao"] == "Aprovado"),
        "rejeitados": sum(1 for item in lista if item["situacao"] == "Rejeitado"),
        "em_tramitacao": sum(1 for item in lista if item["situacao"] == "Em tramitacao"),
        "outro_resultado_oficial": sum(
            1
            for item in lista
            if item["situacao"] not in ("Aprovado", "Rejeitado", "Em tramitacao")
        ),
        "autorias_conjuntas": sum(1 for item in lista if item["autoria_conjunta"]),
        "por_categoria": dict(sorted(categorias.items())),
        "lista": lista,
    }


def conferir_partido_e_foto(base: dict) -> tuple[str, str, str]:
    partido_sigla = (base.get("partido_sigla") or "").strip()
    partido_nome = (base.get("partido_nome") or "").strip()
    foto_url = (base.get("foto_url") or "").strip()
    if not partido_sigla or not partido_nome:
        raise SystemExit(
            f"Vereador {base.get('id_sapl')} sem partido vigente na tabela unica."
        )
    if not foto_url.startswith("http"):
        raise SystemExit(
            f"Vereador {base.get('id_sapl')} sem foto oficial na tabela unica."
        )
    return partido_sigla, partido_nome, foto_url


def temas_globais(projetos: list[dict]) -> dict[str, int]:
    contagem = Counter(
        item["tema"]
        for item in projetos
        if item["tipo_sigla"] == TIPO_PLL and item["tema"]
    )
    return dict(sorted(contagem.items()))


def escrever_csv(caminho: Path, vereadores: list[dict]) -> None:
    campos = [
        "id_sapl",
        "slug_codigo",
        "nome_parlamentar",
        "nome_oficial",
        "partido_sigla",
        "partido_nome",
        "foto_url",
        "link_sapl",
        "sessoes_ordinarias",
        "sessoes_fora_do_mandato",
        "sessoes_licenca",
        "presencas",
        "faltas_com_justificativa",
        "faltas_sem_justificativa",
        "faltas_totais",
        "percentual_faltas",
        "taxa_presenca",
        "votos_sim",
        "votos_nao",
        "votos_abstencao",
        "nao_votou",
        "presidente_que_nao_votou",
        "ausente_com_justificativa",
        "ausente_sem_justificativa",
        "fora_do_mandato",
        "presente_sem_voto_individual_registrado",
        *LICENCA_TIPOS,
        "votos_total_registros",
        "votos_primeiro_turno",
        "votos_turno_nao_identificado",
        "votos_nao_deliberativo",
        "projetos_lei_legislativo",
        "projetos_aprovados",
        "projetos_rejeitados",
        "projetos_em_tramitacao",
    ]
    buffer = io.StringIO(newline="")
    escritor = csv.DictWriter(
        buffer, fieldnames=campos, delimiter=";", lineterminator="\n"
    )
    escritor.writeheader()
    for item in vereadores:
        presenca = item["presenca"]
        votos = item["votos"]
        projetos = item["projetos_lei"]
        escritor.writerow(
            {
                "id_sapl": item["id_sapl"],
                "slug_codigo": item["slug_codigo"],
                "nome_parlamentar": item["nome_parlamentar"],
                "nome_oficial": item["nome_oficial"],
                "partido_sigla": item["partido_sigla"],
                "partido_nome": item["partido_nome"],
                "foto_url": item["foto_url"],
                "link_sapl": item["link_sapl"],
                "sessoes_ordinarias": presenca["sessoes_ordinarias"],
                "sessoes_fora_do_mandato": presenca["sessoes_fora_do_mandato"],
                "sessoes_licenca": presenca["sessoes_licenca"],
                "presencas": presenca["presencas"],
                "faltas_com_justificativa": presenca["faltas_com_justificativa"],
                "faltas_sem_justificativa": presenca["faltas_sem_justificativa"],
                "faltas_totais": presenca["faltas_totais"],
                "percentual_faltas": f"{presenca['percentual_faltas']:.2f}".replace(
                    ".", ","
                ),
                "taxa_presenca": f"{presenca['taxa_presenca']:.2f}".replace(".", ","),
                "votos_sim": votos["sim"],
                "votos_nao": votos["nao"],
                "votos_abstencao": votos["abstencao"],
                "nao_votou": votos["nao_votou"],
                "presidente_que_nao_votou": votos["presidente_que_nao_votou"],
                "ausente_com_justificativa": votos["ausente_com_justificativa"],
                "ausente_sem_justificativa": votos["ausente_sem_justificativa"],
                "fora_do_mandato": votos["fora_do_mandato"],
                "presente_sem_voto_individual_registrado": votos[
                    "presente_sem_voto_individual_registrado"
                ],
                **{tipo: votos[tipo] for tipo in LICENCA_TIPOS},
                "votos_total_registros": votos["total_registros"],
                "votos_primeiro_turno": votos["primeiro_turno_registros"],
                "votos_turno_nao_identificado": votos["turno_nao_identificado_registros"],
                "votos_nao_deliberativo": votos["nao_deliberativo_registros"],
                "projetos_lei_legislativo": projetos["total_propostos"],
                "projetos_aprovados": projetos["aprovados"],
                "projetos_rejeitados": projetos["rejeitados"],
                "projetos_em_tramitacao": projetos["em_tramitacao"],
            }
        )
    escrever_lf(caminho, buffer.getvalue())


def pct(valor: float) -> str:
    return f"{valor:.2f}".replace(".", ",")


def escrever_relatorio(caminho: Path, payload: dict) -> None:
    meta = payload["meta"]
    ano = meta["ano"]
    cidade = meta["cidade"]
    uf = meta["uf"]
    vereadores = payload["vereadores"]
    linhas = [
        f"# Atuação dos vereadores nas sessões ordinárias de {ano}",
        "",
        f"Cidade: {cidade} ({uf})",
        f"Dado coletado em: {meta['dado_coletado_em']}",
        f"Fonte da data: {meta['fonte_data_coleta']}",
        f"Script: `{SCRIPT_REL}`",
        (
            "Fonte dos fatos: arquivos em `dados/brutos/`, "
            "`dados/tratados/vereadores.json`, "
            "`dados/tratados/presidencia_sessoes.json` e "
            "`dados/tratados/autoria_materias.json`."
        ),
        "",
        "## Em uma frase",
        "",
        (
            f"Nas {meta['n_sessoes_ordinarias']} sessões ordinárias de {ano} "
            f"que estão no SAPL, os {meta['n_vereadores']} vereadores com "
            "mandato nesse ano tiveram presença, voto e projetos de lei "
            "lidos do registro oficial."
        ),
        "",
        "## O que este recorte cobre",
        "",
        (
            f"Ano {ano}. Só sessão ordinária. O piso de sessões "
            f"({meta['piso_sessoes_ordinarias']}) é mínimo: o arquivo traz "
            f"{meta['n_sessoes_ordinarias']}, que é pelo menos esse piso."
        ),
        "",
        (
            "Presença e voto nominal só entram quando a data da sessão cai "
            "dentro do mandato da pessoa, pelas datas da tabela de vereadores. "
            "Sessão fora desse intervalo não aparece na lista da pessoa: "
            "a atuação de quem saiu fica congelada na data de saída."
        ),
        "",
    ]
    lacuna = meta.get("lacuna_sessoes_ordinarias") or {}
    aviso = lacuna.get("aviso")
    if isinstance(aviso, str) and aviso.strip():
        linhas.extend(
            [
                "## Lacuna no SAPL",
                "",
                aviso.strip(),
                "",
                (
                    "Números de sessão ordinária ausentes no SAPL: "
                    + ", ".join(
                        str(numero)
                        for numero in lacuna.get("numeros_ausentes_no_sapl") or []
                    )
                    + "."
                ),
                "",
            ]
        )
    linhas.extend(
        [
            "## Como a presença foi lida",
            "",
            (
                "Presente: o vereador está na lista de presença da sessão "
                "ou na lista de presença da ordem do dia, e a data está "
                "dentro do mandato."
            ),
            "",
            (
                "Falta com justificativa: não está em nenhuma das duas listas "
                "e está na lista de justificativa de ausência, ou está em "
                "licença para tratamento de saúde (afastamento manual) ou em "
                "ausência por licença médica do SAPL. Cada sessão guarda o "
                "motivo como está na fonte."
            ),
            "",
            (
                "Falta sem justificativa: não está na presença e não está "
                "na justificativa."
            ),
            "",
            (
                "Fora do mandato: a data da sessão é anterior ao início ou "
                "posterior ao fim do mandato. Essa sessão não aparece na "
                "lista da pessoa e não entra na taxa de presença."
            ),
            "",
            (
                "Taxa de presença: presenças divididas pelo total de sessões "
                "no mandato, que soma presenças e faltas com e sem "
                "justificativa."
            ),
            "",
            "## Como o voto foi lido",
            "",
            (
                "Cada votação com voto individual recebe um estado para cada "
                "vereador da banca do ano. Os rótulos não se misturam."
            ),
            "",
            (
                "Cada votação de projeto de lei tem um turno: a primeira data "
                "é o 1o turno e a seguinte em outra sessão é o 2o turno; os "
                "demais tipos seguem turno único. A contagem de votos de cada "
                "vereador considera só o 2o turno e o turno único. O 1o turno "
                "aparece na lista com a tag, sem entrar na contagem. Projeto "
                "aprovado só no 1o turno continua em tramitação; rejeitado no "
                "1o turno segue rejeitado. Votação sem deliberação (adiada, "
                "pedido de vistas, retirada de pauta) aparece com o nome "
                "oficial do SAPL e não entra em nenhuma contagem de voto."
            ),
            "",
        ]
    )
    for chave in ORDEM_ESTADOS:
        linhas.append(f"- {ROTULOS_ESTADO[chave]}")
    linhas.extend(
        [
            "",
            (
                f"Votação sem nenhum voto individual: {meta['rotulo_sem_voto_individual']}. "
                "Ninguém recebe estado de voto. O arquivo mostra só os totais "
                "oficiais (sim, não e abstenção) e o link da sessão e da matéria. "
                "Isso não é lido como voto unânime."
            ),
            "",
                (
                    "Presidente que não votou só vale quando o texto do SAPL é "
                    "Não Votou e essa pessoa é o presidente daquela sessão em "
                    "`presidencia_sessoes.json`."
                ),
                "",
                (
                    "Licença para tratamento de saúde (`afastamentos_manuais.json`) "
                    "e ausência por licença médica do SAPL contam como falta "
                    "com justificativa, com o motivo e a fonte guardados na "
                    "sessão. No histórico de votos, valem como ausente com "
                    "justificativa."
                ),
                "",
                "## Presença de cada vereador",
            "",
        ]
    )
    for item in vereadores:
        presenca = item["presenca"]
        linhas.extend(
            [
                f"### {item['nome_parlamentar']}",
                "",
                f"Partido: {item['partido_sigla']} ({item['partido_nome']})",
                "",
                f"Página oficial: {item['link_sapl']}",
                "",
                (
                    f"Presente em {presenca['presencas']} das "
                    f"{presenca['sessoes_ordinarias']} sessões em que a presença conta "
                    f"(taxa {pct(presenca['taxa_presenca'])}%)."
                ),
                "",
                (
                    f"Faltas com justificativa: {presenca['faltas_com_justificativa']}. "
                    f"Faltas sem justificativa: {presenca['faltas_sem_justificativa']}. "
                    f"Sessões fora do mandato: {presenca['sessoes_fora_do_mandato']}."
                ),
                "",
            ]
        )
        nota = item.get("nota_factual")
        if nota:
            linhas.extend([nota["texto"], ""])
            for fonte in nota.get("fontes") or []:
                linhas.append(
                    f"Fonte: {fonte['fonte']}. Link: {fonte.get('link_fonte') or 'sem link'}."
                )
            linhas.append("")
    linhas.extend(["## Estados de voto de cada vereador", ""])
    for item in vereadores:
        votos = item["votos"]
        linhas.extend([f"### {item['nome_parlamentar']}", ""])
        for chave in ORDEM_ESTADOS:
            linhas.append(f"- {ROTULOS_ESTADO[chave]}: {votos[chave]}")
        linhas.extend(
            [
                "",
                (
                    "Votações sem voto individual não entram nesta lista. "
                    f"No ano foram {meta['n_votacoes_sem_voto_individual']}."
                ),
                "",
            ]
        )
    linhas.extend(
        [
            "## Projetos de lei",
            "",
            (
                f"Projetos de lei do Legislativo: {meta['n_projetos_lei_legislativo']}. "
                f"Projetos de lei do Executivo: {meta['n_projetos_lei_executivo']}. "
                f"Soma, conferida como mínimo: "
                f"{meta['n_projetos_lei_legislativo_e_executivo']} "
                f"(piso {meta['piso_projetos_lei_legislativo_e_executivo']})."
            ),
            "",
            (
                "A autoria veio de `autoria_materias.json`. "
                "A lista de cada vereador abaixo só inclui projeto de lei "
                "do Legislativo em que o id do parlamentar aparece como autor."
            ),
            "",
            (
                "O tema de cada matéria veio de `temas_materias.json`."
                if meta.get("temas_materias_presente")
                else "O arquivo `temas_materias.json` não está nesta pasta. O tema de cada matéria ficou vazio."
            ),
            "",
            (
                "Classificação por tema revisada pelo mantenedor em todas as "
                "matérias com tema."
                if meta.get("revisada_por_humano")
                else "Nem toda matéria com tema passou pela revisão do mantenedor."
            ),
            "",
        ]
    )
    for item in vereadores:
        projetos = item["projetos_lei"]
        linhas.extend(
            [
                f"### {item['nome_parlamentar']}",
                "",
                (
                    f"Projetos de lei do Legislativo: {projetos['total_propostos']}. "
                    f"Aprovados: {projetos['aprovados']}. "
                    f"Rejeitados: {projetos['rejeitados']}. "
                    f"Em tramitação: {projetos['em_tramitacao']}."
                ),
                "",
            ]
        )
        if not projetos["lista"]:
            linhas.append("Nenhum projeto de lei do Legislativo com esta autoria neste ano.")
            linhas.append("")
            continue
        for projeto in projetos["lista"]:
            linhas.append(
                f"- {projeto['numero']}/{projeto['ano']} "
                f"(id {projeto['id']}): {projeto['ementa']} "
                f"Situação: {projeto['situacao']}. "
                f"Fonte: {projeto['link_sapl']}"
            )
        linhas.append("")
    linhas.extend(
        [
            "## Totais",
            "",
            f"- Sessões ordinárias no SAPL: {meta['n_sessoes_ordinarias']}",
            f"- Vereadores com mandato no ano: {meta['n_vereadores']}",
            f"- Presenças dentro do mandato: {meta['n_presencas']}",
            f"- Faltas com justificativa: {meta['n_faltas_com_justificativa']}",
            f"- Faltas sem justificativa: {meta['n_faltas_sem_justificativa']}",
            (
                "- Afastamentos que não contam como falta: "
                f"{meta['n_sessoes_licenca']}"
            ),
            f"- Votações: {meta['n_votacoes']}",
            f"- Votações com voto individual: {meta['n_votacoes_com_voto_individual']}",
            f"- Votações sem voto individual: {meta['n_votacoes_sem_voto_individual']}",
            "",
            "## Como repetir",
            "",
            "Na pasta do projeto, rode:",
            "",
            f"    python {SCRIPT_REL}",
            "",
            (
                "O programa lê os brutos de novo e reescreve o JSON, o CSV "
                "e este relatório do ano. Não edite esses arquivos na mão."
            ),
            "",
        ]
    )
    escrever_lf(caminho, "\n".join(linhas))


def gerar_do_ano(ano: int) -> None:
    pisos = pisos_sanidade(ano, CONFIG)
    try:
        piso_sessoes = exigir_piso(
            "sessoes_ordinarias", pisos["sessoes_ordinarias"], ano
        )
        piso_projetos = exigir_piso(
            "projetos_lei_legislativo_e_executivo",
            pisos["projetos_lei_legislativo_e_executivo"],
            ano,
        )
        piso_vereadores = exigir_piso("vereadores", pisos["vereadores"], ano)
    except PisoNaoDefinido as erro:
        raise SystemExit(str(erro)) from erro

    tabela = carregar_json(ARQUIVO_VEREADORES)
    por_id = {int(item["id_sapl"]): item for item in tabela["vereadores"]}
    banca = filtrar_banca(tabela, ano, int(piso_vereadores))
    sessoes, lacuna, contagem = carregar_sessoes(ano, int(piso_sessoes))
    presidentes = carregar_presidentes(ano)
    indice_autoria = carregar_autoria()
    rotulo_sem = contagem.get("rotulo_sem_voto_individual")
    if not isinstance(rotulo_sem, str) or not rotulo_sem.strip():
        raise SystemExit(
            f"{ano}: contagem sem rotulo_sem_voto_individual. "
            "Nao vou inventar o texto."
        )
    manuais = carregar_afastamentos()
    registrar_tipos_afastamento(manuais["afastamentos"])
    tipos_materia = carregar_tipos_materia(ano)
    tipos_resultado = carregar_tipos_resultado()
    catalogo_tipos, fonte_catalogo = carregar_catalogo_tipos_materia()
    justificativas_detalhe = carregar_justificativas_detalhe()
    bruto = processar_sessoes(
        ano,
        banca,
        sessoes,
        presidentes,
        indice_autoria,
        por_id,
        rotulo_sem.strip(),
        manuais["afastamentos"],
        manuais["motivos_fora_do_mandato"],
        tipos_materia,
        tipos_resultado,
        justificativas_detalhe,
    )
    notas = notas_publicas(manuais["notas"])
    n_votacoes = len(bruto["votacoes"])
    if contagem.get("total_votacoes") is not None:
        if n_votacoes != int(contagem["total_votacoes"]):
            raise SystemExit(
                f"{ano}: {n_votacoes} votacoes lidas, "
                f"contagem diz {contagem['total_votacoes']}."
            )
    if contagem.get("votacoes_com_voto_individual") is not None:
        if bruto["n_votacoes_com_voto_individual"] != int(
            contagem["votacoes_com_voto_individual"]
        ):
            raise SystemExit(
                f"{ano}: votacoes com voto individual nao batem com a contagem."
            )
    if contagem.get("votacoes_sem_voto_individual") is not None:
        if bruto["n_votacoes_sem_voto_individual"] != int(
            contagem["votacoes_sem_voto_individual"]
        ):
            raise SystemExit(
                f"{ano}: votacoes sem voto individual nao batem com a contagem."
            )

    indice_temas = carregar_temas()
    revisada_tudo = revisao_completa(indice_temas)
    projetos, n_pleg, n_plex = carregar_projetos(
        ano,
        int(piso_projetos),
        indice_autoria,
        por_id,
        bruto["registros_por_materia"],
        indice_temas,
    )
    vereadores = []
    total_esperado_contado = 0
    for base in banca:
        id_sapl = int(base["id_sapl"])
        partido_sigla, partido_nome, foto_url = conferir_partido_e_foto(base)
        presenca = consolidar_presenca(
            bruto["presenca"][id_sapl],
            base["nome_parlamentar"],
            bruto["fora_mandato"][id_sapl],
        )
        n_contado_na_janela = sum(
            1
            for votacao in bruto["votacoes"]
            if votacao.get("voto_individual_registrado")
            and votacao.get("turno") in TURNOS_CONTADOS
            and dentro_do_mandato(base, votacao.get("data_sessao") or "")
        )
        total_esperado_contado += n_contado_na_janela
        votos = consolidar_votos(
            bruto["nominais"][id_sapl],
            n_contado_na_janela,
            base["nome_parlamentar"],
        )
        projetos_lei = projetos_do_vereador(id_sapl, projetos)
        if (
            projetos_lei["aprovados"]
            + projetos_lei["rejeitados"]
            + projetos_lei["em_tramitacao"]
            + projetos_lei["outro_resultado_oficial"]
            != projetos_lei["total_propostos"]
        ):
            raise SystemExit(
                f"{base['nome_parlamentar']}: situacao dos projetos nao fecha."
            )
        vereadores.append(
            {
                "id_sapl": id_sapl,
                "slug_codigo": base["slug_codigo"],
                "nome_oficial": base["nome_oficial"],
                "nome_parlamentar": base["nome_parlamentar"],
                "partido_sigla": partido_sigla,
                "partido_nome": partido_nome,
                "foto_url": foto_url,
                "link_sapl": base["link_sapl"],
                "data_inicio_mandato": base.get("data_inicio_mandato"),
                "data_fim_mandato": base.get("data_fim_mandato"),
                "anos_com_mandato": base.get("anos_com_mandato"),
                "nota_factual": notas.get(id_sapl),
                "afastamentos": afastamentos_publicos(manuais["afastamentos"], id_sapl),
                "presenca": presenca,
                "votos": votos,
                "projetos_lei": projetos_lei,
            }
        )

    n_presencas = sum(item["presenca"]["presencas"] for item in vereadores)
    n_faltas_j = sum(
        item["presenca"]["faltas_com_justificativa"] for item in vereadores
    )
    n_faltas_s = sum(
        item["presenca"]["faltas_sem_justificativa"] for item in vereadores
    )
    n_fora = sum(item["presenca"]["sessoes_fora_do_mandato"] for item in vereadores)
    n_licenca = sum(item["presenca"]["sessoes_licenca"] for item in vereadores)
    if (
        n_presencas + n_faltas_j + n_faltas_s + n_fora + n_licenca
        != len(sessoes) * len(vereadores)
    ):
        raise SystemExit(f"{ano}: a grade de presenca nao fecha.")

    contagem_estados = {chave: 0 for chave in ORDEM_ESTADOS}
    n_primeiro_turno = 0
    n_turno_nao_identificado = 0
    n_nao_deliberativo = 0
    for item in vereadores:
        for chave in ORDEM_ESTADOS:
            contagem_estados[chave] += item["votos"][chave]
        n_primeiro_turno += item["votos"]["primeiro_turno_registros"]
        n_turno_nao_identificado += item["votos"]["turno_nao_identificado_registros"]
        n_nao_deliberativo += item["votos"]["nao_deliberativo_registros"]
    votacoes_turno_nao_identificado = sorted(
        {
            (votacao["sessao_id"], votacao["id"])
            for votacao in bruto["votacoes"]
            if votacao.get("voto_individual_registrado")
            and votacao.get("turno") == TURNO_NAO_IDENTIFICADO
        }
    )
    if sum(contagem_estados.values()) != total_esperado_contado:
        raise SystemExit(f"{ano}: a grade de estados de voto nao fecha.")

    dado_coletado_em, fonte_data = data_da_coleta(ano)
    payload = {
        "meta": {
            "gerado_por": SCRIPT_REL,
            "cidade": nome_cidade(CONFIG),
            "uf": uf_cidade(CONFIG),
            "ano": ano,
            "dado_coletado_em": dado_coletado_em,
            "fonte_data_coleta": fonte_data,
            "n_sessoes_ordinarias": len(sessoes),
            "piso_sessoes_ordinarias": int(piso_sessoes),
            "n_vereadores": len(vereadores),
            "piso_vereadores": int(piso_vereadores),
            "n_projetos_lei_legislativo": n_pleg,
            "n_projetos_lei_executivo": n_plex,
            "n_projetos_lei_legislativo_e_executivo": n_pleg + n_plex,
            "piso_projetos_lei_legislativo_e_executivo": int(piso_projetos),
            "n_presencas": n_presencas,
            "n_faltas_com_justificativa": n_faltas_j,
            "n_faltas_sem_justificativa": n_faltas_s,
            "n_sessoes_fora_do_mandato": n_fora,
            "n_sessoes_licenca": n_licenca,
            "n_votacoes": n_votacoes,
            "n_registros_votacao": n_votacoes,
            "n_votacoes_com_voto_individual": bruto["n_votacoes_com_voto_individual"],
            "n_votacoes_sem_voto_individual": bruto["n_votacoes_sem_voto_individual"],
            "n_nominais_primeiro_turno": n_primeiro_turno,
            "n_nominais_turno_nao_identificado": n_turno_nao_identificado,
            "n_nominais_nao_deliberativo": n_nao_deliberativo,
            "votacoes_turno_nao_identificado": [
                {"sessao_id": sessao_id, "votacao_id": votacao_id}
                for sessao_id, votacao_id in votacoes_turno_nao_identificado
            ],
            "rotulo_sem_voto_individual": rotulo_sem.strip(),
            "contagem_estados": contagem_estados,
            "rotulos_estados": {chave: ROTULOS_ESTADO[chave] for chave in ORDEM_ESTADOS},
            "catalogo_tipos_materia": catalogo_tipos,
            "fonte_catalogo_tipos_materia": fonte_catalogo,
            "lacuna_sessoes_ordinarias": lacuna,
            "sessoes_com_presenca_divergente": bruto["divergencias_presenca"],
            "presentes_com_justificativa_na_mesma_sessao": bruto[
                "presentes_e_justificados"
            ],
            "projetos_lei_legislativo_por_categoria": temas_globais(projetos),
            "temas_materias_presente": ARQUIVO_TEMAS.exists(),
            "fonte_temas": rel(ARQUIVO_TEMAS) if ARQUIVO_TEMAS.exists() else None,
            "revisada_por_humano": revisada_tudo,
            "arquivos_de_origem": [
                rel(DIR_BRUTOS / f"contagem_votacoes_ordinarias_{ano}.json"),
                rel(DIR_BRUTOS / f"materias-{ano}-resposta-original.csv"),
                rel(ARQUIVO_VEREADORES),
                rel(ARQUIVO_PRESIDENCIA),
                rel(ARQUIVO_AUTORIA),
                *([rel(ARQUIVO_AFASTAMENTOS)] if ARQUIVO_AFASTAMENTOS.exists() else []),
                *([rel(ARQUIVO_TEMAS)] if ARQUIVO_TEMAS.exists() else []),
            ],
            "observacao": (
                "Ausência não é voto. Votação sem voto individual não é "
                "unânime. Presidente que não votou só conta quando o SAPL "
                "registrou Não Votou e a pessoa presidia aquela sessão. "
                "Fora do mandato não aparece na lista da pessoa e não entra "
                "em presença nem em voto. Licença para tratamento de saúde "
                "e ausência por licença médica do SAPL contam como falta "
                "com justificativa, com o motivo guardado na sessão. Projeto de lei "
                "tem dois turnos: a contagem de votos considera só o 2o "
                "turno ou o turno único; o 1o turno aparece na lista com a "
                "tag, sem entrar na contagem. Votação adiada, com pedido de "
                "vistas ou retirada de pauta aparece com o nome oficial e "
                "também não entra nas contagens."
            ),
        },
        "sessoes": bruto["sessoes"],
        "votacoes": bruto["votacoes"],
        "projetos_lei": projetos,
        "vereadores": vereadores,
    }
    recusar_campos_pessoais(payload)
    arquivo_json = DIR_SCRIPT / f"atuacao_vereadores_{ano}.json"
    arquivo_csv = DIR_SCRIPT / f"atuacao_vereadores_{ano}.csv"
    arquivo_relatorio = DIR_SCRIPT / f"RELATORIO-ATUACAO-VEREADORES-{ano}.md"
    escrever_lf(
        arquivo_json,
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    )
    escrever_csv(arquivo_csv, vereadores)
    escrever_relatorio(arquivo_relatorio, payload)
    print(
        f"{ano}: {len(vereadores)} vereadores, {len(sessoes)} sessoes, "
        f"{n_votacoes} votacoes ({bruto['n_votacoes_com_voto_individual']} "
        f"com voto individual, {bruto['n_votacoes_sem_voto_individual']} sem), "
        f"{n_pleg} PLEG, {n_plex} PLEX."
    )
    print(f"  {rel(arquivo_json)}")
    print(f"  {rel(arquivo_csv)}")
    print(f"  {rel(arquivo_relatorio)}")


def main() -> None:
    if not DIR_BRUTOS.is_dir():
        raise SystemExit("Pasta de brutos nao encontrada.")
    if not ARQUIVO_VEREADORES.exists():
        raise SystemExit("Tabela de vereadores nao encontrada.")
    for ano in anos_recorte(CONFIG):
        gerar_do_ano(int(ano))


if __name__ == "__main__":
    main()
