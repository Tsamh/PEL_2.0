from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from accounts.testing import build_world, PASSWORD
from audit.models import AuditLog


class ConnexionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def login(self, identifiant, password=PASSWORD):
        return APIClient().post('/api/accounts/login/', {'login': identifiant, 'password': password}, format='json')

    def test_succes_journalise(self):
        res = self.login('etuA')
        self.assertEqual(res.status_code, 200)
        entree = AuditLog.objects.get(action='login_succes')
        self.assertEqual(entree.acteur, self.w.a.etu)
        self.assertEqual(entree.etablissement, self.w.a.etab)

    def test_connexion_par_email(self):
        self.assertEqual(self.login('etuA@test.pel').status_code, 200)

    def test_mauvais_mot_de_passe_journalise(self):
        res = self.login('etuA', 'faux')
        self.assertEqual(res.status_code, 401)
        entree = AuditLog.objects.get(action='login_echec')
        self.assertIsNone(entree.acteur)
        self.assertEqual(entree.details, {'login': 'etuA'})
        self.assertEqual(entree.cible_id, str(self.w.a.etu.pk))

    def test_identifiant_inconnu_renvoie_401(self):
        res = self.login('personne')
        self.assertEqual(res.status_code, 401)
        self.assertTrue(AuditLog.objects.filter(action='login_echec', cible_id='').exists())

    def test_compte_desactive_refuse(self):
        etu = self.w.a.etu
        etu.is_active = False
        etu.save()
        self.assertEqual(self.login('etuA').status_code, 401)

    def test_jeton_existant_refuse_apres_desactivation(self):
        etu = self.w.a.etu
        token = str(AccessToken.for_user(etu))
        etu.is_active = False
        etu.save()
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        self.assertEqual(client.get('/api/accounts/users/me/').status_code, 401)
