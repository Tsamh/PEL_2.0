from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase
from rest_framework.exceptions import ValidationError

from accounts.scoping import (
    EtablissementScopedMixin, classes_enseignant, classes_etudiant,
    classes_du_perimetre, filieres_etudiant, verifier_compte_du_perimetre,
    verifier_filiere_du_perimetre,
)
from accounts.testing import build_world, make_user
from referentiel.models import Classe


class _Base:
    def get_queryset(self):
        return Classe.objects.all()


class _ClasseScoped(EtablissementScopedMixin, _Base):
    scope_path = 'filiere__etablissement'

    def enseignant_scope(self, qs, user):
        return qs.filter(pk__in=classes_enseignant(user))

    def etudiant_scope(self, qs, user):
        return qs.filter(pk__in=classes_etudiant(user))


def vue(user):
    view = _ClasseScoped()
    view.request = SimpleNamespace(user=user)
    return view


class MixinTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def test_superadmin_voit_tout(self):
        self.assertEqual(vue(self.w.superadmin).get_queryset().count(), 2)

    def test_chaque_role_ne_voit_que_son_perimetre(self):
        a = self.w.a
        for user in (a.admin, a.resp, a.ens, a.etu):
            with self.subTest(role=user.role):
                self.assertEqual(list(vue(user).get_queryset()), [a.classe])

    def test_enseignant_sans_affectation_ne_voit_rien(self):
        nouveau = make_user('ensC', 'enseignant', self.w.a.etab)
        self.assertEqual(vue(nouveau).get_queryset().count(), 0)

    def test_admin_sans_etablissement_ne_voit_rien(self):
        orphelin = make_user('adminX', 'admin')
        self.assertEqual(vue(orphelin).get_queryset().count(), 0)

    def test_assert_in_scope(self):
        vue(self.w.a.admin).assert_in_scope(self.w.a.classe)
        with self.assertRaises(ValidationError):
            vue(self.w.a.admin).assert_in_scope(self.w.b.classe)
        vue(self.w.superadmin).assert_in_scope(self.w.b.classe)


class HelpersTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def test_classes_du_perimetre(self):
        a = self.w.a
        self.assertEqual(classes_du_perimetre(self.w.superadmin).count(), 2)
        for user in (a.admin, a.resp, a.ens, a.etu):
            with self.subTest(role=user.role):
                self.assertEqual(list(classes_du_perimetre(user)), [a.classe])

    def test_filieres_etudiant(self):
        self.assertEqual(list(filieres_etudiant(self.w.a.etu)), [self.w.a.filiere.id])

    def test_verifier_compte_du_perimetre(self):
        a, b = self.w.a, self.w.b
        verifier_compte_du_perimetre(a.admin, a.etu, 'etudiant')
        verifier_compte_du_perimetre(self.w.superadmin, b.etu, 'etudiant')
        with self.assertRaises(ValidationError):
            verifier_compte_du_perimetre(a.admin, b.etu, 'etudiant')
        with self.assertRaises(ValidationError):
            verifier_compte_du_perimetre(a.admin, a.ens, 'etudiant')

    def test_verifier_filiere_du_perimetre(self):
        a, b = self.w.a, self.w.b
        verifier_filiere_du_perimetre(a.admin, a.filiere)
        verifier_filiere_du_perimetre(a.ens, a.filiere)
        verifier_filiere_du_perimetre(a.ens, None)
        verifier_filiere_du_perimetre(self.w.superadmin, b.filiere)
        for acteur in (a.admin, a.resp, a.ens):
            with self.subTest(role=acteur.role):
                with self.assertRaises(ValidationError):
                    verifier_filiere_du_perimetre(acteur, b.filiere)


class EnEntierBornesTests(SimpleTestCase):
    def test_au_dela_de_la_borne_sqlite(self):
        from accounts.scoping import en_entier
        self.assertIsNone(en_entier('9' * 20))
        self.assertIsNone(en_entier(2 ** 63))
        self.assertEqual(en_entier(str(2 ** 63 - 1)), 2 ** 63 - 1)
        self.assertEqual(en_entier('12'), 12)
