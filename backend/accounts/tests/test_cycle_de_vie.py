from django.contrib.auth import get_user_model
from django.test import TestCase

from accounts.testing import build_world, client_for, make_user
from audit.models import AuditLog
from referentiel.models import AffectationEnseignant, Inscription

User = get_user_model()


class DesactivationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def post(self, acteur, cible, verbe='deactivate'):
        return client_for(acteur).post(f'/api/accounts/users/{cible.id}/{verbe}/')

    def test_admin_desactive_puis_reactive_un_etudiant(self):
        a = self.w.a
        self.assertEqual(self.post(a.admin, a.etu).status_code, 200)
        a.etu.refresh_from_db()
        self.assertFalse(a.etu.is_active)
        self.assertEqual(self.post(a.admin, a.etu, 'reactivate').status_code, 200)
        a.etu.refresh_from_db()
        self.assertTrue(a.etu.is_active)
        self.assertEqual(
            list(AuditLog.objects.order_by('id').values_list('action', flat=True)),
            ['desactivation', 'reactivation'],
        )

    def test_gardes_fous(self):
        a, b = self.w.a, self.w.b
        autre_admin = make_user('admin2A', 'admin', a.etab)
        cas = [
            (a.admin, a.admin, 400),
            (a.admin, autre_admin, 403),
            (a.admin, b.etu, 404),
            (a.resp, a.etu, 403),
            (a.ens, a.etu, 403),
            (self.w.superadmin, b.admin, 400),
        ]
        for acteur, cible, attendu in cas:
            with self.subTest(acteur=acteur.username, cible=cible.username):
                self.assertEqual(self.post(acteur, cible).status_code, attendu)

    def test_superadmin_desactive_un_admin_s_il_en_reste_un(self):
        a = self.w.a
        make_user('admin2A', 'admin', a.etab)
        self.assertEqual(self.post(self.w.superadmin, a.admin).status_code, 200)


class InvitationResponsableTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def payload(self, **extra):
        return {'email': 'nouveau.resp@test.pel', 'first_name': 'Fatou', 'last_name': 'Diop', **extra}

    def test_admin_invite_un_responsable(self):
        a = self.w.a
        res = client_for(a.admin).post('/api/accounts/users/invite_responsable/', self.payload(), format='json')
        self.assertEqual(res.status_code, 201)
        resp = User.objects.get(email='nouveau.resp@test.pel')
        self.assertEqual(resp.role, 'responsable_formation')
        self.assertEqual(resp.etablissement, a.etab)
        self.assertTrue(resp.is_invited)
        self.assertIsNotNone(resp.invitation_token)
        self.assertTrue(AuditLog.objects.filter(action='invitation', cible_id=str(resp.id)).exists())

    def test_etablissement_impose_pour_l_admin(self):
        res = client_for(self.w.a.admin).post(
            '/api/accounts/users/invite_responsable/', self.payload(etablissement=self.w.b.etab.id), format='json')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(User.objects.get(email='nouveau.resp@test.pel').etablissement, self.w.a.etab)

    def test_superadmin_doit_preciser_l_etablissement(self):
        client = client_for(self.w.superadmin)
        self.assertEqual(client.post('/api/accounts/users/invite_responsable/', self.payload(), format='json').status_code, 400)
        res = client.post('/api/accounts/users/invite_responsable/', self.payload(etablissement=self.w.b.etab.id), format='json')
        self.assertEqual(res.status_code, 201)

    def test_responsable_et_enseignant_refuses(self):
        for user in (self.w.a.resp, self.w.a.ens):
            with self.subTest(role=user.role):
                res = client_for(user).post('/api/accounts/users/invite_responsable/', self.payload(), format='json')
                self.assertEqual(res.status_code, 403)

    def test_email_deja_utilise(self):
        res = client_for(self.w.a.admin).post(
            '/api/accounts/users/invite_responsable/', self.payload(email='etuA@test.pel'), format='json')
        self.assertEqual(res.status_code, 400)


class InvitationsEtAffectationsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def test_responsable_invite_un_etudiant_dans_sa_classe(self):
        a = self.w.a
        res = client_for(a.resp).post('/api/accounts/users/invite_student/', {
            'email': 'nouvel.etu@test.pel', 'first_name': 'Moussa', 'last_name': 'Ba', 'classe': a.classe.id,
        }, format='json')
        self.assertEqual(res.status_code, 201)
        etu = User.objects.get(email='nouvel.etu@test.pel')
        self.assertEqual(etu.etablissement, a.etab)
        self.assertTrue(Inscription.objects.filter(etudiant=etu, classe=a.classe).exists())
        actions = set(AuditLog.objects.filter(cible_id__in=[str(etu.id)]).values_list('action', flat=True))
        self.assertIn('invitation', actions)
        self.assertTrue(AuditLog.objects.filter(action='inscription').exists())

    def test_classe_d_un_autre_etablissement_refusee_sans_creation(self):
        res = client_for(self.w.a.admin).post('/api/accounts/users/invite_student/', {
            'email': 'intrus@test.pel', 'first_name': 'I', 'last_name': 'I', 'classe': self.w.b.classe.id,
        }, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertFalse(User.objects.filter(email='intrus@test.pel').exists())

    def test_responsable_ne_peut_pas_inviter_d_enseignant(self):
        res = client_for(self.w.a.resp).post('/api/accounts/users/invite_enseignant/', {
            'email': 'prof@test.pel', 'first_name': 'P', 'last_name': 'P',
        }, format='json')
        self.assertEqual(res.status_code, 403)

    def test_update_classes_ignore_les_classes_hors_perimetre(self):
        a, b = self.w.a, self.w.b
        res = client_for(a.resp).post(
            f'/api/accounts/users/{a.ens.id}/update_classes/', {'classes': [a.classe.id, b.classe.id]}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            set(AffectationEnseignant.objects.filter(enseignant=a.ens).values_list('classe_id', flat=True)),
            {a.classe.id},
        )
        self.assertTrue(AuditLog.objects.filter(action='affectation', cible_id=str(a.ens.id)).exists())

    def test_validation_admin_journalisee(self):
        candidat = make_user('candidat', 'admin', self.w.a.etab, validation_status='pending', is_validated=False)
        res = client_for(self.w.superadmin).post('/api/accounts/users/validate_admin/', {
            'user_id': candidat.id, 'action': 'reject', 'rejection_reason': 'Doublon',
        }, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(AuditLog.objects.filter(action='rejet_admin', cible_id=str(candidat.id)).exists())
