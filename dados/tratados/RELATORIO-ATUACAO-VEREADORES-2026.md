# Atuação dos vereadores nas sessões ordinárias de 2026

Cidade: Campo do Tenente (PR)
Dado coletado em: 2026-09-27T13:17:32-03:00
Fonte da data: dados/brutos/lote_20260927_atas/indice.json campo atualizado_em
Script: `dados/tratados/gerar_atuacao_vereadores.py`
Fonte dos fatos: arquivos em `dados/brutos/`, `dados/tratados/vereadores.json`, `dados/tratados/presidencia_sessoes.json` e `dados/tratados/autoria_materias.json`.

## Em uma frase

Nas 33 sessões ordinárias de 2026 que estão no SAPL, os 10 vereadores com mandato nesse ano tiveram presença, voto e projetos de lei lidos do registro oficial.

## O que este recorte cobre

Ano 2026. Só sessão ordinária. O piso de sessões (33) é mínimo: o arquivo traz 33, que é pelo menos esse piso.

Presença e voto só entram quando a data da sessão cai dentro do mandato da pessoa, pelas datas da tabela de vereadores. Fora desse intervalo o estado é próprio: fora do mandato.

## Como a presença foi lida

Presente: o vereador está na lista de presença da sessão ou na lista de presença da ordem do dia, e a data está dentro do mandato.

Falta com justificativa: não está em nenhuma das duas listas e está na lista de justificativa de ausência.

Falta sem justificativa: não está na presença e não está na justificativa.

Fora do mandato: a data da sessão é anterior ao início ou posterior ao fim do mandato. Essa sessão não entra na taxa de presença.

## Como o voto foi lido

Cada votação com voto individual recebe um estado para cada vereador da banca do ano. Os rótulos não se misturam.

- Sim
- Não
- Abstenção
- Não votou
- Presidente que não votou
- Ausente com justificativa
- Ausente sem justificativa
- Fora do mandato naquela data
- Presente na sessão sem voto individual registrado
- Licenca para tratamento de saude

Votação sem nenhum voto individual: voto individual nao registrado no SAPL. Ninguém recebe estado de voto. O arquivo mostra só os totais oficiais (sim, não e abstenção) e o link da sessão e da matéria. Isso não é lido como voto unânime.

Presidente que não votou só vale quando o texto do SAPL é Não Votou e essa pessoa é o presidente daquela sessão em `presidencia_sessoes.json`.

Afastamento que não conta como falta vem de `afastamentos_manuais.json`. Esse período não entra em falta nem na taxa de presença. Cada ocorrência guarda a fonte.

## Presença de cada vereador

### Jorge Quege

Partido: PP (PARTIDO PROGRESSISTA)

Página oficial: https://sapl.campodotenente.pr.leg.br/parlamentar/1

Presente em 4 das 5 sessões em que a presença conta (taxa 80,00%).

Faltas com justificativa: 1. Faltas sem justificativa: 0. Afastamentos que não contam como falta: 23. Sessões fora do mandato: 5.

### Dr. Marcos Rodrigues

Partido: MDB (MOVIMENTO DEMOCRÁTICO BRASILEIRO)

Página oficial: https://sapl.campodotenente.pr.leg.br/parlamentar/2

Presente em 31 das 33 sessões em que a presença conta (taxa 93,94%).

Faltas com justificativa: 1. Faltas sem justificativa: 1. Afastamentos que não contam como falta: 0. Sessões fora do mandato: 0.

### Cleiton Costa

Partido: PDT (PARTIDO DEMOCRÁTICO TRABALHISTA)

Página oficial: https://sapl.campodotenente.pr.leg.br/parlamentar/3

Presente em 32 das 33 sessões em que a presença conta (taxa 96,97%).

Faltas com justificativa: 1. Faltas sem justificativa: 0. Afastamentos que não contam como falta: 0. Sessões fora do mandato: 0.

### Kinho Lazarino

Partido: MDB (MOVIMENTO DEMOCRÁTICO BRASILEIRO)

Página oficial: https://sapl.campodotenente.pr.leg.br/parlamentar/4

Presente em 31 das 33 sessões em que a presença conta (taxa 93,94%).

Faltas com justificativa: 1. Faltas sem justificativa: 1. Afastamentos que não contam como falta: 0. Sessões fora do mandato: 0.

### Rafael Ventura

Partido: PL (PARTIDO LIBERAL)

Página oficial: https://sapl.campodotenente.pr.leg.br/parlamentar/5

Presente em 33 das 33 sessões em que a presença conta (taxa 100,00%).

Faltas com justificativa: 0. Faltas sem justificativa: 0. Afastamentos que não contam como falta: 0. Sessões fora do mandato: 0.

### Gustavo Vizentin

Partido: UNIÃO (UNIÃO BRASIL)

Página oficial: https://sapl.campodotenente.pr.leg.br/parlamentar/6

Presente em 33 das 33 sessões em que a presença conta (taxa 100,00%).

Faltas com justificativa: 0. Faltas sem justificativa: 0. Afastamentos que não contam como falta: 0. Sessões fora do mandato: 0.

### Josemar Veiga

Partido: PL (PARTIDO LIBERAL)

Página oficial: https://sapl.campodotenente.pr.leg.br/parlamentar/7

Presente em 33 das 33 sessões em que a presença conta (taxa 100,00%).

Faltas com justificativa: 0. Faltas sem justificativa: 0. Afastamentos que não contam como falta: 0. Sessões fora do mandato: 0.

### Beto Maurer

Partido: PP (PARTIDO PROGRESSISTA)

Página oficial: https://sapl.campodotenente.pr.leg.br/parlamentar/8

Presente em 31 das 33 sessões em que a presença conta (taxa 93,94%).

Faltas com justificativa: 0. Faltas sem justificativa: 2. Afastamentos que não contam como falta: 0. Sessões fora do mandato: 0.

### Gilmar Barbosa

Partido: UNIÃO (UNIÃO BRASIL)

Página oficial: https://sapl.campodotenente.pr.leg.br/parlamentar/9

Presente em 31 das 33 sessões em que a presença conta (taxa 93,94%).

Faltas com justificativa: 2. Faltas sem justificativa: 0. Afastamentos que não contam como falta: 0. Sessões fora do mandato: 0.

### Rivanildo Cavalheiro

Partido: PP (PARTIDO PROGRESSISTA)

Página oficial: https://sapl.campodotenente.pr.leg.br/parlamentar/100

Presente em 28 das 28 sessões em que a presença conta (taxa 100,00%).

Faltas com justificativa: 0. Faltas sem justificativa: 0. Afastamentos que não contam como falta: 0. Sessões fora do mandato: 5.

assumiu em 2026-03-17 durante a licenca de Jorge Quege; vaga permanente apos a cassacao em 2026-08-18

Fonte: comunicado da Camara informado pelo mantenedor em 2026-09-27. Link: sem link.
Fonte: Ata da sessao ordinaria de 17 de marco de 2026 registra a posse do suplente e nao registra a licenca. Link: https://sapl.campodotenente.pr.leg.br/materia/274.
Fonte: Projeto de Decreto Legislativo n 2 de 2026. Link: https://sapl.campodotenente.pr.leg.br/materia/792.

## Estados de voto de cada vereador

### Jorge Quege

- Sim: 7
- Não: 0
- Abstenção: 0
- Não votou: 0
- Presidente que não votou: 0
- Ausente com justificativa: 0
- Ausente sem justificativa: 0
- Fora do mandato naquela data: 21
- Presente na sessão sem voto individual registrado: 0
- Licenca para tratamento de saude: 72

Votações sem voto individual não entram nesta lista. No ano foram 20.

### Dr. Marcos Rodrigues

- Sim: 93
- Não: 1
- Abstenção: 0
- Não votou: 0
- Presidente que não votou: 0
- Ausente com justificativa: 5
- Ausente sem justificativa: 1
- Fora do mandato naquela data: 0
- Presente na sessão sem voto individual registrado: 0
- Licenca para tratamento de saude: 0

Votações sem voto individual não entram nesta lista. No ano foram 20.

### Cleiton Costa

- Sim: 94
- Não: 1
- Abstenção: 0
- Não votou: 0
- Presidente que não votou: 0
- Ausente com justificativa: 5
- Ausente sem justificativa: 0
- Fora do mandato naquela data: 0
- Presente na sessão sem voto individual registrado: 0
- Licenca para tratamento de saude: 0

Votações sem voto individual não entram nesta lista. No ano foram 20.

### Kinho Lazarino

- Sim: 91
- Não: 1
- Abstenção: 0
- Não votou: 0
- Presidente que não votou: 0
- Ausente com justificativa: 5
- Ausente sem justificativa: 3
- Fora do mandato naquela data: 0
- Presente na sessão sem voto individual registrado: 0
- Licenca para tratamento de saude: 0

Votações sem voto individual não entram nesta lista. No ano foram 20.

### Rafael Ventura

- Sim: 7
- Não: 0
- Abstenção: 0
- Não votou: 0
- Presidente que não votou: 93
- Ausente com justificativa: 0
- Ausente sem justificativa: 0
- Fora do mandato naquela data: 0
- Presente na sessão sem voto individual registrado: 0
- Licenca para tratamento de saude: 0

Votações sem voto individual não entram nesta lista. No ano foram 20.

### Gustavo Vizentin

- Sim: 99
- Não: 1
- Abstenção: 0
- Não votou: 0
- Presidente que não votou: 0
- Ausente com justificativa: 0
- Ausente sem justificativa: 0
- Fora do mandato naquela data: 0
- Presente na sessão sem voto individual registrado: 0
- Licenca para tratamento de saude: 0

Votações sem voto individual não entram nesta lista. No ano foram 20.

### Josemar Veiga

- Sim: 97
- Não: 1
- Abstenção: 0
- Não votou: 0
- Presidente que não votou: 0
- Ausente com justificativa: 0
- Ausente sem justificativa: 0
- Fora do mandato naquela data: 0
- Presente na sessão sem voto individual registrado: 2
- Licenca para tratamento de saude: 0

Votações sem voto individual não entram nesta lista. No ano foram 20.

### Beto Maurer

- Sim: 90
- Não: 2
- Abstenção: 0
- Não votou: 0
- Presidente que não votou: 0
- Ausente com justificativa: 0
- Ausente sem justificativa: 8
- Fora do mandato naquela data: 0
- Presente na sessão sem voto individual registrado: 0
- Licenca para tratamento de saude: 0

Votações sem voto individual não entram nesta lista. No ano foram 20.

### Gilmar Barbosa

- Sim: 91
- Não: 1
- Abstenção: 0
- Não votou: 0
- Presidente que não votou: 0
- Ausente com justificativa: 8
- Ausente sem justificativa: 0
- Fora do mandato naquela data: 0
- Presente na sessão sem voto individual registrado: 0
- Licenca para tratamento de saude: 0

Votações sem voto individual não entram nesta lista. No ano foram 20.

### Rivanildo Cavalheiro

- Sim: 90
- Não: 1
- Abstenção: 2
- Não votou: 0
- Presidente que não votou: 0
- Ausente com justificativa: 0
- Ausente sem justificativa: 0
- Fora do mandato naquela data: 7
- Presente na sessão sem voto individual registrado: 0
- Licenca para tratamento de saude: 0

Votações sem voto individual não entram nesta lista. No ano foram 20.

## Projetos de lei

Projetos de lei do Legislativo: 5. Projetos de lei do Executivo: 13. Soma, conferida como mínimo: 18 (piso 18).

A autoria veio de `autoria_materias.json`. A lista de cada vereador abaixo só inclui projeto de lei do Legislativo em que o id do parlamentar aparece como autor.

A classificação por tema ainda não foi revisada por uma pessoa.

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

- Sessões ordinárias no SAPL: 33
- Vereadores com mandato no ano: 10
- Presenças dentro do mandato: 287
- Faltas com justificativa: 6
- Faltas sem justificativa: 4
- Afastamentos que não contam como falta: 23
- Votações: 120
- Votações com voto individual: 100
- Votações sem voto individual: 20

## Como repetir

Na pasta do projeto, rode:

    python dados/tratados/gerar_atuacao_vereadores.py

O programa lê os brutos de novo e reescreve o JSON, o CSV e este relatório do ano. Não edite esses arquivos na mão.
