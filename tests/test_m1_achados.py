"""Testes M1 dos 5 achados menores. Nao fazem pedido ao SAPL, so fixture local."""

from __future__ import annotations

import contextlib
import csv
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
import gerar_autoria_materias as modulo_autoria  # noqa: E402
from coletar_autoria import pedir_filtrado_por_ano  # noqa: E402
from coletar_por_sessao import conferir_prefixo  # noqa: E402
from gerar_autoria_materias import gerar as gerar_autoria  # noqa: E402
from gerar_autoria_materias import ler_lista_repetida  # noqa: E402
from gerar_tabela_vereadores import caminhos_materias  # noqa: E402
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
    """Prove, a partir dos dados reais do repositorio, que a coluna Autorias
    do CSV de materias e sempre vazia, o que justifica varrer_autoria devolver [].
    Se um dia a coluna passar a ter conteudo, este teste falha."""

    def test_coluna_autorias_vazia_em_todos_os_csv(self):
        caminhos = caminhos_materias()
        self.assertGreater(
            len(caminhos), 0, "Nenhum CSV de materias encontrado em dados/brutos."
        )
        total_linhas = 0
        for caminho in caminhos:
            with caminho.open(encoding="utf-8-sig", newline="") as handle:
                leitor = csv.DictReader(handle, delimiter=";")
                self.assertIn(
                    "Autorias",
                    leitor.fieldnames or [],
                    f"{caminho.name}: coluna Autorias ausente do cabeçalho",
                )
                for i, linha in enumerate(leitor, start=1):
                    total_linhas += 1
                    valor = linha.get("Autorias")
                    self.assertEqual(
                        valor,
                        "",
                        f"{caminho.name} linha {i}: coluna Autorias nao vazia: {valor!r}",
                    )
        self.assertGreater(total_linhas, 0, "Nenhuma linha de materia nos CSVs.")

    def test_varrer_autoria_devolve_lista_vazia(self):
        apelidos = defaultdict(lambda: defaultdict(set))
        self.assertEqual(varrer_autoria({}, apelidos), [])
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
    def test_ler_lista_repetida_exprime_total_e_repeticao(self):
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

    def test_gerar_meta_com_valores_exatos_do_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            aut = pasta / "lote_teste_autoria"
            lote = pasta / "lote_teste"
            aut.mkdir()
            lote.mkdir()
            (aut / "autor_p1.json").write_text(
                json.dumps(
                    {
                        "pagination": {"total_pages": 1},
                        "results": [
                            {
                                "id": 1,
                                "tipo": 2,
                                "object_id": 10,
                                "nome": "Nome Tal",
                                "cargo": "",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (aut / "tipoautor_p1.json").write_text(
                json.dumps(
                    {
                        "pagination": {"total_pages": 1},
                        "results": [{"id": 2, "descricao": "Parlamentar"}],
                    }
                ),
                encoding="utf-8",
            )
            (aut / "autoria_p1.json").write_text(
                json.dumps(
                    {
                        "pagination": {"total_entries": 3, "total_pages": 1},
                        "results": [
                            {
                                "id": 5,
                                "materia": 100,
                                "autor": 1,
                                "primeiro_autor": True,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (lote / "materialegislativa_ano2025_p1.json").write_text(
                json.dumps(
                    {
                        "pagination": {"total_entries": 1, "total_pages": 1},
                        "results": [
                            {
                                "id": 100,
                                "numero": 1,
                                "ano": 2025,
                                "tipo": 1,
                                "__str__": "PL 1/2025",
                                "autores": [1],
                                "texto_original": "texto",
                                "ementa": "e",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(modulo_autoria, "DIR_BRUTOS", pasta), mock.patch.object(
                modulo_autoria, "ANOS", [2025]
            ), mock.patch.object(
                modulo_autoria, "rel", lambda caminho: caminho.name
            ), mock.patch.object(
                modulo_autoria, "link_materia", lambda mid, cfg: f"/materia/{mid}"
            ):
                meta = gerar_autoria()["meta"]
        self.assertEqual(meta["autoria_total_entries_api"], 3)
        self.assertEqual(meta["autoria_total_linhas_lidas"], 1)
        self.assertEqual(meta["autoria_ids_distintos"], 1)
        self.assertEqual(meta["por_ano"]["2025"]["n_materias"], 1)
        self.assertEqual(meta["por_ano"]["2025"]["total_entries_api"], 1)
        self.assertEqual(meta["por_ano"]["2025"]["n_pares_materia_autor"], 1)


class TesteM1ConferirSemTotal(unittest.TestCase):
    """Itens 1 e 2: prova de fim de paginacao e motivo com todas as causas."""

    def _pagina(self, ids, paginacao):
        return {"pagination": paginacao, "results": [{"id": i} for i in ids]}

    def test_total_entries_presente_e_conferente_bate(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            (pasta / "sessao_3_ordemdia_p1.json").write_text(
                json.dumps(self._pagina([1, 2], {"total_entries": 2})),
                encoding="utf-8",
            )
            conf = conferir_prefixo(pasta, "sessao_3_ordemdia", 3, "ordemdia")
        self.assertTrue(conf["bate"])
        self.assertEqual(conf["total_entries"], 2)
        self.assertEqual(conf["ids_distintos"], 2)

    def test_total_entries_distinto_de_ids_nao_bate(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            (pasta / "sessao_4_ordemdia_p1.json").write_text(
                json.dumps(self._pagina([1, 2], {"total_entries": 5})),
                encoding="utf-8",
            )
            conf = conferir_prefixo(pasta, "sessao_4_ordemdia", 4, "ordemdia")
        self.assertFalse(conf["bate"])
        self.assertIn("total_entries distinto de ids distintos", conf["motivo"])

    def test_sem_total_sem_prova_fim_nao_bate(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            (pasta / "sessao_5_presencaordemdia_p1.json").write_text(
                json.dumps(self._pagina([1, 2, 3], {})),
                encoding="utf-8",
            )
            conf = conferir_prefixo(
                pasta, "sessao_5_presencaordemdia", 5, "presencaordemdia"
            )
        self.assertFalse(conf["bate"])
        self.assertIn("sem total_entries", conf["motivo"])
        self.assertIn("sem prova de fim de paginacao", conf["motivo"])

    def test_sem_total_pagina_unica_com_total_pages_bate(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            (pasta / "sessao_6_ordemdia_p1.json").write_text(
                json.dumps(self._pagina([1, 2, 3], {"total_pages": 1})),
                encoding="utf-8",
            )
            conf = conferir_prefixo(pasta, "sessao_6_ordemdia", 6, "ordemdia")
        self.assertTrue(conf["bate"])
        self.assertIsNone(conf["motivo"])
        self.assertIsNone(conf["total_entries"])
        self.assertEqual(conf["ids_distintos"], 3)

    def test_sem_total_com_prova_fim_multipagina_bate(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            pagina1 = {
                "pagination": {"total_pages": 2, "next_page": 2},
                "results": [{"id": i} for i in [1, 2]],
            }
            pagina2 = {
                "pagination": {"total_pages": 2},
                "results": [{"id": i} for i in [3, 4]],
            }
            (pasta / "sessao_7_ordemdia_p1.json").write_text(
                json.dumps(pagina1), encoding="utf-8"
            )
            (pasta / "sessao_7_ordemdia_p2.json").write_text(
                json.dumps(pagina2), encoding="utf-8"
            )
            conf = conferir_prefixo(pasta, "sessao_7_ordemdia", 7, "ordemdia")
        self.assertTrue(conf["bate"])
        self.assertIsNone(conf["motivo"])
        self.assertEqual(conf["ids_distintos"], 4)

    def test_motivo_lista_todas_as_causas(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            pagina = {
                "pagination": {"next_page": 2},
                "results": [{"id": i} for i in [1, 1, 2]],
            }
            (pasta / "sessao_8_ordemdia_p1.json").write_text(
                json.dumps(pagina), encoding="utf-8"
            )
            conf = conferir_prefixo(pasta, "sessao_8_ordemdia", 8, "ordemdia")
        self.assertFalse(conf["bate"])
        motivo = conf["motivo"]
        for causa in (
            "sem total_entries",
            "sem prova de fim de paginacao",
            "id repetido",
            "paginacao pendente",
        ):
            self.assertIn(causa, motivo)

    def test_sem_total_com_repeticao_nao_bate(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            (pasta / "sessao_9_ordemdia_p1.json").write_text(
                json.dumps(self._pagina([1, 1, 2], {})),
                encoding="utf-8",
            )
            conf = conferir_prefixo(pasta, "sessao_9_ordemdia", 9, "ordemdia")
        self.assertFalse(conf["bate"])
        self.assertIn("sem total_entries", conf["motivo"])
        self.assertIn("id repetido", conf["motivo"])


if __name__ == "__main__":
    unittest.main()
