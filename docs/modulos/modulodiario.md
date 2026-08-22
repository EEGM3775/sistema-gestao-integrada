# Diário de obra (`modulodiario`)

> Registro **do dia** de uma obra: **um diário por obra por data**, ao qual todos os envolvidos
> agregam contribuições (texto e fotos). Fotos **disparam análise de IA**. É a ponte natural com o
> **drone** e com a [funcoesia](funcoesia.md). Código: [backend/modulodiario/](../../backend/modulodiario/).

## Acesso
App **base** quanto a entitlement, com **permissão por objeto** em dois níveis (a partir de 06/06/2026):

- **Contribuir** (adicionar entrada/foto): funcionário na **equipe** ∪ **responsáveis técnicos** da obra
  (`pode_contribuir`). Append-only.
- **Moderar** (editar/excluir qualquer contribuição): apenas **responsáveis técnicos**
  (`pode_moderar` / `PodeModerarDiario`).

Usuário sem `funcionario_profile` recebe **403** com mensagem explicativa (não 500). Isolado por tenant.

## Modelos
| Modelo | Guarda |
|---|---|
| `DiarioObra` | **Container do dia** (obra + data). Clima do dia, resumo opcional, `criado_por`. Um por obra/data. |
| `EntradaDiario` | Uma **contribuição de texto** com `autor` (Funcionario), `origem` (web/whatsapp), `eh_ocorrencia` |
| `DocumentoDiario` | Foto/vídeo do dia com `autor`, `origem`; cada imagem tem uma `analise_ia` reversa |

> A unicidade **(obra, data)** é garantida via *get-or-create* na ação `contribuir`; a
> `UniqueConstraint` formal por tenant entra na **Fase 8** (uniques por-tenant).

## Relações
- `DiarioObra.obra` → `obras.Obra`; `DiarioObra.criado_por` → `nucleo.Usuario`.
- `EntradaDiario.diario_obra` → `DiarioObra`; `EntradaDiario.autor` → `rh.Funcionario`.
- `DocumentoDiario.diario_obra` → `DiarioObra`; `DocumentoDiario.autor` → `rh.Funcionario`;
  cada documento de imagem tem uma `analise_ia` reversa (`funcoesia.AnaliseImagemIA`).

## Comportamento
- **`contribuir`** é o caminho único de escrita: faz *get-or-create* do diário de hoje da obra e anexa
  uma `EntradaDiario` (texto) e/ou um `DocumentoDiario` (foto), com autoria. Aceita multipart (foto) ou JSON.
- Ao criar um `DocumentoDiario`, dispara `disparar_analise_ia.delay(...)` (Celery) → a IA processa a imagem.
- `today` retorna o diário de hoje por **(obra, data)** — compartilhado, sem escopo de usuário.
- Endpoints auxiliares para acompanhar/reprocessar a análise e listar documentos com status de IA.

## A foto sai pela porta única (D70)

A mídia do diário deixou de ser servida por `/media/` e passou a sair pelo recurso
`obra.diario_midia` do [funcoesimpexp](funcoesimpexp.md), atrás de `obra.diario.view`. Duas
consequências no desenho, e nenhuma é cosmética:

- **a tela não pendura a URL num `<img src>`.** O token vive em memória, então a miniatura é buscada
  por XHR e vira object URL (`ImagemDoArquivo`, sobre `useArquivoBlob`);
- **o serializer publica `arquivo_nome` à parte.** A URL gateada não carrega o nome do arquivo, e é
  pela extensão que a tela decide entre miniatura e ícone.

A galeria de IA e o detalhe da análise montam payload **à mão** nas views (não passam pelo
serializer): o `url_imagem` dos dois sai de `_url_da_midia`, e é por isso que a função existe em vez
de duas expressões iguais.

### Em aberto — a miniatura, e por que o rastro está caro

O recurso entrega com `RASTRO_AUDITADO`, como os outros oito prefixos do D70: a regra do R12 é de
**autoria** (o arquivo é do cliente), não de gravidade. O custo é uma linha de `AuditLog` **por
miniatura carregada** — uma página com 20 fotos grava 20 linhas, e é o risco de afogar a trilha do
D67 que a Prancheta evitou declarando a derivada como `RASTRO_INTERNO`.

Não foi resolvido baixando o rastro deste recurso: enfraquecer auditoria no mesmo movimento que fecha
um vazamento é trocar um problema por outro, em silêncio. **A saída certa é uma miniatura gerada por
nós** — servida como `RASTRO_INTERNO` na linha do tempo, deixando o original (auditado) para quem
pedir o arquivo. Gatilho para fazê-la: quando o volume da trilha incomodar, ou quando a foto do
canteiro em 4G pesar o suficiente para o original não servir de miniatura — os dois chegam juntos.

## Endpoints (`/api/diario/`)
`/diarios/` (list/retrieve/update/delete) · `/diarios/contribuir/` (POST, escrita) ·
`/diarios/today/?obra=` · `/entradas/<id>/` (moderação) · `/documentos/<id>/` (moderação) ·
`/documentos-com-analise/` · `/documento-analise/<id>/` · `/reprocessar-analise/` · `/status-analise/<id>/`.

## UI React

Módulo em `frontend/src/modules/diario/` (Fase A — 06/06/2026):

- **DiarioObraPage** (`/app/diario`) — seletor de obra + 2 abas:
  - **Registros** — cards do **dia**, cada um com a timeline interna de entradas (autor + hora + texto,
    ocorrências destacadas) e miniaturas das fotos (com badge IA). Responsável técnico vê botões de excluir.
  - **Galeria IA** — grade das imagens de `documentos-com-analise` com badge de status (`AnaliseStatusBadge`).
- **DiarioForm** — registra no diário do dia: obra, texto, flag de ocorrência, clima do dia e **foto** (multipart).
- **AnaliseModal** — foto + resultado estruturado da IA + **Reprocessar análise**.
- Hooks: `useDiarios` (lista por dia), `useDiario` (`contribuir` + moderação), `useAnalisesIA`.

## Status / pendências
**Fase A concluída** (modelo do dia + autoria + web texto+foto). Pendente do plano de reintegração:
**Fase B** (pipeline de IA: worker Celery + LLM local) e **Fase C** (canal WhatsApp reescrito em Python).
Ver o plano em [arquitetura/diario-ia-reintegracao.md](../arquitetura/diario-ia-reintegracao.md) e o
desenho detalhado do canal WhatsApp (comunicação do SaaS, sendo o diário um dos seus fluxos) em
[modulos/funcoeswhatsapp.md](funcoeswhatsapp.md) — inclui o refactor
`modulodiario/services.py::registrar_contribuicao`, reusado pela web e pelo WhatsApp.
