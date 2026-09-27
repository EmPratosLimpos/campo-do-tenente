import json
import pathlib
import sys
import unittest

DIR_RAIZ = pathlib.Path(__file__).resolve().parent.parent
if str(DIR_RAIZ / "coletor") not in sys.path:
    sys.path.insert(0, str(DIR_RAIZ / "coletor"))

from config_cidade import (  # noqa: E402
    PisoNaoDefinido,
    anos_recorte,
    carregar_config,
    exigir_piso,
    pisos_sanidade,
)


class TestSanidadeDados(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.config = carregar_config()
        cls.anos = anos_recorte(cls.config)
        cls.pisos = pisos_sanidade(cls.config)
        cls.dir_tratados = DIR_RAIZ / "dados" / "tratados"
        cls.datasets = []
        for ano in cls.anos:
            caminho = cls.dir_tratados / f"atuacao_vereadores_{ano}.json"
            if not caminho.exists():
                continue
            with caminho.open("r", encoding="utf-8") as f:
                cls.datasets.append((ano, caminho, json.load(f)))

    def test_arquivo_existe_e_eh_json_valido(self):
        if not self.datasets:
            self.skipTest(
                "Arquivos de atuacao ainda nao existem. "
                "Nada para validar nesta etapa."
            )
        for ano, caminho, dados in self.datasets:
            with self.subTest(ano=ano):
                self.assertTrue(caminho.exists(), f"Arquivo nao encontrado: {caminho}")
                self.assertIsInstance(dados, dict, f"JSON invalido em {caminho.name}")

    def test_contem_o_numero_esperado_de_vereadores(self):
        try:
            esperado = exigir_piso("vereadores", self.pisos["vereadores"])
        except PisoNaoDefinido as erro:
            self.skipTest(str(erro))
        if not self.datasets:
            self.skipTest(
                "Arquivos de atuacao ainda nao existem. "
                "Nada para validar nesta etapa."
            )
        for ano, caminho, dados in self.datasets:
            with self.subTest(ano=ano):
                vereadores = dados.get("vereadores", [])
                self.assertEqual(
                    len(vereadores),
                    esperado,
                    f"{caminho.name}: esperado exatamente {esperado} vereadores",
                )

    def test_campos_obrigatorios_de_voto(self):
        if not self.datasets:
            self.skipTest(
                "Arquivos de atuacao ainda nao existem. "
                "Nada para validar nesta etapa."
            )
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
        for ano, caminho, dados in self.datasets:
            vereadores = dados.get("vereadores", [])
            self.assertTrue(len(vereadores) > 0, f"{caminho.name}: lista de vereadores vazia")
            for i, vereador in enumerate(vereadores, 1):
                with self.subTest(ano=ano, vereador=i):
                    self.assertIn("votos", vereador, f"{ano}: vereador {i} nao possui 'votos'")
                    votos = vereador["votos"]
                    for campo in campos_voto:
                        self.assertIn(campo, votos, f"{ano}: campo 'votos.{campo}' ausente no vereador {i}")
                        self.assertIsNotNone(votos[campo], f"{ano}: campo 'votos.{campo}' nulo no vereador {i}")

    def test_campos_obrigatorios_de_presenca(self):
        if not self.datasets:
            self.skipTest(
                "Arquivos de atuacao ainda nao existem. "
                "Nada para validar nesta etapa."
            )
        campos_presenca = [
            "presencas",
            "faltas_com_justificativa",
            "faltas_sem_justificativa",
            "taxa_presenca",
            "percentual_faltas",
            "sessoes_ordinarias",
            "por_sessao",
        ]
        for ano, caminho, dados in self.datasets:
            vereadores = dados.get("vereadores", [])
            self.assertTrue(len(vereadores) > 0, f"{caminho.name}: lista de vereadores vazia")
            for i, vereador in enumerate(vereadores, 1):
                with self.subTest(ano=ano, vereador=i):
                    self.assertIn("presenca", vereador, f"{ano}: vereador {i} nao possui 'presenca'")
                    presenca = vereador["presenca"]
                    for campo in campos_presenca:
                        self.assertIn(campo, presenca, f"{ano}: campo 'presenca.{campo}' ausente no vereador {i}")
                        self.assertIsNotNone(presenca[campo], f"{ano}: campo 'presenca.{campo}' nulo no vereador {i}")


if __name__ == "__main__":
    unittest.main()
