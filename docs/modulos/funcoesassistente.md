# funcoesassistente — o sistema explicando a si mesmo

> Peça de **frontend**, sem app Django e sem entitlement: vive no shell da aplicação e serve
> qualquer tela que queira ser explicada. Código em
> [`frontend/src/components/assistente/`](../../frontend/src/components/assistente/).
> Régua visual em [../frontend.md](../frontend.md) · índice em [README.md](README.md).

## 1. O que é

Uma chave na barra de cima que liga e desliga a ajuda da tela aberta. Ligada, um **cartão** no canto
mostra as poucas frases que tiram alguém do lugar; a tecla **`?`** abre o **painel de referência**
com todos os gestos e atalhos daquela tela, agrupados por assunto. Desligada, a tela fica limpa.

Não é tour de primeiro uso, não é tooltip e não é documentação externa. É a tela dizendo o que sabe
fazer, no momento em que a pessoa está olhando para ela.

## 2. Por que existe

A ORC.10 deu à planilha do Orçamento seleção múltipla, arrastar e soltar, `Alt`+setas, `Ctrl+Z`,
menu de contexto, composição editável e um painel de banco acoplado. Tudo funcionava e **nada se
anunciava**.

O dono do sistema olhou para o botão no fim de cada linha e perguntou para que servia. Depois foi
direto ao ponto:

> *"Eu não sabia desses comandos e botões, ninguém me avisou. Assim como o usuário não vai saber. E
> não é intuitivo."*

Se quem **construiu** o sistema precisa perguntar, nenhum cliente vai descobrir sozinho. Poder sem
pista de que existe não é recurso, é dívida — e cada fatia nova acrescenta mais capacidade que
ninguém encontra. O assistente é o pagamento dessa dívida, e a régua para não contraí-la de novo:
**tela que ganha gesto novo publica o gesto**.

Duas coisas mudaram junto com ele, e valem como regra geral:

- **Ícone genérico não ensina.** O `⋮` foi trocado por ícones que dizem o verbo (régua para medida,
  lixeira para excluir), porque um desenho que serve para qualquer coisa não anuncia nenhuma.
- **Ajuda não substitui affordance.** Os quatro verbos frequentes saíram de dentro do menu e viraram
  um clique na própria linha. O assistente conta o que sobrou, não o que deveria estar à vista.

## 3. Como uma tela participa

```tsx
import { useAjudaDaTela, type AjudaDaTela } from '@/components/assistente/contexto'

// Fora do componente: o objeto precisa ser ESTÁVEL. Recriado a cada render, a
// publicação entra em laço.
const AJUDA: AjudaDaTela = {
  tela: 'Planilha orçamentária',
  dicas: ['a frase que tira alguém do lugar', '…'],
  grupos: [{ titulo: 'Escolher linhas', itens: [{ gesto: 'Shift+clique', faz: 'marca a faixa' }] }],
}

function MinhaTela() {
  useAjudaDaTela(estáAberta ? AJUDA : null)   // publica enquanto montada, retira ao sair
}
```

Tela que não publica nada simplesmente não tem assistente, e o painel diz isso em vez de abrir
vazio. **Nenhuma tela é obrigada a participar** para continuar funcionando.

| Peça | Onde | O que é |
|---|---|---|
| `contexto.ts` | [components/assistente/contexto.ts](../../frontend/src/components/assistente/contexto.ts) | Tipos, contexto, `useAssistente`, `useAjudaDaTela` e a leitura/gravação da preferência. Sem JSX de propósito — ver §5 |
| `Assistente.tsx` | [components/assistente/Assistente.tsx](../../frontend/src/components/assistente/Assistente.tsx) | `AssistenteProvider` (estado + tecla `?`), o **cartão** e o **painel de referência** |
| `ChaveDoAssistente` | [layout/AppTopbar.tsx](../../frontend/src/components/layout/AppTopbar.tsx) | A lâmpada acesa/apagada, ao lado da Prancheta e do Calendário |
| montagem | [layout/AppShell.tsx](../../frontend/src/components/layout/AppShell.tsx) | O provider envolve o shell; o cartão flutua por cima |

## 4. Onde a chave mora, e por quê

Ao lado de **Mapas**, **Prancheta** e **Calendário**. Os três são *lentes*: não são lugares do ciclo
de trabalho, são coisas que acompanham a pessoa por todo o sistema e se consultam sem sair de onde se
está ([frontend.md](../frontend.md) §3.2). O assistente é da mesma família — com uma diferença que o
desenho respeita: os outros **navegam**, ele **não**. É uma chave, liga e desliga ali mesmo, com o
estado à vista.

O pedido do dono foi literal: *"pode ter um tutorial que se liga e desliga como o clip do antigo
Office, pode ficar ao lado de calendário e prancheta"*.

## 5. Decisões que não são detalhe

1. **Nasce ligado.** Quem nunca viu a tela é exatamente quem precisa da dica, e desligar é um clique.
   Nascer desligado deixaria o recurso invisível pelo mesmo motivo que ele existe para corrigir.
2. **A preferência vive no navegador** (`localStorage`, chave `sgi.assistente.ativo`), com `try` em
   volta: em janela anônima ou com dados de site bloqueados o acesso **lança**, e uma exceção ali
   derrubaria o shell inteiro por causa de uma preferência. Sem memória, o assistente funciona igual
   — só não lembra da escolha entre sessões.
3. **O cartão não é modal e não rouba o foco.** Quem está digitando quantidade não pode ser
   interrompido por uma caixa que pede clique.
4. **O cartão não fica colado no rodapé** (`bottom: 96`). A faixa de baixo é território das barras da
   própria página — totais, seleção em lote, aviso — e o cartão pousado ali cobria os botões delas.
   Ajuda que tapa o comando que está ensinando a usar é pior que ajuda nenhuma. Quem achou foi o
   roteiro de navegador, tentando clicar em *Limpar seleção* e batendo no assistente.
5. **O X do cartão desliga de vez**, e o texto diz isso. Um X que só fechasse desta vez faria a
   pessoa fechar o mesmo cartão todo dia.
6. **A tecla `?` não dispara dentro de campo de texto.** Lá ela é só um caractere que alguém está
   digitando.
7. **`contexto.ts` não tem JSX.** Misturar componente e hook no mesmo arquivo quebra o *fast refresh*
   do Vite (`react-refresh/only-export-components`), e o módulo já carrega essa dívida em `ui.tsx` e
   `graficos.tsx` — não valia acrescentar mais uma.
8. **A primeira dica responde a dúvida número um.** Na planilha, é onde ficam as ações da linha —
   porque foi a pergunta que o dono fez. Dica que responde a dúvida mais comum não pode ser a
   segunda.

## 6. Quem já publica

| Tela | Dicas | Grupos de referência |
|---|---|---|
| **Planilha orçamentária** ([OrcarPage](../../frontend/src/modules/orcamento/pages/OrcarPage.tsx)) | 5 | Digitar na grade · Escolher linhas · Organizar a EAP · Agir sobre várias · Ações de uma linha · Composição do serviço · Desfazer, procurar e trazer preço |

As demais telas do sistema ainda não publicam. O caminho está aberto e custa um objeto por tela.

## 7. Fronteira — o que ele **não** é

- **Não é onboarding com passos.** Balão que aponta e pede "próximo" ensina uma vez e atrapalha
  sempre; o assistente fica disponível e calado.
- **Não é substituto de rótulo.** Botão que precisa de dica para ser entendido é botão mal
  desenhado. Quando a resposta certa for mudar o ícone ou escrever o nome, a resposta é essa — o
  `⋮` virou ícones exatamente por isso.
- **Não guarda conteúdo de negócio.** Nada de regra de cálculo, de plano ou de permissão. Ele
  descreve **gestos de tela**; o que o sistema faz está nas plantas dos módulos.
- **Não fala com o servidor.** Nenhuma rota, nenhum model, nenhuma migration. É estado de navegador.

## 8. Como se prova

[testes/e2e/orc10_planilha_browser_test.py](../../testes/e2e/orc10_planilha_browser_test.py), no
stack vivo pelo gateway: o cartão aparece ligado por padrão e a primeira dica diz onde estão as ações
da linha; a tecla `?` abre a referência com as seções certas; `Esc` fecha; e a chave da barra desliga
o cartão e o traz de volta.
