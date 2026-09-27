"""Conferencias estaticas da tela (index.html, app.js, estilo.css).

Nao abre navegador. Garante que a tela segue as regras do projeto:
cabecalho gerado a partir do config, CSP restrita, nada de cidade fixa
no codigo e nenhuma construcao perigosa de DOM.
"""

import json
import pathlib
import re
import subprocess
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent


def ler(nome):
    return (RAIZ / nome).read_text(encoding="utf-8")


class TestTelaIndex(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = ler("index.html")
        cls.app = ler("app.js")
        cls.css = ler("estilo.css")
        cls.cfg = json.loads(ler("config_cidade.json"))

    def csp(self):
        m = re.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"', self.index)
        self.assertIsNotNone(m, "CSP ausente no index.html")
        return m.group(1)

    def test_cabecalho_confere_com_config(self):
        res = subprocess.run(
            [sys.executable, "scripts/gerar_cabecalho_index.py", "--conferir"],
            cwd=RAIZ, capture_output=True, text=True,
        )
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_csp_restrita(self):
        csp = self.csp()
        for proibido in ("unsafe-inline", "unsafe-eval", "cloudflare", "workers.dev", "googleapis", "gstatic", "*"):
            self.assertNotIn(proibido, csp)
        for exigido in ("frame-src 'none'", "child-src 'none'", "worker-src 'none'", "object-src 'none'",
                        "script-src 'self'", "style-src 'self'", "connect-src 'self'", "form-action 'none'"):
            self.assertIn(exigido, csp)
        sapl = self.cfg["sapl"]["endereco_base"].rstrip("/")
        self.assertIn(f"img-src 'self' {sapl}", csp)

    def test_sem_votacao_popular_nem_terceiros(self):
        tudo = self.index + self.app + self.css
        for termo in ("turnstile", "workers.dev", "challenges.cloudflare", "geolocation",
                      "fonts.googleapis", "analytics", "gtag", "Campo Largo", "campolargo"):
            self.assertNotIn(termo.lower(), tudo.lower(), termo)

    def test_sem_cidade_nem_ano_fixo_no_codigo(self):
        codigo = self.app + self.css
        cidade = self.cfg["cidade"]["nome"]
        self.assertNotIn(cidade, codigo)
        self.assertNotIn(self.cfg["sapl"]["endereco_base"], codigo)
        for ano in self.cfg["recorte"]["anos"]:
            self.assertIsNone(re.search(rf"\b{ano}\b", self.app), f"ano {ano} fixo no app.js")
        corpo = self.index.split("<!-- fim: bloco gerado -->", 1)[1]
        self.assertNotIn(cidade, corpo)

    def test_sem_construcoes_perigosas(self):
        for padrao in (r"\.innerHTML", r"\.outerHTML", r"insertAdjacentHTML", r"\beval\s*\(",
                       r"new\s+Function", r"document\.write", r"setTimeout\s*\(\s*['\"]",
                       r"setInterval\s*\(\s*['\"]"):
            self.assertIsNone(re.search(padrao, self.app), padrao)
        self.assertIsNone(re.search(r"<[^>]+\son[a-z]+\s*=", self.index), "evento inline no index.html")
        self.assertNotIn("<script>", self.index)
        self.assertNotIn("<style", self.index)
        self.assertNotIn(" style=", self.index)

    def test_esc_remove_ansi_e_existe_url_segura(self):
        self.assertIn("function esc(", self.app)
        self.assertIn("\\u001B", self.app)
        self.assertIn("function urlSegura(", self.app)

    def test_sem_frases_herdadas_de_ranking(self):
        tudo = (self.index + self.app).lower()
        self.assertNotIn("sem nota e sem ranking", tudo)
        self.assertNotIn("nem ranking", tudo)

    def test_sem_selo_de_ia(self):
        tudo = (self.index + self.app).lower()
        for termo in ("classificação por ia", "classificacao por ia", "inteligência artificial"):
            self.assertNotIn(termo, tudo)

    def test_sem_travessao(self):
        for nome, texto in (("index.html", self.index), ("app.js", self.app), ("estilo.css", self.css)):
            self.assertIsNone(re.search("[—–]", texto), nome)


if __name__ == "__main__":
    unittest.main()
