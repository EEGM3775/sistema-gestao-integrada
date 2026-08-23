# modulopdca — PDCA: planejar, executar, verificar, agir

> **Planta do módulo.** Descreve o desenho, não o status: o que existe, o que ele não faz e por quê.
> Status e faseamento em [../roadmap.md](../roadmap.md); achados abertos em
> [../pendencias.md](../pendencias.md).

## 1. O que é

O `modulopdca` é o **laço** da obra: planeja o que será executado, registra o que foi, mede o que foi
feito contra o que foi planejado e trata o desvio.

O nome não é decorativo. A ISO 9001:2015 cita o ciclo de Deming na cláusula 0.3.2 como a estrutura da
própria norma — **cláusulas 4–6 = Plan, 7–8 = Do, 9 = Check, 10 = Act** — e é essa a forma do módulo.
Mais do que isso: é a forma do **SGI inteiro**, que hoje tem o laço aberto.

| Letra | O que a plataforma já tem | O que falta |
|---|---|---|
| **Plan** | [`moduloorcamento`](moduloorcamento.md) é o plano de **custo**: EAP, composição, BDI, curva S | O plano de **tempo e execução** — atividade, precedência, ritmo, contrato |
| **Do** | [`modulosil`](modulosil.md) e [`moduloscm`](moduloscm.md) movem **recurso**; [`modulodiario`](modulodiario.md) registra o **dia** | O que foi **executado** — avanço da atividade, medição do contrato |
| **Check** | — | **Nada.** O avanço da obra é `EtapaObra.percentual_conclusao`, digitado à mão |
| **Act** | — | **Nada.** Não-conformidade, ação corretiva, replanejamento e aditivo não existem |

O módulo fecha as duas colunas vazias. Não é um produto de planejamento ao lado do sistema: é a
metade que faltava do sistema.

## 2. A prática do mercado (pesquisa)

### 2.1 As quatro escolas

| Escola | Referência | O que faz de essencial |
|---|---|---|
| **ERP de construtora** | Sienge | Contrato de empreiteiro → medição por item → aditivo. O aditivo **não deixa a quantidade final cair abaixo do já medido**, e o item aditado fica marcado nas medições. Notável: o Sienge **tirou o planejamento do ERP** e o pôs num produto separado (Prevision), integrando medição física ↔ financeira |
| **Planejamento puro** | Primavera P6, MS Project | CPM, precedências, calendários múltiplos, **linhas de base** (P6 ilimitadas, MSP uma só), nivelamento de recursos e EVM. O P6 mede valor agregado em **homem-hora e em custo separadamente**; o MSP só em custo — porque uma obra pode gastar dentro do previsto e estar perdendo em produtividade de equipe |
| **Lean / Last Planner** | LPS, linha de balanço | **PPC** (percentual da programação concluída — média ~54% em obra convencional, 80–85% com LPS bem aplicado), remoção de **restrições** antes de programar (*make-ready*) e a **causa do não-cumprido** realimentando o ciclo. A LOB planeja por **localização e ritmo**, não por duração |
| **Qualidade e campo** | Procore, Autodesk CC, SAP QM | Observações **tipificadas** (não-conformidade, segurança, boa prática, pré-punch), punch list, RFI. No SAP, a notificação de qualidade **não fecha** enquanto as ações corretivas não forem executadas *e* aprovadas (8D/CAPA) |

### 2.2 O que é obrigatório no Brasil

O **PBQP-H / SiAC** exige, para certificar: **FVS** (Ficha de Verificação de Serviço) — o checklist do
serviço, com possibilidade de **reprovar item** e registrar pendência — e o tratamento da
não-conformidade com **duas** respostas, ação corretiva imediata e ação preventiva. O nível A exige o
sistema de gestão da qualidade implantado; o B é a porta de entrada.

Isso não é diferencial: é requisito de quem quer vender para incorporadora certificada ou disputar
obra pública. Um módulo de obra sem FVS não atende a construtora que já é certificada.

### 2.3 O que o SGI tem e um software de planejamento puro não tem

O MS Project não sabe quanto custa a atividade. O P6 não sabe se o material chegou. O Prevision
precisa de integração para saber o que foi contratado. Aqui, **a régua, o recurso e o contrato moram
na mesma plataforma**:

- o **orçado por etapa** já sai pronto de [`planilha.orcado_por_etapa`](../../backend/moduloorcamento/planilha.py),
  na mesma chave `(obra, etapa)` que o SIL usa para o aplicado;
- o **aplicado** de material vem do SIL sem integração;
- o **comprometido** vem do SCM;
- o canteiro **já fala com a plataforma por WhatsApp** ([`modulodiario`](modulodiario.md));
- a **não-conformidade pode virar pino sobre o desenho**, porque a [Prancheta](moduloprancheta.md) já
  tem acervo, visualizador, marcação com âncora e exportação BCF.

Nenhum concorrente tem os cinco no mesmo lugar. É esse o argumento do módulo.

## 3. Fundação já pronta (o módulo não começa do zero)

| O que o PDCA precisa | Onde já existe |
|---|---|
| Régua de custo por etapa | `planilha.orcado_por_etapa` — orçamento **aprovado** é congelado |
| Insumo explodido e coeficiente da composição | `ItemOrcadoInsumo` — a base da produtividade prevista |
| Distribuição de custo no tempo | `ParcelaEtapa` + curva S |
| Aplicado de material por `(obra, etapa)` | [`modulosil`](modulosil.md) |
| Comprometido | [`moduloscm`](moduloscm.md) |
| Cadastro único de empreiteiro | `fornecedores.Fornecedor` — **sem campo de tipo**; a tipagem vive em `ProdutoServicoFornecedor`, N por fornecedor |
| Título a pagar | `moduloerp.ContaPagar`, no molde de `PedidoCompra.conta_pagar_ref` |
| Pessoa, cargo, equipe | `rh` |
| Feriado federal/estadual/municipal e recorrência RRULE | `modulocalendar` |
| Canal do canteiro | `modulodiario` (`origem = web` ou `whatsapp`), com IA lendo texto e foto |
| Marcação sobre o desenho, BCF | [`moduloprancheta`](moduloprancheta.md) |
| Âncora geográfica | `modulomaps.Local` (fundação sem entitlement) |
| Item de catálogo, inclusive EPI | `catalogo.Item` |
| Importação/exportação tabular | [`funcoesimpexp`](funcoesimpexp.md) |
| Fila de trabalho pesado | `nucleo.frota` |
| Entitlement `pdca` | já reservado em `backend/modulopdca/` (view de status com `RequireModule`) |

## 4. Modelos

Todo modelo herda `TenantScopedModel`, com **RLS fail-closed**. A convenção de linha sintética ×
analítica repete a do `ItemOrcado`, que já provou funcionar em árvore grande.

### 4.1 Estrutura — onde e quando

**`LocalObra`** — a hierarquia **construtiva**, recursiva: empreendimento → torre → pavimento →
unidade → ambiente; e, em obra linear, frente → trecho → estaca. Tem `maps_local` **opcional**
apontando `modulomaps.Local`: a torre tem coordenada, o ambiente não precisa. É o eixo vertical da
linha de balanço e o endereço da não-conformidade.

Nasce com **gerador em lote** por padrão repetitivo (torre A, pavimentos 1–20, quatro unidades por
andar) — criar 1.600 locais à mão é o que faz o recurso não ser usado.

**`CalendarioTrabalho`** — jornada e dias trabalhados, por obra ou por frente, **consumindo** os
feriados que o `modulocalendar` já tem. O calendário de feriado existe; o de trabalho não — e sem ele
a duração em dias úteis é chute.

### 4.2 Planejamento — a WBS própria

**`Cronograma`** — o plano da obra, **versionado** no mesmo padrão do orçamento: rascunho → vigente, e
replanejar cria a versão seguinte com motivo obrigatório, rebaixando a anterior. Toda versão anterior
continua legível: é a **linha de base**. O P6 vende "linhas de base ilimitadas" como diferencial sobre
o MS Project; aqui elas caem de graça do versionamento que o projeto já pratica.

**`Atividade`** — a WBS **própria do PDCA**, recursiva (sintético × analítico), com dois vínculos
**opcionais** que são o coração da integração:

- **`etapa` → `obras.EtapaObra`** — o mapeamento com a macro-fase que a obra já cadastrou. Opcional
  porque o cronograma real tem granularidade que a etapa não tem, e obrigatório seria forçar a
  construtora a redesenhar o cadastro dela para poder planejar.
- **`item_orcado` → `moduloorcamento.ItemOrcado`** — a régua de custo. Vinculada, a atividade sabe
  quanto vale o que executa, e o avanço vira dinheiro sem digitação.

Carrega ainda `local` (opcional), duração, datas previstas, calendário, `eh_marco` — o `Marco` da v01
é atividade de duração zero, não uma segunda tabela — e o **peso** com que pondera o pai: derivado do
orçado quando houver vínculo, informado quando não.

**`Precedencia`** — origem, destino, tipo (`FS`/`SS`/`FF`/`SF`) e *lag*. O CPM roda sobre isso e
devolve datas cedo/tarde, folga total e livre, e o **caminho crítico**.

**`Risco`** — o terceiro modelo que a v01 tinha, ampliado: categoria, probabilidade, impacto,
severidade derivada, mitigação, dono (`rh.Funcionario`) e atividade opcional.

### 4.3 Execução e verificação

**`ApontamentoAvanco`** — quem, quando, onde, quanto. **Append-only**: erro se corrige por apontamento
de sinal contrário, não por edição — o avanço é a base de dinheiro que sai, e histórico reescrito é
dinheiro sem rastro. Carrega `origem` (`web` / `whatsapp` / `app`) no mesmo idioma que o diário já
usa, e foto.

O avanço da atividade é **derivado** dos apontamentos; o do pai, ponderado pelos filhos.

**`Restricao`** — o *make-ready* do Last Planner: tipo (projeto, material, mão de obra, equipamento,
área, licença, decisão, clima), responsável, prazo e status. **Atividade com restrição aberta não
entra na programação** — é a regra que separa o LPS de uma lista de tarefas.

**`ProgramacaoSemanal`** / **`ItemProgramacao`** — o que a equipe **se comprometeu** a fazer na semana.
No fim do ciclo cada item é cumprido ou não; o não-cumprido exige **causa**, escolhida de um catálogo
(`CausaNaoCumprimento`, de fábrica e extensível por tenant). O **PPC** é a razão entre os dois, e o
ranking de causas é o que alimenta o "Act".

### 4.4 Contrato, medição, aditivo

**`ContratoObra`** — obra, `fornecedor` (o cadastro único, que já é neutro quanto a ser de material ou
de serviço), objeto, **regime** (preço unitário, preço global, administração), vigência, garantia e a
cláusula de **retenção** (percentual, natureza e condição de liberação). Carrega **`regime_publico`**
e, quando ligado, o **limite legal de acréscimo** — *selecionado pelo usuário, não imposto pelo
sistema* (§11.3).

**`ItemContrato`** — com `item_orcado` **opcional**: contratado contra a régua do orçamento aprovado.
Quantidade contratada e preço unitário. A trava que o mercado ensina: **medição acumulada não pode
exceder contratado + aditivos**.

**`AditivoContrato`** / **`ItemAditivo`** — acréscimo, supressão, prazo ou reajuste, com motivo e
aprovação própria. Duas regras vindas da prática: a quantidade final de um item **não pode ficar
abaixo do que já foi medido**, e o item aditado fica **marcado** nas medições seguintes. O efeito no
custo já existe do outro lado — `RevisaoOrcamento` do tipo `aditivo` — e o PDCA amarra o documento, o
saldo e o prazo a ele.

**`Medicao`** / **`ItemMedicao`** — o boletim do período. **Nasce do avanço**, não ao lado dele
(§11.4): o sistema propõe a quantidade a partir dos apontamentos do período, o gestor confere, ajusta
e só então submete. Bruto → retenção → **líquido**, e o líquido vira `conta_pagar_ref` no ERP.

**`FluxoAprovacao`** / **`NivelAprovacao`** / **`Atesto`** — a aprovação em **mais de um nível**
(§11.5): engenheiro → gerente de contrato → fiscal, cada nível exigindo uma permissão e registrando
atesto com autor, data e observação. Aprovada no último nível, a medição **congela**; correção exige
medição **retificadora**, nunca edição.

> **Onde essa máquina mora.** Fluxo de aprovação não é assunto de obra — é da plataforma, e o ERP e o
> SCM vão pedi-lo. Nasce em **`nucleo`**, com o PDCA como **primeiro cliente**, pelo mesmo raciocínio
> que pôs a gerência de frota em `nucleo` e não na Prancheta: *a Prancheta é a primeira cliente, não a
> dona*.

### 4.5 Qualidade, segurança e entrega — uma máquina, quatro domínios

FVS, checklist de segurança, vistoria de entrega e inspeção ambiental são **a mesma coisa**: um modelo
de verificação aplicado a um objeto, item a item, com resultado e evidência. Três cópias divergiriam
na primeira mudança de requisito.

**`ModeloVerificacao`** / **`ItemModeloVerificacao`** — o template, com `dominio` (`qualidade` ·
`seguranca` · `ambiental` · `entrega`).

**`Verificacao`** / **`ItemVerificacao`** — a ficha aplicada: obra, local, atividade opcional,
inspetor, data; cada item conforme / não conforme / não aplicável, com observação e foto. Reprovação
**parcial** é o caso normal, não a exceção.

**`NaoConformidade`** — nasce de um item reprovado ou avulsa. Obra, local, atividade opcional,
gravidade, foto — e **`marcacao_prancheta` opcional**, que a ancora ao pino sobre o desenho e a exporta
em BCF junto com o resto.

**`PlanoAcao`** (5W2H) — o quê, por quê, onde, quando, quem, como, quanto; tipo **corretiva** ou
**preventiva**, as duas que o PBQP-H exige. **`VerificacaoEficacia`** fecha o laço: a não-conformidade
**não encerra** enquanto a eficácia não for verificada e registrada. É o padrão do SAP QM, e é o que
separa tratar de arquivar.

### 4.6 SSMA

**`DialogoSeguranca`** (DDS) com participantes de `rh.Funcionario`, **`Ocorrencia`** (quase-acidente /
incidente / acidente, com CAT e dias perdidos) e **`EntregaEPI`**, que aponta `catalogo.Item` — EPI já
é uma natureza do catálogo — e cujo movimento de estoque é do SIL. O PDCA registra a **entrega e a
validade**; quem baixa o saldo é quem sempre baixou.

### 4.7 Apropriação e produtividade

**`Equipe`**, **`Efetivo`** (quantos, onde, quando) e **`ApropriacaoHH`** (horas por atividade). Com o
coeficiente da composição do orçamento, isso produz **produtividade real × prevista** e permite o EVM
em **homem-hora** ao lado do EVM em custo — as duas curvas que o P6 mostra e o MS Project não.

### 4.8 Pós-obra

**`Vistoria`** de entrega sobre a `LocalObra` (a unidade), gerando **punch list**; **`Garantia`** por
sistema construtivo com prazo contado da entrega; **`ChamadoGarantia`** ligado ao cliente. É o "Act" do
empreendimento inteiro, e reaproveita a mesma máquina de verificação da §4.5.

### 4.9 O que é derivado, e não tem tabela

Curva S física, curva S financeira, PV/EV/AC, SPI/CPI, PPC, produtividade, saldo de contrato e caminho
crítico são **calculados**. Guardá-los criaria a segunda verdade que diverge da primeira — o erro que
o `services.componentes_da_composicao` do Orçamento já corrigiu ao virar leitura única.

## 5. A tela que justifica o módulo

O seletor de lente **é o ciclo**: **Planejar · Executar · Verificar · Agir**. É o padrão que o SIL
("Operação × …"), o Maps ("Operação × Território") e a Prancheta ("Campo × Acervo") já usam, e aqui ele
coincide com o nome do módulo.

O hub abre em **fila de decisão**, não em gráfico:

- medições **aguardando o meu atesto**, com valor e nível;
- **restrições vencendo** antes da programação da semana;
- não-conformidades **sem plano de ação** e planos **com prazo vencido**;
- atividades atrasadas **no caminho crítico** — só as que movem a data final;
- contratos com **saldo perto do fim** e itens medidos além do previsto;
- verificações **reprovadas** sem tratamento.

Cada linha leva ao ato, e o ato conclui. Não é lista para contemplar.

## 6. Integrações — o que conversa no backend conversa na tela

| Com quem | O que atravessa |
|---|---|
| [Orçamento](moduloorcamento.md) | Régua orçada por etapa/atividade; a **curva S financeira passa a derivar do cronograma físico**, em vez de a distribuição por competência ser digitada; aditivo ↔ `RevisaoOrcamento` |
| [SIL](modulosil.md) | Aplicado de material por `(obra, etapa)` ao lado do avanço físico — consumo × produção |
| [SCM](moduloscm.md) | Restrição de material vira **demanda**; item de serviço contratado conversa com o pedido |
| [ERP](moduloerp.md) | Medição aprovada → **título líquido** → `ContaPagar`. O ERP decide quando sai do caixa |
| RH | Responsável, equipe, efetivo, DDS, EPI |
| [Diário](modulodiario.md) | Apontamento e NC podem **nascer no diário do dia**, inclusive por WhatsApp; e o diário passa a mostrar o que estava programado |
| [Prancheta](moduloprancheta.md) | NC ancorada no desenho (`Marcacao`), exportada em **BCF** com o resto |
| [Maps](modulomaps.md) | `LocalObra.maps_local` — a frente de serviço no mapa |
| Clientes | Avanço **apurado** no portal, no lugar do digitado; vistoria e chamado de garantia |
| [funcoesia](funcoesia.md) | Causa de não-cumprimento sugerida; foto de NC classificada — o módulo é **consumidor**, sem cliente de IA próprio |
| [funcoesimpexp](funcoesimpexp.md) | Importar cronograma de MS Project/P6 e exportar medição, verificação e curva S |

## 7. Fronteira do módulo (o que ele **não** faz)

- **Não** paga. Medição vira título; caixa é do [ERP](moduloerp.md).
- **Não** compra nem cota. Restrição vira demanda; compra é do [SCM](moduloscm.md).
- **Não** movimenta estoque. Consumo e EPI são do [SIL](modulosil.md).
- **Não** compõe custo. Composição, BDI e preço são do [Orçamento](moduloorcamento.md); aqui o custo
  entra pelo vínculo com `ItemOrcado`.
- **Não** extrai quantitativo de modelo BIM. É da Central BIM com a [Prancheta](moduloprancheta.md).
- **Não** guarda projeto (Prancheta) nem documento de gestão (`modulodms`).
- **Não** cadastra pessoa (RH) nem fornecedor (`fornecedores`) — usa os que existem.
- **Não** substitui o [Diário](modulodiario.md): escreve e lê nele.

## 8. Contrato de módulo

Entitlement `pdca` (já reservado). Grupo de permissões `pdca`, com a segregação que o ORC.6 provou
necessária — quem executa não aprova:

`pdca.local.*` · `pdca.cronograma.view|edit|publicar|replanejar` · `pdca.avanco.apontar` ·
`pdca.programacao.view|comprometer|encerrar` · `pdca.restricao.*` · `pdca.contrato.view|edit` ·
`pdca.medicao.view|apurar|atestar` · `pdca.aditivo.edit|aprovar` ·
`pdca.verificacao.modelo_edit|aplicar` · `pdca.nc.abrir|tratar|verificar_eficacia` · `pdca.ssma.*` ·
`pdca.apropriacao.*` · `pdca.risco.*` · `pdca.garantia.*`

O nível de aprovação da medição **não** cria permissões numeradas: cada `NivelAprovacao` declara
**qual permissão** ele exige, e o tenant compõe a escada com os papéis que já tem.

Uma permissão nasce **fora** deste grupo, no grupo `base`: **`obras.etapa.percentual_manual`** (§11.2).

Personas de fábrica: `planejador`, `engenheiro_de_obra`, `gestor_contratos`, `tecnico_qualidade`,
`fiscal`. As existentes (`orcamentista`, `almoxarife`, `suprimentos`) ganham só leitura do que lhes diz
respeito.

**Tetos em [`payment/planos.py`](../../payment/planos.py)**, como todo limite do sistema: atividades por
cronograma, profundidade da WBS, locais por obra e profundidade da hierarquia, itens por contrato,
linhas por medição, níveis de aprovação, fotos e bytes por apontamento, relógio do recálculo de CPM e o
corte síncrono × job, retenção de linhas de base. Nenhum deles em código de engenharia nem no
`settings.py`.

## 9. O campo — três caminhos, em fases declaradas

*(Decisão do dono, 22/08/2026.)*

1. **WhatsApp** — a porta que **já existe e está em produção**: `modulodiario.origem = whatsapp`, com a
   IA lendo texto e foto. Apontar avanço, abrir NC com foto e responder verificação por conversa. O
   mestre de obras não instala nada.
2. **Web responsiva** — as telas do módulo funcionando no navegador do celular, para o que exige forma
   (ficha de verificação item a item, medição linha a linha).
3. **PWA com offline de verdade** — manifest, service worker, fila de sincronização e resolução de
   conflito. **É fatia de plataforma, não do PDCA**, e o endereço fica reservado aqui para ninguém a
   implementar avulsa dentro deste módulo — o mesmo cuidado que a capacidade de PDF recebeu no
   `modulodms`.

## 10. Seams de expansão (inertes no desenho)

Importação de cronograma de MS Project/P6 · nivelamento de recursos · simulação Monte Carlo de prazo ·
4D (cronograma × modelo, sobre a Prancheta) · benchmark de produtividade entre empresas (Esfera de
Rede) · previsão de atraso por IA sobre PPC e causas.

## 11. Decisões de rumo (tomadas pelo dono do produto)

### 11.1 A WBS é própria, e o vínculo com a etapa é opcional

*(22/08/2026.)* O cronograma tem sua própria árvore, com liberdade total para Gantt e linha de balanço,
e **pode** se vincular a uma `EtapaObra` para mapeamento. Ampliar a `EtapaObra` seria pôr planejamento
dentro de um app de cadastro que é fundação de vários módulos, e uma tabela que a obra usa como
macro-fase não comporta a granularidade de um cronograma real.

**Consequência:** a tradução entre a WBS e a dimensão `(obra, etapa)` — que Orçamento e SIL já
compartilham — é **explícita**, feita pelo vínculo, e a cobertura dela é declarada na resposta da API,
no molde do `realizado_cobertura` do Orçamento. Vínculo que não existe não é inventado.

### 11.2 O percentual digitado continua existindo, sob permissão

*(22/08/2026.)* `EtapaObra.percentual_conclusao` hoje é digitado à mão e pondera quatro leituras
(resumo da obra, serializer, portal do cliente, curva S real). Havendo vínculo direto com uma atividade
do PDCA, ele passa a ser **apurado** — e a edição manual continua **possível**, liberada ou bloqueada
por **`obras.etapa.percentual_manual`**, do usuário ou do admin.

A tela **sempre diz de onde veio o número** — apurado ou informado. Duas fontes silenciosas para o
mesmo número é como se perde a confiança nas duas.

### 11.3 Obra pública é opção do usuário, não regime do sistema

*(22/08/2026.)* O módulo atende contrato privado e público. As **regras duras** — limite legal de
acréscimo, atesto de fiscal — ficam **atrás de uma opção que o usuário liga no contrato**. Nem toda
obra com dinheiro público segue o mesmo estatuto, e sistema que impõe a regra pela origem do dinheiro
erra na exceção.

**O limite legal não vai para `payment/planos.py`.** Ele é regra de domínio, não teto comercial — a
mesma natureza da fórmula do Acórdão 2622/2013-TCU, que mora no código do Orçamento. A §5.6 do
`planos.py` já traça essa fronteira.

### 11.4 Avanço e medição são duas coisas, e a medição nasce do avanço

*(22/08/2026.)* O **avanço** é da atividade e existe sempre — inclusive em serviço executado por equipe
própria, que não tem contrato. A **medição** é do contrato e só existe onde há empreiteiro, e é
**proposta a partir do avanço do período**, para o gestor conferir e ajustar antes de submeter.

Unificar os dois obrigaria toda atividade a ter contrato para ter avanço. Separá-los sem derivação
produziria dois números divergindo sem ninguém notar.

### 11.5 Medição aprovada congela, com escada de atesto

*(22/08/2026.)* Aprovação em **mais de um nível**, com atesto registrado em cada um; no último, a
medição congela e só uma retificadora a corrige. É dinheiro saindo: o mesmo rigor do orçamento
aprovado. A máquina de fluxo nasce em `nucleo` (§4.4).

### 11.6 Uma máquina de verificação, quatro domínios

*(22/08/2026.)* FVS, inspeção de segurança, vistoria de entrega e checagem ambiental compartilham
modelo, aplicação, evidência e tratamento. Ver §4.5.

## 12. Sub-fatias (proposta de faseamento)

O desenho é completo; a execução segue o padrão do projeto — fatias que entram inteiras e testadas.

| Fatia | O que entrega |
|---|---|
| **PDCA.0** | Fundação: `LocalObra` + gerador em lote, `CalendarioTrabalho`, permissões, personas, RLS fail-closed, contrato de módulo — e a **máquina de fluxo de aprovação em `nucleo`** |
| **PDCA.1** | Cronograma versionado, `Atividade` (WBS), `Precedencia`, CPM, linha de base, vínculos opcionais com `EtapaObra` e `ItemOrcado` |
| **PDCA.2** | `ApontamentoAvanco`, avanço ponderado, curva S física × financeira, e a tomada do `percentual_conclusao` com a permissão de override |
| **PDCA.3** | `ContratoObra`, `ItemContrato`, `Medicao` nascendo do avanço, retenção, escada de atesto, título ao ERP |
| **PDCA.4** | `AditivoContrato` com as travas, saldo de contrato e o regime público opcional |
| **PDCA.5** | Last Planner: `Restricao`, `ProgramacaoSemanal`, PPC e catálogo de causas |
| **PDCA.6** | Linha de balanço sobre `LocalObra` — ritmo, sincronia de equipes, gargalo |
| **PDCA.7** | Verificação (FVS), `NaoConformidade` com pino da Prancheta, `PlanoAcao` 5W2H e verificação de eficácia |
| **PDCA.8** | SSMA: DDS, ocorrência, EPI |
| **PDCA.9** | Apropriação, produtividade e EVM em homem-hora |
| **PDCA.10** | Riscos e marcos |
| **PDCA.11** | Pós-obra: vistoria, punch list, garantia, chamado |
| **PDCA.12** | Frontend Malha completo — hub com fila de decisão e as quatro lentes |
| **PDCA.13** | E2E vivo pelo gateway, no padrão de `orc6_orcamento_test.py` e `pra8_prancheta_test.py` |

O canal WhatsApp e a web responsiva entram **dentro** das fatias que produzem dado de campo (2, 5, 7,
8); o PWA offline é fatia de plataforma, fora desta conta (§9).

## 13. O que ficou de fora — e o endereço de cada coisa

| Capacidade | Onde mora |
|---|---|
| Nivelamento de recursos e Monte Carlo de prazo | Aqui, em fatia posterior — depende do CPM estar maduro |
| Importação de MS Project/P6 | [`funcoesimpexp`](funcoesimpexp.md), como recurso declarado |
| 4D — cronograma sobre o modelo | Central BIM + [Prancheta](moduloprancheta.md) |
| Previsão de atraso e de estouro | [`funcoesia`](funcoesia.md), com os dados daqui |
| Benchmark de produtividade entre empresas | Esfera de Rede |
| App de campo offline | Plataforma (§9) |
| Realizado financeiro completo por obra | [`moduloerp`](moduloerp.md) D.1.4 |

## 14. Status

Ver [../roadmap.md](../roadmap.md).
