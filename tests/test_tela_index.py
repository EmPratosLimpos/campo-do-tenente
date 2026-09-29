"""Conferencias estaticas da tela (index.html monolitico estilo Campo Largo)."""

import json
import pathlib
import re
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent


def ler(nome):
    return (RAIZ / nome).read_text(encoding="utf-8")


def script_index(html):
    m = re.search(r"<script>\s*\(function \(\)", html)
    if not m:
        return ""
    return html[m.start() :]


class TestTelaIndex(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = ler("index.html")
        cls.js = script_index(cls.index)
        cls.cfg = json.loads(ler("config_cidade.json"))

    def csp(self):
        m = re.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"', self.index)
        self.assertIsNotNone(m, "CSP ausente no index.html")
        return m.group(1)

    def test_csp_github_pages(self):
        csp = self.csp()
        for proibido in ("cloudflare", "workers.dev", "challenges.cloudflare"):
            self.assertNotIn(proibido, csp)
        for exigido in (
            "frame-src 'none'",
            "child-src 'none'",
            "worker-src 'none'",
            "object-src 'none'",
            "img-src 'self'",
            "connect-src 'self'",
            "form-action 'none'",
        ):
            self.assertIn(exigido, csp)
        self.assertIn("'unsafe-inline'", csp)

    def test_sem_votacao_popular_nem_campo_largo(self):
        tudo = self.index.lower()
        for termo in (
            "turnstile",
            "workers.dev",
            "challenges.cloudflare",
            "geolocation",
            "btn-votar-fab",
            "campo largo",
            "campolargo",
        ):
            self.assertNotIn(termo, tudo, termo)

    def test_config_e_moldura(self):
        self.assertIn("config_cidade.json", self.js)
        self.assertIn("window.top !== window.self", self.js)
        self.assertNotIn("app.js", self.index)

    def test_sem_cidade_fixa_no_script(self):
        cidade = self.cfg["cidade"]["nome"]
        self.assertNotIn(cidade, self.js)
        self.assertNotIn(self.cfg["sapl"]["endereco_base"], self.js)

    def test_esc_e_url_segura(self):
        self.assertIn("function esc(", self.js)
        self.assertIn("\\u0000-\\u0008", self.js)
        self.assertIn("function urlSegura(", self.js)

    def test_sem_frases_herdadas_de_ranking(self):
        tudo = self.index.lower()
        self.assertNotIn("sem nota e sem ranking", tudo)
        self.assertNotIn("nem ranking", tudo)

    def test_sem_selo_de_ia(self):
        tudo = self.index.lower()
        for termo in ("classificação por ia", "classificacao por ia", "inteligência artificial"):
            self.assertNotIn(termo, tudo)

    def test_sem_travessao(self):
        self.assertIsNone(re.search("[—–]", self.index), "index.html")

    def test_arquivos_d1_removidos(self):
        self.assertFalse((RAIZ / "app.js").exists())
        self.assertFalse((RAIZ / "estilo.css").exists())


if __name__ == "__main__":
    unittest.main()
