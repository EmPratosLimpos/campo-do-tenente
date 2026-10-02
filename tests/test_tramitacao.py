"""Testes da tramitacao e da consolidacao C9. Nao fazem pedido ao SAPL.

Regras verificadas aqui (E6d):
    votacao e votos nominais saem so do voto valido: 2o turno ou turno
    unico, e so registro deliberativo lido pelo id do tipo de resultado
    do SAPL;
    materia votada so no 1o turno continua em tramitacao, sem voto
    valido;
    Pedido de Vistas, materia adiada e retirada de pauta nao sao
    votacao;
    voto nominal so entra de quem estava no mandato na data;
    votacao do Executivo e os votos validos da atuacao batem em 100%.
"""

from __future__ import annotations

import hashlib
import json
import sys
import unittest
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "dados" / "tratados"))
sys.path.insert(0, str(RAIZ / "coletor"))

from gerar_proposicoes_executivo import (  # noqa: E402
    ROTULO_SEM_TRAMITACAO,
    ROTULO_SEM_VOTACAO,
    ROTULO_SEM_VOTO_INDIVIDUAL,
    SITUACAO_EM_TRAMITACAO,
    SITUACOES_FINAIS,
    autores_vereadores,
    decodificar_status,
    dividir_periodos,
    escolher_ultima,
    escolher_votacao,
    montar_ultima_tramitacao,
    montar_votacao,
    registro_deliberativo,
    situacao_final,
    voto_valido,
    votos_nominais,
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
NOME_OFICIAL_VOTOS = {
    "Aprovado",
    "Rejeitado",
}

VOTO_1O_TURNO = {
    "id": 10,
    "data_sessao": "2025-06-17",
    "data_hora": "2025-06-17T10:00:00",
    "turno": "1o turno",
    "tipo_resultado_nome": "Aprovada por Unanimidade",
    "situacao_oficial_sapl": "Aprovado",
    "resultado_texto_sapl": "UNANIMIDADE",
    "frase_resultado_sapl": "Aprovada por unanimidade",
    "texto_registro_sapl": "Votacao: Aprovada por unanimidade",
    "totais_oficiais": {
        "numero_votos_sim": 2,
        "numero_votos_nao": 0,
        "numero_abstencoes": 0,
    },
    "voto_individual_registrado": True,
    "link_sessao": "https://exemplo.invalido/sessao/1",
    "link_materia": "https://exemplo.invalido/materia/1",
    "estados_por_vereador": [
        {"id_sapl": 1, "estado": "sim", "rotulo": "Sim", "voto_texto_sapl": "Sim"},
        {"id_sapl": 2, "estado": "sim", "rotulo": "Sim", "voto_texto_sapl": "Sim"},
    ],
}

VOTO_2O_TURNO = dict(
    VOTO_1O_TURNO,
    id=11,
    data_sessao="2025-06-24",
    data_hora="2025-06-24T10:00:00",
    turno="2o turno",
)

PEDIDO_DE_VISTAS = dict(
    VOTO_1O_TURNO,
    id=12,
    turno=None,
    tipo_resultado_nome="Pedido de Vistas",
    situacao_oficial_sapl=None,
    resultado_texto_sapl=None,
    frase_resultado_sapl=None,
    texto_registro_sapl="Pedido de Vistas",
)

REJEITADO_1O_TURNO = dict(
    VOTO_1O_TURNO,
    id=13,
    tipo_resultado_nome="Rejeitada",
    situacao_oficial_sapl="Rejeitado",
    resultado_texto_sapl="REJEITADO",
)

ADIADA = dict(
    VOTO_1O_TURNO,
    id=14,
    turno=None,
    tipo_resultado_nome="Adiada",
    situacao_oficial_sapl=None,
    resultado_texto_sapl=None,
    frase_resultado_sapl=None,
    texto_registro_sapl="Adiada",
)


def tem_chave_ip(obj) -> bool:
    if isinstance(obj, dict):
        if "ip" in obj:
            return True
        return any(tem_chave_ip(valor) for valor in obj.values())
    if isinstance(obj, list):
        return any(tem_chave_ip(valor) for valor in obj)
    return False


def carregar(nome: str) -> dict:
    return json.loads((TRATADOS / nome).read_text(encoding="utf-8"))


def votos_validos_da_atuacao() -> Counter:
    """Conta os votos validos por materia, pelo historico de cada vereador."""
    contagem: Counter = Counter()
    for vereador in carregar("atuacao_vereadores_legislatura.json").get("vereadores") or []:
        for nominal in (vereador.get("votos") or {}).get("nominais") or []:
            materia_id = nominal.get("materia_id")
            if materia_id is not None:
                contagem[int(materia_id)] += 1
    return contagem


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

    def test_sem_votacao_valida_tem_rotulo(self):
        votacao, rotulo = montar_votacao(1, {})
        self.assertIsNone(votacao)
        self.assertEqual(rotulo, ROTULO_SEM_VOTACAO)

    def test_apenas_1o_turno_tem_rotulo(self):
        votacao, rotulo = montar_votacao(1, {1: [VOTO_1O_TURNO]})
        self.assertIsNone(votacao)
        self.assertEqual(rotulo, ROTULO_SEM_VOTACAO)

    def test_pedido_de_vistas_nunca_vira_votacao(self):
        votacao, rotulo = montar_votacao(1, {1: [PEDIDO_DE_VISTAS]})
        self.assertIsNone(votacao)
        self.assertEqual(rotulo, ROTULO_SEM_VOTACAO)

    def test_votacao_escolhe_a_mais_recente_entre_validas(self):
        registros = [VOTO_1O_TURNO, VOTO_2O_TURNO]
        self.assertEqual(escolher_votacao(registros)["id"], VOTO_2O_TURNO["id"])

    def test_ultima_pagina_nao_deliberativa_nao_vence(self):
        registros = [VOTO_2O_TURNO, PEDIDO_DE_VISTAS]
        self.assertEqual(escolher_votacao(registros)["id"], VOTO_2O_TURNO["id"])

    def test_escolher_votacao_de_lista_vazia_da_none(self):
        self.assertIsNone(escolher_votacao([]))


class TestVotoValido(unittest.TestCase):
    def test_turno_unico_e_valido(self):
        registro = dict(VOTO_1O_TURNO, turno="turno unico")
        self.assertTrue(voto_valido(registro))

    def test_segundo_turno_e_valido(self):
        self.assertTrue(voto_valido(VOTO_2O_TURNO))

    def test_primeiro_turno_nao_e_valido(self):
        self.assertFalse(voto_valido(VOTO_1O_TURNO))

    def test_turno_nao_identificado_nao_e_valido(self):
        registro = dict(VOTO_1O_TURNO, turno="turno nao identificado")
        self.assertFalse(voto_valido(registro))

    def test_pedido_de_vistas_nao_e_deliberativo(self):
        self.assertFalse(registro_deliberativo(PEDIDO_DE_VISTAS))
        self.assertFalse(voto_valido(PEDIDO_DE_VISTAS))

    def test_adiada_nao_e_deliberativa(self):
        self.assertFalse(registro_deliberativo(ADIADA))
        self.assertFalse(voto_valido(ADIADA))

    def test_aprovada_e_deliberativa(self):
        self.assertTrue(registro_deliberativo(VOTO_1O_TURNO))


class TestSituacaoFinal(unittest.TestCase):
    DOIS_TURNOS = {"TESTE_DOIS_TURNOS"}

    def test_so_1o_turno_aprovado_segue_em_tramitacao(self):
        situacao = situacao_final([VOTO_1O_TURNO], "TESTE_DOIS_TURNOS", self.DOIS_TURNOS)
        self.assertEqual(situacao, SITUACAO_EM_TRAMITACAO)

    def test_1o_e_2o_turno_o_segundo_decide(self):
        situacao = situacao_final(
            [VOTO_1O_TURNO, VOTO_2O_TURNO], "TESTE_DOIS_TURNOS", self.DOIS_TURNOS
        )
        self.assertEqual(situacao, "Aprovado")

    def test_rejeitado_no_1o_turno_encerra_rejeitado(self):
        situacao = situacao_final(
            [REJEITADO_1O_TURNO], "TESTE_DOIS_TURNOS", self.DOIS_TURNOS
        )
        self.assertEqual(situacao, "Rejeitado")

    def test_apenas_pedido_de_vistas_segue_em_tramitacao(self):
        situacao = situacao_final(
            [VOTO_1O_TURNO, PEDIDO_DE_VISTAS], "TESTE_DOIS_TURNOS", self.DOIS_TURNOS
        )
        self.assertEqual(situacao, SITUACAO_EM_TRAMITACAO)

    def test_sem_registro_deliberativo_nao_deduz_aprovacao(self):
        situacao = situacao_final([PEDIDO_DE_VISTAS], "TESTE_DOIS_TURNOS", self.DOIS_TURNOS)
        self.assertEqual(situacao, SITUACAO_EM_TRAMITACAO)

    def test_tipo_fora_dos_dois_turnos_usa_turno_unico(self):
        registro = dict(VOTO_1O_TURNO, turno="turno unico")
        situacao = situacao_final([registro], "TESTE_TURNO_UNICO", self.DOIS_TURNOS)
        self.assertEqual(situacao, "Aprovado")

    def test_situacao_esta_na_lista_de_rotulos(self):
        situacoes = {situacao_final([], "X", self.DOIS_TURNOS)}
        self.assertTrue(situacoes.issubset(set(SITUACOES_FINAIS)))


class TestVotosNominais(unittest.TestCase):
    VEREADORES = {
        1: {
            "id_sapl": 1,
            "nome_parlamentar": "Pessoa Em Mandato",
            "mandatos": [{"data_inicio_mandato": "2025-01-01"}],
        },
        2: {
            "id_sapl": 2,
            "nome_parlamentar": "Pessoa Fora do Mandato",
            "mandatos": [{"data_inicio_mandato": "2026-01-01"}],
        },
    }

    def test_fora_do_mandato_nao_entra(self):
        saida = votos_nominais(VOTO_2O_TURNO, self.VEREADORES)
        self.assertEqual([item["parlamentar_id_sapl"] for item in saida], [1])

    def test_mandato_que_comeca_na_data_ja_conta(self):
        registro = dict(VOTO_2O_TURNO, data_sessao="2026-01-01")
        saida = votos_nominais(registro, self.VEREADORES)
        self.assertEqual([item["parlamentar_id_sapl"] for item in saida], [1, 2])

    def test_sem_registro_da_lista_vazia(self):
        self.assertEqual(votos_nominais(None, self.VEREADORES), [])


class TestAutoria(unittest.TestCase):
    def test_so_parlamentar_entra_na_lista_de_vereadores(self):
        autoria = {
            10: [
                {"parlamentar_id_sapl": 5, "nome_no_sapl": "Nome No Sapl", "primeiro_autor": True},
                {"parlamentar_id_sapl": None, "nome_no_sapl": "Executivo", "primeiro_autor": False},
            ]
        }
        vereadores = {5: {"nome_parlamentar": "Nome Do Painel"}}
        saida = autores_vereadores(10, autoria, vereadores)
        self.assertEqual(len(saida), 1)
        self.assertEqual(saida[0]["parlamentar_id_sapl"], 5)

    def test_materia_sem_autoria_da_lista_vazia(self):
        self.assertEqual(autores_vereadores(999, {}, {}), [])


class TestPeriodos(unittest.TestCase):
    def test_item_sem_votacao_fica_so_no_todo(self):
        sessoes = [{"id": 5, "data": "2025-06-17"}]
        item = {"id": 1, "votacao": None}
        sessao, mes, todo = dividir_periodos([item], sessoes)
        self.assertEqual(sessao, [])
        self.assertEqual(mes, [])
        self.assertEqual(len(todo), 1)

    def test_item_da_ultima_sessao_entra_no_periodo_sessao(self):
        sessoes = [{"id": 5, "data": "2025-06-17"}]
        item = {"id": 1, "votacao": {"sessao_id": 5, "data_sessao": "2025-06-17"}}
        sessao, _mes, _todo = dividir_periodos([item], sessoes)
        self.assertEqual(len(sessao), 1)


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

    def _todos(self):
        for nome in (
            "proposicoes_2025.json",
            "proposicoes_2026.json",
            "proposicoes_legislatura.json",
            "executivo_2025.json",
            "executivo_2026.json",
            "executivo_legislatura.json",
        ):
            yield nome, self._carregar(nome)

    def test_proposicoes_e_executivo_por_ano_e_legislatura(self):
        for nome, dados in self._todos():
            with self.subTest(arquivo=nome):
                for chave in ("meta", "sessao", "mes", "todo"):
                    self.assertIn(chave, dados, nome)
                self.assertFalse(tem_chave_ip(dados), nome)
                self.assertEqual(dados["meta"]["total"], len(dados["todo"]), nome)
                for item in dados["todo"]:
                    self.assertTrue(item.get("link_sapl"), nome)
                    self.assertIn("ultima_tramitacao_rotulo", item, nome)
                    self.assertIn("votacao_rotulo", item, nome)
                    self.assertIn("situacao_final", item, nome)
                    self.assertIn(item["situacao_final"], SITUACOES_FINAIS, nome)
                    self.assertTrue(item.get("tipo_nome"), nome)
                    if item["ultima_tramitacao"] is None:
                        self.assertEqual(item["ultima_tramitacao_rotulo"], ROTULO_SEM_TRAMITACAO)
                    if item["votacao"] is None:
                        self.assertEqual(item["votacao_rotulo"], ROTULO_SEM_VOTACAO)
                        self.assertEqual(item["votos_nominais"], [])
                        self.assertEqual(item["votos_nominais_rotulo"], ROTULO_SEM_VOTACAO)

    def test_voto_sem_deliberacao_nunca_e_votacao_valido(self):
        for nome, dados in self._todos():
            for item in dados["todo"]:
                for registro in item["votacoes_registradas"]:
                    if registro["deliberativa"]:
                        continue
                    self.assertFalse(registro["voto_valido"], f"{nome} {item['tipo']}")
                if item["votacao"] is not None:
                    self.assertTrue(item["votacao"]["turno"], f"{nome} {item['tipo']}")
                    self.assertNotEqual(item["votacao"]["turno"], "1o turno", nome)

    def test_votacao_escolhida_esta_entre_as_registradas(self):
        for nome, dados in self._todos():
            for item in dados["todo"]:
                if item["votacao"] is None:
                    continue
                validos = [
                    registro
                    for registro in item["votacoes_registradas"]
                    if registro["voto_valido"]
                ]
                self.assertTrue(validos, f"{nome} {item['tipo']}")
                with self.subTest(arquivo=nome, materia=item["tipo"]):
                    self.assertEqual(
                        item["votacao"]["registro_votacao_id"],
                        validos[-1]["registro_votacao_id"],
                    )

    def test_apenas_1o_turno_fica_em_tramitacao(self):
        """So 1o turno aprovado nao decide: segue em tramitacao, sem voto.

        Rejeicao no 1o turno encerra como rejeitada, tambem sem voto
        valido. Nenhum dos dois casos vira votacao.
        """
        achou_em_tramitacao = False
        achou_rejeitada = False
        for nome, dados in self._todos():
            for item in dados["todo"]:
                registros = item["votacoes_registradas"]
                deliberativos = [r for r in registros if r["deliberativa"]]
                if not deliberativos or len(registros) != len(deliberativos):
                    continue
                if any(r["turno"] != "1o turno" for r in deliberativos):
                    continue
                with self.subTest(arquivo=nome, materia=item["tipo"]):
                    self.assertIsNone(item["votacao"])
                    self.assertEqual(item["votos_nominais"], [])
                    self.assertEqual(item["votacao_rotulo"], ROTULO_SEM_VOTACAO)
                    if item["situacao_final"] == "Rejeitado":
                        achou_rejeitada = True
                    else:
                        achou_em_tramitacao = True
                        self.assertEqual(item["situacao_final"], SITUACAO_EM_TRAMITACAO)
        self.assertTrue(achou_em_tramitacao, "nenhuma materia so com 1o turno aprovado")
        self.assertTrue(achou_rejeitada, "nenhuma materia rejeitada no 1o turno")

    def test_pedido_de_vistas_nao_vira_votacao_nos_dados(self):
        achou = False
        for _nome, dados in self._todos():
            for item in dados["todo"]:
                nao_deliberativos = [
                    r for r in item["votacoes_registradas"] if not r["deliberativa"]
                ]
                if not nao_deliberativos:
                    continue
                achou = True
                for registro in nao_deliberativos:
                    with self.subTest(materia=item["tipo"], rotulo=registro["tipo_resultado_nome"]):
                        self.assertFalse(registro["voto_valido"])
                if item["votacao"] is not None:
                    with self.subTest(materia=item["tipo"]):
                        self.assertIn(item["votacao"]["registro_votacao_id"], [
                            r["registro_votacao_id"]
                            for r in item["votacoes_registradas"]
                            if r["voto_valido"]
                        ])
        self.assertTrue(achou, "nenhum voto sem deliberacao nos dados")

    def test_votos_nominais_batem_com_os_votos_validos_da_atuacao(self):
        """Conferencia de 100%: executivo e votos validos da atuacao."""
        validos = votos_validos_da_atuacao()
        conferidos = 0
        for nome in ("executivo_legislatura.json", "proposicoes_legislatura.json"):
            dados = self._carregar(nome)
            for item in dados["todo"]:
                esperado = validos.get(int(item["id"]), 0)
                obtido = len(item["votos_nominais"])
                with self.subTest(arquivo=nome, materia=item["tipo"]):
                    self.assertEqual(
                        obtido, esperado, f"{nome} {item['tipo']} {item['id']}"
                    )
                if item["votacao"] is not None:
                    conferidos += 1
        self.assertTrue(conferidos, "nenhuma materia com voto valido para conferir")

    def test_votos_nominais_do_legislatura_batem_com_a_atuacao(self):
        validos = votos_validos_da_atuacao()
        por_materia: Counter = Counter()
        for vereador in carregar("atuacao_vereadores_legislatura.json").get("vereadores") or []:
            for voto in vereador.get("votos_plex") or []:
                por_materia[int(voto["materia_id"])] += 1
        for materia_id, total in por_materia.items():
            with self.subTest(materia=materia_id):
                self.assertEqual(total, validos.get(materia_id, 0))

    def test_proposicoes_trazem_tema_e_autores(self):
        dados = self._carregar("proposicoes_legislatura.json")
        com_tema = [item for item in dados["todo"] if item.get("tema")]
        self.assertTrue(com_tema, "nenhum item com tema")
        com_autor = [item for item in dados["todo"] if item.get("autores")]
        self.assertTrue(com_autor, "nenhum item com autor vereador")

    def test_executivo_traz_votos_e_vet_traz_rotulo(self):
        dados = self._carregar("executivo_legislatura.json")
        plex = [item for item in dados["todo"] if item.get("tipo_sigla") == "PLEX"]
        self.assertTrue(plex, "sem PLEX no executivo")
        vetoes = [item for item in dados["todo"] if item.get("tipo_sigla") == "VET"]
        self.assertTrue(vetoes, "sem VET no executivo")
        for veto in vetoes:
            self.assertIsNone(veto.get("materia_vetada_id"))
            self.assertTrue(veto.get("materia_vetada_rotulo"))
        siglas = set(tipos_executivo(self.config))
        self.assertEqual({item["tipo_sigla"] for item in dados["todo"]}, siglas)
        for item in dados["todo"]:
            self.assertIn("materia_vetada_rotulo", item)

    def test_votacao_completa_sem_voto_individual_tem_rotulo_proprio(self):
        achou = False
        for _nome, dados in self._todos():
            for item in dados["todo"]:
                if item["votacao"] is None or item["votos_nominais"]:
                    continue
                achou = True
                with self.subTest(materia=item["tipo"]):
                    self.assertEqual(item["votos_nominais_rotulo"], ROTULO_SEM_VOTO_INDIVIDUAL)
                    self.assertFalse(item["votacao"]["voto_individual_registrado"])
        self.assertTrue(achou, "nenhuma votacao sem voto individual nos dados")

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
                for voto in vereador["votos_plex"]:
                    self.assertIn(voto["turno"], ("2o turno", "turno unico"))


if __name__ == "__main__":
    unittest.main()