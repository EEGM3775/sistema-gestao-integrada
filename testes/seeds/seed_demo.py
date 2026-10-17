"""Seed de demonstração da IAM (Fases 2 + 6 + 8.5 + 9.A).

Tenant 'demo' com os módulos drone/erp_financeiro/crm/rh assinados, e os papéis
de fábrica provisionados (Fase 9), para exercitar as DUAS camadas de acesso:
  - Entitlement de módulo (camada 1): quem tem o módulo no token.
  - RBAC por papel/permissão (camada 2): o papel compõe permissões do catálogo
    (identity/catalog.py); o JWT passa a carregar `permissions`.

Um SEGUNDO tenant 'acme' (Fase 8.5) com o módulo drone existe só para provar o
isolamento entre tenants no drone.

Papéis de fábrica: criados por `sync_authz` a partir dos templates do catálogo
(diretoria, rh_gestor, rh_medico, rh_financeiro, financeiro, tesouraria, fiscal,
comercial, engenharia, campo, drone_analista, auditor, gestor_lixo, operacional).

Usuários:
  demo     / demo123     -> tenant demo | módulos: drone,erp,crm,rh,scm,sil,orcamento,maps,prancheta | papéis: financeiro + RH + suprimentos + almoxarife + orcamentista + topografo + projetista + gestor_contratos + tecnico_qualidade (os dois últimos SEM o verbo que aprova — ver o comentário deles)
  semdrone / semdrone123 -> tenant demo | módulos: erp_financeiro    | papel: operacional (restrito — exercita mascaramento)
  acme     / acme123     -> tenant acme | módulos: drone             | papel: operacional
  campo    / campo123    -> tenant demo | módulos: drone,prancheta,pdca | papel: campo (aponta, não resolve — PRA.3; aponta avanço, não edita o plano — PDCA.2)
  (admin e dono entram com segundo fator: o segredo TOTP da demo está no fim deste arquivo)
  dono     / dono123    -> SUPERVISOR da plataforma (is_superuser na IAM → `is_platform_admin` no token).
                          Alcança TODO módulo do catálogo, contratado ou não, e opera o que é da
                          plataforma (base-mãe, incidente ANPD). NÃO atravessa a fronteira de tenant
                          e não é chave mestra. Ver o comentário dele abaixo.

Rodar (no container):  docker compose exec -T iam python manage.py shell < testes/seeds/seed_demo.py
"""
import uuid

from django.core.management import call_command
from identity.models import (
    Tenant, Modulo, Usuario, AssinaturaTenant, AcessoUsuarioModulo, Perfil,
)

# IDs determinísticos e ESTÁVEIS dos tenants de demonstração. O backend espelha o
# tenant da IAM POR ID (nucleo.authentication._sync_tenant → get_or_create(id=<jwt.tenant_id>)):
# num ambiente greenfield (staging/prod), se o backend nascer com outro id, o 1º login
# colide em slug='demo' e responde 500. Derivar por uuid5 do MESMO nome garante o mesmo
# valor aqui e no testes/seeds/seed_demo_data.py, sem literal duplicado que possa divergir.
DEMO_TENANT_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "sgi.tenant.demo")
ACME_TENANT_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "sgi.tenant.acme")

# --- Catálogo de módulos vendáveis (global, compartilhado entre tenants) ---
modulos = {}
for cod, nome in [
    ("drone", "Mapeamento por Drone"),
    ("erp_financeiro", "ERP Financeiro"),
    ("crm", "CRM"),
    ("rh", "Recursos Humanos"),
    ("scm", "Suprimentos (SCM)"),
    ("sil", "Estoque & Logística (SIL)"),
    ("orcamento", "Orçamento de Obra"),
    ("maps", "Mapas & Território"),
    ("prancheta", "Prancheta — Projeto em Campo"),
    # PDCA.0. Comercialmente o módulo é do `empresarial` para cima
    # (payment/planos.py §5.5c); aqui ele entra porque o `demo` é o tenant onde a
    # plataforma tem de ser testável inteira — mesmo motivo de ele já ter
    # `prancheta` e `maps` sem que o `profissional` os venda.
    ("pdca", "PDCA — Planejamento & Melhoria Contínua"),
]:
    modulos[cod], _ = Modulo.objects.get_or_create(codigo=cod, defaults={"nome": nome})


def assinar(tenant, codigos):
    """A empresa contrata (assina) os módulos informados."""
    for cod in codigos:
        AssinaturaTenant.objects.get_or_create(
            tenant=tenant, modulo=modulos[cod],
            defaults={"status": AssinaturaTenant.Status.ATIVA},
        )


def upsert_user(tenant, username, password, modulos_acesso, papeis, is_admin=False):
    u, _ = Usuario.objects.get_or_create(
        username=username, defaults={"email": f"{username}@{tenant.slug}.com", "tenant": tenant}
    )
    u.tenant = tenant
    u.is_tenant_admin = is_admin
    u.set_password(password)
    u.save()
    # Acesso por usuário (subconjunto dos módulos do tenant)
    u.acessos_modulo.all().delete()
    for cod in modulos_acesso:
        AcessoUsuarioModulo.objects.get_or_create(usuario=u, modulo=modulos[cod])
    # Papéis (Perfil por tenant, já provisionados pelo sync_authz)
    perfis = list(Perfil.objects.filter(tenant=tenant, nome__in=papeis))
    u.perfis.set(perfis)
    return u


# --- Tenants (empresas) ---
# D24 — o `plano` é EXPLÍCITO desde o seed. Tenant sem plano cai no `free`
# (1 seat, 2 obras) e, com a trava de quota ligada, o dev não conseguiria criar o
# segundo usuário nem a terceira obra — a demo pareceria quebrada. Os dois seeds
# (este e o do backend) têm de concordar, pela mesma razão do D10: quando eles
# divergem, o defeito só aparece num ambiente greenfield.
#
# `demo` fica em `profissional` para exercitar o produto inteiro; `acme` fica no
# `free` de propósito, para que exista sempre um tenant onde a parede de quota é
# alcançável à mão, sem reconfigurar nada.
tenant, _ = Tenant.objects.get_or_create(
    slug="demo", defaults={"id": DEMO_TENANT_ID, "nome": "Empresa Demo", "plano": "profissional"}
)
if tenant.plano != "profissional":  # idempotente sobre banco já semeado
    tenant.plano = "profissional"
    tenant.save(update_fields=["plano"])
assinar(tenant, modulos.keys())

# --- Os extras que a demo COMPROU (D115, D153, D196 — decisão do dono, 03/10/2026) ---
# A demo continua no `profissional` e compra, além dele, o que usa: a biblioteca
# de planos modelo do PDCA (o `profissional` dá 0) e clientes acima dos 1.000 do
# plano (o `semear_carteira_demo` cria 2.000). É o mesmo caminho que o checkout
# (D24) vai gravar — `AssinaturaTenant.limites`, que vence o plano em
# `payment/regras.quota_efetiva` —, e por isso a demo é também o teste de que a
# compra de extra funciona. O `acme` (free) segue sendo a parede de quota.
# Os limites são do tenant inteiro (`Tenant.limites_contratados` funde as
# assinaturas); cada um fica na assinatura do módulo que o vende.
EXTRAS_DA_DEMO = {
    "pdca": {"planos_modelo": 25},
    "erp_financeiro": {"clientes": 5_000},
}
for cod, limites in EXTRAS_DA_DEMO.items():
    # `save()`, não `.update()`: o `post_save` é o que regrava a ficha da empresa
    # que o backend lê (identity/pdp_sinais.py). Sem ele, a compra fica no banco da
    # IAM e o backend segue cobrando o limite do plano.
    for assinatura in AssinaturaTenant.objects.filter(tenant=tenant, modulo=modulos[cod]):
        assinatura.limites = limites
        assinatura.save(update_fields=["limites"])

acme_tenant, _ = Tenant.objects.get_or_create(
    slug="acme", defaults={"id": ACME_TENANT_ID, "nome": "Empresa Acme", "plano": "free"}
)
assinar(acme_tenant, ["drone"])

# --- Catálogo de permissões + papéis de fábrica nos dois tenants (Fase 9.A) ---
call_command("sync_authz", all_tenants=True)

# --- Usuários e seus papéis ---
demo = upsert_user(
    tenant, "demo", "demo123",
    ["drone", "erp_financeiro", "crm", "rh", "scm", "sil", "orcamento", "maps",
     "prancheta", "pdca"],
    # Power-user: papéis cobrindo todos os módulos do tenant (erp, crm, obras, drone, rh, scm,
    # sil, orcamento, maps, prancheta, pdca).
    ["financeiro", "tesouraria", "fiscal", "comercial", "engenharia",
     "drone_analista", "rh_gestor", "rh_medico", "rh_financeiro", "suprimentos", "almoxarife",
     "orcamentista", "topografo", "projetista", "planejador",
     # PDCA.3. Entra no power-user porque é ele que exercita o caminho principal
     # da fatia (montar contrato, apurar medição) — e entra **sem** o poder de
     # atestar, que é a persona seguinte: o `demo` apurando e aprovando o próprio
     # boletim tornaria a segregação da §8 indemonstrável com token real.
     "gestor_contratos",
     # PDCA.7, pela mesma régua e com a mesma omissão deliberada. Ela exercita o
     # caminho principal da fatia — escrever o método da empresa, aplicar a
     # ficha, abrir a NC e montar o 5W2H — e **não** leva
     # `pdca.nc.verificar_eficacia`, que é do `gerente` (diretoria) e do
     # `fiscal_de_obra`. O `demo` consertando e assinando que o próprio conserto
     # funcionou tornaria o laço da §4.5 indemonstrável com token real, que é
     # exatamente o que o `gestor_contratos` evitou na medição.
     "tecnico_qualidade"]
    # Decisão do dono (17/10/2026): o `demo` testa tudo, sem virar admin (o admin
    # exige segundo fator). Leva TODOS os papéis de fábrica do tenant — os papéis
    # somam, então isto cobre também o que os acima omitiram de propósito.
    + list(Perfil.objects.filter(tenant=tenant).values_list("nome", flat=True)),
)
semdrone = upsert_user(tenant, "semdrone", "semdrone123", ["erp_financeiro"], ["operacional"])
# O `engenharia` aqui não é enfeite: é o único ator do seed capaz de provar a
# tese das DUAS METADES do Maps (planta §2). O tenant acme **não assina `maps`**,
# então o `sync_authz` compõe esta persona sem nenhuma permissão do módulo — e
# ela fica exatamente com `mapa.local.*`, que vive em `base`. É a demonstração de
# que georreferenciar a obra continua valendo para quem não comprou o módulo,
# enquanto camada/voo/rota ficam atrás dele. Sem este papel, o `is_tenant_admin`
# seria o único candidato, e ele herda TODOS os módulos do tenant.
#
# O mesmo ator prova, de graça, o gate da **Prancheta** (PRA.0), e prova o
# contraste: `engenharia` também declara `prancheta.documento.view`, mas o acme
# não assina `prancheta`, então a trava anti-escalada corta essa permissão e o
# acervo de projeto fecha em 403 — enquanto `mapa.local.*` sobrevive. Um módulo
# com fundação e um sem, lado a lado, com o mesmo usuário.
acme = upsert_user(acme_tenant, "acme", "acme123", ["drone"], ["operacional", "engenharia"])
# O ator do canteiro — e o único capaz de provar a segregação da PRA.3 com token
# real. A persona `campo` traz `prancheta.marcacao.view`+`.edit` e **não** traz
# `.resolver`: apontar o problema é o trabalho dele, declarar que acabou não é.
# O `demo` não serve para isso (tem `projetista`, que traz `prancheta.marcacao.*`)
# e o `admin` menos ainda (`is_tenant_admin` herda o catálogo inteiro) — é a mesma
# lição do MAP.6, onde o seed não tinha ator para separar os dois eixos do gate e
# o E2E teve de esperar um re-seed.
#
# **PDCA.2 deu a ele o segundo par.** A persona `campo` traz `pdca.avanco.apontar`
# + `pdca.cronograma.view` e **não** traz `pdca.cronograma.edit`: apontar quanto a
# frente andou é o trabalho do canteiro; mudar o plano contra o qual esse avanço é
# medido, não. Sem o módulo `pdca` aqui a camada 1 barraria antes da camada 2, e a
# segregação ficaria indemonstrável com token real — a mesma lição do MAP.6, em
# que faltou ator para separar os dois eixos do gate. O `demo` não serve de
# contraprova (tem `planejador` + `engenharia`, que editam o plano) e o `admin`
# menos ainda (herda o catálogo inteiro).
campo = upsert_user(tenant, "campo", "campo123", ["drone", "prancheta", "pdca"], ["campo"])
# **PDCA.3 precisou do terceiro par, e pelo mesmo motivo dos dois anteriores.**
# A fatia inteira gira em torno de *quem apura não ateste* (§8), e sem um ator que
# **só** ateste isso é indemonstrável com token real: o `demo` apura (tem
# `gestor_contratos`) e o `admin` herda o catálogo do tenant. Este usuário leva a
# persona `diretoria`, que é o "gerente" da §5.3 — lê contrato e medição, assina o
# degrau, e **não** monta o boletim que assina.
gerente = upsert_user(tenant, "gerente", "gerente123",
                      ["erp_financeiro", "orcamento", "pdca"], ["diretoria"])
# Admin do tenant 'demo': gere papéis/personas e permissões na tela de Administração.
admin = upsert_user(
    tenant, "admin", "admin123", ["drone", "erp_financeiro", "crm", "rh"], [], is_admin=True
)

# --- O SUPERVISOR DA PLATAFORMA -------------------------------------------
#
# **O que ele é** *(decisões do dono, 22/08/2026)*: o supervisor e o teste supremo
# do sistema. Duas frases, e elas não se contradizem:
#
#   1. **sem restrição a nenhum módulo** — alcança o catálogo inteiro, contratado
#      ou não (`modulos_efetivos` tem régua própria para ele). Um teste supremo
#      que só alcança o que alguém comprou testa a assinatura, não o produto;
#   2. **não está aqui para alterar o banco das empresas** — o que protege o
#      cliente não é tirar módulo dele, é a **fronteira de tenant** (que vale para
#      ele como para qualquer um) e o consentimento, que ainda vai existir.
#
# **O que a claim abre:** `is_superuser` aqui vira `is_platform_admin` no JWT
# (identity/tokens.py), e ela gateia operação de PLATAFORMA — carga da base-mãe
# (ORC.8), incidente ANPD (9.D), publicação de base pública pelo `impexp`. Nada
# disso é linha de empresa.
#
# **O que ela NÃO abre:** chave mestra. O `_sync_user` do backend não copia o
# flag para o espelho local, e no backend `is_superuser` fura escopo de tenant,
# RLS, `RequirePermission`, máscara de PII e quota. Ele não recebe nada disso.
#
# **Sem `is_staff`, de propósito.** No Django é ele que abre o /admin, que é a
# porta de editar dado à mão. O supervisor supervisiona **pelo produto** — testar
# por uma porta que o cliente não tem não testa o sistema.
#
# **Sem papel e sem `AcessoUsuarioModulo` na criação** porque ele não precisa: a
# régua dele não passa por nenhum dos dois. As listas vazias abaixo são o
# contrato do `upsert_user`, não uma restrição.
#
# **O tenant é endereço, não fronteira.** A IAM exige um; `demo` é onde ele mora.
# Ele coordena além dele — e a fronteira que o impede de ler OUTRA empresa vale
# para `demo` igual.
#
# Desenho completo em docs/acesso-e-permissoes.md; as duas correções do dia em
# docs/historico-correcoes.md.
dono = upsert_user(tenant, "dono", "dono123", [], [])
dono.is_superuser = True
dono.is_staff = False
dono.save(update_fields=["is_superuser", "is_staff"])

# --- Segundo fator (remodelagem, fase 1) ---
# `admin` e `dono` são OBRIGADOS a ter segundo fator (acesso-e-permissoes.md
# §10.5). Na demo eles já nascem com ele, e com um segredo CONHECIDO — pela mesma
# razão de as senhas acima serem conhecidas: é ambiente de demonstração, e os
# roteiros de testes/e2e/ precisam responder o desafio sozinhos
# (`testes/e2e/_segundo_fator.py` tem o mesmo valor). Para usar na mão, cadastre
# este segredo no app autenticador ("inserir chave de configuração", tipo por
# tempo). Rodar o seed de novo refaz o segundo fator dos dois — e apaga os
# códigos de recuperação que existiam.
from django.utils import timezone as _tz
from identity import segundo_fator as _sf
from identity.models import CodigoRecuperacao, SegundoFator

SEGREDO_TOTP_DEMO = "GXW6RXK3CRP7C6FM3L25R55B6YAE72T5"
for _u in (admin, dono):
    SegundoFator.objects.update_or_create(
        usuario=_u,
        defaults={
            "segredo_cifrado": _sf.cifrar(SEGREDO_TOTP_DEMO),
            "confirmado_em": _tz.now(),
            "ultimo_passo": 0,
        },
    )
    CodigoRecuperacao.objects.filter(usuario=_u).delete()

print("SEED OK | tenants:", tenant.slug, "+", acme_tenant.slug)
print("  demo     -> modulos:", demo.modulos_efetivos(), "| papeis:", demo.nomes_perfis())
print("            permissoes:", len(demo.permissoes_efetivas()), "codigos")
print("  admin    -> tenant_admin:", admin.is_tenant_admin, "| permissoes:", len(admin.permissoes_efetivas()))
print("  dono     -> supervisor:", dono.is_superuser,
      "| modulos:", len(dono.modulos_efetivos()), "(catalogo inteiro, sem restricao)",
      "| permissoes:", len(dono.permissoes_efetivas()),
      "| opera PLATAFORMA (base-mae, ANPD) — nao atravessa tenant")
print("  semdrone -> modulos:", semdrone.modulos_efetivos(), "| papeis:", semdrone.nomes_perfis())
print("  acme     -> modulos:", acme.modulos_efetivos(), "| papeis:", acme.nomes_perfis())
print("  campo    -> modulos:", campo.modulos_efetivos(), "| papeis:", campo.nomes_perfis(),
      "| resolve marcacao:", "prancheta.marcacao.resolver" in campo.permissoes_efetivas())
# A linha que prova a segregação da PDCA.3 no próprio seed: os dois lados
# impressos um embaixo do outro, cada um com o verbo que o outro não tem.
print("  demo     -> apura medicao:", "pdca.medicao.apurar" in demo.permissoes_efetivas(),
      "| ateste:", "pdca.medicao.atestar" in demo.permissoes_efetivas())
print("  gerente  -> modulos:", gerente.modulos_efetivos(), "| papeis:", gerente.nomes_perfis(),
      "| apura medicao:", "pdca.medicao.apurar" in gerente.permissoes_efetivas(),
      "| ateste:", "pdca.medicao.atestar" in gerente.permissoes_efetivas())
