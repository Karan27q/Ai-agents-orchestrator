import React, { useState } from 'react';
import { API_URL } from '../config.js';
import { ShieldCheck, Mail, Lock, Building, ArrowRight, UserPlus, LogIn } from 'lucide-react';

export function AuthView({ setToken }) {
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [orgName, setOrgName] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      if (isLogin) {
        // Log in
        const res = await fetch(`${API_URL}/auth/login`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Login failed');
        setToken(data.access_token);
      } else {
        // Register
        const res = await fetch(`${API_URL}/auth/register`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            email,
            password,
            organization_name: orgName
          })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Registration failed');
        // Auto-login after registration
        const loginRes = await fetch(`${API_URL}/auth/login`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password })
        });
        const loginData = await loginRes.json();
        if (!loginRes.ok) throw new Error('Auto-login failed');
        setToken(loginData.access_token);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex items-center justify-center min-h-screen px-4">
      {/* Background decorations */}
      <div className="absolute w-96 h-96 bg-indigo-600/10 rounded-full blur-3xl -top-12 -left-12"></div>
      <div className="absolute w-96 h-96 bg-purple-600/10 rounded-full blur-3xl -bottom-12 -right-12"></div>

      <div className="w-full max-w-md glass rounded-2xl p-8 glow-indigo relative z-10 animate-float">
        <div className="text-center mb-8">
          <div className="inline-flex p-3 rounded-xl bg-indigo-500/10 text-indigo-400 mb-4">
            <ShieldCheck className="w-8 h-8" />
          </div>
          <h2 className="text-3xl font-extrabold text-white tracking-tight">
            {isLogin ? 'Welcome Back' : 'Create Account'}
          </h2>
          <p className="text-zinc-400 mt-2 text-sm">
            {isLogin ? 'Sign in to orchestrate your AI agents' : 'Set up your lightweight AI automation workspace'}
          </p>
        </div>

        {error && (
          <div className="mb-6 p-4 bg-red-950/40 border border-red-500/20 text-red-300 rounded-lg text-sm">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-zinc-400 mb-2">Email Address</label>
            <div className="relative">
              <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-zinc-400">
                <Mail className="w-4 h-4" />
              </span>
              <input
                type="email"
                required
                value={email}
                onChange={e => setEmail(e.target.value)}
                className="w-full pl-10 pr-4 py-2.5 bg-zinc-950/40 border border-zinc-800 rounded-xl focus:border-indigo-500 focus:outline-none text-white text-sm"
                placeholder="you@example.com"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-zinc-400 mb-2">Password</label>
            <div className="relative">
              <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-zinc-400">
                <Lock className="w-4 h-4" />
              </span>
              <input
                type="password"
                required
                value={password}
                onChange={e => setPassword(e.target.value)}
                className="w-full pl-10 pr-4 py-2.5 bg-zinc-950/40 border border-zinc-800 rounded-xl focus:border-indigo-500 focus:outline-none text-white text-sm"
                placeholder="••••••••"
              />
            </div>
          </div>

          {!isLogin && (
            <>
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-zinc-400 mb-2">Organization Name</label>
                <div className="relative">
                  <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-zinc-400">
                    <Building className="w-4 h-4" />
                  </span>
                  <input
                    type="text"
                    required
                    value={orgName}
                    onChange={e => setOrgName(e.target.value)}
                    className="w-full pl-10 pr-4 py-2.5 bg-zinc-950/40 border border-zinc-800 rounded-xl focus:border-indigo-500 focus:outline-none text-white text-sm"
                    placeholder="Acme Corp"
                  />
                </div>
                <p className="text-[11px] text-zinc-500 mt-2">
                  You will be the Organization Admin of this workspace.
                </p>
              </div>
            </>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full flex items-center justify-center gap-2 py-3 px-4 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold rounded-xl text-sm transition-colors duration-200 shadow-lg shadow-indigo-600/20 disabled:opacity-50"
          >
            {loading ? (
              <span className="border-2 border-white/20 border-t-white rounded-full w-4 h-4 animate-spin"></span>
            ) : isLogin ? (
              <>
                <span>Sign In</span>
                <LogIn className="w-4 h-4" />
              </>
            ) : (
              <>
                <span>Create Account</span>
                <UserPlus className="w-4 h-4" />
              </>
            )}
          </button>
        </form>

        <div className="mt-8 pt-6 border-t border-zinc-800/80 text-center text-sm">
          <button
            onClick={() => setIsLogin(!isLogin)}
            className="text-indigo-400 hover:text-indigo-300 font-medium inline-flex items-center gap-1 transition-colors"
          >
            {isLogin ? "Don't have an account? Sign up" : 'Already have an account? Sign in'}
            <ArrowRight className="w-3 h-3" />
          </button>
        </div>
      </div>
    </div>
  );
}
