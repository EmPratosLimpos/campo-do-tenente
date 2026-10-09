"""NF-1: nota factual do vereador (objeto com texto e fontes, sem [object Object])."""

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

TEXTO_NOTA_RIVANILDO = (
    "Assumiu em 17/03/2026 durante a licença de Jorge Quege; "
    "vaga permanente após a cassação em 18/08/2026."
)
LINK_NOTICIA_CAMARA = (
    "https://www.campodotenente.pr.leg.br/institucional/noticias/"
    "rivanildo-braz-cavalheiro-assume-vaga-de-suplente-na-camara-municipal"
)


class _Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(RAIZ), **kwargs)

    def log_message(self, format, *args):
        pass


def arquivos_atuacao_com_nota() -> list[pathlib.Path]:
    pasta = RAIZ / "dados" / "tratados"
    return sorted(pasta.glob("atuacao_vereadores_*.json"))


def validar_nota_factual(nota) -> None:
    if nota is None:
        return
    if isinstance(nota, str):
        if not nota.strip():
            raise AssertionError("nota_factual string vazia")
        return
    if not isinstance(nota, dict):
        raise AssertionError(f"nota_factual tipo invalido: {type(nota)!r}")
    texto = nota.get("texto")
    if not texto or not str(texto).strip():
        raise AssertionError("nota_factual sem texto")
    fontes = nota.get("fontes")
    if fontes is not None and not isinstance(fontes, list):
        raise AssertionError("nota_factual.fontes nao e lista")


class TestNotaFactualDados(unittest.TestCase):
    def test_nota_factual_em_json_tratados(self):
        for path in arquivos_atuacao_com_nota():
            dados = json.loads(path.read_text(encoding="utf-8"))
            for v in dados.get("vereadores") or []:
                with self.subTest(arquivo=path.name, id_sapl=v.get("id_sapl")):
                    validar_nota_factual(v.get("nota_factual"))

    def test_rivanildo_tem_texto_novo_no_json(self):
        path = RAIZ / "dados" / "tratados" / "atuacao_vereadores_legislatura.json"
        dados = json.loads(path.read_text(encoding="utf-8"))
        riv = next(v for v in dados["vereadores"] if v.get("id_sapl") == 100)
        self.assertEqual(riv["nota_factual"]["texto"], TEXTO_NOTA_RIVANILDO)


@unittest.skipUnless(PLAYWRIGHT_OK, PLAYWRIGHT_MOTIVO)
class TestNotaFactualTela(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servidor = ThreadingHTTPServer(("127.0.0.1", 8796), _Handler)
        thread = threading.Thread(target=cls.servidor.serve_forever, daemon=True)
        thread.start()
        cls.base = "http://127.0.0.1:8796/index.html"
        time.sleep(0.35)

    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown()

    def _abrir_vereadores(self, page):
        page.goto(self.base, wait_until="domcontentloaded", timeout=120000)
        page.wait_for_selector("#bloco-votado-sessao .cab-cartao", timeout=60000)
        page.click('button[data-secao="vereadores"]')
        page.wait_for_selector("#sel-vereador", state="visible", timeout=60000)

    def test_nenhum_vereador_mostra_object_object(self):
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 390, "height": 900})
            self._abrir_vereadores(page)
            valores = page.eval_on_selector(
                "#sel-vereador",
                "el => Array.from(el.options).map(o => o.value)",
            )
            for vid in valores:
                page.select_option("#sel-vereador", vid)
                page.wait_for_timeout(150)
                texto = page.locator("body").inner_text()
                with self.subTest(vereador=vid):
                    self.assertNotIn("[object Object]", texto)
            browser.close()

    def test_nota_rivanildo_texto_e_link_noticia(self):
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 390, "height": 900})
            self._abrir_vereadores(page)
            page.select_option("#sel-vereador", "100")
            page.wait_for_timeout(300)
            wrap = page.locator("#notas-vereador-wrap")
            self.assertIn(TEXTO_NOTA_RIVANILDO, wrap.inner_text())
            link = wrap.locator(f'a[href="{LINK_NOTICIA_CAMARA}"]')
            self.assertEqual(link.count(), 1)
            apoio = page.locator("#apoio-vereador").inner_text()
            self.assertIn("Sessões ordinárias de 2026", apoio)
            self.assertNotIn("2025 e 2026", apoio)
            browser.close()


if __name__ == "__main__":
    unittest.main()
