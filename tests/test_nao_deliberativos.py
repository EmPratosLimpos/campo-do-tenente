"""D-050: resultado oficial pelo tipo, sem deliberacao nao consome turno."""

from __future__ import annotations

import json
import pathlib
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
for pasta in ("coletor", "dados/tratados"):
    if str(RAIZ / pasta) not in sys.path:
        sys.path.insert(0, str(RAIZ / pasta))

from gerar_atuacao_vereadores import (  # noqa: E402
    TURNO_PRIMEIRO,
    TURNO_SEGUNDO,
    atribuir_turnos,
    deliberativa_nome,
    escolher_por_turno,
    situacao_por_nome,
)

DOIS = {"PLEG", "PLEX"}


def registro_falso(rid: int, data: str, sessao: int, oficial=None, texto=None) -> dict:
    return {
        "id": rid,
        "data_sessao": data,
        "sessao_id": sessao,
        "data_hora": "",
        "resultado_texto_sapl": texto,
        "situacao_oficial_sapl": oficial,
    }


class TestNomesOficiais(unittest.TestCase):
    def test_tabela_tem_os_seis_nomes(self):
        from config_cidade import carregar_config  # noqa
        import gerar_atuacao_vereadores as g  # noqa

        tipos = g.carregar_tipos_resultado()
        self.assertEqual(
            tipos,
            {
                1: "Adiada",
                2: "Aprovada por Unanimidade",
                3: "Aprovada por Maioria Absoluta",
                4: "Pedido de Vistas",
                5: "Rejeitada",
                6: "Retirada de Pauta",
            },
        )

    def test_deliberativo_so_aprovada_e_rejeitada(self):
        self.assertEqual(situacao_por_nome("Aprovada por Unanimidade"), "Aprovado")
        self.assertEqual(situacao_por_nome("Aprovada por Maioria Absoluta"), "Aprovado")
        self.assertEqual(situacao_por_nome("Rejeitada"), "Rejeitado")
        for nome in ("Adiada", "Pedido de Vistas", "Retirada de Pauta", None, ""):
            self.assertIsNone(situacao_por_nome(nome))
            self.assertFalse(deliberativa_nome(nome))
        self.assertTrue(deliberativa_nome("Aprovada por Unanimidade"))


class TestNaoConsomeTurno(unittest.TestCase):
    def test_pedido_depois_do_primeiro(self):
        primeiro = registro_falso(1, "2026-08-11", 266, "Aprovado", "UNANIMIDADE")
        turnos = atribuir_turnos("PLEX", [primeiro], DOIS)
        self.assertEqual(turnos, [TURNO_PRIMEIRO])
        escolhida, em_tram = escolher_por_turno([(primeiro, TURNO_PRIMEIRO)])
        self.assertEqual(escolhida, primeiro)
        self.assertTrue(em_tram)

    def test_adiada_antes_do_primeiro(self):
        turnos = atribuir_turnos(
            "PLEG", [registro_falso(1, "2026-08-11", 266, "Aprovado", "UNANIMIDADE")], DOIS
        )
        self.assertEqual(turnos, [TURNO_PRIMEIRO])

    def test_retirada_sozinha_nao_decide(self):
        escolhida, em_tram = escolher_por_turno([])
        self.assertIsNone(escolhida)
        self.assertTrue(em_tram)


class TestPlex9Real(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.atuacao = json.loads(
            (RAIZ / "dados" / "tratados" / "atuacao_vereadores_2026.json").read_text(
                encoding="utf-8"
            )
        )

    def test_situacao_em_tramitacao_com_pedido_de_vistas(self):
        projeto = next(p for p in self.atuacao["projetos_lei"] if p["id"] == 704)
        self.assertEqual(projeto["situacao"], "Em tramitacao")
        self.assertEqual(projeto["nome_oficial_ultimo_registro"], "Pedido de Vistas")
        turnos = [(v["data_sessao"], v["turno"]) for v in projeto["votacoes_ordinarias"]]
        self.assertEqual(
            turnos, [("2026-08-11", TURNO_PRIMEIRO), ("2026-08-25", None)]
        )
        nomes = [v["tipo_resultado_nome"] for v in projeto["votacoes_ordinarias"]]
        self.assertEqual(nomes, ["Aprovada por Unanimidade", "Pedido de Vistas"])

    def test_zero_resultado_nao_mapeado(self):
        for ano in (2025, 2026):
            texto = (
                RAIZ / "dados" / "tratados" / f"atuacao_vereadores_{ano}.json"
            ).read_text(encoding="utf-8")
            self.assertNotIn("Resultado nao mapeado", texto)

    def test_nenhuma_pleg_votada_some_da_camara(self):
        camara = json.loads(
            (RAIZ / "dados" / "tratados" / "materias_camara_legislatura.json").read_text(
                encoding="utf-8"
            )
        )
        no_todo = {int(m["id"]) for m in camara.get("todo") or []}
        for ano in (2025, 2026):
            dados = json.loads(
                (RAIZ / "dados" / "tratados" / f"atuacao_vereadores_{ano}.json").read_text(
                    encoding="utf-8"
                )
            )
            for p in dados["projetos_lei"]:
                if p["tipo_sigla"] == "PLEG" and p["votacoes_ordinarias"]:
                    self.assertIn(p["id"], no_todo)


if __name__ == "__main__":
    unittest.main()
