from django.contrib import admin

from .models import CasDeTest, Devoir, Exercice, NoteMatiere, ReponseExercice, SessionDevoir, SoumissionDevoir


class ExerciceInline(admin.StackedInline):
    model = Exercice
    extra = 0


class CasDeTestInline(admin.TabularInline):
    model = CasDeTest
    extra = 0


class ReponseExerciceInline(admin.StackedInline):
    model = ReponseExercice
    extra = 0


@admin.register(Devoir)
class DevoirAdmin(admin.ModelAdmin):
    list_display = ('titre', 'langage', 'filiere', 'est_publie', 'statut_validation', 'date_creation')
    list_filter = ('langage', 'est_publie', 'statut_validation')
    search_fields = ('titre',)
    inlines = [ExerciceInline]


@admin.register(Exercice)
class ExerciceAdmin(admin.ModelAdmin):
    list_display = ('titre', 'devoir', 'ordre', 'points', 'difficulte')
    search_fields = ('titre', 'devoir__titre')
    inlines = [CasDeTestInline]


@admin.register(SessionDevoir)
class SessionDevoirAdmin(admin.ModelAdmin):
    list_display = ('devoir', 'type', 'libelle', 'ouverture', 'fermeture')
    list_filter = ('type',)


@admin.register(SoumissionDevoir)
class SoumissionDevoirAdmin(admin.ModelAdmin):
    list_display = ('devoir', 'etudiant', 'statut', 'score', 'date_soumission')
    list_filter = ('statut',)
    inlines = [ReponseExerciceInline]


admin.site.register(CasDeTest)
admin.site.register(NoteMatiere)
