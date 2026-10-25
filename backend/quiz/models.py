from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F
from django.db.models.functions import Lower
from django.utils import timezone


def normalize_text(text):
    """Normalize text for fuzzy comparison: lowercase, strip, remove accents, collapse spaces."""
    import unicodedata
    text = text.strip().lower()
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    text = ' '.join(text.split())
    return text


def fuzzy_match(answer, expected, threshold=0.8):
    """
    Check if `answer` matches `expected` with tolerance for:
    - Case differences
    - Accent differences
    - Minor spelling/grammar mistakes
    - Extra/missing spaces
    Returns (is_correct: bool, similarity: float)
    """
    from difflib import SequenceMatcher
    norm_answer = normalize_text(answer)
    norm_expected = normalize_text(expected)

    if norm_answer == norm_expected:
        return True, 1.0

    similarity = SequenceMatcher(None, norm_answer, norm_expected).ratio()
    return similarity >= threshold, round(similarity, 2)


class Quiz(models.Model):
    PUBLICATION_IMMEDIATE = 'immediate'
    PUBLICATION_DIFFEREE = 'differee'
    PUBLICATION_CHOICES = [
        (PUBLICATION_IMMEDIATE, 'Immédiate'),
        (PUBLICATION_DIFFEREE, 'Différée'),
    ]
    BROUILLON = 'brouillon'
    EN_ATTENTE = 'en_attente'
    VALIDEE = 'validee'
    REFUSEE = 'refusee'
    STATUT_VALIDATION_CHOICES = [
        (BROUILLON, 'Brouillon'),
        (EN_ATTENTE, 'En attente de validation'),
        (VALIDEE, 'Validé'),
        (REFUSEE, 'Refusé'),
    ]

    titre = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    filiere = models.ForeignKey('referentiel.Filiere', on_delete=models.CASCADE, related_name='quizzes', null=True, blank=True)
    niveau = models.ForeignKey('referentiel.Niveau', on_delete=models.SET_NULL, null=True, blank=True)
    annee_academique = models.ForeignKey('referentiel.AnneeAcademique', on_delete=models.SET_NULL, null=True, blank=True)
    periode = models.ForeignKey('referentiel.PeriodeEvaluation', on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='quizzes')
    duree_minutes = models.PositiveIntegerField(default=30, validators=[MinValueValidator(1)])
    date_debut = models.DateTimeField(null=True, blank=True)
    date_fin = models.DateTimeField(null=True, blank=True)
    est_publie = models.BooleanField(default=False)
    tentatives_autorisees = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    reprise_autorisee = models.BooleanField(default=True)
    publication_resultats = models.CharField(max_length=10, choices=PUBLICATION_CHOICES, default=PUBLICATION_IMMEDIATE)
    resultats_publies = models.BooleanField(default=False)
    afficher_corrige = models.BooleanField(default=False)
    statut_validation = models.CharField(max_length=12, choices=STATUT_VALIDATION_CHOICES, default=BROUILLON)
    motif_refus = models.TextField(blank=True, default='')
    soumis_le = models.DateTimeField(null=True, blank=True)
    valide_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='quizzes_valides')
    valide_le = models.DateTimeField(null=True, blank=True)
    classes = models.ManyToManyField('referentiel.Classe', related_name='quizzes_affectes', blank=True)
    groupes = models.ManyToManyField('referentiel.Groupe', related_name='quizzes_affectes', blank=True)
    etudiants = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='quizzes_affectes', blank=True)
    code_acces = models.CharField(max_length=6, blank=True, default='')
    cree_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='quizzes_crees')
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Quiz"
        verbose_name_plural = "Quiz"
        ordering = ['-date_creation']

    def __str__(self):
        return self.titre

    @property
    def etablissement(self):
        """Établissement de la filière, ou du créateur si le quiz n'a pas de filière."""
        if self.filiere_id:
            return self.filiere.etablissement
        return getattr(self.cree_par, 'etablissement', None)

class Question(models.Model):
    TYPE_CHOICES = [
        ('qcm', 'QCM'),
        ('vf', 'Vrai/Faux'),
        ('courte', 'Réponse courte'),
    ]
    TOUT_OU_RIEN = 'tout_ou_rien'
    PAR_CHOIX = 'par_choix'
    MODE_CHOICES = [
        (TOUT_OU_RIEN, 'Tout ou rien'),
        (PAR_CHOIX, 'Points par choix'),
    ]
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    texte = models.TextField()
    type_question = models.CharField(max_length=10, choices=TYPE_CHOICES, default='qcm')
    points = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('1'),
                                 validators=[MinValueValidator(Decimal('0.01'))])
    mode_notation = models.CharField(max_length=12, choices=MODE_CHOICES, default=TOUT_OU_RIEN)
    ordre = models.PositiveIntegerField(default=0)
    penalite = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('0'),
                                   validators=[MinValueValidator(Decimal('0'))])
    explication = models.TextField(blank=True, default='')
    source = models.ForeignKey('VersionQuestion', on_delete=models.SET_NULL, null=True, blank=True, related_name='copies')
    version_source = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        verbose_name = "Question"
        verbose_name_plural = "Questions"
        ordering = ['ordre']

    def __str__(self):
        return self.texte[:80]

    @property
    def est_multiple(self):
        """QCM à plusieurs bonnes réponses (cases à cocher côté étudiant)."""
        return self.type_question == 'qcm' and sum(1 for c in self.choix.all() if c.est_correct) > 1

class Choix(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='choix')
    texte = models.CharField(max_length=500)
    est_correct = models.BooleanField(default=False)
    points = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('0'))
    ordre = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Choix"
        verbose_name_plural = "Choix"
        ordering = ['ordre']

    def __str__(self):
        return self.texte[:80]

class TentativeQuiz(models.Model):
    EN_COURS = 'en_cours'
    SOUMISE = 'soumise'
    STATUT_CHOICES = [
        (EN_COURS, 'En cours'),
        (SOUMISE, 'Soumise'),
    ]
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='tentatives')
    etudiant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='tentatives_quiz')
    numero = models.PositiveIntegerField(default=1)
    statut = models.CharField(max_length=10, choices=STATUT_CHOICES, default=EN_COURS)
    debut = models.DateTimeField(default=timezone.now)
    fin_prevue = models.DateTimeField(null=True, blank=True)
    soumise_le = models.DateTimeField(null=True, blank=True)
    soumission_auto = models.BooleanField(default=False)
    score = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0'))
    score_max = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0'))

    class Meta:
        verbose_name = "Tentative de quiz"
        verbose_name_plural = "Tentatives de quiz"
        ordering = ['-debut', '-id']
        constraints = [
            models.UniqueConstraint(fields=['quiz', 'etudiant', 'numero'], name='tentative_unique_par_numero'),
        ]

    def __str__(self):
        return f"{self.etudiant} - {self.quiz} (tentative {self.numero})"

    @property
    def est_provisoire(self):
        return any(r.statut_correction == ReponseQuiz.A_VALIDER for r in self.reponses.all())

    @property
    def duree_secondes(self):
        if self.soumise_le is None:
            return None
        return int((self.soumise_le - self.debut).total_seconds())

    @property
    def etablissement(self):
        return self.quiz.etablissement

class ReponseQuiz(models.Model):
    AUTO = 'auto'
    A_VALIDER = 'a_valider'
    VALIDEE = 'validee'
    STATUT_CHOICES = [
        (AUTO, 'Correction automatique'),
        (A_VALIDER, 'À valider'),
        (VALIDEE, 'Validée'),
    ]
    tentative = models.ForeignKey(TentativeQuiz, on_delete=models.CASCADE, related_name='reponses')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    choix_selectionnes = models.ManyToManyField(Choix, blank=True, related_name='reponses_quiz')
    texte_reponse = models.TextField(blank=True, default='')
    score_obtenu = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('0'))
    similarite = models.FloatField(default=0, help_text="Score de similarité pour réponses courtes (0-1)")
    statut_correction = models.CharField(max_length=10, choices=STATUT_CHOICES, default=AUTO)
    corrige_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='corrections_quiz')
    corrige_le = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Réponse quiz"
        verbose_name_plural = "Réponses quiz"
        constraints = [
            models.UniqueConstraint(fields=['tentative', 'question'], name='reponse_unique_par_question'),
        ]

    def __str__(self):
        return f"{self.question} ({self.score_obtenu})"


class TagQuestion(models.Model):
    CHAPITRE = 'chapitre'
    COMPETENCE = 'competence'
    TYPE_CHOICES = [(CHAPITRE, 'Chapitre'), (COMPETENCE, 'Compétence')]

    etablissement = models.ForeignKey('referentiel.Etablissement', on_delete=models.CASCADE, null=True, blank=True,
                                      related_name='tags_questions')
    type = models.CharField(max_length=12, choices=TYPE_CHOICES)
    libelle = models.CharField(max_length=100)

    class Meta:
        verbose_name = "Tag de question"
        verbose_name_plural = "Tags de questions"
        ordering = ['type', 'libelle']
        constraints = [
            models.UniqueConstraint(F('etablissement'), F('type'), Lower('libelle'), name='tag_question_unique'),
        ]

    def __str__(self):
        return self.libelle


class QuestionBanque(models.Model):
    FACILE = 'facile'
    MOYEN = 'moyen'
    DIFFICILE = 'difficile'
    DIFFICULTE_CHOICES = [(FACILE, 'Facile'), (MOYEN, 'Moyen'), (DIFFICILE, 'Difficile')]

    auteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                               related_name='questions_banque')
    etablissement = models.ForeignKey('referentiel.Etablissement', on_delete=models.CASCADE, null=True, blank=True,
                                      related_name='questions_banque')
    ec = models.ForeignKey('referentiel.EC', on_delete=models.SET_NULL, null=True, blank=True,
                           related_name='questions_banque')
    partagee = models.BooleanField(default=False)
    difficulte = models.CharField(max_length=10, choices=DIFFICULTE_CHOICES, default=MOYEN)
    tags = models.ManyToManyField(TagQuestion, related_name='questions', blank=True)
    archivee = models.BooleanField(default=False)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Question de la banque"
        verbose_name_plural = "Questions de la banque"
        ordering = ['-date_creation', '-id']

    def __str__(self):
        return f"Question {self.pk}"

    @property
    def courante(self):
        """Version la plus récente (utilise le préchargement de `versions` s'il existe)."""
        versions = list(self.versions.all())
        return max(versions, key=lambda v: v.numero) if versions else None


class VersionQuestion(models.Model):
    question = models.ForeignKey(QuestionBanque, on_delete=models.CASCADE, related_name='versions')
    numero = models.PositiveIntegerField()
    texte = models.TextField()
    type_question = models.CharField(max_length=10, choices=Question.TYPE_CHOICES, default='qcm')
    points = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('1'),
                                 validators=[MinValueValidator(Decimal('0.01'))])
    mode_notation = models.CharField(max_length=12, choices=Question.MODE_CHOICES, default=Question.TOUT_OU_RIEN)
    penalite = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('0'),
                                   validators=[MinValueValidator(Decimal('0'))])
    explication = models.TextField(blank=True, default='')
    choix = models.JSONField(default=list)
    creee_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                  related_name='versions_questions')
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Version de question"
        verbose_name_plural = "Versions de questions"
        ordering = ['-numero']
        constraints = [models.UniqueConstraint(fields=['question', 'numero'], name='version_question_unique')]

    def __str__(self):
        return f"{self.question} v{self.numero}"


class SessionQuiz(models.Model):
    NORMALE = 'normale'
    RATTRAPAGE = 'rattrapage'
    TYPE_CHOICES = [(NORMALE, 'Session'), (RATTRAPAGE, 'Rattrapage')]

    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='sessions')
    type = models.CharField(max_length=12, choices=TYPE_CHOICES, default=NORMALE)
    libelle = models.CharField(max_length=100, blank=True, default='')
    ouverture = models.DateTimeField()
    fermeture = models.DateTimeField()
    periode = models.ForeignKey('referentiel.PeriodeEvaluation', on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='sessions_quiz')
    classes = models.ManyToManyField('referentiel.Classe', related_name='sessions_quiz', blank=True)
    groupes = models.ManyToManyField('referentiel.Groupe', related_name='sessions_quiz', blank=True)
    etudiants = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='sessions_rattrapage', blank=True)
    tentatives_supplementaires = models.PositiveSmallIntegerField(default=1, validators=[MaxValueValidator(10)])
    cree_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                 related_name='sessions_quiz_creees')
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Session de quiz"
        verbose_name_plural = "Sessions de quiz"
        ordering = ['ouverture', 'id']

    def __str__(self):
        return f"{self.quiz} : {self.libelle or self.get_type_display()}"

    @property
    def etablissement(self):
        return self.quiz.etablissement
