"""Accusé de réception d'une soumission de devoir : date, version, jamais de note ni de résultat."""
import logging

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

logger = logging.getLogger('programming')


def envoyer_accuse(soumission):
    """Envoie l'accusé à l'étudiant (rien sans e-mail) ; n'échoue jamais : la soumission est déjà enregistrée."""
    try:
        etudiant = soumission.etudiant
        if not etudiant.email:
            return
        titre = soumission.devoir.titre
        quand = timezone.localtime(soumission.date_soumission).strftime('%d/%m/%Y à %H:%M')
        lignes = [
            f"Bonjour {etudiant.get_full_name() or etudiant.username},",
            "",
            f"Nous confirmons la réception de votre devoir « {titre} », soumis le {quand}.",
        ]
        if soumission.numero_version > 1:
            lignes.append(f"Il s'agit de la version n°{soumission.numero_version}.")
        if soumission.soumission_auto:
            lignes.append("Il a été soumis automatiquement à la fermeture, avec votre dernier enregistrement.")
        lignes += ["", "L'équipe PEL"]
        send_mail(f"Accusé de réception : {titre}", "\n".join(lignes),
                  settings.DEFAULT_FROM_EMAIL, [etudiant.email], fail_silently=True)
    except Exception:  # noqa: BLE001 : un échec d'envoi ne doit pas défaire une soumission validée
        logger.exception("Accusé de réception non envoyé (soumission %s)", getattr(soumission, 'pk', None))
