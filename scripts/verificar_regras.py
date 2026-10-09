#!/usr/bin/env python3
"""
Script de verificacao compulsoria de regras de governanca e sanidade.
Executado localmente por qualquer agente ou desenvolvedor antes de commits.
"""

import hashlib
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT / "coletor") not in sys.path:
    sys.path.insert(0, str(ROOT / "coletor"))

from config_cidade import anos_recorte, carregar_config  # noqa: E402

from marcas_ia import verificar_commits_marcas_ia  # noqa: E402


def main():
    erros = []
    print("=======================================================")
    print("Verificando conformidade com as regras de governanca...")
    print("=======================================================\n")

    config = carregar_config()
    anos = anos_recorte(config)

    # 1. Verificar branch atual
    res = subprocess.run(["git", "branch", "--show-current"], cwd=ROOT, capture_output=True, text=True)
    branch = res.stdout.strip()
    print(f"Branch atual: {branch}")
    if branch == "main":
        erros.append("VIOLACAO: Nao e permitido realizar trabalho ou commits diretamente na branch 'main'!")

    # 2. Testes de sanidade de dados
    print("\nExecutando coletor/testes_sanidade.py...")
    res = subprocess.run([sys.executable, "coletor/testes_sanidade.py"], cwd=ROOT, capture_output=True, text=True)
    if res.returncode != 0:
        erros.append(f"FALHA nos testes de sanidade:\n{res.stdout}\n{res.stderr}")
    else:
        print("OK: Testes de sanidade passaram.")

    # 3. Testes unitarios
    print("\nExecutando unittest em tests/...")
    res = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=ROOT, capture_output=True, text=True)
    if res.returncode != 0:
        erros.append(f"FALHA nos testes unitarios:\n{res.stdout}\n{res.stderr}")
    else:
        print("OK: Testes unitarios passaram.")

    # 4. Hash de integridade
    print("\nVerificando hash SHA256...")
    hashes_vistos = 0
    for ano in anos:
        json_path = ROOT / "dados" / "tratados" / f"atuacao_vereadores_{ano}.json"
        hash_path = ROOT / "dados" / "tratados" / f"atuacao_vereadores_{ano}.json.sha256"
        if json_path.exists() and hash_path.exists():
            hashes_vistos += 1
            h = hashlib.sha256(json_path.read_bytes()).hexdigest()
            saved = hash_path.read_text(encoding="utf-8").strip()
            if h != saved:
                erros.append(
                    f"FALHA no hash SHA256 de {ano}: Calculado {h} != Salvo {saved}. "
                    "Execute python coletor/gerar_hash_integridade.py"
                )
            else:
                print(f"OK: Hash SHA256 de {ano} integro.")
        elif json_path.exists() and not hash_path.exists():
            erros.append(
                f"Arquivo de hash ausente para {ano}. "
                "Execute python coletor/gerar_hash_integridade.py"
            )
        else:
            erros.append(
                f"Consolidado de {ano} ausente. "
                "Rode python dados/tratados/gerar_atuacao_vereadores.py"
            )
    if hashes_vistos != len(anos):
        erros.append(
            f"Hashes conferidos: {hashes_vistos}. Anos do config: {len(anos)}."
        )

    # 5. Marcas de ferramentas de IA em mensagens de commit
    print("\nVerificando ausencia de marcas de IA em commits recentes...")
    erros_marcas, avisos_marcas = verificar_commits_marcas_ia(ROOT)
    for aviso in avisos_marcas:
        print(f"AVISO: {aviso}")
    if erros_marcas:
        erros.extend(erros_marcas)
    elif not avisos_marcas:
        print("OK: Nenhuma marca de IA nas mensagens verificadas.")

    # 6. Higiene de travessoes em documentacao
    print("\nVerificando ausencia de caracteres de travessao proibidos...")
    arquivos_norma = [
        "AGENTS.md",
        "CLAUDE.md",
        ".cursorrules",
        "PROCESSO_DESENVOLVIMENTO_E_GOVERNANCA.md",
        "index.html",
        "app.js",
        "estilo.css",
        "README.md",
        "ARCHITECTURE.md",
        "CHANGELOG.md",
    ]
    for nome in arquivos_norma:
        arq = ROOT / nome
        if arq.exists():
            conteudo = arq.read_text(encoding="utf-8")
            if re.search("[\u2014\u2013]", conteudo):
                erros.append(f"VIOLACAO: Caractere travessao encontrado em {nome}!")
            else:
                print(f"OK: {nome} limpo.")

    # 7. Rodada da votacao popular sem autor e so com sigla elegivel
    print("\nVerificando rodada da votacao popular...")
    rodada_path = ROOT / "dados" / "tratados" / "votacao_rodada.json"
    if not rodada_path.is_file():
        erros.append(
            "Arquivo dados/tratados/votacao_rodada.json ausente. "
            "Rode python dados/tratados/gerar_rodada_votacao.py"
        )
    else:
        try:
            rodada = rodada_path.read_text(encoding="utf-8")
            if "\r" in rodada:
                raise ValueError("fim de linha CR")
            rodada = json.loads(rodada)
        except (ValueError, UnicodeDecodeError) as exc:
            erros.append(f"Rodada da votacao com JSON invalido: {exc}.")
            rodada = None
        if isinstance(rodada, dict):
            for chave in (
                "rodada_id",
                "sessao_id",
                "data_sessao",
                "status",
                "fecha_ate",
                "materias",
                "gerado_de",
            ):
                if chave not in rodada:
                    erros.append(f"Rodada da votacao sem a chave {chave}.")
            if rodada.get("status") not in ("aberta", "sem_materias_elegiveis"):
                erros.append(
                    f"Status da rodada invalido: {rodada.get('status')!r}."
                )
            proibidas = ("autor", "partido", "vereador")

            def chaves_proibidas(valor, caminho="raiz"):
                achadas = []
                if isinstance(valor, dict):
                    for chave, item in valor.items():
                        if any(parte in str(chave).lower() for parte in proibidas):
                            achadas.append(f"{caminho}.{chave}")
                        achadas.extend(chaves_proibidas(item, f"{caminho}.{chave}"))
                elif isinstance(valor, list):
                    for posicao, item in enumerate(valor):
                        achadas.extend(chaves_proibidas(item, f"{caminho}[{posicao}]"))
                return achadas

            achadas = chaves_proibidas(rodada)
            if achadas:
                erros.append(
                    "Rodada da votacao com chave de autor, partido ou vereador: "
                    + ", ".join(sorted(set(achadas)))
                    + "."
                )
            elegiveis = set((config.get("votacao_popular") or {}).get("siglas_elegiveis") or [])
            excluidas = set((config.get("votacao_popular") or {}).get("siglas_excluidas") or [])
            materias = rodada.get("materias")
            if not isinstance(materias, list):
                erros.append("Rodada da votacao com materias fora de lista.")
            else:
                for materia in materias:
                    if not isinstance(materia, dict):
                        erros.append("Rodada da votacao com materia fora de objeto.")
                        continue
                    sigla = str(materia.get("sigla") or "")
                    if sigla in excluidas or sigla not in elegiveis:
                        erros.append(
                            f"Materia {materia.get('id')} com sigla nao elegivel: {sigla}."
                        )
                print(
                    f"OK: Rodada {rodada.get('rodada_id')} com "
                    f"{len(materias)} materias, sem autor e so com sigla elegivel."
                )

    print("\n-------------------------------------------------------")
    if erros:
        print(f"ERROS DETECTADOS ({len(erros)}):")
        for e in erros:
            print(f"- {e}")
        sys.exit(1)
    else:
        print("SUCESSO: Todas as regras de governanca e sanidade foram atendidas!")
        sys.exit(0)

if __name__ == "__main__":
    main()
