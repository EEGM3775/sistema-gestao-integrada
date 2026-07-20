"""Reconciliação serviço→serviço com o drone (Fase 10.8, pendência da Fase 3).

Prova que excluir obra/empreendimento enfileira o desvínculo (só quando o drone
está configurado) e que a task pede um JWT de serviço à IAM e chama o endpoint
de desvínculo do drone com ele. As chamadas de rede (IAM/drone) são mockadas.
"""
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from empreendimentos.models import Empreendimento
from nucleo import drone_sync
from nucleo.models import Tenant
from obras.models import Obra

DRONE_URL = "http://java-service:8080"
IAM_URL = "http://iam:8001"


class DroneUnlinkSignalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="drone-t", nome="Drone Tenant")

    def _nova_obra(self):
        return Obra.objects.create(
            nome_obra="Obra Drone", endereco="Rua 1", tenant=self.tenant,
        )

    @override_settings(DRONE_SERVICE_URL=DRONE_URL)
    @patch.object(drone_sync.desvincular_projetos_drone, "delay")
    def test_excluir_obra_enfileira_desvinculo(self, mock_delay):
        obra = self._nova_obra()
        pk = obra.pk
        obra.delete()
        mock_delay.assert_called_once_with(str(self.tenant.id), "obra", pk)

    @override_settings(DRONE_SERVICE_URL=DRONE_URL)
    @patch.object(drone_sync.desvincular_projetos_drone, "delay")
    def test_excluir_empreendimento_enfileira_desvinculo(self, mock_delay):
        emp = Empreendimento.objects.create(
            empreendimento="Emp Drone", razao_social="Emp Drone LTDA",
            cnpj="00.000.000/0001-00", telefone="1199999", endereco="Rua 2",
            tenant=self.tenant,
        )
        pk = emp.pk
        emp.delete()
        mock_delay.assert_called_once_with(str(self.tenant.id), "empreendimento", pk)

    @override_settings(DRONE_SERVICE_URL="")
    @patch.object(drone_sync.desvincular_projetos_drone, "delay")
    def test_sem_drone_configurado_nao_enfileira(self, mock_delay):
        self._nova_obra().delete()
        mock_delay.assert_not_called()


@override_settings(DRONE_SERVICE_URL=DRONE_URL, IAM_INTERNAL_URL=IAM_URL,
                   SERVICE_TOKEN_SECRET="segredo-teste")
class DroneUnlinkTaskTests(TestCase):
    @patch.object(drone_sync.requests, "delete")
    @patch.object(drone_sync.requests, "post")
    def test_task_pede_token_a_iam_e_chama_o_drone(self, mock_post, mock_delete):
        # IAM devolve o JWT de serviço; o drone confirma o desvínculo.
        mock_post.return_value = MagicMock(
            status_code=200, **{"json.return_value": {"access": "tok-servico"},
                                "raise_for_status.return_value": None})
        mock_delete.return_value = MagicMock(
            status_code=200, **{"json.return_value": {"unlinked": 2},
                                "raise_for_status.return_value": None})

        drone_sync.desvincular_projetos_drone.apply(args=["tid-1", "obra", 42]).get()

        # Pediu o token à IAM com o segredo compartilhado e o tenant certo.
        _, post_kwargs = mock_post.call_args
        self.assertEqual(post_kwargs["headers"]["X-Service-Secret"], "segredo-teste")
        self.assertEqual(post_kwargs["json"]["tenant_id"], "tid-1")
        self.assertEqual(post_kwargs["json"]["audience"], "drone")

        # Chamou o desvínculo do drone com o Bearer do token de serviço.
        drone_url = mock_delete.call_args[0][0]
        self.assertEqual(drone_url, f"{DRONE_URL}/api/v1/projects/links/obra/42")
        self.assertEqual(
            mock_delete.call_args[1]["headers"]["Authorization"], "Bearer tok-servico")

    @override_settings(DRONE_SERVICE_URL="")
    @patch.object(drone_sync.requests, "post")
    def test_task_no_op_sem_drone_url(self, mock_post):
        drone_sync.desvincular_projetos_drone.apply(args=["tid-1", "obra", 42]).get()
        mock_post.assert_not_called()
