"""Playwright: aba Vereadores com conteudo completo por ano e vereador."""

from __future__ import annotations

import json
import pathlib
import re
import sys
import threading
import time
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

RAIZ = pathlib.Path(__file__).resolve().parent.parent
if str(RAIZ / "coletor") not in sys.path:
    sys.path.insert(0, str(RAIZ / "coletor"))

from config_cidade import anos_recorte, carregar_config  # noqa: E402

try:
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_OK = True
    PLAYWRIGHT_MOTIVO = ""
except ImportError:
    PLAYWRIGHT_OK = False
    PLAYWRIGHT_MOTIVO = "playwright nao instalado"


def datas_permitidas_ano(ano: int) -> set[str]:
    path = RAIZ / "dados" / "tratados" / f"atuacao_vereadores_{ano}.json"
    dados = json.loads(path.read_text(encoding="utf-8"))
    out = set()

    def add_iso(d: str | None) -> None:
        if not d:
            return
        dia = str(d).split("T")[0]
        p = dia.split("-")
        if len(p) == 3:
            out.add(f"{p[2]}/{p[1]}/{p[0]}")

    for s in dados.get("sessoes") or []:
        add_iso(s.get("data"))
    meta = dados.get("meta") or {}
    add_iso(meta.get("dado_coletado_em"))
    for v in dados.get("vereadores") or []:
        pres = v.get("presenca") or {}
        for item in pres.get("por_sessao") or []:
            add_iso(item.get("data_sessao"))
        votos = v.get("votos") or {}
        for item in votos.get("nominais") or []:
            add_iso(item.get("data_sessao"))
        for af in v.get("afastamentos") or []:
            add_iso(af.get("data_inicio"))
            add_iso(af.get("data_fim"))
    return out


class _Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(RAIZ), **kwargs)


@unittest.skipUnless(PLAYWRIGHT_OK, PLAYWRIGHT_MOTIVO)
class TestTelaVereadores(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = carregar_config()
        cls.cidade = cls.cfg["cidade"]["nome"]
        cls.servidor = ThreadingHTTPServer(("127.0.0.1", 8793), _Handler)
        thread = threading.Thread(target=cls.servidor.serve_forever, daemon=True)
        thread.start()
        cls.base = "http://127.0.0.1:8793/index.html"
        time.sleep(0.4)

    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown()

    def _opcoes_vereador(self, page, ano: int) -> list[str]:
        page.goto(self.base, wait_until="networkidle", timeout=120000)
        page.click(f'button[data-ano="{ano}"]')
        page.wait_for_timeout(2500)
        page.click('button[data-secao="vereadores"]')
        page.wait_for_timeout(1200)
        page.wait_for_selector("#sel-vereador", timeout=20000)
        return page.eval_on_selector(
            "#sel-vereador",
            "el => Array.from(el.options).map(o => o.value)",
        )

    def test_todos_vereadores_com_conteudo(self):
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 390, "height": 900})
            for ano in anos_recorte(self.cfg):
                datas_ok = datas_permitidas_ano(ano)
                valores = self._opcoes_vereador(page, ano)
                self.assertGreater(len(valores), 0, msg=f"sem vereadores em {ano}")
                for vid in valores:
                    page.select_option("#sel-vereador", vid)
                    page.wait_for_timeout(500)
                    texto = page.locator("#conteudo-vereadores").inner_text()
                    with self.subTest(ano=ano, vereador=vid):
                        self.assertIn("Perfil parlamentar", texto)
                        self.assertIn("Presença", texto)
                        self.assertIn("Histórico de votos", texto)
                        self.assertNotIn("Não foi possível carregar", texto)
                        self.assertNotIn("município", texto.lower())
                        self.assertNotIn("municipio", texto.lower())
                        for data_sess in re.findall(r"\b\d{2}/\d{2}/\d{4}\b", texto):
                            self.assertIn(
                                data_sess,
                                datas_ok,
                                msg=f"data {data_sess} fora do consolidado {ano}",
                            )
            browser.close()

    def test_jorge_quege_licenca_2026(self):
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 390, "height": 900})
            page.goto(self.base, wait_until="networkidle", timeout=120000)
            page.click('button[data-ano="2026"]')
            page.wait_for_timeout(2500)
            page.click('button[data-secao="vereadores"]')
            page.wait_for_timeout(1200)
            page.select_option("#sel-vereador", "1")
            page.wait_for_timeout(800)
            texto = page.locator("#conteudo-vereadores").inner_text()
            self.assertIn("Licença para tratamento de saúde", texto)
            browser.close()


if __name__ == "__main__":
    unittest.main()
