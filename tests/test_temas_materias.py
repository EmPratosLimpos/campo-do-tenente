import glob
import json
import pathlib
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
for pasta in ("coletor", "dados/tratados"):
    if str(RAIZ / pasta) not in sys.path:
        sys.path.insert(0, str(RAIZ / pasta))

from config_cidade import (  # noqa: E402
    carregar_config,
    endereco_sapl,
    nomes_categorias,
    rotulos_especiais_tema,
)
from gerar_temas_votacoes import (  # noqa: E402
    ARQUIVO_TEMAS,
    REGRAS,
    TEMA_NAO_SE_APLICA,
    TEMA_SEM_EMENTA,
    TEMAS_ACEITOS,
    USAR_REGRAS_POR_PALAVRA,
)

# A lista vem de config_cidade.json (D-021), nunca de uma lista fixa aqui.
TEMAS_PERMITIDOS = set(nomes_categorias())


def pasta_lote_materias() -> pathlib.Path:
    """Pasta do lote com as materias, sem data fixa: a mais recente que tem o arquivo."""
    candidatas = sorted(
        caminho
        for caminho in (RAIZ / "dados" / "brutos").glob("lote_*")
        if caminho.is_dir()
        and not caminho.name.endswith("_autoria")
        and "porsessao" not in caminho.name
        and next(caminho.glob("materialegislativa_ano*_p*.json"), None) is not None
    )
    if not candidatas:
        raise AssertionError("nenhuma pasta de lote com materias em dados/brutos")
    return candidatas[-1]


PASTA_LOTE = pasta_lote_materias()


def e_artefato_de_tentativa(nome: str) -> bool:
    """Arquivo de tentativa do coletor, nunca dado (ex.: materialegislativa_ano2026_p2_t1.json).

    Desde a AT-1-1 os artefatos novos vao para a pasta falhas, mas os
    antigos seguem no lote e nao podem entrar na leitura.
    """
    base = nome.rsplit(".json", 1)[0] if nome.endswith(".json") else nome
    return "_t" in base.rsplit("_p", 1)[-1]


def ler_bruta(caminho: str) -> dict:
    """Le um bruto exigindo JSON valido, com o nome do arquivo no erro."""
    try:
        return json.loads(pathlib.Path(caminho).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise AssertionError(f"bruto ilegivel: {pathlib.Path(caminho).name}") from exc


class TestTemasMaterias(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = carregar_config()
        dados = ler_bruta(str(ARQUIVO_TEMAS))
        cls.materias = dados["materias"]
        cls.brutas = {}
        for caminho in glob.glob(str(PASTA_LOTE / "materialegislativa_ano*_p*.json")):
            if e_artefato_de_tentativa(pathlib.Path(caminho).name):
                continue
            resposta = ler_bruta(caminho)
            for materia in resposta["results"]:
                cls.brutas[int(materia["id"])] = materia

    def test_categorias_vem_do_config(self):
        self.assertEqual(len(TEMAS_PERMITIDOS), len(self.config["categorias"]["lista"]))
        especiais = rotulos_especiais_tema(self.config)
        self.assertEqual(TEMA_NAO_SE_APLICA, especiais["nao_se_aplica"])
        self.assertEqual(TEMA_SEM_EMENTA, especiais["sem_ementa"])
        self.assertEqual(set(TEMAS_ACEITOS), TEMAS_PERMITIDOS | {TEMA_NAO_SE_APLICA, TEMA_SEM_EMENTA})
        self.assertNotIn(TEMA_NAO_SE_APLICA, TEMAS_PERMITIDOS)
        self.assertNotIn(TEMA_SEM_EMENTA, TEMAS_PERMITIDOS)

    def test_regras_desligadas_usam_nomes_do_config(self):
        self.assertEqual(set(REGRAS), TEMAS_PERMITIDOS)
        self.assertFalse(USAR_REGRAS_POR_PALAVRA)

    def test_materias_sem_repeticao_e_completas(self):
        ids = [item["id"] for item in self.materias]
        self.assertEqual(len(ids), len(self.brutas))
        self.assertGreater(len(ids), 0)
        self.assertEqual(len(set(ids)), len(ids))

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
        import re

        for item in self.materias:
            self.assertIn(item["confianca"], {"alta", "media", "baixa"}, item["id"])
            self.assertTrue(item["justificativa"].strip(), item["id"])
            if item["classificado_por"].startswith("consenso D-047"):
                pass
            else:
                self.assertIn(
                    item["classificado_por"],
                    {
                        "claude-opus-5-5",
                        "agente-e5",
                        "mantenedor (modelos sem consenso, D-047)",
                    },
                    item["id"],
                )
            self.assertIs(item["revisada_por_humano"], True)
            self.assertEqual(item["revisado_por"], "mantenedor")
            self.assertRegex(str(item["data"]), r"^\d{4}-\d{2}-\d{2}$", item["id"])

    def test_sem_travessao(self):
        texto = ARQUIVO_TEMAS.read_text(encoding="utf-8")
        for item in self.materias:
            self.assertNotIn("—", item["justificativa"])
            self.assertNotIn("–", item["justificativa"])
        self.assertNotIn("proposto por IA", texto)


if __name__ == "__main__":
    unittest.main()
