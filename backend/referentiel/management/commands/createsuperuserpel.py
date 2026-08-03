from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = 'Créer un superutilisateur pour l\'établissement'

    def add_arguments(self, parser):
        parser.add_argument('--username', type=str, required=True)
        parser.add_argument('--email', type=str, required=True)
        parser.add_argument('--password', type=str, required=True)
        parser.add_argument('--nom', type=str, default='')
        parser.add_argument('--prenom', type=str, default='')

    def handle(self, *args, **options):
        if User.objects.filter(username=options['username']).exists():
            self.stdout.write(self.style.WARNING(f'L\'utilisateur {options["username"]} existe déjà'))
            return

        user = User.objects.create_superuser(
            username=options['username'],
            email=options['email'],
            password=options['password'],
            first_name=options['prenom'],
            last_name=options['nom'],
            role='admin',
            is_staff=True,
            is_superuser=True,
        )
        self.stdout.write(self.style.SUCCESS(f'Superutilisateur {user.username} créé avec succès'))
