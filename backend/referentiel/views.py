from django.db import models, transaction, IntegrityError
import uuid
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from django.contrib.auth import get_user_model

from accounts.permissions import (
    IsSuperAdmin, IsGestionnaire, RolePermission,
    GESTION, CREATEURS, TOUS_LES_ROLES, SUPERADMIN, ADMIN, ENSEIGNANT, ETUDIANT,
)
from accounts.scoping import (
    EtablissementScopedMixin, en_entier, classes_enseignant, classes_etudiant,
    q_filiere_niveau_etudiant, verifier_compte_du_perimetre, verifier_references_evaluation, MESSAGE_HORS_PERIMETRE,
)
from audit.services import log as audit_log
from . import archives
from .archives import ArchiveMixin
from .models import (
    Etablissement, AnneeAcademique, Filiere, Niveau, UE, EC, Cours,
    Classe, Groupe, Inscription, EnseignantMatiere, AffectationEnseignant, Semestre, PeriodeEvaluation
)
from .serializers import (
    EtablissementSerializer, CreateEtablissementSerializer, InviteAdminSerializer,
    AnneeAcademiqueSerializer, CreateAnneeWithFiliereSerializer, FiliereSerializer, NiveauSerializer,
    UESerializer, ECSerializer, CoursSerializer,
    ClasseSerializer, GroupeSerializer, InscriptionSerializer,
    EnseignantMatiereSerializer, SemestreSerializer, PeriodeEvaluationSerializer
)

User = get_user_model()

LECTURE_TOUS_ECRITURE_GESTION = RolePermission(read=TOUS_LES_ROLES, write=GESTION)


class EtablissementViewSet(viewsets.ModelViewSet):
    queryset = Etablissement.objects.order_by('id')
    serializer_class = EtablissementSerializer
    permission_classes = [RolePermission(read=GESTION, write=(SUPERADMIN,))]

    def get_queryset(self):
        user = self.request.user
        if user.role == SUPERADMIN:
            return Etablissement.objects.order_by('id')
        return Etablissement.objects.filter(pk=user.etablissement_id).order_by('id')

    def get_serializer_class(self):
        if self.action == 'create':
            return CreateEtablissementSerializer
        return EtablissementSerializer

    @action(detail=True, methods=['patch'], permission_classes=[RolePermission(read=GESTION, write=(SUPERADMIN, ADMIN))])
    def parametres(self, request, pk=None):
        etablissement = self.get_object()
        data = request.data if isinstance(request.data, dict) else {}
        valeurs = {}
        if 'validation_quiz_requise' in data:
            if not isinstance(data['validation_quiz_requise'], bool):
                raise ValidationError({'validation_quiz_requise': ["La valeur doit être vrai ou faux."]})
            valeurs['validation_quiz_requise'] = data['validation_quiz_requise']
        if 'delai_retard_minutes' in data:
            delai = data['delai_retard_minutes']
            if isinstance(delai, bool) or not isinstance(delai, int) or not 0 <= delai <= 240:
                raise ValidationError({'delai_retard_minutes': ["Le délai doit être un nombre entier de minutes entre 0 et 240."]})
            valeurs['delai_retard_minutes'] = delai
        if not valeurs:
            raise ValidationError({'detail': "Aucun réglage à modifier."})
        for champ, valeur in valeurs.items():
            setattr(etablissement, champ, valeur)
        etablissement.save(update_fields=list(valeurs))
        audit_log(request, 'parametres_etablissement', cible=etablissement, etablissement=etablissement, details=valeurs)
        return Response(EtablissementSerializer(etablissement, context=self.get_serializer_context()).data)

    def create(self, request, *args, **kwargs):
        serializer = CreateEtablissementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        etablissement = Etablissement.objects.create(
            code=data['code'],
            nom=data['nom'],
            sigle=data.get('sigle', ''),
            adresse=data.get('adresse', ''),
            telephone=data.get('telephone', ''),
            email=data.get('email', ''),
            site_web=data.get('site_web', ''),
        )

        admin_email = data['admin_email']
        if User.objects.filter(email=admin_email).exists():
            etablissement.delete()
            return Response({"error": f"L'email {admin_email} est déjà utilisé"}, status=status.HTTP_400_BAD_REQUEST)

        token = uuid.uuid4()
        username = admin_email.split('@')[0]
        base_username = username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1

        admin_user = User.objects.create(
            username=username,
            email=admin_email,
            first_name=data['admin_first_name'],
            last_name=data['admin_last_name'],
            role='admin',
            etablissement=etablissement,
            must_change_password=True,
            invitation_token=token,
            invited_by=request.user,
            date_invitation=timezone.now(),
            is_invited=True,
            is_active=True,
        )
        audit_log(request, 'invitation', cible=admin_user, details={'role': 'admin'})

        activation_url = f"{settings.FRONTEND_URL}/activate/{token}"
        subject = f"PEL - Invitation à administrer {etablissement.nom}"
        message = f"""Bonjour {data['admin_first_name']} {data['admin_last_name']},

Vous avez été nommé(e) administrateur de l'établissement "{etablissement.nom}" sur la plateforme PEL.

Pour activer votre compte et créer votre mot de passe, cliquez sur le lien ci-dessous :
{activation_url}

Ce lien est valable pendant 7 jours.

Cordialement,
L'équipe PEL"""

        try:
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [admin_email], fail_silently=True)
        except Exception:
            pass

        return Response({
            "message": f"Établissement créé. Invitation envoyée à {admin_email}",
            "etablissement": EtablissementSerializer(etablissement).data,
            "activation_url": activation_url,
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], permission_classes=[IsSuperAdmin])
    def invite_admin(self, request, pk=None):
        etablissement = self.get_object()

        existing_admin = User.objects.filter(etablissement=etablissement, role='admin').first()
        if existing_admin:
            return Response({"error": f"Cet établissement a déjà un admin : {existing_admin.email}"}, status=status.HTTP_400_BAD_REQUEST)

        serializer = InviteAdminSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if User.objects.filter(email=data['admin_email']).exists():
            return Response({"error": "Cet email est déjà utilisé"}, status=status.HTTP_400_BAD_REQUEST)

        token = uuid.uuid4()
        username = data['admin_email'].split('@')[0]
        base_username = username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1

        admin_user = User.objects.create(
            username=username,
            email=data['admin_email'],
            first_name=data['admin_first_name'],
            last_name=data['admin_last_name'],
            role='admin',
            etablissement=etablissement,
            must_change_password=True,
            invitation_token=token,
            invited_by=request.user,
            date_invitation=timezone.now(),
            is_invited=True,
            is_active=True,
        )
        audit_log(request, 'invitation', cible=admin_user, details={'role': 'admin'})

        activation_url = f"{settings.FRONTEND_URL}/activate/{token}"
        subject = f"PEL - Invitation à administrer {etablissement.nom}"
        message = f"""Bonjour {data['admin_first_name']} {data['admin_last_name']},

Vous avez été nommé(e) administrateur de l'établissement "{etablissement.nom}" sur la plateforme PEL.

Pour activer votre compte et créer votre mot de passe, cliquez sur le lien ci-dessous :
{activation_url}

Ce lien est valable pendant 7 jours.

Cordialement,
L'équipe PEL"""

        try:
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [data['admin_email']], fail_silently=True)
        except Exception:
            pass

        return Response({
            "message": f"Invitation envoyée à {data['admin_email']}",
            "activation_url": activation_url,
        })


class AnneeAcademiqueViewSet(ArchiveMixin, EtablissementScopedMixin, viewsets.ModelViewSet):
    queryset = AnneeAcademique.objects.all()
    serializer_class = AnneeAcademiqueSerializer
    permission_classes = [LECTURE_TOUS_ECRITURE_GESTION]
    annee_path = ''
    actions_masquees = ()
    scope_path = 'etablissement'
    scope_etablissement_field = 'etablissement'

    def enseignant_scope(self, qs, user):
        return qs.filter(etablissement_id=user.etablissement_id)

    etudiant_scope = enseignant_scope

    @action(detail=True, methods=['post'], permission_classes=[RolePermission(write=(SUPERADMIN, ADMIN))])
    def archiver(self, request, pk=None):
        annee = self.get_object()
        archives.archiver(annee, request)
        return Response(self.get_serializer(annee).data)

    @action(detail=True, methods=['post'], permission_classes=[RolePermission(write=(SUPERADMIN, ADMIN))])
    def desarchiver(self, request, pk=None):
        annee = self.get_object()
        archives.desarchiver(annee, request)
        return Response(self.get_serializer(annee).data)

    @staticmethod
    def _creer_annee_et_filieres(data, etablissement):
        annee = AnneeAcademique.objects.create(
            libelle=data['annee_libelle'],
            date_debut=data['annee_date_debut'],
            date_fin=data['annee_date_fin'],
            est_active=data.get('annee_est_active', False),
            etablissement=etablissement,
        )

        filieres_crees = []
        for f_data in data.get('filieres', []):
            filiere_etab = etablissement

            niveau_code = f_data.get('niveau', '')
            niveau = Niveau.objects.filter(code=niveau_code).first()
            if not niveau and niveau_code:
                niveau = Niveau.objects.create(code=niveau_code, libelle=niveau_code)

            filiere = Filiere.objects.create(
                code=f_data['code'],
                libelle=f_data['libelle'],
                etablissement=filiere_etab,
                description=f_data.get('description', ''),
            )
            filieres_crees.append(filiere)

            for ue_data in f_data.get('ues', []):
                niveau_code = ue_data.get('niveau', '')
                niveau = Niveau.objects.filter(code=niveau_code).first()
                if not niveau and niveau_code:
                    niveau = Niveau.objects.create(code=niveau_code, libelle=niveau_code)

                UE.objects.create(
                    code=ue_data['code'],
                    libelle=ue_data['libelle'],
                    filiere=filiere,
                    niveau=niveau,
                    credits=ue_data.get('credits', 0),
                    coefficient=ue_data.get('coefficient', 1),
                )
        return annee, filieres_crees

    @action(detail=False, methods=['post'], permission_classes=[IsGestionnaire])
    def create_with_filieres(self, request):
        serializer = CreateAnneeWithFiliereSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if request.user.role == SUPERADMIN:
            etablissement = Etablissement.objects.filter(pk=data.get('annee_etablissement')).first()
            if etablissement is None:
                return Response({"error": "Précisez un établissement existant pour cette année académique."},
                                status=status.HTTP_400_BAD_REQUEST)
        else:
            etablissement = request.user.etablissement

        try:
            with transaction.atomic():
                annee, filieres_crees = self._creer_annee_et_filieres(data, etablissement)
        except IntegrityError:
            return Response({"error": "Un code ou un libellé est déjà utilisé : aucune donnée n'a été créée."},
                            status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "message": f"Année académique {annee.libelle} créée avec {len(filieres_crees)} filière(s)",
            "annee": AnneeAcademiqueSerializer(annee).data,
        }, status=status.HTTP_201_CREATED)


class FiliereViewSet(EtablissementScopedMixin, viewsets.ModelViewSet):
    queryset = Filiere.objects.select_related('etablissement').order_by('id')
    serializer_class = FiliereSerializer
    permission_classes = [LECTURE_TOUS_ECRITURE_GESTION]
    scope_path = 'etablissement'
    scope_etablissement_field = 'etablissement'

    def enseignant_scope(self, qs, user):
        return qs.filter(id__in=classes_enseignant(user).values_list('filiere_id', flat=True))

    def etudiant_scope(self, qs, user):
        return qs.filter(etablissement_id=user.etablissement_id)


class NiveauViewSet(viewsets.ModelViewSet):
    queryset = Niveau.objects.order_by('id')
    serializer_class = NiveauSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsSuperAdmin()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.role == 'enseignant':
            niveau_ids = Classe.objects.filter(
                affectations_enseignants__enseignant=user
            ).values_list('niveau_id', flat=True).distinct()
            qs = qs.filter(id__in=niveau_ids)
        return qs


class UEViewSet(EtablissementScopedMixin, viewsets.ModelViewSet):
    queryset = UE.objects.select_related('filiere', 'niveau').prefetch_related('ecs').order_by('id')
    serializer_class = UESerializer
    permission_classes = [LECTURE_TOUS_ECRITURE_GESTION]
    scope_path = 'filiere__etablissement'

    def get_queryset(self):
        qs = super().get_queryset()
        filiere = self.request.query_params.get('filiere')
        niveau = self.request.query_params.get('niveau')
        if filiere:
            qs = qs.filter(filiere_id=filiere)
        if niveau:
            qs = qs.filter(niveau_id=niveau)
        return qs

    def enseignant_scope(self, qs, user):
        ue_ids = EnseignantMatiere.objects.filter(enseignant=user).values_list('ec__ue_id', flat=True)
        return qs.filter(id__in=ue_ids)

    def etudiant_scope(self, qs, user):
        return qs.filter(q_filiere_niveau_etudiant(user))


class ECViewSet(EtablissementScopedMixin, viewsets.ModelViewSet):
    queryset = EC.objects.select_related('ue').order_by('id')
    serializer_class = ECSerializer
    permission_classes = [LECTURE_TOUS_ECRITURE_GESTION]
    scope_path = 'ue__filiere__etablissement'

    def get_queryset(self):
        qs = super().get_queryset()
        ue = self.request.query_params.get('ue')
        if ue:
            qs = qs.filter(ue_id=ue)
        return qs

    def enseignant_scope(self, qs, user):
        em_qs = EnseignantMatiere.objects.filter(enseignant=user)
        classe = self.request.query_params.get('classe')
        if classe:
            em_qs = em_qs.filter(classe_id=classe)
        return qs.filter(id__in=em_qs.values_list('ec_id', flat=True))

    def etudiant_scope(self, qs, user):
        return qs.filter(q_filiere_niveau_etudiant(user, prefix='ue__'))


class CoursViewSet(EtablissementScopedMixin, viewsets.ModelViewSet):
    queryset = Cours.objects.select_related('ec', 'ec__ue', 'ec__ue__filiere').order_by('id')
    serializer_class = CoursSerializer
    permission_classes = [LECTURE_TOUS_ECRITURE_GESTION]
    scope_path = 'ec__ue__filiere__etablissement'

    def enseignant_scope(self, qs, user):
        classe_ids = AffectationEnseignant.objects.filter(enseignant=user).values_list('classe_id', flat=True)
        ec_ids = EnseignantMatiere.objects.filter(enseignant=user).values_list('ec_id', flat=True)
        return qs.filter(
            models.Q(ec_id__in=ec_ids) | models.Q(ec__enseignants__classe_id__in=classe_ids)
        ).distinct()

    def etudiant_scope(self, qs, user):
        return qs.filter(q_filiere_niveau_etudiant(user, prefix='ec__ue__'))


class ClasseViewSet(EtablissementScopedMixin, viewsets.ModelViewSet):
    queryset = Classe.objects.select_related('filiere', 'niveau', 'annee_academique').prefetch_related('groupes__membres').order_by('id')
    serializer_class = ClasseSerializer
    permission_classes = [LECTURE_TOUS_ECRITURE_GESTION]
    scope_path = 'filiere__etablissement'

    def get_queryset(self):
        qs = super().get_queryset()
        annee = self.request.query_params.get('annee_academique')
        filiere = self.request.query_params.get('filiere')
        if annee:
            qs = qs.filter(annee_academique_id=annee)
        if filiere:
            qs = qs.filter(filiere_id=filiere)
        return qs

    def enseignant_scope(self, qs, user):
        return qs.filter(pk__in=classes_enseignant(user))

    def etudiant_scope(self, qs, user):
        return qs.filter(pk__in=classes_etudiant(user))

    def perform_create(self, serializer, **kwargs):
        verifier_references_evaluation(self.request.user, serializer.validated_data)
        return super().perform_create(serializer, **kwargs)

    def perform_update(self, serializer, **kwargs):
        verifier_references_evaluation(self.request.user, serializer.validated_data)
        return super().perform_update(serializer, **kwargs)


class GroupeViewSet(EtablissementScopedMixin, viewsets.ModelViewSet):
    queryset = Groupe.objects.select_related('classe', 'classe__filiere').prefetch_related('membres').order_by('id')
    serializer_class = GroupeSerializer
    permission_classes = [LECTURE_TOUS_ECRITURE_GESTION]
    scope_path = 'classe__filiere__etablissement'

    def enseignant_scope(self, qs, user):
        return qs.filter(classe__in=classes_enseignant(user))

    def etudiant_scope(self, qs, user):
        return qs.filter(classe__in=classes_etudiant(user))

    @action(detail=True, methods=['post'], url_path='membres')
    def ajouter_membres(self, request, pk=None):
        groupe = self.get_object()
        ids = request.data.get('etudiants') if isinstance(request.data, dict) else None
        if not isinstance(ids, list) or not ids:
            raise ValidationError({'etudiants': ["Indiquez au moins un étudiant."]})
        entiers = [en_entier(i) for i in ids]
        if None in entiers or any(not 1 <= i <= 2**63 - 1 for i in entiers):
            raise ValidationError({'etudiants': ["Les identifiants d'étudiants doivent être des entiers."]})
        inscrits = set(
            User.objects.filter(pk__in=entiers, role=ETUDIANT, inscriptions__classe=groupe.classe)
            .values_list('pk', flat=True)
        )
        refuses = sorted(set(entiers) - inscrits)
        if refuses:
            raise ValidationError({'etudiants': [
                f"Ces comptes ne sont pas des étudiants inscrits dans la classe {groupe.classe.code} : "
                + ', '.join(str(i) for i in refuses) + '.'
            ]})
        groupe.membres.add(*inscrits)
        audit_log(request, 'membre_groupe', cible=groupe, etablissement=groupe.classe.filiere.etablissement,
                  details={'groupe': groupe.id, 'etudiants': sorted(inscrits)})
        return Response(self.get_serializer(groupe).data)

    @action(detail=True, methods=['delete'], url_path=r'membres/(?P<etudiant_id>[0-9]+)')
    def retirer_membre(self, request, pk=None, etudiant_id=None):
        groupe = self.get_object()
        etudiant_id = int(etudiant_id)
        if not groupe.membres.filter(pk=etudiant_id).exists():
            raise NotFound("Cet étudiant n'est pas membre du groupe.")
        groupe.membres.remove(etudiant_id)
        audit_log(request, 'retrait_membre_groupe', cible=groupe, etablissement=groupe.classe.filiere.etablissement,
                  details={'groupe': groupe.id, 'etudiant': etudiant_id})
        return Response(status=status.HTTP_204_NO_CONTENT)


class InscriptionViewSet(EtablissementScopedMixin, viewsets.ModelViewSet):
    queryset = Inscription.objects.select_related('etudiant', 'classe').order_by('id')
    serializer_class = InscriptionSerializer
    permission_classes = [LECTURE_TOUS_ECRITURE_GESTION]
    scope_path = 'classe__filiere__etablissement'

    def enseignant_scope(self, qs, user):
        return qs.filter(classe__in=classes_enseignant(user))

    def etudiant_scope(self, qs, user):
        return qs.filter(etudiant=user)

    def _verifier(self, serializer):
        etudiant = serializer.validated_data.get('etudiant')
        if etudiant is not None:
            verifier_compte_du_perimetre(self.request.user, etudiant, ETUDIANT)

    def perform_create(self, serializer, **kwargs):
        self._verifier(serializer)
        instance = super().perform_create(serializer, **kwargs)
        audit_log(self.request, 'inscription', cible=instance, etablissement=instance.classe.filiere.etablissement,
                  details={'etudiant': instance.etudiant_id, 'classe': instance.classe_id})
        return instance

    def perform_update(self, serializer, **kwargs):
        self._verifier(serializer)
        return super().perform_update(serializer, **kwargs)

    def perform_destroy(self, instance):
        audit_log(self.request, 'retrait_affectation', cible=instance, etablissement=instance.classe.filiere.etablissement,
                  details={'type': 'inscription', 'etudiant': instance.etudiant_id, 'classe': instance.classe_id})
        instance.delete()


class EnseignantMatiereViewSet(EtablissementScopedMixin, viewsets.ModelViewSet):
    queryset = EnseignantMatiere.objects.select_related('enseignant', 'ec', 'classe').order_by('id')
    serializer_class = EnseignantMatiereSerializer
    permission_classes = [RolePermission(read=CREATEURS, write=GESTION)]
    scope_path = 'classe__filiere__etablissement'

    def enseignant_scope(self, qs, user):
        return qs.filter(enseignant=user)

    def _verifier(self, serializer):
        data = serializer.validated_data
        instance = serializer.instance
        enseignant = data.get('enseignant', getattr(instance, 'enseignant', None))
        ec = data.get('ec', getattr(instance, 'ec', None))
        classe = data.get('classe', getattr(instance, 'classe', None))
        verifier_compte_du_perimetre(self.request.user, enseignant, ENSEIGNANT)
        if ec.ue.filiere.etablissement_id != classe.filiere.etablissement_id:
            raise ValidationError({'detail': MESSAGE_HORS_PERIMETRE})

    def perform_create(self, serializer, **kwargs):
        self._verifier(serializer)
        instance = super().perform_create(serializer, **kwargs)
        audit_log(self.request, 'affectation', cible=instance.enseignant, etablissement=instance.classe.filiere.etablissement,
                  details={'ec': instance.ec_id, 'classe': instance.classe_id})
        return instance

    def perform_update(self, serializer, **kwargs):
        self._verifier(serializer)
        return super().perform_update(serializer, **kwargs)

    def perform_destroy(self, instance):
        audit_log(self.request, 'retrait_affectation', cible=instance.enseignant, etablissement=instance.classe.filiere.etablissement,
                  details={'type': 'enseignant_matiere', 'ec': instance.ec_id, 'classe': instance.classe_id})
        instance.delete()


def _identifiant(params, cle):
    valeur = en_entier(params.get(cle))
    return valeur if valeur is not None and 1 <= valeur <= 2 ** 63 - 1 else None


class SemestreViewSet(EtablissementScopedMixin, viewsets.ModelViewSet):
    queryset = Semestre.objects.select_related('annee_academique').order_by('date_debut', 'id')
    serializer_class = SemestreSerializer
    permission_classes = [LECTURE_TOUS_ECRITURE_GESTION]
    scope_path = 'annee_academique__etablissement'

    def get_queryset(self):
        qs = super().get_queryset()
        annee = _identifiant(self.request.query_params, 'annee_academique')
        return qs.filter(annee_academique_id=annee) if annee else qs

    def enseignant_scope(self, qs, user):
        return qs.filter(annee_academique__etablissement_id=user.etablissement_id)

    etudiant_scope = enseignant_scope

    def perform_create(self, serializer, **kwargs):
        verifier_references_evaluation(self.request.user, serializer.validated_data)
        return super().perform_create(serializer, **kwargs)

    def perform_update(self, serializer, **kwargs):
        verifier_references_evaluation(self.request.user, serializer.validated_data)
        return super().perform_update(serializer, **kwargs)


class PeriodeEvaluationViewSet(EtablissementScopedMixin, viewsets.ModelViewSet):
    queryset = PeriodeEvaluation.objects.select_related('semestre', 'semestre__annee_academique').order_by('date_debut', 'id')
    serializer_class = PeriodeEvaluationSerializer
    permission_classes = [LECTURE_TOUS_ECRITURE_GESTION]
    scope_path = 'semestre__annee_academique__etablissement'

    def get_queryset(self):
        qs = super().get_queryset()
        semestre = _identifiant(self.request.query_params, 'semestre')
        annee = _identifiant(self.request.query_params, 'annee_academique')
        if semestre:
            qs = qs.filter(semestre_id=semestre)
        if annee:
            qs = qs.filter(semestre__annee_academique_id=annee)
        return qs

    def enseignant_scope(self, qs, user):
        return qs.filter(semestre__annee_academique__etablissement_id=user.etablissement_id)

    etudiant_scope = enseignant_scope

    def _verifier(self, serializer):
        semestre = serializer.validated_data.get('semestre')
        if semestre is not None:
            verifier_references_evaluation(self.request.user, {'annee_academique': semestre.annee_academique})

    def perform_create(self, serializer, **kwargs):
        self._verifier(serializer)
        return super().perform_create(serializer, **kwargs)

    def perform_update(self, serializer, **kwargs):
        self._verifier(serializer)
        return super().perform_update(serializer, **kwargs)
