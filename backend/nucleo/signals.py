# backend/nucleo/signals.py
"""Telemetria de ciclo de vida das tasks Celery.

**Uma linha por task, na conclusão, sem os argumentos** (D59 + A6, 08/08/2026).

O desenho anterior gravava **duas** linhas por task — uma no `task_prerun`, outra
no `task_postrun` — com `args` e `kwargs` **verbatim** num `JSONField`. Isso tinha
três defeitos que se sustentavam mutuamente:

1. **Nunca funcionou.** Desde a Fase 8 todo task escopado por tenant recebe
   `tenant_id` (um `UUID`) como argumento, e `UUID` não é serializável em JSON: o
   `create` estourava, o `LogAtividadeUsuario` não era gravado para *nenhuma* delas
   e o log do worker ganhava dois tracebacks por task. Ausência de linha é
   indistinguível de "não houve tarefa", então o buraco não se via.
2. **A correção óbvia era pior que o defeito.** Um encoder que soubesse `UUID`
   transformaria o crash em **escrita sem teto**: duas linhas por task, payload
   livre (o `args` de uma task carrega o que o chamador quiser), num `JSONField`
   sem índice, numa tabela **mutável** e **não tenant-scoped** — ou seja, o
   `tenant_id` e o que mais viajasse como argumento passariam a ser persistidos
   fora do escopo de tenant, crescendo com a fila. Consumo sem teto é defeito de
   produto, não incômodo local.
3. **O `postrun` procurava a linha do `prerun`** com `filter(detalhes__task_id=…)`
   sobre `JSONField` sem índice — varredura a cada task. Gravar só a conclusão faz
   essa consulta desaparecer, e com ela a necessidade do índice que o A6 pedia.

O que fica registrado é o que identifica a execução — `task_id`, nome, estado e,
na falha, a mensagem **truncada**. O que a task *recebeu* não entra: para
reconstituir uma execução existe o log estruturado com `request_id`/`tenant_id`
(Fase 10.1), e para a trilha sensível existe o `AuditLog`, que é imutável e
por-tenant. Este modelo é telemetria, e a Fase 10 prevê aposentá-lo.
"""

from celery.signals import task_postrun
from django.dispatch import receiver

from .models import LogAtividadeUsuario, Usuario

#: Teto do texto de retorno/erro guardado em `detalhes`. Não é knob de plano
#: (§5.6 do payment/planos.py: largura de campo não é limite comercial) — é o
#: mesmo motivo de `acao` ser `CharField(255)`: impedir que uma exceção com
#: `repr` de payload inteiro vire linha de banco de tamanho arbitrário.
_MAX_TEXTO = 500


def _ator(kwargs):
    """O usuário que disparou a task, quando o chamador o declara.

    Escalar e barato — é o único dado do `kwargs` que sobrevive aqui, e vem por
    contrato (`user_id`), não por varredura do que a task recebeu.
    """
    user_id = (kwargs or {}).get("user_id")
    if not user_id:
        return None
    return Usuario.objects.filter(id=user_id).first()


@receiver(task_postrun)
def log_task_end(sender=None, task_id=None, task=None, kwargs=None, retval=None, state=None, **_kwargs):
    """Grava UMA linha por task, quando ela termina."""
    nome = getattr(task, "name", None) or getattr(sender, "name", None) or "desconhecida"

    # Evita o log de tarefas de log, para não criar laço.
    if nome.endswith("log_task_activity"):
        return

    detalhes = {
        "task_id": str(task_id) if task_id else None,
        "task_name": nome,
        "status": state,
    }
    if retval is not None:
        chave = "error" if state == "FAILURE" else "return_value"
        detalhes[chave] = str(retval)[:_MAX_TEXTO]

    LogAtividadeUsuario.objects.create(
        usuario=_ator(kwargs),
        acao=f"Task {nome} — {state}"[:255],
        entidade_alvo="CeleryTask",
        detalhes=detalhes,
    )
