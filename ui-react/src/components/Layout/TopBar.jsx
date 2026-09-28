import React, { useState, useRef, useEffect } from 'react';
import { Search, Bell, ChevronDown, CheckCircle, User, Settings, LogOut } from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { Link } from 'react-router-dom';

const TopBar = () => {
  const { principal, logout, sponsoredCompartments } = useAuth();
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const dropdownRef = useRef(null);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const initials = principal?.name
    ? principal.name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase()
    : 'U';

  const userName = principal?.name || 'User';

  return (
    <div className="h-14 w-full bg-transparent flex items-center justify-between px-6 z-40 relative">
      <div className="flex-1 max-w-xl relative">
        <div className="relative flex items-center w-full h-9 rounded-md bg-sov-card border border-sov-border-light focus-within:border-sov-orange transition-colors">
          <Search className="absolute left-3 h-4 w-4 text-sov-text-muted" />
          <input
            type="text"
            placeholder="Search documents, models, or ask anything..."
            className="w-full h-full bg-transparent pl-9 pr-12 text-sm text-sov-text-primary placeholder-sov-text-muted focus:outline-none"
          />
          <div className="absolute right-2 flex items-center">
            <kbd className="hidden sm:inline-block px-1.5 py-0.5 text-[10px] font-mono text-sov-text-muted bg-sov-bg border border-sov-border rounded">
              Ctrl+K
            </kbd>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-6 ml-4">
        <div className="hidden lg:flex items-center gap-2 text-xs text-sov-green bg-sov-green/10 px-3 py-1.5 rounded-full border border-sov-green/20">
          <CheckCircle className="h-3.5 w-3.5" />
          <span className="font-medium tracking-wide">On-premise • Air-gapped • Your data, your control</span>
        </div>

        <button className="relative p-2 text-sov-text-secondary hover:text-sov-text-primary transition-colors">
          <Bell className="h-5 w-5" />
          <span className="absolute top-1.5 right-1.5 h-2 w-2 rounded-full bg-sov-orange ring-2 ring-sov-bg"></span>
        </button>

        <div className="relative" ref={dropdownRef}>
          <button
            onClick={() => setIsDropdownOpen(!isDropdownOpen)}
            className="flex items-center gap-3 p-1 rounded-full hover:bg-sov-card transition-colors focus:outline-none"
          >
            <div className="h-8 w-8 rounded-full bg-sov-orange flex items-center justify-center text-sm font-bold text-white shadow-sm">
              {initials}
            </div>
            <div className="hidden md:block text-left">
              <p className="text-sm font-medium text-sov-text-primary leading-none">{userName}</p>
            </div>
            <ChevronDown className={`h-4 w-4 text-sov-text-secondary transition-transform duration-200 ${isDropdownOpen ? 'rotate-180' : ''}`} />
          </button>

          {isDropdownOpen && (
            <div className="absolute right-0 mt-2 w-48 bg-sov-card border border-sov-border rounded-md shadow-lg py-1 z-50">
              <div className="px-4 py-2 border-b border-sov-border-light mb-1">
                <p className="text-sm font-medium text-sov-text-primary">{userName}</p>
                <p className="text-xs text-sov-text-muted truncate">{principal?.person_id} • {principal?.job_title}</p>
              </div>
              <Link to="/profile" onClick={() => setIsDropdownOpen(false)} className="flex items-center gap-2 px-4 py-2 text-sm text-sov-text-secondary hover:bg-sov-card-hover hover:text-sov-text-primary">
                <User className="h-4 w-4" /> Profile
              </Link>
              {(principal?.is_admin || sponsoredCompartments.length > 0) && (
                <Link to="/admin" onClick={() => setIsDropdownOpen(false)} className="flex items-center gap-2 px-4 py-2 text-sm text-sov-text-secondary hover:bg-sov-card-hover hover:text-sov-text-primary">
                  <Settings className="h-4 w-4" /> {principal?.is_admin ? 'Administration' : 'Compartment Access'}
                </Link>
              )}
              <div className="border-t border-sov-border-light mt-1 pt-1">
                <button
                  onClick={logout}
                  className="w-full flex items-center gap-2 px-4 py-2 text-sm text-sov-red hover:bg-sov-card-hover transition-colors"
                >
                  <LogOut className="h-4 w-4" /> Sign Out
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default TopBar;
