"""O caminho de emergência do segundo fator, para quem tem shell na IAM (D240).

    python manage.py segundo_fator_emergencia <username> --codigos --operador "Nome" --motivo "..."
    python manage.py segundo_fator_emergencia <username> --remover --operador "Nome" --motivo "..."

É para o dono da plataforma que perdeu o celular **e** os códigos — a única
conta que nenhuma tela alcança (o admin do tenant não redefine o supervisor, e
ninguém redefine a própria conta). Chamar `segundo_fator.gerar_codigos` ou
`remover` direto no `manage.py shell` funciona, mas é mudo: foi assim em
30/09/2026. Este comando faz a mesma coisa e **nunca é silencioso**, como a
`redefinir-segundo-fator` do admin: evento na trilha, com o operador e o motivo
nos detalhes (o `autor` fica vazio — quem age não é um usuário do sistema), e
e-mail ao dono da conta.

- `--codigos`: dez códigos de recuperação novos, impressos aqui, uma vez. O
  aparelho segue valendo; os códigos antigos somem.
- `--remover`: apaga o segundo fator e derruba todas as sessões. Quem é obrigado
  a ter cadastra de novo no próximo login.

Shell no contêiner ou escrita no banco continuam podendo tudo — este comando não
fecha esse acesso, só dá à emergência um caminho que deixa rastro.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from identity import emails, recuperacao, segundo_fator
from identity.models import EventoSeguranca
from identity.revocation import bump_session_epoch
from identity.tokens import revoke_all_sessions


class Command(BaseCommand):
    help = "Emergência do segundo fator (códigos novos ou remoção), com evento na trilha e e-mail ao dono."

    def add_arguments(self, parser):
        parser.add_argument("username")
        acao = parser.add_mutually_exclusive_group(required=True)
        acao.add_argument("--codigos", action="store_true", help="Gera dez códigos de recuperação novos.")
        acao.add_argument("--remover", action="store_true", help="Apaga o segundo fator e derruba as sessões.")
        parser.add_argument("--operador", required=True, help="Quem está fazendo (vai para a trilha e o e-mail).")
        parser.add_argument("--motivo", required=True, help="Por quê (vai para a trilha).")

    def handle(self, *args, **opts):
        operador = opts["operador"].strip()
        motivo = opts["motivo"].strip()
        if not operador or not motivo:
            raise CommandError("--operador e --motivo não podem ficar vazios.")
        try:
            alvo = get_user_model().objects.get(username=opts["username"])
        except get_user_model().DoesNotExist:
            raise CommandError(f"Usuário {opts['username']!r} não existe.")
        if segundo_fator.ativo(alvo) is None:
            raise CommandError(f"{alvo.username} não tem segundo fator ativo.")
        detalhes = {"via": "comando", "operador": operador, "motivo": motivo}

        if opts["codigos"]:
            codigos = segundo_fator.gerar_codigos(alvo)
            recuperacao.registrar_evento(
                EventoSeguranca.Tipo.SEGUNDO_FATOR_CODIGOS, alvo=alvo, **detalhes,
            )
            emails.enviar_aviso_segundo_fator(alvo, "codigos", por_quem=operador)
            self.stdout.write(f"Códigos de recuperação novos de {alvo.username} (aparecem só agora):")
            for codigo in codigos:
                self.stdout.write(f"  {codigo}")
        else:
            segundo_fator.remover(alvo)
            revoke_all_sessions(alvo, motivo="segundo_fator_redefinido")
            bump_session_epoch(alvo.id)
            recuperacao.registrar_evento(
                EventoSeguranca.Tipo.SEGUNDO_FATOR_REDEFINIDO, alvo=alvo, **detalhes,
            )
            emails.enviar_aviso_segundo_fator(alvo, "redefinido", por_quem=operador)
            self.stdout.write(f"Segundo fator de {alvo.username} removido; sessões encerradas.")
        self.stdout.write(f"Evento gravado na trilha e {alvo.email or '(sem e-mail)'} avisado.")
