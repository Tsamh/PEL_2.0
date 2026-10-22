from rest_framework.routers import SimpleRouter

from .views import AuditLogViewSet

router = SimpleRouter()
router.register(r'', AuditLogViewSet, basename='audit')

urlpatterns = router.urls
