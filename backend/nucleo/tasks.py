# backend/nucleo/tasks.py
from celery import shared_task
from .models import FailedTask

@shared_task
def handle_failed_task(request, exc, traceback):
    """
    Salva os detalhes de uma tarefa que falhou permanentemente em um modelo
    para análise posterior (Dead Letter Queue).
    """
    try:
        FailedTask.objects.create(
            task_id=request.id,
            task_name=request.task,
            args=request.args,
            kwargs=request.kwargs,
            exception=str(exc),
            traceback=traceback,
        )
    except Exception as e:
        # Se até o handler de erro falhar, logamos para o console.
        print(f"CRÍTICO: Falha ao salvar a tarefa falha no banco de dados: {e}")
