import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8798/index.html"
OUT = Path("docs-previa")


def capturar(browser, largura, tema, nome, preparar):
    page = browser.new_page(
        viewport={"width": largura, "height": 900 if largura > 500 else 844},
        color_scheme=tema,
    )
    page.goto(BASE, wait_until="networkidle")
    if tema == "dark":
        page.evaluate(
            """() => {
              document.documentElement.setAttribute('data-tema', 'escuro');
              localStorage.setItem('epl-tema', 'escuro');
            }"""
        )
        page.wait_for_timeout(300)
    preparar(page)
    page.screenshot(path=str(OUT / nome), full_page=True)
    page.close()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()

        def prep_camara(page):
            if page.viewport_size["width"] >= 900:
                page.locator("#menu-lateral-periodos [data-periodo='todo']").click()
            else:
                page.locator("#seletor-periodo-mobile [data-periodo='todo']").click()
            page.wait_for_timeout(800)

        for tema in ("light", "dark"):
            capturar(browser, 1440, tema, f"1440_camara_todo_{tema}.png", prep_camara)
            capturar(browser, 390, tema, f"390_camara_todo_{tema}.png", prep_camara)

        def prep_vereador(page, nome_opcao):
            if page.viewport_size["width"] >= 900:
                page.click("button[data-secao-lateral='vereadores']")
            else:
                page.click("button[data-secao='vereadores']")
            page.wait_for_selector(".perfil-cabecalho", timeout=60000)
            page.select_option("#sel-vereador", label=nome_opcao)
            page.wait_for_timeout(1200)

        for tema in ("light", "dark"):
            for vereador, slug in (
                ("Jorge Quege (Cassado)", "jorge"),
                ("Rafael Ventura", "rafael"),
            ):
                def prep(page, v=vereador):
                    prep_vereador(page, v)

                capturar(browser, 1440, tema, f"1440_{slug}_{tema}.png", prep)
                capturar(browser, 390, tema, f"390_{slug}_{tema}.png", prep)

        browser.close()


if __name__ == "__main__":
    main()
