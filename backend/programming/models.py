from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

EXTENSIONS = {'python': 'py', 'javascript': 'js', 'c': 'c', 'cpp': 'cpp', 'java': 'java', 'autre': 'txt'}


class Devoir(models.Model):
    LANGAGE_CHOICES = [
        ('python', 'Python'),
        ('java', 'Java'),
        ('c', 'C'),
        ('cpp', 'C++'),
        ('javascript', 'JavaScript'),
        ('autre', 'Autre'),
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
    objectifs = models.TextField(blank=True, default='')
    consignes = models.TextField(blank=True, default='')
    ressources = models.JSONField(default=list, blank=True, help_text="Liens : [{libelle, url}]")
    filiere = models.ForeignKey('referentiel.Filiere', on_delete=models.CASCADE, related_name='devoirs', null=True, blank=True)
    niveau = models.ForeignKey('referentiel.Niveau', on_delete=models.SET_NULL, null=True, blank=True)
    annee_academique = models.ForeignKey('referentiel.AnneeAcademique', on_delete=models.SET_NULL, null=True, blank=True)
    periode = models.ForeignKey('referentiel.PeriodeEvaluation', on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='devoirs')
    ec = models.ForeignKey('referentiel.EC', on_delete=models.SET_NULL, null=True, blank=True, related_name='devoirs', help_text="Matière associée")
    langage = models.CharField(max_length=20, choices=LANGAGE_CHOICES, default='python')
    date_debut = models.DateTimeField(null=True, blank=True)
    date_fin = models.DateTimeField(null=True, blank=True)
    est_publie = models.BooleanField(default=False)
    statut_validation = models.CharField(max_length=12, choices=STATUT_VALIDATION_CHOICES, default=BROUILLON)
    motif_refus = models.TextField(blank=True, default='')
    soumis_le = models.DateTimeField(null=True, blank=True)
    valide_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='devoirs_valides')
    valide_le = models.DateTimeField(null=True, blank=True)
    classes = models.ManyToManyField('referentiel.Classe', related_name='devoirs_affectes', blank=True)
    groupes = models.ManyToManyField('referentiel.Groupe', related_name='devoirs_affectes', blank=True)
    etudiants = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='devoirs_affectes', blank=True)
    cree_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='devoirs_crees')
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Devoir de programmation"
        verbose_name_plural = "Devoirs de programmation"
        ordering = ['-date_creation']

    def __str__(self):
        return self.titre

    @property
    def bareme(self):
        """Somme des points des exercices (zéro sans exercice)."""
        if self.pk is None:
            return Decimal('0')
        return sum((e.points for e in self.exercices.all()), Decimal('0'))

    @property
    def etablissement(self):
        """Établissement de la filière, ou du créateur si le devoir n'a pas de filière."""
        if self.filiere_id:
            return self.filiere.etablissement
        return getattr(self.cree_par, 'etablissement', None)


class Exercice(models.Model):
    FACILE = 'facile'
    MOYEN = 'moyen'
    DIFFICILE = 'difficile'
    DIFFICULTE_CHOICES = [
        (FACILE, 'Facile'),
        (MOYEN, 'Moyen'),
        (DIFFICILE, 'Difficile'),
    ]

    devoir = models.ForeignKey(Devoir, on_delete=models.CASCADE, related_name='exercices')
    ordre = models.PositiveIntegerField(default=0)
    titre = models.CharField(max_length=200)
    enonce = models.TextField(blank=True, default='')
    contraintes = models.TextField(blank=True, default='')
    exemples = models.JSONField(default=list, blank=True, help_text="Exemples : [{entree, sortie, explication}]")
    fichiers_initiaux = models.JSONField(default=list, blank=True, help_text="Fichiers de départ : [{nom, contenu}]")
    solution = models.JSONField(default=list, blank=True, help_text="Solution de référence : [{nom, contenu}]")
    points = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('1'),
                                 validators=[MinValueValidator(Decimal('0.01'))])
    difficulte = models.CharField(max_length=10, choices=DIFFICULTE_CHOICES, default=MOYEN)
    competences = models.ManyToManyField('quiz.TagQuestion', related_name='exercices', blank=True,
                                         limit_choices_to={'type': 'competence'})

    class Meta:
        verbose_name = "Exercice"
        verbose_name_plural = "Exercices"
        ordering = ['ordre', 'id']

    def __str__(self):
        return self.titre


class CasDeTest(models.Model):
    exercice = models.ForeignKey(Exercice, on_delete=models.CASCADE, related_name='tests')
    ordre = models.PositiveIntegerField(default=0)
    entree = models.TextField(blank=True, default='')
    sortie_attendue = models.TextField(blank=True, default='')
    public = models.BooleanField(default=False)
    poids = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])

    class Meta:
        verbose_name = "Cas de test"
        verbose_name_plural = "Cas de test"
        ordering = ['ordre', 'id']

    def __str__(self):
        return f"{self.exercice} : test {self.ordre}"


class SessionDevoir(models.Model):
    NORMALE = 'normale'
    RATTRAPAGE = 'rattrapage'
    TYPE_CHOICES = [(NORMALE, 'Session'), (RATTRAPAGE, 'Rattrapage')]

    devoir = models.ForeignKey(Devoir, on_delete=models.CASCADE, related_name='sessions')
    type = models.CharField(max_length=12, choices=TYPE_CHOICES, default=NORMALE)
    libelle = models.CharField(max_length=100, blank=True, default='')
    ouverture = models.DateTimeField()
    fermeture = models.DateTimeField()
    periode = models.ForeignKey('referentiel.PeriodeEvaluation', on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='sessions_devoir')
    classes = models.ManyToManyField('referentiel.Classe', related_name='sessions_devoir', blank=True)
    groupes = models.ManyToManyField('referentiel.Groupe', related_name='sessions_devoir', blank=True)
    etudiants = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='sessions_rattrapage_devoir', blank=True)
    cree_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                 related_name='sessions_devoir_creees')
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Session de devoir"
        verbose_name_plural = "Sessions de devoirs"
        ordering = ['ouverture', 'id']

    def __str__(self):
        return f"{self.devoir} : {self.libelle or self.get_type_display()}"

    @property
    def etablissement(self):
        return self.devoir.etablissement


class SoumissionDevoir(models.Model):
    STATUT_CHOICES = [
        ('soumis', 'Soumis'),
        ('corrige', 'Corrigé'),
    ]
    devoir = models.ForeignKey(Devoir, on_delete=models.CASCADE, related_name='soumissions')
    etudiant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='soumissions_devoirs')
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='soumis')
    score = models.PositiveIntegerField(null=True, blank=True)
    commentaire = models.TextField(blank=True)
    date_soumission = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Soumission de devoir"
        verbose_name_plural = "Soumissions de devoirs"
        unique_together = ('devoir', 'etudiant')
        ordering = ['-date_soumission']

    def __str__(self):
        return f"{self.etudiant} - {self.devoir}"


class ReponseExercice(models.Model):
    soumission = models.ForeignKey(SoumissionDevoir, on_delete=models.CASCADE, related_name='reponses')
    exercice = models.ForeignKey(Exercice, on_delete=models.CASCADE, related_name='reponses')
    fichiers = models.JSONField(default=list, blank=True, help_text="Fichiers rendus : [{nom, contenu}]")

    class Meta:
        verbose_name = "Réponse à un exercice"
        verbose_name_plural = "Réponses aux exercices"
        ordering = ['exercice__ordre', 'exercice_id']
        constraints = [
            models.UniqueConstraint(fields=['soumission', 'exercice'], name='reponse_exercice_unique'),
        ]

    def __str__(self):
        return f"{self.soumission} : {self.exercice}"


class NoteMatiere(models.Model):
    etudiant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notes_matieres')
    ec = models.ForeignKey('referentiel.EC', on_delete=models.CASCADE, related_name='notes')
    classe = models.ForeignKey('referentiel.Classe', on_delete=models.CASCADE, related_name='notes')
    annee_academique = models.ForeignKey('referentiel.AnneeAcademique', on_delete=models.CASCADE, related_name='notes')
    note_devoir = models.FloatField(null=True, blank=True, help_text="Note sur 20 - Pondération 40%")
    note_examen = models.FloatField(null=True, blank=True, help_text="Note sur 20 - Pondération 60%")
    moyenne = models.FloatField(null=True, blank=True, help_text="Moyenne calculée: devoir*0.4 + examen*0.6")
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Note matière"
        verbose_name_plural = "Notes matières"
        unique_together = ('etudiant', 'ec', 'classe', 'annee_academique')
        ordering = ['-date_modification']

    def calculer_moyenne(self):
        if self.note_devoir is not None and self.note_examen is not None:
            self.moyenne = round(self.note_devoir * 0.4 + self.note_examen * 0.6, 2)
        elif self.note_devoir is not None:
            self.moyenne = round(self.note_devoir * 0.4, 2)
        elif self.note_examen is not None:
            self.moyenne = round(self.note_examen * 0.6, 2)
        else:
            self.moyenne = None
        return self.moyenne

    def save(self, *args, **kwargs):
        self.calculer_moyenne()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.etudiant} - {self.ec} ({self.moyenne or '-'}/20)"
