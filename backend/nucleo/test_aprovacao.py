"""A escada de atesto — a máquina que a PDCA.0 entrega e a PDCA.3 vai usar.

**Por que existe um teste tão grande para uma máquina sem cliente real.** A
escada nasce aqui *antes* da medição, por decisão de faseamento: ela é fundação
de plataforma (o ERP e o SCM vão pedi-la), e fundação sem consumidor é
exatamente o que costuma nascer torta. O contrapeso escolhido foi este arquivo —
ele exerce a máquina no lugar do cliente que ainda não existe, e cada asserção
aqui é uma regra da §11.5 da planta do PDCA.

**O alvo dos cenários é o `LocalObra`**, e não uma `Medicao`, porque a medição só
chega na PDCA.3. Ele é um substituto legítimo: o motor é indiferente ao tipo do
alvo — é essa indiferença que se está provando —, e o `LocalObra` é um
`TenantScopedModel` real, com tenant real e RLS real, o que um modelo de mentira
criado só para o teste não seria.
"""
from datetime import date

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from modulopdca.models import LocalObra, NivelLocal
from obras.models import Obra
from payment.planos import PDCA_TETO_NIVEIS_APROVACAO

from .aprovacao import (
    abrir, aprovacao_concluida, cancelar, decidir, fluxo_para, pedido_de,
    pendentes_para, reordenar_niveis, validar_fluxo,
)
from .models import Atesto, FluxoAprovacao, NivelAprovacao, PedidoAprovacao, Tenant, Usuario

PERM_ENGENHEIRO = "pdca.medicao.atestar_engenheiro"
PERM_GERENTE = "pdca.medicao.atestar_gerente"


class BaseEscada(TestCase):
    """Cenário comum: uma empresa, uma obra, um alvo e uma escada de dois
    degraus — engenheiro depois gerente, que é a escada mais curta que ainda é
    uma escada."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="escada", nome="Construtora Escada")
        cls.obra = Obra.objects.create(
            tenant=cls.tenant, nome_obra="Residencial Aurora", endereco="Rua 1",
        )
        cls.alvo = LocalObra.objects.create(
            tenant=cls.tenant, obra=cls.obra, nivel=NivelLocal.BLOCO,
            codigo="T1", nome="Torre 1",
        )
        cls.ct = ContentType.objects.get_for_model(LocalObra)

        cls.solicitante = Usuario.objects.create(username="apurador", tenant=cls.tenant)
        cls.engenheiro = Usuario.objects.create(username="engenheiro", tenant=cls.tenant)
        cls.gerente = Usuario.objects.create(username="gerente", tenant=cls.tenant)
        cls.engenheiro.iam_permissions = [PERM_ENGENHEIRO]
        cls.gerente.iam_permissions = [PERM_GERENTE]
        cls.solicitante.iam_permissions = []

    def setUp(self):
        self.fluxo = FluxoAprovacao.objects.create(
            tenant=self.tenant, codigo="medicao", nome="Medição de empreiteiro",
            alvo=self.ct, padrao=True,
        )
        NivelAprovacao.objects.create(
            tenant=self.tenant, fluxo=self.fluxo, ordem=1, nome="Engenheiro da obra",
            permissao_exigida=PERM_ENGENHEIRO,
        )
        NivelAprovacao.objects.create(
            tenant=self.tenant, fluxo=self.fluxo, ordem=2, nome="Gerente de contrato",
            permissao_exigida=PERM_GERENTE,
        )


class SubirAEscadaTests(BaseEscada):
    def test_a_escada_sobe_um_degrau_por_vez_e_congela_no_fim(self):
        pedido = abrir(alvo=self.alvo, solicitante=self.solicitante, resumo="Medição 01")
        self.assertEqual(pedido.estado, PedidoAprovacao.Estado.EM_APROVACAO)
        self.assertEqual(pedido.nivel_atual.ordem, 1)

        pedido = decidir(pedido=pedido, usuario=self.engenheiro, aprovar=True)
        self.assertEqual(
            pedido.estado, PedidoAprovacao.Estado.EM_APROVACAO,
            "aprovar o 1º degrau não pode concluir a escada — se concluísse, o "
            "gerente de contrato estaria fora do circuito do dinheiro",
        )
        self.assertEqual(pedido.nivel_atual.ordem, 2)

        pedido = decidir(pedido=pedido, usuario=self.gerente, aprovar=True)
        self.assertEqual(pedido.estado, PedidoAprovacao.Estado.APROVADO)
        self.assertIsNone(pedido.nivel_atual)
        self.assertIsNotNone(pedido.concluido_em)
        self.assertEqual(pedido.atestos.count(), 2)

    def test_o_atesto_guarda_com_que_autoridade_foi_dado(self):
        """Auditoria: o papel do usuário muda com o tempo, o atesto não."""
        pedido = abrir(alvo=self.alvo, solicitante=self.solicitante)
        decidir(pedido=pedido, usuario=self.engenheiro, aprovar=True, observacao="ok")
        atesto = Atesto.objects.get(pedido=pedido, nivel_ordem=1)
        self.assertEqual(atesto.permissao_conferida, PERM_ENGENHEIRO)
        self.assertEqual(atesto.autor_nome, "engenheiro")
        self.assertEqual(atesto.nivel_nome, "Engenheiro da obra")
        self.assertEqual(atesto.observacao, "ok")

    def test_reprovar_encerra_em_qualquer_degrau(self):
        """§11.5: correção é documento novo, nunca reabertura — reabrir apagaria
        o atesto que recusou, que é o registro que mais importa."""
        pedido = abrir(alvo=self.alvo, solicitante=self.solicitante)
        pedido = decidir(
            pedido=pedido, usuario=self.engenheiro, aprovar=False,
            observacao="quantidade não confere com o apontamento",
        )
        self.assertEqual(pedido.estado, PedidoAprovacao.Estado.REPROVADO)
        self.assertIsNone(pedido.nivel_atual)
        with self.assertRaises(ValidationError):
            decidir(pedido=pedido, usuario=self.gerente, aprovar=True)

    def test_o_sinal_avisa_o_dono_do_alvo_uma_vez_e_com_o_alvo_junto(self):
        recebidos = []

        def receptor(sender, pedido, alvo, aprovado, **kwargs):
            recebidos.append((sender, pedido.pk, getattr(alvo, "pk", None), aprovado))

        aprovacao_concluida.connect(receptor, sender=LocalObra)
        try:
            pedido = abrir(alvo=self.alvo, solicitante=self.solicitante)
            decidir(pedido=pedido, usuario=self.engenheiro, aprovar=True)
            self.assertEqual(recebidos, [], "meio da escada não é conclusão")
            decidir(pedido=pedido, usuario=self.gerente, aprovar=True)
        finally:
            aprovacao_concluida.disconnect(receptor, sender=LocalObra)

        self.assertEqual(len(recebidos), 1)
        sender, pedido_id, alvo_id, aprovado = recebidos[0]
        self.assertIs(sender, LocalObra)
        self.assertEqual(alvo_id, self.alvo.pk)
        self.assertTrue(aprovado)

    def test_efeito_colateral_que_falha_nao_desfaz_o_atesto(self):
        """Um erro ao gerar o título no ERP não pode apagar a assinatura do
        fiscal: a decisão de quem tem alçada é verdade por si."""
        def receptor_quebrado(sender, **kwargs):
            raise RuntimeError("o ERP caiu")

        aprovacao_concluida.connect(receptor_quebrado, sender=LocalObra)
        try:
            pedido = abrir(alvo=self.alvo, solicitante=self.solicitante)
            decidir(pedido=pedido, usuario=self.engenheiro, aprovar=True)
            with self.assertLogs("nucleo.aprovacao", level="ERROR"):
                pedido = decidir(pedido=pedido, usuario=self.gerente, aprovar=True)
        finally:
            aprovacao_concluida.disconnect(receptor_quebrado, sender=LocalObra)

        self.assertEqual(pedido.estado, PedidoAprovacao.Estado.APROVADO)
        self.assertEqual(pedido.atestos.count(), 2)


class SegregacaoTests(BaseEscada):
    """Quem executa não aprova — a regra que o ORC.6 provou necessária."""

    def test_quem_solicitou_nao_ateste(self):
        self.solicitante.iam_permissions = [PERM_ENGENHEIRO]
        pedido = abrir(alvo=self.alvo, solicitante=self.solicitante)
        with self.assertRaises(PermissionDenied):
            decidir(pedido=pedido, usuario=self.solicitante, aprovar=True)
        self.solicitante.iam_permissions = []

    def test_autoatesto_e_uma_escolha_declarada_do_cliente(self):
        """A obra pequena, onde o mesmo engenheiro apura e assina, é caso real —
        e continua sendo decisão escrita, não padrão silencioso."""
        self.fluxo.permite_autoatesto = True
        self.fluxo.save(update_fields=["permite_autoatesto"])
        self.solicitante.iam_permissions = [PERM_ENGENHEIRO]
        pedido = abrir(alvo=self.alvo, solicitante=self.solicitante)
        pedido = decidir(pedido=pedido, usuario=self.solicitante, aprovar=True)
        self.assertEqual(pedido.nivel_atual.ordem, 2)
        self.solicitante.iam_permissions = []

    def test_sem_a_permissao_do_degrau_nao_ateste(self):
        pedido = abrir(alvo=self.alvo, solicitante=self.solicitante)
        with self.assertRaises(PermissionDenied):
            decidir(pedido=pedido, usuario=self.gerente, aprovar=True)

    def test_a_permissao_e_a_do_degrau_atual_e_nao_a_do_fluxo(self):
        """O gerente não atesta o 1º degrau; o engenheiro não atesta o 2º. Sem
        isto a escada teria dois nomes e uma alçada só."""
        pedido = abrir(alvo=self.alvo, solicitante=self.solicitante)
        decidir(pedido=pedido, usuario=self.engenheiro, aprovar=True)
        with self.assertRaises(PermissionDenied):
            decidir(pedido=pedido, usuario=self.engenheiro, aprovar=True)

    def test_admin_do_tenant_passa_como_em_toda_a_casa(self):
        admin = Usuario.objects.create(username="admin_escada", tenant=self.tenant)
        admin.is_tenant_admin = True
        pedido = abrir(alvo=self.alvo, solicitante=self.solicitante)
        pedido = decidir(pedido=pedido, usuario=admin, aprovar=True)
        self.assertEqual(pedido.nivel_atual.ordem, 2)


class FilaDeDecisaoTests(BaseEscada):
    def test_a_fila_mostra_so_o_que_a_pessoa_pode_decidir_agora(self):
        """A fila usa o mesmo critério do `decidir` de propósito: uma fila que
        oferece botão para dar 403 é pior que uma fila vazia."""
        pedido = abrir(alvo=self.alvo, solicitante=self.solicitante)
        self.assertEqual(
            list(pendentes_para(self.engenheiro).values_list("pk", flat=True)),
            [pedido.pk],
        )
        self.assertEqual(list(pendentes_para(self.gerente)), [])

        decidir(pedido=pedido, usuario=self.engenheiro, aprovar=True)
        self.assertEqual(list(pendentes_para(self.engenheiro)), [])
        self.assertEqual(
            list(pendentes_para(self.gerente).values_list("pk", flat=True)), [pedido.pk],
        )

    def test_a_fila_esconde_o_proprio_pedido_de_quem_o_abriu(self):
        self.solicitante.iam_permissions = [PERM_ENGENHEIRO]
        abrir(alvo=self.alvo, solicitante=self.solicitante)
        self.assertEqual(list(pendentes_para(self.solicitante)), [])
        self.solicitante.iam_permissions = []

    def test_a_fila_nao_atravessa_a_empresa(self):
        outra = Tenant.objects.create(slug="escada-b", nome="Construtora B")
        forasteiro = Usuario.objects.create(username="forasteiro", tenant=outra)
        forasteiro.iam_permissions = [PERM_ENGENHEIRO]
        abrir(alvo=self.alvo, solicitante=self.solicitante)
        self.assertEqual(list(pendentes_para(forasteiro)), [])


class MoldeDaEscadaTests(BaseEscada):
    def test_fluxo_sem_nivel_nao_serve(self):
        vazio = FluxoAprovacao.objects.create(
            tenant=self.tenant, codigo="vazio", nome="Sem degrau", alvo=self.ct,
        )
        with self.assertRaises(ValidationError):
            validar_fluxo(vazio)

    def test_buraco_na_numeracao_e_recusado(self):
        """1, 2, 5 faria o pedido parar num degrau que não existe — e o defeito
        só apareceria quando alguém submetesse uma medição de verdade."""
        NivelAprovacao.objects.create(
            tenant=self.tenant, fluxo=self.fluxo, ordem=5, nome="Diretor",
            permissao_exigida="pdca.medicao.atestar_diretor",
        )
        with self.assertRaises(ValidationError):
            validar_fluxo(self.fluxo)

    def test_o_teto_de_degraus_vem_do_payment(self):
        for ordem in range(3, PDCA_TETO_NIVEIS_APROVACAO + 2):
            NivelAprovacao.objects.create(
                tenant=self.tenant, fluxo=self.fluxo, ordem=ordem,
                nome=f"Degrau {ordem}", permissao_exigida=f"pdca.medicao.n{ordem}",
            )
        with self.assertRaises(ValidationError):
            validar_fluxo(self.fluxo)

    def test_um_padrao_por_alvo(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                FluxoAprovacao.objects.create(
                    tenant=self.tenant, codigo="outro", nome="Outra escada",
                    alvo=self.ct, padrao=True,
                )

    def test_fluxo_de_outro_tipo_de_alvo_e_recusado(self):
        """Um fluxo de medição não aprova um cronograma — e a checagem é do
        motor, não da tela."""
        outro_ct = ContentType.objects.get_for_model(Obra)
        fluxo = FluxoAprovacao.objects.create(
            tenant=self.tenant, codigo="obra", nome="Escada de obra", alvo=outro_ct,
        )
        NivelAprovacao.objects.create(
            tenant=self.tenant, fluxo=fluxo, ordem=1, nome="Único",
            permissao_exigida=PERM_ENGENHEIRO,
        )
        with self.assertRaises(ValidationError):
            abrir(alvo=self.alvo, solicitante=self.solicitante, fluxo=fluxo)


class UmPedidoPorAlvoTests(BaseEscada):
    def test_dois_pedidos_abertos_sobre_o_mesmo_objeto_sao_barrados_no_banco(self):
        """Dois seriam dois atestos válidos sobre a mesma medição, cada um numa
        metade da escada — e o alvo congelando por qualquer uma delas."""
        abrir(alvo=self.alvo, solicitante=self.solicitante)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                abrir(alvo=self.alvo, solicitante=self.solicitante)

    def test_depois_de_reprovado_o_objeto_pode_subir_de_novo(self):
        """A retificadora é documento novo, mas nada impede que o MESMO objeto
        volte à escada depois de encerrada a anterior — senão uma reprovação
        deixaria o documento preso para sempre."""
        pedido = abrir(alvo=self.alvo, solicitante=self.solicitante)
        decidir(pedido=pedido, usuario=self.engenheiro, aprovar=False)
        segundo = abrir(alvo=self.alvo, solicitante=self.solicitante)
        self.assertEqual(segundo.estado, PedidoAprovacao.Estado.EM_APROVACAO)
        self.assertNotEqual(segundo.pk, pedido.pk)

    def test_pedido_de_e_fluxo_para_acham_o_que_esta_valendo(self):
        self.assertIsNone(pedido_de(self.alvo))
        pedido = abrir(alvo=self.alvo, solicitante=self.solicitante)
        self.assertEqual(pedido_de(self.alvo).pk, pedido.pk)
        self.assertEqual(
            fluxo_para(self.alvo, tenant_id=self.tenant.id).pk, self.fluxo.pk
        )


class CancelamentoTests(BaseEscada):
    def test_so_o_solicitante_ou_o_admin_cancelam(self):
        """Se um aprovador pudesse cancelar, ele teria um jeito de fazer o pedido
        sumir sem registrar a recusa — e a recusa é o que a auditoria procura."""
        pedido = abrir(alvo=self.alvo, solicitante=self.solicitante)
        with self.assertRaises(PermissionDenied):
            cancelar(pedido=pedido, usuario=self.engenheiro)
        pedido = cancelar(
            pedido=pedido, usuario=self.solicitante, motivo="documento retirado",
        )
        self.assertEqual(pedido.estado, PedidoAprovacao.Estado.CANCELADO)
        self.assertIn("documento retirado", pedido.resumo)


class RecusaDeAutoatestoDizASaidaTests(BaseEscada):
    """**A recusa mais provável da máquina precisa dizer o caminho.**

    *(Achado do dono, 15/09/2026, usando a tela: ele submeteu a medição como
    administrador do tenant e levou "Quem solicitou não pode atestar o próprio
    pedido" — com o documento parado e nenhuma saída à vista.)*

    A regra está certa e fica. O defeito era a mensagem: a válvula que a planta
    prevê (`permite_autoatesto`, *"escolha escrita do cliente para a obra
    pequena"*) existia desde a PDCA.0 e **ninguém tinha como descobri-la**.
    """

    def test_a_recusa_nomeia_as_saidas_e_o_interruptor(self):
        self.solicitante.iam_permissions = [PERM_ENGENHEIRO]
        pedido = abrir(alvo=self.alvo, solicitante=self.solicitante)
        with self.assertRaises(PermissionDenied) as erro:
            decidir(pedido=pedido, usuario=self.solicitante, aprovar=True)
        mensagem = str(erro.exception)
        # A permissão do degrau, para quem lê saber a quem pedir.
        self.assertIn(PERM_ENGENHEIRO, mensagem)
        # O nome do fluxo, para o administrador achar qual mexer.
        self.assertIn(self.fluxo.nome, mensagem)
        # E o endereço do interruptor — sem isto, a válvula segue invisível.
        self.assertIn("autoatesto", mensagem.lower())
        self.assertIn("Aprovações", mensagem)

    def test_com_autoatesto_ligado_o_mesmo_gesto_passa(self):
        """O interruptor não é decorativo: ligá-lo resolve de fato, e o atesto
        continua guardando autor e data — o que muda é quem pode assinar, não
        se o registro existe."""
        self.fluxo.permite_autoatesto = True
        self.fluxo.save(update_fields=["permite_autoatesto"])
        self.solicitante.iam_permissions = [PERM_ENGENHEIRO]

        pedido = abrir(alvo=self.alvo, solicitante=self.solicitante)
        pedido = decidir(pedido=pedido, usuario=self.solicitante, aprovar=True)
        atesto = Atesto.objects.get(pedido=pedido, nivel_ordem=1)
        self.assertEqual(atesto.autor_id, self.solicitante.pk)
        self.assertEqual(atesto.decisao, Atesto.Decisao.APROVADO)


class ReordenarDegrausTests(BaseEscada):
    """Reordenar tem de ser **atômico**, e é por isso que mora no servidor.

    A alternativa — a tela trocando `ordem` de dois degraus com dois `PATCH` —
    esbarra na `UniqueConstraint(fluxo, ordem)`, precisa de um valor temporário,
    e uma falha no meio deixa a escada com numeração quebrada: `validar_fluxo`
    passa a recusá-la e o documento que dependia dela para de andar **sem que
    ninguém o tenha tocado**.
    """

    def test_inverter_dois_degraus_mantem_a_escada_valida(self):
        niveis = list(self.fluxo.niveis.order_by("ordem"))
        reordenar_niveis(self.fluxo, [niveis[1].pk, niveis[0].pk])

        agora = list(self.fluxo.niveis.order_by("ordem"))
        self.assertEqual([n.ordem for n in agora], [1, 2])
        self.assertEqual(agora[0].pk, niveis[1].pk)
        validar_fluxo(self.fluxo)  # não levanta

    def test_a_ordem_nova_governa_quem_assina_primeiro(self):
        """A prova de que reordenar **significa** alguma coisa: invertidos os
        degraus, é o gerente que abre a escada, e o engenheiro que fecha."""
        niveis = list(self.fluxo.niveis.order_by("ordem"))
        reordenar_niveis(self.fluxo, [niveis[1].pk, niveis[0].pk])

        pedido = abrir(alvo=self.alvo, solicitante=self.solicitante)
        with self.assertRaises(PermissionDenied):
            decidir(pedido=pedido, usuario=self.engenheiro, aprovar=True)
        pedido = decidir(pedido=pedido, usuario=self.gerente, aprovar=True)
        self.assertEqual(pedido.estado, PedidoAprovacao.Estado.EM_APROVACAO)
        pedido = decidir(pedido=pedido, usuario=self.engenheiro, aprovar=True)
        self.assertEqual(pedido.estado, PedidoAprovacao.Estado.APROVADO)

    def test_lista_incompleta_e_recusada_em_vez_de_apagar_degrau(self):
        """Reordenar não cria nem apaga degrau. Sem esta trava, mandar um id só
        renumeraria aquele para 1 e deixaria os outros onde estavam — escada
        com dois degraus 1, ou com buraco."""
        niveis = list(self.fluxo.niveis.order_by("ordem"))
        with self.assertRaises(ValidationError):
            reordenar_niveis(self.fluxo, [niveis[0].pk])
        self.assertEqual(
            [n.ordem for n in self.fluxo.niveis.order_by("ordem")], [1, 2],
        )


class AlvosDescobertosTests(TestCase):
    """`alvos/` descobre **por construção**, e não por lista escrita à mão.

    Um modelo entra ali no instante em que declara a `GenericRelation` para
    `PedidoAprovacao` — que é exatamente o gesto com que um módulo se candidata a
    ser aprovado. Manter um catálogo em paralelo criaria a segunda verdade que
    envelhece na fatia seguinte.
    """

    def test_a_medicao_e_o_cronograma_aparecem_entre_os_alvos(self):
        from django.apps import apps
        from django.contrib.contenttypes.fields import GenericRelation

        encontrados = set()
        for modelo in apps.get_models():
            if any(
                isinstance(campo, GenericRelation)
                and campo.related_model is PedidoAprovacao
                for campo in modelo._meta.private_fields
            ):
                ct = ContentType.objects.get_for_model(modelo)
                encontrados.add(f"{ct.app_label}.{ct.model}")

        self.assertIn("modulopdca.medicao", encontrados)
        self.assertIn("modulopdca.liberacaoretencao", encontrados)
