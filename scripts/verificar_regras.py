#!/usr/bin/env python3
"""
Script de verificacao compulsoria de regras de governanca e sanidade.
Executado localmente por qualquer agente ou desenvolvedor antes de commits.
"""

import hashlib
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT / "coletor") not in sys.path:
    sys.path.insert(0, str(ROOT / "coletor"))

from config_cidade import anos_recorte, carregar_config  # noqa: E402


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
    if res.returncode == 2:
        print("ADIADO: pisos de sanidade ainda nao definidos ou dados ainda nao coletados.")
        if res.stderr.strip():
            print(res.stderr.strip())
    elif res.returncode != 0:
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
    if hashes_vistos == 0:
        print("ADIADO: nenhum arquivo consolidado com hash para conferir.")

    # 5. Higiene de travessoes em documentacao
    print("\nVerificando ausencia de caracteres de travessao proibidos...")
    arquivos_norma = ["AGENTS.md", "CLAUDE.md", ".cursorrules", "PROCESSO_DESENVOLVIMENTO_E_GOVERNANCA.md", "index.html"]
    for nome in arquivos_norma:
        arq = ROOT / nome
        if arq.exists():
            conteudo = arq.read_text(encoding="utf-8")
            if re.search(r"[—–]", conteudo):
                erros.append(f"VIOLACAO: Caractere travessao encontrado em {nome}!")
            else:
                print(f"OK: {nome} limpo.")

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
