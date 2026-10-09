"""Baixa do SAPL as tabelas de autoria das materias e de autor.

Um pedido por vez. Pausa de PAUSA_SAPL_SEGUNDOS entre pedidos.
page_size=100. Teto desta coleta: 40 pedidos.

Cada resposta e gravada exatamente como veio em
dados/brutos/lote_<AAAAMMDD>_autoria/, com indice.json.
Pagina que ja existe nessa pasta, com HTTP 200 no indice, nao e baixada de novo.

Recursos:
- materia/autoria: liga materia a autor, com primeiro_autor.
  Pedida sempre com o=id, que devolve os ids em ordem crescente e
  repete igual entre leituras. Sem ordenacao a lista mistura as
  paginas (ids repetidos e faltando). ordering=id e ignorado pelo
  SAPL. O filtro por ano (materia__ano) tambem e ignorado, por isso
  nao e mais pedido aqui.
- base/autor: quem e cada autor (parlamentar ou outro tipo)
- base/tipoautor: nome de cada tipo de autor
- parlamentares/cargomesa: nome oficial de cada cargo da mesa

Depois de baixar, a lista de autoria e conferida: os ids unicos
somam total_entries, sem duplicar nem faltar. Se nao fechar, a
pasta nao serve para publicar.

Rodar:  python coletor/coletar_autoria.py
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from coletar_lote import BRUTOS, ColetorLote, OrcamentoEsgotado
from config_cidade import PAUSA_SAPL_SEGUNDOS, carregar_config

TETO_PEDIDOS = 40

PARAMS_AUTORIA_ESTAVEL = {"o": "id"}

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


def conferir_autoria(pasta: Path, prefixo: str = "autoria") -> tuple[bool, str]:
    """Confere a lista estavel: ids unicos somam total_entries.

    Devolve (True, resumo) quando nao ha duplicado nem faltando e
    (False, motivo) quando a lista misturou paginas ou veio incompleta.
    """
    numero = 1
    ids: list = []
    total = None
    while (pasta / f"{prefixo}_p{numero}.json").exists():
        caminho = pasta / f"{prefixo}_p{numero}.json"
        try:
            dados = json.loads(caminho.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            return False, f"pagina {numero} ilegivel em {caminho.name}"
        if not isinstance(dados, dict):
            return False, f"pagina {numero} sem objeto JSON"
        if numero == 1:
            total = total_entries(dados)
        for linha in dados.get("results") or []:
            if isinstance(linha, dict) and linha.get("id") is not None:
                ids.append(int(linha["id"]))
        numero += 1
    if numero == 1:
        return False, "sem arquivo da pagina 1"
    if total is None:
        return False, "pagina 1 sem total_entries"
    unicos = len(set(ids))
    if len(ids) != total or unicos != total:
        return (
            False,
            f"{len(ids)} linhas lidas, {unicos} ids unicos, total {total}",
        )
    return True, f"{unicos} ids unicos, total {total}"


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
    (coletor.pasta / nome).write_bytes(
        (json.dumps(aviso, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
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
            if prefixo == "autoria":
                coletor.pedir_paginas(caminho, dict(PARAMS_AUTORIA_ESTAVEL), prefixo)
            else:
                coletor.pedir_paginas(caminho, {}, prefixo)
        ok, detalhe = conferir_autoria(pasta)
        if not ok:
            print(f"AUTORIA NAO FECHA: {detalhe}. Esta pasta nao serve para publicar.")
            coletor._gravar_indice()
            raise SystemExit(2)
        print(f"Autoria confere: {detalhe}.")
    except OrcamentoEsgotado as exc:
        coletor._gravar_indice()
        print(f"PAROU: {exc}")
        raise SystemExit(2)
    coletor._gravar_indice()
    print(f"Fim. Pedidos: {coletor.pedidos}.")


if __name__ == "__main__":
    main()
