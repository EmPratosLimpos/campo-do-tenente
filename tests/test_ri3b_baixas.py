"""RI-3b B1, B3 e B4: aria-live fixo, teclado na legenda, soma da rosca."""

from __future__ import annotations

import json
import pathlib
import re
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
if str(RAIZ / "coletor") not in sys.path:
    sys.path.insert(0, str(RAIZ / "coletor"))

from config_cidade import carregar_config  # noqa: E402
from tests.test_tela_votacoes import _contar_votados_todo, _lista_votados_todo  # noqa: E402

INDEX = (RAIZ / "index.html").read_text(encoding="utf-8")
SUFIXO = "legislatura"


def _js() -> str:
    ini = INDEX.find("var CONFIG_CIDADE = null;")
    fim = INDEX.find("})();\n</script>", ini)
    bloco = INDEX[ini:fim] if ini >= 0 and fim > ini else INDEX
    sem_linha = re.sub(r"//[^\n]*", "", bloco)
    return re.sub(r"/\*[\s\S]*?\*/", "", sem_linha)


class TestBaixasRi3b(unittest.TestCase):
    def test_aria_live_fixo_no_html(self):
        for per in ("sessao", "mes", "todo"):
            self.assertIn('id="live-votado-' + per + '"', INDEX)
            self.assertIn("aria-live=\"polite\"", INDEX[INDEX.find("live-votado-" + per) : INDEX.find("live-votado-" + per) + 120])

    def test_keydown_so_na_legenda_da_rosca(self):
        frag = _js()[_js().find("function ligarInteracaoGraficoTipos") : _js().find("function renderCartaoGraficoTipos")]
        self.assertIn(".legenda-tipo-votacao", frag)
        self.assertIn("keydown", frag)
        self.assertEqual(frag.count('addEventListener("keydown"'), 1)

    def test_soma_fatias_igual_total_todo(self):
        cont = _contar_votados_todo()
        total = len(_lista_votados_todo())
        self.assertEqual(sum(cont.values()), total)

    def test_todo_tipo_sigla_no_config(self):
        cfg = carregar_config()
        tr = cfg["tramitacao"]
        ordem = (tr.get("tipos_proposicoes") or []) + [
            s for s in (tr.get("tipos_executivo") or []) + (tr.get("tipos_pedidos") or [])
        ]
        for sig in _contar_votados_todo():
            self.assertIn(sig, ordem, msg=f"tipo {sig} fora da ordem configurada")


if __name__ == "__main__":
    unittest.main()
