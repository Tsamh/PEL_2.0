import json

from django.test import TestCase

from accounts.testing import build_world, client_for, make_user
from audit.models import AuditLog
from programming.models import Devoir, SoumissionDevoir, NoteMatiere

P = '/api/programming'


def ids(res):
    return {o['id'] for o in res.data['results']}


class DevoirsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def test_etudiant_ne_recoit_ni_solution_ni_tests(self):
        a = self.w.a
        for url in (f'{P}/devoirs/', f'{P}/devoirs/{a.devoir.id}/'):
            with self.subTest(url=url):
                contenu = json.dumps(client_for(a.etu).get(url).data)
                self.assertNotIn('solution', contenu)
                self.assertNotIn('test_cases', contenu)

    def test_etudiant_limite_a_ses_filieres(self):
        a, b = self.w.a, self.w.b
        self.assertEqual(ids(client_for(a.etu).get(f'{P}/devoirs/')), {a.devoir.id})
        self.assertEqual(client_for(a.etu).get(f'{P}/devoirs/{b.devoir.id}/').status_code, 404)

    def test_ecriture(self):
        a, b = self.w.a, self.w.b
        self.assertEqual(client_for(a.etu).post(f'{P}/devoirs/', {'titre': 'X'}, format='json').status_code, 403)
        res = client_for(a.ens).post(f'{P}/devoirs/', {'titre': 'Piège', 'filiere': b.filiere.id}, format='json')
        self.assertEqual(res.status_code, 400)
        res = client_for(a.resp).post(f'{P}/devoirs/', {'titre': 'TP', 'filiere': a.filiere.id, 'cree_par': b.ens.id}, format='json')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(Devoir.objects.get(titre='TP').cree_par, a.resp)

    def test_suppression_journalisee(self):
        a = self.w.a
        self.assertEqual(client_for(a.ens).delete(f'{P}/devoirs/{a.devoir.id}/').status_code, 204)
        self.assertTrue(AuditLog.objects.filter(action='suppression_evaluation', details__type='devoir').exists())


class SoumissionsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def test_etudiant_soumet_sur_un_devoir_visible(self):
        a, b = self.w.a, self.w.b
        client = client_for(a.etu)
        self.assertEqual(client.post(f'{P}/soumissions/', {'devoir': a.devoir.id, 'code_soumis': 'print(4)'}, format='json').status_code, 201)
        self.assertEqual(client.post(f'{P}/soumissions/', {'devoir': b.devoir.id, 'code_soumis': 'x'}, format='json').status_code, 400)

    def test_seul_l_etudiant_soumet(self):
        a = self.w.a
        res = client_for(a.ens).post(f'{P}/soumissions/', {'devoir': a.devoir.id, 'code_soumis': 'x'}, format='json')
        self.assertEqual(res.status_code, 403)

    def test_correction(self):
        a, b = self.w.a, self.w.b
        soumission = SoumissionDevoir.objects.create(devoir=a.devoir, etudiant=a.etu, code_soumis='print(4)')
        url = f'{P}/soumissions/{soumission.id}/corriger/'
        self.assertEqual(client_for(a.etu).post(url, {'score': 20}, format='json').status_code, 403)
        self.assertEqual(client_for(b.ens).post(url, {'score': 20}, format='json').status_code, 404)
        self.assertEqual(client_for(a.ens).post(url, {'score': 12}, format='json').status_code, 200)
        saisie = AuditLog.objects.get(action='saisie_note')
        self.assertEqual(saisie.details['apres'], 12)
        self.assertEqual(client_for(a.admin).post(url, {'score': 15}, format='json').status_code, 200)
        modif = AuditLog.objects.get(action='modification_note')
        self.assertEqual((modif.details['avant'], modif.details['apres']), (12, 15))

    def test_etudiant_ne_modifie_pas_sa_soumission(self):
        a = self.w.a
        soumission = SoumissionDevoir.objects.create(devoir=a.devoir, etudiant=a.etu, code_soumis='x')
        res = client_for(a.etu).patch(f'{P}/soumissions/{soumission.id}/', {'code_soumis': 'y'}, format='json')
        self.assertEqual(res.status_code, 403)


class NotesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def bulk(self, user, classe, ec, notes):
        return client_for(user).post(f'{P}/notes/bulk_update/', {
            'ec': ec.id, 'classe': classe.id, 'annee_academique': classe.annee_academique_id, 'notes': notes,
        }, format='json')

    def test_enseignant_saisit_puis_modifie(self):
        a = self.w.a
        res = self.bulk(a.ens, a.classe, a.ec, [{'etudiant': a.etu.id, 'note_devoir': 12, 'note_examen': 14}])
        self.assertEqual(res.status_code, 200)
        self.assertTrue(AuditLog.objects.filter(action='saisie_note', cible_id=str(NoteMatiere.objects.get().id)).exists())
        self.bulk(a.ens, a.classe, a.ec, [{'etudiant': a.etu.id, 'note_devoir': 12, 'note_examen': 14}])
        self.assertFalse(AuditLog.objects.filter(action='modification_note').exists())
        self.bulk(a.ens, a.classe, a.ec, [{'etudiant': a.etu.id, 'note_devoir': 13, 'note_examen': 14}])
        modif = AuditLog.objects.get(action='modification_note')
        self.assertEqual(modif.details['avant']['note_devoir'], 12)
        self.assertEqual(modif.details['apres']['note_devoir'], 13)

    def test_classe_hors_perimetre(self):
        a, b = self.w.a, self.w.b
        self.assertEqual(self.bulk(a.ens, b.classe, b.ec, [{'etudiant': b.etu.id, 'note_devoir': 1}]).status_code, 404)
        self.assertEqual(self.bulk(a.admin, b.classe, b.ec, [{'etudiant': b.etu.id, 'note_devoir': 1}]).status_code, 404)
        self.assertFalse(NoteMatiere.objects.exists())

    def test_ec_non_enseignee_refusee(self):
        a, b = self.w.a, self.w.b
        self.assertEqual(self.bulk(a.ens, a.classe, b.ec, [{'etudiant': a.etu.id, 'note_devoir': 1}]).status_code, 404)

    def test_etudiant_non_inscrit_ignore(self):
        a = self.w.a
        intrus = make_user('etuIntrus', 'etudiant', a.etab)
        res = self.bulk(a.ens, a.classe, a.ec, [{'etudiant': intrus.id, 'note_devoir': 20}])
        self.assertEqual(res.data['ignores'], 1)
        self.assertFalse(NoteMatiere.objects.filter(etudiant=intrus).exists())

    def test_droits_etudiant(self):
        a = self.w.a
        self.assertEqual(self.bulk(a.etu, a.classe, a.ec, []).status_code, 403)
        self.assertEqual(client_for(a.etu).post(f'{P}/notes/', {}, format='json').status_code, 403)
        self.assertEqual(client_for(a.etu).get(f'{P}/notes/mes_notes/').status_code, 200)
        self.assertEqual(client_for(a.ens).get(f'{P}/notes/mes_notes/').status_code, 403)


class ControlesNotesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def corps(self, a, **extra):
        data = {'etudiant': a.etu.id, 'ec': a.ec.id, 'classe': a.classe.id,
                'annee_academique': a.annee.id, 'note_devoir': 10, 'note_examen': 12}
        data.update(extra)
        return data

    def test_post_direct_ec_hors_perimetre(self):
        a, b = self.w.a, self.w.b
        res = client_for(a.ens).post(f'{P}/notes/', self.corps(a, ec=b.ec.id), format='json')
        self.assertEqual(res.status_code, 400)
        self.assertFalse(NoteMatiere.objects.exists())

    def test_post_direct_etudiant_non_inscrit(self):
        a = self.w.a
        intrus = make_user('etuIntrus2', 'etudiant', a.etab)
        res = client_for(a.ens).post(f'{P}/notes/', self.corps(a, etudiant=intrus.id), format='json')
        self.assertEqual(res.status_code, 400)
        self.assertFalse(NoteMatiere.objects.exists())

    def test_post_direct_classe_ou_annee_hors_perimetre(self):
        a, b = self.w.a, self.w.b
        res = client_for(a.admin).post(f'{P}/notes/', self.corps(a, classe=b.classe.id), format='json')
        self.assertEqual(res.status_code, 400)
        res = client_for(a.admin).post(f'{P}/notes/', self.corps(a, annee_academique=b.annee.id), format='json')
        self.assertEqual(res.status_code, 400)
        self.assertFalse(NoteMatiere.objects.exists())

    def test_post_direct_valide(self):
        a = self.w.a
        res = client_for(a.ens).post(f'{P}/notes/', self.corps(a), format='json')
        self.assertEqual(res.status_code, 201)
        self.assertTrue(AuditLog.objects.filter(action='saisie_note').exists())

    def test_patch_direct_ec_hors_perimetre(self):
        a, b = self.w.a, self.w.b
        note = NoteMatiere.objects.create(etudiant=a.etu, ec=a.ec, classe=a.classe, annee_academique=a.annee, note_devoir=5)
        res = client_for(a.ens).patch(f'{P}/notes/{note.id}/', {'ec': b.ec.id}, format='json')
        self.assertEqual(res.status_code, 400)
        note.refresh_from_db()
        self.assertEqual(note.ec_id, a.ec.id)

    def test_references_devoir_hors_perimetre(self):
        a, b = self.w.a, self.w.b
        res = client_for(a.ens).post(f'{P}/devoirs/', {'titre': 'X', 'filiere': a.filiere.id, 'ec': b.ec.id}, format='json')
        self.assertEqual(res.status_code, 400)
        res = client_for(a.admin).post(f'{P}/devoirs/', {'titre': 'Y', 'filiere': a.filiere.id, 'annee_academique': b.annee.id}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertFalse(Devoir.objects.filter(titre__in=['X', 'Y']).exists())

    def test_references_quiz_hors_perimetre(self):
        from quiz.models import Quiz
        a, b = self.w.a, self.w.b
        res = client_for(a.admin).post('/api/quiz/quizzes/', {'titre': 'Q', 'filiere': a.filiere.id, 'annee_academique': b.annee.id}, format='json')
        self.assertEqual(res.status_code, 400, res.content)
        self.assertFalse(Quiz.objects.filter(titre='Q').exists())

    def test_corriger_score_invalide(self):
        a = self.w.a
        s = SoumissionDevoir.objects.create(devoir=a.devoir, etudiant=a.etu, code_soumis='x')
        url = f'{P}/soumissions/{s.id}/corriger/'
        for score in ('abc', 25, -1, 1.5):
            self.assertEqual(client_for(a.ens).post(url, {'score': score}, format='json').status_code, 400, score)
        s.refresh_from_db()
        self.assertIsNone(s.score)

    def bulk(self, a, notes, **extra):
        data = {'ec': a.ec.id, 'classe': a.classe.id, 'annee_academique': a.annee.id, 'notes': notes}
        data.update(extra)
        return client_for(a.ens).post(f'{P}/notes/bulk_update/', data, format='json')

    def test_bulk_note_hors_bornes(self):
        a = self.w.a
        res = self.bulk(a, [{'etudiant': a.etu.id, 'note_devoir': 10}, {'etudiant': a.etu.id, 'note_examen': 25}])
        self.assertEqual(res.status_code, 400)
        self.assertFalse(NoteMatiere.objects.exists())
        self.assertEqual(self.bulk(a, [{'etudiant': a.etu.id, 'note_devoir': 'x'}]).status_code, 400)

    def test_bulk_notes_pas_une_liste(self):
        a = self.w.a
        self.assertEqual(self.bulk(a, 'abc').status_code, 400)
        self.assertEqual(self.bulk(a, ['abc']).status_code, 400)

    def test_bulk_annee_incoherente(self):
        a, b = self.w.a, self.w.b
        self.assertEqual(self.bulk(a, [], annee_academique=b.annee.id).status_code, 400)

    def test_bulk_etudiant_chaine_numerique(self):
        a = self.w.a
        res = self.bulk(a, [{'etudiant': str(a.etu.id), 'note_devoir': 10}])
        self.assertEqual(res.status_code, 200)
        self.assertEqual(NoteMatiere.objects.count(), 1)


class AuditEtValidationNotesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def test_suppression_note_journalisee(self):
        a = self.w.a
        note = NoteMatiere.objects.create(etudiant=a.etu, ec=a.ec, classe=a.classe, annee_academique=a.annee,
                                          note_devoir=5, note_examen=7)
        self.assertEqual(client_for(a.ens).delete(f'{P}/notes/{note.id}/').status_code, 204)
        log = AuditLog.objects.get(action='modification_note')
        self.assertEqual(log.details['type'], 'note_matiere')
        self.assertEqual(log.details['etudiant'], a.etu.id)
        self.assertEqual(log.details['avant'], {'note_devoir': 5, 'note_examen': 7})
        self.assertIsNone(log.details['apres'])
        self.assertEqual(log.etablissement, a.etab)

    def test_suppression_soumission_journalisee(self):
        a = self.w.a
        s = SoumissionDevoir.objects.create(devoir=a.devoir, etudiant=a.etu, code_soumis='x', score=8)
        self.assertEqual(client_for(a.ens).delete(f'{P}/soumissions/{s.id}/').status_code, 204)
        log = AuditLog.objects.get(action='modification_note')
        self.assertEqual(log.details['type'], 'soumission')
        self.assertEqual(log.details['avant'], {'score': 8})
        self.assertIsNone(log.details['apres'])
        self.assertEqual(log.etablissement, a.etab)

    def test_correcteur_ne_modifie_ni_code_ni_devoir(self):
        a = self.w.a
        autre = Devoir.objects.create(titre='Autre', filiere=a.filiere, cree_par=a.ens, est_publie=True)
        s = SoumissionDevoir.objects.create(devoir=a.devoir, etudiant=a.etu, code_soumis='original')
        res = client_for(a.ens).patch(f'{P}/soumissions/{s.id}/',
                                      {'code_soumis': 'falsifie', 'devoir': autre.id}, format='json')
        self.assertIn(res.status_code, (200, 400))
        s.refresh_from_db()
        self.assertEqual(s.code_soumis, 'original')
        self.assertEqual(s.devoir_id, a.devoir.id)

    def test_note_directe_hors_bornes(self):
        a = self.w.a
        corps = {'etudiant': a.etu.id, 'ec': a.ec.id, 'classe': a.classe.id, 'annee_academique': a.annee.id}
        for champ in ('note_devoir', 'note_examen'):
            for valeur in (21, -1):
                res = client_for(a.ens).post(f'{P}/notes/', {**corps, champ: valeur}, format='json')
                self.assertEqual(res.status_code, 400, (champ, valeur))
        self.assertFalse(NoteMatiere.objects.exists())
        res = client_for(a.ens).post(f'{P}/notes/', {**corps, 'note_devoir': None, 'note_examen': 20}, format='json')
        self.assertEqual(res.status_code, 201, res.content)


class EntreesNumeriquesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def bulk(self, a, notes, **extra):
        data = {'ec': a.ec.id, 'classe': a.classe.id, 'annee_academique': a.annee.id, 'notes': notes}
        data.update(extra)
        return client_for(a.ens).post(f'{P}/notes/bulk_update/', data, format='json')

    def test_corriger_score_chiffre_non_ascii(self):
        a = self.w.a
        s = SoumissionDevoir.objects.create(devoir=a.devoir, etudiant=a.etu, code_soumis='x')
        res = client_for(a.ens).post(f'{P}/soumissions/{s.id}/corriger/', {'score': '²'}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_bulk_ec_ou_classe_non_numerique(self):
        a = self.w.a
        self.assertEqual(self.bulk(a, [], ec='abc').status_code, 400)
        self.assertEqual(self.bulk(a, [], classe='abc').status_code, 400)
        self.assertEqual(self.bulk(a, [], ec='²').status_code, 400)

    def test_bulk_etudiant_non_scalaire(self):
        a = self.w.a
        for valeur in ([1], {'id': 1}):
            res = self.bulk(a, [{'etudiant': valeur, 'note_devoir': 10}])
            self.assertEqual(res.status_code, 400, valeur)
        self.assertFalse(NoteMatiere.objects.exists())

    def test_bulk_etudiant_illisible_ignore(self):
        a = self.w.a
        res = self.bulk(a, [{'etudiant': '²', 'note_devoir': 10}, {'etudiant': True, 'note_devoir': 10},
                            {'etudiant': None, 'note_devoir': 10}])
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['ignores'], 3)
