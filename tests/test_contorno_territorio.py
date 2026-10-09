"""Contorno do IBGE: ponto no poligono, multipoligono e buraco, sem rede."""

import hashlib
import importlib.util
import json
import pathlib
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
TERRITORIO = RAIZ / "dados" / "territorio"


def carregar_simplificador():
    caminho = TERRITORIO / "simplificar_contorno.py"
    spec = importlib.util.spec_from_file_location("simplificar_contorno", str(caminho))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MOD = carregar_simplificador()

# Centroide informado pelo IBGE em /metadados: dentro do municipio.
LON_DENTRO = -49.6564
LAT_DENTRO = -25.9778
# Mesmo ponto deslocado cerca de 39 km para o norte: claramente fora.
LON_FORA = -49.6564
LAT_FORA = -25.6277


class TestContornoTerritorio(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = json.loads((RAIZ / "config_cidade.json").read_text(encoding="utf-8"))
        cls.codigo = str(cls.cfg["cidade"]["codigo_ibge"])
        cls.malha = json.loads(
            (TERRITORIO / f"{cls.codigo}_malha_ibge.geojson").read_text(encoding="utf-8")
        )
        cls.indice = json.loads((TERRITORIO / "indice.json").read_text(encoding="utf-8"))
        cls.simpl = json.loads(
            (TERRITORIO / f"{cls.codigo}_contorno_simplificado.json").read_text(
                encoding="utf-8"
            )
        )

    def test_codigo_ibge_no_config_com_fonte(self):
        self.assertEqual(self.cfg["cidade"]["codigo_ibge"], "4104105")
        fonte = self.cfg["cidade"].get("codigo_ibge_fonte", "")
        self.assertIn("servicodados.ibge.gov.br", fonte)
        self.assertIn("4104105", fonte)

    def test_siglas_da_votacao_no_config(self):
        bloco = self.cfg.get("votacao_popular") or {}
        self.assertIn("ATA", bloco.get("siglas_excluidas", []))
        self.assertIn("COMPR", bloco.get("siglas_excluidas", []))
        self.assertIn("EMD", bloco.get("siglas_excluidas", []))
        self.assertIn("PLEG", bloco.get("siglas_elegiveis", []))
        self.assertIn("PLEX", bloco.get("siglas_elegiveis", []))

    def test_indice_e_sha_da_malha(self):
        malha_path = TERRITORIO / f"{self.codigo}_malha_ibge.geojson"
        sha = hashlib.sha256(malha_path.read_bytes()).hexdigest()
        self.assertEqual(self.indice["sha256_malha_original"], sha)
        for chave in (
            "url_malha_pedida",
            "data_download",
            "sistema_coordenadas",
            "tolerancia_simplificacao_m",
        ):
            self.assertIn(chave, self.indice)
        self.assertIn("servicodados.ibge.gov.br", self.indice["url_malha_pedida"])

    def test_ponto_interno_dentro_e_fora_30km(self):
        self.assertTrue(MOD.dentro_do_contorno(LON_DENTRO, LAT_DENTRO, self.malha))
        self.assertFalse(MOD.dentro_do_contorno(LON_FORA, LAT_FORA, self.malha))
        self.assertTrue(MOD.dentro_do_contorno(LON_DENTRO, LAT_DENTRO, self.simpl))
        self.assertFalse(MOD.dentro_do_contorno(LON_FORA, LAT_FORA, self.simpl))

    def test_multipoligono(self):
        geo = {
            "type": "MultiPolygon",
            "coordinates": [
                [[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.0, 0.0]]],
                [[[10.0, 10.0], [11.0, 10.0], [11.0, 11.0], [10.0, 11.0], [10.0, 10.0]]],
            ],
        }
        self.assertTrue(MOD.geometria_contem(0.5, 0.5, geo))
        self.assertTrue(MOD.geometria_contem(10.5, 10.5, geo))
        self.assertFalse(MOD.geometria_contem(5.0, 5.0, geo))

    def test_buraco_nao_conta_como_dentro(self):
        externo = [[0.0, 0.0], [4.0, 0.0], [4.0, 4.0], [0.0, 4.0], [0.0, 0.0]]
        buraco = [[1.0, 1.0], [3.0, 1.0], [3.0, 3.0], [1.0, 3.0], [1.0, 1.0]]
        geo = {"type": "Polygon", "coordinates": [externo, buraco]}
        self.assertTrue(MOD.geometria_contem(0.5, 0.5, geo))
        self.assertFalse(MOD.geometria_contem(2.0, 2.0, geo))

    def test_simplificado_menor_e_desvio_limitado(self):
        props = self.simpl["features"][0]["properties"]
        self.assertLess(props["pontos_depois"], props["pontos_antes"])
        self.assertLessEqual(
            props["desvio_maximo_m"], props["tolerancia_m"] + 5.0
        )


if __name__ == "__main__":
    unittest.main()
