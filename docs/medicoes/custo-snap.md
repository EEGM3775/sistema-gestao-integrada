# Custo do índice de snap — o número que define o teto do plano

> Passada de **15/08/2026** (a segunda do dia — a primeira está corrigida na §5), pelo
> [medir_snap.py](../../ferramentas/medicao/medir_snap.py), sobre os DWGs do volume de mídia. Caminho de
> produção: `dwg2dxf` → `MotorDxf` → `Recorder` → `indice_de_snap`, com recorte por grupo igual ao do
> `_folha`. **Teto de medição alto de propósito** (50 milhões): o objetivo é saber o que a prancha
> custa de verdade, não confirmar um teto.

## 1. O resultado

| Grandeza | Mediana | p90 | Máximo |
| --- | ---: | ---: | ---: |
| Pontos indexados (maior folha) | 98.252 | 9.169.981 | **9.388.429** |
| Sidecar que o navegador baixaria | 934 KB | 87,7 MB | **126,5 MB** |
| Pico de RAM do índice | 16 MB | 1.360 MB | **2.048 MB** |
| Relógio do índice | 1,5 s | 178 s | **321 s** |

Pico de `VmHWM` do processo: **3.072 MB**. 13 dos 15 mediram; as 2 falhas são anteriores ao índice
(`DXFStructureError` do intermediário do `dwg2dxf` e o arquivo de 64,9 MB estourando o orçamento de
memória do próprio `dwg2dxf`).

Constantes derivadas, estáveis na amostra: **~10,9 bytes por ponto** de banda e **~0,23 KB de RAM por
ponto** no pico. São elas que convertem qualquer teto em custo previsto.

**A cauda é o dado que importa, e ela é brutal.** A mediana é confortável; o p90 é 93× a mediana. Um
único desenho do acervo (`HS-UFBACALMAS_Cob.dwg`, 0,77 MB em disco) rende 9,1 milhões de pontos.

## 2. Tamanho de arquivo não prevê custo — e isso decide a unidade do teto

| Arquivo | Tamanho | Pontos |
| --- | ---: | ---: |
| `HS-UFBACALMAS_Cob.dwg` | **0,77 MB** | **9.169.988** |
| `fundações_3.4.dwg` | 0,18 MB | 464.268 |
| `Poligonal.dwg` | **6,36 MB** | **466** |

Oito vezes menor em disco, vinte mil vezes maior em custo. Um teto em megabytes cobraria caro do
levantamento topográfico, que é barato, e liberaria de graça a planta que quebra o worker. A unidade
do teto é **ponto indexado**, e só ela.

## 3. Em produção, o teto protege — mas só até onde ele é conferido

Os números acima são **sem teto**. Com o teto do plano (600.000 no Profissional), a extração para ao
cruzá-lo: ~6,5 MB de sidecar e ~140 MB de RAM, muito abaixo da cauda medida.

**O limite conhecido disso** é que o teto é conferido **entre registros**, não entre pontos. Um único
registro — uma polilinha longa, uma hachura densa — pode somar milhões de pontos antes da próxima
conferência. No acervo normal o excesso medido ficou entre 98 e 13.186 pontos (2,2%); num desenho da
cauda ele pode ser muito maior. Está aberto em [pendencias.md](../pendencias.md).

## 4. Onde o custo mora

O censo por tipo é estável: **~48% extremidade, ~47% meio**, e o resto (centro, quadrante, interseção)
soma abaixo de 5%. O custo é a densidade de traço do desenho — não os tipos exóticos de snap.
Interseção pré-calculada, que era o risco de explodir, ficou entre 0,03% e 2,8% dos pontos: a varredura
em grade segurou.

## 5. A primeira passada estava contaminada — e como

A passada anterior deste mesmo dia publicou mediana 65.446 e máximo 473.221, com p90 de 464.268. Os
números eram **menores que a verdade em dois sentidos independentes**, e ambos vieram à tona só quando
o dono relatou que a mira do snap caía fora da linha:

**1. O índice contava geometria que não está na folha.** Registros cuja envolvente o `_caixas` descarta
não são desenhados pelo SVG, mas o extrator os colhia. Na prancha `001` isso era **99,88% do índice**
(516.587 → 627 pontos depois do filtro). O relato inteiro está na
[planta do módulo §14.9](../modulos/moduloprancheta.md). Nos demais arquivos da amostra o efeito foi
pequeno — o fantasma é propriedade do desenho, não do motor.

**2. A amostra anterior media 11 de 15; esta mede 13.** Os dois arquivos que passaram a converter são
justamente os da cauda. Uma amostra que perde os casos caros publica uma cauda que não existe — e foi
sobre essa cauda inexistente que os tetos de plano foram propostos.

**A lição de método, que vale mais que os números:** um relatório que separa "medidos" de "tentados" é
o que torna esse tipo de viés visível. O `medir_snap.py` já imprimia `medidos 11/15`, e a linha passou
despercebida na leitura — o número que precisa saltar aos olhos é o que **não** entrou na conta.

## 6. Dois defeitos do próprio extrator, achados medindo

**RAM em objeto de interpretador.** A primeira implementação gastava 0,35 KB por ponto acumulando
tuplas Python e fundindo no fim. Com `array` e fusão na inserção o pico caiu para 0,23 KB/ponto, e o
`VmHWM` do processo de 981 para 507 MB naquela amostra.

**A varredura perdia o cruzamento que mais importa.** Para não percorrer a *caixa* de uma diagonal
(430 × 430 = 185 mil células, quando a linha toca ~860), a primeira versão registrava o segmento longo
só pelas duas pontas. O preço foi silencioso e pior: **dois eixos que atravessam a prancha nunca
dividiam célula**, então o cruzamento deles não existia — justamente o caso de quem mede de um eixo de
pilar a outro. Trocado por travessia exata (Amanatides & Woo), o custo passou a ser proporcional ao
comprimento e não à caixa.

## 7. Como reproduzir

```sh
docker exec sgi-worker-conversao python /tmp/medir_snap.py /app/media/prancheta \
  --amostra 14 --extensoes .dwg --saida /tmp/snap.json
```

A amostra é espalhada **por tamanho**, não sorteada: o teto é decidido pela cauda, e o sorteio uniforme
quase nunca a pega. Leia sempre a linha `medidos N/M` antes dos percentis.
