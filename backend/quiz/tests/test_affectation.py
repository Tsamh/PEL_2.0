from django.test import TestCase
from django.utils import timezone

from accounts.testing import build_world, client_for, make_user
from audit.models import AuditLog
from quiz.models import TentativeQuiz
from referentiel.models import AffectationEnseignant, Classe, EnseignantMatiere, Groupe, Inscription

Q = '/api/quiz/quizzes'
T = '/api/quiz/tentatives'


class VisibiliteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def setUp(self):
        self.a = self.w.a
        self.quiz = self.a.quiz
        self.quiz.classes.clear()
        self.voisin = make_user('voisin', 'etudiant', self.a.etab)
        Inscription.objects.create(etudiant=self.voisin, classe=self.a.classe)

    def ids(self, user):
        res = client_for(user).get(f'{Q}/')
        self.assertEqual(res.status_code, 200)
        return {q['id'] for q in res.data['results']}

    def assert_invisible(self, user):
        client = client_for(user)
        self.assertNotIn(self.quiz.id, self.ids(user))
        self.assertEqual(client.get(f'{Q}/{self.quiz.id}/').status_code, 404)
        self.assertEqual(client.post(f'{Q}/{self.quiz.id}/demarrer/').status_code, 404)

    def test_sans_affectation_invisible(self):
        self.assert_invisible(self.a.etu)
        self.assert_invisible(self.voisin)

    def test_affecte_par_classe(self):
        self.quiz.classes.add(self.a.classe)
        self.assertIn(self.quiz.id, self.ids(self.a.etu))
        self.assertIn(self.quiz.id, self.ids(self.voisin))

    def test_affecte_par_groupe(self):
        groupe = Groupe.objects.create(code='TD1A', libelle='TD 1', classe=self.a.classe)
        groupe.membres.add(self.a.etu)
        self.quiz.groupes.add(groupe)
        self.assertIn(self.quiz.id, self.ids(self.a.etu))
        self.assert_invisible(self.voisin)

    def test_affecte_nominativement(self):
        self.quiz.etudiants.add(self.voisin)
        self.assertIn(self.quiz.id, self.ids(self.voisin))
        self.assert_invisible(self.a.etu)

    def test_meme_filiere_autre_classe_non_affecte(self):
        self.quiz.classes.add(self.a.classe)
        autre_classe = Classe.objects.create(
            code='L1X', libelle='L1 Info X', filiere=self.a.filiere, niveau=self.w.niveau,
            annee_academique=self.a.annee,
        )
        autre = make_user('autre', 'etudiant', self.a.etab)
        Inscription.objects.create(etudiant=autre, classe=autre_classe)
        self.assert_invisible(autre)

    def test_inscrit_apres_affectation(self):
        self.quiz.classes.add(self.a.classe)
        nouveau = make_user('nouveau', 'etudiant', self.a.etab)
        Inscription.objects.create(etudiant=nouveau, classe=self.a.classe)
        self.assertIn(self.quiz.id, self.ids(nouveau))

    def test_non_publie_invisible(self):
        self.quiz.classes.add(self.a.classe)
        self.quiz.est_publie = False
        self.quiz.save()
        self.assert_invisible(self.a.etu)

    def test_pas_de_doublon_avec_plusieurs_cibles(self):
        groupe = Groupe.objects.create(code='TD1A', libelle='TD 1', classe=self.a.classe)
        groupe.membres.add(self.a.etu)
        self.quiz.classes.add(self.a.classe)
        self.quiz.groupes.add(groupe)
        self.quiz.etudiants.add(self.a.etu)
        res = client_for(self.a.etu).get(f'{Q}/')
        self.assertEqual([q['id'] for q in res.data['results']].count(self.quiz.id), 1)

    def test_retrait_conserve_la_tentative(self):
        self.quiz.etudiants.add(self.voisin)
        client = client_for(self.voisin)
        res = client.post(f'{Q}/{self.quiz.id}/demarrer/')
        self.assertEqual(res.status_code, 201)
        tentative_id = res.data['id']
        self.quiz.etudiants.remove(self.voisin)
        self.assertEqual(client.post(f'{Q}/{self.quiz.id}/demarrer/').status_code, 404)
        self.assertEqual(client.get(f'{T}/{tentative_id}/').status_code, 200)
        self.assertEqual(client.post(f'{T}/{tentative_id}/soumettre/').status_code, 200)
        liste = client.get(f'{T}/').data
        ids = {t['id'] for t in (liste['results'] if isinstance(liste, dict) else liste)}
        self.assertIn(tentative_id, ids)

    def test_tableau_de_bord(self):
        url = '/api/accounts/users/dashboard_stats/'
        self.assertEqual(client_for(self.a.etu).get(url).data['quiz_disponibles'], 0)
        self.quiz.classes.add(self.a.classe)
        self.assertEqual(client_for(self.a.etu).get(url).data['quiz_disponibles'], 1)


class EcritureAffectationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def setUp(self):
        self.a = self.w.a
        self.quiz = self.a.quiz
        self.quiz.classes.clear()
        self.classe_hors = Classe.objects.create(
            code='L1Z', libelle='L1 Info Z', filiere=self.a.filiere, niveau=self.w.niveau,
            annee_academique=self.a.annee,
        )
        self.etu_hors = make_user('etuhors', 'etudiant', self.a.etab)
        Inscription.objects.create(etudiant=self.etu_hors, classe=self.classe_hors)
        self.groupe = Groupe.objects.create(code='TD1A', libelle='TD 1', classe=self.a.classe)
        self.groupe_hors = Groupe.objects.create(code='TD1Z', libelle='TD 1 Z', classe=self.classe_hors)

    def patch(self, user, corps):
        return client_for(user).patch(f'{Q}/{self.quiz.id}/', corps, format='json')

    def test_enseignant_affecte_sa_classe_son_groupe_ses_etudiants(self):
        res = self.patch(self.a.ens, {
            'classes': [self.a.classe.id], 'groupes': [self.groupe.id], 'etudiants': [self.a.etu.id],
        })
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data['classes_detail'], [{'id': self.a.classe.id, 'code': 'L1A', 'libelle': 'L1 Info A'}])
        self.assertEqual(res.data['groupes_detail'][0]['classe_code'], 'L1A')
        self.assertEqual(res.data['etudiants_detail'][0]['id'], self.a.etu.id)
        self.assertEqual(res.data['nb_cibles'], 3)

    def test_enseignant_refuse_hors_perimetre(self):
        for corps, cle in [
            ({'classes': [self.classe_hors.id]}, 'classes'),
            ({'classes': [self.w.b.classe.id]}, 'classes'),
            ({'groupes': [self.groupe_hors.id]}, 'groupes'),
            ({'etudiants': [self.etu_hors.id]}, 'etudiants'),
            ({'etudiants': [self.a.ens.id]}, 'etudiants'),
        ]:
            with self.subTest(corps=corps):
                res = self.patch(self.a.ens, corps)
                self.assertEqual(res.status_code, 400)
                self.assertIn(cle, res.data)
        self.assertFalse(self.quiz.classes.exists())

    def test_gestion_limitee_a_son_etablissement(self):
        self.assertEqual(self.patch(self.a.admin, {'classes': [self.classe_hors.id]}).status_code, 200)
        self.assertEqual(self.patch(self.a.resp, {'etudiants': [self.etu_hors.id]}).status_code, 200)
        res = self.patch(self.a.admin, {'classes': [self.w.b.classe.id]})
        self.assertEqual(res.status_code, 400)
        self.assertIn('classes', res.data)

    def test_superadmin_sans_limite(self):
        res = self.patch(self.w.superadmin, {'classes': [self.w.b.classe.id], 'etudiants': [self.w.b.etu.id]})
        self.assertEqual(res.status_code, 200, res.data)

    def test_affectation_conservee_quand_l_enseignant_perd_la_classe(self):
        self.quiz.classes.add(self.a.classe)
        AffectationEnseignant.objects.filter(enseignant=self.a.ens).delete()
        EnseignantMatiere.objects.filter(enseignant=self.a.ens).delete()
        self.assertEqual(self.patch(self.a.ens, {'titre': 'Renommé'}).status_code, 200)
        self.assertEqual(self.patch(self.a.ens, {'classes': [self.a.classe.id]}).status_code, 200)
        self.assertEqual(list(self.quiz.classes.all()), [self.a.classe])
        self.assertEqual(self.patch(self.a.ens, {'classes': []}).status_code, 200)
        self.assertFalse(self.quiz.classes.exists())

    def test_creation_avec_affectation_et_audit(self):
        res = client_for(self.a.ens).post(f'{Q}/', {'titre': 'Nouveau', 'classes': [self.a.classe.id]}, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        log = AuditLog.objects.get(action='affectation_quiz', cible_id=str(res.data['id']))
        self.assertEqual(log.details['ajouts']['classes'], [self.a.classe.id])
        self.assertEqual(log.details['retraits'], {'classes': [], 'groupes': [], 'etudiants': []})

    def test_audit_seulement_si_changement(self):
        self.patch(self.a.ens, {'classes': [self.a.classe.id]})
        self.assertEqual(AuditLog.objects.filter(action='affectation_quiz').count(), 1)
        self.patch(self.a.ens, {'titre': 'Autre titre'})
        self.patch(self.a.ens, {'classes': [self.a.classe.id]})
        self.assertEqual(AuditLog.objects.filter(action='affectation_quiz').count(), 1)
        self.patch(self.a.ens, {'classes': [], 'etudiants': [self.a.etu.id]})
        log = AuditLog.objects.filter(action='affectation_quiz').order_by('-id').first()
        self.assertEqual(log.details['retraits']['classes'], [self.a.classe.id])
        self.assertEqual(log.details['ajouts']['etudiants'], [self.a.etu.id])

    def test_modifiable_apres_une_tentative(self):
        TentativeQuiz.objects.create(quiz=self.quiz, etudiant=self.a.etu, fin_prevue=timezone.now())
        self.assertEqual(self.patch(self.a.ens, {'classes': [self.a.classe.id]}).status_code, 200)

    def test_vue_etudiant_sans_cibles_ni_code(self):
        self.quiz.classes.add(self.a.classe)
        res = client_for(self.a.etu).get(f'{Q}/{self.quiz.id}/')
        self.assertEqual(res.status_code, 200)
        for champ in ('classes', 'groupes', 'etudiants', 'classes_detail', 'etudiants_detail', 'code_acces'):
            self.assertNotIn(champ, res.data)

    def test_code_acces_en_lecture_seule(self):
        res = self.patch(self.a.ens, {'code_acces': 'AAAAAA'})
        self.assertEqual(res.status_code, 200)
        self.quiz.refresh_from_db()
        self.assertEqual(self.quiz.code_acces, '')
