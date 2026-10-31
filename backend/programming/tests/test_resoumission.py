"""Resoumissions, historique des versions (sous-projet 4c, tâche 4)."""
import json
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.testing import build_world, client_for, make_user
from audit.models import AuditLog
from programming.models import (
    BrouillonExercice, CasDeTest, Devoir, Execution, Exercice, ReponseExercice, SoumissionDevoir, VersionSoumission,
)
from referentiel.models import AnneeAcademique, Inscription

P = '/api/programming'
DEJA_SOUMIS = "Vous avez déjà soumis ce devoir."
NOTE_VALIDEE = "Votre note est validée : ce devoir ne peut plus être modifié."
EN_COURS = "Une correction est en cours : réessayez à la fin."
FERME = "Ce devoir est fermé."


def fic(contenu, nom='main.py'):
    return [{'nom': nom, 'contenu': contenu}]


@override_settings(PEL_EXECUTEUR='factice')
class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()
        a = cls.w.a
        cls.ex1 = a.exercice
        cls.ex1.points = 4
        cls.ex1.save()
        CasDeTest.objects.filter(exercice=cls.ex1).update(entree='a', sortie_attendue='a', public=False)
        cls.ex1_cache = CasDeTest.objects.get(exercice=cls.ex1)
        CasDeTest.objects.create(exercice=cls.ex1, ordre=2, entree='CACHE_ENTREE', sortie_attendue='CACHE_SORTIE',
                                 public=False, poids=0)
        cls.ex2 = Exercice.objects.create(devoir=a.devoir, ordre=2, titre='Deuxième', points=Decimal('6'))
        CasDeTest.objects.create(exercice=cls.ex2, ordre=1, entree='b', sortie_attendue='b', public=True)

    def setUp(self):
        self.a = self.w.a
        self.etu = client_for(self.a.etu)
        self.ens = client_for(self.a.ens)
        Devoir.objects.filter(pk=self.a.devoir.pk).update(resoumission_autorisee=True)

    def corps(self, c1='print(input())', c2='print(input())', seulement=None):
        reponses = [{'exercice': self.ex1.id, 'fichiers': fic(c1)}, {'exercice': self.ex2.id, 'fichiers': fic(c2)}]
        if seulement is not None:
            reponses = [r for r in reponses if r['exercice'] == seulement]
        return {'devoir': self.a.devoir.id, 'reponses': reponses}

    def soumettre(self, client=None, **kwargs):
        return (client or self.etu).post(f'{P}/soumissions/', self.corps(**kwargs), format='json')

    def travailler(self):
        with mock.patch('programming.execution.docker.nettoyer_orphelins'):
            call_command('executer_file', '--une-fois', stdout=StringIO())

    def option(self, valeur):
        Devoir.objects.filter(pk=self.a.devoir.pk).update(resoumission_autorisee=valeur)

    def premiere_version(self, **kwargs):
        res = self.soumettre(**kwargs)
        self.assertEqual(res.status_code, 201, res.data)
        self.travailler()
        return SoumissionDevoir.objects.get(pk=res.data['id'])


class ControlesTests(Base):
    def test_option_desactivee_409_inchange(self):
        self.option(False)
        self.premiere_version()
        res = self.soumettre()
        self.assertEqual((res.status_code, str(res.data['detail'])), (409, DEJA_SOUMIS))
        self.assertFalse(VersionSoumission.objects.exists())

    def test_note_validee_409(self):
        s = self.premiere_version()
        SoumissionDevoir.objects.filter(pk=s.pk).update(statut=SoumissionDevoir.CORRIGE, score=3)
        res = self.soumettre()
        self.assertEqual((res.status_code, str(res.data['detail'])), (409, NOTE_VALIDEE))

    def test_correction_active_409(self):
        res = self.soumettre()
        self.assertEqual(res.status_code, 201)
        res = self.soumettre()
        self.assertEqual((res.status_code, str(res.data['detail'])), (409, EN_COURS))
        self.assertFalse(VersionSoumission.objects.exists())

    def test_option_avant_note_validee(self):
        self.option(False)
        s = self.premiere_version()
        SoumissionDevoir.objects.filter(pk=s.pk).update(statut=SoumissionDevoir.CORRIGE)
        self.assertEqual(str(self.soumettre().data['detail']), DEJA_SOUMIS)

    def test_exercice_deja_repondu_absent_400(self):
        self.premiere_version()
        res = self.soumettre(seulement=self.ex2.id)
        self.assertEqual(res.status_code, 400)
        self.assertIn('reponses', res.data)
        self.assertFalse(VersionSoumission.objects.exists())
        self.assertEqual(SoumissionDevoir.objects.get().numero_version, 1)

    def test_reponses_invalides_400_apres_controles_d_etat(self):
        self.premiere_version()
        res = self.etu.post(f'{P}/soumissions/', {'devoir': self.a.devoir.id, 'reponses': []}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertFalse(VersionSoumission.objects.exists())

    def test_fenetre_fermee_409(self):
        self.premiere_version()
        maintenant = timezone.now()
        Devoir.objects.filter(pk=self.a.devoir.pk).update(date_debut=maintenant - timedelta(days=2),
                                                          date_fin=maintenant - timedelta(days=1))
        res = self.soumettre()
        self.assertEqual((res.status_code, str(res.data['detail'])), (409, FERME))

    def test_annee_archivee_409(self):
        self.premiere_version()
        AnneeAcademique.objects.filter(pk=self.a.annee.pk).update(archivee=True)
        res = self.soumettre()
        self.assertEqual(res.status_code, 409)
        self.assertFalse(VersionSoumission.objects.exists())

    def test_creation_concurrente_409(self):
        with mock.patch('programming.views.SoumissionDevoir.objects.create', side_effect=IntegrityError('unique')):
            res = self.soumettre()
        self.assertEqual((res.status_code, str(res.data['detail'])), (409, DEJA_SOUMIS))

    def test_etat_relu_sous_verrou(self):
        """Une note validée entre le premier contrôle et le verrou est refusée."""
        s = self.premiere_version()
        from programming import versions
        reel = versions.verifier_resoumission

        appels = []

        def valide_puis_verifie(soumission):
            # Premier appel : contrôle avant verrou ; la note est validée juste après, avant le second.
            appels.append(soumission.pk)
            if len(appels) == 2:
                SoumissionDevoir.objects.filter(pk=s.pk).update(statut=SoumissionDevoir.CORRIGE)
                soumission.refresh_from_db()
            return reel(soumission)

        with mock.patch('programming.versions.verifier_resoumission', side_effect=valide_puis_verifie):
            res = self.soumettre()
        self.assertEqual(len(appels), 2)
        self.assertEqual((res.status_code, str(res.data['detail'])), (409, NOTE_VALIDEE))
        self.assertFalse(VersionSoumission.objects.exists())


class ResoumissionTests(Base):
    def test_archivage_complet_et_remise_a_zero(self):
        s = self.premiere_version(c1='print(input())', c2='# PEL:SORTIE=faux')
        s.refresh_from_db()
        self.assertEqual(s.statut, SoumissionDevoir.CORRIGEE_AUTO)
        self.assertEqual(s.note_proposee, Decimal('4.00'))
        SoumissionDevoir.objects.filter(pk=s.pk).update(commentaire='bien', score=3)
        date_avant = s.date_soumission
        corrections = {r.exercice_id: Execution.objects.filter(reponse=r, type=Execution.CORRECTION).get().pk
                       for r in s.reponses.all()}
        res = self.soumettre(c1='print("v2")', c2='print(input())')
        self.assertEqual(res.status_code, 201, res.data)
        v = VersionSoumission.objects.get()
        self.assertEqual((v.soumission_id, v.numero, v.date_soumission, v.soumission_auto), (s.pk, 1, date_avant, False))
        self.assertEqual(v.note_proposee, Decimal('4.00'))
        self.assertEqual(
            sorted(v.reponses, key=lambda r: r['exercice']),
            [{'exercice': self.ex1.id, 'fichiers': fic('print(input())'), 'correction': corrections[self.ex1.id]},
             {'exercice': self.ex2.id, 'fichiers': fic('# PEL:SORTIE=faux'), 'correction': corrections[self.ex2.id]}])
        s.refresh_from_db()
        self.assertEqual(s.numero_version, 2)
        self.assertGreater(s.date_soumission, date_avant)
        self.assertFalse(s.soumission_auto)
        self.assertEqual((s.note_proposee, s.score, s.commentaire), (None, None, ''))
        self.assertEqual(s.statut, SoumissionDevoir.EN_CORRECTION)
        self.assertEqual(s.reponses.count(), 2)
        self.assertEqual(s.reponses.get(exercice=self.ex1).fichiers, fic('print("v2")'))
        self.assertEqual(res.data['id'], s.pk)
        self.assertEqual(res.data['numero_version'], 2)
        self.assertEqual(res.data['statut'], 'en_correction')

    def test_nouvelle_correction_et_note_sur_derniere_version(self):
        s = self.premiere_version(c1='# PEL:SORTIE=faux', c2='print(input())')
        s.refresh_from_db()
        self.assertEqual(s.note_proposee, Decimal('6.00'))
        self.assertEqual(self.soumettre(c1='print(input())', c2='print(input())').status_code, 201)
        self.travailler()
        s.refresh_from_db()
        self.assertEqual(s.statut, SoumissionDevoir.CORRIGEE_AUTO)
        self.assertEqual(s.note_proposee, Decimal('10.00'))
        self.assertEqual(Execution.objects.filter(reponse__soumission=s, type=Execution.CORRECTION).count(), 4)

    def test_deux_resoumissions(self):
        self.premiere_version(c1='un')
        self.assertEqual(self.soumettre(c1='deux').status_code, 201)
        self.travailler()
        self.assertEqual(self.soumettre(c1='trois').status_code, 201)
        s = SoumissionDevoir.objects.get()
        self.assertEqual(s.numero_version, 3)
        self.assertEqual(sorted(s.versions.values_list('numero', flat=True)), [1, 2])
        self.assertEqual(s.versions.get(numero=2).reponses[0]['fichiers'][0]['contenu'].startswith('d'), True)

    def test_audit(self):
        self.premiere_version()
        self.soumettre()
        log = AuditLog.objects.get(action='resoumission_devoir')
        self.assertEqual((log.acteur, log.cible_id), (self.a.etu, str(SoumissionDevoir.objects.get().pk)))
        self.assertEqual(log.details['version'], 2)
        self.assertEqual(log.etablissement, self.a.etab)

    def test_brouillons_supprimes_sans_option_conserves_avec(self):
        BrouillonExercice.objects.create(etudiant=self.a.etu, exercice=self.ex1, fichiers=fic('x'))
        self.soumettre()
        self.assertEqual(BrouillonExercice.objects.count(), 1)
        BrouillonExercice.objects.all().delete()
        SoumissionDevoir.objects.all().delete()
        self.option(False)
        BrouillonExercice.objects.create(etudiant=self.a.etu, exercice=self.ex1, fichiers=fic('x'))
        voisin = make_user('voisin', 'etudiant', self.a.etab)
        BrouillonExercice.objects.create(etudiant=voisin, exercice=self.ex1, fichiers=fic('y'))
        self.assertEqual(self.soumettre().status_code, 201)
        self.assertEqual(list(BrouillonExercice.objects.values_list('etudiant_id', flat=True)), [voisin.pk])

    def test_langage_non_executable_reste_soumis(self):
        Devoir.objects.filter(pk=self.a.devoir.pk).update(langage='autre')
        self.assertEqual(self.soumettre().status_code, 201)
        SoumissionDevoir.objects.update(statut=SoumissionDevoir.SOUMIS)
        res = self.soumettre()
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(SoumissionDevoir.objects.get().statut, SoumissionDevoir.SOUMIS)
        self.assertFalse(Execution.objects.exists())


class HistoriqueTests(Base):
    def deux_versions(self):
        self.premiere_version(c1='print(input())', c2='print(input())')
        self.assertEqual(self.soumettre(c1='autre').status_code, 201)
        self.travailler()
        return SoumissionDevoir.objects.get()

    def url(self, s):
        return f'{P}/soumissions/{s.pk}/versions/'

    def test_correcteur_resultats_complets(self):
        s = self.deux_versions()
        res = self.ens.get(self.url(s))
        self.assertEqual(res.status_code, 200)
        self.assertEqual([v['numero'] for v in res.data], [1])
        v = res.data[0]
        self.assertEqual(set(v), {'numero', 'date_soumission', 'soumission_auto', 'note_proposee', 'reponses'})
        self.assertEqual(v['note_proposee'], '10.00')
        brut = json.dumps(res.data, default=str)
        self.assertIn('CACHE_SORTIE', brut)
        rep = next(r for r in v['reponses'] if r['exercice'] == self.ex1.id)
        self.assertEqual(rep['fichiers'], fic('print(input())'))
        self.assertEqual(rep['correction']['statut'], 'terminee')

    def test_etudiant_immediate_statut_et_temps_seulement(self):
        Devoir.objects.filter(pk=self.a.devoir.pk).update(politique_resultats=Devoir.IMMEDIATE)
        s = self.deux_versions()
        res = self.etu.get(self.url(s))
        self.assertEqual(res.status_code, 200)
        brut = json.dumps(res.data, default=str)
        self.assertNotIn('CACHE_ENTREE', brut)
        self.assertNotIn('CACHE_SORTIE', brut)
        v = res.data[0]
        self.assertEqual(v['note_proposee'], '10.00')
        rep = next(r for r in v['reponses'] if r['exercice'] == self.ex1.id)
        cache = [x for x in rep['correction']['resultats'] if set(x) == {'statut', 'temps_ms'}]
        self.assertEqual(len(cache), 2)

    def test_etudiant_apres_validation_ni_note_ni_resultats(self):
        s = self.deux_versions()
        res = self.etu.get(self.url(s))
        self.assertEqual(res.status_code, 200)
        v = res.data[0]
        self.assertIsNone(v['note_proposee'])
        self.assertEqual([r['correction'] for r in v['reponses']], [None, None])
        self.assertEqual(v['reponses'][0]['fichiers'], fic('print(input())'))
        self.assertNotIn('CACHE', json.dumps(res.data, default=str))

    def test_execution_supprimee_ignoree(self):
        Devoir.objects.filter(pk=self.a.devoir.pk).update(politique_resultats=Devoir.IMMEDIATE)
        s = self.deux_versions()
        Execution.objects.filter(pk=s.versions.get().reponses[0]['correction']).delete()
        for client in (self.etu, self.ens):
            res = self.client_get(client, s)
            self.assertEqual(res.status_code, 200)
            self.assertIsNone(res.data[0]['reponses'][0]['correction'])

    def client_get(self, client, s):
        return client.get(self.url(s))

    def test_autre_etudiant_404(self):
        s = self.deux_versions()
        voisin = make_user('voisin', 'etudiant', self.a.etab)
        Inscription.objects.create(etudiant=voisin, classe=self.a.classe)
        self.assertEqual(client_for(voisin).get(self.url(s)).status_code, 404)
        self.assertEqual(client_for(self.w.b.etu).get(self.url(s)).status_code, 404)
        self.assertEqual(client_for(self.w.b.ens).get(self.url(s)).status_code, 404)

    def test_sans_version_liste_vide(self):
        s = self.premiere_version()
        self.assertEqual(self.etu.get(self.url(s)).data, [])

    def test_champs_des_serialiseurs(self):
        s = self.deux_versions()
        etu = self.etu.get(f'{P}/soumissions/{s.pk}/').data
        self.assertEqual((etu['numero_version'], etu['nombre_versions'], etu['soumission_auto']), (2, 1, False))
        self.assertIs(etu['resoumission_possible'], True)
        ens = self.ens.get(f'{P}/soumissions/{s.pk}/').data
        self.assertEqual((ens['numero_version'], ens['nombre_versions']), (2, 1))
        self.assertNotIn('resoumission_possible', ens)

    def test_resoumission_possible_conditions(self):
        s = self.deux_versions()
        url = f'{P}/soumissions/{s.pk}/'

        def possible():
            return self.etu.get(url).data['resoumission_possible']

        self.assertIs(possible(), True)
        SoumissionDevoir.objects.filter(pk=s.pk).update(statut=SoumissionDevoir.CORRIGE)
        self.assertIs(possible(), False)
        SoumissionDevoir.objects.filter(pk=s.pk).update(statut=SoumissionDevoir.CORRIGEE_AUTO)
        self.option(False)
        self.assertIs(possible(), False)
        self.option(True)
        maintenant = timezone.now()
        Devoir.objects.filter(pk=self.a.devoir.pk).update(date_debut=maintenant - timedelta(days=2),
                                                          date_fin=maintenant - timedelta(days=1))
        self.assertIs(possible(), False)
        Devoir.objects.filter(pk=self.a.devoir.pk).update(date_debut=None, date_fin=None)
        self.assertIs(possible(), True)
        Execution.objects.create(type=Execution.CORRECTION, demandeur=self.a.etu, devoir=self.a.devoir,
                                 exercice=self.ex1, reponse=s.reponses.first())
        self.assertIs(possible(), False)
        Execution.objects.filter(statut=Execution.EN_ATTENTE).delete()
        AnneeAcademique.objects.filter(pk=self.a.annee.pk).update(archivee=True)
        self.assertIs(self.etu.get(url + '?archives=1').data['resoumission_possible'], False)

    def test_liste_correcteur_sans_requete_par_ligne(self):
        self.premiere_version()
        VersionSoumission.objects.create(soumission=SoumissionDevoir.objects.get(), numero=1,
                                         date_soumission=timezone.now())

        def requetes():
            with self.assertNumQueriesLess() as ctx:
                res = self.ens.get(f'{P}/soumissions/', {'devoir': self.a.devoir.id})
            self.assertEqual(res.status_code, 200)
            return len(ctx.captured_queries)

        un = requetes()
        for i in range(3):
            etu = make_user(f'extra{i}', 'etudiant', self.a.etab)
            Inscription.objects.create(etudiant=etu, classe=self.a.classe)
            s = SoumissionDevoir.objects.create(devoir=self.a.devoir, etudiant=etu)
            ReponseExercice.objects.create(soumission=s, exercice=self.ex1, fichiers=fic('x'))
            VersionSoumission.objects.create(soumission=s, numero=1, date_soumission=timezone.now())
        quatre = requetes()
        self.assertEqual(un, quatre)
        res = self.ens.get(f'{P}/soumissions/', {'devoir': self.a.devoir.id})
        donnees = res.data['results'] if 'results' in res.data else res.data
        self.assertEqual({s['nombre_versions'] for s in donnees}, {1})

    def assertNumQueriesLess(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        return CaptureQueriesContext(connection)
