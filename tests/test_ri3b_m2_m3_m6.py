"""RI-3b M2, M3 e M6: rosca ao trocar periodo, vazio unico, foco em pedidos."""

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


class TestRi3bComportamento(unittest.TestCase):
    def test_reset_materias_redesenha_rosca(self):
        js = _js()
        frag = js[js.find("function resetMateriasPeriodo") : js.find("function initNavegacao")]
        self.assertIn('renderCartaoGraficoTipos("mes")', frag)
        self.assertIn('renderCartaoGraficoTipos("todo")', frag)

    def test_vazio_sem_filtro_nao_pede_limpar(self):
        js = _js()
        frag = js[js.find("function renderBlocoVotadoPeriodo") : js.find("function folhaShareAberta")]
        self.assertIn("!temFiltro && listaBase.length === 0", frag)
        self.assertNotIn(
            "Tente outra palavra ou limpe os filtros.</span>' +\n        (estadoMaterias.filtroTema",
            frag,
        )

    def test_ajustar_painel_apos_filtros(self):
        js = _js()
        self.assertIn("ajustarPainelUltimaSessaoSemPll();", js[js.find("function renderTemasDistribuicao") :])

    def test_foco_restaurado_em_pedidos(self):
        js = _js()
        self.assertIn("function restaurarFocoAposRender", js)
        frag = js[js.find("function restaurarFocoAposRender") : js.find("function renderApp")]
        self.assertIn("focus", frag)
        ped = js[js.find(".contagem-pedido[data-ped-filtro]") : js.find("[data-falta-presenca]")]
        self.assertIn("restaurarFocoAposRender", ped)


if __name__ == "__main__":
    unittest.main()
