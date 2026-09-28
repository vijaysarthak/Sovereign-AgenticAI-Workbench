import React from 'react';
import { Server, Database, HardDrive, Globe } from 'lucide-react';

export default function SystemStatus({ documentCount = 0 }) {
  const statuses = [
    { icon: Server, title: 'Inference Node', status: 'In Service', detail: 'localhost:11434' },
    { icon: Database, title: 'Knowledge Base', status: 'Indexed', detail: `${documentCount} documents` },
    { icon: HardDrive, title: 'Storage', status: 'Available', detail: '40 GB free' },
    { icon: Globe, title: 'API Server', status: 'Healthy', detail: 'localhost:8080' },
  ];

  return (
    <div className="bg-sov-card border border-sov-border rounded-xl p-5 mb-6">
      <div className="flex items-center gap-3 mb-5">
        <div className="relative flex h-3 w-3">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-sov-green opacity-75"></span>
          <span className="relative inline-flex rounded-full h-3 w-3 bg-sov-green"></span>
        </div>
        <div>
          <h3 className="font-semibold text-sov-text-primary">System Status</h3>
          <p className="text-xs text-sov-green">All Systems Operational</p>
        </div>
      </div>

      <div className="space-y-4">
        {statuses.map((item, idx) => {
          const Icon = item.icon;
          return (
            <div key={idx} className="flex items-start gap-3">
              <div className="p-2 bg-sov-sidebar rounded text-sov-text-secondary">
                <Icon size={16} />
              </div>
              <div>
                <div className="text-sm font-medium text-sov-text-primary">{item.title}</div>
                <div className="text-xs flex gap-2 mt-0.5">
                  <span className="text-sov-green">{item.status}</span>
                  <span className="text-sov-text-muted">•</span>
                  <span className="text-sov-text-secondary">{item.detail}</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
