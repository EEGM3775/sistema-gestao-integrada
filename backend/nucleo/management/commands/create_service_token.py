# backend/nucleo/management/commands/create_service_token.py
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
import os

class Command(BaseCommand):
    help = 'Cria um usuário de serviço com um nome e CPF específicos e gera/exibe seu token de API.'

    def add_arguments(self, parser):
        parser.add_argument('--username', type=str, help='O nome de usuário para o serviço.', required=True)
        parser.add_argument('--cpf', type=str, help='O CPF placeholder para o usuário de serviço.', required=True)
        parser.add_argument('--first_name', type=str, help='O primeiro nome para o serviço (ex: "Serviço").', required=True)
        parser.add_argument('--last_name', type=str, help='O sobrenome para o serviço (ex: "Notificações").', required=True)

    def handle(self, *args, **options):
        User = get_user_model()
        username = options['username']
        cpf = options['cpf']
        first_name = options['first_name']
        last_name = options['last_name']
        
        # Cria o usuário de serviço ou o obtém se já existir
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                'cpf': cpf,
                'first_name': first_name,
                'last_name': last_name,
                'is_staff': True, # Permite acesso básico, mas as permissões são controladas por Perfis
            }
        )

        if created:
            # Define uma senha inutilizável, pois este usuário não fará login via formulário
            user.set_unusable_password()
            user.save()
            self.stdout.write(self.style.SUCCESS(f'Usuário de serviço "{username}" criado.'))
        else:
            self.stdout.write(self.style.WARNING(f'Usuário de serviço "{username}" já existe.'))

        # Cria um token para o usuário ou o obtém se já existir
        token, token_created = Token.objects.get_or_create(user=user)

        if token_created:
            self.stdout.write(self.style.SUCCESS('Novo token de API gerado.'))
        else:
            self.stdout.write(self.style.WARNING('Token de API já existia.'))

        self.stdout.write(self.style.NOTICE('='*50))
        self.stdout.write(self.style.SUCCESS(f'Token para o usuário "{username}":'))
        self.stdout.write(self.style.HTTP_INFO(token.key))
        self.stdout.write(self.style.NOTICE('='*50))
        self.stdout.write(self.style.WARNING(f'Copie este token e adicione-o ao arquivo .env do serviço {last_name} como DJANGO_API_TOKEN.'))
