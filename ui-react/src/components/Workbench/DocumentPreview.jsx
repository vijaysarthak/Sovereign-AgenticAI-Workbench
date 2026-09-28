import React from 'react';
import { ChevronLeft, ChevronRight, Search, ZoomIn, Maximize2 } from 'lucide-react';

export default function DocumentPreview({ document, citations = [] }) {
  if (!document) {
    return (
      <div className="bg-sov-card border border-sov-border rounded-xl h-full flex items-center justify-center min-h-[400px]">
        <div className="text-sov-text-muted text-center">
          <FileTextIcon />
          <p className="mt-2">Select a document to preview</p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-sov-card border border-sov-border rounded-xl flex flex-col h-full min-h-[400px]">
      <div className="p-3 border-b border-sov-border-light flex items-center justify-between bg-sov-sidebar rounded-t-xl">
        <h3 className="font-medium text-sov-text-primary truncate pr-4">
          {document.title || document.doc_id}
        </h3>
        <div className="flex items-center gap-3 text-sov-text-secondary">
          <div className="flex items-center gap-1 bg-sov-border rounded px-2 py-1">
            <button className="hover:text-sov-text-primary"><ChevronLeft size={16} /></button>
            <span className="text-xs">1 / 14</span>
            <button className="hover:text-sov-text-primary"><ChevronRight size={16} /></button>
          </div>
          <button className="hover:text-sov-text-primary"><Search size={16} /></button>
          <button className="hover:text-sov-text-primary"><ZoomIn size={16} /></button>
          <button className="hover:text-sov-text-primary"><Maximize2 size={16} /></button>
        </div>
      </div>
      
      <div className="flex-1 p-6 overflow-y-auto bg-[#1a1a1a]">
        <div className="max-w-2xl mx-auto bg-sov-bg p-8 shadow-lg min-h-[600px] border border-sov-border text-sov-text-primary font-serif">
          <h1 className="text-2xl font-bold mb-6 text-center">{document.title || 'Document Content'}</h1>
          
          <div className="space-y-4 leading-relaxed">
            <p>This is a placeholder for the document preview content.</p>
            <p>In a fully integrated system, this area would render the PDF or text content of the selected document, potentially highlighting the areas matched by the query citations.</p>
          </div>
          
          {citations && citations.length > 0 && (
            <div className="mt-12 pt-6 border-t border-sov-border-light">
              <h4 className="text-sov-orange font-sans font-semibold mb-4">Citations in this document</h4>
              <div className="space-y-4">
                {citations.map((cite, idx) => (
                  <div key={idx} className="bg-sov-sidebar p-3 rounded border-l-2 border-sov-orange font-sans text-sm">
                    <div className="text-sov-text-muted mb-1 flex justify-between">
                      <span>Page {cite.page}</span>
                      <span className="text-sov-orange">Verified verbatim</span>
                    </div>
                    <div className="text-sov-text-secondary">"{cite.quote}"</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function FileTextIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round" className="mx-auto text-sov-border">
      <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"></path>
      <polyline points="14 2 14 8 20 8"></polyline>
      <line x1="16" y1="13" x2="8" y2="13"></line>
      <line x1="16" y1="17" x2="8" y2="17"></line>
      <line x1="10" y1="9" x2="8" y2="9"></line>
    </svg>
  );
}
