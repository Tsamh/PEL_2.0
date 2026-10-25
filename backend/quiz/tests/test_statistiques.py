from datetime import timedelta
from decimal import Decimal

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from accounts.testing import build_world, client_for, make_user
from quiz import statistiques
from quiz.correction import corriger_tentative
from quiz.models import Choix, Question, Quiz, ReponseQuiz, TentativeQuiz
from referentiel.models import Inscription

Q = '/api/quiz'


class Scenario:
    """Quiz à deux questions : QCM 1 pt (pénalité 0,5) et réponse courte 2 pts ; cinq étudiants de la classe A."""

    def preparer(self):
        self.w = build_world()
        a = self.a = self.w.a
        self.quiz = a.quiz
        self.q1 = a.question
        self.q1.penalite = Decimal('0.5')
        self.q1.save()
        self.bon = self.q1.choix.get(texte='4')
        self.mauvais = self.q1.choix.get(texte='5')
        self.q2 = Question.objects.create(quiz=self.quiz, texte='Capitale de la France ?', type_question='courte',
                                          points=Decimal('2'), ordre=2)
        Choix.objects.create(question=self.q2, texte='Paris', est_correct=True, ordre=1)
        self.etu2, self.etu3, self.etu4, self.etu5 = (make_user(f'etu{i}', 'etudiant', a.etab) for i in range(2, 6))
        for etudiant in (self.etu2, self.etu3, self.etu4, self.etu5):
            Inscription.objects.create(etudiant=etudiant, classe=a.classe)
        self.depart = timezone.now() - timedelta(days=1)
        self.tentative(a.etu, 1, [self.mauvais], 'Lyon')
        self.tentative(a.etu, 2, [self.bon], 'Paris')
        self.tentative(self.etu2, 1, [self.bon], 'lyon ')
        self.tentative(self.etu5, 1, [self.mauvais], 'Lyon')
        self.tentative(self.etu3, 1, [], '', soumise=False)

    def tentative(self, etudiant, numero, choix, texte, soumise=True, quiz=None):
        quiz = quiz or self.quiz
        debut = self.depart + timedelta(hours=numero)
        t = TentativeQuiz.objects.create(
            quiz=quiz, etudiant=etudiant, numero=numero, debut=debut,
            fin_prevue=debut + timedelta(minutes=30) if soumise else timezone.now() + timedelta(minutes=30),
            statut=TentativeQuiz.SOUMISE if soumise else TentativeQuiz.EN_COURS,
            soumise_le=debut + timedelta(minutes=10) if soumise else None,
        )
        for question in quiz.questions.all():
            reponse = ReponseQuiz.objects.create(tentative=t, question=question,
                                                 texte_reponse=texte if question.type_question == 'courte' else '')
            if question.type_question != 'courte':
                reponse.choix_selectionnes.set(choix)
        if soumise:
            corriger_tentative(t)
        return t


class StatistiquesServiceTests(Scenario, TestCase):
    def setUp(self):
        self.preparer()

    def test_population(self):
        p = statistiques.statistiques_quiz(self.quiz)['population']
        self.assertEqual(p, {'concernes': 5, 'soumis': 3, 'en_cours': 1, 'non_commences': 1, 'taux_participation': '60.00'})

    def test_etudiant_retire_ayant_soumis_reste_compte(self):
        Inscription.objects.filter(etudiant=self.etu5).delete()
        Inscription.objects.filter(etudiant=self.etu4).delete()
        p = statistiques.statistiques_quiz(self.quiz)['population']
        self.assertEqual((p['concernes'], p['soumis'], p['non_commences']), (4, 3, 0))

    def test_notes_sur_la_meilleure_tentative(self):
        n = statistiques.statistiques_quiz(self.quiz)['notes']
        self.assertEqual(n['nb'], 3)
        self.assertEqual(n['score_max'], '3.00')
        self.assertEqual((n['moyenne'], n['mediane'], n['minimum'], n['maximum']), ('1.33', '1.00', '0.00', '3.00'))
        self.assertEqual(n['ecart_type'], '1.25')
        self.assertEqual((n['moyenne_pourcentage'], n['mediane_pourcentage']), ('44.44', '33.33'))
        self.assertEqual(n['provisoires'], 3)
        self.assertEqual(n['duree_mediane'], 600)

    def test_distribution(self):
        d = statistiques.statistiques_quiz(self.quiz)['distribution']
        self.assertEqual(len(d), 10)
        self.assertEqual([t['nb'] for t in d], [1, 0, 0, 1, 0, 0, 0, 0, 0, 1])
        self.assertEqual((d[9]['de'], d[9]['a']), (90, 100))

    def test_questions(self):
        q1, q2 = statistiques.statistiques_quiz(self.quiz)['questions']
        self.assertEqual((q1['nb_reponses'], q1['nb_sans_reponse']), (3, 0))
        self.assertEqual(q1['taux_reussite'], '66.67')
        self.assertEqual(q1['score_moyen'], '0.50')
        cinq = next(c for c in q1['choix'] if c['texte'] == '5')
        self.assertEqual((cinq['nb'], cinq['pourcentage'], cinq['est_correct']), (1, '33.33', False))
        self.assertEqual(q1['erreurs_frequentes'], [{'texte': '5', 'nb': 1}])
        self.assertEqual(q2['taux_reussite'], '33.33')
        self.assertEqual(q2['choix'], [])
        self.assertEqual(q2['erreurs_frequentes'], [])
        self.assertEqual((q1['nb_a_valider'], q2['nb_a_valider']), (0, 3))

    def test_reponse_courte_fausse_validee_dans_les_erreurs(self):
        ReponseQuiz.objects.filter(tentative__etudiant=self.etu5, question=self.q2).update(
            statut_correction=ReponseQuiz.VALIDEE, score_obtenu=Decimal('0'))
        q2 = statistiques.statistiques_quiz(self.quiz)['questions'][1]
        self.assertEqual(q2['erreurs_frequentes'], [{'texte': 'lyon', 'nb': 1}])
        self.assertEqual(q2['nb_a_valider'], 2)

    def test_titre(self):
        self.assertEqual(statistiques.statistiques_quiz(self.quiz)['titre'], self.quiz.titre)

    def test_suivi_individuel(self):
        lignes = {l['id']: l for l in statistiques.statistiques_quiz(self.quiz)['etudiants']}
        etu = lignes[self.a.etu.id]
        self.assertEqual((etu['statut'], etu['nb_tentatives'], etu['meilleure'], etu['derniere']), ('soumis', 2, '3.00', '3.00'))
        self.assertEqual(etu['progression'], ['0.00', '3.00'])
        self.assertEqual(etu['temps_total'], 1200)
        self.assertTrue(etu['provisoire'])
        self.assertEqual((lignes[self.etu3.id]['statut'], lignes[self.etu3.id]['meilleure']), ('en_cours', None))
        self.assertEqual((lignes[self.etu4.id]['statut'], lignes[self.etu4.id]['nb_tentatives']), ('non_commence', 0))

    def test_quiz_vide(self):
        vide = Quiz.objects.create(titre='Vide', cree_par=self.a.ens)
        s = statistiques.statistiques_quiz(vide)
        self.assertEqual(s['population']['taux_participation'], '0.00')
        self.assertIsNone(s['notes']['moyenne'])
        self.assertEqual([t['nb'] for t in s['distribution']], [0] * 10)
        self.assertEqual((s['questions'], s['etudiants']), ([], []))
        vide.classes.add(self.a.classe)
        Question.objects.create(quiz=vide, texte='Q', points=Decimal('1'))
        s = statistiques.statistiques_quiz(vide)
        self.assertEqual(s['population']['concernes'], 5)
        self.assertEqual(s['questions'][0]['taux_reussite'], '0.00')

    def test_requetes_independantes_du_nombre_d_etudiants(self):
        with CaptureQueriesContext(connection) as avant:
            statistiques.statistiques_quiz(self.quiz)
        for i in range(6, 12):
            etudiant = make_user(f'etu{i}', 'etudiant', self.a.etab)
            Inscription.objects.create(etudiant=etudiant, classe=self.a.classe)
            self.tentative(etudiant, 1, [self.bon], 'Paris')
        with CaptureQueriesContext(connection) as apres:
            statistiques.statistiques_quiz(self.quiz)
        self.assertEqual(len(apres), len(avant))

    def test_resume(self):
        r = statistiques.resume_quiz(self.quiz)
        self.assertEqual(r['id'], self.quiz.id)
        self.assertEqual(r['population']['taux_participation'], '60.00')
        self.assertEqual(r['notes']['moyenne'], '1.33')
        self.assertEqual(r['nb_a_valider'], 4)

    def test_resultats_etudiant(self):
        autre = Quiz.objects.create(titre='Autre', cree_par=self.a.ens)
        Question.objects.create(quiz=autre, texte='Q', points=Decimal('1'))
        t = self.tentative(self.a.etu, 1, [], '', quiz=autre)
        TentativeQuiz.objects.filter(pk=t.pk).update(debut=self.depart - timedelta(days=2),
                                                     soumise_le=self.depart - timedelta(days=2))
        fiche = statistiques.resultats_etudiant(self.a.etu, Quiz.objects.filter(cree_par=self.a.ens))
        self.assertEqual(fiche['etudiant']['id'], self.a.etu.id)
        self.assertEqual([r['titre'] for r in fiche['resultats']], ['Autre', 'Quiz A'])
        dernier = fiche['resultats'][1]
        self.assertEqual((dernier['nb_tentatives'], dernier['score'], dernier['score_max'], dernier['pourcentage']),
                         (2, '3.00', '3.00', '100.00'))
        self.assertEqual(statistiques.resultats_etudiant(self.a.etu, Quiz.objects.none())['resultats'], [])


class StatistiquesApiTests(Scenario, TestCase):
    def setUp(self):
        self.preparer()

    def test_tableau_de_bord(self):
        res = client_for(self.a.ens).get(f'{Q}/quizzes/{self.quiz.id}/statistiques/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(set(res.data), {'titre', 'population', 'notes', 'distribution', 'questions', 'etudiants'})
        self.assertEqual(res.data['population']['taux_participation'], '60.00')
        self.assertEqual(client_for(self.a.admin).get(f'{Q}/quizzes/{self.quiz.id}/statistiques/').status_code, 200)

    def test_droits(self):
        url = f'{Q}/quizzes/{self.quiz.id}/statistiques/'
        self.assertEqual(client_for(self.w.b.ens).get(url).status_code, 404)
        self.assertEqual(client_for(self.w.b.admin).get(url).status_code, 404)
        self.assertEqual(client_for(self.a.etu).get(url).status_code, 403)
        self.assertEqual(client_for(self.a.etu).get(f'{Q}/quizzes/statistiques/').status_code, 403)
        self.assertEqual(client_for(self.a.etu).get(f'{Q}/etudiants/{self.a.etu.id}/resultats/').status_code, 403)

    def test_tentatives_expirees_cloturees(self):
        t = TentativeQuiz.objects.get(etudiant=self.etu3)
        TentativeQuiz.objects.filter(pk=t.pk).update(fin_prevue=timezone.now() - timedelta(hours=1))
        res = client_for(self.a.ens).get(f'{Q}/quizzes/{self.quiz.id}/statistiques/')
        self.assertEqual(res.data['population']['soumis'], 4)

    def test_vue_ensemble(self):
        res = client_for(self.a.ens).get(f'{Q}/quizzes/statistiques/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual([q['id'] for q in res.data['results']], [self.quiz.id])
        ligne = res.data['results'][0]
        self.assertEqual(ligne['notes']['moyenne'], '1.33')
        self.assertEqual(ligne['nb_a_valider'], 4)
        ids_b = [q['id'] for q in client_for(self.w.b.ens).get(f'{Q}/quizzes/statistiques/').data['results']]
        self.assertEqual(ids_b, [self.w.b.quiz.id])

    def test_fiche_etudiant(self):
        url = f'{Q}/etudiants/{self.a.etu.id}/resultats/'
        res = client_for(self.a.ens).get(url)
        self.assertEqual(res.status_code, 200)
        self.assertEqual([r['titre'] for r in res.data['resultats']], ['Quiz A'])
        self.assertEqual(client_for(self.a.admin).get(url).status_code, 200)
        self.assertEqual(client_for(self.w.b.ens).get(url).status_code, 404)
        self.assertEqual(client_for(self.w.b.admin).get(url).status_code, 404)
        self.assertEqual(client_for(self.a.ens).get(f'{Q}/etudiants/{self.w.b.etu.id}/resultats/').status_code, 404)
        self.assertEqual(client_for(self.a.ens).get(f'{Q}/etudiants/{self.a.ens.id}/resultats/').status_code, 404)
        self.assertEqual(client_for(self.a.ens).get(f'{Q}/etudiants/99999999999999999999999/resultats/').status_code, 404)

    def test_fiche_etudiant_ayant_une_tentative_hors_classe(self):
        Inscription.objects.filter(etudiant=self.etu5).delete()
        self.assertEqual(client_for(self.a.ens).get(f'{Q}/etudiants/{self.etu5.id}/resultats/').status_code, 200)
        Inscription.objects.filter(etudiant=self.etu4).delete()
        self.assertEqual(client_for(self.a.ens).get(f'{Q}/etudiants/{self.etu4.id}/resultats/').status_code, 404)
