"""API asynchrone d'exécution, résultats selon la politique, validation de la note (sous-projet 4b, tâche 4).

Exécuteur factice (`PEL_EXECUTEUR='factice'`) : aucun code n'est lancé ; la file est traitée par
`executer_file --une-fois`.
"""
import json
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from accounts.testing import build_world, client_for, make_user
from audit.models import AuditLog
from programming.models import (CasDeTest, Devoir, Execution, Exercice, ResultatTest, SoumissionDevoir)
from programming.tests.test_devoirs_api import exercice as exercice_payload
from referentiel.models import AnneeAcademique

P = '/api/programming'
EN_COURS = "Une exécution est déjà en cours."
TROP = "Trop d'exécutions : patientez une minute."
FERME = "Ce devoir est fermé."
PAS_OUVERT = "Ce devoir n'est pas ouvert."


def fic(contenu):
    return [{'nom': 'main.py', 'contenu': contenu}]


def traiter_file():
    call_command('executer_file', '--une-fois', stdout=StringIO(), stderr=StringIO())


@override_settings(PEL_EXECUTEUR='factice')
class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()
        a = cls.w.a
        cls.ex1 = a.exercice  # test public : entrée vide, sortie attendue « 4 » ; 20 points
        Exercice.objects.filter(pk=cls.ex1.pk).update(solution=fic('SOLUTION_SECRETE'))
        cls.cache1 = CasDeTest.objects.create(exercice=cls.ex1, ordre=2, entree='CACHE_ENTREE',
                                              sortie_attendue='CACHE_SORTIE', public=False)
        cls.ex2 = Exercice.objects.create(devoir=a.devoir, ordre=2, titre='Deuxième', points=Decimal('5.5'))
        CasDeTest.objects.create(exercice=cls.ex2, ordre=1, entree='1', sortie_attendue='2', public=True)

    def setUp(self):
        cache.clear()
        self.a = self.w.a
        self.etu = client_for(self.a.etu)
        self.ens = client_for(self.a.ens)
        self.maintenant = timezone.now()

    def executer(self, client=None, devoir=None, **corps):
        donnees = {'exercice': self.ex1.id, 'fichiers': fic('print(4)'), 'mode': 'run', 'entree': 'bonjour'}
        donnees.update(corps)
        devoir = devoir or self.a.devoir
        return (client or self.etu).post(f'{P}/devoirs/{devoir.id}/executer/', donnees, format='json')

    def dates(self, debut, fin):
        Devoir.objects.filter(pk=self.a.devoir.pk).update(date_debut=debut, date_fin=fin)

    def soumettre(self, code1='# PEL:SORTIE=4', code2='# PEL:SORTIE=2'):
        res = self.etu.post(f'{P}/soumissions/', {'devoir': self.a.devoir.id, 'reponses': [
            {'exercice': self.ex1.id, 'fichiers': fic(code1)},
            {'exercice': self.ex2.id, 'fichiers': fic(code2)},
        ]}, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        return SoumissionDevoir.objects.get(pk=res.data['id'])

    def politique(self, valeur):
        Devoir.objects.filter(pk=self.a.devoir.pk).update(politique_resultats=valeur)


class ExecuterTests(Base):
    def test_run_202_puis_resultat(self):
        res = self.executer()
        self.assertEqual(res.status_code, 202, res.data)
        self.assertEqual(set(res.data), {'id', 'statut'})
        self.assertEqual(res.data['statut'], 'en_attente')
        execution = Execution.objects.get(pk=res.data['id'])
        self.assertEqual((execution.type, execution.demandeur, execution.entree, execution.fichiers),
                         ('essai_run', self.a.etu, 'bonjour', fic('print(4)')))
        traiter_file()
        lu = self.etu.get(f'{P}/executions/{execution.id}/')
        self.assertEqual(lu.status_code, 200)
        self.assertEqual(lu.data, {
            'id': execution.id, 'type': 'essai_run', 'statut': 'terminee', 'message': '', 'compilation': '',
            'resultats': [{'statut': 'OK', 'temps_ms': 1, 'sortie': 'bonjour', 'erreurs': ''}],
        })

    def test_test_sur_les_tests_publics_seulement(self):
        res = self.executer(mode='test', fichiers=fic('# PEL:SORTIE=4'))
        self.assertEqual(res.status_code, 202, res.data)
        execution = Execution.objects.get(pk=res.data['id'])
        self.assertEqual((execution.type, execution.entree), ('essai_test', ''))
        traiter_file()
        lu = self.etu.get(f'{P}/executions/{execution.id}/')
        self.assertEqual(lu.data['resultats'], [
            {'statut': 'OK', 'temps_ms': 1, 'entree': '', 'sortie_attendue': '4', 'sortie': '4'},
        ])
        self.assertNotIn('CACHE', lu.content.decode())

    def test_une_seule_execution_active(self):
        self.assertEqual(self.executer().status_code, 202)
        res = self.executer(mode='test')
        self.assertEqual(res.status_code, 409)
        self.assertEqual(str(res.data['detail']), EN_COURS)
        Execution.objects.update(statut=Execution.EN_COURS)
        self.assertEqual(self.executer().status_code, 409)
        # Un autre utilisateur n'est pas bloqué ; après la fin, l'étudiant peut relancer.
        self.assertEqual(self.executer(client=self.ens).status_code, 202)
        Execution.objects.update(statut=Execution.TERMINEE)
        self.assertEqual(self.executer().status_code, 202)

    def test_corrections_en_file_ne_bloquent_pas_les_essais(self):
        self.soumettre()
        self.assertTrue(Execution.objects.filter(type='correction', statut='en_attente').exists())
        self.assertEqual(self.executer().status_code, 202)

    def test_limite_20_par_minute(self):
        for i in range(20):
            self.assertEqual(self.executer(mode='x').status_code, 400, i)
        res = self.executer()
        self.assertEqual(res.status_code, 429)
        self.assertEqual(str(res.data['detail']), TROP)
        self.assertFalse(Execution.objects.exists())
        # Par utilisateur : l'enseignant n'est pas concerné ; la fenêtre se rouvre quand la clé expire.
        self.assertEqual(self.executer(client=self.ens).status_code, 202)
        cache.clear()
        self.assertEqual(self.executer().status_code, 202)

    def test_fenetre_de_l_etudiant(self):
        self.dates(self.maintenant - timedelta(days=2), self.maintenant - timedelta(days=1))
        res = self.executer()
        self.assertEqual(res.status_code, 409)
        self.assertEqual(str(res.data['detail']), FERME)
        self.dates(self.maintenant + timedelta(days=1), self.maintenant + timedelta(days=2))
        self.assertEqual(str(self.executer().data['detail']), PAS_OUVERT)
        self.assertFalse(Execution.objects.exists())
        self.assertEqual(self.executer(client=self.ens).status_code, 202)

    def test_perimetre(self):
        intrus = make_user('intrus', 'etudiant', self.a.etab)
        self.assertEqual(self.executer(client=client_for(intrus)).status_code, 404)
        self.assertEqual(self.executer(client=client_for(self.w.b.ens)).status_code, 404)
        self.assertEqual(self.executer(client=client_for(self.w.b.admin)).status_code, 404)
        self.assertEqual(self.executer(client=client_for(self.a.admin)).status_code, 202)
        self.assertEqual(self.executer(client=client_for(self.w.superadmin)).status_code, 202)
        self.assertEqual(self.executer(devoir=self.w.b.devoir).status_code, 404)

    def test_annee_archivee(self):
        AnneeAcademique.objects.filter(pk=self.a.annee.pk).update(archivee=True)
        for client in (self.etu, self.ens):
            res = self.executer(client=client)
            self.assertEqual(res.status_code, 409)
            self.assertIn('est archivée', str(res.data['detail']))
        self.assertFalse(Execution.objects.exists())

    def test_corps_invalides(self):
        cas = {
            'exercice d un autre devoir': {'exercice': self.w.b.exercice.id},
            'exercice absent': {'exercice': None},
            'exercice texte': {'exercice': 'abc'},
            'mode inconnu': {'mode': 'x'},
            'mode absent': {'mode': None},
            'fichiers absents': {'fichiers': None},
            'fichiers non liste': {'fichiers': 'print(1)'},
            'chemin': {'fichiers': [{'nom': '../main.py', 'contenu': ''}]},
            'nom réservé': {'fichiers': [{'nom': 'con.py', 'contenu': ''}]},
            'point final': {'fichiers': [{'nom': 'main.py.', 'contenu': ''}]},
            'doublon casse': {'fichiers': [{'nom': 'main.py', 'contenu': ''}, {'nom': 'MAIN.py', 'contenu': ''}]},
            'NUL dans le contenu': {'fichiers': fic('print(1)\x00')},
            'entrée non texte': {'entree': ['x']},
            'NUL dans l entrée': {'entree': 'a\x00b'},
            'entrée trop longue': {'entree': 'x' * 100001},
        }
        for nom, corps in cas.items():
            with self.subTest(cas=nom):
                cache.clear()
                res = self.executer(**corps)
                self.assertEqual(res.status_code, 400, res.data)
        self.assertEqual(self.etu.post(f'{P}/devoirs/{self.a.devoir.id}/executer/', [1], format='json').status_code,
                         400)
        self.assertFalse(Execution.objects.exists())

    def test_langage_non_pris_en_charge(self):
        Devoir.objects.filter(pk=self.a.devoir.pk).update(langage='autre')
        res = self.executer()
        self.assertEqual(res.status_code, 400)
        self.assertEqual(str(res.data['detail']), "Ce langage n'est pas pris en charge par le service d'exécution.")

    def test_ancienne_route_retiree(self):
        res = self.etu.post(f'{P}/devoirs/{self.a.devoir.id}/execute/', {'exercice': self.ex1.id, 'code': 'x'},
                            format='json')
        self.assertEqual(res.status_code, 404)


class ConsultationExecutionTests(Base):
    def essai(self, client=None, **corps):
        res = self.executer(client=client, **corps)
        self.assertEqual(res.status_code, 202, res.data)
        return Execution.objects.get(pk=res.data['id'])

    def test_droits(self):
        execution = self.essai()
        url = f'{P}/executions/{execution.id}/'
        autre = make_user('autre', 'etudiant', self.a.etab)
        self.assertEqual(client_for(autre).get(url).status_code, 404)
        self.assertEqual(client_for(self.w.b.ens).get(url).status_code, 404)
        self.assertEqual(client_for(self.w.b.admin).get(url).status_code, 404)
        for client in (self.etu, self.ens, client_for(self.a.admin), client_for(self.w.superadmin)):
            self.assertEqual(client.get(url).status_code, 200)
        self.assertEqual(self.etu.get(f'{P}/executions/999999/').status_code, 404)
        # Lecture seule : pas de liste, ni d'écriture.
        self.assertEqual(self.etu.get(f'{P}/executions/').status_code, 404)
        self.assertEqual(self.ens.delete(url).status_code, 405)

    def test_essai_d_un_enseignant_invisible_pour_un_autre_enseignant(self):
        execution = self.essai(client=self.ens)
        autre = make_user('ens2', 'enseignant', self.a.etab)
        self.assertEqual(client_for(autre).get(f'{P}/executions/{execution.id}/').status_code, 404)

    def test_l_etudiant_ne_voit_jamais_un_test_cache(self):
        # Même si un résultat d'essai porte un test caché (test devenu caché, données anciennes), il est réduit.
        execution = self.essai(mode='test')
        Execution.objects.filter(pk=execution.pk).update(statut=Execution.TERMINEE)
        public = self.ex1.tests.get(public=True)
        ResultatTest.objects.create(execution=execution, cas=public, ordre=0, statut='OK', temps_ms=3, sortie='4')
        ResultatTest.objects.create(execution=execution, cas=self.cache1, ordre=1, statut='WA', temps_ms=4,
                                    sortie='CACHE_SORTIE_OBTENUE', erreurs='CACHE_ERREURS')
        res = self.etu.get(f'{P}/executions/{execution.id}/')
        self.assertEqual(res.data['resultats'], [
            {'statut': 'OK', 'temps_ms': 3, 'entree': '', 'sortie_attendue': '4', 'sortie': '4'},
            {'statut': 'WA', 'temps_ms': 4},
        ])
        self.assertNotIn('CACHE', res.content.decode())
        self.assertNotIn('SOLUTION_SECRETE', res.content.decode())
        ens = self.ens.get(f'{P}/executions/{execution.id}/')
        self.assertEqual(ens.data['resultats'][1], {
            'ordre': 1, 'cas': self.cache1.id, 'public': False, 'statut': 'WA', 'temps_ms': 4,
            'entree': 'CACHE_ENTREE', 'sortie_attendue': 'CACHE_SORTIE', 'sortie': 'CACHE_SORTIE_OBTENUE',
            'erreurs': 'CACHE_ERREURS',
        })

    def test_corrections_hors_de_la_route_etudiant(self):
        soumission = self.soumettre()
        correction = Execution.objects.filter(reponse__soumission=soumission).first()
        traiter_file()
        self.assertEqual(self.etu.get(f'{P}/executions/{correction.id}/').status_code, 404)
        res = self.ens.get(f'{P}/executions/{correction.id}/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['type'], 'correction')
        self.assertEqual([r['entree'] for r in res.data['resultats']], ['', 'CACHE_ENTREE'])

    def test_service_indisponible(self):
        execution = self.essai(fichiers=fic('# PEL:INDISPONIBLE'))
        traiter_file()
        res = self.etu.get(f'{P}/executions/{execution.id}/')
        self.assertEqual((res.data['statut'], res.data['message'], res.data['resultats']),
                         ('erreur', "Le service d'exécution est indisponible.", []))


class SoumissionCorrectionTests(Base):
    def test_soumission_corrigee_automatiquement(self):
        soumission = self.soumettre()
        self.assertEqual(soumission.statut, 'en_correction')
        corrections = Execution.objects.filter(type='correction', reponse__soumission=soumission)
        self.assertEqual(corrections.count(), 2)
        self.assertTrue(all(c.statut == 'en_attente' and c.demandeur == self.a.etu for c in corrections))
        traiter_file()
        soumission.refresh_from_db()
        # Exercice 1 : seul le test caché compte (échoué) -> 0 ; exercice 2 : test public seul, réussi -> 5,5.
        self.assertEqual((soumission.statut, soumission.note_proposee, soumission.score),
                         ('corrigee_auto', Decimal('5.50'), None))

    def test_doublon_ne_remet_pas_en_correction(self):
        soumission = self.soumettre()
        traiter_file()
        res = self.etu.post(f'{P}/soumissions/', {'devoir': self.a.devoir.id, 'reponses': [
            {'exercice': self.ex1.id, 'fichiers': fic('x')}]}, format='json')
        self.assertEqual(res.status_code, 409)
        self.assertEqual(Execution.objects.filter(type='correction').count(), 2)
        soumission.refresh_from_db()
        self.assertEqual(soumission.statut, 'corrigee_auto')

    def test_langage_autre_reste_soumis(self):
        Devoir.objects.filter(pk=self.a.devoir.pk).update(langage='autre')
        soumission = self.soumettre()
        self.assertEqual(soumission.statut, 'soumis')
        self.assertFalse(Execution.objects.exists())

    def test_vue_enseignant(self):
        soumission = self.soumettre()
        traiter_file()
        res = self.ens.get(f'{P}/soumissions/{soumission.id}/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual((res.data['statut'], res.data['note_proposee'], res.data['score']),
                         ('corrigee_auto', '5.50', None))
        correction = res.data['reponses'][0]['correction']
        self.assertEqual(correction['type'], 'correction')
        self.assertEqual(correction['statut'], 'terminee')
        self.assertEqual([(r['public'], r['statut'], r['entree'], r['sortie_attendue']) for r in correction['resultats']],
                         [(True, 'OK', '', '4'), (False, 'WA', 'CACHE_ENTREE', 'CACHE_SORTIE')])

    def test_politique_apres_validation(self):
        soumission = self.soumettre()
        lu = self.etu.get(f'{P}/soumissions/{soumission.id}/')
        self.assertEqual((lu.data['statut'], lu.data['resultats_visibles']), ('en_correction', False))
        traiter_file()
        lu = self.etu.get(f'{P}/soumissions/{soumission.id}/')
        self.assertEqual(lu.data['statut'], 'corrigee_auto')
        self.assertEqual((lu.data['resultats_visibles'], lu.data['note_proposee'], lu.data['score']),
                         (False, None, None))
        self.assertEqual([r['correction'] for r in lu.data['reponses']], [None, None])
        self.assertNotIn('CACHE', lu.content.decode())
        liste = self.etu.get(f'{P}/soumissions/')
        lignes = liste.data['results'] if 'results' in liste.data else liste.data
        self.assertEqual([(s['note_proposee'], s['reponses'][0]['correction']) for s in lignes], [(None, None)])
        self.assertNotIn('CACHE', liste.content.decode())
        # Après validation : note validée et résultats limités.
        self.assertEqual(self.ens.post(f'{P}/soumissions/{soumission.id}/corriger/', {'commentaire': 'Bien'},
                                       format='json').status_code, 200)
        lu = self.etu.get(f'{P}/soumissions/{soumission.id}/')
        self.assertEqual((lu.data['statut'], lu.data['resultats_visibles'], lu.data['score'], lu.data['commentaire']),
                         ('corrige', True, 6, 'Bien'))
        self.assertEqual(lu.data['note_proposee'], '5.50')
        self.assertEqual(lu.data['reponses'][0]['correction']['resultats'], [
            {'statut': 'OK', 'temps_ms': 1, 'entree': '', 'sortie_attendue': '4', 'sortie': '4'},
            {'statut': 'WA', 'temps_ms': 1},
        ])
        self.assertNotIn('CACHE', lu.content.decode())
        self.assertNotIn('SOLUTION_SECRETE', lu.content.decode())

    def test_politique_immediate(self):
        self.politique('immediate')
        soumission = self.soumettre()
        lu = self.etu.get(f'{P}/soumissions/{soumission.id}/')
        self.assertEqual((lu.data['resultats_visibles'], lu.data['note_proposee']), (False, None))
        traiter_file()
        lu = self.etu.get(f'{P}/soumissions/{soumission.id}/')
        self.assertEqual((lu.data['statut'], lu.data['resultats_visibles'], lu.data['note_proposee'],
                          lu.data['score']), ('corrigee_auto', True, '5.50', None))
        self.assertEqual([r['statut'] for r in lu.data['reponses'][0]['correction']['resultats']], ['OK', 'WA'])
        self.assertEqual(lu.data['reponses'][0]['correction']['resultats'][1], {'statut': 'WA', 'temps_ms': 1})
        contenu = lu.content.decode()
        self.assertNotIn('CACHE', contenu)
        self.assertNotIn('SOLUTION_SECRETE', contenu)
        self.assertNotIn('CACHE', self.etu.get(f'{P}/soumissions/').content.decode())

    def test_devoir_etudiant_sans_solution_ni_test_cache(self):
        contenu = self.etu.get(f'{P}/devoirs/{self.a.devoir.id}/').content.decode()
        self.assertNotIn('CACHE', contenu)
        self.assertNotIn('SOLUTION_SECRETE', contenu)


class CorrigerTests(Base):
    def url(self, soumission):
        return f'{P}/soumissions/{soumission.id}/corriger/'

    def test_sans_score_note_proposee_arrondie(self):
        soumission = self.soumettre()
        traiter_file()
        res = self.ens.post(self.url(soumission), {}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual((res.data['statut'], res.data['score'], res.data['note_proposee']), ('corrige', 6, '5.50'))
        self.assertEqual(AuditLog.objects.get(action='saisie_note').details['apres'], 6)

    def test_arrondi_borne_au_bareme(self):
        soumission = SoumissionDevoir.objects.create(devoir=self.a.devoir, etudiant=self.a.etu,
                                                     statut='corrigee_auto', note_proposee=Decimal('25.50'))
        res = self.ens.post(self.url(soumission), {}, format='json')
        self.assertEqual(res.data['score'], 25)  # barème 25,5 -> au plus 25
        SoumissionDevoir.objects.filter(pk=soumission.pk).update(note_proposee=Decimal('4.49'))
        self.assertEqual(self.ens.post(self.url(soumission), {'score': None}, format='json').data['score'], 4)

    def test_score_explicite_prioritaire(self):
        soumission = self.soumettre()
        traiter_file()
        res = self.ens.post(self.url(soumission), {'score': 12, 'commentaire': 'Ajusté'}, format='json')
        self.assertEqual((res.data['score'], res.data['commentaire'], res.data['statut']), (12, 'Ajusté', 'corrige'))

    def test_ni_score_ni_note_proposee(self):
        soumission = SoumissionDevoir.objects.create(devoir=self.a.devoir, etudiant=self.a.etu)
        res = self.ens.post(self.url(soumission), {'commentaire': 'x'}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(str(res.data['score']), "Aucune note proposée : indiquez un score.")
        soumission.refresh_from_db()
        self.assertEqual((soumission.statut, soumission.score), ('soumis', None))


class RecorrigerTests(Base):
    def url(self, soumission):
        return f'{P}/soumissions/{soumission.id}/recorriger/'

    def test_relance_les_corrections_en_erreur(self):
        soumission = self.soumettre(code2='# PEL:INDISPONIBLE')
        traiter_file()
        soumission.refresh_from_db()
        self.assertEqual(soumission.statut, 'en_correction')
        res = self.ens.post(self.url(soumission), {}, format='json')
        self.assertEqual(res.status_code, 202, res.data)
        self.assertEqual(res.data['statut'], 'en_correction')
        relancees = list(Execution.objects.filter(reponse__soumission=soumission, statut='en_attente'))
        self.assertEqual([e.exercice_id for e in relancees], [self.ex2.id])
        # Déjà en file : 409.
        res = self.ens.post(self.url(soumission), {'tout': True}, format='json')
        self.assertEqual(res.status_code, 409)
        self.assertEqual(str(res.data['detail']), "Une correction est déjà en cours pour cette soumission.")
        Execution.objects.filter(pk__in=[e.pk for e in relancees]).update(statut=Execution.EN_COURS)
        self.assertEqual(self.ens.post(self.url(soumission), {}, format='json').status_code, 409)
        # Le service revient : la correction relancée aboutit.
        Execution.objects.filter(pk__in=[e.pk for e in relancees]).update(statut=Execution.EN_ATTENTE)
        soumission.reponses.filter(exercice=self.ex2).update(fichiers=fic('# PEL:SORTIE=2'))
        traiter_file()
        soumission.refresh_from_db()
        self.assertEqual((soumission.statut, soumission.note_proposee), ('corrigee_auto', Decimal('5.50')))

    def test_rien_a_relancer_puis_tout(self):
        soumission = self.soumettre()
        traiter_file()
        res = self.ens.post(self.url(soumission), {}, format='json')
        self.assertEqual(res.status_code, 409)
        self.assertEqual(str(res.data['detail']), "Aucune correction en erreur à relancer.")
        res = self.ens.post(self.url(soumission), {'tout': True}, format='json')
        self.assertEqual(res.status_code, 202)
        self.assertEqual(Execution.objects.filter(reponse__soumission=soumission, statut='en_attente').count(), 2)
        traiter_file()
        soumission.refresh_from_db()
        self.assertEqual(soumission.statut, 'corrigee_auto')

    def test_soumission_ancienne_jamais_corrigee(self):
        soumission = SoumissionDevoir.objects.create(devoir=self.a.devoir, etudiant=self.a.etu)
        soumission.reponses.create(exercice=self.ex2, fichiers=fic('# PEL:SORTIE=2'))
        self.assertEqual(self.ens.post(self.url(soumission), {}, format='json').status_code, 202)
        traiter_file()
        soumission.refresh_from_db()
        self.assertEqual((soumission.statut, soumission.note_proposee), ('corrigee_auto', Decimal('5.50')))

    def test_gardes(self):
        soumission = self.soumettre()
        traiter_file()
        self.assertEqual(self.etu.post(self.url(soumission), {}, format='json').status_code, 403)
        self.assertEqual(client_for(self.w.b.ens).post(self.url(soumission), {}, format='json').status_code, 404)
        self.assertEqual(self.ens.post(self.url(soumission), {'tout': 'oui'}, format='json').status_code, 400)
        self.assertEqual(self.ens.post(self.url(soumission), [1], format='json').status_code, 400)
        self.ens.post(f'{P}/soumissions/{soumission.id}/corriger/', {}, format='json')
        res = self.ens.post(self.url(soumission), {'tout': True}, format='json')
        self.assertEqual(res.status_code, 409)
        self.assertEqual(str(res.data['detail']),
                         "Cette soumission est déjà validée : sa correction ne peut plus être relancée.")

    def test_langage_autre(self):
        soumission = SoumissionDevoir.objects.create(devoir=self.a.devoir, etudiant=self.a.etu)
        Devoir.objects.filter(pk=self.a.devoir.pk).update(langage='autre')
        res = self.ens.post(self.url(soumission), {'tout': True}, format='json')
        self.assertEqual(res.status_code, 409)

    def test_annee_archivee(self):
        soumission = self.soumettre(code2='# PEL:INDISPONIBLE')
        traiter_file()
        AnneeAcademique.objects.filter(pk=self.a.annee.pk).update(archivee=True)
        for url, corps in ((self.url(soumission), {}), (f'{P}/soumissions/{soumission.id}/corriger/', {'score': 1})):
            res = self.ens.post(url, corps, format='json')
            self.assertEqual(res.status_code, 409)
            self.assertIn('est archivée', str(res.data['detail']))
        self.assertFalse(Execution.objects.filter(statut='en_attente').exists())


class ValidationExerciceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def creer(self, **extra):
        a = self.w.a
        return client_for(a.ens).post(f'{P}/devoirs/', {
            'titre': 'TP budget', 'filiere': a.filiere.id, 'langage': 'python', 'classes': [a.classe.id],
            'exercices': [exercice_payload(**extra)]}, format='json')

    @staticmethod
    def cas_tests(nombre):
        return [{'entree': str(i), 'sortie_attendue': str(i), 'public': i == 0} for i in range(nombre)]

    def test_budget_des_tests(self):
        self.assertEqual(self.creer(tests=self.cas_tests(70)).status_code, 201)  # 70 x 2000 = 140 000 ms
        res = self.creer(tests=self.cas_tests(71))
        self.assertEqual(res.status_code, 400)
        self.assertEqual(str(res.data['exercices'][0]['tests'][0]),
                         "Le nombre de tests multiplié par la limite de temps ne doit pas dépasser 140000 ms "
                         "(140 s) : ici 71 tests de 2000 ms.")
        self.assertEqual(self.creer(tests=self.cas_tests(100), limite_temps_ms=1400).status_code, 201)
        self.assertEqual(self.creer(tests=self.cas_tests(15), limite_temps_ms=10000).status_code, 400)

    def test_fichiers(self):
        refuses = {
            'nom réservé': [{'nom': 'NUL.py', 'contenu': ''}],
            'deux-points': [{'nom': 'c:main.py', 'contenu': ''}],
            'point final': [{'nom': 'main.py.', 'contenu': ''}],
            'contrôle': [{'nom': 'ma\tin.py', 'contenu': ''}],
            'doublon casse': [{'nom': 'Main.py', 'contenu': ''}, {'nom': 'main.py', 'contenu': ''}],
            'NUL': [{'nom': 'main.py', 'contenu': 'a\x00'}],
        }
        for nom, fichiers in refuses.items():
            with self.subTest(cas=nom):
                self.assertEqual(self.creer(fichiers_initiaux=fichiers).status_code, 400)
        self.assertEqual(self.creer(solution=[{'nom': 'main.py', 'contenu': '\x00'}]).status_code, 400)
        self.assertEqual(self.creer(fichiers_initiaux=[{'nom': 'a..b.py', 'contenu': ''}]).status_code, 201)


def brut(client, url, corps):
    """POST d'un JSON échappé : `\\ud800` redevient un demi-codet isolé une fois décodé par le serveur."""
    return client.post(url, data=json.dumps(corps), content_type='application/json')


DEMI = '\ud800'


class EntreesNonEncodablesTests(Base):
    def test_executer(self):
        url = f'{P}/devoirs/{self.a.devoir.id}/executer/'
        base = {'exercice': self.ex1.id, 'fichiers': fic('print(1)'), 'mode': 'run', 'entree': ''}
        cas = {
            'nom': {**base, 'fichiers': [{'nom': f'a{DEMI}.py', 'contenu': ''}]},
            'nom en double': {**base, 'fichiers': [{'nom': f'a{DEMI}.py', 'contenu': ''}] * 2},
            'contenu': {**base, 'fichiers': fic(f'x{DEMI}')},
            'entree': {**base, 'entree': f'x{DEMI}'},
        }
        for nom, corps in cas.items():
            with self.subTest(cas=nom):
                cache.clear()
                self.assertEqual(brut(self.etu, url, corps).status_code, 400)
        self.assertFalse(Execution.objects.exists())

    def test_soumission_et_devoir(self):
        res = brut(self.etu, f'{P}/soumissions/', {'devoir': self.a.devoir.id, 'reponses': [
            {'exercice': self.ex1.id, 'fichiers': [{'nom': f'm{DEMI}.py', 'contenu': ''}]}]})
        self.assertEqual(res.status_code, 400)
        self.assertFalse(SoumissionDevoir.objects.exists())
        res = brut(self.ens, f'{P}/devoirs/', {
            'titre': 'TP', 'filiere': self.a.filiere.id, 'langage': 'python', 'classes': [self.a.classe.id],
            'exercices': [exercice_payload(fichiers_initiaux=[{'nom': f'm{DEMI}.py', 'contenu': ''}])]})
        self.assertEqual(res.status_code, 400)

    def test_commentaire(self):
        soumission = SoumissionDevoir.objects.create(devoir=self.a.devoir, etudiant=self.a.etu)
        url = f'{P}/soumissions/{soumission.id}/corriger/'
        for commentaire in (f'x{DEMI}', 'a\x00b'):
            self.assertEqual(brut(self.ens, url, {'score': 3, 'commentaire': commentaire}).status_code, 400)
        soumission.refresh_from_db()
        self.assertEqual(soumission.statut, 'soumis')

    def test_donnees_anciennes_affichables(self):
        soumission = SoumissionDevoir.objects.create(devoir=self.a.devoir, etudiant=self.a.etu, statut='corrige',
                                                     score=3, commentaire='ok')
        # Le JSON stocké échappe le demi-codet (SQLite comme PostgreSQL acceptent alors l'écriture).
        soumission.reponses.create(exercice=self.ex1, fichiers=[{'nom': f'm{DEMI}.py', 'contenu': DEMI}])
        for client, url in ((self.ens, f'{P}/soumissions/'), (self.ens, f'{P}/soumissions/{soumission.id}/'),
                            (self.etu, f'{P}/soumissions/'), (self.etu, f'{P}/soumissions/{soumission.id}/')):
            with self.subTest(url=url):
                res = client.get(url)
                self.assertEqual(res.status_code, 200)
                self.assertIn('m�.py', res.content.decode())


class ListeSoumissionsTests(Base):
    def lignes(self, res):
        return res.data['results'] if 'results' in res.data else res.data

    def test_resume_sans_sorties(self):
        soumission = self.soumettre(code1='# PEL:SORTIE=SORTIE_ETUDIANT_LONGUE')
        traiter_file()
        res = self.ens.get(f'{P}/soumissions/', {'devoir': self.a.devoir.id})
        self.assertEqual(res.status_code, 200)
        ligne = self.lignes(res)[0]
        self.assertEqual((ligne['id'], ligne['statut'], ligne['note_proposee']),
                         (soumission.id, 'corrigee_auto', '5.50'))
        correction = ligne['reponses'][0]['correction']
        self.assertEqual(set(correction), {'id', 'statut', 'message', 'nombre_tests', 'compteurs'})
        self.assertEqual((correction['statut'], correction['nombre_tests'], correction['compteurs']),
                         ('terminee', 2, {'WA': 2}))
        self.assertNotIn('"sortie"', res.content.decode())
        self.assertNotIn('"erreurs"', res.content.decode())
        self.assertNotIn('CACHE', res.content.decode())
        # Le détail garde les résultats complets.
        detail = self.ens.get(f'{P}/soumissions/{soumission.id}/')
        self.assertEqual(detail.data['reponses'][0]['correction']['resultats'][0]['sortie'], 'SORTIE_ETUDIANT_LONGUE')
        self.assertEqual(len(detail.data['reponses'][0]['correction']['resultats']), 2)

    def test_pas_de_requete_par_soumission(self):
        def compter():
            with CaptureQueriesContext(connection) as requetes:
                self.assertEqual(self.ens.get(f'{P}/soumissions/', {'devoir': self.a.devoir.id}).status_code, 200)
            return len(requetes)

        self.soumettre()
        traiter_file()
        une = compter()
        for i in range(3):
            etu = make_user(f'etu_liste{i}', 'etudiant', self.a.etab)
            self.a.devoir.etudiants.add(etu)
            self.etu = client_for(etu)
            self.soumettre()
        traiter_file()
        self.assertEqual(compter(), une)


class CorrigerConcurrenceTests(Base):
    def test_correction_en_cours_sans_score_409(self):
        soumission = self.soumettre()
        url = f'{P}/soumissions/{soumission.id}/corriger/'
        res = self.ens.post(url, {}, format='json')
        self.assertEqual(res.status_code, 409)
        self.assertEqual(str(res.data['detail']),
                         "Une correction est en cours : attendez son résultat ou indiquez une note.")
        res = self.ens.post(url, {'score': 9}, format='json')
        self.assertEqual((res.status_code, res.data['score'], res.data['statut']), (200, 9, 'corrige'))

    def test_note_proposee_du_worker_preservee(self):
        soumission = SoumissionDevoir.objects.create(devoir=self.a.devoir, etudiant=self.a.etu,
                                                     statut='corrigee_auto', note_proposee=Decimal('2'))

        def worker_entre_temps(*args):
            SoumissionDevoir.objects.filter(pk=soumission.pk).update(note_proposee=Decimal('10.40'))

        with mock.patch('programming.views.SoumissionDevoirViewSet.verifier_ecriture',
                        side_effect=worker_entre_temps):
            res = self.ens.post(f'{P}/soumissions/{soumission.id}/corriger/', {'commentaire': 'ok'}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        soumission.refresh_from_db()
        self.assertEqual((soumission.score, soumission.note_proposee, soumission.statut),
                         (10, Decimal('10.40'), 'corrige'))


class EssaiActifSerialiseTests(Base):
    def test_ecriture_avant_le_controle(self):
        with CaptureQueriesContext(connection) as requetes:
            self.assertEqual(self.executer().status_code, 202)
        sql = [q['sql'] for q in requetes.captured_queries]
        verrou = next(i for i, q in enumerate(sql) if q.startswith('UPDATE') and 'last_login' in q)
        controle = next(i for i, q in enumerate(sql) if q.startswith('SELECT') and 'programming_execution' in q)
        self.assertLess(verrou, controle)


class ResultatSansCasTests(Base):
    def test_correction_sans_cas_reduite_au_statut(self):
        self.politique('immediate')
        soumission = self.soumettre()
        traiter_file()
        correction = Execution.objects.filter(reponse__soumission=soumission, exercice=self.ex1).first()
        ResultatTest.objects.create(execution=correction, cas=None, ordre=5, statut='RE', temps_ms=2,
                                    sortie='SORTIE_SANS_CAS', erreurs='ERREUR_SANS_CAS')
        res = self.etu.get(f'{P}/soumissions/{soumission.id}/')
        self.assertEqual(res.data['reponses'][0]['correction']['resultats'][-1], {'statut': 'RE', 'temps_ms': 2})
        self.assertNotIn('SANS_CAS', res.content.decode())
