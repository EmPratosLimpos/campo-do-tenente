# Em Pratos Limpos: Câmara Municipal de Campo do Tenente (PR)

Painel cívico, aberto e gratuito que mostra, a partir dos registros oficiais, o que a Câmara Municipal de Campo do Tenente votou, quem estava presente em cada sessão e como cada vereador votou quando o voto individual foi registrado.

**Endereço do painel (em construção):** https://empratoslimpos.github.io/campo-do-tenente/

O painel ainda não publicou nenhum dado. Os números finais só vão aparecer depois da coleta completa, da conferência automática e da aprovação do mantenedor. Enquanto isso, o endereço acima pode estar vazio ou mostrar uma página provisória.

---

## O que é

O **Em Pratos Limpos** reúne em um só lugar informações que já são públicas, mas que ficam espalhadas pelo sistema da Câmara. O painel não cria informação nova: ele copia, organiza e aponta de volta para a fonte oficial, para que qualquer pessoa possa conferir.

O projeto não tem ligação com a Câmara, com a Prefeitura, com vereador, com partido ou com candidatura.

---

## De onde vêm os dados

Todos os dados vêm do **SAPL da Câmara Municipal de Campo do Tenente**:

https://sapl.campodotenente.pr.leg.br

O SAPL (Sistema de Apoio ao Processo Legislativo) é o sistema em que a própria Câmara registra suas sessões, votações, presenças e documentos. O painel lê esse sistema pela sua consulta pública, sem senha, e respeita uma pausa de 2,5 segundos entre um pedido e outro para não sobrecarregar o servidor da Câmara.

Se um dado não está no SAPL, ele não aparece no painel. O painel nunca completa, estima ou adivinha informação que falta.

---

## Palavras do dia a dia da Câmara

Alguns termos aparecem no painel. Em linguagem simples:

| Termo | O que quer dizer |
| :--- | :--- |
| Matéria | Qualquer documento que a Câmara analisa: projeto de lei, requerimento, indicação, moção, veto e outros. |
| Ementa | O resumo oficial de uma matéria, em uma ou duas frases, dizendo do que ela trata. |
| Tramitação | O caminho que a matéria percorre dentro da Câmara, da apresentação até a decisão final. |
| Ordem do dia | A lista de matérias que serão discutidas e votadas em uma sessão. |
| Sessão ordinária | A reunião regular dos vereadores, marcada no calendário da Câmara. |
| Sanção | Quando o prefeito concorda com um projeto aprovado pela Câmara e ele vira lei. |
| Veto | Quando o prefeito discorda de um projeto aprovado, no todo ou em parte. A Câmara depois vota se mantém ou derruba o veto. |

---

## O que o painel mostra

- As sessões ordinárias registradas no SAPL dentro do recorte descrito abaixo.
- As matérias votadas nessas sessões, com a ementa e um link para a página oficial de cada uma.
- O resultado oficial de cada votação, com os totais registrados pela Câmara.
- O voto de cada vereador, **somente** quando o SAPL registra esse voto individual.
- A presença de cada vereador em cada sessão e as faltas, separando as que têm justificativa registrada das que não têm.

Cada número na tela tem link ou referência para o registro oficial de onde saiu.

## O que o painel não mostra

- Opinião sobre o conteúdo das leis ou sobre a postura de qualquer vereador.
- Voto deduzido. Se o SAPL não registrou como cada vereador votou, o painel não preenche.
- Dado pessoal ou da vida privada. O painel trata apenas da atuação pública no exercício do mandato.

---

## Regras de imparcialidade

1. **Ausência não é voto.** Faltar a uma sessão não é votar sim, nem votar não, nem se abster. O painel usa rótulos separados:
   - **Falta com justificativa**: o vereador não estava presente e a Câmara registrou uma justificativa (por exemplo, licença médica, missão oficial ou força maior).
   - **Falta sem justificativa**: o vereador não estava presente e o SAPL não traz justificativa registrada para aquela sessão.
   - **Não votou**: a Câmara registrou no SAPL que o vereador não votou naquela votação. Não é falta e não é voto sim, voto não ou abstenção.
   - **Presidente que não votou**: o painel só usa este rótulo quando o SAPL mostra quem presidia a sessão (a mesa da sessão) e o registro dessa pessoa naquela votação é "Não votou". O painel nunca presume isso apenas pelo cargo.
   - A diferença: "Não votou" é um registro que existe no SAPL para aquele vereador; "voto individual não registrado no SAPL" (item 2) quer dizer que a votação não tem nenhum registro de voto individual.
2. **Voto individual não registrado no SAPL.** Em muitas votações a Câmara registrou apenas o resultado total (quantos votos sim, quantos não), sem anotar o voto de cada vereador. Nesses casos o painel escreve "voto individual não registrado no SAPL" e mostra apenas o total oficial. O painel **não** trata isso como votação unânime e **não** distribui os votos entre os vereadores.
3. **O painel reflete a fonte, não a corrige.** Se um dado oficial parecer estranho, o painel mostra o dado como está no SAPL e registra a observação. Correção de registro oficial cabe à Câmara.

---

## Recorte: o que está coberto

- **Legislatura 2025 a 2028** (a 16ª legislatura da Câmara, a atual), começando em 1º de janeiro de 2025.
- **Sessões ordinárias** de 2025 e 2026, e das próximas à medida que acontecerem.
- **As sessões ordinárias 1 a 16 de 2025 não existem no SAPL.** A primeira sessão ordinária de 2025 disponível no sistema é a 17ª, de 6 de maio de 2025. Por isso o painel começa nela. Se essas sessões forem cadastradas no SAPL no futuro, elas entram na coleta seguinte.

Os totais de sessões, votações e vereadores só serão publicados depois da coleta completa. Uma sondagem inicial feita em setembro de 2026 serviu apenas para conhecer o formato dos dados e não é o número oficial do painel.

---

## Como conferir se os dados não foram alterados

Cada arquivo de dados consolidado vem acompanhado de uma "impressão digital" chamada **hash SHA-256**: um código de 64 letras e números calculado a partir do conteúdo do arquivo. Se uma única letra do arquivo mudar, o código muda por completo.

Quando os dados forem publicados, os arquivos ficarão na pasta `dados/tratados/`, em pares:

- `atuacao_vereadores_<ano>.json`: os dados do ano.
- `atuacao_vereadores_<ano>.json.sha256`: o código de conferência desse arquivo.

Para conferir, baixe os dois arquivos e calcule o código do primeiro no seu computador:

```bash
# Linux ou macOS
sha256sum atuacao_vereadores_2026.json

# Windows (PowerShell)
Get-FileHash .\atuacao_vereadores_2026.json -Algorithm SHA256
```

Depois compare o resultado com o conteúdo do arquivo `.sha256`. Se os dois códigos forem iguais (o Windows mostra em letras maiúsculas, isso não faz diferença), o arquivo que você tem é exatamente o que o projeto publicou.

---

## Encontrou um erro?

Abra uma issue (um aviso público) no GitHub:

https://github.com/EmPratosLimpos/campo-do-tenente/issues

Para ajudar na conferência, informe:

- a sessão ou a matéria (número e data);
- o que o painel mostra;
- o que o SAPL mostra, com o link da página oficial.

É preciso ter uma conta gratuita no GitHub para abrir a issue. Não coloque telefone, endereço ou outro dado pessoal no texto, porque tudo o que é escrito ali fica público.

---

## Histórico de atualizações

Cada atualização dos dados e da tela fica registrada no arquivo [CHANGELOG.md](CHANGELOG.md), com a data, o que mudou e de onde veio.

---

## Como o projeto funciona por dentro

- `index.html`: o painel que abre no navegador, no celular ou no computador.
- `coletor/`: programas em Python que consultam o SAPL e baixam os registros públicos.
- `dados/brutos/`: as respostas do SAPL guardadas exatamente como chegaram.
- `dados/tratados/`: as tabelas organizadas a partir dos dados brutos, com o hash de conferência.
- `config_cidade.json`: endereço do SAPL e recorte da coleta.
- `ARCHITECTURE.md`: o caminho dos dados, da coleta até a tela.
- `PROCESSO_DESENVOLVIMENTO_E_GOVERNANCA.md`: as regras de trabalho, segurança e publicação.

Toda mudança de código passa por testes automáticos de conferência e só vai ao ar depois da aprovação do mantenedor. A atualização semanal de dados roda toda quarta feira as 03h de Brasilia: ela coleta so as sessões ordinárias novas mais a última já coletada, confere os dados e, quando todas as travas passam e só arquivos de dados mudaram, publica direto na main sem pedido de revisão. Se qualquer trava falhar ou se algum código mudar junto, nada é publicado e uma issue é aberta para o mantenedor ver. Cada execução tem teto de 400 pedidos ao SAPL, incluindo no mínimo 5 pedidos por sessão no alvo. Se o alvo não couber no teto, a execução para sem publicar e avisa que a primeira coleta completa precisa ser feita em partes, fora da rotina semanal. A main é a fonte do site: se o passo que leva o dado para desenvolvimento falhar, uma issue é aberta e a main segue válida.

---

## Contribuição

Quem clona o repositório para enviar alterações deve ativar os hooks versionados **uma vez** no clone local:

```bash
git config core.hooksPath .githooks
```

O hook `commit-msg` higieniza a mensagem de commit removendo assinaturas automáticas de ferramentas de IA (por exemplo trailers `Co-authored-by` de assistentes, linhas `Generated with ...` e `Claude-Session:`). Coautores humanos reais não são alterados.

O arquivo `.marcas-ia-desde` define a partir de qual ponto do histórico o CI verifica mensagens de commit. Commits anteriores a esse marco não são reavaliados.

Antes de abrir um pull request, rode localmente:

```bash
python coletor/testes_sanidade.py
python -m unittest discover -s tests
python scripts/verificar_regras.py
```

---

## Licença

Código e dados disponibilizados publicamente sob a licença MIT (arquivo `LICENSE`). Os registros de origem são públicos e produzidos pela Câmara Municipal de Campo do Tenente.
