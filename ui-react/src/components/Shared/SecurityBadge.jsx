import React from 'react';

const SecurityBadge = ({ tier = 'public', compartments = [] }) => {
  const getTierColors = (t) => {
    switch (t?.toLowerCase()) {
      case 'public': return 'bg-sov-green/10 text-sov-green border-sov-green';
      case 'internal': return 'bg-blue-500/10 text-blue-500 border-blue-500';
      case 'confidential': return 'bg-sov-amber/10 text-sov-amber border-sov-amber';
      case 'secret': return 'bg-sov-red/10 text-sov-red border-sov-red';
      default: return 'bg-sov-bg text-sov-text-secondary border-sov-border';
    }
  };

  return (
    <div className="flex flex-wrap gap-2 items-center">
      <span className={`px-2 py-1 text-xs font-mono rounded-full border ${getTierColors(tier)}`}>
        {tier.toUpperCase()}
      </span>
      {compartments?.map((comp, idx) => (
        <span key={idx} className="px-2 py-1 text-xs font-mono rounded-full border bg-purple-500/10 text-purple-400 border-purple-500">
          {comp.toUpperCase()}
        </span>
      ))}
    </div>
  );
};

export default SecurityBadge;
