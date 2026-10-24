import { Fragment, useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import api from '../../services/api';
import { messageErreur } from '../../services/erreurs';
import Barre from '../../components/stats/Barre';
import Courbe from '../../components/stats/Courbe';
import Histogramme from '../../components/stats/Histogramme';
import { duree, nombre, pourcentage } from '../../components/stats/format';

const STATUTS = {
  soumis: ['badge-active', 'Soumis'],
  en_cours: ['badge-pending', 'En cours'],
  non_commence: ['badge-inactive', 'Non commencé'],
};
const TYPES = { qcm: 'QCM', vf: 'Vrai / Faux', courte: 'Réponse courte' };

function Carte({ valeur, libelle, detail }) {
  return (
    <div className="stat-card">
      <div className="stat-number">{valeur}</div>
      <div className="stat-label">{libelle}</div>
      {detail && <div style={{ fontSize: '0.8rem', color: 'var(--gray-500)', marginTop: '4px' }}>{detail}</div>}
    </div>
  );
}

function DetailQuestion({ question }) {
  return (
    <div style={{ padding: '8px 4px' }}>
      {question.choix.length > 0 && (
        <table className="data-table" style={{ marginBottom: '8px' }}>
          <thead><tr><th>Choix</th><th>Cochés</th><th>Part des étudiants</th></tr></thead>
          <tbody>
            {question.choix.map((c) => (
              <tr key={c.id}>
                <td>{c.texte}{c.est_correct && <span className="badge badge-active" style={{ marginLeft: '6px' }}>Bonne réponse</span>}</td>
                <td>{c.nb}</td>
                <td><Barre valeur={c.pourcentage} libelle={`${c.texte} : ${pourcentage(c.pourcentage)}`} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <strong>Erreurs fréquentes</strong>
      {question.erreurs_frequentes.length === 0 ? (
        <p style={{ color: 'var(--gray-500)', margin: '4px 0' }}>Aucune erreur relevée.</p>
      ) : (
        <ul style={{ margin: '4px 0', paddingLeft: '18px' }}>
          {question.erreurs_frequentes.map((e) => <li key={e.texte}>{e.texte} ({e.nb})</li>)}
        </ul>
      )}
    </div>
  );
}

export default function TableauBordQuiz() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [quiz, setQuiz] = useState(null);
  const [stats, setStats] = useState(null);
  const [error, setError] = useState('');
  const [ouverte, setOuverte] = useState(null);

  useEffect(() => {
    Promise.all([api.get(`/quiz/quizzes/${id}/`), api.get(`/quiz/quizzes/${id}/statistiques/`)])
      .then(([q, s]) => { setQuiz(q.data); setStats(s.data); })
      .catch((err) => setError(messageErreur(err, 'Erreur lors du chargement des statistiques.')));
  }, [id]);

  if (error) return <div className="alert alert-error">{error}</div>;
  if (!stats) return <div className="loading">Chargement...</div>;

  const { population: p, notes: n } = stats;

  return (
    <div>
      <div className="page-header" style={{ flexWrap: 'wrap', gap: '12px' }}>
        <h1 style={{ margin: 0 }}>Statistiques : {quiz?.titre}</h1>
        <div style={{ display: 'flex', gap: '8px' }}>
          <Link className="btn btn-outline" to={`/quiz/${id}/tentatives`}>Tentatives</Link>
          <button type="button" className="btn btn-secondary" onClick={() => navigate(-1)}>Retour</button>
        </div>
      </div>

      <div className="dashboard-grid" style={{ marginBottom: '24px' }}>
        <Carte valeur={pourcentage(p.taux_participation)} libelle="Participation" detail={`${p.soumis} sur ${p.concernes} ; ${p.en_cours} en cours, ${p.non_commences} non commencé(s)`} />
        <Carte valeur={n.moyenne == null ? '-' : `${nombre(n.moyenne)} / ${nombre(n.score_max)}`} libelle="Moyenne" detail={n.moyenne == null ? null : pourcentage(n.moyenne_pourcentage)} />
        <Carte valeur={n.mediane == null ? '-' : `${nombre(n.mediane)} / ${nombre(n.score_max)}`} libelle="Médiane" detail={n.mediane == null ? null : pourcentage(n.mediane_pourcentage)} />
        <Carte valeur={nombre(n.ecart_type)} libelle="Écart-type" detail={n.minimum == null ? null : `de ${nombre(n.minimum)} à ${nombre(n.maximum)}`} />
        <Carte valeur={duree(n.duree_mediane)} libelle="Temps médian" />
        <Carte valeur={n.provisoires} libelle="Notes provisoires" detail="Réponses courtes à valider" />
      </div>

      <h2>Distribution des notes</h2>
      <div className="table-container" style={{ padding: '16px', marginBottom: '24px' }}>
        {n.nb === 0 ? <p style={{ color: 'var(--gray-500)' }}>Aucune tentative soumise pour le moment.</p> : (
          <>
            <Histogramme tranches={stats.distribution} />
            <p style={{ fontSize: '0.85rem', color: 'var(--gray-500)', marginBottom: 0 }}>Meilleure tentative de chaque étudiant, en pourcentage de la note maximale.</p>
          </>
        )}
      </div>

      <h2>Questions</h2>
      <div className="table-container" style={{ marginBottom: '24px' }}>
        <table className="data-table">
          <thead><tr><th>#</th><th>Question</th><th>Type</th><th>Réussite</th><th>Note moyenne</th><th>Sans réponse</th><th></th></tr></thead>
          <tbody>
            {stats.questions.map((q, i) => (
              <Fragment key={q.id}>
                <tr>
                  <td>{i + 1}</td>
                  <td style={{ maxWidth: '320px' }}>{q.texte}</td>
                  <td>{TYPES[q.type_question]}</td>
                  <td><Barre valeur={q.taux_reussite} libelle={`Réussite : ${pourcentage(q.taux_reussite)}`} /></td>
                  <td>{nombre(q.score_moyen)} / {nombre(q.points)}</td>
                  <td>{q.nb_sans_reponse}</td>
                  <td><button type="button" className="btn btn-sm btn-secondary" onClick={() => setOuverte(ouverte === q.id ? null : q.id)}>{ouverte === q.id ? 'Masquer' : 'Détail'}</button></td>
                </tr>
                {ouverte === q.id && <tr><td colSpan={7}><DetailQuestion question={q} /></td></tr>}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>

      <h2>Étudiants</h2>
      <div className="table-container">
        {stats.etudiants.length === 0 ? <div className="empty-state"><p>Aucun étudiant concerné par ce quiz.</p></div> : (
          <table className="data-table">
            <thead><tr><th>Étudiant</th><th>Statut</th><th>Tentatives</th><th>Meilleure</th><th>Dernière</th><th>Temps</th><th>Progression</th></tr></thead>
            <tbody>
              {stats.etudiants.map((e) => {
                const [classe, libelle] = STATUTS[e.statut];
                return (
                  <tr key={e.id}>
                    <td><Link to={`/etudiants/${e.id}/resultats`}>{e.nom}</Link></td>
                    <td><span className={`badge ${classe}`}>{libelle}</span>{e.provisoire && <span className="badge badge-pending" style={{ marginLeft: '4px' }}>Provisoire</span>}</td>
                    <td>{e.nb_tentatives}</td>
                    <td>{e.meilleure == null ? '-' : `${nombre(e.meilleure)} / ${nombre(e.score_max)}`}</td>
                    <td>{nombre(e.derniere)}</td>
                    <td>{e.temps_total ? duree(e.temps_total) : '-'}</td>
                    <td><Courbe valeurs={e.progression} max={e.score_max} libelles={e.progression.map((v, j) => `Tentative ${j + 1} : ${nombre(v)}`)} /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
