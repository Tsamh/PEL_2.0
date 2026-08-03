from rest_framework import serializers
from .models import Quiz, Question, Choix


class ChoixSerializer(serializers.ModelSerializer):
    class Meta:
        model = Choix
        fields = '__all__'


class QuestionSerializer(serializers.ModelSerializer):
    choix = ChoixSerializer(many=True, read_only=True)

    class Meta:
        model = Question
        fields = '__all__'


class QuizSerializer(serializers.ModelSerializer):
    questions = QuestionSerializer(many=True, read_only=True)
    cree_par_nom = serializers.CharField(source='cree_par.get_full_name', read_only=True, default='')
    filiere_libelle = serializers.CharField(source='filiere.libelle', read_only=True, default=None)
    niveau_libelle = serializers.CharField(source='niveau.libelle', read_only=True, default=None)
    annee_libelle = serializers.CharField(source='annee_academique.libelle', read_only=True, default=None)

    class Meta:
        model = Quiz
        fields = '__all__'
