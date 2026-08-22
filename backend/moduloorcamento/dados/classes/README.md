# Dicionário de classes por fonte

Um arquivo por fonte — `sinapi.csv`, `orse.csv`, `sicro.csv`, `seinfra.csv`, `sedop.csv`,
`tcpo.csv` — traduzindo a **classe que a publicação escreve** para a **natureza do catálogo**.

```
classe;natureza
TRANSPORTES;material
ATIVIDADES AUXILIARES;servico
```

`#` comenta a linha. A comparação é **exata** sobre a forma normalizada (sem acento, sem
pontuação, caixa única): quem escreve aqui está olhando para a publicação, então não há por que
abrir a mão em cima disso — casar por prefixo faria uma linha escrita para `MATERIAL` capturar
`MATERIAL DE CONSUMO`.

Naturezas aceitas: `material` · `mao_de_obra` · `equipamento` · `encargos_complementares` ·
`servico` · `epi` · `ativo` · `composicao`.

## Por que arquivo, e não tabela

Quem decide isto é o **superuser** — a mesma pessoa que importa a base-mãe, uma vez por fonte e
não por tenant. A base-mãe é global e read-only: o que entra nela **todos os tenants enxergam**,
e traduzir uma classe é uma alavanca de preço para a plataforma inteira de uma vez (classe errada
em `H` vira mão de obra, que leva encargo social sobre custo que pode não ser salário). Em
arquivo, a decisão entra no diff, é revisável e viaja com a imagem. Em tabela, ninguém veria quem
mudou a natureza de uma classe inteira.

## Quando você precisa mexer aqui

Quando `importar_base_referencial` **recusar** a publicação. Ele para antes de gravar, lista as
classes que não soube traduzir com quantos insumos usam cada uma, e aponta para o arquivo desta
pasta. Declare as traduções e rode de novo — a resposta passa a valer para as publicações
seguintes da mesma fonte, então a pergunta não se repete todo mês.

A saída alternativa é `--aceitar-sem-classe`, que importa assumindo que esses insumos entrem pelo
plano B da unidade. É decisão consciente, não default.

## O que **não** vai aqui

Classe que a fonte publica declarando não ser natureza (`ESPECIAIS`, `TAXAS`) já é reconhecida em
`services.CLASSES_SEM_NATUREZA` — a resposta dela é "não classifico", e ela não vira alarme.

O vocabulário da SINAPI (`MATERIAL`, `MÃO DE OBRA`, `EQUIPAMENTO (AQUISIÇÃO)`, `ENCARGOS
COMPLEMENTARES`, `SERVIÇOS`) e as grafias gerais seguras (`MATERIAIS`, `LOCAÇÃO DE EQUIPAMENTO`)
estão embutidas em `services.PREFIXOS_DE_CLASSE`. Só entra aqui o que é **daquela fonte**.

Classificação de um **item específico** também não é aqui: isso é
`reclassificar_itens_catalogo --de-para`, que é por código e por tenant. Esta pasta é por classe e
vale para a plataforma.
