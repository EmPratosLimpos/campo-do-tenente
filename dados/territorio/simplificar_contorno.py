#!/usr/bin/env python3
"""Simplifica o contorno municipal do IBGE e confere ponto dentro do poligono.

Uso:
    python dados/territorio/simplificar_contorno.py --tolerancia-m 60

Leitura:
    - codigo do municipio sai de config_cidade.json (cidade.codigo_ibge),
      nunca fixo aqui;
    - entrada padrao: dados/territorio/<codigo>_malha_ibge.geojson;
    - saida padrao: dados/territorio/<codigo>_contorno_simplificado.json.

Metodo:
    - Douglas-Peucker em Python puro, sem pacote novo;
    - contas em metros num plano local (equiretangular em torno do
      centroide do anel), tolerancia em metros configuravel;
    - ponto-no-poligono por lancamento de raio, com suporte a
      MultiPolygon e a buraco (anel interno).

Saida simplificada: GeoJSON FeatureCollection com um Feature de
Polygon ou MultiPolygon, e propriedades com codigo, tolerancia,
pontos antes e depois e maior desvio em metros.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
ARQUIVO_CONFIG = RAIZ / "config_cidade.json"

METROS_POR_GRAU_LAT = 111320.0


def codigo_ibge_do_config() -> str:
    dados = json.loads(ARQUIVO_CONFIG.read_text(encoding="utf-8"))
    codigo = str(((dados.get("cidade") or {}).get("codigo_ibge")) or "").strip()
    if not codigo.isdigit():
        raise SystemExit(
            "config_cidade.json: cidade.codigo_ibge ausente ou invalido. "
            "O mantenedor precisa confirmar o codigo do IBGE."
        )
    return codigo


def _para_plano(lon: float, lat: float, lon0: float, lat0: float) -> tuple[float, float]:
    kx = METROS_POR_GRAU_LAT * math.cos(math.radians(lat0))
    x = (lon - lon0) * kx
    y = (lat - lat0) * METROS_POR_GRAU_LAT
    return (x, y)


def _dist_ponto_segmento(px, py, ax, ay, bx, by) -> float:
    dx = bx - ax
    dy = by - ay
    if dx == 0.0 and dy == 0.0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def douglas_peucker(
    pontos: list[tuple[float, float]], tolerancia_m: float, lon0: float, lat0: float
) -> list[tuple[float, float]]:
    """Simplifica uma linha aberta. Devolve subconjunto dos pontos de entrada."""
    if tolerancia_m < 0:
        raise ValueError("tolerancia em metros nao pode ser negativa")
    if len(pontos) <= 2:
        return list(pontos)
    planos = [_para_plano(lon, lat, lon0, lat0) for lon, lat in pontos]
    manter = [False] * len(pontos)
    manter[0] = True
    manter[-1] = True
    pilha = [(0, len(pontos) - 1)]
    while pilha:
        ini, fim = pilha.pop()
        if fim - ini < 2:
            continue
        ax, ay = planos[ini]
        bx, by = planos[fim]
        maior = 0.0
        pos = -1
        for i in range(ini + 1, fim):
            d = _dist_ponto_segmento(planos[i][0], planos[i][1], ax, ay, bx, by)
            if d > maior:
                maior = d
                pos = i
        if maior > tolerancia_m and pos > 0:
            manter[pos] = True
            pilha.append((ini, pos))
            pilha.append((pos, fim))
    return [p for p, m in zip(pontos, manter) if m]


def simplificar_anel(anel: list, tolerancia_m: float) -> list:
    """Simplifica um anel fechado [lon, lat, ...]. Mantem o fecho."""
    pts = [(float(p[0]), float(p[1])) for p in anel]
    if len(pts) <= 4:
        return [[lon, lat] for lon, lat in pts]
    fechado = pts[0] == pts[-1]
    base = pts[:-1] if fechado else list(pts)
    lon0 = sum(p[0] for p in base) / len(base)
    lat0 = sum(p[1] for p in base) / len(base)
    # Gira o anel para comecar no ponto mais a leste: resultado estavel.
    ini = max(range(len(base)), key=lambda i: base[i][0])
    ordem = base[ini:] + base[:ini] + [base[ini]]
    # Linha aberta do primeiro ao ultimo (iguais): simplifica o meio.
    simpl = douglas_peucker(ordem, tolerancia_m, lon0, lat0)
    if simpl[0] != simpl[-1]:
        simpl.append(simpl[0])
    return [[lon, lat] for lon, lat in simpl]


def desvio_maximo_m(original: list, simplificado: list) -> float:
    """Maior distancia em metros de cada ponto original ate a linha simplificada."""
    if len(original) < 2 or len(simplificado) < 2:
        return 0.0
    lon0 = sum(float(p[0]) for p in original) / len(original)
    lat0 = sum(float(p[1]) for p in original) / len(original)
    o = [_para_plano(float(p[0]), float(p[1]), lon0, lat0) for p in original]
    s = [_para_plano(float(p[0]), float(p[1]), lon0, lat0) for p in simplificado]
    maior = 0.0
    for px, py in o:
        menor = min(
            _dist_ponto_segmento(px, py, s[i][0], s[i][1], s[i + 1][0], s[i + 1][1])
            for i in range(len(s) - 1)
        )
        maior = max(maior, menor)
    return maior


def ponto_no_anel(lon: float, lat: float, anel: list) -> bool:
    """Lancamento de raio. Borda conta como dentro."""
    dentro = False
    n = len(anel)
    if n < 3:
        return False
    for i in range(n):
        x1, y1 = float(anel[i][0]), float(anel[i][1])
        x2, y2 = float(anel[(i + 1) % n][0]), float(anel[(i + 1) % n][1])
        # Ponto exatamente sobre o segmento: dentro.
        if _dist_grau(lon, lat, x1, y1, x2, y2) == 0.0:
            return True
        if ((y1 > lat) != (y2 > lat)):
            xinters = (x2 - x1) * (lat - y1) / (y2 - y1) + x1
            if lon < xinters:
                dentro = not dentro
    return dentro


def _dist_grau(px, py, ax, ay, bx, by) -> float:
    dx = bx - ax
    dy = by - ay
    if dx == 0.0 and dy == 0.0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def ponto_no_poligono(lon: float, lat: float, coords: list) -> bool:
    """coords: [anel externo, buraco1, ...]. Buraco nunca conta como dentro."""
    if not coords:
        return False
    if not ponto_no_anel(lon, lat, coords[0]):
        return False
    for buraco in coords[1:]:
        if ponto_no_anel(lon, lat, buraco):
            return False
    return True


def geometria_contem(lon: float, lat: float, geometria: dict) -> bool:
    tipo = (geometria or {}).get("type")
    coords = (geometria or {}).get("coordinates") or []
    if tipo == "Polygon":
        return ponto_no_poligono(lon, lat, coords)
    if tipo == "MultiPolygon":
        return any(ponto_no_poligono(lon, lat, poly) for poly in coords)
    return False


def dentro_do_contorno(lon: float, lat: float, geojson: dict) -> bool:
    """Aceita FeatureCollection, Feature ou geometria pura."""
    if not isinstance(geojson, dict):
        return False
    tipo = geojson.get("type")
    if tipo == "FeatureCollection":
        feats = geojson.get("features") or []
        return any(
            geometria_contem(lon, lat, (f or {}).get("geometry") or {})
            for f in feats
            if isinstance(f, dict)
        )
    if tipo == "Feature":
        return geometria_contem(lon, lat, geojson.get("geometry") or {})
    return geometria_contem(lon, lat, geojson)


def simplificar_geometria(geometria: dict, tolerancia_m: float) -> tuple[dict, dict]:
    tipo = geometria.get("type")
    if tipo == "Polygon":
        aneis = geometria.get("coordinates") or []
        novos = [simplificar_anel(a, tolerancia_m) for a in aneis]
        antes = sum(len(a) for a in aneis)
        depois = sum(len(a) for a in novos)
        desvio = max(
            (desvio_maximo_m(a, b) for a, b in zip(aneis, novos)), default=0.0
        )
        return {"type": "Polygon", "coordinates": novos}, {
            "pontos_antes": antes,
            "pontos_depois": depois,
            "desvio_maximo_m": round(desvio, 2),
        }
    if tipo == "MultiPolygon":
        novos_polys = []
        antes = depois = 0
        desvio = 0.0
        for poly in geometria.get("coordinates") or []:
            novos = [simplificar_anel(a, tolerancia_m) for a in poly]
            novos_polys.append(novos)
            antes += sum(len(a) for a in poly)
            depois += sum(len(a) for a in novos)
            for a, b in zip(poly, novos):
                desvio = max(desvio, desvio_maximo_m(a, b))
        return {"type": "MultiPolygon", "coordinates": novos_polys}, {
            "pontos_antes": antes,
            "pontos_depois": depois,
            "desvio_maximo_m": round(desvio, 2),
        }
    raise SystemExit(f"Geometria {tipo} nao suportada para simplificar.")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Simplifica o contorno do IBGE.")
    ap.add_argument("--tolerancia-m", type=float, default=60.0)
    ap.add_argument("--codigo", type=str, default="")
    ap.add_argument("--entrada", type=str, default="")
    ap.add_argument("--saida", type=str, default="")
    args = ap.parse_args(argv)
    if args.tolerancia_m < 0:
        raise SystemExit("Tolerancia em metros nao pode ser negativa.")
    codigo = args.codigo.strip() or codigo_ibge_do_config()
    pasta = RAIZ / "dados" / "territorio"
    entrada = Path(args.entrada) if args.entrada else pasta / f"{codigo}_malha_ibge.geojson"
    saida = Path(args.saida) if args.saida else pasta / f"{codigo}_contorno_simplificado.json"
    geo = json.loads(entrada.read_text(encoding="utf-8"))
    feats = geo.get("features") or []
    if not feats:
        raise SystemExit("Malha do IBGE sem features.")
    geometria = feats[0].get("geometry") or {}
    nova_geom, stats = simplificar_geometria(geometria, float(args.tolerancia_m))
    saida.write_bytes(
        (
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "properties": {
                                "codarea": codigo,
                                "codigo_ibge": codigo,
                                "tolerancia_m": float(args.tolerancia_m),
                                **stats,
                            },
                            "geometry": nova_geom,
                        }
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        ).encode("utf-8")
    )
    print(
        f"pontos antes={stats['pontos_antes']} "
        f"depois={stats['pontos_depois']} "
        f"desvio_maximo_m={stats['desvio_maximo_m']} "
        f"tolerancia_m={float(args.tolerancia_m)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
