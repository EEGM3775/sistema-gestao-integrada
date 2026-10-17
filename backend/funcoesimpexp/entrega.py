# backend/funcoesimpexp/entrega.py
"""IE.3b — a saída de um arquivo do acervo, pela porta única.

**A régua ficou maior do que a R17 escrita** (decisão do dono, 08/08/2026): o
`funcoesimpexp` é o único meio de importação e exportação do projeto, e isso
inclui **download**, não só upload. A R17 tratava da entrada — *"toda outra
entrada de arquivo sai e passa para cá"* — e a saída seguia sendo de cada módulo.

O preço disso estava à vista em [`moduloprancheta/entrega.py`](../moduloprancheta/entrega.py),
que reimplementava sozinha quatro guarda-corpos: `nosniff`, `attachment`, o
`Content-Type` decidido por nós e o saneamento do nome. Todos certos — e todos
uma segunda cópia, que é exatamente a forma do [D75](../../docs/historico-correcoes.md) do
lado da entrada. Este arquivo é a promoção deles, no mesmo movimento que levou o
orçamento de recurso do D57 para [`nucleo/orcamento.py`](../nucleo/orcamento.py).

**O que a porta de saída garante, para todo módulo, sem que ele escreva nada:**

1. **O `Content-Type` sai do recurso, não do nome do arquivo.** `nome_original` é
   texto que veio do cliente; deixar o `mimetypes` adivinhar por ele daria a quem
   enviou o poder de escolher como o browser interpreta o próprio upload.
2. **Nada é servido como página.** Tudo vai com `nosniff` e `attachment` —
   inclusive SVG, que é documento executável. Quem decide exibir é a tela, que o
   carrega por `fetch`+blob dentro de `<img>`, onde script não roda. Sem isso um
   DXF com `<script>` no texto viraria XSS na nossa origem **depois** de passar
   pelo nosso próprio conversor. Isto é guarda-corpo, não knob: nenhum recurso
   pode pedir `inline`.
3. **Cache é declarado pelo recurso, e o padrão não promete nada.** `immutable`
   só é verdade quando a URL identifica o conteúdo; quem não puder garantir isso
   fica com `no-store`. A lição é o [D51](../../docs/historico-correcoes.md): a
   derivada era reescrita a cada reconversão sob `immutable` de um ano, e o
   conserto do D46 ficou invisível na tela depois de aplicado no servidor.
4. **O ato entra na trilha quando é dado do cliente saindo** (R12/D67), e não
   quando é a plataforma lendo o que ela mesma gerou — a mesma distinção que a
   R17 já faz na entrada entre importação e registro.
"""
from __future__ import annotations

import logging
import os
import re

from django.http import FileResponse
from django.urls import reverse

from .registro import RASTRO_AUDITADO, ArquivoEntregue, EntregaInvalida, Recurso

logger = logging.getLogger(__name__)

#: Um ano — o teto prático de `max-age`. Só vale para URL que carrega a
#: identidade do conteúdo (a versão da derivada, o id de uma revisão write-once).
CACHE_IMUTAVEL = "private, max-age=31536000, immutable"

#: O padrão. Quem não declarou cache não prometeu nada, e prometer errado aqui
#: custa um conserto invisível por um ano.
CACHE_NENHUM = "private, no-store"

TIPO_GENERICO = "application/octet-stream"

_NOME_LIMPO = re.compile(r"[^\w.\- ]+")


def nome_para_download(nome: str, *, alternativa: str = "arquivo") -> str:
    """Nome de arquivo sem caminho e sem caractere de controle.

    O `FileResponse` já faz o *quoting* do RFC 6266, mas separador de caminho e
    afins não são problema de codificação: são nome de arquivo mentindo sobre
    onde mora. E o nome quase sempre nasceu num upload, o que o torna texto de
    terceiro mesmo quando o recurso o repassa de boa-fé.
    """
    base = os.path.basename(nome or "")
    limpo = _NOME_LIMPO.sub("_", base).strip() or alternativa
    return limpo[:120]


def servir(entregue: ArquivoEntregue) -> FileResponse:
    """O `FileField` como anexo, com o tipo que NÓS determinamos.

    Levanta `FileNotFoundError` quando o registro existe e o binário não — volume
    trocado, expurgo, derivada ainda convertendo. Quem chama traduz para 404: é
    problema nosso, mas não é 500 com traceback, e o suporte precisa distinguí-lo
    de "o cliente não tem acesso".
    """
    if not entregue.campo:
        raise FileNotFoundError("Esta linha não tem arquivo.")

    arquivo = entregue.campo.open("rb")
    resposta = FileResponse(
        arquivo,
        content_type=entregue.tipo or TIPO_GENERICO,
        as_attachment=True,
        filename=nome_para_download(entregue.nome),
    )
    # `nosniff` importa mesmo com o tipo correto: sem ele o browser pode ignorar
    # o `Content-Type` declarado e reinterpretar o conteúdo — que é justamente o
    # que a decisão (2) do topo evita.
    resposta["X-Content-Type-Options"] = "nosniff"
    resposta["Cache-Control"] = entregue.cache or CACHE_NENHUM
    return resposta


def auditar(recurso: Recurso, entregue: ArquivoEntregue, *, usuario, especie: str) -> None:
    """A R12 valendo para o binário — quando ele é dado do cliente saindo.

    Reusa `EXPORTAR_DADOS` em vez de criar uma ação nova, e é a leitura certa: do
    ponto de vista da LGPD o evento é o mesmo — informação deixando o perímetro
    —, e uma ação separada obrigaria todo relatório de auditoria a somar duas.

    `detalhes` sem PII, como manda o modelo: o recurso, a espécie pedida e o
    tamanho. Nome de arquivo **não entra** — `TorreA/ARQ/laudo-fulano.pdf` é
    conteúdo, e a trilha não pode recriar em texto puro o que a 9.C mascara.
    """
    if entregue.rastro != RASTRO_AUDITADO:
        return

    from nucleo.auditoria import registrar_auditoria
    from nucleo.models import AuditLog

    registrar_auditoria(
        acao=AuditLog.Acao.EXPORTAR_DADOS,
        instance=entregue.objeto,
        usuario=usuario,
        detalhes={
            "recurso": recurso.id,
            "especie": especie,
            "entrega": True,
            "bytes": _tamanho(entregue.campo),
        },
    )


def _tamanho(campo) -> int | None:
    """`size` do `FileField`, ou `None` se o armazenamento não responder.

    Vai num try porque `size` **toca o storage**, e a auditoria não pode ser o
    lugar onde um volume fora do ar derruba um download que já deu certo. O
    princípio é o do `registrar_auditoria`: a trilha nunca derruba o ato que ela
    registra — e aqui o ato já foi entregue.
    """
    try:
        return campo.size
    except Exception:  # noqa: BLE001 — storage pode falhar de muitas formas
        return None


# ---------------------------------------------------------------------------
# D70 — o que todo módulo precisa para ter porta, e ninguém deve reescrever
# ---------------------------------------------------------------------------
#
# As três funções abaixo nasceram dentro do `moduloprancheta` e subiram para cá
# quando os **nove** prefixos de `/media/` da allowlist do D70 precisaram do
# mesmo trio. Deixá-las lá e copiá-las nove vezes seria repetir o
# [D75](../../docs/historico-correcoes.md) num terceiro lugar: guarda-corpo
# duplicado é guarda-corpo que diverge — e o que diverge aqui é escopo de tenant
# e tipo declarado, não formatação.


def url_do_arquivo(recurso_id: str, especie: str, chave) -> str:
    """`/api/impexp/<recurso>/arquivo/<espécie>/<chave>/` — a URL que o JSON publica.

    Caminho **completo** e não relativo à raiz da API: o que sai daqui tem de
    funcionar como está contra o gateway, sem o cliente remontar prefixo.
    """
    return reverse("impexp_entregar", args=[recurso_id, especie, str(chave)])


def buscar_do_tenant(modelo, chave, tenant_id, *, campo_pk: str = "pk"):
    """Busca escopada por tenant, com a chave validada antes de virar consulta.

    **A checagem de tenant não é formalidade mesmo com RLS armada.** A RLS
    protege a consulta; ela não escolhe o que consultar, e um `filter(pk=...)`
    sem tenant devolveria `None` no melhor caso e dependeria da RLS no pior —
    depender é o que a planta chama de fail-open silencioso.

    `chave` vem da URL como texto. Um id não-numérico é `EntregaInvalida` (404) e
    não um `ValueError` que viraria 500: quem monta URL à mão não merece
    traceback, merece "não encontrei".
    """
    try:
        pk = int(chave)
    except (TypeError, ValueError):
        raise EntregaInvalida("Identificador inválido.") from None
    obj = modelo.objects.filter(**{campo_pk: pk, "tenant_id": tenant_id}).first()
    if obj is None:
        raise EntregaInvalida("Não encontrado neste tenant.")
    return obj


#: Extensão → MIME que **nós** declaramos ao servir. Mapa **fechado**: o que não
#: estiver aqui sai como genérico, e não como o que o nome sugerir.
#:
#: **Ele não contradiz a decisão (1) do topo, e a distinção importa.** Aquela
#: regra proíbe deixar o `mimetypes` adivinhar por um nome de terceiro — o
#: espaço de resposta seria o do sistema operacional inteiro, e quem enviou
#: escolheria como o browser interpreta o próprio upload. Aqui o espaço de
#: resposta é esta lista, que é nossa, curta e revisável: o pior que um nome
#: hostil consegue é ser servido como um dos tipos abaixo — todos como
#: `attachment` e com `nosniff`, porque nenhum recurso pode pedir `inline`.
#:
#: **Por que o mapa existe:** os nove modelos do D70 são anteriores à porta
#: única e **não guardam formato declarado** (a Prancheta guarda: sua entrada
#: carimba `formato` pela assinatura de bytes, e por isso ela usa
#: `tipo_do_formato`, não isto). Enquanto a entrada deles não passar pela R17, a
#: extensão é a única identidade que o acervo tem — e o genérico para todos
#: custaria a miniatura da foto do diário sem comprar segurança nenhuma.
TIPO_POR_EXTENSAO: dict[str, str] = {
    ".svg": "image/svg+xml",
    ".glb": "model/gltf-binary",
    ".gltf": "model/gltf+json",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
    ".xml": "application/xml",
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def tipo_por_extensao(nome: str) -> str:
    return TIPO_POR_EXTENSAO.get(os.path.splitext(nome or "")[1].lower(), TIPO_GENERICO)


def entregar_campo(
    objeto,
    campo,
    *,
    alternativa: str = "arquivo",
    rastro: str = RASTRO_AUDITADO,
    cache: str = "",
) -> ArquivoEntregue:
    """O `ArquivoEntregue` de um `FileField` herdado do v01 — as três decisões juntas.

    Os nove prefixos do **D70** repetem exatamente as mesmas três escolhas, e
    escrevê-las seis vezes seria seis lugares de onde uma pode sumir:

    1. **tipo pela extensão, do mapa fechado** — estes modelos não guardam
       formato declarado (ver `TIPO_POR_EXTENSAO`);
    2. **`RASTRO_AUDITADO` por padrão** — são arquivos do cliente saindo do
       perímetro, que é a definição do R12. Quem for exceção declara, e a
       declaração fica no código do módulo, revisável;
    3. **cache `no-store`** (o padrão do motor). `immutable` só é verdade quando
       a URL identifica o conteúdo, e aqui não identifica: substituir o PDF
       reescreve o mesmo campo sob o mesmo id. Prometer imutabilidade guardaria
       o documento vencido no navegador de quem o abriu — o
       [D51](../../docs/historico-correcoes.md) com um agravante de LGPD, porque
       o que ficaria em cache é holerite e atestado de saúde.

    `EntregaInvalida` quando a linha existe e o campo está vazio: é o 404 honesto
    do gancho, e não o 500 que um `FileField` falso produziria adiante.
    """
    if not campo:
        raise EntregaInvalida("Esta linha não tem arquivo.")
    nome = campo.name or alternativa
    return ArquivoEntregue(
        campo=campo,
        nome=nome,
        tipo=tipo_por_extensao(nome),
        objeto=objeto,
        rastro=rastro,
        cache=cache,
    )


class ArquivoGateadoSerializerMixin:
    """Publica o arquivo pela porta única em vez de `/media/` (D70).

    **O que ele conserta é o JSON, e o JSON era o vazamento.** Um serializer com
    `fields = "__all__"` transforma todo `FileField` na URL de `/media/`, e o
    ASO — dado de saúde, LGPD art. 11 — saía assim: o mascaramento da 9.C
    escondia o *valor* na ficha e o mesmo payload entregava o endereço do PDF que
    o contém, fora de auth, de entitlement e da RLS, num caminho que nem tenant
    carrega. Fechar só o gateway deixaria a URL morta no payload; fechar só o
    payload deixaria a porta dos fundos aberta. São as duas metades do mesmo
    achado.

    **Por que reescrever a representação em vez de declarar um campo próprio.**
    Trocar o `FileField` por um campo customizado obrigaria cada serializer a
    redeclarar `required`/`allow_null` à mão, e essa cópia é que sairia do lugar
    quando o modelo mudasse — o upload passaria a exigir arquivo onde o banco
    aceita nulo, e ninguém veria até o primeiro 400. Aqui a **escrita continua
    exatamente a que era** (o campo do `ModelSerializer`, com a validação do
    `UploadValidationMixin` por cima) e só a leitura muda de endereço.

    Uso — o módulo declara o que já sabe, e nada mais::

        class ASOFuncionarioSerializer(ArquivoGateadoSerializerMixin, ...):
            arquivos_gateados = {"arquivo": (RECURSO_ASO, "aso")}

    A chave da URL é sempre o `pk` da linha: é o que o `entregar_arquivo` do
    recurso recebe de volta e refiltra por tenant.
    """

    #: `campo do serializer -> (id do recurso, espécie)`.
    arquivos_gateados: dict[str, tuple[str, str]] = {}

    def to_representation(self, instance):
        dados = super().to_representation(instance)
        for campo, (recurso_id, especie) in self.arquivos_gateados.items():
            # Só troca o que existe: campo vazio continua vazio, e um `None` não
            # pode virar link para um arquivo que não há.
            if dados.get(campo):
                dados[campo] = url_do_arquivo(recurso_id, especie, instance.pk)
        return dados
