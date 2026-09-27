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
    carregar_config,
    exigir_piso,
    link_materia,
    link_sessao,
    nome_cidade,
    pisos_sanidade,
    uf_cidade,
)
from gerar_temas_votacoes import classificar  # noqa: E402

CONFIG = carregar_config()
SCRIPT_REL = "dados/tratados/gerar_atuacao_vereadores.py"
ARQUIVO_VEREADORES = DIR_SCRIPT / "vereadores.json"
ARQUIVO_PRESIDENCIA = DIR_SCRIPT / "presidencia_sessoes.json"
ARQUIVO_AUTORIA = DIR_SCRIPT / "autoria_materias.json"
ARQUIVO_AFASTAMENTOS = DIR_SCRIPT / "afastamentos_manuais.json"
TIPOS_PROJETO = ("PLEG", "PLEX")
TIPO_PLL = "PLEG"
CLASSIFICADOR_TEMAS = "IA, por regras temáticas documentadas"

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


def recusar_ip(obj, caminho: str = "") -> None:
    if isinstance(obj, dict):
        if "ip" in obj:
            raise SystemExit(f"Campo ip em dado tratado: {caminho or 'raiz'}")
        for chave, valor in obj.items():
            recusar_ip(valor, f"{caminho}.{chave}")
    elif isinstance(obj, list):
        for indice, valor in enumerate(obj):
            recusar_ip(valor, f"{caminho}[{indice}]")


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
    global ORDEM_ESTADOS
    for item in afastamentos:
        if item.get("conta_como_falta"):
            raise SystemExit(
                "Afastamento com conta_como_falta verdadeiro ainda nao tem regra. "
                "Nao vou soma-lo como falta comum."
            )
        tipo = str(item["tipo"])
        rotulo = str(item["rotulo"])
        if tipo in ROTULOS_ESTADO and ROTULOS_ESTADO[tipo] != rotulo:
            raise SystemExit(f"Tipo {tipo} com rotulos diferentes.")
        if tipo not in ORDEM_ESTADOS:
            ORDEM_ESTADOS = ORDEM_ESTADOS + (tipo,)
            ROTULOS_ESTADO[tipo] = rotulo
        if tipo not in LICENCA_TIPOS:
            LICENCA_TIPOS.append(tipo)


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
    return {
        "fonte": item.get("fonte") or "",
        "link_fonte": link,
        "fonte_oficial_encontrada": bool(item.get("fonte_oficial_encontrada")),
    }


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


def carregar_registros(sessao: dict) -> dict[int, dict]:
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
            "situacao_oficial_sapl": situacao_oficial(resultado),
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
        return str(afastamento["tipo"]), None, fonte_da_ocorrencia(afastamento)
    if not dentro_do_mandato(vereador, data):
        return "fora_do_mandato", voto_texto, complemento_fora(motivo)
    if voto_texto is not None:
        era_presidente = int(vereador["id_sapl"]) == presidente_id
        return estado_do_texto(voto_texto, era_presidente), voto_texto, {}
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
) -> dict:
    ids_banca = {int(item["id_sapl"]) for item in banca}
    por_banca = {int(item["id_sapl"]): item for item in banca}
    presenca = {id_sapl: [] for id_sapl in ids_banca}
    nominais = {id_sapl: [] for id_sapl in ids_banca}
    registros_por_materia: dict[int, list[dict]] = defaultdict(list)
    sessoes_saida = []
    votacoes = []
    divergencias = []
    presentes_e_justificados = []
    n_com = 0
    n_sem = 0

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
            afastamento = afastamento_na_data(afastamentos, id_sapl, sessao["data"])
            motivo = motivo_fora_na_data(motivos_fora, id_sapl, sessao["data"])
            if afastamento is not None:
                situacao = str(afastamento["tipo"])
            elif not no_mandato:
                situacao = "fora_do_mandato"
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
            elif situacao == "fora_do_mandato":
                registro.update(complemento_fora(motivo))
            presenca[id_sapl].append(registro)
            situacoes[id_sapl] = situacao

        registros = carregar_registros(sessao)
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
                if estado not in ROTULOS_ESTADO:
                    raise SystemExit(f"Estado desconhecido: {estado}")
                linha_estado = {
                    "id_sapl": id_sapl,
                    "nome_parlamentar": vereador["nome_parlamentar"],
                    "estado": estado,
                    "rotulo": ROTULOS_ESTADO[estado],
                    "voto_texto_sapl": texto_contado if estado != "fora_do_mandato" else None,
                    "voto_texto_sapl_fora_do_mandato": (
                        texto if estado == "fora_do_mandato" else None
                    ),
                }
                linha_estado.update(extra_estado)
                estados.append(linha_estado)
                nominal = {
                    "votacao_id": registro["id"],
                    "sessao_id": sessao["id"],
                    "data_sessao": sessao["data"],
                    "materia_id": materia_id,
                    "estado": estado,
                    "rotulo": ROTULOS_ESTADO[estado],
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
        "nominais": nominais,
        "registros_por_materia": registros_por_materia,
        "divergencias_presenca": divergencias,
        "presentes_e_justificados": presentes_e_justificados,
        "n_votacoes_com_voto_individual": n_com,
        "n_votacoes_sem_voto_individual": n_sem,
        "por_banca": por_banca,
    }


def consolidar_presenca(lista: list[dict], nome: str) -> dict:
    contagem = Counter(item["situacao"] for item in lista)
    presencas = contagem.get("presente", 0)
    faltas_just = contagem.get("falta_com_justificativa", 0)
    faltas_sem = contagem.get("falta_sem_justificativa", 0)
    fora = contagem.get("fora_do_mandato", 0)
    por_afastamento = {tipo: contagem.get(tipo, 0) for tipo in LICENCA_TIPOS}
    licenca = sum(por_afastamento.values())
    if presencas + faltas_just + faltas_sem + fora + licenca != len(lista):
        raise SystemExit(f"{nome}: presenca nao fecha o numero de sessoes.")
    no_mandato = presencas + faltas_just + faltas_sem
    if no_mandato == 0:
        raise SystemExit(
            f"{nome}: nenhuma sessao dentro do mandato. Nada sera estimado."
        )
    faltas_totais = faltas_just + faltas_sem
    return {
        "sessoes_ordinarias": no_mandato,
        "sessoes_do_ano": len(lista),
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


def consolidar_votos(lista: list[dict], n_com_voto: int, nome: str) -> dict:
    contagem = Counter(item["estado"] for item in lista)
    resultado = {chave: contagem.get(chave, 0) for chave in ORDEM_ESTADOS}
    resultado["rotulos"] = {chave: ROTULOS_ESTADO[chave] for chave in ORDEM_ESTADOS}
    resultado["total_registros"] = len(lista)
    resultado["nominais"] = lista
    if sum(resultado[chave] for chave in ORDEM_ESTADOS) != len(lista):
        raise SystemExit(f"{nome}: a soma dos estados de voto nao fecha.")
    if len(lista) != n_com_voto:
        raise SystemExit(
            f"{nome}: {len(lista)} estados para {n_com_voto} votacoes "
            "com voto individual."
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


def carregar_projetos(
    ano: int,
    piso: int,
    indice_autoria: dict[int, dict],
    por_id: dict[int, dict],
    registros_por_materia: dict,
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
            registros = registros_por_materia.get(materia_id, [])
            votacoes = []
            for registro in sorted(
                registros,
                key=lambda item: (
                    item.get("data_sessao") or "",
                    item.get("data_hora") or "",
                    item.get("id") or 0,
                ),
            ):
                votacoes.append(
                    {
                        "sessao_id": registro["sessao_id"],
                        "data_sessao": registro["data_sessao"],
                        "registro_votacao_id": registro["id"],
                        "resultado_texto_sapl": registro["resultado_texto_sapl"],
                        "situacao_oficial_sapl": registro["situacao_oficial_sapl"],
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
                "categoria": classificar(ementa),
                "classificador": CLASSIFICADOR_TEMAS,
                "revisada_por_humano": False,
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
            else:
                escolhida = escolher_votacao(registros)
                if escolhida["situacao_oficial_sapl"] is not None:
                    projeto["situacao"] = escolhida["situacao_oficial_sapl"]
                elif escolhida["frase_resultado_sapl"]:
                    projeto["situacao"] = escolhida["frase_resultado_sapl"]
                else:
                    raise SystemExit(
                        f"Materia {materia_id}: votacao {escolhida['id']} "
                        "sem frase de resultado no SAPL."
                    )
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
                "ementa": projeto["ementa"],
                "categoria": projeto["categoria"],
                "classificador": projeto["classificador"],
                "revisada_por_humano": projeto["revisada_por_humano"],
                "situacao": projeto["situacao"],
                "data_sessao": projeto["data_sessao"],
                "resultado_texto_sapl": projeto["resultado_texto_sapl"],
                "frase_resultado_sapl": projeto["frase_resultado_sapl"],
                "sessao_id": projeto["sessao_id"],
                "autoria_conjunta": projeto["autoria_conjunta"],
                "link_sapl": projeto["link_sapl"],
            }
        )
    lista.sort(key=lambda item: (int(item["numero"] or 0), item["id"]))
    categorias = Counter(item["categoria"] for item in lista)
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
        item["categoria"] for item in projetos if item["tipo_sigla"] == TIPO_PLL
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
            "Presença e voto só entram quando a data da sessão cai dentro "
            "do mandato da pessoa, pelas datas da tabela de vereadores. "
            "Fora desse intervalo o estado é próprio: fora do mandato."
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
                "e está na lista de justificativa de ausência."
            ),
            "",
            (
                "Falta sem justificativa: não está na presença e não está "
                "na justificativa."
            ),
            "",
            (
                "Fora do mandato: a data da sessão é anterior ao início ou "
                "posterior ao fim do mandato. Essa sessão não entra na taxa "
                "de presença."
            ),
            "",
            "## Como o voto foi lido",
            "",
            (
                "Cada votação com voto individual recebe um estado para cada "
                "vereador da banca do ano. Os rótulos não se misturam."
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
                    "Afastamento que não conta como falta vem de "
                    "`afastamentos_manuais.json`. Esse período não entra em "
                    "falta nem na taxa de presença. Cada ocorrência guarda a fonte."
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
                    f"Afastamentos que não contam como falta: {presenca['sessoes_licenca']}. "
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
                "A classificação por tema ainda não foi revisada por uma pessoa."
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

    projetos, n_pleg, n_plex = carregar_projetos(
        ano,
        int(piso_projetos),
        indice_autoria,
        por_id,
        bruto["registros_por_materia"],
    )
    vereadores = []
    for base in banca:
        id_sapl = int(base["id_sapl"])
        partido_sigla, partido_nome, foto_url = conferir_partido_e_foto(base)
        presenca = consolidar_presenca(
            bruto["presenca"][id_sapl], base["nome_parlamentar"]
        )
        votos = consolidar_votos(
            bruto["nominais"][id_sapl],
            bruto["n_votacoes_com_voto_individual"],
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
    for item in vereadores:
        for chave in ORDEM_ESTADOS:
            contagem_estados[chave] += item["votos"][chave]
    if sum(contagem_estados.values()) != (
        bruto["n_votacoes_com_voto_individual"] * len(vereadores)
    ):
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
            "rotulo_sem_voto_individual": rotulo_sem.strip(),
            "contagem_estados": contagem_estados,
            "rotulos_estados": {chave: ROTULOS_ESTADO[chave] for chave in ORDEM_ESTADOS},
            "lacuna_sessoes_ordinarias": lacuna,
            "sessoes_com_presenca_divergente": bruto["divergencias_presenca"],
            "presentes_com_justificativa_na_mesma_sessao": bruto[
                "presentes_e_justificados"
            ],
            "projetos_lei_legislativo_por_categoria": temas_globais(projetos),
            "classificador_temas": CLASSIFICADOR_TEMAS,
            "revisada_por_humano": False,
            "arquivos_de_origem": [
                rel(DIR_BRUTOS / f"contagem_votacoes_ordinarias_{ano}.json"),
                rel(DIR_BRUTOS / f"materias-{ano}-resposta-original.csv"),
                rel(ARQUIVO_VEREADORES),
                rel(ARQUIVO_PRESIDENCIA),
                rel(ARQUIVO_AUTORIA),
                *([rel(ARQUIVO_AFASTAMENTOS)] if ARQUIVO_AFASTAMENTOS.exists() else []),
            ],
            "observacao": (
                "Ausência não é voto. Votação sem voto individual não é "
                "unânime. Presidente que não votou só conta quando o SAPL "
                "registrou Não Votou e a pessoa presidia aquela sessão. "
                "Fora do mandato não entra em presença nem em voto. "
                "Afastamento do arquivo de afastamentos não conta como falta."
            ),
        },
        "sessoes": bruto["sessoes"],
        "votacoes": bruto["votacoes"],
        "projetos_lei": projetos,
        "vereadores": vereadores,
    }
    recusar_ip(payload)
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
