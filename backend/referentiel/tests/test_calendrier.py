from datetime import date

from django.test import TestCase

from accounts.testing import build_world, client_for
from referentiel.models import PeriodeEvaluation, Semestre

S = '/api/referentiel/semestres'
P = '/api/referentiel/periodes-evaluation'


class CalendrierTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def setUp(self):
        self.a = self.w.a
        self.admin = client_for(self.a.admin)

    def semestre(self, annee=None, libelle='S1', debut=date(2026, 10, 1), fin=date(2027, 2, 15)):
        return Semestre.objects.create(annee_academique=annee or self.a.annee, libelle=libelle, date_debut=debut, date_fin=fin)

    def test_creation(self):
        res = self.admin.post(f'{S}/', {'annee_academique': self.a.annee.id, 'libelle': 'S1',
                                        'date_debut': '2026-10-01', 'date_fin': '2027-02-15'}, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data['annee_libelle'], self.a.annee.libelle)
        res = self.admin.post(f'{P}/', {'semestre': res.data['id'], 'libelle': 'Examens S1', 'type': 'examen',
                                        'date_debut': '2027-01-10', 'date_fin': '2027-01-25'}, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual((res.data['semestre_libelle'], res.data['annee_academique']), ('S1', self.a.annee.id))
        self.assertEqual(client_for(self.a.resp).post(f'{S}/', {'annee_academique': self.a.annee.id, 'libelle': 'S2',
                                                               'date_debut': '2027-02-16', 'date_fin': '2027-07-31'},
                                                      format='json').status_code, 201)

    def test_dates_controlees(self):
        for corps in (
            {'libelle': 'S1', 'date_debut': '2026-09-01', 'date_fin': '2027-02-15'},
            {'libelle': 'S1', 'date_debut': '2026-10-01', 'date_fin': '2027-08-15'},
            {'libelle': 'S1', 'date_debut': '2027-02-15', 'date_fin': '2026-10-01'},
            {'libelle': 'S1', 'date_debut': 'pas une date', 'date_fin': '2027-02-15'},
        ):
            with self.subTest(corps=corps):
                res = self.admin.post(f'{S}/', {'annee_academique': self.a.annee.id, **corps}, format='json')
                self.assertEqual(res.status_code, 400)
        s1 = self.semestre()
        res = self.admin.post(f'{S}/', {'annee_academique': self.a.annee.id, 'libelle': 'S1',
                                        'date_debut': '2026-10-01', 'date_fin': '2027-02-15'}, format='json')
        self.assertEqual(res.status_code, 400)
        hors = self.admin.post(f'{P}/', {'semestre': s1.id, 'libelle': 'Hors', 'type': 'examen',
                                         'date_debut': '2027-03-01', 'date_fin': '2027-03-10'}, format='json')
        self.assertEqual(hors.status_code, 400)
        self.assertEqual(self.admin.post(f'{P}/', {'semestre': s1.id, 'libelle': 'X', 'type': 'inconnu',
                                                   'date_debut': '2026-11-01', 'date_fin': '2026-11-10'},
                                         format='json').status_code, 400)

    def test_modification_controle_les_dates(self):
        s1 = self.semestre()
        self.assertEqual(self.admin.patch(f'{S}/{s1.id}/', {'date_fin': '2027-09-01'}, format='json').status_code, 400)
        self.assertEqual(self.admin.patch(f'{S}/{s1.id}/', {'libelle': 'Semestre 1'}, format='json').status_code, 200)

    def test_droits_et_perimetre(self):
        s1 = self.semestre()
        sb = self.semestre(annee=self.w.b.annee, libelle='S1')
        self.assertEqual(client_for(self.a.ens).post(f'{S}/', {}, format='json').status_code, 403)
        self.assertEqual(client_for(self.a.etu).get(f'{S}/').status_code, 200)
        ids = {s['id'] for s in client_for(self.a.ens).get(f'{S}/').data['results']}
        self.assertEqual(ids, {s1.id})
        res = client_for(self.w.b.admin).post(f'{S}/', {'annee_academique': self.a.annee.id, 'libelle': 'S9',
                                                        'date_debut': '2026-10-01', 'date_fin': '2027-02-15'}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(client_for(self.w.b.admin).get(f'{S}/{s1.id}/').status_code, 404)
        res = client_for(self.w.b.admin).post(f'{P}/', {'semestre': s1.id, 'libelle': 'X', 'type': 'examen',
                                                        'date_debut': '2026-11-01', 'date_fin': '2026-11-10'}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertEqual({s['id'] for s in self.admin.get(f'{S}/?annee_academique={self.a.annee.id}').data['results']}, {s1.id})
        self.assertEqual(self.admin.get(f'{S}/?annee_academique=abc').status_code, 200)
        self.assertNotIn(sb.id, {s['id'] for s in self.admin.get(f'{S}/').data['results']})

    def test_filtres_des_periodes(self):
        s1 = self.semestre()
        s2 = self.semestre(libelle='S2', debut=date(2027, 2, 16), fin=date(2027, 7, 31))
        p1 = PeriodeEvaluation.objects.create(semestre=s1, libelle='CC1', date_debut=date(2026, 11, 1), date_fin=date(2026, 11, 15))
        p2 = PeriodeEvaluation.objects.create(semestre=s2, libelle='CC2', date_debut=date(2027, 3, 1), date_fin=date(2027, 3, 15))
        self.assertEqual({p['id'] for p in self.admin.get(f'{P}/?semestre={s1.id}').data['results']}, {p1.id})
        self.assertEqual({p['id'] for p in self.admin.get(f'{P}/?annee_academique={self.a.annee.id}').data['results']}, {p1.id, p2.id})

    def test_periode_d_un_quiz(self):
        s1 = self.semestre()
        p1 = PeriodeEvaluation.objects.create(semestre=s1, libelle='CC1', date_debut=date(2026, 11, 1), date_fin=date(2026, 11, 15))
        sb = self.semestre(annee=self.w.b.annee)
        pb = PeriodeEvaluation.objects.create(semestre=sb, libelle='CCB', date_debut=date(2026, 11, 1), date_fin=date(2026, 11, 15))
        ens = client_for(self.a.ens)
        res = ens.patch(f'/api/quiz/quizzes/{self.a.quiz.id}/', {'periode': p1.id}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data['periode_libelle'], 'CC1')
        self.assertEqual(ens.patch(f'/api/quiz/quizzes/{self.a.quiz.id}/', {'periode': pb.id}, format='json').status_code, 400)
        self.assertEqual(ens.patch(f'/api/quiz/quizzes/{self.a.quiz.id}/', {'periode': None}, format='json').status_code, 200)
