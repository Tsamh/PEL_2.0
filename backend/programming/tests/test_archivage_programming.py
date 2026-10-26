from django.test import TestCase

from accounts.testing import build_world, client_for
from programming.models import NoteMatiere, SoumissionDevoir
from referentiel.models import AnneeAcademique

P = '/api/programming'


def ids(res):
    data = res.data['results'] if isinstance(res.data, dict) and 'results' in res.data else res.data
    return [l['id'] for l in data]


class ArchivageProgrammingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()
        a = cls.w.a
        cls.soumission = SoumissionDevoir.objects.create(devoir=a.devoir, etudiant=a.etu, code_soumis='print(4)')
        cls.note = NoteMatiere.objects.create(etudiant=a.etu, ec=a.ec, classe=a.classe, annee_academique=a.annee,
                                              note_devoir=12)
        AnneeAcademique.objects.filter(pk=a.annee.pk).update(archivee=True)

    def setUp(self):
        self.a = self.w.a

    def test_listes(self):
        ens, etu = client_for(self.a.ens), client_for(self.a.etu)
        self.assertNotIn(self.a.devoir.pk, ids(ens.get(f'{P}/devoirs/')))
        self.assertIn(self.a.devoir.pk, ids(ens.get(f'{P}/devoirs/', {'archives': '1'})))
        self.assertNotIn(self.soumission.pk, ids(etu.get(f'{P}/soumissions/')))
        self.assertIn(self.soumission.pk, ids(etu.get(f'{P}/soumissions/', {'archives': '1'})))
        self.assertNotIn(self.note.pk, ids(ens.get(f'{P}/notes/')))
        self.assertNotIn(self.note.pk, ids(etu.get(f'{P}/notes/mes_notes/')))
        self.assertIn(self.note.pk, ids(etu.get(f'{P}/notes/mes_notes/', {'archives': '1'})))

    def test_soumissions_d_un_devoir_archive(self):
        ens = client_for(self.a.ens)
        self.assertIn(self.soumission.pk, ids(ens.get(f'{P}/soumissions/', {'devoir': self.a.devoir.pk})))
        self.assertEqual(ids(client_for(self.w.b.ens).get(f'{P}/soumissions/', {'devoir': self.a.devoir.pk})), [])
        self.assertEqual(ids(ens.get(f'{P}/soumissions/', {'devoir': 'x'})), [])
        self.assertNotIn(self.soumission.pk, ids(ens.get(f'{P}/soumissions/')))

    def test_ecritures_refusees(self):
        ens, etu = client_for(self.a.ens), client_for(self.a.etu)
        cas = [
            ens.patch(f'{P}/devoirs/{self.a.devoir.pk}/', {'titre': 'X'}, format='json'),
            ens.delete(f'{P}/devoirs/{self.a.devoir.pk}/'),
            ens.post(f'{P}/soumissions/{self.soumission.pk}/corriger/', {'score': 5}, format='json'),
            ens.delete(f'{P}/soumissions/{self.soumission.pk}/'),
            ens.patch(f'{P}/notes/{self.note.pk}/', {'note_examen': 10}, format='json'),
            ens.post(f'{P}/notes/bulk_update/', {'ec': self.a.ec.pk, 'classe': self.a.classe.pk,
                                                 'annee_academique': self.a.annee.pk, 'notes': []}, format='json'),
            etu.post(f'{P}/soumissions/', {'devoir': self.a.devoir.pk, 'code_soumis': 'x'}, format='json'),
        ]
        for i, res in enumerate(cas):
            with self.subTest(cas=i):
                self.assertEqual(res.status_code, 409, getattr(res, 'data', None))
                self.assertIn('est archivée', str(res.data['detail']))
        self.assertTrue(SoumissionDevoir.objects.filter(pk=self.soumission.pk).exists())
        self.assertEqual(SoumissionDevoir.objects.filter(devoir=self.a.devoir).count(), 1)

    def test_consultation(self):
        self.assertEqual(client_for(self.a.ens).get(f'{P}/devoirs/{self.a.devoir.pk}/').status_code, 200)
