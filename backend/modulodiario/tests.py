"""Diário de obra — data da contribuição no fuso LOCAL.

Bug encontrado em 19/07/2026 ao validar outra entrega: `registrar_contribuicao`
usava `timezone.now().date()`, que é a data em **UTC**. Como o projeto roda em
America/Sao_Paulo (UTC-3), toda contribuição feita entre **21h e meia-noite** era
arquivada no diário do **dia seguinte** — e esse é exatamente o horário em que a
equipe de campo fecha o dia pelo WhatsApp. O diário de obra é registro
contratual; datar errado não é detalhe cosmético.

O sintoma era invisível de dia: a suíte passava das 00h às 20h59 e falhava depois,
o que faz este teste valer mais que o normal — ele fixa o instante em vez de
depender de quando alguém roda os testes.
"""
from datetime import date, datetime, timezone as dt_timezone
from unittest.mock import patch

from django.test import TestCase

from nucleo.models import Tenant
from obras.models import Obra
from rh.models import Funcionario


class DataDaContribuicaoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="diario-tz", nome="Diário TZ")
        cls.obra = Obra.objects.create(tenant=cls.tenant, nome_obra="Obra TZ")
        cls.func = Funcionario.objects.create(
            tenant=cls.tenant, nome_completo="João da Silva", cpf="52998224725",
            data_nascimento=date(1990, 1, 1), genero="masculino",
            endereco_completo="Rua 1, 100", data_admissao=date(2020, 1, 1),
            salario_base=2000,
        )

    @patch("modulodiario.tasks.disparar_analise_ia.delay")
    def test_contribuicao_as_21h30_fica_no_dia_local_e_nao_no_dia_seguinte(self, _ia):
        """22h30 BRT do dia 18 = 01h30 UTC do dia 19. Tem de virar diário do 18."""
        from modulodiario.services import registrar_contribuicao

        instante_utc = datetime(2026, 7, 19, 1, 30, tzinfo=dt_timezone.utc)
        with patch("django.utils.timezone.now", return_value=instante_utc):
            diario = registrar_contribuicao(
                obra=self.obra, funcionario=self.func, texto="Concretagem encerrada",
                origem="whatsapp", tenant_id=self.tenant.id,
            )

        self.assertEqual(
            diario.data, date(2026, 7, 18),
            "contribuição da noite foi parar no diário do dia seguinte (bug de fuso)",
        )

    @patch("modulodiario.tasks.disparar_analise_ia.delay")
    def test_duas_contribuicoes_na_mesma_noite_reusam_o_mesmo_diario(self, _ia):
        """Consequência prática do bug: 20h55 e 21h05 caíam em diários diferentes."""
        from modulodiario.models import DiarioObra
        from modulodiario.services import registrar_contribuicao

        antes = datetime(2026, 7, 18, 23, 55, tzinfo=dt_timezone.utc)   # 20h55 BRT
        depois = datetime(2026, 7, 19, 0, 5, tzinfo=dt_timezone.utc)    # 21h05 BRT
        for instante in (antes, depois):
            with patch("django.utils.timezone.now", return_value=instante):
                registrar_contribuicao(
                    obra=self.obra, funcionario=self.func, texto="x",
                    origem="whatsapp", tenant_id=self.tenant.id,
                )

        self.assertEqual(
            DiarioObra.objects.filter(obra=self.obra, data=date(2026, 7, 18)).count(), 1
        )
