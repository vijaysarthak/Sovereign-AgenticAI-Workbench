import React, { useState } from 'react';
import { User, Lock, CheckCircle, AlertCircle } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';

const ProfilePage = () => {
  const { principal, changePassword, sponsoredCompartments } = useAuth();
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [status, setStatus] = useState(null);
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setStatus(null);
    if (newPassword !== confirmPassword) {
      setStatus({ type: 'error', message: 'New passwords do not match.' });
      return;
    }
    if (newPassword.length < 8) {
      setStatus({ type: 'error', message: 'New password must be at least 8 characters.' });
      return;
    }
    setSaving(true);
    try {
      await changePassword(oldPassword, newPassword);
      setStatus({ type: 'success', message: 'Password updated.' });
      setOldPassword(''); setNewPassword(''); setConfirmPassword('');
    } catch (err) {
      setStatus({ type: 'error', message: err.message || 'Failed to update password.' });
    } finally {
      setSaving(false);
    }
  };

  const fields = [
    ['Employee ID', principal?.person_id],
    ['Name', principal?.name],
    ['Designation', principal?.job_title],
    ['Pay Grade', principal?.grade],
    ['Role', principal?.is_admin ? 'Administrator' : 'Employee'],
  ];

  const inputClass = 'w-full bg-sov-bg border border-sov-border rounded p-2 text-sm focus:border-sov-orange outline-none';

  return (
    <div className="p-6 h-full flex flex-col bg-sov-bg text-sov-text-primary overflow-y-auto">
      <div className="mb-6 flex items-center gap-3">
        <User className="text-sov-orange" size={28} />
        <h1 className="text-2xl font-bold">Profile</h1>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-sov-card border border-sov-border rounded-lg p-5">
          <h2 className="text-lg font-semibold mb-4">Account</h2>
          <dl className="space-y-3 text-sm">
            {fields.map(([label, value]) => (
              <div key={label} className="flex justify-between gap-4 border-b border-sov-border pb-2">
                <dt className="text-sov-text-muted">{label}</dt>
                <dd className="font-mono text-right">{value || '—'}</dd>
              </div>
            ))}
            <div className="flex justify-between gap-4 border-b border-sov-border pb-2">
              <dt className="text-sov-text-muted">Compartment clearances</dt>
              <dd className="flex flex-wrap gap-1 justify-end">
                {principal?.compartments?.length ? principal.compartments.map((c) => (
                  <span key={c} className="px-2 py-0.5 text-xs font-mono rounded-full border bg-purple-500/10 text-purple-400 border-purple-500">{c.toUpperCase()}</span>
                )) : <span className="text-sov-text-muted italic">None</span>}
              </dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-sov-text-muted">Sponsor of</dt>
              <dd className="flex flex-wrap gap-1 justify-end">
                {sponsoredCompartments.length ? sponsoredCompartments.map((c) => (
                  <span key={c} className="px-2 py-0.5 text-xs font-mono rounded-full border bg-sov-orange/10 text-sov-orange border-sov-orange">{c.toUpperCase()}</span>
                )) : <span className="text-sov-text-muted italic">None</span>}
              </dd>
            </div>
          </dl>
        </div>

        <div className="bg-sov-card border border-sov-border rounded-lg p-5 h-fit">
          <h2 className="text-lg font-semibold flex items-center gap-2 mb-4"><Lock size={18} /> Change Password</h2>
          <form onSubmit={handleSubmit} className="space-y-3">
            <input required type="password" placeholder="Current password" value={oldPassword} onChange={(e) => setOldPassword(e.target.value)} className={inputClass} />
            <input required type="password" placeholder="New password (min 8 characters)" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} className={inputClass} />
            <input required type="password" placeholder="Confirm new password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} className={inputClass} />
            <button type="submit" disabled={saving} className="w-full bg-sov-orange text-black font-bold py-2 rounded hover:bg-sov-orange-dark disabled:opacity-50">
              {saving ? 'Updating...' : 'Update Password'}
            </button>
          </form>
          {status && (
            <div className={`mt-4 p-3 rounded text-sm flex items-center gap-2 ${status.type === 'success' ? 'bg-sov-green/10 border border-sov-green text-sov-green' : 'bg-sov-red/10 border border-sov-red/20 text-sov-red'}`}>
              {status.type === 'success' ? <CheckCircle size={16} /> : <AlertCircle size={16} />}
              {status.message}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default ProfilePage;
