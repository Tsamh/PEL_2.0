from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'email', 'first_name', 'last_name', 'role', 'etablissement', 'is_active', 'is_invited']
    list_filter = ['role', 'is_active', 'is_invited', 'etablissement']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Informations PEL', {'fields': ('role', 'etablissement', 'telephone', 'matricule', 'must_change_password', 'is_invited', 'invited_by', 'date_invitation')}),
    )
