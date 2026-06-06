import React, { useState } from 'react';
import { 
  LayoutDashboard, GitBranch, Search, FileText, Bell, LogOut, 
  Settings, User, Check, Shield, Database, BrainCircuit
} from 'lucide-react';

export function Sidebar({ currentView, setCurrentView, handleLogout, user }) {
  const menuItems = [
    { id: 'dashboard', name: 'Dashboard', icon: LayoutDashboard },
    { id: 'workflows', name: 'Workflows', icon: GitBranch },
    { id: 'research', name: 'Multi-Agent Research', icon: BrainCircuit },
    { id: 'files', name: 'File Indexer', icon: FileText },
  ];

  return (
    <aside class="w-64 glass border-r border-zinc-800/80 flex flex-col h-screen shrink-0">
      {/* Brand Logo */}
      <div class="h-16 flex items-center px-6 border-b border-zinc-800/80 gap-3">
        <div class="bg-indigo-500/10 p-1.5 rounded-lg text-indigo-400">
          <BrainCircuit class="w-6 h-6 animate-pulse" />
        </div>
        <span class="font-extrabold text-lg text-white bg-clip-text text-transparent bg-gradient-to-r from-white to-zinc-400">
          AI Orchestrator
        </span>
      </div>

      {/* Navigation */}
      <nav class="flex-1 px-4 py-6 space-y-1.5 overflow-y-auto">
        {menuItems.map(item => {
          const Icon = item.icon;
          const active = currentView === item.id;
          return (
            <button
              key={item.id}
              onClick={() => setCurrentView(item.id)}
              class={`w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all duration-200 ${
                active 
                  ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/10' 
                  : 'text-zinc-400 hover:text-white hover:bg-zinc-800/40'
              }`}
            >
              <Icon class="w-4.5 h-4.5" />
              <span>{item.name}</span>
            </button>
          );
        })}
      </nav>

      {/* User Footer Profile */}
      <div class="p-4 border-t border-zinc-800/80 flex flex-col gap-3">
        <div class="flex items-center gap-3 px-2 py-1.5">
          <div class="w-9 h-9 rounded-full bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400 font-semibold uppercase">
            {user?.email?.slice(0, 2)}
          </div>
          <div class="min-w-0 flex-1">
            <p class="text-xs font-semibold text-white truncate">{user?.email}</p>
            <p class="text-[10px] text-indigo-400 font-medium mt-0.5 inline-flex items-center gap-1 bg-indigo-500/10 px-1.5 py-0.5 rounded-md border border-indigo-500/10">
              <Shield class="w-2.5 h-2.5" />
              {user?.role}
            </p>
          </div>
        </div>

        <button
          onClick={handleLogout}
          class="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl border border-zinc-800 hover:bg-red-950/20 hover:border-red-900/30 text-zinc-400 hover:text-red-400 text-xs font-semibold transition-all duration-200"
        >
          <LogOut class="w-3.5 h-3.5" />
          <span>Sign Out</span>
        </button>
      </div>
    </aside>
  );
}

export function TopNav({ user, notifications, markNotificationsRead, searchQuery, setSearchQuery, setCurrentView }) {
  const [showNotifDropdown, setShowNotifDropdown] = useState(false);
  const unreadCount = notifications.filter(n => !n.is_read).length;

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      setCurrentView('search');
    }
  };

  const handleNotifClick = () => {
    setShowNotifDropdown(!showNotifDropdown);
    if (!showNotifDropdown) {
      // Mark as read after opening dropdown
      markNotificationsRead();
    }
  };

  return (
    <header class="h-16 border-b border-zinc-800/80 glass flex items-center justify-between px-8 z-20 relative">
      {/* Global Search Bar */}
      <form onSubmit={handleSearchSubmit} class="w-full max-w-md">
        <div class="relative">
          <span class="absolute inset-y-0 left-0 pl-3 flex items-center text-zinc-400">
            <Search class="w-4 h-4" />
          </span>
          <input
            type="search"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            placeholder="Search workflows, documents, semantic memories..."
            class="w-full pl-9 pr-4 py-1.5 bg-zinc-900/50 border border-zinc-800 rounded-xl focus:border-indigo-500 focus:outline-none text-zinc-100 text-sm placeholder-zinc-500"
          />
        </div>
      </form>

      {/* Actions */}
      <div class="flex items-center gap-4">
        {/* Connection status indicator */}
        <div class="flex items-center gap-2 border border-zinc-800 px-3 py-1 rounded-full bg-zinc-950/30">
          <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
          <span class="text-[10px] font-semibold text-emerald-400 uppercase tracking-wider">Sync: Online</span>
        </div>

        {/* Notifications Icon with Dropdown */}
        <div class="relative">
          <button 
            onClick={handleNotifClick}
            class="p-2 rounded-xl border border-zinc-800/80 text-zinc-400 hover:text-white hover:bg-zinc-800/40 relative transition-all duration-200"
          >
            <Bell class="w-4.5 h-4.5" />
            {unreadCount > 0 && (
              <span class="absolute -top-1 -right-1 bg-indigo-500 text-white font-extrabold text-[9px] w-4.5 h-4.5 flex items-center justify-center rounded-full border border-zinc-950 animate-bounce">
                {unreadCount}
              </span>
            )}
          </button>

          {showNotifDropdown && (
            <div class="absolute right-0 mt-3 w-80 glass rounded-xl border border-zinc-800/80 shadow-2xl p-4 z-50">
              <div class="flex items-center justify-between pb-3 border-b border-zinc-800/60 mb-2">
                <span class="text-xs font-bold text-white">Notifications</span>
                {unreadCount > 0 && (
                  <span class="text-[10px] text-zinc-400 bg-zinc-800 px-1.5 py-0.5 rounded">
                    {unreadCount} new
                  </span>
                )}
              </div>
              <div class="max-h-60 overflow-y-auto space-y-2 py-1">
                {notifications.length === 0 ? (
                  <p class="text-xs text-zinc-500 text-center py-4">No notifications yet</p>
                ) : (
                  notifications.map(notif => (
                    <div 
                      key={notif.id} 
                      class={`p-2.5 rounded-lg text-xs transition-colors duration-200 ${
                        notif.is_read ? 'bg-zinc-950/20 text-zinc-400' : 'bg-indigo-500/5 text-zinc-100 border border-indigo-500/10'
                      }`}
                    >
                      <div class="flex items-start justify-between gap-2">
                        <p class="leading-relaxed">{notif.message}</p>
                        {!notif.is_read && <Check class="w-3.5 h-3.5 text-indigo-400 shrink-0 mt-0.5" />}
                      </div>
                      <span class="text-[9px] text-zinc-600 block mt-1">
                        {new Date(notif.created_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
                      </span>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
