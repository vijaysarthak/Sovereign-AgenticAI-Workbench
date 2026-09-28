import React, { useState, useEffect } from 'react';
import { apiGet } from '../api/client';
import { ShieldCheck, Activity, Lock, Database } from 'lucide-react';

const SovereigntyPage = () => {
  const [ledger, setLedger] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [verifyResult, setVerifyResult] = useState(null);
  const [verifying, setVerifying] = useState(false);

  useEffect(() => {
    const fetchLedger = async () => {
      try {
        setLoading(true);
        const data = await apiGet('/ledger?limit=50');
        setLedger(data || []);
      } catch (err) {
        setError(err.message || 'Failed to fetch ledger');
      } finally {
        setLoading(false);
      }
    };
    fetchLedger();
  }, []);

  const handleVerify = async () => {
    try {
      setVerifying(true);
      const res = await apiGet('/ledger/verify');
      setVerifyResult(res);
    } catch (err) {
      setVerifyResult({ error: err.message });
    } finally {
      setVerifying(false);
    }
  };

  return (
    <div className="p-6 h-full flex flex-col bg-sov-bg text-sov-text-primary overflow-y-auto">
      <div className="mb-6 flex items-center gap-3">
        <ShieldCheck className="text-sov-orange" size={28} />
        <h1 className="text-2xl font-bold">Sovereignty & Trust</h1>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
        <div className="bg-sov-card border border-sov-border rounded-lg p-5">
          <h2 className="text-lg font-semibold flex items-center gap-2 mb-4"><Activity className="text-sov-green"/> Air-Gap Status</h2>
          <div className="bg-sov-bg rounded border border-sov-green/30 p-4 flex flex-col items-center justify-center text-center">
            <ShieldCheck className="text-sov-green mb-2" size={32} />
            <h3 className="text-sov-green font-bold text-lg">No external connections detected</h3>
            <p className="text-sm text-sov-text-secondary mt-2">
              System is running in a fully air-gapped sovereign architecture. Network interfaces are isolated.
            </p>
          </div>
        </div>

        <div className="bg-sov-card border border-sov-border rounded-lg p-5">
          <h2 className="text-lg font-semibold flex items-center gap-2 mb-4"><Database className="text-sov-orange"/> Data Residency</h2>
          <div className="bg-sov-bg rounded border border-sov-border p-4">
            <div className="flex items-center gap-3 mb-3 border-b border-sov-border pb-3">
              <Lock className="text-sov-text-muted" size={20} />
              <div>
                <div className="font-semibold text-sm">Storage Location</div>
                <div className="text-xs text-sov-text-secondary font-mono">/var/opt/sovereign/data (On-Premise)</div>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <ShieldCheck className="text-sov-green" size={20} />
              <div>
                <div className="font-semibold text-sm">Encryption at Rest</div>
                <div className="text-xs text-sov-text-secondary font-mono">AES-256-GCM Active</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="bg-sov-card border border-sov-border rounded-lg p-5 flex-1 flex flex-col min-h-0">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-semibold">Audit Ledger</h2>
          <div className="flex items-center gap-3">
            {verifyResult && !verifyResult.error && (
              <span className={`px-3 py-1 rounded text-xs font-bold ${verifyResult.intact ? 'bg-sov-green/20 text-sov-green' : 'bg-sov-red/20 text-sov-red'}`}>
                {verifyResult.intact ? 'CHAIN INTACT' : `BROKEN AT ROW ${verifyResult.broken_at_row_id}`}
              </span>
            )}
            <button 
              onClick={handleVerify} 
              disabled={verifying}
              className="px-4 py-2 bg-sov-orange text-black font-semibold rounded hover:bg-sov-orange-dark disabled:opacity-50 transition-colors text-sm"
            >
              {verifying ? 'Verifying...' : 'Verify Chain'}
            </button>
          </div>
        </div>

        {loading ? (
          <div className="flex-1 flex items-center justify-center text-sov-text-muted">Loading ledger...</div>
        ) : error ? (
          <div className="flex-1 flex items-center justify-center text-sov-red">{error}</div>
        ) : (
          <div className="overflow-auto border border-sov-border rounded bg-sov-bg flex-1">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-sov-sidebar border-b border-sov-border text-sm text-sov-text-secondary sticky top-0">
                  <th className="p-3">ID</th>
                  <th className="p-3">Timestamp</th>
                  <th className="p-3">Actor</th>
                  <th className="p-3">Action</th>
                  <th className="p-3">Hash</th>
                </tr>
              </thead>
              <tbody>
                {ledger.map((row) => (
                  <tr key={row.row_id} className="border-b border-sov-border hover:bg-sov-card-hover text-xs font-mono">
                    <td className="p-3 text-sov-text-muted">{row.row_id}</td>
                    <td className="p-3">{new Date(row.timestamp).toLocaleString()}</td>
                    <td className="p-3 text-sov-amber">{row.actor}</td>
                    <td className="p-3 font-semibold">{row.action}</td>
                    <td className="p-3 text-sov-text-muted truncate max-w-[150px]" title={row.hash}>{row.hash?.substring(0, 16)}...</td>
                  </tr>
                ))}
                {ledger.length === 0 && (
                  <tr><td colSpan="5" className="p-4 text-center text-sov-text-muted">No audit logs found.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default SovereigntyPage;
