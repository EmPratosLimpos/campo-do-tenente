"""RI-3b M4 e M5: aviso de erro de carga e executivo sempre para a Camara."""

from __future__ import annotations

import pathlib
import re
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
INDEX = (RAIZ / "index.html").read_text(encoding="utf-8")


def _js() -> str:
    ini = INDEX.find("var CONFIG_CIDADE = null;")
    fim = INDEX.find("})();\n</script>", ini)
    bloco = INDEX[ini:fim] if ini >= 0 and fim > ini else INDEX
    sem_linha = re.sub(r"//[^\n]*", "", bloco)
    return re.sub(r"/\*[\s\S]*?\*/", "", sem_linha)


class TestErroCargaCamara(unittest.TestCase):
    def test_flag_erro_materias_e_banner(self):
        js = _js()
        self.assertIn("ERRO_CARGA_MATERIAS_CAMARA", js)
        self.assertIn("function atualizarBannerErroCamara", js)
        frag = js[js.find("function carregarMateriasCamara") : js.find("function tiposPedidos")]
        self.assertIn("ERRO_CARGA_MATERIAS_CAMARA = true", frag)
        self.assertIn("erro-carga", js[js.find("function atualizarBannerErroCamara") : js.find("function carregarMateriasCamara")])

    def test_executivo_carrega_mesmo_aba_prefeito_desligada(self):
        js = _js()
        frag = js[js.find("function carregarExecutivoPrefeito") : js.find("function listaPlexExecutivo")]
        self.assertNotIn("if (!abaPrefeitoAtiva()) return Promise.resolve()", frag)
        self.assertIn("ERRO_CARGA_EXECUTIVO", frag)
        self.assertIn("atualizarBannerErroCamara", frag)


if __name__ == "__main__":
    unittest.main()
