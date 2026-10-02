# Atuação dos vereadores nas sessões ordinárias de 2026

Cidade: Campo do Tenente (PR)
Dado coletado em: 2026-09-29T22:57:44-03:00
Fonte da data: dados/brutos/lote_20260927_autoria/indice.json campo atualizado_em
Script: `dados/tratados/gerar_atuacao_vereadores.py`
Fonte dos fatos: arquivos em `dados/brutos/`, `dados/tratados/vereadores.json`, `dados/tratados/presidencia_sessoes.json` e `dados/tratados/autoria_materias.json`.

## Em uma frase

Nas 34 sessões ordinárias de 2026 que estão no SAPL, os 10 vereadores com mandato nesse ano tiveram presença, voto e projetos de lei lidos do registro oficial.

## O que este recorte cobre

Ano 2026. Só sessão ordinária. O piso de sessões (33) é mínimo: o arquivo traz 34, que é pelo menos esse piso.

Presença e voto nominal só entram quando a data da sessão cai dentro do mandato da pessoa, pelas datas da tabela de vereadores. Sessão fora desse intervalo não aparece na lista da pessoa: a atuação de quem saiu fica congelada na data de saída.

## Como a presença foi lida

Presente: o vereador está na lista de presença da sessão ou na lista de presença da ordem do dia, e a data está dentro do mandato.

Falta com justificativa: não está em nenhuma das duas listas e está na lista de justificativa de ausência, ou está em licença para tratamento de saúde (afastamento manual) ou em ausência por licença médica do SAPL. Cada sessão guarda o motivo como está na fonte.

Falta sem justificativa: não está na presença e não está na justificativa.

Fora do mandato: a data da sessão é anterior ao início ou posterior ao fim do mandato. Essa sessão não aparece na lista da pessoa e não entra na taxa de presença.

Taxa de presença: presenças divididas pelo total de sessões no mandato, que soma presenças e faltas com e sem justificativa.

## Como o voto foi lido

Cada votação com voto individual recebe um estado para cada vereador da banca do ano. Os rótulos não se misturam.

Cada votação de projeto de lei tem um turno: a primeira data é o 1o turno e a seguinte em outra sessão é o 2o turno; os demais tipos seguem turno único. A contagem de votos de cada vereador considera só o 2o turno e o turno único. O 1o turno aparece na lista com a tag, sem entrar na contagem. Projeto aprovado só no 1o turno continua em tramitação; rejeitado no 1o turno segue rejeitado. Votação sem deliberação (adiada, pedido de vistas, retirada de pauta) aparece com o nome oficial do SAPL e não entra em nenhuma contagem de voto.

- Sim
- Não
- Abstenção
- Não votou
- Presidente que não votou
- Ausente com justificativa
- Ausente sem justificativa
- Fora do mandato naquela data
- Presente na sessão sem voto individual registrado

Votação sem nenhum voto individual: voto individual nao registrado no SAPL. Ninguém recebe estado de voto. O arquivo mostra só os totais oficiais (sim, não e abstenção) e o link da sessão e da matéria. Isso não é lido como voto unânime.

Presidente que não votou só vale quando o texto do SAPL é Não Votou e essa pessoa é o presidente daquela sessão em `presidencia_sessoes.json`.

Licença para tratamento de saúde (`afastamentos_manuais.json`) e ausência por licença médica do SAPL contam como falta com justificativa, com o motivo e a fonte guardados na sessão. No histórico de votos, valem como ausente com justificativa.

## Presença de cada vereador

### Jorge Quege

Partido: PP (PARTIDO PROGRESSISTA)

Página oficial: https://sapl.campodotenente.pr.leg.br/parlamentar/1

Presente em 4 das 28 sessões em que a presença conta (taxa 14,29%).

Faltas com justificativa: 24. Faltas sem justificativa: 0. Sessões fora do mandato: 6.

### Dr. Marcos Rodrigues

Partido: MDB (MOVIMENTO DEMOCRÁTICO BRASILEIRO)

Página oficial: https://sapl.campodotenente.pr.leg.br/parlamentar/2

Presente em 32 das 34 sessões em que a presença conta (taxa 94,12%).

Faltas com justificativa: 1. Faltas sem justificativa: 1. Sessões fora do mandato: 0.

### Cleiton Costa

Partido: PDT (PARTIDO DEMOCRÁTICO TRABALHISTA)

Página oficial: https://sapl.campodotenente.pr.leg.br/parlamentar/3

Presente em 33 das 34 sessões em que a presença conta (taxa 97,06%).

Faltas com justificativa: 1. Faltas sem justificativa: 0. Sessões fora do mandato: 0.

### Kinho Lazarino

Partido: MDB (MOVIMENTO DEMOCRÁTICO BRASILEIRO)

Página oficial: https://sapl.campodotenente.pr.leg.br/parlamentar/4

Presente em 32 das 34 sessões em que a presença conta (taxa 94,12%).

Faltas com justificativa: 1. Faltas sem justificativa: 1. Sessões fora do mandato: 0.

### Rafael Ventura

Partido: PL (PARTIDO LIBERAL)

Página oficial: https://sapl.campodotenente.pr.leg.br/parlamentar/5

Presente em 34 das 34 sessões em que a presença conta (taxa 100,00%).

Faltas com justificativa: 0. Faltas sem justificativa: 0. Sessões fora do mandato: 0.

### Gustavo Vizentin

Partido: UNIÃO (UNIÃO BRASIL)

Página oficial: https://sapl.campodotenente.pr.leg.br/parlamentar/6

Presente em 34 das 34 sessões em que a presença conta (taxa 100,00%).

Faltas com justificativa: 0. Faltas sem justificativa: 0. Sessões fora do mandato: 0.

### Josemar Veiga

Partido: PL (PARTIDO LIBERAL)

Página oficial: https://sapl.campodotenente.pr.leg.br/parlamentar/7

Presente em 34 das 34 sessões em que a presença conta (taxa 100,00%).

Faltas com justificativa: 0. Faltas sem justificativa: 0. Sessões fora do mandato: 0.

### Beto Maurer

Partido: PP (PARTIDO PROGRESSISTA)

Página oficial: https://sapl.campodotenente.pr.leg.br/parlamentar/8

Presente em 32 das 34 sessões em que a presença conta (taxa 94,12%).

Faltas com justificativa: 0. Faltas sem justificativa: 2. Sessões fora do mandato: 0.

### Gilmar Barbosa

Partido: UNIÃO (UNIÃO BRASIL)

Página oficial: https://sapl.campodotenente.pr.leg.br/parlamentar/9

Presente em 32 das 34 sessões em que a presença conta (taxa 94,12%).

Faltas com justificativa: 2. Faltas sem justificativa: 0. Sessões fora do mandato: 0.

### Rivanildo Cavalheiro

Partido: PP (PARTIDO PROGRESSISTA)

Página oficial: https://sapl.campodotenente.pr.leg.br/parlamentar/100

Presente em 29 das 29 sessões em que a presença conta (taxa 100,00%).

Faltas com justificativa: 0. Faltas sem justificativa: 0. Sessões fora do mandato: 5.

assumiu em 2026-03-17 durante a licenca de Jorge Quege; vaga permanente apos a cassacao em 2026-08-18

Fonte: Noticia da Camara: Rivanildo Braz Cavalheiro assume vaga de suplente na Câmara Municipal. Link: https://www.campodotenente.pr.leg.br/institucional/noticias/rivanildo-braz-cavalheiro-assume-vaga-de-suplente-na-camara-municipal.
Fonte: Ata da sessao ordinaria de 17 de marco de 2026 registra a posse do suplente e nao registra a licenca. Link: https://sapl.campodotenente.pr.leg.br/materia/274.
Fonte: Projeto de Decreto Legislativo n 2 de 2026. Link: https://sapl.campodotenente.pr.leg.br/materia/792.

## Estados de voto de cada vereador

### Jorge Quege

- Sim: 2
- Não: 0
- Abstenção: 0
- Não votou: 0
- Presidente que não votou: 0
- Ausente com justificativa: 64
- Ausente sem justificativa: 0
- Fora do mandato naquela data: 0
- Presente na sessão sem voto individual registrado: 0

Votações sem voto individual não entram nesta lista. No ano foram 20.

### Dr. Marcos Rodrigues

- Sim: 83
- Não: 0
- Abstenção: 0
- Não votou: 0
- Presidente que não votou: 0
- Ausente com justificativa: 5
- Ausente sem justificativa: 1
- Fora do mandato naquela data: 0
- Presente na sessão sem voto individual registrado: 0

Votações sem voto individual não entram nesta lista. No ano foram 20.

### Cleiton Costa

- Sim: 85
- Não: 0
- Abstenção: 0
- Não votou: 0
- Presidente que não votou: 0
- Ausente com justificativa: 4
- Ausente sem justificativa: 0
- Fora do mandato naquela data: 0
- Presente na sessão sem voto individual registrado: 0

Votações sem voto individual não entram nesta lista. No ano foram 20.

### Kinho Lazarino

- Sim: 82
- Não: 0
- Abstenção: 0
- Não votou: 0
- Presidente que não votou: 0
- Ausente com justificativa: 4
- Ausente sem justificativa: 3
- Fora do mandato naquela data: 0
- Presente na sessão sem voto individual registrado: 0

Votações sem voto individual não entram nesta lista. No ano foram 20.

### Rafael Ventura

- Sim: 6
- Não: 0
- Abstenção: 0
- Não votou: 0
- Presidente que não votou: 83
- Ausente com justificativa: 0
- Ausente sem justificativa: 0
- Fora do mandato naquela data: 0
- Presente na sessão sem voto individual registrado: 0

Votações sem voto individual não entram nesta lista. No ano foram 20.

### Gustavo Vizentin

- Sim: 89
- Não: 0
- Abstenção: 0
- Não votou: 0
- Presidente que não votou: 0
- Ausente com justificativa: 0
- Ausente sem justificativa: 0
- Fora do mandato naquela data: 0
- Presente na sessão sem voto individual registrado: 0

Votações sem voto individual não entram nesta lista. No ano foram 20.

### Josemar Veiga

- Sim: 87
- Não: 0
- Abstenção: 0
- Não votou: 0
- Presidente que não votou: 0
- Ausente com justificativa: 0
- Ausente sem justificativa: 0
- Fora do mandato naquela data: 0
- Presente na sessão sem voto individual registrado: 2

Votações sem voto individual não entram nesta lista. No ano foram 20.

### Beto Maurer

- Sim: 80
- Não: 2
- Abstenção: 0
- Não votou: 0
- Presidente que não votou: 0
- Ausente com justificativa: 0
- Ausente sem justificativa: 7
- Fora do mandato naquela data: 0
- Presente na sessão sem voto individual registrado: 0

Votações sem voto individual não entram nesta lista. No ano foram 20.

### Gilmar Barbosa

- Sim: 82
- Não: 0
- Abstenção: 0
- Não votou: 0
- Presidente que não votou: 0
- Ausente com justificativa: 7
- Ausente sem justificativa: 0
- Fora do mandato naquela data: 0
- Presente na sessão sem voto individual registrado: 0

Votações sem voto individual não entram nesta lista. No ano foram 20.

### Rivanildo Cavalheiro

- Sim: 85
- Não: 0
- Abstenção: 2
- Não votou: 0
- Presidente que não votou: 0
- Ausente com justificativa: 0
- Ausente sem justificativa: 0
- Fora do mandato naquela data: 0
- Presente na sessão sem voto individual registrado: 0

Votações sem voto individual não entram nesta lista. No ano foram 20.

## Projetos de lei

Projetos de lei do Legislativo: 5. Projetos de lei do Executivo: 13. Soma, conferida como mínimo: 18 (piso 18).

A autoria veio de `autoria_materias.json`. A lista de cada vereador abaixo só inclui projeto de lei do Legislativo em que o id do parlamentar aparece como autor.

O tema de cada matéria veio de `temas_materias.json`.

Classificação por tema revisada pelo mantenedor em todas as matérias com tema.

### Jorge Quege

Projetos de lei do Legislativo: 0. Aprovados: 0. Rejeitados: 0. Em tramitação: 0.

Nenhum projeto de lei do Legislativo com esta autoria neste ano.

### Dr. Marcos Rodrigues

Projetos de lei do Legislativo: 1. Aprovados: 1. Rejeitados: 0. Em tramitação: 0.

- 4/2026 (id 811): Dispõe sobre princípios, critérios gerais e transparência nos programas habitacionais de interesse social que contem com participação do Município de Campo do Tenente e dá outras providências. Situação: Aprovado. Fonte: https://sapl.campodotenente.pr.leg.br/materia/811

### Cleiton Costa

Projetos de lei do Legislativo: 0. Aprovados: 0. Rejeitados: 0. Em tramitação: 0.

Nenhum projeto de lei do Legislativo com esta autoria neste ano.

### Kinho Lazarino

Projetos de lei do Legislativo: 1. Aprovados: 1. Rejeitados: 0. Em tramitação: 0.

- 3/2026 (id 698): Dispõe sobre a obrigatoriedade de notificação à Companhia de Saneamento do Paraná – Sanepar, quanto da realização de obras de pavimentação. Situação: Aprovado. Fonte: https://sapl.campodotenente.pr.leg.br/materia/698

### Rafael Ventura

Projetos de lei do Legislativo: 3. Aprovados: 3. Rejeitados: 0. Em tramitação: 0.

- 1/2026 (id 244): "CONCEDE REVISÃO GERAL ANUAL AOS SERVIDORES EFETIVOS E COMISSIONADOS DA CÂMARA MUNICIPAL DE CAMPO DO TENENTE." Situação: Aprovado. Fonte: https://sapl.campodotenente.pr.leg.br/materia/244
- 2/2026 (id 245): "CONCEDE REVISÃO DO VALOR DO AUXÍLIO-ALIMENTAÇÃO DOS SERVIDORES EFETIVOS E COMISSIONADOS DA CÂMARA MUNICIPAL DE CAMPO DO TENENTE-PR ALTERA O PARÁGRAFO ÚNICO DO ARTIGO 2° DA LEI MUNICIPAL N°1.066/2022." Situação: Aprovado. Fonte: https://sapl.campodotenente.pr.leg.br/materia/245
- 5/2026 (id 815): Altera a Lei Municipal nº 1.094, de 2022, que institui o “Título Mãe Tenenteana” no Município de Campo do Tenente. Situação: Aprovado. Fonte: https://sapl.campodotenente.pr.leg.br/materia/815

### Gustavo Vizentin

Projetos de lei do Legislativo: 1. Aprovados: 1. Rejeitados: 0. Em tramitação: 0.

- 3/2026 (id 698): Dispõe sobre a obrigatoriedade de notificação à Companhia de Saneamento do Paraná – Sanepar, quanto da realização de obras de pavimentação. Situação: Aprovado. Fonte: https://sapl.campodotenente.pr.leg.br/materia/698

### Josemar Veiga

Projetos de lei do Legislativo: 0. Aprovados: 0. Rejeitados: 0. Em tramitação: 0.

Nenhum projeto de lei do Legislativo com esta autoria neste ano.

### Beto Maurer

Projetos de lei do Legislativo: 0. Aprovados: 0. Rejeitados: 0. Em tramitação: 0.

Nenhum projeto de lei do Legislativo com esta autoria neste ano.

### Gilmar Barbosa

Projetos de lei do Legislativo: 0. Aprovados: 0. Rejeitados: 0. Em tramitação: 0.

Nenhum projeto de lei do Legislativo com esta autoria neste ano.

### Rivanildo Cavalheiro

Projetos de lei do Legislativo: 0. Aprovados: 0. Rejeitados: 0. Em tramitação: 0.

Nenhum projeto de lei do Legislativo com esta autoria neste ano.

## Totais

- Sessões ordinárias no SAPL: 34
- Vereadores com mandato no ano: 10
- Presenças dentro do mandato: 296
- Faltas com justificativa: 29
- Faltas sem justificativa: 4
- Afastamentos que não contam como falta: 0
- Votações: 126
- Votações com voto individual: 106
- Votações sem voto individual: 20

## Como repetir

Na pasta do projeto, rode:

    python dados/tratados/gerar_atuacao_vereadores.py

O programa lê os brutos de novo e reescreve o JSON, o CSV e este relatório do ano. Não edite esses arquivos na mão.
