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

from django.http import FileResponse, HttpResponse
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from nucleo.tenancy import TenantScopedAPIViewMixin
from nucleo.upload_validation import resolve_upload_config

from . import exportacao as motor_exportacao
from . import importacao as motor_importacao
from .acesso import exigir_acesso_total, recursos_permitidos
from .models import Exportacao, Importacao, MapaColunas
from .modelo import nome_do_modelo, planilha_modelo
from .registro import ContextoInvalido, RecursoDesconhecido, listar, obter


class _Base(TenantScopedAPIViewMixin, APIView):
    permission_classes = [IsAuthenticated]

    def recurso(self, recurso_id: str, contexto: dict | None = None, *, validar=False):
        """Resolve o recurso, aplica o gate do §3 e o amarra ao destino.

        Nesta ordem, sempre: quem não pode operar o recurso não deve nem chegar a
        descobrir se o destino que pediu existe.
        """
        try:
            recurso = obter(recurso_id)
        except RecursoDesconhecido:
            raise NotFound(f"Recurso '{recurso_id}' não existe.")
        exigir_acesso_total(self.request.user, recurso)
        if validar:
            try:
                contexto = recurso.validar_contexto(
                    contexto or {}, self.request.user, self.tenant_id,
                )
            except ContextoInvalido as exc:
                raise ValidationError({"contexto": str(exc)})
        return recurso.com_contexto(contexto)

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
    resposta = HttpResponse(conteudo, content_type=content_type)
    resposta["Content-Disposition"] = f'attachment; filename="{nome}"'
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
        return Response({"recursos": [r.descrever() for r in permitidos]})


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

                gerar_exportacao.delay(
                    lote.pk, self.tenant_id, getattr(request.user, "pk", None),
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
        return FileResponse(lote.arquivo.open("rb"), as_attachment=True,
                            filename=lote.arquivo.name.rsplit("/", 1)[-1])


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


class ImportarView(_Base):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, recurso_id: str):
        contexto = _json_do_form(request.data.get("contexto") or {}, "contexto")
        recurso = self.recurso(recurso_id, contexto, validar=True)
        arquivo = request.FILES.get("arquivo")
        if arquivo is None:
            raise ValidationError({"arquivo": "Envie o arquivo em `arquivo`."})
        self._validar_upload(arquivo)

        de_para = self._de_para(request)
        delimitador = request.data.get("delimitador") or None
        conteudo = arquivo.read()

        if motor_importacao.vale_a_pena_job(conteudo):
            return self._enfileirar(recurso, arquivo, conteudo, de_para, delimitador)

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

    def _enfileirar(self, recurso, arquivo, conteudo, de_para, delimitador):
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
        )
        lote.arquivo.save(arquivo.name, ContentFile(conteudo), save=True)
        preparar_importacao.delay(
            lote.pk, self.tenant_id,
            limites=self.limites, de_para=de_para, delimitador=delimitador,
        )
        return Response(
            motor_importacao.resumo(lote), status=status.HTTP_202_ACCEPTED,
        )

    def _validar_upload(self, arquivo) -> None:
        """Só o TETO DE TAMANHO do tenant; o formato quem decide é o leitor.

        Deliberadamente **não** chama `validate_uploaded_file`: aquele validador
        serve a documento que fica guardado, e a lista de MIMEs aceitos do tenant
        (`DEFAULT_TIPOS`) não inclui `text/csv` — reusá-la aqui recusaria toda
        importação por CSV, e um tenant que restringisse a lista a PDF quebraria
        a importação por planilha sem ninguém entender por quê.

        Arquivo de importação não é documento: é lido, classificado e descartado.
        O que dele importa é (a) não estourar memória — daí o teto reusado — e
        (b) ser legível, e disso `ler_bytes` cuida com mensagem própria.
        """
        max_bytes, _ = resolve_upload_config(self.tenant_id)
        if max_bytes and arquivo.size > max_bytes:
            raise ValidationError(
                {"arquivo": f"Arquivo de {arquivo.size / 1048576:.1f} MB acima do limite de "
                            f"{max_bytes / 1048576:.0f} MB configurado para esta empresa."}
            )


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

    def post(self, request, importacao_id: int, acao: str):
        importacao = self.importacao(importacao_id)
        recurso = self.recurso(importacao.recurso, importacao.contexto)
        try:
            if acao == "marcar":
                afetadas = motor_importacao.marcar(
                    importacao,
                    aceitar=bool(request.data.get("aceitar", True)),
                    linhas=request.data.get("linhas"),
                )
                return Response({"linhas_marcadas": afetadas})
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

        importacao.status = Importacao.Status.LENDO
        importacao.mensagem = ""
        importacao.parametros = {}
        importacao.save(update_fields=["status", "mensagem", "parametros"])

        from .tasks import preparar_importacao

        preparar_importacao.delay(
            importacao.pk, self.tenant_id, limites=self.limites, de_para=de_para,
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
