import json

from django.core.cache import cache
from django.test import TestCase

from accounts.testing import build_world, client_for
from audit.models import AuditLog
from quiz.acces import ALPHABET_CODE

Q = '/api/quiz/quizzes'


class CodeAccesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def setUp(self):
        cache.clear()
        self.a = self.w.a
        self.quiz = self.a.quiz
        self.ens = client_for(self.a.ens)
        self.etu = client_for(self.a.etu)

    def generer(self):
        res = self.ens.post(f'{Q}/{self.quiz.id}/code_acces/')
        self.assertEqual(res.status_code, 200)
        return res.data['code_acces']

    def demarrer(self, corps=None):
        return self.etu.post(f'{Q}/{self.quiz.id}/demarrer/', corps if corps is not None else {}, format='json')

    def test_generation(self):
        code = self.generer()
        self.assertEqual(len(code), 6)
        self.assertTrue(all(c in ALPHABET_CODE for c in code))
        self.quiz.refresh_from_db()
        self.assertEqual(self.quiz.code_acces, code)
        log = AuditLog.objects.get(action='code_acces_quiz')
        self.assertEqual(log.details, {'action': 'genere'})
        self.assertNotIn(code, json.dumps(log.details))

    def test_regeneration(self):
        premier = self.generer()
        second = self.generer()
        self.quiz.refresh_from_db()
        self.assertEqual(self.quiz.code_acces, second)
        self.assertEqual(AuditLog.objects.filter(action='code_acces_quiz').count(), 2)
        self.assertEqual(len(premier), 6)

    def test_retrait(self):
        self.generer()
        res = self.ens.delete(f'{Q}/{self.quiz.id}/code_acces/')
        self.assertEqual(res.status_code, 204)
        self.quiz.refresh_from_db()
        self.assertEqual(self.quiz.code_acces, '')
        self.assertTrue(AuditLog.objects.filter(action='code_acces_quiz', details={'action': 'retire'}).exists())

    def test_droits(self):
        self.assertEqual(self.etu.post(f'{Q}/{self.quiz.id}/code_acces/').status_code, 403)
        self.assertEqual(client_for(self.w.b.ens).post(f'{Q}/{self.quiz.id}/code_acces/').status_code, 404)
        self.assertEqual(client_for(self.a.admin).post(f'{Q}/{self.quiz.id}/code_acces/').status_code, 200)

    def test_demarrage_avec_code(self):
        code = self.generer()
        res = self.demarrer()
        self.assertEqual(res.status_code, 400)
        self.assertIn("demande un code", json.dumps(res.data, ensure_ascii=False))
        res = self.demarrer({'code': 'ZZZZZZ' if code != 'ZZZZZZ' else 'YYYYYY'})
        self.assertEqual(res.status_code, 400)
        self.assertIn('incorrect', json.dumps(res.data, ensure_ascii=False))
        self.assertEqual(self.demarrer({'code': f' {code[:3].lower()} {code[3:].lower()} '}).status_code, 201)

    def test_corps_invalides(self):
        self.generer()
        for corps in ([1], 'abc', {'code': 5}, {'code': ['A']}, {'code': 'éééééé'}):
            with self.subTest(corps=corps):
                self.assertEqual(self.demarrer(corps).status_code, 400)

    def test_code_avec_substitut_unicode(self):
        self.generer()
        corps = b'{"code": "' + bytes([92]) + b'ud800"}'
        res = self.etu.post(f'{Q}/{self.quiz.id}/demarrer/', corps, content_type='application/json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('incorrect', json.dumps(res.data, ensure_ascii=False))
        self.assertEqual(self.etu.post(f'{Q}/{self.quiz.id}/demarrer/', b'{"code": "'+bytes([92])+b'ud800"}',
                                       content_type='application/json').status_code, 400)

    def test_reprise_sans_code(self):
        code = self.generer()
        premiere = self.demarrer({'code': code})
        self.assertEqual(premiere.status_code, 201)
        reprise = self.demarrer()
        self.assertEqual(reprise.status_code, 200)
        self.assertEqual(reprise.data['id'], premiere.data['id'])

    def test_reprise_interdite_redemande_le_code(self):
        self.quiz.reprise_autorisee = False
        self.quiz.tentatives_autorisees = 2
        self.quiz.save()
        code = self.generer()
        self.assertEqual(self.demarrer({'code': code}).status_code, 201)
        self.assertEqual(self.demarrer().status_code, 400)

    def test_limite_d_essais(self):
        code = self.generer()
        for _ in range(10):
            self.assertEqual(self.demarrer({'code': 'MAUVAIS'}).status_code, 400)
        res = self.demarrer({'code': code})
        self.assertEqual(res.status_code, 429)
        self.assertIn("Trop d'essais", json.dumps(res.data, ensure_ascii=False))
        self.assertEqual(AuditLog.objects.filter(action='echec_code_acces').count(), 1)

    def test_code_absent_de_la_vue_etudiant(self):
        code = self.generer()
        res = self.etu.get(f'{Q}/{self.quiz.id}/')
        self.assertTrue(res.data['code_requis'])
        self.assertNotIn(code, json.dumps(res.data, default=str))
        self.ens.delete(f'{Q}/{self.quiz.id}/code_acces/')
        self.assertFalse(self.etu.get(f'{Q}/{self.quiz.id}/').data['code_requis'])

    def test_quiz_sans_code(self):
        self.assertEqual(self.demarrer().status_code, 201)
