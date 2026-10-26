import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import api from '../../services/api';
import { chargerTout } from '../../services/pagination';
import { messageErreur } from '../../services/erreurs';
import { useAuth } from '../../context/AuthContext';
import CodeEditor from '../../components/CodeEditor';
import CountdownTimer from '../../components/CountdownTimer';
import ApercuDevoir, { Exemples, ListeRessources, TableTests } from '../../components/devoirs/ApercuDevoir';
import { DIFFICULTES, LANGAGES, avecContenuPrincipal, contenuPrincipal, nomFichier } from '../../components/devoirs/exercices';

const formatDate = (iso) => (iso ? new Date(iso).toLocaleString('fr-FR', { dateStyle: 'medium', timeStyle: 'short' }) : '');
const styleTexte = { whiteSpace: 'pre-wrap', color: 'var(--gray-700)', margin: '4px 0' };
const styleNote = { fontSize: '0.85rem', color: 'var(--gray-500)' };
const stylePre = { background: 'var(--gray-900, #1a1a1a)', color: '#e2e8f0', padding: '12px', borderRadius: '8px', overflow: 'auto', fontFamily: 'monospace', fontSize: '0.85rem', maxHeight: '200px', whiteSpace: 'pre-wrap' };

// Fichiers de travail d'un exercice : copie des fichiers de départ (un fichier principal au moins).
const fichiersDeDepart = (exercice, langage) => {
  const fichiers = (exercice.fichiers_initiaux || []).map((f) => ({ nom: f.nom, contenu: f.contenu }));
  return fichiers.length > 0 ? fichiers : [{ nom: nomFichier(langage), contenu: '' }];
};

function ResultatExecution({ resultat, testsPublics }) {
  if (resultat.enCours) return <div className="loading">Exécution en cours...</div>;
  if (resultat.erreur) return <div className="alert alert-error">{resultat.erreur}</div>;
  const r = resultat.donnees;
  const reussis = (r.test_results || []).filter((t) => t.passed).length;
  return (
    <div>
      <div style={{ display: 'flex', gap: '16px', marginBottom: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
        <span className={`badge ${r.success ? 'badge-active' : 'badge-inactive'}`}>{r.success ? 'Exécution réussie' : 'Erreur'}</span>
        {r.execution_time && <span style={styleNote}>Durée : {r.execution_time}</span>}
      </div>
      {!r.success && r.message && <div className="alert alert-error">{r.message}</div>}
      {r.output && <div><div style={styleNote}>Sortie</div><pre style={stylePre}>{r.output}</pre></div>}
      {r.test_results?.length > 0 && (
        <div>
          <strong>Tests publics : {reussis} / {r.test_results.length} réussis</strong>
          <table className="data-table" style={{ fontSize: '0.85rem', marginTop: '6px' }}>
            <thead><tr><th>#</th><th>Entrée</th><th>Sortie attendue</th><th>Résultat</th></tr></thead>
            <tbody>
              {r.test_results.map((t, i) => (
                <tr key={i}>
                  <td>{i + 1}</td>
                  <td><pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{testsPublics[i]?.entree ?? ''}</pre></td>
                  <td><pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{testsPublics[i]?.sortie_attendue ?? ''}</pre></td>
                  <td>{t.passed ? <span className="badge badge-active">Réussi</span> : <span className="badge badge-inactive">Échoué</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function ApercuGestion({ id }) {
  const navigate = useNavigate();
  const [devoir, setDevoir] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    api.get(`/programming/devoirs/${id}/`).then((res) => setDevoir(res.data))
      .catch((err) => setError(messageErreur(err, 'Devoir introuvable.')));
  }, [id]);

  if (error) return <div className="alert alert-error">{error}</div>;
  if (!devoir) return <div className="loading">Chargement...</div>;
  return (
    <div>
      <div className="page-header">
        <div>
          <button className="btn btn-secondary" onClick={() => navigate(-1)} style={{ marginBottom: '8px' }}>← Retour</button>
          <h1>{devoir.titre}</h1>
        </div>
      </div>
      <div className="form-card"><ApercuDevoir devoir={devoir} /></div>
    </div>
  );
}

function DevoirEtudiant({ id }) {
  const navigate = useNavigate();
  const [devoir, setDevoir] = useState(null);
  const [soumission, setSoumission] = useState(null);
  const [fichiers, setFichiers] = useState({});
  const [resultats, setResultats] = useState({});
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  const charger = useCallback(async () => {
    try {
      const [res, subs] = await Promise.all([
        api.get(`/programming/devoirs/${id}/`),
        chargerTout('/programming/soumissions/', { devoir: id }),
      ]);
      setDevoir(res.data);
      setSoumission(subs.find((s) => s.devoir === res.data.id) || null);
      // Les fichiers en cours d'édition sont gardés ; seuls les exercices nouveaux partent du fichier de départ.
      setFichiers((avant) => Object.fromEntries(res.data.exercices.map((ex) => [ex.id, avant[ex.id] || fichiersDeDepart(ex, res.data.langage)])));
      setError('');
    } catch (err) {
      setError(messageErreur(err, 'Devoir introuvable.'));
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { charger(); }, [charger]);

  if (loading) return <div className="loading">Chargement...</div>;
  if (!devoir) return <div className="alert alert-error">{error}</div>;

  const etat = devoir.etat || {};
  const soumis = Boolean(etat.soumis || soumission);
  const editable = Boolean(etat.ouvert) && !soumis;
  const reponses = Object.fromEntries((soumission?.reponses || []).map((r) => [r.exercice, r.fichiers]));

  const executer = async (exercice) => {
    setResultats((r) => ({ ...r, [exercice.id]: { enCours: true } }));
    try {
      const res = await api.post(`/programming/devoirs/${id}/execute/`, { exercice: exercice.id, code: contenuPrincipal(fichiers[exercice.id]) });
      setResultats((r) => ({ ...r, [exercice.id]: { donnees: res.data } }));
    } catch (err) {
      setResultats((r) => ({ ...r, [exercice.id]: { erreur: messageErreur(err, "Erreur lors de l'exécution.") } }));
    }
  };

  const soumettre = async () => {
    if (!window.confirm('Soumettre le devoir ? Le code de tous les exercices sera rendu et ne pourra plus être modifié.')) return;
    setSubmitting(true);
    setError('');
    setMessage('');
    try {
      const res = await api.post('/programming/soumissions/', {
        devoir: devoir.id,
        reponses: devoir.exercices.map((ex) => ({ exercice: ex.id, fichiers: fichiers[ex.id] })),
      });
      setSoumission(res.data);
      setMessage('Votre devoir a été soumis.');
      charger();
    } catch (err) {
      setError(messageErreur(err, 'Erreur lors de la soumission.'));
      // Une 409 (déjà soumis, fermé) change l'état affiché : il est relu.
      if (err.response?.status === 409) charger();
    } finally {
      setSubmitting(false);
    }
  };

  let messageFenetre = '';
  if (!soumis && !etat.ouvert) {
    messageFenetre = etat.fenetre?.prochaine_ouverture
      ? `Ce devoir n'est pas ouvert. Ouverture le ${formatDate(etat.fenetre.prochaine_ouverture)}.`
      : 'Ce devoir est fermé.';
  }
  const aUneNote = soumission && soumission.score !== null && soumission.score !== undefined;

  return (
    <div>
      <div className="page-header">
        <div>
          <button className="btn btn-secondary" onClick={() => navigate(-1)} style={{ marginBottom: '8px' }}>← Retour</button>
          <h1>{devoir.titre}</h1>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
          <span className="badge badge-active">{devoir.langage_display || LANGAGES[devoir.langage] || devoir.langage}</span>
          <span style={{ color: 'var(--gray-500)' }}>Barème : {Number(devoir.bareme)} pts</span>
          {editable && etat.fenetre?.fermeture && new Date(etat.fenetre.fermeture) > new Date() && <CountdownTimer dateFin={etat.fenetre.fermeture} onTimeUp={charger} />}
        </div>
      </div>

      {(devoir.objectifs || devoir.consignes || devoir.ressources?.length > 0 || etat.fenetre?.fermeture) && (
        <div className="form-card" style={{ marginBottom: '24px' }}>
          {devoir.ec_libelle && <div style={styleNote}>Matière : {devoir.ec_libelle}</div>}
          {etat.fenetre?.fermeture && <div style={styleNote}>Échéance : {formatDate(etat.fenetre.fermeture)}</div>}
          {devoir.objectifs && <div style={{ marginTop: '8px' }}><strong>Objectifs</strong><p style={styleTexte}>{devoir.objectifs}</p></div>}
          {devoir.consignes && <div style={{ marginTop: '8px' }}><strong>Consignes</strong><p style={styleTexte}>{devoir.consignes}</p></div>}
          {devoir.ressources?.length > 0 && <div style={{ marginTop: '8px' }}><strong>Ressources</strong><ListeRessources ressources={devoir.ressources} /></div>}
        </div>
      )}

      {message && <div className="alert alert-success">{message}</div>}
      {error && <div className="alert alert-error">{error}</div>}
      {messageFenetre && <div className="alert alert-error">{messageFenetre}</div>}

      {soumis && (
        <div className="form-card" style={{ marginBottom: '24px' }}>
          <h3>Votre soumission</h3>
          <div>
            <span className={`badge ${soumission?.statut === 'corrige' ? 'badge-active' : 'badge-inactive'}`}>
              {soumission?.statut === 'corrige' ? 'Corrigé' : 'Soumis'}
            </span>
            {soumission?.date_soumission && <span style={{ ...styleNote, marginLeft: '12px' }}>Rendu le {formatDate(soumission.date_soumission)}</span>}
            {aUneNote && <span style={{ marginLeft: '12px', fontWeight: 600, fontSize: '1.1rem' }}>Note : {soumission.score} / {Number(soumission.bareme ?? devoir.bareme)}</span>}
          </div>
          {soumission?.commentaire && (
            <div style={{ marginTop: '12px', padding: '12px', background: 'var(--primary-50, #eff6ff)', borderRadius: '8px', borderLeft: '4px solid var(--primary)' }}>
              <strong style={{ color: 'var(--primary)' }}>Remarques de l'enseignant :</strong>
              <p style={styleTexte}>{soumission.commentaire}</p>
            </div>
          )}
        </div>
      )}

      {devoir.exercices.map((ex, i) => {
        const rendus = reponses[ex.id];
        const affiches = soumis ? rendus : fichiers[ex.id];
        return (
          <div key={ex.id} className="form-card" style={{ marginBottom: '24px' }}>
            <h3 style={{ marginBottom: '4px' }}>Exercice {i + 1} : {ex.titre}</h3>
            <div style={styleNote}>
              {Number(ex.points)} pt{Number(ex.points) > 1 ? 's' : ''}, {DIFFICULTES[ex.difficulte] || ex.difficulte}
              {ex.competences?.length > 0 && `, compétences : ${ex.competences.join(', ')}`}
            </div>
            {ex.enonce && <p style={styleTexte}>{ex.enonce}</p>}
            {ex.contraintes && <div style={{ marginTop: '8px' }}><strong>Contraintes</strong><p style={styleTexte}>{ex.contraintes}</p></div>}
            <Exemples exemples={ex.exemples} />
            {ex.tests_publics?.length > 0 && <div style={{ marginTop: '8px' }}><strong>Tests publics</strong><TableTests tests={ex.tests_publics} /></div>}

            <div style={{ marginTop: '12px' }}>
              {soumis && !rendus ? (
                <p style={styleNote}>Aucune réponse rendue pour cet exercice.</p>
              ) : (
                <>
                  <strong>{soumis ? 'Code rendu' : 'Votre code'} ({affiches[0]?.nom})</strong>
                  <CodeEditor language={devoir.langage} value={contenuPrincipal(affiches)} readOnly={!editable} height="300px"
                    onChange={editable ? (contenu) => setFichiers((f) => ({ ...f, [ex.id]: avecContenuPrincipal(f[ex.id], contenu, devoir.langage) })) : undefined} />
                  {affiches.length > 1 && <small style={styleNote}>Autres fichiers {soumis ? 'rendus' : 'conservés'} : {affiches.slice(1).map((f) => f.nom).join(', ')}.</small>}
                </>
              )}
            </div>

            {editable && (
              <div style={{ marginTop: '12px' }}>
                <button type="button" className="btn btn-secondary" onClick={() => executer(ex)}
                  disabled={resultats[ex.id]?.enCours || !contenuPrincipal(fichiers[ex.id]).trim()}>
                  {resultats[ex.id]?.enCours ? 'Exécution...' : 'Exécuter'}
                </button>
                {ex.tests_publics?.length > 0 && <span style={{ ...styleNote, marginLeft: '8px' }}>Le code est exécuté sur les tests publics de l'exercice.</span>}
              </div>
            )}
            {editable && resultats[ex.id] && (
              <div style={{ marginTop: '12px' }}><ResultatExecution resultat={resultats[ex.id]} testsPublics={ex.tests_publics || []} /></div>
            )}
          </div>
        );
      })}

      {editable && (
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '24px' }}>
          <button className="btn btn-primary" onClick={soumettre} disabled={submitting || devoir.exercices.length === 0}>
            {submitting ? 'Soumission...' : 'Soumettre le devoir'}
          </button>
        </div>
      )}
    </div>
  );
}

export default function DevoirDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  // La gestion et l'auteur voient l'aperçu complet ; l'étudiant compose son devoir.
  return user?.role === 'etudiant' ? <DevoirEtudiant id={id} /> : <ApercuGestion id={id} />;
}
