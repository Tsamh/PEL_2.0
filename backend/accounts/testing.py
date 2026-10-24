from datetime import date
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

User = get_user_model()

PASSWORD = 'Motdepasse!2026'


def make_user(username, role, etablissement=None, **extra):
    return User.objects.create_user(
        username=username,
        email=f'{username}@test.pel',
        password=PASSWORD,
        role=role,
        etablissement=etablissement,
        **extra,
    )


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _build_etablissement(suffix, niveau):
    from referentiel.models import (
        Etablissement, AnneeAcademique, Filiere, UE, EC, Classe,
        Inscription, AffectationEnseignant, EnseignantMatiere,
    )
    from quiz.models import Quiz, Question, Choix
    from programming.models import Devoir

    etab = Etablissement.objects.create(code=f'ET{suffix}', nom=f'Etablissement {suffix}')
    admin = make_user(f'admin{suffix}', 'admin', etab)
    resp = make_user(f'resp{suffix}', 'responsable_formation', etab)
    ens = make_user(f'ens{suffix}', 'enseignant', etab)
    etu = make_user(f'etu{suffix}', 'etudiant', etab)

    annee = AnneeAcademique.objects.create(
        libelle=f'2026-2027{suffix}', date_debut=date(2026, 10, 1),
        date_fin=date(2027, 7, 31), etablissement=etab,
    )
    filiere = Filiere.objects.create(code=f'INFO{suffix}', libelle=f'Informatique {suffix}', etablissement=etab)
    ue = UE.objects.create(code=f'UE{suffix}', libelle='Programmation', filiere=filiere, niveau=niveau)
    ec = EC.objects.create(code=f'EC{suffix}', libelle='Python', ue=ue)
    classe = Classe.objects.create(
        code=f'L1{suffix}', libelle=f'L1 Info {suffix}', filiere=filiere,
        niveau=niveau, annee_academique=annee,
    )
    Inscription.objects.create(etudiant=etu, classe=classe)
    AffectationEnseignant.objects.create(enseignant=ens, classe=classe)
    EnseignantMatiere.objects.create(enseignant=ens, ec=ec, classe=classe)

    quiz = Quiz.objects.create(
        titre=f'Quiz {suffix}', filiere=filiere, niveau=niveau,
        annee_academique=annee, est_publie=True, cree_par=ens,
    )
    quiz.classes.add(classe)
    question = Question.objects.create(quiz=quiz, texte='2 + 2 ?', type_question='qcm', points=1)
    Choix.objects.create(question=question, texte='4', est_correct=True, ordre=1)
    Choix.objects.create(question=question, texte='5', est_correct=False, ordre=2)

    devoir = Devoir.objects.create(
        titre=f'Devoir {suffix}', filiere=filiere, niveau=niveau, annee_academique=annee,
        ec=ec, est_publie=True, cree_par=ens, solution='print(4)',
        test_cases=[{'input': '', 'expected_output': '4'}],
    )
    return SimpleNamespace(
        etab=etab, admin=admin, resp=resp, ens=ens, etu=etu, annee=annee,
        filiere=filiere, ue=ue, ec=ec, classe=classe, quiz=quiz,
        question=question, devoir=devoir,
    )


def build_world():
    """Deux établissements complets (A et B) et un superadmin."""
    from referentiel.models import Niveau

    niveau = Niveau.objects.create(code='L1', libelle='Licence 1')
    superadmin = make_user('root', 'superadmin')
    return SimpleNamespace(
        superadmin=superadmin,
        niveau=niveau,
        a=_build_etablissement('A', niveau),
        b=_build_etablissement('B', niveau),
    )
