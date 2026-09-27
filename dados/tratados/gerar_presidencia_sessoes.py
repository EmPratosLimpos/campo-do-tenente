"""Gera quem ocupava a presidencia em cada sessao ordinaria.

Le so dados/brutos/. Para cada sessao ordinaria listada em
contagem_votacoes_ordinarias_<ano>.json, olha o arquivo
sessao_<id>_integrantemesa.json daquela sessao e pega o integrante cujo
cargo, na tabela oficial parlamentares/cargomesa, tem a descricao
"Presidente". Vice-Presidente nao conta.

Nunca presume pelo cargo do ano nem pela mesa de outra sessao. Sessao sem
presidente registrado fica com presidente nulo e rotulo de lacuna.

Uso posterior: o rotulo "Presidente que nao votou" so vale quando o voto
daquela pessoa, naquela votacao, esta registrado como "Não Votou".

Uso:
    python dados/tratados/gerar_presidencia_sessoes.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

DIR_SCRIPT = Path(__file__).resolve().parent
DIR_RAIZ = DIR_SCRIPT.parent.parent
DIR_BRUTOS = DIR_SCRIPT.parent / "brutos"
if str(DIR_RAIZ / "coletor") not in sys.path:
    sys.path.insert(0, str(DIR_RAIZ / "coletor"))

from config_cidade import anos_recorte, carregar_config, link_sessao  # noqa: E402

CONFIG = carregar_config()
ANOS = anos_recorte(CONFIG)
ARQUIVO_JSON = DIR_SCRIPT / "presidencia_sessoes.json"
DESCRICAO_PRESIDENTE = "Presidente"
ROTULO_LACUNA = "presidencia nao registrada no SAPL para esta sessao"


def carregar_json(caminho: Path):
    return json.loads(caminho.read_text(encoding="utf-8"))


def caminho_relativo(caminho: Path) -> str:
    return caminho.resolve().relative_to(DIR_RAIZ).as_posix()


def arquivo_cargomesa() -> Path:
    candidatos = sorted(DIR_BRUTOS.glob("lote_*/cargomesa_p1.json"))
    if not candidatos:
        raise SystemExit(
            "Tabela oficial de cargos da mesa (cargomesa_p1.json) nao encontrada. "
            "Rode python coletor/coletar_autoria.py."
        )
    return candidatos[-1]


def ids_cargo_presidente(caminho: Path) -> set[int]:
    dados = carregar_json(caminho)
    ids = {
        int(item["id"])
        for item in dados.get("results") or []
        if isinstance(item, dict)
        and (item.get("descricao") or "").strip() == DESCRICAO_PRESIDENTE
    }
    if not ids:
        raise SystemExit(f"Nenhum cargo com descricao '{DESCRICAO_PRESIDENTE}' em {caminho.name}.")
    return ids


def nomes_da_tabela() -> dict[int, str]:
    caminho = DIR_SCRIPT / "vereadores.json"
    if not caminho.exists():
        return {}
    dados = carregar_json(caminho)
    return {
        int(item["id_sapl"]): item.get("nome_parlamentar") or ""
        for item in dados.get("vereadores") or []
    }


def presidencia_da_sessao(sessao: dict, cargos_presidente: set[int], nomes: dict[int, str]) -> dict:
    sid = int(sessao["id"])
    caminho = DIR_BRUTOS / f"sessao_{sid}_integrantemesa.json"
    base = {
        "sessao_id": sid,
        "numero": sessao.get("numero"),
        "data": sessao.get("data"),
        "link_sessao": link_sessao(sid, CONFIG),
        "arquivo_de_origem": caminho_relativo(caminho),
    }
    if not caminho.exists():
        base.update(
            {
                "presidente_id_sapl": None,
                "presidente_nome_parlamentar": None,
                "integrante_mesa_id": None,
                "lacuna": "arquivo da mesa desta sessao ausente em dados/brutos",
            }
        )
        return base
    linhas = carregar_json(caminho).get("results") or []
    presidentes = [
        linha
        for linha in linhas
        if isinstance(linha, dict)
        and linha.get("cargo") is not None
        and int(linha["cargo"]) in cargos_presidente
        and linha.get("parlamentar") is not None
    ]
    if len(presidentes) != 1:
        base.update(
            {
                "presidente_id_sapl": None,
                "presidente_nome_parlamentar": None,
                "integrante_mesa_id": None,
                "lacuna": (
                    ROTULO_LACUNA
                    if not presidentes
                    else "mais de um registro de presidente na mesa desta sessao: "
                    + ", ".join(str(int(p["parlamentar"])) for p in presidentes)
                ),
            }
        )
        return base
    pid = int(presidentes[0]["parlamentar"])
    base.update(
        {
            "presidente_id_sapl": pid,
            "presidente_nome_parlamentar": nomes.get(pid),
            "integrante_mesa_id": int(presidentes[0]["id"]),
            "lacuna": None,
        }
    )
    return base


def gerar() -> dict:
    caminho_cargos = arquivo_cargomesa()
    cargos_presidente = ids_cargo_presidente(caminho_cargos)
    nomes = nomes_da_tabela()
    por_ano = {}
    for ano in ANOS:
        caminho = DIR_BRUTOS / f"contagem_votacoes_ordinarias_{ano}.json"
        if not caminho.exists():
            raise SystemExit(f"Arquivo nao encontrado: {caminho}")
        sessoes = carregar_json(caminho).get("sessoes") or []
        itens = [presidencia_da_sessao(s, cargos_presidente, nomes) for s in sessoes]
        por_ano[str(ano)] = {
            "arquivo_sessoes": caminho_relativo(caminho),
            "n_sessoes_ordinarias": len(itens),
            "n_com_presidente": sum(1 for i in itens if i["presidente_id_sapl"] is not None),
            "lacunas": [i["sessao_id"] for i in itens if i["presidente_id_sapl"] is None],
            "sessoes": itens,
        }
    return {
        "meta": {
            "gerado_por": "dados/tratados/gerar_presidencia_sessoes.py",
            "arquivo_cargos_mesa": caminho_relativo(caminho_cargos),
            "ids_cargo_presidente": sorted(cargos_presidente),
            "regra": (
                "Presidente da sessao e o integrante da mesa daquela sessao com o "
                "cargo oficial Presidente. O rotulo 'Presidente que nao votou' so "
                "vale quando o voto dessa pessoa esta registrado como 'Não Votou'."
            ),
        },
        "por_ano": por_ano,
    }


def main() -> None:
    payload = gerar()
    ARQUIVO_JSON.write_bytes(
        (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )
    for ano, bloco in payload["por_ano"].items():
        print(
            f"{ano}: {bloco['n_sessoes_ordinarias']} ordinarias, "
            f"{bloco['n_com_presidente']} com presidente, "
            f"{len(bloco['lacunas'])} lacunas"
        )
    print(f"  {ARQUIVO_JSON}")


if __name__ == "__main__":
    main()
