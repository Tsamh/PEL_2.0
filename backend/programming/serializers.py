from rest_framework import serializers
from .models import Devoir, SoumissionDevoir, NoteMatiere


class DevoirSerializer(serializers.ModelSerializer):
    cree_par_nom = serializers.CharField(source='cree_par.get_full_name', read_only=True, default='')
    filiere_libelle = serializers.CharField(source='filiere.libelle', read_only=True, default=None)
    niveau_libelle = serializers.CharField(source='niveau.libelle', read_only=True, default=None)
    annee_libelle = serializers.CharField(source='annee_academique.libelle', read_only=True, default=None)
    ec_libelle = serializers.CharField(source='ec.libelle', read_only=True, default=None)
    langage_display = serializers.CharField(source='get_langage_display', read_only=True)

    class Meta:
        model = Devoir
        fields = '__all__'
        read_only_fields = ['cree_par']


class DevoirSerializerPublic(serializers.ModelSerializer):
    cree_par_nom = serializers.CharField(source='cree_par.get_full_name', read_only=True, default='')
    filiere_libelle = serializers.CharField(source='filiere.libelle', read_only=True, default=None)
    niveau_libelle = serializers.CharField(source='niveau.libelle', read_only=True, default=None)
    annee_libelle = serializers.CharField(source='annee_academique.libelle', read_only=True, default=None)
    ec_libelle = serializers.CharField(source='ec.libelle', read_only=True, default=None)
    langage_display = serializers.CharField(source='get_langage_display', read_only=True)

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


class NoteMatiereSerializer(serializers.ModelSerializer):
    etudiant_nom = serializers.CharField(source='etudiant.get_full_name', read_only=True)
    ec_libelle = serializers.CharField(source='ec.libelle', read_only=True)
    classe_libelle = serializers.CharField(source='classe.libelle', read_only=True)
    annee_libelle = serializers.CharField(source='annee_academique.libelle', read_only=True)

    class Meta:
        model = NoteMatiere
        fields = ['id', 'etudiant', 'etudiant_nom', 'ec', 'ec_libelle', 'classe', 'classe_libelle',
                  'annee_academique', 'annee_libelle', 'note_devoir', 'note_examen', 'moyenne', 'date_modification']
        read_only_fields = ['id', 'moyenne', 'date_modification']


class NoteMatiereBulkSerializer(serializers.Serializer):
    ec = serializers.IntegerField()
    classe = serializers.IntegerField()
    annee_academique = serializers.IntegerField()
    notes = serializers.ListField(child=serializers.DictField())

    class NotesEntrySerializer(serializers.Serializer):
        etudiant = serializers.IntegerField()
        note_devoir = serializers.FloatField(allow_null=True, required=False)
        note_examen = serializers.FloatField(allow_null=True, required=False)
