import { useCallback, useLayoutEffect, useRef } from 'react';
import Editor from '@monaco-editor/react';

const LANG_MAP = {
  python: 'python',
  java: 'java',
  c: 'c',
  cpp: 'cpp',
  javascript: 'javascript',
};

export default function CodeEditor({ language = 'python', value = '', onChange, readOnly = false, height = '300px', path, onMount }) {
  // En lecture seule, l'enveloppe pose le texte par setValue, qui émet un changement de contenu vers l'écouteur du rendu
  // précédent (ses effets passifs réabonnent onChange en dernier). L'écouteur reste donc stable et lit ces valeurs,
  // à jour dès la phase de layout, avant tout effet passif : seule une frappe en édition remonte.
  const derniers = useRef({ onChange, readOnly });
  useLayoutEffect(() => { derniers.current = { onChange, readOnly }; });
  const surChangement = useCallback((val) => {
    if (!derniers.current.readOnly) derniers.current.onChange?.(val || '');
  }, []);

  return (
    <div style={{ border: '1px solid var(--gray-200)', borderRadius: '8px', overflow: 'hidden' }}>
      <Editor
        height={height}
        language={LANG_MAP[language] || 'plaintext'}
        value={value}
        path={path}
        onMount={onMount}
        onChange={surChangement}
        theme="vs-dark"
        options={{
          readOnly,
          minimap: { enabled: false },
          fontSize: 14,
          lineNumbers: 'on',
          scrollBeyondLastLine: false,
          wordWrap: 'on',
          automaticLayout: true,
          tabSize: 4,
          padding: { top: 12, bottom: 12 },
        }}
      />
    </div>
  );
}
