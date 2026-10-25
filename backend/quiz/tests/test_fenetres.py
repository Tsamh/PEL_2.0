from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.testing import build_world, client_for, make_user
from quiz.correction import corriger_tentative
from quiz.models import ReponseQuiz, SessionQuiz, TentativeQuiz
from referentiel.models import Groupe, Inscription

Q = '/api/quiz'


class FenetresTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def setUp(self):
        self.a = self.w.a
        self.quiz = self.a.quiz
        self.maintenant = timezone.now()
        self.etu2 = make_user('etu2', 'etudiant', self.a.etab)
        Inscription.objects.create(etudiant=self.etu2, classe=self.a.classe)
        self.bon = self.a.question.choix.get(texte='4')
        self.mauvais = self.a.question.choix.get(texte='5')

    def session(self, debut, fin, type_session=SessionQuiz.NORMALE, classes=(), groupes=(), etudiants=(), bonus=1):
        s = SessionQuiz.objects.create(quiz=self.quiz, type=type_session, ouverture=self.maintenant + debut,
                                       fermeture=self.maintenant + fin, tentatives_supplementaires=bonus)
        s.classes.set(classes)
        s.groupes.set(groupes)
        s.etudiants.set(etudiants)
        return s

    def demarrer(self, etudiant):
        return client_for(etudiant).post(f'{Q}/quizzes/{self.quiz.id}/demarrer/')

    def etat(self, etudiant):
        return client_for(etudiant).get(f'{Q}/quizzes/{self.quiz.id}/').data['etat']

    def soumise(self, etudiant, choix):
        t = TentativeQuiz.objects.create(quiz=self.quiz, etudiant=etudiant,
                                         numero=self.quiz.tentatives.filter(etudiant=etudiant).count() + 1,
                                         fin_prevue=self.maintenant, soumise_le=self.maintenant,
                                         statut=TentativeQuiz.SOUMISE)
        ReponseQuiz.objects.create(tentative=t, question=self.a.question).choix_selectionnes.set([choix])
        corriger_tentative(t)
        return t

    def test_sans_session_rien_ne_change(self):
        etat = self.etat(self.a.etu)
        self.assertTrue(etat['ouvert'])
        self.assertEqual(etat['tentatives_max'], 1)
        self.assertEqual(etat['fenetre'], {'ouverture': None, 'fermeture': None, 'prochaine_ouverture': None})
        self.assertEqual(self.demarrer(self.a.etu).status_code, 201)

    def test_session_future_par_classe(self):
        self.session(timedelta(days=1), timedelta(days=1, hours=2), classes=[self.a.classe])
        res = self.demarrer(self.a.etu)
        self.assertEqual(res.status_code, 409)
        self.assertIn('pas encore ouvert', str(res.data))
        etat = self.etat(self.a.etu)
        self.assertFalse(etat['ouvert'])
        self.assertIsNotNone(etat['fenetre']['prochaine_ouverture'])

    def test_session_ouverte_plafonne_la_fin(self):
        s = self.session(-timedelta(minutes=5), timedelta(minutes=10), classes=[self.a.classe])
        res = self.demarrer(self.a.etu)
        self.assertEqual(res.status_code, 201)
        tentative = TentativeQuiz.objects.get(pk=res.data['id'])
        self.assertEqual(tentative.fin_prevue, s.fermeture)

    def test_la_plus_favorable_l_emporte(self):
        self.session(-timedelta(days=3), -timedelta(days=2), classes=[self.a.classe])
        self.session(-timedelta(hours=1), timedelta(hours=1), classes=[self.a.classe])
        self.assertTrue(self.etat(self.a.etu)['ouvert'])

    def test_groupe_et_etudiant_non_cible(self):
        groupe = Groupe.objects.create(code='TD1A', libelle='TD 1', classe=self.a.classe)
        groupe.membres.add(self.a.etu)
        self.session(timedelta(days=1), timedelta(days=2), groupes=[groupe])
        self.assertEqual(self.demarrer(self.a.etu).status_code, 409)
        self.assertEqual(self.demarrer(self.etu2).status_code, 201)

    def test_membre_desinscrit_n_est_pas_vise(self):
        groupe = Groupe.objects.create(code='TD1A', libelle='TD 1', classe=self.a.classe)
        groupe.membres.add(self.etu2)
        Inscription.objects.filter(etudiant=self.etu2).delete()
        self.quiz.etudiants.add(self.etu2)
        self.session(timedelta(days=1), timedelta(days=2), groupes=[groupe])
        self.assertEqual(self.demarrer(self.etu2).status_code, 201)

    def test_rattrapage_ajoute_des_tentatives(self):
        self.soumise(self.a.etu, self.mauvais)
        self.assertEqual(self.demarrer(self.a.etu).status_code, 409)
        self.session(-timedelta(minutes=1), timedelta(hours=1), type_session=SessionQuiz.RATTRAPAGE,
                     etudiants=[self.a.etu], bonus=1)
        etat = self.etat(self.a.etu)
        self.assertEqual((etat['tentatives_max'], etat['tentatives_restantes']), (2, 1))
        res = self.demarrer(self.a.etu)
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['numero'], 2)
        self.assertEqual(self.etat(self.etu2)['tentatives_max'], 1)

    def test_rattrapage_futur_n_ajoute_pas_de_tentative(self):
        self.soumise(self.a.etu, self.mauvais)
        self.session(timedelta(days=1), timedelta(days=2), type_session=SessionQuiz.RATTRAPAGE, etudiants=[self.a.etu])
        res = self.demarrer(self.a.etu)
        self.assertEqual(res.status_code, 409)
        self.assertIn('plus de tentative', str(res.data))
        etat = self.etat(self.a.etu)
        self.assertEqual(etat['tentatives_max'], 1)
        self.assertIsNotNone(etat['fenetre']['prochaine_ouverture'])

    def test_rattrapage_termine_n_ajoute_pas_de_tentative(self):
        self.soumise(self.a.etu, self.mauvais)
        self.session(-timedelta(days=2), -timedelta(days=1), type_session=SessionQuiz.RATTRAPAGE, etudiants=[self.a.etu])
        self.assertEqual(self.etat(self.a.etu)['tentatives_max'], 1)
        self.assertEqual(self.demarrer(self.a.etu).status_code, 409)

    def test_rattrapage_futur_quand_le_quiz_est_ferme(self):
        self.quiz.date_fin = self.maintenant - timedelta(hours=1)
        self.quiz.save()
        self.session(timedelta(days=1), timedelta(days=2), type_session=SessionQuiz.RATTRAPAGE, etudiants=[self.a.etu])
        res = self.demarrer(self.a.etu)
        self.assertEqual(res.status_code, 409)
        self.assertIn('pas encore ouvert', str(res.data))
        res = self.demarrer(self.etu2)
        self.assertEqual(res.status_code, 409)
        self.assertIn('fermé', str(res.data))

    def test_corrige_retarde_par_un_rattrapage(self):
        self.quiz.afficher_corrige = True
        self.quiz.save()
        t = self.soumise(self.a.etu, self.mauvais)
        url = f'{Q}/tentatives/{t.id}/'
        self.assertIsNotNone(client_for(self.a.etu).get(url).data['corrige'])
        self.session(timedelta(days=1), timedelta(days=2), type_session=SessionQuiz.RATTRAPAGE, etudiants=[self.a.etu])
        self.assertIsNone(client_for(self.a.etu).get(url).data['corrige'])

    def test_candidats_au_rattrapage(self):
        etu3 = make_user('etu3', 'etudiant', self.a.etab)
        Inscription.objects.create(etudiant=etu3, classe=self.a.classe)
        self.soumise(self.a.etu, self.mauvais)
        self.soumise(etu3, self.bon)
        ens = client_for(self.a.ens)
        res = ens.get(f'{Q}/quizzes/{self.quiz.id}/candidats_rattrapage/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual({c['id'] for c in res.data}, {self.a.etu.id, self.etu2.id})
        etu = next(c for c in res.data if c['id'] == self.a.etu.id)
        self.assertEqual((etu['statut'], etu['meilleure_pourcentage']), ('soumis', '0.00'))
        self.assertIsNone(next(c for c in res.data if c['id'] == self.etu2.id)['meilleure_pourcentage'])
        self.assertEqual({c['id'] for c in ens.get(f'{Q}/quizzes/{self.quiz.id}/candidats_rattrapage/?seuil=0').data},
                         {self.etu2.id})
        for seuil in ('abc', '150', '-1'):
            self.assertEqual(ens.get(f'{Q}/quizzes/{self.quiz.id}/candidats_rattrapage/?seuil={seuil}').status_code, 400)
        self.assertEqual(client_for(self.w.b.ens).get(f'{Q}/quizzes/{self.quiz.id}/candidats_rattrapage/').status_code, 404)
        self.assertEqual(client_for(self.a.etu).get(f'{Q}/quizzes/{self.quiz.id}/candidats_rattrapage/').status_code, 403)
