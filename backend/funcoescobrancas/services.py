# backend/funcoescobrancas/services.py
"""
Orquestra a integração Asaas: garante o `customer`, cria a cobrança e aplica a
baixa automática a partir do webhook. A lógica e os models de negócio
continuam no `moduloerp` (`Boleto`, `ContaReceber`) — este módulo só traduz
entre o protocolo Asaas e esses models (ver moduloerp.md §6).

**O que o SGI escreve no boleto, e o que não é dele.** O `POST /payments` leva
exatamente seis campos: `customer`, `billingType`, `value`, `dueDate`,
`description` e `externalReference` (ver `client.criar_payment`). Tudo o mais
que aparece impresso — o campo *Instruções*, com frases do tipo "Não receber
com cheque", o comportamento após o vencimento, juros e multa de boleto — é
**configuração da conta Asaas**, escolhida no painel do gateway, e vale para
toda cobrança emitida por aquela conta. Mudá-lo é lá, não aqui; nenhuma linha
deste módulo pode alterá-lo, e fingir o contrário seria vender controle que não
existe. O que é nosso, e portanto ajustável aqui, é a **descrição** (montada em
`clientes.plano_pagamento.descricao_do_titulo`) e o **vencimento** enviado (ver
`vencimento_bancario`).
"""
import logging
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.db.models import Q
from django.utils import timezone

from nucleo.tenancy import rls_bypass, tenant_context

from .client import AsaasClient, AsaasAPIError
from .models import EventoWebhookAsaas

logger = logging.getLogger(__name__)

# Eventos do Asaas que disparam baixa automática (golden path do MVP). Os
# demais (ex.: PAYMENT_OVERDUE, PAYMENT_DELETED) ficam registrados para
# auditoria, mas não acionam `dar_baixa` nesta fatia.
EVENTOS_DE_BAIXA = ('PAYMENT_RECEIVED', 'PAYMENT_CONFIRMED')

# Eventos que sinalizam cancelamento/remoção da cobrança no Asaas → refletem o
# boleto local como CANCELADO (o cancelamento pode nascer fora do SGI).
EVENTOS_DE_CANCELAMENTO = ('PAYMENT_DELETED',)


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


class CobrancaRejeitada(CobrancaBloqueada):
    """
    O Asaas recusou a cobrança por erro **permanente** de dados (4xx — ex.: CPF
    inválido). Como `CobrancaBloqueada`, a task NÃO reprocessa (retry não ajuda);
    o erro já foi persistido num `Boleto` status ERRO, com os códigos do gateway,
    para a UI abrir no popup de detalhes.
    """
    code = 'cobranca_rejeitada_gateway'

    def __init__(self, mensagem, *, payload=None, status_code=None):
        self.payload = payload
        self.status_code = status_code
        super().__init__(mensagem, contexto={'payload': payload, 'status_code': status_code})


# Traduz o status cru de um payment do Asaas para o `StatusBoleto` local.
# Usado pela verificação ao vivo (a UI abre o documento e confere o gateway).
def _mapear_status_boleto(asaas_status):
    from moduloerp.models import Boleto
    return {
        'PENDING': Boleto.StatusBoleto.EMITIDO,
        'AWAITING_RISK_ANALYSIS': Boleto.StatusBoleto.EMITIDO,
        'RECEIVED': Boleto.StatusBoleto.PAGO,
        'CONFIRMED': Boleto.StatusBoleto.PAGO,
        'RECEIVED_IN_CASH': Boleto.StatusBoleto.PAGO,
        'OVERDUE': Boleto.StatusBoleto.VENCIDO,
        'REFUNDED': Boleto.StatusBoleto.CANCELADO,
        'DELETED': Boleto.StatusBoleto.CANCELADO,
    }.get(asaas_status, Boleto.StatusBoleto.EMITIDO)


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


def _registrar_boleto_erro(conta_receber, exc):
    """
    Persiste (ou atualiza) um `Boleto` status ERRO com o payload cru do Asaas —
    é o que faz o erro APARECER no frontend (lista de Boletos + na própria Conta
    a Receber, que aninha `boletos[]`), em vez de morrer só na fila interna.
    Reaproveita um ERRO anterior da mesma conta para não empilhar boletos a cada
    tentativa. Nunca sobrescreve um boleto já emitido (esse tem `gateway_id`).
    """
    from moduloerp.models import Boleto

    detalhes = {
        'erro': str(exc),
        'status_code': getattr(exc, 'status_code', None),
        'detalhes': getattr(exc, 'payload', None),
    }
    boleto = (
        conta_receber.boletos
        .filter(status=Boleto.StatusBoleto.ERRO)
        .filter(Q(gateway_id__isnull=True) | Q(gateway_id=''))
        .first()
    )
    if boleto:
        boleto.status = Boleto.StatusBoleto.ERRO
        boleto.valor = conta_receber.saldo_aberto
        boleto.data_vencimento = conta_receber.data_vencimento
        boleto.dados_retorno_api = detalhes
        boleto.save(update_fields=['status', 'valor', 'data_vencimento', 'dados_retorno_api', 'atualizado_em'])
        return boleto
    return Boleto.objects.create(
        tenant=conta_receber.tenant,
        conta_receber=conta_receber,
        status=Boleto.StatusBoleto.ERRO,
        valor=conta_receber.saldo_aberto,
        data_vencimento=conta_receber.data_vencimento,
        dados_retorno_api=detalhes,
    )


def vencimento_bancario(conta_receber):
    """A data pagável do título: o vencimento do contrato, ou o próximo dia útil.

    **O título não muda; o boleto sim.** `ContaReceber.data_vencimento` é o que
    foi combinado no contrato e é por ele que se conta atraso, juros e multa —
    mexer nele para caber no calendário do banco reescreveria a dívida. O que se
    ajusta é a data impressa no boleto (`Boleto.data_vencimento`, e o `dueDate`
    que vai ao gateway), porque um boleto com vencimento no sábado não é pagável
    no sábado: ele nasce, na prática, vencido.

    A praça é a do **imóvel** — os feriados que valem são os do município do
    empreendimento, não os da cidade do comprador. Quando o título não tem
    empreendimento (lançamento avulso do financeiro), sobra fim de semana +
    feriado nacional, que já é melhor que nada.

    Devolve `(data, motivo)`; `motivo` vazio significa que a data do contrato já
    era útil e nada foi empurrado.
    """
    from clientes.vencimento import ajuste_da_conta

    return ajuste_da_conta(conta_receber).explicar(conta_receber.data_vencimento)


def gerar_cobranca_asaas(conta_receber, vencimento_pedido=None):
    """
    Cria a cobrança no Asaas para uma `ContaReceber` e grava o `Boleto`
    correspondente (status `EMITIDO`, `gateway_id`, `url_pdf`,
    `linha_digitavel`).

    **O plano é o da prévia** (`segunda_via.planejar`): a data sai ajustada para
    o dia útil, e título vencido leva multa e juros do contrato até ela. O que a
    tela mostrou é o que o boleto carrega.

    **Idempotente por conta:** se já existe um boleto ativo com a mesma data e o
    mesmo valor, é ele que volta — clique duplo ou reprocessamento da task não
    duplicam a cobrança no gateway. Com data ou valor diferentes é **segunda
    via**: o boleto anterior é cancelado no Asaas antes do novo nascer, para o
    cliente nunca ter dois boletos válidos da mesma parcela. Boleto pago ou
    cancelado não conta — a conta parcialmente paga ganha boleto do que falta.

    Se o Asaas recusar, o erro é PERSISTIDO num `Boleto` status ERRO (com os
    códigos/mensagens do gateway) para a UI mostrar — não fica invisível. Erro
    permanente (4xx, ex.: CPF inválido) → `CobrancaRejeitada` (sem retry);
    indisponibilidade (5xx/rede) → propaga `AsaasAPIError` (a task reprocessa).
    """
    from moduloerp.models import Boleto  # import tardio: evita ciclo de apps
    from .segunda_via import boleto_ativo, planejar

    plano = planejar(conta_receber, vencimento_pedido)
    vencimento = plano['vencimento_bancario']
    motivo_do_ajuste = plano['motivo_ajuste']
    valor = plano['total']

    anterior = boleto_ativo(conta_receber)
    if anterior and anterior.data_vencimento == vencimento and anterior.valor == valor:
        return anterior
    try:
        if anterior:
            cancelar_cobranca_asaas(anterior)
        customer_id = garantir_customer_asaas(conta_receber.cliente)
        client = AsaasClient()
        pagamento = client.criar_payment(
            customer_id=customer_id,
            valor=valor,
            vencimento=vencimento,
            descricao=conta_receber.descricao,
            external_reference=conta_receber.conta_receber_id,
        )
    except AsaasAPIError as exc:
        _registrar_boleto_erro(conta_receber, exc)
        status_code = getattr(exc, 'status_code', None)
        if status_code and 400 <= status_code < 500:
            # Dado inválido — repetir não ajuda; já está visível como Boleto ERRO.
            raise CobrancaRejeitada(str(exc), payload=getattr(exc, 'payload', None), status_code=status_code) from exc
        raise  # 5xx/rede: transitório → a task faz retry

    linha = _linha_digitavel_do_asaas(client, pagamento.get('id'))
    boleto = Boleto.objects.create(
        tenant=conta_receber.tenant,
        conta_receber=conta_receber,
        status=Boleto.StatusBoleto.EMITIDO,
        valor=valor,
        valor_multa=plano['multa'],
        valor_juros=plano['juros'],
        data_vencimento=vencimento,
        gateway_id=pagamento.get('id', ''),
        url_pdf=pagamento.get('bankSlipUrl') or pagamento.get('invoiceUrl') or '',
        linha_digitavel=linha.get('linha_digitavel', ''),
        codigo_barras=linha.get('codigo_barras', ''),
        nosso_numero=linha.get('nosso_numero') or pagamento.get('nossoNumero') or '',
        dados_retorno_api={
            'emissao': pagamento,
            # Por que a data do boleto difere da do título — a resposta fica
            # junto do boleto, que é onde a pergunta é feita.
            **({'ajuste_de_vencimento': {
                'contratual': conta_receber.data_vencimento.isoformat(),
                'bancario': vencimento.isoformat(),
                'motivo': motivo_do_ajuste,
            }} if motivo_do_ajuste else {}),
            **({'segunda_via': {
                'substitui_boleto': anterior.boleto_id if anterior else None,
                'dias': plano['dias_encargos'],
                'multa_percentual': str(plano['multa_percentual']),
                'juros_mes_percentual': str(plano['juros_mes_percentual']),
            }} if plano['multa'] or plano['juros'] or anterior else {}),
        },
    )
    return boleto


def _linha_digitavel_do_asaas(client, payment_id) -> dict:
    """Linha digitável, código de barras e nosso número — ou `{}` se não vier.

    Boleto emitido sem linha digitável ainda é boleto (o PDF existe); por isso
    a falha aqui não derruba a emissão: a verificação ao abrir o documento
    pergunta de novo.
    """
    if not payment_id:
        return {}
    try:
        resposta = client.buscar_linha_digitavel(payment_id) or {}
    except AsaasAPIError as exc:
        logger.warning("Asaas não deu a linha digitável de %s: %s", payment_id, exc)
        return {}
    return {
        'linha_digitavel': resposta.get('identificationField') or '',
        'codigo_barras': resposta.get('barCode') or '',
        'nosso_numero': resposta.get('nossoNumero') or '',
    }


def cancelar_cobranca_asaas(boleto):
    """
    Cancela a cobrança no Asaas (DELETE /payments/{id}) e marca o `Boleto` como
    CANCELADO, carimbando `data_cancelamento` e guardando a resposta do gateway.
    Idempotente: um boleto já cancelado (ou sem `gateway_id`) só é normalizado
    localmente, sem nova chamada. Propaga `AsaasAPIError` se o Asaas recusar.
    """
    from moduloerp.models import Boleto

    if boleto.status == Boleto.StatusBoleto.CANCELADO:
        return boleto
    resposta = {}
    if boleto.gateway_id:
        resposta = AsaasClient().cancelar_payment(boleto.gateway_id)
    boleto.status = Boleto.StatusBoleto.CANCELADO
    boleto.data_cancelamento = timezone.now()
    dados = boleto.dados_retorno_api if isinstance(boleto.dados_retorno_api, dict) else {}
    dados = {**dados, 'cancelamento': resposta}
    boleto.dados_retorno_api = dados
    boleto.save(update_fields=['status', 'data_cancelamento', 'dados_retorno_api', 'atualizado_em'])
    return boleto


def verificar_cobranca_asaas(boleto):
    """
    Verifica AO VIVO o estado do boleto no Asaas (GET /payments/{id}) — é o que
    a UI chama ao abrir o documento: **gateway no ar** → devolve a verdade do
    Asaas (status + URL atual do boleto) e a persiste; **gateway fora do ar** →
    devolve a última versão guardada e sinaliza `gateway_online=False` para a UI
    avisar que o Asaas está indisponível. Nunca levanta exceção de rede.

    Retorna: {'gateway_online', 'status', 'url_pdf', 'linha_digitavel',
              'mensagem'}.
    """
    if not boleto.gateway_id:
        return {
            'gateway_online': False,
            'status': boleto.status,
            'url_pdf': boleto.url_pdf or '',
            'linha_digitavel': boleto.linha_digitavel or '',
            'mensagem': 'Boleto sem vínculo no gateway — exibindo a versão local.',
        }
    client = AsaasClient()
    try:
        pagamento = client.buscar_payment(boleto.gateway_id)
    except AsaasAPIError as exc:
        logger.warning("Asaas indisponível ao verificar boleto #%s: %s", boleto.boleto_id, exc)
        return {
            'gateway_online': False,
            'status': boleto.status,
            'url_pdf': boleto.url_pdf or '',
            'linha_digitavel': boleto.linha_digitavel or '',
            'mensagem': 'Asaas fora do ar — exibindo a última versão conhecida do boleto.',
        }

    novo_status = _mapear_status_boleto(pagamento.get('status'))
    url_pdf = pagamento.get('bankSlipUrl') or pagamento.get('invoiceUrl') or boleto.url_pdf or ''
    linha = boleto.linha_digitavel or ''
    campos = []
    from moduloerp.models import Boleto
    if not linha and novo_status in (Boleto.StatusBoleto.EMITIDO, Boleto.StatusBoleto.VENCIDO):
        # Boleto emitido antes de 01/10/2026 (ou cuja linha não veio na hora):
        # a primeira abertura completa.
        extra = _linha_digitavel_do_asaas(client, boleto.gateway_id)
        linha = extra.get('linha_digitavel', '')
        for campo in ('codigo_barras', 'nosso_numero'):
            if extra.get(campo) and not getattr(boleto, campo):
                setattr(boleto, campo, extra[campo])
                campos.append(campo)
    if boleto.status != novo_status:
        boleto.status = novo_status
        campos.append('status')
        if novo_status == Boleto.StatusBoleto.CANCELADO and not boleto.data_cancelamento:
            boleto.data_cancelamento = timezone.now()
            campos.append('data_cancelamento')
    if url_pdf and boleto.url_pdf != url_pdf:
        boleto.url_pdf = url_pdf
        campos.append('url_pdf')
    if linha and boleto.linha_digitavel != linha:
        boleto.linha_digitavel = linha
        campos.append('linha_digitavel')
    if campos:
        boleto.save(update_fields=[*campos, 'atualizado_em'])
    return {
        'gateway_online': True,
        'status': boleto.status,
        'url_pdf': url_pdf,
        'linha_digitavel': linha,
        'mensagem': '',
    }


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
    elif tipo in EVENTOS_DE_CANCELAMENTO:
        # Cancelado direto no Asaas (ou por outro sistema): reflete o cancelamento
        # no boleto local para que a UI mostre o estado correto (aba Cancelados).
        with tenant_context(boleto.tenant_id):
            if boleto.status != Boleto.StatusBoleto.CANCELADO:
                boleto.status = Boleto.StatusBoleto.CANCELADO
                boleto.data_cancelamento = timezone.now()
                dados = boleto.dados_retorno_api if isinstance(boleto.dados_retorno_api, dict) else {}
                boleto.dados_retorno_api = {**dados, 'cancelamento_webhook': payment}
                boleto.save(update_fields=['status', 'data_cancelamento', 'dados_retorno_api', 'atualizado_em'])
        evento.resultado = f"boleto cancelado via webhook ('{tipo}')"
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
                pago = _parse_valor(payment, 'value', conta.saldo_aberto)
                # Segunda via (item 55): o boleto embutiu multa e juros. Pago o
                # valor cheio, os encargos entram como encargos — somados ao
                # principal, a baixa passaria do saldo e iria para revisão.
                multa = juros = Decimal('0')
                if (boleto.valor_multa or boleto.valor_juros) and pago >= boleto.valor:
                    multa, juros = boleto.valor_multa, boleto.valor_juros
                conta.dar_baixa(
                    valor=pago - multa - juros,
                    multa=multa,
                    juros=juros,
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
