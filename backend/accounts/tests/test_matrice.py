from django.test import TestCase

from accounts.testing import build_world, client_for

TOUS = {'superadmin', 'admin', 'responsable_formation', 'enseignant', 'etudiant'}
GESTION = {'superadmin', 'admin', 'responsable_formation'}
CREATEURS = GESTION | {'enseignant'}

LECTURE = {
    '/api/quiz/quizzes/statistiques/': CREATEURS,
    '/api/referentiel/etablissements/': GESTION,
    '/api/referentiel/annees-academiques/': TOUS,
    '/api/referentiel/filieres/': TOUS,
    '/api/referentiel/niveaux/': TOUS,
    '/api/referentiel/ues/': TOUS,
    '/api/referentiel/ecs/': TOUS,
    '/api/referentiel/cours/': TOUS,
    '/api/referentiel/classes/': TOUS,
    '/api/referentiel/groupes/': TOUS,
    '/api/referentiel/inscriptions/': TOUS,
    '/api/referentiel/enseignants-matieres/': CREATEURS,
    '/api/accounts/users/': TOUS,
    '/api/quiz/quizzes/': TOUS,
    '/api/quiz/questions/': CREATEURS,
    '/api/quiz/choix/': CREATEURS,
    '/api/quiz/tentatives/': {'etudiant'},
    '/api/quiz/reponses/': CREATEURS,
    '/api/quiz/banque/': CREATEURS,
    '/api/programming/devoirs/': TOUS,
    '/api/programming/soumissions/': TOUS,
    '/api/programming/notes/': TOUS,
    '/api/audit/': {'superadmin', 'admin'},
}

ECRITURE = {
    '/api/referentiel/etablissements/': {'superadmin'},
    '/api/referentiel/annees-academiques/': GESTION,
    '/api/referentiel/filieres/': GESTION,
    '/api/referentiel/niveaux/': {'superadmin'},
    '/api/referentiel/ues/': GESTION,
    '/api/referentiel/ecs/': GESTION,
    '/api/referentiel/cours/': GESTION,
    '/api/referentiel/classes/': GESTION,
    '/api/referentiel/groupes/': GESTION,
    '/api/referentiel/inscriptions/': GESTION,
    '/api/referentiel/enseignants-matieres/': GESTION,
    '/api/accounts/users/': {'superadmin'},
    '/api/quiz/quizzes/': CREATEURS,
    '/api/quiz/questions/': CREATEURS,
    '/api/quiz/choix/': CREATEURS,
    '/api/quiz/tentatives/': {'etudiant'},
    '/api/quiz/reponses/': CREATEURS,
    '/api/quiz/banque/': CREATEURS,
    '/api/programming/devoirs/': CREATEURS,
    '/api/programming/soumissions/': {'etudiant'},
    '/api/programming/notes/': CREATEURS,
}


class MatriceDesDroitsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        w = build_world()
        cls.utilisateurs = [w.superadmin, w.a.admin, w.a.resp, w.a.ens, w.a.etu]

    def test_lecture(self):
        for url, autorises in LECTURE.items():
            for user in self.utilisateurs:
                with self.subTest(url=url, role=user.role):
                    status = client_for(user).get(url).status_code
                    self.assertEqual(status, 200 if user.role in autorises else 403)

    def test_ecriture(self):
        for url, autorises in ECRITURE.items():
            for user in self.utilisateurs:
                with self.subTest(url=url, role=user.role):
                    status = client_for(user).post(url, {}, format='json').status_code
                    if user.role in autorises:
                        self.assertNotEqual(status, 403)
                    else:
                        self.assertEqual(status, 403)
