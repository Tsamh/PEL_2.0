from django.db import transaction
from django.http import HttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import SAFE_METHODS
from rest_framework.response import Response

from accounts.permissions import CREATEURS, RolePermission
from accounts.scoping import en_entier, verifier_references_evaluation
from audit.services import log as audit_log
from referentiel.models import EC

from . import banque_csv
from .banque import ENTIER_MAX, contenu_version, creer_version, filtrer_banque, peut_modifier, q_banque_visible
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
        if self.action in ('list', 'export'):
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
        archivee_avant = serializer.instance.archivee
        fiche = serializer.save()
        if fiche.archivee != archivee_avant:
            audit_log(self.request, 'archivage_question_banque', cible=fiche, details={'archivee': fiche.archivee})
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
        if fiche.archivee:
            return
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

    def _csv(self, contenu, nom):
        reponse = HttpResponse(contenu, content_type='text/csv; charset=utf-8')
        reponse['Content-Disposition'] = f'attachment; filename="{nom}"'
        return reponse

    @action(detail=False, methods=['get'])
    def export(self, request):
        fiches = self.get_queryset()
        ids = request.query_params.get('ids')
        if ids:
            entiers = [en_entier(x.strip()) for x in ids.split(',')]
            fiches = fiches.filter(pk__in=[i for i in entiers if i is not None and 1 <= i <= ENTIER_MAX])
        audit_log(request, 'export', details={'type': 'banque_questions'})
        return self._csv(banque_csv.exporter(fiches), 'banque_questions.csv')

    @action(detail=False, methods=['get'])
    def modele(self, request):
        return self._csv(banque_csv.modele(), 'modele_banque_questions.csv')

    @action(detail=False, methods=['post'], url_path='import', parser_classes=[MultiPartParser, FormParser])
    def importer(self, request):
        fichier = request.FILES.get('fichier')
        if fichier is None:
            raise ValidationError({'fichier': ["Joignez un fichier CSV."]})
        ec = None
        if request.data.get('ec'):
            identifiant = en_entier(request.data.get('ec'))
            ec = EC.objects.filter(pk=identifiant).first() if identifiant and identifiant <= ENTIER_MAX else None
            if ec is None:
                raise ValidationError({'ec': ["Cette matière n'existe pas."]})
            verifier_references_evaluation(request.user, {'ec': ec})
        try:
            lignes = banque_csv.lire_lignes(fichier)
        except banque_csv.ErreurFichier as erreur:
            raise ValidationError({'fichier': [str(erreur)]})
        rapport, valides = [], []
        for numero, ligne in lignes:
            donnees, erreurs = banque_csv.vers_donnees(ligne)
            if ec is not None:
                donnees['ec'] = ec.pk
            if not erreurs:
                serializer = self.get_serializer(data=donnees)
                if serializer.is_valid():
                    valides.append(serializer)
                else:
                    erreurs = banque_csv.aplatir(serializer.errors)
            rapport.append({'ligne': numero, 'ok': not erreurs, 'erreurs': erreurs,
                            'resume': donnees['contenu']['texte'][:80]})
        corps = {'lignes': rapport, 'valides': len(valides), 'invalides': len(rapport) - len(valides)}
        if request.data.get('apercu') == '1':
            return Response(corps)
        if corps['invalides']:
            return Response(corps, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            for serializer in valides:
                serializer.save()
        audit_log(request, 'import_banque', details={'crees': len(valides)})
        return Response({'crees': len(valides)}, status=status.HTTP_201_CREATED)
