# Em Pratos Limpos

Painel cívico e aberto sobre a atuação legislativa da Câmara Municipal de Campo Largo (PR).

Acesse o painel online: **https://empratoslimposcl.github.io/em-pratos-limpos/**

---

## Proposta

O projeto **Em Pratos Limpos** tem como objetivo apresentar de forma clara, acessível e 100% factual o que a Câmara Municipal vota e como cada vereador votou em plenário.

* **Fonte oficial**: Todos os dados exibidos são públicos e extraídos diretamente do Sistema de Apoio ao Processo Legislativo (SAPL) da Câmara Municipal de Campo Largo.
* **Imparcialidade total**: Sem notas, sem rankings, sem juízos de valor e sem qualquer direcionamento político. O painel apenas organiza os registros oficiais para consulta do cidadão.
* **Transparência**: Cada votação e matéria apresentada possui link direto para a página oficial correspondente no portal da Câmara.

---

## Estrutura do Projeto

* `index.html`: Dashboard completa para acesso via navegador em dispositivos móveis e computadores.
* `coletor/`: Scripts em Python para consulta automatizada e download dos registros públicos do SAPL.
* `dados/brutos/`: Arquivos JSON originais obtidos das consultas à API pública da Câmara.
* `dados/tratados/`: Tabelas consolidadas com a apuração das presenças, votações e matérias.
* `.github/workflows/`: Rotina de automação para atualização periódica dos dados.

---

## Atualização Automática

O repositório conta com esteira automatizada via GitHub Actions:
* Execução programada às terças-feiras e quartas-feiras às 21h (horário de Brasília).
* Coleta automática de novas sessões ordinárias e consolidação dos votos no painel.

---

## Licença

Projeto de dados abertos e interesse cívico. Código e dados disponibilizados publicamente sob licença MIT.
