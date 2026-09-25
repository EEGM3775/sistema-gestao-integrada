"""O supervisor alcança todo módulo — e **não atravessa a fronteira de tenant**.

*(Decisões do dono, 22/08/2026.)* O `is_superuser` da IAM é o supervisor e o teste
supremo do sistema. Ele **não tem restrição a nenhum módulo** (a régua dele, em
`iam/identity/models.py`, ignora o `AssinaturaTenant`) e opera o que é da
plataforma. O que ele não é — e é o que este arquivo garante — é **chave mestra
sobre as empresas**.

O arquivo já se chamou `test_supervisor_nao_le_empresa.py`, e o nome era falso:
ele **lê** a empresa onde está, com módulo e permissão, como qualquer usuário. O
que ele não faz é atravessar para **outra**.

**A fronteira é real, mas vale por OMISSÃO** — é o motivo deste arquivo. No
backend, `Usuario.is_superuser` é chave mestra de verdade:

  - `nucleo/tenancy.py` — arma **bypass de RLS** e não filtra queryset por tenant;
  - `nucleo/permissions.py` — passa por cima do `RequirePermission`;
  - `nucleo/field_masking.py` — lê PII **sem máscara** (CPF, salário, conta);
  - `nucleo/quotas.py` — ignora quota de objeto.

E o flag da IAM **não é copiado** para o espelho local: `_sync_user`
(`nucleo/authentication.py`) sincroniza e-mail, tenant e `is_tenant_admin`, e só.
A separação existe porque alguém **não escreveu** uma linha, e uma refatoração
bem-intencionada — "o supervisor é superuser, vamos espelhar isso" — a desfaria
sem quebrar nada visível. O sintoma seria vazamento entre empresas com aparência
de recurso administrativo: a classe de defeito mais cara desta plataforma
(Fase 8, o calcanhar do isolamento).

**O QUE ESTE ARQUIVO NÃO PROVA, e a lição custou um orçamento aprovado.**

Ele testa a **camada do espelho**: dado um token, o usuário local não vira chave
mestra. Para isso monta o cenário à mão — `iam_modules` e `iam_permissions`
escritos no objeto — e aí está o limite: escrever a claim à mão **presume** o que
o emissor manda.

Na primeira versão desta suíte ela passou inteira enquanto a IAM mandava, para o
mesmo usuário, todos os módulos e todo o catálogo do tenant, porque
`identity/models.py` tratava `is_superuser` igual a `is_tenant_admin`. O
supervisor aprovou um orçamento de uma empresa com o teste verde.

A régua que ficou: *para garantir o que um usuário **pode**, teste o emissor do
token (`testes/iam/identity/tests.py`); para garantir o que o backend **faz com** o que
recebeu, teste aqui.* As duas metades são necessárias.
"""
from datetime import date

from django.test import TestCase
from rest_framework.test import APITestCase

from nucleo.authentication import IamJWTAuthentication
from nucleo.models import Tenant, Usuario


class ClaimDeSupervisorNaoViraChaveMestraTests(TestCase):
    """O degrau exato onde a separação mora: a sincronização JIT."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="sup-a", nome="Construtora A")

    def test_sync_nao_promove_o_espelho_a_superuser(self):
        """Token de supervisor entra; espelho local continua usuário comum.

        Esta é **a** asserção do arquivo. Se um dia `_sync_user` passar a copiar
        `is_platform_admin` para `is_superuser`, o supervisor ganha, de uma vez,
        leitura de todas as empresas, PII sem máscara e escrita sem quota.
        """
        usuario = Usuario.objects.create(username="supervisor", tenant=self.tenant)
        token = {
            "email": "supervisor@plataforma.com",
            "is_tenant_admin": False,
            "is_platform_admin": True,
            "tenant_id": str(self.tenant.id),
            "tenant_slug": self.tenant.slug,
        }

        IamJWTAuthentication()._sync_user(usuario, token, self.tenant)
        usuario.refresh_from_db()

        self.assertFalse(
            usuario.is_superuser,
            "o supervisor virou superuser do backend — isso lhe dá bypass de RLS, "
            "de permissão, de máscara de PII e de quota sobre TODAS as empresas",
        )
        self.assertFalse(
            usuario.is_staff,
            "`is_staff` abre o /admin do Django, que é a porta de editar dado de "
            "empresa à mão — o supervisor supervisiona pelo produto",
        )
        self.assertFalse(usuario.is_data_admin)

    def test_o_tenant_do_supervisor_e_endereco_e_nao_privilegio(self):
        """Ele continua com um tenant (a IAM exige um), e isso não o promove."""
        usuario = Usuario.objects.create(username="supervisor2", tenant=self.tenant)
        IamJWTAuthentication()._sync_user(
            usuario, {"is_platform_admin": True, "is_tenant_admin": False}, self.tenant
        )
        usuario.refresh_from_db()
        self.assertEqual(usuario.tenant_id, self.tenant.id)
        self.assertFalse(usuario.is_superuser)


class SupervisorNaoAlcancaDadoDeEmpresaTests(APITestCase):
    """A mesma fronteira vista de fora, pela API — que é como o dano aconteceria.

    O supervisor **tem** os módulos (a régua dele alcança o catálogo inteiro), e
    é justamente por isso que este teste importa: ele abre a tela de clientes de
    verdade. O que se prova aqui é que, mesmo com módulo e permissão, ele vê a
    empresa **onde está** e nenhuma outra.

    O cenário escreve `iam_modules`/`iam_permissions` à mão para não depender do
    emissor — quem garante o que o emissor manda é a suíte da IAM (nota no topo).
    """

    @classmethod
    def setUpTestData(cls):
        cls.empresa_a = Tenant.objects.create(slug="sup-emp-a", nome="Construtora A")
        cls.empresa_b = Tenant.objects.create(slug="sup-emp-b", nome="Construtora B")
        cls.supervisor = Usuario.objects.create(
            username="supervisor_api", tenant=cls.empresa_a
        )

    def _autenticar(self, modules=(), permissions=()):
        self.supervisor.iam_modules = list(modules)
        self.supervisor.iam_permissions = list(permissions)
        self.supervisor.is_platform_admin = True
        self.client.force_authenticate(user=self.supervisor)

    def test_sem_modulo_a_camada_1_ja_barra(self):
        """A camada 1 vale para ele como para qualquer um: sem o módulo no token,
        403. (No seed ele tem todos — aqui o cenário é montado à mão.)"""
        self._autenticar()
        self.assertEqual(self.client.get("/api/clientes/").status_code, 403)

    def test_com_modulo_e_permissao_ele_ve_a_empresa_dele_e_nada_alem(self):
        """O escopo de tenant continua valendo — `is_platform_admin` não o fura.

        Cria um cliente em cada empresa e confere que a listagem devolve só o da
        empresa dele. Se o espelho fosse superuser, viria a das duas.
        """
        from clientes.models import Cliente

        Cliente.objects.create(
            tenant=self.empresa_a, nome_completo="Cliente da empresa A",
            cpf_cnpj="52998224725", email="a@empresa-a.com",
            data_nascimento=date(1985, 3, 12),
        )
        Cliente.objects.create(
            tenant=self.empresa_b, nome_completo="Cliente da empresa B",
            cpf_cnpj="15350946056", email="b@empresa-b.com",
            data_nascimento=date(1979, 8, 30),
        )
        self._autenticar(
            modules=["erp_financeiro"],
            permissions=["cadastro.cliente.view", "cadastro.cliente.edit"],
        )

        resposta = self.client.get("/api/clientes/")
        self.assertEqual(resposta.status_code, 200, resposta.data)
        dados = resposta.data
        nomes = {
            linha["nome_completo"]
            for linha in (dados.get("results", dados) if isinstance(dados, dict) else dados)
        }
        self.assertIn("Cliente da empresa A", nomes)
        self.assertNotIn(
            "Cliente da empresa B", nomes,
            "o supervisor enxergou o cliente de outra empresa — a claim de "
            "plataforma furou o escopo de tenant",
        )

    def test_a_claim_abre_plataforma_por_si_so(self):
        """A claim basta para a operação de PLATAFORMA — sem módulo, sem papel.

        É o contraste que resume o desenho: `is_platform_admin` sozinho abre a
        carga da base-mãe (dado público, de todos); para a carteira de clientes
        (dado de **uma** empresa) ele passa pelas mesmas duas camadas que todo
        mundo, e é a fronteira de tenant que decide qual empresa ele vê."""
        self._autenticar()
        self.assertEqual(
            self.client.get("/api/orcamento/cargas/estado/").status_code, 200,
            "a claim precisa abrir a operação de plataforma",
        )
        self.assertEqual(
            self.client.get("/api/clientes/").status_code, 403,
            "e precisa continuar fechada para dado de empresa",
        )
