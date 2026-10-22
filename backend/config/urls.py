from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/accounts/', include('accounts.urls')),
    path('api/referentiel/', include('referentiel.urls')),
    path('api/quiz/', include('quiz.urls')),
    path('api/programming/', include('programming.urls')),
    path('api/reporting/', include('reporting.urls')),
    path('api/audit/', include('audit.urls')),
]
