from urllib.parse import urlsplit

from django.db import transaction
from rest_framework import serializers

from quiz import fenetres, validation
from quiz.acces import CLES_CIBLES, verifier_cibles
from quiz.exceptions import Conflit
from quiz.models import TagQuestion
from .models import CasDeTest, Devoir, Exercice, SoumissionDevoir, NoteMatiere
from .validation import PROFIL_DEVOIR, exercices_modifies

MESSAGE_VERROU = "Ce devoir a déjà des soumissions : ses exercices et ses tests ne peuvent plus être modifiés."
MESSAGE_COMPETENCE = "Une compétence choisie n'est pas disponible pour cet établissement."
MESSAGE_SANS_EXERCICE = "Ajoutez au moins un exercice avant de publier le devoir."
RESSOURCES_MAX = 20
LIBELLE_MAX = 200
URL_MAX = 500
FICHIERS_MAX = 20
NOM_FICHIER_MAX = 100
CONTENU_FICHIER_MAX = 100000
EXEMPLES_MAX = 20


def _texte(valeur, defaut=''):
    """Valeur textuelle d'un objet JSON (absente : défaut) ; None si ce n'est pas un texte."""
    if valeur is None:
        return defaut
    return valeur if isinstance(valeur, str) else None


def valider_ressources(valeur):
    erreur = f"Les ressources sont une liste d'au plus {RESSOURCES_MAX} liens {{libelle, url}}."
    if not isinstance(valeur, list) or len(valeur) > RESSOURCES_MAX:
        raise serializers.ValidationError(erreur)
    ressources = []
    for i, lien in enumerate(valeur, start=1):
        if not isinstance(lien, dict):
            raise serializers.ValidationError(erreur)
        libelle, url = _texte(lien.get('libelle')), _texte(lien.get('url'))
        if libelle is None or not 1 <= len(libelle.strip()) <= LIBELLE_MAX:
            raise serializers.ValidationError(f"Lien {i} : le libellé compte de 1 à {LIBELLE_MAX} caractères.")
        url = (url or '').strip()
        try:
            parties = urlsplit(url)
        except ValueError:
            parties = None
        if len(url) > URL_MAX or parties is None or parties.scheme.lower() not in ('http', 'https') or not parties.netloc:
            raise serializers.ValidationError(
                f"Lien {i} : l'adresse doit commencer par http:// ou https:// et compter au plus {URL_MAX} caractères.")
        ressources.append({'libelle': libelle.strip(), 'url': url})
    return ressources


def valider_fichiers(valeur):
    erreur = f"Les fichiers sont une liste d'au plus {FICHIERS_MAX} objets {{nom, contenu}}."
    if not isinstance(valeur, list) or len(valeur) > FICHIERS_MAX:
        raise serializers.ValidationError(erreur)
    fichiers, noms = [], set()
    for fichier in valeur:
        if not isinstance(fichier, dict):
            raise serializers.ValidationError(erreur)
        nom, contenu = _texte(fichier.get('nom')), _texte(fichier.get('contenu'))
        nom = nom.strip() if nom is not None else ''
        if not nom or len(nom) > NOM_FICHIER_MAX or '/' in nom or '\\' in nom or '..' in nom:
            raise serializers.ValidationError(
                f"Un nom de fichier compte de 1 à {NOM_FICHIER_MAX} caractères, sans « / », « \\ » ni « .. ».")
        if contenu is None or len(contenu) > CONTENU_FICHIER_MAX:
            raise serializers.ValidationError(
                f"Le contenu du fichier {nom} doit être un texte d'au plus {CONTENU_FICHIER_MAX} caractères.")
        if nom in noms:
            raise serializers.ValidationError(f"Deux fichiers portent le nom {nom}.")
        noms.add(nom)
        fichiers.append({'nom': nom, 'contenu': contenu})
    return fichiers


def valider_exemples(valeur):
    erreur = f"Les exemples sont une liste d'au plus {EXEMPLES_MAX} objets {{entree, sortie, explication}} (textes)."
    if not isinstance(valeur, list) or len(valeur) > EXEMPLES_MAX:
        raise serializers.ValidationError(erreur)
    exemples = []
    for exemple in valeur:
        if not isinstance(exemple, dict):
            raise serializers.ValidationError(erreur)
        champs = {cle: _texte(exemple.get(cle)) for cle in ('entree', 'sortie', 'explication')}
        if any(v is None for v in champs.values()):
            raise serializers.ValidationError(erreur)
        exemples.append(champs)
    return exemples


class CasDeTestSerializer(serializers.ModelSerializer):
    class Meta:
        model = CasDeTest
        fields = ['id', 'ordre', 'entree', 'sortie_attendue', 'public', 'poids']
        read_only_fields = ['id']
        # Le contenu des tests est conservé à l'identique (retours à la ligne et indentation compris).
        extra_kwargs = {'entree': {'trim_whitespace': False}, 'sortie_attendue': {'trim_whitespace': False}}


class ExerciceSerializer(serializers.ModelSerializer):
    """Exercice saisi dans le formulaire du devoir (vue enseignant : solution et tous les tests)."""
    tests = CasDeTestSerializer(many=True, required=False)
    competences = serializers.PrimaryKeyRelatedField(
        many=True, required=False, queryset=TagQuestion.objects.filter(type=TagQuestion.COMPETENCE),
        error_messages={'does_not_exist': MESSAGE_COMPETENCE, 'incorrect_type': MESSAGE_COMPETENCE})
    competences_detail = serializers.SerializerMethodField()

    class Meta:
        model = Exercice
        fields = ['id', 'ordre', 'titre', 'enonce', 'contraintes', 'exemples', 'fichiers_initiaux', 'solution',
                  'points', 'difficulte', 'competences', 'competences_detail', 'tests']
        read_only_fields = ['id']
        extra_kwargs = {'enonce': {'trim_whitespace': False}, 'contraintes': {'trim_whitespace': False}}

    def get_competences_detail(self, exercice):
        return [{'id': t.id, 'libelle': t.libelle} for t in exercice.competences.all()]

    def validate_exemples(self, valeur):
        return valider_exemples(valeur)

    def validate_fichiers_initiaux(self, valeur):
        return valider_fichiers(valeur)

    def validate_solution(self, valeur):
        return valider_fichiers(valeur)


def _creer_exercices(devoir, exercices_data):
    for i, e_data in enumerate(exercices_data):
        e_data = dict(e_data)
        tests_data = e_data.pop('tests', [])
        competences = e_data.pop('competences', [])
        e_data.setdefault('ordre', i + 1)
        exercice = Exercice.objects.create(devoir=devoir, **e_data)
        exercice.competences.set(competences)
        for j, t_data in enumerate(tests_data):
            t_data = dict(t_data)
            t_data.setdefault('ordre', j + 1)
            CasDeTest.objects.create(exercice=exercice, **t_data)


def _nom(user):
    return (user.get_full_name() or user.username) if user else ''


class DevoirSerializer(serializers.ModelSerializer):
    exercices = ExerciceSerializer(many=True, required=False)
    cree_par_nom = serializers.SerializerMethodField()
    filiere_libelle = serializers.CharField(source='filiere.libelle', read_only=True, default=None)
    niveau_libelle = serializers.CharField(source='niveau.libelle', read_only=True, default=None)
    annee_libelle = serializers.CharField(source='annee_academique.libelle', read_only=True, default=None)
    periode_libelle = serializers.SerializerMethodField()
    ec_libelle = serializers.SerializerMethodField()
    langage_display = serializers.CharField(source='get_langage_display', read_only=True)
    bareme = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)
    nb_exercices = serializers.SerializerMethodField()
    classes_detail = serializers.SerializerMethodField()
    groupes_detail = serializers.SerializerMethodField()
    etudiants_detail = serializers.SerializerMethodField()
    validation_requise = serializers.SerializerMethodField()
    valide_par_nom = serializers.SerializerMethodField()
    a_des_soumissions = serializers.SerializerMethodField()

    class Meta:
        model = Devoir
        fields = '__all__'
        read_only_fields = ['cree_par', 'statut_validation', 'motif_refus', 'soumis_le', 'valide_par', 'valide_le']

    # SerializerMethodField : un CharField(default=None) est omis en PATCH (partial) quand la relation est nulle.
    def get_cree_par_nom(self, devoir):
        return devoir.cree_par.get_full_name() if devoir.cree_par_id else ''

    def get_periode_libelle(self, devoir):
        return devoir.periode.libelle if devoir.periode_id else None

    def get_ec_libelle(self, devoir):
        return devoir.ec.libelle if devoir.ec_id else None

    def get_nb_exercices(self, devoir):
        return len(devoir.exercices.all())

    def get_classes_detail(self, devoir):
        return [{'id': c.id, 'code': c.code, 'libelle': c.libelle} for c in devoir.classes.all()]

    def get_groupes_detail(self, devoir):
        return [{'id': g.id, 'code': g.code, 'libelle': g.libelle, 'classe_code': g.classe.code}
                for g in devoir.groupes.all()]

    def get_etudiants_detail(self, devoir):
        return [{'id': u.id, 'nom': _nom(u)} for u in devoir.etudiants.all()]

    def get_validation_requise(self, devoir):
        return validation.validation_requise(devoir.etablissement)

    def get_valide_par_nom(self, devoir):
        return _nom(devoir.valide_par)

    def get_a_des_soumissions(self, devoir):
        return devoir.soumissions.exists()

    def validate_ressources(self, valeur):
        return valider_ressources(valeur)

    def _verifier_competences(self, acteur, attrs):
        """Les compétences d'un exercice sont celles de l'établissement du devoir ; le message ne cite que l'identifiant."""
        if acteur is not None:
            etablissement = validation.etablissement_de(acteur, self.instance, attrs)
        else:
            etablissement = self.instance.etablissement if self.instance is not None else None
        etablissement_id = etablissement.pk if etablissement is not None else None
        # Même forme et même message qu'une compétence inexistante : rien ne révèle les compétences des autres établissements.
        erreurs = [
            {'competences': [serializers.ErrorDetail(MESSAGE_COMPETENCE, code='does_not_exist')]}
            if any(tag.etablissement_id != etablissement_id for tag in exercice.get('competences', [])) else {}
            for exercice in attrs.get('exercices', [])
        ]
        if any(erreurs):
            raise serializers.ValidationError({'exercices': erreurs})

    def _verifier_exercices_pour_publier(self, attrs):
        instance = self.instance
        publie = attrs.get('est_publie', instance.est_publie if instance is not None else False)
        if not publie or ('est_publie' not in attrs and 'exercices' not in attrs):
            return
        if 'exercices' in attrs:
            nombre = len(attrs['exercices'])
        else:
            nombre = instance.exercices.count() if instance is not None else 0
        if nombre == 0:
            raise serializers.ValidationError({'exercices': [MESSAGE_SANS_EXERCICE]})

    def validate(self, attrs):
        debut = attrs.get('date_debut', getattr(self.instance, 'date_debut', None))
        fin = attrs.get('date_fin', getattr(self.instance, 'date_fin', None))
        if debut and fin and fin <= debut:
            raise serializers.ValidationError({'date_fin': "La date de fin doit être postérieure à la date de début."})
        request = self.context.get('request')
        acteur = request.user if request is not None else None
        self._verifier_competences(acteur, attrs)
        self._verifier_exercices_pour_publier(attrs)
        if acteur is not None:
            verifier_cibles(acteur, self.instance, attrs)
            validation.appliquer_regles(acteur, self.instance, attrs, PROFIL_DEVOIR)
        return attrs

    def create(self, validated_data):
        exercices_data = validated_data.pop('exercices', [])
        cibles_data = {cle: validated_data.pop(cle) for cle in CLES_CIBLES if cle in validated_data}
        with transaction.atomic():
            devoir = Devoir.objects.create(**validated_data)
            for cle, valeurs in cibles_data.items():
                getattr(devoir, cle).set(valeurs)
            _creer_exercices(devoir, exercices_data)
        return devoir

    def update(self, instance, validated_data):
        exercices_data = validated_data.pop('exercices', None)
        cibles_data = {cle: validated_data.pop(cle) for cle in CLES_CIBLES if cle in validated_data}
        with transaction.atomic():
            # Le devoir est verrouillé : une soumission ne peut pas apparaître entre le contrôle et le remplacement.
            Devoir.objects.select_for_update().get(pk=instance.pk)
            # Des exercices renvoyés à l'identique ne sont pas réécrits : les réponses qui les citent restent valables.
            remplacer = exercices_data is not None and exercices_modifies(instance, exercices_data)
            if remplacer and instance.soumissions.exists():
                raise Conflit(MESSAGE_VERROU)
            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            instance.save()
            for cle, valeurs in cibles_data.items():
                getattr(instance, cle).set(valeurs)
            if remplacer:
                instance.exercices.all().delete()
                _creer_exercices(instance, exercices_data)
        return instance


class ExerciceEtudiantSerializer(serializers.ModelSerializer):
    """Exercice vu par l'étudiant : jamais la solution ni les tests cachés."""
    competences = serializers.SerializerMethodField()
    tests_publics = serializers.SerializerMethodField()

    class Meta:
        model = Exercice
        fields = ['id', 'ordre', 'titre', 'enonce', 'contraintes', 'exemples', 'fichiers_initiaux', 'points',
                  'difficulte', 'competences', 'tests_publics']
        read_only_fields = fields

    def get_competences(self, exercice):
        return [t.libelle for t in exercice.competences.all()]

    def get_tests_publics(self, exercice):
        return [{'id': t.id, 'entree': t.entree, 'sortie_attendue': t.sortie_attendue}
                for t in exercice.tests.all() if t.public]


class DevoirEtudiantSerializer(serializers.ModelSerializer):
    """Vue étudiant : ni cibles, ni circuit de validation, ni solution, ni tests cachés."""
    cree_par_nom = serializers.SerializerMethodField()
    filiere_libelle = serializers.CharField(source='filiere.libelle', read_only=True, default=None)
    niveau_libelle = serializers.CharField(source='niveau.libelle', read_only=True, default=None)
    annee_libelle = serializers.CharField(source='annee_academique.libelle', read_only=True, default=None)
    ec_libelle = serializers.SerializerMethodField()
    langage_display = serializers.CharField(source='get_langage_display', read_only=True)
    bareme = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)
    exercices = ExerciceEtudiantSerializer(many=True, read_only=True)
    etat = serializers.SerializerMethodField()

    class Meta:
        model = Devoir
        fields = ['id', 'titre', 'objectifs', 'consignes', 'ressources', 'langage', 'langage_display',
                  'filiere', 'filiere_libelle', 'niveau', 'niveau_libelle', 'annee_academique', 'annee_libelle',
                  'ec', 'ec_libelle', 'date_debut', 'date_fin', 'bareme', 'cree_par_nom', 'exercices', 'etat']
        read_only_fields = fields

    def get_etat(self, devoir):
        etudiant = self.context['request'].user
        fenetre = fenetres.fenetre(devoir, etudiant)
        ouverture, fermeture = fenetre.affichee()
        return {
            'ouvert': fenetre.ouverte is not None,
            'fenetre': {'ouverture': ouverture, 'fermeture': fermeture, 'prochaine_ouverture': fenetre.prochaine_ouverture},
            'soumis': devoir.soumissions.filter(etudiant=etudiant).exists(),
        }

    def get_cree_par_nom(self, devoir):
        return devoir.cree_par.get_full_name() if devoir.cree_par_id else ''

    def get_ec_libelle(self, devoir):
        return devoir.ec.libelle if devoir.ec_id else None


class SoumissionDevoirSerializer(serializers.ModelSerializer):
    etudiant_nom = serializers.CharField(source='etudiant.get_full_name', read_only=True)
    devoir_titre = serializers.CharField(source='devoir.titre', read_only=True)

    class Meta:
        model = SoumissionDevoir
        fields = ['id', 'devoir', 'devoir_titre', 'etudiant', 'etudiant_nom', 'statut', 'score', 'commentaire', 'date_soumission']
        read_only_fields = ['id', 'etudiant', 'statut', 'score', 'commentaire', 'date_soumission']


class SoumissionDevoirUpdateSerializer(SoumissionDevoirSerializer):
    class Meta(SoumissionDevoirSerializer.Meta):
        read_only_fields = SoumissionDevoirSerializer.Meta.read_only_fields + ['devoir']


class NoteMatiereSerializer(serializers.ModelSerializer):
    etudiant_nom = serializers.CharField(source='etudiant.get_full_name', read_only=True)
    ec_libelle = serializers.CharField(source='ec.libelle', read_only=True)
    classe_libelle = serializers.CharField(source='classe.libelle', read_only=True)
    annee_libelle = serializers.CharField(source='annee_academique.libelle', read_only=True)

    class Meta:
        model = NoteMatiere
        fields = ['id', 'etudiant', 'etudiant_nom', 'ec', 'ec_libelle', 'classe', 'classe_libelle',
                  'annee_academique', 'annee_libelle', 'note_devoir', 'note_examen', 'moyenne', 'date_modification']
        read_only_fields = ['id', 'moyenne', 'date_modification']

    @staticmethod
    def _borne(valeur):
        if valeur is not None and not 0 <= valeur <= 20:
            raise serializers.ValidationError("Une note doit être vide ou comprise entre 0 et 20.")
        return valeur

    def validate_note_devoir(self, valeur):
        return self._borne(valeur)

    def validate_note_examen(self, valeur):
        return self._borne(valeur)


class NoteMatiereBulkSerializer(serializers.Serializer):
    ec = serializers.IntegerField()
    classe = serializers.IntegerField()
    annee_academique = serializers.IntegerField()
    notes = serializers.ListField(child=serializers.DictField())

    class NotesEntrySerializer(serializers.Serializer):
        etudiant = serializers.IntegerField()
        note_devoir = serializers.FloatField(allow_null=True, required=False)
        note_examen = serializers.FloatField(allow_null=True, required=False)
