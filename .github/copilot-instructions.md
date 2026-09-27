# GitHub Copilot Instructions

Este repositório segue regras rígidas de governança, segurança e qualidade de dados públicas estabelecidas em `PROCESSO_DESENVOLVIMENTO_E_GOVERNANCA.md`.

## Diretrizes Gerais
1. O mantenedor é o aprovador único. Toda comunicacao deve ser estritamente sem caracteres de travessao (em dash ou en dash) e com estimativas realistas em minutos.
2. Todo desenvolvimento ocorre na branch `desenvolvimento`. A branch `main` é protegida e reservada exclusivamente para produção estável.
3. Não inclua segredos, tokens ou dados sensíveis (e-mails pessoais, caminhos locais absolutos do sistema operacional).
4. Todo dado exibido no painel deve ter origem verificável no SAPL de Campo Largo.
5. Sempre sanitize entradas com `esc()` e mantenha a Content Security Policy estrita no `index.html`.
6. Valide alterações executando a suíte de sanidade (`coletor/testes_sanidade.py` e `tests/test_sanidade_dados.py`).
