import json
import pathlib
import re
import unittest
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

try:
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_OK = True
    PLAYWRIGHT_MOTIVO = ""
except ImportError:
    PLAYWRIGHT_OK = False
    PLAYWRIGHT_MOTIVO = "playwright nao instalado"

RAIZ = pathlib.Path(__file__).resolve().parent.parent


def votos_da_legislatura(slug: str) -> dict:
    dados = json.loads(
        (RAIZ / "dados" / "tratados" / "atuacao_vereadores_legislatura.json").read_text(
            encoding="utf-8"
        )
    )
    for v in dados.get("vereadores") or []:
        if v.get("slug_codigo") == slug:
            return v["votos"]
    raise AssertionError(f"vereador {slug} ausente")


def nominais_por_estado(slug: str, estado: str) -> int:
    votos = votos_da_legislatura(slug)
    return sum(1 for n in votos.get("nominais") or [] if n.get("estado") == estado)


class _Handler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


@unittest.skipUnless(PLAYWRIGHT_OK, PLAYWRIGHT_MOTIVO)
class TestVotosVereadores(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servidor = ThreadingHTTPServer(("127.0.0.1", 8795), _Handler)
        thread = threading.Thread(target=cls.servidor.serve_forever, daemon=True)
        thread.start()
        cls.base = "http://127.0.0.1:8795/index.html"
        time.sleep(0.35)

    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown()

    def test_votos_vereadores(self):
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(self.base, wait_until="networkidle", timeout=60000)

            page.click("button[data-secao-lateral='vereadores']")
            page.wait_for_selector("#sel-vereador", timeout=60000)

            page.select_option("#sel-vereador", label="Rafael Ventura")
            page.wait_for_timeout(1000)

            page.click("button.contagem-item[data-pl-filtro='aprovado']")
            page.wait_for_timeout(500)
            texto_rafael_aprovados = page.locator(".lista-pll").inner_text()
            self.assertIn("Administração e finanças", texto_rafael_aprovados)
            self.assertNotIn("Tema: .", texto_rafael_aprovados)

            opcoes_rafael = page.locator("#sel-vereador option").all_inner_texts()
            self.assertTrue(all("(Cassado)" not in o for o in opcoes_rafael if "Rafael" in o))

            texto_rafael = page.inner_text("body")
            votos_rafael = votos_da_legislatura("rafael-ventura")
            self.assertIn(f"{votos_rafael['sim']}\nSim", texto_rafael)
            self.assertIn(
                f"{votos_rafael['presidente_que_nao_votou']}\nPresidente que não votou",
                texto_rafael,
            )

            page.click("button.voto-card[data-voto-card='presidente_que_nao_votou']")
            page.wait_for_timeout(1000)
            texto_rafael_filtro = page.inner_text("body")
            self.assertIn(
                f"{nominais_por_estado('rafael-ventura', 'presidente_que_nao_votou')} registros",
                texto_rafael_filtro,
            )
            self.assertNotIn("Pedido de Vistas", texto_rafael_filtro)

            for titulo_id in ("tit-presenca", "tit-pll", "tit-votos"):
                self.assertTrue(page.locator("#" + titulo_id).is_visible())

            self.assertNotIn("Cassado", page.locator(".sel-vereador-face .nm").inner_text())

            page.select_option("#sel-vereador", label="Jorge Quege (Cassado)")
            page.wait_for_timeout(1000)

            opcoes_jorge = [o for o in page.locator("#sel-vereador option").all_inner_texts() if "Quege" in o]
            self.assertEqual(len(opcoes_jorge), 1)
            self.assertIn("(Cassado)", opcoes_jorge[0])

            self.assertIn("Cassado", page.locator("#notas-vereador-wrap .perfil-nome").inner_text())

            texto_jorge = page.inner_text("body")
            votos_jorge = votos_da_legislatura("jorge-quege")
            self.assertIn(f"{votos_jorge['sim']}\nSim", texto_jorge)
            self.assertIn(
                f"{votos_jorge['ausente_com_justificativa']}\nAusente com justificativa",
                texto_jorge,
            )
            self.assertNotIn("Fora do mandato naquela data", texto_jorge)

            page.click("button.voto-card[data-voto-card='ausente_com_justificativa']")
            page.wait_for_timeout(1000)
            texto_jorge_filtro = page.inner_text("body")
            self.assertIn(
                f"{nominais_por_estado('jorge-quege', 'ausente_com_justificativa')} registros",
                texto_jorge_filtro,
            )

            btn_falta = page.locator("[data-falta-presenca='falta_com_justificativa']")
            if btn_falta.count():
                btn_falta.first.click()
                page.wait_for_timeout(400)
                self.assertEqual(page.locator("#folha-generica-backdrop.ativo").count(), 1)
                page.keyboard.press("Escape")
                page.wait_for_timeout(200)

            texto = page.locator("body").inner_text()
            for bad in ["esc(", "' +", "+ '", "length)", "undefined", "NaN", "null", "(s)", "(ões)"]:
                self.assertNotIn(bad, texto)

            browser.close()


if __name__ == "__main__":
    unittest.main()
