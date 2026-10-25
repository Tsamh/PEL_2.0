from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from accounts.testing import build_world, client_for, make_user
from quiz.models import Quiz, TentativeQuiz
from referentiel.models import Inscription

Q = '/api/quiz'


class SuiviApiTests(TestCase):
    """Classe A : etu (80 %, en retard de 30 min), etu2 (absent), etu3 (60 %, à l'heure) sur le quiz A fermé.
    Un second quiz A2 (sans matière, ouvert) : etu3 a soumis 100 %."""

    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()
        a = cls.a = cls.w.a
        maintenant = timezone.now()
        cls.quiz = a.quiz
        cls.quiz.date_debut = maintenant - timedelta(days=3)
        cls.quiz.date_fin = maintenant - timedelta(days=1)
        cls.quiz.ec = a.ec
        cls.quiz.save()
        cls.etu2 = make_user('etu2', 'etudiant', a.etab, first_name='Bea', last_name='Diallo')
        cls.etu3 = make_user('etu3', 'etudiant', a.etab, first_name='Cheikh', last_name='Ba')
        for e in (cls.etu2, cls.etu3):
            Inscription.objects.create(etudiant=e, classe=a.classe)
        cls.quiz2 = Quiz.objects.create(titre='Quiz A2', filiere=a.filiere, niveau=cls.w.niveau,
                                        annee_academique=a.annee, est_publie=True, cree_par=a.ens)
        cls.quiz2.classes.add(a.classe)

        def tentative(quiz, etudiant, debut, score):
            TentativeQuiz.objects.create(quiz=quiz, etudiant=etudiant, numero=1, debut=debut,
                                         fin_prevue=debut + timedelta(minutes=30), soumise_le=debut + timedelta(minutes=10),
                                         statut=TentativeQuiz.SOUMISE, score=score, score_max=Decimal('10'))
        tentative(cls.quiz, a.etu, cls.quiz.date_debut + timedelta(minutes=30), Decimal('8'))
        tentative(cls.quiz, cls.etu3, cls.quiz.date_debut + timedelta(minutes=5), Decimal('6'))
        tentative(cls.quiz2, cls.etu3, maintenant - timedelta(hours=1), Decimal('10'))

    def get(self, user, chemin='', **params):
        return client_for(user).get(f'{Q}/suivi/{chemin}', params)

    def test_synthese_par_classe(self):
        res = self.get(self.a.admin, regroupement='classe')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data['regroupement'], 'classe')
        groupe, = res.data['groupes']
        self.assertEqual(groupe['cle'], str(self.a.classe.pk))
        self.assertEqual(groupe['libelle'], self.a.classe.libelle)
        attendu = {'nb_evaluations': 2, 'concernes': 6, 'soumis': 3, 'absents': 1, 'retards': 1, 'en_attente': 2,
                   'taux_participation': '75.00', 'moyenne_pourcentage': '80.00'}
        self.assertEqual({k: groupe[k] for k in attendu}, attendu)
        self.assertEqual({k: res.data['total'][k] for k in attendu}, attendu)

    def test_regroupement_par_matiere(self):
        res = self.get(self.a.admin, regroupement='ec')
        libelles = [g['libelle'] for g in res.data['groupes']]
        self.assertEqual(libelles, ['Python', 'Sans matière'])
        sans = res.data['groupes'][1]
        self.assertEqual((sans['cle'], sans['soumis'], sans['absents'], sans['taux_participation']),
                         ('aucun', 1, 0, '100.00'))

    def test_autres_regroupements(self):
        for regroupement, libelle in (('filiere', self.a.filiere.libelle), ('ue', self.a.ue.libelle)):
            with self.subTest(regroupement=regroupement):
                res = self.get(self.a.admin, regroupement=regroupement)
                self.assertEqual(res.data['groupes'][0]['libelle'], libelle)
        res = self.get(self.a.admin, regroupement='cohorte')
        groupe, = res.data['groupes']
        self.assertEqual(groupe['cle'], f'{self.a.annee.pk}-{self.a.filiere.pk}-{self.w.niveau.pk}')
        self.assertEqual(groupe['libelle'], f'{self.a.annee.libelle} / {self.a.filiere.libelle} / {self.w.niveau.libelle}')

    def test_regroupement_inconnu(self):
        self.assertEqual(self.get(self.a.admin, regroupement='pays').status_code, 400)

    def test_filtre(self):
        res = self.get(self.a.admin, regroupement='classe', ec=str(self.a.ec.pk))
        self.assertEqual(res.data['total']['nb_evaluations'], 1)

    def test_evaluations_d_un_groupe(self):
        res = self.get(self.a.admin, 'evaluations/', regroupement='ec', groupe=str(self.a.ec.pk))
        self.assertEqual(res.status_code, 200, res.data)
        evaluation, = res.data
        self.assertEqual((evaluation['quiz'], evaluation['titre'], evaluation['ec_libelle']),
                         (self.quiz.pk, self.quiz.titre, 'Python'))
        self.assertEqual((evaluation['absents'], evaluation['retards']), (1, 1))
        tous = self.get(self.a.admin, 'evaluations/', regroupement='classe')
        self.assertEqual([e['titre'] for e in tous.data], ['Quiz A', 'Quiz A2'])

    def test_absences(self):
        res = self.get(self.a.admin, 'absences/', quiz=str(self.quiz.pk))
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data['delai_retard_minutes'], 15)
        self.assertEqual(res.data['absents'], [{'id': self.etu2.pk, 'nom': 'Bea Diallo', 'classes': [self.a.classe.code]}])
        retard, = res.data['retards']
        self.assertEqual((retard['id'], retard['minutes']), (self.a.etu.pk, 30))

    def test_absences_parametres(self):
        self.assertEqual(self.get(self.a.admin, 'absences/').status_code, 400)
        self.assertEqual(self.get(self.a.admin, 'absences/', quiz='abc').status_code, 400)
        self.assertEqual(self.get(self.w.b.admin, 'absences/', quiz=str(self.quiz.pk)).status_code, 404)

    def test_droits(self):
        self.assertEqual(self.get(self.a.etu, regroupement='classe').status_code, 403)
        self.assertEqual(self.get(self.a.etu, 'absences/', quiz=str(self.quiz.pk)).status_code, 403)
        autre = make_user('ens2', 'enseignant', self.a.etab)
        self.assertEqual(self.get(autre, regroupement='classe').data['total']['nb_evaluations'], 0)
        self.assertEqual(self.get(autre, 'absences/', quiz=str(self.quiz.pk)).status_code, 404)
        self.assertEqual(self.get(self.a.ens, regroupement='classe').data['total']['nb_evaluations'], 2)
        self.assertEqual(self.get(self.w.b.admin, regroupement='classe').data['total']['nb_evaluations'], 1)
