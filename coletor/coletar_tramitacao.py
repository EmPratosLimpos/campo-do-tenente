"""Coleta da tramitacao no SAPL (C8).

Um pedido por vez, com pausa de PAUSA_SAPL_SEGUNDOS, via ColetorLote.
Um pedido por materia dos tipos lidos de config_cidade.json
(tramitacao.tipos_coleta), a partir de dados/tratados/temas_materias.json.
Mais as paginas 2 e 3 de statustramitacao e de unidadetramitacao.

Cada resposta e gravada exatamente como veio em
dados/brutos/lote_<AAAAMMDD>_tramitacao/, com indice.json.
Pagina que ja existe nessa pasta, com HTTP 200 no indice, nao e baixada
de novo. O bruto nao e editado. Campo de rede nunca e copiado para
dado tratado, so conferido aqui.

Conferencia por materia: cada item traz so a materia pedida; o total
de itens bate com total_entries; se houver proxima pagina, as proximas
sao pedidas.

Uso:
    python coletor/coletar_tramitacao.py
    python coletor/coletar_tramitacao.py --max-novos 30
    python coletor/coletar_tramitacao.py --pasta dados/brutos/lote_20260929_tramitacao
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from coletar_lote import BRUTOS, ColetorLote, OrcamentoEsgotado, tem_proxima_pagina, numero_da_proxima
from config_cidade import PAUSA_SAPL_SEGUNDOS, carregar_config, tipos_tramitacao_coleta

TETO_PEDIDOS = 600
ARQUIVO_TEMAS = "temas_materias.json"


def carregar_materias_alvo(cfg: dict) -> list[dict]:
    """Materias do recorte nos tipos da coleta, sem sigla fixa no codigo."""
    tipos = tipos_tramitacao_coleta(cfg)
    caminho = BRUTOS.parent / "tratados" / ARQUIVO_TEMAS
    if not caminho.exists():
        raise SystemExit(f"Arquivo nao encontrado: {caminho.name}")
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    materias = dados.get("materias") or []
    alvos = [m for m in materias if str(m.get("sigla") or "") in tipos]
    alvos.sort(key=lambda m: (str(m.get("sigla") or ""), int(m.get("ano") or 0), int(m.get("numero") or 0), int(m.get("id") or 0)))
    if not alvos:
        raise SystemExit("Nenhuma materia nos tipos da coleta em temas_materias.json.")
    return alvos


def conferir_tramitacao(dados: dict, materia_id: int, arquivo: str) -> None:
    """Cada item e so da materia pedida; total bate com os itens."""
    if not isinstance(dados, dict):
        raise SystemExit(f"{arquivo}: resposta sem objeto JSON")
    resultados = dados.get("results")
    if not isinstance(resultados, list):
        raise SystemExit(f"{arquivo}: sem lista results")
    for item in resultados:
        if not isinstance(item, dict):
            raise SystemExit(f"{arquivo}: item sem objeto JSON")
        if int(item.get("materia") or -1) != int(materia_id):
            raise SystemExit(
                f"{arquivo}: item da materia {item.get('materia')}, esperado {materia_id}."
            )
    paginacao = dados.get("pagination") or {}
    total = paginacao.get("total_entries")
    if total is not None and int(total) != len(resultados):
        pagina = paginacao.get("page") or 1
        total_paginas = paginacao.get("total_pages") or 1
        if int(total_paginas) <= 1 and int(pagina) == 1:
            raise SystemExit(
                f"{arquivo}: paginacao diz {total} registros, mas o arquivo tem {len(resultados)}."
            )


def pedir_tramitacao_completa(coletor: ColetorLote, materia_id: int) -> dict:
    """Pede a pagina 1 e, se houver next, as proximas. Devolve a pagina 1."""
    arquivo1 = f"tramitacao_materia{int(materia_id)}_p1.json"
    primeira = coletor.pedir("/api/materia/tramitacao/", {"materia": int(materia_id)}, arquivo1)
    conferir_tramitacao(primeira, int(materia_id), arquivo1)
    atual = primeira
    pagina = int((atual.get("pagination") or {}).get("page") or 1)
    while tem_proxima_pagina(atual):
        pagina = numero_da_proxima(atual, pagina)
        arquivo = f"tramitacao_materia{int(materia_id)}_p{pagina}.json"
        dados = coletor.pedir(
            "/api/materia/tramitacao/", {"materia": int(materia_id), "page": pagina}, arquivo
        )
        conferir_tramitacao(dados, int(materia_id), arquivo)
        atual = dados
    return primeira


def pedir_catalogo(coletor: ColetorLote, caminho: str, prefixo: str) -> None:
    """Pede as paginas 1 a 3 do catalogo, com retomada pelo indice."""
    primeira = coletor.pedir(caminho, {}, f"{prefixo}_p1.json")
    if not isinstance(primeira, dict):
        raise SystemExit(f"{prefixo}: resposta sem objeto JSON")
    atual = primeira
    pagina = int((atual.get("pagination") or {}).get("page") or 1)
    while tem_proxima_pagina(atual):
        pagina = numero_da_proxima(atual, pagina)
        atual = coletor.pedir(caminho, {"page": pagina}, f"{prefixo}_p{pagina}.json")
        if not isinstance(atual, dict):
            raise SystemExit(f"{prefixo}: pagina {pagina} sem objeto JSON")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Coleta da tramitacao no SAPL (C8).")
    parser.add_argument("--max-novos", type=int, default=0)
    parser.add_argument("--pasta", default="")
    args = parser.parse_args(argv)

    cfg = carregar_config()
    if args.pasta:
        pasta = Path(args.pasta)
        from coletar_lote import RAIZ as RAIZ_COLETOR

        if not pasta.is_absolute():
            pasta = RAIZ_COLETOR / pasta
    else:
        pasta = BRUTOS / f"lote_{datetime.now().strftime('%Y%m%d')}_tramitacao"
    teto = TETO_PEDIDOS
    if args.max_novos and int(args.max_novos) > 0:
        teto = coletor_teto_limitado(pasta, int(args.max_novos))
    coletor = ColetorLote(cfg, pasta, teto=teto)
    print("Coleta da tramitacao no SAPL (C8)")
    print(f"Pasta dados/brutos/{pasta.name}")
    print(f"Pausa {PAUSA_SAPL_SEGUNDOS}s, teto {coletor.teto}, ja feitos {coletor.pedidos}")
    alvos = carregar_materias_alvo(cfg)
    print(f"Materias alvo: {len(alvos)} nos tipos {', '.join(tipos_tramitacao_coleta(cfg))}")
    try:
        for materia in alvos:
            mid = int(materia["id"])
            print(f"materia {mid} ({materia.get('sigla')} {materia.get('numero')}/{materia.get('ano')})")
            try:
                pedir_tramitacao_completa(coletor, mid)
            except SystemExit as exc:
                print(f"  Falhou a materia {mid}, sigo para a proxima: {exc}")
                continue
        for caminho, prefixo in (
            ("/api/materia/statustramitacao/", "statustramitacao"),
            ("/api/materia/unidadetramitacao/", "unidadetramitacao"),
        ):
            print(prefixo)
            try:
                pedir_catalogo(coletor, caminho, prefixo)
            except SystemExit as exc:
                print(f"  Falhou {prefixo}, sigo: {exc}")
                continue
    except OrcamentoEsgotado as exc:
        coletor._gravar_indice()
        print(f"PAROU: {exc}")
        return 2
    coletor._gravar_indice()
    print(f"Fim. Pedidos: {coletor.pedidos}.")
    return 0


def coletor_teto_limitado(pasta: Path, max_novos: int) -> int:
    """Teto desta execucao = ja feitos + max_novos, sem passar do teto geral."""
    feitos = 0
    indice = pasta / "indice.json"
    if indice.exists():
        try:
            dados = json.loads(indice.read_text(encoding="utf-8"))
            feitos = int(dados.get("total_pedidos") or 0)
        except (OSError, ValueError, TypeError):
            feitos = 0
    return min(TETO_PEDIDOS, feitos + int(max_novos))


if __name__ == "__main__":
    raise SystemExit(main())
