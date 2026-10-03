"""Testes da aba Prefeito: tipo de votacao e veto (D-058). Nao pedem nada ao SAPL.

Regras verificadas aqui:
    votacao_tipo vem do campo tipo_votacao do item da Ordem do Dia ligado ao
    registro de votacao, e vira rotulo so com a tabela oficial do SAPL ou
    com confirmacao dos proprios votos sobre o voto individual;
    codigo sem confirmacao, materia sem voto valido e item da Ordem do Dia
    ausente viram "nao informado no SAPL";
    veto_tipo vem do começo da ementa oficial, veto_situacao vem do
    resultado do voto valido do proprio veto;
    materia_vetada_id vem da revisao do mantenedor em vetos_revisados.json,
    que tem prioridade, ou da regra automatica, que exige numero e texto da
    ementa batendo ao mesmo tempo; com so um criterio, ou com mais de um
    candidato, o vinculo fica nulo e materia_vetada_fonte fica
    pendente_revisao;
    os campos novos so entram no grupo Executivo, e o config traz a chave
    que liga a aba.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "dados" / "tratados"))
sys.path.insert(0, str(RAIZ / "coletor"))

from gerar_proposicoes_executivo import (  # noqa: E402
    FONTE_VETADA_AUTOMATICA,
    FONTE_VETADA_PENDENTE,
    FONTE_VETADA_REVISAO,
    LIMIAR_SIMILARIDADE_VETO,
    ROTULO_VETADA_AUTOMATICA,
    ROTULO_VETADA_PENDENTE,
    ROTULO_VETADA_REVISADA,
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
    carregar_vetos_revisados,
    codigo_do_item_da_ordem,
    indexar_projetos,
    materia_vetada,
    normaliza_texto,
    referencia_da_ementa,
    rotulo_do_nome_oficial,
    rotulos_votacao_confirmados,
    sem_acento,
    similaridade,
    texto_da_sumula,
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

    def test_indice_so_aceita_projeto_de_lei_do_catalogo(self):
        siglas_por_tipo = {1: "PLEX", 6: "PLEG", 2: "PRE"}
        fichas = {
            10: {"numero": "7", "ano": "2025", "tipo_id": 6, "ementa": "INSTITUI O SELO"},
            11: {"numero": "7", "ano": "2025", "tipo_id": 1, "ementa": "DISPOE SOBRE"},
            12: {"numero": "7", "ano": "2025", "tipo_id": 2, "ementa": "AUTORIZA"},
        }
        catalogo = {
            "PLEG": "Projeto de Lei Origem do Poder Legislativo",
            "PLEX": "Projeto de Lei Origem Poder Executivo",
            "PRE": "Projeto de Resolução",
        }
        por_numero, ementas = indexar_projetos(fichas, siglas_por_tipo, catalogo)
        self.assertEqual(por_numero, {"2025|7": [10, 11]})
        self.assertEqual(ementas, {10: "institui o selo", 11: "dispoe sobre"})


# Ementa de veto como o SAPL escreve, com o numero que a Prefeitura cita.
VETO_COM_NUMERO_E_TEXTO = (
    "Veto Parcial ao PROJETO DE LEI Nº 013, DE 2025 - Súmula: "
    "Institui o selo “Empresa Amiga da Juventude”"
)
VETO_COM_NUMERO_E_OUTRO_TEXTO = (
    "Veto Parcial ao PROJETO DE LEI Nº 013, DE 2025 - Súmula: "
    "Autoriza a doação de bens móveis do patrimônio da Câmara"
)
VETO_COM_TEXTO_E_OUTRO_NUMERO = (
    "Veto Integral ao PROJETO DE LEI Nº 099, DE 2025 - Súmula: "
    "Institui o selo “Empresa Amiga da Juventude”"
)
VETO_SEM_NUMERO = "Veto Integral ao projeto de lei - Súmula: Institui o selo da races"
EMENTA_PROJETO = "INSTITUI O SELO “EMPRESA AMIGA DA JUVENTUDE”"


class TestTextoDaSumula(unittest.TestCase):
    def test_pega_o_texto_depois_da_marca(self):
        self.assertEqual(
            texto_da_sumula(VETO_COM_NUMERO_E_TEXTO),
            "institui o selo empresa amiga da juventude",
        )

    def test_ementa_sem_a_marca_usa_a_ementa_inteira(self):
        self.assertEqual(texto_da_sumula(EMENTA_PROJETO), normaliza_texto(EMENTA_PROJETO))

    def test_normalizar_tira_ponto_acento_e_caixa(self):
        self.assertEqual(
            normaliza_texto("Selo “Empresa Amiga”, da Juventude."),
            "selo empresa amiga da juventude",
        )


class TestSimilaridade(unittest.TestCase):
    def test_textos_iguais_dao_um(self):
        self.assertAlmostEqual(
            similaridade(normaliza_texto(EMENTA_PROJETO), normaliza_texto(EMENTA_PROJETO)),
            1.0,
        )

    def test_texto_vazio_da_zero(self):
        self.assertEqual(similaridade("", "dispoe sobre"), 0.0)


class TestVinculoDoVeto(unittest.TestCase):
    """Revisao do mantenedor tem prioridade; a regra automatica exige os dois criterios."""

    def setUp(self):
        self.por_numero = {"2025|13": [37]}
        self.ementas = {37: normaliza_texto(EMENTA_PROJETO)}

    def test_revisao_do_mantenedor_manda(self):
        materia, fonte, medida = materia_vetada(
            169, VETO_COM_NUMERO_E_OUTRO_TEXTO, {169: 99}, self.por_numero, self.ementas
        )
        self.assertEqual((materia, fonte), (99, FONTE_VETADA_REVISAO))
        self.assertIsNone(medida)

    def test_dois_criterios_iguais_ligam_so_um(self):
        materia, fonte, medida = materia_vetada(
            169, VETO_COM_NUMERO_E_TEXTO, {}, self.por_numero, self.ementas
        )
        self.assertEqual(materia, 37)
        self.assertEqual(fonte, FONTE_VETADA_AUTOMATICA)
        self.assertGreaterEqual(medida, LIMIAR_SIMILARIDADE_VETO)

    def test_so_o_numero_bater_nao_liga(self):
        materia, fonte, medida = materia_vetada(
            169, VETO_COM_NUMERO_E_OUTRO_TEXTO, {}, self.por_numero, self.ementas
        )
        self.assertIsNone(materia)
        self.assertEqual(fonte, FONTE_VETADA_PENDENTE)
        self.assertIsNone(medida)

    def test_so_o_texto_bater_nao_liga(self):
        materia, fonte, _medida = materia_vetada(
            169, VETO_COM_TEXTO_E_OUTRO_NUMERO, {}, self.por_numero, self.ementas
        )
        self.assertIsNone(materia)
        self.assertEqual(fonte, FONTE_VETADA_PENDENTE)

    def test_numero_sem_ano_nao_liga(self):
        materia, fonte, _medida = materia_vetada(
            169,
            "Veto Parcial ao PROJETO DE LEI Nº 013 - Súmula: " + EMENTA_PROJETO,
            {},
            self.por_numero,
            self.ementas,
        )
        self.assertIsNone(materia)
        self.assertEqual(fonte, FONTE_VETADA_PENDENTE)

    def test_zero_a_esquerda_da_ementa_nao_quebra_o_criterio_de_numero(self):
        """A ementa do SAPL escreve 013 e a ficha tem 13: a chave e a mesma."""
        materia, fonte, _medida = materia_vetada(
            169, VETO_COM_NUMERO_E_TEXTO, {}, self.por_numero, self.ementas
        )
        self.assertEqual((materia, fonte), (37, FONTE_VETADA_AUTOMATICA))

    def test_dois_projetos_iguais_no_texto_fica_pendente(self):
        """Texto igual em duas materias e ambiguidade: nunca escolhe uma."""
        materia, fonte, _medida = materia_vetada(
            169,
            VETO_COM_NUMERO_E_TEXTO,
            {},
            {"2025|13": [37, 43]},
            {37: normaliza_texto(EMENTA_PROJETO), 43: normaliza_texto(EMENTA_PROJETO)},
        )
        self.assertIsNone(materia)
        self.assertEqual(fonte, FONTE_VETADA_PENDENTE)

    def test_numero_que_aponta_para_outro_projeto_nao_liga(self):
        """O texto bate, mas o numero aponta para outra materia: nada de link."""
        materia, fonte, _medida = materia_vetada(
            169, VETO_COM_NUMERO_E_TEXTO, {}, {"2025|13": [43]}, self.ementas
        )
        self.assertIsNone(materia)
        self.assertEqual(fonte, FONTE_VETADA_PENDENTE)


class TestArquivoDeRevisao(unittest.TestCase):
    ENTRADA = {
        "veto_id": 169,
        "materia_vetada_id": 37,
        "revisada_por_humano": True,
        "revisado_por": "mantenedor",
        "data_revisao": "2026-10-02",
        "criterio": "texto da ementa do veto igual ao do projeto",
    }

    def _gravar(self, conteudo) -> Path:
        pasta = Path(tempfile.mkdtemp(prefix="vetos_e6g_"))
        self.addCleanup(shutil.rmtree, pasta, True)
        caminho = pasta / "vetos_revisados.json"
        caminho.write_text(
            json.dumps(conteudo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return caminho

    def test_arquivo_ausente_nao_e_erro(self):
        self.assertEqual(
            carregar_vetos_revisados(Path("nao_existe_vetos_revisados.json")), {}
        )

    def test_entrada_completa_vira_mapa(self):
        caminho = self._gravar([self.ENTRADA])
        self.assertEqual(carregar_vetos_revisados(caminho), {169: 37})

    def test_sem_revisao_humana_e_erro(self):
        entrada = dict(self.ENTRADA, revisada_por_humano=False)
        with self.assertRaises(SystemExit):
            carregar_vetos_revisados(self._gravar([entrada]))

    def test_sem_criterio_e_erro(self):
        entrada = dict(self.ENTRADA, criterio="")
        with self.assertRaises(SystemExit):
            carregar_vetos_revisados(self._gravar([entrada]))

    def test_sem_data_de_revisao_e_erro(self):
        entrada = dict(self.ENTRADA, data_revisao=None)
        with self.assertRaises(SystemExit):
            carregar_vetos_revisados(self._gravar([entrada]))

    def test_sem_id_e_erro(self):
        entrada = dict(self.ENTRADA, materia_vetada_id=None)
        with self.assertRaises(SystemExit):
            carregar_vetos_revisados(self._gravar([entrada]))

    def test_veto_repetido_e_erro(self):
        with self.assertRaises(SystemExit):
            carregar_vetos_revisados(self._gravar([self.ENTRADA, self.ENTRADA]))

    def test_arquivo_real_tem_os_campos_do_mantenedor(self):
        """O arquivo do repo nao pode perder o rastro de quem revisou."""
        itens = json.loads(
            (TRATADOS / "vetos_revisados.json").read_text(encoding="utf-8")
        )
        self.assertTrue(isinstance(itens, list) and itens)
        for entrada in itens:
            with self.subTest(veto=entrada.get("veto_id")):
                self.assertIs(entrada.get("revisada_por_humano"), True)
                self.assertEqual(entrada.get("revisado_por"), "mantenedor")
                self.assertTrue(entrada.get("data_revisao"))
                self.assertTrue(entrada.get("criterio"))
                self.assertIsInstance(entrada.get("veto_id"), int)
                self.assertIsInstance(entrada.get("materia_vetada_id"), int)


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

    def test_aba_do_prefeito_tem_chave_no_config(self):
        abas = self.cfg.get("abas") or {}
        self.assertIn("prefeito", abas)
        self.assertIsInstance(abas["prefeito"], bool)


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
                self.assertEqual("materia_vetada_similaridade" in item, veto)
                for chave in (
                    "materia_vetada_id",
                    "materia_vetada_fonte",
                    "materia_vetada_tipo",
                    "materia_vetada_link",
                    "materia_vetada_rotulo",
                ):
                    self.assertIn(chave, item)
                if veto:
                    self.assertIn(item["veto_tipo"], VETO_TIPOS)
                    self.assertIn(item["veto_situacao"], VETO_SITUACOES)
                else:
                    self.assertIsNone(item["materia_vetada_id"])
                    self.assertIsNone(item["materia_vetada_fonte"])
                    self.assertIsNone(item["materia_vetada_tipo"])
                    self.assertIsNone(item["materia_vetada_link"])
                    self.assertEqual(item["materia_vetada_rotulo"], ROTULO_VETADA_SEM_ESTRUTURA)

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

    def test_materia_vetada_precisa_ser_unica_e_vem_do_sapl(self):
        """O id ligado tem de ser materia de projeto de lei que existe nos dados."""
        base = Base(self.cfg)
        conhecidos = {
            item["id"] for item in carregar("proposicoes_legislatura.json")["todo"]
        }
        for nome, item in self._itens():
            if "veto_situacao" not in item or item["materia_vetada_id"] is None:
                continue
            vetada_id = int(item["materia_vetada_id"])
            ficha = base.fichas.get(vetada_id)
            with self.subTest(arquivo=nome, materia=item["tipo"]):
                self.assertIsNotNone(ficha, "materia_vetada_id fora dos dados do SAPL")
                self.assertNotEqual(vetada_id, item["id"])
                self.assertEqual(
                    item["materia_vetada_tipo"], base.tipo_da_materia(vetada_id)
                )
                self.assertIn(
                    "Projeto de Lei",
                    str(base.catalogo.get(base.sigla_da_materia(vetada_id))),
                )
                self.assertIn(
                    vetada_id,
                    {m for lista in base.projetos.values() for m in lista},
                    "materia_vetada_id nao e projeto de lei do SAPL",
                )
                self.assertIn(vetada_id, conhecidos, "materia_vetada_id fora dos arquivos")
                self.assertTrue(item["materia_vetada_link"].endswith(f"/materia/{vetada_id}"))

    def test_vinculo_do_veto_confere_com_a_revisao_do_mantenedor(self):
        """Cada veto ligado tem de estar no arquivo de revisao, com a fonte certa."""
        revisados = {
            int(entrada["veto_id"]): int(entrada["materia_vetada_id"])
            for entrada in json.loads(
                (TRATADOS / "vetos_revisados.json").read_text(encoding="utf-8")
            )
        }
        achou = 0
        for nome, item in self._itens():
            if "veto_situacao" not in item:
                continue
            veto_id = int(item["id"])
            with self.subTest(arquivo=nome, materia=item["tipo"]):
                self.assertIn(veto_id, revisados, "veto sem revisao registrada")
                if item["materia_vetada_id"] is None:
                    self.assertEqual(item["materia_vetada_fonte"], FONTE_VETADA_PENDENTE)
                    self.assertEqual(item["materia_vetada_rotulo"], ROTULO_VETADA_PENDENTE)
                else:
                    if nome == "executivo_legislatura.json":
                        achou += 1
                    self.assertEqual(item["materia_vetada_id"], revisados[veto_id])
                    self.assertEqual(item["materia_vetada_fonte"], FONTE_VETADA_REVISAO)
                    self.assertEqual(item["materia_vetada_rotulo"], ROTULO_VETADA_REVISADA)
                    self.assertIsNone(item["materia_vetada_similaridade"])
        self.assertEqual(achou, len(revisados), "alguma revisao do arquivo nao entrou")

    def test_regra_automatica_no_dos_vetos_do_recorte(self):
        """Mede a regra automatica sozinha, sem o arquivo de revisao.

        O limiar de 0,85 tem folga: no recorte inteiro a maior semelhanca
        entre um texto de veto e a ementa de um projeto errado e 0,60. O
        veto 3/2025 e a excecao conhecida: a ementa do veto e o texto de
        uma versao anterior do projeto, e o par chega a 0,34, bem abaixo do
        limiar. Por isso ele fica ligado pela revisao do mantenedor, e o
        campo automatico dele fica nulo.
        """
        base = Base(self.cfg)
        ementas = {
            int(item["id"]): base.fichas[int(item["id"])].get("ementa") or ""
            for _nome, item in self._itens()
            if "veto_situacao" in item
        }
        automaticos = {}
        for veto_id, ementa in ementas.items():
            materia, fonte, medida = materia_vetada(
                veto_id, ementa, {}, base.projetos, base.ementas_de_projeto
            )
            if fonte == FONTE_VETADA_AUTOMATICA:
                self.assertGreaterEqual(medida, LIMIAR_SIMILARIDADE_VETO)
                self.assertIn(veto_id, base.vetos_revisados)
                automaticos[veto_id] = materia
        self.assertTrue(automaticos, "nenhum veto casou pela regra automatica")
        for veto_id, materia in automaticos.items():
            with self.subTest(veto=veto_id):
                self.assertEqual(materia, base.vetos_revisados[veto_id])

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
                self.assertEqual(sum(meta["por_veto_tipo"].values()), vetoes)
                self.assertEqual(sum(meta["por_materia_vetada_fonte"].values()), vetoes)
                self.assertEqual(
                    meta["veto_com_materia_vetada"] + meta["veto_pendente_de_revisao"],
                    vetoes,
                )
                self.assertEqual(meta["limiar_similaridade_veto"], LIMIAR_SIMILARIDADE_VETO)
                self.assertEqual(
                    meta["fonte_vetos_revisados"], "dados/tratados/vetos_revisados.json"
                )

    def test_proposicoes_nao_recebem_campos_da_aba_prefeito(self):
        for nome in ("proposicoes_legislatura.json", "proposicoes_2025.json", "proposicoes_2026.json"):
            for item in carregar(nome)["todo"]:
                with self.subTest(arquivo=nome, materia=item["tipo"]):
                    self.assertNotIn("votacao_tipo", item)
                    self.assertNotIn("veto_tipo", item)
                    self.assertNotIn("veto_situacao", item)


if __name__ == "__main__":
    unittest.main()
