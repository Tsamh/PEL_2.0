"""Brouillons d'exercices enregistrés sur le serveur (sous-projet 4c, tâche 3)."""
from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from accounts.testing import build_world, client_for, make_user
from programming.models import BrouillonExercice, Devoir, Exercice, SoumissionDevoir, VersionSoumission
from referentiel.models import AnneeAcademique, Inscription

P = '/api/programming'
DEJA_SOUMIS = "Vous avez déjà soumis ce devoir."
NOTE_VALIDEE = "Votre note est validée : ce devoir ne peut plus être modifié."
TROP = "Trop d'enregistrements : patientez une minute."
FERME = "Ce devoir est fermé."
PAS_OUVERT = "Ce devoir n'est pas ouvert."


def fic(contenu, nom='main.py'):
    return [{'nom': nom, 'contenu': contenu}]


class BrouillonsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world()

    def setUp(self):
        cache.clear()
        self.a = self.w.a
        self.ex = self.a.exercice
        self.etu = client_for(self.a.etu)
        self.url = f'{P}/devoirs/{self.a.devoir.id}/brouillons/'

    def ecrire(self, client=None, url=None, **corps):
        donnees = {'exercice': self.ex.id, 'fichiers': fic('print(1)')}
        donnees.update(corps)
        return (client or self.etu).put(url or self.url, donnees, format='json')

    def dates(self, debut, fin):
        Devoir.objects.filter(pk=self.a.devoir.pk).update(date_debut=debut, date_fin=fin)

    def soumission(self, statut=SoumissionDevoir.SOUMIS):
        return SoumissionDevoir.objects.create(devoir=self.a.devoir, etudiant=self.a.etu, statut=statut)

    def option(self, valeur=True):
        Devoir.objects.filter(pk=self.a.devoir.pk).update(resoumission_autorisee=valeur)

    # Lecture et écriture
    def test_lecture_vide_puis_ecriture_et_lecture(self):
        res = self.etu.get(self.url)
        self.assertEqual((res.status_code, res.data), (200, []))
        res = self.ecrire()
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(set(res.data), {'exercice', 'modifie_le'})
        self.assertEqual(res.data['exercice'], self.ex.id)
        res = self.etu.get(self.url)
        self.assertEqual(len(res.data), 1)
        self.assertEqual(set(res.data[0]), {'exercice', 'fichiers', 'modifie_le'})
        self.assertEqual(res.data[0]['fichiers'], fic('print(1)'))

    def test_ecrasement_dernier_gagnant(self):
        self.ecrire(fichiers=fic('print(1)'))
        self.ecrire(fichiers=fic('print(2)'))
        self.assertEqual(BrouillonExercice.objects.count(), 1)
        self.assertEqual(BrouillonExercice.objects.get().fichiers, fic('print(2)'))

    def test_brouillons_propres_a_l_etudiant(self):
        voisin = make_user('voisin', 'etudiant', self.a.etab)
        Inscription.objects.create(etudiant=voisin, classe=self.a.classe)
        self.ecrire()
        self.assertEqual(client_for(voisin).get(self.url).data, [])
        self.assertEqual(client_for(voisin).put(self.url, {'exercice': self.ex.id, 'fichiers': fic('v')},
                                                format='json').status_code, 200)
        self.assertEqual(BrouillonExercice.objects.count(), 2)

    def test_lecture_limitee_au_devoir(self):
        autre = Devoir.objects.create(titre='Autre', est_publie=True, filiere=self.a.filiere,
                                      annee_academique=self.a.annee, cree_par=self.a.ens)
        autre.classes.add(*self.a.devoir.classes.all())
        ex = Exercice.objects.create(devoir=autre, ordre=1, titre='X', points=1)
        BrouillonExercice.objects.create(etudiant=self.a.etu, exercice=ex, fichiers=fic('x'))
        self.assertEqual(self.etu.get(self.url).data, [])

    def test_devoir_non_affecte_404(self):
        non_publie = Devoir.objects.create(titre='Caché', est_publie=False, filiere=self.a.filiere,
                                           annee_academique=self.a.annee, cree_par=self.a.ens)
        url = f'{P}/devoirs/{non_publie.id}/brouillons/'
        self.assertEqual(self.etu.get(url).status_code, 404)
        self.assertEqual(self.ecrire(url=url).status_code, 404)

    def test_autre_role_403_sur_put(self):
        res = self.ecrire(client=client_for(self.a.ens))
        self.assertEqual(res.status_code, 403)
        self.assertEqual(BrouillonExercice.objects.count(), 0)

    # Refus d'état
    def test_annee_archivee_409(self):
        AnneeAcademique.objects.filter(pk=self.a.annee.pk).update(archivee=True)
        res = self.ecrire()
        self.assertEqual(res.status_code, 409)
        self.assertIn('est archivée', str(res.data['detail']))

    def test_fenetre_fermee_ou_pas_ouverte_409(self):
        maintenant = timezone.now()
        self.dates(maintenant - timedelta(days=2), maintenant - timedelta(days=1))
        res = self.ecrire()
        self.assertEqual((res.status_code, str(res.data['detail'])), (409, FERME))
        self.dates(maintenant + timedelta(days=1), maintenant + timedelta(days=2))
        res = self.ecrire()
        self.assertEqual((res.status_code, str(res.data['detail'])), (409, PAS_OUVERT))

    # Validations
    def test_exercice_d_un_autre_devoir_400(self):
        autre = Devoir.objects.create(titre='Autre', est_publie=True, filiere=self.a.filiere,
                                      annee_academique=self.a.annee, cree_par=self.a.ens)
        ex = Exercice.objects.create(devoir=autre, ordre=1, titre='X', points=1)
        for exercice in (ex.id, 999999, 'abc', None):
            res = self.ecrire(exercice=exercice)
            self.assertEqual(res.status_code, 400, exercice)
            self.assertIn('exercice', res.data)

    def test_fichiers_invalides_400(self):
        for fichiers in ('x', [{'nom': '../a.py', 'contenu': ''}], [{'nom': 'main.py', 'contenu': 3}], None):
            res = self.ecrire(fichiers=fichiers)
            self.assertEqual(res.status_code, 400, fichiers)
            self.assertIn('fichiers', res.data)

    def test_fichier_principal_absent_400(self):
        res = self.ecrire(fichiers=fic('print(1)', nom='autre.py'))
        self.assertEqual(res.status_code, 400)
        self.assertEqual(str(res.data['fichiers'][0]), 'Le fichier principal main.py est obligatoire.')

    def test_corps_non_objet_400(self):
        for corps in ([], 'texte', 3):
            res = self.etu.put(self.url, corps, format='json')
            self.assertEqual(res.status_code, 400, corps)

    # Soumission existante
    def test_deja_soumis_sans_option_409(self):
        self.soumission()
        res = self.ecrire()
        self.assertEqual((res.status_code, str(res.data['detail'])), (409, DEJA_SOUMIS))
        self.assertEqual(BrouillonExercice.objects.count(), 0)

    def test_option_active_autorise_l_ecriture(self):
        self.soumission()
        self.option()
        res = self.ecrire()
        self.assertEqual(res.status_code, 200, res.data)

    def test_option_active_pendant_une_correction(self):
        self.soumission(SoumissionDevoir.EN_CORRECTION)
        self.option()
        self.assertEqual(self.ecrire().status_code, 200)

    def test_note_validee_409(self):
        self.soumission(SoumissionDevoir.CORRIGE)
        self.option()
        res = self.ecrire()
        self.assertEqual((res.status_code, str(res.data['detail'])), (409, NOTE_VALIDEE))
        self.assertEqual(BrouillonExercice.objects.count(), 0)

    def test_note_validee_sans_option_garde_le_message_deja_soumis(self):
        self.soumission(SoumissionDevoir.CORRIGE)
        res = self.ecrire()
        self.assertEqual(str(res.data['detail']), DEJA_SOUMIS)

    # Limite
    def test_limite_61e_429(self):
        for i in range(60):
            self.assertEqual(self.ecrire(fichiers=fic(f'print({i})')).status_code, 200, i)
        res = self.ecrire()
        self.assertEqual(res.status_code, 429)
        self.assertEqual(str(res.data['detail']), TROP)

    def test_limite_independante_de_celle_des_executions(self):
        cache.set(f'pel:executions:{self.a.etu.pk}', 20, 60)
        self.assertEqual(self.ecrire().status_code, 200)

    # Concurrence
    def test_deux_premieres_ecritures_simultanees_sans_500(self):
        vrai = BrouillonExercice.objects.update_or_create
        appels = []

        def concurrent(*args, **kwargs):
            if not appels:
                appels.append(1)
                BrouillonExercice.objects.create(etudiant=self.a.etu, exercice=self.ex, fichiers=fic('autre'))
                raise IntegrityError()
            return vrai(*args, **kwargs)

        with mock.patch.object(BrouillonExercice.objects, 'update_or_create', side_effect=concurrent):
            res = self.ecrire(fichiers=fic('print(9)'))
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(BrouillonExercice.objects.count(), 1)
        self.assertEqual(BrouillonExercice.objects.get().fichiers, fic('print(9)'))

    # Modèles et vue du devoir
    def test_modeles(self):
        s = self.soumission()
        self.assertEqual((s.numero_version, s.soumission_auto), (1, False))
        self.assertFalse(self.a.devoir.resoumission_autorisee)
        v = VersionSoumission.objects.create(soumission=s, numero=1, date_soumission=timezone.now(), reponses=[])
        self.assertEqual(list(s.versions.all()), [v])
        with self.assertRaises(IntegrityError):
            VersionSoumission.objects.create(soumission=s, numero=1, date_soumission=timezone.now())

    def test_resoumission_autorisee_dans_la_vue_etudiant(self):
        res = self.etu.get(f'{P}/devoirs/{self.a.devoir.id}/')
        self.assertIs(res.data['resoumission_autorisee'], False)
        self.option()
        res = self.etu.get(f'{P}/devoirs/{self.a.devoir.id}/')
        self.assertIs(res.data['resoumission_autorisee'], True)

    def test_resoumission_autorisee_ne_depublie_pas_un_devoir_valide(self):
        self.a.etab.validation_quiz_requise = True
        self.a.etab.save()
        Devoir.objects.filter(pk=self.a.devoir.pk).update(statut_validation='validee', est_publie=True)
        ens = client_for(self.a.ens)
        res = ens.patch(f'{P}/devoirs/{self.a.devoir.id}/', {'resoumission_autorisee': True}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual((res.data['statut_validation'], res.data['est_publie']), ('validee', True))
        self.assertIs(res.data['resoumission_autorisee'], True)
