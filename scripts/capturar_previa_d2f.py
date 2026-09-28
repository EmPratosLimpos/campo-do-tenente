import time
from playwright.sync_api import sync_playwright

def gerar():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        
        # 1. 1440 Camara Todo periodo
        page = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="light")
        page.goto("http://127.0.0.1:8798/index.html", wait_until="networkidle")
        page.locator("#menu-lateral-periodos [data-periodo='todo']").click()
        time.sleep(1)
        page.screenshot(path="docs-previa/1440_camara.png", full_page=True)
        
        # 2. 1440 Vereadores Jorge Quege - Sanfona interna
        page = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="light")
        page.goto("http://127.0.0.1:8798/index.html", wait_until="networkidle")
        page.click("button[data-secao-lateral='vereadores']")
        page.wait_for_selector(".perfil-cabecalho", timeout=10000)
        page.select_option("#sel-vereador", label="Jorge Quege")
        page.wait_for_timeout(1500)
        presenca = page.locator("#tit-presenca").locator("xpath=ancestor::details[1]")
        if not presenca.evaluate("n => n.open"):
            page.locator("#tit-presenca").locator("xpath=ancestor::summary[1]").click()
            page.wait_for_timeout(500)
        inners = presenca.locator('details[name="ac-faltas"]')
        for i in range(inners.count()):
            inners.nth(i).locator("summary").click()
            page.wait_for_timeout(400)
        page.screenshot(path="docs-previa/1440_jorge_presenca_aberta.png", full_page=True)

        # 3. 390 Camara Todo periodo
        page = browser.new_page(viewport={"width": 390, "height": 844}, color_scheme="light")
        page.goto("http://127.0.0.1:8798/index.html", wait_until="networkidle")
        page.locator("#seletor-periodo-mobile [data-periodo='todo']").click()
        time.sleep(1)
        page.screenshot(path="docs-previa/390_camara.png", full_page=True)

        # 4. 390 Vereadores Jorge Quege
        page = browser.new_page(viewport={"width": 390, "height": 844}, color_scheme="light")
        page.goto("http://127.0.0.1:8798/index.html", wait_until="networkidle")
        page.locator("button[data-secao='vereadores']").click()
        page.wait_for_selector(".perfil-cabecalho", timeout=10000)
        page.select_option("#sel-vereador", label="Jorge Quege")
        page.wait_for_timeout(1500)
        presenca_m = page.locator("#tit-presenca").locator("xpath=ancestor::details[1]")
        if not presenca_m.evaluate("n => n.open"):
            page.locator("#tit-presenca").locator("xpath=ancestor::summary[1]").click()
            page.wait_for_timeout(500)
        inners_m = presenca_m.locator('details[name="ac-faltas"]')
        for i in range(inners_m.count()):
            inners_m.nth(i).locator("summary").click()
            page.wait_for_timeout(400)
        page.screenshot(path="docs-previa/390_jorge_presenca_aberta.png", full_page=True)

        browser.close()

if __name__ == "__main__":
    gerar()
