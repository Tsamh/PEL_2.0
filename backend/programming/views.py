import subprocess
import tempfile
import os
import time
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from django.db import transaction
from django.utils import timezone

from accounts.permissions import (
    IsEtudiant, RolePermission, CREATEURS, TOUS_LES_ROLES, ENSEIGNANT, ETUDIANT,
)
from accounts.scoping import (
    EtablissementScopedMixin, classes_du_perimetre, classes_enseignant,
    q_evaluation_etablissement, en_entier, verifier_filiere_du_perimetre, verifier_references_evaluation,
    MESSAGE_HORS_PERIMETRE,
)
from audit.services import log as audit_log
from quiz import acces
from quiz.statistiques import etudiants_affectes
from quiz.views import etablissement_evaluation
from referentiel.archives import ArchiveMixin, filtrer_archives, verifier_non_archivee
from .models import Devoir, SoumissionDevoir, NoteMatiere
from .serializers import (
    DevoirSerializer, DevoirEtudiantSerializer, SoumissionDevoirSerializer, SoumissionDevoirUpdateSerializer,
    NoteMatiereSerializer,
)

CORRECTEURS = RolePermission(read=CREATEURS, write=CREATEURS)


def devoirs_visibles_etudiant(user):
    """Devoirs publiés affectés à l'étudiant (classe, groupe de sa classe ou nominativement)."""
    return Devoir.objects.filter(est_publie=True).filter(acces.q_affecte(Devoir, user))


class DevoirViewSet(ArchiveMixin, EtablissementScopedMixin, viewsets.ModelViewSet):
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
    def execute(self, request, pk=None):
        devoir = self.get_object()
        code = request.data.get('code', '')
        language = devoir.langage

        if not code.strip():
            return Response({"error": "Le code ne peut pas être vide"}, status=status.HTTP_400_BAD_REQUEST)

        # Tests publics de l'exercice demandé, sinon du premier exercice.
        exercices = devoir.exercices.all()
        exercice_id = en_entier(request.data.get('exercice'))
        exercice = exercices.filter(pk=exercice_id).first() if exercice_id is not None else exercices.first()
        test_cases = [
            {'input': t.entree, 'expected_output': t.sortie_attendue}
            for t in (exercice.tests.filter(public=True) if exercice else [])
        ]

        runner = CodeRunner()
        result = runner.run(code, language, test_cases)

        if request.user.role == 'etudiant':
            safe_result = {
                "success": result["success"],
                "output": result.get("output", ""),
                "execution_time": result.get("execution_time", ""),
                "test_results": [],
            }
            if result.get("test_results"):
                for tr in result["test_results"]:
                    safe_result["test_results"].append({
                        "passed": tr["passed"],
                        "expected": tr["expected"] if tr["passed"] else "***",
                        "actual": tr["actual"] if tr["passed"] else "***",
                    })
            if not result["success"]:
                safe_result["message"] = "Votre code contient des erreurs. Veuillez les corriger."
            return Response(safe_result)

        return Response(result)


class SoumissionDevoirViewSet(ArchiveMixin, EtablissementScopedMixin, viewsets.ModelViewSet):
    annee_path = 'devoir__annee_academique'
    parent_params = ('devoir',)
    queryset = SoumissionDevoir.objects.select_related('devoir', 'etudiant').all()
    serializer_class = SoumissionDevoirSerializer

    def get_permissions(self):
        if self.action == 'create':
            return [IsEtudiant()]
        if self.action in ('update', 'partial_update', 'destroy', 'corriger'):
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
        return qs.filter(devoir_id=devoir) if devoir is not None else qs

    def get_serializer_class(self):
        if self.action in ('update', 'partial_update'):
            return SoumissionDevoirUpdateSerializer
        return SoumissionDevoirSerializer

    def perform_destroy(self, instance):
        audit_log(
            self.request, 'modification_note', cible=instance,
            etablissement=etablissement_evaluation(instance.devoir),
            details={'type': 'soumission', 'etudiant': instance.etudiant_id,
                     'avant': {'score': instance.score}, 'apres': None},
        )
        instance.delete()

    def perform_create(self, serializer, **kwargs):
        devoir = serializer.validated_data['devoir']
        if not devoirs_visibles_etudiant(self.request.user).filter(pk=devoir.pk).exists():
            raise ValidationError({'detail': "Devoir introuvable."})
        verifier_non_archivee(devoir.annee_academique)
        if devoir.date_fin and timezone.now() > devoir.date_fin:
            raise ValidationError("Le délai de soumission pour ce devoir est dépassé.")
        return super().perform_create(serializer, etudiant=self.request.user, **kwargs)

    @action(detail=True, methods=['post'])
    def corriger(self, request, pk=None):
        soumission = self.get_object()
        self.verifier_ecriture(soumission)
        avant = soumission.score
        score = request.data.get('score')
        commentaire = request.data.get('commentaire', '')
        if score is not None:
            score = en_entier(score.strip() if isinstance(score, str) else score)
            if score is None:
                raise ValidationError({'score': "Le score doit être un entier."})
            bareme = soumission.devoir.bareme
            if not 0 <= score <= bareme:
                raise ValidationError({'score': f"Le score doit être compris entre 0 et {bareme.normalize():f}."})
            soumission.score = score
        soumission.commentaire = commentaire
        soumission.statut = 'corrige'
        soumission.save()
        if soumission.score != avant:
            audit_log(
                request, 'saisie_note' if avant is None else 'modification_note', cible=soumission,
                etablissement=etablissement_evaluation(soumission.devoir),
                details={'type': 'soumission', 'etudiant': soumission.etudiant_id, 'avant': avant, 'apres': soumission.score},
            )
        return Response(SoumissionDevoirSerializer(soumission).data)


class CodeRunner:
    TIMEOUT = 10
    MAX_MEMORY = 50 * 1024 * 1024

    def run(self, code, language, test_cases=None):
        start = time.time()

        if language == 'python':
            result = self._run_python(code)
        elif language == 'javascript':
            result = self._run_javascript(code)
        else:
            return {
                "success": False,
                "output": "",
                "errors": f"Langage '{language}' non supporté pour l'exécution. Langages disponibles : Python, JavaScript.",
                "execution_time": "0s",
                "test_results": []
            }

        result["execution_time"] = f"{time.time() - start:.2f}s"

        if test_cases:
            result["test_results"] = self._run_tests(code, language, test_cases)

        return result

    def _run_python(self, code):
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
                f.write(code)
                f.flush()
                tmp_path = f.name

            proc = subprocess.run(
                ['python3', tmp_path],
                capture_output=True, text=True,
                timeout=self.TIMEOUT
            )
            return {
                "success": proc.returncode == 0,
                "output": proc.stdout,
                "errors": proc.stderr if proc.returncode != 0 else "",
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "output": "", "errors": f"Timeout ({self.TIMEOUT}s dépassé)"}
        except Exception as e:
            return {"success": False, "output": "", "errors": str(e)}
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    def _run_javascript(self, code):
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False, encoding='utf-8') as f:
                f.write(code)
                f.flush()
                tmp_path = f.name

            proc = subprocess.run(
                ['node', tmp_path],
                capture_output=True, text=True,
                timeout=self.TIMEOUT
            )
            return {
                "success": proc.returncode == 0,
                "output": proc.stdout,
                "errors": proc.stderr if proc.returncode != 0 else "",
            }
        except FileNotFoundError:
            return {"success": False, "output": "", "errors": "Node.js n'est pas installé sur le serveur."}
        except subprocess.TimeoutExpired:
            return {"success": False, "output": "", "errors": f"Timeout ({self.TIMEOUT}s dépassé)"}
        except Exception as e:
            return {"success": False, "output": "", "errors": str(e)}
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    def _run_tests(self, code, language, test_cases):
        results = []
        for i, tc in enumerate(test_cases):
            input_data = tc.get('input', '')
            expected = tc.get('expected_output', '')

            full_code = code + "\n" + self._get_test_harness(language, input_data)

            if language == 'python':
                result = self._run_python(full_code)
            elif language == 'javascript':
                result = self._run_javascript(full_code)
            else:
                result = {"output": "", "errors": "Langage non supporté"}

            actual = result.get('output', '').strip()
            passed = actual == expected.strip()

            results.append({
                "input": input_data,
                "expected": expected,
                "actual": actual,
                "passed": passed
            })
        return results

    def _get_test_harness(self, language, input_data):
        if language == 'python':
            return f"""
import sys
from io import StringIO
_old_stdin = sys.stdin
sys.stdin = StringIO({input_data!r})
try:
    main()
except NameError:
    pass
sys.stdin = _old_stdin
"""
        elif language == 'javascript':
            return f"""
try {{
  if (typeof main === 'function') {{
    const stdin = {input_data!r};
    const _origLog = console.log;
    let output = '';
    console.log = (v) => {{ output += v + '\\n'; }};
    main();
    console.log = _origLog;
  }}
}} catch(e) {{ console.error(e.message); }}
"""
        return ""


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
            notes_20 = [float(s.score) * 20.0 / float(s.devoir.bareme) for s in soumissions if s.devoir.bareme]
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
