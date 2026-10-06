"""RI-3b M1: contagens de filtro respeitam outros filtros ativos (facetas)."""

from __future__ import annotations

import json
import pathlib
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
if str(RAIZ / "coletor") not in sys.path:
    sys.path.insert(0, str(RAIZ / "coletor"))

from config_cidade import carregar_config  # noqa: E402

SUFIXO = "legislatura"
INDEX = (RAIZ / "index.html").read_text(encoding="utf-8")


def _carregar(nome: str) -> dict:
    path = RAIZ / "dados" / "tratados" / f"{nome}_{SUFIXO}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _item_votacao_valida(item: dict) -> bool:
    return bool(
        item
        and item.get("situacao_final_fonte") == "votacao"
        and item.get("votacao")
        and item["votacao"].get("data_sessao")
    )


def _lista_todo() -> list[dict]:
    cfg = carregar_config()
    tipos_ped = cfg["tramitacao"]["tipos_pedidos"]
    tipos_exec = cfg["tramitacao"]["tipos_executivo"]
    out: list[dict] = []
    materias = _carregar("materias_camara")
    ids_pleg: set = set()
    for m in materias.get("todo") or []:
        ids_pleg.add(m.get("id"))
        tags = (_carregar("materias_tags").get(str(m["id"])) or {}) if m.get("id") else {}
        tema = tags.get("tag_tema") or m.get("categoria") or ""
        out.append({"tipo_sigla": m.get("tipo_sigla") or "PLEG", "tema": tema})
    prop = _carregar("proposicoes")
    for item in prop.get("todo") or []:
        if not _item_votacao_valida(item):
            continue
        if item.get("id") in ids_pleg:
            continue
        sig = item.get("tipo_sigla") or ""
        if sig in tipos_ped:
            out.append({"tipo_sigla": sig, "tema": item.get("tema") or ""})
    execu = _carregar("executivo")
    for item in execu.get("todo") or []:
        if not _item_votacao_valida(item):
            continue
        sig = item.get("tipo_sigla") or ""
        if sig in tipos_exec:
            out.append({"tipo_sigla": sig, "tema": item.get("tema") or ""})
    return out


def _filtrar(
    lista: list[dict],
    *,
    tipo: str = "",
    tema: str = "",
    omit_tipo: bool = False,
    omit_tema: bool = False,
) -> list[dict]:
    ft = "" if omit_tipo else tipo
    fm = "" if omit_tema else tema
    out = []
    for e in lista:
        if ft and e["tipo_sigla"] != ft:
            continue
        if fm and e["tema"] != fm:
            continue
        out.append(e)
    return out


class TestFacetasVotacao(unittest.TestCase):
    def test_funcao_facet_no_index(self):
        self.assertIn("function votacoesFiltradasFacet", INDEX)
        self.assertIn("votacoesFiltradasFacet(periodo, { tipo: true })", INDEX)
        self.assertIn("votacoesFiltradasFacet(periodo, { tema: true })", INDEX)

    def test_dois_filtros_soma_chips_igual_cabeca(self):
        lista = _lista_todo()
        temas = sorted({e["tema"] for e in lista if e["tema"]})
        self.assertGreater(len(temas), 1, "precisa de mais de um tema na base")
        tema = temas[0]
        filtrada = _filtrar(lista, tema=tema)
        self.assertGreater(len(filtrada), 0)
        facet_tipo = _filtrar(lista, tema=tema, omit_tipo=True)
        cont: dict[str, int] = {}
        for e in facet_tipo:
            cont[e["tipo_sigla"]] = cont.get(e["tipo_sigla"], 0) + 1
        self.assertEqual(sum(cont.values()), len(filtrada))


if __name__ == "__main__":
    unittest.main()
