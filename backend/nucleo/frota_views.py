# backend/nucleo/frota_views.py
"""D98 — a fila vista de fora: onde estou, e posso subir o meu.

**Duas rotas, e a segunda é a que o dono pediu com um aviso junto:**
*"o administrador do tenant (ou alguém com essa função) pode passar na frente,
com aviso que está passando na frente. Faça um aviso do que está acontecendo e
se ele quer passar."*

O aviso não é texto solto no frontend — ele precisa de **números do servidor**
para não mentir, e é por isso que `GET` devolve `na_frente_da_empresa` junto com
a posição: a frase é "subir este atrasa outros N arquivos **seus**", e o N vem
daqui. Sem ele, o botão seria o que todo mundo aperta sempre.
"""
from __future__ import annotations

from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from . import autorizacao, frota
from .models import TarefaNaFila


class TarefaNaFilaViewSet(viewsets.ReadOnlyModelViewSet):
    """`/api/frota/tarefas/` — a fila **desta empresa**, e só ela.

    **O escopo é aplicado à mão e isso é deliberado.** A tabela não tem RLS,
    porque o despachante precisa ler as linhas de todos os tenants para poder ser
    justo entre eles (ver `frota.py`). O preço é este: quem expõe a fila filtra
    explicitamente, como o `AuditLog` já faz. Errar aqui mostraria a fila do
    vizinho — e por isso o filtro é a primeira linha do `get_queryset`, sem
    caminho alternativo.
    """

    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        return TarefaNaFila.objects.filter(
            tenant_id=getattr(self.request.user, "tenant_id", None),
            situacao__in=[
                TarefaNaFila.Situacao.AGUARDANDO, TarefaNaFila.Situacao.DESPACHADA,
            ],
        ).order_by("prioridade", "criada_em")

    def list(self, request, *args, **kwargs):
        return Response({
            "vagas": frota.vagas_da_frota(),
            "tarefas": [
                {
                    "tarefa_id": t.tarefa_id,
                    "chave": t.chave,
                    "criada_em": t.criada_em,
                    **frota.situacao_da_fila(t),
                }
                for t in self.get_queryset()
            ],
        })

    @action(detail=True, methods=["post"])
    def priorizar(self, request, pk=None):
        """Sobe este trabalho à frente dos **da mesma empresa**.

        Exige `prancheta.documento.edit` — a permissão de quem governa o acervo,
        e não uma permissão nova. Inventar `frota.priorizar` como perm própria
        obrigaria a re-seed do IAM para uma decisão que já tem dono: quem pode
        publicar revisão pode dizer qual delas converte primeiro.

        **Não é uma ordem irrevogável nem um privilégio comprado:** é uma
        permutação dos lugares que a empresa já ocupa. Ninguém de fora se move —
        o que a resposta devolve, com a posição nova, é a prova disso.
        """
        tarefa = self.get_object()
        # `tem_na_lista`, e não `pode`: esta view nunca deu passe ao admin fora
        # do módulo — ela conferia a lista do token, que o admin só tem para o
        # que a empresa assina.
        if not autorizacao.tem_na_lista(request.user, "prancheta.documento.edit"):
            return Response(
                {"detail": "Só quem governa o acervo pode reordenar a fila da empresa."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if tarefa.situacao != TarefaNaFila.Situacao.AGUARDANDO:
            return Response(
                {"detail": "Este arquivo já saiu da fila — está sendo convertido agora."},
                status=status.HTTP_409_CONFLICT,
            )
        frota.priorizar(tarefa, user=request.user)
        tarefa.refresh_from_db()
        return Response(frota.situacao_da_fila(tarefa))
