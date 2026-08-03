from rest_framework import serializers
from .models import Devoir, SoumissionDevoir


class DevoirSerializer(serializers.ModelSerializer):
    cree_par_nom = serializers.CharField(source='cree_par.get_full_name', read_only=True, default='')
    filiere_libelle = serializers.CharField(source='filiere.libelle', read_only=True, default=None)
    niveau_libelle = serializers.CharField(source='niveau.libelle', read_only=True, default=None)
    annee_libelle = serializers.CharField(source='annee_academique.libelle', read_only=True, default=None)

    class Meta:
        model = Devoir
        fields = '__all__'


class DevoirSerializerPublic(serializers.ModelSerializer):
    cree_par_nom = serializers.CharField(source='cree_par.get_full_name', read_only=True, default='')
    filiere_libelle = serializers.CharField(source='filiere.libelle', read_only=True, default=None)
    niveau_libelle = serializers.CharField(source='niveau.libelle', read_only=True, default=None)
    annee_libelle = serializers.CharField(source='annee_academique.libelle', read_only=True, default=None)

    class Meta:
        model = Devoir
        exclude = ['solution', 'test_cases']


class SoumissionDevoirSerializer(serializers.ModelSerializer):
    etudiant_nom = serializers.CharField(source='etudiant.get_full_name', read_only=True)
    devoir_titre = serializers.CharField(source='devoir.titre', read_only=True)

    class Meta:
        model = SoumissionDevoir
        fields = ['id', 'devoir', 'devoir_titre', 'etudiant', 'etudiant_nom', 'code_soumis', 'statut', 'score', 'commentaire', 'date_soumission']
        read_only_fields = ['id', 'etudiant', 'statut', 'score', 'commentaire', 'date_soumission']
