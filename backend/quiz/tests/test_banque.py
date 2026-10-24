from django.test import TestCase

from accounts.testing import build_world, client_for, make_user
from audit.models import AuditLog
from quiz.models import QuestionBanque, TagQuestion
from referentiel.models import EC, EnseignantMatiere

B = '/api/quiz/banque'


def contenu(**extra):
    base = {
        'texte': 'Capitale de la France ?', 'type_question': 'qcm', 'points': '2', 'mode_notation': 'tout_ou_rien',
        'penalite': '0.5', 'explication': 'Paris est la capitale.',
        'choix': [{'texte': 'Paris', 'est_correct': True, 'points': '0'},
                  {'texte': 'Lyon', 'est_correct': False, 'points': '0'}],
    }
    base.update(extra)
    return base


VF = {'texte': 'Vrai ou faux : 2 > 1', 'type_question': 'vf', 'points': '1', 'penalite': '0',
      'choix': [{'texte': 'Vrai', 'est_correct': True, 'points': '0'}, {'texte': 'Faux', 'est_correct': False, 'points': '0'}]}


class BanqueTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()
        a = cls.w.a
        cls.collegue = make_user('collegue', 'enseignant', a.etab)
        EnseignantMatiere.objects.create(enseignant=cls.collegue, ec=a.ec, classe=a.classe)
        cls.autre_ec = EC.objects.create(code='ECZ', libelle='Réseaux', ue=a.ue)
        cls.autre_matiere = make_user('autrematiere', 'enseignant', a.etab)
        EnseignantMatiere.objects.create(enseignant=cls.autre_matiere, ec=cls.autre_ec, classe=a.classe)

    def setUp(self):
        self.a = self.w.a
        self.ens = client_for(self.a.ens)

    def creer(self, client=None, **corps):
        donnees = {'ec': self.a.ec.id, 'difficulte': 'facile', 'chapitres': ['Geographie'],
                   'competences': ['Culture generale'], 'contenu': contenu()}
        donnees.update(corps)
        return (client or self.ens).post(f'{B}/', donnees, format='json')

    def ids(self, requete, client=None):
        res = (client or self.ens).get(f'{B}/?{requete}')
        self.assertEqual(res.status_code, 200)
        return {f['id'] for f in res.data['results']}

    def test_creation(self):
        res = self.creer()
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data['version']['numero'], 1)
        self.assertEqual(res.data['nb_versions'], 1)
        self.assertEqual(res.data['auteur'], self.a.ens.id)
        self.assertTrue(res.data['modifiable'])
        self.assertFalse(res.data['partagee'])
        self.assertEqual(sorted(t['libelle'] for t in res.data['tags']), ['Culture generale', 'Geographie'])
        fiche = QuestionBanque.objects.get(pk=res.data['id'])
        self.assertEqual(fiche.etablissement, self.a.etab)
        self.assertEqual(fiche.versions.get().choix[0], {'texte': 'Paris', 'est_correct': True, 'points': '0.00'})
        self.assertEqual(res.data['version']['penalite'], '0.50')
        self.assertTrue(AuditLog.objects.filter(action='creation_question_banque', cible_id=str(fiche.pk)).exists())

    def test_contenu_obligatoire_et_coherent(self):
        self.assertEqual(self.ens.post(f'{B}/', {'difficulte': 'facile'}, format='json').status_code, 400)
        seul = contenu(choix=[{'texte': 'Seul', 'est_correct': True, 'points': '0'}])
        self.assertEqual(self.creer(contenu=seul).status_code, 400)
        self.assertEqual(self.creer(contenu=contenu(penalite='3')).status_code, 400)
        courte = contenu(type_question='courte', choix=[{'texte': 'Paris', 'est_correct': True, 'points': '0'}])
        self.assertEqual(self.creer(contenu=courte).status_code, 400)
        trop = contenu(penalite='0', choix=[{'texte': str(i), 'est_correct': i == 0, 'points': '0'} for i in range(11)])
        self.assertEqual(self.creer(contenu=trop).status_code, 400)
        for corps in ([1], 'abc'):
            self.assertEqual(self.ens.post(f'{B}/', corps, format='json').status_code, 400)
        self.assertEqual(self.creer(contenu='pas un objet').status_code, 400)

    def test_versioning(self):
        fiche_id = self.creer().data['id']
        url = f'{B}/{fiche_id}/'
        res = self.ens.patch(url, {'difficulte': 'difficile', 'chapitres': ['Europe']}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data['nb_versions'], 1)
        self.assertEqual([t['libelle'] for t in res.data['tags'] if t['type'] == 'chapitre'], ['Europe'])
        self.assertEqual([t['libelle'] for t in res.data['tags'] if t['type'] == 'competence'], ['Culture generale'])
        self.assertEqual(self.ens.patch(url, {'contenu': contenu()}, format='json').data['nb_versions'], 1)
        res = self.ens.patch(url, {'contenu': contenu(texte="Capitale de l'Italie ?")}, format='json')
        self.assertEqual(res.data['nb_versions'], 2)
        self.assertEqual(res.data['version']['numero'], 2)
        self.assertTrue(AuditLog.objects.filter(action='version_question_banque', details={'numero': 2}).exists())
        self.assertEqual([v['numero'] for v in self.ens.get(f'{url}versions/').data], [2, 1])
        res = self.ens.post(f'{url}restaurer/', {'numero': 1}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['version']['numero'], 3)
        self.assertEqual(res.data['version']['texte'], 'Capitale de la France ?')
        for corps in ({'numero': 99}, {'numero': 'x'}, {}, [1]):
            self.assertEqual(self.ens.post(f'{url}restaurer/', corps, format='json').status_code, 400)

    def test_droits_de_partage(self):
        fiche_id = self.creer().data['id']
        url = f'{B}/{fiche_id}/'
        collegue = client_for(self.collegue)
        self.assertEqual(collegue.get(url).status_code, 404)
        self.ens.patch(url, {'partagee': True}, format='json')
        res = collegue.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.data['modifiable'])
        self.assertEqual(collegue.patch(url, {'difficulte': 'moyen'}, format='json').status_code, 403)
        self.assertEqual(collegue.delete(url).status_code, 403)
        self.assertEqual(collegue.post(f'{url}restaurer/', {'numero': 1}, format='json').status_code, 403)
        self.assertEqual(client_for(self.autre_matiere).get(url).status_code, 404)
        self.assertEqual(client_for(self.w.b.ens).get(url).status_code, 404)
        self.assertEqual(client_for(self.a.admin).patch(url, {'difficulte': 'moyen'}, format='json').status_code, 200)
        self.assertEqual(client_for(self.a.resp).get(url).status_code, 200)
        self.assertEqual(client_for(self.w.b.admin).get(url).status_code, 404)
        self.assertEqual(client_for(self.w.superadmin).get(url).status_code, 200)
        self.assertEqual(client_for(self.a.etu).get(f'{B}/').status_code, 403)

    def test_matiere_hors_perimetre(self):
        self.assertEqual(self.creer(ec=self.autre_ec.id).status_code, 400)
        self.assertEqual(self.creer(ec=self.w.b.ec.id).status_code, 400)
        self.assertEqual(self.creer(ec=None).status_code, 201)

    def test_archivage(self):
        fiche_id = self.creer().data['id']
        self.assertEqual(self.ens.delete(f'{B}/{fiche_id}/').status_code, 204)
        self.assertTrue(QuestionBanque.objects.get(pk=fiche_id).archivee)
        self.assertNotIn(fiche_id, self.ids(''))
        self.assertIn(fiche_id, self.ids('archivee=1'))
        self.assertTrue(AuditLog.objects.filter(action='archivage_question_banque').exists())
        self.assertEqual(self.ens.patch(f'{B}/{fiche_id}/', {'archivee': False}, format='json').status_code, 200)
        self.assertIn(fiche_id, self.ids(''))

    def test_tags_sans_doublon_de_casse(self):
        self.creer(chapitres=['Boucles'])
        self.creer(chapitres=['  boucles ', 'BOUCLES', ''])
        self.assertEqual(TagQuestion.objects.filter(type='chapitre', libelle__iexact='boucles').count(), 1)
        res = self.ens.get(f'{B}/tags/?type=chapitre&q=bou')
        self.assertEqual([t['libelle'] for t in res.data], ['Boucles'])
        self.assertEqual(len(self.ens.get(f'{B}/tags/?type=competence').data), 1)
        self.assertEqual(client_for(self.w.b.ens).get(f'{B}/tags/?type=chapitre').data, [])

    def test_filtres(self):
        p1 = self.creer(chapitres=['Boucles']).data['id']
        p2 = self.creer(difficulte='difficile', chapitres=['Tableaux'], contenu=VF).data['id']
        self.assertEqual(self.ids('difficulte=facile'), {p1})
        self.assertEqual(self.ids('type_question=vf'), {p2})
        self.assertEqual(self.ids('recherche=capitale'), {p1})
        boucles = TagQuestion.objects.get(libelle='Boucles').id
        culture = TagQuestion.objects.get(libelle='Culture generale').id
        self.assertEqual(self.ids(f'tag={boucles}&tag={culture}'), {p1})
        self.assertEqual(self.ids(f'tag={culture}'), {p1, p2})
        self.assertEqual(self.ids(f'ec={self.a.ec.id}'), {p1, p2})
        self.assertEqual(self.ids('mes_questions=1'), {p1, p2})
        self.assertEqual(self.ids('mes_questions=1', client_for(self.collegue)), set())
        self.ens.patch(f'{B}/{p1}/', {'contenu': contenu(texte='Nouvelle formulation')}, format='json')
        self.assertEqual(self.ids('recherche=capitale'), set())
        self.assertEqual(self.ids('tag=x&ec=y&tag=99999999999999999999999'), {p1, p2})
