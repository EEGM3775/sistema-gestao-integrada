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

**Este modelo tem um limite estrutural, e a plataforma vai sair dele** (§10). Autorização dentro do
token significa três coisas ao mesmo tempo: o token cresce com o catálogo (o admin passou dos 8 KB
de uma linha de cabeçalho e perdeu a plataforma inteira — [D194](pendencias.md)); tirar uma
permissão de alguém só vale quando o token dele expira; e cada serviço lê a lista do seu jeito.

**Compactar a lista com curinga foi tentado e recusado.** `"pdca.*"` no lugar dos códigos do módulo
concede o que ninguém concedeu: todo código novo que entrar no catálogo durante a vida do token ou
durante uma defasagem de deploy, e qualquer código que não esteja no catálogo — o degrau da escada
de aprovação (§9) guarda o código exigido como **texto livre**, e com o curinga quem tem `pdca.*`
assinaria um degrau criado para ninguém. É concessão por padrão, o oposto de *negar por padrão*.
**Regra que fica: a claim de permissões nunca leva curinga, e nenhum leitor de token interpreta `*`.**

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
rejeita na escrita (RH, clientes, fornecedores). Validado por `testes/iam/identity/tests.py`,
`testes/backend/rh/tests.py`, `testes/backend/rh/test_field_masking.py` e `testes/backend/modulocrm/tests.py`.
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

**Ler, ordenar e buscar são a mesma permissão.** Sem `cadastro.cliente_doc.view`, o CPF/CNPJ não é
critério nem de ordenação (a ordem alfabética reconstrói o dígito escondido) nem de **busca**: buscar um
CPF e ver quem volta é perguntar "existe cliente com este documento?" e ler a resposta — um oráculo
contra a máscara (LGPD art. 46). Vale na busca da carteira, na busca do cadastro
(`/api/clientes/?search=`, via `campos_de_busca` do `BuscaSemAcento`) e no filtro `?cpf_cnpj=`, que sem
a permissão responde vazio para qualquer valor. É a mesma regra do listão do ERP
([moduloerp.md §5.9](modulos/moduloerp.md)).

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
- **Editar papéis/permissões NÃO dispara revogação imediata** (decisão atual — o
  desenho-alvo em §10 resolve isto tirando a permissão do token): a
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

## 5.3 Segundo fator (fase 1 da remodelagem, §10.12)

**Quem é obrigado:** o admin do tenant e o supervisor da plataforma. Para os demais é
opcional, ligado em **Minha conta › Segurança** (`/app/conta`), que insiste com quem tem
alçada financeira ou vê dado de saúde (`segundo_fator.ALCADA_FINANCEIRA` e `DADO_DE_SAUDE`).
A **volta atrás** é por empresa: `Tenant.segundo_fator_obrigatorio = False` devolve o login
só com senha aos admins daquele tenant, sem deploy. Ela não alcança o supervisor.

**O método é TOTP** (RFC 6238, o código de 6 dígitos do app autenticador), implementado em
[`iam/identity/segundo_fator.py`](../iam/identity/segundo_fator.py) só com a biblioteca
padrão. Passkey entra depois como outro `SegundoFator.Metodo`.

**O login tem duas etapas.** A senha certa de quem tem (ou é obrigado a ter) segundo fator
**não abre sessão**: `POST /auth/login/` devolve `{segundo_fator: "codigo" | "cadastro",
desafio}`. O desafio é um passe assinado, de vida curta, que diz quem é, se a sessão será
lembrada e qual etapa falta; depois de abrir a sessão ele é gasto e não abre outra.

| Endpoint | Autoriza por | O que faz |
|---|---|---|
| `POST /auth/login/segundo-fator/` | desafio `codigo` | código do app **ou** de recuperação → sessão com `amr: ["pwd","otp"]` |
| `POST /auth/segundo-fator/cadastro/` | desafio `cadastro` **ou** sessão | segredo novo, QR (SVG gerado na IAM) e URI `otpauth://` |
| `POST /auth/segundo-fator/cadastro/confirmar/` | desafio `cadastro` **ou** sessão | primeiro código certo liga o fator; devolve os códigos de recuperação e uma sessão nova com `otp` (pela sessão, as **outras** sessões caem) |
| `POST /auth/segundo-fator/desativar/` | sessão + senha + código | tira o fator; para o obrigado é o "trocar de celular" |
| `POST /auth/segundo-fator/codigos/` | sessão + código do app | troca os códigos de recuperação (um código de recuperação não gera outros) |
| `GET/PATCH /auth/conta/seguranca/` | sessão | estado do fator e a janela de confirmação da pessoa |
| `POST /usuarios/{id}/redefinir-segundo-fator/` | admin do tenant | celular e códigos perdidos: apaga o fator e derruba as sessões do alvo; não alcança a própria conta nem o supervisor |
| `manage.py segundo_fator_emergencia <username> --codigos\|--remover --operador --motivo` | shell da IAM | a emergência que nenhuma tela alcança (o supervisor sem celular nem códigos): códigos novos impressos uma vez, ou remoção com as sessões derrubadas — com evento (operador e motivo nos detalhes, `autor` vazio) e e-mail ao dono da conta |

**O que torna o código digno do nome:**

- **anti-reuso** — o último passo de 30 s aceito fica no `SegundoFator`, e o update é atômico:
  o mesmo código não abre duas sessões, nem em paralelo;
- **bloqueio por pessoa** — na quinta falha seguida (somando login, desativação e troca de
  códigos) a conta recusa todo código por 15 minutos, mesmo o certo, e o bloqueio vai para a
  trilha. O gateway ainda limita `/auth/login/segundo-fator/` por IP, em zona própria;
- **segredo cifrado** (Fernet, chave `IAM_SEGUNDO_FATOR_CHAVE` fora do banco — obrigatória fora
  de DEBUG) e **códigos de recuperação só como hash**;
- **`amr` no token** (RFC 8176), preservado nas rotações. **O refresh recusa a sessão sem
  `otp`** de quem tem ou é obrigado a ter o fator — é o que faz a regra valer no dia do deploy,
  e não quando a última sessão lembrada do admin expirar.

**Nada é silencioso:** ativar, desativar, trocar códigos, entrar com código de recuperação,
ser bloqueado e ser redefinido pelo admin — ou pela operação, pelo comando de emergência — viram
`EventoSeguranca` e e-mail ao dono da conta (`identidade.aviso_segundo_fator`), dizendo quem fez.
As funções de serviço (`segundo_fator.gerar_codigos`/`remover`) continuam mudas: quem as chama é que
registra. Shell no contêiner ou escrita no banco seguem podendo tudo; o comando só dá à emergência um
caminho com rastro.

**A janela de confirmação** (`Usuario.janela_confirmacao_min`) é escolhida pela pessoa na
mesma tela, dentro da faixa do dono (`payment/planos.py` §5.5o). Ela fica guardada para o
step-up da fase 6, que é quem a aplica; a tela diz isso.

Os números (tentativas, bloqueio, validade do desafio, quantidade de códigos, faixa da
janela) moram em `payment/planos.py` §5.5o; o passo de 30 s, os 6 dígitos e a tolerância de
um passo são do protocolo (§5.6).

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
vazios — segue o **mesmo contrato**, sem reimplementar identidade. (O DMS não é um deles: é o
`funcoesimpexp` e não tem entitlement — o registro de arquivos usa o gate da entrega de cada recurso.)

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
| [testes/iam/identity/tests.py](../testes/iam/identity/tests.py) `PermissoesEfetivasTests` | o que o **emissor** põe no token: alcance de módulo, catálogo, a claim |
| [testes/backend/nucleo/test_supervisor_nao_atravessa_tenant.py](../testes/backend/nucleo/test_supervisor_nao_atravessa_tenant.py) | o que o **backend faz com** o que recebeu: o espelho não vira chave mestra, e o escopo de tenant vale |

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

---

## 10. Desenho-alvo — a remodelagem da segurança

> **Natureza: desenho aprovado, construído em fases.** As seções 1 a 9 descrevem o sistema como ele
> era antes da remodelagem; esta descreve para onde ele vai e por quê. Onde as duas discordam sobre o
> token e a decisão de acesso, vale esta. Faseamento em §10.12; o que já está construído e como,
> em §10.15 e §10.16; o estado de cada fase, no [roadmap](roadmap.md); o que o dono ainda precisa decidir, em
> §10.14.

### 10.1 Por que remodelar

O D194 foi o sintoma: o token do admin passou de 8 KB e a plataforma caiu para ele. A causa é que
**a autorização inteira mora dentro do token**, e isso tem consequências que nenhum remendo resolve:

| Defeito estrutural | Consequência |
|---|---|
| O token carrega as permissões | Cresce com o catálogo — comprimir só adia, curinga concede demais (§3) |
| O token vale até expirar | Tirar uma permissão só vale no próximo refresh. Demissão e troca de função deixam janela; o corte imediato só existe para senha e desativação, e é *fail-open* (§5.1) |
| Cada serviço lê a claim do seu jeito | 15 leituras diretas no backend; três delas perderiam o curinga em silêncio, e o degrau da escada aceita código em texto livre |
| Um `aud` só (`sgi`) para tudo | O token emitido para o backend vale no drone e vice-versa; o token de serviço tem a mesma audiência do de usuário |
| O token vive no JavaScript | Um script injetado (XSS) lê o access token da memória e o usa fora do navegador |
| Sem segundo fator | Quem troca papéis, alçadas e a escada de aprovação entra só com senha |
| Nenhuma decisão de acesso é registrada | Não há como responder "quem viu o CPF de quem" nem detectar abuso — o que a LGPD cobra (art. 46) |

### 10.2 Como os melhores fazem — o que a pesquisa sustenta

| Fonte | O que diz | O que adotamos |
|---|---|---|
| [NIST SP 800-207](https://nvlpubs.nist.gov/nistpubs/specialpublications/NIST.SP.800-207.pdf) (Zero Trust) | Decisão (PDP) separada da aplicação (PEP), **por requisição**, dinâmica | PDP central; cada serviço é PEP e pergunta |
| [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) | Negar por padrão, privilégio mínimo, validar `iss`/`aud`/`exp`/`nbf` | Toda decisão nega quando falta dado; nenhum curinga |
| [OWASP Multi-Tenant](https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html) | `FORCE ROW LEVEL SECURITY`; tenant em toda chave de cache; testar A→B | RLS fica como segunda barreira; tenant em toda chave |
| [Google Zanzibar](https://www.usenix.org/system/files/atc19-pang.pdf) | Autorização como serviço de relações, com token de consistência contra o "novo inimigo" | SpiceDB (implementação aberta do Zanzibar), ZedToken nos objetos sensíveis |
| [Auth0 sobre RBAC no token](https://auth0.com/blog/evaluate-resource-specific-permissions-with-rebac-instead-of-rbac/) | Permissão fina no token gera *token bloat*; a saída é ReBAC consultado | Token sem permissão nenhuma |
| [RFC 9700](https://www.rfc-editor.org/info/rfc9700/) (OAuth Security BCP, 2025) | Restringir o token a recurso e ação; tokens presos ao remetente | `aud` por serviço; BFF |
| [RFC 10017](https://oauth.net/2/browser-based-apps/) (OAuth para apps de navegador) | A arquitetura mais segura é **BFF**: o navegador só tem cookie HttpOnly e nunca vê token | BFF na frente do SPA |
| [RFC 8725](https://www.rfc-editor.org/rfc/rfc8725.html) · [RFC 9068](https://www.rfc-editor.org/info/rfc9068/) | Tipagem explícita (`typ: at+jwt`), `aud` obrigatório, claims mínimas | Contrato do token em §10.6 |
| [OpenID CAEP](https://openid.net/specs/openid-caep-1_0-final.html) · [Microsoft CAE](https://learn.microsoft.com/en-us/entra/identity/conditional-access/concept-continuous-access-evaluation) | Sessão revogada e mudança de claims viram **evento** que o serviço consome | Eventos de sessão e de relação invalidam em segundos |
| [LGPD art. 46](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm) | Medidas técnicas contra acesso não autorizado, desde a concepção | Auditoria de decisão, MFA, minimização do token |

### 10.3 Princípios — cada um vira teste

1. **O token prova quem é, não o que pode.** Nenhuma permissão, papel ou módulo no token.
2. **Uma decisão, um lugar.** Toda pergunta "pode?" passa por uma função única de cada serviço
   (`nucleo.autorizacao.pode(...)` no backend, o equivalente no drone), que consulta o PDP. Ler
   claim de permissão direto é proibido por teste.
3. **Negar por padrão.** Sem resposta do PDP e sem cache válido, nega. Código desconhecido nega.
4. **Revogação em segundos**, para sessão e para permissão.
5. **O que move dinheiro ou tira dado não usa cache** (§10.8, classe C).
6. **Defesa em profundidade.** O PDP não substitui a RLS: a fronteira de tenant continua no banco,
   e o tenant do cache, do token e da relação têm de coincidir.
7. **Toda decisão é registrada** (§10.9).
8. **O modo de falha é declarado por classe**, nunca implícito.

### 10.4 A arquitetura

```
 navegador (SPA)                 BFF / gateway                      serviços (PEP)
 ─────────────                   ─────────────                      ──────────────
 cookie __Host- HttpOnly ──────▶ sessão ⇄ tokens guardados   ──────▶ backend (aud sgi-api)
 nenhum token no JS              injeta o access por serviço        drone   (aud sgi-drone)
                                                                        │
                    IAM  ◀── login + MFA + step-up                      │ pode(usuário, ação, recurso)?
                    │  sessões (sid) · administração de papéis           ▼
                    │                                           cache de decisão (Redis, TLS)
                    └─ escreve relações ──────────────▶  SpiceDB  (PDP, sobre Postgres)
                                                             │
                                          Watch (mudanças) ──┴──▶ invalidador ──▶ cache
                                                                        │
                                                        auditoria de decisões (append-only)
```

- **A IAM continua sendo a autoridade de identidade**: login, MFA, sessões, e a tela onde o admin do
  tenant compõe papéis. O que muda é que ela **escreve relações no SpiceDB** em vez de pôr a lista
  no token.
**A IAM não é substituída.** O SpiceDB não autentica ninguém — não conhece senha, não faz login e
não emite token. Os dois dividem o trabalho assim:

| | IAM (fica) | SpiceDB (entra) |
|---|---|---|
| Pergunta que responde | **Quem é você?** | **O que você pode fazer?** |
| Login, senha, MFA, step-up | ✅ | — |
| Sessões (`sid`) e revogação de sessão | ✅ | — |
| Emissão e assinatura do token | ✅ | — |
| Empresas, usuários, catálogo de permissões | ✅ | — |
| Tela de papéis, alçadas e acesso a módulo | ✅ (a tela e as regras de quem pode editar) | — |
| Guardar quem tem qual papel, em qual empresa, em qual obra | — | ✅ (fonte única) |
| Decidir "pode?" a cada requisição | — | ✅ |

O que o SpiceDB substitui é **a lista de permissões dentro do token** e as checagens espalhadas
pelos serviços — não a IAM. As relações têm **uma fonte só**: a tela da IAM grava direto no
SpiceDB, na mesma operação, e a IAM não mantém uma cópia própria que pudesse divergir. As tabelas
`Perfil`/`Permissao` da IAM passam a ser só a definição dos papéis (nome e composição), e quem tem
cada papel mora no SpiceDB.

- **O catálogo `modulo.recurso.acao` continua sendo o vocabulário.** O schema do SpiceDB é conferido
  contra ele por teste: código no catálogo sem permissão no schema, ou o contrário, quebra a esteira.
- **A RLS do Postgres fica.** O PDP decide "esta pessoa pode esta ação neste objeto"; a RLS garante
  que, mesmo com defeito no código, uma consulta não atravessa empresa.

### 10.5 Autenticação e sessão

- **MFA obrigatório** para o admin do tenant e o supervisor da plataforma, por TOTP ou passkey
  (WebAuthn). Passkey é o padrão recomendado; TOTP fica como alternativa. **Para os demais é
  opcional** *(decisão do dono, 24/09/2026)*: cada pessoa liga o segundo fator na **tela de
  configuração do próprio perfil**, que explica em linguagem simples por que ativar — e insiste mais
  para quem tem alçada financeira ou vê dado de saúde, porque são as contas que mais interessam a
  um invasor.
  - **Trocar de celular nunca passa por "sem fator".** Com a senha e o código do aparelho atual (ou
    um de recuperação), a IAM devolve o QR do aparelho novo e guarda o segredo novo à parte, pelo
    prazo do desafio do login; o aparelho atual segue valendo. O primeiro código certo do novo troca
    o segredo no lugar, gera códigos de recuperação novos e derruba as outras sessões
    (`/auth/segundo-fator/troca/` e `.../troca/confirmar/`). **Desativar** é só para quem não é
    obrigado; o obrigado perde o fator apenas pela redefinição feita por outra pessoa
    (`redefinir-segundo-fator`, nunca na própria conta), registrada na trilha e avisada por e-mail.
- **Step-up para ato crítico** ([RFC 9470](https://www.rfc-editor.org/rfc/rfc9470.html)): atestar
  pagamento, mudar papel ou alçada e exportar dado pessoal exigem autenticação **recente**
  (`auth_time` dentro de uma janela). Fora dela, o serviço responde com o desafio, e a tela pede a
  confirmação de novo — uma sessão sequestrada navega, mas não paga.
  - **A janela é escolha de cada pessoa** *(decisão do dono, 24/09/2026)*, numa caixa de minutos na
    tela de perfil, com a explicação do risco ao lado. **Padrão de 15 minutos, escolha de 1 minuto a
    2 horas** *(decisão do dono, 24/09/2026)*. Sem teto, quem escolhesse um dia inteiro desligaria a
    proteção sem perceber; com ele, o pior caso é uma sessão aberta aprovando por até 2 horas. A
    tela, ao passar do padrão, diz isso com todas as letras. Os três números são limites do produto e
    moram em [payment/planos.py](../payment/planos.py), pela regra da casa; o servidor aplica o teto,
    e a caixa da tela é só a escolha.
  - **Quem tem segundo fator** confirma com o código ou a passkey. **Quem não tem** (é opcional para
    não administradores) confirma **digitando a senha de novo** — protege do computador esquecido
    aberto, não da senha roubada, e a tela diz isso ao sugerir ativar o segundo fator.
- **A sessão tem identidade própria (`sid`)**, guardada pela IAM. Logout, troca de senha,
  desativação, reset de MFA e o "encerrar todas as sessões" do admin marcam o `sid` revogado e
  publicam o evento; o PEP confere o `sid` a cada requisição (com a regra de cache da classe B).
- **BFF**: o SPA fala só com o BFF, por cookie `__Host-` HttpOnly, `Secure`, `SameSite=Strict`, com
  cabeçalho anti-CSRF exigido em toda escrita. Os tokens ficam no servidor. É o fim do access token
  em memória do JavaScript, e vale igual para o escritório, o campo e o frontend do drone.

### 10.6 O token — o contrato

Access token de **5 minutos**, assinado (RS256 hoje; ES256 aceitável), com `kid` e rotação de chave
pelo JWKS. Cabeçalho `typ: at+jwt`. Claims:

| Claim | Para quê |
|---|---|
| `iss`, `aud`, `exp`, `iat`, `nbf`, `jti` | Validação padrão. **`aud` é por serviço** (`sgi-api`, `sgi-drone`, `sgi-iam`) |
| `sub` | Identificador **estável** da pessoa (UUID — hoje é o `username`, que pode mudar) |
| `tenant_id` | A empresa da sessão; confere com a RLS e com a relação no PDP |
| `sid` | A sessão, para revogação |
| `acr`, `amr`, `auth_time` | Força e idade da autenticação, para o step-up |

**Sai do token:** `permissions`, `roles`, `modules`, `is_tenant_admin`, `is_platform_admin` (viram
relações no PDP) e `email` (minimização — ninguém decide acesso por e-mail). Os dados de plano
(`plano`, `rate_hora`, `quotas`) saem para uma leitura do tenant com cache, porque são da empresa e
não da pessoa. O token fica com tamanho constante, perto de 600 bytes, qualquer que seja o catálogo.

**Token de serviço** é outro tipo (`typ` próprio), emitido por *client credentials* para um `aud`
específico, com o mínimo de escopo, e **nunca** aceito onde se espera token de pessoa.

### 10.7 A autorização — o modelo no PDP

O SpiceDB guarda **relações** ("Ana é portadora do papel Fiscal da empresa X"; "a obra 12 é da
empresa X"; "o empreiteiro Y está na equipe da obra 12") e calcula permissões a partir delas. Um
esboço do schema, para mostrar a forma — o definitivo nasce na fase 2:

```zed
definition usuario {}

definition empresa {
    relation administrador: usuario
    relation membro: usuario
    // o supervisor só entra com consentimento, e com prazo
    relation suporte_consentido: usuario with ate_quando
}

definition papel {
    relation empresa: empresa
    relation portador: usuario
}

definition modulo_contratado {          // id: <empresa>_<codigo>, ex.: x_pdca
    relation empresa: empresa
    relation liberado: usuario
    permission usa = liberado + empresa->administrador
}

caveat dentro_da_alcada(limite_centavos int, valor_centavos int) {
    valor_centavos <= limite_centavos
}

definition obra {
    relation empresa: empresa
    relation pdca: modulo_contratado
    relation equipe: usuario
    relation atesta_medicao: papel#portador with dentro_da_alcada
    permission atestar_medicao = pdca->usa & (atesta_medicao + empresa->administrador)
    permission ver = pdca->usa & (equipe + empresa->membro)
}
```

- **Entitlement e RBAC viram uma pergunta só**: "usa o módulo" entra na própria permissão.
- **A alçada vira regra do modelo** (caveat): "atesta medição até R$ 50 mil" é uma relação com
  limite, conferida com o valor da medição na hora — não um verbo novo por faixa.
- **Permissão por obra (a fatia D do AD-9) cabe sem remodelar de novo**: a relação `equipe` já é por
  objeto; o papel da empresa continua valendo para todas as obras dela.
- **A escada de aprovação referencia permissão do schema**, e não texto livre: o degrau que exige
  um código inexistente é recusado ao ser criado.
- **O supervisor da plataforma** não é membro de empresa nenhuma. Para enxergar dado de uma empresa,
  precisa de `suporte_consentido`, dado pelo admin dela, com data de fim — o "consentimento que ainda
  vai existir" (acima) ganha forma.
- **Listas** ("as obras que posso ver") usam a busca de recursos do PDP ou, onde a lista for grande, a
  RLS com a relação espelhada — decisão por tela, medida na fase 3.

### 10.8 Cache, consistência e o que acontece quando algo cai

Consultar o PDP em toda requisição sem cache custaria latência e faria dele um ponto único de
queda. Com cache longo, um demitido continuaria entrando. A resposta é **classificar a ação**:

| Classe | O que é | Exemplos na plataforma | Cache | Consistência no PDP | Se o PDP cair |
|---|---|---|---|---|---|
| **A — leitura comum** | Navegar, listar, sem dado pessoal nem financeiro | carteira, cronograma, quadro da semana, fotos e diário da obra | 60 s | `at_least_as_fresh` (ZedToken da última mudança do tenant; sem mudança conhecida, `minimize_latency`) | Serve do cache até expirar; depois nega |
| **B — sensível ou escrita comum** | Dado pessoal, financeiro, de saúde; escrita que não move dinheiro | salário, CPF, títulos, saldo de contrato, bloco clínico; abrir NC, apontar avanço | 5 s | `at_least_as_fresh` (ZedToken da última mudança do tenant; do objeto, quando houver) | Serve do cache por segundos; depois nega |
| **C — ato crítico** | Move dinheiro, muda quem pode, tira dado da plataforma | atestar medição, aditivo, liberar retenção, pagar; mudar papel, alçada ou escada; exportar dado pessoal ou LGPD; baixar documento confidencial; purgar lixeira; emitir CAT | **Nenhum** | `fully_consistent` | **Nega na hora** |

- **Por que A não usa a consistência mais rápida.** O primeiro desenho dava `minimize_latency` à
  classe A. Ela pode responder com o estado de alguns segundos atrás — e a primeira pergunta depois de
  uma revogação cai exatamente aí: recebe a resposta de antes e a guarda pelo TTL inteiro sob a chave
  nova, anulando a invalidação. Com o ZedToken da última mudança, a resposta nunca é anterior a ela;
  A e B diferem no tempo de cache, não na consistência.
- **Invalidação por evento, não por espera.** Um processo consome o **Watch** do SpiceDB e, a cada
  relação alterada, **sobe a versão** do usuário (ou do objeto) afetado. A versão entra na chave do
  cache (`authz:<tenant>:<usuario>:v<versao>:<acao>:<recurso>`); a entrada velha simplesmente deixa
  de ser lida. Revogar vale em segundos, mesmo com TTL de um minuto.
- **O "novo inimigo".** O objeto sensível (planta, contrato, medição) guarda o ZedToken da última
  mudança de acesso que o afetou, e a checagem pede resposta "pelo menos tão nova quanto". O
  empreiteiro removido da obra não baixa a planta publicada um segundo depois.
- **Negação também é cacheada**, com a mesma regra, e é invalidada do mesmo jeito quando alguém
  concede.
- **O cache guarda decisão, nunca dado**: `permitido`/`negado`, classe, ZedToken. Fica num Redis na
  rede privada, com TLS e senha. **O tenant está em toda chave**, e a chave sem tenant é recusada
  pela função que escreve.
- **Redis fora:** o PEP pergunta direto ao PDP (mais lento, correto). **PDP e Redis fora:** nega. A
  sessão (`sid`) segue a regra da classe B.
- **O que isso exige da operação** está em §10.13 — sem alta disponibilidade do PDP e do Redis, a
  classe C para na primeira queda, e é de propósito.

### 10.9 Auditoria de decisão

Toda decisão vira um evento: instante, id da requisição, tenant, pessoa, `sid`, ação, recurso,
decisão, classe, de onde veio (cache ou PDP), ZedToken e a relação que concedeu. Todas vão para o
fluxo de log estruturado; **as da classe C e todas as negações** vão também para uma tabela
append-only, que ninguém edita. É o que responde "quem abriu o bloco clínico do acidente de ontem" e
o que acende alerta de abuso (muitas negações seguidas, acesso fora do padrão, tentativa entre
empresas).

**O registro guarda só o básico, nunca o conteúdo** *(decisão do dono, 24/09/2026, pela LGPD)*:
quem, quando, qual ação, **o tipo e o número** do registro acessado e a decisão. Nunca o que estava
na tela — o evento diz "abriu o bloco clínico da ocorrência 5", e jamais o CID, o nome da lesão ou
o texto do atestado. A regra vale no código: o evento tem campos fixos, sem campo de texto livre
onde um dado pudesse escapar, e há teste cobrando que nenhum valor de campo sensível chega a ele.

**Por quanto tempo — um piso legal e uma janela por plano** *(decisões do dono, 24/09/2026)*:

- **Piso de 6 meses em todo plano, inclusive o gratuito**, que não é negociável: o Marco Civil da
  Internet ([art. 15](https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2014/lei/l12965.htm))
  obriga o provedor de aplicação a guardar os registros de acesso por esse prazo, sob sigilo e em
  ambiente seguro. Nenhuma paywall pode ficar abaixo dele.
- **Acima do piso, a janela é paywall**, até **5 anos** (o prazo de ações judiciais) no plano mais
  alto. É a mesma forma da lixeira (`lixo_retencao_dias`, §5.5g do `planos.py`): a janela é do
  plano, não configuração do tenant, e a purga ao fim dela é automática — é ela que segura o custo.
- **Os números por plano saem de medida, não de chute.** A fase 2 (PDP em sombra) já produz o
  evento de toda decisão; é dali que se tira o volume real por usuário e por dia, e só então se
  fixam as janelas de cada plano no `planos.py`. Como ordem de grandeza, a estimativa é de alguns
  GB por ano para uma empresa de 50 usuários ativos.
- **Antes de cobrar, reduzir o custo**: o evento é pequeno por construção (campos fixos, sem
  conteúdo); o que passa de 90 dias sai do banco para armazenamento frio comprimido, consultável sob
  demanda. A paywall cobre o que sobra depois disso, e não a ineficiência.
- **Ordem judicial ou pedido de autoridade** para guardar além da janela (§2º do art. 15) congela o
  recorte pedido fora da purga, com registro de quem pediu e até quando.

### 10.10 Ameaças e o controle de cada uma

| Ameaça | Controle |
|---|---|
| Script injetado rouba o token | BFF — não há token no navegador; CSP |
| Token de um serviço usado em outro | `aud` por serviço + `typ` |
| Demitido ou rebaixado continua acessando | `sid` revogado + permissão fora do token + invalidação por evento |
| Concessão por padrão (curinga, código inventado, catálogo novo) | Negar por padrão; permissões tipadas no schema; escada referencia o schema |
| Vazamento entre empresas | RLS mantida; tenant no token, na relação e na chave do cache; teste A→B |
| Senha de admin vazada | MFA obrigatório |
| Sessão sequestrada aprova pagamento | Step-up com `auth_time` recente na classe C |
| Conteúdo novo lido por quem acabou de perder acesso | ZedToken no objeto; classe C sem cache |
| PDP ou Redis fora | Modo de falha por classe; C nega; HA |
| Suporte da plataforma lendo dado de cliente | Supervisor só com `suporte_consentido`, com prazo |
| "Não fui eu" | Auditoria de decisão append-only |
| CSRF contra o BFF | `SameSite=Strict` + cabeçalho anti-CSRF |

### 10.11 O que a remodelagem resolve do que está aberto

- **D194**: o token deixa de carregar permissão e fica com tamanho constante.
- **§5.1 "editar papéis não revoga na hora"**: passa a revogar em segundos.
- **Fail-open da revogação de sessão**: vira o modo de falha declarado da classe B.
- **Fatia D do AD-9 (acesso por objeto)** e o **consentimento do supervisor**: ganham modelo.

### 10.12 Faseamento — cada fase tem saída e volta

Nenhuma fase desliga o mecanismo antigo antes de a nova ter rodado **em paralelo** e ter sido
comparada decisão a decisão.

| Fase | Entrega | Critério de saída | Como volta atrás |
|---|---|---|---|
| **0 — contenção** | Tirar o curinga do código; lista exata no token; guarda de tamanho | Nenhum `*` em claim; testes verdes | — |
| **1 — MFA** | TOTP/passkey obrigatório para admin do tenant e supervisor; opcional para os demais, na tela de perfil, junto da janela do step-up | Nenhum admin entra sem segundo fator | Flag por tenant |
| **2 — PDP em sombra** | SpiceDB + schema + a IAM escrevendo relações; `pode()` no backend decide pelo token **e** consulta o PDP, registrando toda divergência | Zero divergência por duas semanas em uso real | Desligar a consulta |
| **3 — virada por módulo** | O PDP passa a decidir, módulo a módulo; cache, classes e Watch | Cada módulo sem divergência antes da virada | Flag por módulo volta ao token |
| **4 — token enxuto** | Permissões, papéis e módulos saem do token; `sid` com revogação em segundos; auditoria completa | Nenhuma leitura de claim de permissão (teste) | Reemitir claims antigas por flag |
| **5 — BFF e audiência** | SPA atrás do BFF; `aud` por serviço; token de serviço separado | Nenhum token acessível ao JavaScript | Rota antiga mantida até o fim da fase |
| **6 — endurecimento** | Step-up na classe C; consentimento do supervisor; testes de caos (PDP fora, Redis fora); pentest externo | Relatório de pentest sem achado alto | — |

### 10.13 O que isso pede da operação

- **SpiceDB** com pelo menos duas réplicas, sobre Postgres com réplica; **Redis** com réplica
  (Sentinel) e TLS. Sem isso, o desenho funciona mas a classe C para na primeira queda.
- **Monitoramento**: latência do PDP (p95 alvo de poucos milissegundos), taxa de acerto do cache,
  atraso do Watch, divergências da sombra, negações por minuto.
- **Custo honesto**: um serviço a mais para operar, e a latência de uma consulta ao PDP nas ações
  críticas. É o preço de a revogação valer em segundos e de o token nunca mais crescer.

### 10.14 Decisões — tomadas e em aberto

**Tomadas pelo dono (24/09/2026):** revogação em segundos; motor dedicado; cache curto por classe
com invalidação por evento e ação crítica sem cache; BFF; MFA para admin e supervisor; `aud` por
serviço; auditoria de toda decisão.

**Tomada na análise:** SpiceDB em vez de OpenFGA. Os dois implementam o Zanzibar sobre Postgres e
têm regras por contexto (CEL). O SpiceDB tem **token de consistência** (ZedToken) como recurso de
primeira classe — é o que resolve o "novo inimigo" —, **stream de mudanças** (Watch) para a
invalidação e busca de recursos madura; o OpenFGA só oferece "maior consistência" por consulta e
ainda não tem o equivalente do ZedToken
([consistência no OpenFGA](https://openfga.dev/docs/interacting/consistency) ·
[no SpiceDB](https://authzed.com/docs/spicedb/concepts/consistency)). O custo é governança de um
fornecedor só, contra a neutralidade da CNCF no OpenFGA. **Gatilho de troca:** o motor fica atrás
da interface `pode()`; se o SpiceDB deixar de ser mantido em código aberto, a troca é de adaptador,
não de desenho.

**Tomadas pelo dono na segunda rodada (24/09/2026):**
1. **MFA** obrigatório só para o administrador; para os demais, opcional, ligado na tela de perfil
   com a explicação de segurança (§10.5).
2. **Janela do step-up** escolhida por cada pessoa na tela de perfil (§10.5).
3. **As classes de §10.8** ficam como estão — tempos e lista de atos críticos.
4. **Auditoria** só com o básico e nunca com o conteúdo visto (§10.9).

**Terceira rodada (24/09/2026):**
5. **Janela do step-up**: padrão de 15 minutos, escolha de 1 minuto a 2 horas (§10.5).
6. **Sem segundo fator, o ato grave se confirma redigitando a senha** (§10.5).
7. **Retenção da auditoria vira paywall**: piso legal de 6 meses em todo plano (Marco Civil, art.
   15), até 5 anos no plano mais alto, com as janelas fixadas pela medida da fase 2 (§10.9).

**Em aberto, para o dono:**
- As janelas de retenção de cada plano acima do piso. Hoje todo plano está no piso legal de 180 dias
  (`payment/planos.py`); a medida da sombra de 25/09/2026 deu entre 9 e 828 decisões por dia por
  empresa na demo — pouco uso para fixar número.
- A fonte das relações: a fase 4 manteve as tabelas da IAM como fonte, com reconciliação (§10.15). Se
  a fonte única no SpiceDB continuar sendo o alvo, ela é uma fase própria.
- *(Fases 5 e 6, decisões de engenharia de 29/09/2026 a confirmar — §10.16)*: o prazo do
  consentimento de suporte (padrão 1 dia, teto 7, em `payment/planos.py` §5.5r); as duas exceções ao
  consentimento (primeiro admin da empresa sem nenhum; redefinir o segundo fator de um admin); liberar
  o suporte como ato grave (step-up) e encerrar sem ele; o refresh mantido ao lado do cookie da sessão
  (em vez de uma sessão só no servidor).

### 10.15 Como as fases 2, 3 e 4 estão construídas

**Os serviços.** O SpiceDB (`spicedb` no compose) guarda os dados num banco próprio (`spicedb_db`) do
mesmo cluster Postgres, que roda com `track_commit_timestamp=on` — sem isso o SpiceDB desliga o
Watch. Sem porta publicada, sem telemetria. Dois processos acompanham: o `iam-pdp` (IAM →
SpiceDB) e o `pdp-invalidador` (Watch → Redis). No dev, o `spicedb-testes` (em memória, um banco por
chave) serve aos testes de integração.

**O vocabulário comum** mora em [`funcoesautorizacao/`](../funcoesautorizacao/__init__.py), copiado para
as imagens da IAM e do backend: o cliente HTTP do SpiceDB (só biblioteca padrão), o schema **gerado**
do catálogo (`gerado/esquema.zed` — um tipo por módulo, cada código uma permissão; regerar com
`python funcoesautorizacao/gerar.py`, e a IAM reprova a esteira se o arquivo não for o que o catálogo
produz), o mapa código → módulo e classe que o backend lê (`gerado/catalogo.json`), a classe de cada
código (`classes.py`) e o formato das chaves de Redis (`chaves.py`, DB 5).

**O que o schema responde** é a regra que o token já aplicava, pergunta por pergunta — é o que dá
sentido a "zero divergência":

| Pergunta | No PDP | A regra de hoje que ela reproduz |
|---|---|---|
| usa o módulo `m`? | `modulo_m#usa` = supervisor da plataforma (se `m` está na tabela de módulos) + admin (se a empresa assina) + (liberado **e** membro, se assina) | `Usuario.modulos_efetivos` |
| tem o código `c`? | `modulo_m#c` = admin + supervisor + (usa **e** papel que concede `c`); nos códigos de `base`/`plataforma`, sem o `usa` | `permissoes_efetivas` + o atalho do admin do `RequirePermission` |
| é admin? / é o supervisor? | `empresa#administra` · `plataforma#supervisiona` | `is_tenant_admin` · `is_platform_admin` |

**A IAM escreve por reconciliação** ([`identity/pdp.py`](../iam/identity/pdp.py)): calcula o conjunto
de relações que as tabelas implicam para uma empresa e grava só a diferença. Os sinais do ORM
(papel, acesso a módulo, assinatura, usuário, módulo, empresa) a disparam no fim da transação, uma
vez por empresa; PDP fora deixa a empresa numa fila no Redis; o `iam-pdp` refaz a fila na hora e
reconcilia tudo a cada `AUTORIZACAO_SINCRONIA_PERIODO_S` (é o que faz uma assinatura vencer no PDP).
**As tabelas continuam a fonte depois da fase 4** — ver "A fonte das relações", abaixo.

**O backend pergunta num lugar só** ([`nucleo/autorizacao.py`](../backend/nucleo/autorizacao.py)):
`pode`, `usa_modulo`, `tem_na_lista`, `administra`, `supervisiona`, `permitidos`. Ler claim de acesso
fora dali é proibido por teste. Cada pergunta tem um módulo, e a tabela `ModoAutorizacao` diz quem
decide nele — o token ou o PDP ([`autorizacao_pdp.py`](../backend/nucleo/autorizacao_pdp.py), com o
cache e o modo de falha da §10.8). A resposta que não decidiu é conferida em segundo plano
([`autorizacao_sombra.py`](../backend/nucleo/autorizacao_sombra.py)) e a divergência vai para
`DivergenciaAutorizacao` (append-only, sem texto livre), com o tipo: `real`, `token_defasado` (o token
nasceu antes da última troca de acesso da empresa), `pdp_indisponivel` ou `fora_do_esquema`. Token
de serviço decide sempre pelo token.

**Os comandos de quem opera:**

| Comando | Para quê |
|---|---|
| `manage.py relatorio_pdp` (backend) | Dias com a sombra ligada, divergências por tipo e módulo, quem pode virar, e o volume de decisões por empresa e dia — a medida que a §10.9 pede para fixar a retenção |
| `manage.py modo_autorizacao [<módulo> pdp\|token]` (backend) | A virada e a volta. Virar confere o critério (sem divergência real na janela, sombra ligada a janela inteira); `--forcar` só fora de produção |
| `manage.py conferir_pdp --token <jwt>` (backend) | Todas as perguntas de um token real, token × PDP — o instrumento da E2E e de quem investiga |
| `manage.py sincronizar_pdp [--tenant <id>]` (IAM) | Reconcilia na mão; `--continuo` é o `iam-pdp` |
| `manage.py vigiar_pdp` (backend) | O `pdp-invalidador` |

**Os tetos** (relógio do PDP, fila da sombra, período da reconciliação, janela de repetição da
divergência e os dias do critério) estão na §5.5p do [`payment/planos.py`](../payment/planos.py).

**A saída da fase 2 fora de produção.** O critério de calendário (duas semanas de uso real sem
divergência real) só tem sentido onde há uso real. No desenvolvimento, a prova é a **equivalência
exaustiva** da IAM ([`identity/equivalencia.py`](../iam/identity/equivalencia.py),
`manage.py conferir_equivalencia --papeis-de-fabrica`): toda pessoa ativa, mais uma empresa
descartável com uma pessoa por papel de fábrica, com e sem liberação de módulo, e metade dos módulos
sem assinatura — cada uma com todas as perguntas, tabelas × PDP, com consistência total. A virada é
então feita com `modo_autorizacao --todos pdp --forcar`, que fica registrado em `alterado_por`.

**O drone pergunta ao PDP** ([`security/AutorizacaoService`](../funcoesODM/backend/java-service/src/main/java/com/funcoesodm/javaservice/security/AutorizacaoService.java)):
a mesma pergunta `m:drone` do backend, pelas mesmas chaves de cache e com o modo de falha da classe
A. Ele não enxerga a tabela `ModoAutorizacao`: o `modo_autorizacao` a espelha no Redis
(`authz:modo:<módulo>`). O relógio da pergunta chega a ele pelo arquivo gerado
`funcoesautorizacao/gerado/limites-drone.properties`, que o `gerar.py` tira do `planos.py` e o
compose monta em `/authz`.

#### A fase 4 — o token enxuto

**O token** leva `sub`, `tenant_id`, `user_id`, `sid`, `sst`, `amr` e `auth_time`, além das claims
padrão — cerca de 870 B na linha `Authorization` para qualquer persona, com o catálogo inteiro
([`identity/tokens.py`](../iam/identity/tokens.py) `build_claims`). As listas, os papéis, as flags
de admin, o plano e o e-mail saíram. O `/auth/me/` continua dando à tela a lista exata, lida das
tabelas (`claims_de_acesso`). O token de serviço leva só `svc`, `tenant_id` e o `modules` do produto
alvo, e decide pela claim até a fase 5 separá-lo por tipo e audiência.

**Quem decide.** Sem lista no token, o backend pergunta ao PDP em todo módulo, qualquer que seja o
modo da tabela, e o drone faz o mesmo. A sombra não roda, porque não há o que comparar. O modo por
módulo volta a valer só com a **volta atrás** (`AUTORIZACAO_TOKEN_COM_LISTAS=True` na IAM, que
reemite as listas; depois `modo_autorizacao <módulo> token` no backend, que o drone lê pelo Redis).

**A sessão (`sid`).** Cada login abre uma `Sessao` na IAM; a rotação do refresh a preserva, junto do
`auth_time`. Logout, troca de senha, desativação, reset do segundo fator e "encerrar todas" a
revogam e publicam `sess:sid:<sid>` no Redis da revogação (DB 2), com a vida de um access mais a
margem. Backend e drone conferem o `sid` a cada requisição pela regra da classe B: Redis de pé
responde na hora; Redis fora serve o que foi visto há até 5 s e depois pergunta à IAM
(`/auth/interno/sessao/<sid>/`, que o gateway não expõe); nem Redis nem IAM → **nega**. O carimbo
por época do usuário (§5.1) continua, como reforço.

**As fichas.** O que era da empresa no token (slug, nome, plano, `rate_hora`, quotas) e o e-mail da
pessoa são publicados pela IAM no Redis da autorização (`authz:ficha:empresa:<id>`,
`authz:ficha:pessoa:<id>`) no mesmo ciclo da reconciliação do PDP
([`identity/fichas.py`](../iam/identity/fichas.py)). A volta periódica reescreve todas e apaga as
órfãs. O backend as lê com cache de 30 s ([`nucleo/fichas.py`](../backend/nucleo/fichas.py)); ficha
ausente tem o comportamento de antes para a claim ausente (throttle padrão, quotas sem trava, plano
padrão).

**A auditoria de decisão** (§10.9, [`nucleo/auditoria_decisao.py`](../backend/nucleo/auditoria_decisao.py)).
Toda decisão de pessoa vai ao log `sgi.authz.decisao`, em JSON de campos fixos. As da classe C e
todas as negações vão também para `DecisaoAcesso`, gravadas por uma conexão própria (o alias
`auditoria`): na transação da requisição, a linha da negação morreria com o rollback que o DRF marca
em toda resposta de erro. A tabela é append-only no modelo e num gatilho do banco; só a purga de
hora em hora apaga, e só o que passou da janela `auditoria_decisao_retencao_dias` do plano, nunca
abaixo do piso legal de 180 dias (`AUDITORIA_DECISAO_PISO_DIAS`, que vale também contra contrato).
O drone registra as decisões dele só no log. "A relação que concedeu", que a §10.9 lista, não é
gravada: o SpiceDB só a devolve em modo de depuração, caro demais para toda decisão.

**A fonte das relações.** A §10.4 pede uma fonte só, com a IAM gravando direto no SpiceDB. A fase 4
**manteve as tabelas da IAM como fonte** e a reconciliação como escritora, pela mesma operação (fim
da transação) e com a volta periódica cobrindo o resto. A cópia existe, mas não diverge por mais que
uma volta, e a equivalência exaustiva mede exatamente isso. Trocar a fonte levaria a tela de papéis,
o `/me`, os seeds e o `sync_authz` a ler do SpiceDB, e tiraria da operação o conserto que a
reconciliação dá depois de uma queda do PDP. *(Decisão de engenharia de 25/09/2026, a confirmar pelo
dono — ver §10.14.)*

**O que da §10.6 fica para depois:** `sub` como UUID estável (hoje é o `username`, chave do espelho no
backend e no drone). `acr`, `typ: at+jwt` e `aud` por serviço vieram com a fase 5 (§10.16).

### 10.16 Como as fases 5 e 6 estão construídas

#### A fase 5 — o BFF e a audiência por serviço

**O navegador não tem token.** O login (e a segunda etapa, a troca de senha, o cadastro do segundo
fator) grava dois cookies HttpOnly e `SameSite=Strict` e devolve só identidade e o relógio da sessão:
o do **refresh** (`/auth/`, desliza a janela de inatividade, como antes) e o da **sessão**
(`sgi_sessao`, `/`; com HTTPS, `__Host-sgi_sessao`). A credencial do cookie da sessão é aleatória e
fica na `Sessao` só como hash ([`identity/sessoes.py`](../iam/identity/sessoes.py)).

**O gateway é o BFF.** Em `/api/`, `/odm-api/` e `/ws/`, o nginx faz `auth_request` a
`/auth/interno/bff/<api|drone>/` ([`identity/bff.py`](../iam/identity/bff.py)), que troca o cookie
pelo access **daquele serviço** e o devolve em `X-BFF-Authorization`; o gateway o injeta no
`Authorization`, descarta o que o cliente mandou e tira o cookie da sessão do pedido. O access fica
guardado no Redis (DB 2, `sess:bff:<hash>:<aud>`) até um minuto antes de vencer; revogar a sessão o
apaga. A IAM, que é o próprio BFF, autentica o navegador direto pelo cookie
([`identity/autenticacao.py`](../iam/identity/autenticacao.py)). IAM fora → o gateway responde 5xx:
sem sessão confirmável, nada passa.

**Escrita pelo cookie** exige o cabeçalho `X-SGI-CSRF` e, quando o navegador diz de onde vem
(`Sec-Fetch-Site`, `Origin`), a mesma origem; senão, 403 na borda. O WebSocket, que não leva
cabeçalho próprio, é decidido pelo `Origin` (CSWSH) — o drone também deixou de aceitar handshake de
qualquer origem.

**A audiência e o tipo** ([`funcoesautorizacao/audiencias.py`](../funcoesautorizacao/audiencias.py)):

| Token | `typ` | `aud` | Quem aceita |
|---|---|---|---|
| access de pessoa para o backend | `at+jwt` | `sgi-api` | backend |
| access de pessoa para o drone | `at+jwt` | `sgi-drone` | drone (REST e WebSocket) |
| access de pessoa para a IAM (testes, volta atrás) | `at+jwt` | `sgi-iam` | IAM |
| token de serviço | `svc+jwt` | o do produto de destino | só a rota do `scope` dele (hoje: desvínculo de projetos do drone) |

Quem assina é [`identity/emissao.py`](../iam/identity/emissao.py), com a chave e o `kid` do JWKS; o
SimpleJWT segue assinando só o refresh. O access ganhou `acr` (`aal1` só senha, `aal2` com segundo
fator) e `nbf`; a linha `Authorization` ficou perto de 950 B para qualquer persona.

**O SPA** ([`api/attachAuth.ts`](../frontend/src/api/attachAuth.ts)) manda o cabeçalho anti-CSRF em
toda chamada; num 401 renova a sessão pelo refresh e refaz uma vez. A renovação periódica só acontece
se houve interação — é o que fecha a janela de inatividade. **O app do drone** deixou de guardar token
no `localStorage` e de recebê-lo por URL ou `postMessage`: pergunta ao drone quem é a pessoa da sessão
e, sem sessão, volta ao login da plataforma.

**A volta atrás** (§10.12, "rota antiga mantida até o fim da fase") são duas flags da IAM, desligadas:
`BFF_ACCESS_NO_CORPO` devolve o access no corpo (válido para os três serviços) e
`BFF_BEARER_DO_CLIENTE` deixa o gateway repassar o `Authorization` do cliente.

#### A fase 6 — endurecimento

**Step-up na classe C.** Os atos críticos da lista do dono (§10.8) pedem o `auth_time` dentro da
janela que a pessoa escolheu (faixa do dono em `payment/planos.py` §5.5o). No backend a regra mora em
`autorizacao.exigir_confirmacao`, chamada **nos pontos que barram** — `RequirePermission`, o portão
do LGPD, o `_exige` do PDCA e o atesto da escada —, nunca no `pode()`, que também desenha tela. Na
IAM, mudar papel é compor persona, liberar módulo e mexer em `perfis`/`is_tenant_admin` de alguém
(`AtoGraveConfirmado`, `PapelDoUsuarioConfirmado`). A recusa é **401** com
`codigo: confirmacao_necessaria` e o `WWW-Authenticate` da RFC 9470; a janela da pessoa chega ao
backend pela ficha dela. A tela abre "Confirme que é você"
([`ConfirmacaoDialog`](../frontend/src/components/ConfirmacaoDialog.tsx)), chama `/auth/confirmar/`
— o código do app para quem tem segundo fator; a senha para quem não tem (decisão 6) — e refaz o
pedido. Código de recuperação não assina ato grave, e erro de senha conta no mesmo bloqueio do código.

**O consentimento do supervisor** ([`identity/suporte.py`](../iam/identity/suporte.py)). O PDP já
prendia o supervisor à própria empresa; a IAM não — ele via e mexia em pessoas, papéis e acessos de
todas. Agora, fora da empresa dele, só com um `ConsentimentoSuporte` vigente, que o admin concede em
Administração › Usuários por 1 a `SUPORTE_CONSENTIMENTO_MAX_DIAS` e encerra quando quiser (liberar é
ato grave; encerrar não). Duas exceções, sem as quais a empresa trancaria para sempre: criar o
primeiro admin de uma empresa que não tem nenhum, e redefinir o segundo fator de um admin — as duas
continuam na trilha e no e-mail. Conceder e encerrar viram `EventoSeguranca`.

**Testes de caos** ([`seg6_caos_test.py`](../testes/e2e/seg6_caos_test.py)): derrubam o SpiceDB, o
Redis e a IAM do dev, um de cada vez e juntos, e conferem o modo de falha da §10.8 classe a classe,
o logout com o Redis fora e a borda fechada com a IAM fora. Na primeira volta acharam que o Redis
fora parava a plataforma em vez de só deixá-la mais lenta (D221): IAM e backend com um worker
síncrono do gunicorn, operações de Redis por requisição sem disjuntor e o gateway esperando 30 s o
DNS da IAM. Hoje: gunicorn com threads, disjuntor compartilhado (revogação, PDP e throttle no
backend; BFF e sessões na IAM) e tempos curtos no gateway.

**Pentest externo** — o critério de saída da fase 6 — é contratação do dono; o escopo sugerido está
no [roadmap](roadmap.md).

