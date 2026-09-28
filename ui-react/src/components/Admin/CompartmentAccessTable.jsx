import React, { useEffect, useMemo, useState } from 'react';
import { KeyRound, Check, Loader2, AlertCircle } from 'lucide-react';
import { apiGet, apiPut } from '../../api/client';

const sameSet = (a, b) => a.size === b.size && [...a].every((x) => b.has(x));

export default function CompartmentAccessTable({ users, currentUserId, onSaved }) {
  const [compartments, setCompartments] = useState([]);
  const [loadError, setLoadError] = useState(null);
  const [drafts, setDrafts] = useState({});
  const [savingId, setSavingId] = useState(null);
  const [rowStatus, setRowStatus] = useState({});

  useEffect(() => {
    apiGet('/admin/compartments')
      .then(setCompartments)
      .catch((err) => setLoadError(err.message || 'Failed to load compartments'));
  }, []);

  // Reset unsaved edits whenever the server-side user list changes.
  useEffect(() => {
    setDrafts(Object.fromEntries(users.map((u) => [u.person_id, new Set(u.compartments || [])])));
  }, [users]);

  const savedSets = useMemo(
    () => Object.fromEntries(users.map((u) => [u.person_id, new Set(u.compartments || [])])),
    [users],
  );

  const toggle = (personId, compId) => {
    setDrafts((prev) => {
      const next = new Set(prev[personId]);
      next.has(compId) ? next.delete(compId) : next.add(compId);
      return { ...prev, [personId]: next };
    });
    setRowStatus((prev) => ({ ...prev, [personId]: null }));
  };

  const setAll = (personId, grantAll) => {
    setDrafts((prev) => ({ ...prev, [personId]: new Set(grantAll ? compartments.map((c) => c.id) : []) }));
    setRowStatus((prev) => ({ ...prev, [personId]: null }));
  };

  const save = async (personId) => {
    setSavingId(personId);
    try {
      const res = await apiPut(`/admin/users/${personId}/compartments`, {
        compartments: [...drafts[personId]],
      });
      const parts = [];
      if (res.added?.length) parts.push(`granted ${res.added.join(', ')}`);
      if (res.removed?.length) parts.push(`revoked ${res.removed.join(', ')}`);
      setRowStatus((prev) => ({ ...prev, [personId]: { type: 'success', message: parts.join('; ') || 'No changes' } }));
      onSaved();
    } catch (err) {
      setRowStatus((prev) => ({ ...prev, [personId]: { type: 'error', message: err.message } }));
    } finally {
      setSavingId(null);
    }
  };

  return (
    <div className="bg-sov-card border border-sov-border rounded-lg p-5 mb-8">
      <h2 className="text-lg font-semibold flex items-center gap-2 mb-1"><KeyRound size={20} /> Compartment Access Control</h2>
      <p className="text-xs text-sov-text-secondary mb-4">
        As System Administrator you can grant or revoke any compartment for any other user. Tick the compartments a user
        should hold, then save that row. Every change is recorded in the audit ledger. You cannot change your own access.
      </p>

      {loadError ? (
        <div className="p-3 bg-sov-red/10 border border-sov-red/20 rounded text-sov-red text-sm">{loadError}</div>
      ) : (
        <div className="overflow-auto bg-sov-bg rounded border border-sov-border">
          <table className="w-full text-left border-collapse text-sm">
            <thead>
              <tr className="bg-sov-sidebar border-b border-sov-border text-sov-text-secondary">
                <th className="p-3">User</th>
                {compartments.map((c) => (
                  <th key={c.id} className="p-3 text-center" title={`Sponsor: ${c.description} (${c.sponsor})`}>
                    <div className="font-mono uppercase text-xs">{c.id}</div>
                    <div className="text-[10px] text-sov-text-muted font-normal normal-case">{c.description}</div>
                  </th>
                ))}
                <th className="p-3 text-center">All</th>
                <th className="p-3 text-center">Action</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => {
                const isSelf = u.person_id === currentUserId;
                const locked = isSelf || !u.is_active;
                const draft = drafts[u.person_id] || new Set();
                const dirty = !sameSet(draft, savedSets[u.person_id] || new Set());
                const allChecked = compartments.length > 0 && compartments.every((c) => draft.has(c.id));
                const status = rowStatus[u.person_id];
                return (
                  <tr key={u.person_id} className={`border-b border-sov-border align-top ${locked ? 'opacity-50' : 'hover:bg-sov-card-hover'}`}>
                    <td className="p-3">
                      <div className="font-mono">{u.person_id}</div>
                      <div className="text-xs text-sov-text-muted">
                        {u.name}{isSelf && ' (you)'}{!u.is_active && ' (inactive)'}
                      </div>
                      {status && (
                        <div className={`mt-1 text-xs flex items-center gap-1 ${status.type === 'success' ? 'text-sov-green' : 'text-sov-red'}`}>
                          {status.type === 'success' ? <Check size={12} /> : <AlertCircle size={12} />}
                          {status.message}
                        </div>
                      )}
                    </td>
                    {compartments.map((c) => (
                      <td key={c.id} className="p-3 text-center">
                        <input
                          type="checkbox"
                          aria-label={`${c.id} access for ${u.person_id}`}
                          checked={draft.has(c.id)}
                          disabled={locked || savingId === u.person_id}
                          onChange={() => toggle(u.person_id, c.id)}
                          className="h-4 w-4 accent-orange-500 cursor-pointer disabled:cursor-not-allowed"
                        />
                      </td>
                    ))}
                    <td className="p-3 text-center">
                      <input
                        type="checkbox"
                        aria-label={`all compartments for ${u.person_id}`}
                        checked={allChecked}
                        disabled={locked || savingId === u.person_id}
                        onChange={() => setAll(u.person_id, !allChecked)}
                        className="h-4 w-4 accent-orange-500 cursor-pointer disabled:cursor-not-allowed"
                      />
                    </td>
                    <td className="p-3 text-center">
                      <button
                        onClick={() => save(u.person_id)}
                        disabled={locked || !dirty || savingId === u.person_id}
                        title={isSelf ? 'You cannot change your own access' : !u.is_active ? 'Reactivate this user first' : undefined}
                        className="text-xs px-3 py-1 rounded border border-sov-orange text-sov-orange hover:bg-sov-orange hover:text-black transition-colors disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:bg-transparent disabled:hover:text-sov-orange inline-flex items-center gap-1"
                      >
                        {savingId === u.person_id && <Loader2 size={12} className="animate-spin" />}
                        Save
                      </button>
                    </td>
                  </tr>
                );
              })}
              {users.length === 0 && (
                <tr><td colSpan={compartments.length + 3} className="p-4 text-center text-sov-text-muted">No users found.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
