from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.testing import build_world, client_for, make_user
from audit.models import AuditLog
from quiz.models import SessionQuiz
from referentiel.models import Classe, Groupe, Inscription, PeriodeEvaluation, Semestre

S = '/api/quiz/sessions-quiz'


def iso(dt):
    return dt.isoformat()


class SessionsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def setUp(self):
        self.a = self.w.a
        self.quiz = self.a.quiz
        self.ens = client_for(self.a.ens)
        self.maintenant = timezone.now()
        self.groupe = Groupe.objects.create(code='TD1A', libelle='TD 1', classe=self.a.classe)
        self.classe_hors = Classe.objects.create(code='L1Z', libelle='L1 Z', filiere=self.a.filiere,
                                                 niveau=self.w.niveau, annee_academique=self.a.annee)
        self.etu_hors = make_user('etuhors', 'etudiant', self.a.etab)
        Inscription.objects.create(etudiant=self.etu_hors, classe=self.classe_hors)

    def corps(self, **extra):
        donnees = {'quiz': self.quiz.id, 'type': 'normale', 'libelle': 'Lundi',
                   'ouverture': iso(self.maintenant + timedelta(days=1)),
                   'fermeture': iso(self.maintenant + timedelta(days=1, hours=2)), 'classes': [self.a.classe.id]}
        donnees.update(extra)
        return donnees

    def creer(self, client=None, **extra):
        return (client or self.ens).post(f'{S}/', self.corps(**extra), format='json')

    def test_session_normale(self):
        res = self.creer()
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data['quiz_titre'], self.quiz.titre)
        self.assertEqual(res.data['classes_detail'][0]['code'], 'L1A')
        session = SessionQuiz.objects.get(pk=res.data['id'])
        self.assertEqual(session.cree_par, self.a.ens)
        self.assertTrue(AuditLog.objects.filter(action='session_quiz', details__action='creation').exists())
        self.assertEqual(self.creer(classes=[], groupes=[self.groupe.id]).status_code, 201)

    def test_cibles_normales_controlees(self):
        for extra, cle in (
            ({'classes': [self.classe_hors.id]}, 'classes'),
            ({'classes': []}, 'classes'),
            ({'etudiants': [self.a.etu.id]}, 'etudiants'),
            ({'fermeture': iso(self.maintenant)}, 'fermeture'),
        ):
            with self.subTest(extra=extra):
                res = self.creer(**extra)
                self.assertEqual(res.status_code, 400)
                self.assertIn(cle, res.data)
        groupe_hors = Groupe.objects.create(code='TD1Z', libelle='TD Z', classe=self.classe_hors)
        self.assertEqual(self.creer(classes=[], groupes=[groupe_hors.id]).status_code, 400)

    def test_rattrapage(self):
        res = self.creer(type='rattrapage', classes=[], etudiants=[self.a.etu.id], tentatives_supplementaires=2)
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data['nb_etudiants'], 1)
        for extra in (
            {'etudiants': [self.etu_hors.id]},
            {'etudiants': []},
            {'etudiants': [self.a.etu.id], 'classes': [self.a.classe.id]},
            {'etudiants': [self.a.etu.id], 'tentatives_supplementaires': 11},
            {'etudiants': [self.a.etu.id], 'tentatives_supplementaires': -1},
        ):
            with self.subTest(extra=extra):
                corps = {'type': 'rattrapage', 'classes': [], **extra}
                self.assertEqual(self.creer(**corps).status_code, 400)

    def test_periode(self):
        jour = timezone.localtime(self.maintenant + timedelta(days=1)).date()
        semestre = Semestre.objects.create(annee_academique=self.a.annee, libelle='S1',
                                           date_debut=jour - timedelta(days=30), date_fin=jour + timedelta(days=30))
        periode = PeriodeEvaluation.objects.create(semestre=semestre, libelle='CC', date_debut=jour, date_fin=jour)
        self.assertEqual(self.creer(periode=periode.id).status_code, 201)
        trop_tard = iso(self.maintenant + timedelta(days=3))
        self.assertEqual(self.creer(periode=periode.id, fermeture=trop_tard).status_code, 400)
        sb = Semestre.objects.create(annee_academique=self.w.b.annee, libelle='S1',
                                     date_debut=jour - timedelta(days=30), date_fin=jour + timedelta(days=30))
        pb = PeriodeEvaluation.objects.create(semestre=sb, libelle='CCB', date_debut=jour, date_fin=jour)
        self.assertEqual(self.creer(periode=pb.id).status_code, 400)

    def test_droits(self):
        session_id = self.creer().data['id']
        res = self.creer(client=client_for(self.w.b.ens))
        self.assertEqual(res.status_code, 400)
        self.assertIn('quiz', res.data)
        self.assertEqual(client_for(self.w.b.ens).get(f'{S}/{session_id}/').status_code, 404)
        self.assertEqual(client_for(self.w.b.admin).get(f'{S}/{session_id}/').status_code, 404)
        self.assertEqual(client_for(self.a.etu).get(f'{S}/').status_code, 403)
        self.assertEqual(self.creer(client=client_for(self.a.admin)).status_code, 201)

    def test_filtres_modification_suppression(self):
        future = self.creer().data['id']
        passee = self.creer(ouverture=iso(self.maintenant - timedelta(days=3)),
                            fermeture=iso(self.maintenant - timedelta(days=2))).data['id']
        ids = lambda q: {s['id'] for s in self.ens.get(f'{S}/?{q}').data['results']}
        self.assertEqual(ids(f'quiz={self.quiz.id}'), {future, passee})
        self.assertEqual(ids('a_venir=1'), {future})
        self.assertEqual(ids('quiz=abc&periode=99999999999999999999999'), {future, passee})
        res = self.ens.patch(f'{S}/{future}/', {'libelle': 'Mardi'}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(AuditLog.objects.filter(action='session_quiz', details__action='modification').exists())
        autre_quiz = self.w.b.quiz
        self.assertEqual(self.ens.patch(f'{S}/{future}/', {'quiz': autre_quiz.id}, format='json').status_code, 400)
        self.assertEqual(self.ens.delete(f'{S}/{future}/').status_code, 204)
        self.assertTrue(AuditLog.objects.filter(action='session_quiz', details__action='suppression').exists())
