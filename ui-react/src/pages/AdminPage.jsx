import React, { useState, useEffect } from 'react';
import { apiGet, apiPost, apiPatch, apiDelete } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { Users, UserPlus, Shield, Key } from 'lucide-react';
import CompartmentAccessTable from '../components/Admin/CompartmentAccessTable';

const AdminPage = () => {
  const { principal } = useAuth();
  
  const [users, setUsers] = useState([]);
  const [sponsoredComps, setSponsoredComps] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Form states
  const [newEmpId, setNewEmpId] = useState('');
  const [newFullName, setNewFullName] = useState('');
  const [newDesignation, setNewDesignation] = useState('');
  const [newPayGrade, setNewPayGrade] = useState('A');
  const [tempPassword, setTempPassword] = useState('');

  const [resetEmpId, setResetEmpId] = useState('');
  const [resetResult, setResetResult] = useState(null);

  const [grantEmpId, setGrantEmpId] = useState('');
  const [grantComp, setGrantComp] = useState('');

  const isAdmin = !!principal?.is_admin;

  useEffect(() => {
    if (principal) fetchData();
  }, [principal]);

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);
      const [usersData, grantsData] = await Promise.all([
        isAdmin ? apiGet('/admin/users') : Promise.resolve([]),
        apiGet('/grants/mine').catch(() => ({ sponsored_compartments: [] }))
      ]);
      setUsers(usersData || []);
      setSponsoredComps(grantsData?.sponsored_compartments || []);
    } catch (err) {
      setError(err.message || 'Failed to load administration data');
    } finally {
      setLoading(false);
    }
  };

  if (!loading && !isAdmin && sponsoredComps.length === 0) {
    return (
      <div className="p-6 h-full flex flex-col items-center justify-center bg-sov-bg text-sov-text-primary">
        <Shield size={64} className="text-sov-red mb-4" />
        <h1 className="text-2xl font-bold text-sov-red mb-2">Access Denied</h1>
        <p className="text-sov-text-secondary">You need administrator privileges or compartment sponsorship to access this area.</p>
      </div>
    );
  }

  const handleCreateUser = async (e) => {
    e.preventDefault();
    try {
      const res = await apiPost('/admin/users', { 
        person_id: newEmpId, 
        name: newFullName, 
        job_title: newDesignation, 
        grade: newPayGrade 
      });
      setTempPassword(res.temporary_password || 'Success - No temp password returned');
      setNewEmpId(''); setNewFullName(''); setNewDesignation('');
      fetchData();
    } catch (err) {
      alert('Error: ' + err.message);
    }
  };

  const handleResetPassword = async (e) => {
    e.preventDefault();
    try {
      const res = await apiPost(`/admin/users/${resetEmpId}/reset-password`);
      setResetResult({ personId: resetEmpId, password: res.temporary_password });
      setResetEmpId('');
      fetchData();
    } catch (err) {
      alert('Error: ' + err.message);
    }
  };

  const handleGradeChange = async (user, grade) => {
    try {
      await apiPatch(`/admin/users/${user.person_id}/grade`, { grade });
      fetchData();
    } catch (err) {
      alert('Error updating grade: ' + err.message);
    }
  };

  const handleGrant = async (e, type) => {
    e.preventDefault();
    if (!grantEmpId || !grantComp) return;
    try {
      if (type === 'grant') {
        await apiPost('/grants', { person_id: grantEmpId, compartment: grantComp });
        alert(`Granted ${grantComp} to ${grantEmpId}`);
      } else {
        await apiDelete('/grants', { person_id: grantEmpId, compartment: grantComp });
        alert(`Revoked ${grantComp} from ${grantEmpId}`);
      }
      fetchData();
    } catch (err) {
      alert('Error: ' + err.message);
    }
  };

  const toggleUserStatus = async (user) => {
    try {
      if (user.is_active) {
        await apiPost(`/admin/users/${user.person_id}/deactivate`);
      } else {
        await apiPost(`/admin/users/${user.person_id}/reactivate`);
      }
      fetchData();
    } catch (err) {
      alert('Error updating status: ' + err.message);
    }
  };

  // Must match contracts.py VALID_MRPL_GRADES -- the backend rejects anything else.
  const grades = [
    'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I',
    'S1', 'S2', 'S3', 'S4',
    'JM1', 'JM2', 'JM3', 'JM4', 'JM5', 'JM6',
    'TS1', 'TS2', 'TS3', 'TS4', 'TS5', 'TS6',
  ];

  return (
    <div className="p-6 h-full flex flex-col bg-sov-bg text-sov-text-primary overflow-y-auto">
      <div className="mb-6 flex items-center gap-3">
        <Users className="text-sov-orange" size={28} />
        <h1 className="text-2xl font-bold">{isAdmin ? 'Admin Panel' : 'Compartment Access'}</h1>
      </div>

      {error && (
        <div className="mb-6 p-3 bg-sov-red/10 border border-sov-red/20 rounded text-sov-red text-sm">{error}</div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        {/* Left Col - Provisioning (admin only) */}
        {isAdmin && (
        <div className="space-y-6">
          <div className="bg-sov-card border border-sov-border rounded-lg p-5">
            <h2 className="text-lg font-semibold flex items-center gap-2 mb-4"><UserPlus size={20}/> Provision New Employee</h2>
            <form onSubmit={handleCreateUser} className="space-y-3">
              <input required type="text" placeholder="Employee ID" value={newEmpId} onChange={e => setNewEmpId(e.target.value)} className="w-full bg-sov-bg border border-sov-border rounded p-2 text-sm focus:border-sov-orange outline-none"/>
              <input required type="text" placeholder="Full Name" value={newFullName} onChange={e => setNewFullName(e.target.value)} className="w-full bg-sov-bg border border-sov-border rounded p-2 text-sm focus:border-sov-orange outline-none"/>
              <input required type="text" placeholder="Designation" value={newDesignation} onChange={e => setNewDesignation(e.target.value)} className="w-full bg-sov-bg border border-sov-border rounded p-2 text-sm focus:border-sov-orange outline-none"/>
              <select value={newPayGrade} onChange={e => setNewPayGrade(e.target.value)} className="w-full bg-sov-bg border border-sov-border rounded p-2 text-sm focus:border-sov-orange outline-none">
                {grades.map(g => <option key={g} value={g}>{g}</option>)}
              </select>
              <button type="submit" className="w-full bg-sov-orange text-black font-bold py-2 rounded hover:bg-sov-orange-dark">Create User</button>
            </form>
            {tempPassword && (
              <div className="mt-4 p-3 bg-sov-green/10 border border-sov-green text-sov-green rounded text-sm font-mono">
                Temporary Password: {tempPassword}
              </div>
            )}
          </div>

          <div className="bg-sov-card border border-sov-border rounded-lg p-5">
            <h2 className="text-lg font-semibold flex items-center gap-2 mb-4"><Key size={20}/> Password Reset</h2>
            <form onSubmit={handleResetPassword} className="flex gap-2">
              <input required type="text" placeholder="Target Employee ID" value={resetEmpId} onChange={e => setResetEmpId(e.target.value)} className="flex-1 bg-sov-bg border border-sov-border rounded p-2 text-sm focus:border-sov-orange outline-none"/>
              <button type="submit" className="bg-sov-bg border border-sov-orange text-sov-orange hover:bg-sov-orange hover:text-black font-bold px-4 py-2 rounded transition-colors">Reset</button>
            </form>
            {resetResult && (
              <div className="mt-4 p-3 bg-sov-green/10 border border-sov-green text-sov-green rounded text-sm font-mono">
                New temporary password for {resetResult.personId}: {resetResult.password}
              </div>
            )}
          </div>
        </div>
        )}

        {/* Right Col - Grants */}
        {sponsoredComps.length > 0 ? (
          <div className="bg-sov-card border border-sov-border rounded-lg p-5 h-fit">
            <h2 className="text-lg font-semibold flex items-center gap-2 mb-4"><Shield size={20}/> Compartment Clearance</h2>
            <p className="text-xs text-sov-text-secondary mb-4">You have sponsorship rights to manage access for specific compartments.</p>
            <form className="space-y-3">
              <input required type="text" placeholder="Target Employee ID" value={grantEmpId} onChange={e => setGrantEmpId(e.target.value)} className="w-full bg-sov-bg border border-sov-border rounded p-2 text-sm focus:border-sov-orange outline-none"/>
              <select required value={grantComp} onChange={e => setGrantComp(e.target.value)} className="w-full bg-sov-bg border border-sov-border rounded p-2 text-sm focus:border-sov-orange outline-none">
                <option value="">Select Compartment...</option>
                {sponsoredComps.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
              <div className="flex gap-2 pt-2">
                <button onClick={(e) => handleGrant(e, 'grant')} className="flex-1 bg-sov-green text-black font-bold py-2 rounded hover:bg-green-500">Grant Access</button>
                <button onClick={(e) => handleGrant(e, 'revoke')} className="flex-1 bg-sov-bg border border-sov-red text-sov-red font-bold py-2 rounded hover:bg-sov-red hover:text-black transition-colors">Revoke Access</button>
              </div>
            </form>
          </div>
        ) : (
          <div className="bg-sov-card border border-sov-border rounded-lg p-5 flex flex-col items-center justify-center text-center text-sov-text-muted h-fit py-12">
            <Shield size={32} className="mb-2 opacity-30" />
            <p>You do not have sponsorship rights for any compartments.</p>
          </div>
        )}
      </div>

      {isAdmin && (
        <CompartmentAccessTable users={users} currentUserId={principal?.person_id} onSaved={fetchData} />
      )}

      {isAdmin && (
      <div className="bg-sov-card border border-sov-border rounded-lg p-5 flex-1 min-h-0 flex flex-col">
        <h2 className="text-lg font-semibold mb-4">User Directory</h2>
        <div className="flex-1 overflow-auto bg-sov-bg rounded border border-sov-border">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-sov-sidebar border-b border-sov-border text-sm text-sov-text-secondary sticky top-0 z-10">
                <th className="p-3">ID</th>
                <th className="p-3">Name & Role</th>
                <th className="p-3">Grade</th>
                <th className="p-3">Compartments</th>
                <th className="p-3 text-center">Status</th>
                <th className="p-3 text-center">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.person_id} className={`border-b border-sov-border hover:bg-sov-card-hover text-sm ${!u.is_active ? 'opacity-50' : ''}`}>
                  <td className="p-3 font-mono">{u.person_id}</td>
                  <td className="p-3">
                    <div className="font-semibold">{u.name}</div>
                    <div className="text-xs text-sov-text-muted">{u.job_title}</div>
                  </td>
                  <td className="p-3">
                    {u.person_id === principal?.person_id ? (
                      <span className="px-2 py-1 bg-sov-sidebar rounded text-xs border border-sov-border font-mono" title="You cannot change your own grade">{u.grade}</span>
                    ) : (
                      <select
                        value={u.grade}
                        onChange={(e) => handleGradeChange(u, e.target.value)}
                        className="bg-sov-sidebar border border-sov-border rounded px-2 py-1 text-xs font-mono focus:border-sov-orange outline-none"
                      >
                        {(grades.includes(u.grade) ? grades : [u.grade, ...grades]).map(g => <option key={g} value={g}>{g}</option>)}
                      </select>
                    )}
                  </td>
                  <td className="p-3">
                    {u.compartments && u.compartments.length > 0 ? (
                      <div className="flex flex-wrap gap-1">
                        {u.compartments.map((c) => (
                          <span key={c} className="px-2 py-0.5 text-xs font-mono rounded-full border bg-purple-500/10 text-purple-400 border-purple-500">{c.toUpperCase()}</span>
                        ))}
                      </div>
                    ) : (
                      <span className="text-xs text-sov-text-muted italic">None</span>
                    )}
                  </td>
                  <td className="p-3 text-center">
                    <span className={`text-xs font-bold ${u.is_active ? 'text-sov-green' : 'text-sov-red'}`}>
                      {u.is_active ? 'ACTIVE' : 'INACTIVE'}
                    </span>
                  </td>
                  <td className="p-3 text-center">
                    <button
                      onClick={() => toggleUserStatus(u)}
                      disabled={u.person_id === principal?.person_id}
                      title={u.person_id === principal?.person_id ? 'You cannot deactivate your own account' : undefined}
                      className={`text-xs px-3 py-1 rounded border disabled:opacity-30 disabled:cursor-not-allowed ${u.is_active ? 'border-sov-red text-sov-red hover:bg-sov-red/10' : 'border-sov-green text-sov-green hover:bg-sov-green/10'}`}
                    >
                      {u.is_active ? 'Deactivate' : 'Reactivate'}
                    </button>
                  </td>
                </tr>
              ))}
              {users.length === 0 && (
                <tr><td colSpan="6" className="p-4 text-center text-sov-text-muted">No users found.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
      )}
    </div>
  );
};

export default AdminPage;
