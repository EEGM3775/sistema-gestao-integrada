# backend/funcoescobrancas/services.py
"""
Orquestra a integração Asaas: garante o `customer`, cria a cobrança e aplica a
baixa automática a partir do webhook. A lógica e os models de negócio
continuam no `moduloerp` (`Boleto`, `ContaReceber`) — este módulo só traduz
entre o protocolo Asaas e esses models (ver moduloerp.md §6).
"""
import logging
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.utils import timezone

from nucleo.tenancy import rls_bypass, tenant_context

from .client import AsaasClient
from .models import EventoWebhookAsaas

logger = logging.getLogger(__name__)

# Eventos do Asaas que disparam baixa automática (golden path do MVP). Os
# demais (ex.: PAYMENT_OVERDUE, PAYMENT_DELETED) ficam registrados para
# auditoria, mas não acionam `dar_baixa` nesta fatia.
EVENTOS_DE_BAIXA = ('PAYMENT_RECEIVED', 'PAYMENT_CONFIRMED')


# ─── Trava de segurança de identidade ────────────────────────────────────────
#
# NUNCA emitir cobrança para um cadastro divergente do cliente escolhido. Um
# boleto errado sai no CPF de outra pessoa/empresa e é praticamente impossível
# de estornar sem atrito. Por isso, antes de qualquer emissão, exigimos que
# NOME **e** CPF/CNPJ do cliente do sistema batam com o customer do Asaas —
# CPF igual + nome diferente é tratado como erro (provável digitação), não como
# "mesma pessoa". Ver docs/modulos/funcoescobrancas.md e docs/pendencias.md.

class CobrancaBloqueada(Exception):
    """
    Bloqueio de segurança antes de emitir cobrança. `mensagem` é redigida para
    o usuário final (a UI a exibe direto); `code` permite tratamento
    programático; `contexto` carrega os nomes/documentos para a mensagem.
    """
    code = 'cobranca_bloqueada'

    def __init__(self, mensagem, *, code=None, contexto=None):
        self.mensagem = mensagem
        if code:
            self.code = code
        self.contexto = contexto or {}
        super().__init__(mensagem)


class ClienteSemNome(CobrancaBloqueada):
    code = 'cliente_sem_nome'


class ClienteSemDocumento(CobrancaBloqueada):
    code = 'cliente_sem_documento'


class ClienteDivergenteNoGateway(CobrancaBloqueada):
    code = 'cliente_divergente_no_gateway'


def _somente_digitos(texto):
    return ''.join(filter(str.isdigit, texto or ''))


def _documento_valido(cpf_cnpj):
    """Retorna o documento só com dígitos se tiver tamanho de CPF (11) ou CNPJ (14); senão `None`."""
    digitos = _somente_digitos(cpf_cnpj)
    return digitos if len(digitos) in (11, 14) else None


def _normalizar_nome(nome):
    """
    Normaliza para comparação tolerante a acento/caixa/espaço, mas sensível ao
    conteúdo: "Edison Góes " e "EDISON GOES" batem; "EEGM" e "Edison Goes" não.
    """
    texto = unicodedata.normalize('NFKD', nome or '')
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    return ' '.join(texto.upper().split())


def validar_cliente_para_cobranca(cliente):
    """
    Pré-checagem **não destrutiva** (só leituras) executada ANTES de emitir a
    cobrança — é o "método de o usuário saber o que está acontecendo": a view
    a chama de forma síncrona e devolve a mensagem ao clicar em "Gerar
    cobrança", impedindo o erro em vez de descobri-lo depois.

    Garante que o cliente tem nome + CPF/CNPJ válido e, se já existir um
    customer no Asaas com esse documento, que o **nome bate**. Levanta
    `CobrancaBloqueada` (subclasses) com mensagem pronta para o usuário; quando
    está tudo certo, retorna um dict de diagnóstico consumido por
    `garantir_customer_asaas` (evita repetir a busca no Asaas):

        {'situacao': 'reusar', 'customer_id': '...', 'nome_gateway': '...'}
        {'situacao': 'criar'}
    """
    nome = (cliente.nome_completo or '').strip()
    if not nome:
        raise ClienteSemNome(
            'O cliente não tem nome cadastrado. Complete o cadastro antes de gerar a cobrança.'
        )

    documento = _documento_valido(cliente.cpf_cnpj)
    if not documento:
        raise ClienteSemDocumento(
            f'O cliente "{nome}" não tem um CPF/CNPJ válido cadastrado. '
            'Cadastre o CPF (11 dígitos) ou CNPJ (14 dígitos) antes de gerar a cobrança — '
            'sem ele o boleto não pode ser vinculado ao cliente correto.'
        )

    existente = AsaasClient().buscar_customer_por_cpf_cnpj(documento)
    if existente:
        nome_gateway = existente.get('name', '') or ''
        if _normalizar_nome(nome_gateway) != _normalizar_nome(nome):
            raise ClienteDivergenteNoGateway(
                f'Este CPF/CNPJ já está cadastrado no gateway de cobrança (Asaas) em nome de '
                f'"{nome_gateway}", diferente de "{nome}" cadastrado no sistema. '
                'Se for a mesma pessoa, verifique se o nome ou o CPF/CNPJ foi digitado errado e corrija o cadastro; '
                'se forem pessoas diferentes com o mesmo documento, corrija o CPF/CNPJ. '
                'Por segurança, nenhum boleto foi emitido.',
                contexto={
                    'nome_projeto': nome,
                    'nome_gateway': nome_gateway,
                    'documento': documento,
                    'customer_id': existente.get('id'),
                },
            )
        return {'situacao': 'reusar', 'customer_id': existente.get('id'), 'nome_gateway': nome_gateway}

    return {'situacao': 'criar'}


# ─── Auditoria de divergências banco × Asaas ─────────────────────────────────
#
# Mesma trava de identidade, só que em modo "relatório": varre os clientes e
# aponta, ANTES de qualquer emissão, o que impediria/desviaria uma cobrança.
# Alimenta o comando `manage.py analisar_divergencias_asaas` e o painel que
# aparece ao criar cliente (endpoint `clientes/divergencias-asaas/`).

DIVERGENCIA_SEM_DOCUMENTO = 'sem_documento'
DIVERGENCIA_NOME = 'nome_divergente'
DIVERGENCIA_VINCULO = 'vinculo_divergente'


def analisar_divergencias_asaas(clientes):
    """
    Compara `clientes` (queryset/iterável de `Cliente`) com os customers do
    Asaas e devolve as divergências de identidade que a trava de cobrança
    barraria. Faz UMA varredura paginada da conta (dict por documento) — não um
    GET por cliente. **Somente leitura**: não cria/edita nada.

    Retorna:
        {'total_clientes': N, 'total_divergencias': M, 'divergencias': [
            {'cliente_id', 'nome', 'documento', 'tipo', 'detalhe',
             # + 'nome_gateway'/'customer_id'/'id_cliente_gateway' quando aplicável}
        ]}
    """
    por_documento = {}
    for customer in AsaasClient().iterar_todos_customers():
        doc = _somente_digitos(customer.get('cpfCnpj'))
        if doc:
            por_documento.setdefault(doc, customer)  # 1º cadastro vence (ordem do gateway)

    divergencias = []
    total = 0
    for cliente in clientes:
        total += 1
        nome = (cliente.nome_completo or '').strip()
        documento = _documento_valido(cliente.cpf_cnpj)

        if not documento:
            divergencias.append({
                'cliente_id': cliente.pk,
                'nome': nome,
                'documento': _somente_digitos(cliente.cpf_cnpj),
                'tipo': DIVERGENCIA_SEM_DOCUMENTO,
                'detalhe': 'Sem CPF/CNPJ válido (11 ou 14 dígitos) — não será possível gerar cobrança.',
            })
            continue

        customer = por_documento.get(documento)
        if not customer:
            continue  # ainda não existe no Asaas → nada a corrigir

        nome_gateway = customer.get('name', '') or ''
        if _normalizar_nome(nome_gateway) != _normalizar_nome(nome):
            divergencias.append({
                'cliente_id': cliente.pk,
                'nome': nome,
                'documento': documento,
                'tipo': DIVERGENCIA_NOME,
                'nome_gateway': nome_gateway,
                'customer_id': customer.get('id'),
                'detalhe': f'Mesmo CPF/CNPJ já cadastrado no Asaas em nome de "{nome_gateway}". '
                           'A cobrança fica bloqueada até corrigir o nome ou o CPF/CNPJ.',
            })
        elif cliente.id_cliente_gateway and cliente.id_cliente_gateway != customer.get('id'):
            divergencias.append({
                'cliente_id': cliente.pk,
                'nome': nome,
                'documento': documento,
                'tipo': DIVERGENCIA_VINCULO,
                'nome_gateway': nome_gateway,
                'customer_id': customer.get('id'),
                'id_cliente_gateway': cliente.id_cliente_gateway,
                'detalhe': 'O vínculo salvo (id_cliente_gateway) aponta para outro cadastro do Asaas; '
                           'será autocorrigido na próxima cobrança, mas convém revisar.',
            })

    return {
        'total_clientes': total,
        'total_divergencias': len(divergencias),
        'divergencias': divergencias,
    }


def garantir_customer_asaas(cliente):
    """
    Retorna o `asaas_customer_id` do cliente, criando-o no Asaas (e
    espelhando em `Cliente.id_cliente_gateway`) se ainda não existir.

    A identidade é resolvida SEMPRE pela validação (`validar_cliente_para_cobranca`),
    que é a fonte da verdade por CPF/CNPJ + nome — nunca confiamos cegamente no
    `id_cliente_gateway` salvo, que já foi contaminado no passado por adoção de
    um cadastro alheio (ver docs/pendencias.md). Assim, o vínculo se autocorrige
    e a trava de nome/CPF vale também para o caminho assíncrono da task.
    """
    diagnostico = validar_cliente_para_cobranca(cliente)  # levanta CobrancaBloqueada se divergir

    if diagnostico['situacao'] == 'reusar':
        customer_id = diagnostico['customer_id']
    else:
        criado = AsaasClient().criar_customer(
            nome=cliente.nome_completo,
            cpf_cnpj=_documento_valido(cliente.cpf_cnpj),
            email=cliente.email,
            telefone=cliente.telefone,
        )
        customer_id = criado['id']

    if cliente.id_cliente_gateway != customer_id:
        cliente.id_cliente_gateway = customer_id
        cliente.save(update_fields=['id_cliente_gateway'])
    return customer_id


def gerar_cobranca_asaas(conta_receber):
    """
    Cria a cobrança no Asaas para uma `ContaReceber` e grava/atualiza o
    `Boleto` correspondente (status `EMITIDO`, `gateway_id`, `url_pdf`,
    `linha_digitavel`). Idempotente por conta: reaproveita o `Boleto`
    existente em vez de duplicar a cobrança no gateway.
    """
    from moduloerp.models import Boleto  # import tardio: evita ciclo de apps

    boleto_existente = conta_receber.boletos.filter(gateway_id__isnull=False).exclude(gateway_id='').first()
    if boleto_existente:
        return boleto_existente

    customer_id = garantir_customer_asaas(conta_receber.cliente)
    client = AsaasClient()
    pagamento = client.criar_payment(
        customer_id=customer_id,
        valor=conta_receber.saldo_aberto,
        vencimento=conta_receber.data_vencimento,
        descricao=conta_receber.descricao,
        external_reference=conta_receber.conta_receber_id,
    )

    boleto = Boleto.objects.create(
        tenant=conta_receber.tenant,
        conta_receber=conta_receber,
        status=Boleto.StatusBoleto.EMITIDO,
        valor=conta_receber.saldo_aberto,
        data_vencimento=conta_receber.data_vencimento,
        gateway_id=pagamento.get('id', ''),
        url_pdf=pagamento.get('bankSlipUrl') or pagamento.get('invoiceUrl') or '',
        linha_digitavel=pagamento.get('identificationField') or '',
    )
    return boleto


def _parse_data_pagamento(payment):
    bruto = payment.get('paymentDate') or payment.get('clientPaymentDate') or payment.get('confirmedDate')
    if not bruto:
        return timezone.localdate()
    try:
        return date.fromisoformat(bruto[:10])
    except ValueError:
        return timezone.localdate()


def _parse_valor(payment, campo, default):
    bruto = payment.get(campo)
    if bruto is None:
        return default
    try:
        return Decimal(str(bruto))
    except InvalidOperation:
        return default


def processar_evento_webhook(*, evento_id, tipo, payload):
    """
    Processa (de forma idempotente) um evento recebido do webhook do Asaas.

    Primeira chamada com este `evento_id`: localiza o `Boleto` pelo
    `payment.id`, e — se o evento for de pagamento confirmado — aplica a
    baixa automática via `ContaReceber.dar_baixa(origem='asaas')` (o mesmo
    guard `RevisaoBaixa`/`BaixaRequerRevisao` da baixa manual entra em ação
    se o título já estiver QUITADO/CANCELADO, evitando baixa em dobro).

    Reenvios do Asaas (mesmo `evento_id`) retornam o registro já processado
    sem reaplicar nada — é a idempotência exigida pela integração.
    """
    from moduloerp.models import BaixaRequerRevisao, Boleto

    evento, criado = EventoWebhookAsaas.objects.get_or_create(
        evento_id=evento_id,
        defaults={'tipo': tipo, 'payload': payload},
    )
    if not criado:
        logger.info("Evento Asaas %s já processado — ignorando reenvio.", evento_id)
        return evento

    payment = payload.get('payment') or {}
    gateway_id = payment.get('id')
    # O webhook não tem usuário/tenant e o `payment.id` do Asaas é global: a
    # localização do boleto precisa cruzar tenants, então roda sob o bypass
    # explícito da RLS (código confiável, guardado pelo token do Asaas). Sem
    # isto, sob a política fail-closed (S2), a busca não devolveria linha alguma.
    with rls_bypass():
        boleto = (
            Boleto.objects.select_related('conta_receber', 'conta_receber__cliente')
            .filter(gateway_id=gateway_id)
            .first()
            if gateway_id else None
        )
    evento.boleto = boleto

    if not boleto:
        evento.resultado = f"nenhum Boleto encontrado para gateway_id={gateway_id!r}"
    elif tipo not in EVENTOS_DE_BAIXA:
        evento.resultado = f"evento '{tipo}' registrado, sem ação automática nesta fase"
    elif not boleto.conta_receber:
        evento.resultado = "Boleto sem ContaReceber associada — sem baixa automática"
    else:
        conta = boleto.conta_receber
        # A partir daqui já sabemos o tenant do título: a baixa roda escopada
        # nele (não mais em bypass), para que toda escrita (Transacao, rateios)
        # respeite a RLS do tenant dono do boleto.
        try:
            with tenant_context(boleto.tenant_id):
                conta.dar_baixa(
                    valor=_parse_valor(payment, 'value', conta.saldo_aberto),
                    data=_parse_data_pagamento(payment),
                    meio_pagamento=payment.get('billingType', ''),
                    usuario=None,
                    origem='asaas',
                )
                boleto.status = Boleto.StatusBoleto.PAGO
                boleto.data_pagamento = timezone.now()
                boleto.save(update_fields=['status', 'data_pagamento', 'atualizado_em'])
            evento.resultado = 'baixa automática aplicada'
        except BaixaRequerRevisao as exc:
            evento.resultado = f"encaminhado para revisão do financeiro (RevisaoBaixa #{exc.revisao.revisao_id})"

    evento.processado_em = timezone.now()
    evento.save(update_fields=['boleto', 'resultado', 'processado_em'])
    return evento
