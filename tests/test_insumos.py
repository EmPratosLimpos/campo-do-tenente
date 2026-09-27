"""Testes dos insumos derivados. Nao fazem pedido ao SAPL.

As paginas de exemplo repetem o formato das respostas do lote
(results, pagination, ordem, expediente, voto). O campo ip usa o
endereco de documentacao 203.0.113.9, para o teste provar que a saida
o remove.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "coletor"))
sys.path.insert(0, str(RAIZ / "dados" / "tratados"))

from coletar_lote import plano_de_coleta  # noqa: E402
from derivar_insumos import (  # noqa: E402
    AVISO_LACUNA_2025,
    ROTULO_SEM_VOTO,
    TEXTO_NAO_VOTOU,
    escolher_prefixo,
    contem_ip,
    derivar,
)
from gerar_atuacao_vereadores_2026 import extrair_resultado  # noqa: E402

IP_FIXTURE = "203.0.113.9"


def pagina(linhas: list) -> dict:
    return {
        "pagination": {
            "links": {"next": None, "previous": None},
            "next_page": None,
            "total_entries": len(linhas),
            "total_pages": 1,
            "page": 1,
        },
        "results": linhas,
    }


def materializar(pasta: Path) -> None:
    arquivos = {
        "sessaoplenaria_ano2025_p1.json": pagina(
            [
                {
                    "id": 4,
                    "tipo": 3,
                    "numero": 17,
                    "data_inicio": "2025-05-06",
                    "__str__": "17a Sessao Ordinaria",
                    "legislatura": 1,
                },
                {
                    "id": 9,
                    "tipo": 4,
                    "numero": 1,
                    "data_inicio": "2025-12-11",
                    "__str__": "1a Sessao Extraordinaria",
                    "legislatura": 1,
                },
            ]
        ),
        "sessaoplenaria_ano2026_p1.json": pagina(
            [
                {
                    "id": 37,
                    "tipo": 3,
                    "numero": 1,
                    "data_inicio": "2026-02-10",
                    "__str__": "1a Sessao Ordinaria",
                    "legislatura": 1,
                }
            ]
        ),
        "ordemdia_p1.json": pagina(
            [
                {
                    "id": 10,
                    "sessao_plenaria": 4,
                    "materia": 9,
                    "resultado": "Aprovada por Maioria Absoluta",
                    "numero_ordem": 3,
                },
                {
                    "id": 11,
                    "sessao_plenaria": 37,
                    "materia": 244,
                    "resultado": "Aprovada por Unanimidade",
                    "numero_ordem": 1,
                },
            ]
        ),
        "expedientemateria_p1.json": pagina(
            [
                {
                    "id": 20,
                    "sessao_plenaria": 37,
                    "materia": 278,
                    "resultado": "Aprovada por Unanimidade",
                }
            ]
        ),
        "registrovotacao_p1.json": pagina(
            [
                {
                    "id": 3,
                    "ordem": 10,
                    "expediente": None,
                    "materia": 9,
                    "numero_votos_sim": 7,
                    "numero_votos_nao": 0,
                    "numero_abstencoes": 0,
                    "tipo_resultado_votacao": 3,
                    "sessao_plenaria": 999,
                    "ip": IP_FIXTURE,
                    "__str__": "Ordem exemplo - Votação: Aprovada por Maioria Absoluta",
                },
                {
                    "id": 156,
                    "ordem": 11,
                    "expediente": None,
                    "materia": 244,
                    "numero_votos_sim": 8,
                    "numero_votos_nao": 0,
                    "numero_abstencoes": 0,
                    "tipo_resultado_votacao": 2,
                    "ip": IP_FIXTURE,
                    "__str__": "Ordem exemplo - Votação: Aprovada por Unanimidade",
                },
                {
                    "id": 200,
                    "ordem": None,
                    "expediente": 20,
                    "materia": 278,
                    "numero_votos_sim": 8,
                    "numero_votos_nao": 0,
                    "numero_abstencoes": 0,
                    "tipo_resultado_votacao": 2,
                    "ip": IP_FIXTURE,
                    "__str__": "Expediente exemplo - Votação: Aprovada por Unanimidade",
                },
            ]
        ),
        "votoparlamentar_p1.json": pagina(
            [
                {
                    "id": 1,
                    "votacao": 156,
                    "parlamentar": 5,
                    "voto": "Não Votou",
                    "ordem": 11,
                    "expediente": None,
                    "ip": IP_FIXTURE,
                },
                {
                    "id": 2,
                    "votacao": 156,
                    "parlamentar": 8,
                    "voto": "Sim",
                    "ordem": 11,
                    "expediente": None,
                    "ip": IP_FIXTURE,
                },
                {
                    "id": 3,
                    "votacao": 200,
                    "parlamentar": 8,
                    "voto": "Sim",
                    "ordem": None,
                    "expediente": 20,
                    "ip": IP_FIXTURE,
                },
            ]
        ),
        "sessaoplenariapresenca_p1.json": pagina(
            [
                {"id": 1, "sessao_plenaria": 4, "parlamentar": 8, "ip": IP_FIXTURE},
                {"id": 2, "sessao_plenaria": 37, "parlamentar": 8},
                {"id": 3, "sessao_plenaria": 37, "parlamentar": 5},
            ]
        ),
        "presencaordemdia_p1.json": pagina(
            [
                {"id": 1, "sessao_plenaria": 4, "parlamentar": 8},
                {"id": 2, "sessao_plenaria": 37, "parlamentar": 5},
            ]
        ),
        "justificativaausencia_p1.json": pagina(
            [
                {
                    "id": 1,
                    "sessao_plenaria": 4,
                    "parlamentar": 1,
                    "tipo_ausencia": 1,
                }
            ]
        ),
        "integrantemesa_p1.json": pagina(
            [
                {
                    "id": 1,
                    "sessao_plenaria": 4,
                    "parlamentar": 8,
                    "cargo": 1,
                    "__str__": "Presidente - Pessoa 8",
                },
                {
                    "id": 2,
                    "sessao_plenaria": 37,
                    "parlamentar": 5,
                    "cargo": 1,
                    "__str__": "Presidente - Pessoa 5",
                },
            ]
        ),
        "parlamentar_p1.json": pagina(
            [
                {
                    "id": 8,
                    "nome_completo": "Pessoa Oito",
                    "nome_parlamentar": "Pessoa 8",
                    "__str__": "Pessoa 8",
                    "ativo": True,
                    "link_detail_backend": "/parlamentar/8",
                    "fotografia": "https://exemplo/8.jpg",
                    "ip": IP_FIXTURE,
                },
                {
                    "id": 5,
                    "nome_completo": "Pessoa Cinco",
                    "nome_parlamentar": "Pessoa 5",
                    "__str__": "Pessoa 5",
                    "ativo": True,
                    "link_detail_backend": "/parlamentar/5",
                    "fotografia": "https://exemplo/5.jpg",
                },
                {
                    "id": 1,
                    "nome_completo": "Pessoa Um",
                    "nome_parlamentar": "Pessoa 1",
                    "__str__": "Pessoa 1",
                    "ativo": True,
                    "link_detail_backend": "/parlamentar/1",
                    "fotografia": "https://exemplo/1.jpg",
                },
            ]
        ),
        "mandato_p1.json": pagina(
            [
                {
                    "id": 1,
                    "parlamentar": 8,
                    "legislatura": 1,
                    "titular": True,
                    "data_inicio_mandato": "2025-01-01",
                    "data_fim_mandato": "2028-12-31",
                    "tipo_afastamento": None,
                },
                {
                    "id": 6,
                    "parlamentar": 1,
                    "legislatura": 1,
                    "titular": False,
                    "data_inicio_mandato": "2025-01-01",
                    "data_fim_mandato": "2026-08-18",
                    "tipo_afastamento": 2,
                },
                {
                    "id": 9,
                    "parlamentar": 5,
                    "legislatura": 1,
                    "titular": True,
                    "data_inicio_mandato": "2025-01-01",
                    "data_fim_mandato": "2028-12-31",
                    "tipo_afastamento": None,
                },
            ]
        ),
        "partido_p1.json": pagina(
            [{"id": 1, "sigla": "PP", "nome": "Progressistas", "ip": IP_FIXTURE}]
        ),
        "filiacao_p1.json": pagina(
            [
                {
                    "id": 1,
                    "parlamentar": 8,
                    "partido": 1,
                    "data": "2024-01-01",
                    "data_desfiliacao": None,
                },
                {
                    "id": 2,
                    "parlamentar": 5,
                    "partido": 1,
                    "data": "2024-01-01",
                    "data_desfiliacao": None,
                },
                {
                    "id": 3,
                    "parlamentar": 1,
                    "partido": 1,
                    "data": "2024-01-01",
                    "data_desfiliacao": None,
                },
            ]
        ),
        "tipoafastamento_p1.json": pagina(
            [{"id": 2, "nome": "Tipo 2 de teste"}]
        ),
        "tipomaterialegislativa_p1.json": pagina(
            [
                {
                    "id": 6,
                    "sigla": "PLEG",
                    "descricao": "Projeto de Lei Origem do Poder Legislativo",
                },
                {"id": 9, "sigla": "IND", "descricao": "Indicacao"},
                {"id": 19, "sigla": "ATA", "descricao": "Ata Sessao"},
            ]
        ),
        "tiporesultadovotacao_p1.json": pagina(
            [
                {"id": 2, "nome": "Aprovada por Unanimidade"},
                {"id": 3, "nome": "Aprovada por Maioria Absoluta"},
            ]
        ),
        "materialegislativa_ano2025_p1.json": pagina(
            [
                {
                    "id": 9,
                    "numero": 36,
                    "ano": 2025,
                    "tipo": 9,
                    "ementa": "Indicacao de teste",
                    "texto_original": "https://exemplo/9.pdf",
                    "autores": [17],
                    "ip": IP_FIXTURE,
                }
            ]
        ),
        "materialegislativa_ano2026_p1.json": pagina(
            [
                {
                    "id": 244,
                    "numero": 1,
                    "ano": 2026,
                    "tipo": 6,
                    "ementa": "Projeto de teste",
                    "texto_original": "",
                    "autores": [8],
                    "ip": IP_FIXTURE,
                },
                {
                    "id": 278,
                    "numero": 1,
                    "ano": 2026,
                    "tipo": 19,
                    "ementa": "Ata de teste",
                    "texto_original": "",
                    "autores": [],
                },
            ]
        ),
    }
    for nome, dado in arquivos.items():
        (pasta / nome).write_text(
            json.dumps(dado, ensure_ascii=False),
            encoding="utf-8",
        )


class TestInsumos(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.lote = Path(self.tmp.name) / "lote_minimo"
        self.saida = Path(self.tmp.name) / "saida"
        self.lote.mkdir()
        materializar(self.lote)
        self.resumo = derivar(self.lote, self.saida, [2025, 2026], 3, 1)

    def tearDown(self):
        self.tmp.cleanup()

    def test_plano_nao_filtra_sessao_na_votacao(self):
        indice = {
            "parlamentares/tipoafastamento": "x",
            "parlamentares/partido": "x",
            "parlamentares/filiacao": "x",
        }
        plano = plano_de_coleta([2025, 2026], indice)
        prefixos = {item["prefixo"] for item in plano}
        self.assertIn("tipoafastamento", prefixos)
        self.assertIn("partido", prefixos)
        self.assertIn("filiacao", prefixos)
        for item in plano:
            if item["prefixo"] in ("registrovotacao", "votoparlamentar"):
                self.assertNotIn("sessao_plenaria", item["params"])

    def test_plano_sem_indice_nao_inventa_filiacao(self):
        plano = plano_de_coleta([2025, 2026], {})
        prefixos = {item["prefixo"] for item in plano}
        self.assertNotIn("filiacao", prefixos)
        self.assertNotIn("partido", prefixos)

    def test_saida_nao_carrega_ip(self):
        for caminho in self.saida.rglob("*.json"):
            dado = json.loads(caminho.read_text(encoding="utf-8"))
            self.assertFalse(contem_ip(dado), caminho.name)
            self.assertNotIn(IP_FIXTURE, caminho.read_text(encoding="utf-8"))
        for caminho in self.saida.glob("*.csv"):
            texto = caminho.read_text(encoding="utf-8-sig")
            self.assertNotIn(IP_FIXTURE, texto)
            cabecalho = texto.splitlines()[0].split(";")
            self.assertNotIn("ip", cabecalho)

    def test_votacao_sem_voto_individual_tem_rotulo(self):
        contagem = json.loads(
            (self.saida / "contagem_votacoes_ordinarias_2025.json").read_text(encoding="utf-8")
        )
        self.assertEqual(contagem["votacoes_sem_voto_individual"], 1)
        self.assertEqual(contagem["rotulo_sem_voto_individual"], ROTULO_SEM_VOTO)
        votacao = contagem["sessoes"][0]["votacoes"][0]
        self.assertEqual(votacao["id"], 3)
        self.assertEqual(votacao["voto_individual"], ROTULO_SEM_VOTO)
        self.assertEqual(votacao["n_votos_individuais"], 0)

    def test_ignora_sessao_plenaria_no_registro(self):
        pacote = json.loads(
            (self.saida / "sessao_4_registrovotacao.json").read_text(encoding="utf-8")
        )
        ids = [item["id"] for item in pacote["results"]]
        self.assertEqual(ids, [3])
        self.assertFalse((self.saida / "sessao_999_registrovotacao.json").exists())

    def test_nao_votou_permanece(self):
        pacote = json.loads(
            (self.saida / "sessao_37_votoparlamentar.json").read_text(encoding="utf-8")
        )
        votos = {item["parlamentar"]: item["voto"] for item in pacote["results"]}
        self.assertEqual(votos[5], TEXTO_NAO_VOTOU)
        self.assertNotEqual(votos[5], "Sim")
        self.assertNotEqual(votos[5], "Não")
        contagem = json.loads(
            (self.saida / "contagem_votacoes_ordinarias_2026.json").read_text(encoding="utf-8")
        )
        self.assertEqual(contagem["n_nao_votou"], 1)
        self.assertEqual(contagem["n_votacoes_com_exatamente_um_nao_votou"], 1)
        self.assertEqual(contagem["total_votacoes"], 2)

    def test_lacuna_ordinarias_1_a_16_de_2025(self):
        contagem = json.loads(
            (self.saida / "contagem_votacoes_ordinarias_2025.json").read_text(encoding="utf-8")
        )
        lacuna = contagem["lacuna_sessoes_ordinarias"]
        self.assertEqual(lacuna["numeros_ausentes_no_sapl"], list(range(1, 17)))
        self.assertEqual(lacuna["aviso"], AVISO_LACUNA_2025)
        self.assertEqual(lacuna["primeira_ordinaria_no_sapl"]["numero"], 17)
        self.assertEqual(lacuna["primeira_ordinaria_no_sapl"]["data_inicio"], "2025-05-06")
        self.assertEqual(contagem["total_sessoes_ordinarias"], 1)

    def test_mandato_por_id_com_datas(self):
        dado = json.loads(
            (self.saida / "mandatos_legislatura_atual.json").read_text(encoding="utf-8")
        )
        por_id = {item["parlamentar_id"]: item for item in dado["mandatos"]}
        self.assertEqual(set(por_id), {8, 5, 1})
        self.assertEqual(por_id[1]["data_inicio_mandato"], "2025-01-01")
        self.assertEqual(por_id[1]["data_fim_mandato"], "2026-08-18")
        self.assertEqual(por_id[1]["tipo_afastamento_nome"], "Tipo 2 de teste")
        cadastro = json.loads(
            (self.saida / "sessao_cadastro_parlamentares.json").read_text(encoding="utf-8")
        )
        self.assertEqual(set(cadastro), {"1", "5", "8"})
        self.assertEqual(cadastro["1"]["id"], 1)

    def test_escolhe_lista_por_id_quando_ela_e_maior(self):
        self.assertEqual(escolher_prefixo(self.lote, "ordemdia"), "ordemdia")
        (self.lote / "ordemdia_por_id_p1.json").write_text("{}", encoding="utf-8")
        self.assertEqual(escolher_prefixo(self.lote, "ordemdia"), "ordemdia")
        pagina_maior = {
            "pagination": {"total_entries": 3, "total_pages": 1, "links": {"next": None}},
            "results": [{"id": 1}, {"id": 2}, {"id": 3}],
        }
        (self.lote / "ordemdia_por_id_p1.json").write_text(
            json.dumps(pagina_maior),
            encoding="utf-8",
        )
        self.assertEqual(escolher_prefixo(self.lote, "ordemdia"), "ordemdia_por_id")

    def test_frase_de_resultado_deste_sapl(self):
        self.assertEqual(
            extrair_resultado("trecho - Votação: Aprovada por Unanimidade"),
            "UNANIMIDADE",
        )
        self.assertEqual(
            extrair_resultado("trecho - Votação: Aprovada por Maioria Absoluta"),
            "MAIORIA ABSOLUTA",
        )
        self.assertEqual(extrair_resultado("trecho - Votação: Rejeitada"), "REJEITADO")
        self.assertIsNone(extrair_resultado("trecho - Votação: Pedido de Vistas"))


if __name__ == "__main__":
    unittest.main()
