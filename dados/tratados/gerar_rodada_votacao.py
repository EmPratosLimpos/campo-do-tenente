#!/usr/bin/env python3
"""Gera a rodada aberta da votacao popular (V2, v1.3.0).

Rodada e a ultima sessao ordinaria com dados publicados. Entram as
materias com votacao deliberativa nessa sessao, com sigla na lista de
elegiveis do config e fora da lista de excluidas. Votacao procedimental
(vistas, adiada, retirada de pauta, sem deliberacao) fica fora pelo
mesmo criterio que o site ja usa: o campo deliberativa gravado em
proposicoes e executivo por registro_deliberativo
(dados/tratados/gerar_proposicoes_executivo.py), que por sua vez usa
deliberativa_nome (dados/tratados/gerar_atuacao_vereadores.py). Nenhum
criterio novo aqui.

Entradas (anos do recorte em config_cidade.json, nada fixo no codigo):
- dados/tratados/atuacao_vereadores_<ano>.json (sessoes ordinarias)
- dados/tratados/tema-votacoes-<ano>.csv (pauta: item_ordem_id, resultado,
  ementa e link exatamente como estao)
- dados/tratados/proposicoes_<ano>.json e executivo_<ano>.json
  (campo deliberativa de cada votacao registrada)

Saida idempotente (byte a byte quando nada muda):
- dados/tratados/votacao_rodada.json em UTF-8 com LF, sem autor, partido
  ou vereador em nenhum campo.

Uso:
    python dados/tratados/gerar_rodada_votacao.py
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import date, timedelta
from pathlib import Path

DIR_SCRIPT = Path(__file__).resolve().parent
RAIZ = DIR_SCRIPT.parent.parent
for caminho in (DIR_SCRIPT, RAIZ / "coletor"):
    if str(caminho) not in sys.path:
        sys.path.insert(0, str(caminho))

from config_cidade import anos_recorte, carregar_config  # noqa: E402
from gerar_atuacao_vereadores import deliberativa_nome  # noqa: E402

STATUS_ABERTA = "aberta"
STATUS_SEM_MATERIAS = "sem_materias_elegiveis"
SAIDA_REL = "dados/tratados/votacao_rodada.json"


def rel(base: Path, caminho: Path) -> str:
    try:
        return caminho.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return caminho.name


def escrever_lf(caminho: Path, texto: str) -> None:
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    if not texto.endswith("\n"):
        texto += "\n"
    if "\r" in texto:
        raise SystemExit(f"{caminho} ainda tem quebra de linha CR.")
    caminho.write_bytes(texto.encode("utf-8"))


def ler_sessoes(base: Path, anos: list[int]) -> tuple[list[dict], list[str]]:
    """Sessoes ordinarias publicadas, com o arquivo de origem de cada uma."""
    sessoes: list[dict] = []
    gerado: list[str] = []
    for ano in anos:
        caminho = base / "dados" / "tratados" / f"atuacao_vereadores_{ano}.json"
        if not caminho.is_file():
            raise SystemExit(f"Consolidado ausente: {rel(base, caminho)}.")
        gerado.append(rel(base, caminho))
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        for sessao in dados.get("sessoes") or []:
            if not isinstance(sessao, dict) or sessao.get("id") is None:
                continue
            sessoes.append(
                {
                    "id": int(sessao["id"]),
                    "data": str(sessao.get("data") or ""),
                    "numero": sessao.get("numero"),
                }
            )
    return sessoes, gerado


def escolher_ultima_sessao(sessoes: list[dict]) -> dict:
    if not sessoes:
        raise SystemExit("Nenhuma sessao ordinaria publicada nos anos do recorte.")
    return sorted(
        sessoes, key=lambda item: (item.get("data") or "", int(item["id"]))
    )[-1]


def ler_pauta(
    base: Path, anos: list[int], sessao_id: int
) -> tuple[list[dict], list[str]]:
    """Linhas da pauta da sessao, com ordem, resultado, ementa e link."""
    linhas: list[dict] = []
    gerado: list[str] = []
    for ano in anos:
        caminho = base / "dados" / "tratados" / f"tema-votacoes-{ano}.csv"
        if not caminho.is_file():
            raise SystemExit(f"Pauta ausente: {rel(base, caminho)}.")
        gerado.append(rel(base, caminho))
        with caminho.open(encoding="utf-8", newline="") as arquivo:
            for linha in csv.DictReader(arquivo):
                try:
                    sid = int((linha.get("sessao_id") or "").strip())
                except ValueError:
                    continue
                if sid != sessao_id:
                    continue
                try:
                    mid = int((linha.get("materia_id") or "").strip())
                except ValueError:
                    continue
                try:
                    ordem = int((linha.get("item_ordem_id") or "").strip())
                except ValueError:
                    ordem = None
                linhas.append(
                    {
                        "materia_id": mid,
                        "item_ordem_id": ordem,
                        "resultado": str(linha.get("resultado") or "").strip(),
                        "sigla": str(linha.get("tipo_sigla") or "").strip(),
                        "numero": str(linha.get("numero") or "").strip(),
                        "ano": str(linha.get("ano") or "").strip(),
                        "ementa": str(linha.get("ementa") or ""),
                        "link": str(linha.get("fonte_oficial") or "").strip(),
                    }
                )
    return linhas, gerado


def ler_deliberativas(
    base: Path, anos: list[int], sessao_id: int
) -> tuple[dict[int, bool], list[str]]:
    """Campo deliberativa por materia na sessao, como gravado em
    proposicoes e executivo (registro_deliberativo, sem criterio novo)."""
    mapa: dict[int, bool] = {}
    gerado: list[str] = []
    for ano in anos:
        for grupo in ("proposicoes", "executivo"):
            caminho = base / "dados" / "tratados" / f"{grupo}_{ano}.json"
            if not caminho.is_file():
                raise SystemExit(f"Consolidado ausente: {rel(base, caminho)}.")
            gerado.append(rel(base, caminho))
            dados = json.loads(caminho.read_text(encoding="utf-8"))
            for item in dados.get("todo") or []:
                if not isinstance(item, dict) or item.get("id") is None:
                    continue
                mid = int(item["id"])
                for votacao in item.get("votacoes_registradas") or []:
                    if not isinstance(votacao, dict):
                        continue
                    try:
                        sid = int(votacao.get("sessao_id"))
                    except (TypeError, ValueError):
                        continue
                    if sid != sessao_id:
                        continue
                    if votacao.get("deliberativa"):
                        mapa[mid] = True
                    else:
                        mapa.setdefault(mid, False)
    return mapa, gerado


def e_deliberativa(
    materia_id: int,
    resultado_nome: str,
    mapa_registros: dict[int, bool],
) -> tuple[bool, str]:
    """Diz se a votacao decide a materia, pelo criterio do site.

    Quando a materia tem registro em proposicoes ou executivo, vale o
    campo deliberativa gravado por registro_deliberativo. Quando nao
    tem (sigla fora desses dois grupos), vale deliberativa_nome sobre
    o nome oficial, que e a base do mesmo criterio.
    """
    if materia_id in mapa_registros:
        if mapa_registros[materia_id]:
            return True, ""
        return False, "votacao procedimental (sem deliberacao)"
    if deliberativa_nome(resultado_nome):
        return True, ""
    return False, f"votacao procedimental ({resultado_nome or 'sem resultado'})"


def montar_rodada(
    cfg: dict,
    sessao: dict,
    pauta: list[dict],
    mapa_registros: dict[int, bool],
) -> tuple[dict, dict]:
    votacao = cfg.get("votacao_popular") or {}
    elegiveis = set(votacao.get("siglas_elegiveis") or [])
    excluidas = set(votacao.get("siglas_excluidas") or [])
    dias_maximos = int(votacao.get("dias_maximos_rodada"))
    data_sessao = str(sessao.get("data") or "")
    try:
        ano_n, mes_n, dia_n = (int(parte) for parte in data_sessao.split("-"))
        fecha_ate = (date(ano_n, mes_n, dia_n) + timedelta(days=dias_maximos)).isoformat()
    except (ValueError, TypeError):
        raise SystemExit(f"Data da sessao invalida: {data_sessao!r}.")

    por_materia: dict[int, dict] = {}
    for linha in pauta:
        mid = linha["materia_id"]
        atual = por_materia.get(mid)
        ordem = linha["item_ordem_id"]
        if atual is None:
            por_materia[mid] = dict(linha)
        elif ordem is not None and (
            atual["item_ordem_id"] is None or ordem < atual["item_ordem_id"]
        ):
            por_materia[mid] = dict(linha)

    avaliadas = len(por_materia)
    materias: list[dict] = []
    excluidas_rel: list[str] = []
    avisos: list[str] = []
    for mid in sorted(
        por_materia,
        key=lambda item: (
            por_materia[item]["item_ordem_id"]
            if por_materia[item]["item_ordem_id"] is not None
            else 10**12,
            int(item),
        ),
    ):
        linha = por_materia[mid]
        sigla = linha["sigla"]
        rotulo = f"materia {mid} ({sigla} {linha['numero']}/{linha['ano']})".strip()
        if sigla in excluidas:
            excluidas_rel.append(f"{rotulo}: sigla excluida no config")
            continue
        if sigla not in elegiveis:
            excluidas_rel.append(f"{rotulo}: sigla fora da lista de elegiveis")
            continue
        ok, motivo = e_deliberativa(mid, linha["resultado"], mapa_registros)
        if not ok:
            excluidas_rel.append(f"{rotulo}: {motivo}")
            continue
        if linha["item_ordem_id"] is None:
            avisos.append(f"{rotulo}: sem item_ordem_id na pauta, ordem pelo id")
        item: dict = {
            "id": mid,
            "sigla": sigla,
            "numero": linha["numero"],
            "ano": linha["ano"],
        }
        if linha["ementa"].strip():
            item["ementa"] = linha["ementa"]
        else:
            avisos.append(f"{rotulo}: sem ementa no SAPL")
        if linha["link"]:
            item["link_sapl"] = linha["link"]
        else:
            avisos.append(f"{rotulo}: sem link no SAPL")
        item["ordem_pauta"] = linha["item_ordem_id"]
        materias.append(item)

    status = STATUS_ABERTA if materias else STATUS_SEM_MATERIAS
    rodada = {
        "rodada_id": f"sessao:{int(sessao['id'])}",
        "sessao_id": int(sessao["id"]),
        "data_sessao": data_sessao,
        "status": status,
        "fecha_ate": fecha_ate,
        "materias": materias,
        "gerado_de": [],
    }
    conferencia = {
        "avaliadas": avaliadas,
        "entraram": len(materias),
        "excluidas": excluidas_rel,
        "avisos": avisos,
    }
    return rodada, conferencia


def gerar(base: Path | None = None) -> Path:
    raiz = Path(base) if base is not None else RAIZ
    if str(raiz / "coletor") not in sys.path:
        sys.path.insert(0, str(raiz / "coletor"))
    cfg = carregar_config() if base is None else json.loads(
        (raiz / "config_cidade.json").read_text(encoding="utf-8")
    )
    anos = sorted(anos_recorte(cfg))
    sessoes, ger_sessoes = ler_sessoes(raiz, anos)
    sessao = escolher_ultima_sessao(sessoes)
    pauta, ger_pauta = ler_pauta(raiz, anos, int(sessao["id"]))
    mapa, ger_mapa = ler_deliberativas(raiz, anos, int(sessao["id"]))
    rodada, conferencia = montar_rodada(cfg, sessao, pauta, mapa)
    gerado_de = sorted(set(ger_sessoes + ger_pauta + ger_mapa))
    rodada["gerado_de"] = gerado_de

    texto = json.dumps(rodada, ensure_ascii=False, indent=2) + "\n"
    if "\r" in texto:
        raise SystemExit("Conteudo com quebra de linha CR, nada foi gravado.")
    destino = raiz / SAIDA_REL
    if destino.is_file() and destino.read_bytes() == texto.encode("utf-8"):
        print(f"Rodada {rodada['rodada_id']} sem mudanca em {rel(raiz, destino)}.")
    else:
        escrever_lf(destino, texto)
        print(f"Rodada {rodada['rodada_id']} gravada em {rel(raiz, destino)}.")

    numero = sessao.get("numero")
    print(f"Sessao ordinaria {numero}, data {rodada['data_sessao']} (registro {sessao['id']}).")
    print(f"Materias avaliadas: {conferencia['avaliadas']}.")
    print(f"Materias na rodada: {conferencia['entraram']}.")
    if conferencia["excluidas"]:
        print("Excluidas:")
        for motivo in conferencia["excluidas"]:
            print(f"  {motivo}.")
    else:
        print("Excluidas: nenhuma.")
    for aviso in conferencia["avisos"]:
        print(f"Aviso: {aviso}.")
    return destino


def main() -> int:
    gerar()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
