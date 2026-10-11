# funcoesnotificacoes — o que o usuário precisa saber, em três níveis

> **App-fundação**, como o [catalogo](catalogo.md) e o [funcoesimpexp](funcoesimpexp.md): não se vende, não
> tem entitlement próprio, e nenhum módulo depende dele para existir. É a **única porta** pela qual o
> sistema fala com o usuário *fora da tela em que ele está*. Cada módulo declara **o que aconteceu e o
> que fazer**; o motor cuida de endereçar, classificar, agrupar e apagar.
>
> A infraestrutura base já é do [nucleo](nucleo.md) (`Notificacao`, o sino do topbar, `criar_notificacao`).
> Este documento fixa o **desenho para o usuário**: o que merece aviso, em qual dos três níveis, e a régua
> que todo produtor obedece.

## 1. A ideia: o usuário só aprende três cores

Notificação demais ensina a ignorar o sino — e o dia em que a importante chega, ela passa junto com as outras.
Por isso o usuário aprende **uma pergunta e três respostas**:

> *"Eu preciso fazer alguma coisa?"*

| Nível | Cor | Pergunta que responde | O que o usuário faz | Some quando |
|---|---|---|---|---|
| **1 · Saber** | cinza (`--ink-3`) | "Aconteceu algo que me diz respeito." | Nada. Lê se quiser. | Ao abrir, ou em 14 dias |
| **2 · Decidir** | âmbar (`--accent`) | "Há uma decisão minha esperando, e ela tem dono e prazo." | Abre, decide (aprova, recusa, corrige). | Quando **alguém** decide — não só ele |
| **3 · Agir já** | vermelho (`--bad`) | "Dinheiro, prazo legal ou segurança estão em risco **agora**." | Resolve a causa, hoje. | Só quando a **causa** some — nunca por "marcar como lida" |

Três níveis e nenhum a mais: com quatro, o usuário passa a perguntar "qual a diferença entre este e aquele" em
vez de olhar o aviso. A régua de corte entre os níveis é sempre a mesma — **o que acontece se ele não abrir**:

- nada → nível 1;
- uma coisa fica parada esperando ele → nível 2;
- uma coisa errada acontece, ou um dano se confirma → nível 3.

## 2. O que o usuário vê

**O sino** (topbar) mostra **um número só: os níveis 2 e 3 em aberto** — o que depende dele. O nível 1 não entra na
contagem; ele existe na lista, mas nunca acende o sino. Ponto vermelho no sino = há nível 3.

**A lista** abre em três faixas, na ordem de quem tem de ser olhado primeiro:

```
 Agir já (2)        ← vermelho, fixo no topo, não tem "marcar como lida"
 Decidir (5)        ← âmbar, ordenado por prazo
 Saber (12)         ← cinza, recentes; "marcar todas como lidas" vale só aqui
```

**Cada linha responde três coisas, nesta ordem** — e é só isso que o usuário precisa ler:

1. **O que aconteceu** — uma frase, com o número que importa (*"Medição 1 do contrato 01 já estava paga e foi
   retificada"*);
2. **O que fazer** — um verbo (*"Conferir no financeiro"*), que é também o botão;
3. **Onde** — o clique abre **a tela e o registro exatos**, não o módulo.

Aviso sem verbo é nível 1. Aviso que não leva ao registro está mal escrito.

## 3. Régua dos produtores

Regras para quem emite uma notificação — a declaração que viola a régua não entra:

1. **Nível é do fato, não do módulo.** O produtor declara o nível pela pergunta do §1; o motor recusa nível 3
   sem `destino` (não existe "agir já" sem lugar onde agir).
2. **Quem recebe é quem pode agir.** Nível 2 e 3 vão a quem tem a **permissão** do verbo
   (`erp.conta_pagar.baixar`, `pdca.medicao.atestar`…), nunca ao tenant inteiro. Nível 1 vai a quem o fato
   toca (autor, responsável, interessado).
3. **Uma notificação por fato, não por tentativa.** Chave de deduplicação `(tipo do fato, objeto)`: o mesmo
   título vencendo não gera um aviso por dia — gera um, que ganha o texto do dia.
4. **Nível 2 e 3 têm ciclo de vida, nível 1 não.** O produtor que abriu **fecha**: aprovou a medição, a
   notificação "aguarda seu atesto" some para os outros atestadores. Fechar é parte do contrato de abrir.
5. **Número com base** (convenção da [identidade visual](../identidade-visual.md)): "R$ 600 a mais" diz a
   quê; sem base, é ruído.
6. **Escalada, não repetição.** O nível 2 que passa do prazo **sobe** para o nível 3 — uma vez. Reenviar não é
   escalar.
7. **Sem texto de sistema.** Nada de ID de tarefa, nome de função ou "erro 500". O usuário lê o que o
   colega de obra diria.
8. **Todo teto vive no [`payment/planos.py`](../../payment/planos.py)** (tamanho da lista, dias de retenção do
   nível 1, prazo de escalada) — nenhum número desses mora no motor.

## 4. Exemplos, um por nível

| Nível | Fato | Linha que o usuário lê | Destino |
|---|---|---|---|
| 1 · Saber | Medição aprovada pela escada | *"Medição 3 do contrato 01 foi aprovada — R$ 12.400 líquidos."* | o boletim |
| 2 · Decidir | Medição aguardando atesto | *"Medição 4 espera seu atesto (nível 2 de 3) — R$ 8.900."* · **Atestar** | o boletim, no degrau dele |
| 3 · Agir já | Medição já paga foi retificada | *"Medição 1 já tinha R$ 2.600 pagos e foi retificada: o líquido corrigido é R$ 2.000 (R$ 600 pagos a mais)."* · **Conferir** | o título no Contas a pagar |

## 5. Onde cada módulo entra

O motor não conhece domínio: ele recebe `(nível, destinatários, texto, destino, chave)`. Quem produz, hoje e
por desenho:

| Origem | Nível 1 | Nível 2 | Nível 3 |
|---|---|---|---|
| [PDCA](modulopdca.md) | medição / aditivo aprovado | atesto pendente, cronograma a revisar | medição paga retificada |
| [ERP](moduloerp.md) | baixa conciliada | título vencendo, baixa a revisar | título vencido, baixa em excesso |
| [Calendário](modulocalendar.md) | lembrete de evento | prazo do dia | — |
| [SCM](moduloscm.md) | pedido recebido | cotação a decidir | pedido atrasado travando serviço |
| [CRM](modulocrm.md) | lead novo | tarefa a vencer | — |

## 6. Fronteiras

- **Não é e-mail nem WhatsApp.** Canal externo é uma *entrega* do mesmo aviso, escolhida pelo usuário e
  **só para o nível 3** por padrão; o aviso nasce uma vez e o canal é acessório
  ([funcoeswhatsapp](funcoeswhatsapp.md)).
- **Não é a fila de aprovação.** A [escada do `nucleo`](nucleo.md) é o dono da decisão; a notificação só
  **chama** quem decide e **some** quando a escada fecha.
- **Não é auditoria.** O que aconteceu fica no log de auditoria para sempre; a notificação é efêmera por
  natureza.
- **Não é mural.** Comunicado geral da empresa é conteúdo, não aviso — outra função, outro desenho.

## 7. O que o usuário configura

Pouco, de propósito: **o canal do nível 3** (só sino, sino + e-mail, sino + WhatsApp) e **silenciar o nível 1
por módulo**. O nível 2 não se silencia — é decisão que alguém está esperando — e o nível 3 muito menos.
