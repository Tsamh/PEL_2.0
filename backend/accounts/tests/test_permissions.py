from django.contrib.auth.models import AnonymousUser
from django.test import TestCase, RequestFactory

from accounts.permissions import (
    IsSuperAdmin, IsAdmin, IsGestionnaire, IsEnseignant, IsEtudiant,
    RolePermission, peut_gerer_compte, GESTION, ENSEIGNANT,
)
from accounts.testing import build_world, make_user


def requete(user, method='get'):
    request = getattr(RequestFactory(), method)('/')
    request.user = user
    return request


class ClassesDeRoleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def test_chaque_classe_accepte_exactement_ses_roles(self):
        w = self.w
        tous = [w.superadmin, w.a.admin, w.a.resp, w.a.ens, w.a.etu]
        attendu = {
            IsSuperAdmin: {w.superadmin},
            IsAdmin: {w.superadmin, w.a.admin},
            IsGestionnaire: {w.superadmin, w.a.admin, w.a.resp},
            IsEnseignant: {w.a.ens},
            IsEtudiant: {w.a.etu},
        }
        for permission, autorises in attendu.items():
            for user in tous:
                with self.subTest(permission=permission.__name__, role=user.role):
                    self.assertEqual(
                        permission().has_permission(requete(user), None),
                        user in autorises,
                    )

    def test_anonyme_refuse(self):
        self.assertFalse(IsGestionnaire().has_permission(requete(AnonymousUser()), None))

    def test_role_permission_distingue_lecture_et_ecriture(self):
        permission = RolePermission(read=GESTION + (ENSEIGNANT,), write=GESTION)()
        self.assertTrue(permission.has_permission(requete(self.w.a.ens, 'get'), None))
        self.assertFalse(permission.has_permission(requete(self.w.a.ens, 'post'), None))
        self.assertTrue(permission.has_permission(requete(self.w.a.resp, 'post'), None))
        self.assertFalse(permission.has_permission(requete(self.w.a.etu, 'get'), None))


class PeutGererCompteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()
        cls.autre_admin_a = make_user('admin2A', 'admin', cls.w.a.etab)

    def test_regles(self):
        w = self.w
        cas = [
            (w.superadmin, w.a.admin, True),
            (w.a.admin, w.a.admin, True),
            (w.a.admin, w.a.resp, True),
            (w.a.admin, w.a.ens, True),
            (w.a.admin, w.a.etu, True),
            (w.a.admin, self.autre_admin_a, False),
            (w.a.admin, w.b.etu, False),
            (w.a.resp, w.a.resp, True),
            (w.a.resp, w.a.etu, True),
            (w.a.resp, w.a.ens, False),
            (w.a.resp, w.a.admin, False),
            (w.a.resp, w.b.etu, False),
            (w.a.ens, w.a.etu, False),
            (w.a.ens, w.a.ens, False),
            (w.a.etu, w.a.etu, False),
        ]
        for acteur, cible, attendu in cas:
            with self.subTest(acteur=acteur.username, cible=cible.username):
                self.assertEqual(peut_gerer_compte(acteur, cible), attendu)
