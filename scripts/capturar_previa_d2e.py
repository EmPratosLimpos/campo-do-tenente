import time
import os
import pathlib
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from playwright.sync_api import sync_playwright

class _Handler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args): pass

def gerar():
    os.makedirs("docs-previa", exist_ok=True)
    servidor = ThreadingHTTPServer(("127.0.0.1", 8798), _Handler)
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()
    
    with sync_playwright() as p:
        browser = p.chromium.launch()
        
        # 1440 Claro Camara
        page = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="light")
        page.goto("http://127.0.0.1:8798/index.html", wait_until="networkidle")
        page.screenshot(path="docs-previa/1440_claro_camara.png", full_page=True)
        
        # 1440 Escuro Camara
        page = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="dark")
        page.goto("http://127.0.0.1:8798/index.html", wait_until="networkidle")
        page.screenshot(path="docs-previa/1440_escuro_camara.png", full_page=True)
        
        # 390 Claro Camara
        page = browser.new_page(viewport={"width": 390, "height": 844}, color_scheme="light")
        page.goto("http://127.0.0.1:8798/index.html", wait_until="networkidle")
        page.screenshot(path="docs-previa/390_claro_camara.png", full_page=True)
        
        # 1440 Claro Vereadores Jorge
        page = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="light")
        page.goto("http://127.0.0.1:8798/index.html", wait_until="networkidle")
        page.click("button[data-secao-lateral='vereadores']")
        page.wait_for_selector(".perfil-cabecalho", timeout=10000)
        page.select_option("#sel-vereador", label="Jorge Quege")
        time.sleep(1)
        # Open presenca
        page.locator("#tit-presenca").locator("..").click()
        time.sleep(0.5)
        # Open licenca
        page.locator('details[name="ac-faltas"]').nth(0).locator("summary").first.click()
        time.sleep(0.5)
        page.screenshot(path="docs-previa/1440_claro_jorge.png", full_page=True)
        
        # 390 Escuro Vereadores Rafael
        page = browser.new_page(viewport={"width": 390, "height": 844}, color_scheme="dark")
        page.goto("http://127.0.0.1:8798/index.html", wait_until="networkidle")
        page.click("button[data-secao-lateral='vereadores']")
        page.wait_for_selector(".perfil-cabecalho", timeout=10000)
        page.select_option("#sel-vereador", label="Rafael Ventura")
        time.sleep(1)
        page.screenshot(path="docs-previa/390_escuro_rafael.png", full_page=True)
        
        browser.close()
    
    servidor.shutdown()

if __name__ == "__main__":
    gerar()
