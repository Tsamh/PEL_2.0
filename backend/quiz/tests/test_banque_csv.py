from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from accounts.testing import build_world, client_for
from audit.models import AuditLog
from quiz.banque import contenu_version
from quiz.banque_csv import ENTETE
from quiz.models import QuestionBanque

B = '/api/quiz/banque'
ENTETE_TXT = ';'.join(ENTETE)


def ligne(**valeurs):
    return ';'.join(valeurs.get(c, '') for c in ENTETE)


VALIDE = ligne(type='qcm', texte='2 + 2 ?', points='1', difficulte='facile', chapitres='Calcul|Additions',
               choix1='4', correct1='oui', choix2='5', correct2='non')
INVALIDE = ligne(type='qcm', texte='Un seul choix', points='1', choix1='4', correct1='oui')


class BanqueCsvTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def setUp(self):
        self.a = self.w.a
        self.ens = client_for(self.a.ens)

    def fichier(self, texte, encodage='utf-8'):
        return SimpleUploadedFile('banque.csv', texte.encode(encodage), content_type='text/csv')

    def importer(self, texte, encodage='utf-8', **extra):
        return self.ens.post(f'{B}/import/', {'fichier': self.fichier(texte, encodage), **extra}, format='multipart')

    def test_modele_puis_aller_retour(self):
        res = self.ens.get(f'{B}/modele/')
        self.assertEqual(res.status_code, 200)
        texte = res.content.decode('utf-8')
        self.assertTrue(texte.startswith('\ufeff'))
        self.assertEqual(self.importer(texte).status_code, 201)
        fiche = QuestionBanque.objects.get()
        self.assertEqual(fiche.difficulte, 'facile')
        self.assertEqual(fiche.auteur, self.a.ens)
        export = self.ens.get(f'{B}/export/')
        self.assertEqual(export.status_code, 200)
        self.assertIn('banque_questions.csv', export['Content-Disposition'])
        res = self.importer(export.content.decode('utf-8'))
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data, {'crees': 1})
        premiere, seconde = QuestionBanque.objects.order_by('id')
        self.assertEqual(contenu_version(premiere.courante), contenu_version(seconde.courante))
        self.assertEqual({t.libelle for t in seconde.tags.all()}, {t.libelle for t in premiere.tags.all()})
        self.assertTrue(AuditLog.objects.filter(action='import_banque', details={'crees': 1}).exists())

    def test_formules_neutralisees(self):
        contenu = {'texte': '=SOMME(A1:A2)', 'type_question': 'qcm', 'points': '1', 'mode_notation': 'par_choix',
                   'penalite': '0', 'choix': [{'texte': '+1', 'est_correct': True, 'points': '1'},
                                              {'texte': '@moi', 'est_correct': False, 'points': '-0.5'}]}
        self.assertEqual(self.ens.post(f'{B}/', {'contenu': contenu}, format='json').status_code, 201)
        export = self.ens.get(f'{B}/export/').content.decode('utf-8')
        self.assertIn("'=SOMME(A1:A2)", export)
        self.assertIn("'-0.50", export)
        self.assertEqual(self.importer(export).status_code, 201)
        seconde = QuestionBanque.objects.order_by('id').last()
        self.assertEqual(seconde.courante.texte, '=SOMME(A1:A2)')
        self.assertEqual(seconde.courante.choix[1], {'texte': '@moi', 'est_correct': False, 'points': '-0.50'})

    def test_apercu_puis_tout_ou_rien(self):
        texte = '\n'.join([ENTETE_TXT, VALIDE, INVALIDE])
        res = self.importer(texte, apercu='1')
        self.assertEqual(res.status_code, 200)
        self.assertEqual((res.data['valides'], res.data['invalides']), (1, 1))
        self.assertEqual(res.data['lignes'][1]['ligne'], 3)
        self.assertFalse(res.data['lignes'][1]['ok'])
        self.assertTrue(res.data['lignes'][1]['erreurs'])
        self.assertFalse(QuestionBanque.objects.exists())
        self.assertEqual(self.importer(texte).status_code, 400)
        self.assertFalse(QuestionBanque.objects.exists())
        res = self.importer('\n'.join([ENTETE_TXT, VALIDE, VALIDE]))
        self.assertEqual(res.data, {'crees': 2})

    def test_valeurs_invalides_par_ligne(self):
        texte = '\n'.join([ENTETE_TXT, ligne(type='qcm', texte='Q', choix1='a', correct1='peut-etre', choix2='b', correct2='non'),
                           ligne(type='inconnu', texte='Q', choix1='a', correct1='oui', choix2='b', correct2='non'),
                           ligne(type='qcm', texte='Q', points='abc', choix1='a', correct1='oui', choix2='b', correct2='non')])
        res = self.importer(texte, apercu='1')
        self.assertEqual(res.data['invalides'], 3)
        self.assertIn('correct1', ' '.join(res.data['lignes'][0]['erreurs']))

    def test_fichiers_refuses(self):
        self.assertEqual(self.ens.post(f'{B}/import/', {}, format='multipart').status_code, 400)
        self.assertEqual(self.importer('\n'.join([ENTETE_TXT, VALIDE.replace('2 + 2', 'été')]), encodage='latin-1').status_code, 400)
        self.assertEqual(self.importer('mauvais;entete\n' + VALIDE).status_code, 400)
        self.assertEqual(self.importer(ENTETE_TXT).status_code, 400)
        self.assertEqual(self.importer('\n'.join([ENTETE_TXT] + [VALIDE] * 1001)).status_code, 400)
        gros = ENTETE_TXT + '\n' + ligne(type='qcm', texte='x' * (2 * 1024 * 1024), choix1='a', correct1='oui')
        self.assertEqual(self.importer(gros).status_code, 400)
        self.assertFalse(QuestionBanque.objects.exists())

    def test_matiere_en_parametre(self):
        res = self.importer('\n'.join([ENTETE_TXT, VALIDE]), ec=str(self.a.ec.id))
        self.assertEqual(res.status_code, 201)
        self.assertEqual(QuestionBanque.objects.get().ec, self.a.ec)
        self.assertEqual(self.importer('\n'.join([ENTETE_TXT, VALIDE]), ec=str(self.w.b.ec.id)).status_code, 400)
        self.assertEqual(self.importer('\n'.join([ENTETE_TXT, VALIDE]), ec='abc').status_code, 400)

    def test_export_par_identifiants_et_droits(self):
        premiere = self.importer('\n'.join([ENTETE_TXT, VALIDE, VALIDE]))
        self.assertEqual(premiere.status_code, 201)
        fiche = QuestionBanque.objects.order_by('id').first()
        export = self.ens.get(f'{B}/export/?ids={fiche.id},abc,99999999999999999999999').content.decode('utf-8')
        self.assertEqual(len([l for l in export.splitlines() if l.strip()]), 2)
        self.assertEqual(client_for(self.a.etu).get(f'{B}/export/').status_code, 403)
        autre = client_for(self.w.b.ens).get(f'{B}/export/').content.decode('utf-8')
        self.assertEqual(len([l for l in autre.splitlines() if l.strip()]), 1)
