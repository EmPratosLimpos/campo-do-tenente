"""Temas revisados na tela e contagem de presença na última sessão."""

from __future__ import annotations

import json
import pathlib
import re
import sys
import threading
import time
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
if str(RAIZ / "coletor") not in sys.path:
    sys.path.insert(0, str(RAIZ / "coletor"))

from config_cidade import anos_recorte, carregar_config  # noqa: E402

from dados.tratados.gerar_dados_tela import tema_display  # noqa: E402

try:
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_OK = True
    PLAYWRIGHT_MOTIVO = ""
except ImportError:
    PLAYWRIGHT_OK = False
    PLAYWRIGHT_MOTIVO = "playwright nao instalado"


def mapa_temas_revisados() -> dict[int, str]:
    path = RAIZ / "dados" / "tratados" / "temas_materias.json"
    dados = json.loads(path.read_text(encoding="utf-8"))
    return {int(m["id"]): m["tema"] for m in dados.get("materias", [])}


def ultima_sessao(dados: dict) -> dict | None:
    sessoes = dados.get("sessoes") or []
    if not sessoes:
        return None
    return max(sessoes, key=lambda s: s.get("data") or "")


def contagem_presenca(sessao: dict) -> dict[str, int]:
    presentes = int(sessao.get("n_presentes") or 0)
    faltas = int(sessao.get("n_faltas_com_justificativa") or 0) + int(
        sessao.get("n_faltas_sem_justificativa") or 0
    )
    fora = int(sessao.get("n_fora_do_mandato") or 0)
    licenca = int(sessao.get("n_licenca") or 0)
    return {
        "presentes": presentes,
        "faltas": faltas,
        "fora": fora,
        "licenca": licenca,
        "banca": presentes + faltas + licenca,
    }


class TestTemasRevisadosNosJson(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = carregar_config()
        cls.temas = mapa_temas_revisados()

    def test_tag_tema_igual_temas_materias(self):
        for ano in anos_recorte(self.cfg):
            path = RAIZ / "dados" / "tratados" / f"materias_tags_{ano}.json"
            tags = json.loads(path.read_text(encoding="utf-8"))
            for mid_str, tag in tags.items():
                mid = int(mid_str)
                esperado = tema_display(self.temas.get(mid, "Outros"), self.cfg)
                with self.subTest(ano=ano, materia=mid):
                    self.assertEqual(tag.get("tag_tema"), esperado)

    def test_soma_presenca_ultima_sessao(self):
        for ano in anos_recorte(self.cfg):
            path = RAIZ / "dados" / "tratados" / f"atuacao_vereadores_{ano}.json"
            dados = json.loads(path.read_text(encoding="utf-8"))
            sessao = ultima_sessao(dados)
            self.assertIsNotNone(sessao, msg=f"sem sessoes em {ano}")
            c = contagem_presenca(sessao)
            with self.subTest(ano=ano, data=sessao.get("data")):
                self.assertGreaterEqual(c["banca"], 1)
                self.assertEqual(
                    c["presentes"] + c["faltas"] + c["licenca"],
                    c["banca"],
                )


@unittest.skipUnless(PLAYWRIGHT_OK, PLAYWRIGHT_MOTIVO)
class TestTemasRevisadosPlaywright(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

        class _Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(RAIZ), **kwargs)

        cls.servidor = ThreadingHTTPServer(("127.0.0.1", 8792), _Handler)
        thread = threading.Thread(target=cls.servidor.serve_forever, daemon=True)
        thread.start()
        cls.base = "http://127.0.0.1:8792/index.html"
        time.sleep(0.4)

    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown()

    def test_cartao_presenca_bate_com_ultima_sessao(self):
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            path = RAIZ / "dados" / "tratados" / "atuacao_vereadores_legislatura.json"
            dados = json.loads(path.read_text(encoding="utf-8"))
            sessao = ultima_sessao(dados)
            self.assertIsNotNone(sessao)
            c = contagem_presenca(sessao)

            page.goto(self.base, wait_until="networkidle", timeout=120000)
            page.wait_for_timeout(1200)
            page.click('button[data-periodo="sessao"]')
            page.wait_for_timeout(600)

            meta_txt = page.locator("#texto-meta-presenca-sessao").inner_text()
            m = re.search(r"(\d+)\s+parlamentar", meta_txt)
            self.assertIsNotNone(m, msg=f"meta presenca: {meta_txt}")
            self.assertEqual(int(m.group(1)), c["banca"])

            presentes = int(
                page.locator(
                    "#card-presenca-sessao .capsula-verde .capsula-valor"
                ).inner_text()
            )
            faltas = int(
                page.locator(
                    "#card-presenca-sessao .capsula-neutro .capsula-valor"
                ).first.inner_text()
            )
            self.assertEqual(presentes, c["presentes"])
            self.assertEqual(faltas, c["faltas"])

            browser.close()


if __name__ == "__main__":
    unittest.main()
