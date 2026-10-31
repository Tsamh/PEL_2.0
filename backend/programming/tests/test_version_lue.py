"""Note validée sur la version lue, suppression d'une soumission, ordre des verrous."""
from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.db import connection, transaction
from django.db.models.query import QuerySet
from django.test import TestCase
from django.utils import timezone

from accounts.testing import build_world, client_for
from programming import cloture
from programming.execution.file import apres_correction
from programming.models import BrouillonExercice, Devoir, Execution, SoumissionDevoir

P = '/api/programming'
MESSAGE = "L'étudiant a soumis une nouvelle version : rechargez la soumission."


def fic(contenu):
    return [{'nom': 'main.py', 'contenu': contenu}]


class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def setUp(self):
        cache.clear()
        self.a = self.w.a
        self.devoir = self.a.devoir
        self.ex = self.a.exercice
        self.etu = client_for(self.a.etu)
        self.ens = client_for(self.a.ens)
        Devoir.objects.filter(pk=self.devoir.pk).update(resoumission_autorisee=True)

    def soumettre(self, code):
        res = self.etu.post(f'{P}/soumissions/', {'devoir': self.devoir.id, 'reponses': [
            {'exercice': self.ex.id, 'fichiers': fic(code)}]}, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        Execution.objects.all().update(statut=Execution.TERMINEE)
        SoumissionDevoir.objects.filter(pk=res.data['id']).update(statut=SoumissionDevoir.CORRIGEE_AUTO)
        return res.data['id']

    def corriger(self, sid, **corps):
        return self.ens.post(f'{P}/soumissions/{sid}/corriger/', corps, format='json')


class VersionLueTests(Base):
    def test_version_perimee_409_rien_ecrit(self):
        sid = self.soumettre('v1')
        self.soumettre('v2')
        res = self.corriger(sid, score=5, commentaire='lu sur v1', numero_version=1)
        self.assertEqual(res.status_code, 409, res.data)
        self.assertEqual(str(res.data['detail']), MESSAGE)
        s = SoumissionDevoir.objects.get(pk=sid)
        self.assertEqual((s.statut, s.score, s.commentaire, s.numero_version),
                         (SoumissionDevoir.CORRIGEE_AUTO, None, '', 2))

    def test_bonne_version(self):
        sid = self.soumettre('v1')
        self.soumettre('v2')
        res = self.corriger(sid, score=5, numero_version=2)
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(SoumissionDevoir.objects.get(pk=sid).score, 5)
        self.assertEqual(self.corriger(sid, score=6, numero_version='2').status_code, 200)

    def test_version_absente(self):
        sid = self.soumettre('v1')
        self.soumettre('v2')
        self.assertEqual(self.corriger(sid, score=5).status_code, 200)
        self.assertEqual(self.corriger(sid, score=6, numero_version=None).status_code, 200)

    def test_version_invalide_400(self):
        sid = self.soumettre('v1')
        for valeur in ('abc', '', True, 1.5, 0, -1, [1], {'a': 1}):
            res = self.corriger(sid, score=5, numero_version=valeur)
            self.assertEqual(res.status_code, 400, (valeur, res.data))
            self.assertIn('numero_version', res.data)
        self.assertIsNone(SoumissionDevoir.objects.get(pk=sid).score)


class SuppressionSoumissionTests(Base):
    def test_suppression_ne_recree_pas_la_soumission(self):
        sid = self.soumettre('v1')
        res = self.etu.put(f'{P}/devoirs/{self.devoir.id}/brouillons/',
                           {'exercice': self.ex.id, 'fichiers': fic('suite')}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        fin = timezone.now() - timedelta(minutes=5)
        Devoir.objects.filter(pk=self.devoir.pk).update(date_debut=fin - timedelta(hours=1), date_fin=fin)
        self.assertEqual(self.ens.delete(f'{P}/soumissions/{sid}/').status_code, 204)
        self.assertFalse(BrouillonExercice.objects.filter(etudiant=self.a.etu, exercice__devoir=self.devoir).exists())
        self.assertEqual(cloture.cloturer_devoirs_echus(), 0)
        self.assertFalse(SoumissionDevoir.objects.filter(devoir=self.devoir, etudiant=self.a.etu).exists())

    def test_seuls_les_brouillons_de_cet_etudiant(self):
        sid = self.soumettre('v1')
        autre = BrouillonExercice.objects.create(etudiant=self.a.resp, exercice=self.ex, fichiers=fic('autre'))
        self.assertEqual(self.ens.delete(f'{P}/soumissions/{sid}/').status_code, 204)
        self.assertTrue(BrouillonExercice.objects.filter(pk=autre.pk).exists())


class OrdreDesVerrousTests(Base):
    """Les trois lectures verrouillées de la soumission ne verrouillent pas le devoir joint (`of=('self',)`)."""

    def verrous(self):
        appels = []
        origine = QuerySet.select_for_update

        def espion(qs, *args, **kwargs):
            appels.append((qs.model.__name__, kwargs.get('of')))
            return origine(qs, *args, **kwargs)
        return appels, mock.patch.object(QuerySet, 'select_for_update', espion)

    def test_resoumission(self):
        self.soumettre('v1')
        appels, espion = self.verrous()
        with espion:
            self.soumettre('v2')
        self.assertEqual(appels, [('Devoir', None), ('SoumissionDevoir', ('self',))])

    def test_validation(self):
        sid = self.soumettre('v1')
        appels, espion = self.verrous()
        with espion:
            self.assertEqual(self.corriger(sid, score=5).status_code, 200)
        self.assertEqual(appels, [('SoumissionDevoir', ('self',))])

    def test_relance_devoir_puis_soumission(self):
        sid = self.soumettre('v1')
        appels, espion = self.verrous()
        with espion:
            res = self.ens.post(f'{P}/soumissions/{sid}/recorriger/', {'tout': True}, format='json')
        self.assertEqual(res.status_code, 202, res.data)
        self.assertEqual(appels, [('Devoir', None), ('SoumissionDevoir', ('self',))])

    def test_fin_de_correction(self):
        sid = self.soumettre('v1')
        SoumissionDevoir.objects.filter(pk=sid).update(statut=SoumissionDevoir.EN_CORRECTION)
        appels, espion = self.verrous()
        with espion:
            self.assertTrue(apres_correction(Execution.objects.filter(reponse__soumission_id=sid).first()))
        self.assertEqual(appels, [('SoumissionDevoir', ('self',))])

    def test_sql_avec_les_capacites_de_postgresql(self):
        """`of` n'est pas refusé par SQLite (sans FOR UPDATE) ; avec FOR UPDATE, seule la soumission est visée."""
        sid = self.soumettre('v1')
        qs = SoumissionDevoir.objects.select_for_update(of=('self',)).select_related('devoir', 'etudiant').filter(pk=sid)
        with transaction.atomic():
            self.assertEqual(qs.get().pk, sid)
            capacites = {'has_select_for_update': True, 'has_select_for_update_of': True}
            with mock.patch.multiple(connection.features, create=True, **capacites):
                sql = qs.query.get_compiler(using='default').as_sql()[0]
        self.assertIn('FOR UPDATE OF "programming_soumissiondevoir"', sql)
        self.assertNotIn('programming_devoir', sql.split('FOR UPDATE')[1])
