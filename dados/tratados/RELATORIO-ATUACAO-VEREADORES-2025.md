# Atuação dos vereadores nas sessões ordinárias de 2025

Cidade: Campo do Tenente (PR)
Dado coletado em: 2026-09-27T13:53:03-03:00
Fonte da data: dados/brutos/lote_20260927_noticia_licenca/indice.json campo atualizado_em
Script: `dados/tratados/gerar_atuacao_vereadores.py`
Fonte dos fatos: arquivos em `dados/brutos/`, `dados/tratados/vereadores.json`, `dados/tratados/presidencia_sessoes.json` e `dados/tratados/autoria_materias.json`.

## Em uma frase

Nas 32 sessões ordinárias de 2025 que estão no SAPL, os 9 vereadores com mandato nesse ano tiveram presença, voto e projetos de lei lidos do registro oficial.

## O que este recorte cobre

Ano 2025. Só sessão ordinária. O piso de sessões (32) é mínimo: o arquivo traz 32, que é pelo menos esse piso.

Presença e voto nominal só entram quando a data da sessão cai dentro do mandato da pessoa, pelas datas da tabela de vereadores. Sessão fora desse intervalo não aparece na lista da pessoa: a atuação de quem saiu fica congelada na data de saída.

## Lacuna no SAPL

As sessoes ordinarias 1 a 16 de 2025 nao existem no SAPL.

Números de sessão ordinária ausentes no SAPL: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16.

## Como a presença foi lida

Presente: o vereador está na lista de presença da sessão ou na lista de presença da ordem do dia, e a data está dentro do mandato.

Falta com justificativa: não está em nenhuma das duas listas e está na lista de justificativa de ausência.

Falta sem justificativa: não está na presença e não está na justificativa.

Fora do mandato: a data da sessão é anterior ao início ou posterior ao fim do mandato. Essa sessão não aparece na lista da pessoa e não entra na taxa de presença.

Taxa de presença: presenças divididas pelo total de sessões no mandato, que soma presenças, faltas com e sem justificativa e licenças.

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
- Licença para tratamento de saúde

Votação sem nenhum voto individual: voto individual nao registrado no SAPL. Ninguém recebe estado de voto. O arquivo mostra só os totais oficiais (sim, não e abstenção) e o link da sessão e da matéria. Isso não é lido como voto unânime.

Presidente que não votou só vale quando o texto do SAPL é Não Votou e essa pessoa é o presidente daquela sessão em `presidencia_sessoes.json`.

Licença ou afastamento que não conta como falta vem de `afastamentos_manuais.json`, tem rótulo próprio e nunca é chamado de falta, mas entra no total de sessões da taxa de presença. Cada ocorrência guarda a fonte.

## Presença de cada vereador

### Jorge Quege

Partido: PP (PARTIDO PROGRESSISTA)

Página oficial: https://sapl.campodotenente.pr.leg.br/parlamentar/1

Presente em 32 das 32 sessões em que a presença conta (taxa 100,00%).

Faltas com justificativa: 0. Faltas sem justificativa: 0. Afastamentos que não contam como falta: 0. Sessões fora do mandato: 0.

### Dr. Marcos Rodrigues

Partido: MDB (MOVIMENTO DEMOCRÁTICO BRASILEIRO)

Página oficial: https://sapl.campodotenente.pr.leg.br/parlamentar/2

Presente em 30 das 32 sessões em que a presença conta (taxa 93,75%).

Faltas com justificativa: 0. Faltas sem justificativa: 2. Afastamentos que não contam como falta: 0. Sessões fora do mandato: 0.

### Cleiton Costa

Partido: PDT (PARTIDO DEMOCRÁTICO TRABALHISTA)

Página oficial: https://sapl.campodotenente.pr.leg.br/parlamentar/3

Presente em 32 das 32 sessões em que a presença conta (taxa 100,00%).

Faltas com justificativa: 0. Faltas sem justificativa: 0. Afastamentos que não contam como falta: 0. Sessões fora do mandato: 0.

### Kinho Lazarino

Partido: MDB (MOVIMENTO DEMOCRÁTICO BRASILEIRO)

Página oficial: https://sapl.campodotenente.pr.leg.br/parlamentar/4

Presente em 31 das 32 sessões em que a presença conta (taxa 96,88%).

Faltas com justificativa: 1. Faltas sem justificativa: 0. Afastamentos que não contam como falta: 0. Sessões fora do mandato: 0.

### Rafael Ventura

Partido: PL (PARTIDO LIBERAL)

Página oficial: https://sapl.campodotenente.pr.leg.br/parlamentar/5

Presente em 32 das 32 sessões em que a presença conta (taxa 100,00%).

Faltas com justificativa: 0. Faltas sem justificativa: 0. Afastamentos que não contam como falta: 0. Sessões fora do mandato: 0.

### Gustavo Vizentin

Partido: UNIÃO (UNIÃO BRASIL)

Página oficial: https://sapl.campodotenente.pr.leg.br/parlamentar/6

Presente em 32 das 32 sessões em que a presença conta (taxa 100,00%).

Faltas com justificativa: 0. Faltas sem justificativa: 0. Afastamentos que não contam como falta: 0. Sessões fora do mandato: 0.

### Josemar Veiga

Partido: PL (PARTIDO LIBERAL)

Página oficial: https://sapl.campodotenente.pr.leg.br/parlamentar/7

Presente em 32 das 32 sessões em que a presença conta (taxa 100,00%).

Faltas com justificativa: 0. Faltas sem justificativa: 0. Afastamentos que não contam como falta: 0. Sessões fora do mandato: 0.

### Beto Maurer

Partido: PP (PARTIDO PROGRESSISTA)

Página oficial: https://sapl.campodotenente.pr.leg.br/parlamentar/8

Presente em 29 das 32 sessões em que a presença conta (taxa 90,62%).

Faltas com justificativa: 0. Faltas sem justificativa: 3. Afastamentos que não contam como falta: 0. Sessões fora do mandato: 0.

### Gilmar Barbosa

Partido: UNIÃO (UNIÃO BRASIL)

Página oficial: https://sapl.campodotenente.pr.leg.br/parlamentar/9

Presente em 29 das 32 sessões em que a presença conta (taxa 90,62%).

Faltas com justificativa: 1. Faltas sem justificativa: 2. Afastamentos que não contam como falta: 0. Sessões fora do mandato: 0.

## Estados de voto de cada vereador

### Jorge Quege

- Sim: 19
- Não: 0
- Abstenção: 0
- Não votou: 0
- Presidente que não votou: 0
- Ausente com justificativa: 0
- Ausente sem justificativa: 0
- Fora do mandato naquela data: 0
- Presente na sessão sem voto individual registrado: 0
- Licença para tratamento de saúde: 0

Votações sem voto individual não entram nesta lista. No ano foram 96.

### Dr. Marcos Rodrigues

- Sim: 19
- Não: 0
- Abstenção: 0
- Não votou: 0
- Presidente que não votou: 0
- Ausente com justificativa: 0
- Ausente sem justificativa: 0
- Fora do mandato naquela data: 0
- Presente na sessão sem voto individual registrado: 0
- Licença para tratamento de saúde: 0

Votações sem voto individual não entram nesta lista. No ano foram 96.

### Cleiton Costa

- Sim: 17
- Não: 2
- Abstenção: 0
- Não votou: 0
- Presidente que não votou: 0
- Ausente com justificativa: 0
- Ausente sem justificativa: 0
- Fora do mandato naquela data: 0
- Presente na sessão sem voto individual registrado: 0
- Licença para tratamento de saúde: 0

Votações sem voto individual não entram nesta lista. No ano foram 96.

### Kinho Lazarino

- Sim: 19
- Não: 0
- Abstenção: 0
- Não votou: 0
- Presidente que não votou: 0
- Ausente com justificativa: 0
- Ausente sem justificativa: 0
- Fora do mandato naquela data: 0
- Presente na sessão sem voto individual registrado: 0
- Licença para tratamento de saúde: 0

Votações sem voto individual não entram nesta lista. No ano foram 96.

### Rafael Ventura

- Sim: 19
- Não: 0
- Abstenção: 0
- Não votou: 0
- Presidente que não votou: 0
- Ausente com justificativa: 0
- Ausente sem justificativa: 0
- Fora do mandato naquela data: 0
- Presente na sessão sem voto individual registrado: 0
- Licença para tratamento de saúde: 0

Votações sem voto individual não entram nesta lista. No ano foram 96.

### Gustavo Vizentin

- Sim: 19
- Não: 0
- Abstenção: 0
- Não votou: 0
- Presidente que não votou: 0
- Ausente com justificativa: 0
- Ausente sem justificativa: 0
- Fora do mandato naquela data: 0
- Presente na sessão sem voto individual registrado: 0
- Licença para tratamento de saúde: 0

Votações sem voto individual não entram nesta lista. No ano foram 96.

### Josemar Veiga

- Sim: 19
- Não: 0
- Abstenção: 0
- Não votou: 0
- Presidente que não votou: 0
- Ausente com justificativa: 0
- Ausente sem justificativa: 0
- Fora do mandato naquela data: 0
- Presente na sessão sem voto individual registrado: 0
- Licença para tratamento de saúde: 0

Votações sem voto individual não entram nesta lista. No ano foram 96.

### Beto Maurer

- Sim: 13
- Não: 0
- Abstenção: 0
- Não votou: 0
- Presidente que não votou: 0
- Ausente com justificativa: 0
- Ausente sem justificativa: 6
- Fora do mandato naquela data: 0
- Presente na sessão sem voto individual registrado: 0
- Licença para tratamento de saúde: 0

Votações sem voto individual não entram nesta lista. No ano foram 96.

### Gilmar Barbosa

- Sim: 19
- Não: 0
- Abstenção: 0
- Não votou: 0
- Presidente que não votou: 0
- Ausente com justificativa: 0
- Ausente sem justificativa: 0
- Fora do mandato naquela data: 0
- Presente na sessão sem voto individual registrado: 0
- Licença para tratamento de saúde: 0

Votações sem voto individual não entram nesta lista. No ano foram 96.

## Projetos de lei

Projetos de lei do Legislativo: 18. Projetos de lei do Executivo: 26. Soma, conferida como mínimo: 44 (piso 44).

A autoria veio de `autoria_materias.json`. A lista de cada vereador abaixo só inclui projeto de lei do Legislativo em que o id do parlamentar aparece como autor.

O tema de cada matéria veio de `temas_materias.json`.

Classificação por tema revisada pelo mantenedor em todas as matérias com tema.

### Jorge Quege

Projetos de lei do Legislativo: 0. Aprovados: 0. Rejeitados: 0. Em tramitação: 0.

Nenhum projeto de lei do Legislativo com esta autoria neste ano.

### Dr. Marcos Rodrigues

Projetos de lei do Legislativo: 6. Aprovados: 3. Rejeitados: 0. Em tramitação: 3.

- 4/2025 (id 49): Dispõe sobre o atendimento prioritário de agricultores familiares e pequenos produtores rurais do município de Campo do Tenente no âmbito do programa “Porteira Adentro” e dá outras providências. Situação: Em tramitacao. Fonte: https://sapl.campodotenente.pr.leg.br/materia/49
- 5/2025 (id 50): DISPÕE SOBRE A INSTITUIÇÃO DO PROCEDIMENTO OPERACIONAL PADRÃO (POP) NO ÂMBITO DA ADMINISTRAÇÃO PÚBLICA MUNICIPAL, INCLUINDO A CÂMARA MUNICIPAL, E DÁ OUTRAS PROVIDÊNCIAS. Situação: Em tramitacao. Fonte: https://sapl.campodotenente.pr.leg.br/materia/50
- 13/2025 (id 37): INSTITUI O SELO "EMPRESA AMIGA DA JUVENTUDE" Situação: Aprovado. Fonte: https://sapl.campodotenente.pr.leg.br/materia/37
- 16/2025 (id 180): DISPÕE SOBRE A OBRIGATORIEDADE DA INCLUSÃO DE, NO MÍNIMO, UMA ATRAÇÃO DE CARÁTER RELIGIOSO NAS FESTIVIDADES MUNICIPAIS DE CAMPO DO TENENTE COM DURAÇÃO SUPERIOR A UM DIA, E DÁ OUTRAS PROVIDÊNCIAS Situação: Em tramitacao. Fonte: https://sapl.campodotenente.pr.leg.br/materia/180
- 17/2025 (id 211): DISPÕE SOBRE OS CRITÉRIOS PARA  A DENOMINAÇÃO DE PRÉDIOS E EQUIPAMENTOS PÚBLICOS MUNICIPAIS NO ÂMBITO DO MUNICÍPIO DE CAMPO DO TENENTE, E DÁ OUTRAS PROVIDÊNCIAS. Situação: Aprovado. Fonte: https://sapl.campodotenente.pr.leg.br/materia/211
- 18/2025 (id 216): Dispõe sobre a prática esportiva e recreativa de manobras com motocicletas, conhecida como “grau” ou “wheeling”, no âmbito do Município de Campo do Tenente, e dá outras providências. Situação: Aprovado. Fonte: https://sapl.campodotenente.pr.leg.br/materia/216

### Cleiton Costa

Projetos de lei do Legislativo: 2. Aprovados: 1. Rejeitados: 0. Em tramitação: 1.

- 6/2025 (id 13): Dispõe sobre a isenção por tempo determinado de imposto predial e territorial urbano – IPTU para novos loteamentos e condomínios, regularmente cadastrados na área urbana do município de Campo do Tenente e dá outras providências. Situação: Em tramitacao. Fonte: https://sapl.campodotenente.pr.leg.br/materia/13
- 14/2025 (id 151): DISPÕE ACERCA DA IMPLANTAÇÃO DE CÓDIGO QR EM TODAS AS PLACAS DE OBRAS PÚBLICAS MUNICIPAIS PARA LEITURA E FISCALIZAÇÃO ELETRÔNICA. Situação: Aprovado. Fonte: https://sapl.campodotenente.pr.leg.br/materia/151

### Kinho Lazarino

Projetos de lei do Legislativo: 4. Aprovados: 3. Rejeitados: 0. Em tramitação: 1.

- 1/2025 (id 47): Concede acréscimo sobre o valor do auxílio-alimentação dos servidores da Câmara Municipal de Campo do Tenente. Situação: Em tramitacao. Fonte: https://sapl.campodotenente.pr.leg.br/materia/47
- 7/2025 (id 193): DISPÕE SOBRE A DIVULGAÇÃO DE INFORMAÇÕES SOBRE OS SERVIÇOS DE SANEAMENTO BÁSICO E DO PROGRAMA PORTEIRA ADENTRO DO MUNICÍPIO NO SITE OFICIAL DA PREFEITURA DE CAMPO DO TENENTE - PR. Situação: Aprovado. Fonte: https://sapl.campodotenente.pr.leg.br/materia/193
- 8/2025 (id 27): Dispõe sobre o piso salarial ético instituído pela OAB-PR para o cargo de Advogado da Câmara Municipal de Campo do Tenente e dá outras providências. Situação: Aprovado. Fonte: https://sapl.campodotenente.pr.leg.br/materia/27
- 9/2025 (id 28): Dispõe sobre a possibilidade de alteração temporária da carga horária dos servidores da Câmara Municipal de Campo do Tenente, com ajuste proporcional da remuneração, mediante concordância expressa, e dá outras providências. Situação: Aprovado. Fonte: https://sapl.campodotenente.pr.leg.br/materia/28

### Rafael Ventura

Projetos de lei do Legislativo: 10. Aprovados: 6. Rejeitados: 0. Em tramitação: 4.

- 1/2025 (id 47): Concede acréscimo sobre o valor do auxílio-alimentação dos servidores da Câmara Municipal de Campo do Tenente. Situação: Em tramitacao. Fonte: https://sapl.campodotenente.pr.leg.br/materia/47
- 2/2025 (id 55): Dispõe sobre a redução do uso de papel no âmbito da Câmara Municipal de Campo do Tenente e dá outras providências. Situação: Em tramitacao. Fonte: https://sapl.campodotenente.pr.leg.br/materia/55
- 3/2025 (id 56): Dispõe sobre a criação do Orçamento Participativo Digital no município de Campo do Tenente e dá outras providências. Situação: Em tramitacao. Fonte: https://sapl.campodotenente.pr.leg.br/materia/56
- 5/2025 (id 50): DISPÕE SOBRE A INSTITUIÇÃO DO PROCEDIMENTO OPERACIONAL PADRÃO (POP) NO ÂMBITO DA ADMINISTRAÇÃO PÚBLICA MUNICIPAL, INCLUINDO A CÂMARA MUNICIPAL, E DÁ OUTRAS PROVIDÊNCIAS. Situação: Em tramitacao. Fonte: https://sapl.campodotenente.pr.leg.br/materia/50
- 8/2025 (id 27): Dispõe sobre o piso salarial ético instituído pela OAB-PR para o cargo de Advogado da Câmara Municipal de Campo do Tenente e dá outras providências. Situação: Aprovado. Fonte: https://sapl.campodotenente.pr.leg.br/materia/27
- 9/2025 (id 28): Dispõe sobre a possibilidade de alteração temporária da carga horária dos servidores da Câmara Municipal de Campo do Tenente, com ajuste proporcional da remuneração, mediante concordância expressa, e dá outras providências. Situação: Aprovado. Fonte: https://sapl.campodotenente.pr.leg.br/materia/28
- 10/2025 (id 26): INSTITUI O TÍTULO DE "EMBAIXADOR(A) HONORÁRIO(A) DE CAMPO DO TENENTE" E DÁ OUTRAS PROVIDÊNCIAS. Situação: Aprovado. Fonte: https://sapl.campodotenente.pr.leg.br/materia/26
- 11/2025 (id 31): REGULAMENTA A LEI FEDERAL Nº 12.527/2011- LEI DE ACESSO À INFORMAÇÃO - LAI, NO ÂMBITO DA CÂMARA MUNICIPAL DE CAMPO DO TENENTE – PR. Situação: Aprovado. Fonte: https://sapl.campodotenente.pr.leg.br/materia/31
- 12/2025 (id 25): INSTITUI O PARLAMENTO MUNICIPAL DA PESSOA COM DEFICIÊNCIA NO MUNICÍPIO DE CAMPO DO TENENTE, DESTINADO A ESTUDANTES DA APAE, COM FINS EDUCATIVOS E DE CIDADANIA, E DÁ OUTRAS PROVIDÊNCIAS. Situação: Aprovado. Fonte: https://sapl.campodotenente.pr.leg.br/materia/25
- 15/2025 (id 163): DISPÕE SOBRE A RESERVA DE VAGAS PARA NEGROS E PARDOS EM CONCURSOS PÚBLICOS E PROCESSOS SELETIVOS SIMPLIFICADOSNO ÂMBITO DA CÂMARA MUNICIPAL DE CAMPO DO TENENTE E DÁ OUTRAS PROVIDÊNCIAS. Situação: Aprovado. Fonte: https://sapl.campodotenente.pr.leg.br/materia/163

### Gustavo Vizentin

Projetos de lei do Legislativo: 4. Aprovados: 3. Rejeitados: 0. Em tramitação: 1.

- 1/2025 (id 47): Concede acréscimo sobre o valor do auxílio-alimentação dos servidores da Câmara Municipal de Campo do Tenente. Situação: Em tramitacao. Fonte: https://sapl.campodotenente.pr.leg.br/materia/47
- 7/2025 (id 193): DISPÕE SOBRE A DIVULGAÇÃO DE INFORMAÇÕES SOBRE OS SERVIÇOS DE SANEAMENTO BÁSICO E DO PROGRAMA PORTEIRA ADENTRO DO MUNICÍPIO NO SITE OFICIAL DA PREFEITURA DE CAMPO DO TENENTE - PR. Situação: Aprovado. Fonte: https://sapl.campodotenente.pr.leg.br/materia/193
- 8/2025 (id 27): Dispõe sobre o piso salarial ético instituído pela OAB-PR para o cargo de Advogado da Câmara Municipal de Campo do Tenente e dá outras providências. Situação: Aprovado. Fonte: https://sapl.campodotenente.pr.leg.br/materia/27
- 9/2025 (id 28): Dispõe sobre a possibilidade de alteração temporária da carga horária dos servidores da Câmara Municipal de Campo do Tenente, com ajuste proporcional da remuneração, mediante concordância expressa, e dá outras providências. Situação: Aprovado. Fonte: https://sapl.campodotenente.pr.leg.br/materia/28

### Josemar Veiga

Projetos de lei do Legislativo: 3. Aprovados: 2. Rejeitados: 0. Em tramitação: 1.

- 1/2025 (id 47): Concede acréscimo sobre o valor do auxílio-alimentação dos servidores da Câmara Municipal de Campo do Tenente. Situação: Em tramitacao. Fonte: https://sapl.campodotenente.pr.leg.br/materia/47
- 8/2025 (id 27): Dispõe sobre o piso salarial ético instituído pela OAB-PR para o cargo de Advogado da Câmara Municipal de Campo do Tenente e dá outras providências. Situação: Aprovado. Fonte: https://sapl.campodotenente.pr.leg.br/materia/27
- 9/2025 (id 28): Dispõe sobre a possibilidade de alteração temporária da carga horária dos servidores da Câmara Municipal de Campo do Tenente, com ajuste proporcional da remuneração, mediante concordância expressa, e dá outras providências. Situação: Aprovado. Fonte: https://sapl.campodotenente.pr.leg.br/materia/28

### Beto Maurer

Projetos de lei do Legislativo: 0. Aprovados: 0. Rejeitados: 0. Em tramitação: 0.

Nenhum projeto de lei do Legislativo com esta autoria neste ano.

### Gilmar Barbosa

Projetos de lei do Legislativo: 0. Aprovados: 0. Rejeitados: 0. Em tramitação: 0.

Nenhum projeto de lei do Legislativo com esta autoria neste ano.

## Totais

- Sessões ordinárias no SAPL: 32
- Vereadores com mandato no ano: 9
- Presenças dentro do mandato: 279
- Faltas com justificativa: 2
- Faltas sem justificativa: 7
- Afastamentos que não contam como falta: 0
- Votações: 115
- Votações com voto individual: 19
- Votações sem voto individual: 96

## Como repetir

Na pasta do projeto, rode:

    python dados/tratados/gerar_atuacao_vereadores.py

O programa lê os brutos de novo e reescreve o JSON, o CSV e este relatório do ano. Não edite esses arquivos na mão.
