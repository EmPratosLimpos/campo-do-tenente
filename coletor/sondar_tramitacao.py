"""Sondagem C7 da tramitacao no SAPL (maximo 4 URLs distintas).

Um pedido por vez, com pausa de PAUSA_SAPL_SEGUNDOS, via ColetorLote.
O teto fisico inclui repeticoes automaticas em caso de recusa da rede.
URLs distintas pedidas no maximo 4, conforme a tarefa.
Pastas e indice em dados/brutos/lote_<AAAAMMDD>_sondagem_tramitacao/.

Pedidos:
  1. /api/materia/tramitacao/ com materia=96 (REQ de exemplo)
  2. /api/materia/tramitacao/ com materia=138 (PLEX de exemplo)
  3. /api/materia/statustramitacao/ primeira pagina
  4. So se necessario: segunda pagina de um anterior,
     ou primeira pagina de /api/materia/unidadetramitacao/

Rodar: python coletor/sondar_tramitacao.py
"""

from __future__ import annotations

from datetime import datetime

from coletar_lote import BRUTOS, ColetorLote, OrcamentoEsgotado, tem_proxima_pagina
from config_cidade import carregar_config
from config_cidade import PAUSA_SAPL_SEGUNDOS

TETO_FISICO = 10
URLS_DISTINTAS_MAX = 4
MATERIA_REQ = 96
MATERIA_PLEX = 138


def main() -> None:
    cfg = carregar_config()
    pasta = BRUTOS / f"lote_{datetime.now().strftime('%Y%m%d')}_sondagem_tramitacao"
    coletor = ColetorLote(cfg, pasta, teto=TETO_FISICO)
    print("Sondagem C7 da tramitacao no SAPL")
    print(f"Pasta dados/brutos/{pasta.name}")
    print(f"Pausa {PAUSA_SAPL_SEGUNDOS}s, teto fisico {TETO_FISICO}, URLs distintas max {URLS_DISTINTAS_MAX}, ja feitos {coletor.pedidos}")
    try:
        print("1. tramitacao da materia 96 (REQ)")
        try:
            t96 = coletor.pedir(
                "/api/materia/tramitacao/",
                {"materia": MATERIA_REQ},
                "tramitacao_materia96_p1.json",
            )
        except SystemExit as exc:
            print(f"  Falhou o pedido 1, sigo para o 2: {exc}")
            t96 = None
        print("2. tramitacao da materia 138 (PLEX)")
        try:
            t138 = coletor.pedir(
                "/api/materia/tramitacao/",
                {"materia": MATERIA_PLEX},
                "tramitacao_materia138_p1.json",
            )
        except SystemExit as exc:
            print(f"  Falhou o pedido 2, sigo para o 3: {exc}")
            t138 = None
        print("3. tabela de status da tramitacao")
        try:
            st1 = coletor.pedir(
                "/api/materia/statustramitacao/",
                {},
                "statustramitacao_p1.json",
            )
        except SystemExit as exc:
            print(f"  Falhou o pedido 3, sigo para o 4: {exc}")
            st1 = None
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
    except OrcamentoEsgotado as exc:
        coletor._gravar_indice()
        print(f"PAROU: {exc}")
        raise SystemExit(2)
    coletor._gravar_indice()
    print(f"Fim. Pedidos: {coletor.pedidos}.")


if __name__ == "__main__":
    main()
