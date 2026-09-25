"""O schema do PDP, gerado do catálogo de permissões — e os nomes que ligam os dois.

**O catálogo `modulo.recurso.acao` continua sendo o vocabulário**
(docs/acesso-e-permissoes.md §10.4). Este módulo o traduz, de forma
determinística, para o schema do SpiceDB, e a IAM cobra por teste que o arquivo
gerado em `gerado/` é exatamente o que o catálogo de hoje produz: código no
catálogo sem permissão no schema, ou o contrário, quebra a esteira.

**Por que um tipo por módulo, e não um `empresa` com 228 permissões.** O que um
módulo vendável acrescenta à pergunta é o entitlement — "a empresa assina, e a
pessoa foi liberada" —, e isso é uma permissão `usa` do próprio módulo. Com um
tipo por módulo, toda permissão do módulo é ``usa & concessão``, escrito uma vez
e lido no lugar. Cada objeto de módulo é um por empresa, com o id da empresa.

**O que o schema reproduz, e por que exatamente isso.** A fase 2 é sombra: o PDP
tem de responder **o mesmo** que o token responde hoje, pergunta por pergunta,
para que "zero divergência" signifique alguma coisa. Então cada permissão é a
tradução literal da regra em vigor (`Usuario.permissoes_efetivas` e
`modulos_efetivos` na IAM, `RequirePermission` no backend):

- **admin do tenant** passa em todo código, assinado ou não — é o *bypass* do
  `RequirePermission`; o que o barra fora do módulo é o `usa`, que é outra
  pergunta (a do `RequireModule`);
- **supervisor da plataforma** recebe todo código de módulo que existe no
  catálogo de módulos da IAM, assinado ou não (decisão do dono, 22/08/2026);
- **os demais** precisam de um papel que conceda o código **e**, se o código é
  de módulo vendável, de usar o módulo.

Mudar essa semântica (por exemplo, prender o admin ao entitlement também no
código) é decisão de desenho, e acontece depois da virada — nunca escondida
dentro da sombra.
"""
from __future__ import annotations

import json
import re
from typing import Iterable

#: Módulos do catálogo que não são vendáveis: não têm entitlement.
MODULOS_DE_FUNDACAO = ("base", "plataforma")

#: Módulos que o backend exige por `required_module` e que ainda não têm código
#: no catálogo. Sem um tipo no schema, a pergunta "usa?" seria erro no PDP em vez
#: de "não". O teste do backend cobra que todo `required_module` está no schema.
MODULOS_SEM_CODIGO = ("dms",)

#: Objeto único da plataforma — o supervisor não é de empresa nenhuma.
ID_PLATAFORMA = "sgi"

_IDENTIFICADOR = re.compile(r"^[a-z][a-z0-9_]{1,62}[a-z0-9]$")


def tipo_do_modulo(modulo: str) -> str:
    return f"modulo_{modulo}"


def permissao_do_codigo(codigo: str) -> str:
    """``pdca.contrato.view`` → ``pdca__contrato__view``.

    O ponto vira dois sublinhados, e não um: ``erp.conta_pagar.view`` e um
    hipotético ``erp.conta.pagar_view`` virariam o mesmo nome com um só. O
    catálogo nunca usa ``__`` (cobrado por teste), então a volta é unívoca.
    """
    return codigo.replace(".", "__")


def relacao_de_concessao(codigo: str) -> str:
    return "concede_" + permissao_do_codigo(codigo)


def id_do_papel(tenant_id: str, perfil_id: int | str) -> str:
    """O papel carrega o tenant no prefixo: a reconciliação lê e apaga por prefixo,
    e o invalidador tira o tenant de qualquer id sem consultar banco."""
    return f"{tenant_id}_p{perfil_id}"


def tenant_do_id(id_objeto: str) -> str:
    """O tenant de um id de objeto (empresa, módulo ou papel)."""
    return id_objeto.split("_", 1)[0]


def identificador_valido(nome: str) -> bool:
    return bool(_IDENTIFICADOR.match(nome))


def modulos_vendaveis(catalogo: Iterable) -> list[str]:
    """Os módulos com entitlement: os do catálogo mais os que só têm tela."""
    vistos = {p.modulo for p in catalogo if p.modulo not in MODULOS_DE_FUNDACAO}
    return sorted(vistos | set(MODULOS_SEM_CODIGO))


def gerar_esquema(catalogo: Iterable) -> str:
    """Texto do schema, determinístico (mesma entrada, mesmos bytes)."""
    catalogo = list(catalogo)
    por_modulo: dict[str, list[str]] = {}
    for p in catalogo:
        por_modulo.setdefault(p.modulo, []).append(p.code)

    linhas = [
        "// GERADO a partir de iam/identity/catalog.py — não editar à mão.",
        "// Regerar: python funcoesautorizacao/gerar.py  (a IAM cobra por teste).",
        "// Desenho: docs/acesso-e-permissoes.md §10.7.",
        "",
        "definition usuario {}",
        "",
        "definition plataforma {",
        "    relation supervisor: usuario",
        "    permission supervisiona = supervisor",
        "}",
        "",
        "definition empresa {",
        "    relation administrador: usuario",
        "    relation supervisor: usuario",
        "    relation membro: usuario",
        "    permission administra = administrador",
        "}",
        "",
        "definition papel {",
        "    relation empresa: empresa",
        "    relation portador: usuario",
        "}",
    ]

    for modulo in MODULOS_DE_FUNDACAO:
        codigos = sorted(por_modulo.get(modulo, []))
        linhas += ["", f"definition {tipo_do_modulo(modulo)} {{", "    relation empresa: empresa"]
        for c in codigos:
            linhas.append(f"    relation {relacao_de_concessao(c)}: papel#portador")
        for c in codigos:
            linhas.append(
                f"    permission {permissao_do_codigo(c)} = empresa->administrador"
                f" + empresa->supervisor + {relacao_de_concessao(c)}"
            )
        linhas.append("}")

    for modulo in modulos_vendaveis(catalogo):
        codigos = sorted(por_modulo.get(modulo, []))
        linhas += [
            "",
            f"definition {tipo_do_modulo(modulo)} {{",
            "    relation empresa: empresa",
            # `catalogado` só existe quando o módulo está no catálogo de módulos
            # da IAM (a tabela `Modulo`) — é a régua do supervisor.
            "    relation catalogado: empresa",
            # `assinatura` só existe enquanto a assinatura está ativa hoje.
            "    relation assinatura: empresa",
            "    relation liberado: usuario",
            "    permission usa = catalogado->supervisor + assinatura->administrador"
            " + (liberado & assinatura->membro)",
        ]
        for c in codigos:
            linhas.append(f"    relation {relacao_de_concessao(c)}: papel#portador")
        for c in codigos:
            linhas.append(
                f"    permission {permissao_do_codigo(c)} = empresa->administrador"
                f" + catalogado->supervisor + (usa & {relacao_de_concessao(c)})"
            )
        linhas.append("}")

    return "\n".join(linhas) + "\n"


def gerar_catalogo(catalogo: Iterable, classe_de) -> str:
    """O mapa código → módulo e classe, que o backend lê (ele não tem o catálogo).

    `classe_de` é `funcoesautorizacao.classes.classe_do_codigo` — passada por
    parâmetro para este arquivo não importar a política.
    """
    catalogo = list(catalogo)
    dados = {
        "codigos": {
            p.code: {"modulo": p.modulo, "classe": classe_de(p.code)}
            for p in sorted(catalogo, key=lambda p: p.code)
        },
        "modulos_vendaveis": modulos_vendaveis(catalogo),
        "modulos_de_fundacao": list(MODULOS_DE_FUNDACAO),
    }
    return json.dumps(dados, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def gerar_limites_do_drone(pdp_timeout_ms: int) -> str:
    """O relógio do PDP para o PEP do drone, em formato de propriedades do Spring.

    O valor é do dono e mora no `payment/planos.py` (§5.5p); o compose monta este
    arquivo no contêiner do drone, e o Spring o lê por `spring.config.import`.
    """
    return (
        "# GERADO de payment/planos.py — não editar à mão.\n"
        "# Regerar: python funcoesautorizacao/gerar.py  (a IAM cobra por teste).\n"
        f"authz.spicedb.timeout-ms={int(pdp_timeout_ms)}\n"
    )


def tipos_do_esquema(catalogo: Iterable) -> list[str]:
    """Todos os tipos de objeto que a reconciliação precisa ler e apagar."""
    catalogo = list(catalogo)
    return (
        ["plataforma", "empresa", "papel"]
        + [tipo_do_modulo(m) for m in MODULOS_DE_FUNDACAO]
        + [tipo_do_modulo(m) for m in modulos_vendaveis(catalogo)]
    )
