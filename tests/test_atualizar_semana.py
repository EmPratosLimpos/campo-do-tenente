"""Testes da atualizacao semanal. Nao fazem pedido ao SAPL."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
sys.path.insert(0, str(RAIZ / "coletor"))

from atualizar_semana import (  # noqa: E402
    PREFIXOS_GRANDES_POR_SESSAO,
    TETO_EXECUCAO,
    OrcamentoExecucao,
    ano_corrente_candidato,
    anos_da_execucao,
    confirmar_sessao_ordinaria_no_ano,
    custo_minimo_sessoes,
    incluir_ano_se_confirmado,
    inserir_entrada,
    linhas_contagem,
    montar_entrada,
    plano_sem_listas_grandes,
    sessao_tem_arquivo,
    sessoes_alvo_para_coleta,
    sessoes_novas,
    ultima_sessao_coletada,
)
from coletar_lote import ColetorLote, OrcamentoEsgotado  # noqa: E402

sys.path.insert(0, str(RAIZ / "scripts"))
from so_dados_mudaram import (  # noqa: E402
    arquivos_fora_do_permitido,
    planejar_publicacao,
    so_dados_mudaram,
)

CFG_COLETOR = {
    "cidade": {"nome": "Cidade Teste", "uf": "PR"},
    "sapl": {"endereco_base": "https://exemplo.invalid"},
    "campos_pessoais_removidos": {"lista": ["ip", "user"]},
    "rede": {
        "teto_bytes_resposta": 1024,
        "esquemas_permitidos": ["https"],
        "hosts_permitidos_extra": [],
    },
}
CFG_REDE = CFG_COLETOR["rede"]
CORPO = b'{"pagination":{"total_pages":1},"results":[]}'
HOST_CFGSAPL = "exemplo.invalid"


class Resposta:
    status = 200

    def __init__(self, corpo: bytes, url: str = "https://exemplo.invalid/api/"):
        self.corpo = corpo
        self.url = url

    def geturl(self):
        return self.url

    def read(self, tamanho: int | None = None) -> bytes:
        if tamanho is None:
            return self.corpo
        return self.corpo[:tamanho]

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def cfg_anos(anos, inicio, fim) -> dict:
    return {
        "recorte": {"anos": anos},
        "sapl": {"legislatura_inicio": inicio, "legislatura_fim": fim},
    }


class TestesAnos(unittest.TestCase):
    def test_ano_corrente_nao_entra_sem_confirmacao(self):
        cfg = cfg_anos([2025], 2025, 2028)
        self.assertEqual(anos_da_execucao(cfg, date(2026, 9, 27)), [2025])
        self.assertEqual(ano_corrente_candidato(cfg, date(2026, 9, 27)), 2026)

    def test_ano_fora_da_legislatura_nao_entra(self):
        cfg = cfg_anos([2025], 2025, 2028)
        self.assertEqual(anos_da_execucao(cfg, date(2024, 1, 1)), [2025])
        self.assertEqual(anos_da_execucao(cfg, date(2029, 6, 1)), [2025])
        self.assertIsNone(ano_corrente_candidato(cfg, date(2024, 1, 1)))
        self.assertIsNone(ano_corrente_candidato(cfg, date(2029, 6, 1)))

    def test_ano_que_ja_esta_no_config_nao_repete(self):
        cfg = cfg_anos([2025, 2026], 2025, 2028)
        self.assertEqual(anos_da_execucao(cfg, date(2026, 9, 27)), [2025, 2026])
        self.assertIsNone(ano_corrente_candidato(cfg, date(2026, 9, 27)))

    def test_simulado_nao_consulta_e_nao_acrescenta(self):
        cfg = cfg_anos([2025], 2025, 2028)
        chamadas = []

        def confirmar(ano):
            chamadas.append(ano)
            return True

        anos, mudou = incluir_ano_se_confirmado(cfg, date(2027, 1, 2), True, confirmar)
        self.assertEqual(anos, [2025])
        self.assertFalse(mudou)
        self.assertEqual(chamadas, [])

    def test_sem_sessao_ordinaria_nao_acrescenta(self):
        cfg = cfg_anos([2025], 2025, 2028)
        anos, mudou = incluir_ano_se_confirmado(
            cfg, date(2027, 3, 1), False, lambda _ano: False
        )
        self.assertEqual(anos, [2025])
        self.assertFalse(mudou)

    def test_sessao_ordinaria_confirmada_acrescenta_o_ano(self):
        cfg = cfg_anos([2025], 2025, 2028)
        anos, mudou = incluir_ano_se_confirmado(
            cfg, date(2027, 3, 1), False, lambda _ano: True
        )
        self.assertEqual(anos, [2025, 2027])
        self.assertTrue(mudou)

    def test_um_pedido_com_pausa_confirma_sessao_ordinaria(self):
        dormiu = []
        chamadas = []
        corpo = json.dumps(
            {
                "pagination": {"total_entries": 1, "total_pages": 1},
                "results": [{"id": 10, "tipo": 3, "data_inicio": "2027-02-01"}],
            }
        ).encode("utf-8")

        def urlopen(req, timeout=None):
            del timeout
            chamadas.append(req.full_url)
            return Resposta(corpo)

        with tempfile.TemporaryDirectory() as tmp:
            coletor = ColetorLote(CFG_COLETOR, Path(tmp), teto=10)
            coletor.pular_pausa = False
            with mock.patch("coletar_lote.time.sleep", dormiu.append), mock.patch(
                "coletar_lote.urllib.request.urlopen", urlopen
            ):
                ok = confirmar_sessao_ordinaria_no_ano(coletor, 2027, 3)
        self.assertTrue(ok)
        self.assertEqual(len(chamadas), 1)
        self.assertIn("data_inicio__year=2027", chamadas[0])
        self.assertIn("tipo=3", chamadas[0])
        self.assertIn("page_size=1", chamadas[0])
        self.assertEqual(dormiu, [2.5])

    def test_resposta_sem_ordinaria_nao_confirma(self):
        corpo = json.dumps(
            {
                "pagination": {"total_entries": 1, "total_pages": 1},
                "results": [{"id": 11, "tipo": 9, "data_inicio": "2027-02-01"}],
            }
        ).encode("utf-8")

        def urlopen(req, timeout=None):
            del req, timeout
            return Resposta(corpo)

        with tempfile.TemporaryDirectory() as tmp:
            coletor = ColetorLote(CFG_COLETOR, Path(tmp), teto=10)
            coletor.pular_pausa = False
            with mock.patch("coletar_lote.time.sleep", lambda _segundos: None), mock.patch(
                "coletar_lote.urllib.request.urlopen", urlopen
            ):
                ok = confirmar_sessao_ordinaria_no_ano(coletor, 2027, 3)
        self.assertFalse(ok)


class TestesOrcamento(unittest.TestCase):
    def test_teto_acima_de_400_e_recusado(self):
        with self.assertRaises(ValueError):
            OrcamentoExecucao(TETO_EXECUCAO + 1)

    def test_pausa_entre_pedidos_e_teto_da_execucao(self):
        dormiu = []

        def dormir(segundos):
            dormiu.append(segundos)

        chamadas = {"n": 0}

        def urlopen(*_args, **_kwargs):
            chamadas["n"] += 1
            return Resposta(CORPO)

        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            for nome in ("um.json", "dois.json"):
                (pasta / nome).write_bytes(CORPO)
            orcamento = OrcamentoExecucao(2)
            coletor = ColetorLote(CFG_COLETOR, pasta, teto=10)
            coletor.orcamento_execucao = orcamento
            with mock.patch("coletar_lote.time.sleep", dormir), mock.patch(
                "coletar_lote.urllib.request.urlopen", urlopen
            ):
                coletor.pedir("/api/um/", None, "um.json", refrescar=True)
                coletor.pedir("/api/dois/", None, "dois.json", refrescar=True)
                with self.assertRaises(OrcamentoEsgotado):
                    coletor.pedir("/api/tres/", None, "tres.json", refrescar=True)
            self.assertEqual(chamadas["n"], 2)
            self.assertEqual(dormiu, [2.5])
            self.assertFalse(coletor.gravou)
            self.assertFalse((pasta / "indice.json").exists())
            self.assertEqual((pasta / "um.json").read_bytes(), CORPO)


class TestesRespostaVazia(unittest.TestCase):
    def test_corpo_vazio_gera_falha_e_preserva_o_arquivo_bom(self):
        bom = b'{"pagination": {"total_pages": 1}, "results": [{"id": 1}]}'

        class RespostaVazia:
            status = 200

            def geturl(self):
                return "https://exemplo.invalid/api/"

            def read(self, tamanho=None):
                del tamanho
                return b""

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            (pasta / "lista_p1.json").write_bytes(bom)
            coletor = ColetorLote(CFG_COLETOR, pasta, teto=10)
            with mock.patch(
                "coletar_lote.urllib.request.urlopen", lambda *a, **k: RespostaVazia()
            ), mock.patch("coletar_lote.time.sleep", lambda *a: None):
                with self.assertRaises(SystemExit):
                    coletor.pedir("/api/um/", None, "lista_p1.json", refrescar=True)
            self.assertEqual((pasta / "lista_p1.json").read_bytes(), bom)
            self.assertFalse(coletor.gravou)


class TestesChangelog(unittest.TestCase):
    def test_entrada_usa_os_numeros_recebidos(self):
        entrada = montar_entrada(
            "2026-09-27",
            "https://exemplo.invalid",
            12,
            [{"id": 81, "numero": 40, "data_inicio": "2026-09-20"}],
            ["2026: votações de 10 para 12."],
            ["Hash SHA-256 de atuacao_vereadores_2026.json: abc."],
        )
        self.assertIn("Pedidos ao SAPL nesta execução: 12.", entrada)
        self.assertIn("Sessão ordinária 40, data 2026-09-20 (registro 81).", entrada)
        self.assertIn("votações de 10 para 12.", entrada)
        self.assertNotIn("\u2014", entrada)
        self.assertNotIn("\u2013", entrada)
        texto = "# Registro\n\n---\n\n## 2026-09-01: antiga\n"
        novo = inserir_entrada(texto, entrada)
        self.assertLess(novo.index("atualização semanal"), novo.index("2026-09-01: antiga"))

    def test_contagem_so_lista_o_que_mudou(self):
        linhas = linhas_contagem(
            {"2026": {"sessoes_ordinarias": 33, "votacoes": 10}},
            {"2026": {"sessoes_ordinarias": 33, "votacoes": 12}},
        )
        self.assertEqual(linhas, ["2026: votações de 10 para 12."])


class TestesWorkflow(unittest.TestCase):
    SHA_CHECKOUT = "3d3c42e5aac5ba805825da76410c181273ba90b1"
    SHA_SETUP_PYTHON = "5fda3b95a4ea91299a34e894583c3862153e4b97"

    def test_workflows_nao_usam_node_20_nem_ubuntu_latest(self):
        pasta = RAIZ / ".github" / "workflows"
        for caminho in pasta.glob("*.yml"):
            texto = caminho.read_text(encoding="utf-8")
            self.assertNotIn("ubuntu-latest", texto, caminho.name)
            self.assertIn("ubuntu-24.04", texto, caminho.name)
            self.assertNotIn("actions/checkout@v4", texto, caminho.name)
            self.assertNotIn("actions/setup-python@v5", texto, caminho.name)
            self.assertNotIn("actions/checkout@v7", texto, caminho.name)
            self.assertNotIn("actions/setup-python@v7", texto, caminho.name)
        novo = (pasta / "atualizacao_semanal.yml").read_text(encoding="utf-8")
        self.assertNotIn("\u2014", novo)
        self.assertNotIn("\u2013", novo)

    def test_workflows_fixam_as_acoes_por_sha_comentado(self):
        pasta = RAIZ / ".github" / "workflows"
        for caminho in pasta.glob("*.yml"):
            texto = caminho.read_text(encoding="utf-8")
            self.assertIn(
                f"actions/checkout@{self.SHA_CHECKOUT} # v7",
                texto,
                caminho.name,
            )
            self.assertIn(
                f"actions/setup-python@{self.SHA_SETUP_PYTHON} # v7",
                texto,
                caminho.name,
            )
            for linha in texto.splitlines():
                if "uses: actions/" not in linha:
                    continue
                self.assertRegex(
                    linha.strip(),
                    r"^uses: actions/[a-z-]+@[0-9a-f]{40} # v[0-9]+$",
                    f"{caminho.name}: {linha.strip()}",
                )

    def test_workflow_de_validacao_so_le_e_nao_guarda_token(self):
        texto = (RAIZ / ".github" / "workflows" / "verificar_pr.yml").read_text(encoding="utf-8")
        self.assertIn("permissions:", texto)
        self.assertIn("contents: read", texto)
        self.assertNotIn("contents: write", texto)
        self.assertNotIn("issues: write", texto)
        self.assertNotIn("pull-requests: write", texto)
        self.assertIn("persist-credentials: false", texto)

    def test_atualizacao_semanal_publica_so_dados_na_quarta(self):
        texto = (RAIZ / ".github" / "workflows" / "atualizacao_semanal.yml").read_text(encoding="utf-8")
        self.assertIn("cron: '0 6 * * 3'", texto)
        self.assertIn("Quarta-feira as 03:00", texto)
        self.assertIn("workflow_dispatch:", texto)
        self.assertIn("contents: write", texto)
        self.assertIn("issues: write", texto)
        self.assertNotIn("pull-requests: write", texto)
        self.assertIn("ref: main", texto)
        self.assertIn("fetch-depth: 0", texto)
        self.assertIn("so_dados_mudaram", texto)
        self.assertIn("Atualiza dados ate a sessao ordinaria", texto)
        self.assertIn('user.name "github-actions[bot]"', texto)
        self.assertIn("Atualizacao de dados falhou em", texto)
        self.assertNotIn("com alteracao de codigo em", texto)
        self.assertIn("gh issue create", texto)
        self.assertIn("issue_ja_aberta", texto)
        self.assertIn("alteracao de codigo detectada", texto)
        self.assertIn("Motivo:", texto)
        self.assertNotIn("pr merge", texto)
        self.assertNotIn("push --force", texto)
        self.assertNotIn("atualizacao-dados/", texto)
        self.assertNotIn("--base desenvolvimento", texto)

    def test_workflow_auxiliares_fora_do_repositorio(self):
        texto = (RAIZ / ".github" / "workflows" / "atualizacao_semanal.yml").read_text(encoding="utf-8")
        self.assertIn("$RUNNER_TEMP/mudanca.txt", texto)
        self.assertIn("$RUNNER_TEMP/alterados.txt", texto)
        self.assertIn("$RUNNER_TEMP/atualizacao.log", texto)
        self.assertIn("$RUNNER_TEMP/sanidade.log", texto)
        self.assertIn("$RUNNER_TEMP/testes.log", texto)
        self.assertIn("$RUNNER_TEMP/regras.log", texto)
        self.assertNotIn("tee atualizacao.log", texto)
        self.assertNotIn("tee sanidade.log", texto)
        self.assertNotIn("> mudanca.txt", texto)
        self.assertNotIn("> alterados.txt", texto)
        self.assertIn("git diff --name-only", texto)
        self.assertIn("git ls-files --others --exclude-standard", texto)
        self.assertNotIn("mudanca.txt\" || true", texto)
        self.assertNotIn("alterados.txt\" || true", texto)
        self.assertNotIn("awk '{print $2}'", texto)

    def test_script_nao_fixa_cidade_nem_ano(self):
        texto = (RAIZ / "scripts" / "atualizar_semana.py").read_text(encoding="utf-8")
        self.assertNotIn("campodotenente", texto)
        self.assertNotIn("Campo do Tenente", texto)
        self.assertNotIn("[2025", texto)
        self.assertNotIn("[2026", texto)
        self.assertNotIn("\u2014", texto)
        self.assertNotIn("\u2013", texto)


class TestesSessoesAlvo(unittest.TestCase):
    def _sessoes(self):
        return [
            {"id": 10, "numero": 1, "data_inicio": "2026-02-10"},
            {"id": 11, "numero": 2, "data_inicio": "2026-02-17"},
            {"id": 12, "numero": 3, "data_inicio": "2026-02-24"},
        ]

    def _pasta_com(self, nome, ids_com_arquivo):
        from coletar_por_sessao import RECURSOS

        pasta = Path(self.tmp.name) / nome
        pasta.mkdir(parents=True, exist_ok=True)
        for sid in ids_com_arquivo:
            for _caminho, recurso in RECURSOS:
                (pasta / f"sessao_{sid}_{recurso}_p1.json").write_text(
                    '{"pagination": {"total_pages": 1}, "results": []}',
                    encoding="utf-8",
                )
        return pasta

    def setUp(self):
        import tempfile

        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp = self._tmpdir

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_identifica_novas_e_revisao_da_ultima(self):
        sessoes = self._sessoes()
        pasta = self._pasta_com("por1", [10, 11])
        novas = sessoes_novas(pasta, sessoes)
        self.assertEqual([item["id"] for item in novas], [12])
        ultima = ultima_sessao_coletada(pasta, sessoes)
        self.assertEqual(int(ultima["id"]), 11)
        novas2, alvo = sessoes_alvo_para_coleta(sessoes, pasta)
        self.assertEqual([item["id"] for item in novas2], [12])
        self.assertEqual(sorted(item["id"] for item in alvo), [11, 12])

    def test_sem_nova_ainda_reve_a_ultima_para_lancamento_atrasado(self):
        sessoes = self._sessoes()
        pasta = self._pasta_com("por2", [10, 11, 12])
        novas, alvo = sessoes_alvo_para_coleta(sessoes, pasta)
        self.assertEqual(novas, [])
        self.assertEqual([item["id"] for item in alvo], [12])

    def test_sem_pasta_tudo_e_novo(self):
        sessoes = self._sessoes()
        novas, alvo = sessoes_alvo_para_coleta(sessoes, None)
        self.assertEqual(len(novas), 3)
        self.assertEqual(len(alvo), 3)

    def test_sessao_tem_arquivo_exige_os_quatro(self):
        pasta = Path(self.tmp.name) / "por3"
        pasta.mkdir()
        (pasta / "sessao_99_sessaoplenariapresenca_p1.json").write_text("{}", encoding="utf-8")
        self.assertFalse(sessao_tem_arquivo(pasta, 99))


class TestesCaminhoPorSessao(unittest.TestCase):
    def test_lote_pequeno_pula_listas_grandes(self):
        indice = {
            "sessao/sessaoplenaria": {},
            "sessao/registrovotacao": {},
        }
        plano = plano_sem_listas_grandes([2026], indice)
        prefixos = {item["prefixo"] for item in plano}
        for grande in PREFIXOS_GRANDES_POR_SESSAO:
            self.assertNotIn(grande, prefixos)
        self.assertTrue(any(str(item).startswith("sessaoplenaria_ano") for item in prefixos))

    def test_coleta_nova_usa_caminho_por_sessao(self):
        import atualizar_semana as modulo

        chamadas = []

        def fake_completa(coletor, sid):
            chamadas.append(int(sid))
            return {"sessao_id": int(sid), "n_ordem": 1, "n_registros": 1, "n_votos": 2}

        original = modulo.coletar_sessao_completa
        modulo.coletar_sessao_completa = fake_completa
        try:
            modulo.coletar_sessoes_novas(
                object(),
                [{"id": 50, "numero": 9, "data_inicio": "2026-05-01"}],
            )
        finally:
            modulo.coletar_sessao_completa = original
        self.assertEqual(chamadas, [50])

    def test_por_sessao_tem_mesa_registro_e_voto(self):
        import coletar_por_sessao as por_sessao

        self.assertTrue(hasattr(por_sessao, "pedir_mesa_por_sessao"))
        self.assertTrue(hasattr(por_sessao, "pedir_registros_da_sessao"))
        self.assertTrue(hasattr(por_sessao, "pedir_votos_da_sessao"))
        self.assertTrue(hasattr(por_sessao, "coletar_sessao_completa"))


class TestesSoDados(unittest.TestCase):
    def test_so_dados_com_brutos_tratados_config_e_changelog(self):
        self.assertTrue(
            so_dados_mudaram(
                [
                    "dados/brutos/lote_20260926/ordemdia_p1.json",
                    "dados/tratados/atuacao_vereadores_2026.json",
                    "config_cidade.json",
                    "CHANGELOG.md",
                ]
            )
        )

    def test_tela_nao_e_dado_e_reprova(self):
        self.assertFalse(so_dados_mudaram(["tela/painel.json"]))
        self.assertFalse(
            so_dados_mudaram(
                [
                    "dados/brutos/lote_20260926/ordemdia_p1.json",
                    "tela/painel.json",
                ]
            )
        )
        self.assertEqual(
            arquivos_fora_do_permitido(["tela/painel.json"]),
            ["tela/painel.json"],
        )

    def test_codigo_dentro_de_dados_reprova(self):
        self.assertFalse(so_dados_mudaram(["dados/script.py"]))
        self.assertFalse(so_dados_mudaram(["dados/relatorio.md"]))
        self.assertFalse(so_dados_mudaram(["dados/notas.yml"]))
        self.assertFalse(
            so_dados_mudaram(
                [
                    "dados/brutos/lote_20260926/ordemdia_p1.json",
                    "dados/relatorio.md",
                ]
            )
        )

    def test_relatorio_em_markdown_so_passa_em_dados_tratados(self):
        permitidos = [
            "dados/tratados/RELATORIO-ATUACAO-VEREADORES-2026.md",
            "dados/tratados/RELATORIO-TABELA-VEREADORES.md",
            "dados/tratados/atuacao_vereadores_2026.json",
        ]
        self.assertTrue(so_dados_mudaram(permitidos))
        self.assertEqual(arquivos_fora_do_permitido(permitidos), [])
        reprovados = [
            "dados/relatorio.md",
            "dados/RELATORIO-ATUACAO-VEREADORES-2026.md",
            "dados/brutos/lote_20260926/notas.md",
            "dados/tratados_markdown.md",
        ]
        for nome in reprovados:
            self.assertFalse(so_dados_mudaram([nome]), nome)
            self.assertEqual(arquivos_fora_do_permitido([nome]), [nome], nome)

    def test_cname_do_dominio_proprio_nao_sai_na_atualizacao_semanal(self):
        """O CNAME nao entra no commit do bot: dominio so muda por Pull Request."""
        self.assertFalse(so_dados_mudaram(["CNAME"]))
        self.assertEqual(arquivos_fora_do_permitido(["CNAME"]), ["CNAME"])
        semanal = [
            "dados/brutos/lote_20260927_porsessao/indice.json",
            "dados/tratados/atuacao_vereadores_2026.json",
            "dados/tratados/RELATORIO-ATUACAO-VEREADORES-2026.md",
            "config_cidade.json",
            "CHANGELOG.md",
        ]
        self.assertTrue(so_dados_mudaram(semanal))
        self.assertEqual(arquivos_fora_do_permitido(semanal), [])
        self.assertEqual(
            planejar_publicacao(semanal)["decisao"],
            "publicar",
            "a execucao semanal nao pode ser barrada pelo CNAME",
        )

    def test_workflow_semanal_nao_adiciona_cname_no_commit(self):
        texto = (RAIZ / ".github" / "workflows" / "atualizacao_semanal.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("git add -- dados config_cidade.json CHANGELOG.md", texto)
        for linha in texto.splitlines():
            if linha.strip().startswith("git add"):
                self.assertNotIn("CNAME", linha)
        self.assertNotIn("CNAME", texto)

    def test_dentro_de_dados_somente_extensoes_permitidas(self):
        permitidos = [
            "dados/brutos/lote_20260926/ordemdia_p1.json",
            "dados/brutos/resumo_insumos.json",
            "dados/brutos/materias-2026-resposta-original.csv",
            "dados/tratados/LEIA-ME.txt",
            "dados/tratados/atuacao_vereadores_2026.json.sha256",
        ]
        self.assertTrue(so_dados_mudaram(permitidos))
        self.assertEqual(arquivos_fora_do_permitido(permitidos), [])
        reprovados = [
            "dados/pagina.html",
            "dados/brutos/fotos_vereadores/1.jpg",
            "dados/brutos/lote_20260927_atas/materia_274_texto_original.pdf",
            "dados/icones.svg",
            "dados/arquivo",
            "dados/brutos/lote_20260927_noticia_licenca/noticia.xhtml",
            "dados/brutos/lote_20260927_noticia_licenca/pagina.htm",
        ]
        for nome in reprovados:
            self.assertFalse(so_dados_mudaram([nome]), nome)
            self.assertEqual(arquivos_fora_do_permitido([nome]), [nome], nome)
        self.assertFalse(
            so_dados_mudaram(permitidos + ["dados/brutos/fotos_vereadores/1.jpg"])
        )

    def test_codigo_reprova(self):
        self.assertFalse(so_dados_mudaram(["scripts/atualizar_semana.py"]))
        self.assertFalse(so_dados_mudaram(["index.html"]))
        self.assertFalse(so_dados_mudaram(["tela/patch_dados_camara.js"]))
        self.assertFalse(so_dados_mudaram([".github/workflows/atualizacao_semanal.yml"]))
        self.assertFalse(so_dados_mudaram(["README.md"]))
        fora = arquivos_fora_do_permitido(["dados/x.json", "scripts/y.py"])
        self.assertEqual(fora, ["scripts/y.py"])

    def test_vazio_e_so_dados(self):
        self.assertTrue(so_dados_mudaram([]))

    def test_execucao_tipica_so_com_dados_passsa_e_codigo_reprova(self):
        tipicos = [
            "dados/brutos/lote_20260927_porsessao/sessao_12_ordemdia_p1.json",
            "dados/brutos/lote_20260927_porsessao/indice.json",
            "dados/brutos/resumo_insumos.json",
            "dados/tratados/atuacao_vereadores_2026.json",
            "dados/tratados/atuacao_vereadores_2026.json.sha256",
            "config_cidade.json",
            "CHANGELOG.md",
        ]
        self.assertTrue(so_dados_mudaram(tipicos))
        self.assertEqual(arquivos_fora_do_permitido(tipicos), [])
        self.assertFalse(so_dados_mudaram(tipicos + ["scripts/atualizar_semana.py"]))
        self.assertFalse(
            so_dados_mudaram(tipicos + [".github/workflows/atualizacao_semanal.yml"])
        )


class TestesPlanejarPublicacao(unittest.TestCase):
    def test_sem_mudanca(self):
        plano = planejar_publicacao([])
        self.assertEqual(plano["decisao"], "sem_mudanca")
        self.assertEqual(plano["fora"], [])
        self.assertEqual(plano["total"], 0)

    def test_publicar_so_com_dados(self):
        tipicos = [
            "dados/brutos/lote_20260927_porsessao/sessao_12_ordemdia_p1.json",
            "dados/tratados/atuacao_vereadores_2026.json",
            "config_cidade.json",
            "CHANGELOG.md",
        ]
        plano = planejar_publicacao(tipicos)
        self.assertEqual(plano["decisao"], "publicar")
        self.assertEqual(plano["fora"], [])
        self.assertEqual(plano["total"], len(tipicos))

    def test_bloquear_com_codigo(self):
        plano = planejar_publicacao(["dados/brutos/x.json", "scripts/y.py"])
        self.assertEqual(plano["decisao"], "bloquear")
        self.assertEqual(plano["fora"], ["scripts/y.py"])

    def test_bloquear_codigo_dentro_de_dados_e_tela(self):
        for nome in ("dados/script.py", "dados/relatorio.md", "dados/notas.yml", "tela/painel.json"):
            plano = planejar_publicacao([nome])
            self.assertEqual(plano["decisao"], "bloquear", nome)
            self.assertEqual(plano["fora"], [nome], nome)

    def test_bloquear_extensao_fora_da_lista_permitida_em_dados(self):
        for nome in (
            "dados/brutos/fotos_vereadores/1.jpg",
            "dados/pagina.html",
            "dados/arquivo",
        ):
            plano = planejar_publicacao(["dados/tratados/vereadores.json", nome])
            self.assertEqual(plano["decisao"], "bloquear", nome)
            self.assertEqual(plano["fora"], [nome], nome)


class TestesCustoMinimo(unittest.TestCase):
    def test_piso_por_sessao_soma_recursos_mais_mesa(self):
        import coletar_por_sessao as por_sessao

        piso = len(por_sessao.RECURSOS) + 1
        self.assertEqual(custo_minimo_sessoes(0), 0)
        self.assertEqual(custo_minimo_sessoes(1), piso)
        self.assertEqual(custo_minimo_sessoes(3), 3 * piso)


class ColetorFalsoPorSessao:
    """Simula o SAPL por sessao sem rede, so com arquivos locais."""

    def __init__(self, pasta, registros_por_ordem, votos_por_registro):
        self.pasta = pasta
        self.registros_por_ordem = registros_por_ordem
        self.votos_por_registro = votos_por_registro

    def pedir(self, caminho, params, arquivo, refrescar=False):
        import coletar_por_sessao as por_sessao

        del refrescar
        params = dict(params or {})
        if caminho == por_sessao.CAMINHO_REGISTRO:
            resultados = list(self.registros_por_ordem.get(int(params.get("ordem")), []))
        elif caminho == por_sessao.CAMINHO_VOTO:
            resultados = list(self.votos_por_registro.get(int(params.get("votacao")), []))
        else:
            sid = int(params.get("sessao_plenaria"))
            if "ordemdia" in caminho and "presenca" not in caminho:
                resultados = [
                    {"id": 501, "sessao_plenaria": sid},
                    {"id": 502, "sessao_plenaria": sid},
                ]
            else:
                resultados = [{"id": 900, "sessao_plenaria": sid}]
        dado = {
            "pagination": {
                "total_entries": len(resultados),
                "total_pages": 1,
                "page": 1,
                "links": {"next": None, "previous": None},
                "next_page": None,
            },
            "results": resultados,
        }
        (self.pasta / arquivo).write_text(json.dumps(dado), encoding="utf-8")
        return dado


class TestesRecusaSessaoVazia(unittest.TestCase):
    def _coletor(self, tmp, registros, votos):
        pasta = Path(tmp) / "porsessao"
        pasta.mkdir(parents=True, exist_ok=True)
        return ColetorFalsoPorSessao(pasta, registros, votos)

    def test_ordem_com_itens_e_zero_registros_recusa(self):
        import coletar_por_sessao as por_sessao

        with tempfile.TemporaryDirectory() as tmp:
            coletor = self._coletor(tmp, {}, {})
            with self.assertRaises(SystemExit) as contexto:
                por_sessao.coletar_sessao_completa(coletor, 77)
            mensagem = str(contexto.exception)
            self.assertIn("zero registros", mensagem)
            self.assertIn("Nada foi publicado", mensagem)
            aviso = coletor.pasta / "sessao_77_recusada.json"
            self.assertTrue(aviso.is_file())
            dado = json.loads(aviso.read_text(encoding="utf-8"))
            self.assertEqual(dado["sessao_id"], 77)
            self.assertIn("zero registros", dado["motivo"])

    def test_registros_sem_votos_recusa(self):
        import coletar_por_sessao as por_sessao

        with tempfile.TemporaryDirectory() as tmp:
            coletor = self._coletor(tmp, {501: [{"id": 701}]}, {})
            with self.assertRaises(SystemExit) as contexto:
                por_sessao.coletar_sessao_completa(coletor, 78)
            mensagem = str(contexto.exception)
            self.assertIn("zero votos", mensagem)
            self.assertIn("Nada foi publicado", mensagem)
            aviso = coletor.pasta / "sessao_78_recusada.json"
            self.assertTrue(aviso.is_file())

    def test_recusa_restaura_consolidado_previo(self):
        import coletar_por_sessao as por_sessao

        with tempfile.TemporaryDirectory() as tmp:
            coletor = self._coletor(tmp, {}, {})
            previo_registro = coletor.pasta / "sessao_79_registrovotacao_p1.json"
            previo_voto = coletor.pasta / "sessao_79_votoparlamentar_p1.json"
            previo_registro.write_bytes(b"REGISTRO BOM")
            previo_voto.write_bytes(b"VOTO BOM")
            with self.assertRaises(SystemExit):
                por_sessao.coletar_sessao_completa(coletor, 79)
            self.assertEqual(previo_registro.read_bytes(), b"REGISTRO BOM")
            self.assertEqual(previo_voto.read_bytes(), b"VOTO BOM")

    def test_caminho_feliz_devolve_contagens_sem_aviso(self):
        import coletar_por_sessao as por_sessao

        registros = {501: [{"id": 701}], 502: []}
        votos = {701: [{"id": 801}, {"id": 802}]}
        with tempfile.TemporaryDirectory() as tmp:
            coletor = self._coletor(tmp, registros, votos)
            resumo = por_sessao.coletar_sessao_completa(coletor, 80)
            self.assertEqual(resumo["n_ordem"], 2)
            self.assertEqual(resumo["n_registros"], 1)
            self.assertEqual(resumo["n_votos"], 2)
            self.assertFalse((coletor.pasta / "sessao_80_recusada.json").exists())


class TestesDerivacaoTolerante(unittest.TestCase):
    def test_sem_consolidado_devolve_vazio_sem_erro(self):
        from derivar_insumos import ler_consolidados_por_sessao

        with tempfile.TemporaryDirectory() as tmp:
            linhas, nomes = ler_consolidados_por_sessao(Path(tmp), "registrovotacao")
        self.assertEqual(linhas, [])
        self.assertEqual(nomes, [])

    def test_aviso_de_recusa_nao_entra_na_derivacao(self):
        from derivar_insumos import ler_consolidados_por_sessao

        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            (pasta / "sessao_77_recusada.json").write_text(
                '{"sessao_id": 77}', encoding="utf-8"
            )
            linhas, nomes = ler_consolidados_por_sessao(pasta, "registrovotacao")
        self.assertEqual(linhas, [])
        self.assertEqual(nomes, [])


class TesteSimulado(unittest.TestCase):
    def test_simulado_nao_altera_nada_quando_nao_ha_dado_novo(self):
        def porcelana() -> str:
            resultado = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=RAIZ,
                capture_output=True,
                text=True,
                check=True,
            )
            return resultado.stdout

        antes = porcelana()
        resultado = subprocess.run(
            [sys.executable, str(RAIZ / "scripts" / "atualizar_semana.py"), "--simulado"],
            cwd=RAIZ,
            capture_output=True,
            text=True,
        )
        self.assertEqual(resultado.returncode, 0, resultado.stdout + "\n" + resultado.stderr)
        self.assertIn("Pedidos nesta execucao: 0", resultado.stdout)
        self.assertIn("Sessoes ordinarias novas: 0", resultado.stdout)
        self.assertIn("Nada mudou.", resultado.stdout)
        self.assertNotIn("pedido de rede bloqueado", resultado.stdout + resultado.stderr)
        self.assertEqual(porcelana(), antes)


if __name__ == "__main__":
    unittest.main()
