const formatDate = (iso) => (iso ? new Date(iso).toLocaleString('fr-FR', { dateStyle: 'long', timeStyle: 'short' }) : '');

function CorrigeQuestion({ item, index }) {
  const coches = new Set(item.reponse.choix);
  return (
    <div className="form-card" style={{ marginBottom: '12px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px' }}>
        <strong>{index + 1}. {item.texte}</strong>
        <span>{Number(item.score_obtenu)} / {Number(item.points)}{item.statut_correction === 'a_valider' && ' (à valider)'}</span>
      </div>
      {item.type_question === 'courte' ? (
        <div style={{ marginTop: '8px' }}>
          <div>Votre réponse : <em>{item.reponse.texte || 'aucune'}</em></div>
          <div>Réponses acceptées : {item.choix.filter((c) => c.est_correct).map((c) => c.texte).join(', ')}</div>
        </div>
      ) : (
        <ul style={{ listStyle: 'none', padding: 0, marginTop: '8px' }}>
          {item.choix.map((c) => (
            <li key={c.id} style={{ color: c.est_correct ? 'var(--success, #16a34a)' : coches.has(c.id) ? 'var(--danger, #dc2626)' : 'inherit' }}>
              {coches.has(c.id) ? '☑' : '☐'} {c.texte}{c.est_correct && ' (bonne réponse)'}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function ResultatTentative({ tentative }) {
  const { resultat, corrige } = tentative;
  return (
    <div>
      <div className="form-card" style={{ marginBottom: '16px' }}>
        <h2 style={{ marginTop: 0 }}>{tentative.quiz_titre}</h2>
        <p>
          Tentative n°{tentative.numero}, soumise le {formatDate(tentative.soumise_le)}
          {tentative.soumission_auto && ' (automatiquement, à la fin du temps imparti)'}.
          {' '}Un accusé de réception est envoyé à votre adresse e-mail si elle est renseignée.
        </p>
        {resultat ? (
          <p style={{ fontSize: '1.3rem' }}>
            Note : <strong>{Number(resultat.score)} / {Number(resultat.score_max)}</strong>{' '}
            {resultat.provisoire && <span className="badge badge-pending">Provisoire : des réponses sont en cours de correction</span>}
          </p>
        ) : (
          <div className="alert alert-success">Vos réponses ont bien été reçues. Votre enseignant publiera les résultats.</div>
        )}
      </div>
      {corrige && corrige.map((item, i) => <CorrigeQuestion key={item.question} item={item} index={i} />)}
    </div>
  );
}
