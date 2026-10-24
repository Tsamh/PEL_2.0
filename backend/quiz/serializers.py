from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from .acces import CLES_CIBLES, verifier_cibles
from .exceptions import Conflit, MESSAGE_VERROU
from .models import Quiz, Question, Choix, TentativeQuiz, ReponseQuiz
from .passage import corrige_visible, meilleure_tentative, score_visible


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
            if any(bool(c.get('est_correct')) != (c.get('points', Decimal('0')) > 0) for c in choix):
                raise serializers.ValidationError(
                    "En notation par choix, seuls les choix qui rapportent des points (points supérieurs à 0) "
                    "doivent être marqués comme bonnes réponses, et tous doivent l'être."
                )
    elif type_question == 'courte':
        if not any(c.get('texte', '').strip() for c in bonnes):
            raise serializers.ValidationError("Une réponse courte doit avoir au moins une réponse acceptée.")


def verifier_penalite(attrs):
    """La pénalité reste entre 0 et les points, et seulement en QCM tout ou rien ou en vrai/faux."""
    penalite = attrs.get('penalite', Decimal('0'))
    if not penalite:
        return
    type_question = attrs.get('type_question', 'qcm')
    mode = attrs.get('mode_notation', Question.TOUT_OU_RIEN)
    if not (type_question == 'vf' or (type_question == 'qcm' and mode == Question.TOUT_OU_RIEN)):
        raise serializers.ValidationError(
            {'penalite': ["La pénalité ne s'applique qu'aux QCM en tout ou rien et aux questions vrai/faux."]}
        )
    if penalite > attrs.get('points', Decimal('1')):
        raise serializers.ValidationError({'penalite': ["La pénalité ne peut pas dépasser les points de la question."]})


class QuestionCreateSerializer(serializers.ModelSerializer):
    choix = ChoixImbriqueSerializer(many=True, required=False)

    class Meta:
        model = Question
        fields = ['id', 'texte', 'type_question', 'points', 'mode_notation', 'penalite', 'explication', 'ordre', 'choix']
        read_only_fields = ['id']

    def validate(self, attrs):
        verifier_coherence_question(attrs)
        verifier_penalite(attrs)
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
    choix = serializers.SerializerMethodField()
    est_multiple = serializers.BooleanField(read_only=True)

    class Meta:
        model = Question
        fields = ['id', 'texte', 'type_question', 'points', 'penalite', 'ordre', 'est_multiple', 'choix']

    def get_choix(self, question):
        # Pour une réponse courte, les choix sont les réponses acceptées : ne jamais les envoyer.
        if question.type_question == 'courte':
            return []
        return ChoixEtudiantSerializer(question.choix.all(), many=True).data


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
    classes_detail = serializers.SerializerMethodField()
    groupes_detail = serializers.SerializerMethodField()
    etudiants_detail = serializers.SerializerMethodField()
    nb_cibles = serializers.SerializerMethodField()

    class Meta:
        model = Quiz
        fields = '__all__'
        read_only_fields = ['cree_par', 'code_acces']

    def get_a_des_tentatives(self, quiz):
        return quiz.tentatives.exists()

    def get_classes_detail(self, quiz):
        return [{'id': c.id, 'code': c.code, 'libelle': c.libelle} for c in quiz.classes.all()]

    def get_groupes_detail(self, quiz):
        return [{'id': g.id, 'code': g.code, 'libelle': g.libelle, 'classe_code': g.classe.code} for g in quiz.groupes.all()]

    def get_etudiants_detail(self, quiz):
        return [{'id': u.id, 'nom': u.get_full_name() or u.username} for u in quiz.etudiants.all()]

    def get_nb_cibles(self, quiz):
        return len(quiz.classes.all()) + len(quiz.groupes.all()) + len(quiz.etudiants.all())

    def validate(self, attrs):
        debut = attrs.get('date_debut', getattr(self.instance, 'date_debut', None))
        fin = attrs.get('date_fin', getattr(self.instance, 'date_fin', None))
        if debut and fin and fin <= debut:
            raise serializers.ValidationError({'date_fin': "La date de fin doit être postérieure à la date de début."})
        request = self.context.get('request')
        if request is not None:
            verifier_cibles(request.user, self.instance, attrs)
        return attrs

    def create(self, validated_data):
        questions_data = validated_data.pop('questions', [])
        cibles_data = {cle: validated_data.pop(cle) for cle in CLES_CIBLES if cle in validated_data}
        quiz = Quiz.objects.create(**validated_data)
        for cle, valeurs in cibles_data.items():
            getattr(quiz, cle).set(valeurs)
        _creer_questions(quiz, questions_data)
        return quiz

    def update(self, instance, validated_data):
        questions_data = validated_data.pop('questions', None)
        cibles_data = {cle: validated_data.pop(cle) for cle in CLES_CIBLES if cle in validated_data}
        if questions_data is not None and instance.tentatives.exists():
            raise Conflit(MESSAGE_VERROU)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        for cle, valeurs in cibles_data.items():
            getattr(instance, cle).set(valeurs)
        if questions_data is not None:
            instance.questions.all().delete()
            _creer_questions(instance, questions_data)
        return instance

    def to_representation(self, instance):
        self.fields['questions'] = QuestionReadSerializer(many=True, read_only=True)
        return super().to_representation(instance)


def _resultat(tentative):
    return {'score': str(tentative.score), 'score_max': str(tentative.score_max), 'provisoire': tentative.est_provisoire}


class QuizEtudiantSerializer(serializers.ModelSerializer):
    """Vue étudiant : ni questions ni bonnes réponses. Les questions n'arrivent qu'au démarrage d'une tentative."""
    cree_par_nom = serializers.CharField(source='cree_par.get_full_name', read_only=True, default='')
    filiere_libelle = serializers.CharField(source='filiere.libelle', read_only=True, default=None)
    niveau_libelle = serializers.CharField(source='niveau.libelle', read_only=True, default=None)
    annee_libelle = serializers.CharField(source='annee_academique.libelle', read_only=True, default=None)
    nb_questions = serializers.IntegerField(source='questions.count', read_only=True)
    etat = serializers.SerializerMethodField()
    code_requis = serializers.SerializerMethodField()

    class Meta:
        model = Quiz
        fields = [
            'id', 'titre', 'description', 'filiere', 'filiere_libelle', 'niveau', 'niveau_libelle',
            'annee_academique', 'annee_libelle', 'duree_minutes', 'date_debut', 'date_fin',
            'tentatives_autorisees', 'reprise_autorisee', 'publication_resultats',
            'cree_par_nom', 'nb_questions', 'etat', 'code_requis',
        ]
        read_only_fields = fields

    def get_code_requis(self, quiz):
        return bool(quiz.code_acces)

    def get_etat(self, quiz):
        etudiant = self.context['request'].user
        tentatives = list(quiz.tentatives.filter(etudiant=etudiant).order_by('numero'))
        en_cours = next((t for t in tentatives if t.statut == TentativeQuiz.EN_COURS), None)
        soumises = [t for t in tentatives if t.statut == TentativeQuiz.SOUMISE]
        meilleure = meilleure_tentative(soumises) if score_visible(quiz) else None
        maintenant = timezone.now()
        ouvert = (quiz.date_debut is None or quiz.date_debut <= maintenant) and (quiz.date_fin is None or maintenant < quiz.date_fin)
        return {
            'tentatives_utilisees': len(tentatives),
            'tentatives_restantes': max(0, quiz.tentatives_autorisees - len(tentatives)),
            'tentative_en_cours': en_cours.id if en_cours else None,
            'derniere_tentative': soumises[-1].id if soumises else None,
            'meilleure_note': _resultat(meilleure) if meilleure else None,
            'ouvert': ouvert,
        }


class TentativeEtudiantSerializer(serializers.ModelSerializer):
    quiz_titre = serializers.CharField(source='quiz.titre', read_only=True)
    heure_serveur = serializers.SerializerMethodField()
    questions = serializers.SerializerMethodField()
    reponses = serializers.SerializerMethodField()
    resultat = serializers.SerializerMethodField()
    corrige = serializers.SerializerMethodField()

    class Meta:
        model = TentativeQuiz
        fields = [
            'id', 'quiz', 'quiz_titre', 'numero', 'statut', 'debut', 'fin_prevue', 'soumise_le',
            'soumission_auto', 'heure_serveur', 'questions', 'reponses', 'resultat', 'corrige',
        ]
        read_only_fields = fields

    def get_heure_serveur(self, tentative):
        return serializers.DateTimeField().to_representation(timezone.now())

    def get_questions(self, tentative):
        if tentative.statut != TentativeQuiz.EN_COURS:
            return []
        return QuestionEtudiantSerializer(tentative.quiz.questions.prefetch_related('choix'), many=True).data

    def get_reponses(self, tentative):
        if tentative.statut != TentativeQuiz.EN_COURS:
            return []
        return [
            {'question': r.question_id, 'choix': [c.id for c in r.choix_selectionnes.all()], 'texte': r.texte_reponse}
            for r in tentative.reponses.prefetch_related('choix_selectionnes').order_by('question__ordre', 'id')
        ]

    def get_resultat(self, tentative):
        if tentative.statut != TentativeQuiz.SOUMISE or not score_visible(tentative.quiz):
            return None
        return _resultat(tentative)

    def get_corrige(self, tentative):
        if not corrige_visible(tentative):
            return None
        reponses = {r.question_id: r for r in tentative.reponses.prefetch_related('choix_selectionnes')}
        corrige = []
        for question in tentative.quiz.questions.prefetch_related('choix'):
            reponse = reponses.get(question.id)
            corrige.append({
                'question': question.id,
                'texte': question.texte,
                'type_question': question.type_question,
                'points': str(question.points),
                'penalite': str(question.penalite),
                'explication': question.explication,
                'score_obtenu': str(reponse.score_obtenu) if reponse else '0.00',
                'statut_correction': reponse.statut_correction if reponse else 'auto',
                'choix': [{'id': c.id, 'texte': c.texte, 'est_correct': c.est_correct} for c in question.choix.all()],
                'reponse': {
                    'choix': [c.id for c in reponse.choix_selectionnes.all()] if reponse else [],
                    'texte': reponse.texte_reponse if reponse else '',
                },
            })
        return corrige


class TentativeEnseignantSerializer(serializers.ModelSerializer):
    etudiant_nom = serializers.SerializerMethodField()
    duree_secondes = serializers.IntegerField(read_only=True)
    est_provisoire = serializers.BooleanField(read_only=True)
    nb_a_valider = serializers.SerializerMethodField()
    est_meilleure = serializers.SerializerMethodField()

    class Meta:
        model = TentativeQuiz
        fields = [
            'id', 'etudiant', 'etudiant_nom', 'numero', 'statut', 'debut', 'soumise_le', 'soumission_auto',
            'duree_secondes', 'score', 'score_max', 'est_provisoire', 'nb_a_valider', 'est_meilleure',
        ]
        read_only_fields = fields

    def get_etudiant_nom(self, tentative):
        return tentative.etudiant.get_full_name() or tentative.etudiant.username

    def get_nb_a_valider(self, tentative):
        return sum(1 for r in tentative.reponses.all() if r.statut_correction == ReponseQuiz.A_VALIDER)

    def get_est_meilleure(self, tentative):
        return tentative.id in self.context.get('meilleures', set())


class ReponseCorrectionSerializer(serializers.ModelSerializer):
    etudiant_nom = serializers.SerializerMethodField()
    question_texte = serializers.CharField(source='question.texte', read_only=True)
    points = serializers.DecimalField(source='question.points', max_digits=6, decimal_places=2, read_only=True)
    reponses_acceptees = serializers.SerializerMethodField()

    class Meta:
        model = ReponseQuiz
        fields = [
            'id', 'tentative', 'etudiant_nom', 'question', 'question_texte', 'points', 'texte_reponse',
            'reponses_acceptees', 'score_obtenu', 'similarite', 'statut_correction', 'corrige_le',
        ]
        read_only_fields = fields

    def get_etudiant_nom(self, reponse):
        etudiant = reponse.tentative.etudiant
        return etudiant.get_full_name() or etudiant.username

    def get_reponses_acceptees(self, reponse):
        return [c.texte for c in reponse.question.choix.all() if c.est_correct]
