"""
Sonda a porta de dados do SAPL da cidade definida em config_cidade.json
e relata o que existe.

Esta e a primeira tarefa do projeto. Ela nao baixa o acervo: apenas bate
na porta, com educacao, e escreve um relatorio em dados/brutos/sondagem.txt
dizendo quais caminhos responderam e o que veio dentro.

A pergunta que precisa ser respondida: a votacao nominal, o voto de cada
vereador em cada materia, esta disponivel em dado estruturado?

Rodar:  python coletor/sondar.py
"""

import time
from pathlib import Path

import requests

from config_cidade import (
    PAUSA_SAPL_SEGUNDOS,
    carregar_config,
    endereco_sapl,
    nome_cidade,
    remover_campos_pessoais,
    user_agent_http,
)

CONFIG = carregar_config()
BASE = endereco_sapl(CONFIG)
PAUSA = PAUSA_SAPL_SEGUNDOS
TEMPO_LIMITE = 30
CIDADE = nome_cidade(CONFIG)

# Caminhos confirmados no OpenAPI / indice de instalacoes SAPL em 2026-09-14.
# Os primeiros eram hipotese de outras camaras; os acrescentados abaixo
# existem de fato nesta familia de instalacao e ajudam a ler voto, ausencia e mesa.
CAMINHOS = [
    "/api/",
    "/api/materia/materialegislativa/?page_size=1",
    "/api/materia/tipomaterialegislativa/?page_size=5",
    "/api/materia/autoria/?page_size=1",
    "/api/parlamentares/parlamentar/?page_size=1",
    "/api/parlamentares/legislatura/?page_size=5",
    "/api/parlamentares/mandato/?page_size=1",
    "/api/parlamentares/filiacao/?page_size=1",
    "/api/sessao/sessaoplenaria/?page_size=1",
    "/api/sessao/tiposessaoplenaria/?page_size=20",
    "/api/sessao/ordemdia/?page_size=1",
    "/api/sessao/expedientemateria/?page_size=1",
    "/api/sessao/registrovotacao/?page_size=1",
    "/api/sessao/votoparlamentar/?page_size=1",
    "/api/sessao/tiporesultadovotacao/?page_size=20",
    "/api/sessao/presencaordemdia/?page_size=1",
    "/api/sessao/sessaoplenariapresenca/?page_size=1",
    "/api/sessao/justificativaausencia/?page_size=1",
    "/api/sessao/tipojustificativa/?page_size=20",
    "/api/sessao/integrantemesa/?page_size=1",
]

SAIDA = Path(__file__).resolve().parent.parent / "dados" / "brutos"


def sondar(sessao, caminho):
    url = BASE + caminho
    try:
        r = sessao.get(url, timeout=TEMPO_LIMITE)
    except requests.RequestException as e:
        return caminho, "erro de rede", str(e)[:200]

    if r.status_code != 200:
        return caminho, f"HTTP {r.status_code}", r.text[:200]

    try:
        dado = remover_campos_pessoais(r.json(), CONFIG)
    except ValueError:
        return caminho, "respondeu, mas nao em JSON", r.text[:200]

    if isinstance(dado, dict) and "results" in dado:
        # Esta instalacao usa pagination.total_entries; outras usam count.
        paginacao = dado.get("pagination") or {}
        total = dado.get("count", paginacao.get("total_entries", "?"))
        exemplo = dado["results"][0] if dado["results"] else {}
        campos = ", ".join(sorted(exemplo.keys())) if isinstance(exemplo, dict) else ""
        return caminho, f"OK, {total} registros", f"campos: {campos}"

    if isinstance(dado, dict):
        return caminho, "OK, indice", ", ".join(sorted(dado.keys()))[:600]

    return caminho, "OK", str(dado)[:200]


def main():
    SAIDA.mkdir(parents=True, exist_ok=True)
    sessao = requests.Session()
    sessao.headers.update(
        {
            "User-Agent": user_agent_http(CONFIG),
            "Accept": "application/json",
        }
    )

    linhas = [f"Sondagem da porta de dados do SAPL de {CIDADE}", ""]
    print(linhas[0])
    print()

    for caminho in CAMINHOS:
        cam, status, detalhe = sondar(sessao, caminho)
        print(f"  {status:<28} {cam}")
        linhas.append(f"{cam}")
        linhas.append(f"  status: {status}")
        linhas.append(f"  {detalhe}")
        linhas.append("")
        time.sleep(PAUSA)

    destino = SAIDA / "sondagem.txt"
    destino.write_text("\n".join(linhas), encoding="utf-8")

    print()
    print(f"Relatorio completo em {destino}")
    print()
    print("Agora leia o relatorio e responda:")
    print("  1. O caminho de votoparlamentar respondeu?")
    print("  2. Se sim, ele liga voto a parlamentar e a materia?")
    print("  3. Se nao, onde mais esta a votacao nominal?")


if __name__ == "__main__":
    main()
