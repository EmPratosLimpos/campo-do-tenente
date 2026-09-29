#!/usr/bin/env python3
"""Gera prints locais em docs-previa/ (nao commitar)."""

from __future__ import annotations

import pathlib
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from playwright.sync_api import sync_playwright

RAIZ = pathlib.Path(__file__).resolve().parent.parent
OUT = RAIZ / "docs-previa"


class _Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(RAIZ), **kwargs)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    servidor = ThreadingHTTPServer(("127.0.0.1", 8798), _Handler)
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.35)
    base = "http://127.0.0.1:8798/index.html"

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for tema in ("claro", "escuro"):
            for largura in (390, 1440):
                page = browser.new_page(viewport={"width": largura, "height": 900})
                page.goto(base, wait_until="networkidle", timeout=180000)
                page.evaluate(
                    """(t) => {
                      localStorage.setItem("dashboard-campo-tenente-tema", t);
                      document.documentElement.setAttribute("data-tema", t);
                    }""",
                    tema,
                )
                page.reload(wait_until="networkidle")
                page.wait_for_timeout(500)
                if largura >= 900:
                    page.click('button[data-secao-lateral="camara"]')
                page.screenshot(path=str(OUT / f"d2-{largura}-camara-{tema}.png"), full_page=True)
                if largura >= 900:
                    page.click('button[data-secao-lateral="vereadores"]')
                else:
                    page.click('button[data-secao="vereadores"]')
                page.wait_for_selector("#sel-vereador", timeout=120000)
                for vid, slug in (("1", "jorge-quege"), ("5", "rafael-ventura")):
                    page.select_option("#sel-vereador", vid)
                    page.wait_for_timeout(400)
                    page.screenshot(
                        path=str(OUT / f"d2-{largura}-vereadores-{slug}-{tema}.png"),
                        full_page=True,
                    )
        browser.close()
    servidor.shutdown()
    print(f"Prints em {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
