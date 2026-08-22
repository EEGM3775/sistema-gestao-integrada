# ferramentas/ — onde a capacidade nasce antes de existir na tela

> **Não é uma gaveta paralela.** Cada ferramenta daqui resolve à mão um problema que **pertence a um
> módulo** do sistema — e existe justamente para resolvê-lo enquanto o módulo ainda não o resolve.
> Por isso toda ferramenta tem **endereço**: o módulo dono do problema, e o que muda quando a função
> atravessar para lá.

Ferramenta sem endereço vira peça perdida, e é assim que uma capacidade transversal acaba
reimplementada dentro do primeiro módulo que precisou dela. A tabela abaixo é o que impede isso.

## O que existe, e para onde vai

| Ferramenta | O que resolve | Módulo dono | Forma no produto |
|---|---|---|---|
| [marca_dagua/](marca_dagua/README.md) | Remove marca d'água de PDF **sem rasterizar** — o texto continua selecionável | [`modulodms`](../docs/modulos/modulos-planejados.md) — capacidade de PDF da plataforma | **Revisão nova, publicada** (não derivada, não passo de upload) |
| [medicao/](medicao/README.md) | Mede o motor livre sobre o acervo real — custo por arquivo, cobertura, precisão do snap | [`moduloprancheta`](../docs/modulos/moduloprancheta.md) — é dele o número que decide a fronteira entre planos | **Já atravessou em parte**: `manage.py custo_do_acervo` mede o que está no sistema; a bancada continua para o que ainda não subiu |

> **A `medicao/` veio de `infra/medicao/` em 16/08/2026.** Ela nunca foi infraestrutura: não sobe
> serviço nenhum, roda sobre uma pasta de DWGs e não grava nada. Estava em `infra/` por vizinhança
> com o Dockerfile de medição, e a pasta foi virando gaveta — que é o que esta aqui existe para não
> ser. O endereço dela é a Prancheta, e a parte que já atravessou (`custo_do_acervo`) está dita na
> tabela acima, como manda a regra do topo deste arquivo.

O endereço da `marca_dagua` está registrado em
[modulos-planejados.md](../docs/modulos/modulos-planejados.md): a capacidade de PDF do sistema
(marca d'água, carimbo, juntar/dividir, extrair página, girar) é do **DMS**, e as decisões de forma e
de licença já estão tomadas ali — falta a planta do módulo, não o rumo.

Enquanto isso, a ferramenta é a versão de bancada da mesma função: roda na máquina, sobre um arquivo
em mãos, para documentos sobre os quais a empresa tem direito — prancha própria carimbada
`RASCUNHO`/`PRELIMINAR` que foi aprovada depois, PDF de fornecedor com tarja de amostra sobre
material já contratado.

## O que a travessia exige

Uma ferramenta não "muda de pasta" para virar produto: o que atravessa é a **lógica**, e ela ganha
quatro coisas que na bancada não fazem sentido. Registrado aqui porque é o que separa "já está
pronto, é só mover" de trabalho real:

| Na bancada | No produto |
|---|---|
| Arquivo que o operador tem em mãos | `TenantScopedModel` + RLS — o arquivo é de um tenant, e só dele |
| Qualquer um que abra o `.exe` | `RequireModule` + papel; e a operação pode ser degrau de plano |
| Roda e pronto | Deixa rastro: quem, quando, sobre qual revisão, com qual estratégia |
| A dependência que resolveu mais rápido | A dependência que a **licença** do produto permite (abaixo) |

O motor da `marca_dagua` foi escrito para atravessar: a lógica é um módulo importável com funções
nomeadas (`remover_texto`, `remover_xobject`, …) e a interface só as chama — `marca_dagua_gui.py`
faz `import remove_marca_dagua as motor`. Uma task Celery chamaria as mesmas funções. **Interface e
motor separados é a convenção da pasta**, e é ela que torna a travessia um porte em vez de uma
reescrita.

## Licença — o pedágio da travessia, decidido antes de doer

O `pymupdf` que a `marca_dagua` usa é **AGPL-3.0**. Na bancada é aceitável: nada é distribuído e
nada é servido pela rede. Dentro do `backend/` seria regressão de licenciamento — o produto é SaaS
proprietário servido pela rede, o gatilho literal do §13.

Por isso a decisão já está tomada: **a capacidade de PDF do produto se apoia no `pikepdf`**
(MPL-2.0, sobre o QPDF/Apache-2.0), que também dá acesso a content stream, anotações e XObjects — as
cinco estratégias são portáveis. É a mesma política permissiva que a Prancheta seguiu ao escolher
`pypdfium2` ([motores/documento.py](../backend/moduloprancheta/motores/documento.py)).

Duas consequências práticas:

- **Não copie `import fitz` para dentro de módulo.** Muda o licenciamento do produto inteiro; é
  decisão jurídica disfarçada de conveniência.
- **O `.exe` embute o PyMuPDF.** Circular internamente, sim; entregá-lo a alguém de fora da empresa é
  *distribuir* software AGPL, e aí as obrigações de código-fonte valem sobre o conjunto.

## Anatomia de uma ferramenta nova

```
ferramentas/<nome>/
├── README.md          # o que resolve, uso, armadilhas, e o MÓDULO dono do problema
├── requirements.txt   # deps SÓ desta ferramenta (nunca no requirements.txt da raiz)
├── <motor>.py         # a lógica, em funções nomeadas — o que vai atravessar
├── <nome>_gui.py      # opcional: interface, importando o motor — o que NÃO atravessa
└── dist/              # artefato buildado — gitignored, nunca commitado
```

Três convenções, todas herdadas da `marca_dagua`:

1. **Motor antes de interface**, pelo motivo acima.
2. **Diagnosticar antes de agir.** Utilitário trabalha sobre arquivo alheio e imprevisível: o
   primeiro comando mostra o que existe, e só o segundo modifica. No produto esse mesmo diagnóstico
   vira o que o usuário vê antes de confirmar — a diferença entre operação confiável e mágica.
3. **Armadilhas no README.** O que falha em silêncio (fonte subsetada que não casa nada; bloco de
   texto que leva conteúdo real junto) vai escrito — quem porta a função meses depois é outra pessoa.

## Como a esteira trata a pasta

Registrado para que cada ausência seja escolha, e não esquecimento:

| Etapa | Comportamento | Por quê |
|---|---|---|
| **Imagens Docker** | Fora do contexto de build ([.dockerignore](../.dockerignore)) | Nada aqui roda em container — e o `pymupdf` AGPL não pode sequer chegar perto do contexto |
| **`pip-audit` do CI** | Não varre estes `requirements.txt` ([ci.yml](../.github/workflows/ci.yml)) | O gate protege o que é servido pela rede |
| **Trivy do CI** | **Varre** — o scan é do filesystem inteiro (`scan-ref: .`) | CVE fixável aqui pode reprovar o CI; atualize a versão, não silencie |
| **`dist/` e `build/`** | Gitignored na raiz | Binário de ~30 MB não entra em commit |
| **Venv** | Um por ferramenta, separado do `.venv` da raiz | O da raiz é dos dois serviços Django ([desenvolvimento.md](../docs/desenvolvimento.md)) |

## Rodar qualquer ferramenta

```bash
cd ferramentas/<nome>
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt      # Linux/WSL
.venv\Scripts\python -m pip install -r requirements.txt  # Windows
```

Use sempre `.venv/bin/python -m pip` — no WSL deste projeto o wrapper `bin/pip` costuma estar
quebrado (mesma armadilha de [desenvolvimento.md](../docs/desenvolvimento.md)). Interface Tkinter
exige `sudo apt install python3-tk` no Linux; no Windows o Tkinter já vem com o Python.
