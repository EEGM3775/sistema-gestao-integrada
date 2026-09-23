# Acesso & Permissões — modelo de plataforma

> Como a plataforma controla **quem entra**, **o que cada empresa contratou** e **o que cada
> usuário pode acessar** — de forma **genérica, reutilizável por qualquer módulo** (nunca específica
> do backend). O módulo de drone (`funcoesODM`) é a **implementação de referência**.
> Roadmap de execução: ver [roadmap.md](roadmap.md), **Fase 6**.

## 1. Princípio

A autoridade de identidade é **uma só: a IAM**. Nenhum produto cria/autentica usuários; todos
recebem um **JWT assinado pela IAM** (RS256) e apenas o validam. Sobre isso existem **três níveis
independentes** de controle:

```
   AUTENTICAÇÃO        →  você é quem diz ser?            (login único na IAM, SSO)
   ENTITLEMENT (cam.1) →  a empresa contratou o módulo?   (AssinaturaTenant)
                          este usuário pode usá-lo?        (AcessoUsuarioModulo)
   RBAC (camada 2)     →  dentro do módulo, seu papel
                          pode ver/fazer isto?             (Perfil/Permissao)
   + ISOLAMENTO        →  só dados do seu tenant           (tenant_id em tudo + RLS)
```

As camadas são **ortogonais**: um usuário pode ter o módulo `rh` (camada 1) mas só com papel
"operacional" que não vê salários (camada 2); e jamais enxerga dados de outra empresa (isolamento).

## 2. Modelo de dados (na IAM — fonte de verdade)

| Entidade | Papel |
|---|---|
| `Tenant` | a empresa-cliente; fronteira de isolamento |
| `Usuario` | pertence a um tenant; `username` global (vira `sub` no JWT) |
| `Modulo` | **catálogo** de produtos vendáveis: `drone`, `crm`, `rh`, `erp_financeiro`, … |
| `AssinaturaTenant` | **camada 1 (empresa):** quais módulos o tenant **contratou** (+ vigência) |
| `AcessoUsuarioModulo` | **camada 1 (usuário):** quais desses módulos **este usuário** pode usar |
| `Perfil` / `Permissao` | **camada 2:** papéis/permissões dentro do tenant (RBAC) |

`Usuario.modulos_efetivos()` = **interseção** entre as assinaturas ativas do tenant e o acesso do
usuário (admins do tenant recebem todos os módulos ativos). É esse conjunto que entra no JWT.

## 3. O que viaja no JWT

```jsonc
{
  "sub": "username",                 // identidade
  "tenant_id": "...", "tenant_slug": "...",
  "modules":     ["erp_financeiro", "drone"],        // CAMADA 1 — entitlements efetivos
  "permissions": ["rh.dado_medico.view", "erp.conta_pagar.baixar"], // CAMADA 2 — permissões efetivas
  "roles":       ["financeiro"],                     // CAMADA 2 — nomes (transição/exibição)
  "is_tenant_admin": false, "iss": "sgi-iam", "exp": 0
}
```

Todo serviço valida a assinatura (RS256, chave pública/JWKS) e lê essas claims. **Nenhuma decisão
de acesso depende de tabela local de permissão** — a verdade está no token. Desde a **Fase 9.A**, a
checagem da camada 2 é por **permissão** (`permissions`); `roles` fica para transição/exibição.

## 4. Enforcement genérico (o padrão que TODO módulo segue)

A regra é sempre a mesma, independente da tecnologia do módulo:

1. **Entitlement (camada 1):** o endpoint exige um **código de módulo**; se ele não está em
   `modules`, responde **403** (`RequireModule`).
2. **RBAC por permissão (camada 2):** o endpoint declara `required_resource`/`required_permission` e
   `RequirePermission` checa o claim `permissions`; senão **403**. Token legado (sem `permissions`)
   cai no `RequireRole` (papel) durante a transição.
3. **Isolamento:** toda query filtra por `tenant_id` do token (+ RLS no Postgres).

### Implementação de referência — o drone (`funcoesODM`, Java)
- `SecurityConfig` exige a authority `MODULE_drone` em todo endpoint de negócio → **403** sem o
  módulo. O código exigido é **configurável** (`app.module.required`) — ou seja, **é um padrão
  genérico**, não algo "do drone".
- Prova: usuário **sem** `drone` recebe **403**; **com** `drone`, **200** (ver
  `testes/e2e/phase4_e2e.py`).

O drone também demonstra que um módulo pode ser uma **stack inteiramente separada** (Spring +
Angular) e ainda assim plugar na **mesma** identidade/entitlement — sem reimplementar nada.

## 5. Estado atual (honesto) por serviço/módulo

| Serviço / módulo | Autenticação | Entitlement (cam.1) | RBAC (cam.2) | Isolamento |
|---|---|---|---|---|
| **IAM** | é a autoridade | emite os entitlements | dono do catálogo + papéis (personas por tenant) | dono dos tenants |
| **Drone** (`funcoesODM`) | ✅ JWT IAM | ✅ `MODULE_drone` (403) | ⚠️ por owner | ✅ `tenant_id` |
| **backend — `modulocrm` (`crm`)** | ✅ JWT IAM | ✅ `RequireModule` (403) | ✅ `RequirePermission` por recurso (fecha o S5) | ✅ tenant-scope |
| **backend — `rh` (`rh`)** | ✅ | ✅ `RequireModule` | ✅ `RequirePermission` — `rh.dado_medico`/`rh.dado_bancario`/`rh.folha` (papéis provisionados, 403 destravado) | ✅ |
| **backend — `moduloerp` (`erp_financeiro`)** | ✅ | ✅ `RequireModule` | ✅ `RequireRole("financeiro")` (migra p/ permissão na 9.B) | ✅ |
| **backend — base** (`clientes`/`fornecedores`/`obras`/`empreendimentos`) | ✅ | n/a (sempre disponível) | ✅ `RequirePermission` por recurso (`cadastro.*`/`obra.*`) — 05/07/2026 | ✅ |
| **backend — `modulodiario`** | ✅ | n/a (base) | ✅ ABAC próprio (`PodeModerarDiario` + equipe/responsável) | ✅ |
| **Sistema de lixo** (`/api/lixo/`) | ✅ JWT IAM | n/a (base) | ✅ `plataforma.lixo.view|.restaurar|.purgar` | ✅ tenant-scope + RLS |

**Leitura (após a Fase 9.A/9.B, 05/07/2026):** a **camada 1** segue genérica (`RequireModule` lê
`modules`). A **camada 2** passou a checar **permissão** (`RequirePermission` lê `permissions`), com
`RequireRole` **depreciado** (fallback p/ token legado). A IAM ganhou um **catálogo global de
permissões** (`modulo.recurso.acao`, [iam/identity/catalog.py](../iam/identity/catalog.py)),
**personas por tenant** compostas do catálogo (com trava anti-escalada) e uma **UI de administração**
(`/app/admin/papeis` e `/app/admin/usuarios`, via gateway `/iam/`). O 403 histórico do RH foi
**destravado** (papéis `rh_medico`/`rh_financeiro` provisionados). A **fatia C** (mascaramento de
campo/PII) também já vale: `FieldMaskingSerializerMixin` mascara campo sem permissão na leitura e
rejeita na escrita (RH, clientes, fornecedores). Validado por `iam/identity/tests.py`,
`backend/rh/tests.py`, `backend/rh/test_field_masking.py` e `backend/modulocrm/tests.py`.
**Pendência:** ABAC por objeto (fatia D) e remover os **modelos** legados `nucleo.Perfil`/`Permissao`.

> **Desenho-alvo (AD-9) — status por fatia:** **A** (catálogo + personas + `permissions` no JWT),
> **B** (`RequirePermission` no enforcement) e **C** (mascaramento de campo/PII) ✅. A **fatia D do
> AD-9** (ABAC por objeto — acesso a empreendimento) segue pendente; a **fatia E** (limpeza do
> `RequireRole`) também. **LGPD** (roadmap 9.D — portabilidade, esquecimento e incidente ANPD com
> confirmação do dono) ✅ 05/07/2026: `GET/POST /api/lgpd/<tipo>/<id>/exportar|esquecer/` e
> `/api/lgpd/incidentes/` ([nucleo/lgpd.py](../backend/nucleo/lgpd.py)). Desenho completo em
> [arquitetura/rbac-abac.md](arquitetura/rbac-abac.md); paywall/planos em
> [arquitetura/monetizacao.md](arquitetura/monetizacao.md).
>
> ⚠️ Numeração: "9.D" no [roadmap](roadmap.md) = **LGPD**; "fatia D" no AD-9 §6 = **ABAC por objeto**.

### Adimplência do cliente — situação × números (decisão de produto)

A carteira de clientes ([frontend.md §5.8](frontend.md)) mostra uma pílula
**adimplente/inadimplente** para quem enxerga o cadastro (`cadastro.cliente.view`), mas os
**números** — parcelas em atraso, valor, dias, faixa detalhada, subtotais de grupo — exigem também
**`erp.cobranca.view`**. É o mesmo gate de duas pontas das divergências Asaas, pela mesma razão:
`hasModule` é entitlement do **tenant**, não permissão do **usuário**.

O corte é **no backend**: sem a permissão os campos não são serializados, então a tela não tem como
vazá-los por engano — e a ordenação por valor/atraso também é recusada, porque ordenar por dívida é
uma forma de lê-la. O documento segue mascarado sem `cadastro.cliente_doc.view`, e não há exportação
para planilha nesta tela (decisão do dono do produto).

**O que foi decidido conscientemente:** o rótulo binário *é* dado financeiro de pessoa natural e
aparece para todo usuário do cadastro. A alternativa (esconder também a pílula) foi levantada e
recusada — quem atende o cliente precisa saber se há pendência antes de prometer entrega ou emitir
2ª via. Se o entendimento mudar, o corte é uma linha em `_pode_financeiro`
([clientes/views.py](../backend/clientes/views.py)).
> São coisas diferentes (herança de dois esquemas).

## 5.1 Revogação imediata de sessão (época no Redis)

O access token é **stateless**: os resource servers o validam só por
assinatura+`exp`, sem consultar estado. Isso cria uma **janela de acesso
residual**: depois de trocar/resetar a senha ou desativar um usuário, o access
token que já estava emitido **continua válido até expirar** (≤ `ACCESS_TOKEN_LIFETIME`).
Blacklistar o **refresh** não fecha essa janela — só impede a *renovação*.

Para cortar na hora, a IAM mantém um **carimbo de época por usuário** num Redis
compartilhado (DB dedicado `2`): `sess:revoked_after:<user_id> = <timestamp>`.

- **Grava (IAM):** troca de senha (`ChangePasswordView`), reset por admin
  (`UsuarioViewSet.redefinir-senha`) e **desativação** (`is_active` True→False)
  chamam `bump_session_epoch()` ([iam/identity/revocation.py](../iam/identity/revocation.py)),
  **junto** com o blacklist do refresh.
- **Checa (resource server):** a cada requisição, o validador rejeita o access
  cujo `iat` seja **anterior** ao carimbo (`iat < revoked_after`, estrito — o
  token reemitido no mesmo instante para quem trocou a própria senha sobrevive).
  No backend: `IamJWTAuthentication` → `is_session_revoked()`
  ([backend/nucleo/revocation.py](../backend/nucleo/revocation.py)), com **circuit breaker** para não
  pagar o custo de um Redis fora do ar em toda requisição (ver tabela de latência abaixo).
- **Auto-limpeza:** o carimbo tem TTL = access TTL + margem; um token emitido
  antes dele já terá expirado, então a chave some sozinha.

O **access TTL** foi encurtado para **5 min** (`JWT_ACCESS_MINUTES`) como rede de
segurança: se o Redis estiver fora, essa é a janela residual máxima. O usuário
legítimo **não reloga** — o refresh silencioso renova em background.

### Redis indisponível: **fail-open** (padrão) vs fail-closed

Config `SESSION_REVOCATION_FAIL_OPEN` (backend). O padrão é **fail-open** — se o Redis
não responder na checagem, a requisição **passa**. Consequências, exaustivas:

| | **Fail-open (padrão)** | **Fail-closed** |
|---|---|---|
| Redis no ar | Revogação imediata (~40 ms, medido) | Revogação imediata (~40 ms, medido) |
| Redis **fora** | Volta a valer a janela de ≤ **5 min** (o access TTL) para sessões já revogadas; **usuários legítimos seguem normais** | **TODA a autenticação do backend para** (todo request autenticado → 401), inclusive quem nada tem a ver com revogação |
| Superfície de risco | Curta e limitada a quem acabou de ser revogado | Indisponibilidade total do produto |
| Latência (Redis no ar) | 1 `GET` (~40 ms, timeout 0,25s) | idem |
| Latência (Redis **fora**) | A 1ª sondagem após a queda custa **~4 s** (resolução DNS do host parado — o `socket_timeout` **não** cobre DNS). O **circuit breaker** então abre por 5 s e responde na hora (~0 ms); custo amortizado ≈ 1 sondagem lenta a cada 5 s **por worker** | mesma sondagem de ~4 s, mas ao abrir o breaker passa a **negar** na hora |
| Reinício do Redis | Com **AOF ligado** (config atual: `--appendonly yes`), os carimbos **sobrevivem** ao restart → revogação **segue valendo** (medido). Só perda real de chaves (FLUSHDB/eviction) reabre a janela por ≤5 min | idem quanto às chaves |

**Decisão:** fail-open. O objetivo é conter o funcionário descontente **sem** dar
ao Redis o poder de derrubar o produto inteiro; e o access curto (5 min) já
limita o pior caso. Trocar para fail-closed é 1 env var
(`SESSION_REVOCATION_FAIL_OPEN=False`) — recomendado só onde contenção > disponibilidade
e o Redis tenha HA.

### Escopo e follow-ups

- **Aplicado agora:** backend (resource server) + IAM (autoridade) + **drone**
  (`funcoesODM`, Spring Boot): `SessionRevocationService` (Jedis, mesmo Redis DB 2
  e chave `sess:revoked_after:<user_id>`) plugado no `JwtAuthenticationFilter` —
  lê `user_id`+`iat`, e sessão revogada → **não autentica** → 401 no `SecurityConfig`;
  mesmo fail-open + circuit breaker do backend. **E2E validado no stack vivo 13/07/2026**
  (token com módulo drone → 200; carimbo no Redis DB2 → mesmo token 401; relogin → 200).
- **Serviços Node (`funcoesia`/`funcoesnf`/`funcoeswhatsapp`) — fora de escopo:** o
  gateway **não** os roteia (não têm porta de usuário na borda; são chamados só
  serviço→serviço/webhook) e serão absorvidos em Python na **Fase 11**, quando
  herdam a checagem do backend. Portar a revogação neles agora seria código
  descartável contra exposição teórica.
- **Editar papéis/permissões NÃO dispara revogação imediata** (decisão atual): a
  mudança propaga no próximo refresh (≤5 min). Para torná-la imediata seria
  preciso, ao salvar um `Perfil`, **carimbar a época de todos os usuários que têm
  aquele papel** — ex.: no `PerfilViewSet.perform_update`, iterar
  `perfil.usuarios.values_list("id")` e `bump_session_epoch(uid)` para cada um
  (e idem ao (des)vincular papéis de um usuário em `UsuarioSerializer.update`).
  Custo: um `bump` por usuário afetado a cada edição de papel; por isso ficou de
  fora por ora.

## 5.2 Duração da sessão (janela deslizante + teto absoluto)

O **access** (5 min) é só o passe de curta duração; quem define por quanto tempo o
usuário fica logado é o **refresh**, no cookie HttpOnly. Ele tem **dois limites
independentes**, e confundi-los é fácil:

| | Sem "manter conectado" | Com "manter conectado" |
| ---------------------------- | ---------------------- | ---------------------- |
| **Janela deslizante** (inatividade) | 2h | 7 dias |
| **Teto absoluto** (desde o login) | 12h | 30 dias |
| **Aviso antes de cair** | 15 min | 15 min |

- **A janela desliza:** cada rotação do refresh reemite o token com `agora + janela`.
  Quem está trabalhando não cai.
- **O teto não desliza:** o `exp` é sempre aparado por `sst + teto` (`sst` = início da
  sessão, preservado em toda rotação). Batido o teto, **nem a atividade renova** — tem
  de relogar. É este limite que garante que uma sessão roubada morre sozinha.

**Por que o teto é o controle de segurança que importa:** a rotação com detecção de
reuso só desmascara o ladrão se o usuário legítimo usar o sistema **em paralelo** — um
cookie copiado numa sexta à noite seria rotacionado sozinho o fim de semana inteiro sem
disparar nada. O teto é a única barreira que não depende de ninguém notar. Por isso o
teto do "manter conectado" foi reduzido de 90 → 30 dias: no caminho *default* uma
invasão morre em ≤12h, e não fazia sentido o caminho opt-in tolerar 3 meses.

**A rotação depende de interação real do usuário.** O front renova o access sozinho
enquanto a aba está aberta; se essa renovação também rotacionasse o refresh, a janela de
inatividade **nunca fecharia** — uma aba esquecida num notebook destravado seguraria a
sessão até o teto. Por isso o `AuthContext` só renova quando houve interação
(mouse/teclado) desde a última renovação; ocioso, deixa expirar.

**Contrato com o front:** o refresh é HttpOnly (opaco ao JS), então o front não tem como
saber quando a sessão cai. O login, o refresh e a troca de senha devolvem
`session_expires_at` (época do `exp` do refresh) e `session_warn_seconds` — é com isso
que o front agenda o modal de aviso. São instantes, não segredos.

**Onde se configura** (`iam/iam_project/settings.py`, todos com env override):
`JWT_SESSION_IDLE_HOURS` · `JWT_SESSION_IDLE_CAP_HOURS` · `JWT_SESSION_REMEMBER_DAYS` ·
`JWT_SESSION_CAP_DAYS` · `JWT_SESSION_WARN_MINUTES`. **Não existe knob de "dias de
refresh"**: o `REFRESH_TOKEN_LIFETIME` do SimpleJWT é sobrescrito por estes valores.

## 6. Fase 6 — implementada (02/06/2026)

Enforcement **genérico e reutilizável** construído e aplicado:
- `RequireModule("codigo")` / `RequireRole("papel")` em
  [nucleo/permissions.py](../backend/nucleo/permissions.py) — espelho do `MODULE_drone`, lendo os
  claims `modules`/`roles` do JWT.
- Aplicado a `crm`/`rh`/`erp_financeiro` (+ papel `financeiro`).
- Legados removidos (login do backend; endpoints `Perfil`/`Permissao`).

Pendências: mascaramento de campos por papel; remoção dos modelos `nucleo.Perfil`/`Permissao`;
aplicar o contrato (§7) aos módulos hoje vazios. Detalhe e DoD em
[roadmap.md](roadmap.md), **Fase 6**.

## 7. Papel `gestor_lixo`

Papel intra-tenant que controla o ciclo de vida da lixeira (exclusão reversível):

| Operação | `gestor_lixo` | Usuário comum | Permissão |
|---|---|---|---|
| Excluir (marcar a lápide) | ✅ | ✅ | a do próprio módulo — **nenhuma nova** |
| Ver itens na lixeira | ✅ | ❌ | `plataforma.lixo.view` |
| Restaurar item | ✅ | ❌ | `plataforma.lixo.restaurar` |
| Purgar antes do prazo | ✅ | ❌ | `plataforma.lixo.purgar` |

**Excluir não ganhou verbo novo**: quem já podia apagar continua podendo, e o que mudou é que agora
dá para voltar atrás. Trancar a exclusão atrás de uma permissão nova tornaria a lixeira um
rebaixamento de permissão disfarçado de melhoria.

**Purgar é permissão separada de restaurar**: restaurar devolve dado à circulação; purgar destrói,
antes do prazo, o que ainda dava para recuperar. `gestor_lixo` tem as duas pelo `.*`.

**Não há "configurar retenção"**: o prazo é do **plano** (`lixo_retencao_dias`, §5.5g do
[`planos.py`](../payment/planos.py)), não configuração de tenant — é paywall, e a purga não é
opcional, porque é ela que corta o custo que a decisão do dono queria cortar.

Implementação: `RequirePermission` (o padrão da casa desde a Fase 9) no
[`nucleo/lixo_views.py`](../backend/nucleo/lixo_views.py) — e **não** `RequireRole`, que a prancha
antiga previa antes de o catálogo de permissões existir.
Arquitetura completa da lixeira: [arquitetura/lixo.md](arquitetura/lixo.md).

## 8. Contrato de um módulo novo (vendável isoladamente)

Qualquer módulo futuro — um app Django **ou** um serviço separado (estilo drone), incluindo os hoje
vazios (`modulodms`) — segue o **mesmo contrato**, sem reimplementar identidade:

1. Registrar um `Modulo` (código) no catálogo da IAM.
2. Tornar-se vendável por `AssinaturaTenant` (empresa) e liberável por `AcessoUsuarioModulo` (usuário).
3. Validar o JWT da IAM (RS256/JWKS) e **exigir o código do módulo** (403 se ausente) — via
   `RequireModule` (Django) ou o filtro de authority (estilo drone).
4. Aplicar RBAC por papel quando necessário e filtrar tudo por `tenant_id`.

## 9. Alçada — a escada de atesto (`/api/aprovacao/`)

*(PDCA.0, 23/08/2026. Desenho no [modulopdca.md §4.4](modulos/modulopdca.md).)*

As duas camadas respondem *"você pode fazer isto?"*. A escada responde outra pergunta: **"quantas
pessoas precisam concordar antes de isto valer?"** — e ela não se resolve com mais permissões.

Um `FluxoAprovacao` é do tenant e tem N `NivelAprovacao`; **cada nível declara qual permissão do
catálogo ele exige**, e é isso que impede o vocabulário de crescer por cliente: nada de
`…aprovar_nivel_2`. A empresa compõe a escada com os papéis que já tem. Um `PedidoAprovacao` é uma
escada correndo sobre um objeto (alvo por `ContentType`), e cada degrau vencido vira um `Atesto`
append-only com autor, data, observação e **qual permissão foi conferida na hora**.

Três regras que valem para todo módulo que usar a máquina:

- **quem executa não aprova** — o solicitante não ateste, salvo se o fluxo declarar
  `permite_autoatesto` (a saída para a obra pequena, escrita e auditável);
- **reprovar encerra** — não existe voltar um degrau; a correção é documento novo, senão o atesto que
  recusou seria apagado;
- **configurar a escada é do administrador do tenant** (`plataforma.fluxo_aprovacao.edit`). Criar um
  degrau que exige a permissão X é decidir quem tem alçada sobre o dinheiro — mesma classe de ato que
  `plataforma.papel.gerir`, e por isso fora das personas de fábrica: uma delas com esse verbo poderia
  rebaixar a escada que a controla. O `.view` está na `diretoria`.

Mora no `nucleo` porque alçada é da plataforma: o PDCA (medição de empreiteiro) é o primeiro cliente,
e pagamento acima de alçada no ERP entra pela mesma porta, com outro alvo.

**O terceiro cliente estreou uma variação** *(PDCA.4, 15/09/2026)*: o **aditivo de contrato**. Os
dois primeiros — medição e liberação de retenção — congelam um documento e geram um título; o
aditivo aprovado **muda a régua de outro documento**: reescreve o preço vigente de uma linha do
contrato, cria item novo na planilha e move a vigência. Duas consequências para quem for o próximo:

- o receptor de `aprovacao_concluida` precisa ser **idempotente de verdade**, porque aplicar duas
  vezes não é somar duas vezes um valor — é criar o item novo em duplicata;
- o serviço **revalida antes de aplicar**, e não só antes de submeter: entre a submissão e o último
  atesto podem passar dias, e nesse intervalo uma medição pode ter consumido o saldo que a supressão
  ia tirar.

E a escada do aditivo é **própria**, não a da medição: quem confere serviço executado não é quem
autoriza a empresa a gastar acima do contratado (`pdca.aditivo.aprovar` × `pdca.medicao.atestar`).

**Cancelar a medição aprovada também é `atestar`, não `apurar`** *(16/09/2026)*. Ela já gerou título
no ERP, e cancelá-la derruba o título junto: é ato da mesma alçada que autorizou o dinheiro a sair, e
não de quem monta o boletim. Enquanto a medição é rascunho ou está em aprovação, nada saiu, e `apurar`
basta — a régua é o **efeito no mundo**, não o nome do verbo.

**`pdca.programacao.encerrar_antecipado` — o sexto verbo do Last Planner** *(16/09/2026)*. Ele nasceu
de um defeito: dava para fechar na segunda-feira a semana que ia até domingo, julgando como fracasso o
que ainda tinha cinco dias de prazo, e o ponto entrava na série histórica indistinguível dos outros.
A resposta não foi proibir — existe a obra que para na quinta de um feriado prolongado, e trancar faria
o time julgar de memória na segunda seguinte. Quem tem o verbo encerra antes **dando motivo por
escrito**, e a semana fica marcada. Vai junto no curinga `pdca.programacao.*` da persona `engenharia`:
quem sabe que a obra vai parar na quinta é quem está nela, e a trava que importa é a frase, não a
lista de quem pode.

## O supervisor da plataforma

*(Decisões do dono, 22/08/2026 — a seção foi reescrita duas vezes no mesmo dia,
e as duas correções estão no [histórico](historico-correcoes.md).)*

O `is_superuser` da IAM é o **supervisor e o teste supremo do sistema**. Duas
frases o definem, e elas não se contradizem:

1. **Ele não tem restrição a nenhum módulo.** Coordena a plataforma inteira e
   pode exercitar tudo. Um teste supremo que só alcança o que alguém comprou
   testa a assinatura, não o produto.
2. **Ele não está lá para alterar o banco de dados das empresas.** Supervisionar
   e testar não é editar o dado do cliente. Alcançar uma versão **secundária** do
   banco de um cliente é caminho previsto — e só se o cliente **der acesso**.
   Consentimento ainda não existe como mecanismo.

### As três réguas de acesso, lado a lado

O que separa os três atores é **de onde vem o alcance de cada um**:

| Ator | Módulos que alcança | Permissões |
|---|---|---|
| **usuário comum** | interseção: o que o tenant assina ∩ o que lhe concederam | as dos papéis dele, filtradas pelos módulos |
| **admin do tenant** (`is_tenant_admin`) | todos os que **a empresa dele** assina — e nada além | catálogo inteiro, limitado a esses módulos |
| **supervisor** (`is_superuser`) | **todos os do catálogo, contratados ou não** | catálogo inteiro |

A régua do supervisor é a única das três que **ignora o `AssinaturaTenant`**, e é
de propósito: entitlement é do cliente, e supervisionar não é ser cliente.

### O que a claim abre, e o que ela não abre

`is_superuser` na IAM vira a claim `is_platform_admin` no JWT
([identity/tokens.py](../iam/identity/tokens.py)). Ela gateia as operações de
**plataforma** — dado público ou nosso, que vale para todos os tenants ao mesmo
tempo:

- a **carga da base-mãe** (ORC.8 — SINAPI e demais tabelas públicas);
- a **confirmação de incidente ANPD** (Fase 9.D);
- a **publicação de base pública** pelo `impexp`.

E ela **não** é chave mestra. Duas coisas garantem isso:

- **A fronteira de tenant continua valendo para ele.** O escopo de queryset e a
  RLS ([nucleo/tenancy.py](../backend/nucleo/tenancy.py)) o tratam como qualquer
  um: ele enxerga o tenant onde está, não o das outras empresas.
- **O flag não é copiado para o espelho local.** `_sync_user`
  ([nucleo/authentication.py](../backend/nucleo/authentication.py)) sincroniza
  e-mail, tenant e `is_tenant_admin` — e só. Isso importa porque no backend
  `Usuario.is_superuser` **é** chave mestra: fura escopo de tenant e RLS, fura o
  `RequirePermission`, desmascara PII e ignora quota. O supervisor não recebe
  nada disso.

### O que não é dele na tela

Operação de plataforma e assunto de cliente não se misturam, **nos dois
sentidos**:

- **Plataforma não aparece para tenant, nem trancada.** Item que a pessoa não
  alcança normalmente mostra cadeado, porque é caminho que existe para ela e ela
  pode contratar. Operação de plataforma não é vendável nem contratável: mostrar
  cadeado anunciaria uma porta que não é para o lado de cá. Por isso a seção
  **Sistema** da sidebar tem `platformOnly` (o item some, e a seção vazia some
  junto) e a rota usa [PlatformRoute](../frontend/src/components/PlatformRoute.tsx),
  que redireciona em silêncio em vez de explicar a recusa.
- **Plano e quota não aparecem para o supervisor.** Eles descrevem o que uma
  *empresa* contratou: quanto pode cadastrar, quando trava, qual o próximo degrau
  de venda. Mostrá-los a quem vende o produto é oferecer upsell a si mesmo.

### Como isso é garantido, e a régua de teste que saiu daqui

Duas suítes, e **nenhuma substitui a outra**:

| Onde | O que garante |
|---|---|
| [iam/identity/tests.py](../iam/identity/tests.py) `PermissoesEfetivasTests` | o que o **emissor** põe no token: alcance de módulo, catálogo, a claim |
| [backend/nucleo/test_supervisor_nao_atravessa_tenant.py](../backend/nucleo/test_supervisor_nao_atravessa_tenant.py) | o que o **backend faz com** o que recebeu: o espelho não vira chave mestra, e o escopo de tenant vale |

A régua nasceu de um erro concreto (abaixo): *para garantir o que um usuário
**pode**, teste o emissor do token; para garantir o que o backend **faz com** o
que recebeu, teste o backend.*

### O furo que existiu, e por que ele é a melhor prova da regra

No dia em que o supervisor nasceu, o dono entrou com ele e **aprovou um orçamento
de uma empresa** — ato de alçada financeira.

A causa estava na IAM: `modulos_efetivos()` e `permissoes_efetivas()` tratavam
`is_superuser` **igual** a `is_tenant_admin`, e o token saía com tudo do tenant
onde ele mora. As duas camadas do backend fizeram o certo com o que receberam e
deixaram passar.

**O teste do backend estava verde**, porque montava o cenário com `iam_modules`
escrito à mão — presumia o que o emissor manda. Foi daí que saiu a régua acima.

A correção **não** foi tirar o alcance dele (isso trancou tudo e foi revertido no
mesmo dia, quando o dono apontou que ele não pode ter restrição a nenhum módulo):
foi separar **alcance** de **fronteira**. Ele alcança todo módulo; a empresa
continua protegida pela fronteira de tenant e pelo consentimento que ainda vai
existir.
