"""O suporte da plataforma só entra com consentimento, e com prazo (fase 6, §10.7).

Até a fase 6 o supervisor da plataforma (superusuário da IAM) via e mudava as
pessoas, os papéis e os acessos de **todas** as empresas — as telas de
administração da IAM não filtravam nada para ele. Agora:

- **a própria empresa** dele continua dele, como a de qualquer admin;
- **outra empresa**, só enquanto houver um `ConsentimentoSuporte` vigente, que o
  admin dela concede na tela de usuários (com prazo de até
  `SUPORTE_CONSENTIMENTO_MAX_DIAS`) e encerra quando quiser;
- **duas exceções, sem as quais a empresa trava para sempre**: criar o primeiro
  administrador de uma empresa que não tem nenhum ativo (a implantação), e
  redefinir o segundo fator de um administrador que perdeu o celular e os
  códigos (não há outro admin para consentir). As duas continuam registradas
  na trilha e avisadas por e-mail, como antes.

O PDP já prendia o supervisor à própria empresa (`empresa#supervisor` só é
escrito para o superusuário daquela empresa): o que muda aqui é a IAM.
"""
from __future__ import annotations

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from payment.planos import SUPORTE_CONSENTIMENTO_MAX_DIAS

from . import recuperacao
from .models import ConsentimentoSuporte, EventoSeguranca, Usuario


def _vigentes():
    return ConsentimentoSuporte.objects.filter(encerrado_em__isnull=True, ate__gt=timezone.now())


def vigente(tenant_id) -> ConsentimentoSuporte | None:
    return _vigentes().filter(tenant_id=tenant_id).order_by("-ate").first()


def empresas_que_o_supervisor_ve(supervisor) -> set:
    """A empresa do próprio supervisor e as que consentiram, hoje."""
    ids = set(_vigentes().values_list("tenant_id", flat=True))
    if supervisor.tenant_id:
        ids.add(supervisor.tenant_id)
    return ids


def sem_administrador(tenant_id) -> bool:
    return not Usuario.objects.filter(tenant_id=tenant_id, is_tenant_admin=True, is_active=True).exists()


def filtro_de_pessoas(usuario, campo: str = "tenant_id") -> Q | None:
    """O recorte das pessoas que `usuario` enxerga na IAM, ou `None` para
    "só a própria empresa" (o admin comum)."""
    if not usuario.is_superuser:
        return None
    return Q(**{f"{campo}__in": empresas_que_o_supervisor_ve(usuario)})


def pode_criar_em(supervisor, tenant_id, *, criando_admin: bool) -> bool:
    if tenant_id in empresas_que_o_supervisor_ve(supervisor):
        return True
    return criando_admin and sem_administrador(tenant_id)


def conceder(admin, dias: int, motivo: str = "", request=None) -> ConsentimentoSuporte:
    """Libera o suporte na empresa do admin por `dias` (1 a o teto do dono).
    Um consentimento vigente é substituído — fica um só, o mais novo."""
    dias = max(1, min(int(dias), SUPORTE_CONSENTIMENTO_MAX_DIAS))
    agora = timezone.now()
    _vigentes().filter(tenant_id=admin.tenant_id).update(
        encerrado_em=agora, encerrado_por_username=admin.username,
    )
    consentimento = ConsentimentoSuporte.objects.create(
        tenant_id=admin.tenant_id, concedido_por=admin, concedido_por_username=admin.username,
        motivo=(motivo or "")[:200], ate=agora + timedelta(days=dias),
    )
    recuperacao.registrar_evento(
        EventoSeguranca.Tipo.SUPORTE_CONSENTIDO, alvo=admin, autor=admin, request=request,
        dias=dias, ate=consentimento.ate.isoformat(),
    )
    return consentimento


def encerrar(admin, request=None) -> int:
    n = _vigentes().filter(tenant_id=admin.tenant_id).update(
        encerrado_em=timezone.now(), encerrado_por_username=admin.username,
    )
    if n:
        recuperacao.registrar_evento(
            EventoSeguranca.Tipo.SUPORTE_ENCERRADO, alvo=admin, autor=admin, request=request,
        )
    return n
