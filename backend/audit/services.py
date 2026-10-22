import logging

from django.db import transaction

from .models import AuditLog

logger = logging.getLogger(__name__)


def _ip(request):
    if request is None:
        return None
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def log(request, action, cible=None, details=None, acteur=None, etablissement=None):
    """Écrit une entrée du journal. Ne lève jamais : un échec est logué côté serveur."""
    try:
        if acteur is None:
            user = getattr(request, 'user', None)
            acteur = user if user is not None and user.is_authenticated else None
        if etablissement is None and cible is not None:
            etablissement = getattr(cible, 'etablissement', None)
        if etablissement is None and acteur is not None:
            etablissement = acteur.etablissement
        with transaction.atomic():
            return AuditLog.objects.create(
                acteur=acteur,
                role_acteur=getattr(acteur, 'role', '') or '',
                etablissement=etablissement,
                action=action,
                cible_type=cible._meta.model_name if cible is not None else '',
                cible_id=str(cible.pk) if cible is not None else '',
                cible_repr=str(cible)[:255] if cible is not None else '',
                details=details or {},
                ip=_ip(request),
            )
    except Exception:
        logger.exception("Échec d'écriture du journal d'audit (%s)", action)
        return None
