# Calendário (`modulocalendar`)

> Agenda unificada: agrega eventos de múltiplas fontes numa única API compatível com FullCalendar.
> Código: [backend/modulocalendar/](../../backend/modulocalendar/).

## Fontes de dados

1. **Eventos locais** — modelo `CalendarEvent` (criados na interface do calendário).
2. **Feriados nacionais** — API externa [Nager.Date](https://date.nager.at/), como eventos de dia
   inteiro, buscados para cada ano coberto pelo período consultado.
3. **CRM** — tarefas e reuniões (`Interaction`) atribuídas ao usuário (direto ou via lead sob sua
   responsabilidade), consultadas **in-process** no `modulocrm` (o microsserviço funcoeslead foi
   absorvido — Fase 11.2). Google Calendar saiu do fluxo; reintegração é decisão futura.

## API

`GET /api/calendar/events/` (rota em `modulocalendar/urls.py`, incluída por `config/urls.py`)

- **Auth:** `IsAuthenticated` (módulo base, sem `RequireModule`).
- **Query:** `start` e `end` em ISO 8601 (ex.: `2026-01-01T00:00:00-03:00`).
- **Resposta:** array JSON de eventos no formato [FullCalendar](https://fullcalendar.io/);
  `extendedProps.type` identifica a fonte (`local`, `diario_obra`, `holiday`); eventos locais
  trazem `id` (edição/exclusão via CRUD do ViewSet).

## Cache

- Django cache com Redis (`django-redis`); chave por usuário + intervalo consultado; **TTL 30 s**.
- Invalidação automática quando: (a) um `CalendarEvent` do usuário muda; (b) uma `Interaction`
  associada a ele muda (signal do `modulocrm` → este módulo).

A invalidação por `Interaction` usa o sinal `interaction_changed` do `modulocrm`
(receiver em `receivers.py`).
