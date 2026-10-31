"""Modification d'un devoir sans soumission : exercices mis à jour sur place, identifiants et brouillons conservés."""
from django.core.cache import cache
from django.test import TestCase

from accounts.testing import build_world, client_for
from programming.execution.executeur import _cas, _resultats
from programming.models import BrouillonExercice, CasDeTest, Devoir, Execution, Exercice, ResultatTest, SoumissionDevoir
from programming.serializers import MESSAGE_VERROU

P = '/api/programming'


def fic(contenu):
    return [{'nom': 'main.py', 'contenu': contenu}]


class ExercicesSurPlaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def setUp(self):
        cache.clear()
        self.a = self.w.a
        self.devoir = self.a.devoir
        self.ens = client_for(self.a.ens)
        self.etu = client_for(self.a.etu)
        self.ex_a = self.a.exercice
        self.ex_b = Exercice.objects.create(devoir=self.devoir, ordre=2, titre='Exercice B', points=5)
        self.ex_c = Exercice.objects.create(devoir=self.devoir, ordre=3, titre='Exercice C', points=5)
        for exercice in (self.ex_a, self.ex_b, self.ex_c):
            self.brouillon(exercice, f'travail {exercice.pk}')

    def brouillon(self, exercice, contenu):
        res = self.etu.put(f'{P}/devoirs/{self.devoir.id}/brouillons/',
                           {'exercice': exercice.id, 'fichiers': fic(contenu)}, format='json')
        self.assertEqual(res.status_code, 200, res.data)

    def lire(self):
        return [dict(e) for e in self.ens.get(f'{P}/devoirs/{self.devoir.id}/').data['exercices']]

    def envoyer(self, exercices, statut=200):
        res = self.ens.patch(f'{P}/devoirs/{self.devoir.id}/', {'exercices': exercices}, format='json')
        self.assertEqual(res.status_code, statut, res.data)
        return res

    def renumeroter(self, exercices):
        return [{**e, 'ordre': i + 1} for i, e in enumerate(exercices)]

    def ids(self):
        return list(self.devoir.exercices.order_by('ordre', 'id').values_list('id', flat=True))

    def travail(self, exercice):
        return BrouillonExercice.objects.get(etudiant=self.a.etu, exercice_id=exercice.pk).fichiers[0]['contenu']

    def test_faute_corrigee_garde_identifiants_et_brouillons(self):
        cas = self.ex_a.tests.get()
        exercices = self.lire()
        exercices[0]['enonce'] = 'Énoncé corrigé'
        self.envoyer(exercices)
        self.assertEqual(self.ids(), [self.ex_a.id, self.ex_b.id, self.ex_c.id])
        self.ex_a.refresh_from_db()
        self.assertEqual(self.ex_a.enonce, 'Énoncé corrigé')
        self.assertEqual(self.travail(self.ex_a), f'travail {self.ex_a.pk}')
        self.assertEqual(BrouillonExercice.objects.count(), 3)
        # Tests identiques : la ligne, et les résultats d'essai qui la citent, restent.
        self.assertTrue(CasDeTest.objects.filter(pk=cas.pk).exists())

    def test_reordonner_garde_chaque_brouillon_avec_son_exercice(self):
        a, b, c = self.lire()
        self.envoyer(self.renumeroter([c, a, b]))
        self.assertEqual(self.ids(), [self.ex_c.id, self.ex_a.id, self.ex_b.id])
        for exercice in (self.ex_a, self.ex_b, self.ex_c):
            self.assertEqual(self.travail(exercice), f'travail {exercice.pk}')

    def test_exercice_renomme_apparie_par_rang(self):
        a, b, c = self.lire()
        b['titre'] = 'Exercice B bis'
        self.envoyer([a, b, c])
        self.ex_b.refresh_from_db()
        self.assertEqual(self.ex_b.titre, 'Exercice B bis')
        self.assertEqual(self.devoir.exercices.count(), 3)
        self.assertEqual(self.travail(self.ex_b), f'travail {self.ex_b.pk}')

    def test_rang_compte_parmi_les_exercices_non_apparies(self):
        a, b, c = self.lire()
        b['titre'] = 'Renommé'
        # A et B sont sans titre reçu : « Renommé » prend le premier d'entre eux (A), et B, resté seul, part.
        self.envoyer(self.renumeroter([b, c]))
        self.assertEqual(self.ids(), [self.ex_a.id, self.ex_c.id])
        self.ex_a.refresh_from_db()
        self.assertEqual(self.ex_a.titre, 'Renommé')
        self.assertEqual(self.travail(self.ex_c), f'travail {self.ex_c.pk}')
        self.assertFalse(BrouillonExercice.objects.filter(exercice_id=self.ex_b.pk).exists())

    def test_titres_en_double(self):
        Exercice.objects.filter(pk=self.ex_c.pk).update(titre='Exercice B')
        a, b, c = self.lire()
        b['enonce'], c['enonce'] = 'premier', 'second'
        self.envoyer([a, b, c])
        self.ex_b.refresh_from_db()
        self.ex_c.refresh_from_db()
        self.assertEqual((self.ex_b.enonce, self.ex_c.enonce), ('premier', 'second'))

    def test_retirer_un_exercice_supprime_ses_seuls_brouillons(self):
        a, b, c = self.lire()
        self.envoyer(self.renumeroter([a, c]))
        self.assertFalse(Exercice.objects.filter(pk=self.ex_b.pk).exists())
        self.assertFalse(BrouillonExercice.objects.filter(exercice_id=self.ex_b.pk).exists())
        self.assertEqual(self.travail(self.ex_a), f'travail {self.ex_a.pk}')
        self.assertEqual(self.travail(self.ex_c), f'travail {self.ex_c.pk}')

    def test_ajouter_un_exercice(self):
        exercices = self.lire()
        nouveau = {'titre': 'Nouveau', 'points': '2', 'tests': [{'entree': '', 'sortie_attendue': 'x'}]}
        self.envoyer(self.renumeroter([nouveau, *exercices]))
        lignes = list(self.devoir.exercices.order_by('ordre'))
        self.assertEqual([e.titre for e in lignes], ['Nouveau', self.ex_a.titre, 'Exercice B', 'Exercice C'])
        self.assertEqual(lignes[1].pk, self.ex_a.pk)
        self.assertEqual(lignes[0].tests.count(), 1)
        self.assertEqual(BrouillonExercice.objects.count(), 3)
        self.brouillon(lignes[0], 'neuf')

    def test_tests_modifies_remplaces(self):
        exercices = self.lire()
        ancien = self.ex_a.tests.get()
        exercices[0]['tests'] = [{'ordre': 1, 'entree': '1', 'sortie_attendue': '2', 'public': True, 'poids': 3},
                                 {'ordre': 2, 'entree': '3', 'sortie_attendue': '4', 'public': False, 'poids': 1}]
        self.envoyer(exercices)
        self.assertFalse(CasDeTest.objects.filter(pk=ancien.pk).exists())
        self.assertEqual([(t.entree, t.poids) for t in self.ex_a.tests.all()], [('1', 3), ('3', 1)])
        self.assertEqual(self.travail(self.ex_a), f'travail {self.ex_a.pk}')

    def test_champs_absents_remis_a_leur_valeur_par_defaut(self):
        Exercice.objects.filter(pk=self.ex_b.pk).update(enonce='ancien', limite_temps_ms=3000)
        a, _, c = self.lire()
        self.envoyer([a, {'titre': 'Exercice B', 'points': '5', 'ordre': 2}, c])
        self.ex_b.refresh_from_db()
        self.assertEqual((self.ex_b.enonce, self.ex_b.limite_temps_ms), ('', 2000))

    def test_competences_mises_a_jour(self):
        from quiz.models import TagQuestion
        tag = TagQuestion.objects.create(type=TagQuestion.COMPETENCE, libelle='Boucles', etablissement=self.a.etab)
        exercices = self.lire()
        exercices[1]['competences'] = [tag.id]
        self.envoyer(exercices)
        self.assertEqual(list(self.ex_b.competences.all()), [tag])

    def test_enregistrement_et_soumission_de_l_etudiant_apres_la_modification(self):
        exercices = self.lire()
        exercices[0]['enonce'] = 'Énoncé corrigé'
        self.envoyer(exercices)
        self.brouillon(self.ex_a, 'suite')
        self.assertEqual(self.travail(self.ex_a), 'suite')
        res = self.etu.post(f'{P}/soumissions/', {'devoir': self.devoir.id, 'reponses': [
            {'exercice': self.ex_a.id, 'fichiers': fic('rendu')}]}, format='json')
        self.assertEqual(res.status_code, 201, res.data)

    def test_ordres_identiques_stables(self):
        a, b, c = self.lire()
        corps = [{**c, 'ordre': 1}, {**a, 'ordre': 1}, {**b, 'ordre': 1}]
        self.envoyer(corps)
        self.assertEqual(self.ids(), [self.ex_c.id, self.ex_a.id, self.ex_b.id])
        self.preparer_validation()
        # Même contenu renvoyé : rien n'a changé, la validation reste acquise.
        self.envoyer(corps)
        self.assertEqual(Devoir.objects.get(pk=self.devoir.pk).statut_validation, Devoir.VALIDEE)

    def test_devoir_verrouille_inchange(self):
        SoumissionDevoir.objects.create(devoir=self.devoir, etudiant=self.a.etu)
        exercices = self.lire()
        exercices[0]['enonce'] = 'Interdit'
        res = self.envoyer(exercices, statut=409)
        self.assertEqual(str(res.data['detail']), MESSAGE_VERROU)
        self.ex_a.refresh_from_db()
        self.assertNotEqual(self.ex_a.enonce, 'Interdit')
        self.assertEqual(BrouillonExercice.objects.count(), 3)
        # Renvoi à l'identique : toujours permis.
        self.envoyer(self.lire())

    def test_a_des_brouillons(self):
        self.assertTrue(self.ens.get(f'{P}/devoirs/{self.devoir.id}/').data['a_des_brouillons'])
        self.assertNotIn('a_des_brouillons', self.etu.get(f'{P}/devoirs/{self.devoir.id}/').data)
        BrouillonExercice.objects.all().delete()
        self.assertFalse(self.ens.get(f'{P}/devoirs/{self.devoir.id}/').data['a_des_brouillons'])
        res = self.ens.patch(f'{P}/devoirs/{self.devoir.id}/', {'a_des_brouillons': True}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertFalse(res.data['a_des_brouillons'])

    def preparer_validation(self):
        self.a.etab.validation_quiz_requise = True
        self.a.etab.save()
        Devoir.objects.filter(pk=self.devoir.pk).update(est_publie=True, statut_validation=Devoir.VALIDEE)

    def test_vrai_changement_de_contenu_remet_la_validation(self):
        self.preparer_validation()
        exercices = self.lire()
        exercices[0]['enonce'] = 'Autre énoncé'
        res = self.envoyer(exercices)
        self.assertEqual(res.data['statut_validation'], 'brouillon')
        self.assertFalse(res.data['est_publie'])
        self.assertEqual(self.travail(self.ex_a), f'travail {self.ex_a.pk}')

    def test_reordonner_remet_la_validation(self):
        self.preparer_validation()
        a, b, c = self.lire()
        res = self.envoyer(self.renumeroter([b, a, c]))
        self.assertEqual(res.data['statut_validation'], 'brouillon')

    def test_contenu_identique_garde_la_validation(self):
        self.preparer_validation()
        res = self.envoyer(self.lire())
        self.assertEqual(res.data['statut_validation'], 'validee')
        self.assertTrue(res.data['est_publie'])

    def test_contenu_relu_identique_apres_une_ecriture_sur_place(self):
        a, b, c = self.lire()
        c['titre'] = 'Exercice C bis'
        self.envoyer(self.renumeroter([c, a, b]))
        self.preparer_validation()
        res = self.envoyer(self.lire())
        self.assertEqual(res.data['statut_validation'], 'validee')

    def essai(self):
        return Execution.objects.create(type=Execution.ESSAI_TEST, demandeur=self.a.etu, devoir=self.devoir,
                                        exercice=self.ex_a, fichiers=fic('x'), statut=Execution.TERMINEE)

    def test_resultats_d_un_essai_termine_gardes_si_tests_inchanges(self):
        essai = self.essai()
        ResultatTest.objects.create(execution=essai, cas=self.ex_a.tests.get(), statut=ResultatTest.OK)
        exercices = self.lire()
        exercices[0]['enonce'] = 'Énoncé corrigé'
        self.envoyer(exercices)
        res = self.etu.get(f'{P}/executions/{essai.id}/')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(len(res.data['resultats']), 1)

    def test_essai_termine_lisible_apres_remplacement_des_tests(self):
        essai = self.essai()
        ResultatTest.objects.create(execution=essai, cas=self.ex_a.tests.get(), statut=ResultatTest.OK)
        exercices = self.lire()
        exercices[0]['tests'] = [{'ordre': 1, 'entree': '9', 'sortie_attendue': '9', 'public': True}]
        self.envoyer(exercices)
        res = self.etu.get(f'{P}/executions/{essai.id}/')
        self.assertEqual(res.status_code, 200, res.data)

    def test_essai_en_cours_quand_les_tests_sont_remplaces(self):
        """Les résultats sont écrits sans le test disparu, avec le seul statut : rien ne fuit, pas d'erreur du service."""
        essai = self.essai()
        cas = _cas(essai)
        self.ex_a.tests.all().delete()
        CasDeTest.objects.create(exercice=self.ex_a, ordre=1, entree='9', sortie_attendue='9', public=True)
        resultats = _resultats(essai, cas, {'compilation_ok': True, 'resultats': [{'sortie': '4', 'code_sortie': 0}]})
        ResultatTest.objects.bulk_create(resultats)
        self.assertIsNone(essai.resultats.get().cas)
        res = self.etu.get(f'{P}/executions/{essai.id}/')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertNotIn('entree', res.data['resultats'][0])
