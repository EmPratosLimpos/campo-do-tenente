"""RI-1k: paleta chamativa, centro da rosca sem vazar e unico grafico em rosca."""

from __future__ import annotations

import itertools
import json
import math
import pathlib
import re
import threading
import time
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

RAIZ = pathlib.Path(__file__).resolve().parent.parent
INDEX = (RAIZ / "index.html").read_text(encoding="utf-8")
CONFIG = json.loads((RAIZ / "config_cidade.json").read_text(encoding="utf-8"))

try:
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_OK = True
    PLAYWRIGHT_MOTIVO = ""
except ImportError:
    PLAYWRIGHT_OK = False
    PLAYWRIGHT_MOTIVO = "playwright nao instalado"

LARGURAS = (320, 390, 900, 1440)


def _bloco_tema(seletor: str) -> str:
    ini = INDEX.find(seletor + " {")
    return INDEX[ini: INDEX.find("}", ini)]


def _tokens(bloco: str) -> dict[str, str]:
    return dict(re.findall(r"(--[\w-]+):\s*([^;]+);", bloco))


CLARO = _tokens(_bloco_tema(":root"))
ESCURO = _tokens(_bloco_tema('[data-tema="escuro"]'))


def _resolver(tokens: dict[str, str], valor: str) -> str:
    m = re.fullmatch(r"var\((--[\w-]+)\)", valor.strip())
    return _resolver(tokens, tokens[m.group(1)]) if m else valor.strip()


def _paleta(tokens: dict[str, str]) -> list[str]:
    return [_resolver(tokens, tokens[f"--graf-vot-tipo-{i}"]) for i in range(1, 7)]


def _lin(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _rgb_lin(h: str) -> list[float]:
    h = h.lstrip("#")
    return [_lin(int(h[i:i + 2], 16) / 255) for i in (0, 2, 4)]


def _rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


MATRIZES = {
    "normal": None,
    "deuteranopia": [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.011820, 0.042940, 0.968881]],
    "protanopia": [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]],
}


def _simular(h: str, tipo: str) -> list[float]:
    r = _rgb_lin(h)
    m = MATRIZES[tipo]
    if m is None:
        return r
    return [min(max(sum(m[i][j] * r[j] for j in range(3)), 0.0), 1.0) for i in range(3)]


def _lab(rgb: list[float]) -> tuple[float, float, float]:
    r, g, b = rgb
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
    f = lambda t: t ** (1 / 3) if t > 216 / 24389 else (24389 / 27 * t + 16) / 116  # noqa: E731
    return 116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))


def _de2000(l1, l2) -> float:
    L1, a1, b1 = l1
    L2, a2, b2 = l2
    cb = (math.hypot(a1, b1) + math.hypot(a2, b2)) / 2
    g = 0.5 * (1 - math.sqrt(cb ** 7 / (cb ** 7 + 25 ** 7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360
    h2p = math.degrees(math.atan2(b2, a2p)) % 360
    dh = 0.0 if c1p * c2p == 0 else h2p - h1p
    if dh > 180:
        dh -= 360
    elif dh < -180:
        dh += 360
    dhp = 2 * math.sqrt(c1p * c2p) * math.sin(math.radians(dh / 2))
    lbp, cbp = (L1 + L2) / 2, (c1p + c2p) / 2
    if c1p * c2p == 0:
        hbp = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hbp = (h1p + h2p) / 2
    elif h1p + h2p < 360:
        hbp = (h1p + h2p + 360) / 2
    else:
        hbp = (h1p + h2p - 360) / 2
    t = (1 - 0.17 * math.cos(math.radians(hbp - 30)) + 0.24 * math.cos(math.radians(2 * hbp))
         + 0.32 * math.cos(math.radians(3 * hbp + 6)) - 0.20 * math.cos(math.radians(4 * hbp - 63)))
    rc = 2 * math.sqrt(cbp ** 7 / (cbp ** 7 + 25 ** 7))
    sl = 1 + 0.015 * (lbp - 50) ** 2 / math.sqrt(20 + (lbp - 50) ** 2)
    sc, sh = 1 + 0.045 * cbp, 1 + 0.015 * cbp * t
    rt = -math.sin(math.radians(60 * math.exp(-((hbp - 275) / 25) ** 2))) * rc
    return math.sqrt(((L2 - L1) / sl) ** 2 + ((c2p - c1p) / sc) ** 2 + (dhp / sh) ** 2 + rt * ((c2p - c1p) / sc) * (dhp / sh))


def _luminancia(h: str) -> float:
    r, g, b = _rgb_lin(h)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contraste(a: str, b: str) -> float:
    la, lb = sorted((_luminancia(a), _luminancia(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _matiz(h: str) -> float:
    r, g, b = (x / 255 for x in _rgb(h))
    mx, mn = max(r, g, b), min(r, g, b)
    if mx == mn:
        return 0.0
    d = mx - mn
    if mx == r:
        h = (g - b) / d + (6 if g < b else 0)
    elif mx == g:
        h = (b - r) / d + 2
    else:
        h = (r - g) / d + 4
    return h * 60


def _saturacao(h: str) -> float:
    r, g, b = (x / 255 for x in _rgb(h))
    mx, mn = max(r, g, b), min(r, g, b)
    if mx == 0:
        return 0.0
    return (mx - mn) / mx


def _cor_proibida(h: str) -> str | None:
    sat = _saturacao(h)
    hue = _matiz(h)
    if sat < 0.12:
        return None
    if 300 <= hue <= 335 and sat > 0.35:
        return "magenta"
    if sat > 0.35 and (hue >= 335 or hue <= 10):
        r, g, b = _rgb(h)
        if b > r * 0.55 and g > r * 0.38:
            return "rosa"
    return None


def _funcao_rosca() -> str:
    ini = INDEX.find("function roscaSVGTiposInterativa(")
    fim = INDEX.find("\n  function ", ini + 10)
    return INDEX[ini:fim if fim > ini else len(INDEX)]


class TestRi1kEstatico(unittest.TestCase):
    def test_sem_chave_grafico_tipos_no_config(self):
        self.assertNotIn("grafico_tipos_votacao", CONFIG.get("painel", {}))

    def test_sem_barra_nem_modo_no_codigo(self):
        self.assertNotIn("graficoTiposVotacaoModo", INDEX)
        self.assertNotIn("htmlBarraGraficoTiposVotacao", INDEX)
        self.assertNotIn("barra-tipos-votacao-trilho", INDEX)
        self.assertNotIn("segmento-tipo-votacao", INDEX)

    def test_centro_sem_nome_do_tipo_quando_selecionado(self):
        rosca = _funcao_rosca()
        self.assertIn('ativa ? ("de " + total)', rosca)
        self.assertNotIn("ativa ? ativa.rotulo", rosca)
        self.assertIn("ariaGrafico", rosca)
        self.assertIn("esc(ariaGrafico)", rosca)

    def test_paleta_chamativa_sem_cores_proibidas(self):
        for nome, tokens in (("claro", CLARO), ("escuro", ESCURO)):
            fundo = _resolver(tokens, tokens["--superficie"])
            reservadas = [_resolver(tokens, tokens[t]) for t in ("--marca", "--sim", "--nao")]
            for cor in _paleta(tokens):
                motivo = _cor_proibida(cor)
                self.assertIsNone(motivo, msg=f"{nome} {cor}: parece {motivo}")
                self.assertGreaterEqual(_contraste(cor, fundo), 3.0, msg=f"{nome} {cor}")
                for r in reservadas:
                    d = _de2000(_lab(_simular(cor, "normal")), _lab(_simular(r, "normal")))
                    self.assertGreaterEqual(d, 12.0, msg=f"{nome} {cor} perto de {r} (Delta E {d:.1f})")

    def test_paleta_distinguivel_com_daltonismo(self):
        for nome, tokens in (("claro", CLARO), ("escuro", ESCURO)):
            pal = _paleta(tokens)
            self.assertEqual(len(set(pal)), 6, msg=f"{nome}: repetida {pal}")
            for tipo in MATRIZES:
                labs = [_lab(_simular(c, tipo)) for c in pal]
                menor = min(_de2000(labs[i], labs[j]) for i, j in itertools.combinations(range(6), 2))
                self.assertGreaterEqual(menor, 12.0, msg=f"{nome} {tipo}: menor Delta E {menor:.1f}")


class _Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(RAIZ), **kwargs)

    def log_message(self, *args):
        pass


ABRIR_MAIS = """() => { for (let i = 0; i < 40; i++) {
  const b = [...document.querySelectorAll('button')].find(x => /Mostrar mais/.test(x.textContent) && x.offsetParent);
  if (!b) break; b.click(); } }"""

MEDE_CENTRO = """(c) => {
  const fig = document.querySelector(c + ' .rosca-tipos-figura');
  if (!fig) return ['sem rosca'];
  const fr = fig.getBoundingClientRect();
  const cx = fr.left + fr.width / 2;
  const cy = fr.top + fr.height / 2;
  const rHole = (72 / 100) * (fr.width / 2);
  const out = [];
  document.querySelectorAll(c + ' .rosca-tipos-centro *').forEach(el => {
    const r = el.getBoundingClientRect();
    [[r.left, r.top], [r.right, r.top], [r.left, r.bottom], [r.right, r.bottom]].forEach(([x, y]) => {
      if (Math.hypot(x - cx, y - cy) > rHole + 1.5) out.push('fora: ' + el.textContent.trim());
    });
  });
  const pressed = document.querySelector(c + ' .legenda-tipo-votacao[aria-pressed=true]');
  if (pressed) {
    const nome = pressed.querySelector('.legenda-nome')?.textContent?.trim() || '';
    const centro = document.querySelector(c + ' .rosca-tipos-centro')?.innerText || '';
    if (nome && centro.includes(nome)) out.push('nome no centro: ' + nome);
    const svg = document.querySelector(c + ' svg.rosca-tipos-votacao');
    const al = svg?.getAttribute('aria-label') || '';
    if (nome && !al.includes(nome.split(' ')[0])) out.push('aria sem tipo: ' + nome);
  }
  return out;
}"""


@unittest.skipUnless(PLAYWRIGHT_OK, PLAYWRIGHT_MOTIVO)
class TestRi1kPlaywright(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servidor = ThreadingHTTPServer(("127.0.0.1", 8825), _Handler)
        threading.Thread(target=cls.servidor.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:8825/index.html"
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.servidor.shutdown()
        finally:
            cls.servidor.server_close()

    def _pagina(self, browser, largura: int, tema: str):
        page = browser.new_page(viewport={"width": largura, "height": 900})
        erros: list[str] = []
        page.on("pageerror", lambda e: erros.append(str(e)))
        page.goto(self.base, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_load_state("networkidle", timeout=90000)
        if tema == "escuro":
            page.evaluate("document.documentElement.setAttribute('data-tema','escuro')")
        else:
            page.evaluate("document.documentElement.removeAttribute('data-tema')")
        return page, erros

    def test_sem_pageerror_e_sem_rolagem_lateral(self):
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for largura in LARGURAS:
                for tema in ("claro", "escuro"):
                    page, erros = self._pagina(browser, largura, tema)
                    for aba in ("camara", "vereadores", "prefeito"):
                        if largura >= 900:
                            sel = f"button[data-secao-lateral='{aba}']" if aba != "prefeito" else "#nav-lateral-prefeito"
                        else:
                            sel = "#nav-prefeito" if aba == "prefeito" else f"#nav-principal button[data-secao='{aba}']"
                        page.locator(sel).first.click(timeout=15000)
                        page.wait_for_timeout(400)
                        for per in ("sessao", "mes", "todo"):
                            tab = page.locator(f"#tab-periodo-{per}-lateral" if largura >= 900 else f"#tab-periodo-{per}")
                            if tab.count() and tab.first.is_visible():
                                tab.first.click()
                                page.wait_for_timeout(300)
                            page.evaluate(ABRIR_MAIS)
                            dif = page.evaluate("() => document.documentElement.scrollWidth - innerWidth")
                            self.assertEqual(dif, 0, msg=f"{largura} {tema} {aba} {per}")
                    self.assertEqual(erros, [], msg=str(erros))
                    page.close()
            browser.close()

    def test_centro_dentro_do_furo_em_todos_os_tipos(self):
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for largura in LARGURAS:
                for tema in ("claro", "escuro"):
                    page, erros = self._pagina(browser, largura, tema)
                    for per in ("mes", "todo"):
                        page.locator(f"#tab-periodo-{per}-lateral" if largura >= 900 else f"#tab-periodo-{per}").click()
                        page.wait_for_timeout(350)
                        card = f"#card-grafico-tipos-{per}"
                        siglas = page.evaluate(
                            "(c) => [...document.querySelectorAll(c + ' .legenda-tipo-votacao')].map(b => b.dataset.tipoVotacao)",
                            card,
                        )
                        for sigla in siglas:
                            page.locator(f"{card} .legenda-tipo-votacao[data-tipo-votacao='{sigla}']").click()
                            page.wait_for_timeout(200)
                            probs = page.evaluate(MEDE_CENTRO, card)
                            self.assertEqual(probs, [], msg=f"{largura} {tema} {per} {sigla}: {probs}")
                        page.locator(f"{card} .legenda-tipo-votacao[aria-pressed=true]").click()
                        page.wait_for_timeout(150)
                        probs = page.evaluate(MEDE_CENTRO, card)
                        self.assertEqual(probs, [], msg=f"{largura} {tema} {per} sem filtro: {probs}")
                    self.assertEqual(erros, [], msg=str(erros))
                    page.close()
            browser.close()


if __name__ == "__main__":
    unittest.main()
