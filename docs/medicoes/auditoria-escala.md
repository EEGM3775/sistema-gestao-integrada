# Auditoria da escala derivada — a régua que publicamos bate com o desenho?

> Passada **preventiva** de 15/08/2026, pelo [auditar_escala.py](../../ferramentas/medicao/auditar_escala.py),
> sobre os DWGs do volume de mídia. Ninguém relatou número errado: a pergunta é se a escala pode
> estar errada **em silêncio**, que é o modo de falha caro deste módulo.

## 1. Por que preventiva

Escala errada não parece defeito. Um fator de 3,28× (pé lido como metro) transforma uma fachada de
30 m em 98 m — número que cai dentro de qualquer janela de plausibilidade, não dispara alarme nenhum
e vira parede no lugar errado no canteiro. Diferente de uma prancha que não abre, este erro **é
invisível até custar dinheiro**.

## 2. Método: duas fontes independentes do mesmo fato

| Fonte | De onde sai |
| --- | --- |
| O que o **arquivo** declara | `$INSUNITS` + envolvente da geometria, lidos direto pelo `ezdxf` |
| O que **nós** publicamos | `escala_do_desenho()` sobre o SVG realmente emitido |

Divergência acima de **1%** é achado. A tolerância é folgada de propósito: cobre arredondamento de
emissão, e o menor engano de unidade fisicamente possível (polegada→centímetro) é de 2,54× — não há
erro real que se esconda abaixo de 1%.

## 3. Resultado

| | |
| --- | ---: |
| Conferidos | **16** |
| **Achados** | **0** |
| Desvio mediano | 4,8 × 10⁻⁵ |
| Desvio máximo | **5,85 × 10⁻⁴** (0,06%) |
| Sem régua | 9 |

Os 9 sem régua não são erro de escala: são `DXFStructureError` do intermediário do `dwg2dxf` e
modelspace vazio (a família do [D43](../historico-correcoes.md) e o caminho do paperspace do D44) —
defeitos anteriores à escala, e já conhecidos. Para eles a calibração humana segue sendo o caminho,
como a planta do módulo declara.

## 4. O que esta auditoria NÃO prova

Ela confere a **aplicação** da tabela `$INSUNITS`, não a veracidade do que o arquivo declara. Um
projetista que modela em metros e declara milímetro engana as duas fontes igualmente, e as duas
concordariam num valor errado. Esse caso é limite conhecido do método, e a resposta para ele é a
calibração por cota conhecida — que existe e continua sendo o caminho para quem desconfia da régua.

## 5. Um falso verde que a própria passada pegou

A primeira execução reportou "0 achados" com **0 de 25 conferidos**: o script lia `escala_valor`, que
é o nome da **coluna** (escrita depois por `pipeline._publicar_escala`), quando o motor devolve
`escala_largura_m`, o nome da **grandeza**. Todo arquivo caía em `None` e a auditoria passava sem ter
conferido nada.

Fica registrado porque é o modo de falha mais perigoso de uma auditoria: **verde por não ter
olhado**. Um relatório que separa "conferidos" de "auditados" — como o da §3 faz — é o que torna isso
visível na primeira leitura.

## 6. Como reproduzir

```sh
docker exec -w /tmp sgi-worker-conversao python auditar_escala.py /app/media/prancheta --amostra 25
```

Sai com código 1 se houver achado, para poder virar porta de CI.
