#!/usr/bin/env python3
"""Gera JSON da aba Câmara (materias_camara, materias_tags, filtros_materia) por ano."""

from __future__ import annotations

import json
import pathlib
import sys
from datetime import datetime, timezone, timedelta

RAIZ = pathlib.Path(__file__).resolve().parent.parent.parent
if str(RAIZ / "coletor") not in sys.path:
    sys.path.insert(0, str(RAIZ / "coletor"))

from config_cidade import anos_recorte, carregar_config  # noqa: E402

TZ = timezone(timedelta(hours=-3))


def normalizar_resultado(resultado_texto: str | None, frase: str | None) -> str:
    texto = " ".join(filter(None, [resultado_texto, frase])).upper()
    if "UNANIM" in texto:
        return "unanimidade"
    if "MAIORIA" in texto or "ABSOLUT" in texto:
        return "maioria"
    return "unanimidade"


def placar_resumido(vot: dict) -> str:
    tot = vot.get("totais_oficiais") or {}
    sim = tot.get("numero_votos_sim")
    nao = tot.get("numero_votos_nao")
    if sim is None and nao is None:
        return ""
    return f"{sim or 0} x {nao or 0}"


def tema_display(tema_bruto: str, cfg: dict) -> str:
    especiais = cfg.get("categorias", {}).get("rotulos_especiais", {})
    if tema_bruto in especiais.values() or tema_bruto.lower() in (
        especiais.get("nao_se_aplica", "").lower(),
        especiais.get("sem_ementa", "").lower(),
    ):
        return tema_bruto
    for item in cfg.get("categorias", {}).get("lista", []):
        if item["nome"].lower() == str(tema_bruto).lower():
            return item["nome"]
    return tema_bruto


def carregar_temas() -> dict[int, str]:
    path = RAIZ / "dados" / "tratados" / "temas_materias.json"
    dados = json.loads(path.read_text(encoding="utf-8"))
    return {int(m["id"]): m["tema"] for m in dados.get("materias", [])}


def pll_votados_no_ano(atuacao: dict) -> list[dict]:
    itens = []
    for p in atuacao.get("projetos_lei", []):
        if p.get("tipo_sigla") != "PLEG":
            continue
        votos = p.get("votacoes_ordinarias") or []
        if not votos:
            continue
        ultima = max(votos, key=lambda v: v.get("data_sessao") or "")
        if not ultima.get("situacao_oficial_sapl") and not ultima.get("resultado_texto_sapl"):
            continue
        itens.append(
            {
                "projeto": p,
                "votacao": ultima,
            }
        )
    return itens


def montar_item(entry: dict, cfg: dict, temas: dict[int, str]) -> dict:
    p = entry["projeto"]
    v = entry["votacao"]
    mid = int(p["id"])
    tema_bruto = temas.get(mid) or p.get("tema") or "Outros"
    tema = tema_display(tema_bruto, cfg)
    resultado = normalizar_resultado(v.get("resultado_texto_sapl"), v.get("frase_resultado_sapl"))
    tipo = f"PLL {p.get('numero')}/{p.get('ano')}"
    return {
        "id": mid,
        "tipo": tipo,
        "resultado": resultado,
        "ementa": p.get("ementa") or "",
        "categoria": tema,
        "placar": placar_resumido(v),
        "data_sessao": v.get("data_sessao"),
        "sessao_id": v.get("sessao_id"),
    }


def periodos(lista: list[dict], sessoes: list[dict]) -> tuple[list, list, list]:
    if not lista:
        return [], [], []
    datas = sorted({s["data"] for s in sessoes if s.get("data")})
    ultima_data = datas[-1] if datas else None
    sessao_ids_ultima = {s["id"] for s in sessoes if s.get("data") == ultima_data}

    sessao = [m for m in lista if m.get("sessao_id") in sessao_ids_ultima]

    if ultima_data:
        y, mo, _ = map(int, ultima_data.split("-"))
        mes_ant = mo - 1
        ano_ant = y
        if mes_ant < 1:
            mes_ant = 12
            ano_ant -= 1
    else:
        ano_ant, mes_ant = 0, 0

    mes = [
        m
        for m in lista
        if m.get("data_sessao")
        and int(m["data_sessao"].split("-")[0]) == ano_ant
        and int(m["data_sessao"].split("-")[1]) == mes_ant
    ]
    todo = list(lista)
    return sessao, mes, todo


def filtros_de(lista: list[dict]) -> list[dict]:
    total = len(lista)
    uni = sum(1 for m in lista if m["resultado"] == "unanimidade")
    mai = total - uni
    return [
        {"id": "", "rotulo": "Todos", "qtd": total},
        {"id": "unanimidade", "rotulo": "Unânimes", "qtd": uni},
        {"id": "maioria", "rotulo": "Maioria", "qtd": mai},
    ]


def gerar_ano(ano: int, cfg: dict) -> None:
    path = RAIZ / "dados" / "tratados" / f"atuacao_vereadores_{ano}.json"
    atuacao = json.loads(path.read_text(encoding="utf-8"))
    temas = carregar_temas()
    bruto = pll_votados_no_ano(atuacao)
    lista = [montar_item(e, cfg, temas) for e in bruto]
    sessao, mes, todo = periodos(lista, atuacao.get("sessoes") or [])

    camara = {"sessao": sessao, "mes": mes, "todo": todo}
    tags = {
        str(m["id"]): {"tag_tipo": "PLL", "tag_tema": m["categoria"]}
        for m in lista
    }
    filtros = {
        "sessao": filtros_de(sessao),
        "mes": filtros_de(mes),
        "todo": filtros_de(todo),
    }

    out = RAIZ / "dados" / "tratados"
    (out / f"materias_camara_{ano}.json").write_text(
        json.dumps(camara, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out / f"materias_tags_{ano}.json").write_text(
        json.dumps(tags, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out / f"filtros_materia_{ano}.json").write_text(
        json.dumps(filtros, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Ano {ano}: sessao={len(sessao)} mes={len(mes)} todo={len(todo)} PLL")


def main():
    cfg = carregar_config()
    for ano in anos_recorte(cfg):
        gerar_ano(ano, cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
