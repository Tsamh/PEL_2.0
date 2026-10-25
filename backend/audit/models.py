from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    ACTION_CHOICES = [
        ('login_succes', 'Connexion réussie'),
        ('login_echec', 'Échec de connexion'),
        ('invitation', 'Invitation'),
        ('validation_admin', 'Validation administrateur'),
        ('rejet_admin', 'Rejet administrateur'),
        ('desactivation', 'Désactivation de compte'),
        ('reactivation', 'Réactivation de compte'),
        ('suppression_compte', 'Suppression de compte'),
        ('inscription', 'Inscription'),
        ('affectation', 'Affectation'),
        ('retrait_affectation', "Retrait d'affectation"),
        ('publication_evaluation', "Publication d'évaluation"),
        ('suppression_evaluation', "Suppression d'évaluation"),
        ('saisie_note', 'Saisie de note'),
        ('modification_note', 'Modification de note'),
        ('export', 'Export'),
        ('demarrage_quiz', 'Démarrage de quiz'),
        ('soumission_quiz', 'Soumission de quiz'),
        ('validation_reponse', 'Validation de réponse'),
        ('publication_resultats', 'Publication des résultats'),
        ('affectation_quiz', 'Affectation de quiz'),
        ('code_acces_quiz', "Code d'accès de quiz"),
        ('echec_code_acces', "Essais de code d'accès épuisés"),
        ('membre_groupe', 'Ajout à un groupe'),
        ('retrait_membre_groupe', "Retrait d'un groupe"),
        ('creation_question_banque', 'Création de question (banque)'),
        ('version_question_banque', 'Nouvelle version de question (banque)'),
        ('archivage_question_banque', 'Archivage de question (banque)'),
        ('import_banque', 'Import de la banque de questions'),
        ('session_quiz', 'Session de quiz'),
        ('soumission_validation', 'Soumission pour validation'),
        ('validation_quiz', 'Validation de quiz'),
        ('refus_quiz', 'Refus de quiz'),
        ('parametres_etablissement', "Paramètres de l'établissement"),
    ]

    acteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='actions_auditees')
    role_acteur = models.CharField(max_length=30, blank=True)
    etablissement = models.ForeignKey('referentiel.Etablissement', on_delete=models.SET_NULL, null=True, blank=True, related_name='journal_audit')
    action = models.CharField(max_length=40, choices=ACTION_CHOICES, db_index=True)
    cible_type = models.CharField(max_length=50, blank=True)
    cible_id = models.CharField(max_length=50, blank=True)
    cible_repr = models.CharField(max_length=255, blank=True)
    details = models.JSONField(default=dict, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    date = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Entrée du journal d'audit"
        verbose_name_plural = "Journal d'audit"
        ordering = ['-date']

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("Le journal d'audit est en lecture seule.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Le journal d'audit est en lecture seule.")

    def __str__(self):
        return f"{self.date:%Y-%m-%d %H:%M} {self.action} {self.cible_repr}"
