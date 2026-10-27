"""File d'exécution, worker et notation (sous-projet 4b, tâche 3). Exécuteur factice : pas de Docker."""
from datetime import timedelta
from decimal import Decimal
import threading
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.db import OperationalError
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.testing import build_world
from programming.execution import file as fichier
from programming.execution.docker import DUREE_MAX_S
from programming.execution.notation import note_exercice, note_soumission
from programming.models import (CasDeTest, Devoir, Execution, Exercice, ReponseExercice, ResultatTest,
                                SoumissionDevoir)

PYTHON = 'main.py'


def fic(contenu='print(input())'):
    return [{'nom': PYTHON, 'contenu': contenu}]


class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()
        a = cls.w.a
        cls.etu = a.etu
        cls.devoir = Devoir.objects.create(titre='TP', filiere=a.filiere, langage='python', cree_par=a.ens)

    def exercice(self, points='4', tests=()):
        """tests : [(entree, sortie_attendue, public, poids)]"""
        exo = Exercice.objects.create(devoir=self.devoir, titre='E', points=Decimal(points),
                                      ordre=self.devoir.exercices.count())
        for i, (entree, sortie, public, poids) in enumerate(tests):
            CasDeTest.objects.create(exercice=exo, ordre=i, entree=entree, sortie_attendue=sortie,
                                     public=public, poids=poids)
        return exo

    def en_file(self, exo=None, **extra):
        exo = exo or self.exercice()
        return fichier.mettre_en_file(Execution.ESSAI_RUN, self.etu, self.devoir, exo, fichiers=fic(), **extra)


class FileTests(Base):
    def test_mettre_en_file(self):
        e = self.en_file(entree='x')
        self.assertEqual((e.statut, e.entree, e.reprises), (Execution.EN_ATTENTE, 'x', 0))
        self.assertEqual(e.fichiers, fic())

    def test_reclamation_unique_et_ordre(self):
        e1, e2 = self.en_file(), self.en_file()
        r1, r2 = fichier.reclamer(), fichier.reclamer()
        self.assertEqual((r1.pk, r2.pk), (e1.pk, e2.pk))
        self.assertIsNone(fichier.reclamer())
        r1.refresh_from_db()
        self.assertEqual(r1.statut, Execution.EN_COURS)
        self.assertIsNotNone(r1.debut)

    def test_reclamation_perdue_passe_a_la_suivante(self):
        e1, e2 = self.en_file(), self.en_file()
        # Un autre worker prend e1 entre la lecture du candidat et la mise à jour conditionnelle.
        reel = Execution.objects.filter

        def concurrent(*args, **kwargs):
            if kwargs.get('pk') == e1.pk and kwargs.get('statut') == Execution.EN_ATTENTE:
                Execution.objects.filter(pk=e1.pk).update(statut=Execution.EN_COURS)
            return reel(*args, **kwargs)

        with mock.patch.object(Execution.objects, 'filter', side_effect=concurrent):
            pris = fichier.reclamer()
        self.assertEqual(pris.pk, e2.pk)

    def test_seuil_derive_de_la_duree_maximale(self):
        self.assertGreaterEqual(fichier.SEUIL_REPRISE_S, 300)
        self.assertGreater(fichier.SEUIL_REPRISE_S, DUREE_MAX_S + 60)

    def bloquer(self, e, age_s, reprises=0):
        Execution.objects.filter(pk=e.pk).update(statut=Execution.EN_COURS, reprises=reprises,
                                                 debut=timezone.now() - timedelta(seconds=age_s))

    def test_reprise_d_une_bloquee(self):
        e = self.en_file()
        self.bloquer(e, fichier.SEUIL_REPRISE_S + 5)
        self.assertEqual(fichier.recuperer_bloquees(), (1, 0))
        e.refresh_from_db()
        self.assertEqual((e.statut, e.reprises, e.debut), (Execution.EN_ATTENTE, 1, None))

    def test_execution_lente_mais_saine_non_reprise(self):
        e = self.en_file()
        self.bloquer(e, DUREE_MAX_S + 30)
        self.assertEqual(fichier.recuperer_bloquees(), (0, 0))
        e.refresh_from_db()
        self.assertEqual(e.statut, Execution.EN_COURS)

    def test_abandon_apres_deux_reprises(self):
        e = self.en_file()
        self.bloquer(e, fichier.SEUIL_REPRISE_S + 5, reprises=1)
        self.assertEqual(fichier.recuperer_bloquees(), (1, 0))
        self.bloquer(e, fichier.SEUIL_REPRISE_S + 5, reprises=2)
        self.assertEqual(fichier.recuperer_bloquees(), (0, 1))
        e.refresh_from_db()
        self.assertEqual(e.statut, Execution.ERREUR)
        self.assertEqual(e.message, "Le service d'exécution est indisponible.")
        self.assertIsNotNone(e.fin)

    def test_en_cours_sans_debut_est_reprise(self):
        e = self.en_file()
        Execution.objects.filter(pk=e.pk).update(statut=Execution.EN_COURS, debut=None)
        self.assertEqual(fichier.recuperer_bloquees(), (1, 0))


@override_settings(PEL_EXECUTEUR='factice')
class WorkerTests(Base):
    def lancer(self, *args):
        sortie = StringIO()
        with mock.patch('programming.execution.docker.nettoyer_orphelins') as nettoyage:
            call_command('executer_file', '--une-fois', *args, stdout=sortie)
        return sortie.getvalue(), nettoyage

    def test_une_fois_traite_toute_la_file(self):
        exo = self.exercice(tests=[('a', 'a', True, 1)])
        executions = [self.en_file(exo) for _ in range(3)]
        sortie, nettoyage = self.lancer()
        self.assertIn('3 exécution(s) traitée(s).', sortie)
        nettoyage.assert_not_called()  # exécuteur factice : rien à nettoyer
        for e in executions:
            e.refresh_from_db()
            self.assertEqual(e.statut, Execution.TERMINEE)
            self.assertIsNotNone(e.debut)
            self.assertIsNotNone(e.fin)
        self.assertIsNone(fichier.reclamer())

    @override_settings(PEL_EXECUTEUR='docker')
    def test_nettoyage_au_demarrage_ne_bloque_pas_le_worker(self):
        e = self.en_file()
        with mock.patch('programming.execution.docker.nettoyer_orphelins', side_effect=RuntimeError('x')) as n:
            with mock.patch('programming.execution.executeur.executer'):
                call_command('executer_file', '--une-fois', stdout=StringIO())
        n.assert_called_once()
        e.refresh_from_db()
        self.assertEqual(e.statut, Execution.EN_COURS)  # executer simulé : l'exécution a bien été prise

    def test_une_execution_defaillante_n_arrete_pas_le_worker(self):
        e1, e2 = self.en_file(), self.en_file()
        from programming.execution import executeur
        original = executeur.executer

        def fragile(execution):
            if execution.pk == e1.pk:
                raise RuntimeError('boom')
            original(execution)

        with mock.patch('programming.execution.executeur.executer', side_effect=fragile):
            sortie, _ = self.lancer()
        self.assertIn('2 exécution(s) traitée(s).', sortie)
        e1.refresh_from_db(); e2.refresh_from_db()
        self.assertEqual(e1.statut, Execution.ERREUR)
        self.assertEqual(e2.statut, Execution.TERMINEE)

    def test_reprise_au_demarrage(self):
        e = self.en_file()
        Execution.objects.filter(pk=e.pk).update(
            statut=Execution.EN_COURS, debut=timezone.now() - timedelta(seconds=fichier.SEUIL_REPRISE_S + 5))
        self.lancer()
        e.refresh_from_db()
        self.assertEqual((e.statut, e.reprises), (Execution.TERMINEE, 1))

    def test_workers_invalide(self):
        erreur = StringIO()
        call_command('executer_file', '--une-fois', '--workers', '0', stdout=StringIO(), stderr=erreur)
        self.assertIn('--workers', erreur.getvalue())


class NotationTests(Base):
    def resultat(self, execution, cas, statut):
        return ResultatTest.objects.create(execution=execution, cas=cas, ordre=cas.ordre, statut=statut)

    def execution(self, exo, reponse=None):
        return Execution.objects.create(type=Execution.CORRECTION, demandeur=self.etu, devoir=self.devoir,
                                        exercice=exo, reponse=reponse, statut=Execution.TERMINEE)

    def test_poids_des_tests_caches(self):
        exo = self.exercice('4', [('1', '1', True, 1), ('a', 'x', False, 1), ('b', 'b', False, 3)])
        e = self.execution(exo)
        c1, c2, c3 = exo.tests.all()
        resultats = [self.resultat(e, c1, 'OK'), self.resultat(e, c2, 'WA'), self.resultat(e, c3, 'OK')]
        self.assertEqual(note_exercice(exo, resultats), Decimal('3.00'))  # 3/4 de 4 points

    def test_public_seulement_sans_test_cache(self):
        exo = self.exercice('4', [('1', '1', True, 1), ('2', '2', True, 1)])
        e = self.execution(exo)
        c1, c2 = exo.tests.all()
        self.assertEqual(note_exercice(exo, [self.resultat(e, c1, 'OK'), self.resultat(e, c2, 'WA')]),
                         Decimal('2.00'))

    def test_tests_publics_ignores_si_caches(self):
        exo = self.exercice('4', [('1', '1', True, 1), ('b', 'b', False, 1)])
        e = self.execution(exo)
        c1, c2 = exo.tests.all()
        self.assertEqual(note_exercice(exo, [self.resultat(e, c1, 'OK'), self.resultat(e, c2, 'WA')]), 0)

    def test_exercice_sans_test(self):
        self.assertEqual(note_exercice(self.exercice('4'), []), Decimal('0'))

    def test_test_sans_resultat_echoue(self):
        exo = self.exercice('3', [('a', 'a', False, 1), ('b', 'b', False, 2)])
        e = self.execution(exo)
        c1, _ = exo.tests.all()
        self.assertEqual(note_exercice(exo, [self.resultat(e, c1, 'OK')]), Decimal('1.00'))

    def test_arrondi_au_centieme(self):
        exo = self.exercice('1', [('a', 'a', False, 1), ('b', 'b', False, 2)])
        e = self.execution(exo)
        c1, _ = exo.tests.all()
        self.assertEqual(note_exercice(exo, [self.resultat(e, c1, 'OK')]), Decimal('0.33'))

    def test_somme_sur_les_exercices(self):
        soumission = SoumissionDevoir.objects.create(devoir=self.devoir, etudiant=self.etu)
        total = Decimal('0')
        for points, reussi in (('4', True), ('6', False), ('2', True)):
            exo = self.exercice(points, [('a', 'a', False, 1)])
            reponse = ReponseExercice.objects.create(soumission=soumission, exercice=exo, fichiers=fic())
            e = self.execution(exo, reponse)
            self.resultat(e, exo.tests.get(), 'OK' if reussi else 'WA')
            total += Decimal(points) if reussi else 0
        self.assertEqual(note_soumission(soumission), total)
        self.assertEqual(total, Decimal('6'))

    def test_exercice_sans_reponse_vaut_zero(self):
        soumission = SoumissionDevoir.objects.create(devoir=self.devoir, etudiant=self.etu)
        self.exercice('5', [('a', 'a', False, 1)])
        self.assertEqual(note_soumission(soumission), Decimal('0.00'))


@override_settings(PEL_EXECUTEUR='factice')
class CorrectionTests(Base):
    def preparer(self, contenus):
        """Un exercice (1 test caché 'a' -> 'a', 4 points) par contenu de réponse."""
        soumission = SoumissionDevoir.objects.create(devoir=self.devoir, etudiant=self.etu,
                                                     statut=SoumissionDevoir.SOUMIS)
        for contenu in contenus:
            exo = self.exercice('4', [('a', 'a', False, 1)])
            ReponseExercice.objects.create(soumission=soumission, exercice=exo, fichiers=fic(contenu))
        return soumission

    def travailler(self):
        with mock.patch('programming.execution.docker.nettoyer_orphelins'):
            call_command('executer_file', '--une-fois', stdout=StringIO())

    def test_une_correction_par_reponse(self):
        soumission = self.preparer(['print(input())', 'print(input())'])
        executions = fichier.corriger_soumission(soumission)
        self.assertEqual(len(executions), 2)
        self.assertTrue(all(e.type == Execution.CORRECTION and e.reponse_id for e in executions))
        soumission.refresh_from_db()
        self.assertEqual(soumission.statut, SoumissionDevoir.EN_CORRECTION)
        self.assertIsNone(soumission.note_proposee)

    def test_note_proposee_quand_tout_est_termine(self):
        soumission = self.preparer(['print(input())', '# PEL:SORTIE=faux'])
        fichier.corriger_soumission(soumission)
        self.travailler()
        soumission.refresh_from_db()
        self.assertEqual(soumission.statut, SoumissionDevoir.CORRIGEE_AUTO)
        self.assertEqual(soumission.note_proposee, Decimal('4.00'))

    def test_pas_de_note_tant_qu_une_correction_manque(self):
        soumission = self.preparer(['print(input())', 'print(input())'])
        e1, e2 = fichier.corriger_soumission(soumission)
        e1 = fichier.reclamer()
        fichier.traiter(e1)
        soumission.refresh_from_db()
        self.assertEqual(soumission.statut, SoumissionDevoir.EN_CORRECTION)
        self.assertIsNone(soumission.note_proposee)

    def test_correction_en_erreur_laisse_en_correction(self):
        soumission = self.preparer(['print(input())', '# PEL:INDISPONIBLE'])
        fichier.corriger_soumission(soumission)
        self.travailler()
        soumission.refresh_from_db()
        self.assertEqual(soumission.statut, SoumissionDevoir.EN_CORRECTION)
        self.assertIsNone(soumission.note_proposee)
        self.assertEqual(Execution.objects.filter(statut=Execution.ERREUR).count(), 1)

    def test_relance_apres_erreur_note_la_soumission(self):
        soumission = self.preparer(['print(input())', '# PEL:INDISPONIBLE'])
        fichier.corriger_soumission(soumission)
        self.travailler()
        erreur = Execution.objects.get(statut=Execution.ERREUR)
        reponse = erreur.reponse
        reponse.fichiers = fic('print(input())')
        reponse.save()
        fichier.mettre_en_file(Execution.CORRECTION, self.etu, self.devoir, erreur.exercice, reponse=reponse)
        self.travailler()
        soumission.refresh_from_db()
        self.assertEqual(soumission.statut, SoumissionDevoir.CORRIGEE_AUTO)
        self.assertEqual(soumission.note_proposee, Decimal('8.00'))

    def test_soumission_deja_corrigee_n_est_pas_renotee(self):
        soumission = self.preparer(['print(input())'])
        fichier.corriger_soumission(soumission)
        self.travailler()
        SoumissionDevoir.objects.filter(pk=soumission.pk).update(statut=SoumissionDevoir.CORRIGE,
                                                                 note_proposee=Decimal('1'))
        e = Execution.objects.get()
        self.assertFalse(fichier.apres_correction(e))
        soumission.refresh_from_db()
        self.assertEqual((soumission.statut, soumission.note_proposee),
                         (SoumissionDevoir.CORRIGE, Decimal('1.00')))

    def test_essai_sans_effet_sur_la_soumission(self):
        e = self.en_file()
        self.assertFalse(fichier.apres_correction(e))

    def test_soumission_sans_reponse(self):
        soumission = SoumissionDevoir.objects.create(devoir=self.devoir, etudiant=self.etu)
        self.assertEqual(fichier.corriger_soumission(soumission), [])
        soumission.refresh_from_db()
        self.assertEqual((soumission.statut, soumission.note_proposee), (SoumissionDevoir.CORRIGEE_AUTO, 0))


@override_settings(PEL_EXECUTEUR='factice')
class JetonDeReclamationTests(Base):
    def prete(self):
        exo = self.exercice(tests=[('a', 'a', False, 1)])
        return self.en_file(exo, entree='a')

    def reprendre_et_reclamer(self, e):
        Execution.objects.filter(pk=e.pk).update(
            debut=timezone.now() - timedelta(seconds=fichier.SEUIL_REPRISE_S + 5))
        fichier.recuperer_bloquees()
        return fichier.reclamer()

    def test_ancien_worker_ecarte_apres_reclamation_par_un_autre(self):
        self.prete()
        premier = fichier.reclamer()
        second = self.reprendre_et_reclamer(premier)
        self.assertEqual(second.pk, premier.pk)
        from programming.execution.executeur import executer
        # Le second termine d'abord, puis le premier (périmé) tente d'écrire.
        self.assertTrue(executer(second))
        avant = list(second.resultats.values_list('pk', 'statut'))
        self.assertFalse(executer(premier))
        e = Execution.objects.get(pk=premier.pk)
        self.assertEqual(e.statut, Execution.TERMINEE)
        self.assertEqual(list(e.resultats.values_list('pk', 'statut')), avant)

    def test_ancien_worker_n_ecrase_pas_une_execution_en_cours_chez_un_autre(self):
        self.prete()
        premier = fichier.reclamer()
        second = self.reprendre_et_reclamer(premier)
        from programming.execution.executeur import executer
        self.assertFalse(executer(premier))
        e = Execution.objects.get(pk=premier.pk)
        self.assertEqual((e.statut, e.fin), (Execution.EN_COURS, None))
        self.assertEqual(e.resultats.count(), 0)
        self.assertEqual(e.debut, second.debut)

    def test_abandonnee_reste_en_erreur(self):
        self.prete()
        e = fichier.reclamer()
        Execution.objects.filter(pk=e.pk).update(
            reprises=fichier.MAX_REPRISES, debut=timezone.now() - timedelta(seconds=fichier.SEUIL_REPRISE_S + 5))
        e.debut = Execution.objects.get(pk=e.pk).debut
        fichier.recuperer_bloquees()
        from programming.execution.executeur import executer
        self.assertFalse(executer(e))
        fichier.traiter(e)
        e2 = Execution.objects.get(pk=e.pk)
        self.assertEqual(e2.statut, Execution.ERREUR)
        self.assertEqual(e2.resultats.count(), 0)

    def test_ancien_worker_ne_note_pas_la_soumission(self):
        soumission = SoumissionDevoir.objects.create(devoir=self.devoir, etudiant=self.etu)
        exo = self.exercice(tests=[('a', 'a', False, 1)])
        ReponseExercice.objects.create(soumission=soumission, exercice=exo, fichiers=fic())
        fichier.corriger_soumission(soumission)
        premier = fichier.reclamer()
        self.reprendre_et_reclamer(premier)  # remise en file puis réclamée par un autre
        fichier.traiter(premier)
        soumission.refresh_from_db()
        self.assertEqual(soumission.statut, SoumissionDevoir.EN_CORRECTION)
        self.assertIsNone(soumission.note_proposee)

    def test_erreur_de_l_executeur_perimee_n_ecrase_rien(self):
        self.prete()
        premier = fichier.reclamer()
        self.reprendre_et_reclamer(premier)
        with mock.patch('programming.execution.executeur.executer', side_effect=RuntimeError('x')):
            fichier.traiter(premier)
        self.assertEqual(Execution.objects.get(pk=premier.pk).statut, Execution.EN_COURS)


@override_settings(PEL_EXECUTEUR='factice')
class ResilienceTests(Base):
    def commande(self):
        from programming.management.commands.executer_file import Command
        return Command()

    def test_reprise_survit_a_une_coupure_de_la_base(self):
        arret = threading.Event()
        appels = []

        def recuperer(*a, **k):
            appels.append(1)
            if len(appels) == 1:
                raise OperationalError('connexion perdue')
            arret.set()
            return (0, 0)

        with mock.patch.object(fichier, 'recuperer_bloquees', side_effect=recuperer),                 mock.patch('programming.management.commands.executer_file.close_old_connections') as renouvelle:
            self.commande()._boucle_principale(arret, periode=0)
        self.assertEqual(len(appels), 2)
        self.assertGreaterEqual(renouvelle.call_count, 2)

    def test_fil_continue_apres_une_coupure(self):
        arret = threading.Event()
        appels = []

        def reclamer():
            appels.append(1)
            if len(appels) == 1:
                raise OperationalError('connexion perdue')
            arret.set()
            return None

        with mock.patch.object(fichier, 'reclamer', side_effect=reclamer),                 mock.patch('programming.management.commands.executer_file.close_old_connections') as renouvelle,                 mock.patch('programming.management.commands.executer_file.connection'):
            self.commande()._fil(arret, 0)
        self.assertEqual(len(appels), 2)
        self.assertGreaterEqual(renouvelle.call_count, 2)
