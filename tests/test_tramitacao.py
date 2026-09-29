"""Testes da tramitacao e da consolidacao C9. Nao fazem pedido ao SAPL."""

from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "dados" / "tratados"))
sys.path.insert(0, str(RAIZ / "coletor"))

from gerar_proposicoes_executivo import (  # noqa: E402
    ROTULO_SEM_TRAMITACAO,
    ROTULO_SEM_VOTACAO,
    autores_vereadores,
    decodificar_status,
    escolher_ultima,
    escolher_votacao,
    montar_ultima_tramitacao,
    montar_votacao,
)
from config_cidade import (  # noqa: E402
    anos_recorte,
    carregar_config,
    piso_status_decodificados,
    tipos_executivo,
    tipos_proposicoes,
    tipos_tramitacao_coleta,
)

TRATADOS = RAIZ / "dados" / "tratados"


def tem_chave_ip(obj) -> bool:
    if isinstance(obj, dict):
        if "ip" in obj:
            return True
        return any(tem_chave_ip(valor) for valor in obj.values())
    if isinstance(obj, list):
        return any(tem_chave_ip(valor) for valor in obj)
    return False


class TestUltimaTramitacao(unittest.TestCase):
    def test_maior_data_vence(self):
        itens = [
            {"id": 1, "data_tramitacao": "2025-08-05"},
            {"id": 2, "data_tramitacao": "2025-08-01"},
        ]
        self.assertEqual(escolher_ultima(itens)["id"], 1)

    def test_empate_de_data_desempata_pelo_maior_id(self):
        itens = [
            {"id": 276, "data_tramitacao": "2025-08-05"},
            {"id": 315, "data_tramitacao": "2025-08-05"},
            {"id": 277, "data_tramitacao": "2025-08-05"},
        ]
        self.assertEqual(escolher_ultima(itens)["id"], 315)

    def test_lista_vazia_da_none(self):
        self.assertIsNone(escolher_ultima([]))


class TestDecodificacao(unittest.TestCase):
    def test_indicador_r_e_em_curso(self):
        tabela = {5: {"sigla": "AGPARECER", "descricao": "Aguardando parecer", "indicador": "R"}}
        saida = decodificar_status(5, tabela)
        self.assertEqual(saida["situacao"], "em curso")
        self.assertEqual(saida["sigla"], "AGPARECER")

    def test_indicador_f_e_fim(self):
        tabela = {13: {"sigla": "APROVADA", "descricao": "Proposicao aprovada", "indicador": "F"}}
        saida = decodificar_status(13, tabela)
        self.assertEqual(saida["situacao"], "fim")

    def test_status_desconhecido_nao_inventa(self):
        saida = decodificar_status(999, {})
        self.assertEqual(saida["situacao"], "nao informado no SAPL")
        self.assertIsNone(saida["sigla"])

    def test_status_nulo_nao_inventa(self):
        saida = decodificar_status(None, {})
        self.assertEqual(saida["situacao"], "nao informado no SAPL")


class TestRotulosAusencia(unittest.TestCase):
    def test_sem_tramitacao_tem_rotulo(self):
        ultima, rotulo = montar_ultima_tramitacao(1, {}, {}, {})
        self.assertIsNone(ultima)
        self.assertEqual(rotulo, ROTULO_SEM_TRAMITACAO)

    def test_sem_votacao_tem_rotulo(self):
        votacao, rotulo = montar_votacao(1, {})
        self.assertIsNone(votacao)
        self.assertEqual(rotulo, ROTULO_SEM_VOTACAO)

    def test_votacao_escolhe_a_mais_recente(self):
        registros = [
            {"id": 1, "data_sessao": "2025-05-13", "data_hora": "2025-05-13T10:00:00"},
            {"id": 2, "data_sessao": "2025-06-17", "data_hora": "2025-06-17T10:00:00"},
        ]
        self.assertEqual(escolher_votacao(registros)["id"], 2)


class TestAutoria(unittest.TestCase):
    def test_so_parlamentar_entra_na_lista_de_vereadores(self):
        autoria = {
            10: [
                {"parlamentar_id_sapl": 5, "nome_no_sapl": "Rafael Ventura", "primeiro_autor": True},
                {"parlamentar_id_sapl": None, "nome_no_sapl": "Prefeito", "primeiro_autor": False},
            ]
        }
        vereadores = {5: {"nome_parlamentar": "Rafael Ventura"}}
        saida = autores_vereadores(10, autoria, vereadores)
        self.assertEqual(len(saida), 1)
        self.assertEqual(saida[0]["parlamentar_id_sapl"], 5)

    def test_materia_sem_autoria_da_lista_vazia(self):
        self.assertEqual(autores_vereadores(999, {}, {}), [])


class TestConfigSemSiglaFixa(unittest.TestCase):
    def test_tipos_vem_do_config(self):
        cfg = carregar_config()
        coleta = tipos_tramitacao_coleta(cfg)
        self.assertEqual(sorted(coleta), ["IND", "MOC", "PLEX", "REQ", "VET"])
        prop = tipos_proposicoes(cfg)
        self.assertIn("REQ", prop)
        self.assertIn("IND", prop)
        exe = tipos_executivo(cfg)
        self.assertIn("PLEX", exe)
        self.assertIn("VET", exe)

    def test_piso_de_status_definido(self):
        cfg = carregar_config()
        self.assertGreaterEqual(piso_status_decodificados(cfg), 1)


class TestArquivosGerados(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = carregar_config()
        cls.anos = anos_recorte(cls.config)

    def _carregar(self, nome: str) -> dict:
        caminho = TRATADOS / nome
        self.assertTrue(caminho.exists(), f"Arquivo nao encontrado: {nome}")
        bruto = caminho.read_bytes()
        self.assertNotIn(b"\r", bruto, f"{nome} nao esta em LF")
        return json.loads(bruto.decode("utf-8"))

    def test_proposicoes_e_executivo_por_ano_e_legislatura(self):
        for nome in (
            "proposicoes_2025.json",
            "proposicoes_2026.json",
            "proposicoes_legislatura.json",
            "executivo_2025.json",
            "executivo_2026.json",
            "executivo_legislatura.json",
        ):
            with self.subTest(arquivo=nome):
                dados = self._carregar(nome)
                for chave in ("meta", "sessao", "mes", "todo"):
                    self.assertIn(chave, dados, nome)
                self.assertFalse(tem_chave_ip(dados), nome)
                for item in dados["todo"]:
                    self.assertTrue(item.get("link_sapl"), nome)
                    self.assertIn("ultima_tramitacao_rotulo", item, nome)
                    self.assertIn("votacao_rotulo", item, nome)
                    if item["ultima_tramitacao"] is None:
                        self.assertEqual(item["ultima_tramitacao_rotulo"], ROTULO_SEM_TRAMITACAO)
                    if item["votacao"] is None:
                        self.assertEqual(item["votacao_rotulo"], ROTULO_SEM_VOTACAO)

    def test_proposicoes_trazem_tema_e_autores(self):
        dados = self._carregar("proposicoes_legislatura.json")
        com_tema = [item for item in dados["todo"] if item.get("tema")]
        self.assertTrue(com_tema, "nenhum item com tema")
        com_autor = [item for item in dados["todo"] if item.get("autores")]
        self.assertTrue(com_autor, "nenhum item com autor vereador")

    def test_executivo_plex_traz_votos_e_vet_traz_rotulo(self):
        dados = self._carregar("executivo_legislatura.json")
        plex = [item for item in dados["todo"] if item.get("tipo_sigla") == "PLEX"]
        self.assertTrue(plex, "sem PLEX no executivo")
        vetos = [item for item in dados["todo"] if item.get("tipo_sigla") == "VET"]
        self.assertTrue(vetos, "sem VET no executivo")
        for veto in vetos:
            self.assertIsNone(veto.get("materia_vetada_id"))
            self.assertTrue(veto.get("materia_vetada_rotulo"))

    def test_legislatura_complementada_sem_tocar_nos_anos(self):
        for ano in self.anos:
            caminho = TRATADOS / f"atuacao_vereadores_{ano}.json"
            referencia = TRATADOS / f"atuacao_vereadores_{ano}.json.sha256"
            calculado = hashlib.sha256(caminho.read_bytes()).hexdigest()
            salvo = referencia.read_text(encoding="utf-8").strip()
            self.assertEqual(calculado, salvo, f"atuacao_{ano} mudou")
        dados = self._carregar("atuacao_vereadores_legislatura.json")
        for vereador in dados.get("vereadores") or []:
            with self.subTest(vereador=vereador.get("id_sapl")):
                self.assertIn("proposicoes_req_moc_ind", vereador)
                self.assertIn("votos_plex", vereador)


if __name__ == "__main__":
    unittest.main()
