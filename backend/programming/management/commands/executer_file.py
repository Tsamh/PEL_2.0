"""Worker de la file d'exécution : `python manage.py executer_file [--workers N] [--une-fois]`.

`--workers N` lance N fils (threads) qui réclament chacun des exécutions ; chaque fil a sa connexion à la base.
Avec SQLite (développement), préférer `--workers 1` : l'écriture concurrente peut verrouiller la base.
`--une-fois` traite la file séquentiellement, dans le processus courant, puis s'arrête (tests, cron).
Ctrl+C arrête proprement : les exécutions en cours se terminent, aucune nouvelle n'est réclamée.
"""
import logging
import threading
import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import close_old_connections, connection

from programming.execution import file as fichier_attente

logger = logging.getLogger('programming.execution')

INTERVALLE_REPRISE_S = 30


def nettoyer_au_demarrage():
    """Supprime les conteneurs et dossiers orphelins ; n'empêche jamais le worker de démarrer."""
    if getattr(settings, 'PEL_EXECUTEUR', 'docker') != 'docker':
        return
    try:
        from programming.execution import docker
        docker.nettoyer_orphelins()
    except Exception:  # noqa: BLE001
        logger.exception("Nettoyage des orphelins impossible")


class Command(BaseCommand):
    help = "Traite la file des exécutions de code (correction automatique et essais)."

    def add_arguments(self, parser):
        parser.add_argument('--workers', type=int, default=None,
                            help="Nombre de fils de traitement (défaut : PEL_WORKERS_EXECUTION).")
        parser.add_argument('--une-fois', action='store_true', dest='une_fois',
                            help="Traite la file puis s'arrête.")
        parser.add_argument('--intervalle', type=float, default=1.0,
                            help="Secondes d'attente quand la file est vide (défaut : 1).")

    def handle(self, *args, **options):
        nombre = options['workers'] if options['workers'] is not None else settings.PEL_WORKERS_EXECUTION
        if nombre < 1:
            self.stderr.write("--workers doit être au moins 1.")
            return
        nettoyer_au_demarrage()
        self._reprendre()
        if options['une_fois']:
            traitees = self._vider()
            self.stdout.write(f"{traitees} exécution(s) traitée(s).")
            return
        arret = threading.Event()
        fils = [threading.Thread(target=self._fil, args=(arret, options['intervalle']), daemon=True)
                for _ in range(nombre)]
        for f in fils:
            f.start()
        self.stdout.write(f"Worker démarré ({nombre} fil(s)). Ctrl+C pour arrêter.")
        try:
            while not arret.is_set():
                time.sleep(INTERVALLE_REPRISE_S)
                self._reprendre()
        except KeyboardInterrupt:
            self.stdout.write("Arrêt en cours...")
        finally:
            arret.set()
            for f in fils:
                f.join()

    def _reprendre(self):
        try:
            fichier_attente.recuperer_bloquees()
        except Exception:  # noqa: BLE001
            logger.exception("Reprise des exécutions bloquées impossible")

    def _vider(self):
        traitees = 0
        while True:
            execution = fichier_attente.reclamer()
            if execution is None:
                return traitees
            fichier_attente.traiter(execution)
            traitees += 1

    def _fil(self, arret, intervalle):
        try:
            while not arret.is_set():
                try:
                    execution = fichier_attente.reclamer()
                except Exception:  # noqa: BLE001 : base momentanément indisponible
                    logger.exception("Réclamation impossible")
                    execution = None
                    close_old_connections()
                if execution is None:
                    arret.wait(intervalle)
                    continue
                fichier_attente.traiter(execution)
        finally:
            connection.close()
