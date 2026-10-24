from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import SAFE_METHODS
from rest_framework.response import Response

from accounts.permissions import CREATEURS, RolePermission
from accounts.scoping import en_entier
from audit.services import log as audit_log

from .banque import contenu_version, creer_version, filtrer_banque, peut_modifier, q_banque_visible
from .models import QuestionBanque, TagQuestion
from .serializers_banque import QuestionBanqueSerializer, TagSerializer, VersionSerializer

TAGS_AUTOCOMPLETION = 20
TAGS_MAX = 200


class QuestionBanqueViewSet(viewsets.ModelViewSet):
    queryset = QuestionBanque.objects.all()
    serializer_class = QuestionBanqueSerializer
    permission_classes = [RolePermission(read=CREATEURS, write=CREATEURS)]

    def get_queryset(self):
        user = self.request.user
        qs = (
            QuestionBanque.objects.filter(q_banque_visible(user))
            .select_related('auteur', 'ec').prefetch_related('tags', 'versions__creee_par')
            .order_by('-date_creation', '-id')
        )
        if self.action == 'list':
            qs = filtrer_banque(qs, self.request.query_params, user)
        return qs

    def get_object(self):
        fiche = super().get_object()
        if self.request.method not in SAFE_METHODS and not peut_modifier(self.request.user, fiche):
            raise PermissionDenied("Seuls l'auteur et la gestion peuvent modifier cette question.")
        return fiche

    def _relire(self, fiche):
        return self.get_serializer(self.get_queryset().get(pk=fiche.pk)).data

    def perform_create(self, serializer):
        fiche = serializer.save()
        audit_log(self.request, 'creation_question_banque', cible=fiche, details={'numero': 1})

    def perform_update(self, serializer):
        fiche = serializer.save()
        if serializer.version_creee is not None:
            audit_log(self.request, 'version_question_banque', cible=fiche,
                      details={'numero': serializer.version_creee.numero})

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(self._relire(serializer.instance), status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        fiche = self.get_object()
        serializer = self.get_serializer(fiche, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(self._relire(fiche))

    def perform_destroy(self, fiche):
        fiche.archivee = True
        fiche.save(update_fields=['archivee'])
        audit_log(self.request, 'archivage_question_banque', cible=fiche)

    @action(detail=True, methods=['get'])
    def versions(self, request, pk=None):
        fiche = self.get_object()
        return Response(VersionSerializer(fiche.versions.select_related('creee_par').order_by('-numero'), many=True).data)

    @action(detail=True, methods=['post'])
    def restaurer(self, request, pk=None):
        fiche = self.get_object()
        numero = en_entier(request.data.get('numero')) if isinstance(request.data, dict) else None
        ancienne = fiche.versions.filter(numero=numero).first() if numero is not None and numero < 2 ** 31 else None
        if ancienne is None:
            raise ValidationError({'numero': ["Cette version n'existe pas."]})
        version, creee = creer_version(fiche, contenu_version(ancienne), request.user)
        if creee:
            audit_log(request, 'version_question_banque', cible=fiche, details={'numero': version.numero})
        return Response(self._relire(fiche))

    @action(detail=False, methods=['get'])
    def tags(self, request):
        tags = TagQuestion.objects.filter(etablissement_id=request.user.etablissement_id)
        type_tag = request.query_params.get('type')
        if type_tag in (TagQuestion.CHAPITRE, TagQuestion.COMPETENCE):
            tags = tags.filter(type=type_tag)
        recherche = (request.query_params.get('q') or '').strip()
        if recherche:
            tags = tags.filter(libelle__icontains=recherche)[:TAGS_AUTOCOMPLETION]
        else:
            tags = tags[:TAGS_MAX]
        return Response(TagSerializer(tags, many=True).data)
