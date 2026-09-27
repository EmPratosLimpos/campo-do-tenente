"""
Sonda a porta de dados do SAPL de Campo do Tenente/PR.

Nao baixa o acervo completo. Faz pedidos em lote, um por vez, com pausa,
e grava cada resposta exatamente como veio em
dados/brutos/sondagem_20260927/.

Rodar:  python coletor/sondar_campo_do_tenente.py
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

BASE = "https://sapl.campodotenente.pr.leg.br"
PAUSA = 3.0
TEMPO_LIMITE = 120
MAX_PEDIDOS = 60
MAX_REPETICOES = 2
PAGE_SIZE = 100
USER_AGENT = "painel-camara-campo-do-tenente/0.1 (projeto de transparencia civica)"

RAIZ = Path(__file__).resolve().parent.parent
SAIDA = RAIZ / "dados" / "brutos" / "sondagem_20260927"
INDICE = SAIDA / "indice.json"


class OrcamentoEsgotado(Exception):
    pass


def agora():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def montar_url(caminho, params=None):
    url = BASE + caminho
    if params:
        query = urllib.parse.urlencode(params, doseq=True)
        return url + "?" + query
    return url


class Sonda:
    def __init__(self):
        self.pedidos = 0
        self.consultas = []
        self.pular_pausa = True
        self.page_size_ok = None
        self._abrir_saida()

    def _abrir_saida(self):
        SAIDA.mkdir(parents=True, exist_ok=True)
        if INDICE.exists():
            try:
                velho = json.loads(INDICE.read_text(encoding="utf-8"))
                self.consultas = velho.get("pedidos") or []
                self.pedidos = int(velho.get("total_pedidos") or len(self.consultas))
            except (OSError, ValueError, TypeError):
                self.consultas = []
                self.pedidos = 0

    def _gravar_indice(self):
        dado = {
            "fonte": BASE,
            "user_agent": USER_AGENT,
            "pausa_segundos": PAUSA,
            "page_size_pedido": PAGE_SIZE,
            "page_size_aceito": self.page_size_ok,
            "total_pedidos": self.pedidos,
            "atualizado_em": agora(),
            "pedidos": self.consultas,
        }
        texto = json.dumps(dado, ensure_ascii=False, indent=2) + "\n"
        tmp = INDICE.with_suffix(".json.tmp")
        tmp.write_text(texto, encoding="utf-8")
        tmp.replace(INDICE)

    def _registrar(self, entrada):
        self.pedidos += 1
        entrada["n"] = self.pedidos
        self.consultas.append(entrada)
        self._gravar_indice()

    def _ler_se_ja_baixado(self, arquivo):
        destino = SAIDA / arquivo
        if not destino.exists():
            return None
        for item in self.consultas:
            if item.get("arquivo") == arquivo and item.get("status") == 200:
                try:
                    return json.loads(destino.read_text(encoding="utf-8"))
                except (OSError, ValueError, UnicodeDecodeError):
                    return None
        return None

    def pedir(self, caminho, params=None, arquivo=""):
        ja = self._ler_se_ja_baixado(arquivo)
        if ja is not None:
            print(f"  [ja tinha] {arquivo}")
            return ja, None

        if self.pedidos >= MAX_PEDIDOS:
            raise OrcamentoEsgotado(f"orcamento de {MAX_PEDIDOS} pedidos atingido")

        if self.pular_pausa:
            self.pular_pausa = False
        else:
            time.sleep(PAUSA)

        url = montar_url(caminho, params)
        tentativas_extra = 0

        while True:
            if self.pedidos >= MAX_PEDIDOS:
                raise OrcamentoEsgotado(f"orcamento de {MAX_PEDIDOS} pedidos atingido")

            quando = agora()
            status = None
            corpo = b""
            erro = None
            tentativa = tentativas_extra + 1
            nome = arquivo
            if tentativa > 1:
                raiz, ponto, ext = arquivo.rpartition(".")
                nome = f"{raiz}_t{tentativa}.{ext}" if ponto else f"{arquivo}_t{tentativa}"

            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
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

            destino = SAIDA / nome
            destino.write_bytes(corpo)

            self._registrar(
                {
                    "url": url,
                    "quando": quando,
                    "status": status,
                    "arquivo": nome,
                    "bytes": len(corpo),
                    "tentativa": tentativa,
                    "erro": erro,
                }
            )

            print(f"  [{self.pedidos:02d}/{MAX_PEDIDOS}] {status or 'erro'} {nome}")

            recusar = status in (429, 500, 502, 503) or erro in (
                "tempo esgotado",
            ) or (erro and erro.startswith("rede:"))

            if recusar and tentativas_extra < MAX_REPETICOES:
                tentativas_extra += 1
                espera = 30 * tentativas_extra
                print(f"    recusa ou demora, espera {espera}s e tenta de novo")
                time.sleep(espera)
                continue

            if status != 200:
                return None, erro or f"HTTP {status}"

            try:
                return json.loads(corpo.decode("utf-8")), None
            except (UnicodeDecodeError, ValueError):
                return None, "resposta nao e JSON"

    def pedir_paginas(self, caminho, params, prefixo):
        params = dict(params)
        params.setdefault("page_size", PAGE_SIZE)
        params["page"] = 1
        dados, erro = self.pedir(caminho, params, f"{prefixo}_p1.json")
        if erro or not isinstance(dados, dict):
            return None, erro or "sem JSON"

        if self.page_size_ok is None:
            lote = dados.get("results") or []
            self.page_size_ok = len(lote) <= PAGE_SIZE and dados is not None

        paginas = [dados]
        paginacao = dados.get("pagination") or {}
        total_paginas = paginacao.get("total_pages")
        if total_paginas is None:
            count = dados.get("count")
            page_size = params.get("page_size") or PAGE_SIZE
            if isinstance(count, int) and page_size:
                total_paginas = max(1, (count + page_size - 1) // page_size)
            elif dados.get("next"):
                total_paginas = 2
            else:
                total_paginas = 1
        total_paginas = int(total_paginas)

        pagina = 2
        while pagina <= total_paginas:
            params["page"] = pagina
            mais, erro = self.pedir(caminho, params, f"{prefixo}_p{pagina}.json")
            if erro:
                return paginas, f"pagina {pagina}: {erro}"
            paginas.append(mais)
            if not mais.get("next") and not (mais.get("pagination") or {}).get("next"):
                if pagina >= total_paginas:
                    break
            pagina += 1
        return paginas, None

    def total_de(self, dados):
        if not isinstance(dados, dict):
            return None
        paginacao = dados.get("pagination") or {}
        if dados.get("count") is not None:
            return dados.get("count")
        if paginacao.get("total_entries") is not None:
            return paginacao.get("total_entries")
        results = dados.get("results")
        if isinstance(results, list):
            return len(results)
        return None


def main():
    sonda = Sonda()
    print("Sondagem do SAPL de Campo do Tenente/PR")
    print(f"Fonte {BASE}")
    print(f"Pausa {PAUSA}s, teto {MAX_PEDIDOS} pedidos")
    print(f"Pedidos ja registrados: {sonda.pedidos}")
    print()

    try:
        print("1. Indice da API")
        sonda.pedir("/api/", None, "api_indice.json")

        print("2. Catalogos")
        sonda.pedir_paginas(
            "/api/sessao/tiposessaoplenaria/",
            {"page_size": PAGE_SIZE},
            "tiposessaoplenaria",
        )
        sonda.pedir_paginas(
            "/api/parlamentares/legislatura/",
            {"page_size": PAGE_SIZE},
            "legislatura",
        )
        sonda.pedir_paginas(
            "/api/parlamentares/mandato/",
            {"page_size": PAGE_SIZE},
            "mandato",
        )
        sonda.pedir_paginas(
            "/api/parlamentares/parlamentar/",
            {"page_size": PAGE_SIZE},
            "parlamentar",
        )
        sonda.pedir_paginas(
            "/api/materia/tipomaterialegislativa/",
            {"page_size": PAGE_SIZE},
            "tipomaterialegislativa",
        )
        sonda.pedir(
            "/api/sessao/tiporesultadovotacao/",
            {"page_size": PAGE_SIZE},
            "tiporesultadovotacao_p1.json",
        )
        sonda.pedir(
            "/api/sessao/tipojustificativa/",
            {"page_size": PAGE_SIZE},
            "tipojustificativa_p1.json",
        )

        print("3. Sessoes plenarias 2025 e 2026")
        pags_2025, erro_2025 = sonda.pedir_paginas(
            "/api/sessao/sessaoplenaria/",
            {"data_inicio__year": 2025, "page_size": PAGE_SIZE},
            "sessaoplenaria_ano2025",
        )
        pags_2026, erro_2026 = sonda.pedir_paginas(
            "/api/sessao/sessaoplenaria/",
            {"data_inicio__year": 2026, "page_size": PAGE_SIZE},
            "sessaoplenaria_ano2026",
        )
        if erro_2025:
            print(f"    aviso 2025: {erro_2025}")
        if erro_2026:
            print(f"    aviso 2026: {erro_2026}")

        sid_ordinaria = None
        resultados_sessao = []
        for bloco in (pags_2026 or []) + (pags_2025 or []):
            if isinstance(bloco, dict):
                resultados_sessao.extend(bloco.get("results") or [])
        for item in resultados_sessao:
            tipo = item.get("tipo")
            if tipo == 3 or item.get("tipo__nome") == "Sessao Ordinaria":
                sid_ordinaria = item.get("id")
                break
        if sid_ordinaria is None and resultados_sessao:
            sid_ordinaria = resultados_sessao[0].get("id")

        print("4. Votacoes em lote e testes de filtro")
        pags_reg, erro_reg = sonda.pedir_paginas(
            "/api/sessao/registrovotacao/",
            {"page_size": PAGE_SIZE},
            "registrovotacao",
        )
        if erro_reg:
            print(f"    aviso registrovotacao: {erro_reg}")

        votacao_id = None
        ordem_id = None
        if pags_reg:
            for bloco in pags_reg:
                for item in bloco.get("results") or []:
                    if item.get("id") is not None:
                        votacao_id = item.get("id")
                        ordem_id = item.get("ordem")
                        break
                if votacao_id is not None:
                    break

        if sid_ordinaria is not None:
            sonda.pedir(
                "/api/sessao/registrovotacao/",
                {"sessao_plenaria": sid_ordinaria, "page_size": 5},
                f"registrovotacao_filtro_sessao_{sid_ordinaria}_p1.json",
            )
            sonda.pedir(
                "/api/sessao/votoparlamentar/",
                {"sessao_plenaria": sid_ordinaria, "page_size": 5},
                f"votoparlamentar_filtro_sessao_{sid_ordinaria}_p1.json",
            )
            sonda.pedir_paginas(
                "/api/sessao/ordemdia/",
                {"sessao_plenaria": sid_ordinaria, "page_size": PAGE_SIZE},
                f"ordemdia_filtro_sessao_{sid_ordinaria}",
            )

        if votacao_id is not None:
            sonda.pedir(
                "/api/sessao/votoparlamentar/",
                {"votacao": votacao_id, "page_size": PAGE_SIZE},
                f"votoparlamentar_filtro_votacao_{votacao_id}_p1.json",
            )
        # votacao 20 aparece no lote com votos individuais; serve para
        # distinguir filtro que funciona de votacao sem voto registrado.
        sonda.pedir(
            "/api/sessao/votoparlamentar/",
            {"votacao": 20, "page_size": PAGE_SIZE},
            "votoparlamentar_filtro_votacao_20_p1.json",
        )
        if ordem_id is not None:
            sonda.pedir(
                "/api/sessao/registrovotacao/",
                {"ordem": ordem_id, "page_size": 5},
                f"registrovotacao_filtro_ordem_{ordem_id}_p1.json",
            )

        pags_voto, erro_voto = sonda.pedir_paginas(
            "/api/sessao/votoparlamentar/",
            {"page_size": PAGE_SIZE},
            "votoparlamentar",
        )
        if erro_voto:
            print(f"    aviso votoparlamentar: {erro_voto}")
        if pags_voto:
            print(f"    votoparlamentar paginas: {len(pags_voto)}")

        print("5. Presenca, justificativa e mesa")
        sonda.pedir(
            "/api/sessao/sessaoplenariapresenca/",
            {"page_size": 1},
            "sessaoplenariapresenca_contagem_p1.json",
        )
        sonda.pedir(
            "/api/sessao/presencaordemdia/",
            {"page_size": 1},
            "presencaordemdia_contagem_p1.json",
        )
        sonda.pedir(
            "/api/sessao/justificativaausencia/",
            {"page_size": 1},
            "justificativaausencia_contagem_p1.json",
        )
        sonda.pedir(
            "/api/sessao/integrantemesa/",
            {"page_size": PAGE_SIZE},
            "integrantemesa_p1.json",
        )
        if sid_ordinaria is not None:
            sonda.pedir(
                "/api/sessao/sessaoplenariapresenca/",
                {"sessao_plenaria": sid_ordinaria, "page_size": PAGE_SIZE},
                f"sessaoplenariapresenca_filtro_sessao_{sid_ordinaria}_p1.json",
            )
            sonda.pedir(
                "/api/sessao/presencaordemdia/",
                {"sessao_plenaria": sid_ordinaria, "page_size": PAGE_SIZE},
                f"presencaordemdia_filtro_sessao_{sid_ordinaria}_p1.json",
            )
            sonda.pedir(
                "/api/sessao/justificativaausencia/",
                {"sessao_plenaria": sid_ordinaria, "page_size": PAGE_SIZE},
                f"justificativaausencia_filtro_sessao_{sid_ordinaria}_p1.json",
            )
            sonda.pedir(
                "/api/sessao/integrantemesa/",
                {"sessao_plenaria": sid_ordinaria, "page_size": PAGE_SIZE},
                f"integrantemesa_filtro_sessao_{sid_ordinaria}_p1.json",
            )

        print("5b. Contagem de ordem do dia e expediente")
        sonda.pedir(
            "/api/sessao/ordemdia/",
            {"page_size": 1},
            "ordemdia_contagem_p1.json",
        )
        sonda.pedir(
            "/api/sessao/expedientemateria/",
            {"page_size": 1},
            "expedientemateria_contagem_p1.json",
        )

        print("6. Materias 2025 e 2026")
        sonda.pedir_paginas(
            "/api/materia/materialegislativa/",
            {"ano": 2025, "page_size": PAGE_SIZE},
            "materialegislativa_ano2025",
        )
        sonda.pedir_paginas(
            "/api/materia/materialegislativa/",
            {"ano": 2026, "page_size": PAGE_SIZE},
            "materialegislativa_ano2026",
        )

    except OrcamentoEsgotado as exc:
        print()
        print(f"PAROU: {exc}")
        sonda._gravar_indice()
        raise SystemExit(2)

    sonda._gravar_indice()
    print()
    print(f"Fim. Total de pedidos: {sonda.pedidos}")
    print("Indice em dados/brutos/sondagem_20260927/indice.json")


if __name__ == "__main__":
    main()
