# Registro de atualizações

Este arquivo conta, em ordem da mais nova para a mais antiga, tudo o que mudou no painel **Em Pratos Limpos** da Câmara Municipal de Campo do Tenente (PR): nos dados e na tela.

Está prevista uma atualização semanal automática. Cada vez que ela trouxer sessões novas do SAPL, uma nova entrada será acrescentada no topo desta lista, seguindo o modelo abaixo. Nenhuma entrada vai ao ar sem a aprovação do mantenedor. Entradas antigas não são apagadas nem reescritas: se algo precisar ser corrigido, a correção aparece como uma entrada nova.

## Modelo de entrada

```markdown
## AAAA-MM-DD: título curto da atualização

**O que mudou nos dados**
- Sessões ordinárias incluídas: números e datas.
- Votações, presenças ou matérias acrescentadas ou corrigidas.
- Hash SHA-256 novo de cada arquivo de dados alterado.

**O que mudou na tela**
- Mudanças visíveis para quem usa o painel, ou "Nenhuma".

**De onde veio**
- Endereço do SAPL consultado e data da coleta.
- Observações sobre dados ausentes ou diferentes na fonte, sem juízo de valor.
```

---

## 2026-10-01: 34a sessão ordinária e nova regra de presença

**O que mudou nos dados**
- Sessão ordinária 34 incluída: 29/09/2026 (registro 274 no SAPL), com 6 itens de ordem, 6 registros de votação e 54 votos nominais.
- 2026 passou a 34 sessões ordinárias; 2025 segue com 32. Presidente da sessão 34: Rafael Ventura, sem lacuna de presidência.
- Regra de presença D-046: contam só as sessões dentro do mandato; licença entra no total com rótulo próprio e nunca como falta; quem saiu tem a atuação congelada na data de saída. Jorge Quege na legislatura: 36 presenças em 60 sessões no mandato, taxa 60,0%.
- Matérias novas 966 a 969 com tema revisado pelo mantenedor.
- Hash SHA-256 novo de atuacao_vereadores_2025.json: e20e29463bf23096fb69aba46559b26b07df57562185a7a61cd6d5751b80b3df.
- Hash SHA-256 novo de atuacao_vereadores_2026.json: 976e28bd2ceaa73b722728fe61285eb0dc93e5667d51254a8e13810f60289fd0.

**O que mudou na tela**
- Legenda de presença mostra o total no mandato; a lista de fora do mandato saiu da tela.
- Última sessão na tela: 34a, 29/09/2026.

**De onde veio**
- SAPL da Câmara Municipal de Campo do Tenente, https://sapl.campodotenente.pr.leg.br. Coleta em 29/09/2026, consolidação em 01/10/2026.
- Decisão D-046 do mantenedor sobre a regra de presença.

---

## 2026-09-27: ajuste nas regras de imparcialidade

**O que mudou nos dados**
- Nenhum.

**O que mudou na tela**
- Nenhuma.

**De onde veio**
- Decisão do mantenedor registrada nos documentos do projeto.
- Regras de imparcialidade: deixa de proibir listas ordenadas e comparações entre vereadores; continuam proibidos rótulos partidários e dado sem fonte.

---

## 2026-09-26: estrutura inicial do projeto

**O que mudou nos dados**
- Nenhum dado publicado ainda. A coleta completa ainda não foi feita.
- Foi feita uma sondagem do SAPL apenas para conhecer o formato dos registros. Os números dessa sondagem não são publicados como resultado do painel.

**O que mudou na tela**
- Nenhuma. O endereço do painel está em construção.

**De onde veio**
- Fonte definida: SAPL da Câmara Municipal de Campo do Tenente, https://sapl.campodotenente.pr.leg.br
- Recorte definido: legislatura 2025 a 2028, sessões ordinárias. As sessões ordinárias 1 a 16 de 2025 não existem no SAPL, e o painel começa na 17ª, de 6 de maio de 2025.
- Documentos do projeto criados ou adaptados para Campo do Tenente: README.md, ARCHITECTURE.md e PROCESSO_DESENVOLVIMENTO_E_GOVERNANCA.md.
