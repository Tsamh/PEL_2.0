from django.core.management.base import BaseCommand

from quiz.passage import cloturer_expirees


class Command(BaseCommand):
    help = "Soumet automatiquement les tentatives de quiz dont le temps est écoulé (à lancer par cron)."

    def handle(self, *args, **options):
        nombre = cloturer_expirees()
        self.stdout.write(f"{nombre} tentative(s) clôturée(s).")
