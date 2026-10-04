"""RI-1g: votacoes unificadas na aba Camara e etiqueta sem registro."""

from __future__ import annotations

import json
import pathlib
import re
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
if str(RAIZ / "coletor") not in sys.path:
    sys.path.insert(0, str(RAIZ / "coletor"))

from config_cidade import carregar_config  # noqa: E402

INDEX = (RAIZ / "index.html").read_text(encoding="utf-8")
SUFIXO = "legislatura"


def _js_principal_sem_comentario() -> str:
    ini = INDEX.find("var CONFIG_CIDADE = null;")
    fim = INDEX.find("})();\n</script>", ini)
    bloco = INDEX[ini:fim] if ini >= 0 and fim > ini else INDEX
    sem_linha = re.sub(r"//[^\n]*", "", bloco)
    return re.sub(r"/\*[\s\S]*?\*/", "", sem_linha)


def _carregar_json(nome: str) -> dict:
    path = RAIZ / "dados" / "tratados" / f"{nome}_{SUFIXO}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _item_votacao_valida(item: dict) -> bool:
    return bool(
        item
        and item.get("situacao_final_fonte") == "votacao"
        and item.get("votacao")
        and item["votacao"].get("data_sessao")
    )


def _data_minima_votacao() -> str:
    datas: list[str] = []
    materias = _carregar_json("materias_camara")
    for periodo in ("sessao", "mes", "todo"):
        for m in materias.get(periodo) or []:
            if m.get("data_sessao"):
                datas.append(m["data_sessao"])
            for v in m.get("votacoes") or []:
                if v and v.get("data_sessao"):
                    datas.append(v["data_sessao"])
    prop = _carregar_json("proposicoes")
    for periodo in ("sessao", "mes", "todo"):
        for item in prop.get(periodo) or []:
            if _item_votacao_valida(item):
                datas.append(item["votacao"]["data_sessao"])
    execu = _carregar_json("executivo")
    for periodo in ("sessao", "mes", "todo"):
        for item in execu.get(periodo) or []:
            if _item_votacao_valida(item):
                datas.append(item["votacao"]["data_sessao"])
    return min(datas) if datas else ""


def _contar_votados_todo() -> dict[str, int]:
    cfg = carregar_config()
    tipos_ped = cfg["tramitacao"]["tipos_pedidos"]
    tipos_exec = cfg["tramitacao"]["tipos_executivo"]
    out: dict[str, int] = {}
    materias = _carregar_json("materias_camara")
    ids_pleg = set()
    for m in materias.get("todo") or []:
        sig = m.get("tipo_sigla") or "PLEG"
        out[sig] = out.get(sig, 0) + 1
        ids_pleg.add(m.get("id"))
    prop = _carregar_json("proposicoes")
    for item in prop.get("todo") or []:
        if not _item_votacao_valida(item):
            continue
        if item.get("id") in ids_pleg:
            continue
        sig = item.get("tipo_sigla") or ""
        if sig in tipos_ped:
            out[sig] = out.get(sig, 0) + 1
    execu = _carregar_json("executivo")
    for item in execu.get("todo") or []:
        if not _item_votacao_valida(item):
            continue
        sig = item.get("tipo_sigla") or ""
        if sig in tipos_exec:
            out[sig] = out.get(sig, 0) + 1
    return out


class TestIndexVotacoes(unittest.TestCase):
    def test_titulos_votacoes_camara(self):
        self.assertIn("tituloCartaoVotacoesPeriodo", INDEX)
        self.assertIn("Vota\\u00e7\\u00f5es da sess\\u00e3o", INDEX)
        self.assertIn("Do que tratam as vota\\u00e7\\u00f5es", INDEX)
        self.assertNotIn("Projetos votados", INDEX)
        self.assertNotIn("Pedidos dos vereadores", INDEX)

    def test_lista_votacoes_e_filtro_tipo(self):
        js = _js_principal_sem_comentario()
        self.assertIn("listaVotacoesPeriodo", js)
        self.assertIn("filtroTipo", js)
        self.assertIn("htmlFiltrosTipoVotacao", js)

    def test_data_minima_calculada(self):
        self.assertIn("dataMinimaVotacaoRegistrada", INDEX)
        self.assertIn("fraseApoioCorteVotacaoSapl", INDEX)
        d = _data_minima_votacao()
        self.assertEqual(d, "2025-05-13")

    def test_sem_registro_votacao_etiqueta(self):
        self.assertIn("sem_registro_votacao", INDEX)
        self.assertIn("textoExplicacaoSemRegistroVotacao", INDEX)
        self.assertIn("Sem registro de vota\\u00e7\\u00e3o", INDEX)

    def test_rotulos_pedidos_ui(self):
        self.assertIn("rotuloTipoPedidoUi", INDEX)
        self.assertIn("rotulo_plural", INDEX)


class TestContagemVotados(unittest.TestCase):
    def test_pleg_sem_duplicar_proposicoes(self):
        cont = _contar_votados_todo()
        prop = _carregar_json("proposicoes")
        pleg_prop = sum(
            1
            for item in prop.get("todo") or []
            if _item_votacao_valida(item) and item.get("tipo_sigla") == "PLEG"
        )
        materias = _carregar_json("materias_camara")
        pleg_m = len(materias.get("todo") or [])
        self.assertEqual(cont.get("PLEG", 0), pleg_m)
        if pleg_prop:
            self.assertGreater(pleg_prop, 0)
            self.assertEqual(cont.get("PLEG", 0), pleg_m)

    def test_contagens_todo_batem_esperado(self):
        cont = _contar_votados_todo()
        self.assertEqual(cont.get("PLEG", 0), 16)
        self.assertEqual(cont.get("IND", 0), 58)
        self.assertEqual(cont.get("REQ", 0), 30)
        self.assertEqual(cont.get("MOC", 0), 7)
        self.assertEqual(cont.get("PLEX", 0), 17)
        self.assertEqual(cont.get("VET", 0), 3)


if __name__ == "__main__":
    unittest.main()
