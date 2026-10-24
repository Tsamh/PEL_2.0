from django.test import TestCase

from accounts.testing import build_world, client_for, make_user
from quiz.models import QuestionBanque
from referentiel.models import EnseignantMatiere

B = '/api/quiz/banque'
Q = '/api/quiz/quizzes'

CONTENU = {
    'texte': 'Capitale de la France ?', 'type_question': 'qcm', 'points': '2', 'mode_notation': 'tout_ou_rien',
    'penalite': '0.5', 'explication': 'Paris.',
    'choix': [{'texte': 'Paris', 'est_correct': True, 'points': '0'}, {'texte': 'Lyon', 'est_correct': False, 'points': '0'}],
}


def question_depuis(version, **extra):
    q = {cle: version[cle] for cle in ('texte', 'type_question', 'points', 'mode_notation', 'penalite', 'explication')}
    q['choix'] = [dict(c, ordre=i + 1) for i, c in enumerate(version['choix'])]
    q['source'] = version['id']
    q.update(extra)
    return q


class BanqueEtQuizTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def setUp(self):
        self.a = self.w.a
        self.quiz = self.a.quiz
        self.ens = client_for(self.a.ens)
        res = self.ens.post(f'{B}/', {'ec': self.a.ec.id, 'contenu': CONTENU}, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        self.fiche = res.data

    def enregistrer(self, questions, client=None):
        return (client or self.ens).patch(f'{Q}/{self.quiz.id}/', {'questions': questions}, format='json')

    def question_lue(self):
        return self.ens.get(f'{Q}/{self.quiz.id}/').data['questions'][0]

    def test_source_conservee_et_version_recalculee(self):
        res = self.enregistrer([question_depuis(self.fiche['version'], version_source=99)])
        self.assertEqual(res.status_code, 200, res.data)
        question = self.quiz.questions.get()
        self.assertEqual(question.source_id, self.fiche['version']['id'])
        self.assertEqual(question.version_source, 1)
        lue = self.question_lue()
        self.assertEqual(lue['fiche_source'], self.fiche['id'])
        self.assertEqual(lue['version_source'], 1)
        self.assertEqual(lue['version_courante'], 1)
        self.assertFalse(lue['modifiee_localement'])
        self.assertEqual(lue['penalite'], '0.50')

    def test_nouvelle_version_et_modification_locale(self):
        self.enregistrer([question_depuis(self.fiche['version'])])
        self.ens.patch(f"{B}/{self.fiche['id']}/", {'contenu': dict(CONTENU, texte='Capitale ?')}, format='json')
        lue = self.question_lue()
        self.assertEqual(lue['version_courante'], 2)
        self.assertEqual(lue['version_source'], 1)
        self.enregistrer([question_depuis(self.fiche['version'], texte='Texte retouché')])
        self.assertTrue(self.question_lue()['modifiee_localement'])

    def test_source_invisible_refusee(self):
        res = client_for(self.w.b.ens).post(f'{B}/', {'contenu': CONTENU}, format='json')
        version_b = res.data['version']
        res = self.enregistrer([question_depuis(version_b)])
        self.assertEqual(res.status_code, 400)
        self.assertIn('questions', res.data)
        self.assertEqual(self.enregistrer([question_depuis(self.fiche['version'], source=999999)]).status_code, 400)

    def test_source_partagee_acceptee(self):
        collegue = make_user('collegue', 'enseignant', self.a.etab)
        EnseignantMatiere.objects.create(enseignant=collegue, ec=self.a.ec, classe=self.a.classe)
        res = client_for(collegue).post(f'{B}/', {'ec': self.a.ec.id, 'partagee': True, 'contenu': CONTENU}, format='json')
        self.assertEqual(self.enregistrer([question_depuis(res.data['version'])]).status_code, 200)

    def test_sans_source(self):
        question = question_depuis(self.fiche['version'], source=None)
        self.assertEqual(self.enregistrer([question]).status_code, 200)
        lue = self.question_lue()
        self.assertIsNone(lue['fiche_source'])
        self.assertIsNone(lue['version_courante'])
        self.assertFalse(lue['modifiee_localement'])

    def test_fiche_supprimee(self):
        self.enregistrer([question_depuis(self.fiche['version'])])
        QuestionBanque.objects.filter(pk=self.fiche['id']).delete()
        question = self.quiz.questions.get()
        self.assertIsNone(question.source)
        self.assertEqual(question.texte, 'Capitale de la France ?')


class BanqueEtQuizCorrectionsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    setUp = BanqueEtQuizTests.setUp
    enregistrer = BanqueEtQuizTests.enregistrer

    def test_api_questions_ne_ecrit_pas_la_source(self):
        res = client_for(self.w.b.ens).post(f'{B}/', {'contenu': CONTENU}, format='json')
        version_b = res.data['version']
        self.enregistrer([question_depuis(self.fiche['version'], source=None)])
        question = self.quiz.questions.get()
        res = self.ens.patch(f'/api/quiz/questions/{question.id}/',
                             {'source': version_b['id'], 'version_source': 42}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        question.refresh_from_db()
        self.assertIsNone(question.source_id)
        self.assertIsNone(question.version_source)

    def test_api_questions_valide_la_penalite(self):
        self.enregistrer([question_depuis(self.fiche['version'])])
        question = self.quiz.questions.get()
        url = f'/api/quiz/questions/{question.id}/'
        self.assertEqual(self.ens.patch(url, {'penalite': '50'}, format='json').status_code, 400)
        self.assertEqual(self.ens.patch(url, {'penalite': '1'}, format='json').status_code, 200)
        self.assertEqual(
            self.ens.patch(url, {'type_question': 'court', 'penalite': '1'}, format='json').status_code, 400)

    def test_source_devenue_invisible_conservee(self):
        collegue = make_user('collegue2', 'enseignant', self.a.etab)
        EnseignantMatiere.objects.create(enseignant=collegue, ec=self.a.ec, classe=self.a.classe)
        cc = client_for(collegue)
        res = cc.post(f'{B}/', {'ec': self.a.ec.id, 'partagee': True, 'contenu': CONTENU}, format='json')
        version = res.data['version']
        self.assertEqual(self.enregistrer([question_depuis(version)]).status_code, 200)
        cc.patch(f"{B}/{res.data['id']}/", {'partagee': False}, format='json')
        res2 = self.enregistrer([question_depuis(version, id=self.quiz.questions.get().id)])
        self.assertEqual(res2.status_code, 200, res2.data)
        self.assertEqual(self.quiz.questions.get().source_id, version['id'])
        # une source invisible jamais utilisee dans ce quiz reste refusee
        autre = client_for(self.w.b.ens).post(f'{B}/', {'contenu': CONTENU}, format='json')
        self.assertEqual(self.enregistrer([question_depuis(autre.data['version'])]).status_code, 400)
