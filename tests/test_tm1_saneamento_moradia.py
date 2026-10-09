"""TM-1: 12 materias de saneamento em Desenvolvimento e moradia e descricao do config."""

import json
import pathlib
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
TEMA = "Desenvolvimento e moradia"
IDS_12 = {
    79: ("IND", 22, 2025),
    234: ("REQ", 36, 2025),
    220: ("REQ", 34, 2025),
    1058: ("REQ", 19, 2026),
    889: ("REQ", 17, 2026),
    69: ("IND", 12, 2025),
    605: ("REQ", 9, 2026),
    112: ("REQ", 8, 2025),
    193: ("PLEG", 7, 2025),
    213: ("VET", 3, 2025),
    350: ("IND", 12, 2026),
    1052: ("IND", 35, 2026),
}


class TestTm1SaneamentoMoradia(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = RAIZ / "dados" / "tratados" / "temas_materias.json"
        cls.materias = {m["id"]: m for m in json.loads(path.read_text(encoding="utf-8"))["materias"]}
        cls.config = json.loads((RAIZ / "config_cidade.json").read_text(encoding="utf-8"))

    def test_doze_materias_tema_e_revisao(self):
        for mid, (sigla, numero, ano) in IDS_12.items():
            with self.subTest(id=mid):
                m = self.materias[mid]
                self.assertEqual((m["sigla"], m["numero"], m["ano"]), (sigla, numero, ano))
                self.assertEqual(m["tema"], TEMA)
                self.assertTrue(m["revisada_por_humano"])

    def test_descricao_categoria_cita_esgoto(self):
        cats = self.config["categorias"]["lista"]
        dm = next(c for c in cats if c["nome"] == TEMA)
        desc = dm["descricao"].lower()
        self.assertIn("esgoto", desc)
        self.assertIn("saneamento", desc)


if __name__ == "__main__":
    unittest.main()
