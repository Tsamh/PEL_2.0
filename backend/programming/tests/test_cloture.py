"""Soumission automatique des brouillons à la fermeture (sous-projet 4c, tâche 5)."""
from datetime import timedelta
from io import StringIO
from unittest import mock

from django.core import mail
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from accounts.testing import build_world, make_user
from audit.models import AuditLog
from programming import cloture
from programming.models import (
    BrouillonExercice, Devoir, Exercice, Execution, ReponseExercice, SessionDevoir, SoumissionDevoir,
)
from referentiel.models import Inscription


def fic(contenu, nom='main.py'):
    return [{'nom': nom, 'contenu': contenu}]


@override_settings(PEL_EXECUTEUR='factice')
class ClotureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def setUp(self):
        self.a = self.w.a
        self.devoir = self.a.devoir
        self.etu = self.a.etu
        self.ex = self.a.exercice
        self.maintenant = timezone.now()
        self.fermeture = self.maintenant - timedelta(seconds=31)
        self.dates(self.maintenant - timedelta(days=1), self.fermeture)

    def dates(self, debut, fin):
        Devoir.objects.filter(pk=self.devoir.pk).update(date_debut=debut, date_fin=fin)

    def brouillon(self, etudiant=None, contenu='print(4)'):
        return BrouillonExercice.objects.create(etudiant=etudiant or self.etu, exercice=self.ex, fichiers=fic(contenu))

    def cloturer(self, maintenant=None):
        with self.captureOnCommitCallbacks(execute=True):
            return cloture.cloturer_devoirs_echus(maintenant or self.maintenant)

    def autre_etudiant(self, nom='etu2'):
        etu = make_user(nom, 'etudiant', self.a.etab)
        Inscription.objects.create(etudiant=etu, classe=self.a.classe)
        return etu

    def test_fermeture_depassee_de_31_s(self):
        self.brouillon()
        self.assertEqual(self.cloturer(), 1)
        s = SoumissionDevoir.objects.get()
        self.assertEqual((s.devoir, s.etudiant, s.soumission_auto), (self.devoir, self.etu, True))
        self.assertEqual(s.statut, SoumissionDevoir.EN_CORRECTION)
        reponse = ReponseExercice.objects.get(soumission=s)
        self.assertEqual((reponse.exercice, reponse.fichiers), (self.ex, fic('print(4)')))
        self.assertEqual(Execution.objects.filter(reponse=reponse, type=Execution.CORRECTION,
                                                  statut=Execution.EN_ATTENTE).count(), 1)
        self.assertFalse(BrouillonExercice.objects.exists())
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.etu.email])
        self.assertIn('automatiquement', mail.outbox[0].body)
        entree = AuditLog.objects.get(action='soumission_devoir_auto')
        self.assertEqual((entree.acteur, entree.cible_id), (self.etu, str(s.pk)))
        self.assertEqual(entree.etablissement, self.a.etab)
        self.assertEqual(entree.details['devoir'], self.devoir.pk)

    def test_brouillons_supprimes_meme_si_resoumission_autorisee(self):
        Devoir.objects.filter(pk=self.devoir.pk).update(resoumission_autorisee=True)
        self.brouillon()
        self.assertEqual(self.cloturer(), 1)
        self.assertFalse(BrouillonExercice.objects.exists())

    def test_fermeture_depassee_de_29_s(self):
        self.dates(self.maintenant - timedelta(days=1), self.maintenant - timedelta(seconds=29))
        self.brouillon()
        self.assertEqual(self.cloturer(), 0)
        self.assertFalse(SoumissionDevoir.objects.exists())
        self.assertTrue(BrouillonExercice.objects.exists())

    def test_rattrapage_ouvert_rien(self):
        SessionDevoir.objects.create(
            devoir=self.devoir, type=SessionDevoir.RATTRAPAGE, ouverture=self.maintenant - timedelta(hours=1),
            fermeture=self.maintenant + timedelta(hours=1)).etudiants.add(self.etu)
        self.brouillon()
        self.assertEqual(self.cloturer(), 0)
        self.assertTrue(BrouillonExercice.objects.exists())

    def test_rattrapage_a_venir_rien(self):
        SessionDevoir.objects.create(
            devoir=self.devoir, type=SessionDevoir.RATTRAPAGE, ouverture=self.maintenant + timedelta(hours=1),
            fermeture=self.maintenant + timedelta(hours=2)).etudiants.add(self.etu)
        self.brouillon()
        self.assertEqual(self.cloturer(), 0)
        self.assertTrue(BrouillonExercice.objects.exists())

    def test_rattrapage_termine_depasse_de_31_s(self):
        SessionDevoir.objects.create(
            devoir=self.devoir, type=SessionDevoir.RATTRAPAGE, ouverture=self.maintenant - timedelta(hours=1),
            fermeture=self.maintenant - timedelta(seconds=31)).etudiants.add(self.etu)
        self.brouillon()
        self.assertEqual(self.cloturer(), 1)

    def test_devoir_a_sessions_seulement(self):
        self.dates(None, None)
        session = SessionDevoir.objects.create(
            devoir=self.devoir, ouverture=self.maintenant - timedelta(hours=1), fermeture=self.fermeture)
        session.classes.add(self.a.classe)
        self.brouillon()
        self.assertEqual(self.cloturer(), 1)

    def test_devoir_a_sessions_encore_ouverte(self):
        self.dates(None, None)
        session = SessionDevoir.objects.create(
            devoir=self.devoir, ouverture=self.maintenant - timedelta(hours=1),
            fermeture=self.maintenant + timedelta(hours=1))
        session.classes.add(self.a.classe)
        self.brouillon()
        self.assertEqual(self.cloturer(), 0)

    def test_devoir_sans_fermeture(self):
        self.dates(self.maintenant - timedelta(days=1), None)
        self.brouillon()
        self.assertEqual(self.cloturer(), 0)
        self.assertTrue(BrouillonExercice.objects.exists())

    def test_devoir_sans_aucune_date(self):
        self.dates(None, None)
        self.brouillon()
        self.assertEqual(self.cloturer(), 0)

    def test_soumission_existante_ignoree_sans_erreur(self):
        SoumissionDevoir.objects.create(devoir=self.devoir, etudiant=self.etu)
        self.brouillon()
        with self.assertNoLogs('programming', level='ERROR'):
            self.assertEqual(self.cloturer(), 0)
        self.assertEqual(SoumissionDevoir.objects.count(), 1)
        self.assertTrue(BrouillonExercice.objects.exists())
        self.assertEqual(mail.outbox, [])

    def test_soumission_apparue_sous_verrou(self):
        """Soumission créée entre la sélection et le verrou : rien, ni erreur ni accusé."""
        self.brouillon()
        reel = Devoir.objects.select_for_update

        def concurrente(*args, **kwargs):
            SoumissionDevoir.objects.get_or_create(devoir=self.devoir, etudiant=self.etu)
            return reel(*args, **kwargs)

        with mock.patch.object(Devoir.objects, 'select_for_update', side_effect=concurrente):
            self.assertEqual(self.cloturer(), 0)
        self.assertEqual(SoumissionDevoir.objects.count(), 1)
        self.assertFalse(SoumissionDevoir.objects.get().soumission_auto)
        self.assertEqual(mail.outbox, [])

    def test_annee_archivee_rien(self):
        type(self.a.annee).objects.filter(pk=self.a.annee.pk).update(archivee=True)
        self.brouillon()
        with self.assertNoLogs('programming', level='ERROR'):
            self.assertEqual(self.cloturer(), 0)
        self.assertTrue(BrouillonExercice.objects.exists())

    def test_plus_affecte_rien(self):
        self.devoir.classes.clear()
        self.brouillon()
        self.assertEqual(self.cloturer(), 0)
        self.assertTrue(BrouillonExercice.objects.exists())

    def test_devoir_depublie_non_cloture_brouillons_gardes(self):
        Devoir.objects.filter(pk=self.devoir.pk).update(est_publie=False)
        self.brouillon()
        self.assertEqual(self.cloturer(), 0)
        self.assertFalse(SoumissionDevoir.objects.exists())
        self.assertTrue(BrouillonExercice.objects.exists())

    def test_deuxieme_appel_zero(self):
        self.brouillon()
        self.assertEqual(self.cloturer(), 1)
        self.assertEqual(self.cloturer(), 0)
        self.assertEqual(SoumissionDevoir.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_brouillon_invalide_journalise_les_autres_traites(self):
        autre = self.autre_etudiant()
        self.brouillon(self.etu, contenu='print(4)')
        BrouillonExercice.objects.create(etudiant=autre, exercice=self.ex, fichiers=[])
        with self.assertLogs('programming', level='ERROR') as journal:
            self.assertEqual(self.cloturer(), 1)
        self.assertTrue(any(f'etudiant {autre.pk}' in ligne for ligne in journal.output), journal.output)
        self.assertEqual(list(SoumissionDevoir.objects.values_list('etudiant', flat=True)), [self.etu.pk])
        self.assertTrue(BrouillonExercice.objects.filter(etudiant=autre).exists())

    def test_brouillon_invalide_ignore_seul_les_valides_soumis(self):
        ex2 = Exercice.objects.create(devoir=self.devoir, ordre=2, titre='Deux')
        self.brouillon(contenu='print(4)')
        BrouillonExercice.objects.create(etudiant=self.etu, exercice=ex2, fichiers=[])
        with self.assertLogs('programming', level='ERROR') as journal:
            self.assertEqual(self.cloturer(), 1)
        self.assertTrue(any(f'exercice {ex2.pk}' in ligne for ligne in journal.output), journal.output)
        s = SoumissionDevoir.objects.get()
        self.assertEqual(list(s.reponses.values_list('exercice', flat=True)), [self.ex.pk])
        self.assertFalse(BrouillonExercice.objects.exists())

    def test_aucun_brouillon_valide_pas_de_soumission(self):
        BrouillonExercice.objects.create(etudiant=self.etu, exercice=self.ex, fichiers=[])
        with self.assertLogs('programming', level='ERROR'):
            self.assertEqual(self.cloturer(), 0)
        self.assertFalse(SoumissionDevoir.objects.exists())
        self.assertTrue(BrouillonExercice.objects.exists())

    def test_fermeture_depassee_de_exactement_30_s(self):
        self.dates(self.maintenant - timedelta(days=1), self.maintenant - timedelta(seconds=30))
        self.brouillon()
        self.assertEqual(self.cloturer(), 0)
        self.assertFalse(SoumissionDevoir.objects.exists())

    def test_verrou_du_devoir_sans_jointure_externe(self):
        """PostgreSQL refuse FOR UPDATE sur le côté nullable d'une jointure externe (annee_academique nullable)."""
        self.brouillon()
        with CaptureQueriesContext(connection) as requetes:
            self.assertEqual(self.cloturer(), 1)
        sur_devoir = [r['sql'] for r in requetes if 'FROM "programming_devoir"' in r['sql']]
        self.assertTrue(sur_devoir)
        self.assertFalse([sql for sql in sur_devoir if 'OUTER JOIN' in sql], sur_devoir)

    def test_devoir_ouvert_aucune_transaction_verrouillee(self):
        self.dates(self.maintenant - timedelta(days=1), self.maintenant + timedelta(days=1))
        self.brouillon()
        with mock.patch.object(Devoir.objects, 'select_for_update', wraps=Devoir.objects.select_for_update) as verrou:
            self.assertEqual(self.cloturer(), 0)
        verrou.assert_not_called()
        self.assertTrue(BrouillonExercice.objects.exists())

    def test_langage_autre_reste_soumis(self):
        Devoir.objects.filter(pk=self.devoir.pk).update(langage='autre')
        self.brouillon(contenu='x')
        self.assertEqual(self.cloturer(), 1)
        s = SoumissionDevoir.objects.get()
        self.assertEqual(s.statut, SoumissionDevoir.SOUMIS)
        self.assertFalse(Execution.objects.exists())

    def test_executer_file_une_fois_traite_la_cloture(self):
        self.dates(timezone.now() - timedelta(days=2), timezone.now() - timedelta(days=1))
        self.brouillon()
        with mock.patch('programming.execution.docker.nettoyer_orphelins'):
            call_command('executer_file', '--une-fois', stdout=StringIO())
        s = SoumissionDevoir.objects.get()
        self.assertTrue(s.soumission_auto)
        # Les corrections créées par la clôture sont vidées dans la même passe.
        self.assertFalse(Execution.objects.filter(type=Execution.CORRECTION, statut=Execution.EN_ATTENTE).exists())

    def test_echec_de_cloture_n_empeche_pas_la_reprise(self):
        from programming.management.commands.executer_file import Command
        with mock.patch('programming.cloture.cloturer_devoirs_echus', side_effect=RuntimeError('boum')), \
                mock.patch('programming.execution.file.recuperer_bloquees') as reprise, \
                self.assertLogs('programming.execution', level='ERROR'):
            Command()._reprendre()
        reprise.assert_called_once()

    def test_echec_de_reprise_n_empeche_pas_la_cloture(self):
        from programming.management.commands.executer_file import Command
        with mock.patch('programming.execution.file.recuperer_bloquees', side_effect=RuntimeError('boum')),                 mock.patch('programming.cloture.cloturer_devoirs_echus') as fermeture,                 self.assertLogs('programming.execution', level='ERROR'):
            Command()._reprendre()
        fermeture.assert_called_once()
