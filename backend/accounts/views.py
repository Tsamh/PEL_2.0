import uuid
import csv
import io
from datetime import timedelta
from django.utils import timezone
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.db.models import Q
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.contrib.auth import get_user_model

from audit.services import log as audit_log
from referentiel.archives import verifier_non_archivee
from .permissions import (
    IsSuperAdmin, IsAdmin, IsGestionnaire, CanManageUser, MESSAGE_REFUS,
    peut_gerer_compte, SUPERADMIN, ADMIN, RESPONSABLE, ENSEIGNANT, ETUDIANT,
)
from .scoping import classes_enseignant, classes_du_perimetre
from .serializers import (
    UserSerializer, UserCreateSerializer, InviteStudentSerializer,
    InviteEnseignantSerializer, InviteResponsableSerializer,
    ImportStudentsSerializer, ActivateAccountSerializer,
    ForgotPasswordSerializer, ResetPasswordSerializer,
    ChangePasswordSerializer, RegisterAdminSerializer, ValidateAdminSerializer
)

User = get_user_model()


def _generer_username(email):
    base = email.split('@')[0]
    username = base
    compteur = 1
    while User.objects.filter(username=username).exists():
        username = f"{base}{compteur}"
        compteur += 1
    return username


def _reponse_garde_dernier_admin(cible):
    """400 si `cible` est le dernier administrateur actif de son établissement."""
    if cible.role != ADMIN or not cible.is_active:
        return None
    autres = User.objects.filter(role=ADMIN, etablissement_id=cible.etablissement_id, is_active=True).exclude(pk=cible.pk)
    if autres.exists():
        return None
    return Response(
        {"error": "Impossible : c'est le dernier administrateur actif de l'établissement."},
        status=status.HTTP_400_BAD_REQUEST,
    )


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.order_by('id')
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = User.objects.select_related('etablissement').order_by('id')
        if user.role == SUPERADMIN:
            pass
        elif user.role in (ADMIN, RESPONSABLE) and user.etablissement_id:
            if user.role == ADMIN:
                qs = qs.filter(etablissement_id=user.etablissement_id)
            else:
                qs = qs.filter(
                    Q(pk=user.pk)
                    | Q(etablissement_id=user.etablissement_id, role__in=(RESPONSABLE, ENSEIGNANT, ETUDIANT))
                )
        elif user.role == ENSEIGNANT:
            qs = qs.filter(
                Q(pk=user.pk) | Q(role=ETUDIANT, inscriptions__classe__in=classes_enseignant(user))
            ).distinct()
        else:
            qs = qs.filter(pk=user.pk)

        role = self.request.query_params.get('role')
        classe = self.request.query_params.get('classe')
        if role:
            qs = qs.filter(role=role)
        if classe:
            qs = qs.filter(inscriptions__classe_id=classe).distinct()
        return qs

    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        return UserSerializer

    def get_permissions(self):
        if self.action in ['register_admin', 'activate', 'forgot_password', 'reset_password']:
            return [permissions.AllowAny()]
        if self.action in ['create', 'destroy', 'pending_validations', 'validate_admin']:
            return [IsSuperAdmin()]
        if self.action in ['update', 'partial_update']:
            return [IsGestionnaire(), CanManageUser()]
        return super().get_permissions()

    def destroy(self, request, *args, **kwargs):
        cible = self.get_object()
        if cible.pk == request.user.pk:
            return Response({"error": "Vous ne pouvez pas supprimer votre propre compte."}, status=status.HTTP_400_BAD_REQUEST)
        garde = _reponse_garde_dernier_admin(cible)
        if garde:
            return garde
        if cible.soumissions_devoirs.exists() or cible.tentatives_quiz.exists() or cible.notes_matieres.exists():
            return Response(
                {"error": "Ce compte a un historique (soumissions, résultats ou notes). Désactivez-le plutôt que de le supprimer."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        audit_log(request, 'suppression_compte', cible=cible, details={'email': cible.email, 'role': cible.role})
        cible.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def me(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], permission_classes=[IsGestionnaire])
    def by_role(self, request):
        serializer = UserSerializer(self.get_queryset(), many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'], permission_classes=[IsGestionnaire])
    def invite_student(self, request):
        serializer = InviteStudentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if User.objects.filter(email=data['email']).exists():
            return Response({"error": "Cet email est déjà utilisé"}, status=status.HTTP_400_BAD_REQUEST)

        classe = None
        if data.get('classe'):
            classe = classes_du_perimetre(request.user).filter(id=data['classe']).first()
            if classe is None:
                return Response({"error": "Classe introuvable dans votre établissement."}, status=status.HTTP_400_BAD_REQUEST)
            verifier_non_archivee(classe.annee_academique)

        token = uuid.uuid4()
        username = data['email'].split('@')[0]
        base_username = username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1

        user = User.objects.create(
            username=username,
            email=data['email'],
            first_name=data['first_name'],
            last_name=data['last_name'],
            matricule=data.get('matricule', ''),
            role='etudiant',
            etablissement=request.user.etablissement,
            must_change_password=True,
            invitation_token=token,
            invited_by=request.user,
            date_invitation=timezone.now(),
            is_invited=True,
            is_active=True,
        )

        mot_de_passe = data.get('mot_de_passe', '')
        if mot_de_passe:
            user.set_password(mot_de_passe)
            user.save()

        audit_log(request, 'invitation', cible=user, details={'role': ETUDIANT})
        if classe is not None:
            from referentiel.models import Inscription
            inscription = Inscription.objects.create(etudiant=user, classe=classe)
            audit_log(request, 'inscription', cible=inscription, etablissement=user.etablissement,
                      details={'etudiant': user.id, 'classe': classe.id})

        if mot_de_passe:
            subject = "Bienvenue sur PEL - Vos identifiants de connexion"
            message = f"""Bonjour {data['first_name']} {data['last_name']},

Votre compte a été créé sur la plateforme PEL (Plateforme d'Évaluation en Ligne).

Vous pouvez vous connecter dès maintenant avec :
- Email : {data['email']}
- Mot de passe : {mot_de_passe}

Lors de votre première connexion, vous serez invité(e) à changer votre mot de passe.

Cordialement,
L'équipe PEL"""
        else:
            activation_url = f"{settings.FRONTEND_URL}/activate/{token}"
            subject = "Bienvenue sur PEL - Créez votre mot de passe"
            message = f"""Bonjour {data['first_name']} {data['last_name']},

Vous avez été invité(e) à rejoindre la plateforme PEL (Plateforme d'Évaluation en Ligne).

Pour activer votre compte et créer votre mot de passe, cliquez sur le lien ci-dessous :
{activation_url}

Ce lien est valable pendant 7 jours.

Si vous n'avez pas demandé cet email, ignorez-le.

Cordialement,
L'équipe PEL"""

        try:
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [data['email']], fail_silently=True)
        except Exception:
            pass

        return Response({
            "message": f"Compte créé pour {data['email']}" + (" : l'étudiant peut se connecter dès maintenant" if mot_de_passe else f" : invitation envoyée à {data['email']}"),
            "user_id": user.id
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], permission_classes=[IsGestionnaire])
    def import_students(self, request):
        serializer = ImportStudentsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        file = serializer.validated_data['file']

        try:
            if file.name.endswith('.csv'):
                file_content = file.read().decode('utf-8')
                reader = csv.DictReader(io.StringIO(file_content))
            else:
                import openpyxl
                wb = openpyxl.load_workbook(file)
                ws = wb.active
                headers = [cell.value for cell in ws[1]]
                reader = []
                for row in ws.iter_rows(min_row=2, values_only=True):
                    reader.append(dict(zip(headers, row)))
        except Exception as e:
            return Response({"error": f"Erreur de lecture du fichier: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        created = 0
        errors = []
        for row_num, row in enumerate(reader, start=2):
            email = row.get('email', '').strip()
            first_name = row.get('prenom', row.get('first_name', '')).strip()
            last_name = row.get('nom', row.get('last_name', '')).strip()

            if not email or not first_name or not last_name:
                errors.append(f"Ligne {row_num}: email, nom et prénom sont requis")
                continue

            if User.objects.filter(email=email).exists():
                errors.append(f"Ligne {row_num}: {email} existe déjà")
                continue

            token = uuid.uuid4()
            username = email.split('@')[0]
            base_username = username
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{base_username}{counter}"
                counter += 1

            nouvel_etudiant = User.objects.create(
                username=username,
                email=email,
                first_name=first_name,
                last_name=last_name,
                role='etudiant',
                etablissement=request.user.etablissement,
                must_change_password=True,
                invitation_token=token,
                invited_by=request.user,
                date_invitation=timezone.now(),
                is_invited=True,
                is_active=True,
            )

            activation_url = f"{settings.FRONTEND_URL}/activate/{token}"
            subject = "Bienvenue sur PEL - Créez votre mot de passe"
            message = f"""Bonjour {first_name} {last_name},

Vous avez été invité(e) à rejoindre la plateforme PEL.

Pour activer votre compte et créer votre mot de passe, cliquez sur le lien ci-dessous :
{activation_url}

Ce lien est valable pendant 7 jours.

Cordialement,
L'équipe PEL"""

            try:
                send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [email], fail_silently=True)
            except Exception:
                pass

            audit_log(request, 'invitation', cible=nouvel_etudiant, details={'role': ETUDIANT, 'import': True})
            created += 1

        return Response({
            "message": f"{created} étudiant(s) importé(s) avec succès",
            "errors": errors,
            "created": created
        })

    @action(detail=False, methods=['post'], permission_classes=[permissions.AllowAny])
    def activate(self, request):
        serializer = ActivateAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            user = User.objects.get(invitation_token=data['token'], is_invited=True)
        except User.DoesNotExist:
            return Response({"error": "Lien d'activation invalide ou déjà utilisé"}, status=status.HTTP_400_BAD_REQUEST)

        if user.date_invitation:
            elapsed = timezone.now() - user.date_invitation
            if elapsed > timedelta(days=7):
                return Response({"error": "Ce lien a expiré. Demandez un nouveau lien."}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(data['password'])
        user.must_change_password = False
        user.is_invited = False
        user.invitation_token = None
        user.save()

        return Response({"message": "Votre compte a été activé avec succès. Vous pouvez vous connecter."})

    @action(detail=False, methods=['post'], permission_classes=[permissions.AllowAny])
    def forgot_password(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']

        try:
            user = User.objects.get(email=email, is_active=True)
        except User.DoesNotExist:
            return Response({"message": "Si cet email existe, un lien de réinitialisation a été envoyé."})

        reset_token = uuid.uuid4()
        user.invitation_token = reset_token
        user.date_invitation = timezone.now()
        user.save()

        reset_url = f"{settings.FRONTEND_URL}/reset-password/{reset_token}"
        subject = "PEL - Réinitialisation de votre mot de passe"
        message = f"""Bonjour {user.first_name},

Vous avez demandé la réinitialisation de votre mot de passe.

Cliquez sur le lien ci-dessous pour créer un nouveau mot de passe :
{reset_url}

Ce lien est valable pendant 24 heures.

Si vous n'avez pas demandé cette réinitialisation, ignorez cet email.

Cordialement,
L'équipe PEL"""

        try:
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [email], fail_silently=True)
        except Exception:
            pass

        return Response({"message": "Si cet email existe, un lien de réinitialisation a été envoyé."})

    @action(detail=False, methods=['post'], permission_classes=[permissions.AllowAny])
    def reset_password(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            user = User.objects.get(invitation_token=data['token'], is_active=True)
        except User.DoesNotExist:
            return Response({"error": "Lien de réinitialisation invalide"}, status=status.HTTP_400_BAD_REQUEST)

        if user.date_invitation:
            elapsed = timezone.now() - user.date_invitation
            if elapsed > timedelta(hours=24):
                return Response({"error": "Ce lien a expiré. Demandez un nouveau lien."}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(data['password'])
        user.invitation_token = None
        user.date_invitation = None
        user.must_change_password = False
        user.save()

        return Response({"message": "Votre mot de passe a été réinitialisé avec succès."})

    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def change_password(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        request.user.set_password(data['new_password'])
        request.user.must_change_password = False
        request.user.save()

        return Response({"message": "Mot de passe modifié avec succès"})

    @action(detail=False, methods=['post'], permission_classes=[permissions.AllowAny])
    def register_admin(self, request):
        serializer = RegisterAdminSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if User.objects.filter(email=data['email']).exists():
            return Response({"error": "Cet email est déjà utilisé"}, status=status.HTTP_400_BAD_REQUEST)

        from referentiel.models import Etablissement
        if Etablissement.objects.filter(code=data['etablissement_code']).exists():
            return Response({"error": f"Le code établissement '{data['etablissement_code']}' existe déjà"}, status=status.HTTP_400_BAD_REQUEST)

        token = uuid.uuid4()
        username = data['email'].split('@')[0]
        base_username = username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1

        user = User.objects.create(
            username=username,
            email=data['email'],
            first_name=data['first_name'],
            last_name=data['last_name'],
            telephone=data.get('telephone', ''),
            role='admin',
            is_active=True,
            is_validated=False,
            validation_status='pending',
            invitation_token=token,
            date_invitation=timezone.now(),
        )
        user.set_password(data['password'])
        user.save()

        etablissement = Etablissement.objects.create(
            code=data['etablissement_code'],
            nom=data['etablissement_nom'],
            sigle=data.get('etablissement_sigle', ''),
            adresse=data.get('etablissement_adresse', ''),
            telephone=data.get('etablissement_telephone', ''),
            email=data.get('etablissement_email', ''),
        )
        user.etablissement = etablissement
        user.save()

        return Response({
            "message": "Votre demande de compte a été envoyée. Vous recevrez une confirmation par email.",
            "user_id": user.id,
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'], permission_classes=[IsSuperAdmin])
    def pending_validations(self, request):
        users = User.objects.filter(validation_status='pending', role='admin')
        serializer = UserSerializer(users, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'], permission_classes=[IsSuperAdmin])
    def validate_admin(self, request):
        user_id = request.data.get('user_id')
        action_type = request.data.get('action')
        rejection_reason = request.data.get('rejection_reason', '')

        try:
            user = User.objects.get(id=user_id, validation_status='pending')
        except User.DoesNotExist:
            return Response({"error": "Utilisateur non trouvé ou déjà traité"}, status=status.HTTP_400_BAD_REQUEST)

        if action_type == 'approve':
            user.is_validated = True
            user.validation_status = 'approved'
            user.save()

            activation_url = f"{settings.FRONTEND_URL}/activate/{user.invitation_token}"
            subject = f"PEL - Votre compte a été approuvé"
            message = f"""Bonjour {user.first_name} {user.last_name},

Votre demande de compte administrateur pour "{user.etablissement.nom}" a été approuvée.

Pour activer votre compte et créer votre mot de passe, cliquez sur le lien ci-dessous :
{activation_url}

Ce lien est valable pendant 7 jours.

Cordialement,
L'équipe PEL"""

            try:
                send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=True)
            except Exception:
                pass

            audit_log(request, 'validation_admin', cible=user)
            return Response({"message": f"Compte de {user.email} approuvé. Invitation envoyée."})

        elif action_type == 'reject':
            user.is_validated = False
            user.validation_status = 'rejected'
            user.rejection_reason = rejection_reason
            user.save()

            subject = f"PEL - Votre demande de compte a été rejetée"
            message = f"""Bonjour {user.first_name} {user.last_name},

Votre demande de compte administrateur pour "{user.etablissement.nom}" a été rejetée.

Motif : {rejection_reason or "Non précisé"}

Si vous pensez qu'il s'agit d'une erreur, contactez le support.

Cordialement,
L'équipe PEL"""

            try:
                send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=True)
            except Exception:
                pass

            audit_log(request, 'rejet_admin', cible=user, details={'motif': rejection_reason})
            return Response({"message": f"Demande de {user.email} rejetée."})

        return Response({"error": "Action invalide. Utilisez 'approve' ou 'reject'."}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def force_change_password(self, request):
        user = request.user
        old_password = request.data.get('ancien_mot_de_passe', '')
        new_password = request.data.get('nouveau_mot_de_passe', '')
        confirm_password = request.data.get('confirmer_mot_de_passe', '')

        if not user.check_password(old_password):
            return Response({"error": "L'ancien mot de passe est incorrect"}, status=status.HTTP_400_BAD_REQUEST)

        if new_password != confirm_password:
            return Response({"error": "Les mots de passe ne correspondent pas"}, status=status.HTTP_400_BAD_REQUEST)

        if len(new_password) < 8:
            return Response({"error": "Le mot de passe doit contenir au moins 8 caractères"}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.must_change_password = False
        user.save()

        return Response({"message": "Mot de passe changé avec succès"})

    @action(detail=False, methods=['post'], permission_classes=[IsAdmin])
    def invite_enseignant(self, request):
        serializer = InviteEnseignantSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if User.objects.filter(email=data['email']).exists():
            return Response({"error": "Cet email est déjà utilisé"}, status=status.HTTP_400_BAD_REQUEST)

        username = data['email'].split('@')[0]
        base_username = username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1

        mot_de_passe = data.get('mot_de_passe', '')
        user = User.objects.create(
            username=username,
            email=data['email'],
            first_name=data['first_name'],
            last_name=data['last_name'],
            telephone=data.get('telephone', ''),
            role='enseignant',
            etablissement=request.user.etablissement,
            must_change_password=bool(mot_de_passe),
            is_active=True,
        )
        if mot_de_passe:
            user.set_password(mot_de_passe)
            user.save()

        audit_log(request, 'invitation', cible=user, details={'role': ENSEIGNANT})
        classes_affectees = self._affecter_classes(user, data.get('classes', []))
        if classes_affectees:
            audit_log(request, 'affectation', cible=user, details={'classes': classes_affectees})

        return Response({
            "message": f"Enseignant créé : {data['email']}" + (" : connexion directe disponible" if mot_de_passe else " : en attente de configuration du mot de passe"),
            "user_id": user.id
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], permission_classes=[IsGestionnaire])
    def update_classes(self, request, pk=None):
        user = self.get_object()
        if user.role != ENSEIGNANT:
            return Response({"error": "Cet utilisateur n'est pas un enseignant"}, status=status.HTTP_400_BAD_REQUEST)
        classes = request.data.get('classes', [])
        if not isinstance(classes, list) or any(isinstance(c, bool) or not isinstance(c, int) for c in classes):
            return Response({"error": "Le champ classes doit être une liste d'identifiants entiers."},
                            status=status.HTTP_400_BAD_REQUEST)
        from referentiel.models import AffectationEnseignant, EnseignantMatiere
        perimetre = classes_du_perimetre(request.user).exclude(annee_academique__archivee=True)
        AffectationEnseignant.objects.filter(enseignant=user, classe__in=perimetre).delete()
        EnseignantMatiere.objects.filter(enseignant=user, classe__in=perimetre).delete()
        classes_affectees = self._affecter_classes(user, classes)
        audit_log(request, 'affectation', cible=user, details={'classes': classes_affectees})
        return Response({"message": "Classes mises à jour avec succès"})

    def _affecter_classes(self, enseignant, classes_ids):
        """Affecte l'enseignant aux classes du périmètre de l'appelant et à leurs EC. Renvoie les ids retenus."""
        from referentiel.models import AffectationEnseignant, EnseignantMatiere, EC
        retenues = []
        for classe in classes_du_perimetre(self.request.user).filter(id__in=classes_ids).exclude(
                annee_academique__archivee=True):
            AffectationEnseignant.objects.get_or_create(enseignant=enseignant, classe=classe)
            for ec_id in EC.objects.filter(ue__filiere=classe.filiere, ue__niveau=classe.niveau).values_list('id', flat=True):
                EnseignantMatiere.objects.get_or_create(enseignant=enseignant, ec_id=ec_id, classe=classe)
            retenues.append(classe.id)
        return retenues

    @action(detail=False, methods=['post'], permission_classes=[IsAdmin])
    def invite_responsable(self, request):
        serializer = InviteResponsableSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if request.user.role == SUPERADMIN:
            from referentiel.models import Etablissement
            etablissement = Etablissement.objects.filter(pk=data.get('etablissement')).first()
            if etablissement is None:
                return Response({"error": "Précisez l'établissement du responsable."}, status=status.HTTP_400_BAD_REQUEST)
        else:
            etablissement = request.user.etablissement
            if etablissement is None:
                return Response({"error": "Votre compte n'est rattaché à aucun établissement."},
                                status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(email=data['email']).exists():
            return Response({"error": "Cet email est déjà utilisé"}, status=status.HTTP_400_BAD_REQUEST)

        token = uuid.uuid4()
        user = User.objects.create(
            username=_generer_username(data['email']),
            email=data['email'],
            first_name=data['first_name'],
            last_name=data['last_name'],
            telephone=data.get('telephone', ''),
            role=RESPONSABLE,
            etablissement=etablissement,
            must_change_password=True,
            invitation_token=token,
            invited_by=request.user,
            date_invitation=timezone.now(),
            is_invited=True,
            is_active=True,
        )

        activation_url = f"{settings.FRONTEND_URL}/activate/{token}"
        message = f"""Bonjour {data['first_name']} {data['last_name']},

Vous avez été nommé(e) responsable de formation pour "{etablissement.nom}" sur la plateforme PEL.

Pour activer votre compte et créer votre mot de passe, cliquez sur le lien ci-dessous :
{activation_url}

Ce lien est valable pendant 7 jours.

Cordialement,
L'équipe PEL"""
        try:
            send_mail("Bienvenue sur PEL : créez votre mot de passe", message,
                      settings.DEFAULT_FROM_EMAIL, [data['email']], fail_silently=True)
        except Exception:
            pass

        audit_log(request, 'invitation', cible=user, details={'role': RESPONSABLE})
        return Response({
            "message": f"Invitation envoyée à {data['email']}",
            "user_id": user.id,
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], permission_classes=[IsAdmin])
    def deactivate(self, request, pk=None):
        cible = self.get_object()
        if cible.pk == request.user.pk:
            return Response({"error": "Vous ne pouvez pas désactiver votre propre compte."}, status=status.HTTP_400_BAD_REQUEST)
        if not peut_gerer_compte(request.user, cible):
            return Response({"error": MESSAGE_REFUS}, status=status.HTTP_403_FORBIDDEN)
        garde = _reponse_garde_dernier_admin(cible)
        if garde:
            return garde
        cible.is_active = False
        cible.save(update_fields=['is_active'])
        audit_log(request, 'desactivation', cible=cible)
        return Response({"message": f"Compte {cible.email} désactivé."})

    @action(detail=True, methods=['post'], permission_classes=[IsAdmin])
    def reactivate(self, request, pk=None):
        cible = self.get_object()
        if not peut_gerer_compte(request.user, cible):
            return Response({"error": MESSAGE_REFUS}, status=status.HTTP_403_FORBIDDEN)
        cible.is_active = True
        cible.save(update_fields=['is_active'])
        audit_log(request, 'reactivation', cible=cible)
        return Response({"message": f"Compte {cible.email} réactivé."})

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def dashboard_stats(self, request):
        user = request.user
        stats = {}

        if user.role in ('admin', 'responsable_formation') and user.etablissement:
            from referentiel.models import Filiere, Classe, AnneeAcademique
            from programming.models import Devoir, SoumissionDevoir
            from quiz.models import Quiz

            etab = user.etablissement
            stats['filieres'] = Filiere.objects.filter(etablissement=etab).count()
            stats['classes'] = Classe.objects.filter(filiere__etablissement=etab).count()
            stats['etudiants'] = User.objects.filter(etablissement=etab, role='etudiant').count()
            stats['enseignants'] = User.objects.filter(etablissement=etab, role='enseignant').count()
            stats['quiz'] = Quiz.objects.filter(filiere__etablissement=etab).count()
            stats['devoirs'] = Devoir.objects.filter(filiere__etablissement=etab).count()
            stats['soumissions'] = SoumissionDevoir.objects.filter(devoir__filiere__etablissement=etab).count()
            stats['annees'] = AnneeAcademique.objects.filter(etablissement=etab).count()

        elif user.role == 'enseignant':
            from programming.models import Devoir, SoumissionDevoir
            from quiz.models import Quiz

            stats['mes_quiz'] = Quiz.objects.filter(cree_par=user).count()
            stats['mes_devoirs'] = Devoir.objects.filter(cree_par=user).count()
            stats['soumissions_recues'] = SoumissionDevoir.objects.filter(devoir__cree_par=user).count()
            stats['soumissions_a_corriger'] = SoumissionDevoir.objects.filter(
                devoir__cree_par=user, statut__in=('soumis', 'en_correction', 'corrigee_auto'),
            ).exclude(devoir__annee_academique__archivee=True).count()

        elif user.role == 'etudiant':
            from programming.models import SoumissionDevoir
            from quiz.models import Quiz

            from quiz.acces import q_quiz_affecte
            stats['quiz_disponibles'] = Quiz.objects.filter(est_publie=True).filter(q_quiz_affecte(user)).exclude(
                annee_academique__archivee=True).count()
            stats['mes_soumissions'] = SoumissionDevoir.objects.filter(etudiant=user).count()
            stats['soumissions_corrigees'] = SoumissionDevoir.objects.filter(etudiant=user, statut='corrige').count()
            if stats['mes_soumissions'] > 0:
                from django.db.models import Avg
                avg = SoumissionDevoir.objects.filter(etudiant=user, statut='corrige').aggregate(avg=Avg('score'))
                stats['moyenne'] = round(avg['avg'] or 0, 1)

        elif user.role == 'superadmin':
            stats['etablissements'] = User.objects.filter(role='admin', validation_status='pending').count()
            stats['total_users'] = User.objects.count()
            stats['total_etudiants'] = User.objects.filter(role='etudiant').count()
            stats['total_enseignants'] = User.objects.filter(role='enseignant').count()
            stats['demandes_attente'] = User.objects.filter(role='admin', validation_status='pending').count()

        return Response(stats)
