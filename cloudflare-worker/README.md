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
- `schema.sql`: tabelas `vp_*`, `vp_config` e os triggers do teto e do uso unico.
- `wrangler.toml`: ambientes `teste` e `producao`, cada um com seu D1.
- `test/`: testes `node --test`, com D1 falso em memoria.

Nomes com o slug da cidade (`campo-do-tenente`, de `cidade.nome` no config):
worker `epl-votacao-campo-do-tenente`, bancos
`epl-votacao-campo-do-tenente` (producao) e
`epl-votacao-campo-do-tenente-teste` (teste).

## Como testar

Sem instalar pacote, sem rede, sem login:

```
python cloudflare-worker/gerar_dados_worker.py
node --test cloudflare-worker/test/
```

## Variaveis publicas (wrangler.toml)

`AMBIENTE` (`teste` ou `producao`), `SITE_ORIGEM`, `RODADA_URL`,
`TURNSTILE_SITE_KEY`, `RODADA_ID_LOCAL` (reservada, o Worker ignora).

## Segredos (so no cofre, nunca em arquivo)

`TURNSTILE_SECRET_KEY`, `HMAC_SECRET`, `MODO_TESTE_SECRETO`.
O modo de teste (pular o GPS) so vale com `AMBIENTE` igual a `teste`
e cabecalho `X-Modo-Teste` igual ao segredo.
