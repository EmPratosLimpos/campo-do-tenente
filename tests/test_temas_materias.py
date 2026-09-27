import glob
import json
import pathlib
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
for pasta in ("coletor", "dados/tratados"):
    if str(RAIZ / pasta) not in sys.path:
        sys.path.insert(0, str(RAIZ / pasta))

from config_cidade import carregar_config, endereco_sapl  # noqa: E402
from gerar_temas_votacoes import (  # noqa: E402
    ARQUIVO_TEMAS,
    REGRAS,
    TEMA_NAO_SE_APLICA,
    TEMA_SEM_EMENTA,
    USAR_REGRAS_POR_PALAVRA,
)

TEMAS_PERMITIDOS = {
    "Homenagens, nomes e datas",
    "Defesa Civil",
    "Saúde",
    "Educação",
    "Segurança pública",
    "Assistência social e direitos",
    "Cultura, esporte e lazer",
    "Meio ambiente e animais",
    "Iluminação e serviços urbanos",
    "Ruas, trânsito e transporte",
    "Desenvolvimento, moradia e agricultura",
    "Administração e finanças",
}
PASTA_LOTE = RAIZ / "dados" / "brutos" / "lote_20260926"


class TestTemasMaterias(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = carregar_config()
        dados = json.loads(ARQUIVO_TEMAS.read_text(encoding="utf-8"))
        cls.materias = dados["materias"]
        cls.brutas = {}
        for caminho in glob.glob(str(PASTA_LOTE / "materialegislativa_ano*_p*.json")):
            resposta = json.loads(pathlib.Path(caminho).read_text(encoding="utf-8"))
            for materia in resposta["results"]:
                cls.brutas[int(materia["id"])] = materia

    def test_lista_de_temas_igual_as_regras(self):
        self.assertEqual(set(REGRAS), TEMAS_PERMITIDOS)
        self.assertFalse(USAR_REGRAS_POR_PALAVRA)

    def test_401_materias_sem_repeticao(self):
        ids = [item["id"] for item in self.materias]
        self.assertEqual(len(ids), 401)
        self.assertEqual(len(set(ids)), 401)

    def test_cobre_todas_as_materias_do_lote(self):
        self.assertEqual({item["id"] for item in self.materias}, set(self.brutas))

    def test_ano_numero_do_lote(self):
        for item in self.materias:
            bruta = self.brutas[item["id"]]
            self.assertEqual(item["ano"], bruta["ano"], item["id"])
            self.assertEqual(item["numero"], bruta["numero"], item["id"])
            self.assertIn(item["ano"], self.config["recorte"]["anos"])

    def test_tema_dentro_da_lista(self):
        aceitos = TEMAS_PERMITIDOS | {TEMA_NAO_SE_APLICA, TEMA_SEM_EMENTA}
        for item in self.materias:
            self.assertIn(item["tema"], aceitos, item["id"])

    def test_ata_e_oficio_nao_se_aplica(self):
        for item in self.materias:
            ementa = (self.brutas[item["id"]].get("ementa") or "").strip()
            if not ementa:
                self.assertEqual(item["tema"], TEMA_SEM_EMENTA, item["id"])
            elif item["sigla"] in {"ATA", "OFEX"}:
                self.assertEqual(item["tema"], TEMA_NAO_SE_APLICA, item["id"])
            else:
                self.assertIn(item["tema"], TEMAS_PERMITIDOS, item["id"])

    def test_link_oficial(self):
        base = endereco_sapl(self.config)
        for item in self.materias:
            self.assertEqual(item["link"], f"{base}/materia/{item['id']}")
            self.assertTrue(item["link"].startswith("https://"))

    def test_campos_de_classificacao(self):
        for item in self.materias:
            self.assertIn(item["confianca"], {"alta", "media", "baixa"}, item["id"])
            self.assertTrue(item["justificativa"].strip(), item["id"])
            self.assertEqual(item["classificado_por"], "claude-opus-5-5")
            self.assertIs(item["revisada_por_humano"], False)

    def test_sem_travessao(self):
        texto = ARQUIVO_TEMAS.read_text(encoding="utf-8")
        for item in self.materias:
            self.assertNotIn("—", item["justificativa"])
            self.assertNotIn("–", item["justificativa"])
        self.assertNotIn("proposto por IA", texto)


if __name__ == "__main__":
    unittest.main()
