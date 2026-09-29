"""Testes M1 dos 5 achados menores. Nao fazem pedido ao SAPL, so fixture local."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "coletor"))
sys.path.insert(0, str(RAIZ / "dados" / "tratados"))

import baixar_voto_presenca_ordinarias as modulo_voto  # noqa: E402
from coletar_autoria import pedir_filtrado_por_ano  # noqa: E402
from coletar_por_sessao import conferir_prefixo  # noqa: E402
from gerar_autoria_materias import gerar as gerar_autoria  # noqa: E402
from gerar_autoria_materias import ler_lista_repetida  # noqa: E402
from gerar_tabela_vereadores import varrer_autoria  # noqa: E402


class TesteM1RegistrovotacaoPagina(unittest.TestCase):
    def test_busca_pagina_2_da_mesma_ordem(self):
        coletor = modulo_voto.Coletor.__new__(modulo_voto.Coletor)
        coletor.erros = []
        pagina1 = {
            "pagination": {"total_pages": 2},
            "results": [{"id": 1}, {"id": 2}],
        }
        pagina2 = {
            "pagination": {"total_pages": 2},
            "results": [{"id": 3}],
        }
        chamadas = []

        def pedir_falso(caminho, params):
            chamadas.append(dict(params))
            if params.get("page", 1) in (None, 1):
                return pagina1, None
            return pagina2, None

        coletor.pedir = pedir_falso
        gravados = {}

        def salvar_falso(caminho, dado, tentativas=8):
            gravados["dado"] = dado

        with mock.patch.object(
            modulo_voto, "arquivo_sessao", return_value=Path("/nulo.json")
        ), mock.patch.object(modulo_voto, "salvar_json", salvar_falso):
            with contextlib.redirect_stdout(io.StringIO()):
                dado, ok = coletor.baixar_registrovotacao(999999, [{"id": 111}])
        self.assertTrue(ok)
        self.assertEqual(dado["total"], 3)
        self.assertEqual(sorted(item["id"] for item in dado["results"]), [1, 2, 3])
        paginas_pedidas = [c.get("page", 1) for c in chamadas]
        self.assertIn(2, paginas_pedidas)
        self.assertTrue(all(c.get("ordem") == 111 for c in chamadas))


class TesteM1VarrerAutoriaMorta(unittest.TestCase):
    def test_devolve_lista_vazia_e_aponta_varrer_autores_sapl(self):
        texto = (RAIZ / "dados" / "tratados" / "gerar_tabela_vereadores.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("varrer_autores_sapl", texto)
        self.assertNotIn('linha.get("Autorias")', texto)
        apelidos = defaultdict(lambda: defaultdict(set))
        saida = varrer_autoria({}, apelidos)
        self.assertEqual(saida, [])
        self.assertEqual(dict(apelidos), {})


class TesteM1AvisoFiltroAno(unittest.TestCase):
    def test_filtro_ignorado_grava_aviso_e_avisa_no_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            primeira = {"pagination": {"total_entries": 500}, "results": [{"id": 1}]}
            falso = SimpleNamespace(
                pasta=pasta,
                pedir=lambda caminho, params, arquivo: primeira,
                pedir_paginas=mock.Mock(),
            )
            saida = io.StringIO()
            with contextlib.redirect_stdout(saida):
                pedir_filtrado_por_ano(falso, 2025, 500)
            falso.pedir_paginas.assert_not_called()
            aviso_caminho = pasta / "aviso_filtro_materia_ano2025.json"
            self.assertTrue(aviso_caminho.is_file())
            aviso = json.loads(aviso_caminho.read_text(encoding="utf-8"))
            self.assertEqual(aviso["ano"], 2025)
            self.assertEqual(aviso["total_entries_sem_filtro"], 500)
            self.assertIn("motivo", aviso)
            self.assertIn("AVISO", saida.getvalue())

    def test_sem_total_entries_tambem_grava_aviso(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            primeira = {"pagination": {}, "results": []}
            falso = SimpleNamespace(
                pasta=pasta,
                pedir=lambda caminho, params, arquivo: primeira,
                pedir_paginas=mock.Mock(),
            )
            with contextlib.redirect_stdout(io.StringIO()):
                pedir_filtrado_por_ano(falso, 2026, 500)
            falso.pedir_paginas.assert_not_called()
            self.assertTrue((pasta / "aviso_filtro_materia_ano2026.json").is_file())


class TesteM1MetaAutoria(unittest.TestCase):
    def test_lista_repetida_expõe_total_e_meta_traz_conferencia(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            (pasta / "autoria_p1.json").write_text(
                json.dumps(
                    {
                        "pagination": {"total_entries": 5},
                        "results": [{"id": 1}, {"id": 2}, {"id": 3}],
                    }
                ),
                encoding="utf-8",
            )
            (pasta / "autoria_p2.json").write_text(
                json.dumps({"pagination": {}, "results": [{"id": 3}, {"id": 4}]}),
                encoding="utf-8",
            )
            linhas, nomes, total = None, None, None
            import gerar_autoria_materias as modulo_autoria  # noqa: E402

            with mock.patch.object(
                modulo_autoria, "rel", side_effect=lambda caminho: caminho.name
            ):
                linhas, nomes, total = ler_lista_repetida(pasta, "autoria")
            self.assertEqual(total, 5)
            self.assertEqual(len(linhas), 5)
            distintos = len(
                {int(item["id"]) for item in linhas if item.get("id") is not None}
            )
            self.assertEqual(distintos, 4)
            self.assertEqual(len(nomes), 2)
        payload = gerar_autoria()
        meta = payload["meta"]
        for chave in (
            "autoria_total_entries_api",
            "autoria_total_linhas_lidas",
            "autoria_ids_distintos",
        ):
            self.assertIn(chave, meta)
        self.assertIsInstance(meta["autoria_total_linhas_lidas"], int)
        self.assertGreaterEqual(
            meta["autoria_total_linhas_lidas"], meta["autoria_ids_distintos"]
        )


class TesteM1ConferirSemTotal(unittest.TestCase):
    def _pagina(self, ids, paginacao):
        return {"pagination": paginacao, "results": [{"id": i} for i in ids]}

    def test_sem_total_e_sem_repeticao_bate(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            (pasta / "sessao_7_presencaordemdia_p1.json").write_text(
                json.dumps(self._pagina([1, 2, 3], {})),
                encoding="utf-8",
            )
            conf = conferir_prefixo(pasta, "sessao_7_presencaordemdia", 7, "presencaordemdia")
        self.assertTrue(conf["bate"])
        self.assertEqual(conf["motivo"], "sem total_entries, sem repeticao")
        self.assertIsNone(conf["total_entries"])
        self.assertEqual(conf["ids_distintos"], 3)

    def test_sem_total_com_repeticao_nao_bate(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            (pasta / "sessao_8_ordemdia_p1.json").write_text(
                json.dumps(self._pagina([1, 1, 2], {})),
                encoding="utf-8",
            )
            conf = conferir_prefixo(pasta, "sessao_8_ordemdia", 8, "ordemdia")
        self.assertFalse(conf["bate"])


if __name__ == "__main__":
    unittest.main()
