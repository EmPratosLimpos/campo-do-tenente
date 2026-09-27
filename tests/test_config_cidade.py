import json
import pathlib
import sys
import unittest

PASTA_COLETOR = pathlib.Path(__file__).resolve().parent.parent / "coletor"
if str(PASTA_COLETOR) not in sys.path:
    sys.path.insert(0, str(PASTA_COLETOR))


CAMPOS_OBRIGATORIOS = {
    "cidade": ("nome", "uf"),
    "sapl": (
        "endereco_base",
        "id_tipo_sessao_ordinaria",
        "id_legislatura_atual",
    ),
    "recorte": ("anos",),
    "vereadores": ("numero_esperado",),
    "pisos_sanidade": ("por_ano",),
    "categorias": ("lista", "rotulos_especiais"),
}


class TestConfigCidade(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.caminho = pathlib.Path(__file__).resolve().parent.parent / "config_cidade.json"
        with cls.caminho.open(encoding="utf-8") as arquivo:
            cls.config = json.load(arquivo)

    def test_arquivo_existe_e_eh_json_objeto(self):
        self.assertTrue(self.caminho.exists(), "config_cidade.json ausente na raiz")
        self.assertIsInstance(self.config, dict)

    def test_campos_obrigatorios_existem(self):
        for bloco, campos in CAMPOS_OBRIGATORIOS.items():
            self.assertIn(bloco, self.config, f"Bloco obrigatorio ausente: {bloco}")
            self.assertIsInstance(self.config[bloco], dict, f"Bloco {bloco} deve ser objeto")
            for campo in campos:
                self.assertIn(
                    campo,
                    self.config[bloco],
                    f"Campo obrigatorio ausente: {bloco}.{campo}",
                )

    def test_fatos_conhecidos_da_cidade(self):
        self.assertEqual(self.config["cidade"]["nome"], "Campo do Tenente")
        self.assertEqual(self.config["cidade"]["uf"], "PR")
        self.assertEqual(
            self.config["sapl"]["endereco_base"],
            "https://sapl.campodotenente.pr.leg.br",
        )
        self.assertEqual(self.config["sapl"]["id_tipo_sessao_ordinaria"], 3)
        self.assertEqual(self.config["sapl"]["id_legislatura_atual"], 1)
        self.assertEqual(self.config["recorte"]["anos"], [2025, 2026])

    def test_valores_desconhecidos_ficam_nulos(self):
        self.assertIsNone(self.config["vereadores"]["numero_esperado"])

    def test_anos_do_recorte_sao_inteiros(self):
        anos = self.config["recorte"]["anos"]
        self.assertIsInstance(anos, list)
        self.assertGreaterEqual(len(anos), 1)
        for ano in anos:
            self.assertIsInstance(ano, int)

    def test_categorias_da_cidade(self):
        from config_cidade import categorias, rotulos_especiais_tema

        lista = categorias(self.config)
        self.assertEqual(len(lista), 13, "D-021 aprovou 13 categorias")
        nomes = [item["nome"] for item in lista]
        self.assertEqual(len(set(nomes)), len(nomes))
        for item in lista:
            self.assertTrue(item["descricao"])
        especiais = rotulos_especiais_tema(self.config)
        self.assertEqual(set(especiais), {"nao_se_aplica", "sem_ementa"})
        self.assertFalse(set(especiais.values()) & set(nomes))


if __name__ == "__main__":
    unittest.main()
