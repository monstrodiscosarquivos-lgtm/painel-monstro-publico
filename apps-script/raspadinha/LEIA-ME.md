# Raspadinha · sorteio (D-070)

Apps Script na conta Gmail da Monstro que sorteia o prêmio na hora em que a pessoa raspa e cria o cupom único na Nuvemshop.
Chamado pela página pública (`raspadinha_pagina/index.html`, no GitHub Pages). Guia completo: `docs/RASPADINHA.md`.

- Implantar como app da Web: Executar como **Eu**; Quem pode acessar **Qualquer pessoa**.
- Propriedades do script: `NUVEMSHOP_STORE_ID`, `NUVEMSHOP_TOKEN`, `NUVEMSHOP_USER_AGENT` (os valores do `.env`).
- Rode `prepararRaspadinha()` uma vez: cria as abas `rasp_campanhas`, `rasp_jogadas`, `rasp_eventos` e a campanha `teste-raspadinha` em modo teste.
- `simularSorteio()` mostra 1.000 sorteios da campanha de teste sem criar nada.
