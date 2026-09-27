"""
Baixa voto individual, presenca, mesa e justificativa das sessoes
ordinarias de 2026 que ainda nao tem o pacote completo.

O filtro sessao_plenaria em registrovotacao e votoparlamentar e ignorado
pelo SAPL de Campo Largo (devolve o acervo inteiro). O metodo que funciona,
o mesmo da sessao 786, e:

  registrovotacao?ordem=<id do item da ordem do dia>
  votoparlamentar?votacao=<id do registro de votacao>

Rodar:  python coletor/baixar_voto_presenca_ordinarias_2026.py

Se o arquivo ja existe, nao baixa de novo. Pausa de 2,5 segundos entre
pedidos. Se o servidor recusar, espera mais e tenta de novo.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

BASE = "https://sapl.campolargo.pr.leg.br"
PAUSA = 2.5
TEMPO_LIMITE = 120
SAIDA = Path(__file__).resolve().parent.parent / "dados" / "brutos"
LOG_PATH = SAIDA / "log_consultas_voto_presenca_ordinarias_2026.json"
PROGRESSO_PATH = SAIDA / "_progresso_coleta_vereadores_2026.json"

PACOTE = [
    "registrovotacao",
    "votoparlamentar",
    "sessaoplenariapresenca",
    "presencaordemdia",
    "justificativaausencia",
    "integrantemesa",
    "parlamentares",
]


def agora():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def ler_json(caminho: Path):
    return json.loads(caminho.read_text(encoding="utf-8"))


def salvar_json(caminho: Path, dado, tentativas=8):
    tmp = caminho.with_suffix(caminho.suffix + ".tmp")
    texto = json.dumps(dado, ensure_ascii=False, indent=2) + "\n"
    ultimo_erro = None
    for i in range(tentativas):
        try:
            tmp.write_text(texto, encoding="utf-8")
            tmp.replace(caminho)
            return
        except OSError as exc:
            ultimo_erro = exc
            time.sleep(0.4 * (i + 1))
    if tmp.exists():
        try:
            tmp.unlink()
        except OSError:
            pass
    raise ultimo_erro


def ids_ordinarias_2026():
    cont = ler_json(SAIDA / "contagem_votacoes_ordinarias_2026.json")
    return [int(s["id"]) for s in cont["sessoes"]]


def arquivo_sessao(sid: int, nome: str) -> Path:
    return SAIDA / f"sessao_{sid}_{nome}.json"


def carregar_ordemdia(sid: int):
    itens = []
    for caminho in (
        arquivo_sessao(sid, "ordemdia"),
        SAIDA / f"sessao_{sid}_ordemdia_pagina_2.json",
        SAIDA / f"sessao_{sid}_ordemdia_pagina_3.json",
    ):
        if caminho.exists():
            dados = ler_json(caminho)
            itens.extend(dados.get("results") or [])
    return itens


def pacote_completo(sid: int) -> bool:
    return all(arquivo_sessao(sid, nome).exists() for nome in PACOTE)


class Coletor:
    def __init__(self):
        self.http = requests.Session()
        self.http.headers.update(
            {
                "User-Agent": "painel-camara-campo-largo/0.1 (projeto de transparencia)",
                "Accept": "application/json",
            }
        )
        self.consultas = []
        self.pedidos = 0
        self.pular_pausa = True
        self.cache_parlamentar = {}
        self.erros = []
        self.sessoes_baixadas = []
        self.sessoes_incompletas = []
        self.sessoes_ja_tinham = []
        self._log_sujo = 0
        self._carregar_log()
        self._carregar_cache_parlamentar()

    def _carregar_log(self):
        if LOG_PATH.exists():
            try:
                velho = ler_json(LOG_PATH)
                self.consultas = velho.get("consultas") or []
                self.pedidos = int(velho.get("pedidos") or len(self.consultas))
            except (OSError, ValueError, TypeError):
                self.consultas = []
                self.pedidos = 0

    def _carregar_cache_parlamentar(self):
        for caminho in SAIDA.glob("sessao_*_parlamentares.json"):
            try:
                dados = ler_json(caminho)
            except (OSError, ValueError):
                continue
            if isinstance(dados, dict) and "results" not in dados:
                for chave, valor in dados.items():
                    if isinstance(valor, dict) and valor.get("id") is not None:
                        self.cache_parlamentar[int(valor["id"])] = valor
                    else:
                        try:
                            self.cache_parlamentar[int(chave)] = valor
                        except (TypeError, ValueError):
                            pass

    def _marcar_log_sujo(self, forcar=False):
        self._log_sujo += 1
        if forcar or self._log_sujo >= 50:
            self._gravar_log()

    def _gravar_log(self):
        self._log_sujo = 0
        try:
            salvar_json(
                LOG_PATH,
                {
                    "pedidos": self.pedidos,
                    "atualizado_em": agora(),
                    "metodo": {
                        "registrovotacao": "filtro ordem=<id do item da ordem do dia>; sessao_plenaria e ignorado pelo servidor",
                        "votoparlamentar": "filtro votacao=<id do registrovotacao>; sessao_plenaria e registrovotacao sao ignorados",
                        "pausa_segundos": PAUSA,
                    },
                    "consultas": self.consultas,
                },
            )
        except OSError as exc:
            print(f"    aviso: nao consegui gravar o log ({exc})")

    def _gravar_progresso(self, fase: str, sid=None):
        try:
            salvar_json(
                PROGRESSO_PATH,
                {
                    "fase": fase,
                    "sessao_atual": sid,
                    "pedidos": self.pedidos,
                    "sessoes_baixadas": self.sessoes_baixadas,
                    "sessoes_incompletas": self.sessoes_incompletas,
                    "sessoes_ja_tinham": self.sessoes_ja_tinham,
                    "erros": self.erros[-20:],
                    "atualizado_em": agora(),
                },
            )
        except OSError as exc:
            print(f"    aviso: nao consegui gravar o progresso ({exc})")

    def pedir(self, caminho: str, params: dict | None = None):
        if self.pular_pausa:
            self.pular_pausa = False
        else:
            time.sleep(PAUSA)

        url = BASE + caminho
        ultimo_erro = None
        for tentativa in range(6):
            quando = agora()
            try:
                resposta = self.http.get(url, params=params, timeout=TEMPO_LIMITE)
            except requests.RequestException as exc:
                ultimo_erro = f"rede: {exc}"
                self.consultas.append(
                    {
                        "url": url,
                        "params": params,
                        "quando": quando,
                        "status": None,
                        "erro": ultimo_erro,
                        "tentativa": tentativa + 1,
                    }
                )
                self.pedidos += 1
                self._marcar_log_sujo(forcar=True)
                time.sleep(30 * (tentativa + 1))
                continue

            self.consultas.append(
                {
                    "url": resposta.url,
                    "quando": quando,
                    "status": resposta.status_code,
                    "tentativa": tentativa + 1,
                }
            )
            self.pedidos += 1
            self._marcar_log_sujo()

            if resposta.status_code in (429, 500, 502, 503):
                ultimo_erro = f"HTTP {resposta.status_code}"
                time.sleep(30 * (tentativa + 1))
                continue

            if resposta.status_code != 200:
                return None, f"HTTP {resposta.status_code}"

            try:
                return resposta.json(), None
            except ValueError:
                return None, "resposta nao e JSON"

        return None, ultimo_erro or "esgotou tentativas"

    def pedir_lista(self, caminho: str, params: dict):
        params = dict(params)
        params.setdefault("page_size", 100)
        params["page"] = 1
        dados, erro = self.pedir(caminho, params)
        if erro:
            return None, erro
        resultados = list(dados.get("results") or [])
        paginacao = dados.get("pagination") or {}
        total_paginas = int(paginacao.get("total_pages") or 1)
        pagina = 2
        while pagina <= total_paginas:
            params["page"] = pagina
            mais, erro = self.pedir(caminho, params)
            if erro:
                return None, f"pagina {pagina}: {erro}"
            resultados.extend(mais.get("results") or [])
            pagina += 1
        return {"pagination": paginacao, "results": resultados, "total": len(resultados)}, None

    def baixar_registrovotacao(self, sid: int, itens_ordem: list):
        destino = arquivo_sessao(sid, "registrovotacao")
        if destino.exists():
            print(f"    registrovotacao: ja existe, pulando")
            return ler_json(destino), True

        resultados = []
        vazios = 0
        falhas = []
        for item in itens_ordem:
            ordem_id = item.get("id")
            if ordem_id is None:
                continue
            dados, erro = self.pedir(
                "/api/sessao/registrovotacao/",
                {"ordem": ordem_id, "page_size": 100},
            )
            if erro:
                falhas.append({"ordem": ordem_id, "erro": erro})
                continue
            lote = dados.get("results") or []
            if lote:
                resultados.extend(lote)
            else:
                vazios += 1

        if falhas:
            self.erros.append({"sessao": sid, "arquivo": "registrovotacao", "falhas": falhas})
            print(f"    registrovotacao: {len(falhas)} pedidos falharam, nao gravei o arquivo")
            return None, False

        salvar_json(destino, {"total": len(resultados), "results": resultados})
        print(f"    registrovotacao: {len(resultados)} registros ({vazios} ordens sem registro)")
        return {"total": len(resultados), "results": resultados}, True

    def baixar_votoparlamentar(self, sid: int, registros: dict | None):
        destino = arquivo_sessao(sid, "votoparlamentar")
        if destino.exists():
            print(f"    votoparlamentar: ja existe, pulando")
            return ler_json(destino), True

        ids_votacao = []
        if registros:
            for item in registros.get("results") or []:
                if item.get("id") is not None:
                    ids_votacao.append(item["id"])

        ordem_por_votacao = {}
        if registros:
            for item in registros.get("results") or []:
                if item.get("id") is not None:
                    ordem_por_votacao[item["id"]] = item.get("ordem")

        resultados = []
        falhas = []
        for votacao_id in ids_votacao:
            dados, erro = self.pedir(
                "/api/sessao/votoparlamentar/",
                {"votacao": votacao_id, "page_size": 100},
            )
            if erro:
                ordem_id = ordem_por_votacao.get(votacao_id)
                if ordem_id is not None:
                    print(f"    votoparlamentar votacao={votacao_id}: {erro}; tentando ordem={ordem_id}")
                    dados, erro = self.pedir(
                        "/api/sessao/votoparlamentar/",
                        {"ordem": ordem_id, "page_size": 100},
                    )
            if erro:
                falhas.append({"votacao": votacao_id, "erro": erro})
                continue
            lote = dados.get("results") or []
            paginacao = dados.get("pagination") or {}
            total_paginas = int(paginacao.get("total_pages") or 1)
            resultados.extend(lote)
            pagina = 2
            while pagina <= total_paginas:
                mais, erro = self.pedir(
                    "/api/sessao/votoparlamentar/",
                    {"votacao": votacao_id, "page_size": 100, "page": pagina},
                )
                if erro:
                    falhas.append({"votacao": votacao_id, "pagina": pagina, "erro": erro})
                    break
                resultados.extend(mais.get("results") or [])
                pagina += 1

        if resultados:
            salvar_json(destino, {"total": len(resultados), "results": resultados})
            print(f"    votoparlamentar: {len(resultados)} votos de {len(ids_votacao)} votacoes")
        if falhas:
            self.erros.append({"sessao": sid, "arquivo": "votoparlamentar", "falhas": falhas})
            print(f"    votoparlamentar: {len(falhas)} pedidos falharam")
            return ({"total": len(resultados), "results": resultados} if resultados else None, False)

        if not resultados:
            salvar_json(destino, {"total": 0, "results": []})
            print(f"    votoparlamentar: 0 votos de {len(ids_votacao)} votacoes")
        return {"total": len(resultados), "results": resultados}, True

    def baixar_lista_sessao(self, sid: int, nome: str, caminho: str, params: dict):
        destino = arquivo_sessao(sid, nome)
        if destino.exists():
            print(f"    {nome}: ja existe, pulando")
            return ler_json(destino), True
        dados, erro = self.pedir_lista(caminho, params)
        if erro:
            self.erros.append({"sessao": sid, "arquivo": nome, "erro": erro})
            print(f"    {nome}: {erro}, nao gravei nada")
            return None, False
        salvar_json(destino, dados)
        n = len(dados.get("results") or [])
        print(f"    {nome}: {n} registros")
        return dados, True

    def parlamentar_por_id(self, pid: int):
        if pid in self.cache_parlamentar:
            return self.cache_parlamentar[pid], True
        dados, erro = self.pedir(f"/api/parlamentares/parlamentar/{pid}/")
        if erro:
            return None, False
        self.cache_parlamentar[pid] = dados
        return dados, True

    def baixar_parlamentares(self, sid: int, fontes: list):
        destino = arquivo_sessao(sid, "parlamentares")
        if destino.exists():
            print(f"    parlamentares: ja existe, pulando")
            return True

        ids = set()
        for fonte in fontes:
            if not fonte:
                continue
            for item in fonte.get("results") or []:
                pid = item.get("parlamentar")
                if pid is not None:
                    ids.add(int(pid))

        saida = {}
        falhas = []
        for pid in sorted(ids):
            dados, ok = self.parlamentar_por_id(pid)
            if not ok:
                falhas.append(pid)
                continue
            saida[str(pid)] = dados

        if falhas:
            self.erros.append({"sessao": sid, "arquivo": "parlamentares", "ids": falhas})
            print(f"    parlamentares: falhou ids {falhas}, nao gravei o arquivo")
            return False

        salvar_json(destino, saida)
        print(f"    parlamentares: {len(saida)} vereadores desta sessao")
        return True

    def baixar_sessao(self, sid: int):
        print(f"Sessao {sid}")
        self._gravar_progresso("baixando", sid)
        itens = carregar_ordemdia(sid)
        if not itens:
            self.erros.append({"sessao": sid, "erro": "ordem do dia nao encontrada em disco"})
            self.sessoes_incompletas.append(sid)
            print("    sem ordem do dia em disco, pulando")
            return

        registros, ok_reg = self.baixar_registrovotacao(sid, itens)
        votos, ok_votos = self.baixar_votoparlamentar(sid, registros if ok_reg else None)
        presenca, ok_pres = self.baixar_lista_sessao(
            sid,
            "sessaoplenariapresenca",
            "/api/sessao/sessaoplenariapresenca/",
            {"sessao_plenaria": sid, "page_size": 100},
        )
        presenca_od, ok_pod = self.baixar_lista_sessao(
            sid,
            "presencaordemdia",
            "/api/sessao/presencaordemdia/",
            {"sessao_plenaria": sid, "page_size": 100},
        )
        justif, ok_just = self.baixar_lista_sessao(
            sid,
            "justificativaausencia",
            "/api/sessao/justificativaausencia/",
            {"sessao_plenaria": sid, "page_size": 100},
        )
        mesa, ok_mesa = self.baixar_lista_sessao(
            sid,
            "integrantemesa",
            "/api/sessao/integrantemesa/",
            {"sessao_plenaria": sid, "page_size": 50},
        )
        ok_parl = self.baixar_parlamentares(
            sid, [presenca, presenca_od, justif, mesa, votos]
        )

        if all([ok_reg, ok_votos, ok_pres, ok_pod, ok_just, ok_mesa, ok_parl]):
            self.sessoes_baixadas.append(sid)
            print(f"    pacote completo ({self.pedidos} pedidos ate agora)")
        else:
            self.sessoes_incompletas.append(sid)
            print(f"    pacote incompleto")
        self._gravar_log()
        self._gravar_progresso("sessao_fechada", sid)

    def run(self):
        print("Coleta de voto e presenca das ordinarias de 2026")
        print(f"Inicio {agora()}")
        ids = [int(x) for x in sys.argv[1:]] or ids_ordinarias_2026()
        for sid in ids:
            if pacote_completo(sid):
                self.sessoes_ja_tinham.append(sid)
                print(f"Sessao {sid}: pacote completo ja existia, pulando")
                continue
            self.baixar_sessao(sid)

        resumo = {
            "fim": agora(),
            "pedidos": self.pedidos,
            "sessoes_ja_tinham": self.sessoes_ja_tinham,
            "sessoes_baixadas": self.sessoes_baixadas,
            "sessoes_incompletas": self.sessoes_incompletas,
            "erros": self.erros,
        }
        self._gravar_log()
        self._gravar_progresso("fim")
        salvar_json(SAIDA / "_resumo_coleta_vereadores_2026.json", resumo)
        print()
        print(f"Pedidos feitos nesta execucao (log acumulado): {self.pedidos}")
        print(f"Ja tinham pacote: {self.sessoes_ja_tinham}")
        print(f"Baixadas agora: {self.sessoes_baixadas}")
        print(f"Incompletas: {self.sessoes_incompletas}")
        print("Fim")


if __name__ == "__main__":
    Coletor().run()
