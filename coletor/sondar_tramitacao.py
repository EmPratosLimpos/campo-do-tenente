"""Sondagem da tramitacao no SAPL (C7 e C7b).

Um pedido por vez, com pausa de PAUSA_SAPL_SEGUNDOS, via ColetorLote.
O teto fisico inclui repeticoes automaticas em caso de recusa da rede.
C7 pediu no maximo 4 URLs distintas. C7b pede no maximo 3 URLs distintas
na mesma pasta, sem sobrescrever os arquivos validos anteriores.
Pastas e indice em dados/brutos/lote_<AAAAMMDD>_sondagem_tramitacao/.

C7 (padrao, sem argumentos):
  1. /api/materia/tramitacao/ com materia=96 (REQ de exemplo)
  2. /api/materia/tramitacao/ com materia=138 (PLEX de exemplo)
  3. /api/materia/statustramitacao/ primeira pagina
  4. So se necessario: segunda pagina de um anterior,
     ou primeira pagina de /api/materia/unidadetramitacao/

C7b (exemplo):
  python coletor/sondar_tramitacao.py --materias 164 806 --status

Rodar C7: python coletor/sondar_tramitacao.py
"""

from __future__ import annotations

import argparse
from datetime import datetime

from coletar_lote import BRUTOS, ColetorLote, OrcamentoEsgotado, tem_proxima_pagina
from config_cidade import carregar_config
from config_cidade import PAUSA_SAPL_SEGUNDOS

TETO_FISICO = 20
URLS_DISTINTAS_MAX_C7 = 4
URLS_DISTINTAS_MAX_C7B = 3
MATERIA_REQ = 96
MATERIA_PLEX = 138


def pedir_tramitacao(coletor: ColetorLote, materia: int):
    try:
        return coletor.pedir(
            "/api/materia/tramitacao/",
            {"materia": int(materia)},
            f"tramitacao_materia{int(materia)}_p1.json",
        )
    except SystemExit as exc:
        print(f"  Falhou a tramitacao da materia {materia}, sigo: {exc}")
        return None


def pedir_status(coletor: ColetorLote):
    try:
        return coletor.pedir(
            "/api/materia/statustramitacao/",
            {},
            "statustramitacao_p1.json",
        )
    except SystemExit as exc:
        print(f"  Falhou o status, sigo: {exc}")
        return None


def fluxo_c7(coletor: ColetorLote) -> None:
    print("1. tramitacao da materia 96 (REQ)")
    t96 = pedir_tramitacao(coletor, MATERIA_REQ)
    print("2. tramitacao da materia 138 (PLEX)")
    t138 = pedir_tramitacao(coletor, MATERIA_PLEX)
    print("3. tabela de status da tramitacao")
    st1 = pedir_status(coletor)
    pendentes = []
    if isinstance(t96, dict) and tem_proxima_pagina(t96):
        pendentes.append(("tramitacao 96", "/api/materia/tramitacao/",
                          {"materia": MATERIA_REQ, "page": 2},
                          "tramitacao_materia96_p2.json"))
    if isinstance(t138, dict) and tem_proxima_pagina(t138):
        pendentes.append(("tramitacao 138", "/api/materia/tramitacao/",
                          {"materia": MATERIA_PLEX, "page": 2},
                          "tramitacao_materia138_p2.json"))
    if isinstance(st1, dict) and tem_proxima_pagina(st1):
        pendentes.append(("status p2", "/api/materia/statustramitacao/",
                          {"page": 2},
                          "statustramitacao_p2.json"))
    if pendentes:
        nome, caminho, params, arquivo = pendentes[0]
        print(f"4. segunda pagina necessaria: {nome}")
        try:
            coletor.pedir(caminho, params, arquivo)
        except SystemExit as exc:
            print(f"  Falhou o pedido 4: {exc}")
    else:
        print("4. sem segunda pagina pendente. Unidades da tramitacao.")
        try:
            coletor.pedir(
                "/api/materia/unidadetramitacao/",
                {},
                "unidadetramitacao_p1.json",
            )
        except SystemExit as exc:
            print(f"  Falhou o pedido 4: {exc}")


def fluxo_c7b(coletor: ColetorLote, materias: list[int], com_status: bool) -> None:
    for materia in materias:
        print(f"tramitacao da materia {materia}")
        pedir_tramitacao(coletor, int(materia))
    if com_status:
        print("tabela de status da tramitacao (nova tentativa)")
        pedir_status(coletor)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--materias", nargs="*", type=int, default=None)
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    cfg = carregar_config()
    pasta = BRUTOS / f"lote_{datetime.now().strftime('%Y%m%d')}_sondagem_tramitacao"
    coletor = ColetorLote(cfg, pasta, teto=TETO_FISICO)
    print("Sondagem da tramitacao no SAPL")
    print(f"Pasta dados/brutos/{pasta.name}")
    print(f"Pausa {PAUSA_SAPL_SEGUNDOS}s, teto fisico {TETO_FISICO}, ja feitos {coletor.pedidos}")
    try:
        if args.materias is None and not args.status:
            print(f"C7: URLs distintas max {URLS_DISTINTAS_MAX_C7}")
            fluxo_c7(coletor)
        else:
            materias = [int(m) for m in (args.materias or [])]
            if len(materias) + (1 if args.status else 0) > URLS_DISTINTAS_MAX_C7B:
                raise SystemExit(
                    f"C7b aceita no maximo {URLS_DISTINTAS_MAX_C7B} URLs distintas."
                )
            print(f"C7b: URLs distintas max {URLS_DISTINTAS_MAX_C7B}")
            fluxo_c7b(coletor, materias, args.status)
    except OrcamentoEsgotado as exc:
        coletor._gravar_indice()
        print(f"PAROU: {exc}")
        raise SystemExit(2)
    coletor._gravar_indice()
    print(f"Fim. Pedidos: {coletor.pedidos}.")


if __name__ == "__main__":
    main()
