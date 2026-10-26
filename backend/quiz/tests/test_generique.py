"""Modules génériques (affectation, fenêtres, validation) : non-régression pour les quiz et généricité."""
from datetime import timedelta
from types import SimpleNamespace

from django.db.models import Q
from django.test import TestCase
from django.utils import timezone

from accounts.testing import build_world, make_user
from quiz import fenetres, validation
from quiz.acces import q_affecte, q_quiz_affecte
from quiz.models import Quiz
from quiz.statistiques import etudiants_affectes
from referentiel.models import Groupe, Inscription


def _ancien_q_quiz_affecte(user):
    """Implémentation d'origine, gardée ici comme référence."""
    return (
        Q(pk__in=Quiz.objects.filter(classes__inscriptions__etudiant=user).values('pk'))
        | Q(pk__in=Quiz.objects.filter(groupes__membres=user, groupes__classe__inscriptions__etudiant=user).values('pk'))
        | Q(pk__in=Quiz.objects.filter(etudiants=user).values('pk'))
    )


class AffectationGeneriqueTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def setUp(self):
        a = self.w.a
        self.etu = a.etu
        self.voisin = make_user('voisin', 'etudiant', a.etab)
        Inscription.objects.create(etudiant=self.voisin, classe=a.classe)
        self.hors_classe = make_user('hors_classe', 'etudiant', a.etab)
        groupe = Groupe.objects.create(code='TD1A', libelle='TD 1', classe=a.classe)
        groupe.membres.add(self.etu, self.hors_classe)
        self.par_classe = a.quiz
        self.par_groupe = Quiz.objects.create(titre='Groupe', filiere=a.quiz.filiere, cree_par=a.quiz.cree_par)
        self.par_groupe.groupes.add(groupe)
        self.nominatif = Quiz.objects.create(titre='Nominatif', filiere=a.quiz.filiere, cree_par=a.quiz.cree_par)
        self.nominatif.etudiants.add(self.voisin)
        self.aucun = Quiz.objects.create(titre='Aucun', filiere=a.quiz.filiere, cree_par=a.quiz.cree_par)

    def test_q_affecte_equivaut_a_l_ancien(self):
        for user in (self.etu, self.voisin, self.hors_classe):
            attendu = set(Quiz.objects.filter(_ancien_q_quiz_affecte(user)).values_list('pk', flat=True))
            self.assertEqual(set(Quiz.objects.filter(q_affecte(Quiz, user)).values_list('pk', flat=True)), attendu)
            self.assertEqual(set(Quiz.objects.filter(q_quiz_affecte(user)).values_list('pk', flat=True)), attendu)
        self.assertIn(self.par_groupe.pk, set(Quiz.objects.filter(q_affecte(Quiz, self.etu)).values_list('pk', flat=True)))
        self.assertNotIn(self.par_groupe.pk,
                         set(Quiz.objects.filter(q_affecte(Quiz, self.hors_classe)).values_list('pk', flat=True)))

    def test_etudiants_affectes(self):
        self.assertIn(self.etu, etudiants_affectes(self.par_groupe))
        self.assertNotIn(self.hors_classe, etudiants_affectes(self.par_groupe))
        self.assertEqual(list(etudiants_affectes(self.nominatif)), [self.voisin])
        self.assertEqual(list(etudiants_affectes(self.aucun)), [])
        self.assertEqual(set(etudiants_affectes(self.par_classe)) >= {self.etu, self.voisin}, True)


class FenetreGeneriqueTests(TestCase):
    def test_sans_tentatives_autorisees_une_tentative(self):
        maintenant = timezone.now()
        evaluation = SimpleNamespace(date_debut=maintenant - timedelta(days=1), date_fin=maintenant + timedelta(days=1))
        f = fenetres.construire(evaluation, [], [], maintenant)
        self.assertEqual(f.tentatives_max, 1)
        self.assertEqual(f.intervalles, [(evaluation.date_debut, evaluation.date_fin)])
        self.assertIsNotNone(f.ouverte)

    def test_rattrapage_sans_tentatives_supplementaires(self):
        maintenant = timezone.now()
        evaluation = SimpleNamespace(date_debut=None, date_fin=maintenant - timedelta(days=1))
        rattrapage = SimpleNamespace(ouverture=maintenant - timedelta(hours=1), fermeture=maintenant + timedelta(hours=1))
        f = fenetres.construire(evaluation, [], [rattrapage], maintenant)
        self.assertEqual(f.tentatives_max, 1)
        self.assertEqual(f.ouverte, (rattrapage.ouverture, rattrapage.fermeture))


class ProfilQuizTests(TestCase):
    def test_textes_du_quiz(self):
        p = validation.PROFIL_QUIZ
        self.assertEqual(p.message_publication,
                         "La publication de ce quiz demande la validation du responsable de formation.")
        self.assertEqual(p.nom, 'quiz')
        self.assertEqual(p.article, 'ce quiz')
        self.assertEqual(p.url_validation, '/validation-quiz')
        self.assertEqual(p.details(SimpleNamespace(titre='T')), {'titre': 'T'})

    def test_autre_profil_ajoute_le_type_aux_details(self):
        p = validation.Profil(nom='devoir', article='ce devoir', message_publication='m',
                              contenu_modifie=lambda i, a: False, a_du_contenu=lambda o: True,
                              message_sans_contenu='s')
        self.assertEqual(p.details(SimpleNamespace(titre='T'), motif='x'), {'titre': 'T', 'motif': 'x', 'type': 'devoir'})
        self.assertEqual(p.article_majuscule, 'Ce devoir')
        self.assertEqual(p.nom_majuscule, 'Devoir')

    def test_alias_etablissement(self):
        self.assertIs(validation.etablissement_du_quiz, validation.etablissement_de)
