import React, { useState, useEffect } from 'react';
import ReactDOM from 'react-dom/client';
import { AuthView } from './components/auth.js';
import { Sidebar, TopNav } from './components/dashboard.js';
import { HomeView } from './components/home.js';
import { WorkflowsView } from './components/workflows.js';
import { ResearchView } from './components/research.js';
import { FilesView } from './components/files.js';
import { SearchView } from './components/search.js';

// Base API URL
export const API_URL = window.location.origin.includes('localhost') 
  ? 'http://localhost:8000/api/v1' 
  : window.location.origin + '/api/v1';

function App() {
  const [token, setToken] = useState(localStorage.getItem('token') || '');
  const [user, setUser] = useState(null);
  const [currentView, setCurrentView] = useState('dashboard');
  const [notifications, setNotifications] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(!!token);

  // Configure global authorization headers
  const apiFetch = async (endpoint, options = {}) => {
    const headers = {
      'Content-Type': 'application/json',
      ...options.headers,
    };
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    const response = await fetch(`${API_URL}${endpoint}`, {
      ...options,
      headers,
    });
    if (response.status === 401) {
      // Auto-logout on unauthorized
      handleLogout();
      throw new Error('Unauthorized');
    }
    if (!response.ok) {
      const contentType = response.headers.get('content-type') || '';
      if (contentType.includes('application/json')) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || errData.message || 'API request failed');
      }

      const errorText = await response.text().catch(() => '');
      const trimmed = errorText.trim();
      throw new Error(trimmed || 'API request failed');
    }
    return response.json();
  };

  useEffect(() => {
    if (token) {
      localStorage.setItem('token', token);
      // Fetch user profile
      apiFetch('/auth/me')
        .then(userData => {
          setUser(userData);
          setLoading(false);
          fetchNotifications();
        })
        .catch(err => {
          console.error('Failed to fetch profile:', err);
          handleLogout();
          setLoading(false);
        });
    } else {
      localStorage.removeItem('token');
      setUser(null);
      setLoading(false);
    }
  }, [token]);

  const handleLogout = () => {
    setToken('');
    setUser(null);
    localStorage.removeItem('token');
  };

  const fetchNotifications = async () => {
    try {
      const data = await apiFetch('/notifications');
      setNotifications(data);
    } catch (err) {
      console.error('Failed to load notifications:', err);
    }
  };

  const markNotificationsRead = async () => {
    const unread = notifications.filter(n => !n.is_read).map(n => n.id);
    if (unread.length === 0) return;
    try {
      await apiFetch('/notifications/read', {
        method: 'POST',
        body: JSON.stringify({ notification_ids: unread })
      });
      fetchNotifications();
    } catch (err) {
      console.error(err);
    }
  };

  // Poll notifications every 10 seconds for live updates
  useEffect(() => {
    if (!token) return;
    const interval = setInterval(fetchNotifications, 10000);
    return () => clearInterval(interval);
  }, [token]);

  if (loading) {
    return (
      <div class="flex items-center justify-center min-h-screen">
        <div class="relative w-16 h-16">
          <div class="absolute border-4 border-indigo-500/20 border-t-indigo-500 rounded-full w-full h-full animate-spin"></div>
        </div>
      </div>
    );
  }

  if (!token) {
    return <AuthView setToken={setToken} />;
  }

  const renderActiveView = () => {
    switch (currentView) {
      case 'dashboard':
        return <HomeView apiFetch={apiFetch} user={user} setCurrentView={setCurrentView} />;
      case 'workflows':
        return <WorkflowsView apiFetch={apiFetch} user={user} />;
      case 'research':
        return <ResearchView apiFetch={apiFetch} user={user} />;
      case 'files':
        return <FilesView apiFetch={apiFetch} user={user} />;
      case 'search':
        return <SearchView apiFetch={apiFetch} query={searchQuery} />;
      default:
        return <HomeView apiFetch={apiFetch} user={user} setCurrentView={setCurrentView} />;
    }
  };

  return (
    <div class="flex min-h-screen overflow-hidden">
      {/* Sidebar Navigation */}
      <Sidebar currentView={currentView} setCurrentView={setCurrentView} handleLogout={handleLogout} user={user} />

      {/* Main Content Area */}
      <div class="flex-1 flex flex-col min-w-0">
        <TopNav 
          user={user} 
          notifications={notifications} 
          markNotificationsRead={markNotificationsRead}
          searchQuery={searchQuery}
          setSearchQuery={setSearchQuery}
          setCurrentView={setCurrentView}
        />
        
        <main class="flex-1 overflow-y-auto p-6 md:p-8">
          {renderActiveView()}
        </main>
      </div>
    </div>
  );
}

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<App />);
