"""D-046: presenca conta so dentro do mandato e licenca entra no total.

Vereador com licenca, vereador com mandato encerrado no meio do periodo
e suplente com posse no meio do periodo, tudo com dados de mentira.
Nenhum nome, data ou cidade de verdade aqui.
"""

from __future__ import annotations

import copy
import pathlib
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
for pasta in ("coletor", "dados/tratados"):
    if str(RAIZ / pasta) not in sys.path:
        sys.path.insert(0, str(RAIZ / pasta))

import gerar_atuacao_vereadores as atuacao  # noqa: E402
import gerar_dados_tela as tela  # noqa: E402

TIPO_LICENCA = "licenca_tratamento_saude"
ROTULO_LICENCA = "Licença para tratamento de saúde"


def vereador_falso(inicio: str, fim: str | None) -> dict:
    return {
        "id_sapl": 999,
        "nome_parlamentar": "Vereadora Ficticia",
        "mandatos": [
            {
                "mandato_id": 1,
                "condicao": "titular",
                "data_inicio_mandato": inicio,
                "data_fim_mandato": fim,
            }
        ],
    }


def sessao_falsa(sid: int, data: str, situacao: str) -> dict:
    return {
        "sessao_id": sid,
        "data_sessao": data,
        "rotulo": f"Sessao {sid}",
        "situacao": situacao,
        "rotulo_situacao": situacao,
        "presente_sessao_plenaria": situacao == "presente",
        "presente_ordem_dia": situacao == "presente",
        "justificativa": situacao == "falta_com_justificativa",
        "era_presidente": False,
        "link_sessao": "https://exemplo.invalid/sessao/1",
    }


class BaseD046(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._ordem = atuacao.ORDEM_ESTADOS
        cls._rotulos = dict(atuacao.ROTULOS_ESTADO)
        cls._licencas = list(atuacao.LICENCA_TIPOS)
        atuacao.registrar_tipos_afastamento(
            [
                {
                    "tipo": TIPO_LICENCA,
                    "rotulo": ROTULO_LICENCA,
                    "conta_como_falta": False,
                }
            ]
        )

    @classmethod
    def tearDownClass(cls):
        atuacao.ORDEM_ESTADOS = cls._ordem
        atuacao.ROTULOS_ESTADO = cls._rotulos
        atuacao.LICENCA_TIPOS[:] = cls._licencas


class TestJanelaDoMandato(BaseD046):
    def test_dentro_inclui_as_bordas(self):
        v = vereador_falso("2025-01-01", "2026-08-18")
        self.assertTrue(atuacao.dentro_do_mandato(v, "2025-01-01"))
        self.assertTrue(atuacao.dentro_do_mandato(v, "2026-08-18"))
        self.assertTrue(atuacao.dentro_do_mandato(v, "2026-03-17"))

    def test_fora_antes_da_posse_e_depois_do_fim(self):
        v = vereador_falso("2026-03-17", "2026-12-31")
        self.assertFalse(atuacao.dentro_do_mandato(v, "2026-03-16"))
        self.assertFalse(atuacao.dentro_do_mandato(v, "2027-01-01"))

    def test_mandato_sem_fim_vale_ate_o_futuro(self):
        v = vereador_falso("2025-01-01", None)
        self.assertTrue(atuacao.dentro_do_mandato(v, "2026-12-31"))


class TestLicencaNoTotal(BaseD046):
    def test_licenca_conta_como_falta_com_justificativa(self):
        lista = (
            [sessao_falsa(i, "2026-04-01", "presente") for i in range(6)]
            + [sessao_falsa(7, "2026-04-08", "falta_com_justificativa")]
            + [sessao_falsa(i, "2026-05-01", "falta_com_justificativa") for i in (8, 9, 10)]
        )
        p = atuacao.consolidar_presenca(lista, "Ficticia")
        self.assertEqual(p["presencas"], 6)
        self.assertEqual(p["faltas_com_justificativa"], 4)
        self.assertEqual(p["faltas_totais"], 4)
        self.assertEqual(p["sessoes_licenca"], 0)
        self.assertEqual(p["sessoes_ordinarias"], 10)
        self.assertAlmostEqual(p["taxa_presenca"], 60.0)
        self.assertAlmostEqual(p["percentual_faltas"], 40.0)
        self.assertEqual(p["sessoes_por_afastamento"], {})

    def test_situacao_licenca_antiga_e_rejeitada(self):
        lista = [sessao_falsa(8, "2026-05-01", TIPO_LICENCA)]
        with self.assertRaises(SystemExit):
            atuacao.consolidar_presenca(lista, "Ficticia")

    def test_sem_licenca_a_taxa_nao_muda(self):
        lista = [sessao_falsa(i, "2026-04-01", "presente") for i in range(9)] + [
            sessao_falsa(10, "2026-04-08", "falta_sem_justificativa")
        ]
        p = atuacao.consolidar_presenca(lista, "Ficticia")
        self.assertEqual(p["sessoes_ordinarias"], 10)
        self.assertAlmostEqual(p["taxa_presenca"], 90.0)

    def test_fora_do_mandato_nao_aparece_na_lista(self):
        lista = [sessao_falsa(i, "2026-04-01", "presente") for i in range(4)]
        p = atuacao.consolidar_presenca(lista, "Ficticia", sessoes_fora=5)
        self.assertEqual(p["sessoes_ordinarias"], 4)
        self.assertEqual(p["sessoes_do_ano"], 9)
        self.assertEqual(p["sessoes_fora_do_mandato"], 5)
        self.assertEqual(len(p["por_sessao"]), 4)
        for item in p["por_sessao"]:
            self.assertNotEqual(item["situacao"], "fora_do_mandato")

    def test_recomputar_da_legislatura_usa_a_mesma_regra(self):
        lista = (
            [sessao_falsa(i, "2026-04-01", "presente") for i in range(6)]
            + [sessao_falsa(7, "2026-04-08", "falta_com_justificativa")]
            + [sessao_falsa(i, "2026-05-01", "falta_com_justificativa") for i in (8, 9, 10)]
        )
        p = tela._recomputar_presenca(copy.deepcopy(lista), 2)
        self.assertEqual(p["sessoes_ordinarias"], 10)
        self.assertEqual(p["sessoes_do_ano"], 12)
        self.assertEqual(p["sessoes_fora_do_mandato"], 2)
        self.assertAlmostEqual(p["taxa_presenca"], 60.0)
        self.assertAlmostEqual(p["percentual_faltas"], 40.0)

    def test_recomputar_converte_licenca_antiga_em_falta_justificada(self):
        lista = (
            [sessao_falsa(i, "2026-04-01", "presente") for i in range(6)]
            + [sessao_falsa(i, "2026-05-01", TIPO_LICENCA) for i in (8, 9, 10)]
        )
        p = tela._recomputar_presenca(copy.deepcopy(lista), 0)
        self.assertEqual(p["faltas_com_justificativa"], 3)
        self.assertEqual(p["sessoes_licenca"], 0)
        self.assertAlmostEqual(p["taxa_presenca"], 66.67)


class TestCodigoGenerico(unittest.TestCase):
    def test_sem_nome_nem_data_fixa_no_codigo(self):
        arquivos = [
            RAIZ / "dados" / "tratados" / "gerar_atuacao_vereadores.py",
            RAIZ / "dados" / "tratados" / "gerar_dados_tela.py",
            RAIZ / "tela" / "patch_dados_vereadores.js",
            RAIZ / "tela" / "patch_dados_camara.js",
        ]
        for caminho in arquivos:
            with self.subTest(arquivo=caminho.name):
                texto = caminho.read_text(encoding="utf-8")
                for proibido in ("quege", "Quege", "QUEGE", "Rivanildo", "rivanildo"):
                    self.assertNotIn(proibido, texto)
                self.assertNotIn("2026-08-18", texto)


if __name__ == "__main__":
    unittest.main()
