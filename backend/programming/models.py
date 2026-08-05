from django.db import models
from django.conf import settings


class Devoir(models.Model):
    LANGAGE_CHOICES = [
        ('python', 'Python'),
        ('java', 'Java'),
        ('c', 'C'),
        ('cpp', 'C++'),
        ('javascript', 'JavaScript'),
        ('autre', 'Autre'),
    ]
    titre = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    filiere = models.ForeignKey('referentiel.Filiere', on_delete=models.CASCADE, related_name='devoirs', null=True, blank=True)
    niveau = models.ForeignKey('referentiel.Niveau', on_delete=models.SET_NULL, null=True, blank=True)
    annee_academique = models.ForeignKey('referentiel.AnneeAcademique', on_delete=models.SET_NULL, null=True, blank=True)
    ec = models.ForeignKey('referentiel.EC', on_delete=models.SET_NULL, null=True, blank=True, related_name='devoirs', help_text="Matière associée")
    langage = models.CharField(max_length=20, choices=LANGAGE_CHOICES, default='python')
    code_initial = models.TextField(blank=True, help_text="Code fourni aux étudiants")
    solution = models.TextField(blank=True, help_text="Solution de référence")
    test_cases = models.JSONField(default=list, blank=True, help_text="Liste de tests : [{input, expected_output}]")
    date_debut = models.DateTimeField(null=True, blank=True)
    date_fin = models.DateTimeField(null=True, blank=True)
    points_max = models.PositiveIntegerField(default=20)
    est_publie = models.BooleanField(default=False)
    cree_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='devoirs_crees')
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Devoir de programmation"
        verbose_name_plural = "Devoirs de programmation"
        ordering = ['-date_creation']

    def __str__(self):
        return self.titre


class SoumissionDevoir(models.Model):
    STATUT_CHOICES = [
        ('soumis', 'Soumis'),
        ('corrige', 'Corrigé'),
    ]
    devoir = models.ForeignKey(Devoir, on_delete=models.CASCADE, related_name='soumissions')
    etudiant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='soumissions_devoirs')
    code_soumis = models.TextField()
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
