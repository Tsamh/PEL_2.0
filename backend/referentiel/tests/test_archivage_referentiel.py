from datetime import date

from django.test import TestCase

from accounts.testing import build_world, client_for, make_user
from referentiel.models import (
    AnneeAcademique, Classe, EnseignantMatiere, Groupe, Inscription, PeriodeEvaluation, Semestre,
)
from programming.models import NoteMatiere

R = '/api/referentiel'


def lignes(res):
    return res.data['results'] if isinstance(res.data, dict) and 'results' in res.data else res.data


class ArchivageReferentielTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()
        a = cls.w.a
        cls.semestre = Semestre.objects.create(annee_academique=a.annee, libelle='S1', date_debut=date(2026, 10, 1),
                                               date_fin=date(2027, 2, 28))
        cls.periode = PeriodeEvaluation.objects.create(semestre=cls.semestre, libelle='CC1', date_debut=date(2026, 11, 1),
                                                       date_fin=date(2026, 11, 30))
        cls.groupe = Groupe.objects.create(code='TD1', libelle='TD 1', classe=a.classe)
        cls.nouvelle = AnneeAcademique.objects.create(libelle='2027-2028A', date_debut=date(2027, 10, 1),
                                                      date_fin=date(2028, 7, 31), etablissement=a.etab)
        cls.classe_active = Classe.objects.create(code='L1N', libelle='L1 nouvelle', filiere=a.filiere,
                                                  niveau=cls.w.niveau, annee_academique=cls.nouvelle)
        AnneeAcademique.objects.filter(pk=a.annee.pk).update(archivee=True)

    def setUp(self):
        self.a = self.w.a
        self.admin = client_for(self.a.admin)

    def assert_archive(self, res):
        self.assertEqual(res.status_code, 409, getattr(res, 'data', None))

    def test_listes_masquees_et_archives(self):
        for chemin, attendu in (('classes', self.a.classe.pk), ('groupes', self.groupe.pk),
                                ('semestres', self.semestre.pk), ('periodes-evaluation', self.periode.pk)):
            with self.subTest(chemin=chemin):
                ids = [l['id'] for l in lignes(self.admin.get(f'{R}/{chemin}/'))]
                self.assertNotIn(attendu, ids)
                ids = [l['id'] for l in lignes(self.admin.get(f'{R}/{chemin}/', {'archives': '1'}))]
                self.assertIn(attendu, ids)
        ids = [l['id'] for l in lignes(self.admin.get(f'{R}/classes/', {'archives': '1'}))]
        self.assertNotIn(self.classe_active.pk, ids)

    def test_consultation_par_identifiant(self):
        self.assertEqual(self.admin.get(f'{R}/classes/{self.a.classe.pk}/').status_code, 200)

    def test_classe(self):
        self.assert_archive(self.admin.patch(f'{R}/classes/{self.a.classe.pk}/', {'libelle': 'X'}, format='json'))
        self.assert_archive(self.admin.delete(f'{R}/classes/{self.a.classe.pk}/'))
        self.assert_archive(self.admin.post(f'{R}/classes/', {
            'code': 'L1Z', 'libelle': 'Z', 'filiere': self.a.filiere.pk, 'niveau': self.w.niveau.pk,
            'annee_academique': self.a.annee.pk}, format='json'))
        self.assert_archive(self.admin.patch(f'{R}/classes/{self.classe_active.pk}/',
                                             {'annee_academique': self.a.annee.pk}, format='json'))
        self.assertEqual(Classe.objects.get(pk=self.classe_active.pk).annee_academique_id, self.nouvelle.pk)
        self.assertEqual(self.admin.patch(f'{R}/classes/{self.classe_active.pk}/', {'libelle': 'Y'},
                                          format='json').status_code, 200)

    def test_groupe_et_membres(self):
        self.assert_archive(self.admin.patch(f'{R}/groupes/{self.groupe.pk}/', {'libelle': 'X'}, format='json'))
        self.assert_archive(self.admin.post(f'{R}/groupes/{self.groupe.pk}/membres/',
                                            {'etudiants': [self.a.etu.pk]}, format='json'))
        self.assert_archive(self.admin.delete(f'{R}/groupes/{self.groupe.pk}/membres/{self.a.etu.pk}/'))

    def test_inscription(self):
        etu2 = make_user('etu2', 'etudiant', self.a.etab)
        self.assert_archive(self.admin.post(f'{R}/inscriptions/', {'etudiant': etu2.pk, 'classe': self.a.classe.pk},
                                            format='json'))
        inscription = Inscription.objects.get(etudiant=self.a.etu, classe=self.a.classe)
        self.assert_archive(self.admin.delete(f'{R}/inscriptions/{inscription.pk}/'))

    def test_enseignant_matiere(self):
        em = EnseignantMatiere.objects.get(enseignant=self.a.ens, classe=self.a.classe)
        self.assert_archive(self.admin.delete(f'{R}/enseignants-matieres/{em.pk}/'))

    def test_semestre_et_periode(self):
        self.assert_archive(self.admin.patch(f'{R}/semestres/{self.semestre.pk}/', {'libelle': 'S9'}, format='json'))
        self.assert_archive(self.admin.post(f'{R}/semestres/', {
            'annee_academique': self.a.annee.pk, 'libelle': 'S2', 'date_debut': '2027-03-01',
            'date_fin': '2027-07-01'}, format='json'))
        self.assert_archive(self.admin.patch(f'{R}/periodes-evaluation/{self.periode.pk}/', {'libelle': 'CC9'},
                                             format='json'))


class SuppressionCascadeTests(TestCase):
    """Un DELETE du référentiel ne doit jamais emporter de données d'une année archivée."""

    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()
        a = cls.w.a
        cls.note = NoteMatiere.objects.create(etudiant=a.etu, ec=a.ec, classe=a.classe, annee_academique=a.annee,
                                              note_devoir=12)
        AnneeAcademique.objects.filter(pk=a.annee.pk).update(archivee=True)

    def setUp(self):
        self.a = self.w.a
        self.admin = client_for(self.a.admin)

    def test_suppression_refusee(self):
        for chemin, pk in (('filieres', self.a.filiere.pk), ('ues', self.a.ue.pk), ('ecs', self.a.ec.pk)):
            with self.subTest(chemin=chemin):
                res = self.admin.delete(f'{R}/{chemin}/{pk}/')
                self.assertEqual(res.status_code, 409, getattr(res, 'data', None))
                self.assertIn("année archivée", str(res.data['detail']))
        self.assertTrue(Classe.objects.filter(pk=self.a.classe.pk).exists())
        self.assertTrue(NoteMatiere.objects.filter(pk=self.note.pk).exists())

    def test_suppression_sans_donnee_archivee(self):
        b = self.w.b
        self.assertEqual(client_for(b.admin).delete(f'{R}/ecs/{b.ec.pk}/').status_code, 204)
        self.assertEqual(client_for(b.admin).delete(f'{R}/ues/{b.ue.pk}/').status_code, 204)
        self.assertEqual(client_for(b.admin).delete(f'{R}/filieres/{b.filiere.pk}/').status_code, 204)
