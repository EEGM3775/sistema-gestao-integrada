# backend/nucleo/lixo_views.py
"""API da lixeira — `/api/lixo/`.

**Só de leitura, mais dois verbos.** Não existe `POST /api/lixo/` para "mover
para o lixo": o que põe um objeto aqui é o `DELETE` do próprio módulo, onde o
usuário está. A prancha original previa um `POST /api/lixo/mover/` com
`{modelo, objeto_id}` — um endpoint genérico de exclusão, paralelo ao `DELETE`
que cada ViewSet já tem, com a permissão do módulo alvo tendo de ser reconferida
à mão. O `perform_destroy` do `TenantScopedViewSetMixin` faz o mesmo serviço
reusando a autorização que já roda.

**Quem pode o quê.** Excluir continua sendo de quem já podia excluir — a lixeira
não tranca nada que era livre. Ver, restaurar e purgar são do `gestor_lixo`:

- **ver** expõe, num lugar só, tudo que a empresa apagou — inclusive o que foi
  apagado por engano e o que foi apagado de propósito para sumir do relatório.
  É uma janela de auditoria, não uma listagem de cadastro;
- **restaurar** devolve à circulação um dado que alguém decidiu tirar dela;
- **purgar** destrói, antes do prazo, o que ainda dava para recuperar.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .lixo import _nome_de, purgar, restaurar
from .lixo_pagination import LixoPageNumberPagination
from .models import Lixo
from .permissions import RequirePermission
from .tenancy import TenantScopedViewSetMixin


class LixoSerializer(serializers.ModelSerializer):
    #: `app_label.model` — o que a tela usa para agrupar e filtrar.
    modelo = serializers.SerializerMethodField()
    #: O nome que uma pessoa lê ("Obra", "Cliente"), vindo do `verbose_name` do
    #: modelo. Não é hardcoded aqui: um modelo novo a entrar na lixeira aparece com
    #: o nome certo sem tocar neste arquivo.
    modelo_rotulo = serializers.SerializerMethodField()
    estado = serializers.SerializerMethodField()
    #: Quantos dias faltam para a purga. A tela mostra isto em vez da data
    #: crua porque "purga em 2 dias" é o que muda a decisão de quem olha.
    dias_para_purga = serializers.SerializerMethodField()
    restaurado_por_nome = serializers.SerializerMethodField()
    purgado_por_nome = serializers.SerializerMethodField()

    class Meta:
        model = Lixo
        fields = [
            "lixo_id", "modelo", "modelo_rotulo", "alvo_id", "rotulo",
            "excluido_em", "excluido_por_nome", "motivo",
            "purgar_em", "dias_para_purga", "estado",
            "restaurado_em", "restaurado_por_nome",
            "purgado_em", "purgado_por_nome", "falha_na_purga",
        ]
        read_only_fields = fields

    def get_modelo(self, obj) -> str:
        return f"{obj.alvo_tipo.app_label}.{obj.alvo_tipo.model}"

    def get_modelo_rotulo(self, obj) -> str:
        modelo = obj.alvo_tipo.model_class()
        if modelo is None:
            return obj.alvo_tipo.model
        return str(modelo._meta.verbose_name).capitalize()

    def get_estado(self, obj) -> str:
        if obj.purgado_em is not None:
            return "purgado"
        if obj.restaurado_em is not None:
            return "restaurado"
        return "no_lixo"

    def get_dias_para_purga(self, obj):
        """`None` quando o item já saiu da lixeira — não há relógio correndo.

        Negativo é resposta honesta e não um bug: significa que o prazo venceu e
        a varredura ainda não passou (ou passou e foi recusada, e aí
        `falha_na_purga` diz por quê). Zerar isso esconderia exatamente o caso
        que alguém precisa investigar.
        """
        if not obj.ativo:
            return None
        return (obj.purgar_em - timezone.now()).days

    def get_restaurado_por_nome(self, obj) -> str:
        return _nome_de(obj.restaurado_por)

    def get_purgado_por_nome(self, obj) -> str:
        """Purgado **sem** autor é a varredura, não um ator anônimo.

        O modelo grava `purgado_por = None` de propósito nesse caso (inventar um
        usuário-robô poria um ator falso no log de auditoria); é aqui que esse
        nulo vira a palavra que a tela mostra.
        """
        if obj.purgado_em is not None and obj.purgado_por is None:
            return "purga automática"
        return _nome_de(obj.purgado_por)


class LixoViewSet(TenantScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """`/api/lixo/` — o que este tenant excluiu, e o que dá para desfazer."""

    queryset = Lixo.objects.select_related("alvo_tipo").all()
    serializer_class = LixoSerializer
    permission_classes = [RequirePermission]
    pagination_class = LixoPageNumberPagination
    required_resource = "plataforma.lixo"
    action_permission_map = {
        "restaurar": "plataforma.lixo.restaurar",
        "purgar": "plataforma.lixo.purgar",
    }
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = {
        "alvo_tipo__model": ["exact"],
        "excluido_em": ["gte", "lte"],
    }
    search_fields = ["rotulo", "motivo", "excluido_por_nome"]
    ordering_fields = ["excluido_em", "purgar_em", "rotulo"]
    ordering = ["-excluido_em"]

    def get_queryset(self):
        """Por padrão a página mostra **o que está na lixeira**, não o histórico.

        `?estado=todos` abre o histórico inteiro (restaurados e purgados) — é o
        modo auditoria, e é dele que sai a resposta a "quem apagou o contrato do
        cliente em março". O padrão é o outro porque quem abre a página quer
        desfazer alguma coisa, e misturar 400 linhas purgadas com as 3
        recuperáveis esconde as 3.
        """
        qs = super().get_queryset()
        estado = (self.request.query_params.get("estado") or "").strip()
        if estado == "todos":
            return qs
        if estado == "purgado":
            return qs.filter(purgado_em__isnull=False)
        if estado == "restaurado":
            return qs.filter(restaurado_em__isnull=False)
        return qs.filter(restaurado_em__isnull=True, purgado_em__isnull=True)

    @action(detail=True, methods=["post"])
    def restaurar(self, request, pk=None):
        """Tira a lápide — o registro volta a aparecer onde sempre esteve."""
        item = self.get_object()
        try:
            restaurar(item, usuario=request.user)
        except DjangoValidationError as exc:
            raise ValidationError(getattr(exc, "messages", [str(exc)]))
        item.refresh_from_db()
        return Response(self.get_serializer(item).data)

    @action(detail=True, methods=["post", "delete"])
    def purgar(self, request, pk=None):
        """Apaga de verdade, antes do prazo. Irreversível.

        Aceita `POST` e `DELETE` de propósito: `DELETE` é o verbo da prancha e
        diz o que acontece; `POST` é o que a tela manda, porque o modal exige
        que o usuário digite o nome do item e nem todo cliente HTTP envia corpo
        num `DELETE`.

        Uma purga **recusada** pelo desenho do módulo (um `PROTECT`) devolve
        200 com `falha_na_purga` preenchido, e não um erro: a chamada funcionou,
        quem recusou foi o banco, e a tela precisa mostrar o motivo ao lado do
        item — que continua lá.
        """
        item = self.get_object()
        try:
            item = purgar(item, usuario=request.user)
        except DjangoValidationError as exc:
            raise ValidationError(getattr(exc, "messages", [str(exc)]))
        return Response(self.get_serializer(item).data)

    @action(detail=False)
    def resumo(self, request):
        """Contagem por tipo do que está na lixeira agora — o cabeçalho da tela.

        Uma consulta agregada em vez de contar no cliente: a página pagina 25
        itens, e "3 obras, 12 clientes" não pode sair de uma página de 25.
        """
        qs = self._scope(
            Lixo.objects.filter(restaurado_em__isnull=True, purgado_em__isnull=True)
        )
        por_tipo = (
            qs.values("alvo_tipo__app_label", "alvo_tipo__model")
            .annotate(quantidade=Count("lixo_id"))
            .order_by("-quantidade")
        )
        vencidos = qs.filter(purgar_em__lte=timezone.now()).count()
        return Response({
            "total": qs.count(),
            # Itens cujo prazo já venceu e que a varredura ainda não levou —
            # normalmente zero. Diferente de zero por muito tempo significa que
            # a task parou, e é o tipo de silêncio que o D21 ensinou a não ter.
            "vencidos_nao_purgados": vencidos,
            "com_falha": qs.exclude(falha_na_purga="").count(),
            "por_tipo": [
                {
                    "modelo": f"{linha['alvo_tipo__app_label']}.{linha['alvo_tipo__model']}",
                    "quantidade": linha["quantidade"],
                }
                for linha in por_tipo
            ],
        })
