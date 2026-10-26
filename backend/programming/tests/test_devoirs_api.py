from decimal import Decimal

from django.test import TestCase

from accounts.testing import build_world, client_for, make_user
from audit.models import AuditLog
from programming.models import CasDeTest, Devoir, Exercice, SoumissionDevoir
from programming.validation import PROFIL_DEVOIR
from quiz.models import TagQuestion
from referentiel.models import AffectationEnseignant, Classe, Groupe, Inscription

P = '/api/programming/devoirs'
MESSAGE_VERROU = "Ce devoir a déjà des soumissions : ses exercices et ses tests ne peuvent plus être modifiés."
MESSAGE_SANS_EXERCICE = "Ajoutez au moins un exercice avant de publier le devoir."


def exercice(titre='Somme', points='5', tests=None, **extra):
    data = {
        'titre': titre,
        'enonce': "Lire deux entiers et afficher leur somme.",
        'contraintes': "Pas de bibliothèque externe.",
        'exemples': [{'entree': '1 2', 'sortie': '3', 'explication': '1 + 2'}],
        'fichiers_initiaux': [{'nom': 'main.py', 'contenu': '# à compléter'}],
        'solution': [{'nom': 'main.py', 'contenu': 'print(SOLUTION_SECRETE)'}],
        'points': points,
        'difficulte': 'facile',
        'tests': tests if tests is not None else [
            {'entree': '1 2', 'sortie_attendue': '3', 'public': True},
            {'entree': '40 2', 'sortie_attendue': 'SORTIE_CACHEE', 'public': False, 'poids': 2},
        ],
    }
    data.update(extra)
    return data


class DevoirsApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()
        a, b = cls.w.a, cls.w.b
        cls.competence = TagQuestion.objects.create(etablissement=a.etab, type='competence', libelle='Boucles')
        cls.chapitre = TagQuestion.objects.create(etablissement=a.etab, type='chapitre', libelle='Chapitre 1')
        cls.competence_b = TagQuestion.objects.create(etablissement=b.etab, type='competence', libelle='Récursivité')

    def setUp(self):
        self.a = self.w.a

    def creer(self, user=None, **extra):
        data = {
            'titre': 'TP sommes', 'objectifs': 'Savoir lire une entrée.', 'consignes': 'Rendre un seul fichier.',
            'ressources': [{'libelle': 'Documentation', 'url': 'https://docs.python.org/3/'}],
            'filiere': self.a.filiere.id, 'langage': 'python', 'classes': [self.a.classe.id],
            'exercices': [exercice(competences=[self.competence.id]), exercice('Produit', points='3', tests=[])],
        }
        data.update(extra)
        return client_for(user or self.a.ens).post(f'{P}/', data, format='json')

    def patch(self, devoir, data, user=None):
        return client_for(user or self.a.ens).patch(f'{P}/{devoir.id}/', data, format='json')

    def test_creation_imbriquee_et_relecture(self):
        res = self.creer()
        self.assertEqual(res.status_code, 201, res.data)
        devoir = Devoir.objects.get(pk=res.data['id'])
        self.assertEqual(devoir.cree_par, self.a.ens)
        self.assertEqual(list(devoir.classes.all()), [self.a.classe])
        exercices = list(devoir.exercices.all())
        self.assertEqual([e.titre for e in exercices], ['Somme', 'Produit'])
        self.assertEqual([e.ordre for e in exercices], [1, 2])
        self.assertEqual(list(exercices[0].competences.all()), [self.competence])
        tests = list(exercices[0].tests.all())
        self.assertEqual([(t.ordre, t.public, t.poids) for t in tests], [(1, True, 1), (2, False, 2)])

        lu = client_for(self.a.ens).get(f'{P}/{devoir.id}/').data
        self.assertEqual(lu['bareme'], '8.00')
        self.assertEqual(lu['nb_exercices'], 2)
        self.assertEqual(lu['ressources'], [{'libelle': 'Documentation', 'url': 'https://docs.python.org/3/'}])
        self.assertEqual(lu['classes_detail'][0]['id'], self.a.classe.id)
        self.assertFalse(lu['a_des_soumissions'])
        premier = lu['exercices'][0]
        self.assertEqual(premier['solution'], [{'nom': 'main.py', 'contenu': 'print(SOLUTION_SECRETE)'}])
        self.assertEqual(premier['competences'], [self.competence.id])
        self.assertEqual(premier['competences_detail'], [{'id': self.competence.id, 'libelle': 'Boucles'}])
        self.assertEqual([t['sortie_attendue'] for t in premier['tests']], ['3', 'SORTIE_CACHEE'])
        self.assertEqual(lu['exercices'][1]['tests'], [])

        log = AuditLog.objects.get(action='affectation_evaluation', cible_id=str(devoir.id))
        self.assertEqual(log.details['ajouts']['classes'], [self.a.classe.id])
        self.assertEqual(log.details['type'], 'devoir')

    def test_remplacement_des_exercices(self):
        devoir = Devoir.objects.get(pk=self.creer().data['id'])
        anciens = set(devoir.exercices.values_list('pk', flat=True))
        res = self.patch(devoir, {'exercices': [exercice('Nouveau', points='4', tests=[
            {'entree': '', 'sortie_attendue': 'ok', 'public': True}])]})
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual([e['titre'] for e in res.data['exercices']], ['Nouveau'])
        self.assertEqual(res.data['bareme'], '4.00')
        self.assertFalse(Exercice.objects.filter(pk__in=anciens).exists())
        self.assertEqual(CasDeTest.objects.filter(exercice__devoir=devoir).count(), 1)

    def test_au_plus_50_exercices(self):
        res = self.creer(exercices=[exercice(f'Exercice {i}', tests=[]) for i in range(51)])
        self.assertEqual(res.status_code, 400)
        self.assertEqual(str(res.data['exercices'][0]), "Un devoir compte au plus 50 exercices.")

    def test_au_plus_100_tests_par_exercice(self):
        tests = [{'entree': str(i), 'sortie_attendue': str(i), 'public': True} for i in range(101)]
        res = self.creer(exercices=[exercice(tests=tests)])
        self.assertEqual(res.status_code, 400)
        self.assertEqual(str(res.data['exercices'][0]['tests'][0]), "Un exercice compte au plus 100 tests.")

    def test_bareme_maximal_relu_sans_erreur(self):
        res = self.creer(exercices=[exercice(f'Exercice {i}', points='9999.99', tests=[]) for i in range(50)])
        self.assertEqual(res.status_code, 201, res.data)
        lu = client_for(self.a.ens).get(f'{P}/{res.data["id"]}/')
        self.assertEqual(lu.status_code, 200)
        self.assertEqual(lu.data['bareme'], '499999.50')
        self.assertEqual(client_for(self.a.ens).get(f'{P}/').status_code, 200)

    def test_bareme_somme_des_points(self):
        res = self.creer(exercices=[exercice(points='2.5'), exercice(points='7.25'), exercice(points='0.25')])
        self.assertEqual(res.data['bareme'], '10.00')
        self.assertEqual(Devoir.objects.get(pk=res.data['id']).bareme, Decimal('10.00'))

    def test_langage_fige_apres_une_soumission(self):
        devoir = self.a.devoir
        SoumissionDevoir.objects.create(devoir=devoir, etudiant=self.a.etu)
        langage = devoir.langage
        autre = 'java' if langage != 'java' else 'python'
        res = self.patch(devoir, {'langage': autre})
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data['detail'], MESSAGE_VERROU)
        devoir.refresh_from_db()
        self.assertEqual(devoir.langage, langage)

        # Renvoyer le même langage n'est pas un changement.
        res = self.patch(devoir, {'langage': langage, 'titre': 'Renommé'})
        self.assertEqual(res.status_code, 200, res.data)

    def test_verrou_apres_une_soumission(self):
        devoir = self.a.devoir
        SoumissionDevoir.objects.create(devoir=devoir, etudiant=self.a.etu)
        avant = list(devoir.exercices.values_list('pk', flat=True))
        res = self.patch(devoir, {'exercices': [exercice()]})
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data['detail'], MESSAGE_VERROU)
        self.assertEqual(list(devoir.exercices.values_list('pk', flat=True)), avant)

        # Les exercices renvoyés à l'identique ne sont pas un changement : ils sont conservés.
        lu = client_for(self.a.ens).get(f'{P}/{devoir.id}/').data
        self.assertTrue(lu['a_des_soumissions'])
        res = self.patch(devoir, {'exercices': lu['exercices'], 'titre': 'Renommé'})
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(list(devoir.exercices.values_list('pk', flat=True)), avant)

        res = self.patch(devoir, {'date_debut': '2026-11-01T08:00:00Z', 'date_fin': '2026-11-10T18:00:00Z',
                                  'classes': [], 'etudiants': [self.a.etu.id]})
        self.assertEqual(res.status_code, 200, res.data)
        devoir.refresh_from_db()
        self.assertEqual(list(devoir.etudiants.all()), [self.a.etu])
        self.assertFalse(devoir.classes.exists())

    def test_competence_hors_etablissement_ou_autre_type(self):
        for tag in (self.competence_b, self.chapitre):
            with self.subTest(tag=tag.libelle):
                res = self.creer(exercices=[exercice(competences=[tag.id])])
                self.assertEqual(res.status_code, 400)
                self.assertNotIn(tag.libelle, str(res.data))
        self.assertFalse(Devoir.objects.filter(titre='TP sommes').exists())

    def test_ressources_invalides(self):
        lien = {'libelle': 'Lien', 'url': 'https://exemple.org'}
        cas = {
            'javascript': [{'libelle': 'Piège', 'url': 'javascript:alert(1)'}],
            'sans hôte': [{'libelle': 'Vide', 'url': 'https://'}],
            'trop de liens': [lien] * 21,
            'libellé vide': [{'libelle': '  ', 'url': 'https://exemple.org'}],
            'libellé trop long': [{'libelle': 'x' * 201, 'url': 'https://exemple.org'}],
            'adresse trop longue': [{'libelle': 'Long', 'url': 'https://exemple.org/' + 'a' * 500}],
            'pas un objet': ['https://exemple.org'],
            'pas une liste': {'libelle': 'Lien', 'url': 'https://exemple.org'},
        }
        for nom, ressources in cas.items():
            with self.subTest(cas=nom):
                res = self.creer(ressources=ressources)
                self.assertEqual(res.status_code, 400)
                self.assertIn('ressources', res.data)
        self.assertEqual(self.creer(ressources=[lien] * 20).status_code, 201)

    def test_fichiers_et_exemples_invalides(self):
        cas = {
            'remontée': {'fichiers_initiaux': [{'nom': '../x', 'contenu': ''}]},
            'barre oblique': {'solution': [{'nom': 'src/main.py', 'contenu': ''}]},
            'barre inverse': {'fichiers_initiaux': [{'nom': 'src\\main.py', 'contenu': ''}]},
            'nom vide': {'fichiers_initiaux': [{'nom': ' ', 'contenu': ''}]},
            'nom trop long': {'fichiers_initiaux': [{'nom': 'a' * 101, 'contenu': ''}]},
            'contenu trop long': {'solution': [{'nom': 'main.py', 'contenu': 'x' * 100001}]},
            'contenu non texte': {'solution': [{'nom': 'main.py', 'contenu': 12}]},
            'trop de fichiers': {'fichiers_initiaux': [{'nom': f'f{i}.py', 'contenu': ''} for i in range(21)]},
            'doublon': {'fichiers_initiaux': [{'nom': 'main.py', 'contenu': ''}, {'nom': 'main.py', 'contenu': ''}]},
            'fichier non objet': {'fichiers_initiaux': ['main.py']},
            'exemple non objet': {'exemples': ['1 2 -> 3']},
            'exemple non texte': {'exemples': [{'entree': ['1'], 'sortie': '3'}]},
        }
        for nom, extra in cas.items():
            with self.subTest(cas=nom):
                res = self.creer(exercices=[exercice(**extra)])
                self.assertEqual(res.status_code, 400, res.data)
        self.assertFalse(Devoir.objects.filter(titre='TP sommes').exists())

    def test_publication_sans_exercice(self):
        res = self.creer(exercices=[], est_publie=True)
        self.assertEqual(res.status_code, 400)
        self.assertIn(MESSAGE_SANS_EXERCICE, str(res.data))
        self.assertEqual(self.creer(exercices=[]).status_code, 201)
        res = self.patch(self.a.devoir, {'exercices': []})
        self.assertEqual(res.status_code, 400)
        self.assertIn(MESSAGE_SANS_EXERCICE, str(res.data))

    def test_dates_incoherentes(self):
        res = self.creer(date_debut='2026-11-10T08:00:00Z', date_fin='2026-11-01T08:00:00Z')
        self.assertEqual(res.status_code, 400)
        self.assertIn('date_fin', res.data)

    def test_affectation_hors_perimetre(self):
        b = self.w.b
        for champ, valeur in (('classes', [b.classe.id]), ('etudiants', [b.etu.id])):
            with self.subTest(champ=champ):
                res = self.creer(**{champ: valeur})
                self.assertEqual(res.status_code, 400)
                self.assertIn(champ, res.data)
        res = self.patch(self.a.devoir, {'classes': [b.classe.id]}, user=self.a.admin)
        self.assertEqual(res.status_code, 400)

    def test_enseignant_ne_voit_que_ses_devoirs_et_admin_b_ne_voit_pas_a(self):
        collegue = make_user('collegue', 'enseignant', self.a.etab)
        AffectationEnseignant.objects.create(enseignant=collegue, classe=self.a.classe)
        res = self.creer(user=collegue)
        self.assertEqual(res.status_code, 201, res.data)
        autre = res.data['id']
        ids = {d['id'] for d in client_for(self.a.ens).get(f'{P}/').data['results']}
        self.assertIn(self.a.devoir.id, ids)
        self.assertNotIn(autre, ids)
        self.assertEqual(client_for(self.a.ens).get(f'{P}/{autre}/').status_code, 404)
        self.assertIn(autre, {d['id'] for d in client_for(self.a.admin).get(f'{P}/').data['results']})
        self.assertEqual(client_for(self.w.b.admin).get(f'{P}/{self.a.devoir.id}/').status_code, 404)
        self.assertEqual(client_for(self.w.b.admin).get(f'{P}/{autre}/').status_code, 404)

    def test_contenu_modifie(self):
        devoir = Devoir.objects.get(pk=self.creer().data['id'])
        lu = client_for(self.a.ens).get(f'{P}/{devoir.id}/').data
        from programming.serializers import DevoirSerializer
        meme = DevoirSerializer(devoir, data={'exercices': lu['exercices']}, partial=True)
        self.assertTrue(meme.is_valid(), meme.errors)
        self.assertFalse(PROFIL_DEVOIR.contenu_modifie(devoir, meme.validated_data))
        modifies = lu['exercices']
        modifies[0]['tests'][1]['sortie_attendue'] = 'autre'
        change = DevoirSerializer(devoir, data={'exercices': modifies}, partial=True)
        self.assertTrue(change.is_valid(), change.errors)
        self.assertTrue(PROFIL_DEVOIR.contenu_modifie(devoir, change.validated_data))
        self.assertTrue(PROFIL_DEVOIR.contenu_modifie(devoir, {'consignes': 'Nouvelles consignes'}))
        self.assertFalse(PROFIL_DEVOIR.contenu_modifie(devoir, {'consignes': devoir.consignes}))
        self.assertFalse(PROFIL_DEVOIR.contenu_modifie(None, {'titre': 'x'}))

    def test_contenu_conserve_a_l_identique(self):
        res = self.creer(exercices=[exercice(
            enonce='  def f():\n    pass\n', contraintes='\n  Aucune.\n',
            tests=[{'entree': '3\n', 'sortie_attendue': '  *\n ***\n', 'public': True}])])
        self.assertEqual(res.status_code, 201, res.data)
        test = CasDeTest.objects.get(exercice__devoir_id=res.data['id'])
        self.assertEqual((test.entree, test.sortie_attendue), ('3\n', '  *\n ***\n'))
        exo = test.exercice
        self.assertEqual((exo.enonce, exo.contraintes), ('  def f():\n    pass\n', '\n  Aucune.\n'))

    def test_renvoi_identique_de_donnees_non_rognees_apres_soumission(self):
        devoir = Devoir.objects.get(pk=self.creer().data['id'])
        exo = devoir.exercices.first()
        exo.enonce = '  Énoncé indenté\n'
        exo.save()
        CasDeTest.objects.filter(exercice=exo).update(entree='3\n', sortie_attendue='  *\n')
        SoumissionDevoir.objects.create(devoir=devoir, etudiant=self.a.etu)
        self.a.etab.validation_quiz_requise = True
        self.a.etab.save()
        Devoir.objects.filter(pk=devoir.pk).update(statut_validation=Devoir.VALIDEE, est_publie=True)
        lu = client_for(self.a.ens).get(f'{P}/{devoir.id}/').data
        res = self.patch(devoir, {'exercices': lu['exercices'], 'date_debut': '2026-11-01T08:00:00Z',
                                  'date_fin': '2026-11-10T18:00:00Z'})
        self.assertEqual(res.status_code, 200, res.data)
        devoir.refresh_from_db()
        self.assertEqual(devoir.statut_validation, Devoir.VALIDEE)
        self.assertTrue(devoir.est_publie)
        self.assertEqual(CasDeTest.objects.filter(exercice=exo).first().entree, '3\n')

    def test_verrou_un_seul_test_cache_modifie(self):
        devoir = Devoir.objects.get(pk=self.creer().data['id'])
        SoumissionDevoir.objects.create(devoir=devoir, etudiant=self.a.etu)
        for champ, valeur in (('sortie_attendue', 'autre'), ('public', True), ('poids', 5)):
            with self.subTest(champ=champ):
                lu = client_for(self.a.ens).get(f'{P}/{devoir.id}/').data
                lu['exercices'][0]['tests'][1][champ] = valeur
                res = self.patch(devoir, {'exercices': lu['exercices']})
                self.assertEqual(res.status_code, 409)
                self.assertEqual(res.data['detail'], MESSAGE_VERROU)

    def test_changement_de_contenu_remet_un_devoir_valide_en_brouillon(self):
        self.a.etab.validation_quiz_requise = True
        self.a.etab.save()
        devoir = Devoir.objects.get(pk=self.creer().data['id'])
        Devoir.objects.filter(pk=devoir.pk).update(statut_validation=Devoir.VALIDEE, est_publie=True)
        res = self.patch(devoir, {'consignes': 'Consignes modifiées'})
        self.assertEqual(res.status_code, 200, res.data)
        devoir.refresh_from_db()
        self.assertEqual(devoir.statut_validation, Devoir.BROUILLON)
        self.assertFalse(devoir.est_publie)

    def test_exercices_et_tests_non_listes(self):
        self.assertEqual(self.creer(exercices='abc').status_code, 400)
        self.assertEqual(self.creer(exercices={'titre': 'x'}).status_code, 400)
        self.assertEqual(self.creer(exercices=[exercice(tests='abc')]).status_code, 400)
        self.assertEqual(self.creer(exercices=[exercice(tests={'entree': '1'})]).status_code, 400)

    def test_competence_inexistante_et_autre_etablissement_meme_erreur(self):
        erreurs = []
        for pk in (self.competence_b.id, 999999):
            res = self.creer(exercices=[exercice(competences=[pk])])
            self.assertEqual(res.status_code, 400)
            erreurs.append(str(res.data['exercices']))
        self.assertEqual(erreurs[0], erreurs[1])
        self.assertNotIn(str(self.competence_b.id), erreurs[0])


class VisibiliteEtudiantTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()
        a = cls.w.a
        cls.devoir = a.devoir
        exercice_ = a.exercice
        exercice_.solution = [{'nom': 'main.py', 'contenu': 'SOLUTION_SECRETE'}]
        exercice_.save()
        CasDeTest.objects.create(exercice=exercice_, ordre=2, entree='ENTREE_CACHEE', sortie_attendue='SORTIE_CACHEE',
                                 public=False)
        cls.voisin = make_user('voisin', 'etudiant', a.etab)
        Inscription.objects.create(etudiant=cls.voisin, classe=a.classe)

    def setUp(self):
        self.a = self.w.a
        self.devoir.classes.clear()

    def ids(self, user):
        res = client_for(user).get(f'{P}/')
        self.assertEqual(res.status_code, 200)
        return {d['id'] for d in res.data['results']}

    def assert_invisible(self, user):
        self.assertNotIn(self.devoir.id, self.ids(user))
        self.assertEqual(client_for(user).get(f'{P}/{self.devoir.id}/').status_code, 404)

    def test_sans_affectation_invisible(self):
        self.assert_invisible(self.a.etu)

    def test_affecte_par_classe(self):
        self.devoir.classes.add(self.a.classe)
        self.assertIn(self.devoir.id, self.ids(self.a.etu))
        self.assertIn(self.devoir.id, self.ids(self.voisin))

    def test_affecte_par_groupe_avec_inscription(self):
        groupe = Groupe.objects.create(code='TD1A', libelle='TD 1', classe=self.a.classe)
        groupe.membres.add(self.a.etu)
        self.devoir.groupes.add(groupe)
        self.assertIn(self.devoir.id, self.ids(self.a.etu))
        self.assert_invisible(self.voisin)
        Inscription.objects.filter(etudiant=self.a.etu, classe=self.a.classe).delete()
        self.assert_invisible(self.a.etu)

    def test_affecte_nominativement(self):
        self.devoir.etudiants.add(self.voisin)
        self.assertIn(self.devoir.id, self.ids(self.voisin))
        self.assert_invisible(self.a.etu)

    def test_autre_classe_de_la_filiere_non_affectee(self):
        self.devoir.classes.add(self.a.classe)
        autre_classe = Classe.objects.create(code='L1X', libelle='L1 Info X', filiere=self.a.filiere,
                                             niveau=self.w.niveau, annee_academique=self.a.annee)
        autre = make_user('autre', 'etudiant', self.a.etab)
        Inscription.objects.create(etudiant=autre, classe=autre_classe)
        self.assert_invisible(autre)

    def test_brouillon_invisible(self):
        self.devoir.classes.add(self.a.classe)
        Devoir.objects.filter(pk=self.devoir.pk).update(est_publie=False)
        self.assert_invisible(self.a.etu)

    def test_ni_solution_ni_test_cache(self):
        self.devoir.classes.add(self.a.classe)
        client = client_for(self.a.etu)
        for url in (f'{P}/', f'{P}/{self.devoir.id}/'):
            with self.subTest(url=url):
                res = client.get(url)
                self.assertEqual(res.status_code, 200)
                brut = res.content.decode('utf-8')
                for interdit in ('solution', 'SOLUTION_SECRETE', 'ENTREE_CACHEE', 'SORTIE_CACHEE', '"poids"',
                                 '"public"', 'classes_detail', 'motif_refus'):
                    self.assertNotIn(interdit, brut)
        detail = client.get(f'{P}/{self.devoir.id}/').data
        self.assertEqual(detail['bareme'], '20.00')
        exercice_ = detail['exercices'][0]
        self.assertEqual(exercice_['tests_publics'], [
            {'id': self.a.exercice.tests.get(public=True).id, 'entree': '', 'sortie_attendue': '4'}])
        self.assertEqual(set(exercice_), {'id', 'ordre', 'titre', 'enonce', 'contraintes', 'exemples',
                                          'fichiers_initiaux', 'points', 'difficulte', 'competences',
                                          'tests_publics'})

    def test_competences_en_libelles(self):
        self.devoir.classes.add(self.a.classe)
        tag = TagQuestion.objects.create(etablissement=self.a.etab, type='competence', libelle='Entrées-sorties')
        self.a.exercice.competences.add(tag)
        detail = client_for(self.a.etu).get(f'{P}/{self.devoir.id}/').data
        self.assertEqual(detail['exercices'][0]['competences'], ['Entrées-sorties'])
