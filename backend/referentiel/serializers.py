import uuid
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from .models import (
    Etablissement, AnneeAcademique, Filiere, Niveau, UE, EC, Cours,
    Classe, Groupe, Inscription, EnseignantMatiere
)

User = get_user_model()


class EtablissementSerializer(serializers.ModelSerializer):
    admin_nom = serializers.SerializerMethodField()

    class Meta:
        model = Etablissement
        fields = '__all__'

    def get_admin_nom(self, obj):
        admin = User.objects.filter(etablissement=obj, role='admin').first()
        if admin:
            return admin.get_full_name() or admin.email
        return None


class CreateEtablissementSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=20)
    nom = serializers.CharField(max_length=200)
    sigle = serializers.CharField(max_length=30, required=False, allow_blank=True)
    adresse = serializers.CharField(required=False, allow_blank=True)
    telephone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    email = serializers.CharField(max_length=254, required=False, allow_blank=True)
    site_web = serializers.URLField(required=False, allow_blank=True)
    admin_email = serializers.EmailField()
    admin_first_name = serializers.CharField(max_length=150)
    admin_last_name = serializers.CharField(max_length=150)


class InviteAdminSerializer(serializers.Serializer):
    admin_email = serializers.EmailField()
    admin_first_name = serializers.CharField(max_length=150)
    admin_last_name = serializers.CharField(max_length=150)


class AnneeAcademiqueSerializer(serializers.ModelSerializer):
    etablissement_nom = serializers.CharField(source='etablissement.nom', read_only=True, default=None)
    filieres = serializers.SerializerMethodField()

    class Meta:
        model = AnneeAcademique
        fields = '__all__'

    def get_filieres(self, obj):
        if 'include_filieres' not in self.context.get('view', {}).__class__.__name__:
            return None
        filieres = Filiere.objects.filter(etablissement=obj.etablissement) if obj.etablissement else Filiere.objects.all()
        return FiliereSerializer(filieres, many=True).data


class CreateAnneeWithFiliereSerializer(serializers.Serializer):
    annee_libelle = serializers.CharField(max_length=20)
    annee_date_debut = serializers.DateField()
    annee_date_fin = serializers.DateField()
    annee_est_active = serializers.BooleanField(default=False)
    annee_etablissement = serializers.IntegerField(required=False, allow_null=True)

    filieres = serializers.ListField(child=serializers.DictField(), required=False, default=list)

    def validate_filieres(self, value):
        for f in value:
            if 'code' not in f or 'libelle' not in f:
                raise serializers.ValidationError("Chaque filière doit avoir 'code' et 'libelle'")
            if 'niveau' not in f or not f['niveau']:
                raise serializers.ValidationError("Chaque filière doit avoir un 'niveau'")
        return value


class FiliereSerializer(serializers.ModelSerializer):
    etablissement_nom = serializers.CharField(source='etablissement.nom', read_only=True, default=None)

    class Meta:
        model = Filiere
        fields = '__all__'


class NiveauSerializer(serializers.ModelSerializer):
    class Meta:
        model = Niveau
        fields = '__all__'


class CoursSerializer(serializers.ModelSerializer):
    ec_libelle = serializers.CharField(source='ec.libelle', read_only=True)
    ue_libelle = serializers.CharField(source='ec.ue.libelle', read_only=True)
    filiere_libelle = serializers.CharField(source='ec.ue.filiere.libelle', read_only=True)

    class Meta:
        model = Cours
        fields = '__all__'


class ECSerializer(serializers.ModelSerializer):
    ue_libelle = serializers.CharField(source='ue.libelle', read_only=True)

    class Meta:
        model = EC
        fields = '__all__'


class UESerializer(serializers.ModelSerializer):
    filiere_libelle = serializers.CharField(source='filiere.libelle', read_only=True)
    niveau_libelle = serializers.CharField(source='niveau.libelle', read_only=True)
    ecs = ECSerializer(many=True, read_only=True)

    class Meta:
        model = UE
        fields = '__all__'


class GroupeSerializer(serializers.ModelSerializer):
    classe_libelle = serializers.CharField(source='classe.libelle', read_only=True)

    class Meta:
        model = Groupe
        fields = '__all__'


class ClasseSerializer(serializers.ModelSerializer):
    filiere_libelle = serializers.CharField(source='filiere.libelle', read_only=True)
    niveau_libelle = serializers.CharField(source='niveau.libelle', read_only=True)
    annee_libelle = serializers.CharField(source='annee_academique.libelle', read_only=True)
    groupes = GroupeSerializer(many=True, read_only=True)

    class Meta:
        model = Classe
        fields = '__all__'


class InscriptionSerializer(serializers.ModelSerializer):
    etudiant_nom = serializers.CharField(source='etudiant.get_full_name', read_only=True)
    classe_libelle = serializers.CharField(source='classe.libelle', read_only=True)

    class Meta:
        model = Inscription
        fields = '__all__'


class EnseignantMatiereSerializer(serializers.ModelSerializer):
    enseignant_nom = serializers.CharField(source='enseignant.get_full_name', read_only=True)
    ec_libelle = serializers.CharField(source='ec.libelle', read_only=True)
    classe_libelle = serializers.CharField(source='classe.libelle', read_only=True)

    class Meta:
        model = EnseignantMatiere
        fields = '__all__'
