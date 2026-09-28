"""Playwright: layout responsivo (390 e 1440 px), sem vazamento horizontal."""

from __future__ import annotations

import pathlib
import re
import threading
import time
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

RAIZ = pathlib.Path(__file__).resolve().parent.parent

try:
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_OK = True
    PLAYWRIGHT_MOTIVO = ""
except ImportError:
    PLAYWRIGHT_OK = False
    PLAYWRIGHT_MOTIVO = "playwright nao instalado"


class _Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(RAIZ), **kwargs)


def _sem_scroll_horizontal(page) -> None:
    dims = page.evaluate(
        """() => ({
          sw: document.documentElement.scrollWidth,
          cw: document.documentElement.clientWidth
        })"""
    )
    assert dims["sw"] <= dims["cw"] + 1, f"scroll horizontal sw={dims['sw']} cw={dims['cw']}"


def _cartoes_dentro(page, seletor_area: str) -> None:
    page.wait_for_selector(seletor_area, timeout=30000)
    overflow = page.eval_on_selector(
        seletor_area,
        """el => {
          const lim = el.getBoundingClientRect().right;
          const alvos = el.querySelectorAll('.card-app, .secao, .bloco-votado');
          for (const node of alvos) {
            const r = node.getBoundingClientRect();
            if (r.right > lim + 1) return node.className || node.tagName;
          }
          return '';
        }""",
    )
    assert not overflow, f"cartao ultrapassa area: {overflow}"


@unittest.skipUnless(PLAYWRIGHT_OK, PLAYWRIGHT_MOTIVO)
class TestTelaLayout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servidor = ThreadingHTTPServer(("127.0.0.1", 8794), _Handler)
        thread = threading.Thread(target=cls.servidor.serve_forever, daemon=True)
        thread.start()
        cls.base = "http://127.0.0.1:8794/index.html"
        time.sleep(0.35)

    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown()

    def _ir_aba(self, page, secao: str) -> None:
        largura = page.viewport_size["width"] if page.viewport_size else 390
        if largura >= 900:
            page.click(f'button[data-secao-lateral="{secao}"]')
        elif secao == "vereadores":
            page.click('button[data-secao="vereadores"]')
        else:
            page.click('button[data-secao="camara"]')
        page.wait_for_timeout(400)

    def _assert_sem_elementos_proibidos(self, page) -> None:
        texto = page.inner_text("body")
        self.assertNotIn("nao existem no SAPL", texto.lower())
        self.assertIsNone(page.query_selector("#seletor-ano-wrap"))
        self.assertIsNone(page.query_selector("button[data-ano]"))

    def _caso(self, page, largura: int, secao: str) -> None:
        page.set_viewport_size({"width": largura, "height": 900})
        page.goto(self.base, wait_until="networkidle", timeout=120000)
        page.wait_for_timeout(800)
        self._assert_sem_elementos_proibidos(page)
        self._ir_aba(page, secao)
        _sem_scroll_horizontal(page)
        if secao == "camara":
            _cartoes_dentro(page, "#painel-camara")
        else:
            _cartoes_dentro(page, "#painel-vereadores")
        lateral = page.query_selector("#menu-lateral")
        self.assertIsNotNone(lateral)
        visivel = page.locator("#menu-lateral").is_visible()
        if largura >= 900:
            self.assertTrue(visivel, "menu lateral deve aparecer em desktop")
        else:
            self.assertFalse(visivel, "menu lateral nao deve aparecer no celular")

    def test_layout_camara_e_vereadores(self):
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            for largura in (390, 1440):
                for secao in ("camara", "vereadores"):
                    with self.subTest(largura=largura, secao=secao):
                        self._caso(page, largura, secao)
            browser.close()


if __name__ == "__main__":
    unittest.main()
