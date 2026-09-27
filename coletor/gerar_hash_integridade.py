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


def gerar_hash_do_ano(ano: int) -> None:
    arquivo_json = pathlib.Path(f"dados/tratados/atuacao_vereadores_{ano}.json")
    arquivo_hash = pathlib.Path(f"dados/tratados/atuacao_vereadores_{ano}.json.sha256")
    if not arquivo_json.exists():
        raise SystemExit(f"Arquivo nao encontrado: {arquivo_json}")

    hash_hex = calcular_hash_sha256(arquivo_json)
    data_hora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    arquivo_hash.parent.mkdir(parents=True, exist_ok=True)
    with arquivo_hash.open("w", encoding="utf-8") as f:
        f.write(hash_hex + "\n")

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
