# Arquitetura

Este documento descreve a esteira de dados do **Em Pratos Limpos**, do
download bruto na API pública do SAPL até a publicação no painel.

## Visão geral da esteira

```
coletor (Python)  ->  dados/brutos/  ->  gerador de agregados  ->  validacao (sanidade)  ->  publicacao (GitHub Pages)
```

1. **Coletor Python** (`coletor/`)
   - `sondar.py`: exploração pontual da API pública do SAPL de Campo
     Largo (`https://sapl.campolargo.pr.leg.br`) para descobrir endpoints
     e formatos antes de automatizar a coleta.
   - `baixar_voto_presenca_ordinarias_2026.py`: coletor principal. Busca,
     sessão a sessão, os pacotes `registrovotacao`, `votoparlamentar`,
     `sessaoplenariapresenca`, `presencaordemdia` e `justificativaausencia`
     das sessões ordinárias de 2026. É incremental (não baixa de novo o
     que já existe em disco) e respeita um intervalo de 2,5s entre
     requisições para não sobrecarregar o servidor da Câmara.
   - Dependências fixadas em `coletor/requirements.txt` (ex.:
     `requests==2.32.3`) para builds reprodutíveis.

2. **Dados brutos** (`dados/brutos/`)
   - Resposta crua da API, em JSON/CSV, um arquivo por endpoint/sessão.
   - Nunca é editado manualmente; é sempre reproduzível a partir de uma
     nova execução do coletor.

3. **Gerador de agregados** (`dados/tratados/`)
   - `gerar_tabela_vereadores.py`: consolida a tabela única de vereadores
     (`vereadores.json`/`.csv`) usada como referência pelos demais
     scripts.
   - `gerar_temas_votacoes_2026.py`: classifica as matérias votadas por
     tema, a partir de regras de palavras-chave.
   - `gerar_atuacao_vereadores_2026.py`: script principal de consolidação.
     Lê apenas `dados/brutos/` e `vereadores.json`, nunca infere ou
     inventa voto, presença ou autoria, e produz:
     - `atuacao_vereadores_2026.json` / `.csv` — atuação consolidada por
       vereador (presença, votos, faltas).
     - `RELATORIO-ATUACAO-VEREADORES-2026.md` — relatório legível.
   - Execução determinística: rodar de novo com os mesmos dados brutos
     produz o mesmo resultado, exceto pelo timestamp de geração.

4. **Validação (testes de sanidade)** (`coletor/testes_sanidade.py`)
   - Roda antes de qualquer publicação, tanto localmente quanto na
     esteira do GitHub Actions.
   - Confere que os arquivos consolidados existem, são JSON/CSV válidos e
     batem com os totais oficiais esperados (26 sessões ordinárias, 100
     PLLs, 15 vereadores, contagem de registros de votação > 0).
   - Falha rápido (`exit 1`) se qualquer verificação não bater, impedindo
     que dados corrompidos ou truncados cheguem a `main`.

5. **Publicação** (`.github/workflows/atualizacao_semanal.yml` +
   GitHub Pages)
   - Roda semanalmente (terça e quarta às 21h BRT) e sob demanda.
   - Ordem: instalar dependências -> coletor -> gerador de agregados ->
     testes de sanidade -> (se houver mudança em `dados/`) empacotar
     backup de `dados/` como `.tar.gz` e publicar como artefato do
     workflow -> abrir Pull Request de um branch dedicado
     (`atualizacao-dados/<timestamp>`) para `main`, em vez de escrever
     direto na branch de produção.
   - Em caso de falha em qualquer etapa, um passo final (`if: failure()`)
     registra no log da execução em qual etapa a esteira quebrou.
   - Após o merge do Pull Request em `main`, o GitHub Pages publica o
     painel (`index.html`) lendo diretamente os arquivos consolidados em
     `dados/tratados/`.
