import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { 
  Zap, 
  LayoutDashboard, 
  ShieldCheck, 
  BookOpen, 
  Layers, 
  FileText, 
  FileOutput 
} from 'lucide-react';

const Sidebar = () => {
  const location = useLocation();

  const navItems = [
    { name: 'Workbench', path: '/workbench', icon: LayoutDashboard },
    { name: 'Sovereignty', path: '/sovereignty', icon: ShieldCheck },
    { name: 'Knowledge Base', path: '/knowledge-base', icon: BookOpen },
    { name: 'Models', path: '/models', icon: Layers },
  ];

  const subItems = [
    { name: 'Documents', path: '/documents', icon: FileText },
    { name: 'Generated Outputs', path: '/generated-outputs', icon: FileOutput },
  ];

  const isActive = (path) => location.pathname === path;

  return (
    <div className="fixed top-0 left-0 h-full w-56 bg-sov-sidebar border-r border-sov-border flex flex-col z-50">
      <div className="p-4 border-b border-sov-border-light">
        <div className="flex items-center gap-2 mb-1">
          <Zap className="text-sov-orange h-6 w-6" />
          <span className="font-bold text-lg text-sov-text-primary tracking-wide">SovereignAI</span>
        </div>
        <p className="text-xs text-sov-text-muted font-mono tracking-tight">Secure. Local. Industrial.</p>
      </div>

      <div className="flex-1 overflow-y-auto py-4">
        <nav className="space-y-1 px-2">
          {navItems.map((item) => (
            <Link
              key={item.path}
              to={item.path}
              className={`flex items-center gap-3 px-3 py-2 rounded-md transition-colors duration-200 ${
                isActive(item.path)
                  ? 'bg-sov-orange text-white'
                  : 'text-sov-text-secondary hover:bg-sov-card hover:text-sov-text-primary'
              }`}
            >
              <item.icon className="h-5 w-5" />
              <span className="text-sm font-medium">{item.name}</span>
            </Link>
          ))}
        </nav>

        <div className="my-4 mx-4 border-t border-sov-border"></div>

        <nav className="space-y-1 px-2">
          {subItems.map((item) => (
            <Link
              key={item.path}
              to={item.path}
              className={`flex items-center gap-3 px-3 py-2 rounded-md transition-colors duration-200 ${
                isActive(item.path)
                  ? 'bg-sov-orange text-white'
                  : 'text-sov-text-secondary hover:bg-sov-card hover:text-sov-text-primary'
              }`}
            >
              <item.icon className="h-5 w-5" />
              <span className="text-sm font-medium">{item.name}</span>
            </Link>
          ))}
        </nav>
      </div>

      <div className="mt-auto p-4 relative">
        <div className="absolute inset-0 bg-gradient-to-t from-sov-orange-dark/20 to-transparent pointer-events-none" />
        <div className="relative z-10 mb-4 p-3 bg-sov-card/50 border border-sov-border-light rounded backdrop-blur-sm">
          <p className="text-xs text-sov-text-secondary leading-relaxed">
            Powering safer industries with on-premise AI.
          </p>
        </div>
        <div className="text-xs text-sov-text-muted font-mono text-center relative z-10">
          SovereignAI v1.0.0
        </div>
      </div>
    </div>
  );
};

export default Sidebar;
