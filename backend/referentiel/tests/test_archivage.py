from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.testing import build_world, client_for
from audit.models import AuditLog
from quiz.models import TentativeQuiz
from referentiel.models import AnneeAcademique

R = '/api/referentiel'


class ArchivageAnneeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def setUp(self):
        self.a = self.w.a
        self.annee = self.a.annee
        AnneeAcademique.objects.filter(pk=self.annee.pk).update(date_fin=date.today() - timedelta(days=1), est_active=True)

    def post(self, user, action, annee=None):
        annee = annee or self.annee
        return client_for(user).post(f'{R}/annees-academiques/{annee.pk}/{action}/')

    def test_admin_archive(self):
        res = self.post(self.a.admin, 'archiver')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertTrue(res.data['archivee'])
        self.assertEqual(res.data['archivee_par_nom'], self.a.admin.get_full_name() or self.a.admin.username)
        self.annee.refresh_from_db()
        self.assertTrue(self.annee.archivee)
        self.assertFalse(self.annee.est_active)
        self.assertIsNotNone(self.annee.archivee_le)
        self.assertEqual(self.annee.archivee_par, self.a.admin)
        self.assertTrue(AuditLog.objects.filter(action='archivage_annee', etablissement=self.a.etab).exists())

    def test_superadmin_archive(self):
        self.assertEqual(self.post(self.w.superadmin, 'archiver').status_code, 200)

    def test_deja_archivee(self):
        self.post(self.a.admin, 'archiver')
        self.assertEqual(self.post(self.a.admin, 'archiver').status_code, 409)

    def test_annee_non_terminee(self):
        AnneeAcademique.objects.filter(pk=self.annee.pk).update(date_fin=date.today())
        res = self.post(self.a.admin, 'archiver')
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data['detail'], "L'année académique n'est pas terminée : elle ne peut pas encore être archivée.")

    def test_tentative_en_cours(self):
        TentativeQuiz.objects.create(quiz=self.a.quiz, etudiant=self.a.etu, numero=1,
                                     fin_prevue=timezone.now() + timedelta(hours=1))
        res = self.post(self.a.admin, 'archiver')
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data['detail'], "Des tentatives de quiz sont encore en cours pour cette année.")

    def test_tentative_expiree_cloturee(self):
        t = TentativeQuiz.objects.create(quiz=self.a.quiz, etudiant=self.a.etu, numero=1,
                                         debut=timezone.now() - timedelta(days=2),
                                         fin_prevue=timezone.now() - timedelta(days=1))
        self.assertEqual(self.post(self.a.admin, 'archiver').status_code, 200)
        t.refresh_from_db()
        self.assertEqual(t.statut, TentativeQuiz.SOUMISE)

    def test_droits(self):
        self.assertEqual(self.post(self.a.resp, 'archiver').status_code, 403)
        self.assertEqual(self.post(self.a.ens, 'archiver').status_code, 403)
        self.assertEqual(self.post(self.a.etu, 'archiver').status_code, 403)
        self.assertEqual(self.post(self.w.b.admin, 'archiver').status_code, 404)
        self.assertEqual(self.post(self.w.b.admin, 'desarchiver').status_code, 404)

    def test_desarchiver(self):
        self.post(self.a.admin, 'archiver')
        res = self.post(self.a.admin, 'desarchiver')
        self.assertEqual(res.status_code, 200, res.data)
        self.annee.refresh_from_db()
        self.assertFalse(self.annee.archivee)
        self.assertIsNone(self.annee.archivee_le)
        self.assertIsNone(self.annee.archivee_par)
        self.assertTrue(AuditLog.objects.filter(action='desarchivage_annee').exists())
        self.assertEqual(self.post(self.a.admin, 'desarchiver').status_code, 409)

    def test_annee_archivee_en_lecture_seule(self):
        self.post(self.a.admin, 'archiver')
        url = f'{R}/annees-academiques/{self.annee.pk}/'
        res = client_for(self.a.admin).patch(url, {'libelle': 'Autre'}, format='json')
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data['detail'],
                         f"L'année académique {self.annee.libelle} est archivée : ses données sont en lecture seule.")
        self.assertEqual(client_for(self.a.admin).delete(url).status_code, 409)
        self.assertEqual(client_for(self.a.admin).get(url).status_code, 200)
        self.post(self.a.admin, 'desarchiver')
        self.assertEqual(client_for(self.a.admin).patch(url, {'libelle': 'Autre'}, format='json').status_code, 200)

    def test_liste_des_annees_non_masquee(self):
        self.post(self.a.admin, 'archiver')
        res = client_for(self.a.admin).get(f'{R}/annees-academiques/')
        lignes = res.data['results'] if isinstance(res.data, dict) else res.data
        self.assertEqual([(l['id'], l['archivee']) for l in lignes], [(self.annee.pk, True)])

    def test_drapeau_en_lecture_seule(self):
        client_for(self.a.admin).patch(f'{R}/annees-academiques/{self.annee.pk}/', {'archivee': True}, format='json')
        self.annee.refresh_from_db()
        self.assertFalse(self.annee.archivee)
