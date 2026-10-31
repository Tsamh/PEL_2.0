import Editor from '@monaco-editor/react';

const LANG_MAP = {
  python: 'python',
  java: 'java',
  c: 'c',
  cpp: 'cpp',
  javascript: 'javascript',
};

export default function CodeEditor({ language = 'python', value = '', onChange, readOnly = false, height = '300px', path, onMount }) {
  return (
    <div style={{ border: '1px solid var(--gray-200)', borderRadius: '8px', overflow: 'hidden' }}>
      <Editor
        height={height}
        language={LANG_MAP[language] || 'plaintext'}
        value={value}
        path={path}
        onMount={onMount}
        onChange={(val) => onChange?.(val || '')}
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
