# Assets locais do painel

## posthog-1.435.8.js

Cópia local do bundle PostHog (versão 1.435.8), servida pelo mesmo domínio do site para respeitar a CSP.

SHA-256: `f55972f4039038d7643622199b3b989b8bc3b052d12020dd8bbfdefd8bb44b08`

Origem no pacote de implementação: `codigo/posthog-array-1.435.8.js`.

## posthog-config.js

Cópia local do `config.js` remoto do projeto (chave pública no `config_cidade.json`), servida em `script-src 'self'` para o SDK não depender de script externo em `eu-assets.i.posthog.com`. A configuração remota continua acessível via `connect-src` para `https://eu-assets.i.posthog.com`.
