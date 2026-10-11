"""Gitignore do Worker: tmp_build ignorado e wrangler.toml rastreado.

Sem rede, sem segredo, sem escrita. A checagem de segredo no toml ja
existe em tests/test_worker_votacao.py.
"""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


class TestGitignoreWorker(unittest.TestCase):
    def test_tmp_build_ignorado_e_toml_sem_regra(self):
        gitignore = (RAIZ / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("tmp_build", gitignore)
        self.assertNotIn("cloudflare-worker/wrangler.toml", gitignore)

    def test_wrangler_toml_rastreado(self):
        proc = subprocess.run(
            ["git", "ls-files", "cloudflare-worker/wrangler.toml"],
            cwd=RAIZ,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("cloudflare-worker/wrangler.toml", proc.stdout)


if __name__ == "__main__":
    unittest.main()
