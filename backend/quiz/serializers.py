from rest_framework import serializers
from .models import Quiz, Question, Choix


class ChoixSerializer(serializers.ModelSerializer):
    class Meta:
        model = Choix
        fields = '__all__'


class QuestionCreateSerializer(serializers.ModelSerializer):
    choix = ChoixSerializer(many=True, required=False)

    class Meta:
        model = Question
        fields = ['id', 'texte', 'type_question', 'points', 'ordre', 'choix']


class QuestionReadSerializer(serializers.ModelSerializer):
    choix = ChoixSerializer(many=True, read_only=True)

    class Meta:
        model = Question
        fields = '__all__'


class QuizSerializer(serializers.ModelSerializer):
    questions = QuestionCreateSerializer(many=True, required=False)
    cree_par_nom = serializers.CharField(source='cree_par.get_full_name', read_only=True, default='')
    filiere_libelle = serializers.CharField(source='filiere.libelle', read_only=True, default=None)
    niveau_libelle = serializers.CharField(source='niveau.libelle', read_only=True, default=None)
    annee_libelle = serializers.CharField(source='annee_academique.libelle', read_only=True, default=None)

    class Meta:
        model = Quiz
        fields = '__all__'

    def create(self, validated_data):
        questions_data = validated_data.pop('questions', [])
        quiz = Quiz.objects.create(**validated_data)
        for i, q_data in enumerate(questions_data):
            choix_data = q_data.pop('choix', [])
            q_data.setdefault('ordre', i + 1)
            question = Question.objects.create(quiz=quiz, **q_data)
            for j, c_data in enumerate(choix_data):
                c_data.setdefault('ordre', j + 1)
                Choix.objects.create(question=question, **c_data)
        return quiz

    def update(self, instance, validated_data):
        questions_data = validated_data.pop('questions', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if questions_data is not None:
            instance.questions.all().delete()
            for i, q_data in enumerate(questions_data):
                choix_data = q_data.pop('choix', [])
                q_data.setdefault('ordre', i + 1)
                question = Question.objects.create(quiz=instance, **q_data)
                for j, c_data in enumerate(choix_data):
                    c_data.setdefault('ordre', j + 1)
                    Choix.objects.create(question=question, **c_data)

        return instance

    def to_representation(self, instance):
        self.fields['questions'] = QuestionReadSerializer(many=True, read_only=True)
        return super().to_representation(instance)
