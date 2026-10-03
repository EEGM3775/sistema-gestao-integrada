# backend/clientes/views.py
from nucleo.busca import BuscaSemAcento
from rest_framework import viewsets, permissions, filters, status as drf_status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Count, Max
from django.utils import timezone
from django.utils.dateparse import parse_date
from django_filters.rest_framework import DjangoFilterBackend
from empreendimentos.models import Unidade
from nucleo.tenancy import TenantScopedViewSetMixin, TenantScopedAPIViewMixin
from nucleo import autorizacao
from nucleo.permissions import RequirePermission
from nucleo.field_masking import mask_document_unless
from nucleo.quotas import QuotaEnforcedMixin
from nucleo.models import IndiceEconomico
from funcoescobrancas.services import analisar_divergencias_asaas
from funcoescobrancas.client import AsaasAPIError
from moduloerp.models import ContaReceber, StatusConta
from payment.planos import VENDA_TETO_MEIOS_DE_PAGAMENTO
from . import carteira as carteira_svc
from . import correcao
from . import plano_pagamento
from . import vencimento as vencimento_svc
from .models import (
    Cliente,
    ClienteEmpreendimento,
    ContratoCliente,
    DocumentoCliente,
    DadoBancarioCliente
)
from .serializers import (
    ClienteSerializer,
    ClienteEmpreendimentoSerializer,
    ContratoClienteSerializer,
    DocumentoClienteSerializer,
    DadoBancarioClienteSerializer
)
from .filters import (
    ClienteFilter,
    ClienteEmpreendimentoFilter,
    ContratoClienteFilter,
    DocumentoClienteFilter,
)
from .pagination import ClientePageNumberPagination


class ClienteViewSet(QuotaEnforcedMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    quota_recurso = "clientes"  # D24
    queryset = Cliente.objects.all().order_by('nome_completo')
    serializer_class = ClienteSerializer
    filter_backends = [DjangoFilterBackend, BuscaSemAcento, filters.OrderingFilter]
    filterset_class = ClienteFilter
    search_fields = ['nome_completo', 'email', 'telefone', 'bairro', 'cidade', 'cep']
    ordering_fields = ['nome_completo', 'data_cadastro', 'cidade', 'estado', 'email', 'telefone']
    ordering = ['nome_completo']
    pagination_class = ClientePageNumberPagination
    permission_classes = [permissions.IsAuthenticated, RequirePermission]
    required_resource = "cadastro.cliente"  # GET→.view · escrita→.edit

    def campos_de_busca(self, request):
        """O CPF/CNPJ só é critério de busca para quem pode lê-lo (LGPD; D257):
        buscar por ele e ver quem volta é ler o documento que a máscara esconde."""
        campos = list(self.search_fields)
        if _pode_documento(request):
            campos.append('cpf_cnpj')
        return campos

    @action(detail=False, methods=['get'], url_path='divergencias-asaas')
    def divergencias_asaas(self, request):
        """
        Relatório (só leitura) das divergências de identidade entre os clientes
        deste tenant e os customers do Asaas — o mesmo critério que barra a
        emissão de cobrança. Consumido no fluxo de gerar cobrança e no botão-alerta
        do hub do ERP (D3), para ver o que impediria/desviaria um boleto.

        **Gate (LGPD + escopo):** é dado **financeiro** que carrega **PII de
        cliente**, logo exige as DUAS pontas — `cadastro.cliente.view` (acesso aos
        clientes, já imposto pelo `RequirePermission` do viewset no GET) **e**
        `erp.cobranca.view` (checado explícito aqui). `hasModule` não basta: é
        entitlement do **tenant**, não permissão do **usuário** (um `operacional`
        num tenant com ERP não deve ver isto). O documento (CPF/CNPJ) ainda vem
        **mascarado** para quem não tem `cadastro.cliente_doc.view` (regra da 9.C).
        """
        if not autorizacao.pode(request.user, "erp.cobranca.view"):
            return Response(
                {'detail': 'Requer permissão de cobranças (erp.cobranca.view).'},
                status=drf_status.HTTP_403_FORBIDDEN,
            )
        try:
            relatorio = analisar_divergencias_asaas(self.get_queryset())
        except AsaasAPIError as exc:
            return Response(
                {'detail': f'Não foi possível consultar o gateway de cobrança (Asaas) agora: {exc}'},
                status=drf_status.HTTP_502_BAD_GATEWAY,
            )
        for d in relatorio.get('divergencias', []):
            d['documento'] = mask_document_unless(request.user, d.get('documento'))
        return Response(relatorio)

    @action(detail=True, methods=['get'], url_path='financeiro')
    def financeiro(self, request, pk=None):
        """Extrato do cliente: parcelas, boletos emitidos e o resumo da dívida.

        É a aba **Financeiro** da ficha. Mesmo gate de duas pontas da carteira —
        sem `erp.cobranca.view` não devolve extrato, porque parcela e valor são
        dado financeiro de pessoa natural (a situação adimplente/inadimplente,
        essa sim, a carteira já mostra a todos).
        """
        if not _pode_financeiro(request):
            return Response(
                {'detail': 'Requer permissão de cobranças (erp.cobranca.view).'},
                status=drf_status.HTTP_403_FORBIDDEN,
            )
        cliente = self.get_object()
        hoje = carteira_svc.hoje_local()
        parcelas = (
            self._scope(ContaReceber.objects.filter(cliente=cliente))
            .select_related('cliente_empreendimento', 'cliente_empreendimento__empreendimento', 'empreendimento')
            .prefetch_related('boletos')
            .order_by('data_vencimento')
        )

        linhas, aberto, atraso, pago, em_atraso = [], Decimal('0'), Decimal('0'), Decimal('0'), 0
        for p in parcelas:
            saldo = p.saldo_aberto
            vencida = p.status in carteira_svc.STATUS_EM_ABERTO and p.data_vencimento < hoje
            if p.status in carteira_svc.STATUS_EM_ABERTO:
                aberto += saldo
                if vencida:
                    atraso += saldo
                    em_atraso += 1
            pago += p.valor_pago
            boleto = next(iter(p.boletos.all()), None)
            linhas.append({
                'id': p.pk,
                'descricao': p.descricao,
                'vencimento': p.data_vencimento.isoformat(),
                'valor': str(p.total_devido),
                'pago': str(p.valor_pago),
                'saldo': str(saldo),
                'status': p.status,
                'diasAtraso': (hoje - p.data_vencimento).days if vencida else 0,
                'recebimento': p.data_recebimento.isoformat() if p.data_recebimento else None,
                'unidade': p.cliente_empreendimento.rotulo_unidade if p.cliente_empreendimento else None,
                'empreendimento': (
                    p.cliente_empreendimento.empreendimento.empreendimento
                    if p.cliente_empreendimento else
                    (p.empreendimento.empreendimento if p.empreendimento else None)
                ),
                'boleto': {
                    'id': boleto.pk,
                    'status': boleto.status,
                    'linhaDigitavel': boleto.linha_digitavel,
                    'urlPdf': boleto.url_pdf,
                    'vencimento': boleto.data_vencimento.isoformat(),
                } if boleto else None,
            })

        return Response({
            'resumo': {
                'valorAberto': str(aberto),
                'valorAtraso': str(atraso),
                'valorPago': str(pago),
                'parcelasAtraso': em_atraso,
                'parcelasTotal': len(linhas),
                # Item 60: sem parcela (cancelada não conta) não há adimplência
                # a afirmar — `None`, a mesma régua da pílula da carteira.
                'adimplente': (
                    em_atraso == 0
                    if any(l['status'] != StatusConta.CANCELADO for l in linhas) else None
                ),
            },
            'parcelas': linhas,
        })

    @action(detail=True, methods=['get'], url_path='obra')
    def obra(self, request, pk=None):
        """Andamento das obras dos empreendimentos que este cliente comprou.

        É a aba **Obra** da ficha — a conversa entre módulos aparecendo na tela
        (frontend.md §1.6.6): quem comprou a unidade acompanha o que está sendo
        construído. O percentual é a **média das etapas** da obra e vem declarado
        como tal; obra sem etapa cadastrada devolve `percentual: null` em vez de
        um zero que pareceria "parada".
        """
        from obras.models import Obra

        cliente = self.get_object()
        aquisicoes = self._scope(
            ClienteEmpreendimento.objects.filter(cliente=cliente).select_related('empreendimento')
        )
        ids = {a.empreendimento_id for a in aquisicoes}
        obras = (
            self._scope(Obra.objects.filter(empreendimento_id__in=ids))
            .select_related('empreendimento')
            .prefetch_related('etapas')
            .order_by('nome_obra')
        )

        saida = []
        for obra in obras:
            etapas = list(obra.etapas.all())
            media = (
                sum((e.percentual_conclusao or Decimal('0')) for e in etapas) / len(etapas)
                if etapas else None
            )
            saida.append({
                'id': obra.pk,
                'nome': obra.nome_obra,
                'status': obra.status_obra,
                'empreendimento': obra.empreendimento.empreendimento if obra.empreendimento else None,
                'empreendimentoId': obra.empreendimento_id,
                'inicioPrevisto': obra.data_inicio_prevista.isoformat() if obra.data_inicio_prevista else None,
                'fimPrevisto': obra.data_fim_prevista.isoformat() if obra.data_fim_prevista else None,
                'fimReal': obra.data_fim_real.isoformat() if obra.data_fim_real else None,
                'percentual': round(float(media), 1) if media is not None else None,
                'etapasTotal': len(etapas),
                'etapas': [{
                    'id': e.pk,
                    'nome': e.nome_etapa,
                    'status': e.status_etapa,
                    'percentual': float(e.percentual_conclusao or 0),
                    'fimPrevisto': e.data_fim_prevista.isoformat() if e.data_fim_prevista else None,
                } for e in etapas],
            })

        return Response({
            'unidades': [{
                'id': a.pk,
                'unidade': a.rotulo_unidade,
                'empreendimento': a.empreendimento.empreendimento,
                'empreendimentoId': a.empreendimento_id,
            } for a in aquisicoes],
            'obras': saida,
        })


class ClienteEmpreendimentoViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    # `meios` no prefetch: o resumo do plano de cada linha é montado a partir
    # deles, e sem isto a lista faria uma consulta por aquisição.
    queryset = ClienteEmpreendimento.objects.select_related(
        'cliente', 'empreendimento', 'unidade'
    ).prefetch_related('meios').order_by('-data_compra')
    serializer_class = ClienteEmpreendimentoSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = ClienteEmpreendimentoFilter
    ordering_fields = ['data_compra', 'valor_compra']
    ordering = ['-data_compra']
    permission_classes = [permissions.IsAuthenticated, RequirePermission]
    # A venda tem permissão própria, não a de cadastro: registrar uma aquisição
    # tira a unidade da praça e o carnê cria títulos a receber no ERP. Enquanto
    # os dois dividiam `cadastro.cliente.edit`, quem podia corrigir o telefone
    # de um comprador podia vender um lote e emitir a dívida dele.
    required_resource = "cadastro.venda"
    action_permission_map = {
        # Simular é leitura: a proposta é anterior à venda e não grava nada — o
        # corretor precisa cotar antes de ter permissão para fechar.
        "condicoes": "cadastro.venda.view",
        "simular": "cadastro.venda.view",
        # Ver o carnê que sairia é leitura, como simular: quem pode cotar pode
        # conferir o que seria criado antes de pedir a emissão a quem a emite.
        "previa_parcelas": "cadastro.venda.view",
        "gerar_parcelas": "cadastro.venda.gerar_carne",
        # Reajustar mexe no valor de títulos já emitidos — é a mesma classe de
        # ato que emitir o carnê, não edição de venda.
        "corrigir": "cadastro.venda.gerar_carne",
    }

    @action(detail=False, methods=['get'], url_path='condicoes')
    def condicoes(self, request):
        """`GET /api/clientes-empreendimentos/condicoes/` — o que cada meio de
        pagamento comporta (`meios`), e como a venda inteira é rotulada na
        carteira (`condicoes`).

        Existe para o formulário **ler** a regra em vez de reescrevê-la. Ela
        morava duplicada: um `PLANO_DA_CONDICAO` no React decidia quais campos
        mostrar, e o motor de cálculo decidia, por conta própria, o que aceitar.
        Duas cópias da mesma regra é uma que um dia discorda da outra — e a que
        discorda em silêncio é a da tela, porque ela some do rastro.

        Leitura pura, sem tenant: é o catálogo do produto, igual para todo mundo.
        """
        return Response({
            'meios': [t.como_dict() for t in plano_pagamento.TIPOS_DE_MEIO.values()],
            'condicoes': [
                {'codigo': codigo, 'rotulo': str(rotulo)}
                for codigo, rotulo in ClienteEmpreendimento.CONDICOES_PAGAMENTO_CHOICES
            ],
            'tetoMeios': VENDA_TETO_MEIOS_DE_PAGAMENTO,
        })

    @action(detail=False, methods=['post'], url_path='simular')
    def simular(self, request):
        """`POST /api/clientes-empreendimentos/simular/` — a proposta sem gravar.

        Existe para a tela recalcular a cada tecla enquanto o vendedor negocia:
        um cálculo que só acontece no submit obriga a salvar para ver o preço, e
        a conta do corretor passa a ser feita fora do sistema. **Não grava nada**
        e não exige aquisição existente — a proposta é anterior à venda.
        """
        dados = request.data or {}
        unidade_id = dados.get('unidade')
        valor_tabela = dados.get('valor_tabela')
        unidade = None
        if unidade_id:
            unidade = (
                self._scope(Unidade.objects.select_related('empreendimento'))
                .filter(pk=unidade_id).first()
            )
            if unidade is None:
                return Response({'unidade': 'Unidade não encontrada.'}, status=400)
            if valor_tabela in (None, ''):
                valor_tabela = unidade.valor_base

        # O carnê simulado é o carnê que vai ser emitido — e nele não existe
        # vencimento no domingo. Simular sem o calendário mostraria ao comprador
        # datas que o boleto não vai ter.
        ajuste = vencimento_svc.ajuste_do_empreendimento(
            unidade.empreendimento if unidade else None
        )

        try:
            meios = dados.get('meios') or []
            if not isinstance(meios, list):
                raise ValueError('Os meios de pagamento vêm em lista.')
            plano = plano_pagamento.montar(
                valor_tabela=_decimal(valor_tabela),
                desconto_percentual=_decimal(dados.get('desconto_percentual')),
                desconto_valor=_decimal(dados.get('desconto_valor')),
                meios=[m if isinstance(m, dict) else {} for m in meios],
                data_compra=_data(dados.get('data_compra')),
                ajustar_vencimento=ajuste,
            )
        except (ValueError, InvalidOperation) as erro:
            resposta = {'detail': str(erro)}
            try:
                resposta['valorNegociado'] = str(plano_pagamento.negociar(
                    _decimal(valor_tabela), _decimal(dados.get('desconto_percentual')),
                    _decimal(dados.get('desconto_valor')),
                )[2])
            except (ValueError, InvalidOperation):
                pass
            return Response(resposta, status=400)
        return Response({
            **plano.como_dict(),
            # A tela precisa poder dizer "ajustado para o próximo dia útil" e,
            # quando a base de feriados nunca foi sincronizada, precisa dizer que
            # só desviou de sábado e domingo. Prometer feriado que não se conhece
            # é o oposto de dado honesto.
            'calendario': _estado_do_calendario(ajuste),
        })

    @action(detail=True, methods=['post'], url_path='gerar-parcelas')
    def gerar_parcelas(self, request, pk=None):
        """`POST /api/clientes-empreendimentos/<id>/gerar-parcelas/`

        Materializa o carnê como `ContaReceber` — uma linha por entrada, parcela
        e balão, cada uma amarrada à unidade que ela paga. **Não emite boleto**:
        a cobrança no gateway é decisão separada, feita no ERP unitariamente ou
        por lote, e uma venda registrada não deveria disparar cobrança sozinha.

        Idempotente por decisão explícita: se já houve geração, recusa com 409 em
        vez de duplicar o carnê. Regerar exige apagar as parcelas em aberto —
        e nunca apaga as pagas.

        **O escopo é UMA aquisição, e a resposta o diz por extenso.** O endpoint
        é `detail=True`: não há caminho aqui que toque outra venda, outro cliente
        ou outro lote. A resposta devolve cliente, empreendimento e unidade
        porque a tela precisa confirmar *o que* foi criado — quem gera um carnê e
        depois olha o total do ERP (que soma a carteira inteira, de todos os
        compradores) não tem como saber, só pelo número, que os títulos novos são
        os três dele.

        O vencimento sai já no **dia útil bancário** da praça do imóvel: sábado,
        domingo e feriado — nacional, estadual e municipal — empurram a data para
        a frente. Boleto que vence no domingo é parcela que só pode ser paga em
        atraso.
        """
        aquisicao = self.get_object()
        if aquisicao.parcelas_geradas_em:
            return Response(
                {'detail': 'As parcelas desta aquisição já foram geradas.',
                 'geradasEm': aquisicao.parcelas_geradas_em.isoformat()},
                status=409,
            )
        ajuste = vencimento_svc.ajuste_da_aquisicao(aquisicao)
        try:
            plano = plano_pagamento.montar_da_aquisicao(aquisicao, ajustar_vencimento=ajuste)
        except ValueError as erro:
            return Response({'detail': str(erro)}, status=400)
        if not plano.parcelas:
            return Response({'detail': 'O plano não tem parcelas a gerar.'}, status=400)

        descricoes = plano_pagamento.descricoes_do_carne(plano, aquisicao)

        with transaction.atomic():
            titulos = [
                ContaReceber(
                    tenant=aquisicao.tenant,
                    cliente=aquisicao.cliente,
                    empreendimento=aquisicao.empreendimento,
                    cliente_empreendimento=aquisicao,
                    descricao=descricao,
                    valor=parcela.valor,
                    data_emissao=aquisicao.data_compra,
                    data_vencimento=parcela.vencimento,
                )
                for parcela, descricao in zip(plano.parcelas, descricoes)
            ]
            ContaReceber.objects.bulk_create(titulos)
            aquisicao.parcelas_geradas_em = timezone.now()
            aquisicao.save(update_fields=['parcelas_geradas_em'])

        return Response({
            'geradas': len(titulos),
            'total': str(plano.total),
            'geradasEm': aquisicao.parcelas_geradas_em.isoformat(),
            'aquisicaoId': aquisicao.pk,
            'clienteId': aquisicao.cliente_id,
            'cliente': aquisicao.cliente.nome_completo,
            'empreendimento': aquisicao.empreendimento.empreendimento,
            'unidade': aquisicao.unidade.rotulo,
            'ajustadas': plano.parcelas_ajustadas,
            'calendario': _estado_do_calendario(ajuste),
        }, status=201)

    @action(detail=True, methods=['get'], url_path='previa-parcelas')
    def previa_parcelas(self, request, pk=None):
        """`GET /api/clientes-empreendimentos/<id>/previa-parcelas/`

        O carnê que **seria** gerado, sem gerar nada: quantos títulos, de que
        valor, de quem, de qual unidade e entre que datas.

        Existe porque gerar carnê é irreversível pela tela — o botão some e o 409
        barra a segunda tentativa — e ato irreversível não pode ser um clique sem
        prévia. É também o que responde à dúvida legítima de quem clica e depois
        vê dezenas de milhares de títulos no ERP: o número aqui é o desta venda,
        e é ele que a confirmação mostra.
        """
        aquisicao = self.get_object()
        ajuste = vencimento_svc.ajuste_da_aquisicao(aquisicao)
        try:
            plano = plano_pagamento.montar_da_aquisicao(aquisicao, ajustar_vencimento=ajuste)
        except ValueError as erro:
            return Response({'detail': str(erro)}, status=400)
        return Response({
            'jaGeradas': bool(aquisicao.parcelas_geradas_em),
            'aquisicaoId': aquisicao.pk,
            'clienteId': aquisicao.cliente_id,
            'cliente': aquisicao.cliente.nome_completo,
            'empreendimento': aquisicao.empreendimento.empreendimento,
            'unidade': aquisicao.unidade.rotulo,
            'quantidade': plano.quantidade_parcelas,
            'total': str(plano.total),
            'primeiroVencimento': (
                plano.parcelas[0].vencimento.isoformat() if plano.parcelas else None
            ),
            'ultimoVencimento': (
                plano.parcelas[-1].vencimento.isoformat() if plano.parcelas else None
            ),
            'ajustadas': plano.parcelas_ajustadas,
            'calendario': _estado_do_calendario(ajuste),
        })

    @action(detail=True, methods=['get', 'post'], url_path='corrigir')
    def corrigir(self, request, pk=None):
        """`GET|POST /api/clientes-empreendimentos/<id>/corrigir/`

        A correção monetária do carnê. **GET é a prévia** (o que mudaria, título
        a título, sem gravar) e **POST aplica**. Prévia antes de aplicar porque
        reajuste mexe em dinheiro que já foi prometido ao comprador: quem assina
        precisa ver a conta antes, não descobrir pelo extrato.

        Só toca título **em aberto**: reajustar o que já foi pago seria cobrar
        duas vezes pelo mesmo mês. Cada título é trazido até o **próprio
        vencimento** — é o que faz a parcela de 2031 carregar mais índice que a
        de 2027, que é a mecânica do reajuste.
        """
        aquisicao = self.get_object()
        if aquisicao.indice_correcao is None:
            return Response(
                {'detail': 'Este contrato não tem índice de correção definido.'}, status=400,
            )

        titulos = list(
            ContaReceber.objects.filter(
                cliente_empreendimento=aquisicao,
                status__in=[StatusConta.ABERTO, StatusConta.PARCIAL],
            ).order_by('data_vencimento')
        )
        if not titulos:
            return Response({'detail': 'Não há parcelas em aberto para corrigir.'}, status=400)

        previa, alterados = [], []
        for titulo in titulos:
            # O nominal é a base: corrigir sobre o já corrigido comporia o índice
            # duas vezes a cada rodada e o saldo fugiria em progressão.
            base = titulo.valor_nominal if titulo.valor_nominal is not None else titulo.valor
            calculo = correcao.corrigir_da_aquisicao(aquisicao, base, titulo.data_vencimento)
            previa.append({
                'contaReceberId': titulo.pk,
                'descricao': titulo.descricao,
                'vencimento': titulo.data_vencimento.isoformat(),
                'valorAtual': str(titulo.valor),
                **calculo.como_dict(),
            })
            if calculo.valor_corrigido != titulo.valor:
                titulo.valor_nominal = base
                titulo.valor = calculo.valor_corrigido
                titulo.fator_correcao = calculo.fator
                titulo.correcao_ate_competencia = calculo.ate_competencia
                titulo.corrigido_em = timezone.now()
                alterados.append(titulo)

        resposta = {
            'indice': aquisicao.indice_correcao.codigo,
            'periodicidade': aquisicao.periodicidade_correcao,
            'dataBase': aquisicao.data_base_efetiva.isoformat(),
            'parcelas': previa,
            'aplicado': False,
        }
        if request.method == 'GET':
            return Response(resposta)

        with transaction.atomic():
            ContaReceber.objects.bulk_update(
                alterados,
                ['valor', 'valor_nominal', 'fator_correcao',
                 'correcao_ate_competencia', 'corrigido_em'],
                batch_size=500,
            )
        resposta.update(aplicado=True, alteradas=len(alterados))
        return Response(resposta)


def _estado_do_calendario(ajuste) -> dict:
    """O que a tela precisa saber sobre o ajuste de dia útil.

    `feriadosCarregados=False` é o que impede a promessa vazia: a tabela de
    feriados é global e nasce **vazia** (quem a enche é
    `manage.py sincronizar_feriados`). Sem ela o vencimento ainda desvia de
    sábado e domingo, mas não de feriado — e a tela tem de dizer isso, senão o
    usuário lê "ajustado para o próximo dia útil" e acredita em algo que
    aconteceu pela metade.
    """
    from modulocalendar.dias_uteis import base_sincronizada

    return {
        'uf': ajuste.uf,
        'municipio': bool(ajuste.ibge),
        'feriadosCarregados': base_sincronizada(),
        # Lido depois do cálculo: diz se algum feriado da cidade veio da regra
        # (o dataset municipal só publica alguns anos).
        'municipalProjetado': ajuste.municipal_projetado,
    }


def _decimal(valor) -> Decimal:
    if valor in (None, ''):
        return Decimal('0')
    return Decimal(str(valor))


def _data(valor):
    return parse_date(valor) if isinstance(valor, str) and valor else None


class ContratoClienteViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = ContratoCliente.objects.all().order_by('-data_assinatura')
    serializer_class = ContratoClienteSerializer
    filter_backends = [DjangoFilterBackend, BuscaSemAcento, filters.OrderingFilter]
    filterset_class = ContratoClienteFilter
    search_fields = ['numero_contrato', 'objeto_contrato']
    ordering_fields = ['data_assinatura', 'numero_contrato', 'status_contrato']
    ordering = ['-data_assinatura']
    permission_classes = [permissions.IsAuthenticated, RequirePermission]
    required_resource = "cadastro.cliente"


class DocumentoClienteViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = DocumentoCliente.objects.all().order_by('-data_upload')
    serializer_class = DocumentoClienteSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = DocumentoClienteFilter
    ordering_fields = ['data_upload', 'tipo_documento']
    ordering = ['-data_upload']
    permission_classes = [permissions.IsAuthenticated, RequirePermission]
    required_resource = "cadastro.cliente"


class DadoBancarioClienteViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = DadoBancarioCliente.objects.all().order_by('cliente')
    serializer_class = DadoBancarioClienteSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['cliente']
    permission_classes = [permissions.IsAuthenticated, RequirePermission]
    required_resource = "cadastro.cliente_banco"


# ─────────────────────────────────────────────────────────────────────────────
# Carteira — a grade tipo planilha da tela de Clientes
# ─────────────────────────────────────────────────────────────────────────────

def _pode_financeiro(request) -> bool:
    """`erp.cobranca.view` além do acesso ao cadastro — gate de duas pontas.

    Mesmo critério das divergências Asaas: `hasModule` não basta (é entitlement
    do tenant, não permissão do usuário). Sem isto, os números da adimplência
    não saem do backend — a tela nunca recebe o que não pode mostrar.
    """
    return autorizacao.pode(request.user, "erp.cobranca.view")


def _pode_documento(request) -> bool:
    """`cadastro.cliente_doc.view` — a mesma permissão que desmascara o CPF.

    Vale para **ordenar** por documento, não só para lê-lo: a ordem alfabética
    dos CPFs reconstrói, linha a linha, o dígito que a máscara esconde.
    """
    return autorizacao.pode(request.user, "cadastro.cliente_doc.view")


class CarteiraBaseView(TenantScopedAPIViewMixin, APIView):
    permission_classes = [permissions.IsAuthenticated, RequirePermission]
    required_resource = "cadastro.cliente"

    def montar(self, request):
        """Visão pedida, já anotada, filtrada e escopada ao tenant."""
        visao = request.query_params.get('visao', 'clientes')
        if visao not in ('clientes', 'unidades'):
            visao = 'clientes'
        hoje = carteira_svc.hoje_local()
        contas = self.scope_qs(ContaReceber.objects.all())
        aquisicoes = self.scope_qs(ClienteEmpreendimento.objects.all())

        if visao == 'unidades':
            qs = carteira_svc.base_unidades(aquisicoes, contas, hoje)
        else:
            qs = carteira_svc.base_clientes(
                self.scope_qs(Cliente.objects.all()), contas, aquisicoes, hoje
            )
        return visao, carteira_svc.aplicar_filtros(
            qs, visao, request.query_params, hoje, pode_documento=_pode_documento(request),
        ), hoje


class CarteiraView(CarteiraBaseView):
    """`GET /api/clientes/carteira/` — uma página da folha.

    Paginada de propósito: a grade rola infinito e pede a próxima página, em vez
    de baixar a carteira inteira (o comportamento antigo desta tela).
    """

    def get(self, request):
        visao, qs, hoje = self.montar(request)
        pode = _pode_financeiro(request)

        qs = qs.order_by(*carteira_svc.ordenacao(
            visao,
            request.query_params.get('ordenar', ''),
            pode,
            _pode_documento(request),
        ))

        try:
            pagina = max(1, int(request.query_params.get('page', 1)))
            tamanho = min(300, max(10, int(request.query_params.get('page_size', 100))))
        except ValueError:
            pagina, tamanho = 1, 100

        total = qs.count()
        inicio = (pagina - 1) * tamanho
        linhas = list(qs[inicio:inicio + tamanho])
        serializar = (
            carteira_svc.serializar_unidade if visao == 'unidades' else carteira_svc.serializar_cliente
        )
        return Response({
            'visao': visao,
            'count': total,
            'page': pagina,
            'pageSize': tamanho,
            'temMais': inicio + len(linhas) < total,
            'podeFinanceiro': pode,
            # A tela precisa saber para não oferecer uma ordenação que o backend
            # vai ignorar — clicar e nada mudar é pior do que a opção travada.
            'podeDocumento': _pode_documento(request),
            'results': [serializar(linha, request.user, pode, hoje) for linha in linhas],
        })


class CarteiraGruposView(CarteiraBaseView):
    """`GET /api/clientes/carteira/grupos/?por=empreendimento,quadra`

    Os cabeçalhos recolhíveis da grade. Contagem e subtotais vêm de `GROUP BY`
    sobre a carteira inteira — não sobre a página que a tela tem em mãos.

    **`count` é o total de linhas, e não a soma dos grupos.** As duas coisas
    divergem de propósito quando se agrupa pessoas por uma dimensão de muitos:
    quem comprou em dois empreendimentos é *um* cliente e aparece em *dois*
    grupos, então somar os cabeçalhos dá 5.312 numa carteira de 5.000. Cada
    grupo continua contando distinto (`Count(distinct=True)`), o que o mantém
    certo dentro dele; o que não fecha é a soma entre grupos, e é por isso que o
    total vem daqui, calculado sobre o mesmo recorte, em vez de a tela somar os
    cabeçalhos e ver o número de clientes mudar só porque alguém agrupou.
    """

    def get(self, request):
        visao, qs, _ = self.montar(request)
        pode = _pode_financeiro(request)
        niveis = [n for n in request.query_params.get('por', '').split(',') if n]
        grupos = carteira_svc.agrupar(qs, visao, niveis, pode)
        total = qs.order_by().values('pk').distinct().count()
        return Response({
            'visao': visao,
            'niveis': niveis[:3],
            'podeFinanceiro': pode,
            'podeDocumento': _pode_documento(request),
            'count': total,
            # Quantas linhas estão em mais de um grupo. Zero na maioria das
            # combinações; quando não é zero, a tela explica a diferença em vez
            # de deixar o usuário descobrir sozinho que a soma não fecha.
            'somaDosGrupos': sum(g['contagem'] for g in grupos),
            'grupos': grupos,
        })


class IndicesEconomicosView(APIView):
    """`GET /api/indices-economicos/` — os índices publicados na plataforma.

    Sem escopo de tenant porque a série é **dado público**: IPCA é o mesmo número
    para todo mundo. Traz a última competência de cada um para a tela poder dizer
    até quando o índice está alimentado — um seletor que oferece um índice sem
    série faria o usuário escolher uma correção que não corrige.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        indices = IndiceEconomico.objects.filter(ativo=True).annotate(
            ultima_competencia=Max('valores__competencia'),
            competencias=Count('valores'),
        ).order_by('codigo')
        return Response([
            {
                'id': i.pk, 'codigo': i.codigo, 'nome': i.nome, 'fonte': i.fonte,
                'ultimaCompetencia': i.ultima_competencia.isoformat() if i.ultima_competencia else None,
                'competencias': i.competencias,
            }
            for i in indices
        ])


class CarteiraOpcoesView(TenantScopedAPIViewMixin, APIView):
    """`GET /api/clientes/carteira/opcoes/` — o que existe para filtrar e agrupar.

    Alimenta os selects da barra de filtros com os valores que **este tenant**
    tem de fato (não uma lista fixa no frontend, que envelhece).
    """
    permission_classes = [permissions.IsAuthenticated, RequirePermission]
    required_resource = "cadastro.cliente"

    def get(self, request):
        aquisicoes = self.scope_qs(ClienteEmpreendimento.objects.all())
        empreendimentos = (
            aquisicoes.values('empreendimento_id', 'empreendimento__empreendimento')
            .order_by('empreendimento__empreendimento').distinct()
        )
        pode = _pode_financeiro(request)
        return Response({
            'empreendimentos': [
                {'id': e['empreendimento_id'], 'nome': e['empreendimento__empreendimento']}
                for e in empreendimentos
            ],
            'quadras': sorted({q for q in aquisicoes.values_list('unidade__quadra', flat=True) if q}),
            'cidades': sorted({c for c in aquisicoes.values_list('empreendimento__cidade', flat=True) if c}),
            'estados': sorted({u for u in aquisicoes.values_list('empreendimento__estado', flat=True) if u}),
            'anos': sorted({d.year for d in aquisicoes.values_list('data_compra', flat=True) if d}, reverse=True),
            'faixas': carteira_svc.FAIXAS,
            'dimensoes': {
                visao: [
                    {'chave': chave, 'rotulo': dim['rotulo']}
                    for chave, dim in dims.items()
                ]
                for visao, dims in carteira_svc.DIMENSOES.items()
            },
            'podeFinanceiro': pode,
        })
