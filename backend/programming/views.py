import subprocess
import tempfile
import os
import time
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from .models import Devoir, SoumissionDevoir, NoteMatiere
from .serializers import DevoirSerializer, DevoirSerializerPublic, SoumissionDevoirSerializer, NoteMatiereSerializer


class DevoirViewSet(viewsets.ModelViewSet):
    queryset = Devoir.objects.select_related('filiere', 'niveau', 'annee_academique', 'cree_par').all()
    serializer_class = DevoirSerializer

    def get_serializer_class(self):
        if self.request.user.role == 'etudiant':
            return DevoirSerializerPublic
        return DevoirSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.role in ('admin', 'responsable_formation') and user.etablissement:
            qs = qs.filter(filiere__etablissement=user.etablissement)
        elif user.role == 'enseignant':
            qs = qs.filter(cree_par=user)
        elif user.role == 'etudiant':
            qs = qs.filter(est_publie=True)
        return qs

    def perform_create(self, serializer):
        serializer.save(cree_par=self.request.user)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def execute(self, request, pk=None):
        devoir = self.get_object()
        code = request.data.get('code', '')
        language = devoir.langage

        if not code.strip():
            return Response({"error": "Le code ne peut pas être vide"}, status=status.HTTP_400_BAD_REQUEST)

        runner = CodeRunner()
        result = runner.run(code, language, devoir.test_cases)

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


class SoumissionDevoirViewSet(viewsets.ModelViewSet):
    queryset = SoumissionDevoir.objects.select_related('devoir', 'etudiant').all()
    serializer_class = SoumissionDevoirSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.role == 'etudiant':
            qs = qs.filter(etudiant=user)
        elif user.role == 'enseignant':
            qs = qs.filter(devoir__cree_par=user)
        elif user.role in ('admin', 'responsable_formation') and user.etablissement:
            qs = qs.filter(devoir__filiere__etablissement=user.etablissement)
        return qs

    def perform_create(self, serializer):
        devoir = serializer.validated_data['devoir']
        if devoir.date_fin and timezone.now() > devoir.date_fin:
            from rest_framework.exceptions import ValidationError
            raise ValidationError("Le délai de soumission pour ce devoir est dépassé.")
        serializer.save(etudiant=self.request.user)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def corriger(self, request, pk=None):
        soumission = self.get_object()
        if request.user.role not in ('admin', 'responsable_formation', 'enseignant'):
            return Response({"error": "Non autorisé"}, status=status.HTTP_403_FORBIDDEN)
        score = request.data.get('score')
        commentaire = request.data.get('commentaire', '')
        if score is not None:
            soumission.score = int(score)
        soumission.commentaire = commentaire
        soumission.statut = 'corrige'
        soumission.save()
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


class NoteMatiereViewSet(viewsets.ModelViewSet):
    queryset = NoteMatiere.objects.select_related('etudiant', 'ec', 'classe', 'annee_academique').all()
    serializer_class = NoteMatiereSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.role == 'etudiant':
            qs = qs.filter(etudiant=user)
        elif user.role == 'enseignant':
            from referentiel.models import AffectationEnseignant
            classe_ids = AffectationEnseignant.objects.filter(enseignant=user).values_list('classe_id', flat=True)
            qs = qs.filter(classe_id__in=classe_ids)
        elif user.role in ('admin', 'responsable_formation') and user.etablissement:
            qs = qs.filter(ec__ue__filiere__etablissement=user.etablissement)
        return qs

    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def bulk_update(self, request):
        if request.user.role not in ('admin', 'responsable_formation', 'enseignant'):
            return Response({"error": "Non autorisé"}, status=status.HTTP_403_FORBIDDEN)

        ec_id = request.data.get('ec')
        classe_id = request.data.get('classe')
        annee_id = request.data.get('annee_academique')
        notes_data = request.data.get('notes', [])

        if not all([ec_id, classe_id, annee_id]):
            return Response({"error": "ec, classe et annee_academique requis"}, status=status.HTTP_400_BAD_REQUEST)

        created = 0
        updated = 0
        for entry in notes_data:
            etudiant_id = entry.get('etudiant')
            note_devoir = entry.get('note_devoir')
            note_examen = entry.get('note_examen')

            obj, is_created = NoteMatiere.objects.update_or_create(
                etudiant_id=etudiant_id,
                ec_id=ec_id,
                classe_id=classe_id,
                annee_academique_id=annee_id,
                defaults={
                    'note_devoir': note_devoir,
                    'note_examen': note_examen,
                }
            )
            if is_created:
                created += 1
            else:
                updated += 1

        return Response({"message": f"{created} créée(s), {updated} mise(s) à jour", "created": created, "updated": updated})

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def mes_notes(self, request):
        if request.user.role != 'etudiant':
            return Response({"error": "Réservé aux étudiants"}, status=status.HTTP_403_FORBIDDEN)

        from django.db.models import Avg, F, ExpressionWrapper, FloatField

        notes = NoteMatiere.objects.filter(etudiant=request.user).select_related('ec', 'classe', 'annee_academique')
        data = []
        for note in notes:
            devoirs_ec = Devoir.objects.filter(ec=note.ec, est_publie=True)
            soumissions = SoumissionDevoir.objects.filter(
                etudiant=request.user,
                devoir__in=devoirs_ec,
                statut='corrige',
                score__isnull=False
            ).annotate(
                note_20=ExpressionWrapper(
                    F('score') * 20.0 / F('devoir__points_max'),
                    output_field=FloatField()
                )
            )
            avg_prog = soumissions.aggregate(avg=Avg('note_20'))['avg']

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
