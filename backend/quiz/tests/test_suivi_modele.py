from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.testing import build_world, client_for
from audit.models import AuditLog
from quiz import fenetres
from quiz.models import SessionQuiz
from referentiel.models import EC, UE

Q = '/api/quiz'
R = '/api/referentiel'


class MatiereQuizTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def test_enseignant_choisit_une_matiere_enseignee(self):
        a = self.w.a
        res = client_for(a.ens).patch(f'{Q}/quizzes/{a.quiz.id}/', {'ec': a.ec.id}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data['ec'], a.ec.id)
        self.assertEqual(res.data['ec_libelle'], 'Python')

    def test_matiere_non_enseignee_refusee(self):
        a = self.w.a
        autre = EC.objects.create(code='ECX', libelle='Réseaux', ue=a.ue)
        res = client_for(a.ens).patch(f'{Q}/quizzes/{a.quiz.id}/', {'ec': autre.id}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_matiere_d_un_autre_etablissement_refusee_a_la_gestion(self):
        a, b = self.w.a, self.w.b
        res = client_for(a.admin).patch(f'{Q}/quizzes/{a.quiz.id}/', {'ec': b.ec.id}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_matiere_facultative(self):
        a = self.w.a
        res = client_for(a.ens).patch(f'{Q}/quizzes/{a.quiz.id}/', {'ec': None}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertIsNone(res.data['ec_libelle'])


class DelaiRetardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def url(self, etab):
        return f'{R}/etablissements/{etab.id}/parametres/'

    def test_valeur_par_defaut(self):
        self.assertEqual(self.w.a.etab.delai_retard_minutes, 15)

    def test_admin_modifie_le_delai(self):
        a = self.w.a
        res = client_for(a.admin).patch(self.url(a.etab), {'delai_retard_minutes': 30}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data['delai_retard_minutes'], 30)
        a.etab.refresh_from_db()
        self.assertEqual(a.etab.delai_retard_minutes, 30)
        self.assertFalse(a.etab.validation_quiz_requise)
        log = AuditLog.objects.filter(action='parametres_etablissement').latest('id')
        self.assertEqual(log.details, {'delai_retard_minutes': 30})

    def test_les_deux_reglages_ensemble(self):
        a = self.w.a
        res = client_for(a.admin).patch(self.url(a.etab), {'delai_retard_minutes': 0, 'validation_quiz_requise': True},
                                        format='json')
        self.assertEqual(res.status_code, 200, res.data)
        a.etab.refresh_from_db()
        self.assertEqual((a.etab.delai_retard_minutes, a.etab.validation_quiz_requise), (0, True))

    def test_valeurs_invalides(self):
        a = self.w.a
        for valeur in (-1, 241, 'abc', True, 12.5, None):
            with self.subTest(valeur=valeur):
                res = client_for(a.admin).patch(self.url(a.etab), {'delai_retard_minutes': valeur}, format='json')
                self.assertEqual(res.status_code, 400)
        res = client_for(a.admin).patch(self.url(a.etab), {}, format='json')
        self.assertEqual(res.status_code, 400)
        a.etab.refresh_from_db()
        self.assertEqual(a.etab.delai_retard_minutes, 15)

    def test_lecture_seule_hors_action(self):
        a = self.w.a
        client_for(self.w.superadmin).patch(f'{R}/etablissements/{a.etab.id}/', {'delai_retard_minutes': 50}, format='json')
        a.etab.refresh_from_db()
        self.assertEqual(a.etab.delai_retard_minutes, 15)

    def test_droits(self):
        a, b = self.w.a, self.w.b
        self.assertEqual(client_for(a.resp).patch(self.url(a.etab), {'delai_retard_minutes': 5}, format='json').status_code, 403)
        self.assertEqual(client_for(a.admin).patch(self.url(b.etab), {'delai_retard_minutes': 5}, format='json').status_code, 404)


class ConstruireTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def test_construire_equivaut_a_fenetre(self):
        a = self.w.a
        maintenant = timezone.now()
        normale = SessionQuiz.objects.create(quiz=a.quiz, ouverture=maintenant - timedelta(hours=1),
                                             fermeture=maintenant + timedelta(hours=1))
        normale.classes.add(a.classe)
        rattrapage = SessionQuiz.objects.create(quiz=a.quiz, type=SessionQuiz.RATTRAPAGE,
                                                ouverture=maintenant + timedelta(days=1),
                                                fermeture=maintenant + timedelta(days=2), tentatives_supplementaires=2)
        rattrapage.etudiants.add(a.etu)
        attendu = fenetres.fenetre(a.quiz, a.etu, maintenant)
        obtenu = fenetres.construire(a.quiz, [normale], [rattrapage], maintenant)
        self.assertEqual(obtenu, attendu)
        self.assertTrue(obtenu.rattrapage_a_venir)

    def test_sans_session_fenetre_generale(self):
        a = self.w.a
        maintenant = timezone.now()
        f = fenetres.construire(a.quiz, [], [], maintenant)
        self.assertEqual(f.intervalles, [(a.quiz.date_debut, a.quiz.date_fin)])
        self.assertEqual(f.tentatives_max, a.quiz.tentatives_autorisees)
