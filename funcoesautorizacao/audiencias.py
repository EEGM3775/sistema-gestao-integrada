"""Para quem é o token e de que tipo ele é — fase 5 da remodelagem (§10.6).

Até a fase 4 todo token tinha o mesmo `aud` (`sgi`): o emitido para o backend
valia no drone, e o de serviço tinha a mesma audiência do de pessoa (§10.1).
Agora cada serviço aceita só o que foi emitido **para ele**, e o `typ` do
cabeçalho separa a pessoa do serviço (RFC 9068 · RFC 8725 §3.11):

| Quem valida | `aud` que exige | `typ` que aceita |
|---|---|---|
| backend (`/api/`) | `sgi-api` | `at+jwt` |
| drone (`/odm-api/`, `/ws/`) | `sgi-drone` | `at+jwt`; `svc+jwt` só na rota de serviço |
| IAM (`/auth/`, `/iam/`) | `sgi-iam` | `at+jwt` (o navegador entra pelo cookie) |

O drone (Java) não importa este módulo: os mesmos valores estão no
`application.properties` dele, e o teste da IAM cobra que batem.
"""
from __future__ import annotations

EMISSOR = "sgi-iam"

API = "sgi-api"
DRONE = "sgi-drone"
IAM = "sgi-iam"

#: As audiências que o BFF (o gateway) pede à IAM, pelo trecho da URL interna.
DO_BFF = {"api": API, "drone": DRONE}

TIPO_PESSOA = "at+jwt"
TIPO_SERVICO = "svc+jwt"

#: O token de serviço diz o que pode fazer em `scope` (RFC 8693 §4.2), e só isto.
ESCOPO_DESVINCULAR_PROJETOS = "drone.projetos.desvincular"

#: O que o pedido de token de serviço aceita em `audience`: o nome curto do
#: produto (como o backend sempre pediu) → a audiência e o escopo que ele leva.
SERVICOS = {
    "drone": (DRONE, ESCOPO_DESVINCULAR_PROJETOS),
}
