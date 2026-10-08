"""E5c: materia votada em mais de uma sessao aparece em cada periodo.

Dados de mentira para a regra e dados reais para a materia 811
(PLEG 4/2026, votada em 22/09/2026 e 29/09/2026). Nao faz pedido ao SAPL.
"""

from __future__ import annotations

import json
import pathlib
import sys
import threading
import time
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

RAIZ = pathlib.Path(__file__).resolve().parent.parent
for pasta in ("coletor", "dados/tratados"):
    if str(RAIZ / pasta) not in sys.path:
        sys.path.insert(0, str(RAIZ / pasta))

from gerar_dados_tela import montar_item, periodos, pll_votados_no_ano  # noqa: E402

try:
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_OK = True
    PLAYWRIGHT_MOTIVO = ""
except ImportError:
    PLAYWRIGHT_OK = False
    PLAYWRIGHT_MOTIVO = "playwright nao instalado"

CFG_FALSA = {"categorias": {"lista": [], "rotulos_especiais": {}}}


def voto_falso(sessao_id: int, data: str) -> dict:
    return {
        "sessao_id": sessao_id,
        "data_sessao": data,
        "resultado_texto_sapl": "UNANIMIDADE",
        "frase_resultado_sapl": None,
        "numero_votos_sim": 8,
        "numero_votos_nao": 0,
        "numero_abstencoes": 0,
    }


def materia_falsa() -> dict:
    return {
        "id": 9999,
        "numero": "1",
        "ano": "2026",
        "tipo_sigla": "PLEG",
        "ementa": "Materia de mentira votada duas vezes",
        "tema": None,
    }


def atuacao_falsa() -> dict:
    projeto = materia_falsa()
    projeto["votacoes_ordinarias"] = [voto_falso(101, "2026-09-22"), voto_falso(102, "2026-09-29")]
    return {"projetos_lei": [projeto]}


def sessoes_falsas() -> list[dict]:
    return [
        {"id": 101, "data": "2026-09-22"},
        {"id": 102, "data": "2026-09-29"},
    ]


class TestMultiplaVotacaoFixture(unittest.TestCase):
    def test_entra_na_ultima_sessao_com_a_votacao_da_sessao(self):
        materias = pll_votados_no_ano(atuacao_falsa())
        self.assertEqual(len(materias), 1)
        sessao, _mes, todo = periodos(materias, sessoes_falsas(), CFG_FALSA, {})
        self.assertEqual(len(sessao), 1)
        self.assertEqual(sessao[0]["data_sessao"], "2026-09-29")
        self.assertEqual(sessao[0]["sessao_id"], 102)
        self.assertEqual(
            [v["data_sessao"] for v in sessao[0]["votacoes"]],
            ["2026-09-22", "2026-09-29"],
        )
        self.assertEqual(len(todo), 1)
        self.assertEqual(todo[0]["data_sessao"], "2026-09-29")

    def test_entra_na_sessao_anterior_quando_ela_e_a_ultima(self):
        materias = pll_votados_no_ano(atuacao_falsa())
        sessao, _mes, _todo = periodos(materias, sessoes_falsas()[:1], CFG_FALSA, {})
        self.assertEqual(len(sessao), 1)
        self.assertEqual(sessao[0]["data_sessao"], "2026-09-22")
        self.assertEqual(sessao[0]["sessao_id"], 101)

    def test_mes_anterior_so_com_voto_do_mes(self):
        materias = pll_votados_no_ano(atuacao_falsa())
        _sessao, mes, _todo = periodos(materias, sessoes_falsas(), CFG_FALSA, {})
        self.assertEqual(mes, [])

    def test_item_so_com_uma_votacao_nao_tem_lista(self):
        projeto = materia_falsa()
        voto = voto_falso(101, "2026-09-22")
        item = montar_item(projeto, voto, [voto], CFG_FALSA, {})
        self.assertEqual(
            item["votacoes"],
            [
                {
                    "data_sessao": "2026-09-22",
                    "sessao_id": 101,
                    "turno": None,
                    "tipo_resultado": None,
                }
            ],
        )
        self.assertIsNone(item["turno"])
        self.assertIsNone(item["tipo_resultado"])


class TestPleg4Real(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.camara = json.loads(
            (RAIZ / "dados" / "tratados" / "materias_camara_legislatura.json").read_text(
                encoding="utf-8"
            )
        )

    def test_todo_conta_o_pleg_4_uma_vez_com_a_votacao_mais_recente(self):
        bloco = self.camara.get("todo") or []
        achados = [m for m in bloco if int(m["id"]) == 811]
        self.assertEqual(len(achados), 1)
        item = achados[0]
        self.assertEqual(item["tipo"], "PLEG 4/2026")
        datas = [v["data_sessao"] for v in item["votacoes"]]
        self.assertGreaterEqual(len(datas), 2)
        self.assertEqual(item["data_sessao"], max(datas))

    def test_sessao_so_traz_o_pleg_4_com_a_data_da_ultima_sessao(self):
        bloco = self.camara.get("sessao") or []
        achados = [m for m in bloco if int(m["id"]) == 811]
        if not achados:
            self.skipTest("PLEG 4/2026 fora da ultima sessao nesta base")
        self.assertEqual(len(achados), 1)
        todo = self.camara.get("todo") or []
        ultima = max(
            [m["data_sessao"] for m in todo]
            + [v["data_sessao"] for m in todo for v in m.get("votacoes") or []]
        )
        self.assertEqual(achados[0]["data_sessao"], ultima)

    def test_pleg_4_nao_se_repete_dentro_de_cada_periodo(self):
        for periodo in ("sessao", "mes", "todo"):
            bloco = self.camara.get(periodo) or []
            self.assertLessEqual(
                len([m for m in bloco if int(m["id"]) == 811]),
                1,
                f"PLEG 4/2026 repetido em {periodo}",
            )


class _Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(RAIZ), **kwargs)

    def log_message(self, format, *args):
        pass


@unittest.skipUnless(PLAYWRIGHT_OK, PLAYWRIGHT_MOTIVO)
class TestPreviaMultiplaVotacao(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servidor = ThreadingHTTPServer(("127.0.0.1", 8797), _Handler)
        thread = threading.Thread(target=cls.servidor.serve_forever, daemon=True)
        thread.start()
        cls.base = "http://127.0.0.1:8797/index.html"
        time.sleep(0.4)

    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown()

    def test_pleg_4_duas_datas_visiveis_no_periodo_todo(self):
        camara = json.loads(
            (RAIZ / "dados" / "tratados" / "materias_camara_legislatura.json").read_text(
                encoding="utf-8"
            )
        )
        item811 = next(
            (m for m in (camara.get("todo") or []) if int(m["id"]) == 811),
            None,
        )
        self.assertIsNotNone(item811, "PLEG 811 deveria existir em todo")
        tipo = item811["tipo"]
        datas_voto = [v["data_sessao"] for v in item811["votacoes"]]
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(self.base, wait_until="domcontentloaded", timeout=120000)
            page.wait_for_selector(
                "#bloco-votado-sessao .cab-cartao", state="visible", timeout=60000
            )
            page.click('button[data-periodo="todo"]')
            page.wait_for_selector(
                "#bloco-votado-todo .cab-cartao", state="visible", timeout=60000
            )
            page.wait_for_timeout(400)
            texto = page.inner_text("body")
            self.assertIn(tipo, texto)
            self.assertIn("2º turno", texto)
            item = page.locator(
                '#bloco-votado-todo li.item-votado:has-text("' + tipo + '")'
            )
            self.assertGreater(item.count(), 0, tipo + " deveria aparecer na lista Tudo")
            datas = item.locator(".materia-datas").inner_text()
            for d in datas_voto:
                partes = d.split("-")
                fmt = f"{partes[2]}/{partes[1]}/{partes[0]}"
                self.assertIn(fmt, datas)
            page.locator("#bloco-votado-todo .tag-turno").first.click()
            page.wait_for_timeout(400)
            folha = page.locator("#folha-generica-corpo").inner_text()
            self.assertIn("turno", folha.lower())
            browser.close()

    def test_ultimo_mes_mostra_projetos_do_mes(self):
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(self.base, wait_until="domcontentloaded", timeout=120000)
            page.wait_for_selector("#bloco-votado-sessao .cab-cartao", timeout=60000)
            page.click('button[data-periodo="mes"]')
            page.wait_for_timeout(600)
            titulo = page.locator("#tit-grafico-tipos-mes").inner_text()
            self.assertIn("itens votados no último mês", titulo)
            self.assertIn("itens votados no último mês", page.inner_text("#card-grafico-tipos-mes"))
            browser.close()


if __name__ == "__main__":
    unittest.main()
