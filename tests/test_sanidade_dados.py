import json
import pathlib
import sys
import unittest

DIR_RAIZ = pathlib.Path(__file__).resolve().parent.parent
if str(DIR_RAIZ / "coletor") not in sys.path:
    sys.path.insert(0, str(DIR_RAIZ / "coletor"))

from config_cidade import (  # noqa: E402
    PisoNaoDefinido,
    anos_recorte,
    carregar_config,
    exigir_piso,
    pisos_sanidade,
)

CAMPOS_VOTO = (
    "sim",
    "nao",
    "abstencao",
    "nao_votou",
    "presidente_que_nao_votou",
    "ausente_com_justificativa",
    "ausente_sem_justificativa",
    "fora_do_mandato",
    "presente_sem_voto_individual_registrado",
    "total_registros",
    "nominais",
)
CAMPOS_PRESENCA = (
    "presencas",
    "faltas_com_justificativa",
    "faltas_sem_justificativa",
    "taxa_presenca",
    "percentual_faltas",
    "sessoes_ordinarias",
    "sessoes_licenca",
    "por_sessao",
)


def tem_chave_ip(obj) -> bool:
    if isinstance(obj, dict):
        if "ip" in obj:
            return True
        return any(tem_chave_ip(valor) for valor in obj.values())
    if isinstance(obj, list):
        return any(tem_chave_ip(valor) for valor in obj)
    return False


class TestSanidadeDados(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.config = carregar_config()
        cls.anos = anos_recorte(cls.config)
        cls.pisos = {ano: pisos_sanidade(ano, cls.config) for ano in cls.anos}
        cls.dir_tratados = DIR_RAIZ / "dados" / "tratados"
        cls.dir_brutos = DIR_RAIZ / "dados" / "brutos"
        cls.datasets = []
        for ano in cls.anos:
            caminho = cls.dir_tratados / f"atuacao_vereadores_{ano}.json"
            cls.datasets.append((ano, caminho))

    def _carregar(self, caminho: pathlib.Path) -> dict:
        self.assertTrue(caminho.exists(), f"Arquivo nao encontrado: {caminho.name}")
        bruto = caminho.read_bytes()
        self.assertNotIn(b"\r", bruto, f"{caminho.name} nao esta em LF")
        return json.loads(bruto.decode("utf-8"))

    def test_arquivo_existe_e_eh_json_valido(self):
        self.assertTrue(self.datasets, "config sem anos de recorte")
        for ano, caminho in self.datasets:
            with self.subTest(ano=ano):
                dados = self._carregar(caminho)
                self.assertIsInstance(dados, dict, f"JSON invalido em {caminho.name}")
                self.assertIn("meta", dados)
                self.assertIn("vereadores", dados)
                self.assertIn("votacoes", dados)

    def test_contem_o_numero_esperado_de_vereadores(self):
        for ano, caminho in self.datasets:
            with self.subTest(ano=ano):
                dados = self._carregar(caminho)
                try:
                    esperado = exigir_piso("vereadores", self.pisos[ano]["vereadores"], ano)
                except PisoNaoDefinido as erro:
                    self.fail(str(erro))
                vereadores = dados.get("vereadores", [])
                self.assertEqual(
                    len(vereadores),
                    esperado,
                    f"{caminho.name}: esperado exatamente {esperado} vereadores",
                )
                self.assertEqual(dados["meta"].get("n_vereadores"), esperado)

    def test_sessoes_e_projetos_respeitam_o_piso_minimo(self):
        for ano, caminho in self.datasets:
            with self.subTest(ano=ano):
                dados = self._carregar(caminho)
                meta = dados["meta"]
                try:
                    piso_sessoes = exigir_piso(
                        "sessoes_ordinarias", self.pisos[ano]["sessoes_ordinarias"], ano
                    )
                    piso_projetos = exigir_piso(
                        "projetos_lei_legislativo_e_executivo",
                        self.pisos[ano]["projetos_lei_legislativo_e_executivo"],
                        ano,
                    )
                except PisoNaoDefinido as erro:
                    self.fail(str(erro))
                self.assertGreaterEqual(int(meta["n_sessoes_ordinarias"]), piso_sessoes)
                self.assertGreaterEqual(
                    int(meta["n_projetos_lei_legislativo_e_executivo"]),
                    piso_projetos,
                )
                self.assertGreater(int(meta["n_registros_votacao"]), 0)

    def test_campos_obrigatorios_de_voto(self):
        for ano, caminho in self.datasets:
            dados = self._carregar(caminho)
            vereadores = dados.get("vereadores", [])
            self.assertTrue(vereadores, f"{caminho.name}: lista de vereadores vazia")
            for vereador in vereadores:
                with self.subTest(ano=ano, vereador=vereador.get("id_sapl")):
                    self.assertIn("votos", vereador)
                    votos = vereador["votos"]
                    for campo in CAMPOS_VOTO:
                        self.assertIn(campo, votos)
                        self.assertIsNotNone(votos[campo])

    def test_campos_obrigatorios_de_presenca(self):
        for ano, caminho in self.datasets:
            dados = self._carregar(caminho)
            vereadores = dados.get("vereadores", [])
            self.assertTrue(vereadores, f"{caminho.name}: lista de vereadores vazia")
            for vereador in vereadores:
                with self.subTest(ano=ano, vereador=vereador.get("id_sapl")):
                    self.assertIn("presenca", vereador)
                    presenca = vereador["presenca"]
                    for campo in CAMPOS_PRESENCA:
                        self.assertIn(campo, presenca)
                        self.assertIsNotNone(presenca[campo])

    def test_data_de_coleta_e_lacuna_e_links(self):
        for ano, caminho in self.datasets:
            with self.subTest(ano=ano):
                dados = self._carregar(caminho)
                meta = dados["meta"]
                self.assertIsInstance(meta.get("dado_coletado_em"), str)
                self.assertTrue(meta["dado_coletado_em"].strip())
                contagem = json.loads(
                    (self.dir_brutos / f"contagem_votacoes_ordinarias_{ano}.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertEqual(
                    meta.get("lacuna_sessoes_ordinarias"),
                    contagem.get("lacuna_sessoes_ordinarias"),
                )
                self.assertFalse(tem_chave_ip(dados))
                for votacao in dados["votacoes"]:
                    self.assertTrue(votacao.get("link_sessao"))
                    if votacao.get("materia_id") is not None:
                        self.assertTrue(votacao.get("link_materia"))
                    if votacao.get("voto_individual_registrado"):
                        self.assertEqual(
                            len(votacao["estados_por_vereador"]),
                            len(dados["vereadores"]),
                        )
                    else:
                        self.assertIsNone(votacao["estados_por_vereador"])
                        self.assertEqual(
                            votacao.get("rotulo"),
                            contagem.get("rotulo_sem_voto_individual"),
                        )
                for projeto in dados["projetos_lei"]:
                    self.assertTrue(projeto.get("link_sapl"))

    def test_grade_fecha_com_afastamento(self):
        for ano, caminho in self.datasets:
            with self.subTest(ano=ano):
                dados = self._carregar(caminho)
                meta = dados["meta"]
                soma = (
                    int(meta["n_presencas"])
                    + int(meta["n_faltas_com_justificativa"])
                    + int(meta["n_faltas_sem_justificativa"])
                    + int(meta["n_sessoes_licenca"])
                    + int(meta["n_sessoes_fora_do_mandato"])
                )
                self.assertEqual(
                    soma,
                    int(meta["n_sessoes_ordinarias"]) * int(meta["n_vereadores"]),
                )

    def test_afastamento_manual_conta_como_falta_com_justificativa(self):
        caminho = self.dir_tratados / "afastamentos_manuais.json"
        self.assertTrue(caminho.exists(), "afastamentos_manuais.json ausente")
        manuais = json.loads(caminho.read_text(encoding="utf-8"))
        por_ano = {ano: self._carregar(arquivo) for ano, arquivo in self.datasets}
        for afastamento in manuais.get("afastamentos") or []:
            parlamentar_id = int(afastamento["parlamentar_id_sapl"])
            inicio = afastamento["data_inicio"]
            fim = afastamento["data_fim"]
            for ano, dados in por_ano.items():
                pessoa = next(
                    (
                        item
                        for item in dados["vereadores"]
                        if int(item["id_sapl"]) == parlamentar_id
                    ),
                    None,
                )
                if pessoa is None:
                    continue
                datas = [item["data"] for item in dados.get("sessoes") or []]
                if not any(inicio <= data <= fim for data in datas):
                    continue
                with self.subTest(ano=ano, parlamentar=parlamentar_id):
                    no_intervalo = [
                        item
                        for item in pessoa["presenca"]["por_sessao"]
                        if inicio <= item["data_sessao"] <= fim
                    ]
                    self.assertTrue(no_intervalo)
                    for item in no_intervalo:
                        self.assertEqual(item["situacao"], "falta_com_justificativa")
                        self.assertEqual(item["fonte"], afastamento["fonte"])
                        self.assertEqual(
                            item["fonte_oficial_encontrada"],
                            afastamento["fonte_oficial_encontrada"],
                        )
                        motivo = item.get("motivo_ausencia") or {}
                        self.assertEqual(
                            motivo.get("motivo"), afastamento["rotulo"]
                        )
                    faltas_no_intervalo = [
                        item
                        for item in no_intervalo
                        if item["situacao"] == "falta_sem_justificativa"
                    ]
                    self.assertEqual(faltas_no_intervalo, [])
                    votos_no_intervalo = [
                        item
                        for item in pessoa["votos"]["nominais"]
                        if inicio <= item["data_sessao"] <= fim
                        and item.get("voto_texto_sapl") is None
                    ]
                    for item in votos_no_intervalo:
                        self.assertEqual(item["estado"], "ausente_com_justificativa")
                        self.assertEqual(
                            item["fonte_oficial_encontrada"],
                            afastamento["fonte_oficial_encontrada"],
                        )


    def test_catalogo_tipos_materia_vem_do_sapl(self):
        lote = sorted((self.dir_brutos / ".").glob("lote_*/tipomaterialegislativa_p1.json"))
        self.assertTrue(lote, "tabela tipomaterialegislativa ausente em dados/brutos")
        tabela = json.loads(lote[-1].read_text(encoding="utf-8"))
        esperado = {}
        for item in tabela.get("results") or []:
            sigla = str(item.get("sigla") or "").strip()
            descricao = str(item.get("descricao") or "").strip()
            if sigla and descricao:
                esperado[sigla] = descricao
        self.assertIn("PLEG", esperado)
        self.assertIn("PLEX", esperado)
        for ano, caminho in self.datasets:
            with self.subTest(ano=ano):
                dados = self._carregar(caminho)
                catalogo = (dados.get("meta") or {}).get("catalogo_tipos_materia") or {}
                for sigla in ("PLEG", "PLEX"):
                    self.assertEqual(catalogo.get(sigla), esperado.get(sigla))
                for projeto in dados.get("projetos_lei") or []:
                    sigla = projeto.get("tipo_sigla")
                    self.assertIn(sigla, ("PLEG", "PLEX"))
                    self.assertEqual(projeto.get("tipo_descricao"), esperado.get(sigla))


class TestSemCampoPessoalEmDados(unittest.TestCase):
    """Nenhum campo pessoal do SAPL pode ficar em dados/ (SEG2)."""

    def test_nenhum_arquivo_de_dados_tem_campo_pessoal(self):
        from testes_sanidade import arquivo_com_campo_pessoal

        self.assertEqual(arquivo_com_campo_pessoal(), [])

    def test_a_trava_encontra_campo_pessoal_em_qualquer_nivel(self):
        from testes_sanidade import arquivo_com_campo_pessoal, campos_pessoais
        from config_cidade import carregar_config, remover_campos_pessoais

        cfg = carregar_config()
        chaves = campos_pessoais(cfg)
        pasta = DIR_RAIZ / "dados" / "brutos" / "lote_tmp_seg2_pessoal"
        pasta.mkdir(parents=True, exist_ok=True)
        try:
            for nome in ("a.json", "b.json"):
                (pasta / nome).write_text(
                    json.dumps({"results": [{"id": 1, chaves[0]: "10.0.0.1"}]}),
                    encoding="utf-8",
                )
            achados = arquivo_com_campo_pessoal()
            self.assertEqual(len(achados), 2, achados)
            limpo = remover_campos_pessoais({"id": 1, chaves[1]: 5}, cfg)
            self.assertEqual(limpo, {"id": 1})
        finally:
            for arquivo in sorted(pasta.glob("*")):
                arquivo.unlink()
            pasta.rmdir()
        self.assertEqual(arquivo_com_campo_pessoal(), [])

    def test_lista_vem_do_config(self):
        from config_cidade import campos_pessoais, carregar_config

        cfg = carregar_config()
        lista = campos_pessoais(cfg)
        self.assertEqual(lista, ["ip", "user"])
        for chave in lista:
            self.assertIsInstance(chave, str)
            self.assertTrue(chave.strip())
        self.assertNotIn("nome_parlamentar", lista)

    def test_remocao_no_texto_preserva_o_formato(self):
        from config_cidade import carregar_config, remover_campos_pessoais_do_texto

        cfg = carregar_config()
        casos = {
            '{"a":1,"ip":"1.2.3.4","b":2}': '{"a":1,"b":2}',
            '{"a":1,"user":5}': '{"a":1}',
            '{"ip":"1.2.3.4"}': "{}",
            '{\n  "a": 1,\n  "ip": "x",\n  "b": 2\n}': '{\n  "a": 1,\n  "b": 2\n}',
            '{\n  "a": 1,\n  "b": 2,\n  "user": 7\n}': '{\n  "a": 1,\n  "b": 2\n}',
            '{"n":{"ip":1,"user":2}}': '{"n":{}}',
            '{"a":1,"user":2,"ip":3}': '{"a":1}',
        }
        for entrada, esperado in casos.items():
            with self.subTest(entrada=entrada):
                saida = remover_campos_pessoais_do_texto(entrada, cfg)
                self.assertEqual(saida, esperado)
                self.assertEqual(json.loads(saida), json.loads(esperado))
        sem_chave = '{"a":1,"b":"ip e user dentro do texto"}'
        self.assertEqual(remover_campos_pessoais_do_texto(sem_chave, cfg), sem_chave)

    def test_todo_coletor_grava_pelo_coletor_com_a_remocao(self):
        """Nenhum coletor abre conexao fora do ColetorLote."""
        coletor = DIR_RAIZ / "coletor"
        nomes = (
            "coletar_tramitacao.py",
            "sondar_tramitacao.py",
            "coletar_por_sessao.py",
            "coletar_autoria.py",
        )
        for nome in nomes:
            caminho = coletor / nome
            if not caminho.is_file():
                continue
            with self.subTest(arquivo=nome):
                texto = caminho.read_text(encoding="utf-8")
                self.assertIn("ColetorLote", texto)
                self.assertNotIn("urlopen(", texto)
                self.assertNotIn("requests.get(", texto)
                self.assertNotIn(".get(url", texto)

    def test_coletores_de_tramitacao_nao_gravam_resposta_por_conta_propria(self):
        coletor = DIR_RAIZ / "coletor"
        for nome in ("coletar_tramitacao.py", "sondar_tramitacao.py"):
            caminho = coletor / nome
            if not caminho.is_file():
                continue
            with self.subTest(arquivo=nome):
                texto = caminho.read_text(encoding="utf-8")
                self.assertNotIn("write_bytes(", texto)
                self.assertNotIn("write_text(", texto)
                self.assertNotIn("open(", texto)

    def test_coletor_lote_usa_a_remocao_antes_de_gravar(self):
        from coletar_lote import limpar_resposta
        from config_cidade import carregar_config

        cfg = carregar_config()
        corpo = b'{"results":[{"id":1,"ip":"10.0.0.1","user":5}],"total":1}'
        saida = limpar_resposta(corpo, cfg)
        self.assertEqual(
            json.loads(saida.decode("utf-8")),
            {"results": [{"id": 1}], "total": 1},
        )
        sem_campo = b'{"results":[{"id":1}]}'
        self.assertEqual(limpar_resposta(sem_campo, cfg), sem_campo)
        self.assertEqual(limpar_resposta(b"", cfg), b"")


class TestSemPaginaEmDados(unittest.TestCase):
    """Nenhuma pagina de terceiro pode ser versionada dentro de dados/."""

    def test_nenhuma_pagina_em_dados(self):
        from testes_sanidade import pagina_versionada_em_dados

        self.assertEqual(pagina_versionada_em_dados(), [])

    def test_a_trava_encontra_qualquer_pagina(self):
        from testes_sanidade import pagina_versionada_em_dados

        pasta = DIR_RAIZ / "dados" / "brutos" / "lote_tmp_seg2"
        pasta.mkdir(parents=True, exist_ok=True)
        try:
            for nome in ("pagina.html", "pagina.htm", "pagina.xhtml", "icone.svg"):
                (pasta / nome).write_text("conteudo", encoding="utf-8")
            achados = pagina_versionada_em_dados()
            self.assertEqual(len(achados), 4)
            for nome in ("pagina.html", "pagina.htm", "pagina.xhtml", "icone.svg"):
                self.assertIn(f"dados/brutos/lote_tmp_seg2/{nome}", achados)
        finally:
            for arquivo in sorted(pasta.glob("*")):
                arquivo.unlink()
            pasta.rmdir()
        self.assertEqual(pagina_versionada_em_dados(), [])

    def test_noticia_da_licenca_ficou_em_json(self):
        pasta = DIR_RAIZ / "dados" / "brutos" / "lote_20260927_noticia_licenca"
        self.assertTrue((pasta / "noticia.json").is_file())
        self.assertFalse((pasta / "noticia.html").exists())
        noticia = json.loads((pasta / "noticia.json").read_text(encoding="utf-8"))
        for chave in ("url_oficial", "titulo", "data", "trecho"):
            self.assertTrue(str(noticia.get(chave) or "").strip(), chave)
        self.assertTrue(noticia["url_oficial"].startswith("https://"))
        tratado = json.loads(
            (DIR_RAIZ / "dados" / "tratados" / "afastamentos_manuais.json").read_text(
                encoding="utf-8"
            )
        )
        afastamento = tratado["afastamentos"][0]
        self.assertEqual(noticia["url_oficial"], afastamento["link_fonte"])
        self.assertEqual(noticia["trecho"], afastamento["trecho"])


if __name__ == "__main__":
    unittest.main()
