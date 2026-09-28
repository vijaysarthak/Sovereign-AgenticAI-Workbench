import React, { useState, useEffect } from 'react';
import { apiGet, apiDelete, apiPatch } from '../api/client';
import { MessageSquare, Trash2, Edit2, Download, FileText, AlertCircle } from 'lucide-react';

const GeneratedOutputsPage = () => {
  const [conversations, setConversations] = useState([]);
  const [selectedConvId, setSelectedConvId] = useState(null);
  const [conversationDetail, setConversationDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState(null);
  const [editingId, setEditingId] = useState(null);
  const [editTitle, setEditTitle] = useState('');

  const fetchConversations = async () => {
    try {
      setLoading(true);
      const data = await apiGet('/conversations');
      setConversations(data || []);
    } catch (err) {
      setError(err.message || 'Failed to fetch conversations');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchConversations();
  }, []);

  useEffect(() => {
    if (selectedConvId) {
      const fetchDetail = async () => {
        try {
          setDetailLoading(true);
          const data = await apiGet(`/conversations/${selectedConvId}`);
          setConversationDetail(data);
        } catch (err) {
          console.error(err);
        } finally {
          setDetailLoading(false);
        }
      };
      fetchDetail();
    } else {
      setConversationDetail(null);
    }
  }, [selectedConvId]);

  const handleDelete = async (id, e) => {
    e.stopPropagation();
    try {
      await apiDelete(`/conversations/${id}`);
      if (selectedConvId === id) setSelectedConvId(null);
      fetchConversations();
    } catch (err) {
      alert('Failed to delete conversation');
    }
  };

  const handleRenameSubmit = async (id) => {
    try {
      await apiPatch(`/conversations/${id}`, { title: editTitle });
      setEditingId(null);
      fetchConversations();
      if (selectedConvId === id && conversationDetail) {
        setConversationDetail({...conversationDetail, title: editTitle});
      }
    } catch (err) {
      alert('Failed to rename');
    }
  };

  const handleDownloadReport = (rowId, format) => {
    window.location.href = `/report/${rowId}?format=${format}`;
  };

  return (
    <div className="p-6 h-full flex flex-col bg-sov-bg text-sov-text-primary">
      <div className="mb-6 flex items-center gap-3">
        <FileText className="text-sov-orange" size={28} />
        <h1 className="text-2xl font-bold">Generated Outputs</h1>
      </div>

      <div className="flex-1 flex gap-6 overflow-hidden">
        {/* Left Panel - List */}
        <div className="w-1/3 bg-sov-card border border-sov-border rounded-lg flex flex-col min-w-[300px]">
          <div className="p-4 border-b border-sov-border font-semibold text-lg flex items-center gap-2">
            <MessageSquare size={18}/> History
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {loading ? (
              <div className="p-4 text-center text-sov-text-muted">Loading...</div>
            ) : error ? (
              <div className="p-4 text-center text-sov-red">{error}</div>
            ) : conversations.length === 0 ? (
              <div className="p-4 text-center text-sm text-sov-text-muted">
                No conversations yet. Ask a question on the Workbench to get started.
              </div>
            ) : (
              conversations.map(conv => (
                <div 
                  key={conv.conversation_id}
                  onClick={() => setEditingId(null) || setSelectedConvId(conv.conversation_id)}
                  className={`p-3 rounded-lg cursor-pointer flex justify-between items-center group ${selectedConvId === conv.conversation_id ? 'bg-sov-orange/10 border border-sov-orange/30' : 'hover:bg-sov-card-hover border border-transparent'}`}
                >
                  <div className="overflow-hidden flex-1">
                    {editingId === conv.conversation_id ? (
                      <input 
                        type="text" 
                        value={editTitle}
                        onChange={(e) => setEditTitle(e.target.value)}
                        onBlur={() => handleRenameSubmit(conv.conversation_id)}
                        onKeyDown={(e) => e.key === 'Enter' && handleRenameSubmit(conv.conversation_id)}
                        autoFocus
                        className="w-full bg-sov-bg border border-sov-orange text-sm p-1 rounded outline-none"
                      />
                    ) : (
                      <h3 
                        className="font-medium text-sm truncate"
                        onDoubleClick={() => { setEditingId(conv.conversation_id); setEditTitle(conv.title); }}
                      >
                        {conv.title || 'New Conversation'}
                      </h3>
                    )}
                    <div className="text-xs text-sov-text-secondary mt-1">
                      {/* Backend timestamps are Unix seconds; Date expects milliseconds. */}
                      {new Date((conv.updated_at || conv.created_at) * 1000).toLocaleString()} • {conv.turn_count} {conv.turn_count === 1 ? 'turn' : 'turns'}
                    </div>
                  </div>
                  <div className="flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button onClick={(e) => { e.stopPropagation(); setEditingId(conv.conversation_id); setEditTitle(conv.title); }} className="text-sov-text-muted hover:text-sov-text-primary"><Edit2 size={14}/></button>
                    <button onClick={(e) => handleDelete(conv.conversation_id, e)} className="text-sov-text-muted hover:text-sov-red"><Trash2 size={14}/></button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Right Panel - Detail */}
        <div className="w-2/3 bg-sov-card border border-sov-border rounded-lg flex flex-col">
          {!selectedConvId ? (
            <div className="flex-1 flex flex-col items-center justify-center text-sov-text-muted gap-3">
              <MessageSquare size={48} className="opacity-20" />
              <p>Select a conversation to view details</p>
            </div>
          ) : detailLoading ? (
            <div className="flex-1 flex items-center justify-center text-sov-text-muted">Loading detail...</div>
          ) : !conversationDetail ? (
            <div className="flex-1 flex items-center justify-center text-sov-red"><AlertCircle/> Could not load details</div>
          ) : (
            <>
              <div className="p-4 border-b border-sov-border font-semibold text-lg">
                {conversationDetail.title || 'Conversation Detail'}
              </div>
              <div className="flex-1 overflow-y-auto p-6 space-y-6">
                {conversationDetail.turns?.map((turn, idx) => (
                  <div key={idx} className="flex flex-col gap-4">
                    {turn.question && (
                      <div className="self-end bg-sov-bg border border-sov-border-light p-4 rounded-xl rounded-tr-sm max-w-[80%]">
                        <div className="text-xs text-sov-text-muted mb-1 font-mono uppercase">User</div>
                        <div className="text-sm">{turn.question}</div>
                      </div>
                    )}
                    {turn.response?.answer && (
                      <div className="self-start bg-sov-sidebar border border-sov-orange/30 p-4 rounded-xl rounded-tl-sm max-w-[90%] w-full">
                        <div className="flex justify-between items-start mb-2">
                          <div className="text-xs text-sov-orange font-mono uppercase">Sovereign AI</div>
                          {turn.response.status === 'answered' && turn.response.ledger_row_id != null && (
                            <div className="flex gap-2">
                              <button onClick={() => handleDownloadReport(turn.response.ledger_row_id, 'docx')} className="flex items-center gap-1 text-xs bg-sov-bg border border-sov-border px-2 py-1 rounded hover:text-blue-400">
                                <Download size={12}/> DOCX
                              </button>
                              <button onClick={() => handleDownloadReport(turn.response.ledger_row_id, 'pptx')} className="flex items-center gap-1 text-xs bg-sov-bg border border-sov-border px-2 py-1 rounded hover:text-orange-400">
                                <Download size={12}/> PPTX
                              </button>
                              <button onClick={() => handleDownloadReport(turn.response.ledger_row_id, 'xlsx')} className="flex items-center gap-1 text-xs bg-sov-bg border border-sov-border px-2 py-1 rounded hover:text-green-400">
                                <Download size={12}/> XLSX
                              </button>
                              {turn.response.approval_note && (
                                <button onClick={() => { window.location.href = `/report/${turn.response.ledger_row_id}/approval-note`; }} className="flex items-center gap-1 text-xs bg-sov-bg border border-sov-orange/40 text-sov-orange px-2 py-1 rounded hover:bg-sov-border">
                                  <Download size={12}/> Approval Note
                                </button>
                              )}
                            </div>
                          )}
                        </div>
                        <div className="text-sm whitespace-pre-wrap">{turn.response.answer}</div>
                      </div>
                    )}
                  </div>
                ))}
                {(!conversationDetail.turns || conversationDetail.turns.length === 0) && (
                  <div className="text-center text-sov-text-muted mt-10">No messages in this conversation.</div>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default GeneratedOutputsPage;
