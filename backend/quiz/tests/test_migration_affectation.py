import importlib

from django.apps import apps
from django.test import TestCase

from accounts.testing import build_world
from quiz.models import Quiz
from referentiel.models import Classe, Niveau

migration = importlib.import_module('quiz.migrations.0004_affectation')


class RepriseDesQuizExistantsTests(TestCase):
    def test_affectation_par_filiere_et_niveau(self):
        w = build_world()
        a = w.a
        a.quiz.classes.clear()
        niveau_l2 = Niveau.objects.create(code='L2', libelle='Licence 2')
        classe_l2 = Classe.objects.create(
            code='L2A', libelle='L2 Info A', filiere=a.filiere, niveau=niveau_l2, annee_academique=a.annee,
        )
        sans_niveau = Quiz.objects.create(titre='Sans niveau', filiere=a.filiere, cree_par=a.ens)
        sans_filiere = Quiz.objects.create(titre='Sans filière', cree_par=a.ens)

        migration.affecter_quiz_existants(apps, None)

        self.assertEqual(set(a.quiz.classes.all()), {a.classe})
        self.assertEqual(set(sans_niveau.classes.all()), {a.classe, classe_l2})
        self.assertFalse(sans_filiere.classes.exists())
        self.assertEqual(set(w.b.quiz.classes.all()), {w.b.classe})

    def test_monde_de_test_affecte(self):
        w = build_world()
        self.assertEqual(list(w.a.quiz.classes.all()), [w.a.classe])
        self.assertEqual(w.a.quiz.code_acces, '')
