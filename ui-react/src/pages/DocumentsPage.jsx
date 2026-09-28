import React, { useState, useEffect } from 'react';
import { apiGet } from '../api/client';
import SecurityBadge from '../components/Shared/SecurityBadge';
import { Search, FileText, Lock, CheckCircle, AlertCircle } from 'lucide-react';

const DocumentsPage = () => {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterReadable, setFilterReadable] = useState('all');

  useEffect(() => {
    const fetchDocs = async () => {
      try {
        setLoading(true);
        const data = await apiGet('/documents');
        setDocuments(data || []);
      } catch (err) {
        setError(err.message || 'Failed to fetch documents');
      } finally {
        setLoading(false);
      }
    };
    fetchDocs();
  }, []);

  const filteredDocs = documents.filter(doc => {
    const matchesSearch = doc.title?.toLowerCase().includes(searchTerm.toLowerCase()) || doc.source?.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesReadable = filterReadable === 'all' ? true : (filterReadable === 'readable' ? doc.readable : !doc.readable);
    return matchesSearch && matchesReadable;
  });

  return (
    <div className="p-6 h-full flex flex-col bg-sov-bg text-sov-text-primary">
      <div className="mb-6">
        <h1 className="text-2xl font-bold mb-2">Document Library</h1>
        <p className="text-sov-text-secondary">Browse and search accessible documents</p>
      </div>

      <div className="flex flex-col md:flex-row gap-4 mb-6">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-sov-text-muted" size={20} />
          <input 
            type="text"
            placeholder="Search documents..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-10 pr-4 py-2 bg-sov-card border border-sov-border rounded-lg focus:outline-none focus:border-sov-orange"
          />
        </div>
        <select
          value={filterReadable}
          onChange={(e) => setFilterReadable(e.target.value)}
          className="bg-sov-card border border-sov-border rounded-lg px-4 py-2 focus:outline-none focus:border-sov-orange"
        >
          <option value="all">All Documents</option>
          <option value="readable">Readable Only</option>
          <option value="unreadable">Denied Only</option>
        </select>
      </div>

      {loading ? (
        <div className="flex-1 flex items-center justify-center text-sov-text-muted">Loading documents...</div>
      ) : error ? (
        <div className="flex-1 flex items-center justify-center text-sov-red gap-2">
          <AlertCircle /> {error}
        </div>
      ) : filteredDocs.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-sov-text-muted">No documents found</div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 overflow-y-auto">
          {filteredDocs.map(doc => (
            <div key={doc.doc_id} className={`p-4 rounded-lg border flex flex-col gap-3 ${doc.readable ? 'bg-sov-card border-sov-border hover:bg-sov-card-hover' : 'bg-sov-bg border-sov-border-light opacity-75'}`}>
              <div className="flex items-start justify-between gap-4">
                <div className="flex gap-3">
                  <div className="mt-1">
                    {doc.readable ? <FileText className="text-sov-orange" /> : <Lock className="text-sov-text-muted" />}
                  </div>
                  <div>
                    <h3 className="font-semibold text-lg">{doc.title}</h3>
                    <p className="text-sm text-sov-text-secondary">{doc.source}</p>
                  </div>
                </div>
                {doc.readable ? (
                  <CheckCircle className="text-sov-green shrink-0" size={20} />
                ) : (
                  <Lock className="text-sov-red shrink-0" size={20} />
                )}
              </div>
              
              <div className="mt-auto pt-3 border-t border-sov-border flex flex-col gap-2">
                <SecurityBadge tier={doc.label?.tier} compartments={doc.label?.compartments} />
                {!doc.readable && doc.denial_reason && (
                  <p className="text-xs text-sov-red mt-1 font-mono">{doc.denial_reason}</p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default DocumentsPage;
