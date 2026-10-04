"""RI-1h: Playwright sem pageerror, barra e rosca, rolagem lateral."""

from __future__ import annotations

import json
import pathlib
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


def _config_com_grafico(modo: str) -> str:
    cfg = json.loads((RAIZ / "config_cidade.json").read_text(encoding="utf-8"))
    cfg.setdefault("painel", {})["grafico_tipos_votacao"] = modo
    return json.dumps(cfg, ensure_ascii=False)


@unittest.skipUnless(PLAYWRIGHT_OK, PLAYWRIGHT_MOTIVO)
class TestRi1hPlaywright(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servidor = ThreadingHTTPServer(("127.0.0.1", 8802), _Handler)
        thread = threading.Thread(target=cls.servidor.serve_forever, daemon=True)
        thread.start()
        cls.base = "http://127.0.0.1:8802/index.html"
        time.sleep(0.4)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.servidor.shutdown()
        finally:
            cls.servidor.server_close()

    def _aguardar_dados(self, page):
        page.wait_for_load_state("networkidle", timeout=90000)

    def _ir_secao(self, page, largura: int, secao: str):
        if largura >= 900:
            alvo = {
                "camara": "button[data-secao-lateral='camara']",
                "vereadores": "button[data-secao-lateral='vereadores']",
                "prefeito": "#nav-lateral-prefeito",
            }[secao]
            page.locator(alvo).click(timeout=15000)
        else:
            page.locator(f"#nav-principal button[data-secao='{secao}']").click(timeout=15000)
        if secao == "prefeito":
            page.wait_for_selector("#painel-prefeito.ativo", timeout=30000)
        elif secao == "vereadores":
            page.wait_for_selector("#painel-vereadores.ativo", timeout=30000)
        else:
            page.wait_for_selector("#painel-camara.ativo", timeout=30000)
        page.wait_for_timeout(300)

    def _abrir_com_modo_grafico(self, page, modo: str):
        cfg_body = _config_com_grafico(modo)

        def rota(route):
            if route.request.url.endswith("/config_cidade.json"):
                route.fulfill(body=cfg_body, content_type="application/json; charset=utf-8")
            else:
                route.continue_()

        page.route("**/*", rota)

    def _percorrer_abas(self, page, largura: int, tema: str):
        page.set_viewport_size({"width": largura, "height": 900})
        page.goto(self.base, wait_until="domcontentloaded", timeout=60000)
        self._aguardar_dados(page)
        if tema == "escuro":
            page.evaluate("document.documentElement.setAttribute('data-tema','escuro')")
        else:
            page.evaluate("document.documentElement.removeAttribute('data-tema')")
        for secao in ("camara", "vereadores", "prefeito"):
            self._ir_secao(page, largura, secao)
        self._ir_secao(page, largura, "camara")
        if largura >= 900:
            page.locator("#tab-periodo-todo-lateral").click(timeout=10000)
            page.wait_for_timeout(400)
            page.locator("#tab-periodo-mes-lateral").click(timeout=10000)
            page.wait_for_timeout(400)
        else:
            page.locator("#tab-periodo-todo").click(timeout=10000)
            page.wait_for_timeout(400)
            page.locator("#tab-periodo-mes").click(timeout=10000)
            page.wait_for_timeout(400)
        overflow = page.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth + 1"
        )
        self.assertTrue(overflow, msg=f"rolagem lateral {largura} {tema}")

    def test_sem_pageerror_barra_e_rosca(self):
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for modo in ("barra", "rosca"):
                for largura in (320, 390, 900, 1440):
                    for tema in ("claro", "escuro"):
                        page = browser.new_page()
                        erros = []
                        page.on("pageerror", lambda e: erros.append(str(e)))
                        self._abrir_com_modo_grafico(page, modo)
                        self._percorrer_abas(page, largura, tema)
                        if modo == "rosca":
                            page.wait_for_selector(
                                ".cartao-grafico-tipos .rosca-tipos-votacao, .cartao-grafico-tipos .barra-tipos-votacao-trilho",
                                timeout=15000,
                            )
                        self.assertEqual(
                            erros,
                            [],
                            msg=f"pageerror modo={modo} {largura} {tema}: {erros}",
                        )
                        page.close()
            browser.close()


if __name__ == "__main__":
    unittest.main()
