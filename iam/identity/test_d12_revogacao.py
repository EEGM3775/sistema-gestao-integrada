"""D12 — a revogação vale em QUALQUER caminho, não só pelo endpoint.

O achado: `revoke_all_sessions` + `bump_session_epoch` só rodavam dentro do
`UsuarioSerializer`. Desativar por Django admin, `manage.py shell` ou script
deixava o access residual válido até expirar; excluir deixava o backend
RECRIAR o espelho local por JIT enquanto o token vivesse.

Estes testes exercitam o ORM direto — sem passar pela API — que é exatamente o
caminho que não era coberto.
"""
from unittest import mock

from django.test import TestCase

from identity.models import Tenant, Usuario


class D12RevogacaoPorSignalTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug="d12", nome="D12")
        self.usuario = Usuario.objects.create_user(
            username="d12_alvo", email="d12@exemplo.com", password="x", tenant=self.tenant
        )

    def test_desativar_pelo_orm_carimba_a_epoca(self):
        """O caminho do Django admin/shell — o que o serializer não cobria."""
        with mock.patch("identity.revocation.bump_session_epoch") as bump:
            self.usuario.is_active = False
            self.usuario.save()
        bump.assert_called_once_with(self.usuario.pk)

    def test_excluir_pelo_orm_carimba_a_epoca(self):
        """Sem isto o token vivo recriava o espelho no backend (JIT)."""
        pk = self.usuario.pk
        with mock.patch("identity.revocation.bump_session_epoch") as bump:
            self.usuario.delete()
        bump.assert_called_once_with(pk)

    def test_salvar_sem_mudar_is_active_nao_revoga(self):
        """Revogar a cada `save()` derrubaria a sessão do usuário a cada edição
        banal de cadastro — o gatilho é a TRANSIÇÃO ativo→inativo."""
        with mock.patch("identity.revocation.bump_session_epoch") as bump:
            self.usuario.first_name = "Nome Novo"
            self.usuario.save()
        bump.assert_not_called()

    def test_reativar_nao_revoga(self):
        self.usuario.is_active = False
        self.usuario.save()
        with mock.patch("identity.revocation.bump_session_epoch") as bump:
            self.usuario.is_active = True
            self.usuario.save()
        bump.assert_not_called()

    def test_criar_usuario_nao_revoga(self):
        with mock.patch("identity.revocation.bump_session_epoch") as bump:
            Usuario.objects.create_user(
                username="d12_novo", email="novo@exemplo.com", password="x",
                tenant=self.tenant,
            )
        bump.assert_not_called()

    def test_trocar_senha_pelo_orm_carimba_a_epoca(self):
        """O buraco que sobrou do D12: trocar a senha pelo Django admin/shell não
        encerrava nada — e o refresh antigo seguia renovando indefinidamente,
        porque o /auth/refresh/ confere `is_active`, não a senha."""
        with mock.patch("identity.revocation.bump_session_epoch") as bump:
            self.usuario.set_password("outra-senha-forte")
            self.usuario.save(update_fields=["password"])
        bump.assert_called_once_with(self.usuario.pk)

    def test_trocar_senha_blacklista_o_refresh(self):
        """Carimbar a época sozinha não basta: sem blacklistar, o refresh antigo
        continuaria emitindo access novo depois da troca."""
        with mock.patch("identity.tokens.revoke_all_sessions") as revoga:
            self.usuario.set_password("mais-uma-senha")
            self.usuario.save(update_fields=["password"])
        self.assertTrue(revoga.called)

    def test_salvar_sem_trocar_senha_nao_revoga(self):
        """Editar cadastro não pode derrubar a sessão de ninguém."""
        with mock.patch("identity.revocation.bump_session_epoch") as bump:
            self.usuario.email = "outro@exemplo.com"
            self.usuario.save()
        bump.assert_not_called()
