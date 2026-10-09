"""Uma sessao nova nao quebra os testes de dado. Sem pedido ao SAPL.

Copia temporaria dos tratados para fora do repositorio, com uma sessao
a mais, e confere que as relacoes que os testes de dado protegem
continuam valendo. Nenhum total fixo aqui: tudo e calculado dos dados.
"""

from __future__ import annotations

import glob
import json
import pathlib
import shutil
import sys
import tempfile
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
for pasta in ("coletor", "dados/tratados", "tests"):
    if str(RAIZ / pasta) not in sys.path:
        sys.path.insert(0, str(RAIZ / pasta))

from config_cidade import anos_recorte, carregar_config  # noqa: E402

SESSAO_FALSA = 999999


def ler(caminho: pathlib.Path) -> dict:
    return json.loads(caminho.read_text(encoding="utf-8"))


def nova_pasta_temp() -> pathlib.Path:
    """Pasta temporaria fora do repositorio para as copias."""
    return pathlib.Path(tempfile.mkdtemp(prefix="tmp_sessao_nova_"))


class TestSessaoNovaNaoQuebra(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = carregar_config()
        cls.anos = [int(a) for a in anos_recorte(cls.cfg)]

    def test_contagem_e_presidencia_continuam_iguais(self):
        nomes = [f"contagem_votacoes_ordinarias_{a}.json" for a in self.anos]
        nomes.append("presidencia_sessoes.json")
        tmp = nova_pasta_temp()
        try:
            for nome in nomes:
                origem = RAIZ / "dados" / "brutos" / nome
                if nome == "presidencia_sessoes.json":
                    origem = RAIZ / "dados" / "tratados" / nome
                shutil.copy2(origem, tmp / nome)
            contagem = ler(tmp / f"contagem_votacoes_ordinarias_{self.anos[-1]}.json")
            contagem["sessoes"].append({"id": SESSAO_FALSA, "numero": 99})
            (tmp / f"contagem_votacoes_ordinarias_{self.anos[-1]}.json").write_text(
                json.dumps(contagem), encoding="utf-8"
            )
            presidencia = ler(tmp / "presidencia_sessoes.json")
            bloco = presidencia["por_ano"][str(self.anos[-1])]
            bloco["sessoes"].append(
                {
                    "sessao_id": SESSAO_FALSA,
                    "presidente_id_sapl": None,
                    "lacuna": True,
                }
            )
            bloco["lacunas"].append(SESSAO_FALSA)
            (tmp / "presidencia_sessoes.json").write_text(
                json.dumps(presidencia), encoding="utf-8"
            )
            total = 0
            esperado = 0
            dados = ler(tmp / "presidencia_sessoes.json")
            for ano in self.anos:
                esperadas = {
                    int(s["id"])
                    for s in ler(
                        tmp / f"contagem_votacoes_ordinarias_{ano}.json"
                    )["sessoes"]
                }
                esperado += len(esperadas)
                bloco_atual = dados["por_ano"][str(ano)]
                achadas = {s["sessao_id"] for s in bloco_atual["sessoes"]}
                self.assertEqual(esperadas, achadas)
                total += len(achadas)
            self.assertEqual(total, esperado)
            self.assertIn(SESSAO_FALSA, achadas)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_temas_continuam_cobrindo_o_lote(self):
        from test_temas_materias import e_artefato_de_tentativa, pasta_lote_materias

        lote = pasta_lote_materias()
        brutas: dict[int, dict] = {}
        for caminho in glob.glob(str(lote / "materialegislativa_ano*_p*.json")):
            if e_artefato_de_tentativa(pathlib.Path(caminho).name):
                continue
            resposta = ler(pathlib.Path(caminho))
            for materia in resposta["results"]:
                brutas[int(materia["id"])] = materia
        tratadas = ler(RAIZ / "dados" / "tratados" / "temas_materias.json")["materias"]
        self.assertEqual({item["id"] for item in tratadas}, set(brutas))
        brutas[SESSAO_FALSA] = {"id": SESSAO_FALSA}
        tratadas = list(tratadas) + [{"id": SESSAO_FALSA}]
        self.assertEqual({item["id"] for item in tratadas}, set(brutas))

    def test_soma_da_legislatura_e_conta_interna_sem_numero_fixo(self):
        leg = ler(RAIZ / "dados" / "tratados" / "atuacao_vereadores_legislatura.json")
        por_ano = {
            int(a): ler(RAIZ / "dados" / "tratados" / f"atuacao_vereadores_{a}.json")
            for a in leg["meta"]["anos_recorte"]
        }
        campos = (
            "sessoes_ordinarias",
            "presencas",
            "faltas_totais",
            "faltas_com_justificativa",
            "faltas_sem_justificativa",
            "sessoes_licenca",
            "sessoes_fora_do_mandato",
        )
        for vleg in leg.get("vereadores") or []:
            soma = {c: 0 for c in campos}
            for dados in por_ano.values():
                va = next(
                    (x for x in dados["vereadores"] if x["id_sapl"] == vleg["id_sapl"]),
                    None,
                )
                if va is None:
                    continue
                for c in campos:
                    soma[c] += va["presenca"].get(c) or 0
            for c in campos:
                self.assertEqual(
                    vleg["presenca"].get(c), soma[c],
                    msg=f"id {vleg['id_sapl']} campo {c}",
                )
            soma_votos = 0
            ids_anos = set()
            for dados in por_ano.values():
                va = next(
                    (x for x in dados["vereadores"] if x["id_sapl"] == vleg["id_sapl"]),
                    None,
                )
                if va is None:
                    continue
                soma_votos += va["votos"]["total_registros"]
                ids_anos.update(n.get("votacao_id") for n in va["votos"]["nominais"])
            self.assertEqual(vleg["votos"]["total_registros"], soma_votos)
            self.assertEqual(
                {n.get("votacao_id") for n in vleg["votos"]["nominais"]}, ids_anos
            )

    def test_sem_totais_fixos_reintroduzidos(self):
        proibidos = {
            "test_c4_vereadores.py": ["assertEqual(total, 65)"],
            "test_d3_revisao_codigo.py": [
                'p["sessoes_ordinarias"], 60',
                'p["presencas"], 36',
            ],
            "test_d051_historico_seletor.py": ['total_registros"], 98'],
            "test_temas_materias.py": [
                "lote_20260926",
                "len(ids), 401",
            ],
        }
        for nome, trechos in proibidos.items():
            texto = (RAIZ / "tests" / nome).read_text(encoding="utf-8")
            for trecho in trechos:
                self.assertNotIn(trecho, texto, f"{nome}: {trecho}")


if __name__ == "__main__":
    unittest.main()
