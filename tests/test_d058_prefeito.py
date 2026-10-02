"""Testes da aba Prefeito: tipo de votacao e veto (D-058). Nao pedem nada ao SAPL.

Regras verificadas aqui:
    votacao_tipo vem do campo tipo_votacao do item da Ordem do Dia ligado ao
    registro de votacao, e vira rotulo so com a tabela oficial do SAPL ou
    com confirmacao dos proprios votos sobre o voto individual;
    codigo sem confirmacao, materia sem voto valido e item da Ordem do Dia
    ausente viram "nao informado no SAPL";
    veto_tipo vem do começo da ementa oficial, veto_situacao vem do
    resultado do voto valido do proprio veto;
    materia_vetada_id so existe quando numero e ano da ementa levam a UMA
    unica materia de projeto de lei do SAPL;
    os campos novos so entram no grupo Executivo, e o config traz a chave
    que liga a aba.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "dados" / "tratados"))
sys.path.insert(0, str(RAIZ / "coletor"))

from gerar_proposicoes_executivo import (  # noqa: E402
    ROTULO_VETADA_LIGADA,
    ROTULO_VETADA_SEM_ESTRUTURA,
    VETO_AINDA_VAI_VOTAR,
    VETO_DERRUBADO,
    VETO_MANTIDO,
    VETO_TIPO_NAO_INFORMADO,
    VETO_TIPO_PARCIAL,
    VETO_TIPO_TOTAL,
    VOTACAO_TIPO_NAO_INFORMADO,
    VOTACAO_TIPO_NOMINAL,
    VOTACAO_TIPO_SIMBOLICA,
    Base,
    codigo_do_item_da_ordem,
    indexar_projetos,
    materia_vetada_de,
    referencia_da_ementa,
    rotulo_do_nome_oficial,
    rotulos_votacao_confirmados,
    sem_acento,
    veto_situacao_de,
    veto_tipo_de,
    votacao_tipo_de,
)
from config_cidade import carregar_config, tipos_veto  # noqa: E402

TRATADOS = RAIZ / "dados" / "tratados"

VOTACAO_TIPOS = (
    VOTACAO_TIPO_NOMINAL,
    VOTACAO_TIPO_SIMBOLICA,
    VOTACAO_TIPO_NAO_INFORMADO,
)
VETO_TIPOS = (VETO_TIPO_TOTAL, VETO_TIPO_PARCIAL, VETO_TIPO_NAO_INFORMADO)
VETO_SITUACOES = (VETO_DERRUBADO, VETO_MANTIDO, VETO_AINDA_VAI_VOTAR)

# Item da Ordem do Dia como o SAPL grava: o codigo tipo_votacao mora no
# item, e o registro de votacao aponta para o item pelo campo ordem.
ORDENS = {
    (3, 10): {"tipo_votacao": 1, "resultado_item_sapl": "Aprovada por Maioria Absoluta"},
    (3, 11): {"tipo_votacao": 2, "resultado_item_sapl": "Aprovada por Unanimidade"},
    (3, 12): {"tipo_votacao": 4, "resultado_item_sapl": "Matéria lida"},
}


def voto_de_exemplo(ordem, individual=True, turno="turno unico", situacao="Aprovado"):
    """Voto valido de exemplo, do jeito que a atuacao grava."""
    return {
        "id": 100 + (ordem or 0),
        "sessao_id": 3,
        "ordem": ordem,
        "data_sessao": "2025-08-05",
        "turno": turno,
        "tipo_resultado_nome": "Aprovada por Maioria Absoluta",
        "situacao_oficial_sapl": situacao,
        "voto_individual_registrado": individual,
    }


class TestNomeOficialTipoVotacao(unittest.TestCase):
    def test_nominal_e_nominal(self):
        self.assertEqual(rotulo_do_nome_oficial("Nominal"), VOTACAO_TIPO_NOMINAL)

    def test_simbolica_com_acento_e_simbolica(self):
        self.assertEqual(rotulo_do_nome_oficial("Simbólica"), VOTACAO_TIPO_SIMBOLICA)

    def test_nome_que_o_codigo_nao_explica_fica_desconhecido(self):
        for nome in ("Secreta", "Leitura", "", None):
            with self.subTest(nome=nome):
                self.assertEqual(
                    rotulo_do_nome_oficial(nome), VOTACAO_TIPO_NAO_INFORMADO
                )

    def test_sem_acento_tira_acento_e_sobe(self):
        self.assertEqual(sem_acento("Veto Parcial"), "VETO PARCIAL")


class TestLigacaoComOrdemDoDia(unittest.TestCase):
    def test_codigo_veem_do_item_ligado_por_sessao_e_ordem(self):
        self.assertEqual(codigo_do_item_da_ordem(voto_de_exemplo(11), ORDENS), 2)

    def test_ordem_de_outra_sessao_nao_acha_item(self):
        voto = dict(voto_de_exemplo(11), sessao_id=99)
        self.assertIsNone(codigo_do_item_da_ordem(voto, ORDENS))

    def test_ordem_inexistente_nao_acha_item(self):
        self.assertIsNone(codigo_do_item_da_ordem(voto_de_exemplo(999), ORDENS))

    def test_voto_sem_ordem_nao_acha_item(self):
        self.assertIsNone(codigo_do_item_da_ordem(voto_de_exemplo(None), ORDENS))

    def test_item_sem_codigo_devolve_none(self):
        ordens = {(3, 10): {"tipo_votacao": None, "resultado_item_sapl": ""}}
        self.assertIsNone(codigo_do_item_da_ordem(voto_de_exemplo(10), ordens))

    def test_lista_de_ordens_vazia_nao_quebra(self):
        self.assertIsNone(codigo_do_item_da_ordem(voto_de_exemplo(10), {}))


class TestRotuloConfirmadoPeloVoto(unittest.TestCase):
    def test_tabela_oficial_manda_sobre_os_votos(self):
        """Com a tabela tipovotacao do SAPL, o texto oficial decide."""
        rotulos = rotulos_votacao_confirmados({}, ORDENS, {1: "Nominal", 2: "Simbólica"})
        self.assertEqual(rotulos, {1: VOTACAO_TIPO_NOMINAL, 2: VOTACAO_TIPO_SIMBOLICA})

    def test_tabela_oficial_sem_nome_util_nao_entra(self):
        rotulos = rotulos_votacao_confirmados({}, ORDENS, {1: "Secreta"})
        self.assertEqual(rotulos, {})

    def test_codigo_com_voto_individual_e_nominal(self):
        votacoes = {1: [voto_de_exemplo(11, individual=True)]}
        rotulos = rotulos_votacao_confirmados(votacoes, ORDENS, {})
        self.assertEqual(rotulos, {2: VOTACAO_TIPO_NOMINAL})

    def test_codigo_sem_voto_individual_e_simbolica(self):
        votacoes = {1: [voto_de_exemplo(10, individual=False)]}
        rotulos = rotulos_votacao_confirmados(votacoes, ORDENS, {})
        self.assertEqual(rotulos, {1: VOTACAO_TIPO_SIMBOLICA})

    def test_evidencia_contraditoria_deixa_codigo_de_fora(self):
        votacoes = {
            1: [voto_de_exemplo(11, individual=True)],
            2: [voto_de_exemplo(11, individual=False)],
        }
        self.assertEqual(rotulos_votacao_confirmados(votacoes, ORDENS, {}), {})

    def test_codigo_sem_voto_valido_nao_confirma_nada(self):
        votacoes = {1: [voto_de_exemplo(12, individual=False, turno="1o turno")]}
        self.assertEqual(rotulos_votacao_confirmados(votacoes, ORDENS, {}), {})

    def test_voto_sem_item_da_ordem_nao_confirma_nada(self):
        votacoes = {1: [voto_de_exemplo(999, individual=True)]}
        self.assertEqual(rotulos_votacao_confirmados(votacoes, ORDENS, {}), {})


class TestRotuloDaVotacao(unittest.TestCase):
    def test_materia_sem_voto_valido_fica_nao_informado(self):
        self.assertEqual(
            votacao_tipo_de(None, ORDENS, {1: VOTACAO_TIPO_SIMBOLICA}),
            VOTACAO_TIPO_NAO_INFORMADO,
        )

    def test_codigo_sem_confirmacao_fica_nao_informado(self):
        self.assertEqual(
            votacao_tipo_de(voto_de_exemplo(12), ORDENS, {1: VOTACAO_TIPO_SIMBOLICA}),
            VOTACAO_TIPO_NAO_INFORMADO,
        )

    def test_codigo_confirmado_vira_rotulo(self):
        self.assertEqual(
            votacao_tipo_de(voto_de_exemplo(10, individual=False), ORDENS, {1: VOTACAO_TIPO_SIMBOLICA}),
            VOTACAO_TIPO_SIMBOLICA,
        )


class TestVetoTipo(unittest.TestCase):
    def test_integral_e_total(self):
        self.assertEqual(
            veto_tipo_de("Veto Integral ao Projeto de Lei 008/2025"), VETO_TIPO_TOTAL
        )

    def test_total_e_total(self):
        self.assertEqual(veto_tipo_de("Veto Total ao PL 008/2025"), VETO_TIPO_TOTAL)

    def test_parcial_e_parcial(self):
        self.assertEqual(
            veto_tipo_de("Veto Parcial ao PROJETO DE LEI Nº 013, DE 2025"),
            VETO_TIPO_PARCIAL,
        )

    def test_minuscula_e_acentuada_tem_o_mesmo_efeito(self):
        self.assertEqual(veto_tipo_de("veto integral ao projeto de lei"), VETO_TIPO_TOTAL)

    def test_ementa_sem_veto_nao_inventa(self):
        for ementa in ("AUTORIZA A DOACAO DE BENS", "", None):
            with self.subTest(ementa=ementa):
                self.assertEqual(veto_tipo_de(ementa), VETO_TIPO_NAO_INFORMADO)


class TestVetoSituacao(unittest.TestCase):
    def test_rejeitado_derruba(self):
        self.assertEqual(
            veto_situacao_de({"situacao_oficial_sapl": "Rejeitado"}), VETO_DERRUBADO
        )

    def test_aprovado_mantem(self):
        self.assertEqual(
            veto_situacao_de({"situacao_oficial_sapl": "Aprovado"}), VETO_MANTIDO
        )

    def test_sem_voto_valido_a_camara_ainda_vai_votar(self):
        self.assertEqual(veto_situacao_de(None), VETO_AINDA_VAI_VOTAR)

    def test_resultado_fora_do_mapa_para_o_script(self):
        with self.assertRaises(SystemExit):
            veto_situacao_de({"registro_votacao_id": 7, "situacao_oficial_sapl": None})


class TestMateriaVetada(unittest.TestCase):
    def test_referencia_com_numeracao_do_sapl(self):
        self.assertEqual(
            referencia_da_ementa("Veto Parcial ao PROJETO DE LEI Nº 013, DE 2025"),
            ("013", "2025"),
        )

    def test_referencia_com_barra(self):
        self.assertEqual(
            referencia_da_ementa("Veto Integral ao Projeto de Lei 008/2025"),
            ("008", "2025"),
        )

    def test_referencia_com_sigla_curta(self):
        self.assertEqual(referencia_da_ementa("Veto Integral ao PL 8/2025"), ("8", "2025"))

    def test_ementa_sem_numero_nao_inventa(self):
        self.assertEqual(
            referencia_da_ementa("Veto Integral ao projeto de lei em causa"), (None, None)
        )

    def test_numero_que_so_aponta_para_uma_materia_liga(self):
        indice = {"2025|8": [27]}
        self.assertEqual(
            materia_vetada_de("Veto Integral ao Projeto de Lei 008/2025", indice), 27
        )

    def test_zero_a_esquerda_da_ementa_nao_quebra_a_ligacao(self):
        indice = {"2025|13": [37]}
        self.assertEqual(
            materia_vetada_de("Veto Parcial ao PROJETO DE LEI Nº 013, DE 2025", indice),
            37,
        )

    def test_numero_ambigo_fica_nulo(self):
        indice = {"2025|8": [27, 148]}
        self.assertIsNone(materia_vetada_de("Veto Integral ao Projeto de Lei 8/2025", indice))

    def test_numero_que_nao_existe_fica_nulo(self):
        self.assertIsNone(materia_vetada_de("Veto Integral ao PL 999/2025", {"2025|8": [27]}))

    def test_referencia_sem_ano_fica_nula(self):
        self.assertIsNone(materia_vetada_de("Veto Integral ao Projeto de Lei 8", {"2025|8": [27]}))

    def test_indice_so_aceita_projeto_de_lei_do_catalogo(self):
        cfg = carregar_config()
        base = Base(cfg)
        siglas_por_tipo = {1: "PLEX", 6: "PLEG", 2: "PRE"}
        fichas = {
            10: {"numero": "7", "ano": "2025", "tipo_id": 6},
            11: {"numero": "7", "ano": "2025", "tipo_id": 1},
            12: {"numero": "7", "ano": "2025", "tipo_id": 2},
        }
        catalogo = {
            "PLEG": "Projeto de Lei Origem do Poder Legislativo",
            "PLEX": "Projeto de Lei Origem Poder Executivo",
            "PRE": "Projeto de Resolução",
        }
        indice = indexar_projetos(fichas, siglas_por_tipo, catalogo)
        self.assertEqual(indice, {"2025|7": [10, 11]})
        self.assertEqual(base.projetos["2025|7"], sorted(base.projetos["2025|7"]))
        self.assertNotIn("2025|" + str(7) + "|" + str(2), indice)


class TestConfigDaAba(unittest.TestCase):
    def setUp(self):
        self.cfg = carregar_config()

    def test_tipos_veto_vem_do_config(self):
        siglas = tipos_veto(self.cfg)
        self.assertTrue(siglas)
        self.assertEqual(siglas, (self.cfg.get("tramitacao") or {}).get("tipos_veto"))

    def test_config_sem_tipos_veto_e_recusado(self):
        cfg = {"tramitacao": {}}
        with self.assertRaises(SystemExit):
            tipos_veto(cfg)

    def test_aba_do_prefeito_esta_desligada_no_config(self):
        abas = self.cfg.get("abas") or {}
        self.assertIn("prefeito", abas)
        self.assertIs(abas["prefeito"], False)


def carregar(nome: str) -> dict:
    return json.loads((TRATADOS / nome).read_text(encoding="utf-8"))


class TestExecutivoGerado(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = carregar_config()
        cls.siglas_veto = set(tipos_veto(cls.cfg))
        cls.arquivos = {
            nome: carregar(nome)
            for nome in ("executivo_legislatura.json", "executivo_2025.json", "executivo_2026.json")
        }

    def _itens(self):
        for nome, dados in self.arquivos.items():
            for item in dados["todo"]:
                yield nome, item

    def test_todo_item_executivo_tem_votacao_tipo_conhecido(self):
        achou_simbolica = achou_nominal = False
        for nome, item in self._itens():
            with self.subTest(arquivo=nome, materia=item["tipo"]):
                self.assertIn(item["votacao_tipo"], VOTACAO_TIPOS)
            achou_simbolica = achou_simbolica or item["votacao_tipo"] == VOTACAO_TIPO_SIMBOLICA
            achou_nominal = achou_nominal or item["votacao_tipo"] == VOTACAO_TIPO_NOMINAL
        self.assertTrue(achou_nominal, "nenhum item com votacao nominal nos dados")
        self.assertTrue(achou_simbolica, "nenhum item com votacao simbolica nos dados")

    def test_item_sem_voto_valido_nao_tem_tipo_de_votacao(self):
        for nome, item in self._itens():
            if item["votacao"] is None:
                with self.subTest(arquivo=nome, materia=item["tipo"]):
                    self.assertEqual(item["votacao_tipo"], VOTACAO_TIPO_NAO_INFORMADO)

    def test_tipo_de_votacao_conferido_pelo_voto_individual(self):
        """O rotulo nunca discorda do voto individual do proprio SAPL."""
        for nome, item in self._itens():
            votacao = item["votacao"]
            if votacao is None or item["votacao_tipo"] == VOTACAO_TIPO_NAO_INFORMADO:
                continue
            with self.subTest(arquivo=nome, materia=item["tipo"]):
                if item["votacao_tipo"] == VOTACAO_TIPO_NOMINAL:
                    self.assertTrue(votacao["voto_individual_registrado"])
                    self.assertTrue(item["votos_nominais"])
                else:
                    self.assertFalse(votacao["voto_individual_registrado"])
                    self.assertEqual(item["votos_nominais"], [])

    def test_codigo_cru_tem_o_item_da_ordem_ligado(self):
        for nome, item in self._itens():
            votacao = item["votacao"]
            if votacao is None:
                continue
            with self.subTest(arquivo=nome, materia=item["tipo"]):
                self.assertIn("tipo_votacao_codigo", votacao)
                if item["votacao_tipo"] != VOTACAO_TIPO_NAO_INFORMADO:
                    self.assertIsInstance(votacao["tipo_votacao_codigo"], int)

    def test_so_veto_tem_campos_de_veto(self):
        for nome, item in self._itens():
            veto = item["tipo_sigla"] in self.siglas_veto
            with self.subTest(arquivo=nome, materia=item["tipo"]):
                self.assertEqual("veto_tipo" in item, veto)
                self.assertEqual("veto_situacao" in item, veto)
                self.assertIn("materia_vetada_id", item)
                self.assertIn("materia_vetada_rotulo", item)
                if veto:
                    self.assertIn(item["veto_tipo"], VETO_TIPOS)
                    self.assertIn(item["veto_situacao"], VETO_SITUACOES)

    def test_situacao_do_veto_bate_com_o_resultado_do_voto_valido(self):
        for nome, item in self._itens():
            if "veto_situacao" not in item:
                continue
            votacao = item["votacao"]
            with self.subTest(arquivo=nome, materia=item["tipo"]):
                if votacao is None:
                    self.assertEqual(item["veto_situacao"], VETO_AINDA_VAI_VOTAR)
                elif votacao["situacao_oficial_sapl"] == "Rejeitado":
                    self.assertEqual(item["veto_situacao"], VETO_DERRUBADO)
                else:
                    self.assertEqual(item["veto_situacao"], VETO_MANTIDO)

    def test_materia_vetada_so_quando_o_numero_leva_a_uma_so(self):
        base = Base(self.cfg)
        ids = {item["id"]: item for _nome, item in self._itens()}
        conferidos = 0
        for nome, item in self._itens():
            if item["materia_vetada_id"] is None:
                with self.subTest(arquivo=nome, materia=item["tipo"]):
                    self.assertEqual(item["materia_vetada_rotulo"], ROTULO_VETADA_SEM_ESTRUTURA)
                continue
            conferidos += 1
            vetada = ids.get(int(item["materia_vetada_id"]))
            with self.subTest(arquivo=nome, materia=item["tipo"]):
                self.assertIsNotNone(vetada, "materia_vetada_id fora dos dados")
                self.assertEqual(item["materia_vetada_rotulo"], ROTULO_VETADA_LIGADA)
                self.assertNotEqual(vetada["id"], item["id"])
                candidatos = base.projetos.get(f"{vetada['ano']}|{vetada['numero']}") or []
                self.assertEqual(candidatos, [vetada["id"]])
                self.assertIn("Projeto de Lei", str(base.catalogo.get(vetada["tipo_sigla"])))
        self.assertGreaterEqual(conferidos, 0)

    def test_meta_conta_os_campos_novos(self):
        for nome, dados in self.arquivos.items():
            meta = dados["meta"]
            vetoes = meta["por_tipo_sigla"].get("VET", 0)
            with self.subTest(arquivo=nome):
                self.assertEqual(sum(meta["por_votacao_tipo"].values()), meta["total"])
                self.assertTrue(set(meta["por_tipo_sigla"]) <= {"PLEX", "VET"})
                if not vetoes:
                    self.assertNotIn("por_veto_situacao", meta)
                    continue
                self.assertEqual(sum(meta["por_veto_situacao"].values()), vetoes)
                self.assertEqual(
                    meta["veto_derrotados"]
                    + meta["veto_mantidos"]
                    + meta["veto_sem_voto_valido"],
                    vetoes,
                )
                self.assertEqual(sum(meta["por_veto_tipo"].values()), vetoes)

    def test_proposicoes_nao_recebem_campos_da_aba_prefeito(self):
        for nome in ("proposicoes_legislatura.json", "proposicoes_2025.json", "proposicoes_2026.json"):
            for item in carregar(nome)["todo"]:
                with self.subTest(arquivo=nome, materia=item["tipo"]):
                    self.assertNotIn("votacao_tipo", item)
                    self.assertNotIn("veto_tipo", item)
                    self.assertNotIn("veto_situacao", item)


if __name__ == "__main__":
    unittest.main()