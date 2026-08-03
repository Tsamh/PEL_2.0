import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    ROLE_CHOICES = [
        ('superadmin', 'Super Administrateur'),
        ('admin', 'Administrateur établissement'),
        ('responsable_formation', 'Responsable de formation'),
        ('enseignant', 'Enseignant'),
        ('etudiant', 'Étudiant'),
    ]

    role = models.CharField(max_length=30, choices=ROLE_CHOICES, default='etudiant')
    etablissement = models.ForeignKey('referentiel.Etablissement', on_delete=models.CASCADE, null=True, blank=True, related_name='utilisateurs')
    telephone = models.CharField(max_length=20, blank=True)
    matricule = models.CharField(max_length=50, blank=True, null=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    must_change_password = models.BooleanField(default=False)
    invitation_token = models.UUIDField(default=uuid.uuid4, null=True, blank=True)
    invited_by = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='invites')
    date_invitation = models.DateTimeField(null=True, blank=True)
    is_invited = models.BooleanField(default=False)
    is_validated = models.BooleanField(default=True)
    validation_status = models.CharField(max_length=20, choices=[
        ('pending', 'En attente'),
        ('approved', 'Approuvé'),
        ('rejected', 'Rejeté'),
    ], default='approved')
    rejection_reason = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Utilisateur'
        verbose_name_plural = 'Utilisateurs'

    def __str__(self):
        return f"{self.get_full_name()} ({self.role})"
