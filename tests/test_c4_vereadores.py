import json
import pathlib
import sys
import unittest

DIR_RAIZ = pathlib.Path(__file__).resolve().parent.parent
DIR_BRUTOS = DIR_RAIZ / "dados" / "brutos"
DIR_TRATADOS = DIR_RAIZ / "dados" / "tratados"
if str(DIR_RAIZ / "coletor") not in sys.path:
    sys.path.insert(0, str(DIR_RAIZ / "coletor"))

from config_cidade import (  # noqa: E402
    PisoNaoDefinido,
    anos_recorte,
    carregar_config,
    endereco_sapl,
    exigir_piso,
    pisos_sanidade,
)


def ler(caminho: pathlib.Path):
    return json.loads(caminho.read_text(encoding="utf-8"))


def contem_ip(valor) -> bool:
    if isinstance(valor, dict):
        return "ip" in valor or any(contem_ip(v) for v in valor.values())
    if isinstance(valor, list):
        return any(contem_ip(v) for v in valor)
    return False


class TestPisosPorAno(unittest.TestCase):
    def setUp(self):
        self.cfg = carregar_config()

    def test_pisos_de_2025(self):
        self.assertEqual(
            pisos_sanidade(2025, self.cfg),
            {
                "vereadores": 9,
                "sessoes_ordinarias": 32,
                "projetos_lei_legislativo_e_executivo": 44,
            },
        )

    def test_pisos_de_2026(self):
        self.assertEqual(
            pisos_sanidade(2026, self.cfg),
            {
                "vereadores": 10,
                "sessoes_ordinarias": 33,
                "projetos_lei_legislativo_e_executivo": 18,
            },
        )

    def test_chave_antiga_de_pll_nao_existe(self):
        texto = (DIR_RAIZ / "config_cidade.json").read_text(encoding="utf-8")
        self.assertNotIn('"plls"', texto)

    def test_ano_sem_piso_para_o_script(self):
        pisos = pisos_sanidade(2099, self.cfg)
        for chave, valor in pisos.items():
            self.assertIsNone(valor)
            with self.assertRaises(PisoNaoDefinido):
                exigir_piso(chave, valor, 2099)

    def test_piso_nulo_no_config_para_o_script(self):
        cfg = json.loads(json.dumps(self.cfg))
        cfg["pisos_sanidade"]["por_ano"]["2026"]["vereadores"] = None
        with self.assertRaises(PisoNaoDefinido):
            exigir_piso("vereadores", pisos_sanidade(2026, cfg)["vereadores"], 2026)


class TestTabelaVereadores(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = carregar_config()
        cls.dados = ler(DIR_TRATADOS / "vereadores.json")
        cls.vereadores = cls.dados["vereadores"]

    def test_dez_vereadores_na_legislatura(self):
        self.assertEqual(len(self.vereadores), 10)
        ids = [v["id_sapl"] for v in self.vereadores]
        self.assertEqual(len(ids), len(set(ids)))
        mandatos = ler(DIR_BRUTOS / "mandatos_legislatura_atual.json")["mandatos"]
        self.assertEqual(set(ids), {m["parlamentar_id"] for m in mandatos})

    def test_vereadores_por_ano_batem_com_o_piso(self):
        for ano in anos_recorte(self.cfg):
            with self.subTest(ano=ano):
                do_ano = [v for v in self.vereadores if ano in v["anos_com_mandato"]]
                self.assertEqual(len(do_ano), pisos_sanidade(ano, self.cfg)["vereadores"])

    def test_campos_de_cada_vereador(self):
        base = endereco_sapl(self.cfg)
        for v in self.vereadores:
            with self.subTest(id_sapl=v["id_sapl"]):
                self.assertTrue(v["nome_parlamentar"])
                self.assertTrue(v["partido_sigla"])
                self.assertTrue(v["mandatos"])
                for m in v["mandatos"]:
                    self.assertIn(m["condicao"], ("titular", "suplente"))
                    self.assertTrue(m["data_inicio_mandato"])
                    self.assertTrue(m["data_fim_mandato"])
                self.assertTrue(v["link_sapl"].startswith(base + "/parlamentar/"))

    def test_afastamento_como_registrado_no_sapl(self):
        com_afastamento = [
            (v["id_sapl"], a)
            for v in self.vereadores
            for a in v["afastamento_registro_oficial"]
        ]
        self.assertEqual(len(com_afastamento), 1)
        _pid, afastamento = com_afastamento[0]
        self.assertEqual(afastamento["mandato_id"], 6)
        self.assertEqual(afastamento["tipo_afastamento_nome"], "Cassação de mandato")

    def test_sem_campo_ip(self):
        self.assertFalse(contem_ip(self.dados))


class TestPresidenciaPorSessao(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = carregar_config()
        cls.dados = ler(DIR_TRATADOS / "presidencia_sessoes.json")
        cls.ids_tabela = {
            v["id_sapl"] for v in ler(DIR_TRATADOS / "vereadores.json")["vereadores"]
        }

    def test_todas_as_ordinarias_tem_presidente_ou_lacuna(self):
        total = 0
        esperado = 0
        for ano in anos_recorte(self.cfg):
            contagem = ler(DIR_BRUTOS / f"contagem_votacoes_ordinarias_{ano}.json")
            esperadas = {int(s["id"]) for s in contagem["sessoes"]}
            esperado += len(esperadas)
            bloco = self.dados["por_ano"][str(ano)]
            achadas = {s["sessao_id"] for s in bloco["sessoes"]}
            self.assertEqual(esperadas, achadas)
            total += len(achadas)
            for s in bloco["sessoes"]:
                with self.subTest(sessao=s["sessao_id"]):
                    if s["presidente_id_sapl"] is None:
                        self.assertTrue(s["lacuna"])
                        self.assertIn(s["sessao_id"], bloco["lacunas"])
                    else:
                        self.assertIsNone(s["lacuna"])
                        self.assertIn(s["presidente_id_sapl"], self.ids_tabela)
        self.assertEqual(total, esperado)
        self.assertGreaterEqual(total, 1)

    def test_presidente_confere_com_a_mesa_da_sessao(self):
        for bloco in self.dados["por_ano"].values():
            for s in bloco["sessoes"]:
                if s["presidente_id_sapl"] is None:
                    continue
                mesa = ler(DIR_BRUTOS / f"sessao_{s['sessao_id']}_integrantemesa.json")["results"]
                linha = [m for m in mesa if m["id"] == s["integrante_mesa_id"]]
                self.assertEqual(len(linha), 1)
                self.assertEqual(linha[0]["parlamentar"], s["presidente_id_sapl"])
                self.assertIn(linha[0]["cargo"], self.dados["meta"]["ids_cargo_presidente"])


class TestAutoriaMaterias(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = carregar_config()
        cls.dados = ler(DIR_TRATADOS / "autoria_materias.json")
        cls.ids_tabela = {
            v["id_sapl"] for v in ler(DIR_TRATADOS / "vereadores.json")["vereadores"]
        }

    def materias_brutas(self, ano: int) -> list:
        linhas = []
        arquivos = self.dados["meta"]["por_ano"][str(ano)]["arquivos_materias"]
        for rel in arquivos:
            linhas.extend(ler(DIR_RAIZ / rel)["results"])
        return linhas

    def test_nenhuma_materia_perdida(self):
        por_id = {m["materia_id"]: m for m in self.dados["materias"]}
        self.assertEqual(len(por_id), len(self.dados["materias"]))
        for ano in anos_recorte(self.cfg):
            with self.subTest(ano=ano):
                brutas = self.materias_brutas(ano)
                meta = self.dados["meta"]["por_ano"][str(ano)]
                self.assertEqual(len({m["id"] for m in brutas}), meta["total_entries_api"])
                for bruta in brutas:
                    saida = por_id.get(bruta["id"])
                    self.assertIsNotNone(saida, f"materia {bruta['id']} perdida")
                    self.assertEqual(
                        [a["autor_id"] for a in saida["autorias"]], bruta["autores"]
                    )
                    if not bruta["autores"]:
                        self.assertTrue(saida["autoria_rotulo"])

    def test_autor_vereador_ligado_ao_id(self):
        for materia in self.dados["materias"]:
            for autoria in materia["autorias"]:
                if autoria["tipo_autor_id"] == 2:
                    self.assertIn(autoria["parlamentar_id_sapl"], self.ids_tabela)
                else:
                    self.assertIsNone(autoria["parlamentar_id_sapl"])
                    self.assertTrue(autoria["tipo_autor"] or autoria["lacuna"])

    def test_sem_campo_ip(self):
        self.assertFalse(contem_ip(self.dados))


if __name__ == "__main__":
    unittest.main()
