#!/usr/bin/env python3
"""Captura prints lado a lado Campo Largo x Campo do Tenente."""

from __future__ import annotations

import pathlib
import subprocess
import sys
import time

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Instale playwright: pip install playwright && playwright install chromium")
    sys.exit(1)

RAIZ = pathlib.Path(__file__).resolve().parent.parent
SAIDA = RAIZ / "docs-previa"
REF = RAIZ / "referencia-campo-largo"
PORTA_REF = 8765
PORTA_CT = 8766


def servir(pasta: pathlib.Path, porta: int) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-m", "http.server", str(porta), "--bind", "127.0.0.1"],
        cwd=pasta,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def capturar(page, url: str, prefixo: str, largura: int, tema: str, aba: str) -> None:
    page.set_viewport_size({"width": largura, "height": 900})
    page.goto(url, wait_until="networkidle", timeout=120000)
    page.evaluate(
        """(tema) => {
      document.documentElement.setAttribute('data-tema', tema);
      localStorage.setItem('dashboard-campo-tenente-tema', tema);
      localStorage.setItem('dashboard-campo-largo-tema', tema);
    }""",
        tema,
    )
    if aba == "vereadores":
        page.evaluate("""() => {
          var b = document.querySelector('[data-secao=\"vereadores\"]');
          if (b) b.click();
        }""")
        page.wait_for_timeout(1500)
    else:
        page.wait_for_timeout(800)
    nome = f"{prefixo}-{largura}-{tema}-{aba}.png"
    page.screenshot(path=str(SAIDA / nome), full_page=True)


def main():
    SAIDA.mkdir(parents=True, exist_ok=True)
    s1 = servir(REF, PORTA_REF)
    s2 = servir(RAIZ, PORTA_CT)
    time.sleep(1.5)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            for largura in (390, 1440):
                for tema in ("claro", "escuro"):
                    for aba in ("camara", "vereadores"):
                        capturar(
                            page,
                            f"http://127.0.0.1:{PORTA_REF}/index.html",
                            "campolargo",
                            largura,
                            tema,
                            aba,
                        )
                        capturar(
                            page,
                            f"http://127.0.0.1:{PORTA_CT}/index.html",
                            "campodotenente",
                            largura,
                            tema,
                            aba,
                        )
            browser.close()
    finally:
        s1.terminate()
        s2.terminate()
    print(f"Prints em {SAIDA}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
