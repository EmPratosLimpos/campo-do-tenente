"""Testes da tarefa AT-1b. Nenhum faz pedido ao SAPL, tudo com servidor falso."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
sys.path.insert(0, str(RAIZ / "coletor"))

from atualizar_semana import (  # noqa: E402
    baixar_lote,
    coletar_autoria,
    conferir_lista_nao_regrediu,
    e_indice_api,
    e_lista_descoberta,
    maior_data_inicio,
    montar_entrada,
    repetir_pendentes,
    separar_divergencias_por_alvo,
)
from coletar_lote import ColetorLote, OrcamentoEsgotado, PedidoPendente  # noqa: E402
from so_dados_mudaram import arquivos_fora_do_permitido, so_dados_mudaram  # noqa: E402

CFG = {
    "cidade": {"nome": "Cidade Teste", "uf": "PR"},
    "sapl": {"endereco_base": "https://exemplo.invalid"},
    "campos_pessoais_removidos": {"lista": []},
    "rede": {
        "teto_bytes_resposta": 1024,
        "esquemas_permitidos": ["https"],
        "hosts_permitidos_extra": [],
    },
}


def quebrado(caminho="/api/x/", arquivo="x.json", motivo="recusado"):
    def refazer():
        raise PedidoPendente(caminho, {}, arquivo, motivo)

    return refazer


class TestA1ListaDescoberta(unittest.TestCase):
    def test_lista_de_sessoes_com_arquivo_bom_ainda_bloqueia(self):
        import atualizar_semana as modulo

        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            (pasta / "sessaoplenaria_ano2026_p1.json").write_bytes(b'{"results": []}')
            pendentes = [
                {
                    "descricao": "sessaoplenaria_ano2026 pagina 1 (recusado)",
                    "sessao_id": None,
                    "pasta": pasta,
                    "arquivo": "sessaoplenaria_ano2026_p1.json",
                    "refazer": quebrado(),
                }
            ]
            self.assertTrue(e_lista_descoberta("sessaoplenaria_ano2026_p1.json"))
            with mock.patch.object(modulo, "esperar_antes_da_repeticao", lambda *a: None):
                with self.assertRaises(SystemExit) as ctx:
                    repetir_pendentes(pendentes, [99])
            mensagem = str(ctx.exception)
            self.assertIn("lista de descoberta", mensagem)
            self.assertIn("Nada foi publicado", mensagem)

    def test_lista_de_materias_tambem_bloqueia(self):
        import atualizar_semana as modulo

        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            (pasta / "materialegislativa_ano2026_p1.json").write_bytes(b'{"results": []}')
            pendentes = [
                {
                    "descricao": "materialegislativa_ano2026 pagina 1 (recusado)",
                    "sessao_id": None,
                    "pasta": pasta,
                    "arquivo": "materialegislativa_ano2026_p1.json",
                    "refazer": quebrado(),
                }
            ]
            with mock.patch.object(modulo, "esperar_antes_da_repeticao", lambda *a: None):
                with self.assertRaises(SystemExit) as ctx:
                    repetir_pendentes(pendentes, [99])
            self.assertIn("lista de descoberta", str(ctx.exception))

    def test_lista_que_voltou_no_tempo_nao_publica(self):
        antes = [
            {"id": 10, "numero": 34, "data_inicio": "2026-10-06"},
        ]
        depois = [
            {"id": 9, "numero": 33, "data_inicio": "2026-09-29"},
        ]
        self.assertEqual(maior_data_inicio(antes), "2026-10-06")
        with self.assertRaises(SystemExit) as ctx:
            conferir_lista_nao_regrediu(antes, depois)
        self.assertIn("regrediu", str(ctx.exception))
        self.assertIn("Nada foi publicado", str(ctx.exception))
        conferir_lista_nao_regrediu(antes, list(antes))


class TestM2IndiceEAutoriaNaFila(unittest.TestCase):
    def test_indice_da_api_entra_na_fila_e_bloqueia_depois(self):
        import atualizar_semana as modulo

        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            (pasta / "api_indice.json").write_bytes(b'{"sessao/sessaoplenaria": {}}')
            coletor = ColetorLote(CFG, pasta, teto=10)
            coletor.adiar_falha = True
            with mock.patch.object(
                ColetorLote, "pedir", side_effect=PedidoPendente("/api/", None, "api_indice.json", "503")
            ):
                pendentes: list = []
                baixar_lote(coletor, [2026], False, pendentes)
            self.assertEqual(len(pendentes), 1)
            self.assertEqual(pendentes[0]["arquivo"], "api_indice.json")
            self.assertTrue(e_indice_api(pendentes[0]["arquivo"]))
            pendentes[0]["refazer"] = quebrado("/api/", "api_indice.json", "503")
            with mock.patch.object(modulo, "esperar_antes_da_repeticao", lambda *a: None):
                with self.assertRaises(SystemExit) as ctx:
                    repetir_pendentes(pendentes, [99])
            self.assertIn("indice da API", str(ctx.exception))
            self.assertIn("Nada foi publicado", str(ctx.exception))

    def test_autoria_p1_entra_na_fila_e_segue_com_aviso(self):
        import atualizar_semana as modulo

        valido = {"pagination": {"total_pages": 1}, "results": []}

        def pedir_falso(self, caminho, params, arquivo, refrescar=False):
            if arquivo == "autoria_p1.json":
                raise PedidoPendente(caminho, params, arquivo, "503")
            return dict(valido)

        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            (pasta / "autoria_p1.json").write_bytes(b'{"pagination": {}, "results": []}')
            coletor = ColetorLote(CFG, pasta, teto=20)
            coletor.adiar_falha = True
            with mock.patch.object(ColetorLote, "pedir", pedir_falso):
                pendentes: list = []
                coletar_autoria(coletor, [2026], False, pendentes)
            achados = [item for item in pendentes if item["arquivo"] == "autoria_p1.json"]
            self.assertGreaterEqual(len(achados), 1)
            for item in achados:
                item["refazer"] = quebrado("/api/materia/autoria/", "autoria_p1.json", "503")
            with mock.patch.object(modulo, "esperar_antes_da_repeticao", lambda *a: None):
                avisos = repetir_pendentes(pendentes, [99])
            self.assertEqual(sorted(avisos), sorted(item["descricao"] for item in achados))


class TestM3RevisaoContaNoAlvo(unittest.TestCase):
    def test_falha_na_revisao_com_arquivo_antigo_nao_publica(self):
        import atualizar_semana as modulo
        from coletar_por_sessao import RECURSOS

        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp) / "porsessao"
            pasta.mkdir()
            for _caminho, recurso in RECURSOS:
                (pasta / f"sessao_11_{recurso}_p1.json").write_text(
                    '{"pagination": {}, "results": []}', encoding="utf-8"
                )
            pendentes = [
                {
                    "descricao": "sessao 11 (recusado)",
                    "sessao_id": 11,
                    "pasta": pasta,
                    "arquivo": None,
                    "refazer": quebrado(),
                }
            ]
            with mock.patch.object(modulo, "esperar_antes_da_repeticao", lambda *a: None):
                with self.assertRaises(SystemExit) as ctx:
                    repetir_pendentes(pendentes, [11, 12])
            self.assertIn("sessao 11", str(ctx.exception))
            self.assertIn("Nada foi publicado", str(ctx.exception))


class TestM4RefrescarP1(unittest.TestCase):
    def test_pagina_1_e_pedida_de_novo(self):
        import coletar_por_sessao as por_sessao

        chamadas: list = []

        class Falso:
            pasta = Path(".")

            def pedir(self, caminho, params, arquivo, refrescar=False):
                chamadas.append((arquivo, bool(refrescar)))
                sid = int(params.get("sessao_plenaria", 50))
                return {
                    "pagination": {"total_pages": 1, "total_entries": 1},
                    "results": [{"id": 1, "sessao_plenaria": sid}],
                }

        por_sessao.pedir_recurso(Falso(), 50, "/api/sessao/ordemdia/", "ordemdia")
        primeira = [item for item in chamadas if item[0].endswith("_p1.json")]
        self.assertTrue(primeira)
        self.assertTrue(all(item[1] for item in primeira))


class TestM6PresencaZerada(unittest.TestCase):
    def test_sessao_nova_com_presenca_zerada_recusa(self):
        import coletar_por_sessao as por_sessao

        class FalsoM6:
            def __init__(self, pasta):
                self.pasta = pasta

            def pedir(self, caminho, params, arquivo, refrescar=False):
                del params, refrescar
                if "sessaoplenariapresenca" in caminho or "presencaordemdia" in caminho:
                    dado = {
                        "pagination": {"total_entries": 0, "total_pages": 1, "page": 1},
                        "results": [],
                    }
                elif "ordemdia" in caminho and "presenca" not in caminho:
                    dado = {
                        "pagination": {"total_entries": 1, "total_pages": 1, "page": 1},
                        "results": [{"id": 501, "sessao_plenaria": 90}],
                    }
                else:
                    dado = {
                        "pagination": {"total_entries": 1, "total_pages": 1, "page": 1},
                        "results": [{"id": 900, "sessao_plenaria": 90}],
                    }
                (self.pasta / arquivo).write_text(json.dumps(dado), encoding="utf-8")
                return dado

        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            coletor = FalsoM6(pasta)
            with self.assertRaises(SystemExit) as ctx:
                por_sessao.coletar_sessao_completa(coletor, 90)
            mensagem = str(ctx.exception)
            self.assertIn("zerado", mensagem)
            self.assertIn("Ausencia nao vira falta", mensagem)
            self.assertIn("Nada foi publicado", mensagem)
            aviso = pasta / "sessao_90_recusada.json"
            self.assertTrue(aviso.is_file())
            self.assertFalse((pasta / "sessao_90_sessaoplenariapresenca_p1.json").is_file())


class TestB5Conferencia(unittest.TestCase):
    def test_nova_bloqueia_e_revisao_vira_aviso(self):
        divergencias = [
            {"sessao_id": 12, "recurso": "ordemdia", "bate": False, "motivo": "total distinto"},
            {"sessao_id": 11, "recurso": "ordemdia", "bate": False, "motivo": "total distinto"},
            {"sessao_id": 5, "recurso": "ordemdia", "bate": False, "motivo": "antiga"},
        ]
        bloqueantes, avisos = separar_divergencias_por_alvo(divergencias, [12], [11, 12])
        self.assertEqual([item["sessao_id"] for item in bloqueantes], [12])
        self.assertEqual(len(avisos), 1)
        self.assertIn("sessao 11", avisos[0])
        entrada = montar_entrada("2026-10-07", "https://exemplo.invalid", 10, [], [], [], avisos)
        self.assertIn("conferencia da sessao 11", entrada)


class TestM1Falhas(unittest.TestCase):
    def test_arquivo_em_falhas_e_recusado(self):
        nome = "dados/brutos/lote_20260927_porsessao/falhas/sessao_99_ordemdia_p1_t1.json"
        self.assertFalse(so_dados_mudaram([nome]))
        self.assertEqual(arquivos_fora_do_permitido([nome]), [nome])
        gitignore = (RAIZ / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("dados/**/falhas/", gitignore)


class TestB1B2Workflow(unittest.TestCase):
    def test_issue_sem_duplicar_e_cobre_cancelamento_e_timeout(self):
        texto = (RAIZ / ".github" / "workflows" / "atualizacao_semanal.yml").read_text(encoding="utf-8")
        self.assertIn("gh issue list --search", texto)
        self.assertIn("gh issue comment", texto)
        self.assertIn("mesmo titulo do dia", texto)
        self.assertIn("failure() || cancelled()", texto)
        self.assertIn("timeout-minutes: 240", texto)
        self.assertIn("400 pedidos", texto)


class TestB7Sonda(unittest.TestCase):
    def test_falha_da_sonda_vira_aviso_no_changelog(self):
        fonte = (RAIZ / "scripts" / "atualizar_semana.py").read_text(encoding="utf-8")
        self.assertIn("sonda do ano", fonte)
        entrada = montar_entrada(
            "2026-10-07",
            "https://exemplo.invalid",
            3,
            [],
            [],
            [],
            ["sonda do ano 2027 falhou (503). O recorte nao mudou."],
        )
        self.assertIn("sonda do ano 2027", entrada)
        self.assertIn("Coleta com aviso", entrada)


class TestB6CaminhosDePublicacao(unittest.TestCase):
    def test_repeticao_que_estoura_o_teto_nada_publica(self):
        import atualizar_semana as modulo

        def estourado():
            raise OrcamentoEsgotado("teto de 2 pedidos nesta execucao")

        pendentes = [
            {
                "descricao": "exemplo pagina 2",
                "sessao_id": None,
                "pasta": None,
                "arquivo": None,
                "refazer": estourado,
            }
        ]
        with mock.patch.object(modulo, "esperar_antes_da_repeticao", lambda *a: None):
            with self.assertRaises(OrcamentoEsgotado):
                repetir_pendentes(pendentes, [99])

    def test_sessao_do_alvo_com_arquivo_parcial_nao_publica(self):
        import atualizar_semana as modulo

        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            (pasta / "sessao_99_sessaoplenariapresenca_p1.json").write_text("{}", encoding="utf-8")
            pendentes = [
                {
                    "descricao": "sessao 99 (recusado)",
                    "sessao_id": 99,
                    "pasta": pasta,
                    "arquivo": None,
                    "refazer": quebrado(),
                }
            ]
            with mock.patch.object(modulo, "esperar_antes_da_repeticao", lambda *a: None):
                with self.assertRaises(SystemExit) as ctx:
                    repetir_pendentes(pendentes, [99])
            self.assertIn("Nada foi publicado", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
