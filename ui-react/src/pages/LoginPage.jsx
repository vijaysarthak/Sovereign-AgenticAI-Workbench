import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { Zap, Eye, EyeOff, ShieldAlert, Lock, User, AlertCircle } from 'lucide-react';

const LoginPage = () => {
  const navigate = useNavigate();
  const { login, changePassword } = useAuth();

  const [designationId, setDesignationId] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const [needsPasswordChange, setNeedsPasswordChange] = useState(false);
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showNewPassword, setShowNewPassword] = useState(false);

  const handleLogin = async (e) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      const result = await login(designationId, password);
      if (result?.mustChangePassword) {
        setNeedsPasswordChange(true);
      } else {
        navigate('/workbench');
      }
    } catch (err) {
      setError(err.message || 'Authentication failed. Please verify your credentials.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleChangePassword = async (e) => {
    e.preventDefault();
    setError('');

    if (newPassword !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    if (newPassword.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }

    setIsLoading(true);
    try {
      await changePassword(password, newPassword);
      navigate('/workbench');
    } catch (err) {
      setError(err.message || 'Failed to update password.');
    } finally {
      setIsLoading(false);
    }
  };

  // Simple password strength calculation
  const getStrength = (pass) => {
    let strength = 0;
    if (pass.length > 7) strength += 25;
    if (/[A-Z]/.test(pass)) strength += 25;
    if (/[0-9]/.test(pass)) strength += 25;
    if (/[^A-Za-z0-9]/.test(pass)) strength += 25;
    return strength;
  };

  const strength = getStrength(newPassword);

  return (
    <div className="min-h-screen bg-sov-bg flex flex-col items-center justify-center relative overflow-hidden">
      {/* Background Effects */}
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-sov-orange/5 rounded-full blur-[128px] pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-sov-orange-dark/5 rounded-full blur-[128px] pointer-events-none" />
      
      <div className="z-10 w-full max-w-md p-8 bg-sov-card border border-sov-border shadow-2xl rounded-xl">
        <div className="flex flex-col items-center mb-8">
          <div className="h-16 w-16 bg-sov-bg border border-sov-border-light rounded-2xl flex items-center justify-center mb-4 shadow-inner relative overflow-hidden">
             <div className="absolute inset-0 bg-gradient-to-br from-sov-orange/20 to-transparent opacity-50" />
             <Zap className="h-8 w-8 text-sov-orange relative z-10" />
          </div>
          <h1 className="text-2xl font-bold text-sov-text-primary tracking-wide">SovereignAI</h1>
          <p className="text-sm font-mono text-sov-text-muted mt-1 uppercase tracking-widest">Secure Authentication</p>
        </div>

        {error && (
          <div className="mb-6 p-3 bg-sov-red/10 border border-sov-red/20 rounded flex items-start gap-2 text-sov-red text-sm">
            <AlertCircle className="h-5 w-5 shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        {!needsPasswordChange ? (
          <form onSubmit={handleLogin} className="space-y-5">
            <div className="space-y-1">
              <label className="text-xs font-medium text-sov-text-secondary uppercase tracking-wider">Employee Designation ID</label>
              <div className="relative">
                <User className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-sov-text-muted" />
                <input
                  type="text"
                  required
                  value={designationId}
                  onChange={(e) => setDesignationId(e.target.value)}
                  className="w-full bg-sov-bg border border-sov-border-light text-sov-text-primary rounded px-10 py-2.5 focus:outline-none focus:border-sov-orange focus:ring-1 focus:ring-sov-orange transition-all placeholder:text-sov-text-muted/50"
                  placeholder="e.g. EMP-2049"
                />
              </div>
            </div>

            <div className="space-y-1">
              <label className="text-xs font-medium text-sov-text-secondary uppercase tracking-wider">Passphrase</label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-sov-text-muted" />
                <input
                  type={showPassword ? 'text' : 'password'}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full bg-sov-bg border border-sov-border-light text-sov-text-primary rounded px-10 py-2.5 focus:outline-none focus:border-sov-orange focus:ring-1 focus:ring-sov-orange transition-all placeholder:text-sov-text-muted/50"
                  placeholder="••••••••••••"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-sov-text-muted hover:text-sov-text-primary transition-colors focus:outline-none"
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={isLoading}
              className="w-full bg-sov-orange hover:bg-sov-orange-dark text-white font-medium py-2.5 rounded transition-colors focus:outline-none focus:ring-2 focus:ring-sov-orange/50 focus:ring-offset-2 focus:ring-offset-sov-card disabled:opacity-50 disabled:cursor-not-allowed mt-2"
            >
              {isLoading ? 'Authenticating...' : 'Authenticate Session'}
            </button>
          </form>
        ) : (
          <form onSubmit={handleChangePassword} className="space-y-5 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="bg-sov-amber/10 border border-sov-amber/20 rounded p-3 flex items-start gap-3 mb-2">
              <ShieldAlert className="h-5 w-5 text-sov-amber shrink-0 mt-0.5" />
              <div>
                <h4 className="text-sm font-medium text-sov-amber">First-Time Sign-In Detected</h4>
                <p className="text-xs text-sov-amber/80 mt-1">Enterprise security policy requires you to establish a secure, personalized passphrase before continuing.</p>
              </div>
            </div>

            <div className="space-y-1">
              <label className="text-xs font-medium text-sov-text-secondary uppercase tracking-wider">New Passphrase</label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-sov-text-muted" />
                <input
                  type={showNewPassword ? 'text' : 'password'}
                  required
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  className="w-full bg-sov-bg border border-sov-border-light text-sov-text-primary rounded px-10 py-2.5 focus:outline-none focus:border-sov-orange focus:ring-1 focus:ring-sov-orange transition-all placeholder:text-sov-text-muted/50"
                  placeholder="Enter new passphrase"
                />
                <button
                  type="button"
                  onClick={() => setShowNewPassword(!showNewPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-sov-text-muted hover:text-sov-text-primary transition-colors focus:outline-none"
                >
                  {showNewPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
              {/* Strength Meter */}
              {newPassword && (
                <div className="pt-2">
                  <div className="h-1 w-full bg-sov-bg rounded overflow-hidden flex">
                    <div className={`h-full transition-all duration-300 ${
                      strength < 50 ? 'bg-sov-red w-1/4' : 
                      strength < 75 ? 'bg-sov-amber w-2/4' : 
                      strength < 100 ? 'bg-sov-green/70 w-3/4' : 
                      'bg-sov-green w-full'
                    }`} />
                  </div>
                </div>
              )}
            </div>

            <div className="space-y-1">
              <label className="text-xs font-medium text-sov-text-secondary uppercase tracking-wider">Confirm Passphrase</label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-sov-text-muted" />
                <input
                  type={showNewPassword ? 'text' : 'password'}
                  required
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="w-full bg-sov-bg border border-sov-border-light text-sov-text-primary rounded px-10 py-2.5 focus:outline-none focus:border-sov-orange focus:ring-1 focus:ring-sov-orange transition-all placeholder:text-sov-text-muted/50"
                  placeholder="Confirm new passphrase"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={isLoading || !newPassword || !confirmPassword}
              className="w-full bg-sov-orange hover:bg-sov-orange-dark text-white font-medium py-2.5 rounded transition-colors focus:outline-none focus:ring-2 focus:ring-sov-orange/50 focus:ring-offset-2 focus:ring-offset-sov-card disabled:opacity-50 disabled:cursor-not-allowed mt-2"
            >
              {isLoading ? 'Updating...' : 'Set Password & Continue'}
            </button>
          </form>
        )}

        <div className="mt-8 pt-6 border-t border-sov-border-light">
          <p className="text-[10px] leading-relaxed text-sov-text-muted text-center font-mono uppercase">
            Self-signup is prohibited. All enterprise access credentials are provisioned by System Administrators.
          </p>
        </div>
      </div>
    </div>
  );
};

export default LoginPage;
