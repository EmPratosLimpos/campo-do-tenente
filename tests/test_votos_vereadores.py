import re
import unittest
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from playwright.sync_api import sync_playwright

class _Handler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

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
            page.wait_for_selector(".perfil-cabecalho", timeout=60000)

            def abrir_se_fechado(titulo_id):
                page.locator("#" + titulo_id).locator("xpath=ancestor::details[1]").evaluate(
                    """n => {
                      n.open = true;
                      var s = n.querySelector('summary');
                      if (s) s.setAttribute('aria-expanded', 'true');
                    }"""
                )
                page.wait_for_timeout(200)

            page.select_option("#sel-vereador", label="Rafael Ventura")
            page.wait_for_timeout(1000)

            abrir_se_fechado("tit-pll")
            page.click("button[data-filtro-pll='aprovado']")
            page.wait_for_timeout(500)
            texto_rafael_aprovados = page.locator(".lista-pll").inner_text()
            self.assertIn("Tema: Administração e finanças.", texto_rafael_aprovados)
            self.assertNotIn("Tema: .", texto_rafael_aprovados)

            opcoes_rafael = page.locator("#sel-vereador option").all_inner_texts()
            self.assertTrue(all("(Cassado)" not in o for o in opcoes_rafael if "Rafael" in o))

            page.locator("#tit-votos").locator("xpath=ancestor::summary[1]").click()
            page.wait_for_timeout(500)
            texto_rafael = page.inner_text("body")
            self.assertIn("26\nSim", texto_rafael)
            self.assertIn("93\nPresidente que não votou", texto_rafael)

            page.select_option("#filtro-voto", label="Presidente que não votou")
            page.wait_for_timeout(1000)
            abrir_se_fechado("tit-votos")
            texto_rafael_filtro = page.inner_text("body")
            self.assertIn("93 registros", texto_rafael_filtro)

            abrir_se_fechado("tit-pll")
            abrir_se_fechado("tit-votos")

            presenca_card = page.locator("#tit-presenca").locator("xpath=ancestor::details[1]")
            pll_card = page.locator("#tit-pll").locator("xpath=ancestor::details[1]")
            votos_card = page.locator("#tit-votos").locator("xpath=ancestor::details[1]")
            abrir_se_fechado("tit-presenca")

            self.assertTrue(votos_card.evaluate("node => node.open"))
            self.assertTrue(pll_card.evaluate("node => node.open"))
            self.assertTrue(presenca_card.evaluate("node => node.open"))

            for titulo_id in ("tit-presenca", "tit-pll", "tit-votos"):
                texto_cab = page.locator("#" + titulo_id).locator("xpath=ancestor::summary[1]").inner_text()
                self.assertIsNone(re.search(r"\d", texto_cab), f"cabecalho com numero: {titulo_id} -> {texto_cab}")

            self.assertNotIn("Cassado", page.locator(".perfil-nome").inner_text())

            page.select_option("#sel-vereador", label="Jorge Quege (Cassado)")
            page.wait_for_timeout(1000)

            opcoes_jorge = [o for o in page.locator("#sel-vereador option").all_inner_texts() if "Quege" in o]
            self.assertEqual(len(opcoes_jorge), 1)
            self.assertIn("(Cassado)", opcoes_jorge[0])

            self.assertIn("Cassado", page.locator(".perfil-nome").inner_text())

            abrir_se_fechado("tit-votos")

            texto_jorge = page.inner_text("body")
            self.assertIn("26\nSim", texto_jorge)
            self.assertIn("72\nLicença para tratamento de saúde", texto_jorge)
            self.assertIn("21\nFora do mandato naquela data", texto_jorge)

            page.select_option("#filtro-voto", label="Licença para tratamento de saúde")
            page.wait_for_timeout(1000)
            abrir_se_fechado("tit-votos")
            texto_jorge_filtro = page.inner_text("body")
            self.assertIn("72 registros", texto_jorge_filtro)

            presenca_card = page.locator("#tit-presenca").locator("xpath=ancestor::details[1]")
            if not presenca_card.evaluate("node => node.open"):
                page.locator("#tit-presenca").locator("xpath=ancestor::summary[1]").click()
                page.wait_for_timeout(400)

            inner_acs = presenca_card.locator("details.ac-cartao-inner")
            self.assertGreater(inner_acs.count(), 0)

            ac_1 = inner_acs.nth(0)
            ac_2 = inner_acs.nth(1)

            def texto_visivel_sem_literais_js():
                if not presenca_card.evaluate("node => node.open"):
                    page.locator("#tit-presenca").locator("xpath=ancestor::summary[1]").click()
                    page.wait_for_timeout(400)
                for i in range(inner_acs.count()):
                    inner_acs.nth(i).locator("summary").click()
                    page.wait_for_timeout(150)
                texto = page.locator("body").inner_text()
                for bad in ["esc(", "' +", "+ '", "length)", "undefined", "NaN", "null"]:
                    self.assertNotIn(bad, texto)

            ac_1.evaluate("n => { n.open = true; }")
            ac_2.evaluate("n => { n.open = true; }")
            page.wait_for_timeout(300)
            self.assertTrue(ac_1.evaluate("node => node.open"))
            self.assertTrue(ac_2.evaluate("node => node.open"))

            for i in range(min(3, inner_acs.count())):
                cab = inner_acs.nth(i).locator("summary").inner_text()
                self.assertNotRegex(cab, r"\(\d+\)")

            texto_visivel_sem_literais_js()

            browser.close()

if __name__ == "__main__":
    unittest.main()
