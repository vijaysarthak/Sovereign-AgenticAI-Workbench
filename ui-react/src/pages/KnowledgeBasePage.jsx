import React, { useState, useEffect } from 'react';
import { apiGet } from '../api/client';
import SecurityBadge from '../components/Shared/SecurityBadge';
import { Database, BarChart3, Search, AlertCircle } from 'lucide-react';

const KnowledgeBasePage = () => {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState('');

  useEffect(() => {
    const fetchDocs = async () => {
      try {
        setLoading(true);
        const data = await apiGet('/documents');
        setDocuments(data || []);
      } catch (err) {
        setError(err.message || 'Failed to fetch knowledge base');
      } finally {
        setLoading(false);
      }
    };
    fetchDocs();
  }, []);

  const totalDocs = documents.length;
  const docsByTier = documents.reduce((acc, doc) => {
    const tier = doc.label?.tier || 'unknown';
    acc[tier] = (acc[tier] || 0) + 1;
    return acc;
  }, {});
  const docsByCompartment = documents.reduce((acc, doc) => {
    doc.label?.compartments?.forEach(comp => {
      acc[comp] = (acc[comp] || 0) + 1;
    });
    return acc;
  }, {});

  const filteredDocs = documents.filter(d => d.title?.toLowerCase().includes(search.toLowerCase()));

  return (
    <div className="p-6 h-full flex flex-col bg-sov-bg text-sov-text-primary overflow-y-auto">
      <div className="mb-6 flex items-center gap-3">
        <Database className="text-sov-orange" size={28} />
        <h1 className="text-2xl font-bold">Knowledge Base</h1>
      </div>

      {loading ? (
        <div className="flex-1 flex items-center justify-center text-sov-text-muted">Loading corpus...</div>
      ) : error ? (
        <div className="flex-1 flex items-center justify-center text-sov-red gap-2"><AlertCircle /> {error}</div>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
            <div className="bg-sov-card p-4 rounded-lg border border-sov-border">
              <h3 className="text-sov-text-secondary text-sm mb-1 flex items-center gap-2"><BarChart3 size={16}/> Total Documents</h3>
              <p className="text-3xl font-mono text-sov-orange">{totalDocs}</p>
            </div>
            <div className="bg-sov-card p-4 rounded-lg border border-sov-border">
              <h3 className="text-sov-text-secondary text-sm mb-2">By Security Tier</h3>
              <div className="space-y-2">
                {Object.entries(docsByTier).map(([tier, count]) => (
                  <div key={tier} className="flex justify-between items-center text-sm">
                    <span className="capitalize">{tier}</span>
                    <span className="font-mono">{count}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="bg-sov-card p-4 rounded-lg border border-sov-border">
              <h3 className="text-sov-text-secondary text-sm mb-2">By Compartment</h3>
              <div className="space-y-2">
                {Object.entries(docsByCompartment).map(([comp, count]) => (
                  <div key={comp} className="flex justify-between items-center text-sm">
                    <span className="uppercase">{comp}</span>
                    <span className="font-mono">{count}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="mb-4 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-sov-text-muted" size={20} />
            <input 
              type="text"
              placeholder="Search indexed documents..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-10 pr-4 py-2 bg-sov-card border border-sov-border rounded-lg focus:outline-none focus:border-sov-orange"
            />
          </div>

          <div className="bg-sov-card border border-sov-border rounded-lg overflow-hidden">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-sov-sidebar border-b border-sov-border text-sm text-sov-text-secondary">
                  <th className="p-3">Title</th>
                  <th className="p-3">Source</th>
                  <th className="p-3">Security Level</th>
                  <th className="p-3 text-center">Status</th>
                </tr>
              </thead>
              <tbody>
                {filteredDocs.map((doc, idx) => (
                  <tr key={idx} className="border-b border-sov-border hover:bg-sov-card-hover text-sm">
                    <td className="p-3 font-medium">{doc.title}</td>
                    <td className="p-3 text-sov-text-muted">{doc.source}</td>
                    <td className="p-3">
                      <SecurityBadge tier={doc.label?.tier} compartments={doc.label?.compartments} />
                    </td>
                    <td className="p-3 text-center">
                      <span className={doc.readable ? "text-sov-green" : "text-sov-red"}>
                        {doc.readable ? 'Indexed' : 'Restricted'}
                      </span>
                    </td>
                  </tr>
                ))}
                {filteredDocs.length === 0 && (
                  <tr><td colSpan="4" className="p-4 text-center text-sov-text-muted">No documents found.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
};

export default KnowledgeBasePage;
