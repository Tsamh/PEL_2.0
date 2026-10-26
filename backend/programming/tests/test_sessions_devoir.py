from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.testing import build_world, client_for, make_user
from audit.models import AuditLog
from programming.models import Devoir, SessionDevoir, SoumissionDevoir
from referentiel.models import AnneeAcademique, Classe, Groupe, Inscription

S = '/api/programming/sessions-devoir'
D = '/api/programming/devoirs'


def iso(dt):
    return dt.isoformat()


class SessionsDevoirTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def setUp(self):
        self.a = self.w.a
        self.devoir = self.a.devoir
        self.ens = client_for(self.a.ens)
        self.maintenant = timezone.now()
        self.groupe = Groupe.objects.create(code='TD1A', libelle='TD 1', classe=self.a.classe)
        self.classe_hors = Classe.objects.create(code='L1Z', libelle='L1 Z', filiere=self.a.filiere,
                                                 niveau=self.w.niveau, annee_academique=self.a.annee)
        self.etu_hors = make_user('etuhors', 'etudiant', self.a.etab)
        Inscription.objects.create(etudiant=self.etu_hors, classe=self.classe_hors)

    def corps(self, **extra):
        donnees = {'devoir': self.devoir.id, 'type': 'normale', 'libelle': 'Lundi',
                   'ouverture': iso(self.maintenant + timedelta(days=1)),
                   'fermeture': iso(self.maintenant + timedelta(days=1, hours=2)), 'classes': [self.a.classe.id]}
        donnees.update(extra)
        return donnees

    def creer(self, client=None, **extra):
        return (client or self.ens).post(f'{S}/', self.corps(**extra), format='json')

    def etat(self):
        res = client_for(self.a.etu).get(f'{D}/{self.devoir.id}/')
        self.assertEqual(res.status_code, 200, res.data)
        return res.data['etat']

    def test_session_classe_et_groupe(self):
        res = self.creer()
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data['devoir_titre'], self.devoir.titre)
        self.assertEqual(res.data['classes_detail'][0]['code'], 'L1A')
        session = SessionDevoir.objects.get(pk=res.data['id'])
        self.assertEqual(session.cree_par, self.a.ens)
        self.assertTrue(AuditLog.objects.filter(action='session_quiz', details__action='creation',
                                                details__type='devoir').exists())
        self.assertEqual(self.creer(classes=[], groupes=[self.groupe.id]).status_code, 201)

    def test_classe_non_affectee_refusee(self):
        res = self.creer(classes=[self.classe_hors.id])
        self.assertEqual(res.status_code, 400)
        self.assertIn('classes', res.data)

    def test_rattrapage_etudiant_non_concerne(self):
        res = self.creer(type='rattrapage', classes=[], etudiants=[self.etu_hors.id])
        self.assertEqual(res.status_code, 400)
        self.assertIn('etudiants', res.data)

    def test_changement_de_devoir_refuse(self):
        session = self.creer().data
        autre = Devoir.objects.create(titre='Autre', filiere=self.a.filiere, annee_academique=self.a.annee,
                                      cree_par=self.a.ens)
        res = self.ens.patch(f'{S}/{session["id"]}/', {'devoir': autre.id}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('devoir', res.data)

    def test_etat_sans_session(self):
        etat = self.etat()
        self.assertTrue(etat['ouvert'])
        self.assertFalse(etat['soumis'])
        self.assertIsNone(etat['fenetre']['prochaine_ouverture'])

    def test_etat_session_future(self):
        self.creer()
        etat = self.etat()
        self.assertFalse(etat['ouvert'])
        self.assertIsNotNone(etat['fenetre']['prochaine_ouverture'])

    def test_rattrapage_rouvre_devoir_ferme(self):
        Devoir.objects.filter(pk=self.devoir.pk).update(date_debut=self.maintenant - timedelta(days=5),
                                                        date_fin=self.maintenant - timedelta(days=1))
        self.assertFalse(self.etat()['ouvert'])
        res = self.creer(type='rattrapage', classes=[], etudiants=[self.a.etu.id],
                         ouverture=iso(self.maintenant - timedelta(hours=1)),
                         fermeture=iso(self.maintenant + timedelta(hours=2)))
        self.assertEqual(res.status_code, 201, res.data)
        self.assertTrue(self.etat()['ouvert'])

    def test_etat_soumis(self):
        SoumissionDevoir.objects.create(devoir=self.devoir, etudiant=self.a.etu)
        self.assertTrue(self.etat()['soumis'])

    def test_candidats_rattrapage(self):
        autre = make_user('etu2', 'etudiant', self.a.etab)
        Inscription.objects.create(etudiant=autre, classe=self.a.classe)
        SoumissionDevoir.objects.create(devoir=self.devoir, etudiant=self.a.etu)
        res = self.ens.get(f'{D}/{self.devoir.id}/candidats_rattrapage/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual([c['id'] for c in res.data], [autre.id])
        self.assertEqual(set(res.data[0]), {'id', 'nom'})
        self.assertEqual(client_for(self.a.etu).get(f'{D}/{self.devoir.id}/candidats_rattrapage/').status_code, 403)

    def test_droits(self):
        session = self.creer().data
        autre_ens = make_user('ens2', 'enseignant', self.a.etab)
        autre = client_for(autre_ens)
        self.assertEqual(autre.get(f'{S}/{session["id"]}/').status_code, 404)
        self.assertEqual(autre.get(f'{D}/{self.devoir.id}/candidats_rattrapage/').status_code, 404)
        self.assertEqual(self.creer(client=autre).status_code, 400)
        etu = client_for(self.a.etu)
        self.assertEqual(etu.get(f'{S}/').status_code, 403)
        self.assertEqual(self.creer(client=etu).status_code, 403)
        self.assertEqual(client_for(self.a.admin).get(f'{S}/{session["id"]}/').status_code, 200)
        self.assertEqual(client_for(self.w.b.admin).get(f'{S}/{session["id"]}/').status_code, 404)

    def test_filtres(self):
        self.creer()
        res = self.ens.get(f'{S}/', {'devoir': self.devoir.id})
        donnees = res.data['results'] if 'results' in res.data else res.data
        self.assertEqual(len(donnees), 1)

    def test_annee_archivee(self):
        session = self.creer().data
        AnneeAcademique.objects.filter(pk=self.a.annee.pk).update(archivee=True)
        cas = [
            self.creer(),
            self.ens.patch(f'{S}/{session["id"]}/', {'libelle': 'X'}, format='json'),
            self.ens.delete(f'{S}/{session["id"]}/'),
        ]
        for i, res in enumerate(cas):
            with self.subTest(cas=i):
                self.assertEqual(res.status_code, 409, getattr(res, 'data', None))
                self.assertIn('est archivée', str(res.data['detail']))
