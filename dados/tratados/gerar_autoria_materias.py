"""Gera a autoria de cada materia de 2025 e 2026.

Le so dados/brutos/:
- materialegislativa_ano<ano>_p*.json do lote em dados/brutos/lote_<data>/
  (campo autores: lista de ids de autor, a ligacao oficial da materia)
- autor_p*.json, tipoautor_p*.json e autoria_p*.json de
  dados/brutos/lote_<data>_autoria/

Autor do tipo Parlamentar fica ligado ao id do parlamentar no SAPL
(object_id). Os outros ficam ligados ao tipo de autor oficial
(Chefe do Poder Executivo Municipal, MESA DIRETORA, Comissao, Orgao).
Nome nunca e chave.

A lista paginada materia/autoria repete ids entre paginas. Por isso ela so
serve para dizer quem e o primeiro autor. Quando o par materia e autor nao
veio nessa lista, primeiro_autor fica nulo com rotulo. Nada e deduzido.

Uso:
    python dados/tratados/gerar_autoria_materias.py
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

DIR_SCRIPT = Path(__file__).resolve().parent
DIR_RAIZ = DIR_SCRIPT.parent.parent
DIR_BRUTOS = DIR_SCRIPT.parent / "brutos"
if str(DIR_RAIZ / "coletor") not in sys.path:
    sys.path.insert(0, str(DIR_RAIZ / "coletor"))

from config_cidade import anos_recorte, carregar_config, link_materia  # noqa: E402
from derivar_insumos import ler_paginas  # noqa: E402

CONFIG = carregar_config()
ANOS = anos_recorte(CONFIG)
ARQUIVO_JSON = DIR_SCRIPT / "autoria_materias.json"
ARQUIVO_CSV = DIR_SCRIPT / "autoria_materias.csv"
TIPO_AUTOR_PARLAMENTAR = 2
ROTULO_SEM_AUTOR = "sem autor registrado no SAPL"
ROTULO_PRIMEIRO_AUTOR_AUSENTE = (
    "primeiro autor nao informado: a lista de autoria do SAPL nao trouxe este par"
)


def rel(caminho: Path) -> str:
    return caminho.resolve().relative_to(DIR_RAIZ).as_posix()


def pasta_com(glob_pasta: str, arquivo: str) -> Path:
    candidatas = sorted(
        caminho
        for caminho in DIR_BRUTOS.glob(glob_pasta)
        if caminho.is_dir() and (caminho / arquivo).exists()
    )
    if not candidatas:
        raise SystemExit(f"Nenhuma pasta dados/brutos/{glob_pasta} com {arquivo}.")
    return candidatas[-1]


def ler_lista_repetida(pasta: Path, prefixo: str) -> tuple[list, list[str], int | None]:
    """Le todas as paginas sem exigir total, pois a lista repete ids."""
    linhas = []
    nomes = []
    total = None
    numero = 1
    while (pasta / f"{prefixo}_p{numero}.json").exists():
        caminho = pasta / f"{prefixo}_p{numero}.json"
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        if numero == 1:
            valor = (dados.get("pagination") or {}).get("total_entries")
            total = int(valor) if valor is not None else None
        linhas.extend(dados.get("results") or [])
        nomes.append(rel(caminho))
        numero += 1
    return linhas, nomes, total


def gerar() -> dict:
    pasta_autoria = pasta_com("lote_*_autoria", "autor_p1.json")
    autores_linhas, nomes_autor = ler_paginas(pasta_autoria, "autor")
    tipos_linhas, nomes_tipo = ler_paginas(pasta_autoria, "tipoautor")
    autoria_linhas, nomes_autoria, total_autoria = ler_lista_repetida(pasta_autoria, "autoria")
    autor_por_id = {int(a["id"]): a for a in autores_linhas}
    tipo_por_id = {int(t["id"]): (t.get("descricao") or "").strip() for t in tipos_linhas}
    primeiro = {}
    for linha in autoria_linhas:
        if not isinstance(linha, dict) or linha.get("materia") is None:
            continue
        primeiro[(int(linha["materia"]), int(linha["autor"]))] = bool(linha.get("primeiro_autor"))

    materias_saida = []
    por_ano = {}
    for ano in ANOS:
        prefixo = f"materialegislativa_ano{ano}"
        pasta_lote = pasta_com("lote_*", f"{prefixo}_p1.json")
        materias, nomes = ler_paginas(pasta_lote, prefixo)
        total_api = json.loads(
            (pasta_lote / f"{prefixo}_p1.json").read_text(encoding="utf-8")
        )["pagination"]["total_entries"]
        contagem_tipo = Counter()
        pares_ano = 0
        for materia in sorted(materias, key=lambda m: int(m["id"])):
            mid = int(materia["id"])
            autorias = []
            for ordem, autor_id in enumerate(materia.get("autores") or [], start=1):
                autor_id = int(autor_id)
                autor = autor_por_id.get(autor_id)
                chave = (mid, autor_id)
                item = {
                    "ordem_no_sapl": ordem,
                    "autor_id": autor_id,
                    "primeiro_autor": primeiro.get(chave),
                    "primeiro_autor_rotulo": None if chave in primeiro else ROTULO_PRIMEIRO_AUTOR_AUSENTE,
                }
                if autor is None:
                    item.update(
                        {
                            "tipo_autor_id": None,
                            "tipo_autor": None,
                            "parlamentar_id_sapl": None,
                            "nome_no_sapl": None,
                            "lacuna": "autor ausente na tabela base/autor baixada",
                        }
                    )
                else:
                    tipo_id = int(autor["tipo"]) if autor.get("tipo") is not None else None
                    e_parlamentar = tipo_id == TIPO_AUTOR_PARLAMENTAR and autor.get("object_id") is not None
                    item.update(
                        {
                            "tipo_autor_id": tipo_id,
                            "tipo_autor": tipo_por_id.get(tipo_id) if tipo_id is not None else None,
                            "parlamentar_id_sapl": int(autor["object_id"]) if e_parlamentar else None,
                            "nome_no_sapl": (autor.get("nome") or "").strip(),
                            "cargo_no_sapl": (autor.get("cargo") or "").strip() or None,
                            "lacuna": None,
                        }
                    )
                autorias.append(item)
            pares_ano += len(autorias)
            tipos_da_materia = {a["tipo_autor"] or "tipo de autor ausente" for a in autorias}
            if not autorias:
                tipos_da_materia = {ROTULO_SEM_AUTOR}
            for tipo in tipos_da_materia:
                contagem_tipo[tipo] += 1
            materias_saida.append(
                {
                    "materia_id": mid,
                    "ano": int(materia.get("ano") or ano),
                    "numero": materia.get("numero"),
                    "tipo_materia_id": materia.get("tipo"),
                    "rotulo_sapl": materia.get("__str__") or "",
                    "link_sapl": link_materia(mid, CONFIG),
                    "autoria_rotulo": None if autorias else ROTULO_SEM_AUTOR,
                    "autorias": autorias,
                }
            )
        por_ano[str(ano)] = {
            "n_materias": len(materias),
            "total_entries_api": int(total_api),
            "n_pares_materia_autor": pares_ano,
            "materias_por_tipo_de_autor": dict(sorted(contagem_tipo.items())),
            "arquivos_materias": [rel(pasta_lote / nome) for nome in nomes],
        }

    return {
        "meta": {
            "gerado_por": "dados/tratados/gerar_autoria_materias.py",
            "anos": ANOS,
            "fonte_ligacao": "campo autores de materialegislativa",
            "arquivos_autor": [rel(pasta_autoria / n) for n in nomes_autor],
            "arquivos_tipoautor": [rel(pasta_autoria / n) for n in nomes_tipo],
            "arquivos_autoria": nomes_autoria,
            "autoria_total_entries_api": total_autoria,
            "autoria_ids_distintos": len(
                {int(l["id"]) for l in autoria_linhas if isinstance(l, dict) and l.get("id") is not None}
            ),
            "nota_autoria": (
                "A lista materia/autoria repetiu ids entre paginas e o filtro por ano "
                "foi ignorado pelo SAPL. Ela so informa o primeiro autor. A ligacao "
                "materia e autor vem do campo autores da propria materia."
            ),
            "por_ano": por_ano,
        },
        "materias": materias_saida,
    }


def escrever_csv(payload: dict) -> None:
    campos = [
        "materia_id",
        "ano",
        "numero",
        "rotulo_sapl",
        "autor_id",
        "ordem_no_sapl",
        "primeiro_autor",
        "tipo_autor_id",
        "tipo_autor",
        "parlamentar_id_sapl",
        "nome_no_sapl",
        "rotulo",
        "link_sapl",
    ]
    with ARQUIVO_CSV.open("w", encoding="utf-8", newline="") as handle:
        escritor = csv.DictWriter(handle, fieldnames=campos, delimiter=";", lineterminator="\n")
        escritor.writeheader()
        for materia in payload["materias"]:
            base = {
                "materia_id": materia["materia_id"],
                "ano": materia["ano"],
                "numero": materia["numero"],
                "rotulo_sapl": materia["rotulo_sapl"],
                "link_sapl": materia["link_sapl"],
            }
            if not materia["autorias"]:
                escritor.writerow({**base, "rotulo": materia["autoria_rotulo"]})
                continue
            for autoria in materia["autorias"]:
                primeiro = autoria["primeiro_autor"]
                escritor.writerow(
                    {
                        **base,
                        "autor_id": autoria["autor_id"],
                        "ordem_no_sapl": autoria["ordem_no_sapl"],
                        "primeiro_autor": "" if primeiro is None else ("true" if primeiro else "false"),
                        "tipo_autor_id": autoria["tipo_autor_id"] if autoria["tipo_autor_id"] is not None else "",
                        "tipo_autor": autoria["tipo_autor"] or "",
                        "parlamentar_id_sapl": autoria["parlamentar_id_sapl"] or "",
                        "nome_no_sapl": autoria["nome_no_sapl"] or "",
                        "rotulo": autoria["primeiro_autor_rotulo"] or autoria["lacuna"] or "",
                    }
                )


def main() -> None:
    payload = gerar()
    for ano, bloco in payload["meta"]["por_ano"].items():
        if bloco["n_materias"] != bloco["total_entries_api"]:
            raise SystemExit(
                f"{ano}: {bloco['n_materias']} materias lidas, a API informa "
                f"{bloco['total_entries_api']}. Materia perdida."
            )
    ARQUIVO_JSON.write_bytes(
        (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )
    escrever_csv(payload)
    for ano, bloco in payload["meta"]["por_ano"].items():
        print(f"{ano}: {bloco['n_materias']} materias, {bloco['n_pares_materia_autor']} pares")
        for tipo, n in bloco["materias_por_tipo_de_autor"].items():
            print(f"  {tipo}: {n}")
    print(f"  {ARQUIVO_JSON}")
    print(f"  {ARQUIVO_CSV}")


if __name__ == "__main__":
    main()
