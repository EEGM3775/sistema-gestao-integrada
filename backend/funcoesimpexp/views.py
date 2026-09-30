# backend/funcoesimpexp/views.py
"""IE.0 — a API. Um conjunto de endpoints só, para todo recurso de todo módulo.

Nenhuma view aqui conhece domínio: o `recurso` vem na URL, o registry resolve e
os motores fazem o trabalho. Um módulo novo ganha import e export **sem tocar
neste arquivo** — que é o ponto do desenho.

Toda view arma a RLS pelo `TenantScopedAPIViewMixin` (a lição do **S1**: `APIView`
pura não escopa nada sozinha) e passa pelo gate do §3 antes de qualquer trabalho.
"""
from __future__ import annotations

import json

from django.db import transaction
from django.http import FileResponse, HttpResponse
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from nucleo.tenancy import TenantScopedAPIViewMixin

from . import entrega as motor_entrega
from . import exportacao as motor_exportacao
from . import importacao as motor_importacao
from .acesso import exigir_acesso_total, exigir_entrega, recursos_permitidos
from .limites import (
    FORMATOS_POR_CODIGO,
    ArquivoGrandeDemais,
    FormatoDesconhecido,
    FormatoNaoContratado,
    limites_do_plano,
    teto_do_formato,
    validar_entrada,
)
from .models import Exportacao, Importacao, MapaColunas
from .modelo import nome_do_modelo, planilha_modelo
from .registro import (
    ArquivoRecebido,
    ContextoInvalido,
    EntregaInvalida,
    RecursoDesconhecido,
    listar,
    obter,
)


class _Base(TenantScopedAPIViewMixin, APIView):
    permission_classes = [IsAuthenticated]

    def recurso(self, recurso_id: str, contexto: dict | None = None, *, validar=False,
                escrita: bool = False):
        """Resolve o recurso, aplica o gate do §3 e o amarra ao destino.

        Nesta ordem, sempre: quem não pode operar o recurso não deve nem chegar a
        descobrir se o destino que pediu existe.

        `escrita=True` no que GRAVA no destino (importar, aplicar, desfazer,
        remapear): soma o entitlement do módulo ao conjunto de permissões.
        """
        try:
            recurso = obter(recurso_id)
        except RecursoDesconhecido:
            raise NotFound(f"Recurso '{recurso_id}' não existe.")
        exigir_acesso_total(self.request.user, recurso, escrita=escrita)
        if validar:
            try:
                contexto = recurso.validar_contexto(
                    contexto or {}, self.request.user, self.tenant_id,
                )
            except ContextoInvalido as exc:
                raise ValidationError({"contexto": str(exc)})
        # **O tenant entra no contexto sempre** (R19). Os ganchos declarativos
        # que consultam o banco do módulo — hoje o `opcoes_da_coluna`, que lista o
        # vocabulário do cliente para a conferência oferecer — precisam saber de
        # quem é o acervo, e o recurso é uma instância única por processo, sem
        # request. Injetar aqui é o mesmo raciocínio do `tiers` no lote: o dado
        # vem do request, e o gancho roda onde request não existe.
        #
        # **Como texto**: o contexto é persistido em `Importacao.contexto`, que é
        # JSON, e `UUID` não serializa. O ORM aceita a string no filtro.
        return recurso.com_contexto({
            **(contexto or {}),
            "tenant_id": str(self.tenant_id) if self.tenant_id else None,
        })

    def separar_contexto(self, recurso, params: dict) -> tuple[dict, dict]:
        """Query params → `(contexto, recorte)`.

        O que o recurso declarou como destino é contexto; **todo o resto é recorte
        da tela** (R7). Sem essa separação, `banco=12` entraria no cabeçalho de
        procedência como se fosse um filtro que a pessoa escolheu — e o leitor do
        arquivo concluiria que faltam linhas.
        """
        chaves = set(recurso.contexto_requerido or ())
        contexto = {k: v for k, v in params.items() if k in chaves}
        recorte = {k: v for k, v in params.items() if k not in chaves}
        return contexto, recorte

    @property
    def tenant_id(self):
        return getattr(getattr(self.request.user, "tenant", None), "id", None)

    @property
    def usuario_nome(self) -> str:
        user = self.request.user
        return (getattr(user, "get_full_name", lambda: "")() or getattr(user, "username", "") or "")

    @property
    def limites(self):
        return getattr(self.request.user, "iam_quotas", None)

    def teto_serializavel(self) -> dict:
        """O orçamento de recurso do plano como JSON, para viajar na task.

        No `_Base` porque dois caminhos precisam do mesmo — o upload que vira job
        e o `remapear`, que relê o mesmo arquivo. Duas cópias divergiriam na
        primeira vez que um terceiro número entrasse no orçamento.

        Resolvido no REQUEST e não no worker, de propósito: é aqui que existe o
        token com a claim `plano`. Recalcular lá exigiria carregar o usuário —
        e `RequisicaoDiferida` já registra que o worker não tem request.
        """
        teto = limites_do_plano(self.request.user)
        return {
            "memoria_mb": teto.memoria_mb,
            "segundos": teto.segundos,
            "plano": teto.plano,
        }

    def _de_para(self, request) -> dict | None:
        """De-para vindo à mão ou de um mapa salvo (R4).

        No `_Base` porque dois caminhos precisam do mesmo: o upload inicial e o
        `remapear` do lote que ficou esperando. Duas cópias divergiriam na
        primeira vez que o formato do mapa mudasse.
        """
        mapa_id = request.data.get("mapa")
        if mapa_id:
            salvo = self.scope_qs(MapaColunas.objects.all()).filter(pk=mapa_id).first()
            if salvo is None:
                raise ValidationError({"mapa": "Mapa de colunas não encontrado."})
            return salvo.mapa
        return _json_do_form(request.data.get("de_para") or None, "de_para")

    def importacao(self, importacao_id: int) -> Importacao:
        """Sempre pelo queryset escopado — id de outro tenant tem de dar 404, não 403."""
        obj = self.scope_qs(Importacao.objects.all()).filter(
            importacao_id=importacao_id,
        ).first()
        if obj is None:
            raise NotFound("Importação não encontrada.")
        return obj


def _arquivo(conteudo: bytes, content_type: str, nome: str) -> HttpResponse:
    return _blindar(
        HttpResponse(conteudo, content_type=content_type), nome,
    )


def _blindar(resposta, nome: str):
    """`attachment` + `nosniff` em toda saída de arquivo.

    O `attachment` já estava; o `nosniff` faltava, e o par é o padrão que a
    PRA.2 fixou na porta de leitura da Prancheta. Sem ele o navegador pode
    ignorar o `Content-Type` que declaramos e decidir pelo conteúdo — e o dia em
    que um recurso exportar em formato que o navegador saiba renderizar, o
    arquivo passa a executar na nossa origem em vez de baixar.
    """
    resposta["Content-Disposition"] = f'attachment; filename="{nome}"'
    resposta["X-Content-Type-Options"] = "nosniff"
    return resposta


def _json_do_form(valor, campo: str):
    """Campo JSON dentro de um multipart chega como texto."""
    if not isinstance(valor, str):
        return valor
    try:
        return json.loads(valor)
    except ValueError:
        raise ValidationError({campo: "JSON inválido."})


# ---------------------------------------------------------------------------
# Catálogo — o que esta pessoa pode importar/exportar
# ---------------------------------------------------------------------------


class RecursosView(_Base):
    """Alimenta a decisão do frontend de mostrar ou sumir com o botão (§10).

    Devolve **só o que a pessoa pode operar**: botão que aparece e dá 403 no
    clique é pior que botão ausente — ensina o usuário a desconfiar da tela.
    """

    def get(self, request):
        permitidos = recursos_permitidos(request.user, listar())
        limites = limites_do_plano(request.user)
        return Response({
            # `com_contexto` com o tenant: o catálogo publica as opções das
            # colunas editáveis, e elas são do cliente (ver `_Base.recurso`).
            "recursos": [
                self._descrever(
                    r.com_contexto(
                        {"tenant_id": str(self.tenant_id) if self.tenant_id else None},
                    ),
                    limites,
                )
                for r in permitidos
            ],
            # O teto e a lista de formatos vão JUNTO do catálogo, e não escondidos
            # atrás de um erro: é a terceira parte do método do assinador gov.br
            # (a tela diz "até 100 MB, nestes formatos" antes de a pessoa
            # escolher o arquivo). Descobrir o limite no 402 depois de esperar o
            # upload de 40 MB é a experiência que este campo evita.
            "limites": limites.descrever(),
        })

    @staticmethod
    def _descrever(recurso, limites) -> dict:
        """A declaração do recurso + o teto que a PORTA DELE vai aplicar (D83).

        **O `limites` global não serve a recurso de arquivo, e isso não é
        detalhe de layout.** O teto de um formato de arquivo é do **recurso** —
        o mesmo PDF é planilha de preço no Orçamento e prancha de 100 MB na
        Prancheta —, e `Limites.descrever()`, que não conhece recurso nenhum,
        só sabe publicar o número do plano. Resultado: o catálogo anunciava
        25 MB para DWG enquanto a porta aceitava 150.
        A tela que acreditou no anúncio recusou sozinha um arquivo bom.

        O conserto é publicar aqui o resultado de `teto_do_formato` — **a mesma
        função que a porta chama** —, e não uma segunda conta parecida. Duas
        contas voltariam a divergir; o ponto é que exista uma só.
        """
        dados = recurso.descrever()
        if recurso.de_arquivo:
            dados["tetos_mb"] = {
                codigo: teto_do_formato(recurso, FORMATOS_POR_CODIGO[codigo], limites)
                for codigo in recurso.formatos_arquivo
                if codigo in FORMATOS_POR_CODIGO
            }
        return dados


# ---------------------------------------------------------------------------
# Exportação
# ---------------------------------------------------------------------------


class ExportarView(_Base):
    def get(self, request, recurso_id: str):
        formato = request.query_params.get("formato", "xlsx")
        recurso = self.recurso(recurso_id)
        contexto, recorte = self.separar_contexto(
            recurso, {k: v for k, v in request.query_params.items() if k != "formato"},
        )
        recurso = self.recurso(recurso_id, contexto, validar=True)
        try:
            if motor_exportacao.vale_a_pena_job(recurso, request, recorte):
                lote = motor_exportacao.abrir_lote(
                    recurso=recurso, formato=formato, recorte=recorte,
                    tenant_id=self.tenant_id, usuario_nome=self.usuario_nome,
                )
                from .tasks import gerar_exportacao

                # Depois do commit (D217): na transação da requisição, o worker
                # podia pegar o job antes de o lote existir para ele.
                usuario_id = getattr(request.user, "pk", None)
                transaction.on_commit(
                    lambda: gerar_exportacao.delay(lote.pk, self.tenant_id, usuario_id)
                )
                # 202: o arquivo ainda não existe. A tela acompanha por
                # `exportacoes/<id>/` e baixa quando ficar pronta.
                return Response(_resumo_exportacao(lote), status=status.HTTP_202_ACCEPTED)

            conteudo, content_type, nome = motor_exportacao.exportar(
                recurso=recurso, request=request, formato=formato,
                recorte=recorte, tenant_id=self.tenant_id,
            )
        except motor_exportacao.ExportacaoInvalida as exc:
            raise ValidationError(str(exc))
        return _arquivo(conteudo, content_type, nome)


class EntregarArquivoView(_Base):
    """IE.3b — a outra metade da porta única: o **download** de um arquivo.

    Uma rota para todos os módulos, como todas as daqui: `especie` e `chave` são
    opacas e vão inteiras para o gancho do recurso, que é quem conhece domínio.

    **Não confundir com `ExportarView`.** Lá se gera um arquivo tabular a partir
    do `queryset`, com recorte, procedência e caminho de job. Aqui se deixa sair
    um binário que o recurso já guarda. São verbos diferentes com gates
    diferentes — ver `exigir_entrega`.
    """

    def get(self, request, recurso_id: str, especie: str, chave: str):
        try:
            recurso = obter(recurso_id)
        except RecursoDesconhecido:
            raise NotFound(f"Recurso '{recurso_id}' não existe.")
        if not recurso.entrega:
            # 404 e não 405: para quem pede, um recurso que não entrega arquivo é
            # indistinguível de um caminho que não existe — e é o que ele é.
            raise NotFound(f"Recurso '{recurso_id}' não entrega arquivo.")

        exigir_entrega(request.user, recurso)

        try:
            entregue = recurso.entregar_arquivo(especie, chave, self.tenant_id)
        except EntregaInvalida as exc:
            raise NotFound(str(exc))

        try:
            resposta = motor_entrega.servir(entregue)
        except FileNotFoundError as erro:
            raise NotFound(
                "O registro existe, mas o arquivo não está no armazenamento deste "
                "servidor. É falha de infraestrutura, não de permissão."
            ) from erro

        # Depois de servir, nunca antes: trilha de download é registro de um ato
        # consumado, e auditar a tentativa que terminou em 404 encheria a trilha
        # de eventos que não aconteceram.
        motor_entrega.auditar(recurso, entregue, usuario=request.user, especie=especie)
        return resposta


class ExportacaoDetalheView(_Base):
    """Acompanhamento e download do que saiu por job (R10)."""

    def get(self, request, exportacao_id: int):
        lote = self.scope_qs(Exportacao.objects.all()).filter(
            exportacao_id=exportacao_id,
        ).first()
        if lote is None:
            raise NotFound("Exportação não encontrada.")
        self.recurso(lote.recurso)

        if request.query_params.get("baixar") not in ("1", "true", "sim"):
            return Response(_resumo_exportacao(lote))

        if lote.status == Exportacao.Status.GERANDO:
            raise ValidationError("Ainda estamos gerando este arquivo.")
        if not lote.arquivo:
            raise NotFound(
                "O arquivo desta exportação expirou e foi removido. "
                "Gere de novo — a nova saída reflete o dado de agora."
            )
        if lote.expirada:
            raise NotFound("O link desta exportação expirou. Gere o arquivo de novo.")
        nome = lote.arquivo.name.rsplit("/", 1)[-1]
        return _blindar(
            FileResponse(lote.arquivo.open("rb"), as_attachment=True, filename=nome),
            nome,
        )


def _resumo_exportacao(lote: Exportacao) -> dict:
    return {
        "exportacao_id": lote.exportacao_id,
        "recurso": lote.recurso,
        "formato": lote.formato,
        "status": lote.status,
        "status_nome": lote.get_status_display(),
        "mensagem": lote.mensagem,
        "linhas": lote.linhas,
        "baixavel": lote.baixavel,
        "expira_em": lote.expira_em,
    }


class ModeloView(_Base):
    """A planilha-modelo (R2) — mesma fonte que valida a importação."""

    def get(self, request, recurso_id: str):
        recurso = self.recurso(recurso_id)
        if not recurso.importa:
            raise ValidationError(f"'{recurso.rotulo}' não aceita importação.")
        return _arquivo(
            planilha_modelo(recurso),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            nome_do_modelo(recurso),
        )


# ---------------------------------------------------------------------------
# Importação — R1: preparar, conferir, decidir
# ---------------------------------------------------------------------------


class ImportarArquivosView(_Base):
    """IE.3 — a porta de lote de ARQUIVO: N binários, uma decisão.

    Endpoint separado do `ImportarView` e não um ramo dentro dele, porque as duas
    naturezas divergem em tudo que um endpoint faz: o corpo (`arquivos[]` +
    `caminhos[]` × um `arquivo`), as recusas possíveis (não há de-para nem
    `ColunasNaoReconhecidas` aqui), o corte de job (por contagem de arquivos, não
    por bytes de planilha) e o resumo. Um `if recurso.de_arquivo` no meio do POST
    daria uma view com dois corpos costurados.

    **`caminhos[]` é o que faz a pasta virar taxonomia.** O navegador entrega
    `webkitRelativePath` ao arrastar um diretório, e é esse caminho relativo — não
    o nome do arquivo — que carrega obra e disciplina num acervo histórico. Vem
    como lista paralela a `arquivos[]` em vez de dentro do nome porque nome de
    arquivo com `/` é rejeitado pelo storage do Django, e embuti-lo forçaria uma
    codificação que alguém teria de decodificar do outro lado.
    """

    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, recurso_id: str):
        contexto = _json_do_form(request.data.get("contexto") or {}, "contexto")
        recurso = self.recurso(recurso_id, contexto, validar=True, escrita=True)
        if not recurso.de_arquivo:
            raise ValidationError({
                "recurso": (
                    f"'{recurso.id}' importa planilha, não arquivos soltos. "
                    "Use a porta de importação tabular."
                )
            })

        enviados = request.FILES.getlist("arquivos")
        if not enviados:
            raise ValidationError({"arquivos": "Envie os arquivos em `arquivos`."})

        caminhos = request.data.getlist("caminhos") if hasattr(request.data, "getlist") else []
        teto = limites_do_plano(request.user)

        recebidos = []
        for indice, enviado in enumerate(enviados):
            # Amostra primeiro, hash depois: o formato é decidido nos primeiros
            # 4 KB, e um arquivo recusado por formato não deve custar a leitura
            # inteira de 300 MB para calcular um SHA que ninguém vai usar.
            enviado.seek(0)
            amostra = enviado.read(4096)
            enviado.seek(0)
            try:
                formato = validar_entrada(
                    tamanho=enviado.size or 0, nome=enviado.name,
                    conteudo=amostra, limites=teto,
                    # PRA.5a — o recurso entra na porta: é ele que diz quais
                    # formatos este destino recebe, quanto cada um pode pesar e
                    # o que o plano do módulo dono inclui.
                    recurso=recurso, user=request.user,
                )
            except ArquivoGrandeDemais as exc:
                return Response(
                    {
                        "detail": str(exc), "code": "arquivo_grande_demais",
                        "arquivo": enviado.name,
                        "limite_mb": exc.limite_mb, "tamanho_mb": round(exc.tamanho_mb, 1),
                    },
                    status=status.HTTP_402_PAYMENT_REQUIRED,
                )
            except FormatoNaoContratado as exc:
                return Response(
                    {
                        "detail": str(exc), "code": "formato_nao_contratado",
                        "arquivo": enviado.name,
                        "formato": exc.formato, "disponiveis": exc.disponiveis,
                    },
                    status=status.HTTP_402_PAYMENT_REQUIRED,
                )
            except FormatoDesconhecido as exc:
                raise ValidationError({"arquivos": f"{enviado.name}: {exc}"})

            # **O recurso é mais estrito que a plataforma.** A allowlist diz o que
            # o sistema reconhece; `formatos_arquivo` diz o que ESTE recurso
            # aceita. Sem esta checagem, um DWG entraria no anexo de ASO do RH só
            # porque a Prancheta registrou o formato.
            if formato.codigo not in recurso.formatos_arquivo:
                raise ValidationError({
                    "arquivos": (
                        f"{enviado.name}: {recurso.rotulo} não recebe "
                        f"{formato.rotulo}. Aceita: {', '.join(recurso.formatos_arquivo)}."
                    )
                })

            caminho = (caminhos[indice] if indice < len(caminhos) else "") or enviado.name
            digest, tamanho = _hash_em_blocos(enviado)
            recebidos.append((
                ArquivoRecebido(
                    nome=enviado.name, caminho=str(caminho).strip().lstrip("/"),
                    tamanho=tamanho, hash=digest, formato=formato.codigo,
                ),
                enviado,
            ))

        try:
            importacao = motor_importacao.preparar_arquivos(
                recurso=recurso,
                arquivos=recebidos,
                tenant_id=self.tenant_id,
                usuario_nome=self.usuario_nome,
                limites=self.limites,
            )
        except motor_importacao.LimiteDoPlano as exc:
            return Response(
                {
                    "detail": str(exc), "code": "quota_excedida",
                    "quota": exc.quota, "limite": exc.limite, "uso": exc.tentado,
                },
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )
        except motor_importacao.ImportacaoInvalida as exc:
            raise ValidationError(str(exc))

        return Response(
            motor_importacao.resumo(importacao), status=status.HTTP_201_CREATED,
        )


def _hash_em_blocos(enviado) -> tuple[str, int]:
    """SHA-256 e tamanho lendo em blocos, restaurando a posição.

    Em blocos porque acima de `FILE_UPLOAD_MAX_MEMORY_SIZE` o Django já pôs o
    arquivo em disco temporário, e um `.read()` inteiro de 300 MB traria de volta
    para a memória exatamente o que ele acabou de tirar dela. É a mesma função
    que a Prancheta tinha em `uploads.py` — ela vem para cá com a porta, para não
    ficarem duas.
    """
    import hashlib

    digest = hashlib.sha256()
    tamanho = 0
    enviado.seek(0)
    for bloco in iter(lambda: enviado.read(1024 * 1024), b""):
        digest.update(bloco)
        tamanho += len(bloco)
    enviado.seek(0)
    return digest.hexdigest(), tamanho


class ImportarView(_Base):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, recurso_id: str):
        contexto = _json_do_form(request.data.get("contexto") or {}, "contexto")
        recurso = self.recurso(recurso_id, contexto, validar=True, escrita=True)
        arquivo = request.FILES.get("arquivo")
        if arquivo is None:
            raise ValidationError({"arquivo": "Envie o arquivo em `arquivo`."})
        teto = limites_do_plano(request.user)
        try:
            formato = self._validar_upload(arquivo, teto)
        except ArquivoGrandeDemais as exc:
            # 402 e não 400: o arquivo não está errado — o plano é que não o
            # comporta. O 400 mandaria a pessoa procurar defeito no arquivo.
            return Response(
                {
                    "detail": str(exc), "code": "arquivo_grande_demais",
                    "limite_mb": exc.limite_mb, "tamanho_mb": round(exc.tamanho_mb, 1),
                },
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )
        except FormatoNaoContratado as exc:
            return Response(
                {
                    "detail": str(exc), "code": "formato_nao_contratado",
                    "formato": exc.formato, "disponiveis": exc.disponiveis,
                },
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )

        de_para = self._de_para(request)
        delimitador = request.data.get("delimitador") or None
        conteudo = arquivo.read()

        if motor_importacao.vale_a_pena_job(conteudo):
            return self._enfileirar(
                recurso, arquivo, conteudo, de_para, delimitador, formato,
            )

        try:
            importacao = motor_importacao.preparar(
                recurso=recurso,
                conteudo=conteudo,
                nome_arquivo=arquivo.name,
                tenant_id=self.tenant_id,
                usuario_nome=self.usuario_nome,
                limites=self.limites,
                de_para=de_para,
                delimitador=delimitador,
                teto=teto,
                # `.codigo`, não o objeto: `ler_bytes` despacha por string. Passar
                # o `FormatoEntrada` fazia todo casamento falhar, cair no `raise
                # LeituraInvalida("Formato não suportado")` e o lote nascer em
                # ERRO com zero linhas — ver o D76.
                formato=formato.codigo,
            )
        except motor_importacao.ColunasNaoReconhecidas as exc:
            # 422 e não 400: o arquivo não está "errado" — só não foi reconhecido,
            # e a saída é o de-para manual, com o que o motor viu na mão do
            # operador (R4).
            return Response(
                {
                    "detail": str(exc),
                    "code": "colunas_nao_reconhecidas",
                    "cabecalhos_vistos": exc.cabecalhos_vistos,
                    "obrigatorias": exc.obrigatorias,
                    "colunas": [
                        {"campo": c.campo, "rotulo": c.rotulo, "obrigatoria": c.obrigatoria}
                        for c in recurso.colunas
                    ],
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        except motor_importacao.LimiteDoPlano as exc:
            return Response(
                {
                    "detail": str(exc), "code": "quota_excedida",
                    "quota": exc.quota, "limite": exc.limite, "uso": exc.tentado,
                },
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )
        except motor_importacao.ImportacaoInvalida as exc:
            raise ValidationError(str(exc))

        return Response(
            motor_importacao.resumo(importacao), status=status.HTTP_201_CREATED,
        )

    def _enfileirar(self, recurso, arquivo, conteudo, de_para, delimitador, formato):
        """R10 — arquivo grande vira job, e a resposta é o id para acompanhar."""
        from django.core.files.base import ContentFile

        from .tasks import preparar_importacao

        lote = Importacao.objects.create(
            tenant_id=self.tenant_id,
            recurso=recurso.id,
            arquivo_nome=arquivo.name[:255],
            contexto=dict(recurso.contexto or {}),
            status=Importacao.Status.LENDO,
            assincrona=True,
            usuario_nome=self.usuario_nome[:150],
            # O formato foi reconhecido pelos BYTES no request e viaja com o
            # lote. Sem isso o worker voltaria a decidir pelo sufixo do nome que
            # o cliente mandou — a porta que a validação acabou de fechar.
            parametros={"formato": formato.codigo},
        )
        lote.arquivo.save(arquivo.name, ContentFile(conteudo), save=True)
        # Depois do commit (D217): enfileirado dentro da transação da
        # requisição, o worker pegava o job antes de o lote existir para ele
        # ("importação sumiu antes do job") e a tela ficava em "lendo".
        argumentos = dict(
            limites=self.limites, de_para=de_para, delimitador=delimitador,
            teto=self.teto_serializavel(), formato=formato.codigo,
        )
        transaction.on_commit(
            lambda: preparar_importacao.delay(lote.pk, self.tenant_id, **argumentos)
        )
        return Response(
            motor_importacao.resumo(lote), status=status.HTTP_202_ACCEPTED,
        )

    def _validar_upload(self, arquivo, teto):
        """Tamanho e formato, os dois vindos do PLANO. Devolve o formato reconhecido.

        **O que mudou, e por quê** (análise de 07/08/2026). Antes daqui saía só um
        teto de tamanho lido de `ConfiguracaoArquivos` do tenant — um número
        invisível ao dono do produto — e **nenhuma** checagem de formato: o
        despacho era por sufixo do nome, lá dentro do `ler_bytes`. `payload.exe`
        renomeado para `.xlsx` passava a porta, era gravado em disco no caminho
        de job e só falhava ao ser parseado.

        A recusa de reusar `validate_uploaded_file` continua valendo e o motivo é
        o mesmo de antes: aquela lista de MIMEs é de documento que fica guardado,
        não tem `text/csv`, e reusá-la aqui recusaria toda importação por CSV. O
        que faltava não era aquele validador — era um **próprio**, e é o
        `limites.validar_entrada`, que decide pelos bytes e pergunta ao plano.

        A amostra de 4 KB basta para a assinatura e é lida antes do arquivo
        inteiro: o teto de tamanho tem de barrar **antes** de a gente trazer 50 MB
        para a memória, senão o limite protege depois de já ter pago o custo.
        """
        amostra = arquivo.read(4096)
        arquivo.seek(0)
        try:
            return validar_entrada(
                tamanho=arquivo.size, nome=arquivo.name or "",
                conteudo=amostra, limites=teto, user=self.request.user,
            )
        except FormatoDesconhecido as exc:
            raise ValidationError({"arquivo": str(exc)})


class ImportacoesDoRecursoView(_Base):
    """O histórico de lotes de um recurso — e é dele que se alcança o desfazer.

    Sem listagem, a R6 seria letra morta na tela: o lote aplicado ontem não teria
    por onde ser encontrado, e "desfazível" viraria uma promessa que só o
    `curl` cumpre.
    """

    def get(self, request, recurso_id: str):
        recurso = self.recurso(recurso_id)
        lotes = self.scope_qs(Importacao.objects.all()).filter(recurso=recurso_id)
        limite = min(int(request.query_params.get("limite", 30)), 200)
        return Response({
            "importacoes": [
                {
                    **motor_importacao.resumo(lote),
                    "criada_em": lote.criada_em,
                    "decidida_em": lote.decidida_em,
                    "usuario_nome": lote.usuario_nome,
                    # Só o **último** lote aplicado é desfazível: desfazer um lote
                    # do meio restauraria valores por cima do que veio depois, e o
                    # resultado não seria nem o antes nem o depois.
                    "pode_desfazer": (
                        recurso.desfazivel
                        and lote.status == Importacao.Status.APLICADA
                        and lote.pk == self._ultimo_aplicado(recurso_id)
                    ),
                }
                for lote in lotes[:limite]
            ],
        })

    def _ultimo_aplicado(self, recurso_id: str):
        ultimo = (
            self.scope_qs(Importacao.objects.all())
            .filter(recurso=recurso_id, status=Importacao.Status.APLICADA)
            .order_by("-decidida_em", "-importacao_id")
            .first()
        )
        return ultimo.pk if ultimo else None


class ImportacaoDetalheView(_Base):
    """A tela de conferência: o resumo e as linhas com veredito."""

    def get(self, request, importacao_id: int):
        importacao = self.importacao(importacao_id)
        self.recurso(importacao.recurso)
        situacao = request.query_params.get("situacao")
        linhas = importacao.linhas.all()
        if situacao:
            linhas = linhas.filter(situacao=situacao)
        limite = min(int(request.query_params.get("limite", 200)), 1000)
        return Response({
            **motor_importacao.resumo(importacao),
            "linhas": [
                {
                    "linha_id": l.linha_id, "numero": l.numero, "chave": l.chave,
                    "valores": l.valores, "situacao": l.situacao, "motivo": l.motivo,
                    "aceita": l.aceita, "bruto": l.bruto,
                }
                for l in linhas[:limite]
            ],
        })


class ImportacaoDecisaoView(_Base):
    """Confirmar tudo · confirmar seleção · negar tudo · desfazer."""

    #: Verbos que GRAVAM no destino (ou desfazem a gravação) — exigem, além do
    #: conjunto de permissões, o módulo contratado. `marcar` e `descartar` ficam
    #: de fora porque não tocam no destino: só mexem na área de conferência, que
    #: é do próprio tenant e já foi paga quando o arquivo subiu.
    ACOES_DE_ESCRITA = frozenset({"aplicar", "desfazer", "remapear"})

    def post(self, request, importacao_id: int, acao: str):
        importacao = self.importacao(importacao_id)
        recurso = self.recurso(
            importacao.recurso, importacao.contexto,
            escrita=acao in self.ACOES_DE_ESCRITA,
        )
        try:
            if acao == "marcar":
                afetadas = motor_importacao.marcar(
                    importacao,
                    aceitar=bool(request.data.get("aceitar", True)),
                    linhas=request.data.get("linhas"),
                )
                return Response({"linhas_marcadas": afetadas})
            if acao == "corrigir":
                afetadas = motor_importacao.corrigir(
                    importacao,
                    recurso=recurso,
                    valores=request.data.get("valores") or {},
                    linhas=request.data.get("linhas"),
                )
                return Response({"linhas_corrigidas": afetadas})
            if acao == "aplicar":
                aplicadas = motor_importacao.aplicar(
                    importacao, recurso=recurso, usuario_nome=self.usuario_nome,
                    limites=self.limites,
                )
                return Response({**motor_importacao.resumo(importacao), "aplicadas": aplicadas})
            if acao == "descartar":
                motor_importacao.descartar(importacao, usuario_nome=self.usuario_nome)
                return Response(motor_importacao.resumo(importacao))
            if acao == "desfazer":
                desfeitas = motor_importacao.desfazer(importacao, recurso=recurso)
                return Response({**motor_importacao.resumo(importacao), "desfeitas": desfeitas})
            if acao == "remapear":
                return Response(self._remapear(importacao, recurso, request))
        except motor_importacao.LimiteDoPlano as exc:
            return Response(
                {
                    "detail": str(exc), "code": "quota_excedida",
                    "quota": exc.quota, "limite": exc.limite, "uso": exc.tentado,
                },
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )
        except motor_importacao.ImportacaoInvalida as exc:
            raise ValidationError(str(exc))
        raise NotFound(f"Ação '{acao}' não existe.")

    def _remapear(self, importacao: Importacao, recurso, request) -> dict:  # noqa: ARG002
        """R4 no caminho de job: relê o **mesmo arquivo** com o de-para escolhido.

        Sem isto, um cabeçalho não reconhecido num arquivo grande seria um beco
        sem saída — e arquivo grande é justamente o de origem mais estranha, onde
        a R4 mais vale. O upload não se repete: o arquivo ficou guardado
        exatamente para esta segunda passada.
        """
        if not (importacao.parametros or {}).get("aguarda_de_para"):
            raise ValidationError("Esta importação não está esperando um de-para.")
        if not importacao.arquivo:
            raise ValidationError(
                "O arquivo desta importação não está mais no servidor. Suba de novo."
            )
        de_para = self._de_para(request)
        if not de_para:
            raise ValidationError({"de_para": "Informe o de-para (`campo: índice`) ou um `mapa`."})

        # O formato reconhecido no upload original é preservado: o `remapear`
        # relê o MESMO arquivo, e redetectá-lo pelo nome desfaria a validação por
        # bytes justamente no caminho de origem mais estranha.
        formato = (importacao.parametros or {}).get("formato") or ""
        importacao.status = Importacao.Status.LENDO
        importacao.mensagem = ""
        importacao.parametros = {"formato": formato} if formato else {}
        importacao.save(update_fields=["status", "mensagem", "parametros"])

        from .tasks import preparar_importacao

        argumentos = dict(
            limites=self.limites, de_para=de_para, teto=self.teto_serializavel(), formato=formato,
        )
        transaction.on_commit(  # D217: só depois de o novo estado existir para o worker
            lambda: preparar_importacao.delay(importacao.pk, self.tenant_id, **argumentos)
        )
        return motor_importacao.resumo(importacao)



class ImportacaoRecusadasView(_Base):
    """R5 — as linhas recusadas de volta como planilha, para corrigir e reenviar."""

    def get(self, request, importacao_id: int):
        importacao = self.importacao(importacao_id)
        recurso = self.recurso(importacao.recurso, importacao.contexto)
        conteudo = motor_importacao.recusadas_xlsx(importacao, recurso)
        return _arquivo(
            conteudo,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            f"recusadas-{importacao.importacao_id}.xlsx",
        )


# ---------------------------------------------------------------------------
# De-para salvável (R4)
# ---------------------------------------------------------------------------


class MapasView(_Base):
    """Os de-para guardados de um recurso — a importação recorrente da R4."""

    def get(self, request, recurso_id: str):
        self.recurso(recurso_id)
        mapas = self.scope_qs(MapaColunas.objects.all()).filter(recurso=recurso_id)
        return Response({"mapas": [_resumo_mapa(m) for m in mapas]})

    def post(self, request, recurso_id: str):
        recurso = self.recurso(recurso_id)
        nome = (request.data.get("nome") or "").strip()
        mapa = request.data.get("mapa") or {}
        if not nome:
            raise ValidationError({"nome": "Dê um nome ao mapa (ex.: 'Prefeitura — planilha mensal')."})
        campos = {c.campo for c in recurso.colunas}
        limpo = {k: v for k, v in mapa.items() if k in campos and isinstance(v, int) and v >= 0}
        if not limpo:
            raise ValidationError({"mapa": "Mapa vazio — informe `campo: índice da coluna`."})
        salvo, _ = MapaColunas.objects.update_or_create(
            tenant_id=self.tenant_id, recurso=recurso_id, nome=nome[:120],
            defaults={
                "mapa": limpo,
                "delimitador": (request.data.get("delimitador") or "")[:4],
                "usuario_nome": self.usuario_nome[:150],
            },
        )
        return Response(_resumo_mapa(salvo), status=status.HTTP_201_CREATED)


class MapaDetalheView(_Base):
    def delete(self, request, mapa_id: int):
        salvo = self.scope_qs(MapaColunas.objects.all()).filter(pk=mapa_id).first()
        if salvo is None:
            raise NotFound("Mapa de colunas não encontrado.")
        self.recurso(salvo.recurso)
        salvo.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


def _resumo_mapa(mapa: MapaColunas) -> dict:
    return {
        "mapa_id": mapa.mapa_id,
        "recurso": mapa.recurso,
        "nome": mapa.nome,
        "mapa": mapa.mapa,
        "delimitador": mapa.delimitador,
        "criado_por": mapa.usuario_nome,
        "criado_em": mapa.criado_em,
    }
