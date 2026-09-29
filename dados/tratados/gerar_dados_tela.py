#!/usr/bin/env python3
"""Gera JSON da aba Câmara e consolidado da legislatura (soma dos anos do recorte)."""

from __future__ import annotations

import copy
import json
import pathlib
import sys
from datetime import datetime, timezone, timedelta

RAIZ = pathlib.Path(__file__).resolve().parent.parent.parent
if str(RAIZ / "coletor") not in sys.path:
    sys.path.insert(0, str(RAIZ / "coletor"))

from config_cidade import anos_recorte, carregar_config  # noqa: E402

TZ = timezone(timedelta(hours=-3))
SUFIXO_LEGISLATURA = "legislatura"

RESULTADO_NAO_MAPEADO = "resultado_nao_mapeado"

CHAVES_CONTAGEM_VOTO = (
    "sim",
    "nao",
    "abstencao",
    "nao_votou",
    "presidente_que_nao_votou",
    "ausente_com_justificativa",
    "ausente_sem_justificativa",
    "fora_do_mandato",
    "presente_sem_voto_individual_registrado",
    "licenca_tratamento_saude",
)

CHAVES_META_SOMA = (
    "n_sessoes_ordinarias",
    "n_presencas",
    "n_faltas_com_justificativa",
    "n_faltas_sem_justificativa",
    "n_sessoes_fora_do_mandato",
    "n_sessoes_licenca",
    "n_votacoes",
    "n_registros_votacao",
    "n_votacoes_com_voto_individual",
    "n_votacoes_sem_voto_individual",
    "n_projetos_lei_legislativo",
    "n_projetos_lei_executivo",
    "n_projetos_lei_legislativo_e_executivo",
)


def normalizar_resultado(resultado_texto: str | None, frase: str | None) -> tuple[str, str | None]:
    oficial = " ".join(filter(None, [resultado_texto, frase])).strip()
    texto = oficial.upper()
    if "UNANIM" in texto:
        return "unanimidade", oficial or None
    if "REJEIT" in texto:
        return "rejeitado", oficial or None
    if "MAIORIA" in texto or "ABSOLUT" in texto:
        return "maioria", oficial or None
    if "APROV" in texto and "REJEIT" not in texto:
        return "maioria", oficial or None
    if not texto:
        return RESULTADO_NAO_MAPEADO, oficial or None
    return RESULTADO_NAO_MAPEADO, oficial or None


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
    resultado, resultado_oficial = normalizar_resultado(
        v.get("resultado_texto_sapl"), v.get("frase_resultado_sapl")
    )
    tipo = f"PLL {p.get('numero')}/{p.get('ano')}"
    return {
        "id": mid,
        "tipo": tipo,
        "resultado": resultado,
        "resultado_oficial": resultado_oficial,
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
    mai = sum(1 for m in lista if m["resultado"] == "maioria")
    rej = sum(1 for m in lista if m["resultado"] == "rejeitado")
    outro = total - uni - mai - rej
    filtros = [
        {"id": "", "rotulo": "Todos", "qtd": total},
        {"id": "unanimidade", "rotulo": "Unânimes", "qtd": uni},
        {"id": "maioria", "rotulo": "Maioria", "qtd": mai},
    ]
    if rej:
        filtros.append({"id": "rejeitado", "rotulo": "Rejeitados", "qtd": rej})
    if outro:
        filtros.append(
            {"id": RESULTADO_NAO_MAPEADO, "rotulo": "Resultado não mapeado", "qtd": outro}
        )
    return filtros


def gravar_camara(sufixo: str, sessao: list, mes: list, todo: list, lista: list, out: pathlib.Path) -> None:
    camara = {"sessao": sessao, "mes": mes, "todo": todo}
    tags = {}
    try:
        import json
        with open(RAIZ / "dados" / "tratados" / "temas_materias.json", "r", encoding="utf-8") as f_temas:
            todas = json.load(f_temas)
            for mat in todas.get("materias", []):
                tags[str(mat["id"])] = {
                    "tag_tipo": mat.get("sigla", "Outros"),
                    "tag_tema": mat.get("tema", "Outros")
                }
    except Exception:
        pass
    # Sobrepõe com a lista atual caso necessário
    for m in lista:
        tags[str(m["id"])] = {"tag_tipo": "PLL", "tag_tema": m["categoria"]}
    filtros = {
        "sessao": filtros_de(sessao),
        "mes": filtros_de(mes),
        "todo": filtros_de(todo),
    }
    (out / f"materias_camara_{sufixo}.json").write_text(
        json.dumps(camara, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out / f"materias_tags_{sufixo}.json").write_text(
        json.dumps(tags, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out / f"filtros_materia_{sufixo}.json").write_text(
        json.dumps(filtros, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def gerar_ano(ano: int, cfg: dict) -> None:
    path = RAIZ / "dados" / "tratados" / f"atuacao_vereadores_{ano}.json"
    atuacao = json.loads(path.read_text(encoding="utf-8"))
    temas = carregar_temas()
    bruto = pll_votados_no_ano(atuacao)
    lista = [montar_item(e, cfg, temas) for e in bruto]
    sessao, mes, todo = periodos(lista, atuacao.get("sessoes") or [])
    out = RAIZ / "dados" / "tratados"
    gravar_camara(str(ano), sessao, mes, todo, lista, out)
    print(f"Ano {ano}: sessao={len(sessao)} mes={len(mes)} todo={len(todo)} PLL")


def _ordenar_sessoes(sessoes: list[dict]) -> list[dict]:
    vistos: dict[int, dict] = {}
    for s in sessoes:
        sid = s.get("id")
        if sid is None:
            continue
        vistos[int(sid)] = s
    return sorted(vistos.values(), key=lambda x: (x.get("data") or "", x.get("id") or 0))


def _mesclar_por_categoria(a: dict, b: dict) -> dict:
    out = dict(a or {})
    for chave, val in (b or {}).items():
        out[chave] = out.get(chave, 0) + val
    return out


def _mesclar_projetos_lei_vereador(a: dict, b: dict) -> dict:
    out = copy.deepcopy(a or {})
    bb = b or {}
    for chave in (
        "total_propostos",
        "aprovados",
        "rejeitados",
        "em_tramitacao",
        "outro_resultado_oficial",
        "autorias_conjuntas",
    ):
        out[chave] = (out.get(chave) or 0) + (bb.get(chave) or 0)
    out["por_categoria"] = _mesclar_por_categoria(
        out.get("por_categoria") or {}, bb.get("por_categoria") or {}
    )
    lista = list(out.get("lista") or [])
    ids = {item.get("id") for item in lista if item.get("id") is not None}
    for item in bb.get("lista") or []:
        iid = item.get("id")
        if iid is not None and iid in ids:
            continue
        lista.append(item)
        if iid is not None:
            ids.add(iid)
    out["lista"] = lista
    return out


def _recomputar_presenca(por_sessao: list[dict]) -> dict:
    cont = {
        "presente": 0,
        "falta_com_justificativa": 0,
        "falta_sem_justificativa": 0,
        "licenca_tratamento_saude": 0,
        "fora_do_mandato": 0,
    }
    for s in por_sessao:
        sit = s.get("situacao") or ""
        if sit in cont:
            cont[sit] += 1
    presencas = cont["presente"]
    faltas_j = cont["falta_com_justificativa"]
    faltas_s = cont["falta_sem_justificativa"]
    licenca = cont["licenca_tratamento_saude"]
    fora = cont["fora_do_mandato"]
    no_mandato = presencas + faltas_j + faltas_s
    total_sessoes = len(por_sessao)
    taxa = round((presencas / no_mandato) * 100, 2) if no_mandato else 0.0
    pct_faltas = round(((faltas_j + faltas_s) / no_mandato) * 100, 2) if no_mandato else 0.0
    por_afast = {}
    if licenca:
        por_afast["licenca_tratamento_saude"] = licenca
    return {
        "sessoes_ordinarias": no_mandato,
        "sessoes_do_ano": total_sessoes,
        "sessoes_fora_do_mandato": fora,
        "sessoes_licenca": licenca,
        "sessoes_por_afastamento": por_afast,
        "presencas": presencas,
        "faltas_com_justificativa": faltas_j,
        "faltas_sem_justificativa": faltas_s,
        "faltas_totais": faltas_j + faltas_s,
        "percentual_faltas": pct_faltas,
        "taxa_presenca": taxa,
        "por_sessao": por_sessao,
    }


def _mesclar_votos(a: dict, b: dict) -> dict:
    out = copy.deepcopy(a or {})
    bb = b or {}
    for chave in CHAVES_CONTAGEM_VOTO:
        out[chave] = (out.get(chave) or 0) + (bb.get(chave) or 0)
    if bb.get("rotulos"):
        out["rotulos"] = bb["rotulos"]
    nominais = list(out.get("nominais") or [])
    chaves = {
        (n.get("votacao_id"), n.get("sessao_id"), n.get("materia_id")) for n in nominais
    }
    for n in bb.get("nominais") or []:
        chave = (n.get("votacao_id"), n.get("sessao_id"), n.get("materia_id"))
        if chave in chaves:
            continue
        nominais.append(n)
        chaves.add(chave)
    nominais.sort(key=lambda x: (x.get("data_sessao") or "", x.get("votacao_id") or 0))
    out["nominais"] = nominais
    out["total_registros"] = len(nominais)
    return out


def _mesclar_afastamentos(a: list, b: list) -> list:
    out = list(a or [])
    vistos = {
        (
            x.get("tipo"),
            x.get("data_inicio"),
            x.get("data_fim"),
            x.get("rotulo"),
        )
        for x in out
    }
    for item in b or []:
        chave = (item.get("tipo"), item.get("data_inicio"), item.get("data_fim"), item.get("rotulo"))
        if chave in vistos:
            continue
        out.append(item)
        vistos.add(chave)
    return out


def _mesclar_vereador(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    por_sessao = list(out.get("presenca", {}).get("por_sessao") or [])
    ids_sess = {s.get("sessao_id") for s in por_sessao}
    for s in (extra.get("presenca") or {}).get("por_sessao") or []:
        if s.get("sessao_id") in ids_sess:
            continue
        por_sessao.append(s)
        ids_sess.add(s.get("sessao_id"))
    por_sessao.sort(key=lambda x: (x.get("data_sessao") or "", x.get("sessao_id") or 0))
    out["presenca"] = _recomputar_presenca(por_sessao)
    out["votos"] = _mesclar_votos(out.get("votos") or {}, extra.get("votos") or {})
    out["projetos_lei"] = _mesclar_projetos_lei_vereador(
        out.get("projetos_lei") or {}, extra.get("projetos_lei") or {}
    )
    out["afastamentos"] = _mesclar_afastamentos(
        out.get("afastamentos") or [], extra.get("afastamentos") or []
    )
    anos = sorted(set((out.get("anos_com_mandato") or []) + (extra.get("anos_com_mandato") or [])))
    out["anos_com_mandato"] = anos
    for campo in ("data_inicio_mandato", "data_fim_mandato"):
        va = out.get(campo)
        vb = extra.get(campo)
        if va and vb:
            if campo == "data_inicio_mandato":
                out[campo] = min(va, vb)
            else:
                out[campo] = max(va, vb)
        elif vb and not va:
            out[campo] = vb
    if extra.get("nota_factual") and not out.get("nota_factual"):
        out["nota_factual"] = extra["nota_factual"]
    return out


def _mesclar_projetos_lei_raiz(listas: list[list]) -> list[dict]:
    por_id: dict[int, dict] = {}
    for lista in listas:
        for p in lista:
            pid = p.get("id")
            if pid is None:
                continue
            por_id[int(pid)] = p

    return list(por_id.values())



def _parse_coleta_em(meta: dict) -> datetime:
    raw = (meta or {}).get("dado_coletado_em") or ""
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=TZ)


def mesclar_atuacao_legislatura(dados_por_ano: list[dict], anos: list[int], cfg: dict) -> dict:
    if not dados_por_ano:
        raise ValueError("sem dados para mesclar")
    base_meta = copy.deepcopy(dados_por_ano[-1]["meta"])
    base_meta["anos_recorte"] = anos
    base_meta.pop("ano", None)
    base_meta["escopo"] = SUFIXO_LEGISLATURA
    base_meta["gerado_por"] = "dados/tratados/gerar_dados_tela.py"
    lacuna_por_ano: dict[str, dict] = {}
    for d in dados_por_ano:
        ano = d["meta"].get("ano")
        lac = d["meta"].get("lacuna_sessoes_ordinarias")
        if ano is not None and lac:
            lacuna_por_ano[str(int(ano))] = copy.deepcopy(lac)
    base_meta.pop("lacuna_sessoes_ordinarias", None)
    if lacuna_por_ano:
        base_meta["lacuna_sessoes_ordinarias_por_ano"] = lacuna_por_ano

    for chave in CHAVES_META_SOMA:
        base_meta[chave] = sum((d["meta"].get(chave) or 0) for d in dados_por_ano)

    contagem = {ch: 0 for ch in CHAVES_CONTAGEM_VOTO}
    for d in dados_por_ano:
        parcial = (d["meta"].get("contagem_estados") or {})
        for ch in CHAVES_CONTAGEM_VOTO:
            contagem[ch] += parcial.get(ch) or 0
    base_meta["contagem_estados"] = contagem

    coletas = [_parse_coleta_em(d["meta"]) for d in dados_por_ano]
    mais_recente = max(coletas)
    base_meta["dado_coletado_em"] = mais_recente.isoformat()
    base_meta["n_vereadores"] = len(
        {
            v["id_sapl"]
            for d in dados_por_ano
            for v in d.get("vereadores") or []
        }
    )

    sessoes = _ordenar_sessoes([s for d in dados_por_ano for s in (d.get("sessoes") or [])])
    projetos = _mesclar_projetos_lei_raiz([d.get("projetos_lei") or [] for d in dados_por_ano])

    por_id: dict[int, dict] = {}
    ordem: list[int] = []
    for d in dados_por_ano:
        for v in d.get("vereadores") or []:
            vid = int(v["id_sapl"])
            if vid not in por_id:
                por_id[vid] = copy.deepcopy(v)
                ordem.append(vid)
            else:
                por_id[vid] = _mesclar_vereador(por_id[vid], v)


    try:
        with open(RAIZ / "dados" / "tratados" / "afastamentos_manuais.json", "r", encoding="utf-8") as f:
            manuais = json.load(f)
            motivos = manuais.get("motivos_fora_do_mandato") or []
            for m in motivos:
                vid_sapl = m.get("parlamentar_id_sapl")
                if vid_sapl in por_id:
                    if "motivos_fora_do_mandato" not in por_id[vid_sapl]:
                        por_id[vid_sapl]["motivos_fora_do_mandato"] = []
                    por_id[vid_sapl]["motivos_fora_do_mandato"].append(m)
    except Exception as e:
        pass

    vereadores = [por_id[i] for i in ordem]

    return {
        "meta": base_meta,
        "sessoes": sessoes,
        "projetos_lei": projetos,
        "vereadores": vereadores,
    }


def gerar_legislatura(cfg: dict) -> None:
    anos = anos_recorte(cfg)
    dados = []
    for ano in anos:
        path = RAIZ / "dados" / "tratados" / f"atuacao_vereadores_{ano}.json"
        dados.append(json.loads(path.read_text(encoding="utf-8")))
    consolidado = mesclar_atuacao_legislatura(dados, anos, cfg)
    out = RAIZ / "dados" / "tratados"
    dest = out / f"atuacao_vereadores_{SUFIXO_LEGISLATURA}.json"
    dest.write_text(json.dumps(consolidado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    temas = carregar_temas()
    bruto = pll_votados_no_ano(consolidado)
    lista = [montar_item(e, cfg, temas) for e in bruto]
    sessao, mes, todo = periodos(lista, consolidado.get("sessoes") or [])
    gravar_camara(SUFIXO_LEGISLATURA, sessao, mes, todo, lista, out)
    print(
        f"Legislatura {anos}: sessao={len(sessao)} mes={len(mes)} todo={len(todo)} PLL, "
        f"{len(consolidado['vereadores'])} vereadores"
    )


def main():
    cfg = carregar_config()
    for ano in anos_recorte(cfg):
        gerar_ano(ano, cfg)
    gerar_legislatura(cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
