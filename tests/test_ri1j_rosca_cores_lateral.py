"""RI-1j: rosca menor, cores dos tipos distintas (tambem com daltonismo) e pagina sem rolagem lateral."""

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

try:
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_OK = True
    PLAYWRIGHT_MOTIVO = ""
except ImportError:
    PLAYWRIGHT_OK = False
    PLAYWRIGHT_MOTIVO = "playwright nao instalado"

LARGURAS = (320, 390, 900, 1200, 1440)


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


# Cor: sRGB -> Lab (D65), CIEDE2000 e simulacao de daltonismo (Machado, Oliveira e Fernandes, 2009, severidade 1).
def _lin(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _rgb_lin(h: str) -> list[float]:
    h = h.lstrip("#")
    return [_lin(int(h[i:i + 2], 16) / 255) for i in (0, 2, 4)]


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


class TestRi1jEstatico(unittest.TestCase):
    def test_rosca_menor(self):
        bloco = INDEX[INDEX.find(".rosca-tipos-figura {"):]
        bloco = bloco[: bloco.find("}")]
        self.assertIn("width: 130px", bloco)
        self.assertRegex(INDEX, r"\.rosca-tipos-figura \{ width: 140px; height: 140px; \}")
        self.assertIn("--t-numero-rosca: 18px", INDEX)
        self.assertIn("--t-numero-rosca: 20px", INDEX)

    def test_legenda_ao_lado_por_largura_do_cartao(self):
        self.assertIn("container: tipos-votacao / inline-size", INDEX)
        self.assertRegex(INDEX, r"@container tipos-votacao \(min-width: 316px\)")

    def test_barra_e_rosca_na_mesma_paleta(self):
        self.assertNotIn("--rosca-tipo-", INDEX)
        self.assertNotIn("corTokenRoscaTipoVotacao", INDEX)
        self.assertIn('"var(--graf-vot-tipo-"', INDEX)

    def test_paleta_sem_verde_azul_laranja_e_com_contraste(self):
        for nome, tokens in (("claro", CLARO), ("escuro", ESCURO)):
            fundo = _resolver(tokens, tokens["--superficie"])
            reservadas = [_resolver(tokens, tokens[t]) for t in ("--marca", "--sim", "--nao")]
            for cor in _paleta(tokens):
                self.assertGreaterEqual(_contraste(cor, fundo), 3.0, msg=f"{nome} {cor} contra {fundo}")
                for r in reservadas:
                    d = _de2000(_lab(_simular(cor, "normal")), _lab(_simular(r, "normal")))
                    self.assertGreaterEqual(d, 15, msg=f"{nome} {cor} parecida com {r} (Delta E {d:.1f})")

    def test_paleta_distinguivel_com_daltonismo(self):
        for nome, tokens in (("claro", CLARO), ("escuro", ESCURO)):
            pal = _paleta(tokens)
            self.assertEqual(len(set(pal)), 6, msg=f"{nome}: cores repetidas {pal}")
            for tipo in MATRIZES:
                labs = [_lab(_simular(c, tipo)) for c in pal]
                menor = min(_de2000(labs[i], labs[j]) for i, j in itertools.combinations(range(6), 2))
                self.assertGreaterEqual(menor, 14, msg=f"{nome} {tipo}: menor Delta E {menor:.1f}")

    def test_tag_longa_quebra_e_grade_com_minimo_zero(self):
        self.assertRegex(INDEX, r"#painel-camara \.lista-materias,\s*#painel-prefeito \.lista-materias \{[^}]*minmax\(0, 1fr\)")
        bloco = INDEX[INDEX.find("#painel-camara .item-votado.materia,"):]
        self.assertIn("grid-template-columns: minmax(0, 1fr)", bloco[: bloco.find("}")])
        chip = INDEX[INDEX.find(".materia-tags .chip {"):]
        chip = chip[: chip.find("}")]
        self.assertIn("white-space: normal", chip)
        self.assertNotIn("ellipsis", chip)


class _Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(RAIZ), **kwargs)

    def log_message(self, *args):
        pass


def _config_com_grafico(modo: str) -> str:
    cfg = json.loads((RAIZ / "config_cidade.json").read_text(encoding="utf-8"))
    cfg.setdefault("painel", {})["grafico_tipos_votacao"] = modo
    return json.dumps(cfg, ensure_ascii=False)


ABRIR_MAIS = """() => { let n = 0; for (let i = 0; i < 40; i++) {
  const b = [...document.querySelectorAll('button')].find(x => /Mostrar mais/.test(x.textContent) && x.offsetParent);
  if (!b) break; b.click(); n++; } return n; }"""

MEDE_ROSCA = """(c) => {
  const card = document.querySelector(c);
  const f = card.querySelector('.rosca-tipos-figura').getBoundingClientRect();
  const l = card.querySelector('.legenda-rosca').getBoundingClientRect();
  const linhas = [...card.querySelectorAll('.legenda-tipo-votacao')];
  return {
    lado: f.width, aoLado: l.left >= f.right - 1,
    centro: Math.abs((f.top + f.height / 2) - (l.top + l.height / 2)),
    baixas: linhas.filter(b => b.getBoundingClientRect().height < 44).length,
    cortados: linhas.map(b => b.querySelector('.legenda-nome')).filter(n => n.scrollWidth > n.clientWidth + 1).map(n => n.textContent)
  };
}"""


@unittest.skipUnless(PLAYWRIGHT_OK, PLAYWRIGHT_MOTIVO)
class TestRi1jPlaywright(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servidor = ThreadingHTTPServer(("127.0.0.1", 8821), _Handler)
        threading.Thread(target=cls.servidor.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:8821/index.html"
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

    def test_sem_rolagem_lateral_em_abas_periodos_e_larguras(self):
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for modo in ("barra", "rosca"):
                for largura in LARGURAS:
                    page, erros = self._abrir(browser, modo, largura)
                    for aba in ("camara", "vereadores", "prefeito"):
                        if largura >= 900:
                            sel = f"button[data-secao-lateral='{aba}']"
                        else:
                            sel = "#nav-prefeito" if aba == "prefeito" else f"#nav-principal button[data-secao='{aba}']"
                        botao = page.locator(sel)
                        if not botao.count() or not botao.first.is_visible():
                            continue
                        botao.first.click()
                        page.wait_for_timeout(400)
                        for per in ("sessao", "mes", "todo"):
                            tab = page.locator(f"#tab-periodo-{per}-lateral" if largura >= 900 else f"#tab-periodo-{per}")
                            if tab.count() and tab.first.is_visible():
                                tab.first.click()
                                page.wait_for_timeout(300)
                            page.evaluate(ABRIR_MAIS)
                            page.wait_for_timeout(200)
                            dif = page.evaluate("() => document.documentElement.scrollWidth - innerWidth")
                            self.assertEqual(dif, 0, msg=f"{modo} {largura} {aba} {per}: rola {dif} px para o lado")
                    self.assertEqual(erros, [], msg=str(erros))
                    page.close()
            browser.close()

    def test_rosca_menor_com_legenda_ao_lado(self):
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for largura, lado, ao_lado in ((320, 130, False), (390, 130, True), (1440, 140, True)):
                page, erros = self._abrir(browser, "rosca", largura)
                for per in ("mes", "todo"):
                    page.locator(f"#tab-periodo-{per}-lateral" if largura >= 900 else f"#tab-periodo-{per}").click()
                    page.wait_for_timeout(300)
                    m = page.evaluate(MEDE_ROSCA, f"#card-grafico-tipos-{per}")
                    self.assertEqual(round(m["lado"]), lado, msg=f"{largura} {per}")
                    self.assertEqual(m["aoLado"], ao_lado, msg=f"{largura} {per}")
                    if ao_lado:
                        self.assertLessEqual(m["centro"], 2, msg=f"{largura} {per}: legenda fora do centro da rosca")
                    self.assertEqual(m["baixas"], 0, msg=f"{largura} {per}: linha da legenda abaixo de 44 px")
                    self.assertEqual(m["cortados"], [], msg=f"{largura} {per}: nome cortado")
                self.assertEqual(erros, [], msg=str(erros))
                page.close()
            browser.close()


if __name__ == "__main__":
    unittest.main()
