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
        self.assertNotIn("workers.dev", csp)
        self.assertNotIn("*", csp)
        for exigido in (
            "script-src 'self' 'unsafe-inline' https://challenges.cloudflare.com",
            "frame-src https://challenges.cloudflare.com",
            "child-src 'none'",
            "worker-src 'none'",
            "object-src 'none'",
            "img-src 'self'",
            "connect-src 'self'",
            "form-action 'none'",
        ):
            self.assertIn(exigido, csp)
        self.assertIn("'unsafe-inline'", csp)

    def test_csp_connect_src_worker_url(self):
        csp = self.csp()
        worker = (self.cfg.get("votacao_popular") or {}).get("worker_url") or ""
        worker = worker.strip()
        if worker:
            self.assertIn(worker, csp)
            resto = csp.replace(worker, "")
            self.assertNotIn("workers.dev", resto)
        else:
            self.assertNotIn("workers.dev", csp)

    def test_sem_votacao_popular_nem_campo_largo(self):
        tudo = self.index.lower()
        for termo in (
            "campo largo",
            "campolargo",
        ):
            self.assertNotIn(termo, tudo, termo)
        worker_cfg = ((self.cfg.get("votacao_popular") or {}).get("worker_url") or "").strip().lower()
        if worker_cfg:
            self.assertIn(worker_cfg, tudo)
        proibidos_extra = ("campolargo", "campo largo")
        for host in (
            "campolargo",
            "campo-largo",
            "campo largo",
        ):
            self.assertNotIn(host, tudo, host)
        connect = self.csp()
        partes = [p.strip() for p in connect.split(";")]
        connect_src = next((p for p in partes if p.startswith("connect-src")), "")
        permitidos_connect = {"'self'", "https://eu.i.posthog.com", "https://eu-assets.i.posthog.com"}
        if worker_cfg:
            permitidos_connect.add(worker_cfg)
        for pedaco in connect_src.replace("connect-src", "").strip().split():
            if pedaco.startswith("https://") or pedaco == "'self'":
                self.assertIn(pedaco, permitidos_connect, pedaco)

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

    def test_tokens_escala_destaque(self):
        """HF-5: escala de titulos e destaque no :root (celular e computador)."""
        pares = (
            ("--t-tela: 24px", "--t-tela: 31px"),
            ("--t-resumo: 18px", "--t-resumo: 22px"),
            ("--t-cartao: 17px",),
            ("--t-numero: 22px", "--t-numero-quadro: 28px"),
            ("--t-numero-legenda: 14px", "--t-numero-legenda: 13px"),
            ("--t-materia: 15px",),
        )
        for grupo in pares:
            for token in grupo:
                self.assertIn(token, self.index, token)

    def test_molde_com_conteudo_de_outra_cidade_nao_existe(self):
        """O index.html e mantido na mao. Nao ha molde de outra cidade no repositorio."""
        for caminho in (
            RAIZ / "tela" / "modelo.html",
            RAIZ / "referencia-campo-largo",
            RAIZ / "scripts" / "montar_tela_d1b.py",
            RAIZ / "scripts" / "gerar_modelo_tela.py",
        ):
            with self.subTest(caminho=caminho.name):
                self.assertFalse(caminho.exists())
        proibidos = (
            "campolargo",
            "campo largo",
            "campolargo",
            "challenges.cloudflare",
            "workers.dev",
        )
        for caminho in sorted(RAIZ.glob("tela/*")):
            if not caminho.is_file():
                continue
            texto = caminho.read_text(encoding="utf-8", errors="ignore").lower()
            for termo in proibidos:
                with self.subTest(arquivo=caminho.name, termo=termo):
                    self.assertNotIn(termo, texto)


if __name__ == "__main__":
    unittest.main()
