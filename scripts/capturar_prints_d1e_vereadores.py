#!/usr/bin/env python3
"""Captura prints da aba Vereadores para docs-previa (D1e)."""

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
PORTA = 8777


def servir() -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-m", "http.server", str(PORTA), "--bind", "127.0.0.1"],
        cwd=RAIZ,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def capturar(page, largura: int, ano: int, vereador_id: str, nome_arquivo: str) -> None:
    page.set_viewport_size({"width": largura, "height": 1200})
    page.goto(f"http://127.0.0.1:{PORTA}/index.html", wait_until="networkidle", timeout=120000)
    page.click(f'button[data-ano="{ano}"]')
    page.wait_for_timeout(2500)
    page.click('button[data-secao="vereadores"]')
    page.wait_for_timeout(1200)
    page.select_option("#sel-vereador", vereador_id)
    page.wait_for_timeout(1000)
    page.screenshot(path=str(SAIDA / nome_arquivo), full_page=True)


def main() -> int:
    SAIDA.mkdir(parents=True, exist_ok=True)
    proc = servir()
    time.sleep(1.2)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            for largura in (390, 1440):
                capturar(
                    page,
                    largura,
                    2026,
                    "1",
                    f"vereadores-jorge-quege-2026-{largura}.png",
                )
                capturar(
                    page,
                    largura,
                    2026,
                    "5",
                    f"vereadores-rafael-ventura-2026-{largura}.png",
                )
            browser.close()
    finally:
        proc.terminate()
    print(f"Prints em {SAIDA}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
