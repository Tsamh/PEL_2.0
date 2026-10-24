from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from accounts.testing import build_world
from quiz.models import QuestionBanque, TagQuestion, VersionQuestion


class ModelesBanqueTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def test_version_courante_et_unicite(self):
        a = self.w.a
        fiche = QuestionBanque.objects.create(auteur=a.ens, etablissement=a.etab, ec=a.ec)
        self.assertIsNone(fiche.courante)
        VersionQuestion.objects.create(question=fiche, numero=1, texte='A', choix=[])
        VersionQuestion.objects.create(question=fiche, numero=2, texte='B', choix=[])
        fiche = QuestionBanque.objects.prefetch_related('versions').get(pk=fiche.pk)
        self.assertEqual(fiche.courante.numero, 2)
        self.assertEqual(fiche.difficulte, QuestionBanque.MOYEN)
        self.assertFalse(fiche.partagee)
        with self.assertRaises(IntegrityError), transaction.atomic():
            VersionQuestion.objects.create(question=fiche, numero=2, texte='C', choix=[])

    def test_tag_unique_sans_casse(self):
        TagQuestion.objects.create(etablissement=self.w.a.etab, type=TagQuestion.CHAPITRE, libelle='Boucles')
        TagQuestion.objects.create(etablissement=self.w.a.etab, type=TagQuestion.COMPETENCE, libelle='Boucles')
        TagQuestion.objects.create(etablissement=self.w.b.etab, type=TagQuestion.CHAPITRE, libelle='Boucles')
        with self.assertRaises(IntegrityError), transaction.atomic():
            TagQuestion.objects.create(etablissement=self.w.a.etab, type=TagQuestion.CHAPITRE, libelle='BOUCLES')

    def test_champs_de_question(self):
        q = self.w.a.question
        self.assertEqual(q.penalite, Decimal('0'))
        self.assertEqual(q.explication, '')
        self.assertIsNone(q.source)
        self.assertIsNone(q.version_source)
