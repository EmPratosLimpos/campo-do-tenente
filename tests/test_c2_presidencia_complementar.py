"""C2: presidencia pela abertura do expediente quando a mesa esta vazia.

Sem rede. Todo o ambiente da mesa e do complemento e sintetico, em pasta
temporaria. A mesa do SAPL sempre vence (D-079).
"""

from __future__ import annotations

import contextlib
import io
import json
import pathlib
import shutil
import sys
import tempfile
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
for pasta in ("coletor", "dados/tratados"):
    if str(RAIZ / pasta) not in sys.path:
        sys.path.insert(0, str(RAIZ / pasta))

from config_cidade import carregar_config, endereco_sapl  # noqa: E402
import gerar_presidencia_sessoes as gps  # noqa: E402

BASE = endereco_sapl(carregar_config())
CARGO_PRESIDENTE = 1
NOMES = {3: "Cleiton Costa", 5: "Rafael Ventura"}
TRECHO = "sob a Presidência do Excelentíssimo Vereador Rafael de Jesus Ventura"
LINK = f"{BASE}/sessao/277/expediente"


def escrever(caminho: pathlib.Path, dados: dict) -> None:
    caminho.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")


def entrada_complemento(**troca) -> dict:
    item = {
        "sessao_id": 277,
        "presidente_id_sapl": 5,
        "fonte": "expediente",
        "link_fonte": LINK,
        "trecho": TRECHO,
        "conferido_em": "2026-10-23",
    }
    item.update(troca)
    return item


class TestComplementoPresidencia(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="tmp_c2_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        for nome, valor in (("DIR_RAIZ", self.tmp), ("DIR_BRUTOS", self.tmp)):
            original = getattr(gps, nome)
            setattr(gps, nome, valor)
            self.addCleanup(setattr, gps, nome, original)

    def mesa(self, sessao_id: int, linhas: list[dict]) -> None:
        escrever(
            self.tmp / f"sessao_{sessao_id}_integrantemesa.json",
            {"results": linhas},
        )

    def complemento(self, *itens: dict) -> pathlib.Path:
        caminho = self.tmp / "presidencia_complementar.json"
        escrever(caminho, {"nota": "teste", "sessoes": list(itens)})
        return caminho

    def carregar(self, caminho: pathlib.Path) -> dict[int, dict]:
        return gps.carregar_complementos(NOMES, caminho=caminho)

    def resolver(self, sessao_id: int, complementos: dict[int, dict]) -> dict:
        return gps.presidencia_da_sessao(
            {"id": sessao_id, "numero": 37, "data": "2026-10-20"},
            {CARGO_PRESIDENTE},
            NOMES,
            complementos,
        )

    def test_mesa_vazia_usa_o_expediente(self):
        self.mesa(277, [])
        complementos = self.carregar(self.complemento(entrada_complemento()))
        saida = self.resolver(277, complementos)
        self.assertEqual(saida["presidente_id_sapl"], 5)
        self.assertEqual(saida["presidente_nome_parlamentar"], "Rafael Ventura")
        self.assertIsNone(saida["integrante_mesa_id"])
        self.assertIsNone(saida["lacuna"])
        self.assertEqual(saida["origem_presidencia"], "expediente")
        self.assertEqual(saida["link_fonte"], LINK)
        self.assertEqual(saida["trecho"], TRECHO)

    def test_mesa_com_presidente_vence_e_avisa(self):
        self.mesa(277, [{"id": 41, "cargo": CARGO_PRESIDENTE, "parlamentar": 3}])
        complementos = self.carregar(self.complemento(entrada_complemento()))
        saida_stdout = io.StringIO()
        with contextlib.redirect_stdout(saida_stdout):
            saida = self.resolver(277, complementos)
        self.assertEqual(saida["presidente_id_sapl"], 3)
        self.assertEqual(saida["integrante_mesa_id"], 41)
        self.assertIsNone(saida["lacuna"])
        self.assertEqual(saida["origem_presidencia"], "mesa")
        self.assertNotIn("link_fonte", saida)
        texto = saida_stdout.getvalue()
        self.assertIn("AVISO", texto)
        self.assertIn("sessao 277", texto)
        self.assertIn("presidente 3", texto)
        self.assertIn("aponta 5", texto)

    def test_mesa_ausente_mantem_lacuna(self):
        complementos = self.carregar(self.complemento(entrada_complemento()))
        saida = self.resolver(277, complementos)
        self.assertIsNone(saida["presidente_id_sapl"])
        self.assertIn("ausente", saida["lacuna"])
        self.assertIsNone(saida["origem_presidencia"])

    def test_mais_de_um_presidente_ignora_complemento(self):
        self.mesa(
            277,
            [
                {"id": 41, "cargo": CARGO_PRESIDENTE, "parlamentar": 3},
                {"id": 42, "cargo": CARGO_PRESIDENTE, "parlamentar": 5},
            ],
        )
        complementos = self.carregar(self.complemento(entrada_complemento()))
        saida = self.resolver(277, complementos)
        self.assertIsNone(saida["presidente_id_sapl"])
        self.assertIn("mais de um", saida["lacuna"])
        self.assertIsNone(saida["origem_presidencia"])

    def test_complemento_ausente_mantem_comportamento(self):
        caminho = self.tmp / "presidencia_complementar.json"
        self.assertEqual(self.carregar(caminho), {})
        self.mesa(277, [])
        saida = self.resolver(277, self.carregar(caminho))
        self.assertIsNone(saida["presidente_id_sapl"])
        self.assertEqual(saida["lacuna"], gps.ROTULO_LACUNA)
        self.assertIsNone(saida["origem_presidencia"])

    def test_link_fora_do_sapl_e_erro(self):
        caminho = self.complemento(
            entrada_complemento(link_fonte="https://example.com/sessao/277")
        )
        with self.assertRaises(SystemExit) as erro:
            self.carregar(caminho)
        self.assertIn("link_fonte", str(erro.exception))

    def test_presidente_inexistente_e_erro(self):
        caminho = self.complemento(entrada_complemento(presidente_id_sapl=999))
        with self.assertRaises(SystemExit) as erro:
            self.carregar(caminho)
        self.assertIn("999", str(erro.exception))

    def test_arquivo_real_valida_e_tem_a_sessao_277(self):
        caminho = RAIZ / "dados" / "tratados" / "presidencia_complementar.json"
        complementos = gps.carregar_complementos(gps.nomes_da_tabela(), caminho=caminho)
        self.assertIn(277, complementos)
        self.assertEqual(complementos[277]["presidente_id_sapl"], 5)
        self.assertEqual(complementos[277]["origem_presidencia"], "expediente")
        self.assertEqual(complementos[277]["link_fonte"], LINK)
        self.assertEqual(complementos[277]["trecho"], TRECHO)

    def test_gerar_marca_origem_e_conta_pelo_expediente(self):
        (self.tmp / "lote_teste").mkdir()
        escrever(
            self.tmp / "lote_teste" / "cargomesa_p1.json",
            {"results": [{"id": CARGO_PRESIDENTE, "descricao": "Presidente"}]},
        )
        escrever(
            self.tmp / "contagem_votacoes_ordinarias_2025.json",
            {
                "sessoes": [
                    {"id": 100, "numero": 1, "data": "2025-02-04"},
                    {"id": 101, "numero": 2, "data": "2025-02-11"},
                ]
            },
        )
        escrever(
            self.tmp / "contagem_votacoes_ordinarias_2026.json",
            {"sessoes": [{"id": 277, "numero": 37, "data": "2026-10-20"}]},
        )
        self.mesa(100, [])
        self.mesa(
            101, [{"id": 43, "cargo": CARGO_PRESIDENTE, "parlamentar": 3}]
        )
        self.mesa(277, [])
        caminho_complemento = self.complemento(entrada_complemento())
        original = gps.ARQUIVO_COMPLEMENTO
        gps.ARQUIVO_COMPLEMENTO = caminho_complemento
        self.addCleanup(setattr, gps, "ARQUIVO_COMPLEMENTO", original)
        payload = gps.gerar()
        self.assertTrue(payload["meta"]["arquivo_complemento"].endswith(
            "presidencia_complementar.json"
        ))
        self.assertIn("complemento", payload["meta"]["regra"])
        self.assertIn("D-079", payload["meta"]["regra"])
        bloco_2025 = payload["por_ano"]["2025"]
        bloco_2026 = payload["por_ano"]["2026"]
        self.assertEqual(bloco_2025["n_pelo_expediente"], 0)
        self.assertEqual(bloco_2026["n_pelo_expediente"], 1)
        self.assertEqual(bloco_2026["n_com_presidente"], 1)
        por_id = {i["sessao_id"]: i for i in bloco_2026["sessoes"]}
        self.assertEqual(por_id[277]["origem_presidencia"], "expediente")
        self.assertIsNone(por_id[277]["lacuna"])
        por_id_2025 = {i["sessao_id"]: i for i in bloco_2025["sessoes"]}
        self.assertEqual(por_id_2025[100]["origem_presidencia"], None)
        self.assertIsNotNone(por_id_2025[100]["lacuna"])
        self.assertEqual(por_id_2025[101]["origem_presidencia"], "mesa")


if __name__ == "__main__":
    unittest.main()
