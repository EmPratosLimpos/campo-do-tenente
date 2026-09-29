"""Baixa do SAPL as tabelas de autoria das materias e de autor.

Um pedido por vez. Pausa de PAUSA_SAPL_SEGUNDOS entre pedidos.
page_size=100. Teto desta coleta: 40 pedidos.

Cada resposta e gravada exatamente como veio em
dados/brutos/lote_<AAAAMMDD>_autoria/, com indice.json.
Pagina que ja existe nessa pasta, com HTTP 200 no indice, nao e baixada de novo.

Recursos:
- materia/autoria: liga materia a autor, com primeiro_autor
- base/autor: quem e cada autor (parlamentar ou outro tipo)
- base/tipoautor: nome de cada tipo de autor
- parlamentares/cargomesa: nome oficial de cada cargo da mesa

A lista completa de autoria repete ids entre paginas. Por isso ha uma
segunda leitura filtrada por ano da materia (materia__ano). Se o SAPL
ignorar o filtro (total igual ao da lista completa), so a primeira
pagina fica gravada, como prova, e as outras nao sao pedidas.

Rodar:  python coletor/coletar_autoria.py
"""

from __future__ import annotations

import json
from datetime import datetime

from coletar_lote import BRUTOS, ColetorLote, OrcamentoEsgotado
from config_cidade import PAUSA_SAPL_SEGUNDOS, anos_recorte, carregar_config

TETO_PEDIDOS = 40

PLANO = (
    ("/api/materia/autoria/", "autoria"),
    ("/api/base/autor/", "autor"),
    ("/api/base/tipoautor/", "tipoautor"),
    ("/api/parlamentares/cargomesa/", "cargomesa"),
)


def total_entries(dados) -> int | None:
    if not isinstance(dados, dict):
        return None
    valor = (dados.get("pagination") or {}).get("total_entries")
    return int(valor) if valor is not None else None


def gravar_aviso_filtro_ignorado(
    coletor: ColetorLote, ano: int, total: int | None, total_sem_filtro: int | None, motivo: str
) -> str:
    """Grava aviso estruturado nos brutos quando o SAPL ignora o filtro por ano."""
    nome = f"aviso_filtro_materia_ano{ano}.json"
    aviso = {
        "ano": int(ano),
        "prefixo": f"autoria_materia_ano{ano}",
        "total_entries_com_filtro": total,
        "total_entries_sem_filtro": total_sem_filtro,
        "motivo": motivo,
        "conduta": "só a primeira página ficou gravada como prova; as demais não foram pedidas",
        "registrado_em": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    (coletor.pasta / nome).write_text(
        json.dumps(aviso, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return nome


def pedir_filtrado_por_ano(coletor: ColetorLote, ano: int, total_sem_filtro: int | None) -> None:
    prefixo = f"autoria_materia_ano{ano}"
    params = {"materia__ano": ano, "page_size": 100, "page": 1}
    primeiro = coletor.pedir("/api/materia/autoria/", params, f"{prefixo}_p1.json")
    total = total_entries(primeiro)
    if total is None:
        nome = gravar_aviso_filtro_ignorado(
            coletor, ano, total, total_sem_filtro, "total_entries ausente na resposta com filtro"
        )
        print(f"  AVISO: filtro materia__ano={ano} sem total_entries, nao pagina (aviso em {nome})")
        return
    if total_sem_filtro is not None and total >= total_sem_filtro:
        nome = gravar_aviso_filtro_ignorado(
            coletor, ano, total, total_sem_filtro, "filtro materia__ano ignorado pelo SAPL"
        )
        print(f"  AVISO: filtro materia__ano={ano} ignorado pelo SAPL, nao pagina (aviso em {nome})")
        return
    coletor.pedir_paginas("/api/materia/autoria/", {"materia__ano": ano}, prefixo)


def main() -> None:
    cfg = carregar_config()
    pasta = BRUTOS / f"lote_{datetime.now().strftime('%Y%m%d')}_autoria"
    coletor = ColetorLote(cfg, pasta, teto=TETO_PEDIDOS)
    print("Coleta de autoria no SAPL")
    print(f"Pasta dados/brutos/{pasta.name}")
    print(f"Pausa {PAUSA_SAPL_SEGUNDOS}s, teto {TETO_PEDIDOS}, ja feitos {coletor.pedidos}")
    try:
        for caminho, prefixo in PLANO:
            print(prefixo)
            coletor.pedir_paginas(caminho, {}, prefixo)
        total_sem_filtro = total_entries(
            coletor.pedir("/api/materia/autoria/", {"page_size": 100, "page": 1}, "autoria_p1.json")
        )
        for ano in anos_recorte(cfg):
            print(f"autoria_materia_ano{ano}")
            pedir_filtrado_por_ano(coletor, ano, total_sem_filtro)
    except OrcamentoEsgotado as exc:
        coletor._gravar_indice()
        print(f"PAROU: {exc}")
        raise SystemExit(2)
    coletor._gravar_indice()
    print(f"Fim. Pedidos: {coletor.pedidos}.")


if __name__ == "__main__":
    main()
