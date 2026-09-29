"""Catálogo de planos e o teto de requisições derivado dele (D23 + base do D24).

O que estes testes protegem, em ordem de importância:

1. **A empresa grande não é estrangulada** — foi o defeito que originou a
   revisão: com teto fixo, 1000 funcionários receberiam 60 requisições/hora cada.
2. **O default é o plano MENOR, nunca "sem limite"** — tenant provisionado com
   erro tem de doer pouco, não abrir tudo.
3. **Comprar seat aumenta o teto** — é o que faz o limite acompanhar a receita.
"""
from django.test import TestCase

from identity.models import AssinaturaTenant, Modulo, Tenant
from identity.tokens import claims_de_acesso
from payment.planos import (
    PLANO_PADRAO,
    PLANOS,
    RATE_BASE_HORA,
    RATE_POR_SEAT_HORA,
    RATE_TETO_INFRA_HORA,
)
from payment.regras import (
    plano_valido,
    proximo_plano,
    quotas_do_plano,
    teto_requisicoes_hora,
)


class TetoDerivadoDoPlanoTests(TestCase):
    def test_teto_cresce_com_o_tamanho_do_plano(self):
        """O ponto do achado: um número só não serve para 1 e para 40 pessoas."""
        tetos = [teto_requisicoes_hora(slug) for slug in
                 ("free", "essencial", "profissional", "empresarial")]
        self.assertEqual(tetos, sorted(tetos), f"teto não é monotônico: {tetos}")
        self.assertLess(tetos[0], tetos[-1])

    def test_empresa_grande_nao_e_estrangulada(self):
        """Regressão do defeito original. Com o teto fixo de 60.000/h, uma
        empresa de 40 seats dava 1.500/h por pessoa; de 1000, dava 60/h — menos
        que o polling do sino de notificações consome sem ninguém trabalhar."""
        teto = teto_requisicoes_hora("empresarial")
        seats = PLANOS["empresarial"]["seats"]
        por_pessoa = teto / seats
        self.assertGreater(por_pessoa, RATE_POR_SEAT_HORA * 0.9,
                           "o teto não acompanhou o tamanho do plano")

    def test_seats_contratados_a_mais_aumentam_o_teto(self):
        """Add-on de usuário extra (R$29/mês) — o limite acompanha a receita."""
        base = teto_requisicoes_hora("essencial")
        seats_do_plano = PLANOS["essencial"]["seats"]
        com_addon = teto_requisicoes_hora("essencial", {"seats": seats_do_plano + 2})
        self.assertEqual(com_addon - base, 2 * RATE_POR_SEAT_HORA)

    def test_contrato_explicito_vence_o_plano(self):
        """"Sob Medida": o provisionamento grava o negociado em `limites`."""
        self.assertEqual(
            teto_requisicoes_hora("essencial", {"requisicoes_hora": 25_000}), 25_000
        )

    def test_nada_passa_do_teto_de_infraestrutura(self):
        """Nem contrato, nem plano ilimitado: acima disso é projeto de
        capacidade, não cláusula. Todo grande mantém um limite absoluto por cima
        da fórmula (GitHub para em 12.500/h) para ela não virar cheque em branco."""
        self.assertEqual(
            teto_requisicoes_hora("essencial", {"requisicoes_hora": 10_000_000}),
            RATE_TETO_INFRA_HORA,
        )
        self.assertLessEqual(teto_requisicoes_hora("sob_medida"), RATE_TETO_INFRA_HORA)

    def test_sob_medida_sem_contrato_nao_vira_ilimitado(self):
        """`seats: None` no catálogo significa "negociado", não "infinito" — se
        virasse infinito, um tenant sozinho consumiria a capacidade dos outros."""
        teto = teto_requisicoes_hora("sob_medida")
        self.assertIsInstance(teto, int)
        self.assertGreater(teto, 0)


class PlanoPadraoTests(TestCase):
    def test_plano_desconhecido_cai_no_padrao_e_nao_levanta(self):
        """Plano escrito errado no banco não pode derrubar a emissão de token."""
        self.assertEqual(plano_valido("plano_que_nao_existe"), PLANO_PADRAO)
        self.assertEqual(plano_valido(None), PLANO_PADRAO)
        self.assertEqual(plano_valido(""), PLANO_PADRAO)

    def test_o_padrao_e_o_menor_plano(self):
        """Default seguro: tenant provisionado com erro fica no plano MENOR, e
        não sem limite — mesmo princípio fail-closed do RequirePermission."""
        teto_padrao = teto_requisicoes_hora(None)
        outros = [teto_requisicoes_hora(s) for s in PLANOS if s != PLANO_PADRAO]
        self.assertTrue(all(teto_padrao <= t for t in outros),
                        "o plano padrão não é o mais restritivo")

    def test_quotas_do_plano_sao_declaradas(self):
        """As demais quotas estão inertes até o D24, mas têm de existir para
        serem lidas e exibidas (é o que permite testar o modelo sem checkout)."""
        quotas = quotas_do_plano("profissional")
        for chave in ("seats", "obras", "clientes", "analises_ia_mes"):
            self.assertIn(chave, quotas)

    def test_regua_de_upgrade(self):
        self.assertEqual(proximo_plano("free"), "essencial")
        self.assertIsNone(proximo_plano("sob_medida"))


class ClaimDoTetoTests(TestCase):
    """O teto sai da IAM no token porque só ela sabe quantos seats a empresa
    contratou — o `Usuario` do backend é espelho JIT (só quem já logou)."""

    def setUp(self):
        from django.contrib.auth import get_user_model

        self.tenant = Tenant.objects.create(nome="Construtora X", slug="construtora-x")
        self.user = get_user_model().objects.create_user(
            username="d23_plano", email="d23@exemplo.com", password="x", tenant=self.tenant
        )

    def test_token_carrega_o_teto_e_o_plano(self):
        claims = claims_de_acesso(self.user)
        self.assertEqual(claims["plano"], PLANO_PADRAO)
        self.assertEqual(claims["rate_hora"], teto_requisicoes_hora(PLANO_PADRAO))

    def test_upgrade_de_plano_muda_o_teto_do_token(self):
        antes = claims_de_acesso(self.user)["rate_hora"]
        self.tenant.plano = "empresarial"
        self.tenant.save(update_fields=["plano"])
        depois = claims_de_acesso(self.user)["rate_hora"]
        self.assertGreater(depois, antes)

    def test_limites_da_assinatura_vencem_o_plano(self):
        modulo = Modulo.objects.create(codigo="erp_financeiro", nome="ERP")
        AssinaturaTenant.objects.create(
            tenant=self.tenant, modulo=modulo, limites={"requisicoes_hora": 33_000}
        )
        self.assertEqual(claims_de_acesso(self.user)["rate_hora"], 33_000)

    def test_usuario_sem_tenant_nao_recebe_teto(self):
        """Dono da plataforma: sem empresa, o eixo não se aplica (o backend cai
        no default do settings em vez de quebrar)."""
        from django.contrib.auth import get_user_model

        sozinho = get_user_model().objects.create_user(
            username="d23_semtenant", email="sem@exemplo.com", password="x"
        )
        self.assertNotIn("rate_hora", claims_de_acesso(sozinho))


class FusaoDeLimitesTests(TestCase):
    """`limites` é por módulo, mas seats/teto são do tenant inteiro."""

    def test_maior_valor_entre_assinaturas_ativas(self):
        tenant = Tenant.objects.create(nome="Y", slug="y")
        erp = Modulo.objects.create(codigo="erp_financeiro", nome="ERP")
        crm = Modulo.objects.create(codigo="crm", nome="CRM")
        AssinaturaTenant.objects.create(tenant=tenant, modulo=erp, limites={"seats": 5})
        AssinaturaTenant.objects.create(tenant=tenant, modulo=crm, limites={"seats": 12})
        self.assertEqual(tenant.limites_contratados()["seats"], 12,
                         "cliente recebeu menos que a assinatura mais generosa")
