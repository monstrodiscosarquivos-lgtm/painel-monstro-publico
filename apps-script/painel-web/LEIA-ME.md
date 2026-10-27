# Painel Monstro como app da Web (D-069)

O mesmo Painel do Claude, aberto por um link com login Google e dois níveis de acesso.

| Arquivo | Onde vai |
|---|---|
| `Entrada.gs` | Projeto **Painel Monstro** no Apps Script (conta da Monstro) |
| `Painel.html` | Mesmo projeto, arquivo HTML chamado `Painel` |
| `Cofre.gs` | Projeto **Painel Monstro · cofre** (conta da Monstro), com o serviço Google Sheets API |
| `painel-monstro.html` | Fonte do Painel (é o artifact do Claude). Não vai para o Apps Script |
| `montar_painel_web.py` | Gera `Painel.html` a partir da fonte: `python montar_painel_web.py painel-monstro.html Painel.html` |

Como funciona: a ENTRADA roda com a conta de quem abre, só para saber o email. Ela pede os dados ao COFRE, que roda com a conta da Monstro, confere a aba **Acessos** (email, nome, nivel) e devolve só o que o nível permite. Ninguém da equipe recebe acesso à planilha.

- **especial**: vê e altera tudo.
- **comum**: vê e altera tudo, menos a Comissão.
- Toda gravação fica na aba **acessos_log**.

Sempre que o Painel do Claude mudar, gerar o `Painel.html` de novo e colar no projeto da entrada (Implantar > Gerenciar implantações > editar > Nova versão).
