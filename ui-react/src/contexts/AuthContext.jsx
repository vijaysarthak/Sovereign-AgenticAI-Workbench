import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { fetchAPI } from '../api/client';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [principal, setPrincipal] = useState(null);
  const [loading, setLoading] = useState(true);
  const [sponsoredCompartments, setSponsoredCompartments] = useState([]);

  // Sponsors aren't admins, so without this the UI has no way to know a
  // user may grant/revoke compartments (and no link to the page that does it).
  useEffect(() => {
    if (!principal) {
      setSponsoredCompartments([]);
      return;
    }
    fetchAPI('/grants/mine')
      .then((res) => (res.ok ? res.json() : { sponsored_compartments: [] }))
      .then((data) => setSponsoredCompartments(data.sponsored_compartments || []))
      .catch(() => setSponsoredCompartments([]));
  }, [principal]);

  const checkAuth = useCallback(async () => {
    try {
      const res = await fetchAPI('/me');
      if (res.ok) {
        const data = await res.json();
        setPrincipal(data);
      } else {
        setPrincipal(null);
      }
    } catch {
      setPrincipal(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  const login = async (person_id, password) => {
    const res = await fetchAPI('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ person_id, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Authentication failed' }));
      throw new Error(err.detail || 'Authentication failed');
    }
    const data = await res.json();
    if (data.must_change_password) {
      return { mustChangePassword: true, person_id };
    }
    setPrincipal(data.principal);
    return { mustChangePassword: false };
  };

  const changePassword = async (old_password, new_password) => {
    const res = await fetchAPI('/auth/change-password', {
      method: 'POST',
      body: JSON.stringify({ old_password, new_password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Password change failed' }));
      throw new Error(err.detail || 'Password change failed');
    }
    // Re-check auth to get principal
    await checkAuth();
  };

  const logout = async () => {
    try {
      await fetchAPI('/auth/logout', { method: 'POST' });
    } finally {
      setPrincipal(null);
    }
  };

  return (
    <AuthContext.Provider value={{ principal, loading, login, logout, changePassword, checkAuth, sponsoredCompartments }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
