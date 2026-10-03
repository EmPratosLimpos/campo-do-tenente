"""Testes do endereco publico do painel.

O site e servido pelo GitHub Pages com o dominio proprio empratoslimpos.com.
O arquivo CNAME na raiz, criado pelo GitHub, diz qual e esse dominio.
O endereco antigo, no endereco do projeto no GitHub, nao pode sobrar em
nenhum arquivo versionado, fora das respostas brutas do SAPL e do
historico do CHANGELOG.
"""

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

DOMINIO_PROPRIO = "empratoslimpos.com"
ENDERECO_PUBLICO = f"https://{DOMINIO_PROPRIO}/"
# Montado em partes: assim o endereco antigo nao fica escrito neste arquivo e
# a varredura do repositorio inteiro nao acha a si mesma.
HOST_ANTIGO = "empratoslimpos" + ".github.io"
ENDERECO_ANTIGO = HOST_ANTIGO + "/campo-do-tenente"

# Documentos de historico: registram o que foi publicado no passado e nao
# descrevem o endereco de hoje.
HISTORICOS = frozenset({"CHANGELOG.md"})
PREFIXO_BRUTOS = "dados/brutos/"


def arquivos_versionados() -> list[str]:
    res = subprocess.run(
        ["git", "ls-files"],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=True,
    )
    return [linha.strip() for linha in res.stdout.splitlines() if linha.strip()]


def arquivos_com_texto(agulha: str) -> list[str]:
    """Lista os arquivos versionados de texto que contem a agulha.

    O -I do git grep deixa de fora os arquivos binarios (fotos, pdf, docx),
    que nao tem endereco de site para conferir. O codigo 1 do git grep
    significa que nada foi encontrado.
    """
    res = subprocess.run(
        ["git", "grep", "-I", "-l", "--", agulha],
        cwd=RAIZ,
        capture_output=True,
        text=True,
    )
    if res.returncode not in (0, 1):
        raise AssertionError(f"git grep falhou: {res.stderr.strip()}")
    return sorted(linha.strip() for linha in res.stdout.splitlines() if linha.strip())


class TestCname(unittest.TestCase):
    def test_cname_existe_na_raiz(self):
        caminho = RAIZ / "CNAME"
        self.assertTrue(caminho.is_file(), "CNAME ausente na raiz do repositorio")

    def test_cname_tem_so_o_dominio_proprio(self):
        conteudo = (RAIZ / "CNAME").read_text(encoding="utf-8")
        linhas = [linha.strip() for linha in conteudo.splitlines() if linha.strip()]
        self.assertEqual(linhas, [DOMINIO_PROPRIO])

    def test_cname_e_o_arquivo_do_github_e_nao_esta_ignorado(self):
        res = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "CNAME"],
            cwd=RAIZ,
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0, "CNAME precisa estar versionado")


class TestEnderecoNoConfig(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        caminho = RAIZ / "config_cidade.json"
        cls.config = json.loads(caminho.read_text(encoding="utf-8"))

    def test_endereco_publico_e_o_dominio_proprio(self):
        self.assertEqual(self.config["painel"]["endereco_publico"], ENDERECO_PUBLICO)

    def test_endereco_publico_usa_https(self):
        self.assertTrue(self.config["painel"]["endereco_publico"].startswith("https://"))

    def test_config_nao_guarda_o_endereco_antigo(self):
        bruto = (RAIZ / "config_cidade.json").read_text(encoding="utf-8")
        self.assertNotIn(ENDERECO_ANTIGO, bruto)


class TestEnderecoNaTela(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = (RAIZ / "index.html").read_text(encoding="utf-8")

    def test_index_nao_guarda_o_endereco_antigo(self):
        self.assertNotIn(HOST_ANTIGO, self.index)

    def test_cabecalho_impresso_mostra_o_dominio_proprio(self):
        self.assertIn("ENDERECO_EXIBIDO", self.index)
        self.assertIn("preencherFolhaImpressao", self.index)
        self.assertIn("ENDERECO_EXIBIDO = PORTAL_OFICIAL.replace", self.index)

    def test_trava_de_moldura_aponta_para_o_dominio_proprio(self):
        self.assertIn(f'lk.href = "{ENDERECO_PUBLICO}";', self.index)

    def test_compartilhamento_vem_do_config_e_nao_do_codigo(self):
        """O texto de compartilhamento tem de sair do endereco do config."""
        self.assertIn("PORTAL_OFICIAL = cfg.painel.endereco_publico", self.index)
        self.assertIn('return PORTAL_OFICIAL + "#vereadores";', self.index)
        self.assertIn("linkCompartilharSite", self.index)

    def test_csp_nao_traz_endereco_do_site(self):
        """A CSP estrita fica em 'self': o dominio publico do painel nao entra nela."""
        linhas = [linha for linha in self.index.splitlines() if "Content-Security-Policy" in linha]
        self.assertEqual(len(linhas), 1, "esperado uma unica CSP no index.html")
        csp = linhas[0]
        self.assertNotIn(DOMINIO_PROPRIO, csp)
        self.assertNotIn("github.io", csp)
        self.assertIn("default-src 'self'", csp)
        self.assertIn("frame-src 'none'", csp)


class TestEnderecoAntigoSumiuDoRepositorio(unittest.TestCase):
    def test_endereco_antigo_so_fica_em_bruto_e_historico(self):
        achados = arquivos_com_texto(ENDERECO_ANTIGO)
        fora = [
            nome
            for nome in achados
            if nome not in HISTORICOS and not nome.startswith(PREFIXO_BRUTOS)
        ]
        self.assertEqual(fora, [], f"endereco antigo fora do permitido: {fora}")


if __name__ == "__main__":
    unittest.main()
