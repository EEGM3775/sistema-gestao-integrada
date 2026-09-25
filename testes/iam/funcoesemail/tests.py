"""Testes do pacote compartilhado de e-mail.

Rodam junto da suíte da IAM (`manage.py test funcoesemail`), que é quem o usa
hoje. Se o backend passar a usá-lo, os mesmos testes valem lá — o pacote não
depende de nada específico de nenhum dos dois serviços, que é justamente a
propriedade que se quer proteger aqui.
"""
from django.core import mail
from django.test import SimpleTestCase, override_settings

from funcoesemail import MENSAGENS, enviar, enviar_varios
from funcoesemail.mensagens import MensagemDesconhecida
from funcoesemail.render import renderizar


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    EMAIL_HOST="smtp-de-teste",
    DEFAULT_FROM_EMAIL="SGI <noreply@exemplo.com>",
)
class EnvioTests(SimpleTestCase):
    def setUp(self):
        mail.outbox = []

    def test_envia_e_preenche_assunto_e_corpo(self):
        ok = enviar(
            "identidade.recuperacao",
            "maria@empresa.com",
            {"nome": "Maria", "conta": "maria", "link": "https://x/y?token=abc", "minutos": 30},
        )
        self.assertTrue(ok)
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertEqual(msg.subject, "Redefinição de senha")
        self.assertEqual(msg.to, ["maria@empresa.com"])
        self.assertIn("Olá, Maria.", msg.body)
        self.assertIn("https://x/y?token=abc", msg.body)
        self.assertIn("30 minutos", msg.body)

    def test_assinatura_vai_em_todo_e_mail(self):
        enviar("identidade.aviso_senha_alterada", "a@b.com",
               {"nome": "A", "conta": "a", "por_quem": "por você"})
        self.assertIn("não responda", mail.outbox[0].body)

    def test_destinatario_vazio_nao_envia_e_nao_levanta(self):
        self.assertFalse(enviar("identidade.recuperacao", "", {}))
        self.assertEqual(mail.outbox, [])

    def test_chave_desconhecida_levanta(self):
        """Erro de programação tem de aparecer no teste, não virar e-mail vazio."""
        with self.assertRaises(MensagemDesconhecida):
            enviar("identidade.inexistente", "a@b.com", {})

    def test_enviar_varios_deduplica(self):
        """Trocar só a grafia da caixa não deve mandar o mesmo aviso duas vezes."""
        n = enviar_varios(
            "identidade.aviso_email_trocado",
            ["mesmo@x.com", "mesmo@x.com", ""],
            {"nome": "A", "conta": "a", "email_antigo": "mesmo@x.com",
             "email_novo": "mesmo@x.com", "autor": "Admin"},
        )
        self.assertEqual(n, 1)
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(EMAIL_HOST="")
    def test_sem_smtp_configurado_nao_envia_e_nao_levanta(self):
        self.assertFalse(enviar("identidade.recuperacao", "a@b.com",
                                {"nome": "A", "conta": "a", "link": "l", "minutos": 1}))


class RenderTests(SimpleTestCase):
    def test_nao_escapa_html_em_texto_puro(self):
        """`Fulano & Cia` não pode virar `Fulano &amp; Cia` no corpo."""
        _, corpo = renderizar(
            "identidade.aviso_privilegio_alterado",
            {"nome": "Fulano & Cia", "conta": "f", "autor": "Admin", "resumo": "x > y"},
        )
        self.assertIn("Fulano & Cia", corpo)
        self.assertIn("x > y", corpo)
        self.assertNotIn("&amp;", corpo)

    def test_assunto_aceita_placeholder(self):
        assunto, _ = renderizar(
            "identidade.aviso_admin_recuperacao",
            {"nome": "Chefe", "alvo": "joao", "alvo_nome_completo": "",
             "alvo_email": "j@x.com", "origem": "1.2.3.4"},
        )
        self.assertEqual(assunto, "Pedido de recuperação de senha: joao")

    def test_todo_template_registrado_existe_em_disco(self):
        """Pega chave registrada apontando para arquivo que ninguém criou —
        falha que, sem isto, só apareceria na hora de mandar o e-mail real."""
        for chave in MENSAGENS:
            with self.subTest(chave=chave):
                renderizar(chave, {})
