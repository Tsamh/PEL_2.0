"""Reprise des devoirs existants (migration de données) : exercice, tests publics, réponses, affectation."""
from datetime import date
from decimal import Decimal

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

AVANT = [('programming', '0005_devoirs_exercices')]
ORIGINE = [('programming', '0004_devoir_ec_notematiere')]


class RepriseDevoirsTests(TransactionTestCase):
    def setUp(self):
        executor = MigrationExecutor(connection)
        self.apres = [('programming', '0010_ide_etudiant')]
        executor.migrate(AVANT)
        autres = [n for n in executor.loader.graph.leaf_nodes() if n[0] != 'programming']
        apps = executor.loader.project_state(AVANT + autres).apps

        User = apps.get_model('accounts', 'User')
        Etablissement = apps.get_model('referentiel', 'Etablissement')
        AnneeAcademique = apps.get_model('referentiel', 'AnneeAcademique')
        Filiere = apps.get_model('referentiel', 'Filiere')
        Niveau = apps.get_model('referentiel', 'Niveau')
        Classe = apps.get_model('referentiel', 'Classe')
        Inscription = apps.get_model('referentiel', 'Inscription')
        Devoir = apps.get_model('programming', 'Devoir')
        SoumissionDevoir = apps.get_model('programming', 'SoumissionDevoir')

        etab = Etablissement.objects.create(code='ETM', nom='Etablissement M')
        ens = User.objects.create(username='ensM', role='enseignant', etablissement=etab)
        etu = User.objects.create(username='etuM', role='etudiant', etablissement=etab)
        inscrit = User.objects.create(username='etuInscritM', role='etudiant', etablissement=etab)
        annee = AnneeAcademique.objects.create(libelle='2026-2027M', date_debut=date(2026, 10, 1),
                                               date_fin=date(2027, 7, 31), etablissement=etab)
        filiere = Filiere.objects.create(code='INFOM', libelle='Informatique M', etablissement=etab)
        l1 = Niveau.objects.create(code='L1M', libelle='Licence 1')
        l2 = Niveau.objects.create(code='L2M', libelle='Licence 2')
        self.classe_l1 = Classe.objects.create(code='L1M', libelle='L1', filiere=filiere, niveau=l1,
                                               annee_academique=annee).pk
        self.classe_l2 = Classe.objects.create(code='L2M', libelle='L2', filiere=filiere, niveau=l2,
                                               annee_academique=annee).pk

        devoir = Devoir.objects.create(
            titre='Somme', description='Calculer une somme.', code_initial='def main():\n    pass\n',
            solution='def main():\n    print(4)\n',
            test_cases=[{'input': '1 3', 'expected_output': '4'}, {'input': '2 2', 'expected_output': '4'}],
            points_max=15, langage='python', est_publie=True, filiere=filiere, niveau=l1,
            annee_academique=annee, cree_par=ens,
        )
        self.brouillon = Devoir.objects.create(titre='Brouillon', langage='java', filiere=filiere,
                                               cree_par=ens).pk
        self.devoir = devoir.pk
        Inscription.objects.create(etudiant=inscrit, classe_id=self.classe_l1)
        self.etu, self.inscrit = etu.pk, inscrit.pk
        self.soumission = SoumissionDevoir.objects.create(devoir=devoir, etudiant=etu, code_soumis='print(4)').pk
        SoumissionDevoir.objects.create(devoir=devoir, etudiant=inscrit, code_soumis='print(5)')
        self.gros = Devoir.objects.create(titre='Gros', langage='python', points_max=20000, cree_par=ens).pk
        sans_points = Devoir.objects.create(titre='Sans points', langage='python', points_max=0, cree_par=ens)
        self.sans_points = sans_points.pk
        SoumissionDevoir.objects.create(devoir=sans_points, etudiant=etu, code_soumis='x', statut='corrige', score=7)

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(self.apres)

    def migrer(self, cible):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(cible)
        autres = [n for n in executor.loader.graph.leaf_nodes() if n[0] != 'programming']
        return executor.loader.project_state(cible + autres).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_reprise(self):
        from programming.models import Devoir, ReponseExercice

        devoir = Devoir.objects.get(pk=self.devoir)
        self.assertEqual(devoir.objectifs, '')
        exercice = devoir.exercices.get()
        self.assertEqual(exercice.titre, 'Somme')
        self.assertEqual(exercice.enonce, 'Calculer une somme.')
        self.assertEqual(exercice.fichiers_initiaux, [{'nom': 'main.py', 'contenu': 'def main():\n    pass\n'}])
        self.assertEqual(exercice.solution, [{'nom': 'main.py', 'contenu': 'def main():\n    print(4)\n'}])
        self.assertEqual(exercice.points, Decimal('15'))
        self.assertEqual(devoir.bareme, Decimal('15'))
        tests = list(exercice.tests.values_list('entree', 'sortie_attendue', 'public', 'poids'))
        self.assertEqual(tests, [('1 3', '4', True, 1), ('2 2', '4', True, 1)])
        reponse = ReponseExercice.objects.get(soumission_id=self.soumission)
        self.assertEqual(reponse.exercice, exercice)
        self.assertEqual(reponse.fichiers, [{'nom': 'main.py', 'contenu': 'print(4)'}])
        self.assertEqual(set(devoir.classes.values_list('pk', flat=True)), {self.classe_l1})
        self.assertEqual(devoir.statut_validation, Devoir.VALIDEE)

        brouillon = Devoir.objects.get(pk=self.brouillon)
        self.assertEqual(brouillon.statut_validation, Devoir.BROUILLON)
        self.assertEqual(set(brouillon.classes.values_list('pk', flat=True)), {self.classe_l1, self.classe_l2})
        self.assertEqual(brouillon.exercices.get().fichiers_initiaux, [{'nom': 'Main.java', 'contenu': ''}])
        self.assertEqual(brouillon.exercices.get().points, Decimal('20'))

    def test_points_bornes(self):
        from programming.models import Devoir

        self.assertEqual(Devoir.objects.get(pk=self.gros).exercices.get().points, Decimal('9999.99'))
        # Sans barème : le barème migré couvre la meilleure note déjà attribuée.
        self.assertEqual(Devoir.objects.get(pk=self.sans_points).exercices.get().points, Decimal('7'))

    def test_soumissionnaires_hors_classes_affectes_nominativement(self):
        from programming.models import Devoir

        devoir = Devoir.objects.get(pk=self.devoir)
        self.assertEqual(set(devoir.etudiants.values_list('pk', flat=True)), {self.etu})

    def test_retour_puis_aller(self):
        apps = self.migrer(ORIGINE)
        Devoir = apps.get_model('programming', 'Devoir')
        SoumissionDevoir = apps.get_model('programming', 'SoumissionDevoir')
        devoir = Devoir.objects.get(pk=self.devoir)
        self.assertEqual(devoir.description, 'Calculer une somme.')
        self.assertEqual(devoir.code_initial, 'def main():\n    pass\n')
        self.assertEqual(devoir.solution, 'def main():\n    print(4)\n')
        self.assertEqual(devoir.test_cases, [{'input': '1 3', 'expected_output': '4'},
                                             {'input': '2 2', 'expected_output': '4'}])
        self.assertEqual(devoir.points_max, 15)
        self.assertEqual(SoumissionDevoir.objects.get(pk=self.soumission).code_soumis, 'print(4)')
        self.assertEqual(SoumissionDevoir.objects.count(), 3)
        self.assertEqual(Devoir.objects.get(pk=self.gros).points_max, 9999)
        self.assertEqual(Devoir.objects.get(pk=self.brouillon).points_max, 20)

        self.migrer(self.apres)
        from programming.models import Devoir as DevoirActuel, ReponseExercice

        devoir = DevoirActuel.objects.get(pk=self.devoir)
        exercice = devoir.exercices.get()
        self.assertEqual(exercice.enonce, 'Calculer une somme.')
        self.assertEqual(exercice.points, Decimal('15'))
        self.assertEqual(exercice.tests.count(), 2)
        self.assertEqual(ReponseExercice.objects.get(soumission_id=self.soumission).fichiers,
                         [{'nom': 'main.py', 'contenu': 'print(4)'}])
