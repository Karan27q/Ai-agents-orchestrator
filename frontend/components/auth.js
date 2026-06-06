import React, { useState } from 'react';
import { API_URL } from '../app.js';
import { ShieldCheck, Mail, Lock, Building, ArrowRight, UserPlus, LogIn } from 'lucide-react';

export function AuthView({ setToken }) {
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [orgName, setOrgName] = useState('');
  const [role, setRole] = useState('Workflow Developer'); // Super Admin, Org Admin, Research Manager, Workflow Developer, Viewer
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
            organization_name: orgName,
            role: role
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
    <div class="flex items-center justify-center min-h-screen px-4">
      {/* Background decorations */}
      <div class="absolute w-96 h-96 bg-indigo-600/10 rounded-full blur-3xl -top-12 -left-12"></div>
      <div class="absolute w-96 h-96 bg-purple-600/10 rounded-full blur-3xl -bottom-12 -right-12"></div>

      <div class="w-full max-w-md glass rounded-2xl p-8 glow-indigo relative z-10 animate-float">
        <div class="text-center mb-8">
          <div class="inline-flex p-3 rounded-xl bg-indigo-500/10 text-indigo-400 mb-4">
            <ShieldCheck class="w-8 h-8" />
          </div>
          <h2 class="text-3xl font-extrabold text-white tracking-tight">
            {isLogin ? 'Welcome Back' : 'Create Account'}
          </h2>
          <p class="text-zinc-400 mt-2 text-sm">
            {isLogin ? 'Sign in to orchestrate your AI agents' : 'Set up your lightweight AI automation workspace'}
          </p>
        </div>

        {error && (
          <div class="mb-6 p-4 bg-red-950/40 border border-red-500/20 text-red-300 rounded-lg text-sm">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} class="space-y-5">
          <div>
            <label class="block text-xs font-semibold uppercase tracking-wider text-zinc-400 mb-2">Email Address</label>
            <div class="relative">
              <span class="absolute inset-y-0 left-0 pl-3 flex items-center text-zinc-400">
                <Mail class="w-4 h-4" />
              </span>
              <input
                type="email"
                required
                value={email}
                onChange={e => setEmail(e.target.value)}
                class="w-full pl-10 pr-4 py-2.5 bg-zinc-950/40 border border-zinc-800 rounded-xl focus:border-indigo-500 focus:outline-none text-white text-sm"
                placeholder="you@example.com"
              />
            </div>
          </div>

          <div>
            <label class="block text-xs font-semibold uppercase tracking-wider text-zinc-400 mb-2">Password</label>
            <div class="relative">
              <span class="absolute inset-y-0 left-0 pl-3 flex items-center text-zinc-400">
                <Lock class="w-4 h-4" />
              </span>
              <input
                type="password"
                required
                value={password}
                onChange={e => setPassword(e.target.value)}
                class="w-full pl-10 pr-4 py-2.5 bg-zinc-950/40 border border-zinc-800 rounded-xl focus:border-indigo-500 focus:outline-none text-white text-sm"
                placeholder="••••••••"
              />
            </div>
          </div>

          {!isLogin && (
            <>
              <div>
                <label class="block text-xs font-semibold uppercase tracking-wider text-zinc-400 mb-2">Organization Name</label>
                <div class="relative">
                  <span class="absolute inset-y-0 left-0 pl-3 flex items-center text-zinc-400">
                    <Building class="w-4 h-4" />
                  </span>
                  <input
                    type="text"
                    required
                    value={orgName}
                    onChange={e => setOrgName(e.target.value)}
                    class="w-full pl-10 pr-4 py-2.5 bg-zinc-950/40 border border-zinc-800 rounded-xl focus:border-indigo-500 focus:outline-none text-white text-sm"
                    placeholder="Acme Corp"
                  />
                </div>
              </div>

              <div>
                <label class="block text-xs font-semibold uppercase tracking-wider text-zinc-400 mb-2">Desired Role</label>
                <select
                  value={role}
                  onChange={e => setRole(e.target.value)}
                  class="w-full px-4 py-2.5 bg-zinc-950/40 border border-zinc-800 rounded-xl focus:border-indigo-500 focus:outline-none text-white text-sm"
                >
                  <option value="Org Admin" class="bg-zinc-950">Organization Admin</option>
                  <option value="Research Manager" class="bg-zinc-950">Research Manager</option>
                  <option value="Workflow Developer" class="bg-zinc-950">Workflow Developer</option>
                  <option value="Viewer" class="bg-zinc-950">Viewer</option>
                </select>
              </div>
            </>
          )}

          <button
            type="submit"
            disabled={loading}
            class="w-full flex items-center justify-center gap-2 py-3 px-4 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold rounded-xl text-sm transition-colors duration-200 shadow-lg shadow-indigo-600/20 disabled:opacity-50"
          >
            {loading ? (
              <span class="border-2 border-white/20 border-t-white rounded-full w-4 h-4 animate-spin"></span>
            ) : isLogin ? (
              <>
                <span>Sign In</span>
                <LogIn class="w-4 h-4" />
              </>
            ) : (
              <>
                <span>Create Account</span>
                <UserPlus class="w-4 h-4" />
              </>
            )}
          </button>
        </form>

        <div class="mt-8 pt-6 border-t border-zinc-800/80 text-center text-sm">
          <button
            onClick={() => setIsLogin(!isLogin)}
            class="text-indigo-400 hover:text-indigo-300 font-medium inline-flex items-center gap-1 transition-colors"
          >
            {isLogin ? "Don't have an account? Sign up" : 'Already have an account? Sign in'}
            <ArrowRight class="w-3 h-3" />
          </button>
        </div>
      </div>
    </div>
  );
}
