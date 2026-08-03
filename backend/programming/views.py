import subprocess
import tempfile
import os
import time
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from .models import Devoir, SoumissionDevoir
from .serializers import DevoirSerializer, DevoirSerializerPublic, SoumissionDevoirSerializer


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
        language = request.data.get('language', devoir.langage)

        if not code.strip():
            return Response({"error": "Le code ne peut pas être vide"}, status=status.HTTP_400_BAD_REQUEST)

        runner = CodeRunner()
        result = runner.run(code, language, devoir.test_cases)

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
