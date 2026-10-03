"""Playwright: folha de compartilhar, cartoes PNG e folha de impressao (fases 11 e 12)."""

from __future__ import annotations

import pathlib
import struct
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


def _png_wh(data: bytes) -> tuple[int, int]:
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("nao e PNG")
    w, h = struct.unpack(">II", data[16:24])
    return w, h


@unittest.skipUnless(PLAYWRIGHT_OK, PLAYWRIGHT_MOTIVO)
class TestTelaCompartilhar(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servidor = ThreadingHTTPServer(("127.0.0.1", 8802), _Handler)
        thread = threading.Thread(target=cls.servidor.serve_forever, daemon=True)
        thread.start()
        cls.base = "http://127.0.0.1:8802/index.html"
        time.sleep(0.35)

    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown()

    def _nova_pagina(self, browser, largura: int, escuro: bool):
        altura = 844 if largura < 900 else 900
        page = browser.new_page(
            viewport={"width": largura, "height": altura},
            color_scheme="dark" if escuro else "light",
        )
        erros: list[str] = []
        page.on("pageerror", lambda e: erros.append(str(e)))
        page.goto(self.base, wait_until="domcontentloaded", timeout=120000)
        if escuro:
            page.evaluate("document.documentElement.setAttribute('data-tema','escuro')")
        page.wait_for_selector("#bloco-votado-sessao .cab-cartao", timeout=60000)
        page.wait_for_timeout(400)
        return page, erros

    def _ir_aba(self, page, secao: str) -> None:
        largura = page.viewport_size["width"] if page.viewport_size else 390
        if largura >= 900:
            page.click(f'button[data-secao-lateral="{secao}"]')
        else:
            page.click(f'button[data-secao="{secao}"]')
        page.wait_for_timeout(400)

    def _abrir_share_topo(self, page) -> None:
        page.click(".topo-fixo .btn-compartilhar-topo")
        page.wait_for_selector("#share-sheet-backdrop.ativo", timeout=10000)
        page.wait_for_function(
            """() => {
              const cv = document.getElementById('share-canvas-balao');
              return cv && cv.width === 1080 && cv.height === 1350;
            }""",
            timeout=20000,
        )
        page.wait_for_function(
            """() => {
              const el = document.getElementById('share-sheet');
              const r = el.getBoundingClientRect();
              return Math.abs(r.bottom - window.innerHeight) < 3;
            }""",
            timeout=5000,
        )

    def _fluxo_share(self, page, largura: int, escuro: bool, secao: str) -> None:
        self._ir_aba(page, secao)
        self._abrir_share_topo(page)
        rect = page.evaluate(
            """() => {
              const el = document.getElementById('share-sheet');
              const r = el.getBoundingClientRect();
              return { top: r.top, bottom: r.bottom };
            }"""
        )
        vh = page.viewport_size["height"]
        self.assertGreaterEqual(rect["top"], -2)
        self.assertLessEqual(rect["bottom"], vh + 2)

        w, h = page.evaluate(
            """() => {
              const cv = document.getElementById('share-canvas-balao');
              return [cv.width, cv.height];
            }"""
        )
        self.assertEqual([w, h], [1080, 1350])

        page.click('#share-sheet button[data-rede="feed"]')
        page.wait_for_selector("#share-rede:not([hidden])", timeout=10000)
        with page.expect_download() as dl_info:
            page.click('#share-sheet button[data-acao="baixar"]')
        download = dl_info.value
        png = download.path()
        self.assertIsNotNone(png)
        with open(png, "rb") as f:
            pw, ph = _png_wh(f.read())
        self.assertEqual((pw, ph), (1080, 1350))

        page.click('#share-sheet button[data-rede="story"]')
        page.wait_for_function(
            """() => document.getElementById('share-canvas-rede').classList.contains('story')""",
            timeout=10000,
        )
        with page.expect_download() as dl_story:
            page.click('#share-sheet button[data-acao="baixar"]')
        path_story = dl_story.value.path()
        self.assertIsNotNone(path_story)
        with open(path_story, "rb") as f:
            sw, sh = _png_wh(f.read())
        self.assertEqual((sw, sh), (1080, 1920))

        page.context.grant_permissions(["clipboard-read", "clipboard-write"])
        page.click('#share-sheet button[data-acao="link"]')
        page.wait_for_function(
            """() => (document.getElementById('share-sheet-feedback').textContent || '').includes('Link copiado')""",
            timeout=5000,
        )

        page.evaluate(
            """() => {
              window.__printChamado = false;
              window.print = function () { window.__printChamado = true; };
            }"""
        )
        page.click('#share-sheet button[data-acao="pdf"]')
        page.wait_for_function("() => window.__printChamado === true", timeout=5000)
        html = page.inner_html("#folha-impressao")
        self.assertIn("empratoslimpos.com", html)
        self.assertIn("marca/qr-site.svg", html)

        page.emulate_media(media="print")
        pdf_bytes = page.pdf(format="A4")
        self.assertGreater(len(pdf_bytes), 500)
        page.emulate_media(media="screen")

    def test_compartilhar_sem_erros_js(self):
        casos = (
            (390, False, "camara"),
            (390, True, "camara"),
            (390, False, "vereadores"),
            (1440, False, "camara"),
            (1440, True, "vereadores"),
        )
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for largura, escuro, secao in casos:
                with self.subTest(largura=largura, escuro=escuro, secao=secao):
                    page, erros = self._nova_pagina(browser, largura, escuro)
                    try:
                        self._fluxo_share(page, largura, escuro, secao)
                    finally:
                        page.close()
                    self.assertEqual(erros, [], f"pageerror: {erros}")


if __name__ == "__main__":
    unittest.main()
