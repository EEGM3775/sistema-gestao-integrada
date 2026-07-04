# Microsserviço `funcoeslead` (Node) — absorvido pelo ERP

> **Serviço descomissionado** (Fase 11.2, antecipada pelo achado L4): toda a lógica roda hoje
> **in-process no ERP**, em Python — **não subir este serviço**. O código Node permanece em
> [backend/funcoeslead/](../../backend/funcoeslead/) apenas como referência até a Fase 11 removê-lo
> do repositório.

## Onde cada função vive agora

| Função que era daqui | Onde vive agora |
|---|---|
| Conversão de lead (lead → account/contact/opportunity) | `modulocrm/services.py::converter_lead` — action `POST /api/crm/leads/{id}/convert/` |
| Scoring de lead | `modulocrm/services.py::calcular_score` — action `POST /api/crm/leads/{id}/score/` |
| Agenda unificada (interações CRM no calendário) | consulta direta no `modulocalendar` (`_crm_events`) |
| Notificações de tarefas a vencer (e-mail) | Celery task `modulocrm/tasks.py::notificar_tarefas_a_vencer` (beat horário; no-op sem `MAIL_HOST`) |
| CRUD de produtos de oportunidade | já era nativo do ERP: `/api/crm/opportunity-products/` |
| Integração Google Calendar | **não portada** — reintegração é decisão futura (ver [modulocalendar.md](modulocalendar.md)) |

Detalhes em [modulocrm.md](modulocrm.md) e [modulocalendar.md](modulocalendar.md).
