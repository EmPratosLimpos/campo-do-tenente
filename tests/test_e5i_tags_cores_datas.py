"""E5i: ordem das tags, cor da tag de categoria e datas menores."""

from __future__ import annotations

import pathlib
import re
import threading
import time
import unittest
from contextlib import contextmanager
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

RAIZ = pathlib.Path(__file__).resolve().parent.parent

try:
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_OK = True
    PLAYWRIGHT_MOTIVO = ""
except ImportError:
    PLAYWRIGHT_OK = False
    PLAYWRIGHT_MOTIVO = "playwright nao instalado"

TEMA_ALVO = "Desenvolvimento e moradia"
ORDEM_ESPERADA = ["PLEG", "2\u00ba turno", TEMA_ALVO]

CONTRASTE_JS = """
n => {
  function par(c){var m=String(c).match(/\\d+/g)||[0,0,0];return m.slice(0,3).map(Number);}
  function lin(v){v/=255;return v<=0.03928?v/12.92:Math.pow((v+0.055)/1.055,2.4);}
  function lum(r){return 0.2126*lin(r[0])+0.7152*lin(r[1])+0.0722*lin(r[2]);}
  var s=getComputedStyle(n);var a=lum(par(s.backgroundColor));var b=lum(par(s.color));
  return (Math.max(a,b)+0.05)/(Math.min(a,b)+0.05);
}
"""


class _Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(RAIZ), **kwargs)

    def log_message(self, *args):
        pass


@contextmanager
def _navegador(p):
    browser = p.chromium.launch()
    try:
        yield browser
    finally:
        try:
            browser.close()
        except Exception:
            pass


@unittest.skipUnless(PLAYWRIGHT_OK, PLAYWRIGHT_MOTIVO)
class TestE5iTagsCoresDatas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servidor = ThreadingHTTPServer(("127.0.0.1", 8813), _Handler)
        thread = threading.Thread(target=cls.servidor.serve_forever, daemon=True)
        thread.start()
        cls.base = "http://127.0.0.1:8813/index.html"
        time.sleep(0.4)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.servidor.shutdown()
        finally:
            cls.servidor.server_close()

    def _abrir_camara(self, page, largura, tema):
        page.goto(self.base, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector("#bloco-votado-sessao .item-votado", timeout=60000)
        page.wait_for_timeout(500)
        if tema == "escuro":
            page.locator(".alternar-tema").first.click()
            page.wait_for_timeout(400)
        self.assertEqual(
            page.evaluate("document.documentElement.getAttribute('data-tema')"),
            tema,
        )

    def test_ordem_cor_contraste_e_datas(self):
        for largura in (390, 1440):
            for tema in ("claro", "escuro"):
                with self.subTest(largura=largura, tema=tema):
                    with sync_playwright() as p:
                        with _navegador(p) as browser:
                            page = browser.new_page(viewport={"width": largura, "height": 900})
                            erros = []
                            page.on("pageerror", lambda e: erros.append(str(e)))
                            self._abrir_camara(page, largura, tema)

                            card = page.locator(
                                "#bloco-votado-sessao .item-votado", has_text="PLEG 4/2026"
                            ).first
                            self.assertEqual(card.count(), 1)
                            tags = card.locator(".materia-tags > *")
                            self.assertEqual(
                                [t.strip() for t in tags.all_inner_texts()],
                                ORDEM_ESPERADA,
                            )

                            tag = card.locator(
                                '.tag-categoria[data-valor="%s"]' % TEMA_ALVO
                            ).first
                            estilo = tag.evaluate(
                                "n => { var c = getComputedStyle(n); "
                                "return c.fontSize + '|' + c.paddingTop + ' ' + c.paddingRight "
                                "+ ' ' + c.paddingBottom + ' ' + c.paddingLeft; }"
                            )
                            self.assertEqual(estilo, "10px|2px 8px 2px 8px")

                            barra = page.locator(
                                "#temas-distribuicao-sessao .barra-tema-linha",
                                has_text=TEMA_ALVO,
                            ).first
                            self.assertEqual(barra.count(), 1)
                            cor_barra = barra.locator(".preenchido").evaluate(
                                "n => getComputedStyle(n).backgroundColor"
                            )
                            cor_tag = tag.evaluate(
                                "n => getComputedStyle(n).backgroundColor"
                            )
                            self.assertEqual(cor_tag, cor_barra)
                            self.assertGreaterEqual(tag.evaluate(CONTRASTE_JS), 4.5)

                            ementa = card.locator(".materia-ementa").first
                            datas = card.locator(".materia-datas").first
                            self.assertEqual(datas.count(), 1)
                            tam_ementa = float(
                                ementa.evaluate("n => parseFloat(getComputedStyle(n).fontSize)")
                            )
                            tam_datas = float(
                                datas.evaluate("n => parseFloat(getComputedStyle(n).fontSize)")
                            )
                            self.assertLess(tam_datas, tam_ementa)
                            self.assertIn("Votada em", datas.inner_text())

                            self.assertTrue(
                                page.evaluate(
                                    "document.documentElement.scrollWidth <= window.innerWidth + 1"
                                ),
                                msg=f"rolagem lateral em {largura}px {tema}",
                            )
                            self.assertEqual(erros, [])

    def test_ordem_no_historico_do_vereador(self):
        for largura in (390, 1440):
            with self.subTest(largura=largura):
                with sync_playwright() as p:
                    with _navegador(p) as browser:
                        page = browser.new_page(viewport={"width": largura, "height": 900})
                        erros = []
                        page.on("pageerror", lambda e: erros.append(str(e)))
                        page.goto(self.base, wait_until="domcontentloaded", timeout=60000)
                        page.wait_for_selector(
                            "button[data-secao-lateral='vereadores'], "
                            "button[data-secao='vereadores']",
                            state="attached",
                            timeout=60000,
                        )
                        try:
                            page.click("button[data-secao-lateral='vereadores']", timeout=5000)
                        except Exception:
                            page.click('button[data-secao="vereadores"]', timeout=15000)
                        page.wait_for_selector("#sel-vereador", state="visible", timeout=30000)
                        page.select_option("#sel-vereador", "2")
                        page.wait_for_timeout(500)
                        page.locator("#tit-votos").locator(
                            "xpath=ancestor::details[1]"
                        ).evaluate("n => { n.open = true; }")
                        page.wait_for_timeout(300)
                        page.fill("#filtro-texto", "habitacionais")
                        page.wait_for_timeout(1000)
                        item = page.locator(".lista-votos li", has_text="PLEG 4/2026").first
                        self.assertEqual(item.count(), 1)
                        ordem = item.evaluate(
                            """n => Array.from(n.querySelectorAll(
                              '.tag-tipo, .tag-turno, .tag-categoria, .voto-selo'
                            )).map(e => e.className.split(' ')[0])"""
                        )
                        self.assertEqual(
                            ordem[:3], ["tag-tipo", "tag-turno", "tag-categoria"]
                        )
                        self.assertEqual(ordem[3], "voto-selo")
                        textos = [
                            t.strip()
                            for t in item.locator(".materia-tags > *").all_inner_texts()
                        ]
                        self.assertEqual(textos[:3], ORDEM_ESPERADA)
                        self.assertEqual(textos[3], "Sim")
                        self.assertEqual(erros, [])

    def test_blocos_da_lista_de_votos(self):
        for largura in (390, 1440):
            with self.subTest(largura=largura):
                with sync_playwright() as p:
                    with _navegador(p) as browser:
                        page = browser.new_page(viewport={"width": largura, "height": 900})
                        erros = []
                        page.on("pageerror", lambda e: erros.append(str(e)))
                        page.goto(self.base, wait_until="domcontentloaded", timeout=60000)
                        page.wait_for_selector(
                            "button[data-secao-lateral='vereadores'], "
                            "button[data-secao='vereadores']",
                            state="attached",
                            timeout=60000,
                        )
                        try:
                            page.click("button[data-secao-lateral='vereadores']", timeout=5000)
                        except Exception:
                            page.click('button[data-secao="vereadores"]', timeout=15000)
                        page.wait_for_selector("#sel-vereador", state="visible", timeout=30000)
                        page.select_option("#sel-vereador", "2")
                        page.wait_for_timeout(500)
                        page.locator("#tit-votos").locator(
                            "xpath=ancestor::details[1]"
                        ).evaluate("n => { n.open = true; }")
                        page.wait_for_timeout(300)
                        page.click("button.voto-card[data-voto-card='sim']")
                        page.wait_for_timeout(800)
                        itens = page.locator(".lista-votos li")
                        self.assertGreaterEqual(itens.count(), 5)
                        for i in range(5):
                            item = itens.nth(i)
                            fora = item.evaluate(
                                "n => Array.from(n.querySelectorAll('.tag-explicavel'))"
                                ".filter(e => !e.closest('.materia-tags')).length"
                            )
                            self.assertEqual(fora, 0)
                            ementa = item.locator(".ementa-voto").first
                            self.assertEqual(ementa.count(), 1)
                            self.assertEqual(
                                ementa.evaluate("n => getComputedStyle(n).display"),
                                "block",
                            )
                            bloco = item.locator(".materia-tags").first
                            self.assertEqual(bloco.count(), 1)
                            caixa_tags = bloco.bounding_box()
                            caixa_ementa = ementa.bounding_box()
                            self.assertGreaterEqual(
                                caixa_ementa["y"] + 0.5,
                                caixa_tags["y"] + caixa_tags["height"] - 0.5,
                                msg=f"ementa sobre as tags em {largura}px item {i}",
                            )
                        folga = page.locator(".lista-votos li").first.evaluate(
                            "n => getComputedStyle(n).rowGap"
                        )
                        self.assertEqual(folga, "5px")
                        self.assertEqual(erros, [])


if __name__ == "__main__":
    unittest.main()
