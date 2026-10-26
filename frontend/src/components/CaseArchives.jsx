// Case « Voir les archives » et bandeau de consultation seule.
export default function CaseArchives({ archives, onChange }) {
  return (
    <>
      <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 'normal', marginBottom: '12px' }}>
        <input type="checkbox" style={{ width: 'auto' }} checked={archives} onChange={(e) => onChange(e.target.checked)} />
        Voir les archives
      </label>
      {archives && <div className="alert">Archives : consultation seule.</div>}
    </>
  );
}
