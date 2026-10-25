import uuid
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from .models import (
    Etablissement, AnneeAcademique, Filiere, Niveau, UE, EC, Cours,
    Classe, Groupe, Inscription, EnseignantMatiere, Semestre, PeriodeEvaluation
)

User = get_user_model()


class EtablissementSerializer(serializers.ModelSerializer):
    admin_nom = serializers.SerializerMethodField()

    class Meta:
        model = Etablissement
        fields = '__all__'
        read_only_fields = ['validation_quiz_requise', 'delai_retard_minutes']  # modifié seulement par l'action `parametres`, avec audit

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
    membres_detail = serializers.SerializerMethodField()

    class Meta:
        model = Groupe
        fields = ['id', 'code', 'libelle', 'classe', 'classe_libelle', 'type_groupe', 'membres_detail']

    def get_membres_detail(self, groupe):
        # Un étudiant ne voit pas la liste de ses camarades.
        request = self.context.get('request')
        if request is None or request.user.role == 'etudiant':
            return []
        membres = [{'id': u.id, 'nom': u.get_full_name() or u.username} for u in groupe.membres.all()]
        return sorted(membres, key=lambda m: m['nom'].lower())


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


def _verifier_bornes(attrs, instance, parent_cle, message_parent):
    """Début avant fin, et dates dans celles du parent (année ou semestre)."""
    def valeur(cle):
        return attrs.get(cle, getattr(instance, cle, None))
    debut, fin, parent = valeur('date_debut'), valeur('date_fin'), valeur(parent_cle)
    if debut and fin and debut > fin:
        raise serializers.ValidationError({'date_fin': ["La date de fin doit suivre la date de début."]})
    if parent and debut and fin and (debut < parent.date_debut or fin > parent.date_fin):
        raise serializers.ValidationError({'date_debut': [message_parent]})


class SemestreSerializer(serializers.ModelSerializer):
    annee_libelle = serializers.CharField(source='annee_academique.libelle', read_only=True)

    class Meta:
        model = Semestre
        fields = '__all__'

    def validate(self, attrs):
        _verifier_bornes(attrs, self.instance, 'annee_academique', "Le semestre doit tenir dans les dates de l'année académique.")
        return attrs


class PeriodeEvaluationSerializer(serializers.ModelSerializer):
    semestre_libelle = serializers.CharField(source='semestre.libelle', read_only=True)
    annee_academique = serializers.IntegerField(source='semestre.annee_academique_id', read_only=True)

    class Meta:
        model = PeriodeEvaluation
        fields = '__all__'

    def validate(self, attrs):
        _verifier_bornes(attrs, self.instance, 'semestre', "La période doit tenir dans les dates du semestre.")
        return attrs
