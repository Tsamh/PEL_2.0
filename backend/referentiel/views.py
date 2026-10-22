from django.db import models
import uuid
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from django.contrib.auth import get_user_model

from accounts.permissions import (
    IsSuperAdmin, IsGestionnaire, RolePermission,
    GESTION, CREATEURS, TOUS_LES_ROLES, SUPERADMIN, ENSEIGNANT, ETUDIANT,
)
from accounts.scoping import (
    EtablissementScopedMixin, classes_enseignant, classes_etudiant,
    q_filiere_niveau_etudiant, verifier_compte_du_perimetre, MESSAGE_HORS_PERIMETRE,
)
from audit.services import log as audit_log
from .models import (
    Etablissement, AnneeAcademique, Filiere, Niveau, UE, EC, Cours,
    Classe, Groupe, Inscription, EnseignantMatiere, AffectationEnseignant
)
from .serializers import (
    EtablissementSerializer, CreateEtablissementSerializer, InviteAdminSerializer,
    AnneeAcademiqueSerializer, CreateAnneeWithFiliereSerializer, FiliereSerializer, NiveauSerializer,
    UESerializer, ECSerializer, CoursSerializer,
    ClasseSerializer, GroupeSerializer, InscriptionSerializer,
    EnseignantMatiereSerializer
)

User = get_user_model()

LECTURE_TOUS_ECRITURE_GESTION = RolePermission(read=TOUS_LES_ROLES, write=GESTION)


class EtablissementViewSet(viewsets.ModelViewSet):
    queryset = Etablissement.objects.all()
    serializer_class = EtablissementSerializer
    permission_classes = [RolePermission(read=GESTION, write=(SUPERADMIN,))]

    def get_queryset(self):
        user = self.request.user
        if user.role == SUPERADMIN:
            return Etablissement.objects.all()
        return Etablissement.objects.filter(pk=user.etablissement_id)

    def get_serializer_class(self):
        if self.action == 'create':
            return CreateEtablissementSerializer
        return EtablissementSerializer

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


class AnneeAcademiqueViewSet(EtablissementScopedMixin, viewsets.ModelViewSet):
    queryset = AnneeAcademique.objects.all()
    serializer_class = AnneeAcademiqueSerializer
    permission_classes = [LECTURE_TOUS_ECRITURE_GESTION]
    scope_path = 'etablissement'
    scope_etablissement_field = 'etablissement'

    def enseignant_scope(self, qs, user):
        return qs.filter(etablissement_id=user.etablissement_id)

    etudiant_scope = enseignant_scope

    @action(detail=False, methods=['post'], permission_classes=[IsGestionnaire])
    def create_with_filieres(self, request):
        serializer = CreateAnneeWithFiliereSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if request.user.role == SUPERADMIN:
            etablissement = Etablissement.objects.filter(pk=data.get('annee_etablissement')).first()
        else:
            etablissement = request.user.etablissement

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

        return Response({
            "message": f"Année académique {annee.libelle} créée avec {len(filieres_crees)} filière(s)",
            "annee": AnneeAcademiqueSerializer(annee).data,
        }, status=status.HTTP_201_CREATED)


class FiliereViewSet(EtablissementScopedMixin, viewsets.ModelViewSet):
    queryset = Filiere.objects.select_related('etablissement').all()
    serializer_class = FiliereSerializer
    permission_classes = [LECTURE_TOUS_ECRITURE_GESTION]
    scope_path = 'etablissement'
    scope_etablissement_field = 'etablissement'

    def enseignant_scope(self, qs, user):
        return qs.filter(id__in=classes_enseignant(user).values_list('filiere_id', flat=True))

    def etudiant_scope(self, qs, user):
        return qs.filter(etablissement_id=user.etablissement_id)


class NiveauViewSet(viewsets.ModelViewSet):
    queryset = Niveau.objects.all()
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
    queryset = UE.objects.select_related('filiere', 'niveau').prefetch_related('ecs').all()
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
    queryset = EC.objects.select_related('ue').all()
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
    queryset = Cours.objects.select_related('ec', 'ec__ue', 'ec__ue__filiere').all()
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
    queryset = Classe.objects.select_related('filiere', 'niveau', 'annee_academique').prefetch_related('groupes').all()
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


class GroupeViewSet(EtablissementScopedMixin, viewsets.ModelViewSet):
    queryset = Groupe.objects.select_related('classe').all()
    serializer_class = GroupeSerializer
    permission_classes = [LECTURE_TOUS_ECRITURE_GESTION]
    scope_path = 'classe__filiere__etablissement'

    def enseignant_scope(self, qs, user):
        return qs.filter(classe__in=classes_enseignant(user))

    def etudiant_scope(self, qs, user):
        return qs.filter(classe__in=classes_etudiant(user))


class InscriptionViewSet(EtablissementScopedMixin, viewsets.ModelViewSet):
    queryset = Inscription.objects.select_related('etudiant', 'classe').all()
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
    queryset = EnseignantMatiere.objects.select_related('enseignant', 'ec', 'classe').all()
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
