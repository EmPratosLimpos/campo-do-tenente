"""Baixa o acervo de 2025 e 2026 do SAPL em lote, pagina por pagina.

Um pedido por vez. Pausa de PAUSA_SAPL_SEGUNDOS entre pedidos.
Nao usa o filtro sessao_plenaria em registrovotacao nem em votoparlamentar:
nesse SAPL esse filtro e ignorado e devolve o acervo inteiro.

Cada resposta e gravada exatamente como veio em
dados/brutos/lote_<AAAAMMDD>/. Pagina que ja existe nessa pasta, com HTTP 200
no indice, nao e baixada de novo. O bruto nao e editado.

Rodar:  python coletor/coletar_lote.py
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from config_cidade import (
    PAUSA_SAPL_SEGUNDOS,
    anos_recorte,
    carregar_config,
    endereco_sapl,
    user_agent_http,
)

PAGE_SIZE = 100
TEMPO_LIMITE = 120
TETO_PEDIDOS = 200
MAX_REPETICOES = 2
ESPERA_RECUSA = (30, 60)

RAIZ = Path(__file__).resolve().parent.parent
BRUTOS = RAIZ / "dados" / "brutos"


class OrcamentoEsgotado(Exception):
    pass


def agora() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def montar_url(base: str, caminho: str, params: dict | None) -> str:
    url = base.rstrip("/") + caminho
    if not params:
        return url
    query = urllib.parse.urlencode(params, doseq=True)
    return url + "?" + query


def indice_tem(indice_api: dict | None, chave: str) -> bool:
    return isinstance(indice_api, dict) and chave in indice_api


def plano_de_coleta(anos: list[int], indice_api: dict | None) -> list[dict]:
    """Lista os recursos do caminho em lote. Nao inclui o indice da API.

    registrovotacao e votoparlamentar entram sem sessao_plenaria.
    """
    catalogos = [
        ("/api/sessao/tiposessaoplenaria/", "tiposessaoplenaria"),
        ("/api/parlamentares/legislatura/", "legislatura"),
        ("/api/parlamentares/mandato/", "mandato"),
        ("/api/parlamentares/parlamentar/", "parlamentar"),
        ("/api/materia/tipomaterialegislativa/", "tipomaterialegislativa"),
        ("/api/sessao/tiporesultadovotacao/", "tiporesultadovotacao"),
        ("/api/sessao/tipojustificativa/", "tipojustificativa"),
    ]
    opcionais = [
        ("parlamentares/tipoafastamento", "/api/parlamentares/tipoafastamento/", "tipoafastamento"),
        ("parlamentares/partido", "/api/parlamentares/partido/", "partido"),
        ("parlamentares/filiacao", "/api/parlamentares/filiacao/", "filiacao"),
    ]
    plano = []
    for caminho, prefixo in catalogos:
        plano.append(_paginado(caminho, {}, prefixo))
    for chave, caminho, prefixo in opcionais:
        if indice_tem(indice_api, chave):
            plano.append(_paginado(caminho, {}, prefixo))
    for ano in anos:
        plano.append(
            _paginado(
                "/api/sessao/sessaoplenaria/",
                {"data_inicio__year": int(ano)},
                f"sessaoplenaria_ano{int(ano)}",
            )
        )
    plano.append(_paginado("/api/sessao/registrovotacao/", {}, "registrovotacao"))
    plano.append(_paginado("/api/sessao/votoparlamentar/", {}, "votoparlamentar"))
    plano.append(_paginado("/api/sessao/ordemdia/", {}, "ordemdia"))
    plano.append(_paginado("/api/sessao/expedientemateria/", {}, "expedientemateria"))
    for ano in anos:
        plano.append(
            _paginado(
                "/api/materia/materialegislativa/",
                {"ano": int(ano)},
                f"materialegislativa_ano{int(ano)}",
            )
        )
    plano.append(_paginado("/api/sessao/sessaoplenariapresenca/", {}, "sessaoplenariapresenca"))
    plano.append(_paginado("/api/sessao/presencaordemdia/", {}, "presencaordemdia"))
    plano.append(_paginado("/api/sessao/justificativaausencia/", {}, "justificativaausencia"))
    plano.append(_paginado("/api/sessao/integrantemesa/", {}, "integrantemesa"))
    return plano


def _paginado(caminho: str, params: dict, prefixo: str) -> dict:
    return {
        "caminho": caminho,
        "params": dict(params),
        "prefixo": prefixo,
        "paginar": True,
    }


class ColetorLote:
    def __init__(self, cfg: dict, pasta: Path, teto: int | None = None):
        if PAUSA_SAPL_SEGUNDOS < 2.5:
            raise SystemExit(
                "PAUSA_SAPL_SEGUNDOS esta abaixo de 2,5. A pausa nao pode ser reduzida."
            )
        self.cfg = cfg
        self.base = endereco_sapl(cfg)
        self.user_agent = user_agent_http(cfg)
        self.pasta = pasta
        self.teto = TETO_PEDIDOS if teto is None else int(teto)
        self.indice_path = pasta / "indice.json"
        self.pedidos = 0
        self.consultas = []
        self.pular_pausa = True
        self.inicio = agora()
        self.inicio_mono = time.monotonic()
        self.duracao_base = 0.0
        self.pasta.mkdir(parents=True, exist_ok=True)
        self._carregar_indice()
        self.gravou = False
        self.ultimo_igual = False
        self.simulado = False
        self.orcamento_execucao = None

    def _carregar_indice(self) -> None:
        if not self.indice_path.exists():
            return
        try:
            velho = json.loads(self.indice_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return
        self.consultas = list(velho.get("pedidos") or [])
        self.pedidos = int(velho.get("total_pedidos") or len(self.consultas))
        if velho.get("iniciado_em"):
            self.inicio = velho["iniciado_em"]
        if velho.get("duracao_segundos") is not None:
            self.duracao_base = float(velho["duracao_segundos"])

    def _gravar_indice(self) -> None:
        dado = {
            "fonte": self.base,
            "pausa_segundos": PAUSA_SAPL_SEGUNDOS,
            "page_size": PAGE_SIZE,
            "teto_pedidos": self.teto,
            "total_pedidos": self.pedidos,
            "iniciado_em": self.inicio,
            "atualizado_em": agora(),
            "duracao_segundos": round(self.duracao_base + time.monotonic() - self.inicio_mono, 1),
            "pedidos": self.consultas,
        }
        texto = json.dumps(dado, ensure_ascii=False, indent=2) + "\n"
        tmp = self.indice_path.with_suffix(".json.tmp")
        tmp.write_text(texto, encoding="utf-8")
        tmp.replace(self.indice_path)

    def _ja_baixado(self, arquivo: str):
        destino = self.pasta / arquivo
        if not destino.is_file() or destino.stat().st_size == 0:
            return None
        for item in self.consultas:
            if item.get("arquivo") == arquivo and item.get("status") == 200:
                try:
                    return json.loads(destino.read_text(encoding="utf-8"))
                except (OSError, ValueError, UnicodeDecodeError):
                    return None
        return None

    def _registrar(self, entrada: dict) -> None:
        self.pedidos += 1
        entrada["n"] = self.pedidos
        self.consultas.append(entrada)
        self._gravar_indice()

    def _esperar_pausa(self) -> None:
        orc = self.orcamento_execucao
        if orc is not None:
            if orc.pedidos > 0:
                time.sleep(PAUSA_SAPL_SEGUNDOS)
            return
        if self.pular_pausa:
            self.pular_pausa = False
            return
        time.sleep(PAUSA_SAPL_SEGUNDOS)

    def _recusar_orcamento(self) -> None:
        orc = self.orcamento_execucao
        if orc is None:
            return
        if orc.pedidos >= orc.teto:
            raise OrcamentoEsgotado(
                f"teto de {orc.teto} pedidos nesta execucao"
            )

    def _consumir_orcamento(self) -> None:
        orc = self.orcamento_execucao
        if orc is None:
            return
        self._recusar_orcamento()
        orc.pedidos += 1

    def pedir(self, caminho: str, params: dict | None, arquivo: str, refrescar: bool = False):
        self.ultimo_igual = False
        if not refrescar:
            ja = self._ja_baixado(arquivo)
            if ja is not None:
                print(f"  [ja tinha] {arquivo}")
                return ja

        if self.simulado:
            destino = self.pasta / arquivo
            if destino.is_file() and destino.stat().st_size > 0:
                try:
                    print(f"  [simulado] {arquivo}")
                    return json.loads(destino.read_text(encoding="utf-8"))
                except (OSError, UnicodeDecodeError, ValueError):
                    pass
            raise SystemExit(
                f"Modo simulado: {arquivo} nao esta salvo. "
                "Nenhum pedido foi feito ao SAPL."
            )

        if self.pedidos >= self.teto:
            raise OrcamentoEsgotado(
                f"teto de {self.teto} pedidos atingido antes de {arquivo}"
            )
        self._recusar_orcamento()

        self._esperar_pausa()
        url = montar_url(self.base, caminho, params)
        tentativas_extra = 0
        destino = self.pasta / arquivo

        while True:
            if self.pedidos >= self.teto:
                raise OrcamentoEsgotado(
                    f"teto de {self.teto} pedidos atingido antes de {arquivo}"
                )
            self._recusar_orcamento()
            self._consumir_orcamento()
            quando = agora()
            status = None
            corpo = b""
            erro = None
            tentativa = tentativas_extra + 1
            raiz_nome, ponto, ext = arquivo.rpartition(".")
            nome_falha = (
                f"{raiz_nome}_t{tentativa}.{ext}" if ponto else f"{arquivo}_t{tentativa}"
            )

            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": self.user_agent,
                    "Accept": "application/json",
                },
                method="GET",
            )
            try:
                with urllib.request.urlopen(req, timeout=TEMPO_LIMITE) as resp:
                    status = int(resp.status)
                    corpo = resp.read()
            except urllib.error.HTTPError as exc:
                status = int(exc.code)
                try:
                    corpo = exc.read()
                except Exception:
                    corpo = b""
                erro = f"HTTP {status}"
            except urllib.error.URLError as exc:
                erro = f"rede: {exc.reason}"
            except TimeoutError:
                erro = "tempo esgotado"

            if (
                refrescar
                and status == 200
                and destino.is_file()
                and destino.read_bytes() == corpo
            ):
                self.ultimo_igual = True
                print(f"  [igual] {arquivo}")
                try:
                    return json.loads(corpo.decode("utf-8"))
                except (UnicodeDecodeError, ValueError) as exc:
                    raise SystemExit(f"Resposta nao e JSON: {arquivo}") from exc

            nome_gravado = arquivo if status == 200 else nome_falha
            (self.pasta / nome_gravado).write_bytes(corpo)
            self.gravou = True
            self._registrar(
                {
                    "url": url,
                    "quando": quando,
                    "status": status,
                    "arquivo": nome_gravado,
                }
            )
            print(f"  [{self.pedidos:03d}/{self.teto}] {status or 'erro'} {nome_gravado}")

            recusar = status in (429, 500, 502, 503) or erro in (
                "tempo esgotado",
            ) or (isinstance(erro, str) and erro.startswith("rede:"))
            if recusar and tentativas_extra < MAX_REPETICOES:
                tentativas_extra += 1
                espera = ESPERA_RECUSA[tentativas_extra - 1]
                print(f"    recusa, espera {espera}s (tentativa extra {tentativas_extra})")
                time.sleep(espera)
                continue

            if status != 200:
                raise SystemExit(f"Pedido falhou: {url} ({erro or status})")
            try:
                return json.loads(corpo.decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as exc:
                raise SystemExit(f"Resposta nao e JSON: {arquivo}") from exc

    def pedir_paginas(self, caminho: str, params: dict, prefixo: str) -> None:
        params = dict(params)
        params["page_size"] = PAGE_SIZE
        params["page"] = 1
        primeiro = self.pedir(caminho, params, f"{prefixo}_p1.json")
        if not isinstance(primeiro, dict):
            raise SystemExit(f"{prefixo}: resposta sem objeto JSON")
        total_paginas = _total_paginas(primeiro, PAGE_SIZE)
        for pagina in range(2, total_paginas + 1):
            params["page"] = pagina
            self.pedir(caminho, params, f"{prefixo}_p{pagina}.json")


def _total_paginas(dados: dict, page_size: int) -> int:
    paginacao = dados.get("pagination") or {}
    total = paginacao.get("total_pages")
    if total is None:
        count = dados.get("count")
        if isinstance(count, int):
            total = max(1, (count + page_size - 1) // page_size)
        elif dados.get("next") or paginacao.get("next_page"):
            raise SystemExit(
                "A API nao informou total_pages. Nao vou adivinhar o numero de paginas."
            )
        else:
            total = 1
    total = int(total)
    if total < 1:
        return 1
    return total


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--somente-completar",
        action="store_true",
        help="So relê listas que vieram com id repetido, na pasta indicada.",
    )
    parser.add_argument("--pasta", default="")
    args = parser.parse_args()

    cfg = carregar_config()
    if args.pasta:
        pasta = Path(args.pasta)
        if not pasta.is_absolute():
            pasta = RAIZ / pasta
    elif args.somente_completar:
        pastas = sorted(caminho for caminho in BRUTOS.glob("lote_*") if caminho.is_dir())
        if not pastas:
            raise SystemExit("Nenhuma pasta de lote para completar.")
        pasta = pastas[-1]
    else:
        pasta = BRUTOS / f"lote_{datetime.now().strftime('%Y%m%d')}"

    coletor = ColetorLote(cfg, pasta)
    print("Coleta em lote do SAPL")
    print(f"Fonte {coletor.base}")
    print(f"Pasta dados/brutos/{pasta.name}")
    print(f"Pausa {PAUSA_SAPL_SEGUNDOS}s, teto {TETO_PEDIDOS}, ja feitos {coletor.pedidos}")

    try:
        if not args.somente_completar:
            print("Indice da API")
            indice = coletor.pedir("/api/", None, "api_indice.json")
            if not isinstance(indice, dict):
                raise SystemExit("Indice da API nao e um objeto JSON.")
            plano = plano_de_coleta(anos_recorte(cfg), indice)
            for item in plano:
                print(item["prefixo"])
                if item["paginar"]:
                    coletor.pedir_paginas(item["caminho"], item["params"], item["prefixo"])
                else:
                    coletor.pedir(item["caminho"], item["params"], f"{item['prefixo']}.json")
        completar_listas_instaveis(coletor)
    except OrcamentoEsgotado as exc:
        coletor._gravar_indice()
        print(f"PAROU: {exc}")
        raise SystemExit(2)

    coletor._gravar_indice()
    print(f"Fim. Pedidos: {coletor.pedidos}. Duracao no indice.")


RECURSOS_ORDEM_ESTAVEL = (
    ("/api/sessao/ordemdia/", "ordemdia"),
    ("/api/sessao/sessaoplenariapresenca/", "sessaoplenariapresenca"),
    ("/api/sessao/presencaordemdia/", "presencaordemdia"),
)


def lista_tem_repeticao(pasta: Path, prefixo: str) -> bool:
    ids = []
    total = None
    numero = 1
    while True:
        caminho = pasta / f"{prefixo}_p{numero}.json"
        if not caminho.exists():
            if numero == 1:
                return False
            break
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        linhas = dados.get("results") or []
        ids.extend(item.get("id") for item in linhas if isinstance(item, dict))
        if numero == 1:
            total = (dados.get("pagination") or {}).get("total_entries")
        numero += 1
    if total is None:
        return len(ids) != len(set(ids))
    return len(set(ids)) != int(total) or len(ids) != len(set(ids))


def completar_listas_instaveis(coletor: ColetorLote) -> None:
    """Segunda leitura com ordering=id quando a lista veio com id repetido.

    Nao regrava as paginas ja salvas. Grava outro prefixo.
    """
    for caminho, prefixo in RECURSOS_ORDEM_ESTAVEL:
        if not lista_tem_repeticao(coletor.pasta, prefixo):
            continue
        destino = f"{prefixo}_por_id"
        print(f"{prefixo} veio com id repetido. Nova leitura com ordering=id.")
        coletor.pedir_paginas(caminho, {"ordering": "id"}, destino)
        if lista_tem_repeticao(coletor.pasta, destino):
            raise SystemExit(
                f"{destino} ainda nao fecha com total_entries. "
                "Nao vou completar a lista na mao."
            )


if __name__ == "__main__":
    main()
