# Viabilidade econômica da conversão — o que custa servir, e o que o mercado cobra

> Estudo de **16/08/2026**, cruzando a bancada instrumentada
> ([`fila_com_dwg_real`](../../backend/nucleo/management/commands/fila_com_dwg_real.py)) com preço de
> infraestrutura, de mercado e do concorrente direto. Câmbio do dia: **EUR 6,04 · USD 5,16**.
> Versão navegável da bancada que o alimenta:
> [A Fila com DWG Real](https://claude.ai/code/artifact/9788a6eb-3244-4d47-9601-56be6268532f).

## 1. A pergunta

Se converter DWG custa CPU e RAM de verdade — e a medição mostrou que custa —, o módulo Prancheta se
paga? E o preço praticado é atraente contra o que o mercado cobra pela mesma capacidade?

## 2. O custo de uma cadeira, e o de um segundo de CPU

A bancada mediu **100% de aproveitamento** (279,6 s de CPU para 278,4 s de relógio): a conversão é
trabalho de CPU de uma linha só. Isso obriga **vCPU dedicada** — em vCPU compartilhada a cadeira anda
mais devagar e ainda sofre com o vizinho —, e é a linha de instância que mais encareceu.

| | |
| --- | ---: |
| Hetzner CCX13 — 2 vCPU dedicadas, 8 GB | €42,99/mês ≈ **R$ 260** |
| Comporta ~2 cadeiras (1 vCPU + 3 GB cada) | **R$ 130/cadeira/mês** |
| Uma cadeira entrega | 2.628.000 s de CPU/mês |
| **Custo do segundo de CPU** | **R$ 0,0000495** |

> As linhas de vCPU dedicada da Hetzner subiram **113%–176% em junho/2026** porque a DRAM subiu ~171%
> no ano. O preço acima já é o de depois do reajuste.

## 3. O que custa converter, aplicado aos arquivos medidos

| Trabalho | CPU | Custo |
| --- | ---: | ---: |
| Arquivo mediano do acervo | 6,6 s | **R$ 0,0003** |
| Arquivo pesado real (`04-MaxPlast`, 21,7 MB) | 68 s | **R$ 0,0034** |
| A bancada inteira (6 arquivos, 103 MB) | 279,6 s | **R$ 0,014** |
| Acervo de onboarding (159 arquivos, o E2E da PRA.5c) | 17 min – 2 h | **R$ 0,05 – R$ 0,37** |

**Subir o acervo inteiro de um cliente novo custa entre cinco e trinta e sete centavos de máquina.**
Contra planos de R$ 149 a R$ 1.199.

## 4. Contra o que o mercado cobra

**Por tradução.** A Autodesk cobrava 1,5 crédito por modelo Revit/Navisworks e **0,2 pelos demais
formatos** — a ~US$ 1 o crédito, **R$ 1,03 por DWG**. Em 2026 o Model Derivative subiu de preço e
atividades antes gratuitas passaram a ser cobradas, então esse número é **piso**, não teto.

    nós:      R$ 0,0034  (arquivo pesado, medido)
    Autodesk: R$ 1,03    (piso histórico, formato não-Revit)
    razão:    ~300×

**Por assento.** O que o mercado cobra só pelo visualizador:

| | Por usuário/ano |
| --- | ---: |
| Autodesk Construction Cloud | ~US$ 600 |
| Bluebeam Revu | US$ 260 – 590 |
| **SGI `profissional`** (R$ 449 ÷ 12 assentos) | **US$ 87** |
| **SGI `empresarial`** (R$ 1.199 ÷ 40 assentos) | **US$ 70** |

E a Prancheta é **um módulo entre muitos**, não o produto. O concorrente brasileiro direto — Obra
Prima — começa em **R$ 399/mês**, o mesmo patamar do nosso plano de R$ 449.

## 5. Onde o dinheiro realmente vai: armazenamento

| Plano | Quota total | Custo estimado | % da receita |
| --- | ---: | ---: | ---: |
| `essencial` R$ 149 | 10 GB | ~R$ 3 | 2% |
| `profissional` R$ 449 | 150 GB | ~R$ 45 | **10%** |
| `empresarial` R$ 1.199 | 800 GB | ~R$ 240 | **20%** |

A ~R$ 0,30/GB/mês, **estimado e não reverificado para 2026** (disco também subiu). E é a quota cheia,
que quase ninguém alcança.

Somada a infra fixa de produção (app + banco + workers + conversão), estimada em **R$ 700–1.100/mês**,
a plataforma **paga a própria infraestrutura com dois clientes de R$ 449** ou um de R$ 1.199.

## 6. As três coisas que podem quebrar isto

### 6.1 O `empresarial` é o único plano que pode inverter o sinal

Ele vende **200 conversões premium/mês**, e o motor premium é a Autodesk — custo que é dela, não
nosso:

| As 200 conversões são… | Custo/mês | Contra R$ 1.199 |
| --- | ---: | --- |
| DWG (0,2 crédito) | R$ 206 | 17% — sadio |
| Revit (1,5 crédito) | **R$ 1.548** | **negativo antes do armazenamento** |

Como a PRA.4 ainda não existe, dá tempo. Registrado como pendência.

### 6.2 O gargalo não é custo, é espera — e ela cai no pior momento

Uma cadeira. A bancada: 6 arquivos em 278 s; um acervo de 159 leva de 17 min a 2 h. Dois clientes
entrando no mesmo dia e o segundo espera. Isso acontece **no primeiro uso**, o momento de maior
churn. Resolve-se com R$ 130 por cadeira — daí a decisão do dono de a frota crescer com a demanda
(`planos.py` §5.4c) —, e depende também do eixo por custo que a fila ainda não tem.

### 6.3 O que precifica a máquina é RAM, e RAM é o insumo que mais inflaciona

Um arquivo comum sozinho leva o contêiner a **2.532 MB de 3.072**. É isso que obriga a instância cara,
e foi exatamente a DRAM que subiu 171% no ano. **A [PRA.1e](../roadmap.md) não é só projeto de
velocidade — é proteção de COGS**: ela tira o estágio que segura 85 MB de DXF em texto mais a
geometria expandida na memória.

## 7. O que este estudo NÃO responde

Unit economics não é viabilidade. Ficaram de fora — e é onde a maioria dos SaaS morre, não no COGS:

- **tamanho de mercado, custo de aquisição, churn e disposição a pagar** do construtor brasileiro;
- **paridade de funcionalidade** com Obra Prima e Sienge: sabemos o preço deles, não o que entregam;
- **o custo de suporte humano**, que em software de construção costuma passar o de infraestrutura.

O que este estudo afirma é o que foi medido: **o custo de servir é da ordem de 10–20% da receita, o
preço por assento está 3 a 7× abaixo do mercado de visualizador, e o único item capaz de virar o
sinal é o repasse da Autodesk no plano de cima.**

## Fontes

- [Hetzner — reajuste de junho/2026 em CPX e CCX](https://wz-it.com/en/blog/hetzner-price-increase-june-2026-cpx-ccx-alternatives/) ·
  [contexto do salto de preço de DRAM](https://byteiota.com/hetzner-june-2026-price-shock/)
- [Autodesk — custo por API do Model Derivative](https://aps.autodesk.com/blog/forge-pricing-explained-3-what-does-each-forge-api-cost) ·
  [evolução do modelo de negócio e reajuste de 2026](https://aps.autodesk.com/blog/aps-business-model-evolution)
- [Bluebeam — planos e preços](https://www.bluebeam.com/pricing/) ·
  [comparativo com o Autodesk Construction Cloud](https://costbench.com/software/construction-management/bluebeam-revu/)
- [Obra Prima — preço de entrada](https://gestaoobras1.com.br/software/1626.html)
