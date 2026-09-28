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
            page = browser.new_page()
            page.goto(self.base, wait_until="networkidle", timeout=60000)
            
            # Click on Vereadores tab
            page.click("button[data-secao-lateral='vereadores']")
            page.wait_for_selector(".perfil-cabecalho", timeout=60000)
            
            # Select Rafael Ventura
            page.select_option("#sel-vereador", label="Rafael Ventura")
            page.wait_for_timeout(1000)
            
            # Open Votos for Rafael before checking votes
            page.locator("#tit-votos").locator("xpath=ancestor::summary[1]").click()
            page.wait_for_timeout(500)
            texto_rafael = page.inner_text("body")
            self.assertIn("26\nSim", texto_rafael)
            self.assertIn("93\nPresidente que não votou", texto_rafael)
            
            # Check filter for Rafael
            page.select_option("#filtro-voto", label="Presidente que não votou")
            page.wait_for_timeout(1000)
            page.locator("#tit-votos").locator("xpath=ancestor::summary[1]").click()
            page.wait_for_timeout(500)
            texto_rafael_filtro = page.inner_text("body")
            self.assertIn("93 registros", texto_rafael_filtro)
            
            # Check Accordion exclusivity
            presenca_card = page.locator("#tit-presenca").locator("xpath=ancestor::details[1]")
            pll_card = page.locator("#tit-pll").locator("xpath=ancestor::details[1]")
            votos_card = page.locator("#tit-votos").locator("xpath=ancestor::details[1]")
            
            # Initially votos is open because we clicked it
            self.assertTrue(votos_card.evaluate("node => node.open"))
            self.assertFalse(presenca_card.evaluate("node => node.open"))
            self.assertFalse(pll_card.evaluate("node => node.open"))
            
            # Click PLL
            page.locator("#tit-pll").locator("xpath=ancestor::summary[1]").click()
            page.wait_for_timeout(500)
            self.assertFalse(votos_card.evaluate("node => node.open"))
            self.assertTrue(pll_card.evaluate("node => node.open"))

            # Click Votos
            page.locator("#tit-votos").locator("xpath=ancestor::summary[1]").click()
            page.wait_for_timeout(500)
            self.assertTrue(votos_card.evaluate("node => node.open"))
            self.assertFalse(pll_card.evaluate("node => node.open"))


            # Open Votos for Rafael
            votos_card_rafael = page.locator("#tit-votos").locator("..").locator("..")
            page.locator("#tit-votos").locator("xpath=ancestor::summary[1]").click()
            page.wait_for_timeout(500)
            
            # Check Cassado badge for Rafael Ventura (should NOT have)
            texto_rafael = page.inner_text("body")

            self.assertNotIn("Cassado", page.locator(".perfil-nome").inner_text())

            # Select Jorge Quege
            page.select_option("#sel-vereador", label="Jorge Quege")
            page.wait_for_timeout(1000)
            
            # Check Cassado badge for Jorge Quege
            self.assertIn("Cassado", page.locator(".perfil-nome").inner_text())
            

            # Open Votos for Jorge
            votos_card_jorge = page.locator("#tit-votos").locator("..").locator("..")
            page.locator("#tit-votos").locator("xpath=ancestor::summary[1]").click()
            page.wait_for_timeout(500)

            # Test Votos inner content
            texto_jorge = page.inner_text("body")

            self.assertIn("26\nSim", texto_jorge)
            self.assertIn("72\nLicença para tratamento de saúde", texto_jorge)
            self.assertIn("21\nFora do mandato naquela data", texto_jorge)
            
            # Check filter for Jorge
            page.select_option("#filtro-voto", label="Licença para tratamento de saúde")
            page.wait_for_timeout(1000)
            page.locator("#tit-votos").locator("xpath=ancestor::summary[1]").click()
            page.wait_for_timeout(500)
            texto_jorge_filtro = page.inner_text("body")
            self.assertIn("72 registros", texto_jorge_filtro)


            # Open Presenca card for Jorge
            presenca_card = page.locator("#tit-presenca").locator("xpath=ancestor::details[1]")
            page.locator("#tit-presenca").locator("xpath=ancestor::summary[1]").click()
            page.wait_for_timeout(500)
            
            # Check inner accordion exclusivity
            inner_acs = presenca_card.locator('details[name="ac-faltas"]')
            self.assertGreater(inner_acs.count(), 0)
            
            ac_1 = inner_acs.nth(0)
            ac_2 = inner_acs.nth(1)
            self.assertFalse(ac_1.evaluate("node => node.open"))
            self.assertFalse(ac_2.evaluate("node => node.open"))

            def texto_visivel_sem_literais_js():
                page.locator("#tit-presenca").locator("xpath=ancestor::summary[1]").click()
                page.wait_for_timeout(400)
                if not presenca_card.evaluate("node => node.open"):
                    page.locator("#tit-presenca").locator("xpath=ancestor::summary[1]").click()
                    page.wait_for_timeout(400)
                for inner in presenca_card.locator('details[name="ac-faltas"]').all():
                    inner.locator("summary").first.click()
                    page.wait_for_timeout(150)
                texto = page.locator("body").inner_text()
                for bad in ["esc(", "' +", "+ '", "length)", "undefined", "NaN", "null"]:
                    self.assertNotIn(bad, texto)

            ac_1.locator("summary").first.click()
            page.wait_for_timeout(500)
            self.assertTrue(ac_1.evaluate("node => node.open"))
            self.assertFalse(ac_2.evaluate("node => node.open"))

            texto_visivel_sem_literais_js()

            ac_2.locator("summary").first.click()
            page.wait_for_timeout(500)
            self.assertFalse(ac_1.evaluate("node => node.open"))
            self.assertTrue(ac_2.evaluate("node => node.open"))

            browser.close()

if __name__ == "__main__":
    unittest.main()
