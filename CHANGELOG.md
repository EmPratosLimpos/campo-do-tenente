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

## 2026-10-09: v1.2.1, atualização semanal mais segura, autoria completa e temas automáticos

**O que mudou nos dados**
- Autoria das matérias recoletada do SAPL com a lista em ordem fixa: 1.281 registros, sem repetição nem falta. Corrige a marca de primeiro autor em 10 matérias (entre elas IND 6, IND 56, IND 59 e REQ 36 de 2025); o número de matérias de cada vereador não muda.
- Nota sobre a posse do vereador Rivanildo Cavalheiro com texto revisto e três fontes oficiais.
- 2025 segue igual, com o mesmo hash.

**O que mudou na tela**
- Perfil do vereador Rivanildo Cavalheiro: a nota sobre a posse aparece em texto, com os links das fontes, no lugar de "[object Object]". O período do perfil mostra só os anos em que ele teve mandato.

**O que mudou na atualização semanal**
- Uma falha isolada do SAPL não derruba mais a semana: o pedido é repetido uma vez depois de 5 minutos. Se faltar algo da sessão nova, nada é publicado e abre uma issue.
- A sessão nova não é publicada com presença vazia; presença ainda não lançada no SAPL não vira falta.
- Novas tentativas às quartas às 16h e às quintas às 10h, só se a semana ainda não foi publicada.
- Tema de matéria nova escolhido por consenso de três modelos de inteligência artificial (decisões D-047, D-071 e D-072). Sem consenso, a matéria fica sem tema e o mantenedor recebe uma issue para decidir.
- Arquivo de ano fechado só é regravado quando o conteúdo muda.

**De onde veio**
- https://sapl.campodotenente.pr.leg.br/api/materia/autoria/ (lista ordenada por id), coletada em 09/10/2026, 21 pedidos.

## 2026-10-08: 35a sessão ordinária

**O que mudou nos dados**
- Sessão ordinária 35 incluída: 06/10/2026 (registro 275 no SAPL), com 4 itens de ordem, 4 registros de votação e 36 votos nominais. Votadas as IND 35, 36 e 37/2026 e o REQ 19/2026. Presidente da sessão: Rafael Ventura, 9 vereadores presentes.
- Revisão de lançamento atrasado da sessão 34 (29/09/2026): sem mudança nos votos.
- 2026 passou a 35 sessões ordinárias; 2025 segue igual, com o mesmo hash.
- Matérias novas 1047, 1052, 1054, 1055, 1056, 1058 e 1097 com tema: seis por consenso de três modelos (D-047), aprovadas pelo mantenedor, e a IND 37/2026 decidida pelo mantenedor porque os três modelos discordaram.
- Autoria de requerimentos, indicações e moções recoletada do SAPL. A lista de autorias do SAPL vem paginada sem ordem fixa e alguns registros podem faltar a cada coleta; a correção da coleta está em andamento.
- Hash SHA-256 novo de atuacao_vereadores_2026.json: c057c9e1a85ba545db27a0a72d97d0cd5c34db04d2bd3c54ca8c9fe07ae13dd8.
- Pedidos ao SAPL nesta coleta: 62.

**O que mudou na tela**
- Última sessão na tela: 35a, 06/10/2026.

**De onde veio**
- SAPL da Câmara Municipal de Campo do Tenente, https://sapl.campodotenente.pr.leg.br. Coleta em 08/10/2026.

---

## 2026-10-05: v1.2.0, pedidos dos vereadores e votações unificadas

**O que mudou nos dados**
- Nenhum arquivo de dados mudou. A configuração ganhou os nomes e as explicações de requerimentos, indicações e moções.

**O que mudou na tela**
- Cartão "Pedidos que fez" em cada vereador: requerimentos, indicações e moções, com tipos, temas e o primeiro autor em destaque.
- Aba Câmara: resumo do período, gráfico em rosca dos tipos votados e lista "Votações" com projetos, requerimentos, indicações, moções e vetos juntos, filtrável por tipo.
- "Do que tratam as votações" passa a contar todos os tipos.

**De onde veio**
- Dados do SAPL já publicados na v1.1. Pedidos sem registro de votação aparecem marcados: o SAPL só registra votações a partir de 13/05/2025.

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
