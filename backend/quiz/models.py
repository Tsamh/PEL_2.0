from django.db import models
from django.conf import settings


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
    titre = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    filiere = models.ForeignKey('referentiel.Filiere', on_delete=models.CASCADE, related_name='quizzes', null=True, blank=True)
    niveau = models.ForeignKey('referentiel.Niveau', on_delete=models.SET_NULL, null=True, blank=True)
    annee_academique = models.ForeignKey('referentiel.AnneeAcademique', on_delete=models.SET_NULL, null=True, blank=True)
    duree_minutes = models.PositiveIntegerField(default=30)
    date_debut = models.DateTimeField(null=True, blank=True)
    date_fin = models.DateTimeField(null=True, blank=True)
    est_publie = models.BooleanField(default=False)
    cree_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='quizzes_crees')
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Quiz"
        verbose_name_plural = "Quiz"
        ordering = ['-date_creation']

    def __str__(self):
        return self.titre


class Question(models.Model):
    TYPE_CHOICES = [
        ('qcm', 'QCM'),
        ('vf', 'Vrai/Faux'),
        ('courte', 'Réponse courte'),
    ]
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    texte = models.TextField()
    type_question = models.CharField(max_length=10, choices=TYPE_CHOICES, default='qcm')
    points = models.PositiveIntegerField(default=1)
    ordre = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Question"
        verbose_name_plural = "Questions"
        ordering = ['ordre']

    def __str__(self):
        return self.texte[:80]


class Choix(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='choix')
    texte = models.CharField(max_length=500)
    est_correct = models.BooleanField(default=False)
    ordre = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Choix"
        verbose_name_plural = "Choix"
        ordering = ['ordre']

    def __str__(self):
        return self.texte[:80]


class ResultatQuiz(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='resultats')
    etudiant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='resultats_quiz')
    score = models.PositiveIntegerField(default=0)
    score_max = models.PositiveIntegerField(default=0)
    pourcentage = models.FloatField(default=0)
    duree_secondes = models.PositiveIntegerField(default=0)
    date_passage = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Résultat quiz"
        verbose_name_plural = "Résultats quiz"
        unique_together = ('quiz', 'etudiant')
        ordering = ['-date_passage']

    def __str__(self):
        return f"{self.etudiant} - {self.quiz} ({self.score}/{self.score_max})"


class ReponseQuiz(models.Model):
    resultat = models.ForeignKey(ResultatQuiz, on_delete=models.CASCADE, related_name='reponses')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    choix_selectionne = models.ForeignKey(Choix, on_delete=models.SET_NULL, null=True, blank=True)
    texte_reponse = models.TextField(blank=True, default='')
    est_correct = models.BooleanField(default=False)
    score_obtenu = models.PositiveIntegerField(default=0)
    similarite = models.FloatField(default=0, help_text="Score de similarité pour réponses courtes (0-1)")

    class Meta:
        verbose_name = "Réponse quiz"
        verbose_name_plural = "Réponses quiz"

    def __str__(self):
        return f"{self.question} -> {'OK' if self.est_correct else 'KO'}"
