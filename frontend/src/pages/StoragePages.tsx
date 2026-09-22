import {useEffect, useRef, useState} from 'react';
import {CloudUpload, FileCheck2, RefreshCw} from 'lucide-react';
import {api} from '../lib/api';
import {Empty, PageHeader, Status} from '../components/UI';

type StorageStatus = {
  configured: boolean;
  mode: string;
  bucket: string;
  message?: string | null;
};

type RemoteItem = {
  id: number;
  original_name: string;
  file_hash: string;
  status: string;
  size_bytes: number;
  duplicate_invoice_ids: number[];
  created_at: string;
  note?: string | null;
};

const STATUS_IT: Record<string, string> = {
  pending_review: 'Da verificare',
  possible_duplicate: 'Possibile duplicato',
  in_preview: 'In anteprima',
  imported: 'Importata',
  rejected: 'Scartata',
};

function statusLabel(status: string) {
  return STATUS_IT[status] || status;
}

function statusTone(status: string): 'ok' | 'warn' | 'danger' | undefined {
  if (status === 'possible_duplicate' || status === 'in_preview') return 'warn';
  if (status === 'rejected') return 'danger';
  return 'ok';
}

export function UploaderPage() {
  const input = useRef<HTMLInputElement>(null);
  const [status, setStatus] = useState<StorageStatus>();
  const [items, setItems] = useState<RemoteItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  async function refresh() {
    setError('');
    try {
      setStatus(await api<StorageStatus>('/storage/status'));
      setItems(await api<RemoteItem[]>('/storage/inbox'));
    } catch (e: any) {
      setError(e.message || 'Impossibile leggere lo Storage');
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function upload(file: File) {
    setBusy(true);
    setError('');
    setMessage('');
    const body = new FormData();
    body.append('file', file);
    try {
      const session = localStorage.getItem('randfatture.session') || '';
      const res = await fetch('/api/storage/upload', {
        method: 'POST',
        headers: {'X-Eye-Session': session},
        body,
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      const dup = data.duplicate_matches?.length
        ? ` Attenzione: possibile duplicato (fatture #${data.duplicate_matches.join(', #')}).`
        : '';
      setMessage(`File caricato: ${data.upload.original_name}.${dup}`);
      await refresh();
    } catch (e: any) {
      setError(e.message || 'Upload fallito');
    } finally {
      setBusy(false);
      if (input.current) input.current.value = '';
    }
  }

  return (
    <>
      <PageHeader
        title="Carica fatture"
        subtitle="I file vanno su Supabase Storage (o mirror locale). Non entrano in archivio finché un operatore non conferma."
      >
        <button className="secondary-btn" onClick={refresh}>
          <RefreshCw size={16} /> Aggiorna
        </button>
      </PageHeader>
      <section className="import-layout">
        <article
          className="panel dropzone"
          onClick={() => input.current?.click()}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            if (e.dataTransfer.files[0]) upload(e.dataTransfer.files[0]);
          }}
        >
          <CloudUpload />
          <h2>{busy ? 'Caricamento…' : 'Trascina qui una fattura'}</h2>
          <p>PDF / XML · solo upload file · max 30 MB</p>
          <button className="primary-btn" type="button">
            Seleziona file
          </button>
          <input
            ref={input}
            hidden
            type="file"
            accept=".pdf,.xml,.jpg,.jpeg,.png,.csv,.docx,.xlsx,.pptx"
            onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])}
          />
          {status && (
            <div className={status.configured ? 'success' : 'warning'} style={{marginTop: 16, maxWidth: '90%'}}>
              Storage: <b>{status.mode}</b>
              {status.message ? ` — ${status.message}` : ` · bucket ${status.bucket}`}
            </div>
          )}
          {error && <div className="error">{error}</div>}
          {message && <div className="success">{message}</div>}
        </article>
        <article className="panel list-panel">
          <div className="panel-title" style={{padding: 17, margin: 0}}>
            <h2>I miei caricamenti</h2>
          </div>
          {items.length ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>File</th>
                    <th>Stato</th>
                    <th>Data</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((x) => (
                    <tr key={x.id}>
                      <td>
                        <b>{x.original_name}</b>
                      </td>
                      <td>
                        <Status tone={statusTone(x.status)}>{statusLabel(x.status)}</Status>
                      </td>
                      <td>{new Date(x.created_at).toLocaleString('it-IT')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty title="Nessun file" text="I caricamenti di questo utente appariranno qui." />
          )}
        </article>
      </section>
    </>
  );
}

export function StorageInboxPage({onPreview}: {onPreview?: (jobPreview: any) => void}) {
  const [items, setItems] = useState<RemoteItem[]>([]);
  const [error, setError] = useState('');
  const [busyId, setBusyId] = useState<number | null>(null);

  async function refresh() {
    setError('');
    try {
      setItems(await api<RemoteItem[]>('/storage/inbox'));
    } catch (e: any) {
      setError(e.message || 'Coda non disponibile');
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function openPreview(id: number) {
    setBusyId(id);
    setError('');
    try {
      const preview = await api(`/storage/${id}/import-preview`, {method: 'POST'});
      onPreview?.(preview);
    } catch (e: any) {
      setError(e.message || 'Anteprima non riuscita');
    } finally {
      setBusyId(null);
      await refresh();
    }
  }

  async function reject(id: number) {
    if (!confirm('Scartare questo file dalla coda?')) return;
    setBusyId(id);
    try {
      await api(`/storage/${id}/reject`, {method: 'POST'});
      await refresh();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <>
      <PageHeader
        title="Coda Storage"
        subtitle="File caricati dal ruolo Caricatore. Confronta i doppioni e apri l’anteprima prima di confermare."
      >
        <button className="secondary-btn" onClick={refresh}>
          <RefreshCw size={16} /> Aggiorna
        </button>
      </PageHeader>
      <section className="panel list-panel">
        {error && <div className="error" style={{margin: 16}}>{error}</div>}
        {items.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>File</th>
                  <th>Hash</th>
                  <th>Stato</th>
                  <th>Duplicati</th>
                  <th>Data</th>
                  <th aria-label="Azioni" />
                </tr>
              </thead>
              <tbody>
                {items.map((x) => (
                  <tr key={x.id}>
                    <td>
                      <b>{x.original_name}</b>
                    </td>
                    <td>
                      <code style={{fontSize: 10}}>{x.file_hash.slice(0, 12)}…</code>
                    </td>
                    <td>
                      <Status tone={statusTone(x.status)}>{statusLabel(x.status)}</Status>
                    </td>
                    <td>{x.duplicate_invoice_ids?.length ? `#${x.duplicate_invoice_ids.join(', #')}` : '—'}</td>
                    <td>{new Date(x.created_at).toLocaleString('it-IT')}</td>
                    <td>
                      <div style={{display: 'flex', gap: 6, flexWrap: 'wrap'}}>
                        <button
                          className="secondary-btn"
                          disabled={busyId === x.id}
                          onClick={() => openPreview(x.id)}
                        >
                          <FileCheck2 size={16} />
                          {busyId === x.id ? '…' : 'Anteprima'}
                        </button>
                        <button className="secondary-btn" disabled={busyId === x.id} onClick={() => reject(x.id)}>
                          Scarta
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty title="Coda vuota" text="Quando il Caricatore invia file, appariranno qui per la verifica." />
        )}
      </section>
    </>
  );
}
