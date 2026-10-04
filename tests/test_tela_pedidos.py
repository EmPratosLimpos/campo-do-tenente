"""RI-1: pedidos (IND, REQ, MOC) lidos do config e proposicoes, sem siglas fixas no JS."""

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


def _js_principal_sem_comentario() -> str:
    ini = INDEX.find('var CONFIG_CIDADE = null;')
    fim = INDEX.find("})();\n</script>", ini)
    bloco = INDEX[ini:fim] if ini >= 0 and fim > ini else INDEX
    sem_linha = re.sub(r"//[^\n]*", "", bloco)
    return re.sub(r"/\*[\s\S]*?\*/", "", sem_linha)


def _tipos_config() -> list[str]:
    cfg = carregar_config()
    return list(cfg["tramitacao"]["tipos_pedidos"])


def _carregar_proposicoes(sufixo: str = "legislatura") -> dict:
    path = RAIZ / "dados" / "tratados" / f"proposicoes_{sufixo}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _contar_pedidos_vereador(dados: dict, id_sapl: int) -> dict[str, int]:
    tipos = set(_tipos_config())
    out = {t: 0 for t in tipos}
    for item in dados.get("todo") or []:
        if item.get("tipo_sigla") not in tipos:
            continue
        autores = item.get("autores") or []
        if any(a.get("parlamentar_id_sapl") == id_sapl for a in autores):
            out[item["tipo_sigla"]] += 1
    return out


class TestConfigPedidos(unittest.TestCase):
    def test_tipos_pedidos_no_config(self):
        cfg = carregar_config()
        tipos = cfg["tramitacao"]["tipos_pedidos"]
        self.assertEqual(tipos, ["IND", "REQ", "MOC"])
        self.assertIn("MOC", cfg["tramitacao"]["ementa_oculta_tipos"])

    def test_nomes_pedidos_no_config(self):
        cfg = carregar_config()
        nomes = cfg["tramitacao"]["nomes_pedidos"]
        self.assertEqual(nomes["REQ"]["plural"], "requerimentos")
        self.assertEqual(nomes["MOC"]["plural"], "moções")


class TestIndexPedidos(unittest.TestCase):
    def test_js_lê_tipos_do_config(self):
        self.assertIn("tiposPedidos", INDEX)
        self.assertIn("tipos_pedidos", INDEX)
        self.assertIn("nomesPedidosConfig", INDEX)
        self.assertIn("nomes_pedidos", INDEX)
        self.assertIn("ementa_oculta_tipos", INDEX)
        self.assertIn("carregarProposicoesCamara", INDEX)

    def test_plural_e_resumo_sem_regra_fixa_no_js(self):
        js = _js_principal_sem_comentario()
        self.assertNotIn('lower === "moção"', js)
        self.assertNotIn("lower.slice(-1)", js)
        self.assertNotIn('return "moções"', js)
        self.assertIn("nomesPedidosConfig", js)
        frag = js[js.find("function htmlFraseResumoPedidos"): js.find("function pedidoFoiAprovado")]
        self.assertNotIn("htmlBotaoTermoSigla(sigla) +", frag)
        self.assertIn("htmlBotaoTermoSigla(sigla, rotulo)", frag)

    def test_sem_siglas_fixas_no_js(self):
        js = _js_principal_sem_comentario()
        for sigla in ("IND", "REQ", "MOC"):
            self.assertNotIn(f'"{sigla}"', js, msg=f"literal {sigla} no JS fora de comentario")

    def test_pilula_sem_registro_sapl(self):
        self.assertIn("Sem registro no SAPL", INDEX)
        self.assertIn('situacao_final_fonte === "sem_registro"', INDEX)

    def test_ementa_oculta_moc(self):
        self.assertIn("ementaVisivelPedido", INDEX)
        self.assertIn("ementaOcultaTipos", INDEX)

    def test_estado_vazio_vereador(self):
        self.assertIn("Nenhum pedido registrado no SAPL neste", INDEX)

    def test_cartoes_titulos(self):
        self.assertIn('id="tit-pedidos"', INDEX)
        self.assertIn("Pedidos dos vereadores", INDEX)


class TestContagemPorId(unittest.TestCase):
    def test_gustavo_e_beto_batem_com_json(self):
        dados = _carregar_proposicoes()
        for id_sapl, slug in ((6, "gustavo-vizentin"), (8, "beto-maurer")):
            cont = _contar_pedidos_vereador(dados, id_sapl)
            total = sum(cont.values())
            with self.subTest(vereador=slug):
                self.assertGreater(total, 0, msg="esperado pedidos no periodo legislatura")
                for sigla, q in cont.items():
                    self.assertGreaterEqual(q, 0)


if __name__ == "__main__":
    unittest.main()
