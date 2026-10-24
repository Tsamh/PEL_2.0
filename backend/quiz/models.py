from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
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

    titre = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    filiere = models.ForeignKey('referentiel.Filiere', on_delete=models.CASCADE, related_name='quizzes', null=True, blank=True)
    niveau = models.ForeignKey('referentiel.Niveau', on_delete=models.SET_NULL, null=True, blank=True)
    annee_academique = models.ForeignKey('referentiel.AnneeAcademique', on_delete=models.SET_NULL, null=True, blank=True)
    duree_minutes = models.PositiveIntegerField(default=30, validators=[MinValueValidator(1)])
    date_debut = models.DateTimeField(null=True, blank=True)
    date_fin = models.DateTimeField(null=True, blank=True)
    est_publie = models.BooleanField(default=False)
    tentatives_autorisees = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    reprise_autorisee = models.BooleanField(default=True)
    publication_resultats = models.CharField(max_length=10, choices=PUBLICATION_CHOICES, default=PUBLICATION_IMMEDIATE)
    resultats_publies = models.BooleanField(default=False)
    afficher_corrige = models.BooleanField(default=False)
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
