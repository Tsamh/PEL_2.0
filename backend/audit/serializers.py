from rest_framework import serializers

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    acteur_nom = serializers.SerializerMethodField()
    action_libelle = serializers.CharField(source='get_action_display', read_only=True)
    etablissement_nom = serializers.CharField(source='etablissement.nom', read_only=True, default=None)

    class Meta:
        model = AuditLog
        fields = [
            'id', 'date', 'action', 'action_libelle', 'acteur', 'acteur_nom', 'role_acteur',
            'etablissement', 'etablissement_nom', 'cible_type', 'cible_id', 'cible_repr',
            'details', 'ip',
        ]
        read_only_fields = fields

    def get_acteur_nom(self, obj):
        if obj.acteur is None:
            return None
        return obj.acteur.get_full_name() or obj.acteur.username
