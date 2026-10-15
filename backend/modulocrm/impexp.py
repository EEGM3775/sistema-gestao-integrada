# backend/modulocrm/impexp.py
"""O CRM entra e sai como planilha (15/10/2026) — leads, contas, contatos e
oportunidades, sobre o `RecursoDeCadastro`.

**O arquivo vê o que a tela vê.** No CRM quem não é staff enxerga só o que está
sob a responsabilidade dele (`BaseCrmViewSet.get_queryset`); exportar a carteira
inteira por planilha seria a porta lateral dessa regra. E o que entra fica com
quem importou, como o `perform_create` da tela — por isso o usuário vai para o
contexto do lote: a aplicação roda numa requisição posterior, a do "sim".

**Ordem de carga:** contas → contatos → oportunidades. O contato aponta a conta
pelo nome; a oportunidade aponta a conta pelo nome e o contato principal pelo
e-mail **dentro daquela conta** (o e-mail do contato só é único por conta).
Leads não dependem de nada.

**Fica fora do arquivo** o que o sistema calcula ou tem tela própria: a
pontuação do lead (regras/IA), o valor da oportunidade (soma dos produtos), os
produtos, as interações e o vínculo com o cliente do cadastro.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from funcoesimpexp.cadastro import RecursoDeCadastro
from funcoesimpexp.registro import Coluna, registrar

from .models import Account, Campaign, Contact, Lead, Opportunity

RECURSO_LEADS = "crm.lead"
RECURSO_CONTAS = "crm.conta"
RECURSO_CONTATOS = "crm.contato"
RECURSO_OPORTUNIDADES = "crm.oportunidade"


class _RecursoDoCrm(RecursoDeCadastro):
    """O que os quatro têm em comum: módulo, dono do registro e chave sem caixa."""

    modulo = "crm"
    #: Caminho do responsável — o recorte de quem não é staff, como na tela.
    campo_do_dono: str = "assigned_to"

    def validar_contexto(self, contexto, user, tenant_id) -> dict:
        return {**dict(contexto or {}), "usuario": getattr(user, "pk", None)}

    def escopo(self, qs, request):
        if getattr(request.user, "is_staff", False):
            return qs
        return qs.filter(**{self.campo_do_dono: request.user})

    def campos(self, dados: dict, tenant_id) -> dict:
        saida = super().campos(dados, tenant_id)
        if self.campo_do_dono == "assigned_to":
            saida["assigned_to_id"] = self.contexto.get("usuario")
        return saida

    def aplicar_linha(self, dados: dict, existente, tenant_id) -> dict:
        # A PK do CRM é UUID, e o estado do desfazer vai para um campo JSON.
        estado = super().aplicar_linha(dados, existente, tenant_id)
        return {**estado, "pk": str(estado["pk"])}

    def localizar(self, dados: dict, tenant_id):
        # "Ana@X.com" e "ana@x.com" são a mesma pessoa; a mesma conta com outra
        # caixa também — entrar como nova seria a duplicata que a R3 evita.
        chave = self.normalizar_chave(dados.get(self.chave))
        if not chave:
            return None
        return self.modelo._default_manager.filter(
            tenant_id=tenant_id, **{f"{self.chave}__iexact": chave},
        ).first()


@registrar(RECURSO_LEADS)
class LeadsDoCrm(_RecursoDoCrm):
    rotulo = "Leads"
    permissoes_exigidas = ("crm.lead.view", "crm.lead.create")
    modelo = Lead
    chave = "email"
    ordem = ("first_name", "last_name")
    campos_de_busca = ("first_name", "last_name", "email", "company")
    filtros = {"status": "status", "source": "source", "campaign": "campaign_id"}
    referencias = {"campaign": (Campaign, "name")}

    colunas = (
        Coluna("email", "E-mail", obrigatoria=True, exemplo="ana@exemplo.com",
               aliases=("email", "e mail")),
        Coluna("first_name", "Nome", obrigatoria=True, exemplo="Ana", aliases=("primeiro nome",)),
        Coluna("last_name", "Sobrenome", obrigatoria=True, exemplo="Souza"),
        Coluna("phone", "Telefone", exemplo="(71) 99999-0000", aliases=("fone", "celular")),
        Coluna("company", "Empresa", exemplo="Souza Incorporações"),
        Coluna("status", "Status", exemplo="Novo", aliases=("situacao", "situação")),
        Coluna("source", "Origem", exemplo="Indicação", aliases=("origem do lead", "fonte")),
        Coluna("campaign", "Campanha", exemplo="", aliases=("campanha",)),
    )

    def campos(self, dados: dict, tenant_id) -> dict:
        saida = super().campos(dados, tenant_id)
        # Em branco é "Novo", como na tela — o `default` do model só vale
        # quando o campo não é passado, e aqui ele sempre é.
        saida["status"] = saida.get("status") or Lead.StatusChoices.NOVO
        return saida


@registrar(RECURSO_CONTAS)
class ContasDoCrm(_RecursoDoCrm):
    rotulo = "Contas"
    permissoes_exigidas = ("crm.conta.view", "crm.conta.edit")
    modelo = Account
    chave = "name"
    ordem = ("name",)
    campos_de_busca = ("name", "email")

    colunas = (
        Coluna("name", "Conta (empresa)", obrigatoria=True, exemplo="Souza Incorporações",
               aliases=("conta", "empresa", "nome")),
        Coluna("email", "E-mail", exemplo="contato@souza.com.br", aliases=("email", "e mail")),
        Coluna("phone", "Telefone", exemplo="(71) 3333-0000", aliases=("fone",)),
        Coluna("website", "Site", exemplo="www.souza.com.br", aliases=("website",)),
        Coluna("industry", "Setor", exemplo="Incorporação", aliases=("industria", "indústria")),
    )

    def campos(self, dados: dict, tenant_id) -> dict:
        saida = super().campos(dados, tenant_id)
        # "www.souza.com.br" é como as pessoas escrevem site; o `URLField` só
        # aceita com o esquema. O que já tem esquema passa como veio.
        site = str(saida.get("website") or "").strip()
        if site and "://" not in site:
            site = f"https://{site}"
        saida["website"] = site
        return saida


@registrar(RECURSO_CONTATOS)
class ContatosDoCrm(_RecursoDoCrm):
    """O contato. A identidade é **e-mail + conta**, como no banco."""

    rotulo = "Contatos"
    permissoes_exigidas = ("crm.contato.view", "crm.contato.edit")
    modelo = Contact
    chave = "email"
    # O contato não tem responsável: quem o vê é quem gerencia a conta.
    campo_do_dono = "account__assigned_to"
    ordem = ("account__name", "first_name", "last_name")
    campos_de_busca = ("first_name", "last_name", "email", "account__name")
    filtros = {"account": "account_id"}
    referencias = {"account": (Account, "name")}

    colunas = (
        Coluna("email", "E-mail", obrigatoria=True, exemplo="carlos@souza.com.br",
               aliases=("email", "e mail")),
        Coluna("account", "Conta (empresa)", obrigatoria=True, exemplo="Souza Incorporações",
               aliases=("conta", "empresa")),
        Coluna("first_name", "Nome", obrigatoria=True, exemplo="Carlos"),
        Coluna("last_name", "Sobrenome", obrigatoria=True, exemplo="Souza"),
        Coluna("phone", "Telefone", exemplo="(71) 99999-1111", aliases=("fone", "celular")),
        Coluna("title", "Cargo", exemplo="Diretor", aliases=("funcao", "função")),
    )

    def chave_da_linha(self, dados: dict) -> str:
        email = self.normalizar_chave(dados.get("email"))
        conta = str(dados.get("account") or "").strip()
        return f"{email} ({conta})" if email and conta else email

    def localizar(self, dados: dict, tenant_id):
        email = self.normalizar_chave(dados.get("email"))
        conta = self._referencia("account", dados.get("account"), tenant_id)
        if not email or conta is None:
            return None
        return Contact.objects.filter(
            tenant_id=tenant_id, account=conta, email__iexact=email,
        ).first()


@registrar(RECURSO_OPORTUNIDADES)
class OportunidadesDoCrm(_RecursoDoCrm):
    """A oportunidade. A identidade é **nome + conta** — "Torre B" de duas contas
    são duas negociações."""

    rotulo = "Oportunidades"
    permissoes_exigidas = ("crm.oportunidade.view", "crm.oportunidade.create")
    modelo = Opportunity
    chave = "name"
    ordem = ("close_date", "name")
    campos_de_busca = ("name", "account__name")
    filtros = {"stage": "stage", "account": "account_id"}

    @property
    def referencias(self) -> dict:
        from empreendimentos.models import Empreendimento

        return {
            "account": (Account, "name"),
            "empreendimento": (Empreendimento, "empreendimento"),
        }

    colunas = (
        Coluna("name", "Oportunidade", obrigatoria=True, exemplo="Venda Torre B — 12 unidades",
               aliases=("nome", "negocio", "negócio")),
        Coluna("account", "Conta (empresa)", obrigatoria=True, exemplo="Souza Incorporações",
               aliases=("conta", "empresa")),
        Coluna("contact", "E-mail do contato principal", exemplo="carlos@souza.com.br",
               aliases=("contato", "contato principal")),
        Coluna("stage", "Estágio", exemplo="Qualificação", aliases=("etapa", "fase")),
        Coluna("probability", "Probabilidade (%)", tipo=Decimal, exemplo="40",
               aliases=("probabilidade",)),
        Coluna("close_date", "Fechamento previsto", tipo=date, obrigatoria=True,
               exemplo="30/11/2026", aliases=("data de fechamento", "fechamento")),
        Coluna("empreendimento", "Empreendimento", exemplo=""),
    )

    def chave_da_linha(self, dados: dict) -> str:
        nome = self.normalizar_chave(dados.get("name"))
        conta = str(dados.get("account") or "").strip()
        return f"{nome} ({conta})" if nome and conta else nome

    def localizar(self, dados: dict, tenant_id):
        nome = self.normalizar_chave(dados.get("name"))
        conta = self._referencia("account", dados.get("account"), tenant_id)
        if not nome or conta is None:
            return None
        return Opportunity.objects.filter(
            tenant_id=tenant_id, account=conta, name__iexact=nome,
        ).first()

    def serializar_objeto(self, obj) -> dict:
        saida = super().serializar_objeto(obj)
        saida["contact"] = obj.contact.email if obj.contact_id else ""
        return saida

    def campos(self, dados: dict, tenant_id) -> dict:
        saida = super().campos(dados, tenant_id)
        saida["contact"] = self._contato(dados, saida.get("account"))
        saida["stage"] = saida.get("stage") or Opportunity.StageChoices.QUALIFICACAO
        probabilidade = saida.get("probability")
        saida["probability"] = float(probabilidade) if probabilidade is not None else 0.0
        return saida

    def validar_regras(self, objeto, dados, tenant_id) -> str:
        email = str(dados.get("contact") or "").strip()
        if email and objeto.contact is None:
            return (f"Contato “{email}” não existe na conta “{dados.get('account')}” — "
                    "importe os contatos antes.")
        if not 0 <= objeto.probability <= 100:
            return "Probabilidade fora de 0 a 100."
        return ""

    def _contato(self, dados: dict, conta):
        email = str(dados.get("contact") or "").strip()
        if not email or conta is None:
            return None
        return Contact.objects.filter(account=conta, email__iexact=email).first()
