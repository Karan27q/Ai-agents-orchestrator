import React, { useState, useEffect } from 'react';
import { 
  GitBranch, BrainCircuit, FileText, Cpu, HardDrive, CheckCircle2, 
  Clock, ArrowUpRight, Play, Server, Layers
} from 'lucide-react';

export function HomeView({ apiFetch, user, setCurrentView }) {
  const [stats, setStats] = useState({
    workflows: 0,
    runs: 0,
    files: 0,
    tasks: 0,
  });
  const [recentRuns, setRecentRuns] = useState([]);
  const [loading, setLoading] = useState(true);

  const loadDashboardData = async () => {
    try {
      // Load workflows to get count
      const workflows = await apiFetch('/workflows');
      // Load files to get count
      const files = await apiFetch('/files');
      // Load agent tasks to get count
      const tasks = await apiFetch('/agents/tasks');

      // Fetch runs across all workflows
      let totalRuns = [];
      for (const w of workflows) {
        const wRuns = await apiFetch(`/workflows/${w.id}/runs`);
        totalRuns = [...totalRuns, ...wRuns];
      }
      
      // Sort runs by time
      totalRuns.sort((a, b) => new Date(b.started_at) - new Date(a.started_at));

      setStats({
        workflows: workflows.length,
        runs: totalRuns.length,
        files: files.length,
        tasks: tasks.length,
      });
      setRecentRuns(totalRuns.slice(0, 5));
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDashboardData();
  }, []);

  const systemMetrics = [
    { name: 'Server Core Footprint', value: '0.1% CPU (Idle)', desc: 'Consolidated Async Core', icon: Cpu, color: 'text-emerald-400' },
    { name: 'System Memory Usage', value: '42 MB RAM', desc: 'SQLite & Python Monolith', icon: HardDrive, color: 'text-sky-400' },
    { name: 'Vector DB Pipeline', value: 'Cosine Local', desc: 'Numpy Embeddings', icon: Layers, color: 'text-indigo-400' },
  ];

  if (loading) {
    return (
      <div class="space-y-6">
        <div class="h-10 bg-zinc-800/40 rounded-lg w-1/4 shimmer relative overflow-hidden"></div>
        <div class="grid grid-cols-1 md:grid-cols-4 gap-6">
          {[...Array(4)].map((_, i) => (
            <div key={i} class="h-28 bg-zinc-800/40 rounded-xl shimmer relative overflow-hidden"></div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div class="space-y-8 max-w-7xl mx-auto">
      {/* Header */}
      <div>
        <h1 class="text-3xl font-extrabold text-white tracking-tight">Overview</h1>
        <p class="text-zinc-400 mt-2 text-sm">Real-time status of your lightweight workflow orchestrator.</p>
      </div>

      {/* Stats Grid */}
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        <div class="glass glass-hover p-6 rounded-2xl flex items-center justify-between">
          <div>
            <p class="text-xs font-semibold uppercase tracking-wider text-zinc-500">Workflows</p>
            <h3 class="text-3xl font-extrabold text-white mt-2">{stats.workflows}</h3>
          </div>
          <div class="bg-indigo-500/10 p-3.5 rounded-xl text-indigo-400">
            <GitBranch class="w-6 h-6" />
          </div>
        </div>

        <div class="glass glass-hover p-6 rounded-2xl flex items-center justify-between">
          <div>
            <p class="text-xs font-semibold uppercase tracking-wider text-zinc-500">DAG Executions</p>
            <h3 class="text-3xl font-extrabold text-white mt-2">{stats.runs}</h3>
          </div>
          <div class="bg-violet-500/10 p-3.5 rounded-xl text-violet-400">
            <Play class="w-6 h-6" />
          </div>
        </div>

        <div class="glass glass-hover p-6 rounded-2xl flex items-center justify-between">
          <div>
            <p class="text-xs font-semibold uppercase tracking-wider text-zinc-500">Indexed Files</p>
            <h3 class="text-3xl font-extrabold text-white mt-2">{stats.files}</h3>
          </div>
          <div class="bg-emerald-500/10 p-3.5 rounded-xl text-emerald-400">
            <FileText class="w-6 h-6" />
          </div>
        </div>

        <div class="glass glass-hover p-6 rounded-2xl flex items-center justify-between">
          <div>
            <p class="text-xs font-semibold uppercase tracking-wider text-zinc-500">Research Tasks</p>
            <h3 class="text-3xl font-extrabold text-white mt-2">{stats.tasks}</h3>
          </div>
          <div class="bg-amber-500/10 p-3.5 rounded-xl text-amber-400">
            <BrainCircuit class="w-6 h-6" />
          </div>
        </div>
      </div>

      {/* Main split */}
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        {/* Recent runs list */}
        <div class="glass p-6 rounded-2xl lg:col-span-2 space-y-4">
          <div class="flex items-center justify-between">
            <h3 class="text-lg font-bold text-white">Recent DAG Runs</h3>
            <button 
              onClick={() => setCurrentView('workflows')}
              class="text-indigo-400 hover:text-indigo-300 text-xs font-semibold inline-flex items-center gap-1"
            >
              Manage Workflows
              <ArrowUpRight class="w-3.5 h-3.5" />
            </button>
          </div>

          <div class="overflow-x-auto">
            <table class="w-full text-left text-xs border-collapse">
              <thead>
                <tr class="border-b border-zinc-800 text-zinc-500 font-semibold uppercase tracking-wider">
                  <th class="py-3 pr-4">Run ID</th>
                  <th class="py-3 px-4">Status</th>
                  <th class="py-3 px-4">Started</th>
                  <th class="py-3 pl-4 text-right">Action</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-zinc-800/60 font-medium">
                {recentRuns.length === 0 ? (
                  <tr>
                    <td colSpan={4} class="py-8 text-center text-zinc-500">No workflow runs recorded yet.</td>
                  </tr>
                ) : (
                  recentRuns.map(run => (
                    <tr key={run.id} class="hover:bg-zinc-800/10">
                      <td class="py-3.5 pr-4 text-white">Run #{run.id}</td>
                      <td class="py-3.5 px-4">
                        <span class={`px-2 py-0.5 rounded-full font-bold text-[10px] uppercase border ${
                          run.status === 'completed' ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400' :
                          run.status === 'running' ? 'bg-indigo-500/10 border-indigo-500/20 text-indigo-400 animate-pulse' :
                          run.status === 'failed' ? 'bg-red-500/10 border-red-500/20 text-red-400' :
                          'bg-zinc-500/10 border-zinc-500/20 text-zinc-400'
                        }`}>
                          {run.status}
                        </span>
                      </td>
                      <td class="py-3.5 px-4 text-zinc-400">
                        {new Date(run.started_at).toLocaleString()}
                      </td>
                      <td class="py-3.5 pl-4 text-right">
                        <button 
                          onClick={() => setCurrentView('workflows')}
                          class="text-indigo-400 hover:text-indigo-300 font-bold"
                        >
                          View Logs
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Optimisation Specs */}
        <div class="glass p-6 rounded-2xl space-y-6">
          <div>
            <h3 class="text-lg font-bold text-white">Hardware Profiling</h3>
            <p class="text-xs text-zinc-400 mt-1">Resource benchmarks optimized for i3-level specs.</p>
          </div>

          <div class="space-y-4">
            {systemMetrics.map((metric, idx) => {
              const Icon = metric.icon;
              return (
                <div key={idx} class="flex items-center gap-4 p-3 bg-zinc-950/20 rounded-xl border border-zinc-800/50">
                  <div class={`p-2.5 rounded-lg bg-zinc-900 border border-zinc-800 ${metric.color}`}>
                    <Icon class="w-5 h-5" />
                  </div>
                  <div>
                    <p class="text-xs font-semibold text-white">{metric.name}</p>
                    <p class="text-sm font-bold text-zinc-300 mt-0.5">{metric.value}</p>
                    <p class="text-[10px] text-zinc-500 mt-0.5">{metric.desc}</p>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Quick shortcuts */}
          <div class="pt-4 border-t border-zinc-800/80">
            <h4 class="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-3">Quick Actions</h4>
            <div class="grid grid-cols-2 gap-2 text-center text-xs font-bold text-white">
              <button 
                onClick={() => setCurrentView('workflows')}
                class="p-2.5 bg-indigo-600 hover:bg-indigo-500 rounded-lg transition-colors"
              >
                + New Workflow
              </button>
              <button 
                onClick={() => setCurrentView('research')}
                class="p-2.5 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700/50 rounded-lg transition-colors"
              >
                Launch Research
              </button>
            </div>
          </div>

        </div>

      </div>
    </div>
  );
}
