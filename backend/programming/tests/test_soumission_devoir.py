from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from accounts.testing import build_world, client_for, make_user
from programming.models import CasDeTest, Devoir, Exercice, ReponseExercice, SessionDevoir, SoumissionDevoir
from referentiel.models import AnneeAcademique, Inscription

P = '/api/programming'
DEJA_SOUMIS = "Vous avez déjà soumis ce devoir."
PAS_OUVERT = "Ce devoir n'est pas ouvert."
FERME = "Ce devoir est fermé."


class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()
        a = cls.w.a
        cls.ex1 = a.exercice
        CasDeTest.objects.create(exercice=cls.ex1, ordre=2, entree='CACHE_ENTREE', sortie_attendue='CACHE_SORTIE',
                                 public=False)
        cls.ex2 = Exercice.objects.create(devoir=a.devoir, ordre=2, titre='Deuxième', points=Decimal('5.5'))
        CasDeTest.objects.create(exercice=cls.ex2, ordre=1, entree='1', sortie_attendue='2', public=True)
        cls.autre_ex = cls.w.b.exercice

    def setUp(self):
        self.a = self.w.a
        self.etu = client_for(self.a.etu)
        self.maintenant = timezone.now()

    def corps(self, reponses=None, devoir=None):
        if reponses is None:
            reponses = [
                {'exercice': self.ex1.id, 'fichiers': [{'nom': 'main.py', 'contenu': 'print(4)\n'}]},
                {'exercice': self.ex2.id, 'fichiers': [{'nom': 'main.py', 'contenu': 'print(2)'}]},
            ]
        return {'devoir': devoir or self.a.devoir.id, 'reponses': reponses}

    def soumettre(self, client=None, **kwargs):
        return (client or self.etu).post(f'{P}/soumissions/', self.corps(**kwargs), format='json')

    def dates(self, debut, fin):
        Devoir.objects.filter(pk=self.a.devoir.pk).update(date_debut=debut, date_fin=fin)


class SoumissionTests(Base):
    def test_soumission_valide(self):
        res = self.soumettre()
        self.assertEqual(res.status_code, 201, res.data)
        soumission = SoumissionDevoir.objects.get(pk=res.data['id'])
        self.assertEqual(soumission.etudiant, self.a.etu)
        self.assertEqual(
            [(r.exercice_id, r.fichiers) for r in soumission.reponses.all()],
            [(self.ex1.id, [{'nom': 'main.py', 'contenu': 'print(4)\n'}]),
             (self.ex2.id, [{'nom': 'main.py', 'contenu': 'print(2)'}])],
        )
        self.assertEqual(res.data['bareme'], '25.50')
        self.assertEqual(res.data['reponses'][0], {
            'exercice': self.ex1.id, 'exercice_titre': 'Afficher 4',
            'fichiers': [{'nom': 'main.py', 'contenu': 'print(4)\n'}], 'correction': None,
        })
        self.assertEqual(res.data['statut'], 'en_correction')
        lu = self.etu.get(f'{P}/soumissions/{soumission.id}/')
        self.assertEqual(lu.status_code, 200)
        self.assertEqual(len(lu.data['reponses']), 2)
        liste = client_for(self.a.ens).get(f'{P}/soumissions/', {'devoir': self.a.devoir.id})
        donnees = liste.data['results'] if 'results' in liste.data else liste.data
        self.assertEqual([s['id'] for s in donnees], [soumission.id])

    def test_reponse_partielle_acceptee(self):
        res = self.soumettre(reponses=[{'exercice': self.ex2.id, 'fichiers': []}])
        self.assertEqual(res.status_code, 201, res.data)

    def test_doublon_409_sans_500(self):
        self.assertEqual(self.soumettre().status_code, 201)
        res = self.soumettre()
        self.assertEqual(res.status_code, 409)
        self.assertEqual(str(res.data['detail']), DEJA_SOUMIS)
        self.assertEqual(SoumissionDevoir.objects.filter(devoir=self.a.devoir).count(), 1)

    def test_doublon_concurrent_409(self):
        with mock.patch('programming.views.SoumissionDevoir.objects.create', side_effect=IntegrityError('unique')):
            res = self.soumettre()
        self.assertEqual(res.status_code, 409)
        self.assertEqual(str(res.data['detail']), DEJA_SOUMIS)

    def test_avant_ouverture(self):
        self.dates(self.maintenant + timedelta(days=1), self.maintenant + timedelta(days=2))
        res = self.soumettre()
        self.assertEqual(res.status_code, 409)
        self.assertEqual(str(res.data['detail']), PAS_OUVERT)
        self.assertFalse(SoumissionDevoir.objects.exists())

    def test_apres_fermeture(self):
        self.dates(self.maintenant - timedelta(days=2), self.maintenant - timedelta(days=1))
        res = self.soumettre()
        self.assertEqual(res.status_code, 409)
        self.assertEqual(str(res.data['detail']), FERME)

    def test_rattrapage_ouvert_accepte(self):
        self.dates(self.maintenant - timedelta(days=2), self.maintenant - timedelta(days=1))
        session = SessionDevoir.objects.create(devoir=self.a.devoir, type=SessionDevoir.RATTRAPAGE,
                                               ouverture=self.maintenant - timedelta(hours=1),
                                               fermeture=self.maintenant + timedelta(hours=1))
        session.etudiants.add(self.a.etu)
        self.assertEqual(self.soumettre().status_code, 201)

    def test_exercice_d_un_autre_devoir(self):
        res = self.soumettre(reponses=[{'exercice': self.autre_ex.id, 'fichiers': []}])
        self.assertEqual(res.status_code, 400)
        self.assertIn('reponses', res.data)
        self.assertFalse(SoumissionDevoir.objects.exists())

    def test_exercice_en_double(self):
        res = self.soumettre(reponses=[{'exercice': self.ex1.id, 'fichiers': []},
                                       {'exercice': self.ex1.id, 'fichiers': []}])
        self.assertEqual(res.status_code, 400)
        self.assertIn('reponses', res.data)
        self.assertFalse(SoumissionDevoir.objects.exists())

    def test_entrees_invalides(self):
        cas = [
            None, 'abc', [], ['x'], [{'fichiers': []}], [{'exercice': 'abc', 'fichiers': []}],
            [{'exercice': True, 'fichiers': []}],
            [{'exercice': self.ex1.id, 'fichiers': 'x'}],
            [{'exercice': self.ex1.id, 'fichiers': [{'nom': '../x', 'contenu': ''}]}],
            [{'exercice': self.ex1.id, 'fichiers': [{'nom': 'a.py', 'contenu': 'x' * 100001}]}],
            [{'exercice': self.ex1.id, 'fichiers': [{'nom': 'a.py', 'contenu': ''}, {'nom': 'a.py', 'contenu': ''}]}],
        ]
        for reponses in cas:
            with self.subTest(reponses=str(reponses)[:60]):
                corps = {'devoir': self.a.devoir.id}
                if reponses is not None:
                    corps['reponses'] = reponses
                res = self.etu.post(f'{P}/soumissions/', corps, format='json')
                self.assertEqual(res.status_code, 400, res.data)
        self.assertFalse(SoumissionDevoir.objects.exists())

    def test_etudiant_non_affecte(self):
        intrus = make_user('intrus', 'etudiant', self.a.etab)
        res = self.soumettre(client=client_for(intrus))
        self.assertEqual(res.status_code, 400)
        self.assertEqual(str(res.data['detail']), "Devoir introuvable.")
        self.assertEqual(self.soumettre(devoir=self.w.b.devoir.id).status_code, 400)
        self.assertEqual(self.etu.post(f'{P}/soumissions/', {'devoir': 'x', 'reponses': []}, format='json').status_code, 400)

    def test_annee_archivee(self):
        AnneeAcademique.objects.filter(pk=self.a.annee.pk).update(archivee=True)
        res = self.soumettre()
        self.assertEqual(res.status_code, 409)
        self.assertIn('est archivée', str(res.data['detail']))
        self.assertFalse(SoumissionDevoir.objects.exists())

    def test_correcteur_ne_modifie_pas_les_reponses(self):
        soumission = SoumissionDevoir.objects.get(pk=self.soumettre().data['id'])
        res = client_for(self.a.ens).patch(f'{P}/soumissions/{soumission.id}/', {'reponses': []}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(ReponseExercice.objects.filter(soumission=soumission).count(), 2)


class RattrapageTests(Base):
    def test_rattrapage_refuse_un_etudiant_ayant_soumis(self):
        SoumissionDevoir.objects.create(devoir=self.a.devoir, etudiant=self.a.etu)
        res = client_for(self.a.ens).post(f'{P}/sessions-devoir/', {
            'devoir': self.a.devoir.id, 'type': 'rattrapage',
            'ouverture': (self.maintenant + timedelta(days=1)).isoformat(),
            'fermeture': (self.maintenant + timedelta(days=2)).isoformat(),
            'etudiants': [self.a.etu.id],
        }, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('etudiants', res.data)

    def test_rattrapage_existant_modifiable_apres_soumission(self):
        res = client_for(self.a.ens).post(f'{P}/sessions-devoir/', {
            'devoir': self.a.devoir.id, 'type': 'rattrapage',
            'ouverture': (self.maintenant + timedelta(days=1)).isoformat(),
            'fermeture': (self.maintenant + timedelta(days=2)).isoformat(),
            'etudiants': [self.a.etu.id],
        }, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        SoumissionDevoir.objects.create(devoir=self.a.devoir, etudiant=self.a.etu)
        res = client_for(self.a.ens).patch(f'{P}/sessions-devoir/{res.data["id"]}/', {'libelle': 'Rattrapage'},
                                           format='json')
        self.assertEqual(res.status_code, 200, res.data)


class CorrectionTests(Base):
    def test_score_borne_par_le_bareme(self):
        Exercice.objects.filter(pk=self.ex1.pk).update(points=Decimal('2'))
        soumission = SoumissionDevoir.objects.create(devoir=self.a.devoir, etudiant=self.a.etu)
        url = f'{P}/soumissions/{soumission.id}/corriger/'
        ens = client_for(self.a.ens)
        res = ens.post(url, {'score': 8}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(str(res.data['score']), "Le score doit être compris entre 0 et 7.")
        res = ens.post(url, {'score': 7}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data['score'], 7)
        self.assertEqual(ens.post(url, {'score': 0}, format='json').status_code, 200)
        self.assertEqual(ens.post(url, {'score': -1}, format='json').status_code, 400)
