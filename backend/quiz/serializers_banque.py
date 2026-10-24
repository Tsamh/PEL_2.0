from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from accounts.scoping import verifier_references_evaluation

from .banque import appliquer_tags, creer_version, peut_modifier
from .models import Question, QuestionBanque, TagQuestion, VersionQuestion
from .serializers import verifier_coherence_question, verifier_penalite

NB_CHOIX_MAX = 10


class ChoixContenuSerializer(serializers.Serializer):
    texte = serializers.CharField(max_length=500)
    est_correct = serializers.BooleanField(default=False)
    points = serializers.DecimalField(max_digits=6, decimal_places=2, default=Decimal('0'))


class ContenuSerializer(serializers.Serializer):
    """Contenu complet d'une question de la banque (toujours validé en entier)."""
    texte = serializers.CharField()
    type_question = serializers.ChoiceField(choices=Question.TYPE_CHOICES, default='qcm')
    points = serializers.DecimalField(max_digits=6, decimal_places=2, min_value=Decimal('0.01'), default=Decimal('1'))
    mode_notation = serializers.ChoiceField(choices=Question.MODE_CHOICES, default=Question.TOUT_OU_RIEN)
    penalite = serializers.DecimalField(max_digits=6, decimal_places=2, min_value=Decimal('0'), default=Decimal('0'))
    explication = serializers.CharField(allow_blank=True, default='')
    choix = ChoixContenuSerializer(many=True)

    def validate(self, attrs):
        if len(attrs['choix']) > NB_CHOIX_MAX:
            raise serializers.ValidationError({'choix': [f"Une question a au plus {NB_CHOIX_MAX} choix."]})
        verifier_coherence_question(attrs)
        verifier_penalite(attrs)
        return attrs


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = TagQuestion
        fields = ['id', 'type', 'libelle']


class VersionSerializer(serializers.ModelSerializer):
    creee_par_nom = serializers.SerializerMethodField()

    class Meta:
        model = VersionQuestion
        fields = ['id', 'numero', 'texte', 'type_question', 'points', 'mode_notation', 'penalite', 'explication',
                  'choix', 'creee_par_nom', 'date']

    def get_creee_par_nom(self, version):
        u = version.creee_par
        return (u.get_full_name() or u.username) if u else ''


class QuestionBanqueSerializer(serializers.ModelSerializer):
    auteur_nom = serializers.SerializerMethodField()
    ec_libelle = serializers.CharField(source='ec.libelle', read_only=True, default=None)
    tags = TagSerializer(many=True, read_only=True)
    version = serializers.SerializerMethodField()
    nb_versions = serializers.SerializerMethodField()
    modifiable = serializers.SerializerMethodField()
    contenu = serializers.JSONField(write_only=True, required=False)
    chapitres = serializers.ListField(child=serializers.CharField(max_length=100, allow_blank=True),
                                      write_only=True, required=False)
    competences = serializers.ListField(child=serializers.CharField(max_length=100, allow_blank=True),
                                        write_only=True, required=False)

    class Meta:
        model = QuestionBanque
        fields = ['id', 'auteur', 'auteur_nom', 'ec', 'ec_libelle', 'partagee', 'difficulte', 'archivee',
                  'date_creation', 'tags', 'version', 'nb_versions', 'modifiable', 'contenu', 'chapitres',
                  'competences']
        read_only_fields = ['auteur', 'date_creation']

    version_creee = None

    def get_auteur_nom(self, fiche):
        u = fiche.auteur
        return (u.get_full_name() or u.username) if u else ''

    def get_version(self, fiche):
        courante = fiche.courante
        return VersionSerializer(courante).data if courante else None

    def get_nb_versions(self, fiche):
        return len(fiche.versions.all())

    def get_modifiable(self, fiche):
        return peut_modifier(self.context['request'].user, fiche)

    def validate_contenu(self, valeur):
        contenu = ContenuSerializer(data=valeur)
        if not contenu.is_valid():
            raise serializers.ValidationError(contenu.errors)
        return contenu.validated_data

    def validate_ec(self, ec):
        if ec is not None:
            verifier_references_evaluation(self.context['request'].user, {'ec': ec})
        return ec

    def validate(self, attrs):
        if self.instance is None and 'contenu' not in attrs:
            raise serializers.ValidationError({'contenu': ['Ce champ est obligatoire.']})
        return attrs

    def create(self, validated_data):
        contenu = validated_data.pop('contenu')
        chapitres = validated_data.pop('chapitres', [])
        competences = validated_data.pop('competences', [])
        acteur = self.context['request'].user
        with transaction.atomic():
            fiche = QuestionBanque.objects.create(auteur=acteur, etablissement_id=acteur.etablissement_id, **validated_data)
            self.version_creee, _ = creer_version(fiche, contenu, acteur)
            appliquer_tags(fiche, chapitres, competences)
        return fiche

    def update(self, instance, validated_data):
        contenu = validated_data.pop('contenu', None)
        chapitres = validated_data.pop('chapitres', None)
        competences = validated_data.pop('competences', None)
        acteur = self.context['request'].user
        self.version_creee = None
        with transaction.atomic():
            for attr, valeur in validated_data.items():
                setattr(instance, attr, valeur)
            instance.save()
            if contenu is not None:
                version, creee = creer_version(instance, contenu, acteur)
                if creee:
                    self.version_creee = version
            if chapitres is not None or competences is not None:
                actuels = list(instance.tags.all())
                if chapitres is None:
                    chapitres = [t.libelle for t in actuels if t.type == TagQuestion.CHAPITRE]
                if competences is None:
                    competences = [t.libelle for t in actuels if t.type == TagQuestion.COMPETENCE]
                appliquer_tags(instance, chapitres, competences)
        return instance
