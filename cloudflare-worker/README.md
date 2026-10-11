# Worker da votacao popular (Campo do Tenente)

Worker Cloudflare com D1 que recebe os votos Util ou Inutil das materias
da rodada aberta. A rodada sai do arquivo
`dados/tratados/votacao_rodada.json` no proprio site. Nenhum numero,
cidade, codigo IBGE ou endereco fixo no codigo: tudo vem de
`src/dados_cidade.js`, gerado de `config_cidade.json`.

## Arquivos

- `gerar_dados_worker.py`: gera `src/dados_cidade.js` do config e do contorno.
- `src/regras.js`: logica pura, sem D1 nem rede.
- `src/dados_cidade.js`: GERADO, nao edite a mao.
- `src/index.js`: handler fino, rotas `/api/rodada`, `/api/verificar`,
  `/api/votar`, `/api/resultados`, mais a rotina agendada de limpeza.
- `schema.sql`: tabelas `vp_*`, `vp_config` e os triggers do teto, do uso
  unico e da autorizacao dentro do batch.
- `wrangler.toml`: ambientes `teste` e `producao`, cada um com seu D1.
- `test/`: testes `node --test`, com D1 falso em memoria e com SQLite real
  (`sqlite_real.test.js`, que aplica o `schema.sql` de verdade).

Nomes com o slug da cidade (`campo-do-tenente`, de `cidade.nome` no config):
worker `epl-votacao-campo-do-tenente`, bancos
`epl-votacao-campo-do-tenente` (producao) e
`epl-votacao-campo-do-tenente-teste` (teste).

## Como testar

Sem instalar pacote, sem rede, sem login:

```
python cloudflare-worker/gerar_dados_worker.py
node --test cloudflare-worker/test/handler.test.js cloudflare-worker/test/regras.test.js cloudflare-worker/test/sqlite_real.test.js
```

## Variaveis publicas (wrangler.toml)

`AMBIENTE` (`teste` ou `producao`), `SITE_ORIGEM`, `RODADA_URL`,
`TURNSTILE_SITE_KEY`, `RODADA_ID_LOCAL` (reservada, o Worker ignora).

## Segredos (so no cofre, nunca em arquivo)

`TURNSTILE_SECRET_KEY`, `HMAC_SECRET`, `MODO_TESTE_SECRETO`.
O modo de teste (pular o GPS) so vale com `AMBIENTE` igual a `teste`
e cabecalho `X-Modo-Teste` igual ao segredo.

## Regras que a tela precisa conhecer

- A tela envia `action: "votacao"` no widget do Turnstile. O servidor
  confere `success`, `hostname` igual ao host de `SITE_ORIGEM` (no
  ambiente de teste valem tambem `localhost` e `127.0.0.1`) e `action`
  igual a `"votacao"` quando a resposta traz `action`. Falha vira 400
  `captcha_invalido`.
- POST com `Content-Length` acima de 32 KB ou corpo lido maior que isso
  e recusado antes de interpretar, com 413 e codigo `corpo_grande`
  ("Pedido grande demais. Tente de novo.").
- `GET /api/resultados` devolve, por materia acima do minimo de
  respostas, `respostas` (numero), `total_util`, `total_inutil`,
  `percentual_util` e `percentual_inutil` (que somam sempre 100).
  Abaixo do minimo, continua `respostas: "menos de N"` com os dois
  percentuais `null` e sem contagem. Exemplo acima do minimo:

```json
{"materia_id": 811, "respostas": 200, "total_util": 1, "total_inutil": 199,
 "percentual_util": 1, "percentual_inutil": 99}
```

## Protecoes do voto (resumo para auditoria)

- O `jti` da autorizacao e conferido dentro do proprio batch por trigger
  (`trg_vp_participacao_autorizacao`): sem linha em `vp_autorizacoes`
  com o mesmo `jti`, rodada e aparelho ja marcada como usada, o batch
  aborta com 400 `autorizacao_invalida` e nada e gravado.
- O teto por endereco falha fechado: sem a linha do teto em `vp_config`,
  qualquer participacao e recusada com `teto_endereco`. O upsert do teto
  e a primeira instrucao do batch do voto. A chave e a constante
  `CHAVE_TETO` em `src/index.js`, igual ao texto no `schema.sql`.
- Rodada com status diferente de `aberta` no D1 nunca volta a ser
  servida como aberta, mesmo que o arquivo publico diga aberta.
- A rotina agendada so apaga autorizacao vencida ha mais de 1 hora
  (`MARGEM_RETENCAO_AUTORIZACAO_S`), para nao apagar o `jti` de um voto
  em andamento.
- Erro interno no log (`console.error`) traz so rota, codigo interno
  curto (por exemplo `d1_batch`, `turnstile_rede`, `rodada_busca`) e a
  classe do erro. Nunca mensagem completa, pilha, IP, endereco,
  aparelho, hash, coordenada, `jti`, token ou segredo.
