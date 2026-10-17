# backend/modulocrm/services.py
"""
Regras de negócio do CRM que rodavam no microsserviço Node `funcoeslead`,
absorvidas como Python (Fase 11.2): conversão e scoring de leads executam
in-process — sem HTTP entre serviços nem token de serviço.
"""
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import Account, Contact, Lead, Opportunity


class LeadNaoConversivel(Exception):
    """Lead fora do estado exigido para conversão."""


SCORE_POR_ORIGEM = {"indicação": 30, "indicacao": 30, "site": 20, "evento": 10}


def calcular_score(lead):
    """Pontuação por regras: origem do lead + completude dos dados de contato."""
    score = SCORE_POR_ORIGEM.get((lead.source or "").strip().lower(), 0)
    if lead.company:
        score += 20
    if lead.phone:
        score += 10
    return score


def pontuar_lead(lead):
    lead.score = calcular_score(lead)
    lead.save(update_fields=["score", "updated_at"])
    return lead


@transaction.atomic
def converter_lead(lead, usuario=None):
    """
    Converte um Lead QUALIFICADO em Account + Contact + Opportunity (estágio
    PROPOSTA, fechamento estimado em 30 dias) e marca o Lead como CONVERTIDO.
    A Account é reaproveitada por nome dentro do tenant e o Contact por
    (account, email); tudo herda o tenant do Lead.
    """
    if lead.status != Lead.StatusChoices.QUALIFICADO:
        raise LeadNaoConversivel("O Lead precisa ter o status 'QUALIFICADO' para ser convertido.")

    responsavel = lead.assigned_to or usuario
    nome_conta = lead.company or f"{lead.first_name} {lead.last_name}"

    account = Account.objects.filter(tenant=lead.tenant, name=nome_conta).first()
    if account is None:
        account = Account.objects.create(
            tenant=lead.tenant,
            name=nome_conta,
            email=lead.email,
            phone=lead.phone,
            assigned_to=responsavel,
        )

    contact, _ = Contact.objects.get_or_create(
        account=account,
        email=lead.email,
        defaults={
            "tenant": lead.tenant,
            "first_name": lead.first_name,
            "last_name": lead.last_name,
            "phone": lead.phone,
        },
    )

    opportunity = Opportunity.objects.create(
        tenant=lead.tenant,
        name=f"Oportunidade - {account.name}",
        account=account,
        contact=contact,
        stage=Opportunity.StageChoices.PROPOSTA,
        close_date=timezone.localdate() + timedelta(days=30),
        assigned_to=responsavel,
    )

    lead.status = Lead.StatusChoices.CONVERTIDO
    lead.save(update_fields=["status", "updated_at"])

    return {
        "message": "Lead convertido.",
        "account_id": str(account.id),
        "contact_id": str(contact.id),
        "opportunity_id": str(opportunity.id),
    }
