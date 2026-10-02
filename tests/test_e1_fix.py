"""Testes dos ajustes da revisao E1. Nao fazem pedido ao SAPL."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "coletor"))
sys.path.insert(0, str(RAIZ / "dados" / "tratados"))

from coletar_lote import (  # noqa: E402
    TETO_PAGINAS,
    ColetorLote,
    _total_paginas,
    continuar_apos_primeira,
)
from coletar_por_sessao import (  # noqa: E402
    exigir_minimo_de_sessoes,
    pasta_lote_origem,
    sessoes_ordinarias,
)
from derivar_insumos import (  # noqa: E402
    aplicar_fonte_incompleta,
    exigir_pasta_por_sessao,
    ler_paginas,
    recursos_com_faltante,
)
from gerar_atuacao_vereadores import (  # noqa: E402
    AVISO_CONFLITO_AFASTAMENTO,
    SITUACAO_NAO_MAPEADA,
    aplicar_aviso_na_votacao,
    estado_na_votacao,
    situacao_da_votacao_escolhida,
)

CFG_COLETOR = {
    "cidade": {"nome": "Cidade Teste", "uf": "PR"},
    "sapl": {"endereco_base": "https://exemplo.invalid"},
}


class Resposta:
    status = 200

    def __init__(self, corpo: bytes):
        self.corpo = corpo

    def read(self) -> bytes:
        return self.corpo

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def cfg_pisos(pisos: dict[int, int]) -> dict:
    por_ano = {
        str(ano): {
            "vereadores": 1,
            "sessoes_ordinarias": piso,
            "projetos_lei_legislativo_e_executivo": 1,
        }
        for ano, piso in pisos.items()
    }
    return {
        "recorte": {"anos": list(pisos)},
        "pisos_sanidade": {"por_ano": por_ano},
    }


def gravar_ordinarias(pasta: Path, ano: int, datas: list[str]) -> None:
    linhas = []
    for indice, data in enumerate(datas, start=1):
        linhas.append(
            {
                "id": int(ano) * 100 + indice,
                "tipo": 3,
                "numero": indice,
                "data_inicio": data,
            }
        )
    pagina = {
        "pagination": {
            "total_entries": len(linhas),
            "total_pages": 1,
            "links": {"next": None},
            "next_page": None,
        },
        "results": linhas,
    }
    (pasta / f"sessaoplenaria_ano{ano}_p1.json").write_text(
        json.dumps(pagina), encoding="utf-8"
    )


def pagina_lista(total: int, linhas: list) -> dict:
    return {
        "pagination": {
            "total_entries": total,
            "total_pages": 1,
            "links": {"next": None},
            "next_page": None,
        },
        "results": linhas,
    }


class TestePisoDeSessoes(unittest.TestCase):
    def test_codigo_nao_exige_total_fixo_nem_data_de_lote(self):
        texto = (RAIZ / "coletor" / "coletar_por_sessao.py").read_text(encoding="utf-8")
        self.assertNotIn("lote_20260926", texto)
        self.assertNotIn("!= 65", texto)
        self.assertNotIn("Esperava 65", texto)

    def test_sessao_acima_do_piso_nao_interrompe(self):
        cfg = cfg_pisos({2025: 1})
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            gravar_ordinarias(pasta, 2025, ["2025-02-01", "2025-03-01", "2025-04-01"])
            sessoes = sessoes_ordinarias(pasta, 3, [2025])
            self.assertEqual(len(sessoes), 3)
            exigir_minimo_de_sessoes(sessoes, cfg)

    def test_quantidade_igual_ao_piso_passa(self):
        cfg = cfg_pisos({2025: 2})
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            gravar_ordinarias(pasta, 2025, ["2025-02-01", "2025-03-01"])
            exigir_minimo_de_sessoes(sessoes_ordinarias(pasta, 3, [2025]), cfg)

    def test_abaixo_do_piso_para(self):
        cfg = cfg_pisos({2025: 3, 2026: 1})
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            gravar_ordinarias(pasta, 2025, ["2025-02-01"])
            gravar_ordinarias(pasta, 2026, ["2026-02-01"])
            sessoes = sessoes_ordinarias(pasta, 3, [2025, 2026])
            with self.assertRaises(SystemExit) as ctx:
                exigir_minimo_de_sessoes(sessoes, cfg)
        self.assertIn("2025: piso 3, achei 1", str(ctx.exception))

    def test_lote_mais_recente_que_tem_as_listas(self):
        with tempfile.TemporaryDirectory() as tmp:
            brutos = Path(tmp)
            antigo = brutos / "lote_20260101"
            recente = brutos / "lote_20260301"
            sem_lista = brutos / "lote_20260401"
            por_sessao = brutos / "lote_20260501_porsessao"
            for pasta in (antigo, recente):
                pasta.mkdir(parents=True)
                (pasta / "sessaoplenaria_ano2025_p1.json").write_text("{}", encoding="utf-8")
                (pasta / "sessaoplenaria_ano2026_p1.json").write_text("{}", encoding="utf-8")
            sem_lista.mkdir()
            por_sessao.mkdir()
            (por_sessao / "sessaoplenaria_ano2025_p1.json").write_text("{}", encoding="utf-8")
            (por_sessao / "sessaoplenaria_ano2026_p1.json").write_text("{}", encoding="utf-8")
            self.assertEqual(pasta_lote_origem(brutos, [2025, 2026]), recente)


class TesteListaIncompleta(unittest.TestCase):
    def test_ordem_incompleta_avisa_e_usa_coleta_por_sessao(self):
        with tempfile.TemporaryDirectory() as tmp:
            lote = Path(tmp) / "lote"
            por = Path(tmp) / "por"
            lote.mkdir()
            por.mkdir()
            (lote / "ordemdia_p1.json").write_text(
                json.dumps(
                    pagina_lista(
                        2,
                        [
                            {"id": 1, "sessao_plenaria": 4},
                            {"id": 1, "sessao_plenaria": 4},
                        ],
                    )
                ),
                encoding="utf-8",
            )
            (por / "sessao_4_ordemdia_p1.json").write_text(
                json.dumps(
                    pagina_lista(
                        2,
                        [
                            {"id": 1, "sessao_plenaria": 4},
                            {"id": 7, "sessao_plenaria": 4},
                        ],
                    )
                ),
                encoding="utf-8",
            )
            saida = io.StringIO()
            with contextlib.redirect_stdout(saida):
                linhas, _nomes = ler_paginas(lote, "ordemdia")
            self.assertIn("AVISO:", saida.getvalue())
            self.assertIn("faltam 1", saida.getvalue())
            avisos = json.loads((lote / "avisos_leitura.json").read_text(encoding="utf-8"))
            self.assertEqual(avisos[0]["prefixo"], "ordemdia")
            self.assertEqual(avisos[0]["total_entries"], 2)
            self.assertEqual(avisos[0]["ids_distintos"], 1)
            self.assertEqual(avisos[0]["faltantes"], 1)
            self.assertEqual(recursos_com_faltante(lote), ["ordemdia"])
            with self.assertRaises(SystemExit) as ctx:
                exigir_pasta_por_sessao(recursos_com_faltante(lote), None)
            self.assertIn("coleta por sessao", str(ctx.exception))
            mescladas, _nomes_novos, cobertura = aplicar_fonte_incompleta(
                "ordemdia", linhas, por, {4}, True
            )
            self.assertEqual(sorted(item["id"] for item in mescladas), [1, 7])
            self.assertEqual(cobertura["fonte"], "coleta_por_sessao")

    def test_recurso_sem_coleta_por_sessao_para_com_aviso(self):
        with tempfile.TemporaryDirectory() as tmp:
            lote = Path(tmp)
            (lote / "votoparlamentar_p1.json").write_text(
                json.dumps(pagina_lista(2, [{"id": 1}, {"id": 1}])),
                encoding="utf-8",
            )
            saida = io.StringIO()
            with self.assertRaises(SystemExit) as ctx:
                with contextlib.redirect_stdout(saida):
                    ler_paginas(lote, "votoparlamentar")
            self.assertIn("nao tem coleta por sessao", str(ctx.exception))
            self.assertIn("AVISO:", saida.getvalue())
            avisos = json.loads((lote / "avisos_leitura.json").read_text(encoding="utf-8"))
            self.assertEqual(avisos[0]["faltantes"], 1)


class TesteResultadoNaoMapeado(unittest.TestCase):
    def test_frase_nao_reconhecida_preserva_o_texto(self):
        escolhida = {
            "id": 9,
            "situacao_oficial_sapl": None,
            "frase_resultado_sapl": "Aprovada por maioria simples",
            "texto_registro_sapl": "Projeto - Votação: Aprovada por maioria simples",
            "resultado_texto_sapl": None,
        }
        self.assertEqual(situacao_da_votacao_escolhida(escolhida), SITUACAO_NAO_MAPEADA)
        self.assertEqual(
            escolhida["texto_registro_sapl"],
            "Projeto - Votação: Aprovada por maioria simples",
        )
        self.assertEqual(escolhida["frase_resultado_sapl"], "Aprovada por maioria simples")

    def test_resultado_oficial_conhecido_permanece(self):
        escolhida = {
            "id": 3,
            "situacao_oficial_sapl": "Aprovado",
            "frase_resultado_sapl": "Aprovada por Unanimidade",
            "texto_registro_sapl": "Votação: Aprovada por Unanimidade",
        }
        self.assertEqual(situacao_da_votacao_escolhida(escolhida), "Aprovado")

    def test_votacao_sem_texto_ainda_para(self):
        with self.assertRaises(SystemExit):
            situacao_da_votacao_escolhida(
                {
                    "id": 1,
                    "situacao_oficial_sapl": None,
                    "frase_resultado_sapl": None,
                    "texto_registro_sapl": "",
                }
            )


class TestePaginacaoSemTotal(unittest.TestCase):
    def test_sem_total_nao_assume_duas_paginas(self):
        dados = {
            "pagination": {"links": {"next": "https://exemplo.invalid/api?page=2"}},
            "results": [{"id": 1}],
        }
        self.assertIsNone(_total_paginas(dados, 100))
        self.assertNotEqual(_total_paginas(dados, 100), 2)

    def test_segue_next_ate_a_terceira_pagina(self):
        corpos = {
            1: {
                "pagination": {"page": 1, "links": {"next": "https://exemplo.invalid/api?page=2"}},
                "results": [{"id": 1}],
            },
            2: {
                "pagination": {"page": 2, "links": {"next": "https://exemplo.invalid/api?page=3"}},
                "results": [{"id": 2}],
            },
            3: {
                "pagination": {"page": 3, "links": {"next": None}},
                "results": [{"id": 3}],
            },
        }
        chamadas = []

        def urlopen(req, timeout=None):
            del timeout
            consulta = req.full_url
            pagina = 1
            if "page=" in consulta:
                pagina = int(consulta.split("page=")[1].split("&")[0])
            chamadas.append(pagina)
            return Resposta(json.dumps(corpos[pagina]).encode("utf-8"))

        with tempfile.TemporaryDirectory() as tmp:
            coletor = ColetorLote(CFG_COLETOR, Path(tmp), teto=10)
            saida = io.StringIO()
            with mock.patch("coletar_lote.time.sleep", lambda segundos: None), mock.patch(
                "coletar_lote.urllib.request.urlopen", urlopen
            ), contextlib.redirect_stdout(saida):
                coletor.pedir_paginas("/api/exemplo/", {}, "exemplo")
            pasta = Path(tmp)
            self.assertTrue((pasta / "exemplo_p1.json").is_file())
            self.assertTrue((pasta / "exemplo_p2.json").is_file())
            self.assertTrue((pasta / "exemplo_p3.json").is_file())
            self.assertEqual(chamadas, [1, 2, 3])
            self.assertIn("Sigo o link next", saida.getvalue())
            self.assertIn(str(TETO_PAGINAS), saida.getvalue())

    def test_teto_interrompe_quando_next_nao_acaba(self):
        def urlopen(req, timeout=None):
            del req, timeout
            corpo = {
                "pagination": {"links": {"next": "https://exemplo.invalid/api?page=99"}},
                "results": [{"id": 1}],
            }
            return Resposta(json.dumps(corpo).encode("utf-8"))

        with tempfile.TemporaryDirectory() as tmp:
            coletor = ColetorLote(CFG_COLETOR, Path(tmp), teto=10)
            with mock.patch("coletar_lote.TETO_PAGINAS", 2), mock.patch(
                "coletar_lote.time.sleep", lambda segundos: None
            ), mock.patch("coletar_lote.urllib.request.urlopen", urlopen):
                with self.assertRaises(SystemExit) as ctx:
                    coletor.pedir_paginas("/api/exemplo/", {}, "exemplo")
            self.assertIn("teto", str(ctx.exception))
            self.assertFalse((Path(tmp) / "exemplo_p3.json").is_file())


class TesteConflitoAfastamento(unittest.TestCase):
    def _vereador(self) -> dict:
        return {
            "id_sapl": 4,
            "nome_parlamentar": "Vereador Teste",
            "mandatos": [
                {
                    "data_inicio_mandato": "2025-01-01",
                    "data_fim_mandato": "2028-12-31",
                }
            ],
        }

    def _afastamento(self) -> dict:
        return {
            "tipo": "licenca",
            "rotulo": "Licenca",
            "parlamentar_id_sapl": 4,
            "data_inicio": "2026-03-01",
            "data_fim": "2026-03-31",
            "conta_como_falta": False,
            "fonte_oficial_encontrada": True,
            "fonte": "ato de teste",
            "link_fonte": "https://exemplo.invalid/ato",
        }

    def test_voto_oficial_permanece_e_a_votacao_recebe_aviso(self):
        estado, texto, extra = estado_na_votacao(
            self._vereador(),
            "2026-03-10",
            "Sim",
            9,
            False,
            False,
            self._afastamento(),
            None,
        )
        self.assertEqual(estado, "sim")
        self.assertEqual(texto, "Sim")
        self.assertEqual(extra["aviso"], AVISO_CONFLITO_AFASTAMENTO)
        votacao = {}
        resto = aplicar_aviso_na_votacao(votacao, 4, texto, extra)
        self.assertNotIn("aviso", resto)
        self.assertEqual(len(votacao["avisos"]), 1)
        self.assertEqual(votacao["avisos"][0]["aviso"], AVISO_CONFLITO_AFASTAMENTO)
        self.assertEqual(votacao["avisos"][0]["voto_texto_sapl"], "Sim")
        self.assertEqual(votacao["avisos"][0]["id_sapl"], 4)

    def test_afastamento_sem_voto_nao_gera_conflito(self):
        estado, texto, extra = estado_na_votacao(
            self._vereador(),
            "2026-03-10",
            None,
            9,
            False,
            False,
            self._afastamento(),
            None,
        )
        self.assertEqual(estado, "ausente_com_justificativa")
        self.assertIsNone(texto)
        self.assertNotIn("aviso", extra)


class TesteContinuarNaoInventaTotal(unittest.TestCase):
    def test_total_pages_e_count_continuam_validos(self):
        self.assertEqual(
            _total_paginas({"pagination": {"total_pages": 4}, "results": []}, 100),
            4,
        )
        self.assertEqual(_total_paginas({"count": 250, "results": []}, 100), 3)
        self.assertEqual(_total_paginas({"results": []}, 100), 1)

    def test_helper_segue_next(self):
        paginas = {
            1: {"pagination": {"page": 1, "next_page": 2}, "results": [{"id": 1}]},
            2: {"pagination": {"page": 2, "next_page": None}, "results": [{"id": 2}]},
        }
        baixadas = []

        def baixar(numero: int):
            baixadas.append(numero)
            return paginas[numero]

        continuar_apos_primeira(paginas[1], "lista", baixar)
        self.assertEqual(baixadas, [2])


if __name__ == "__main__":
    unittest.main()
