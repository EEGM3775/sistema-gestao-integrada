# backend/modulocrm/tasks.py
"""
Notificações do CRM (portadas do worker do `funcoeslead`, Fase 11.2):
lembrete por e-mail de tarefas com vencimento nas próximas 24h. Agendada em
`CELERY_BEAT_SCHEDULE`; sem `MAIL_HOST` configurado a task é no-op — mesma
paridade do worker Node, que ficava desabilitado sem as variáveis de e-mail.
"""
import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from nucleo.tasks import DLQTask

from .models import Interaction

logger = logging.getLogger(__name__)


def _destinatario(interaction):
    """E-mail e nome do responsável — Usuario, Funcionario ou Fornecedor (GenericFK)."""
    responsavel = interaction.assigned_to
    if responsavel is None and interaction.lead_id:
        responsavel = interaction.lead.assigned_to
    if responsavel is None:
        return None, None
    email = getattr(responsavel, "email", "") or getattr(responsavel, "email_pessoal", "")
    nome = (
        getattr(responsavel, "first_name", "")
        or getattr(responsavel, "nome_completo", "")
        or getattr(responsavel, "razao_social", "")
    )
    return (email or None), nome


@shared_task(bind=True, base=DLQTask, max_retries=3)
def notificar_tarefas_a_vencer(self):
    """Envia lembrete das tarefas não concluídas que vencem nas próximas 24h."""
    if not settings.EMAIL_HOST:
        logger.info("Notificação de tarefas desativada: MAIL_HOST não configurado.")
        return 0

    agora = timezone.now()
    tarefas = Interaction.objects.filter(
        type=Interaction.TypeChoices.TAREFA,
        completed=False,
        due_date__gte=agora,
        due_date__lte=agora + timedelta(days=1),
    ).select_related("lead__assigned_to")

    enviados = 0
    for tarefa in tarefas:
        email, nome = _destinatario(tarefa)
        if not email:
            logger.warning("Tarefa %s sem e-mail de responsável para notificar.", tarefa.pk)
            continue
        vencimento = timezone.localtime(tarefa.due_date).strftime("%d/%m/%Y %H:%M")
        send_mail(
            subject=f"Lembrete de Tarefa: {tarefa.subject}",
            message=(
                f"Olá, {nome or ''}!\n\n"
                f'A tarefa "{tarefa.subject}" está com o vencimento próximo: {vencimento}.\n\n'
                f"Notas: {tarefa.notes or 'Nenhuma nota adicional.'}\n\n"
                f"Sistema de Gestão Integrada"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
        )
        enviados += 1
    return enviados
