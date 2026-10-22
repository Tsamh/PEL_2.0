from django.utils.dateparse import parse_date
from rest_framework import viewsets

from accounts.permissions import IsAdmin, SUPERADMIN
from .models import AuditLog
from .serializers import AuditLogSerializer


def _date(valeur):
    """Date AAAA-MM-JJ, ou None si absente ou invalide (le filtre est alors ignoré)."""
    try:
        return parse_date(valeur or '')
    except ValueError:
        return None


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AuditLogSerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        user = self.request.user
        qs = AuditLog.objects.select_related('acteur', 'etablissement')
        if user.role != SUPERADMIN:
            if not user.etablissement_id:
                return qs.none()
            qs = qs.filter(etablissement_id=user.etablissement_id)

        params = self.request.query_params
        if params.get('action'):
            qs = qs.filter(action=params['action'])
        if params.get('acteur'):
            qs = qs.filter(acteur_id=params['acteur'])
        date_debut = _date(params.get('date_debut'))
        if date_debut:
            qs = qs.filter(date__date__gte=date_debut)
        date_fin = _date(params.get('date_fin'))
        if date_fin:
            qs = qs.filter(date__date__lte=date_fin)
        return qs
