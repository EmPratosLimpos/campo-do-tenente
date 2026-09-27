"""Gera a atuacao consolidada dos 15 vereadores em 2026.

Le apenas arquivos em dados/brutos/ e a tabela unica em
dados/tratados/vereadores.json. Nao inventa numero, voto, falta
nem autoria. Rode de novo: o resultado tem que ser o mesmo,
salvo a data de geracao.

Uso:
    python dados/tratados/gerar_atuacao_vereadores_2026.py
"""

from __future__ import annotations

import csv
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

DIR_SCRIPT = Path(__file__).resolve().parent
DIR_BRUTOS = DIR_SCRIPT.parent / "brutos"
if str(DIR_SCRIPT) not in sys.path:
    sys.path.insert(0, str(DIR_SCRIPT))

from gerar_temas_votacoes_2026 import REGRAS, classificar  # noqa: E402

ARQUIVO_VEREADORES = DIR_SCRIPT / "vereadores.json"
ARQUIVO_CONTAGEM = DIR_BRUTOS / "contagem_votacoes_ordinarias_2026.json"
ARQUIVO_MATERIAS = DIR_BRUTOS / "materias-2026-resposta-original.csv"
ARQUIVO_RESUMO_COLETA = DIR_BRUTOS / "_resumo_coleta_vereadores_2026.json"
ARQUIVO_JSON = DIR_SCRIPT / "atuacao_vereadores_2026.json"
ARQUIVO_CSV = DIR_SCRIPT / "atuacao_vereadores_2026.csv"
ARQUIVO_RELATORIO = DIR_SCRIPT / "RELATORIO-ATUACAO-VEREADORES-2026.md"

LINK_MATERIA = "https://sapl.campolargo.pr.leg.br/materia/{id}"
LINK_SESSAO = "https://sapl.campolargo.pr.leg.br/sessao/{id}"
TIPO_PLL = "PLL"
DESCRICAO_PLL = "PROJETO DE LEI DO LEGISLATIVO"
N_SESSOES_ESPERADAS = 26
N_PLL_ESPERADOS = 100
N_VEREADORES_ESPERADOS = 15

PREFIXO_PRESIDENTE = re.compile(r"^PRESIDENTE(\s|-)", re.IGNORECASE)
RESULTADO_VOTACAO = re.compile(
    r"Votação:\s*(UNANIMIDADE|MAIORIA ABSOLUTA|REJEITADO)\s*$",
    re.IGNORECASE,
)
APROVADOS = {"UNANIMIDADE", "MAIORIA ABSOLUTA"}
REJEITADOS = {"REJEITADO"}
VOTOS_SIM = {"Sim"}
VOTOS_NAO = {"Não", "Nao"}
VOTOS_ABSTENCAO = {"Abstenção", "Abstencao"}
VOTOS_NAO_VOTOU = {"Não Votou", "Nao Votou", "-1"}
VOTOS_AUSENTE = {"Ausente"}
CATEGORIAS = list(REGRAS.keys()) + ["Outros"]
PACOTE_SESSAO = (
    "sessaoplenariapresenca",
    "presencaordemdia",
    "justificativaausencia",
    "integrantemesa",
    "votoparlamentar",
    "registrovotacao",
)


def agora_iso() -> str:
    try:
        agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
    except Exception:
        agora = datetime.now(timezone.utc).astimezone()
    return agora.isoformat(timespec="seconds")


def iso_de_mtime(caminho: Path) -> str:
    return (
        datetime.fromtimestamp(caminho.stat().st_mtime, tz=timezone.utc)
        .astimezone()
        .isoformat(timespec="seconds")
    )


def mtime_mais_recente_brutos() -> str:
    arquivos = [p for p in DIR_BRUTOS.iterdir() if p.is_file()]
    if not arquivos:
        raise SystemExit(
            f"Nenhum arquivo em {DIR_BRUTOS} para obter a data da coleta."
        )
    mais_recente = max(arquivos, key=lambda p: p.stat().st_mtime)
    return iso_de_mtime(mais_recente)


def ler_dado_coletado_em() -> tuple[str, str]:
    if ARQUIVO_RESUMO_COLETA.exists():
        data = carregar_json(ARQUIVO_RESUMO_COLETA)
        fim = data.get("fim") if isinstance(data, dict) else None
        if isinstance(fim, str) and fim.strip():
            return (
                fim.strip(),
                "dados/brutos/_resumo_coleta_vereadores_2026.json",
            )
    return (
        mtime_mais_recente_brutos(),
        "mtime dos arquivos em dados/brutos/",
    )


def carregar_json(caminho: Path):
    return json.loads(caminho.read_text(encoding="utf-8"))


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
                f"mas o arquivo tem {len(resultados)} registros. "
                "Nao completar lacuna na mao."
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


def normalizar_nome(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", (texto or "").strip())
    sem_acento = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sem_acento.casefold())


def conferir_partido_e_foto(base: dict) -> tuple[str, str, str]:
    partido_sigla = (base.get("partido_sigla") or "").strip()
    partido_nome = (base.get("partido_nome") or "").strip()
    foto_url = (base.get("foto_url") or "").strip()
    if not partido_sigla or not partido_nome:
        raise SystemExit(
            f"Vereador {base.get('id_sapl')} sem partido vigente na tabela unica. "
            "Rode gerar_tabela_vereadores.py de novo."
        )
    if not foto_url.startswith("http"):
        raise SystemExit(
            f"Vereador {base.get('id_sapl')} sem foto oficial na tabela unica. "
            "Rode gerar_tabela_vereadores.py de novo."
        )
    return partido_sigla, partido_nome, foto_url


def percentual(parte: int, total: int) -> float:
    if total == 0:
        raise SystemExit("Nao da para calcular porcentagem com total zero.")
    return round(parte * 100 / total, 2)


def arquivo_sessao(sessao_id: int, sufixo: str) -> Path:
    return DIR_BRUTOS / f"sessao_{sessao_id}_{sufixo}.json"


def eh_presidente(item: dict) -> bool:
    texto = unicodedata.normalize("NFKC", (item.get("__str__") or "").strip())
    return bool(PREFIXO_PRESIDENTE.match(texto))


def extrair_resultado(texto: str | None) -> str | None:
    if not texto:
        return None
    achado = RESULTADO_VOTACAO.search(texto.strip())
    if not achado:
        return None
    return achado.group(1).upper()


def situacao_do_resultado(resultado: str | None) -> str | None:
    if resultado in APROVADOS:
        return "Aprovado"
    if resultado in REJEITADOS:
        return "Rejeitado"
    return None


def classificar_voto(voto_fonte: str, era_presidente: bool) -> str:
    if voto_fonte in VOTOS_SIM:
        return "sim"
    if voto_fonte in VOTOS_NAO:
        return "nao"
    if voto_fonte in VOTOS_ABSTENCAO:
        return "abstencao"
    if voto_fonte in VOTOS_AUSENTE:
        return "ausente"
    if voto_fonte in VOTOS_NAO_VOTOU:
        if era_presidente:
            return "presidente_nao_votou"
        return "nao_votou_nao_era_presidente"
    return "outro"


def montar_indice_nomes(vereadores: list[dict]) -> dict[str, int]:
    indice: dict[str, set[int]] = defaultdict(set)
    for item in vereadores:
        id_sapl = int(item["id_sapl"])
        for campo in ("nome_oficial", "nome_parlamentar"):
            chave = normalizar_nome(item.get(campo) or "")
            if chave:
                indice[chave].add(id_sapl)
        for apelido in item.get("apelidos") or []:
            chave = normalizar_nome(apelido)
            if chave:
                indice[chave].add(id_sapl)
    unico: dict[str, int] = {}
    colisoes = []
    for chave, ids in sorted(indice.items()):
        if len(ids) != 1:
            colisoes.append((chave, sorted(ids)))
            continue
        unico[chave] = next(iter(ids))
    if colisoes:
        raise SystemExit(
            "Grafia de vereador bate em mais de uma pessoa: " + repr(colisoes)
        )
    return unico


def carregar_sessoes() -> list[dict]:
    if not ARQUIVO_CONTAGEM.exists():
        raise SystemExit(f"Arquivo nao encontrado: {ARQUIVO_CONTAGEM}")
    contagem = carregar_json(ARQUIVO_CONTAGEM)
    sessoes = contagem.get("sessoes") or []
    if len(sessoes) != N_SESSOES_ESPERADAS:
        raise SystemExit(
            f"A contagem oficial lista {len(sessoes)} sessoes, "
            f"nao {N_SESSOES_ESPERADAS}."
        )
    saida = []
    for item in sessoes:
        saida.append(
            {
                "id": int(item["id"]),
                "data": item["data"],
                "rotulo": item["rotulo"],
                "n_votacoes_contagem": int(item["n_votacoes"]),
                "link_sapl": LINK_SESSAO.format(id=int(item["id"])),
            }
        )
    return saida


def ids_presentes(caminho: Path) -> set[int]:
    if not caminho.exists():
        raise SystemExit(f"Arquivo nao encontrado: {caminho}")
    data = carregar_json(caminho)
    conferir_total(caminho, data)
    ids = set()
    for linha in resultados_de_lista(data):
        parlamentar = linha.get("parlamentar")
        if parlamentar is None:
            raise SystemExit(f"{caminho.name}: registro sem parlamentar.")
        ids.add(int(parlamentar))
    return ids


def ids_justificados(caminho: Path) -> set[int]:
    if not caminho.exists():
        raise SystemExit(f"Arquivo nao encontrado: {caminho}")
    data = carregar_json(caminho)
    conferir_total(caminho, data)
    ids = set()
    for linha in resultados_de_lista(data):
        parlamentar = linha.get("parlamentar")
        if parlamentar is None:
            raise SystemExit(f"{caminho.name}: justificativa sem parlamentar.")
        ids.add(int(parlamentar))
    return ids


def presidente_da_sessao(caminho: Path) -> int:
    if not caminho.exists():
        raise SystemExit(
            f"Arquivo da mesa nao encontrado: {caminho}. "
            "Sem a mesa nao da para dizer quem era presidente."
        )
    data = carregar_json(caminho)
    conferir_total(caminho, data)
    presidentes = []
    for linha in resultados_de_lista(data):
        if eh_presidente(linha):
            parlamentar = linha.get("parlamentar")
            if parlamentar is None:
                raise SystemExit(f"{caminho.name}: presidente sem parlamentar.")
            presidentes.append(int(parlamentar))
    if len(presidentes) != 1:
        raise SystemExit(
            f"{caminho.name}: achei {len(presidentes)} presidente(s) "
            f"({presidentes}). Precisa ser exatamente um, e nao vice."
        )
    return presidentes[0]


def carregar_registros(sessao: dict) -> dict[int, dict]:
    caminho = arquivo_sessao(sessao["id"], "registrovotacao")
    if not caminho.exists():
        raise SystemExit(f"Arquivo nao encontrado: {caminho}")
    data = carregar_json(caminho)
    conferir_total(caminho, data)
    registros = {}
    for linha in resultados_de_lista(data):
        registro_id = int(linha["id"])
        resultado = extrair_resultado(linha.get("__str__"))
        registros[registro_id] = {
            "id": registro_id,
            "sessao_id": sessao["id"],
            "data_sessao": sessao["data"],
            "rotulo_sessao": sessao["rotulo"],
            "materia_id": linha.get("materia"),
            "ordem": linha.get("ordem"),
            "data_hora": linha.get("data_hora"),
            "resultado_votacao": resultado,
            "situacao": situacao_do_resultado(resultado),
            "observacao": linha.get("observacao") or "",
            "numero_votos_sim": linha.get("numero_votos_sim"),
            "numero_votos_nao": linha.get("numero_votos_nao"),
            "numero_abstencoes": linha.get("numero_abstencoes"),
            "link_sessao": sessao["link_sapl"],
        }
        if linha.get("materia") is not None:
            registros[registro_id]["materia_id"] = int(linha["materia"])
            registros[registro_id]["link_materia"] = LINK_MATERIA.format(
                id=int(linha["materia"])
            )
    return registros


def carregar_votos(sessao: dict, presidente_id: int, registros: dict) -> list[dict]:
    caminho = arquivo_sessao(sessao["id"], "votoparlamentar")
    if not caminho.exists():
        raise SystemExit(f"Arquivo nao encontrado: {caminho}")
    data = carregar_json(caminho)
    conferir_total(caminho, data)
    votos = []
    for linha in resultados_de_lista(data):
        parlamentar = linha.get("parlamentar")
        if parlamentar is None:
            raise SystemExit(f"{caminho.name}: voto sem parlamentar.")
        id_sapl = int(parlamentar)
        voto_fonte = linha.get("voto")
        if voto_fonte is None or str(voto_fonte).strip() == "":
            raise SystemExit(
                f"{caminho.name}: voto sem valor para parlamentar {id_sapl}."
            )
        voto_fonte = str(voto_fonte)
        era_presidente = id_sapl == presidente_id
        votacao_id = linha.get("votacao")
        if votacao_id is not None:
            votacao_id = int(votacao_id)
            registro = registros.get(votacao_id)
            if registro is None:
                raise SystemExit(
                    f"{caminho.name}: voto com votacao_id {votacao_id} "
                    "nao existe no registrovotacao desta sessao."
                )
        else:
            registro = None
        materia_id = registro["materia_id"] if registro else None
        votos.append(
            {
                "id_sapl": id_sapl,
                "sessao_id": sessao["id"],
                "data_sessao": sessao["data"],
                "votacao_id": int(votacao_id) if votacao_id is not None else None,
                "materia_id": materia_id,
                "voto": voto_fonte,
                "classificacao": classificar_voto(voto_fonte, era_presidente),
                "era_presidente_na_sessao": era_presidente,
            }
        )
    return votos


def processar_sessoes(ids_banca: set[int], sessoes: list[dict]):
    por_vereador_presenca = {
        id_sapl: [] for id_sapl in ids_banca
    }
    votos_por_vereador = {id_sapl: [] for id_sapl in ids_banca}
    registros_por_materia: dict[int, list[dict]] = defaultdict(list)
    sessoes_saida = []
    divergencias_presenca = []
    presentes_e_justificados = []
    n_registros = 0
    n_votos = 0

    for sessao in sessoes:
        for sufixo in PACOTE_SESSAO:
            caminho = arquivo_sessao(sessao["id"], sufixo)
            if not caminho.exists():
                raise SystemExit(f"Falta o arquivo {caminho.name}.")

        plenaria = ids_presentes(arquivo_sessao(sessao["id"], "sessaoplenariapresenca"))
        ordem = ids_presentes(arquivo_sessao(sessao["id"], "presencaordemdia"))
        justificados = ids_justificados(
            arquivo_sessao(sessao["id"], "justificativaausencia")
        )
        presidente_id = presidente_da_sessao(
            arquivo_sessao(sessao["id"], "integrantemesa")
        )
        if presidente_id not in ids_banca:
            raise SystemExit(
                f"Sessao {sessao['id']}: presidente {presidente_id} "
                "nao esta na banca de 2026."
            )

        presentes = plenaria | ordem
        if plenaria != ordem:
            divergencias_presenca.append(
                {
                    "sessao_id": sessao["id"],
                    "so_plenaria": sorted(plenaria - ordem),
                    "so_ordem_dia": sorted(ordem - plenaria),
                }
            )

        situacoes = {}
        for id_sapl in sorted(ids_banca):
            if id_sapl in presentes:
                situacao = "presente"
            elif id_sapl in justificados:
                situacao = "falta_com_justificativa"
            else:
                situacao = "falta_sem_justificativa"
            if id_sapl in presentes and id_sapl in justificados:
                presentes_e_justificados.append(
                    {"sessao_id": sessao["id"], "id_sapl": id_sapl}
                )
            registro_presenca = {
                "sessao_id": sessao["id"],
                "data_sessao": sessao["data"],
                "rotulo": sessao["rotulo"],
                "situacao": situacao,
                "presente_sessao_plenaria": id_sapl in plenaria,
                "presente_ordem_dia": id_sapl in ordem,
                "justificativa": id_sapl in justificados,
                "era_presidente": id_sapl == presidente_id,
                "link_sessao": sessao["link_sapl"],
            }
            por_vereador_presenca[id_sapl].append(registro_presenca)
            situacoes[id_sapl] = situacao

        cobertos = set(presentes) | set(justificados)
        extra = cobertos - ids_banca
        if extra:
            raise SystemExit(
                f"Sessao {sessao['id']}: pessoa fora da banca de 15: {sorted(extra)}"
            )

        registros = carregar_registros(sessao)
        for registro in registros.values():
            materia_id = registro.get("materia_id")
            if materia_id is not None:
                registros_por_materia[int(materia_id)].append(registro)
        votos = carregar_votos(sessao, presidente_id, registros)
        for voto in votos:
            id_sapl = voto.pop("id_sapl")
            if id_sapl not in ids_banca:
                raise SystemExit(
                    f"Sessao {sessao['id']}: voto de parlamentar "
                    f"{id_sapl}, fora da banca."
                )
            votos_por_vereador[id_sapl].append(voto)

        n_registros += len(registros)
        n_votos += len(votos)
        sessao_saida = dict(sessao)
        sessao_saida.update(
            {
                "presidente_id_sapl": presidente_id,
                "n_presentes": len(presentes),
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
                "n_registros_votacao": len(registros),
                "n_votos_individuais": len(votos),
            }
        )
        sessoes_saida.append(sessao_saida)

    return {
        "sessoes": sessoes_saida,
        "presenca": por_vereador_presenca,
        "votos": votos_por_vereador,
        "registros_por_materia": registros_por_materia,
        "divergencias_presenca": divergencias_presenca,
        "presentes_e_justificados": presentes_e_justificados,
        "n_registros_votacao": n_registros,
        "n_votos_individuais": n_votos,
    }


def escolher_votacao(registros: list[dict]) -> dict:
    def chave(item: dict):
        return (
            item.get("data_sessao") or "",
            item.get("data_hora") or "",
            item.get("id") or 0,
        )

    return sorted(registros, key=chave)[-1]


def carregar_pll(indice_nomes: dict[str, int], por_id: dict[int, dict]) -> list[dict]:
    if not ARQUIVO_MATERIAS.exists():
        raise SystemExit(f"Arquivo nao encontrado: {ARQUIVO_MATERIAS}")
    projetos = []
    autorias_nao_vereador: Counter = Counter()
    with ARQUIVO_MATERIAS.open(encoding="utf-8-sig", newline="") as handle:
        leitor = csv.DictReader(handle, delimiter=";")
        for linha in leitor:
            sigla = (linha.get("Tipo de Matéria Legislativa/Sigla") or "").strip()
            descricao = (
                linha.get("Tipo de Matéria Legislativa/Descrição") or ""
            ).strip()
            if sigla != TIPO_PLL and descricao != DESCRICAO_PLL:
                continue
            materia_id = int(linha["ID"])
            ementa = linha.get("Ementa") or ""
            grafias = [
                parte.strip()
                for parte in (linha.get("Autorias") or "").split(",")
                if parte.strip()
            ]
            autores = []
            nao_vereador = []
            vistos = set()
            for grafia in grafias:
                id_sapl = indice_nomes.get(normalizar_nome(grafia))
                if id_sapl is None:
                    nao_vereador.append(grafia)
                    autorias_nao_vereador[grafia] += 1
                    continue
                if id_sapl in vistos:
                    continue
                vistos.add(id_sapl)
                vereador = por_id[id_sapl]
                autores.append(
                    {
                        "id_sapl": id_sapl,
                        "slug_codigo": vereador["slug_codigo"],
                        "nome_parlamentar": vereador["nome_parlamentar"],
                        "grafia_no_csv": grafia,
                    }
                )
            projetos.append(
                {
                    "id": materia_id,
                    "numero": linha.get("Número"),
                    "ano": linha.get("Ano"),
                    "tipo_sigla": sigla,
                    "tipo_descricao": descricao,
                    "ementa": ementa,
                    "categoria": classificar(ementa),
                    "classificador": "IA, por regras temáticas documentadas",
                    "revisada_por_humano": False,
                    "autoria_conjunta": len(autores) > 1,
                    "autores": autores,
                    "autorias_nao_vereador": nao_vereador,
                    "link_sapl": LINK_MATERIA.format(id=materia_id),
                    "texto_original": linha.get("Texto Original") or "",
                }
            )
    if len(projetos) != N_PLL_ESPERADOS:
        raise SystemExit(
            f"Esperava {N_PLL_ESPERADOS} Projetos de Lei do Legislativo, "
            f"achei {len(projetos)}."
        )
    ids = [item["id"] for item in projetos]
    if len(ids) != len(set(ids)):
        raise SystemExit("ID repetido entre os Projetos de Lei do Legislativo.")
    return projetos, [
        {"grafia": grafia, "vezes_no_csv": vezes}
        for grafia, vezes in sorted(autorias_nao_vereador.items())
    ]


def cruzar_projetos(projetos: list[dict], registros_por_materia: dict) -> None:
    for projeto in projetos:
        registros = registros_por_materia.get(projeto["id"], [])
        votacoes = []
        for registro in registros:
            if registro.get("resultado_votacao") is None:
                raise SystemExit(
                    f"Materia {projeto['id']}: registro {registro['id']} "
                    "sem resultado de votacao reconhecido."
                )
            votacoes.append(
                {
                    "sessao_id": registro["sessao_id"],
                    "data_sessao": registro["data_sessao"],
                    "rotulo_sessao": registro["rotulo_sessao"],
                    "registro_votacao_id": registro["id"],
                    "resultado_votacao": registro["resultado_votacao"],
                    "situacao": registro["situacao"],
                    "link_sessao": registro["link_sessao"],
                }
            )
        projeto["votacoes_ordinarias"] = votacoes
        if not votacoes:
            projeto["situacao"] = "Em tramitacao"
            projeto["data_sessao"] = None
            projeto["resultado_votacao"] = None
            projeto["sessao_id"] = None
            continue
        escolhida = escolher_votacao(registros)
        if escolhida["situacao"] is None:
            raise SystemExit(
                f"Materia {projeto['id']}: resultado "
                f"{escolhida['resultado_votacao']} nao vira Aprovado/Rejeitado."
            )
        projeto["situacao"] = escolhida["situacao"]
        projeto["data_sessao"] = escolhida["data_sessao"]
        projeto["resultado_votacao"] = escolhida["resultado_votacao"]
        projeto["sessao_id"] = escolhida["sessao_id"]


def consolidar_presenca(lista: list[dict]) -> dict:
    contagem = Counter(item["situacao"] for item in lista)
    presencas = contagem.get("presente", 0)
    faltas_just = contagem.get("falta_com_justificativa", 0)
    faltas_sem = contagem.get("falta_sem_justificativa", 0)
    faltas_totais = faltas_just + faltas_sem
    total = len(lista)
    if total != N_SESSOES_ESPERADAS:
        raise SystemExit(f"Presenca com {total} sessoes, nao {N_SESSOES_ESPERADAS}.")
    if presencas + faltas_totais != total:
        raise SystemExit("Presenca + faltas nao fecha o total de sessoes.")
    return {
        "sessoes_ordinarias": total,
        "presencas": presencas,
        "faltas_com_justificativa": faltas_just,
        "faltas_sem_justificativa": faltas_sem,
        "faltas_totais": faltas_totais,
        "percentual_faltas": percentual(faltas_totais, total),
        "taxa_presenca": percentual(presencas, total),
        "por_sessao": lista,
    }


def consolidar_votos(lista: list[dict]) -> dict:
    contagem = Counter(item["classificacao"] for item in lista)
    fonte = Counter(item["voto"] for item in lista)
    resultado = {
        "sim": contagem.get("sim", 0),
        "nao": contagem.get("nao", 0),
        "abstencao": contagem.get("abstencao", 0),
        "presidente_nao_votou": contagem.get("presidente_nao_votou", 0),
        "nao_votou_nao_era_presidente": contagem.get(
            "nao_votou_nao_era_presidente", 0
        ),
        "ausente": contagem.get("ausente", 0),
        "outro": contagem.get("outro", 0),
        "total_registros": len(lista),
        "por_texto_da_fonte": dict(sorted(fonte.items())),
        "nominais": lista,
    }
    soma = (
        resultado["sim"]
        + resultado["nao"]
        + resultado["abstencao"]
        + resultado["presidente_nao_votou"]
        + resultado["nao_votou_nao_era_presidente"]
        + resultado["ausente"]
        + resultado["outro"]
    )
    if soma != resultado["total_registros"]:
        raise SystemExit(
            "Contagem de votos nao fecha: "
            f"soma das classificacoes {soma} != "
            f"total_registros {resultado['total_registros']}."
        )
    return resultado


def resumo_projeto(projeto: dict, id_sapl: int) -> dict:
    papel = next(
        (autor["grafia_no_csv"] for autor in projeto["autores"] if autor["id_sapl"] == id_sapl),
        None,
    )
    return {
        "id": projeto["id"],
        "numero": projeto["numero"],
        "ano": projeto["ano"],
        "ementa": projeto["ementa"],
        "categoria": projeto["categoria"],
        "classificador": projeto["classificador"],
        "revisada_por_humano": projeto["revisada_por_humano"],
        "situacao": projeto["situacao"],
        "data_sessao": projeto["data_sessao"],
        "resultado_votacao": projeto["resultado_votacao"],
        "sessao_id": projeto["sessao_id"],
        "autoria_conjunta": projeto["autoria_conjunta"],
        "grafia_no_csv": papel,
        "n_autores_vereadores": len(projeto["autores"]),
        "link_sapl": projeto["link_sapl"],
    }


def consolidar_projetos(id_sapl: int, projetos: list[dict]) -> dict:
    lista = [
        resumo_projeto(projeto, id_sapl)
        for projeto in projetos
        if any(autor["id_sapl"] == id_sapl for autor in projeto["autores"])
    ]
    lista.sort(key=lambda item: (int(item["numero"]), item["id"]))
    por_categoria = {tema: 0 for tema in CATEGORIAS}
    for item in lista:
        por_categoria[item["categoria"]] = por_categoria.get(item["categoria"], 0) + 1
    return {
        "total_propostos": len(lista),
        "aprovados": sum(1 for item in lista if item["situacao"] == "Aprovado"),
        "rejeitados": sum(1 for item in lista if item["situacao"] == "Rejeitado"),
        "em_tramitacao": sum(
            1 for item in lista if item["situacao"] == "Em tramitacao"
        ),
        "autorias_individuais": sum(
            1 for item in lista if not item["autoria_conjunta"]
        ),
        "autorias_conjuntas": sum(1 for item in lista if item["autoria_conjunta"]),
        "por_categoria": por_categoria,
        "lista": lista,
    }


def temas_globais(projetos: list[dict]) -> dict[str, int]:
    contagem = Counter(item["categoria"] for item in projetos)
    return {tema: contagem.get(tema, 0) for tema in CATEGORIAS}


def escrever_json(payload: dict) -> None:
    texto = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    with ARQUIVO_JSON.open("w", encoding="utf-8", newline="\n") as f:
        f.write(texto)


def escrever_csv(vereadores: list[dict]) -> None:
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
        "presencas",
        "faltas_com_justificativa",
        "faltas_sem_justificativa",
        "faltas_totais",
        "percentual_faltas",
        "taxa_presenca",
        "votos_sim",
        "votos_nao",
        "votos_abstencao",
        "presidente_nao_votou",
        "nao_votou_nao_era_presidente",
        "votos_ausente",
        "votos_outro",
        "votos_total_registros",
        "projetos_propostos",
        "projetos_aprovados",
        "projetos_rejeitados",
        "projetos_em_tramitacao",
        "projetos_por_categoria",
    ]
    with ARQUIVO_CSV.open("w", encoding="utf-8", newline="") as handle:
        escritor = csv.DictWriter(handle, fieldnames=campos, delimiter=";")
        escritor.writeheader()
        for item in vereadores:
            presenca = item["presenca"]
            votos = item["votos"]
            projetos = item["projetos_lei"]
            temas = " | ".join(
                f"{tema}:{quantidade}"
                for tema, quantidade in projetos["por_categoria"].items()
                if quantidade
            )
            escritor.writerow(
                {
                    "id_sapl": item["id_sapl"],
                    "slug_codigo": item["slug_codigo"],
                    "nome_parlamentar": item["nome_parlamentar"],
                    "nome_oficial": item["nome_oficial"],
                    "partido_sigla": item["partido_sigla"] or "",
                    "partido_nome": item["partido_nome"] or "",
                    "foto_url": item["foto_url"] or "",
                    "link_sapl": item["link_sapl"],
                    "sessoes_ordinarias": presenca["sessoes_ordinarias"],
                    "presencas": presenca["presencas"],
                    "faltas_com_justificativa": presenca["faltas_com_justificativa"],
                    "faltas_sem_justificativa": presenca["faltas_sem_justificativa"],
                    "faltas_totais": presenca["faltas_totais"],
                    "percentual_faltas": f"{presenca['percentual_faltas']:.2f}".replace(
                        ".", ","
                    ),
                    "taxa_presenca": f"{presenca['taxa_presenca']:.2f}".replace(
                        ".", ","
                    ),
                    "votos_sim": votos["sim"],
                    "votos_nao": votos["nao"],
                    "votos_abstencao": votos["abstencao"],
                    "presidente_nao_votou": votos["presidente_nao_votou"],
                    "nao_votou_nao_era_presidente": votos[
                        "nao_votou_nao_era_presidente"
                    ],
                    "votos_ausente": votos["ausente"],
                    "votos_outro": votos["outro"],
                    "votos_total_registros": votos["total_registros"],
                    "projetos_propostos": projetos["total_propostos"],
                    "projetos_aprovados": projetos["aprovados"],
                    "projetos_rejeitados": projetos["rejeitados"],
                    "projetos_em_tramitacao": projetos["em_tramitacao"],
                    "projetos_por_categoria": temas,
                }
            )


def vezes_em_palavras(n: int) -> str:
    if n == 1:
        return "1 vez"
    return f"{n} vezes"


def pct(valor: float) -> str:
    return f"{valor:.2f}".replace(".", ",")


def frase_temas(por_categoria: dict) -> str:
    partes = [
        f"{tema} ({quantidade})"
        for tema, quantidade in por_categoria.items()
        if quantidade
    ]
    if not partes:
        return "nenhum projeto de lei do Legislativo neste recorte"
    if len(partes) == 1:
        return partes[0]
    return ", ".join(partes[:-1]) + " e " + partes[-1]


def frase_projetos_vereador(pl: dict) -> str:
    total = pl["total_propostos"]
    if total == 0:
        return (
            "Não apresentou Projeto de Lei do Legislativo neste recorte de 2026."
        )
    elif total == 1:
        inicio = "Apresentou 1 Projeto de Lei do Legislativo em 2026."
    else:
        inicio = (
            f"Apresentou {total} Projetos de Lei do Legislativo em 2026."
        )
    return (
        f"{inicio} Aprovados em sessão ordinária: {pl['aprovados']}. "
        f"Rejeitados: {pl['rejeitados']}. Em tramitação: {pl['em_tramitacao']}."
    )


def escrever_relatorio(payload: dict) -> None:
    meta = payload["meta"]
    vereadores = payload["vereadores"]
    projetos = payload["projetos_lei_legislativo"]
    n_aprovados = sum(1 for item in projetos if item["situacao"] == "Aprovado")
    n_rejeitados = sum(1 for item in projetos if item["situacao"] == "Rejeitado")
    n_tramitacao = sum(1 for item in projetos if item["situacao"] == "Em tramitacao")
    n_mesa = sum(1 for item in projetos if not item["autores"])
    n_conjuntos = sum(1 for item in projetos if item["autoria_conjunta"])
    temas = meta["projetos_por_categoria"]
    linhas = [
        "# Atuação dos vereadores nas sessões ordinárias de 2026",
        "",
        f"Gerado em: {meta['gerado_em']}",
        f"Dado coletado em: {meta['dado_coletado_em']}",
        "Script: `dados/tratados/gerar_atuacao_vereadores_2026.py`",
        "Fonte: arquivos oficiais guardados em `dados/brutos/` e a tabela única `dados/tratados/vereadores.json`. Nada foi inventado na mão.",
        "",
        "## Em uma frase",
        "",
        (
            f"Nas {meta['n_sessoes_ordinarias']} sessões ordinárias de 2026, "
            f"os {meta['n_vereadores']} vereadores da legislatura atual tiveram "
            "presença, voto e projetos de lei consolidados a partir do sistema "
            "oficial da Câmara (SAPL)."
        ),
        "",
        (
            "Sessão ordinária: o encontro regular da Câmara, às segundas. "
            "Projeto de lei do Legislativo: proposta de lei apresentada por "
            "vereador ou pela mesa da Câmara, não pela Prefeitura."
        ),
        "",
        "## O que este recorte cobre",
        "",
        (
            "Só 2026. Só sessão ordinária. A sessão extraordinária 768 "
            "(26/01/2026) ficou de fora de propósito: ela serve de prova de "
            "falta justificada, mas não entra nesses 26 encontros."
        ),
        "",
        (
            "A sessão 795 (14/09/2026) tinha zero votações na contagem "
            "feita em 14/09. Os arquivos de voto baixados depois já trazem "
            "16 registros. Este consolidado usa os arquivos de voto, não o "
            "zero antigo."
        ),
        "",
        (
            f"Os 100 Projetos de Lei do Legislativo vieram da planilha "
            f"`materias-2026-resposta-original.csv`. Desses 100, {n_aprovados} "
            f"já foram votados e aprovados em sessão ordinária, {n_rejeitados} "
            f"foram rejeitados e {n_tramitacao} ainda estão em tramitação "
            "(tramitação: o projeto continua andando na Câmara e ainda não "
            "foi votado em sessão ordinária até a data da coleta)."
        ),
        "",
        (
            f"{n_mesa} desses 100 projetos não têm vereador como autor no "
            "campo de autoria: a fonte aponta a Mesa Executiva. Eles entram "
            "no total da Câmara e não na lista de nenhum dos 15."
        ),
        "",
        (
            f"{n_conjuntos} projetos têm mais de um nome no campo de autoria "
            "(coautoria: dois ou mais vereadores assinam o mesmo projeto). "
            "Nesse caso o projeto conta para cada autor. Por isso a soma das "
            "listas individuais passa de 100. O total da Câmara, sem repetir "
            "projeto, continua 100."
        ),
        "",
        "## Como a presença foi lida",
        "",
        (
            "Presente: o vereador aparece na lista de presença da sessão "
            "(`sessaoplenariapresenca`) ou na lista de presença da ordem do "
            "dia (ordem do dia: a pauta do que vai ser votado naquela sessão)."
        ),
        "",
        (
            "Falta com justificativa: o vereador está na lista de "
            "justificativa de ausência e não está em nenhuma das duas listas "
            "de presença."
        ),
        "",
        (
            "Falta sem justificativa: o vereador não está na presença e não "
            "está na justificativa. O método existe. Nas 26 sessões "
            "ordinárias deste recorte, esse caso "
            + (
                "não apareceu."
                if meta["n_faltas_sem_justificativa"] == 0
                else f"apareceu {meta['n_faltas_sem_justificativa']} "
                f"{'vez' if meta['n_faltas_sem_justificativa'] == 1 else 'vezes'}."
            )
        ),
        "",
        (
            "As duas listas de presença bateram em todas as 26 sessões."
            if not meta["sessoes_com_presenca_divergente"]
            else (
                "Houve sessão em que a presença da sessão e a presença da "
                "ordem do dia não eram a mesma lista. O detalhe está no JSON, "
                "campo `sessoes_com_presenca_divergente`. Quem apareceu em "
                "qualquer uma das duas foi contado como presente."
            )
        ),
        "",
        "## Como o voto foi lido",
        "",
        (
            "Cada linha de `votoparlamentar` é um voto de uma pessoa em uma "
            "votação. Os textos da fonte foram mantidos: Sim, Não, Abstenção, "
            "Não Votou, Ausente."
        ),
        "",
        (
            "Abstenção (abstenção: o vereador estava lá e escolheu não dizer "
            "sim nem não) só conta quando a própria fonte escreve a palavra "
            "Abstenção. Neste recorte isso apareceu "
            f"{meta['n_votos_abstencao']} "
            f"{'vez' if meta['n_votos_abstencao'] == 1 else 'vezes'}."
        ),
        "",
        (
            "Presidente que não votou: só quando a pessoa era PRESIDENTE na "
            "mesa daquela sessão (não vice) e o voto veio `Não Votou`. A "
            "palavra `Não Votou` sozinha não basta. Há vereador que não era "
            "presidente e mesmo assim veio `Não Votou`. Há sessão em que o "
            "presidente votou de verdade. Os dois casos ficam separados."
        ),
        "",
        "## Classificação por tema",
        "",
        (
            "O tema de cada um dos 100 projetos foi proposto por programa, "
            "com as mesmas regras de palavra-chave de "
            "`dados/tratados/gerar_temas_votacoes_2026.py`. Isso não foi "
            "revisado por uma pessoa. Número de 'prioridade da Câmara' a "
            "partir dessa classificação não vai ao ar."
        ),
        "",
        "Distribuição dos 100 Projetos de Lei do Legislativo por tema:",
        "",
    ]
    for tema, quantidade in temas.items():
        linhas.append(f"- {tema}: {quantidade}")
    linhas.extend(
        [
            "",
            "## Presença de cada vereador",
            "",
            (
                "A ordem abaixo é a ordem da tabela única, pelo número "
                "oficial do SAPL. Não é ranking."
            ),
            "",
        ]
    )
    for item in vereadores:
        p = item["presenca"]
        linhas.extend(
            [
                f"### {item['nome_parlamentar']}",
                "",
                f"Partido: {item['partido_sigla']} ({item['partido_nome']})",
                "",
                f"Foto oficial: {item['foto_url']}",
                "",
                f"Página oficial: {item['link_sapl']}",
                "",
                (
                    f"Esteve presente em {p['presencas']} das "
                    f"{p['sessoes_ordinarias']} sessões ordinárias "
                    f"(taxa de presença {pct(p['taxa_presenca'])}%)."
                ),
                "",
                (
                    (
                        "Não faltou a nenhuma das 26 sessões. "
                        if p["faltas_totais"] == 0
                        else (
                            f"Faltou a {p['faltas_totais']} das 26 sessões. "
                            f"Com justificativa: {p['faltas_com_justificativa']}. "
                            f"Sem justificativa: {p['faltas_sem_justificativa']}. "
                        )
                    )
                    + (
                        f"Porcentagem de sessões em que faltou: "
                        f"{pct(p['percentual_faltas'])}%."
                    )
                ),
                "",
            ]
        )
        if p["faltas_totais"]:
            faltas = [
                sessao
                for sessao in p["por_sessao"]
                if sessao["situacao"] != "presente"
            ]
            for falta in faltas:
                tipo = (
                    "falta com justificativa"
                    if falta["situacao"] == "falta_com_justificativa"
                    else "falta sem justificativa"
                )
                linhas.append(
                    f"- {falta['data_sessao']}, {falta['rotulo']}: {tipo}. "
                    f"Fonte: {falta['link_sessao']}"
                )
            linhas.append("")
    linhas.extend(
        [
            "## Votos nominais consolidados",
            "",
            (
                "Voto nominal: o sistema registra o voto de cada vereador, "
                "com nome, em cada matéria votada. Não é voto secreto."
            ),
            "",
        ]
    )
    for item in vereadores:
        v = item["votos"]
        linhas.extend(
            [
                f"### {item['nome_parlamentar']}",
                "",
                f"- Sim: {v['sim']}",
                f"- Não: {v['nao']}",
                f"- Abstenção: {v['abstencao']}",
                (
                    f"- Presidente que não votou (cruzamento mesa + Não Votou): "
                    f"{v['presidente_nao_votou']}"
                ),
                (
                    f"- Não votou, e não era presidente naquela sessão: "
                    f"{v['nao_votou_nao_era_presidente']}"
                ),
                f"- Ausente no campo de voto: {v['ausente']}",
                f"- Total de registros de voto deste vereador: {v['total_registros']}",
                "",
            ]
        )
    linhas.extend(
        [
            "## Projetos de Lei do Legislativo de cada vereador",
            "",
            (
                "Aqui só entra Projeto de Lei do Legislativo de 2026. "
                "Requerimento, moção, veto e projeto da Prefeitura não entram "
                "nesta lista, embora o voto neles entre na conta de votos "
                "nominais acima."
            ),
            "",
        ]
    )
    for item in vereadores:
        pl = item["projetos_lei"]
        linhas.extend(
            [
                f"### {item['nome_parlamentar']}",
                "",
                frase_projetos_vereador(pl),
                "",
                f"Temas (classificação por IA, não revisada): {frase_temas(pl['por_categoria'])}.",
                "",
            ]
        )
        if not pl["lista"]:
            linhas.append("Nenhum projeto de lei do Legislativo com a autoria desta pessoa neste recorte.")
            linhas.append("")
            continue
        for projeto in pl["lista"]:
            if projeto["situacao"] == "Em tramitacao":
                situacao = "Em tramitação (ainda não votado em sessão ordinária até a data da coleta)"
            elif projeto["situacao"] == "Aprovado":
                situacao = (
                    f"Aprovado em {projeto['data_sessao']} "
                    f"({projeto['resultado_votacao']})"
                )
            elif projeto["situacao"] == "Rejeitado":
                situacao = (
                    f"Rejeitado em {projeto['data_sessao']} "
                    f"({projeto['resultado_votacao']})"
                )
            else:
                situacao = projeto["situacao"]
            conjunto = "sim" if projeto["autoria_conjunta"] else "não"
            linhas.append(
                f"- PLL {projeto['numero']}/{projeto['ano']} "
                f"(id {projeto['id']}): {projeto['ementa']} "
                f"Tema: {projeto['categoria']}. Situação: {situacao}. "
                f"Autoria conjunta: {conjunto}. "
                f"Fonte: {projeto['link_sapl']}"
            )
        linhas.append("")
    linhas.extend(
        [
            "## Totais da Câmara neste recorte",
            "",
            f"- Sessões ordinárias: {meta['n_sessoes_ordinarias']}",
            f"- Vereadores: {meta['n_vereadores']}",
            f"- Presenças somadas (cada vereador em cada sessão): {meta['n_presencas']}",
            f"- Faltas com justificativa somadas: {meta['n_faltas_com_justificativa']}",
            f"- Faltas sem justificativa somadas: {meta['n_faltas_sem_justificativa']}",
            f"- Registros de votação baixados: {meta['n_registros_votacao']}",
            f"- Votos individuais baixados: {meta['n_votos_individuais']}",
            f"- Projetos de Lei do Legislativo de 2026: {meta['n_pll_2026']}",
            f"- Desses, aprovados em sessão ordinária: {n_aprovados}",
            f"- Desses, rejeitados em sessão ordinária: {n_rejeitados}",
            f"- Desses, em tramitação: {n_tramitacao}",
            "",
            "## O que ficou de fora, de propósito",
            "",
            "- Sessão extraordinária.",
            "- Projeto de Lei do Executivo (proposta da Prefeitura).",
            "- Requerimento, moção, veto e outros tipos, na lista de projetos. O voto neles entra na conta de votos.",
            "- Projeto de lei de 2025 votado em 2026 (por exemplo o PLL 110/2025, rejeitado na sessão 776). Ele não entra nos 100 de 2026.",
            "",
            "## Como repetir",
            "",
            "Na pasta do projeto, rode:",
            "",
            "    python dados/tratados/gerar_atuacao_vereadores_2026.py",
            "",
            (
                "O programa lê os brutos de novo e reescreve "
                "`atuacao_vereadores_2026.json`, "
                "`atuacao_vereadores_2026.csv` e este relatório. "
                "Não edite esses três arquivos na mão."
            ),
            "",
        ]
    )
    texto_relatorio = "\n".join(linhas).replace("\r\n", "\n").replace("\r", "\n")
    with ARQUIVO_RELATORIO.open("w", encoding="utf-8", newline="\n") as f:
        f.write(texto_relatorio)


def main() -> None:
    if not DIR_BRUTOS.is_dir():
        raise SystemExit(f"Pasta de brutos nao encontrada: {DIR_BRUTOS}")
    if not ARQUIVO_VEREADORES.exists():
        raise SystemExit(f"Tabela de vereadores nao encontrada: {ARQUIVO_VEREADORES}")

    tabela = carregar_json(ARQUIVO_VEREADORES)
    vereadores_base = tabela["vereadores"]
    if len(vereadores_base) != N_VEREADORES_ESPERADOS:
        raise SystemExit(
            f"A tabela unica tem {len(vereadores_base)} vereadores, "
            f"nao {N_VEREADORES_ESPERADOS}."
        )
    por_id = {int(item["id_sapl"]): item for item in vereadores_base}
    ids_banca = set(por_id)
    indice_nomes = montar_indice_nomes(vereadores_base)
    sessoes = carregar_sessoes()
    bruto_sessoes = processar_sessoes(ids_banca, sessoes)
    projetos, autorias_nao_vereador = carregar_pll(indice_nomes, por_id)
    cruzar_projetos(projetos, bruto_sessoes["registros_por_materia"])

    vereadores = []
    for base in vereadores_base:
        id_sapl = int(base["id_sapl"])
        partido_sigla, partido_nome, foto_url = conferir_partido_e_foto(base)
        presenca = consolidar_presenca(bruto_sessoes["presenca"][id_sapl])
        votos = consolidar_votos(bruto_sessoes["votos"][id_sapl])
        projetos_lei = consolidar_projetos(id_sapl, projetos)
        if (
            projetos_lei["aprovados"]
            + projetos_lei["rejeitados"]
            + projetos_lei["em_tramitacao"]
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
    if n_presencas + n_faltas_j + n_faltas_s != N_SESSOES_ESPERADAS * N_VEREADORES_ESPERADOS:
        raise SystemExit("A grade de presenca 15 x 26 nao fecha.")

    n_abstencao = sum(item["votos"]["abstencao"] for item in vereadores)
    dado_coletado_em, fonte_data_coleta = ler_dado_coletado_em()
    payload = {
        "meta": {
            "gerado_em": dado_coletado_em,
            "gerado_por": "dados/tratados/gerar_atuacao_vereadores_2026.py",
            "dado_coletado_em": dado_coletado_em,
            "fonte_data_coleta": fonte_data_coleta,
            "n_sessoes_ordinarias": N_SESSOES_ESPERADAS,
            "n_vereadores": N_VEREADORES_ESPERADOS,
            "n_pll_2026": len(projetos),
            "n_presencas": n_presencas,
            "n_faltas_com_justificativa": n_faltas_j,
            "n_faltas_sem_justificativa": n_faltas_s,
            "n_registros_votacao": bruto_sessoes["n_registros_votacao"],
            "n_votos_individuais": bruto_sessoes["n_votos_individuais"],
            "n_votos_abstencao": n_abstencao,
            "sessoes_com_presenca_divergente": bruto_sessoes["divergencias_presenca"],
            "presentes_com_justificativa_na_mesma_sessao": bruto_sessoes[
                "presentes_e_justificados"
            ],
            "autorias_pll_que_nao_sao_vereador": autorias_nao_vereador,
            "projetos_por_categoria": temas_globais(projetos),
            "classificador_temas": "IA, por regras temáticas documentadas",
            "revisada_por_humano": False,
            "observacao": (
                "Ausência não é voto. Presidente que não votou só conta com "
                "cruzamento da mesa daquela sessão (cargo PRESIDENTE, não vice) "
                "e voto Não Votou. Falta com justificativa e falta sem "
                "justificativa ficam em rótulos separados."
            ),
        },
        "sessoes": bruto_sessoes["sessoes"],
        "projetos_lei_legislativo": projetos,
        "vereadores": vereadores,
    }
    escrever_json(payload)
    escrever_csv(vereadores)
    escrever_relatorio(payload)
    print(
        f"Atuacao gerada: {len(vereadores)} vereadores, "
        f"{len(sessoes)} sessoes, {len(projetos)} PLL."
    )
    print(f"  {ARQUIVO_JSON}")
    print(f"  {ARQUIVO_CSV}")
    print(f"  {ARQUIVO_RELATORIO}")


if __name__ == "__main__":
    main()
