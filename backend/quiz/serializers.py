from decimal import Decimal

from rest_framework import serializers

from .exceptions import Conflit, MESSAGE_VERROU
from .models import Quiz, Question, Choix


class ChoixSerializer(serializers.ModelSerializer):
    class Meta:
        model = Choix
        fields = '__all__'


class ChoixImbriqueSerializer(serializers.ModelSerializer):
    """Choix saisi dans le formulaire d'un quiz : la question est déduite du parent."""

    class Meta:
        model = Choix
        fields = ['id', 'texte', 'est_correct', 'ordre', 'points']
        read_only_fields = ['id']


def verifier_coherence_question(attrs):
    type_question = attrs.get('type_question', 'qcm')
    choix = attrs.get('choix', [])
    bonnes = [c for c in choix if c.get('est_correct')]
    if type_question == 'vf':
        if len(choix) != 2 or len(bonnes) != 1:
            raise serializers.ValidationError("Une question vrai/faux a exactement deux choix, dont une seule bonne réponse.")
    elif type_question == 'qcm':
        if len(choix) < 2 or not bonnes:
            raise serializers.ValidationError("Un QCM a au moins deux choix et au moins une bonne réponse.")
        if attrs.get('mode_notation', Question.TOUT_OU_RIEN) == Question.PAR_CHOIX:
            points = attrs.get('points', Decimal('1'))
            total = sum((c.get('points', Decimal('0')) for c in choix if c.get('points', Decimal('0')) > 0), Decimal('0'))
            if total != points:
                raise serializers.ValidationError(
                    f"En notation par choix, la somme des points positifs ({total}) doit être égale aux points de la question ({points})."
                )
    elif type_question == 'courte':
        if not any(c.get('texte', '').strip() for c in bonnes):
            raise serializers.ValidationError("Une réponse courte doit avoir au moins une réponse acceptée.")


class QuestionCreateSerializer(serializers.ModelSerializer):
    choix = ChoixImbriqueSerializer(many=True, required=False)

    class Meta:
        model = Question
        fields = ['id', 'texte', 'type_question', 'points', 'mode_notation', 'ordre', 'choix']
        read_only_fields = ['id']

    def validate(self, attrs):
        verifier_coherence_question(attrs)
        return attrs


class QuestionReadSerializer(serializers.ModelSerializer):
    choix = ChoixSerializer(many=True, read_only=True)

    class Meta:
        model = Question
        fields = '__all__'


class ChoixEtudiantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Choix
        fields = ['id', 'texte', 'ordre']


class QuestionEtudiantSerializer(serializers.ModelSerializer):
    choix = ChoixEtudiantSerializer(many=True, read_only=True)

    class Meta:
        model = Question
        fields = ['id', 'texte', 'type_question', 'points', 'ordre', 'choix']


def _creer_questions(quiz, questions_data):
    for i, q_data in enumerate(questions_data):
        choix_data = q_data.pop('choix', [])
        q_data.setdefault('ordre', i + 1)
        question = Question.objects.create(quiz=quiz, **q_data)
        for j, c_data in enumerate(choix_data):
            c_data.setdefault('ordre', j + 1)
            Choix.objects.create(question=question, **c_data)


class QuizSerializer(serializers.ModelSerializer):
    questions = QuestionCreateSerializer(many=True, required=False)
    cree_par_nom = serializers.CharField(source='cree_par.get_full_name', read_only=True, default='')
    filiere_libelle = serializers.CharField(source='filiere.libelle', read_only=True, default=None)
    niveau_libelle = serializers.CharField(source='niveau.libelle', read_only=True, default=None)
    annee_libelle = serializers.CharField(source='annee_academique.libelle', read_only=True, default=None)
    a_des_tentatives = serializers.SerializerMethodField()

    class Meta:
        model = Quiz
        fields = '__all__'
        read_only_fields = ['cree_par']

    def get_a_des_tentatives(self, quiz):
        return quiz.tentatives.exists()

    def validate(self, attrs):
        debut = attrs.get('date_debut', getattr(self.instance, 'date_debut', None))
        fin = attrs.get('date_fin', getattr(self.instance, 'date_fin', None))
        if debut and fin and fin <= debut:
            raise serializers.ValidationError({'date_fin': "La date de fin doit être postérieure à la date de début."})
        return attrs

    def create(self, validated_data):
        questions_data = validated_data.pop('questions', [])
        quiz = Quiz.objects.create(**validated_data)
        _creer_questions(quiz, questions_data)
        return quiz

    def update(self, instance, validated_data):
        questions_data = validated_data.pop('questions', None)
        if questions_data is not None and instance.tentatives.exists():
            raise Conflit(MESSAGE_VERROU)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if questions_data is not None:
            instance.questions.all().delete()
            _creer_questions(instance, questions_data)
        return instance

    def to_representation(self, instance):
        self.fields['questions'] = QuestionReadSerializer(many=True, read_only=True)
        return super().to_representation(instance)


class QuizEtudiantSerializer(serializers.ModelSerializer):
    """Vue étudiant : jamais de bonne réponse. La publication du corrigé arrive au sous-projet 3."""
    questions = QuestionEtudiantSerializer(many=True, read_only=True)
    cree_par_nom = serializers.CharField(source='cree_par.get_full_name', read_only=True, default='')
    filiere_libelle = serializers.CharField(source='filiere.libelle', read_only=True, default=None)
    niveau_libelle = serializers.CharField(source='niveau.libelle', read_only=True, default=None)
    annee_libelle = serializers.CharField(source='annee_academique.libelle', read_only=True, default=None)

    class Meta:
        model = Quiz
        fields = [
            'id', 'titre', 'description', 'filiere', 'filiere_libelle', 'niveau', 'niveau_libelle',
            'annee_academique', 'annee_libelle', 'duree_minutes', 'date_debut', 'date_fin',
            'cree_par_nom', 'questions',
        ]
        read_only_fields = fields
