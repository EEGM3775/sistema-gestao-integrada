# backend/nucleo/signals.py
from django.dispatch import receiver
from celery.signals import task_prerun, task_postrun
from .models import LogAtividadeUsuario, Usuario
import json

@receiver(task_prerun)
def log_task_start(sender=None, task_id=None, task=None, args=None, kwargs=None, **_kwargs):
    """
    Registra o início de uma tarefa Celery no log de atividades.
    """
    # Evita o log de tarefas de log para não criar loops
    if task.name.endswith('log_task_activity'):
        return

    user_id = kwargs.get('user_id')
    usuario = None
    if user_id:
        try:
            usuario = Usuario.objects.get(id=user_id)
        except Usuario.DoesNotExist:
            usuario = None

    LogAtividadeUsuario.objects.create(
        usuario=usuario,
        acao=f"Início da tarefa: {task.name}",
        entidade_alvo="CeleryTask",
        detalhes={
            "task_id": task_id,
            "task_name": task.name,
            "args": args,
            "kwargs": kwargs,
            "status": "Iniciada"
        }
    )

@receiver(task_postrun)
def log_task_end(sender=None, task_id=None, task=None, args=None, kwargs=None, retval=None, state=None, **_kwargs):
    """
    Atualiza o log de atividades com o resultado da tarefa Celery.
    """
    # Evita o log de tarefas de log
    if task.name.endswith('log_task_activity'):
        return

    try:
        log_entry = LogAtividadeUsuario.objects.filter(
            entidade_alvo="CeleryTask",
            detalhes__task_id=task_id
        ).latest('timestamp')

        log_entry.acao = f"Fim da tarefa: {task.name} - {state}"
        
        # Atualiza os detalhes existentes
        if isinstance(log_entry.detalhes, dict):
            details = log_entry.detalhes
        else:
            try:
                details = json.loads(log_entry.detalhes)
            except (json.JSONDecodeError, TypeError):
                details = {}

        details["status"] = state
        if state == 'FAILURE':
            details["error"] = str(retval)
        else:
            details["return_value"] = str(retval)
            
        log_entry.detalhes = details
        log_entry.save()

    except LogAtividadeUsuario.DoesNotExist:
        # Se o log de início não foi encontrado, cria um novo.
        # Isso pode acontecer se a aplicação foi reiniciada durante a execução da tarefa.
        user_id = kwargs.get('user_id')
        usuario = None
        if user_id:
            try:
                usuario = Usuario.objects.get(id=user_id)
            except Usuario.DoesNotExist:
                usuario = None
        
        LogAtividadeUsuario.objects.create(
            usuario=usuario,
            acao=f"Fim da tarefa: {task.name} - {state}",
            entidade_alvo="CeleryTask",
            detalhes={
                "task_id": task_id,
                "task_name": task.name,
                "args": args,
                "kwargs": kwargs,
                "status": state,
                "error": str(retval) if state == 'FAILURE' else None,
                "return_value": str(retval) if state != 'FAILURE' else None,
                "note": "Log de início não encontrado."
            }
        )
