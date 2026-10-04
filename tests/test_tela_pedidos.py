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
        self.assertEqual(cfg["tramitacao"]["ementa_oculta_tipos"], [])

    def test_nomes_pedidos_no_config(self):
        cfg = carregar_config()
        nomes = cfg["tramitacao"]["nomes_pedidos"]
        self.assertEqual(nomes["REQ"]["plural"], "requerimentos")
        self.assertEqual(nomes["MOC"]["plural"], "moções")
        self.assertEqual(nomes["REQ"]["rotulo_plural"], "Requerimentos")
        self.assertEqual(nomes["IND"]["rotulo_singular"], "Indicação")


class TestIndexPedidos(unittest.TestCase):
    def test_js_lê_tipos_do_config(self):
        self.assertIn("tiposPedidos", INDEX)
        self.assertIn("tipos_pedidos", INDEX)
        self.assertIn("nomesPedidosConfig", INDEX)
        self.assertIn("nomes_pedidos", INDEX)
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

    def test_pilula_sem_registro_votacao(self):
        self.assertIn("sem_registro_votacao", INDEX)
        self.assertIn('situacao_final_fonte === "sem_registro"', INDEX)

    def test_estado_vazio_vereador(self):
        self.assertIn("Nenhum pedido registrado no SAPL neste", INDEX)

    def test_cartao_pedidos_titulo(self):
        self.assertIn('id="tit-pedidos"', INDEX)
        self.assertIn("Pedidos que fez", INDEX)

    def test_temas_pedidos_por_tipo(self):
        self.assertIn("listaTemasPedidos", INDEX)
        self.assertIn("filtroPedidoTipo", INDEX)

    def test_frase_sapl_pedidos_vereador(self):
        self.assertIn("fraseApoioPedidosVereadorSapl", INDEX)
        self.assertIn("Pedidos anteriores n\\u00e3o t\\u00eam registro de vota\\u00e7\\u00e3o", INDEX)
        self.assertIn("pedido-tipo-nome", INDEX)
        self.assertIn("pedido-tipo-sigla", INDEX)


class TestAutoriaPedidos(unittest.TestCase):
    """Regras RI-1f e RI-1g espelhadas para autoria resumida."""

    @staticmethod
    def _nome(a: dict) -> str:
        return a.get("nome_parlamentar") or a.get("nome_no_sapl") or a.get("nome") or ""

    def _html_autoria(self, autores: list[dict], id_vereador: int) -> str:
        if not autores:
            return ""
        if len(autores) == 1 and autores[0].get("parlamentar_id_sapl") == id_vereador:
            return ""
        primarios = [a for a in autores if a.get("primeiro_autor") is True]
        demais = [a for a in autores if a.get("primeiro_autor") is not True]
        if not primarios:
            nomes = [self._nome(a) for a in autores if self._nome(a)]
            if not nomes:
                return ""
            if len(nomes) <= 2:
                return "Autoria: " + ", ".join(nomes)
            return f"Autoria: {', '.join(nomes[:2])} e mais {len(nomes) - 2} vereadores"
        linha = "Autoria: " + ", ".join(self._nome(a) for a in primarios)
        outros = [self._nome(a) for a in demais if self._nome(a)]
        if not outros:
            return linha
        if len(outros) <= 2:
            return linha + "\ncom " + ", ".join(outros)
        return linha + f"\ncom {', '.join(outros[:2])} e mais {len(outros) - 2} vereadores"

    def test_um_primeiro_autor(self):
        autores = [
            {"parlamentar_id_sapl": 6, "nome_parlamentar": "Gustavo", "primeiro_autor": True},
            {"parlamentar_id_sapl": 8, "nome_parlamentar": "Beto", "primeiro_autor": False},
        ]
        txt = self._html_autoria(autores, 6)
        self.assertIn("Autoria:", txt)
        self.assertIn("Gustavo", txt)
        self.assertIn("com", txt)
        self.assertIn("Beto", txt)

    def test_varios_primeiros_autores(self):
        autores = [
            {"parlamentar_id_sapl": 6, "nome_parlamentar": "A", "primeiro_autor": True},
            {"parlamentar_id_sapl": 8, "nome_parlamentar": "B", "primeiro_autor": True},
            {"parlamentar_id_sapl": 3, "nome_parlamentar": "C", "primeiro_autor": False},
        ]
        txt = self._html_autoria(autores, 6)
        self.assertIn("A", txt.split("com")[0])
        self.assertIn("B", txt.split("com")[0])

    def test_nenhum_primeiro_autor(self):
        autores = [
            {"parlamentar_id_sapl": 6, "nome_parlamentar": "Gustavo", "primeiro_autor": None},
            {"parlamentar_id_sapl": 8, "nome_parlamentar": "Beto", "primeiro_autor": False},
        ]
        txt = self._html_autoria(autores, 6)
        self.assertTrue(txt.startswith("Autoria:"))
        self.assertNotIn("com", txt)

    def test_muitos_autores_resumo(self):
        autores = [
            {"parlamentar_id_sapl": i, "nome_parlamentar": f"V{i}", "primeiro_autor": None}
            for i in range(5)
        ]
        txt = self._html_autoria(autores, 99)
        self.assertIn("e mais 3 vereadores", txt)

    def test_js_html_autoria_pedido(self):
        self.assertIn("htmlAutoriaPedido", INDEX)
        self.assertIn("primeiro_autor === true", INDEX)
        self.assertIn("e mais", INDEX)
        self.assertNotIn("textoCoautoresPedido", INDEX)


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
