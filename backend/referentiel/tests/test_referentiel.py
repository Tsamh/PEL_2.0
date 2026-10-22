from django.test import TestCase

from accounts.testing import build_world, client_for, make_user
from audit.models import AuditLog
from referentiel.models import AnneeAcademique, Classe, Filiere, Inscription, EnseignantMatiere, EC

R = '/api/referentiel'


def ids(res):
    data = res.data['results'] if isinstance(res.data, dict) and 'results' in res.data else res.data
    return {o['id'] for o in data}


class EcritureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def test_etudiant_et_enseignant_ne_peuvent_pas_ecrire(self):
        a = self.w.a
        for user in (a.ens, a.etu):
            for url, data in [
                (f'{R}/filieres/', {'code': 'X', 'libelle': 'X'}),
                (f'{R}/ues/', {'code': 'X', 'libelle': 'X', 'filiere': a.filiere.id, 'niveau': self.w.niveau.id}),
                (f'{R}/classes/', {}),
            ]:
                with self.subTest(role=user.role, url=url):
                    self.assertEqual(client_for(user).post(url, data, format='json').status_code, 403)

    def test_etablissement_impose_a_la_creation(self):
        a, b = self.w.a, self.w.b
        res = client_for(a.resp).post(f'{R}/filieres/', {'code': 'MATH', 'libelle': 'Maths', 'etablissement': b.etab.id}, format='json')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(Filiere.objects.get(code='MATH').etablissement, a.etab)

    def test_reference_hors_perimetre_refusee_et_annulee(self):
        a, b = self.w.a, self.w.b
        res = client_for(a.admin).post(f'{R}/classes/', {
            'code': 'PIEGE', 'libelle': 'Piège', 'filiere': b.filiere.id,
            'niveau': self.w.niveau.id, 'annee_academique': b.annee.id,
        }, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertFalse(Classe.objects.filter(code='PIEGE').exists())

    def test_deplacement_hors_perimetre_refuse(self):
        a, b = self.w.a, self.w.b
        res = client_for(a.admin).patch(f'{R}/ues/{a.ue.id}/', {'filiere': b.filiere.id}, format='json')
        self.assertEqual(res.status_code, 400)
        a.ue.refresh_from_db()
        self.assertEqual(a.ue.filiere, a.filiere)

    def test_objet_d_un_autre_etablissement_introuvable(self):
        a, b = self.w.a, self.w.b
        self.assertEqual(client_for(a.admin).get(f'{R}/classes/{b.classe.id}/').status_code, 404)
        self.assertEqual(client_for(a.admin).delete(f'{R}/filieres/{b.filiere.id}/').status_code, 404)

    def test_niveaux_globaux_en_ecriture_superadmin(self):
        self.assertEqual(client_for(self.w.a.admin).post(f'{R}/niveaux/', {'code': 'M1', 'libelle': 'Master 1'}).status_code, 403)
        self.assertEqual(client_for(self.w.a.admin).get(f'{R}/niveaux/').status_code, 200)
        self.assertEqual(client_for(self.w.superadmin).post(f'{R}/niveaux/', {'code': 'M1', 'libelle': 'Master 1'}).status_code, 201)

    def test_create_with_filieres_impose_l_etablissement(self):
        a, b = self.w.a, self.w.b
        res = client_for(a.resp).post(f'{R}/annees-academiques/create_with_filieres/', {
            'annee_libelle': '2027-2028', 'annee_date_debut': '2027-10-01', 'annee_date_fin': '2028-07-31',
            'annee_etablissement': b.etab.id,
            'filieres': [{'code': 'GL', 'libelle': 'Génie logiciel', 'niveau': 'L1'}],
        }, format='json')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(AnneeAcademique.objects.get(libelle='2027-2028').etablissement, a.etab)
        self.assertEqual(Filiere.objects.get(code='GL').etablissement, a.etab)
        self.assertEqual(client_for(a.ens).post(f'{R}/annees-academiques/create_with_filieres/', {}).status_code, 403)


class LectureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def test_chaque_role_lit_son_perimetre(self):
        a = self.w.a
        ressources = {
            'filieres': a.filiere.id, 'ues': a.ue.id, 'ecs': a.ec.id, 'classes': a.classe.id,
            'annees-academiques': a.annee.id,
        }
        for user in (a.admin, a.resp, a.ens, a.etu):
            for ressource, attendu in ressources.items():
                with self.subTest(role=user.role, ressource=ressource):
                    res = client_for(user).get(f'{R}/{ressource}/')
                    self.assertEqual(res.status_code, 200)
                    self.assertEqual(ids(res), {attendu})

    def test_etablissements(self):
        a = self.w.a
        self.assertEqual(ids(client_for(a.admin).get(f'{R}/etablissements/')), {a.etab.id})
        self.assertEqual(ids(client_for(a.resp).get(f'{R}/etablissements/')), {a.etab.id})
        self.assertEqual(client_for(a.ens).get(f'{R}/etablissements/').status_code, 403)
        self.assertEqual(client_for(a.etu).get(f'{R}/etablissements/').status_code, 403)
        self.assertEqual(client_for(a.admin).post(f'{R}/etablissements/', {}).status_code, 403)
        self.assertEqual(len(ids(client_for(self.w.superadmin).get(f'{R}/etablissements/'))), 2)

    def test_inscriptions_lues_selon_le_role(self):
        a = self.w.a
        attendu = set(Inscription.objects.filter(classe=a.classe).values_list('id', flat=True))
        for user in (a.admin, a.ens, a.etu):
            with self.subTest(role=user.role):
                self.assertEqual(ids(client_for(user).get(f'{R}/inscriptions/')), attendu)

    def test_etudiant_ne_lit_pas_les_affectations_enseignants(self):
        self.assertEqual(client_for(self.w.a.etu).get(f'{R}/enseignants-matieres/').status_code, 403)


class InscriptionsAffectationsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def test_inscription_journalisee(self):
        a = self.w.a
        nouvel = make_user('etuA2', 'etudiant', a.etab)
        res = client_for(a.resp).post(f'{R}/inscriptions/', {'etudiant': nouvel.id, 'classe': a.classe.id}, format='json')
        self.assertEqual(res.status_code, 201)
        entree = AuditLog.objects.get(action='inscription')
        self.assertEqual(entree.etablissement, a.etab)

    def test_inscription_d_un_etudiant_d_un_autre_etablissement_refusee(self):
        a, b = self.w.a, self.w.b
        res = client_for(a.admin).post(f'{R}/inscriptions/', {'etudiant': b.etu.id, 'classe': a.classe.id}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_retrait_journalise(self):
        a = self.w.a
        inscription = Inscription.objects.get(etudiant=a.etu, classe=a.classe)
        self.assertEqual(client_for(a.admin).delete(f'{R}/inscriptions/{inscription.id}/').status_code, 204)
        self.assertTrue(AuditLog.objects.filter(action='retrait_affectation', details__type='inscription').exists())

    def test_affectation_enseignant_matiere(self):
        a, b = self.w.a, self.w.b
        ec2 = EC.objects.create(code='EC2A', libelle='Algo', ue=a.ue)
        client = client_for(a.resp)
        res = client.post(f'{R}/enseignants-matieres/', {'enseignant': a.ens.id, 'ec': ec2.id, 'classe': a.classe.id}, format='json')
        self.assertEqual(res.status_code, 201)
        self.assertTrue(AuditLog.objects.filter(action='affectation').exists())
        res = client.post(f'{R}/enseignants-matieres/', {'enseignant': a.ens.id, 'ec': b.ec.id, 'classe': a.classe.id}, format='json')
        self.assertEqual(res.status_code, 400)
        res = client.post(f'{R}/enseignants-matieres/', {'enseignant': a.etu.id, 'ec': ec2.id, 'classe': a.classe.id}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(EnseignantMatiere.objects.filter(ec=b.ec, classe=a.classe).count(), 0)
