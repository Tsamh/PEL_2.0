import uuid
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    etablissement_nom = serializers.CharField(source='etablissement.nom', read_only=True, default=None)
    classe_nom = serializers.SerializerMethodField()
    classes_assignees = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 'role',
            'telephone', 'matricule', 'etablissement', 'etablissement_nom',
            'must_change_password', 'is_invited', 'date_invitation',
            'date_joined', 'is_active', 'is_validated', 'validation_status',
            'rejection_reason', 'classe_nom', 'classes_assignees'
        ]
        read_only_fields = [
            'id', 'date_joined', 'is_invited', 'date_invitation', 'role', 'etablissement',
            'is_active', 'is_validated', 'validation_status', 'rejection_reason',
            'must_change_password',
        ]

    def get_classe_nom(self, obj):
        from referentiel.models import Inscription
        inscription = Inscription.objects.filter(etudiant=obj).select_related('classe').first()
        if inscription:
            return f"{inscription.classe.libelle} ({inscription.classe.code})"
        return None

    def get_classes_assignees(self, obj):
        if obj.role != 'enseignant':
            return None
        from referentiel.models import AffectationEnseignant
        affectations = AffectationEnseignant.objects.filter(enseignant=obj).select_related('classe')
        return [{"id": a.classe.id, "libelle": a.classe.libelle, "code": a.classe.code} for a in affectations]


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'password', 'first_name', 'last_name', 'role', 'telephone', 'matricule', 'etablissement']

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class InviteStudentSerializer(serializers.Serializer):
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    matricule = serializers.CharField(max_length=50, required=False, allow_blank=True)
    classe = serializers.IntegerField(required=False, allow_null=True)
    mot_de_passe = serializers.CharField(max_length=128, required=False, allow_blank=True)


class InviteEnseignantSerializer(serializers.Serializer):
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    telephone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    mot_de_passe = serializers.CharField(max_length=128, required=False, allow_blank=True)
    classes = serializers.ListField(child=serializers.IntegerField(), required=False, default=list)


class ImportStudentsSerializer(serializers.Serializer):
    file = serializers.FileField()

    def validate_file(self, value):
        if not value.name.endswith(('.csv', '.xlsx', '.xls')):
            raise serializers.ValidationError("Le fichier doit être un CSV ou Excel (.csv, .xlsx)")
        return value


class ActivateAccountSerializer(serializers.Serializer):
    token = serializers.UUIDField()
    password = serializers.CharField(validators=[validate_password])
    password_confirm = serializers.CharField()

    def validate(self, data):
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError({"password_confirm": "Les mots de passe ne correspondent pas"})
        return data


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ResetPasswordSerializer(serializers.Serializer):
    token = serializers.UUIDField()
    password = serializers.CharField(validators=[validate_password])
    password_confirm = serializers.CharField()

    def validate(self, data):
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError({"password_confirm": "Les mots de passe ne correspondent pas"})
        return data


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField()
    new_password = serializers.CharField(validators=[validate_password])

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Mot de passe actuel incorrect")
        return value


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()


class RegisterAdminSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(validators=[validate_password])
    password_confirm = serializers.CharField()
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    telephone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    etablissement_nom = serializers.CharField(max_length=200)
    etablissement_code = serializers.CharField(max_length=20)
    etablissement_sigle = serializers.CharField(max_length=30, required=False, allow_blank=True)
    etablissement_adresse = serializers.CharField(required=False, allow_blank=True)
    etablissement_telephone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    etablissement_email = serializers.EmailField(required=False, allow_blank=True)

    def validate(self, data):
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError({"password_confirm": "Les mots de passe ne correspondent pas"})
        return data


class ValidateAdminSerializer(serializers.Serializer):
    rejection_reason = serializers.CharField(required=False, allow_blank=True)
