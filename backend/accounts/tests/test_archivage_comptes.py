from django.contrib.auth import get_user_model
from django.test import TestCase

from accounts.testing import build_world, client_for
from referentiel.models import AffectationEnseignant, AnneeAcademique, EnseignantMatiere, Inscription

User = get_user_model()
U = '/api/accounts/users'


class ArchivageComptesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()
        AnneeAcademique.objects.filter(pk=cls.w.a.annee.pk).update(archivee=True)

    def setUp(self):
        self.a = self.w.a
        self.admin = client_for(self.a.admin)

    def test_invite_student_refuse_dans_une_classe_archivee(self):
        res = self.admin.post(f'{U}/invite_student/', {
            'email': 'nouveau@test.pel', 'first_name': 'N', 'last_name': 'N', 'classe': self.a.classe.id,
        }, format='json')
        self.assertEqual(res.status_code, 409, res.data)
        self.assertIn('est archivée', str(res.data['detail']))
        self.assertFalse(User.objects.filter(email='nouveau@test.pel').exists())
        self.assertEqual(Inscription.objects.filter(classe=self.a.classe).count(), 1)

    def test_invite_enseignant_n_affecte_pas_de_classe_archivee(self):
        res = self.admin.post(f'{U}/invite_enseignant/', {
            'email': 'prof2@test.pel', 'first_name': 'P', 'last_name': 'P', 'classes': [self.a.classe.id],
        }, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        prof = User.objects.get(email='prof2@test.pel')
        self.assertFalse(AffectationEnseignant.objects.filter(enseignant=prof).exists())
        self.assertFalse(EnseignantMatiere.objects.filter(enseignant=prof).exists())

    def test_update_classes_conserve_les_affectations_archivees(self):
        avant_aff = set(AffectationEnseignant.objects.filter(enseignant=self.a.ens).values_list('pk', flat=True))
        avant_em = set(EnseignantMatiere.objects.filter(enseignant=self.a.ens).values_list('pk', flat=True))
        self.assertTrue(avant_aff and avant_em)
        for classes in ([], [self.a.classe.id]):
            with self.subTest(classes=classes):
                res = self.admin.post(f'{U}/{self.a.ens.id}/update_classes/', {'classes': classes}, format='json')
                self.assertEqual(res.status_code, 200, res.data)
                self.assertEqual(set(AffectationEnseignant.objects.filter(enseignant=self.a.ens)
                                     .values_list('pk', flat=True)), avant_aff)
                self.assertEqual(set(EnseignantMatiere.objects.filter(enseignant=self.a.ens)
                                     .values_list('pk', flat=True)), avant_em)
