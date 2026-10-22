from django.test import TestCase

from accounts.testing import build_world, client_for, make_user
from audit.models import AuditLog
from programming.models import SoumissionDevoir


class ListeComptesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def ids(self, user, url='/api/accounts/users/'):
        res = client_for(user).get(url)
        self.assertEqual(res.status_code, 200)
        return {u['id'] for u in res.data['results']}

    def test_admin_voit_son_etablissement(self):
        a = self.w.a
        self.assertEqual(self.ids(a.admin), {a.admin.id, a.resp.id, a.ens.id, a.etu.id})

    def test_responsable_ne_voit_pas_les_admins(self):
        a = self.w.a
        self.assertEqual(self.ids(a.resp), {a.resp.id, a.ens.id, a.etu.id})

    def test_enseignant_voit_ses_etudiants(self):
        a = self.w.a
        self.assertEqual(self.ids(a.ens), {a.ens.id, a.etu.id})

    def test_filtre_role_et_classe_pour_enseignant(self):
        a = self.w.a
        url = f'/api/accounts/users/?role=etudiant&classe={a.classe.id}'
        self.assertEqual(self.ids(a.ens, url), {a.etu.id})

    def test_etudiant_se_voit_seul(self):
        self.assertEqual(self.ids(self.w.a.etu), {self.w.a.etu.id})

    def test_by_role_reserve_aux_gestionnaires(self):
        a = self.w.a
        self.assertEqual(client_for(a.resp).get('/api/accounts/users/by_role/?role=etudiant').status_code, 200)
        self.assertEqual(client_for(a.ens).get('/api/accounts/users/by_role/?role=etudiant').status_code, 403)
        self.assertEqual(client_for(a.etu).get('/api/accounts/users/by_role/?role=etudiant').status_code, 403)


class ModificationComptesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()
        cls.autre_admin_a = make_user('admin2A', 'admin', cls.w.a.etab)

    def patch(self, acteur, cible, data):
        return client_for(acteur).patch(f'/api/accounts/users/{cible.id}/', data, format='json')

    def test_admin_ne_peut_pas_promouvoir(self):
        a = self.w.a
        res = self.patch(a.admin, a.etu, {'role': 'superadmin', 'etablissement': self.w.b.etab.id, 'first_name': 'Awa'})
        self.assertEqual(res.status_code, 200)
        a.etu.refresh_from_db()
        self.assertEqual(a.etu.role, 'etudiant')
        self.assertEqual(a.etu.etablissement, a.etab)
        self.assertEqual(a.etu.first_name, 'Awa')

    def test_admin_ne_peut_pas_s_auto_promouvoir(self):
        a = self.w.a
        self.patch(a.admin, a.admin, {'role': 'superadmin'})
        a.admin.refresh_from_db()
        self.assertEqual(a.admin.role, 'admin')

    def test_is_active_non_modifiable_par_patch(self):
        a = self.w.a
        self.patch(a.admin, a.etu, {'is_active': False})
        a.etu.refresh_from_db()
        self.assertTrue(a.etu.is_active)

    def test_regles_de_gestion(self):
        a, b = self.w.a, self.w.b
        cas = [
            (a.resp, a.etu, 200),
            (a.resp, a.ens, 403),
            (a.admin, self.autre_admin_a, 403),
            (a.admin, b.etu, 404),
            (a.etu, a.etu, 403),
            (a.ens, a.etu, 403),
        ]
        for acteur, cible, attendu in cas:
            with self.subTest(acteur=acteur.username, cible=cible.username):
                self.assertEqual(self.patch(acteur, cible, {'first_name': 'X'}).status_code, attendu)


class CreationSuppressionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def test_creation_directe_reservee_au_superadmin(self):
        data = {'username': 'x', 'email': 'x@test.pel', 'password': 'Motdepasse!2026', 'role': 'admin'}
        self.assertEqual(client_for(self.w.a.admin).post('/api/accounts/users/', data).status_code, 403)

    def test_actions_d_invitation_fermees_aux_etudiants(self):
        res = client_for(self.w.a.etu).post('/api/accounts/users/invite_student/', {
            'email': 'pirate@test.pel', 'first_name': 'P', 'last_name': 'P',
        })
        self.assertEqual(res.status_code, 403)

    def test_suppression_reservee_au_superadmin(self):
        self.assertEqual(client_for(self.w.a.admin).delete(f'/api/accounts/users/{self.w.a.etu.id}/').status_code, 403)

    def test_suppression_refusee_si_historique(self):
        SoumissionDevoir.objects.create(devoir=self.w.a.devoir, etudiant=self.w.a.etu, code_soumis='print(4)')
        res = client_for(self.w.superadmin).delete(f'/api/accounts/users/{self.w.a.etu.id}/')
        self.assertEqual(res.status_code, 400)

    def test_suppression_sans_historique_journalisee(self):
        cible = make_user('etuSansHisto', 'etudiant', self.w.a.etab)
        res = client_for(self.w.superadmin).delete(f'/api/accounts/users/{cible.id}/')
        self.assertEqual(res.status_code, 204)
        entree = AuditLog.objects.get(action='suppression_compte')
        self.assertEqual(entree.cible_id, str(cible.id))
        self.assertEqual(entree.etablissement, self.w.a.etab)

    def test_suppression_du_dernier_admin_refusee(self):
        res = client_for(self.w.superadmin).delete(f'/api/accounts/users/{self.w.b.admin.id}/')
        self.assertEqual(res.status_code, 400)
