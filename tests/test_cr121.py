"""Testes dos achados CR-121 (revisao da v1.2.1). Nenhum pedido a internet.

Um teste por item: A1, A2, M1, M2, B5, ano fechado (M3), B2 e B7.
Tudo com servidor falso ou arquivos temporarios.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
sys.path.insert(0, str(RAIZ / "coletor"))
sys.path.insert(0, str(RAIZ / "dados" / "tratados"))

from atualizar_semana import (  # noqa: E402
    avisos_ordem_vazia,
    conferir_autoria_apos_repeticao,
    montar_entrada,
    repetir_pendentes,
    retrato_autoria,
)
from coletar_lote import ColetorLote  # noqa: E402

CFG_COLETOR = {
    "cidade": {"nome": "Cidade Teste", "uf": "PR"},
    "sapl": {"endereco_base": "https://exemplo.invalid"},
    "campos_pessoais_removidos": {"lista": ["ip", "user"]},
    "rede": {
        "teto_bytes_resposta": 5000,
        "esquemas_permitidos": ["https"],
        "hosts_permitidos_extra": [],
    },
}


class Resposta:
    status = 200

    def __init__(self, corpo: bytes, url: str = "https://exemplo.invalid/api/"):
        self.corpo = corpo
        self.url = url

    def geturl(self):
        return self.url

    def read(self, tamanho: int | None = None) -> bytes:
        if tamanho is None:
            return self.corpo
        return self.corpo[:tamanho]

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class FalsoSessao:
    """Servidor falso por sessao: grava o JSON e devolve o dicionario."""

    def __init__(self, pasta: Path, zeros: set[str], falhar_mesa_uma_vez: bool = False):
        self.pasta = pasta
        self.zeros = set(zeros)
        self.falhar_mesa = falhar_mesa_uma_vez
        self.chamadas_mesa = 0
        self.registros_por_ordem: dict[int, list[dict]] = {}
        self.votos_por_registro: dict[int, list[dict]] = {}

    def pedir(self, caminho, params, arquivo, refrescar=False):
        from coletar_lote import PedidoPendente
        import coletar_por_sessao as ps

        del refrescar
        if caminho == ps.CAMINHO_MESA and self.falhar_mesa and self.chamadas_mesa == 0:
            self.chamadas_mesa += 1
            raise PedidoPendente(caminho, params, arquivo, "503")
        if caminho == ps.CAMINHO_REGISTRO:
            resultados = list(self.registros_por_ordem.get(int(params.get("ordem")), []))
            dado = {
                "pagination": {
                    "total_entries": len(resultados),
                    "total_pages": 1,
                    "page": 1,
                    "links": {"next": None, "previous": None},
                    "next_page": None,
                },
                "results": resultados,
            }
            (self.pasta / arquivo).write_text(json.dumps(dado), encoding="utf-8")
            return dado
        if caminho == ps.CAMINHO_VOTO:
            resultados = list(self.votos_por_registro.get(int(params.get("votacao")), []))
            dado = {
                "pagination": {
                    "total_entries": len(resultados),
                    "total_pages": 1,
                    "page": 1,
                    "links": {"next": None, "previous": None},
                    "next_page": None,
                },
                "results": resultados,
            }
            (self.pasta / arquivo).write_text(json.dumps(dado), encoding="utf-8")
            return dado
        sid = int(params.get("sessao_plenaria"))
        if "presenca" in caminho and "sessaoplenaria" in caminho:
            recurso = "sessaoplenariapresenca"
        elif "presencaordemdia" in caminho:
            recurso = "presencaordemdia"
        elif "ordemdia" in caminho:
            recurso = "ordemdia"
        elif "justificativa" in caminho:
            recurso = "justificativaausencia"
        else:
            recurso = "integrantemesa"
        total = 0 if recurso in self.zeros else 1
        resultados = []
        if total:
            resultados = [{"id": 900 + sid, "sessao_plenaria": sid, "parlamentar": 5}]
        dado = {
            "pagination": {
                "total_entries": total,
                "total_pages": 1,
                "page": 1,
                "links": {"next": None, "previous": None},
                "next_page": None,
            },
            "results": resultados,
        }
        (self.pasta / arquivo).write_text(json.dumps(dado), encoding="utf-8")
        return dado


class TesteA1(unittest.TestCase):
    def test_presenca_zerada_recusa_na_repeticao_com_a_mesma_decisao(self):
        import coletar_por_sessao as ps
        from coletar_lote import PedidoPendente

        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            coletor = FalsoSessao(
                pasta,
                {"sessaoplenariapresenca", "presencaordemdia"},
                falhar_mesa_uma_vez=True,
            )
            with self.assertRaises(PedidoPendente):
                ps.coletar_sessao_completa(coletor, 99, True)
            self.assertTrue((pasta / "sessao_99_sessaoplenariapresenca_p1.json").is_file())
            coletor.falhar_mesa = False
            with self.assertRaises(SystemExit) as ctx:
                ps.coletar_sessao_completa(coletor, 99, True)
            self.assertIn("zerado", str(ctx.exception))
            self.assertTrue((pasta / "sessao_99_recusada.json").is_file())

    def test_revisao_com_presenca_zerada_nao_recusa(self):
        import coletar_por_sessao as ps

        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            coletor = FalsoSessao(pasta, {"sessaoplenariapresenca", "presencaordemdia"})
            coletor.registros_por_ordem = {999: [{"id": 701}]}
            coletor.votos_por_registro = {701: [{"id": 801}]}
            resumo = ps.coletar_sessao_completa(coletor, 99, False)
            self.assertEqual(resumo["sessao_id"], 99)


def _pagina_autoria(ids: list[int], total: int, paginas: int) -> bytes:
    return json.dumps(
        {
            "pagination": {
                "total_entries": total,
                "total_pages": paginas,
                "page": 1,
                "links": {"next": None, "previous": None},
                "next_page": None,
            },
            "results": [{"id": item} for item in ids],
        }
    ).encode("utf-8")


class TesteA2(unittest.TestCase):
    def test_falha_na_pagina_2_restaura_tudo_e_deixa_um_pendente_generico(self):
        import atualizar_semana as modulo
        from atualizar_semana import OrcamentoExecucao, preparar_coletor
        from coletar_autoria import conferir_autoria

        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            velha_p1 = _pagina_autoria([1], 2, 2)
            velha_p2 = _pagina_autoria([2], 2, 2)
            (pasta / "autoria_p1.json").write_bytes(velha_p1)
            (pasta / "autoria_p2.json").write_bytes(velha_p2)
            orcamento = OrcamentoExecucao(50)
            coletor = preparar_coletor(CFG_COLETOR, pasta, orcamento, False)
            nova_p1 = _pagina_autoria([101], 2, 2)

            def comportamento(req, timeout=None):
                del timeout
                if "page=2" in req.full_url:
                    import urllib.error

                    raise urllib.error.URLError("recusado")
                if "page=1" in req.full_url or "page%22%3A+1" in req.full_url:
                    return Resposta(nova_p1)
                return Resposta(nova_p1)

            pendentes = []
            with mock.patch(
                "coletar_lote.urllib.request.urlopen", comportamento
            ), mock.patch("coletar_lote.time.sleep", lambda *a: None):
                modulo.coletar_autoria_estavel(coletor, False, pendentes)
            self.assertEqual(len(pendentes), 1)
            self.assertTrue(pendentes[0]["descricao"].startswith("autoria ("))
            self.assertNotIn("pagina 2", pendentes[0]["descricao"])
            self.assertEqual((pasta / "autoria_p1.json").read_bytes(), velha_p1)
            self.assertEqual((pasta / "autoria_p2.json").read_bytes(), velha_p2)
            ok, _detalhe = conferir_autoria(pasta)
            self.assertTrue(ok)

    def test_repeticao_nunca_mistura_pagina_nova_com_antiga(self):
        import atualizar_semana as modulo
        from atualizar_semana import OrcamentoExecucao, preparar_coletor
        from coletar_autoria import conferir_autoria
        from coletar_lote import PedidoPendente

        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            velha_p1 = _pagina_autoria([1], 2, 2)
            velha_p2 = _pagina_autoria([2], 2, 2)
            (pasta / "autoria_p1.json").write_bytes(velha_p1)
            (pasta / "autoria_p2.json").write_bytes(velha_p2)
            orcamento = OrcamentoExecucao(50)
            coletor = preparar_coletor(CFG_COLETOR, pasta, orcamento, False)
            nova_p1 = _pagina_autoria([101], 2, 2)
            nova_p2 = _pagina_autoria([102], 2, 2)
            estado = {"p2_ok": False}

            def comportamento(req, timeout=None):
                del timeout
                if "page=2" in req.full_url:
                    if not estado["p2_ok"]:
                        import urllib.error

                        raise urllib.error.URLError("recusado")
                    return Resposta(nova_p2)
                return Resposta(nova_p1)

            pendentes = []
            with mock.patch(
                "coletar_lote.urllib.request.urlopen", comportamento
            ), mock.patch("coletar_lote.time.sleep", lambda *a: None):
                modulo.coletar_autoria_estavel(coletor, False, pendentes)
                self.assertEqual(len(pendentes), 1)
                with self.assertRaises(PedidoPendente):
                    pendentes[0]["refazer"]()
                self.assertEqual((pasta / "autoria_p1.json").read_bytes(), velha_p1)
                self.assertEqual((pasta / "autoria_p2.json").read_bytes(), velha_p2)
                estado["p2_ok"] = True
                pendentes[0]["refazer"]()
            ok, detalhe = conferir_autoria(pasta)
            self.assertTrue(ok, detalhe)
            misturada = json.loads((pasta / "autoria_p1.json").read_text(encoding="utf-8"))
            ids_p1 = [item["id"] for item in misturada["results"]]
            self.assertEqual(ids_p1, [101])

    def test_conferencia_apos_repeticao_restaura_quando_nao_fecha(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            velha = _pagina_autoria([1], 2, 2)
            (pasta / "autoria_p1.json").write_bytes(velha)
            (pasta / "autoria_p2.json").write_bytes(_pagina_autoria([2], 2, 2))
            retrato = retrato_autoria(pasta)
            (pasta / "autoria_p2.json").write_bytes(_pagina_autoria([1], 2, 2))
            aviso = conferir_autoria_apos_repeticao(pasta, retrato)
            self.assertIsNotNone(aviso)
            self.assertIn("Valem os arquivos antigos", aviso)
            self.assertEqual((pasta / "autoria_p1.json").read_bytes(), velha)


class TesteM1(unittest.TestCase):
    def test_aviso_da_sonda_sobrevive_a_repeticao_e_chega_ao_changelog(self):
        import atualizar_semana as modulo

        avisos_coleta = [
            "sonda do ano 2027 falhou (recusado). O recorte nao mudou."
        ]
        with mock.patch.object(
            modulo, "esperar_antes_da_repeticao", lambda *a: None
        ):
            avisos_coleta.extend(repetir_pendentes([], [99], True))
        self.assertEqual(len(avisos_coleta), 1)
        entrada = montar_entrada(
            "2026-09-27", "https://exemplo.invalid", 12, [], [], [],
            avisos_coleta,
        )
        self.assertIn("sonda do ano 2027", entrada)


class TesteM2(unittest.TestCase):
    def _coletor(self, tmp):
        from atualizar_semana import OrcamentoExecucao

        pasta = Path(tmp)
        orcamento = OrcamentoExecucao(50)
        coletor = ColetorLote(CFG_COLETOR, pasta, teto=50)
        coletor.orcamento_execucao = orcamento
        coletor.adiar_falha = True
        return coletor

    def test_host_fora_do_config_nao_vira_pendente(self):
        from coletar_lote import PedidoPendente

        corpo = b'{"pagination": {"total_pages": 1}, "results": []}'
        with tempfile.TemporaryDirectory() as tmp:
            coletor = self._coletor(tmp)
            with mock.patch(
                "coletar_lote.urllib.request.urlopen",
                lambda *a, **k: Resposta(corpo, "https://malicioso.invalid/api/"),
            ), mock.patch("coletar_lote.time.sleep", lambda *a: None):
                with self.assertRaises(SystemExit) as ctx:
                    coletor.pedir("/api/um/", None, "lista_p1.json", refrescar=True)
            self.assertNotIsInstance(ctx.exception, PedidoPendente)
            self.assertIn("nao esta no config", str(ctx.exception))
            self.assertFalse((Path(tmp) / "lista_p1.json").is_file())

    def test_resposta_acima_do_teto_nao_vira_pendente(self):
        from coletar_lote import PedidoPendente

        corpo = b'{"results": [' + b"1," * 3000 + b"2]}"
        with tempfile.TemporaryDirectory() as tmp:
            coletor = self._coletor(tmp)
            with mock.patch(
                "coletar_lote.urllib.request.urlopen",
                lambda *a, **k: Resposta(corpo),
            ), mock.patch("coletar_lote.time.sleep", lambda *a: None):
                with self.assertRaises(SystemExit) as ctx:
                    coletor.pedir("/api/um/", None, "lista_p1.json", refrescar=True)
            self.assertNotIsInstance(ctx.exception, PedidoPendente)
            self.assertIn("teto", str(ctx.exception))
            self.assertFalse((Path(tmp) / "lista_p1.json").is_file())


class TesteB5(unittest.TestCase):
    def test_ordem_vazia_em_sessao_nova_nao_recusa_e_vira_aviso(self):
        import coletar_por_sessao as ps

        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            coletor = FalsoSessao(pasta, {"ordemdia"})
            resumo = ps.coletar_sessao_completa(coletor, 77, True)
            self.assertEqual(resumo["n_ordem"], 0)
            self.assertFalse((pasta / "sessao_77_recusada.json").exists())
            avisos = avisos_ordem_vazia(pasta, [77])
            self.assertEqual(avisos, ["sessao 77 sem itens na ordem do dia no SAPL"])
            entrada = montar_entrada(
                "2026-09-27", "https://exemplo.invalid", 12, [], [], [],
                [], [], avisos,
            )
            self.assertIn("sessao 77 sem itens na ordem do dia no SAPL", entrada)
            self.assertNotIn("Valeu o arquivo ja salvo", entrada)


class TesteAnoFechado(unittest.TestCase):
    def test_so_metadado_nao_regrava_e_conteudo_regrava(self):
        import gerar_atuacao_vereadores as g

        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            with mock.patch.object(g, "DIR_SCRIPT", pasta):
                with mock.patch.object(g, "ano_corrente_hoje", lambda: 2026):
                    base = {
                        "meta": {
                            "ano": 2025,
                            "dado_coletado_em": "2026-01-01T00:00:00-03:00",
                            "fonte_data_coleta": "pasta_antiga/indice.json",
                        },
                        "vereadores": [{"id_sapl": 1, "votos": {"sim": 2}}],
                    }
                    velho_json = json.dumps(base, ensure_ascii=False, indent=2) + "\n"
                    (pasta / "atuacao_vereadores_2025.json").write_text(
                        velho_json, encoding="utf-8"
                    )
                    (pasta / "atuacao_vereadores_2025.csv").write_text(
                        "a;b\n1;2\n", encoding="utf-8"
                    )
                    relatorio = (
                        "# Titulo\n\nDado coletado em: antiga\n"
                        "Fonte da data: antiga\n\nCorpo igual.\n"
                    )
                    (pasta / "RELATORIO-ATUACAO-VEREADORES-2025.md").write_text(
                        relatorio, encoding="utf-8"
                    )
                    nova_base = {
                        "meta": {
                            "ano": 2025,
                            "dado_coletado_em": "2026-10-09T00:00:00-03:00",
                            "fonte_data_coleta": "pasta_nova/indice.json",
                        },
                        "vereadores": [{"id_sapl": 1, "votos": {"sim": 2}}],
                    }
                    novo_json = json.dumps(nova_base, ensure_ascii=False, indent=2) + "\n"
                    novo_relatorio = (
                        "# Titulo\n\nDado coletado em: nova\n"
                        "Fonte da data: nova\n\nCorpo igual.\n"
                    )
                    self.assertTrue(
                        g.ano_fechado_sem_mudanca(2025, novo_json, "a;b\n1;2\n", novo_relatorio)
                    )
                    mudada = {
                        "meta": dict(nova_base["meta"]),
                        "vereadores": [{"id_sapl": 1, "votos": {"sim": 3}}],
                    }
                    self.assertFalse(
                        g.ano_fechado_sem_mudanca(
                            2025,
                            json.dumps(mudada, ensure_ascii=False, indent=2) + "\n",
                            "a;b\n1;2\n",
                            novo_relatorio,
                        )
                    )
                    self.assertFalse(
                        g.ano_fechado_sem_mudanca(2026, novo_json, "a;b\n1;2\n", novo_relatorio)
                    )

    def test_quebra_windows_nao_regrava_ano_fechado(self):
        import gerar_atuacao_vereadores as g

        velho = json.dumps(
            {"meta": {"dado_coletado_em": "a", "fonte_data_coleta": "b"}, "x": "A\r\nB"},
            ensure_ascii=False,
        )
        novo = json.dumps(
            {"meta": {"dado_coletado_em": "c", "fonte_data_coleta": "d"}, "x": "A\nB"},
            ensure_ascii=False,
        )
        self.assertEqual(g.json_sem_datas(velho), g.json_sem_datas(novo))


class TesteB2(unittest.TestCase):
    def _cfg(self):
        return {
            "sapl": {"endereco_base": "https://exemplo.invalid"},
            "categorias": {
                "lista": [
                    {"nome": "Saude", "descricao": "temas de saude"},
                    {"nome": "Educacao", "descricao": "temas de educacao"},
                ],
                "rotulos_especiais": {"nao_se_aplica": "Nao se aplica", "sem_ementa": "Sem ementa"},
            },
            "classificacao_temas": {
                "endpoint": "https://modelo.invalid",
                "modelos": [{"id": "modelo-a"}, {"id": "modelo-b"}],
                "tempo_limite_s": 60,
                "max_tokens_resposta": 300,
            },
        }

    def test_issues_so_abrem_no_fim(self):
        import classificar_temas as temas

        materia = {
            "id": 1,
            "ano": 2026,
            "sigla": "PLEG",
            "numero": "1",
            "ementa": "cria programa de saude",
            "link": "https://exemplo.invalid/materia/1",
        }

        def pedir_falso(modelo, ponta, prompt, chave, sessao, limite, teto):
            del ponta, prompt, chave, sessao, limite, teto
            tema = "Saude" if modelo == "modelo-a" else "Educacao"
            return {"tema": tema, "confianca": "alta", "justificativa": "motivo"}, None, 5, 0.2

        chamadas = []

        class Saida:
            def __init__(self, returncode=0, stdout="", stderr=""):
                self.returncode = returncode
                self.stdout = stdout
                self.stderr = stderr

        def correr_falso(args, **kwargs):
            del kwargs
            chamadas.append(list(args))
            if "list" in args:
                return Saida(0, "[]", "")
            return Saida(0, "", "")

        with mock.patch.object(temas, "ler_temas", lambda: {"materias": []}), mock.patch.object(
            temas, "pasta_lote_mais_recente", lambda: Path(tempfile.gettempdir())
        ), mock.patch.object(temas, "ler_materias_brutas", lambda _p, _c: {1: materia}):
            resultado = temas.classificar_novas(
                self._cfg(),
                "chave",
                pedir=pedir_falso,
                correr=correr_falso,
                gravar=False,
                abrir_issues=False,
            )
        self.assertEqual(len(resultado["pendentes"]), 1)
        self.assertFalse([c for c in chamadas if "create" in c])
        avisos = temas.abrir_issues_revisao(resultado, correr_falso)
        self.assertEqual(avisos, [])
        criadas = [c for c in chamadas if "create" in c]
        self.assertEqual(len(criadas), 1)
        self.assertIn("Tema para revisao: PLEG 1/2026", criadas[0])


class TesteB7(unittest.TestCase):
    def test_subprocesso_nao_recebe_a_chave(self):
        import atualizar_semana as modulo

        with mock.patch.dict(
            os.environ, {modulo.VAR_CHAVE_CLASSIFICADOR: "segredo"}, clear=False
        ):
            ambiente = modulo.ambiente_sem_chave()
            self.assertNotIn(modulo.VAR_CHAVE_CLASSIFICADOR, ambiente)
            self.assertEqual(ambiente.get("PATH"), os.environ.get("PATH"))
            with mock.patch.object(modulo.subprocess, "run") as executar:
                executar.return_value = mock.Mock(returncode=0)
                modulo.rodar(["coletor/testes_sanidade.py"])
                _args, kwargs = executar.call_args
                self.assertNotIn(modulo.VAR_CHAVE_CLASSIFICADOR, kwargs["env"])


if __name__ == "__main__":
    unittest.main()
