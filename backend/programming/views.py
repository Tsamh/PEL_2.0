import math
from decimal import Decimal, ROUND_HALF_UP

from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from django.db import IntegrityError, transaction
from django.db.models import Count, Prefetch

from accounts.permissions import (
    IsEtudiant, RolePermission, CREATEURS, GESTION, TOUS_LES_ROLES, ENSEIGNANT, ETUDIANT,
)
from accounts.scoping import (
    EtablissementScopedMixin, classes_du_perimetre, classes_enseignant,
    q_evaluation_etablissement, en_entier, verifier_filiere_du_perimetre, verifier_references_evaluation,
    MESSAGE_HORS_PERIMETRE,
)
from audit.services import log as audit_log
from quiz import acces, fenetres, validation
from quiz.exceptions import Conflit
from quiz.statistiques import etudiants_affectes
from quiz.views import etablissement_evaluation
from referentiel.archives import ArchiveMixin, filtrer_archives, verifier_non_archivee
from .execution import file as file_execution
from .execution.executeur import MESSAGE_LANGAGE
from . import accuses, versions
from .models import BrouillonExercice, Devoir, Execution, ReponseExercice, ResultatTest, SoumissionDevoir, NoteMatiere
from .serializers import (
    DevoirSerializer, DevoirEtudiantSerializer, SoumissionDevoirSerializer, SoumissionDevoirEtudiantSerializer,
    SoumissionDevoirUpdateSerializer,
    NoteMatiereSerializer, valider_reponses, ATTRIBUT_CORRECTIONS, NON_AUTORISE, contient_non_stockable,
)
from .validation import PROFIL_DEVOIR
from .views_brouillons import BrouillonsMixin
from .views_execution import ACTIVES, demander_essai, langage_executable

CORRECTEURS = RolePermission(read=CREATEURS, write=CREATEURS)
MESSAGE_DEJA_SOUMIS = "Vous avez déjà soumis ce devoir."
MESSAGE_NOTE_VALIDEE = "Votre note est validée : ce devoir ne peut plus être modifié."
MESSAGE_PAS_OUVERT = "Ce devoir n'est pas ouvert."
MESSAGE_FERME = "Ce devoir est fermé."
MESSAGE_SANS_NOTE = "Aucune note proposée : indiquez un score."
MESSAGE_CORRECTION_ATTENDUE = "Une correction est en cours : attendez son résultat ou indiquez une note."
MESSAGE_DEJA_VALIDEE = "Cette soumission est déjà validée : sa correction ne peut plus être relancée."
MESSAGE_CORRECTION_EN_FILE = "Une correction est déjà en cours pour cette soumission."
MESSAGE_RIEN_A_RELANCER = "Aucune correction en erreur à relancer."


def devoirs_visibles_etudiant(user):
    """Devoirs publiés affectés à l'étudiant (classe, groupe de sa classe ou nominativement)."""
    return Devoir.objects.filter(est_publie=True).filter(acces.q_affecte(Devoir, user))


def verifier_fenetre_ouverte(devoir, etudiant):
    """409 si la fenêtre effective de l'étudiant (sessions, rattrapages) n'est pas ouverte."""
    fenetre = fenetres.fenetre(devoir, etudiant)
    if fenetre.ouverte is None:
        raise Conflit(MESSAGE_PAS_OUVERT if fenetre.prochaine_ouverture is not None else MESSAGE_FERME)


class DevoirViewSet(BrouillonsMixin, ArchiveMixin, EtablissementScopedMixin, viewsets.ModelViewSet):
    annee_path = 'annee_academique'
    queryset = (
        Devoir.objects.select_related('filiere__etablissement', 'niveau', 'annee_academique', 'cree_par__etablissement',
                                      'valide_par', 'periode', 'ec')
        .prefetch_related('classes', 'groupes__classe', 'etudiants', 'exercices__tests', 'exercices__competences')
    )
    serializer_class = DevoirSerializer
    permission_classes = [RolePermission(read=TOUS_LES_ROLES, write=CREATEURS)]

    def get_serializer_class(self):
        if self.request.user.role == ETUDIANT:
            return DevoirEtudiantSerializer
        return DevoirSerializer

    def gestion_scope(self, qs, user):
        return qs.filter(q_evaluation_etablissement(user.etablissement_id))

    def enseignant_scope(self, qs, user):
        return qs.filter(cree_par=user)

    def etudiant_scope(self, qs, user):
        return qs.filter(pk__in=devoirs_visibles_etudiant(user))

    def get_queryset(self):
        qs = super().get_queryset()
        statut = self.request.query_params.get('statut_validation')
        if statut in dict(Devoir.STATUT_VALIDATION_CHOICES):
            qs = qs.filter(statut_validation=statut)
        return qs

    @action(detail=True, methods=['post'], permission_classes=[RolePermission(write=CREATEURS)])
    def soumettre_validation(self, request, pk=None):
        devoir = self.get_object()
        self.verifier_ecriture(devoir)
        validation.soumettre(devoir, request, PROFIL_DEVOIR)
        return Response(self.get_serializer(devoir).data)

    @action(detail=True, methods=['post'], permission_classes=[RolePermission(write=GESTION)])
    def valider(self, request, pk=None):
        devoir = self.get_object()
        self.verifier_ecriture(devoir)
        validation.valider(devoir, request, PROFIL_DEVOIR)
        return Response(self.get_serializer(devoir).data)

    @action(detail=True, methods=['post'], permission_classes=[RolePermission(write=GESTION)])
    def refuser(self, request, pk=None):
        devoir = self.get_object()
        self.verifier_ecriture(devoir)
        motif = request.data.get('motif') if isinstance(request.data, dict) else None
        validation.refuser(devoir, request, motif, PROFIL_DEVOIR)
        return Response(self.get_serializer(devoir).data)

    def perform_create(self, serializer, **kwargs):
        verifier_filiere_du_perimetre(self.request.user, serializer.validated_data.get('filiere'))
        verifier_references_evaluation(self.request.user, serializer.validated_data)
        instance = super().perform_create(serializer, cree_par=self.request.user, **kwargs)
        if instance.est_publie:
            self._journaliser('publication_evaluation', instance)
        self._journaliser_affectation(acces.cibles_vides(), instance)
        return instance

    def perform_update(self, serializer, **kwargs):
        if 'filiere' in serializer.validated_data:
            verifier_filiere_du_perimetre(self.request.user, serializer.validated_data['filiere'])
        verifier_references_evaluation(self.request.user, serializer.validated_data)
        etait_publie = serializer.instance.est_publie
        avant = acces.cibles(serializer.instance)
        instance = super().perform_update(serializer, **kwargs)
        if instance.est_publie and not etait_publie:
            self._journaliser('publication_evaluation', instance)
        self._journaliser_affectation(avant, instance)
        return instance

    def perform_destroy(self, instance):
        self._journaliser('suppression_evaluation', instance)
        instance.delete()

    def _journaliser(self, action_audit, instance):
        audit_log(self.request, action_audit, cible=instance, etablissement=etablissement_evaluation(instance),
                  details={'type': 'devoir', 'titre': instance.titre})

    def _journaliser_affectation(self, avant, instance):
        details = acces.ecart_cibles(avant, acces.cibles(instance))
        if details is not None:
            audit_log(self.request, 'affectation_evaluation', cible=instance,
                      etablissement=etablissement_evaluation(instance), details={**details, 'type': 'devoir'})

    @action(detail=True, methods=['get'], permission_classes=[RolePermission(read=CREATEURS)])
    def candidats_rattrapage(self, request, pk=None):
        """Étudiants concernés (affectés ou ayant soumis) qui n'ont pas de soumission."""
        devoir = self.get_object()
        ont_soumis = set(devoir.soumissions.values_list('etudiant_id', flat=True))
        candidats = [
            {'id': e.pk, 'nom': e.get_full_name() or e.username}
            for e in etudiants_affectes(devoir) if e.pk not in ont_soumis
        ]
        return Response(sorted(candidats, key=lambda c: c['nom'].lower()))

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def executer(self, request, pk=None):
        """Essai asynchrone `{exercice, fichiers, mode: 'run'|'test', entree?}` -> 202 `{id, statut}`.

        Ordre : devoir visible (404), année archivée (409), fenêtre de l'étudiant (409), 20 demandes par minute
        (429), langage et corps (400), une exécution active par utilisateur (409).
        """
        devoir = self.get_object()
        self.verifier_ecriture(devoir)
        if request.user.role == ETUDIANT:
            verifier_fenetre_ouverte(devoir, request.user)
        execution = demander_essai(request.user, devoir, request.data)
        return Response({'id': execution.id, 'statut': execution.statut}, status=status.HTTP_202_ACCEPTED)


class SoumissionDevoirViewSet(ArchiveMixin, EtablissementScopedMixin, viewsets.ModelViewSet):
    annee_path = 'devoir__annee_academique'
    parent_params = ('devoir',)
    queryset = (
        SoumissionDevoir.objects.select_related('devoir', 'etudiant')
        .prefetch_related('devoir__exercices', 'reponses__exercice')
    )
    serializer_class = SoumissionDevoirSerializer

    def get_permissions(self):
        if self.action == 'create':
            return [IsEtudiant()]
        if self.action in ('update', 'partial_update', 'destroy', 'corriger', 'recorriger'):
            return [CORRECTEURS()]
        return super().get_permissions()

    def gestion_scope(self, qs, user):
        return qs.filter(q_evaluation_etablissement(user.etablissement_id, prefix='devoir__'))

    def enseignant_scope(self, qs, user):
        return qs.filter(devoir__cree_par=user)

    def etudiant_scope(self, qs, user):
        return qs.filter(etudiant=user)

    def get_queryset(self):
        qs = super().get_queryset()
        devoir = en_entier(self.request.query_params.get('devoir'))
        qs = qs.filter(devoir_id=devoir) if devoir is not None else qs
        # L'agrégat supprime le tri du modèle : il est répété ici.
        qs = qs.annotate(nb_versions=Count('versions', distinct=True)).order_by('-date_soumission', '-pk')
        if self.action == 'list' and self.request.user.role != ETUDIANT:
            # Liste des correcteurs : dernières corrections et statuts de leurs tests, sans les sorties.
            corrections = (Execution.objects.filter(type=Execution.CORRECTION)
                           .only('id', 'reponse_id', 'statut', 'message').order_by('-id')
                           .prefetch_related(Prefetch('resultats', queryset=ResultatTest.objects.only(
                               'id', 'execution_id', 'statut'))))
            qs = qs.prefetch_related(Prefetch('reponses__executions', queryset=corrections,
                                              to_attr=ATTRIBUT_CORRECTIONS))
        return qs

    def get_serializer_context(self):
        contexte = super().get_serializer_context()
        contexte['resume'] = self.action == 'list'
        return contexte

    def get_serializer_class(self):
        if self.action in ('update', 'partial_update'):
            return SoumissionDevoirUpdateSerializer
        if self.request.user.role == ETUDIANT:
            return SoumissionDevoirEtudiantSerializer
        return SoumissionDevoirSerializer

    def perform_destroy(self, instance):
        audit_log(
            self.request, 'modification_note', cible=instance,
            etablissement=etablissement_evaluation(instance.devoir),
            details={'type': 'soumission', 'etudiant': instance.etudiant_id,
                     'avant': {'score': instance.score}, 'apres': None},
        )
        instance.delete()

    def create(self, request, *args, **kwargs):
        """Soumission finale : `{devoir, reponses: [{exercice, fichiers: [{nom, contenu}]}]}`, une seule par devoir (resoumission
        possible si le devoir l'autorise).

        Ordre des contrôles : devoir visible (400), année archivée (409), fenêtre (409), soumission existante
        (409 : option désactivée, note validée, correction active), réponses (400) ; la soumission et ses réponses
        sont créées (ou remplacées par une nouvelle version) ensemble, devoir verrouillé, avec leurs
        corrections en file (soumission `en_correction`). Un langage que le service n'exécute pas (`autre`)
        laisse la soumission `soumis`, pour une correction manuelle.
        """
        etudiant = request.user
        donnees = request.data if isinstance(request.data, dict) else {}
        devoir_id = en_entier(donnees.get('devoir'))
        devoir = devoirs_visibles_etudiant(etudiant).filter(pk=devoir_id).first() if devoir_id is not None else None
        if devoir is None:
            raise ValidationError({'detail': "Devoir introuvable."})
        verifier_non_archivee(devoir.annee_academique)
        verifier_fenetre_ouverte(devoir, etudiant)
        existante = devoir.soumissions.filter(etudiant=etudiant).select_related('devoir').first()
        if existante is not None:
            versions.verifier_resoumission(existante)
        resoumission = False
        try:
            with transaction.atomic():
                # Verrou partagé avec la modification des exercices : ils ne changent pas pendant l'écriture.
                devoir = Devoir.objects.select_for_update().get(pk=devoir.pk)
                soumission = (SoumissionDevoir.objects.select_for_update().select_related('devoir', 'etudiant')
                              .filter(devoir=devoir, etudiant=etudiant).first())
                if soumission is not None:
                    # État relu sous verrou : 409 avant la validation des réponses (400).
                    versions.verifier_resoumission(soumission)
                reponses = valider_reponses(devoir, donnees.get('reponses'))
                if soumission is not None:
                    resoumission = True
                    versions.resoumettre(soumission, reponses)
                else:
                    soumission = SoumissionDevoir.objects.create(devoir=devoir, etudiant=etudiant)
                    ReponseExercice.objects.bulk_create([
                        ReponseExercice(soumission=soumission, exercice=exercice, fichiers=fichiers)
                        for exercice, fichiers in reponses
                    ])
                    if langage_executable(devoir):
                        # Seule une soumission qui vient d'être créée est mise en correction ici.
                        file_execution.corriger_soumission(soumission)
                if not devoir.resoumission_autorisee:
                    BrouillonExercice.objects.filter(etudiant=etudiant, exercice__devoir=devoir).delete()
                transaction.on_commit(lambda s=soumission: accuses.envoyer_accuse(s))
        except IntegrityError:
            # Deux envois simultanés : la contrainte d'unicité tranche, sans erreur 500.
            raise Conflit(MESSAGE_DEJA_SOUMIS)
        if resoumission:
            audit_log(self.request, 'resoumission_devoir', cible=soumission,
                      etablissement=etablissement_evaluation(devoir),
                      details={'type': 'soumission', 'devoir': devoir.pk, 'version': soumission.numero_version})
        soumission = self.get_queryset().get(pk=soumission.pk)
        return Response(self.get_serializer(soumission).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], url_path='versions')
    def lister_versions(self, request, pk=None):
        """Versions remplacées, de la plus récente à la plus ancienne (version en cours exclue).

        Correcteur : tout. Étudiant : fichiers toujours ; note et résultats (tests cachés réduits au statut et au
        temps) seulement si la politique du devoir est `immediate`.
        """
        soumission = self.get_object()
        complet = request.user.role != ETUDIANT
        visibles = soumission.devoir.politique_resultats == Devoir.IMMEDIATE
        return Response([versions.donnees_version(v, complet, visibles) for v in soumission.versions.all()])

    @action(detail=True, methods=['post'])
    def corriger(self, request, pk=None):
        soumission = self.get_object()
        self.verifier_ecriture(soumission)
        donnees = request.data
        if not isinstance(donnees, dict):
            raise ValidationError("Le corps de la requête doit être un objet JSON.")
        score = donnees.get('score')
        commentaire = donnees.get('commentaire', '')
        if not isinstance(commentaire, str):
            raise ValidationError({'commentaire': "Le commentaire doit être un texte."})
        if contient_non_stockable(commentaire):
            raise ValidationError({'commentaire': f"Le commentaire contient un caractère non autorisé ({NON_AUTORISE})."})
        # Score entier : au plus l'arrondi inférieur du barème du devoir.
        maximum = math.floor(soumission.devoir.bareme)
        if score is not None:
            score = en_entier(score.strip() if isinstance(score, str) else score)
            if score is None:
                raise ValidationError({'score': "Le score doit être un entier."})
            if not 0 <= score <= maximum:
                raise ValidationError({'score': f"Le score doit être compris entre 0 et {maximum}."})
        with transaction.atomic():
            # Relue sous verrou : la note proposée posée entre-temps par le worker est prise en compte.
            soumission = SoumissionDevoir.objects.select_for_update().select_related('devoir', 'etudiant').get(
                pk=soumission.pk)
            avant = soumission.score
            if score is None:
                if Execution.objects.filter(reponse__soumission=soumission, type=Execution.CORRECTION,
                                            statut__in=ACTIVES).exists():
                    raise Conflit(MESSAGE_CORRECTION_ATTENDUE)
                if soumission.note_proposee is None:
                    raise ValidationError({'score': MESSAGE_SANS_NOTE})
                # Sans score : la note proposée, arrondie à l'entier le plus proche et bornée au barème.
                arrondie = int(soumission.note_proposee.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
                score = min(max(arrondie, 0), maximum)
            soumission.score = score
            soumission.commentaire = commentaire
            soumission.statut = SoumissionDevoir.CORRIGE
            # Seuls ces champs : la note proposée écrite par le worker n'est jamais écrasée.
            soumission.save(update_fields=['score', 'commentaire', 'statut'])
        if soumission.score != avant:
            audit_log(
                request, 'saisie_note' if avant is None else 'modification_note', cible=soumission,
                etablissement=etablissement_evaluation(soumission.devoir),
                details={'type': 'soumission', 'etudiant': soumission.etudiant_id, 'avant': avant, 'apres': soumission.score},
            )
        return Response(SoumissionDevoirSerializer(soumission).data)

    @action(detail=True, methods=['post'])
    def recorriger(self, request, pk=None):
        """Remet en file les corrections dont la dernière est en erreur (ou absente) ; toutes avec `{tout: true}`.

        409 : année archivée, langage non exécutable, soumission déjà validée, correction déjà en file, rien à relancer.
        """
        from .execution.notation import derniere_correction
        soumission = self.get_object()
        self.verifier_ecriture(soumission)
        donnees = request.data if request.data is not None else {}
        if not isinstance(donnees, dict):
            raise ValidationError("Le corps de la requête doit être un objet JSON.")
        tout = donnees.get('tout', False)
        if not isinstance(tout, bool):
            raise ValidationError({'tout': "Le champ tout doit être un booléen."})
        if not langage_executable(soumission.devoir):
            raise Conflit(MESSAGE_LANGAGE)
        with transaction.atomic():
            soumission = SoumissionDevoir.objects.select_for_update().select_related('devoir').get(pk=soumission.pk)
            if soumission.statut == SoumissionDevoir.CORRIGE:
                raise Conflit(MESSAGE_DEJA_VALIDEE)
            if Execution.objects.filter(reponse__soumission=soumission, type=Execution.CORRECTION,
                                        statut__in=ACTIVES).exists():
                raise Conflit(MESSAGE_CORRECTION_EN_FILE)
            reponses = list(soumission.reponses.select_related('exercice'))
            if not tout:
                reponses = [r for r in reponses
                            if (derniere := derniere_correction(r)) is None or derniere.statut == Execution.ERREUR]
            if not reponses:
                raise Conflit(MESSAGE_RIEN_A_RELANCER)
            soumission.statut = SoumissionDevoir.EN_CORRECTION
            soumission.save(update_fields=['statut'])
            for reponse in reponses:
                file_execution.mettre_en_file(Execution.CORRECTION, soumission.etudiant, soumission.devoir,
                                              reponse.exercice, reponse=reponse)
        soumission = self.get_queryset().get(pk=soumission.pk)
        return Response(SoumissionDevoirSerializer(soumission).data, status=status.HTTP_202_ACCEPTED)


def ec_autorisee_pour_classe(user, classe, ec_id):
    """Matière enseignée par l'enseignant dans la classe, ou matière de l'établissement de la classe pour la gestion."""
    from referentiel.models import EC, EnseignantMatiere
    if user.role == ENSEIGNANT:
        return EnseignantMatiere.objects.filter(enseignant=user, classe=classe, ec_id=ec_id).exists()
    return EC.objects.filter(pk=ec_id, ue__filiere__etablissement_id=classe.filiere.etablissement_id).exists()


def verifier_ecriture_note(user, classe_id, ec_id, etudiant_id, annee_id):
    """Garde-fous d'une saisie de note directe : ValidationError (400) en cas de violation."""
    from referentiel.models import Inscription
    erreur = ValidationError({'detail': MESSAGE_HORS_PERIMETRE})
    classe = classes_du_perimetre(user).filter(pk=classe_id).first()
    if classe is None or not ec_autorisee_pour_classe(user, classe, ec_id):
        raise erreur
    if not Inscription.objects.filter(classe=classe, etudiant_id=etudiant_id).exists():
        raise ValidationError({'detail': "Cet étudiant n'est pas inscrit dans cette classe."})
    if annee_id != classe.annee_academique_id:
        raise ValidationError({'detail': "L'année académique ne correspond pas à celle de la classe."})


def _note_valide(valeur):
    if valeur is None:
        return True
    return isinstance(valeur, (int, float)) and not isinstance(valeur, bool) and 0 <= valeur <= 20


class NoteMatiereViewSet(ArchiveMixin, EtablissementScopedMixin, viewsets.ModelViewSet):
    annee_path = 'annee_academique'
    queryset = NoteMatiere.objects.select_related('etudiant', 'ec', 'classe', 'annee_academique').all()
    serializer_class = NoteMatiereSerializer
    permission_classes = [RolePermission(read=TOUS_LES_ROLES, write=CREATEURS)]
    scope_path = 'ec__ue__filiere__etablissement'

    def enseignant_scope(self, qs, user):
        return qs.filter(classe__in=classes_enseignant(user))

    def etudiant_scope(self, qs, user):
        return qs.filter(etudiant=user)

    @staticmethod
    def _verifier_donnees(user, serializer):
        data, instance = serializer.validated_data, serializer.instance

        def valeur(champ):
            if champ in data:
                return data[champ]
            return getattr(instance, champ) if instance else None

        verifier_ecriture_note(
            user, valeur('classe').pk, valeur('ec').pk, valeur('etudiant').pk, valeur('annee_academique').pk,
        )

    def perform_create(self, serializer, **kwargs):
        self._verifier_donnees(self.request.user, serializer)
        instance = super().perform_create(serializer, **kwargs)
        self._journaliser_note(instance, None)
        return instance

    def perform_update(self, serializer, **kwargs):
        self._verifier_donnees(self.request.user, serializer)
        avant = self._valeurs(serializer.instance)
        instance = super().perform_update(serializer, **kwargs)
        self._journaliser_note(instance, avant)
        return instance

    def perform_destroy(self, instance):
        audit_log(
            self.request, 'modification_note', cible=instance,
            etablissement=instance.classe.filiere.etablissement,
            details={'type': 'note_matiere', 'etudiant': instance.etudiant_id,
                     'avant': self._valeurs(instance), 'apres': None},
        )
        instance.delete()

    @staticmethod
    def _valeurs(note):
        return {'note_devoir': note.note_devoir, 'note_examen': note.note_examen}

    def _journaliser_note(self, note, avant):
        apres = self._valeurs(note)
        if avant == apres:
            return
        audit_log(
            self.request, 'saisie_note' if avant is None else 'modification_note', cible=note,
            etablissement=note.classe.filiere.etablissement,
            details={'type': 'note_matiere', 'etudiant': note.etudiant_id, 'avant': avant, 'apres': apres},
        )

    @action(detail=False, methods=['post'], permission_classes=[CORRECTEURS])
    def bulk_update(self, request):
        from referentiel.models import Inscription

        ec_id = request.data.get('ec')
        classe_id = request.data.get('classe')
        annee_id = request.data.get('annee_academique')
        notes_data = request.data.get('notes', [])

        if not all([ec_id, classe_id, annee_id]):
            return Response({"error": "ec, classe et annee_academique requis"}, status=status.HTTP_400_BAD_REQUEST)
        ec_id, classe_id = en_entier(ec_id), en_entier(classe_id)
        if ec_id is None or classe_id is None:
            return Response({"error": "ec et classe doivent être des identifiants numériques."},
                            status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        classe = classes_du_perimetre(user).filter(pk=classe_id).first()
        if classe is None:
            return Response({"error": "Classe introuvable."}, status=status.HTTP_404_NOT_FOUND)
        verifier_non_archivee(classe.annee_academique)
        if not ec_autorisee_pour_classe(user, classe, ec_id):
            return Response({"error": "Matière introuvable pour cette classe."}, status=status.HTTP_404_NOT_FOUND)
        if str(annee_id) != str(classe.annee_academique_id):
            raise ValidationError({'detail': "L'année académique ne correspond pas à celle de la classe."})

        if not isinstance(notes_data, list) or not all(isinstance(e, dict) for e in notes_data):
            raise ValidationError({'notes': "Le champ notes doit être une liste d'objets."})
        entrees = []
        for entry in notes_data:
            for champ in ('note_devoir', 'note_examen'):
                if not _note_valide(entry.get(champ)):
                    raise ValidationError({champ: "Une note doit être vide ou comprise entre 0 et 20."})
            brut = entry.get('etudiant')
            if isinstance(brut, (list, dict)):
                raise ValidationError({'etudiant': "L'identifiant de l'étudiant doit être un entier."})
            entrees.append((en_entier(brut), entry))

        inscrits = set(Inscription.objects.filter(classe=classe).values_list('etudiant_id', flat=True))
        created = updated = ignores = 0
        with transaction.atomic():
            for etudiant_id, entry in entrees:
                if etudiant_id is None or etudiant_id not in inscrits:
                    ignores += 1
                    continue
                existante = NoteMatiere.objects.filter(
                    etudiant_id=etudiant_id, ec_id=ec_id, classe=classe, annee_academique_id=classe.annee_academique_id,
                ).first()
                avant = self._valeurs(existante) if existante else None
                obj, is_created = NoteMatiere.objects.update_or_create(
                    etudiant_id=etudiant_id,
                    ec_id=ec_id,
                    classe=classe,
                    annee_academique_id=classe.annee_academique_id,
                    defaults={
                        'note_devoir': entry.get('note_devoir'),
                        'note_examen': entry.get('note_examen'),
                    }
                )
                self._journaliser_note(obj, avant)
                if is_created:
                    created += 1
                else:
                    updated += 1

        return Response({
            "message": f"{created} créée(s), {updated} mise(s) à jour",
            "created": created, "updated": updated, "ignores": ignores,
        })

    @action(detail=False, methods=['get'], permission_classes=[IsEtudiant])
    def mes_notes(self, request):
        notes = NoteMatiere.objects.filter(etudiant=request.user).select_related('ec', 'classe', 'annee_academique')
        notes = filtrer_archives(notes, 'annee_academique', request.query_params)
        data = []
        for note in notes:
            devoirs_ec = Devoir.objects.filter(ec=note.ec, est_publie=True)
            soumissions = SoumissionDevoir.objects.filter(
                etudiant=request.user,
                devoir__in=devoirs_ec,
                statut='corrige',
                score__isnull=False
            ).select_related('devoir').prefetch_related('devoir__exercices')
            # Même règle que la correction et GestionNotes : la note maximale est floor(barème).
            maximums = [(s, math.floor(s.devoir.bareme)) for s in soumissions]
            notes_20 = [float(s.score) * 20.0 / maximum for s, maximum in maximums if maximum]
            avg_prog = sum(notes_20) / len(notes_20) if notes_20 else None

            note_prog = round(avg_prog, 1) if avg_prog else None
            note_manuelle = note.note_devoir

            if note_manuelle is not None and note_prog is not None:
                best_devoir = max(note_manuelle, note_prog)
            elif note_manuelle is not None:
                best_devoir = note_manuelle
            elif note_prog is not None:
                best_devoir = note_prog
            else:
                best_devoir = None

            examen = note.note_examen
            if best_devoir is not None and examen is not None:
                moyenne = round(best_devoir * 0.4 + examen * 0.6, 2)
            elif best_devoir is not None:
                moyenne = round(best_devoir * 0.4, 2)
            elif examen is not None:
                moyenne = round(examen * 0.6, 2)
            else:
                moyenne = None

            data.append({
                'id': note.id,
                'ec_id': note.ec.id,
                'ec_libelle': note.ec.libelle,
                'classe_libelle': note.classe.libelle,
                'annee_libelle': note.annee_academique.libelle,
                'note_devoir_manuelle': note_manuelle,
                'note_devoir_prog': note_prog,
                'note_examen': examen,
                'moyenne': moyenne,
            })
        return Response(data)
