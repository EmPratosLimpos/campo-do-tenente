"""D-049: turno de cada votacao. Nao faz pedido ao SAPL."""

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
    TURNO_NAO_IDENTIFICADO,
    TURNO_PRIMEIRO,
    TURNO_SEGUNDO,
    TURNO_UNICO,
    atribuir_turnos,
    escolher_por_turno,
)

DOIS = {"PLEG", "PLEX"}


def voto(indice: int, data: str, sessao: int, resultado: str = "UNANIMIDADE") -> dict:
    return {
        "id": indice,
        "data_sessao": data,
        "sessao_id": sessao,
        "data_hora": "",
        "resultado_texto_sapl": resultado,
        "situacao_oficial_sapl": None,
    }


class TestAtribuirTurnos(unittest.TestCase):
    def test_tipo_fora_dos_dois_turnos_e_unico(self):
        votos = [voto(1, "2026-09-22", 273), voto(2, "2026-09-29", 274)]
        self.assertEqual(atribuir_turnos("REQ", votos, DOIS), [TURNO_UNICO, TURNO_UNICO])
        self.assertEqual(atribuir_turnos(None, votos, DOIS), [TURNO_UNICO, TURNO_UNICO])

    def test_primeira_data_e_primeiro_e_outra_e_segundo(self):
        votos = [voto(1, "2026-09-22", 273), voto(2, "2026-09-29", 274)]
        self.assertEqual(
            atribuir_turnos("PLEG", votos, DOIS), [TURNO_PRIMEIRO, TURNO_SEGUNDO]
        )

    def test_repeticao_no_mesmo_dia_segue_o_turno_do_dia(self):
        votos = [
            voto(1, "2026-06-17", 10),
            voto(2, "2026-06-17", 10),
            voto(3, "2026-06-24", 11),
        ]
        self.assertEqual(
            atribuir_turnos("PLEG", votos, DOIS),
            [TURNO_PRIMEIRO, TURNO_PRIMEIRO, TURNO_SEGUNDO],
        )

    def test_terceira_data_nao_identificada(self):
        votos = [
            voto(1, "2026-06-17", 10),
            voto(2, "2026-06-24", 11),
            voto(3, "2026-07-01", 12),
        ]
        self.assertEqual(
            atribuir_turnos("PLEG", votos, DOIS),
            [TURNO_PRIMEIRO, TURNO_SEGUNDO, TURNO_NAO_IDENTIFICADO],
        )

    def test_rejeicao_no_primeiro_marca_o_seguinte(self):
        votos = [
            voto(1, "2026-06-17", 10, "REJEITADO"),
            voto(2, "2026-06-24", 11, "UNANIMIDADE"),
        ]
        self.assertEqual(
            atribuir_turnos("PLEG", votos, DOIS),
            [TURNO_PRIMEIRO, TURNO_NAO_IDENTIFICADO],
        )


class TestEscolherPorTurno(unittest.TestCase):
    def test_segundo_turno_decide(self):
        primeiro = voto(1, "2026-09-22", 273)
        segundo = voto(2, "2026-09-29", 274)
        escolhida, em_tram = escolher_por_turno(
            [(primeiro, TURNO_PRIMEIRO), (segundo, TURNO_SEGUNDO)]
        )
        self.assertEqual(escolhida, segundo)
        self.assertFalse(em_tram)

    def test_so_primeiro_aprovado_segue_em_tramitacao(self):
        primeiro = voto(1, "2026-09-22", 273)
        escolhida, em_tram = escolher_por_turno([(primeiro, TURNO_PRIMEIRO)])
        self.assertEqual(escolhida, primeiro)
        self.assertTrue(em_tram)

    def test_rejeitado_no_primeiro_encerra(self):
        primeiro = voto(1, "2026-06-17", 10, "REJEITADO")
        segundo = voto(2, "2026-06-24", 11, "UNANIMIDADE")
        escolhida, em_tram = escolher_por_turno(
            [(primeiro, TURNO_PRIMEIRO), (segundo, TURNO_NAO_IDENTIFICADO)]
        )
        self.assertEqual(escolhida, primeiro)
        self.assertFalse(em_tram)

    def test_sem_voto_nao_escolhe(self):
        escolhida, em_tram = escolher_por_turno([])
        self.assertIsNone(escolhida)
        self.assertTrue(em_tram)


class TestConfigTurnos(unittest.TestCase):
    def test_dois_turnos_vem_do_config(self):
        from config_cidade import carregar_config, tipos_dois_turnos

        cfg = carregar_config()
        dois = tipos_dois_turnos(cfg)
        self.assertIn("PLEG", dois)
        self.assertIn("PLEX", dois)
        self.assertNotIn("REQ", dois)
        self.assertNotIn("IND", dois)

    def test_config_sem_lista_e_recusada(self):
        from config_cidade import tipos_dois_turnos

        with self.assertRaises(SystemExit):
            tipos_dois_turnos({"turnos_votacao": {}})
        with self.assertRaises(SystemExit):
            tipos_dois_turnos({"turnos_votacao": {"dois_turnos": ["PLEG", "PLEG"]}})


class TestTurnosReais(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.atuacao = json.loads(
            (RAIZ / "dados" / "tratados" / "atuacao_vereadores_2026.json").read_text(
                encoding="utf-8"
            )
        )
        cls.leg = json.loads(
            (
                RAIZ / "dados" / "tratados" / "atuacao_vereadores_legislatura.json"
            ).read_text(encoding="utf-8")
        )
        cls.camara = json.loads(
            (
                RAIZ / "dados" / "tratados" / "materias_camara_legislatura.json"
            ).read_text(encoding="utf-8")
        )

    def test_pleg_4_primeiro_e_segundo_turno(self):
        projeto = next(p for p in self.atuacao["projetos_lei"] if p["id"] == 811)
        turnos = [(v["data_sessao"], v["turno"]) for v in projeto["votacoes_ordinarias"]]
        self.assertEqual(
            turnos, [("2026-09-22", TURNO_PRIMEIRO), ("2026-09-29", TURNO_SEGUNDO)]
        )
        self.assertEqual(projeto["situacao"], "Aprovado")

    def test_camara_mostra_o_segundo_turno(self):
        item = next(m for m in self.camara["sessao"] if int(m["id"]) == 811)
        self.assertEqual(item["turno"], TURNO_SEGUNDO)
        self.assertEqual(item["resultado"], "unanimidade")

    def test_requerimento_e_turno_unico(self):
        achados = [
            n
            for v in self.leg["vereadores"]
            for n in v["votos"]["nominais"]
            if n.get("votacao_id") == 277
        ]
        self.assertTrue(achados)
        for nominal in achados:
            self.assertEqual(nominal.get("turno"), TURNO_UNICO)

    def test_nenhum_turno_nao_identificado_nos_dados(self):
        for ano in (2025, 2026):
            dados = json.loads(
                (
                    RAIZ / "dados" / "tratados" / f"atuacao_vereadores_{ano}.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(dados["meta"]["votacoes_turno_nao_identificado"], [])


if __name__ == "__main__":
    unittest.main()
