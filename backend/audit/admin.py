from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ['date', 'action', 'acteur', 'role_acteur', 'etablissement', 'cible_repr', 'ip']
    list_filter = ['action', 'etablissement']
    search_fields = ['cible_repr', 'acteur__username', 'acteur__email']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
