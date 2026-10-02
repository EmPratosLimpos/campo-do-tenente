"""Baixa o texto original de materias ja listadas nos brutos.

Nao consulta a API de novo. Le o campo texto_original nos arquivos
materialegislativa ja guardados e baixa esse arquivo, um por vez.
Pausa de 2,5 segundos entre pedidos. Teto de 8 pedidos nesta coleta.
O arquivo e gravado como veio. Ids entram pela linha de comando.

Uso:
    python coletor/baixar_textos_originais.py 274 276 284
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ / "coletor") not in sys.path:
    sys.path.insert(0, str(RAIZ / "coletor"))

from config_cidade import (  # noqa: E402
    PAUSA_SAPL_SEGUNDOS,
    carregar_config,
    conferir_url_permitida,
    endereco_sapl,
    host_da_url,
    user_agent_http,
)

TETO_PEDIDOS = 8
BRUTOS = RAIZ / "dados" / "brutos"


def agora() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def materias_locais() -> dict[int, dict]:
    indice = {}
    for caminho in sorted(BRUTOS.glob("lote_*/materialegislativa_ano*_p*.json")):
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        for materia in dados.get("results") or []:
            if materia.get("id") is None:
                continue
            indice[int(materia["id"])] = materia
    return indice


def nome_arquivo(materia_id: int, url: str) -> str:
    caminho = urllib.parse.urlparse(url).path
    ext = Path(caminho).suffix.lower() or ".bin"
    if ext not in {".pdf", ".docx", ".doc", ".odt", ".txt"}:
        ext = ".bin"
    return f"materia_{materia_id}_texto_original{ext}"


def baixar(url: str, destino: Path, user_agent: str, cfg: dict) -> int:
    """So https e host do config. Recusa antes de abrir qualquer conexao."""
    conferir_url_permitida(url, cfg, rotulo=f"texto original de {destino.name}")
    req = urllib.request.Request(url, headers={"User-Agent": user_agent}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            from config_cidade import conferir_host_final

            conferir_host_final(host_da_url(resp.geturl()), cfg, destino.name)
            corpo = resp.read()
            status = int(resp.status)
    except urllib.error.HTTPError as exc:
        corpo = exc.read()
        status = int(exc.code)
    destino.write_bytes(corpo)
    return status


def main(argv: list[str]) -> None:
    if PAUSA_SAPL_SEGUNDOS < 2.5:
        raise SystemExit("A pausa entre pedidos nao pode ser menor que 2,5 segundos.")
    ids = []
    for item in argv:
        ids.append(int(item))
    if not ids:
        raise SystemExit("Informe os ids das materias.")
    if len(ids) > TETO_PEDIDOS:
        raise SystemExit(f"Teto desta coleta: {TETO_PEDIDOS} pedidos.")
    cfg = carregar_config()
    base = endereco_sapl(cfg)
    agente = user_agent_http(cfg)
    locais = materias_locais()
    pasta = BRUTOS / f"lote_{datetime.now().strftime('%Y%m%d')}_atas"
    pasta.mkdir(parents=True, exist_ok=True)
    pedidos = []
    for indice, materia_id in enumerate(ids):
        materia = locais.get(materia_id)
        if materia is None:
            raise SystemExit(f"Materia {materia_id} nao esta nos brutos locais.")
        url = (materia.get("texto_original") or "").strip()
        if not url:
            raise SystemExit(f"Materia {materia_id} sem texto_original nos brutos.")
        if indice:
            time.sleep(PAUSA_SAPL_SEGUNDOS)
        arquivo = nome_arquivo(materia_id, url)
        quando = agora()
        status = baixar(url, pasta / arquivo, agente, cfg)
        pedidos.append(
            {
                "n": indice + 1,
                "materia_id": materia_id,
                "url": url,
                "quando": quando,
                "status": status,
                "arquivo": arquivo,
            }
        )
        print(f"  [{indice + 1:03d}/{TETO_PEDIDOS}] {status} {arquivo}")
        if status != 200:
            gravar_indice(pasta, base, pedidos)
            raise SystemExit(f"Pedido falhou: {url} (HTTP {status})")
    gravar_indice(pasta, base, pedidos)
    print(f"Pasta dados/brutos/{pasta.name}")


def gravar_indice(pasta: Path, base: str, pedidos: list[dict]) -> None:
    dado = {
        "fonte": base,
        "pausa_segundos": PAUSA_SAPL_SEGUNDOS,
        "teto_pedidos": TETO_PEDIDOS,
        "total_pedidos": len(pedidos),
        "atualizado_em": agora(),
        "pedidos": pedidos,
    }
    texto = json.dumps(dado, ensure_ascii=False, indent=2) + "\n"
    (pasta / "indice.json").write_bytes(texto.encode("utf-8"))


if __name__ == "__main__":
    main(sys.argv[1:])
