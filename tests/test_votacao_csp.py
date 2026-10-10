"""CSP e config da votacao popular na tela (V4)."""

import json
import pathlib
import re
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent


class TestVotacaoCsp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = (RAIZ / "index.html").read_text(encoding="utf-8")
        cls.cfg = json.loads((RAIZ / "config_cidade.json").read_text(encoding="utf-8"))

    def csp(self):
        m = re.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"', self.index)
        self.assertIsNotNone(m, "CSP ausente no index.html")
        return m.group(1)

    def test_csp_turnstile_sem_worker_no_connect(self):
        csp = self.csp()
        self.assertIn("script-src 'self' 'unsafe-inline' https://challenges.cloudflare.com", csp)
        self.assertIn("frame-src https://challenges.cloudflare.com", csp)
        self.assertNotIn("workers.dev", csp)
        self.assertNotIn("*", csp)
        vp = self.cfg.get("votacao_popular") or {}
        worker = (vp.get("worker_url") or "").strip()
        if worker:
            self.assertIn(worker, csp)
            self.assertIn("connect-src 'self'", csp)
        else:
            self.assertNotIn("workers.dev", csp)

    def test_connect_src_inclui_worker_quando_config_preenchido(self):
        """Quando worker_url estiver no config, deve aparecer exatamente em connect-src."""
        exemplo = "https://epl-votacao-campo-do-tenente.exemplo.workers.dev"
        cfg = json.loads((RAIZ / "config_cidade.json").read_text(encoding="utf-8"))
        vp = dict(cfg.get("votacao_popular") or {})
        vp["worker_url"] = exemplo
        cfg["votacao_popular"] = vp
        connect = csp_connect_src_com_config(cfg)
        self.assertIn(exemplo, connect)
        self.assertNotIn("*", connect)
        partes = connect.split()
        self.assertEqual(partes.count(exemplo), 1)

    def test_config_chaves_votacao_popular(self):
        vp = self.cfg.get("votacao_popular") or {}
        self.assertIn("worker_url", vp)
        self.assertIn("turnstile_site_key", vp)
        self.assertEqual(vp.get("worker_url"), "")
        self.assertEqual(vp.get("turnstile_site_key"), "")


def csp_connect_src_com_config(cfg):
    """Replica a regra de montagem do connect-src quando o worker_url estiver preenchido."""
    vp = cfg.get("votacao_popular") or {}
    worker = (vp.get("worker_url") or "").strip()
    base = (
        "connect-src 'self' https://eu.i.posthog.com https://eu-assets.i.posthog.com"
    )
    if worker:
        return base + " " + worker
    return base


if __name__ == "__main__":
    unittest.main()
