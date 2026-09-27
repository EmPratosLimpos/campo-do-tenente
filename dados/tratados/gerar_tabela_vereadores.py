"""Gera a tabela unica de vereadores a partir dos dados brutos.

Le apenas arquivos em dados/brutos/. Nao inventa vereador, apelido,
partido nem foto. Partido e foto saem do cadastro oficial do SAPL.
Rode de novo: o resultado tem que ser o mesmo.

Uso:
    python dados/tratados/gerar_tabela_vereadores.py
"""

from __future__ import annotations

import csv
import json
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

DIR_SCRIPT = Path(__file__).resolve().parent
DIR_BRUTOS = DIR_SCRIPT.parent / "brutos"

BANCA_REFERENCIA_2026 = [
    47,
    49,
    50,
    51,
    53,
    55,
    56,
    57,
    58,
    59,
    60,
    61,
    62,
    63,
    64,
]

CSV_AUTORIA = "materias-2026-resposta-original.csv"
ARQUIVO_PARTIDO = DIR_BRUTOS / "api_parlamentares_partido.json"
ARQUIVO_FILIACAO = DIR_BRUTOS / "api_parlamentares_filiacao.json"
ARQUIVO_JSON = DIR_SCRIPT / "vereadores.json"
ARQUIVO_CSV = DIR_SCRIPT / "vereadores.csv"
ARQUIVO_RELATORIO = DIR_SCRIPT / "RELATORIO-TABELA-VEREADORES.md"

CARGOS_MESA_PREFIXO = re.compile(
    r"^(PRESIDENTE|1º VICE-PRESIDENTE|2º VICE-PRESIDENTE|"
    r"1º SECRETÁRIO|2º SECRETÁRIO)\s*-\s*",
    re.IGNORECASE,
)


def agora_iso() -> str:
    try:
        agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
    except Exception:
        agora = datetime.now(timezone.utc).astimezone()
    return agora.isoformat(timespec="seconds")


def slugify(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto or "")
    sem_acento = "".join(c for c in nfkd if not unicodedata.combining(c))
    limpo = re.sub(r"[^a-z0-9]+", "-", sem_acento.lower())
    return limpo.strip("-")


def normalizar(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", (texto or "").strip())
    sem_acento = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sem_acento.casefold())


def carregar_json(caminho: Path):
    return json.loads(caminho.read_text(encoding="utf-8"))


def nome_do_voto(texto: str | None) -> str | None:
    if not texto:
        return None
    achado = re.search(r"Parlamentar:\s*(.+)$", texto)
    if not achado:
        return None
    nome = achado.group(1).strip()
    return nome or None


def nome_da_mesa(texto: str | None) -> str | None:
    if not texto:
        return None
    sem_cargo = CARGOS_MESA_PREFIXO.sub("", texto).strip()
    if sem_cargo and sem_cargo != texto.strip():
        return sem_cargo
    if " - " in texto:
        return texto.rsplit(" - ", 1)[-1].strip() or None
    return None


def nome_da_presenca(texto: str | None) -> str | None:
    return nome_do_voto(texto)


def resultados_de_lista(data) -> list:
    if isinstance(data, dict) and isinstance(data.get("results"), list):
        return data["results"]
    if isinstance(data, list):
        return data
    return []


def registrar_apelido(destino, id_sapl: int, grafia: str, fonte: str) -> None:
    nome = (grafia or "").strip()
    if not nome:
        return
    destino[id_sapl][nome].add(fonte)


def ler_cadastro() -> dict[int, dict]:
    cadastro: dict[int, dict] = {}
    arquivos = sorted(DIR_BRUTOS.glob("sessao_*_parlamentares.json"))
    if not arquivos:
        raise SystemExit("Nenhum arquivo sessao_*_parlamentares.json em dados/brutos/.")
    for caminho in arquivos:
        data = carregar_json(caminho)
        if not isinstance(data, dict):
            continue
        for chave, registro in data.items():
            if not isinstance(registro, dict):
                continue
            try:
                id_sapl = int(registro.get("id", chave))
            except (TypeError, ValueError):
                continue
            foto = (registro.get("fotografia") or "").strip()
            if id_sapl not in cadastro:
                cadastro[id_sapl] = {
                    "id_sapl": id_sapl,
                    "nome_oficial": (registro.get("nome_completo") or "").strip(),
                    "nome_parlamentar": (registro.get("nome_parlamentar") or "").strip(),
                    "str_sapl": (registro.get("__str__") or "").strip(),
                    "ativo_cadastro_sapl": registro.get("ativo"),
                    "link_detail_backend": registro.get("link_detail_backend") or "",
                    "fotografia": foto,
                }
                continue
            foto_existente = cadastro[id_sapl].get("fotografia") or ""
            if foto and foto_existente and foto != foto_existente:
                raise SystemExit(
                    f"Foto oficial divergente para o parlamentar {id_sapl}: "
                    f"{foto_existente} e {foto}."
                )
            if foto and not foto_existente:
                cadastro[id_sapl]["fotografia"] = foto
    return cadastro


def carregar_partidos() -> dict[int, dict]:
    if not ARQUIVO_PARTIDO.exists():
        raise SystemExit(f"Arquivo de partidos nao encontrado: {ARQUIVO_PARTIDO}")
    data = carregar_json(ARQUIVO_PARTIDO)
    partidos = {}
    for linha in resultados_de_lista(data):
        if not isinstance(linha, dict):
            continue
        try:
            partido_id = int(linha["id"])
        except (KeyError, TypeError, ValueError):
            continue
        partidos[partido_id] = {
            "sigla": (linha.get("sigla") or "").strip(),
            "nome": (linha.get("nome") or "").strip(),
        }
    if not partidos:
        raise SystemExit("Nenhum partido encontrado em api_parlamentares_partido.json.")
    return partidos


def escolher_filiacao_vigente(filiacoes: list[dict]) -> dict | None:
    if not filiacoes:
        return None
    vigentes = [item for item in filiacoes if item.get("data_desfiliacao") is None]
    candidatas = vigentes if vigentes else filiacoes

    def chave(item: dict):
        return (item.get("data") or "", int(item.get("id") or 0))

    return sorted(candidatas, key=chave)[-1]


def carregar_filiacoes_vigentes(partidos: dict[int, dict]) -> dict[int, dict]:
    if not ARQUIVO_FILIACAO.exists():
        raise SystemExit(f"Arquivo de filiacao nao encontrado: {ARQUIVO_FILIACAO}")
    data = carregar_json(ARQUIVO_FILIACAO)
    por_parlamentar: dict[int, list[dict]] = defaultdict(list)
    for linha in resultados_de_lista(data):
        if not isinstance(linha, dict):
            continue
        parlamentar = linha.get("parlamentar")
        if parlamentar is None:
            continue
        por_parlamentar[int(parlamentar)].append(linha)

    vigentes: dict[int, dict] = {}
    for id_sapl, lista in por_parlamentar.items():
        escolhida = escolher_filiacao_vigente(lista)
        if escolhida is None:
            continue
        partido_id = escolhida.get("partido")
        if partido_id is None:
            raise SystemExit(
                f"Filiacao {escolhida.get('id')} do parlamentar {id_sapl} sem partido."
            )
        partido = partidos.get(int(partido_id))
        if partido is None:
            raise SystemExit(
                f"Partido {partido_id} da filiacao do parlamentar {id_sapl} "
                "nao esta em api_parlamentares_partido.json."
            )
        if not partido["sigla"] or not partido["nome"]:
            raise SystemExit(
                f"Partido {partido_id} veio sem sigla ou sem nome no cadastro oficial."
            )
        vigentes[id_sapl] = {
            "partido_sigla": partido["sigla"],
            "partido_nome": partido["nome"],
        }
    return vigentes


def varrer_sessoes(cadastro: dict[int, dict], apelidos: dict) -> set[int]:
    ids_em_2026: set[int] = set()
    leitores = {
        "votoparlamentar": ("voto", nome_do_voto),
        "integrantemesa": ("mesa", nome_da_mesa),
        "presencaordemdia": ("presenca_ordem_dia", nome_da_presenca),
        "sessaoplenariapresenca": ("presenca_sessao", None),
        "justificativaausencia": ("justificativa_ausencia", None),
    }
    for sufixo, (fonte, extrator) in leitores.items():
        for caminho in sorted(DIR_BRUTOS.glob(f"sessao_*_{sufixo}.json")):
            data = carregar_json(caminho)
            for linha in resultados_de_lista(data):
                if not isinstance(linha, dict):
                    continue
                parlamentar = linha.get("parlamentar")
                if parlamentar is None:
                    continue
                id_sapl = int(parlamentar)
                ids_em_2026.add(id_sapl)
                if extrator:
                    nome = extrator(linha.get("__str__"))
                    if nome:
                        registrar_apelido(apelidos, id_sapl, nome, fonte)
    return ids_em_2026


def montar_indice_nomes(cadastro: dict[int, dict], apelidos: dict) -> dict[str, int]:
    indice: dict[str, set[int]] = defaultdict(set)
    for id_sapl, dados in cadastro.items():
        for campo in ("nome_oficial", "nome_parlamentar", "str_sapl"):
            chave = normalizar(dados.get(campo, ""))
            if chave:
                indice[chave].add(id_sapl)
        for grafia in apelidos.get(id_sapl, {}):
            chave = normalizar(grafia)
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
            "Grafia normalizada bate em mais de um vereador: " + repr(colisoes)
        )
    return unico


def varrer_autoria(indice: dict[str, int], apelidos: dict) -> list[dict]:
    caminho = DIR_BRUTOS / CSV_AUTORIA
    if not caminho.exists():
        raise SystemExit(f"Arquivo de autoria nao encontrado: {caminho}")
    nao_vereador: dict[str, int] = defaultdict(int)
    with caminho.open(encoding="utf-8", newline="") as handle:
        leitor = csv.DictReader(handle, delimiter=";")
        for linha in leitor:
            bruto = (linha.get("Autorias") or "").strip()
            if not bruto:
                continue
            partes = [parte.strip() for parte in bruto.split(",") if parte.strip()]
            for parte in partes:
                chave = normalizar(parte)
                id_sapl = indice.get(chave)
                if id_sapl is None:
                    nao_vereador[parte] += 1
                    continue
                registrar_apelido(apelidos, id_sapl, parte, "autoria")
    return [
        {"grafia": grafia, "vezes_no_csv": vezes}
        for grafia, vezes in sorted(nao_vereador.items())
    ]


def nome_curto(cadastro: dict[int, dict], id_sapl: int) -> str:
    dados = cadastro[id_sapl]
    return (
        f"{dados['nome_parlamentar']} (número {id_sapl}, "
        f"nome completo {dados['nome_oficial']})"
    )


def casos_de_atencao(cadastro: dict[int, dict]) -> list[dict]:
    casos = []
    if 47 in cadastro and 57 in cadastro:
        casos.append(
            {
                "tipo": "nomes_parecidos",
                "titulo": "Dois vereadores chamados Rogério",
                "detalhe": (
                    f"{nome_curto(cadastro, 47)} não é a mesma pessoa que "
                    f"{nome_curto(cadastro, 57)}. No cadastro, o primeiro "
                    "aparece sem acento no nome de urna "
                    f"({cadastro[47]['nome_parlamentar']}) e o segundo com "
                    f"acento ({cadastro[57]['nome_parlamentar']}). "
                    "São duas pessoas. Não misturar."
                ),
                "ids_sapl": [47, 57],
            }
        )
    if 53 in cadastro and 61 in cadastro:
        casos.append(
            {
                "tipo": "nomes_parecidos",
                "titulo": "Dois vereadores com Luiz no nome",
                "detalhe": (
                    f"{nome_curto(cadastro, 53)} não é a mesma pessoa que "
                    f"{nome_curto(cadastro, 61)}. O segundo usa Gustavo "
                    "como nome de urna, não Luiz."
                ),
                "ids_sapl": [53, 61],
            }
        )
    if all(i in cadastro for i in (56, 60, 63)):
        casos.append(
            {
                "tipo": "nomes_parecidos",
                "titulo": "Três vereadores com Junior no nome de registro",
                "detalhe": (
                    f"{nome_curto(cadastro, 56)}, "
                    f"{nome_curto(cadastro, 60)} e "
                    f"{nome_curto(cadastro, 63)} "
                    "são três pessoas. A palavra Junior sozinha não "
                    "identifica ninguém."
                ),
                "ids_sapl": [56, 60, 63],
            }
        )
    return casos


def montar_vereadores(
    cadastro: dict[int, dict],
    apelidos: dict,
    ids_em_2026: set[int],
    filiacoes: dict[int, dict],
) -> list[dict]:
    slugs_usados: dict[str, int] = {}
    tabela = []
    for id_sapl in sorted(cadastro):
        dados = cadastro[id_sapl]
        slug = slugify(dados["nome_parlamentar"] or dados["nome_oficial"] or str(id_sapl))
        if not slug:
            slug = f"parlamentar-{id_sapl}"
        if slug in slugs_usados:
            slug = f"{slug}-{id_sapl}"
        slugs_usados[slug] = id_sapl

        grafias = apelidos.get(id_sapl, {})
        for campo in ("nome_oficial", "nome_parlamentar", "str_sapl"):
            registrar_apelido(apelidos, id_sapl, dados.get(campo, ""), "cadastro")
        grafias = apelidos[id_sapl]

        lista_apelidos = sorted(grafias.keys(), key=lambda n: (normalizar(n), n))
        origem = {
            grafia: sorted(fontes) for grafia, fontes in sorted(grafias.items())
        }
        caminho = dados["link_detail_backend"] or f"/parlamentar/{id_sapl}"
        filiacao = filiacoes.get(id_sapl) or {}
        foto_url = dados.get("fotografia") or None
        tabela.append(
            {
                "id_sapl": id_sapl,
                "slug_codigo": slug,
                "nome_oficial": dados["nome_oficial"],
                "nome_parlamentar": dados["nome_parlamentar"],
                "partido": None,
                "partido_sigla": filiacao.get("partido_sigla") or None,
                "partido_nome": filiacao.get("partido_nome") or None,
                "foto_url": foto_url,
                "apelidos": lista_apelidos,
                "apelidos_origem": origem,
                "ativo_2026": id_sapl in ids_em_2026,
                "link_sapl": "https://sapl.campolargo.pr.leg.br" + caminho,
            }
        )
    return tabela


def conferir_partido_e_foto(vereadores: list[dict]) -> None:
    faltando = []
    for item in vereadores:
        if not item["ativo_2026"]:
            continue
        if not item.get("partido_sigla") or not item.get("partido_nome"):
            faltando.append(f"{item['id_sapl']} sem partido vigente")
        foto = item.get("foto_url") or ""
        if not foto.startswith("http"):
            faltando.append(f"{item['id_sapl']} sem foto oficial")
    if faltando:
        raise SystemExit(
            "Partido ou foto oficial faltando na banca de 2026: "
            + "; ".join(faltando)
        )


def escrever_json(payload: dict) -> None:
    ARQUIVO_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def escrever_csv(vereadores: list[dict]) -> None:
    campos = [
        "id_sapl",
        "slug_codigo",
        "nome_oficial",
        "nome_parlamentar",
        "partido",
        "partido_sigla",
        "partido_nome",
        "foto_url",
        "apelidos",
        "ativo_2026",
        "link_sapl",
    ]
    with ARQUIVO_CSV.open("w", encoding="utf-8", newline="") as handle:
        escritor = csv.DictWriter(handle, fieldnames=campos, delimiter=";")
        escritor.writeheader()
        for item in vereadores:
            escritor.writerow(
                {
                    "id_sapl": item["id_sapl"],
                    "slug_codigo": item["slug_codigo"],
                    "nome_oficial": item["nome_oficial"],
                    "nome_parlamentar": item["nome_parlamentar"],
                    "partido": item["partido"] or "",
                    "partido_sigla": item["partido_sigla"] or "",
                    "partido_nome": item["partido_nome"] or "",
                    "foto_url": item["foto_url"] or "",
                    "apelidos": " | ".join(item["apelidos"]),
                    "ativo_2026": "true" if item["ativo_2026"] else "false",
                    "link_sapl": item["link_sapl"],
                }
            )


def frase_apelidos(item: dict) -> str:
    if not item["apelidos"]:
        return "nenhum apelido extra além do cadastro"
    return ", ".join(f'"{nome}"' for nome in item["apelidos"])


def vezes_em_palavras(n: int) -> str:
    if n == 1:
        return "1 vez"
    return f"{n} vezes"


def escrever_relatorio(payload: dict) -> None:
    meta = payload["meta"]
    linhas = [
        "# Tabela única de vereadores da legislatura de 2026",
        "",
        f"Gerada em: {meta['gerado_em']}",
        "Script: `dados/tratados/gerar_tabela_vereadores.py`",
        "Fonte: exatamente os arquivos oficiais guardados em `dados/brutos/`. Nada foi inventado na mão.",
        "",
        "## Em uma frase",
        "",
        (
            f"Foram identificados **{meta['n_ativos_2026']} vereadores ativos em 2026**. "
            "A banca bate com a prova já feita: são as mesmas 15 pessoas."
        ),
        "",
        "## A banca de 15 confere?",
        "",
        "Sim.",
        "",
        (
            "A prova em `dados/brutos/PROVA-CRUZAMENTO-VOTO-AUSENCIA.md` listou "
            "os números oficiais do SAPL: "
            + ", ".join(str(n) for n in meta["banca_referencia_prova"])
            + "."
        ),
        "",
        (
            "Esta tabela achou os mesmos números, na mesma ordem: "
            + ", ".join(str(n) for n in meta["banca_encontrada"])
            + "."
        ),
        "",
        "Nenhum vereador a mais. Nenhum vereador a menos.",
        "",
        "## O que cada código significa",
        "",
        (
            "O painel não deve usar o nome solto para somar votos. "
            "O mesmo vereador pode aparecer escrito de mais de um jeito. "
            "Tudo no projeto deve apontar para o código próprio (`slug_codigo`) "
            "e para o número oficial do SAPL (`id_sapl`)."
        ),
        "",
        "## Lista completa",
        "",
    ]

    for item in payload["vereadores"]:
        ativo = "sim, atuou em 2026" if item["ativo_2026"] else "não atuou em 2026"
        if item.get("partido_sigla") and item.get("partido_nome"):
            partido = f"{item['partido_sigla']} ({item['partido_nome']})"
        else:
            partido = "não veio no cadastro baixado"
        foto = item.get("foto_url") or "não veio no cadastro baixado"
        linhas.extend(
            [
                f"### {item['nome_parlamentar']}",
                "",
                f"- Código próprio do projeto: `{item['slug_codigo']}`",
                f"- Número oficial no SAPL: {item['id_sapl']}",
                f"- Nome completo no cadastro: {item['nome_oficial']}",
                f"- Nome de urna / parlamentar: {item['nome_parlamentar']}",
                f"- Partido: {partido}",
                f"- Foto oficial: {foto}",
                f"- Ativo em 2026: {ativo}",
                f"- Página oficial: {item['link_sapl']}",
                f"- Grafias encontradas: {frase_apelidos(item)}",
                "",
            ]
        )

    linhas.extend(
        [
            "## Nomes parecidos, cuidado",
            "",
        ]
    )
    for caso in payload["casos_de_atencao"]:
        linhas.extend(
            [
                f"### {caso['titulo']}",
                "",
                caso["detalhe"],
                "",
                "Números envolvidos: "
                + ", ".join(str(n) for n in caso["ids_sapl"])
                + ".",
                "",
            ]
        )

    linhas.extend(
        [
            "## Quem aparece como autor, mas não é vereador",
            "",
            (
                "No arquivo de matérias de 2026, o campo de autoria também traz "
                "nomes que não são vereadores. Eles não entram nesta tabela."
            ),
            "",
        ]
    )
    if payload["autorias_que_nao_sao_vereador"]:
        for item in payload["autorias_que_nao_sao_vereador"]:
            linhas.append(
                f"- \"{item['grafia']}\" (apareceu "
                f"{vezes_em_palavras(item['vezes_no_csv'])} no CSV de matérias)"
            )
        linhas.append("")
    else:
        linhas.extend(["Nenhum caso além dos vereadores da banca.", ""])

    linhas.extend(
        [
            "## Partido e foto oficial",
            "",
            (
                "O partido vigente veio de dois arquivos oficiais do SAPL: "
                "`dados/brutos/api_parlamentares_filiacao.json` (quem está "
                "filiado a qual partido e desde quando) e "
                "`dados/brutos/api_parlamentares_partido.json` (sigla e nome "
                "do partido). Vigente aqui significa: a filiação sem data de "
                "desfiliação. Se a pessoa não tiver uma filiação aberta, "
                "fica a mais recente. Nada foi preenchido na mão."
            ),
            "",
            (
                "A foto oficial veio do campo `fotografia` nos arquivos "
                "`dados/brutos/sessao_*_parlamentares.json`. A URL é a mesma "
                "que o SAPL devolveu."
            ),
            "",
            "## Vereador antigo que não atuou em 2026",
            "",
            (
                "Nos arquivos brutos desta pasta, só aparecem os 15 vereadores "
                "da legislatura atual. Não veio cadastro antigo de outras "
                "legislaturas. Por isso não há ninguém marcado como "
                "`ativo_2026: false`. Se no futuro entrar um cadastro velho, "
                "a pessoa entra na tabela com esse campo em falso, em vez de "
                "sumir ou ser misturada com a banca de 2026."
            ),
            "",
            "## De onde veio cada grafia",
            "",
            "- Cadastro oficial: `dados/brutos/sessao_*_parlamentares.json`",
            "- Partido: `dados/brutos/api_parlamentares_filiacao.json` e `dados/brutos/api_parlamentares_partido.json`",
            "- Foto oficial: campo `fotografia` em `dados/brutos/sessao_*_parlamentares.json`",
            "- Voto individual: `dados/brutos/sessao_*_votoparlamentar.json`",
            "- Mesa diretora: `dados/brutos/sessao_*_integrantemesa.json`",
            "- Presença na ordem do dia: `dados/brutos/sessao_*_presencaordemdia.json`",
            "- Presença na sessão: `dados/brutos/sessao_*_sessaoplenariapresenca.json` (só o número do vereador, sem nome escrito)",
            "- Autoria das matérias: `dados/brutos/materias-2026-resposta-original.csv`",
            "",
            "Em voto, mesa, presença e autoria, o nome de urna veio igual ao cadastro. "
            "A grafia extra de cada um é o nome completo civil, que só aparece no cadastro.",
            "",
            "## Como repetir",
            "",
            "Na pasta do projeto, rode:",
            "",
            "    python dados/tratados/gerar_tabela_vereadores.py",
            "",
            "O programa lê os brutos de novo e reescreve `vereadores.json`, "
            "`vereadores.csv` e este relatório. Não edite esses três arquivos na mão.",
            "",
        ]
    )
    ARQUIVO_RELATORIO.write_text("\n".join(linhas), encoding="utf-8")


def main() -> None:
    if not DIR_BRUTOS.is_dir():
        raise SystemExit(f"Pasta de brutos nao encontrada: {DIR_BRUTOS}")

    cadastro = ler_cadastro()
    apelidos: dict[int, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))

    for id_sapl, dados in cadastro.items():
        for campo in ("nome_oficial", "nome_parlamentar", "str_sapl"):
            registrar_apelido(apelidos, id_sapl, dados.get(campo, ""), "cadastro")

    ids_em_2026 = varrer_sessoes(cadastro, apelidos)
    indice = montar_indice_nomes(cadastro, apelidos)
    autorias_nao_vereador = varrer_autoria(indice, apelidos)
    filiacoes = carregar_filiacoes_vigentes(carregar_partidos())
    vereadores = montar_vereadores(cadastro, apelidos, ids_em_2026, filiacoes)
    conferir_partido_e_foto(vereadores)

    banca_encontrada = [item["id_sapl"] for item in vereadores if item["ativo_2026"]]
    if banca_encontrada != BANCA_REFERENCIA_2026:
        raise SystemExit(
            "A banca de 2026 nao confere com a prova. "
            f"Referencia={BANCA_REFERENCIA_2026} encontrada={banca_encontrada}"
        )

    slugs = [item["slug_codigo"] for item in vereadores]
    if len(slugs) != len(set(slugs)):
        raise SystemExit("Slug repetido na tabela de vereadores.")

    payload = {
        "meta": {
            "gerado_em": agora_iso(),
            "gerado_por": "dados/tratados/gerar_tabela_vereadores.py",
            "banca_referencia_prova": BANCA_REFERENCIA_2026,
            "banca_encontrada": banca_encontrada,
            "banca_confere": True,
            "n_ativos_2026": len(banca_encontrada),
            "n_cadastro": len(vereadores),
            "partido_no_cadastro_estruturado": True,
            "observacao_partido": (
                "O partido vigente veio de api_parlamentares_filiacao.json "
                "cruzado com api_parlamentares_partido.json. A foto veio do "
                "campo fotografia do cadastro de parlamentar."
            ),
        },
        "casos_de_atencao": casos_de_atencao(cadastro),
        "autorias_que_nao_sao_vereador": autorias_nao_vereador,
        "vereadores": vereadores,
    }
    escrever_json(payload)
    escrever_csv(vereadores)
    escrever_relatorio(payload)
    print(
        f"Tabela gerada: {len(vereadores)} vereadores, "
        f"{len(banca_encontrada)} ativos em 2026. Banca confere."
    )
    print(f"  {ARQUIVO_JSON}")
    print(f"  {ARQUIVO_CSV}")
    print(f"  {ARQUIVO_RELATORIO}")


if __name__ == "__main__":
    main()
