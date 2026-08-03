from django.contrib import admin
from .models import (
    Etablissement, AnneeAcademique, Filiere, Niveau, UE, EC, Cours,
    Classe, Groupe, Inscription, EnseignantMatiere
)

admin.site.register(Etablissement)
admin.site.register(AnneeAcademique)
admin.site.register(Filiere)
admin.site.register(Niveau)
admin.site.register(UE)
admin.site.register(EC)
admin.site.register(Cours)
admin.site.register(Classe)
admin.site.register(Groupe)
admin.site.register(Inscription)
admin.site.register(EnseignantMatiere)
