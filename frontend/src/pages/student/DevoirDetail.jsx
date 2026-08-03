import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import api from '../../services/api';
import CodeEditor from '../../components/CodeEditor';
import CountdownTimer from '../../components/CountdownTimer';

export default function DevoirDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [devoir, setDevoir] = useState(null);
  const [code, setCode] = useState('');
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [soumission, setSoumission] = useState(null);

  const [executing, setExecuting] = useState(false);
  const [execResult, setExecResult] = useState(null);
  const [execError, setExecError] = useState('');
  const [showResults, setShowResults] = useState(false);

  useEffect(() => {
    const fetchDevoir = async () => {
      try {
        const res = await api.get(`/programming/devoirs/${id}/`);
        setDevoir(res.data);
        setCode(res.data.code_initial || '');
      } catch (err) {
        setError('Devoir non trouvé.');
      } finally {
        setLoading(false);
      }
    };
    const fetchSoumission = async () => {
      try {
        const res = await api.get('/programming/soumissions/');
        const list = res.data.results || res.data;
        const existing = list.find((s) => s.devoir === parseInt(id));
        if (existing) setSoumission(existing);
      } catch {}
    };
    fetchDevoir();
    fetchSoumission();
  }, [id]);

  const handleSubmit = async () => {
    setSubmitting(true);
    setError('');
    setMessage('');
    try {
      const res = await api.post('/programming/soumissions/', {
        devoir: parseInt(id),
        code_soumis: code,
      });
      setSoumission(res.data);
      setMessage('Votre code a été soumis avec succès !');
    } catch (err) {
      const detail = err.response?.data?.devoir?.[0] || err.response?.data?.detail || '';
      if (detail.includes('exists') || detail.includes('existe')) {
        setError('Vous avez déjà soumis ce devoir.');
      } else {
        setError(err.response?.data?.error || 'Erreur lors de la soumission.');
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleTimeUp = useCallback(() => {
    if (!soumission) {
      handleSubmit();
    }
  }, [soumission, code]);

  const handleExecute = async () => {
    setExecuting(true);
    setExecError('');
    setExecResult(null);
    setShowResults(true);
    try {
      const res = await api.post(`/programming/devoirs/${id}/execute/`, {
        code,
        language: devoir?.langage || 'python',
      });
      setExecResult(res.data);
    } catch (err) {
      setExecError(err.response?.data?.error || "Erreur lors de l'exécution.");
    } finally {
      setExecuting(false);
    }
  };

  if (loading) return <div className="loading">Chargement...</div>;
  if (error && !devoir) return <div className="alert alert-error">{error}</div>;

  const langageLabel = { python: 'Python', java: 'Java', c: 'C', cpp: 'C++', javascript: 'JavaScript', autre: 'Autre' };
  const isExpired = devoir?.date_fin && new Date(devoir.date_fin) <= new Date();

  return (
    <div>
      <div className="page-header">
        <div>
          <button className="btn btn-secondary" onClick={() => navigate(-1)} style={{ marginBottom: '8px' }}>← Retour</button>
          <h1>{devoir?.titre}</h1>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span className="badge badge-active">{langageLabel[devoir?.langage] || devoir?.langage}</span>
          <span style={{ color: 'var(--gray-500)' }}>{devoir?.points_max} pts</span>
          {devoir?.date_fin && !soumission && (
            <CountdownTimer dateFin={devoir.date_fin} onTimeUp={handleTimeUp} />
          )}
        </div>
      </div>

      {devoir?.description && (
        <div className="form-card" style={{ marginBottom: '24px' }}>
          <h3>Description</h3>
          <p style={{ color: 'var(--gray-600)', whiteSpace: 'pre-wrap' }}>{devoir.description}</p>
        </div>
      )}

      {message && <div className="alert alert-success">{message}</div>}
      {error && <div className="alert alert-error">{error}</div>}

      {soumission ? (
        <div className="form-card">
          <h3>Votre soumission</h3>
          <div style={{ marginBottom: '16px' }}>
            <span className={`badge ${soumission.statut === 'corrige' ? 'badge-active' : 'badge-inactive'}`}>
              {soumission.statut === 'corrige' ? 'Corrigé' : 'Soumis'}
            </span>
            {soumission.score !== null && soumission.score !== undefined && (
              <span style={{ marginLeft: '12px', fontWeight: 600 }}>{soumission.score} / {devoir.points_max}</span>
            )}
          </div>
          {soumission.commentaire && (
            <div style={{ marginBottom: '16px' }}>
              <strong>Commentaire :</strong>
              <p style={{ color: 'var(--gray-600)', marginTop: '4px' }}>{soumission.commentaire}</p>
            </div>
          )}
          <h4 style={{ marginBottom: '8px' }}>Code soumis :</h4>
          <CodeEditor language={devoir.langage} value={soumission.code_soumis} readOnly height="300px" />
        </div>
      ) : (
        <>
          {isExpired && (
            <div className="alert alert-error" style={{ marginBottom: '24px' }}>
              Le temps imparti pour ce devoir est écoulé.
            </div>
          )}

          {devoir?.code_initial && (
            <div className="form-card" style={{ marginBottom: '24px' }}>
              <h3>Code initial</h3>
              <p style={{ color: 'var(--gray-500)', marginBottom: '12px', fontSize: '0.9rem' }}>
                Voici le code de départ. Copiez-le dans votre éditeur ci-dessous pour commencer.
              </p>
              <CodeEditor language={devoir.langage} value={devoir.code_initial} readOnly height="200px" />
            </div>
          )}

          <div className="form-card" style={{ marginBottom: showResults ? '24px' : 0 }}>
            <h3>Votre solution</h3>
            <p style={{ color: 'var(--gray-500)', marginBottom: '12px', fontSize: '0.9rem' }}>
              Écrivez votre code ici. Testez-le avec "Exécuter" puis soumettez.
            </p>
            <CodeEditor language={devoir?.langage} value={code} onChange={setCode} height="400px" />
            <div style={{ marginTop: '16px', display: 'flex', justifyContent: 'space-between' }}>
              <button
                className="btn btn-secondary"
                onClick={handleExecute}
                disabled={executing || !code.trim()}
              >
                {executing ? 'Exécution...' : '▶ Exécuter'}
              </button>
              <button className="btn btn-primary" onClick={handleSubmit} disabled={submitting || isExpired}>
                {submitting ? 'Soumission...' : 'Soumettre'}
              </button>
            </div>
          </div>

          {showResults && (
            <div className="form-card" style={{ marginTop: '24px' }}>
              <h3>Résultats de l'exécution</h3>
              {execError && <div className="alert alert-error">{execError}</div>}
              {executing && <div className="loading">Exécution en cours...</div>}
              {execResult && (
                <>
                  <div style={{ display: 'flex', gap: '16px', marginBottom: '16px', flexWrap: 'wrap' }}>
                    <span className={`badge ${execResult.success ? 'badge-active' : 'badge-inactive'}`}>
                      {execResult.success ? '✅ Succès' : '❌ Erreur'}
                    </span>
                    {execResult.execution_time && (
                      <span style={{ color: 'var(--gray-500)' }}>⏱ {execResult.execution_time}</span>
                    )}
                  </div>

                  {execResult.output && (
                    <div style={{ marginBottom: '16px' }}>
                      <label style={{ fontWeight: 600, display: 'block', marginBottom: '4px' }}>Sortie :</label>
                      <pre style={{
                        background: 'var(--gray-900, #1a1a1a)', color: '#e2e8f0',
                        padding: '12px', borderRadius: '8px', overflow: 'auto',
                        fontFamily: 'monospace', fontSize: '0.85rem', maxHeight: '200px'
                      }}>
                        {execResult.output}
                      </pre>
                    </div>
                  )}

                  {execResult.errors && (
                    <div style={{ marginBottom: '16px' }}>
                      <label style={{ fontWeight: 600, display: 'block', marginBottom: '4px', color: 'var(--danger, #ef4444)' }}>Erreurs :</label>
                      <pre style={{
                        background: 'var(--gray-900, #1a1a1a)', color: '#fca5a5',
                        padding: '12px', borderRadius: '8px', overflow: 'auto',
                        fontFamily: 'monospace', fontSize: '0.85rem', maxHeight: '200px'
                      }}>
                        {execResult.errors}
                      </pre>
                    </div>
                  )}

                  {execResult.test_results?.length > 0 && (
                    <div>
                      <label style={{ fontWeight: 600, display: 'block', marginBottom: '8px' }}>Tests :</label>
                      <table className="data-table" style={{ fontSize: '0.85rem' }}>
                        <thead>
                          <tr><th>#</th><th>Entrée</th><th>Attendu</th><th>Obtenu</th><th>Résultat</th></tr>
                        </thead>
                        <tbody>
                          {execResult.test_results.map((t, i) => (
                            <tr key={i}>
                              <td>{i + 1}</td>
                              <td><code>{t.input}</code></td>
                              <td><code>{t.expected}</code></td>
                              <td><code>{t.actual}</code></td>
                              <td>{t.passed ? <span className="badge badge-active">✅</span> : <span className="badge badge-inactive">❌</span>}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
