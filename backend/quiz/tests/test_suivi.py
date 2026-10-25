from datetime import timedelta
from decimal import Decimal

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from accounts.testing import build_world, make_user
from quiz import suivi
from quiz.models import SessionQuiz, TentativeQuiz
from referentiel.models import Classe, Groupe, Inscription


class Base(TestCase):
    """Quiz A fermé hier (ouvert il y a 3 jours) ; classe A : etu et etu2, sans tentative au départ."""

    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def setUp(self):
        a = self.a = self.w.a
        self.maintenant = timezone.now()
        self.quiz = a.quiz
        self.quiz.date_debut = self.maintenant - timedelta(days=3)
        self.quiz.date_fin = self.maintenant - timedelta(days=1)
        self.quiz.save()
        self.etu2 = make_user('etu2', 'etudiant', a.etab, first_name='Bea', last_name='Diallo')
        Inscription.objects.create(etudiant=self.etu2, classe=a.classe)

    def tentative(self, etudiant, debut, score=Decimal('1'), soumise=True, quiz=None):
        quiz = quiz or self.quiz
        numero = TentativeQuiz.objects.filter(quiz=quiz, etudiant=etudiant).count() + 1
        return TentativeQuiz.objects.create(
            quiz=quiz, etudiant=etudiant, numero=numero, debut=debut,
            fin_prevue=self.maintenant + timedelta(hours=1),
            statut=TentativeQuiz.SOUMISE if soumise else TentativeQuiz.EN_COURS,
            soumise_le=debut + timedelta(minutes=5) if soumise else None, score=score, score_max=Decimal('1'),
        )

    def lignes(self, **params):
        return {(l.quiz.pk, l.etudiant.pk): l for l in suivi.charger(suivi.quizzes_suivis(self.a.admin, params),
                                                                      maintenant=self.maintenant).lignes}


class StatutsTests(Base):
    def test_soumis_absent(self):
        self.tentative(self.a.etu, self.quiz.date_debut + timedelta(minutes=2))
        lignes = self.lignes()
        self.assertEqual(lignes[(self.quiz.pk, self.a.etu.pk)].statut, suivi.SOUMIS)
        self.assertEqual(lignes[(self.quiz.pk, self.a.etu.pk)].pourcentage, Decimal('100.00'))
        self.assertEqual(lignes[(self.quiz.pk, self.etu2.pk)].statut, suivi.ABSENT)
        self.assertIsNone(lignes[(self.quiz.pk, self.etu2.pk)].pourcentage)
        self.assertEqual(lignes[(self.quiz.pk, self.etu2.pk)].classes, [self.a.classe.pk])

    def test_en_cours(self):
        self.quiz.date_fin = self.maintenant + timedelta(days=1)
        self.quiz.save()
        self.tentative(self.a.etu, self.quiz.date_debut + timedelta(minutes=2), soumise=False)
        lignes = self.lignes()
        self.assertEqual(lignes[(self.quiz.pk, self.a.etu.pk)].statut, suivi.EN_COURS)
        self.assertEqual(lignes[(self.quiz.pk, self.etu2.pk)].statut, suivi.A_VENIR)

    def test_fenetre_sans_fin_jamais_absent(self):
        self.quiz.date_fin = None
        self.quiz.save()
        self.assertEqual(self.lignes()[(self.quiz.pk, self.etu2.pk)].statut, suivi.A_VENIR)

    def test_absent_avec_rattrapage_a_venir_reste_a_venir(self):
        r = SessionQuiz.objects.create(quiz=self.quiz, type=SessionQuiz.RATTRAPAGE,
                                       ouverture=self.maintenant + timedelta(days=1),
                                       fermeture=self.maintenant + timedelta(days=2))
        r.etudiants.add(self.etu2)
        self.assertEqual(self.lignes()[(self.quiz.pk, self.etu2.pk)].statut, suivi.A_VENIR)

    def test_session_normale_future_pour_la_classe(self):
        s = SessionQuiz.objects.create(quiz=self.quiz, ouverture=self.maintenant + timedelta(days=1),
                                       fermeture=self.maintenant + timedelta(days=2))
        s.classes.add(self.a.classe)
        self.assertEqual(self.lignes()[(self.quiz.pk, self.etu2.pk)].statut, suivi.A_VENIR)

    def test_etudiant_d_un_groupe_et_nominatif(self):
        self.quiz.classes.clear()
        groupe = Groupe.objects.create(code='TD1', libelle='TD 1', classe=self.a.classe)
        groupe.membres.add(self.a.etu)
        self.quiz.groupes.add(groupe)
        self.quiz.etudiants.add(self.etu2)
        lignes = self.lignes()
        self.assertEqual(set(lignes), {(self.quiz.pk, self.a.etu.pk), (self.quiz.pk, self.etu2.pk)})
        self.assertEqual(lignes[(self.quiz.pk, self.a.etu.pk)].classes, [self.a.classe.pk])
        self.assertEqual(lignes[(self.quiz.pk, self.etu2.pk)].classes, [self.a.classe.pk])

    def test_etudiant_retire_ayant_une_tentative_reste_compte(self):
        autre = make_user('etu9', 'etudiant', self.a.etab)
        self.tentative(autre, self.quiz.date_debut)
        ligne = self.lignes()[(self.quiz.pk, autre.pk)]
        self.assertEqual((ligne.statut, ligne.classes), (suivi.SOUMIS, []))

    def test_quiz_non_publie_sans_tentative_ignore(self):
        self.quiz.est_publie = False
        self.quiz.save()
        self.assertEqual(self.lignes(), {})
        self.tentative(self.a.etu, self.quiz.date_debut)
        self.assertIn((self.quiz.pk, self.a.etu.pk), self.lignes())

    def test_tentative_expiree_cloturee(self):
        t = self.tentative(self.a.etu, self.quiz.date_debut, soumise=False)
        t.fin_prevue = self.maintenant - timedelta(hours=2)
        t.save()
        self.assertEqual(self.lignes()[(self.quiz.pk, self.a.etu.pk)].statut, suivi.SOUMIS)


class RetardTests(Base):
    def test_retard_fenetre_generale(self):
        self.tentative(self.a.etu, self.quiz.date_debut + timedelta(minutes=20))
        self.tentative(self.etu2, self.quiz.date_debut + timedelta(minutes=15))
        lignes = self.lignes()
        self.assertEqual(lignes[(self.quiz.pk, self.a.etu.pk)].retard, 20)
        self.assertIsNone(lignes[(self.quiz.pk, self.etu2.pk)].retard)

    def test_premiere_tentative_seule(self):
        self.tentative(self.a.etu, self.quiz.date_debut + timedelta(minutes=1))
        self.tentative(self.a.etu, self.quiz.date_debut + timedelta(hours=5))
        self.assertIsNone(self.lignes()[(self.quiz.pk, self.a.etu.pk)].retard)

    def test_retard_mesure_depuis_la_session(self):
        ouverture = self.maintenant - timedelta(days=2)
        s = SessionQuiz.objects.create(quiz=self.quiz, ouverture=ouverture, fermeture=ouverture + timedelta(hours=2))
        s.classes.add(self.a.classe)
        self.tentative(self.a.etu, ouverture + timedelta(minutes=30))
        self.tentative(self.etu2, ouverture + timedelta(minutes=10))
        lignes = self.lignes()
        self.assertEqual(lignes[(self.quiz.pk, self.a.etu.pk)].retard, 30)
        self.assertIsNone(lignes[(self.quiz.pk, self.etu2.pk)].retard)

    def test_delai_de_l_etablissement(self):
        self.a.etab.delai_retard_minutes = 0
        self.a.etab.save()
        self.tentative(self.a.etu, self.quiz.date_debut + timedelta(minutes=1))
        self.assertEqual(self.lignes()[(self.quiz.pk, self.a.etu.pk)].retard, 1)

    def test_sans_ouverture_pas_de_retard(self):
        self.quiz.date_debut = None
        self.quiz.save()
        self.tentative(self.a.etu, self.maintenant - timedelta(days=2))
        self.assertIsNone(self.lignes()[(self.quiz.pk, self.a.etu.pk)].retard)


class FiltresEtPerimetreTests(Base):
    def test_enseignant_voit_ses_quiz_seulement(self):
        self.assertIn(self.quiz, suivi.quizzes_suivis(self.a.ens, {}))
        autre_ens = make_user('ens2', 'enseignant', self.a.etab)
        self.assertNotIn(self.quiz, suivi.quizzes_suivis(autre_ens, {}))

    def test_gestion_b_ne_voit_pas_a(self):
        self.assertNotIn(self.quiz, suivi.quizzes_suivis(self.w.b.admin, {}))

    def test_filtres(self):
        a = self.a
        self.quiz.ec = a.ec
        self.quiz.save()
        cas = {
            'annee': a.annee.pk, 'filiere': a.filiere.pk, 'niveau': self.w.niveau.pk,
            'ue': a.ue.pk, 'ec': a.ec.pk, 'classe': a.classe.pk,
        }
        for cle, valeur in cas.items():
            with self.subTest(cle=cle):
                self.assertIn(self.quiz, suivi.quizzes_suivis(a.admin, {cle: str(valeur)}))
                self.assertNotIn(self.quiz, suivi.quizzes_suivis(a.admin, {cle: '999999'}))

    def test_filtre_invalide_ignore(self):
        self.assertIn(self.quiz, suivi.quizzes_suivis(self.a.admin, {'filiere': 'abc', 'classe': '-1'}))

    def test_filtre_classe_restreint_les_etudiants(self):
        a = self.a
        autre = Classe.objects.create(code='L1A2', libelle='L1 Info A bis', filiere=a.filiere,
                                      niveau=self.w.niveau, annee_academique=a.annee)
        self.quiz.classes.add(autre)
        Inscription.objects.create(etudiant=self.etu2, classe=autre)
        Inscription.objects.filter(etudiant=self.etu2, classe=a.classe).delete()
        contexte = suivi.charger(suivi.quizzes_suivis(a.admin, {'classe': str(autre.pk)}), classe=autre.pk,
                                 maintenant=self.maintenant)
        self.assertEqual([l.etudiant.pk for l in contexte.lignes], [self.etu2.pk])


class RequetesTests(Base):
    def compter(self):
        with CaptureQueriesContext(connection) as ctx:
            suivi.charger(suivi.quizzes_suivis(self.a.admin, {}), maintenant=self.maintenant)
        return len(ctx.captured_queries)

    def test_nombre_de_requetes_constant(self):
        self.tentative(self.a.etu, self.quiz.date_debut)
        s = SessionQuiz.objects.create(quiz=self.quiz, ouverture=self.maintenant - timedelta(days=2),
                                       fermeture=self.maintenant - timedelta(days=1))
        s.classes.add(self.a.classe)
        groupe = Groupe.objects.create(code='TD1', libelle='TD 1', classe=self.a.classe)
        self.quiz.groupes.add(groupe)
        avant = self.compter()
        for i in range(10, 16):
            e = make_user(f'etu{i}', 'etudiant', self.a.etab)
            Inscription.objects.create(etudiant=e, classe=self.a.classe)
            groupe.membres.add(e)
            self.tentative(e, self.quiz.date_debut)
        self.assertEqual(self.compter(), avant)
