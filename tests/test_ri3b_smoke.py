"""RI-3b-6: smoke dos testes RI-3b sem Playwright."""

from __future__ import annotations

import pathlib
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent


class TestRi3bSmoke(unittest.TestCase):
    def test_modulos_ri3b_existem(self):
        pasta = RAIZ / "tests"
        nomes = sorted(pasta.glob("test_ri3b_*.py"))
        self.assertGreaterEqual(len(nomes), 5)
        self.assertTrue(any("facetas" in n.name for n in nomes))


if __name__ == "__main__":
    unittest.main()
