"""RI-1i: rosca de tipos no padrao do site e caixas de tipo do vereador sem altura fixa."""

from __future__ import annotations

import json
import pathlib
import re
import threading
import time
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

RAIZ = pathlib.Path(__file__).resolve().parent.parent
INDEX = (RAIZ / "index.html").read_text(encoding="utf-8")

try:
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_OK = True
    PLAYWRIGHT_MOTIVO = ""
except ImportError:
    PLAYWRIGHT_OK = False
    PLAYWRIGHT_MOTIVO = "playwright nao instalado"


def _funcao(nome: str) -> str:
    ini = INDEX.find("function " + nome + "(")
    if ini < 0:
        return ""
    fim = INDEX.find("\n  function ", ini + 10)
    return INDEX[ini:fim if fim > ini else len(INDEX)]


class TestRi1iEstatico(unittest.TestCase):
    def test_sem_texto_de_comparacao(self):
        self.assertNotIn("Visualiza\\u00e7\\u00e3o em", INDEX)
        self.assertNotIn("Visualização em", INDEX)
        self.assertNotIn("nota-grafico-mod", INDEX)

    def test_rosca_sem_biblioteca_externa(self):
        for termo in ("chart.js", "Chart(", "d3.", "echarts", "apexcharts", "cdn.jsdelivr", "unpkg.com"):
            self.assertNotIn(termo, INDEX, msg=termo)
        rosca = _funcao("roscaSVGTiposInterativa")
        self.assertTrue(rosca, "roscaSVGTiposInterativa ausente")
        self.assertIn("<path", rosca)
        self.assertNotRegex(rosca, r"\son[a-z]+=", "atributo de evento inline na rosca")
        # todo texto vindo de dado passa por esc()
        for trecho in ("esc(p.sigla)", "esc(p.cor)", "esc(resumo)", "esc(numero)", "esc(rotulo)"):
            self.assertIn(trecho, rosca)

    def test_rosca_cores_por_token_nos_dois_temas(self):
        # RI-1j: barra e rosca usam a mesma paleta (--graf-vot-tipo-N), definida nos dois temas
        for i in range(1, 8):
            self.assertGreaterEqual(INDEX.count(f"--graf-vot-tipo-{i}:"), 2, msg=f"--graf-vot-tipo-{i}")
        self.assertIn('"var(--graf-vot-tipo-"', INDEX)

    def test_rosca_centro_usa_tokens_de_numero(self):
        bloco = INDEX[INDEX.find(".rosca-tipos-centro b {"):]
        bloco = bloco[: bloco.find("}")]
        # RI-1j: centro reduzido na proporcao da rosca menor
        self.assertIn("var(--t-numero-rosca)", bloco)

    def test_rosca_movimento_reduzido(self):
        self.assertRegex(
            INDEX,
            r"prefers-reduced-motion: no-preference\)\s*\{\s*\.rosca-tipos-votacao \.fatia-tipo-votacao \{ transition",
        )

    def test_caixas_sem_botao_dentro_de_botao(self):
        frag = INDEX[INDEX.find("var linhasTipo = tiposPedidos()"):]
        frag = frag[: frag.find("}).join")]
        fecha = frag.find("</button>")
        self.assertGreater(fecha, 0)
        self.assertNotIn("htmlBotaoTermoSigla", frag[:fecha], "sigla explicavel dentro do botao de filtro")
        self.assertIn("pedido-tipo-sigla", frag[fecha:])

    def test_caixas_sem_altura_fixa(self):
        regras = re.findall(r"[^{}]*pedido-tipo[^{}]*\{[^}]*\}", INDEX)
        self.assertTrue(regras)
        for r in regras:
            self.assertIsNone(re.search(r"(?<![-\w])height:\s*\d+px", r), msg=r.strip()[:120])


class _Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(RAIZ), **kwargs)

    def log_message(self, *args):
        pass


def _config_com_grafico(modo: str) -> str:
    cfg = json.loads((RAIZ / "config_cidade.json").read_text(encoding="utf-8"))
    cfg.setdefault("painel", {})["grafico_tipos_votacao"] = modo
    return json.dumps(cfg, ensure_ascii=False)


JS_CAIXAS = """() => {
  const out = [];
  document.querySelectorAll('.cartao-pedidos .numeros li.clicavel').forEach(li => {
    const bx = li.querySelector('.contagem-pedido');
    if (!bx) { out.push('sem botao'); return; }
    const r = bx.getBoundingClientRect();
    li.querySelectorAll('*').forEach(f => {
      const q = f.getBoundingClientRect();
      if (q.height && (q.bottom > r.bottom + 1 || q.right > r.right + 1 || q.top < r.top - 1 || q.left < r.left - 1)) {
        out.push('fora: ' + (f.getAttribute('class') || f.tagName));
      }
    });
    const nome = bx.querySelector('.pedido-tipo-nome');
    if (!nome) out.push('nome fora do botao');
    else if (nome.scrollWidth > nome.clientWidth + 1) out.push('palavra cortada: ' + nome.textContent);
  });
  return out;
}"""


@unittest.skipUnless(PLAYWRIGHT_OK, PLAYWRIGHT_MOTIVO)
class TestRi1iPlaywright(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servidor = ThreadingHTTPServer(("127.0.0.1", 8803), _Handler)
        threading.Thread(target=cls.servidor.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:8803/index.html"
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.servidor.shutdown()
        finally:
            cls.servidor.server_close()

    def _abrir(self, browser, modo: str, largura: int):
        page = browser.new_page(viewport={"width": largura, "height": 900})
        erros: list[str] = []
        page.on("pageerror", lambda e: erros.append(str(e)))
        corpo = _config_com_grafico(modo)
        page.route(
            "**/config_cidade.json",
            lambda r: r.fulfill(body=corpo, content_type="application/json; charset=utf-8"),
        )
        page.goto(self.base, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_load_state("networkidle", timeout=90000)
        return page, erros

    def _periodo(self, page, largura: int, p: str):
        sel = f"#tab-periodo-{p}-lateral" if largura >= 900 else f"#tab-periodo-{p}"
        page.locator(sel).click(timeout=10000)
        page.wait_for_timeout(300)

    def test_rosca_legenda_filtra_e_desfaz(self):
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for largura in (390, 1440):
                page, erros = self._abrir(browser, "rosca", largura)
                self._periodo(page, largura, "todo")
                card = "#card-grafico-tipos-todo"
                self.assertNotIn("Visualiza", page.inner_text(card))
                self.assertEqual(page.locator(card + " svg.rosca-tipos-votacao").count(), 1)
                alturas = page.evaluate(
                    "(c) => [...document.querySelectorAll(c + ' .legenda-tipo-votacao')].map(b => b.getBoundingClientRect().height)",
                    card,
                )
                self.assertTrue(alturas)
                self.assertTrue(all(h >= 44 for h in alturas), msg=str(alturas))
                menor = page.evaluate(
                    "(c) => [...document.querySelectorAll(c + ' .legenda-tipo-votacao')].pop().getAttribute('data-tipo-votacao')",
                    card,
                )
                btn = page.locator(f"{card} .legenda-tipo-votacao[data-tipo-votacao='{menor}']")
                btn.focus()
                page.keyboard.press("Enter")
                page.wait_for_timeout(300)
                estado = page.evaluate(
                    """([c, s]) => {
                      const b = document.querySelector(c + " .legenda-tipo-votacao[data-tipo-votacao='" + s + "']");
                      return [b.getAttribute('aria-pressed'), document.activeElement === b,
                              !!document.querySelector(c + " .fatia-tipo-votacao.ativo[data-tipo-votacao='" + s + "']"),
                              getComputedStyle(b).outlineStyle];
                    }""",
                    [card, menor],
                )
                self.assertEqual(estado[:3], ["true", True, True])
                self.assertNotEqual(estado[3], "none", "foco sem contorno visivel")
                page.keyboard.press("Enter")
                page.wait_for_timeout(300)
                self.assertEqual(page.locator(card + " [aria-pressed='true']").count(), 0)
                self.assertEqual(erros, [], msg=str(erros))
                page.close()
            browser.close()

    def test_caixas_tipo_vereador_dentro_da_caixa(self):
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for largura in (390, 900, 1200, 1440):
                page, erros = self._abrir(browser, "barra", largura)
                if largura >= 900:
                    page.locator("button[data-secao-lateral='vereadores']").click(timeout=15000)
                else:
                    page.locator("#nav-principal button[data-secao='vereadores']").click(timeout=15000)
                page.wait_for_selector("#painel-vereadores.ativo", timeout=30000)
                page.wait_for_timeout(400)
                opcoes = page.evaluate(
                    "() => { const s = document.getElementById('sel-vereador'); return s ? [...s.options].map(o => o.value).filter(Boolean) : []; }"
                )
                for valor in opcoes[:4] or [None]:
                    if valor is not None:
                        page.select_option("#sel-vereador", valor)
                        page.wait_for_timeout(300)
                    problemas = page.evaluate(JS_CAIXAS)
                    self.assertEqual(problemas, [], msg=f"{largura} {valor}: {problemas}")
                self.assertEqual(erros, [], msg=str(erros))
                page.close()
            browser.close()


if __name__ == "__main__":
    unittest.main()
