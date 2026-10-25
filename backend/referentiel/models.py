from django.db import models


class Etablissement(models.Model):
    code = models.CharField(max_length=20, unique=True)
    nom = models.CharField(max_length=200)
    sigle = models.CharField(max_length=30, blank=True)
    adresse = models.TextField(blank=True)
    telephone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    site_web = models.URLField(blank=True)
    logo = models.ImageField(upload_to='logos/', blank=True, null=True)
    validation_quiz_requise = models.BooleanField(default=False)
    date_creation = models.DateField(auto_now_add=True)

    class Meta:
        verbose_name = "Établissement"
        verbose_name_plural = "Établissements"

    def __str__(self):
        return self.nom


class AnneeAcademique(models.Model):
    libelle = models.CharField(max_length=20, unique=True)
    date_debut = models.DateField()
    date_fin = models.DateField()
    est_active = models.BooleanField(default=False)
    etablissement = models.ForeignKey(Etablissement, on_delete=models.CASCADE, null=True, blank=True, related_name='annees_academiques')

    class Meta:
        verbose_name = "Année académique"
        verbose_name_plural = "Années académiques"
        ordering = ['-date_debut']

    def __str__(self):
        return self.libelle


class Filiere(models.Model):
    code = models.CharField(max_length=20, unique=True)
    libelle = models.CharField(max_length=200)
    etablissement = models.ForeignKey(Etablissement, on_delete=models.CASCADE, related_name='filieres', null=True, blank=True)
    description = models.TextField(blank=True)

    class Meta:
        verbose_name = "Filière"
        verbose_name_plural = "Filières"

    def __str__(self):
        return self.libelle


class Niveau(models.Model):
    code = models.CharField(max_length=10, unique=True)
    libelle = models.CharField(max_length=100)

    class Meta:
        verbose_name = "Niveau"
        verbose_name_plural = "Niveaux"

    def __str__(self):
        return self.libelle


class UE(models.Model):
    code = models.CharField(max_length=20, unique=True)
    libelle = models.CharField(max_length=200)
    filiere = models.ForeignKey(Filiere, on_delete=models.CASCADE, related_name='ues')
    niveau = models.ForeignKey(Niveau, on_delete=models.CASCADE, related_name='ues')
    credits = models.PositiveIntegerField(default=0)
    coefficient = models.DecimalField(max_digits=4, decimal_places=2, default=1)

    class Meta:
        verbose_name = "Unité d'enseignement"
        verbose_name_plural = "Unités d'enseignement"

    def __str__(self):
        return f"{self.code} - {self.libelle}"


class EC(models.Model):
    code = models.CharField(max_length=20, unique=True)
    libelle = models.CharField(max_length=200)
    ue = models.ForeignKey(UE, on_delete=models.CASCADE, related_name='ecs')
    volume_horaire = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Enseignement composable"
        verbose_name_plural = "Enseignements composable"

    def __str__(self):
        return f"{self.code} - {self.libelle}"


class Cours(models.Model):
    titre = models.CharField(max_length=200)
    ec = models.ForeignKey(EC, on_delete=models.CASCADE, related_name='cours')
    description = models.TextField(blank=True)

    class Meta:
        verbose_name = "Cours"
        verbose_name_plural = "Cours"

    def __str__(self):
        return self.titre


class Classe(models.Model):
    code = models.CharField(max_length=20, unique=True)
    libelle = models.CharField(max_length=200)
    filiere = models.ForeignKey(Filiere, on_delete=models.CASCADE, related_name='classes')
    niveau = models.ForeignKey(Niveau, on_delete=models.CASCADE, related_name='classes')
    annee_academique = models.ForeignKey(AnneeAcademique, on_delete=models.CASCADE, related_name='classes')
    effectif_max = models.PositiveIntegerField(default=60)

    class Meta:
        verbose_name = "Classe"
        verbose_name_plural = "Classes"

    def __str__(self):
        return f"{self.code} - {self.libelle}"


class Groupe(models.Model):
    TYPE_CHOICES = [
        ('td', 'Travaux Dirigés'),
        ('tp', 'Travaux Pratiques'),
    ]
    code = models.CharField(max_length=20, unique=True)
    libelle = models.CharField(max_length=200)
    classe = models.ForeignKey(Classe, on_delete=models.CASCADE, related_name='groupes')
    type_groupe = models.CharField(max_length=2, choices=TYPE_CHOICES, default='td')
    membres = models.ManyToManyField('accounts.User', related_name='groupes', blank=True)

    class Meta:
        verbose_name = "Groupe"
        verbose_name_plural = "Groupes"

    def __str__(self):
        return self.libelle


class Inscription(models.Model):
    etudiant = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='inscriptions')
    classe = models.ForeignKey(Classe, on_delete=models.CASCADE, related_name='inscriptions')
    date_inscription = models.DateField(auto_now_add=True)
    est_validee = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Inscription"
        verbose_name_plural = "Inscriptions"
        unique_together = ['etudiant', 'classe']

    def __str__(self):
        return f"{self.etudiant} - {self.classe}"


class EnseignantMatiere(models.Model):
    enseignant = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='matieres_enseignees')
    ec = models.ForeignKey(EC, on_delete=models.CASCADE, related_name='enseignants')
    classe = models.ForeignKey(Classe, on_delete=models.CASCADE, related_name='enseignants_matieres')

    class Meta:
        verbose_name = "Affectation enseignant"
        verbose_name_plural = "Affectations enseignants"
        unique_together = ['enseignant', 'ec', 'classe']


class AffectationEnseignant(models.Model):
    enseignant = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='affectations_classes')
    classe = models.ForeignKey(Classe, on_delete=models.CASCADE, related_name='affectations_enseignants')
    date_affectation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Affectation enseignant-classe"
        verbose_name_plural = "Affectations enseignant-classe"
        unique_together = ['enseignant', 'classe']

    def __str__(self):
        return f"{self.enseignant} -> {self.classe}"


class Semestre(models.Model):
    annee_academique = models.ForeignKey(AnneeAcademique, on_delete=models.CASCADE, related_name='semestres')
    libelle = models.CharField(max_length=50)
    date_debut = models.DateField()
    date_fin = models.DateField()

    class Meta:
        verbose_name = "Semestre"
        verbose_name_plural = "Semestres"
        ordering = ['date_debut', 'id']
        unique_together = ['annee_academique', 'libelle']

    def __str__(self):
        return f"{self.libelle} ({self.annee_academique})"


class PeriodeEvaluation(models.Model):
    CONTROLE_CONTINU = 'controle_continu'
    EXAMEN = 'examen'
    RATTRAPAGE = 'rattrapage'
    TYPE_CHOICES = [(CONTROLE_CONTINU, 'Contrôle continu'), (EXAMEN, 'Examen'), (RATTRAPAGE, 'Rattrapage')]

    semestre = models.ForeignKey(Semestre, on_delete=models.CASCADE, related_name='periodes')
    libelle = models.CharField(max_length=100)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=CONTROLE_CONTINU)
    date_debut = models.DateField()
    date_fin = models.DateField()

    class Meta:
        verbose_name = "Période d'évaluation"
        verbose_name_plural = "Périodes d'évaluation"
        ordering = ['date_debut', 'id']

    def __str__(self):
        return self.libelle
