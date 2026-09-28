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
            
            texto_rafael = page.inner_text("body")
            self.assertIn("26\nSim", texto_rafael)
            self.assertIn("93\nPresidente que não votou", texto_rafael)
            
            # Check filter for Rafael
            page.select_option("#filtro-voto", label="Presidente que não votou")
            page.wait_for_timeout(1000)
            texto_rafael_filtro = page.inner_text("body")
            self.assertIn("93 registros", texto_rafael_filtro)
            
            # Select Jorge Quege
            page.select_option("#sel-vereador", label="Jorge Quege")
            page.wait_for_timeout(1000)
            
            texto_jorge = page.inner_text("body")
            self.assertIn("26\nSim", texto_jorge)
            self.assertIn("72\nLicença para tratamento de saúde", texto_jorge)
            self.assertIn("21\nFora do mandato naquela data", texto_jorge)
            
            # Check filter for Jorge
            page.select_option("#filtro-voto", label="Licença para tratamento de saúde")
            page.wait_for_timeout(1000)
            texto_jorge_filtro = page.inner_text("body")
            self.assertIn("72 registros", texto_jorge_filtro)

            browser.close()

if __name__ == "__main__":
    unittest.main()
