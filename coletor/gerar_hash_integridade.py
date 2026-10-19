#!/usr/bin/env python3
import datetime
import hashlib
import pathlib

from config_cidade import anos_recorte, carregar_config

CONFIG = carregar_config()
ANOS = anos_recorte(CONFIG)


def calcular_hash_sha256(caminho):
    sha256 = hashlib.sha256()
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(65536), b""):
            sha256.update(bloco)
    return sha256.hexdigest()


def gravar_hash(caminho_json, caminho_hash) -> str:
    """Grava o .sha256 do JSON e devolve o hash calculado.

    Usado pelo gerador da atuacao, no mesmo passo em que o JSON e
    escrito, e pelos testes. Os caminhos sao explicitos para o mesmo
    codigo servir ao repositorio e a uma copia temporaria. O JSON tem
    que estar em LF, para o hash ser o mesmo em qualquer sistema.
    """
    caminho_json = pathlib.Path(caminho_json)
    caminho_hash = pathlib.Path(caminho_hash)
    if not caminho_json.exists():
        raise SystemExit(f"Arquivo nao encontrado: {caminho_json}")
    conteudo = caminho_json.read_bytes()
    if b"\r" in conteudo:
        raise SystemExit(
            f"{caminho_json} nao esta em LF. O hash tem que ser o do conteudo com fim de linha LF."
        )
    hash_hex = calcular_hash_sha256(caminho_json)
    caminho_hash.parent.mkdir(parents=True, exist_ok=True)
    caminho_hash.write_bytes((hash_hex + "\n").encode("ascii"))
    return hash_hex


def conferir_hash(caminho_json, caminho_hash) -> None:
    """Levanta SystemExit quando o hash salvo nao corresponde ao arquivo salvo."""
    caminho_json = pathlib.Path(caminho_json)
    caminho_hash = pathlib.Path(caminho_hash)
    if not caminho_json.exists():
        raise SystemExit(f"Arquivo nao encontrado: {caminho_json}")
    if not caminho_hash.is_file():
        raise SystemExit(
            f"Hash ausente para {caminho_json}. "
            "Rode python coletor/gerar_hash_integridade.py"
        )
    calculado = calcular_hash_sha256(caminho_json)
    salvo = caminho_hash.read_text(encoding="utf-8").strip()
    if calculado != salvo:
        raise SystemExit(
            f"Hash SHA256 de {caminho_json} nao confere: "
            f"calculado {calculado}, salvo {salvo}"
        )


def gerar_hash_do_ano(ano: int) -> None:
    arquivo_json = pathlib.Path(f"dados/tratados/atuacao_vereadores_{ano}.json")
    arquivo_hash = pathlib.Path(f"dados/tratados/atuacao_vereadores_{ano}.json.sha256")
    hash_hex = gravar_hash(arquivo_json, arquivo_hash)
    data_hora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"Arquivo: {arquivo_json}")
    print(f"SHA256: {hash_hex}")
    print(f"Data/hora: {data_hora}")
    print(f"Hash salvo em: {arquivo_hash}")


def main():
    faltando = []
    for ano in ANOS:
        caminho = pathlib.Path(f"dados/tratados/atuacao_vereadores_{ano}.json")
        if not caminho.exists():
            faltando.append(str(caminho))
    if faltando:
        raise SystemExit(
            "Arquivos de atuacao ainda nao existem para gerar o hash: "
            + ", ".join(faltando)
        )
    for ano in ANOS:
        gerar_hash_do_ano(ano)


if __name__ == "__main__":
    main()
