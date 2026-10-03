"""Playwright: aba Prefeito com dados reais (390 e 1440, claro e escuro)."""

from __future__ import annotations

import json
import pathlib
import threading
import time
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

RAIZ = pathlib.Path(__file__).resolve().parent.parent


def contagem_resumo_plex_registrados() -> dict:
    dados = json.loads(
        (RAIZ / "dados" / "tratados" / "executivo_legislatura.json").read_text(encoding="utf-8")
    )
    plex = [x for x in dados.get("todo") or [] if x.get("tipo_sigla") == "PLEX"]
    c = {"aprovados": 0, "rejeitados": 0, "tramitacao": 0, "retirados": 0}
    for item in plex:
        if item.get("situacao_final_fonte") == "sem_registro":
            continue
        s = (item.get("situacao_final") or "").strip()
        if s in ("Aprovado", "Proposição transformada em lei"):
            c["aprovados"] += 1
        elif s == "Rejeitado":
            c["rejeitados"] += 1
        elif s in ("Proposição Substituída", "Proposição retirada pelo autor"):
            c["retirados"] += 1
        elif s == "Aguardando emissão de parecer da comissão" or s.startswith(
            "Adiada discussão"
        ):
            c["tramitacao"] += 1
    return c


def qtd_plex_sem_registro() -> int:
    dados = json.loads(
        (RAIZ / "dados" / "tratados" / "executivo_legislatura.json").read_text(encoding="utf-8")
    )
    return sum(
        1
        for x in dados.get("todo") or []
        if x.get("tipo_sigla") == "PLEX" and x.get("situacao_final_fonte") == "sem_registro"
    )

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


@unittest.skipUnless(PLAYWRIGHT_OK, PLAYWRIGHT_MOTIVO)
class TestTelaPrefeito(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servidor = ThreadingHTTPServer(("127.0.0.1", 8801), _Handler)
        thread = threading.Thread(target=cls.servidor.serve_forever, daemon=True)
        thread.start()
        cls.base = "http://127.0.0.1:8801/index.html"
        time.sleep(0.4)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.servidor.shutdown()
        finally:
            cls.servidor.server_close()

    def _aguardar_dados(self, page):
        page.wait_for_load_state("networkidle", timeout=90000)

    def _abrir_prefeito(self, page, largura: int, tema: str):
        page.set_viewport_size({"width": largura, "height": 900})
        page.goto(self.base, wait_until="domcontentloaded", timeout=60000)
        self._aguardar_dados(page)
        page.wait_for_function(
            """() => {
              const m = document.getElementById('nav-prefeito');
              const l = document.querySelector('[data-secao-lateral="prefeito"]');
              return (m && !m.hidden) || (l && !l.hidden);
            }""",
            timeout=30000,
        )
        if tema == "escuro":
            page.evaluate("document.documentElement.setAttribute('data-tema','escuro')")
        else:
            page.evaluate("document.documentElement.removeAttribute('data-tema')")
        seletor = (
            "button[data-secao-lateral='prefeito']"
            if largura >= 900
            else "button[data-secao='prefeito']"
        )
        page.click(seletor, timeout=15000)
        page.wait_for_selector("#painel-prefeito.ativo #tit-prefeito", state="visible", timeout=30000)
        page.wait_for_selector(".btn-votos-plex", state="attached", timeout=30000)
        page.wait_for_timeout(400)

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

    def test_abas_sem_pageerror_em_viewports_e_temas(self):
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for largura in (390, 1440):
                for tema in ("claro", "escuro"):
                    page = browser.new_page(viewport={"width": largura, "height": 900})
                    erros = []
                    page.on("pageerror", lambda e: erros.append(str(e)))
                    page.goto(self.base, wait_until="domcontentloaded", timeout=60000)
                    self._aguardar_dados(page)
                    if tema == "escuro":
                        page.evaluate("document.documentElement.setAttribute('data-tema','escuro')")
                    else:
                        page.evaluate("document.documentElement.removeAttribute('data-tema')")
                    for secao in ("camara", "vereadores", "prefeito"):
                        self._ir_secao(page, largura, secao)
                    titulo = page.locator("#painel-prefeito.ativo #tit-prefeito")
                    titulo.wait_for(state="visible", timeout=30000)
                    self.assertIn("Prefeito enviou", titulo.inner_text())
                    self.assertGreater(
                        page.locator("#painel-prefeito.ativo .btn-votos-plex").count(), 0
                    )
                    overflow = page.evaluate(
                        "document.documentElement.scrollWidth <= window.innerWidth + 1"
                    )
                    self.assertTrue(overflow, msg=f"rolagem lateral {largura} {tema}")
                    self.assertEqual(erros, [], msg=f"pageerror {largura} {tema}: {erros}")
                    page.close()
            browser.close()

    def test_resumo_so_plex_com_registro_e_nota_sem_registro(self):
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            erros = []
            page.on("pageerror", lambda e: erros.append(str(e)))
            self._abrir_prefeito(page, 1440, "claro")
            resumo = page.locator("#cartao-resumo-prefeito")
            texto_resumo = resumo.inner_text()
            self.assertNotIn("Sem registro no SAPL", texto_resumo.split("Projetos do Prefeito")[0])
            c = contagem_resumo_plex_registrados()
            self.assertIn(f"{c['aprovados']}\nAprovados", texto_resumo)
            self.assertIn(f"{c['rejeitados']}\nRejeitados", texto_resumo)
            self.assertIn(f"{c['tramitacao']}\nEm tramitação", texto_resumo)
            self.assertIn(f"{c['retirados']}\nRetirados ou substituídos", texto_resumo)
            qtd = qtd_plex_sem_registro()
            if qtd:
                self.assertIn(
                    f"{qtd} projetos do início de 2025 não têm votação registrada no SAPL.",
                    texto_resumo,
                )
            pilulas = page.locator(
                "#lista-prefeito button.pilula-sem-registro-sapl"
            )
            while pilulas.count() == 0 and page.locator("#btn-mais-prefeito").count():
                page.locator("#btn-mais-prefeito").click()
                page.wait_for_timeout(500)
            self.assertGreater(pilulas.count(), 0)
            pilulas.first.click()
            page.wait_for_selector("#folha-generica-backdrop.ativo", timeout=10000)
            folha = page.inner_text("#folha-generica-backdrop.ativo")
            self.assertIn("sessões do início de 2025", folha)
            self.assertEqual(erros, [])
            browser.close()

    def test_folha_votacao_simbolica_ou_nominal(self):
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 390, "height": 844})
            erros = []
            page.on("pageerror", lambda e: erros.append(str(e)))
            self._abrir_prefeito(page, 390, "claro")
            btn = page.locator(".btn-votos-plex").first
            btn.wait_for(state="visible", timeout=15000)
            btn.click()
            page.wait_for_selector("#folha-generica-backdrop.ativo", timeout=10000)
            corpo = page.inner_text("#folha-generica-backdrop.ativo")
            self.assertTrue(
                "Votação simbólica" in corpo or "Sim" in corpo or "SAPL" in corpo,
                msg=corpo[:200],
            )
            self.assertEqual(erros, [])
            browser.close()


if __name__ == "__main__":
    unittest.main()
