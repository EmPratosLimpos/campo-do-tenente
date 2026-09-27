import json
import pathlib
import unittest


class TestSanidadeDados(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        base_dir = pathlib.Path(__file__).resolve().parent.parent
        cls.json_path = base_dir / "dados" / "tratados" / "atuacao_vereadores_2026.json"
        cls.data = None
        if cls.json_path.exists():
            try:
                with cls.json_path.open("r", encoding="utf-8") as f:
                    cls.data = json.load(f)
            except Exception:
                cls.data = None

    def test_arquivo_existe_e_eh_json_valido(self):
        self.assertTrue(self.json_path.exists(), f"Arquivo não encontrado: {self.json_path}")
        self.assertIsNotNone(self.data, "JSON inválido ou falha ao carregar")

    def test_contem_exatamente_15_vereadores(self):
        self.assertIsNotNone(self.data, "Dados não carregados")
        vereadores = self.data.get("vereadores", [])
        self.assertEqual(len(vereadores), 15, "Deve haver exatamente 15 vereadores")

    def test_campos_obrigatorios_de_voto(self):
        self.assertIsNotNone(self.data, "Dados não carregados")
        vereadores = self.data.get("vereadores", [])
        self.assertTrue(len(vereadores) > 0, "Lista de vereadores vazia")

        campos_voto = [
            "sim",
            "nao",
            "abstencao",
            "presidente_nao_votou",
            "nao_votou_nao_era_presidente",
            "ausente",
            "total_registros",
            "nominais",
        ]

        for i, vereador in enumerate(vereadores, 1):
            with self.subTest(vereador=i):
                self.assertIn("votos", vereador, f"Vereador {i} não possui 'votos'")
                votos = vereador["votos"]
                for campo in campos_voto:
                    self.assertIn(campo, votos, f"Campo 'votos.{campo}' ausente no vereador {i}")
                    self.assertIsNotNone(votos[campo], f"Campo 'votos.{campo}' nulo no vereador {i}")

    def test_campos_obrigatorios_de_presenca(self):
        self.assertIsNotNone(self.data, "Dados não carregados")
        vereadores = self.data.get("vereadores", [])
        self.assertTrue(len(vereadores) > 0, "Lista de vereadores vazia")

        campos_presenca = [
            "presencas",
            "faltas_com_justificativa",
            "faltas_sem_justificativa",
            "taxa_presenca",
            "percentual_faltas",
            "sessoes_ordinarias",
            "por_sessao",
        ]

        for i, vereador in enumerate(vereadores, 1):
            with self.subTest(vereador=i):
                self.assertIn("presenca", vereador, f"Vereador {i} não possui 'presenca'")
                presenca = vereador["presenca"]
                for campo in campos_presenca:
                    self.assertIn(campo, presenca, f"Campo 'presenca.{campo}' ausente no vereador {i}")
                    self.assertIsNotNone(presenca[campo], f"Campo 'presenca.{campo}' nulo no vereador {i}")


if __name__ == "__main__":
    unittest.main()
