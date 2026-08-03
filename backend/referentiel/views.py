from django.db import models
import uuid
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.contrib.auth import get_user_model

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


class IsSuperAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'superadmin'


class EtablissementViewSet(viewsets.ModelViewSet):
    queryset = Etablissement.objects.all()
    serializer_class = EtablissementSerializer
    permission_classes = [IsSuperAdmin]

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


class AnneeAcademiqueViewSet(viewsets.ModelViewSet):
    queryset = AnneeAcademique.objects.all()
    serializer_class = AnneeAcademiqueSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.role == 'admin' and user.etablissement:
            qs = qs.filter(etablissement=user.etablissement)
        elif user.role in ('enseignant', 'etudiant') and user.etablissement:
            qs = qs.filter(etablissement=user.etablissement)
        return qs

    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @action(detail=False, methods=['post'])
    def create_with_filieres(self, request):
        serializer = CreateAnneeWithFiliereSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        etablissement_id = data.get('annee_etablissement')
        if not etablissement_id and request.user.role == 'admin' and request.user.etablissement:
            etablissement_id = request.user.etablissement.id

        etablissement = None
        if etablissement_id:
            etablissement = Etablissement.objects.get(id=etablissement_id)

        annee = AnneeAcademique.objects.create(
            libelle=data['annee_libelle'],
            date_debut=data['annee_date_debut'],
            date_fin=data['annee_date_fin'],
            est_active=data.get('annee_est_active', False),
            etablissement=etablissement,
        )

        filieres_crees = []
        for f_data in data.get('filieres', []):
            filiere_etab = etablissement if request.user.role == 'admin' else None
            if request.user.role != 'superadmin' and request.user.etablissement:
                filiere_etab = request.user.etablissement

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


class FiliereViewSet(viewsets.ModelViewSet):
    queryset = Filiere.objects.select_related('etablissement').all()
    serializer_class = FiliereSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.role == 'admin' and user.etablissement:
            qs = qs.filter(etablissement=user.etablissement)
        elif user.role in ('enseignant', 'etudiant') and user.etablissement:
            qs = qs.filter(etablissement=user.etablissement)
        return qs

    def perform_create(self, serializer):
        user = self.request.user
        if user.role == 'admin' and user.etablissement:
            serializer.save(etablissement=user.etablissement)
        else:
            serializer.save()


class NiveauViewSet(viewsets.ModelViewSet):
    queryset = Niveau.objects.all()
    serializer_class = NiveauSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsSuperAdmin()]
        return [permissions.IsAuthenticated()]


class UEViewSet(viewsets.ModelViewSet):
    queryset = UE.objects.select_related('filiere', 'niveau').prefetch_related('ecs').all()
    serializer_class = UESerializer

    def get_queryset(self):
        qs = super().get_queryset()
        filiere = self.request.query_params.get('filiere')
        niveau = self.request.query_params.get('niveau')
        if filiere:
            qs = qs.filter(filiere_id=filiere)
        if niveau:
            qs = qs.filter(niveau_id=niveau)
        return qs


class ECViewSet(viewsets.ModelViewSet):
    queryset = EC.objects.select_related('ue').all()
    serializer_class = ECSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        ue = self.request.query_params.get('ue')
        if ue:
            qs = qs.filter(ue_id=ue)
        return qs


class CoursViewSet(viewsets.ModelViewSet):
    queryset = Cours.objects.select_related('ec', 'ec__ue', 'ec__ue__filiere').all()
    serializer_class = CoursSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.role == 'admin' and user.etablissement:
            qs = qs.filter(ec__ue__filiere__etablissement=user.etablissement)
        elif user.role == 'enseignant':
            classe_ids = AffectationEnseignant.objects.filter(enseignant=user).values_list('classe_id', flat=True)
            ec_ids = EnseignantMatiere.objects.filter(enseignant=user).values_list('ec_id', flat=True)
            qs = qs.filter(
                models.Q(ec_id__in=ec_ids) |
                models.Q(ec__enseignants__classe_id__in=classe_ids)
            ).distinct()
        return qs


class ClasseViewSet(viewsets.ModelViewSet):
    queryset = Classe.objects.select_related('filiere', 'niveau', 'annee_academique').prefetch_related('groupes').all()
    serializer_class = ClasseSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        annee = self.request.query_params.get('annee_academique')
        filiere = self.request.query_params.get('filiere')
        if annee:
            qs = qs.filter(annee_academique_id=annee)
        if filiere:
            qs = qs.filter(filiere_id=filiere)
        return qs


class GroupeViewSet(viewsets.ModelViewSet):
    queryset = Groupe.objects.select_related('classe').all()
    serializer_class = GroupeSerializer


class InscriptionViewSet(viewsets.ModelViewSet):
    queryset = Inscription.objects.select_related('etudiant', 'classe').all()
    serializer_class = InscriptionSerializer


class EnseignantMatiereViewSet(viewsets.ModelViewSet):
    queryset = EnseignantMatiere.objects.select_related('enseignant', 'ec', 'classe').all()
    serializer_class = EnseignantMatiereSerializer
