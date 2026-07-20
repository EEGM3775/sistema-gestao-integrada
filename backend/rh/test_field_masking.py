"""Fase 9.C — mascaramento de PII por permissão (FieldMaskingSerializerMixin).

Valida que a ficha do funcionário "para de chover 403": quem tem
``rh.funcionario.view`` vê o cadastro, mas sem ``rh.cpf.view`` o CPF vem
mascarado (``••••`` + 2 últimos dígitos) e sem ``rh.folha.view`` o salário vem
``null``. Admin de tenant vê tudo. Tentar gravar campo sensível sem a
permissão ``.edit`` correspondente é rejeitado com 400.
"""
from decimal import Decimal

from rest_framework.test import APITestCase

from nucleo.models import Tenant, Usuario
from rh.models import Funcionario, Cargo
from rh.serializers import FuncionarioSerializer


class FieldMaskingRHTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="mask-a", nome="Empresa Máscara")
        cls.user = Usuario.objects.create(username="rh_user", tenant=cls.tenant)
        cls.admin = Usuario.objects.create(
            username="adm", tenant=cls.tenant, is_tenant_admin=True
        )
        cls.cargo = Cargo.objects.create(
            tenant=cls.tenant, nome_cargo="Pedreiro", departamento="Obra"
        )
        cls.func = Funcionario.objects.create(
            tenant=cls.tenant,
            cargo=cls.cargo,
            nome_completo="João da Silva",
            cpf="12345678909",
            data_nascimento="1990-01-01",
            genero="masculino",
            endereco_completo="Rua das Flores, 123",
            data_admissao="2020-01-01",
            salario_base=Decimal("3500.00"),
            status_contrato="ativo",
        )

    def _ctx(self, user):
        return {"request": type("R", (), {"user": user})()}

    def _ser(self, user):
        return FuncionarioSerializer(self.func, context=self._ctx(user))

    # ---- Leitura: máscara parcial/redigido por permissão -------------------
    def test_sem_permissao_cpf_vem_mascarado_e_salario_null(self):
        self.user.iam_permissions = ["rh.funcionario.view"]
        data = self._ser(self.user).data
        self.assertTrue(data["cpf"].startswith("••••"))
        self.assertTrue(data["cpf"].endswith("09"))
        self.assertIsNone(data["salario_base"])

    def test_com_permissao_cpf_e_salario_visiveis(self):
        self.user.iam_permissions = [
            "rh.funcionario.view", "rh.cpf.view", "rh.folha.view",
        ]
        data = self._ser(self.user).data
        self.assertEqual(data["cpf"], "12345678909")
        self.assertEqual(str(data["salario_base"]), "3500.00")

    def test_admin_de_tenant_ve_tudo(self):
        self.admin.iam_permissions = []  # nem precisa das permissões
        data = self._ser(self.admin).data
        self.assertEqual(data["cpf"], "12345678909")
        self.assertEqual(str(data["salario_base"]), "3500.00")

    def test_soh_cpf_sem_salario(self):
        self.user.iam_permissions = ["rh.funcionario.view", "rh.cpf.view"]
        data = self._ser(self.user).data
        self.assertEqual(data["cpf"], "12345678909")
        self.assertIsNone(data["salario_base"])

    def test_sem_contexto_mascara_tudo(self):
        # Fail-closed: serialização sem request/user não vaza PII.
        data = FuncionarioSerializer(self.func).data
        self.assertTrue(data["cpf"].startswith("••••"))
        self.assertIsNone(data["salario_base"])

    # ---- Escrita: só campos com .edit concedível são protegidos ------------
    def test_cpf_nao_e_travado_no_serializer(self):
        # CPF é sensível na LEITURA, mas a escrita é do cadastro (endpoint) — o
        # mixin não a trava, senão ninguém criaria funcionário (não há rh.cpf.edit).
        self.user.iam_permissions = ["rh.funcionario.view", "rh.funcionario.edit"]
        ser = FuncionarioSerializer(
            self.func, data={"cpf": "98765432100"}, partial=True,
            context=self._ctx(self.user),
        )
        self.assertTrue(ser.is_valid(), ser.errors)

    def test_salario_sem_folha_edit_rejeita(self):
        self.user.iam_permissions = ["rh.funcionario.view", "rh.folha.view"]  # sem .edit
        ser = FuncionarioSerializer(
            self.func, data={"salario_base": "4000.00"}, partial=True,
            context=self._ctx(self.user),
        )
        self.assertFalse(ser.is_valid(), ser.errors)
        self.assertIn("salario_base", ser.errors)

    def test_salario_com_folha_edit_ok(self):
        self.user.iam_permissions = [
            "rh.funcionario.view", "rh.folha.view", "rh.folha.edit",
        ]
        ser = FuncionarioSerializer(
            self.func, data={"salario_base": "4000.00"}, partial=True,
            context=self._ctx(self.user),
        )
        self.assertTrue(ser.is_valid(), ser.errors)

    def test_rh_gestor_cria_ficha_completa(self):
        # Regressão do bug: com funcionario.* + folha.edit, cria a ficha inteira
        # (CPF não travado, salário liberado pela permissão de folha).
        self.user.iam_permissions = [
            "rh.funcionario.view", "rh.funcionario.create", "rh.funcionario.edit",
            "rh.cpf.view", "rh.folha.view", "rh.folha.edit",
        ]
        data = {
            "tenant": self.tenant.id,  # no endpoint real é injetado pelo perform_create
            "cargo": self.cargo.cargo_id, "nome_completo": "Maria Nova",
            "cpf": "98765432100", "data_nascimento": "1992-02-02", "genero": "feminino",
            "endereco_completo": "Rua B, 22", "data_admissao": "2021-01-01",
            "salario_base": "5000.00", "status_contrato": "ativo",
        }
        ser = FuncionarioSerializer(data=data, context=self._ctx(self.user))
        self.assertTrue(ser.is_valid(), ser.errors)

    def test_admin_escreve_qualquer_campo(self):
        self.admin.iam_permissions = []
        ser = FuncionarioSerializer(
            self.func, data={"salario_base": "4000.00"}, partial=True,
            context=self._ctx(self.admin),
        )
        self.assertTrue(ser.is_valid(), ser.errors)