import React, { useState, useEffect, useRef } from 'react';
import { 
  BrainCircuit, Send, Play, Terminal, HelpCircle, FileText, 
  CheckCircle, ArrowRight, Clipboard, AlertCircle
} from 'lucide-react';
import { API_URL } from '../app.js';

export function ResearchView({ apiFetch, user }) {
  const [topic, setTopic] = useState('');
  const [isResearching, setIsResearching] = useState(false);
  const [agentLogs, setAgentLogs] = useState([]);
  const [activeAgent, setActiveAgent] = useState('');
  const [reportMarkdown, setReportMarkdown] = useState('');
  const [pastTasks, setPastTasks] = useState([]);
  const [viewingTask, setViewingTask] = useState(null);

  const logsEndRef = useRef(null);

  const loadPastTasks = async () => {
    try {
      const data = await apiFetch('/agents/tasks');
      setPastTasks(data);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    loadPastTasks();
  }, []);

  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [agentLogs]);

  const handleLaunchResearch = async (e) => {
    e.preventDefault();
    if (!topic.trim()) return;

    setIsResearching(true);
    setAgentLogs([]);
    setActiveAgent('Planner Agent');
    setReportMarkdown('');
    setViewingTask(null);

    try {
      // Use standard EventSource or fetch with response reader for POST requests with body.
      // Since EventSource only supports GET naturally, we can write a fetch loop with response reader!
      // This is extremely standard for streaming POST requests.
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_URL}/agents/research`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ topic })
      });

      if (!response.ok) {
        const contentType = response.headers.get('content-type') || '';
        const errorText = await response.text().catch(() => '');
        if (contentType.includes('application/json')) {
          let errMsg = 'Failed to start research task';
          try {
            const errorJson = JSON.parse(errorText || '{}');
            errMsg = errorJson.detail || errorJson.message || errMsg;
          } catch (parseErr) {
            errMsg = errorText || errMsg;
          }
          throw new Error(errMsg);
        }
        throw new Error(errorText || 'Failed to start research task');
      }

      const contentType = response.headers.get('content-type') || '';
      if (!contentType.includes('text/event-stream')) {
        const bodyText = await response.text().catch(() => 'Unexpected non-stream response');
        throw new Error(bodyText || 'Unexpected non-stream response from research endpoint');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        
        // Parse Server-Sent Events from buffer
        const lines = buffer.split('\n');
        // Keep the last partial line in the buffer
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const dataStr = line.slice(6).trim();
            try {
              const event = JSON.parse(dataStr);

              if (event.type === 'status') {
                setActiveAgent(event.agent);
                setAgentLogs(prev => [...prev, {
                  agent: event.agent,
                  message: event.message,
                  timestamp: new Date().toLocaleTimeString()
                }]);
              } else if (event.type === 'token') {
                setReportMarkdown(prev => prev + event.content);
              } else if (event.type === 'error') {
                setAgentLogs(prev => [...prev, {
                  agent: 'System',
                  message: `ERROR: ${event.message}`,
                  timestamp: new Date().toLocaleTimeString()
                }]);
              }
            } catch (err) {
              const raw = dataStr || 'Unknown stream event';
              console.warn('Non-JSON SSE event received:', raw);
              if (raw.toLowerCase().includes('internal server error') || raw.toLowerCase().includes('error')) {
                setAgentLogs(prev => [...prev, {
                  agent: 'System',
                  message: `Stream error: ${raw}`,
                  timestamp: new Date().toLocaleTimeString()
                }]);
              }
            }
          }
        }
      }
      
      // Refresh tasks
      loadPastTasks();
    } catch (err) {
      setAgentLogs(prev => [...prev, {
        agent: 'System',
        message: `Execution Failure: ${err.message}`,
        timestamp: new Date().toLocaleTimeString()
      }]);
    } finally {
      setIsResearching(false);
      setActiveAgent('');
    }
  };

  const copyToClipboard = () => {
    navigator.clipboard.writeText(reportMarkdown || viewingTask?.result || '');
    alert('Markdown report copied to clipboard!');
  };

  // Basic markdown compiler to render neat styling on the fly
  const renderMarkdown = (md) => {
    if (!md) return '';
    
    // Replace headers
    let html = md
      .replace(/^### (.*$)/gim, '<h4 class="text-sm font-bold text-white mt-4 mb-2">$1</h4>')
      .replace(/^## (.*$)/gim, '<h3 class="text-base font-extrabold text-white border-b border-zinc-800 pb-2 mt-6 mb-3">$1</h3>')
      .replace(/^# (.*$)/gim, '<h2 class="text-lg font-black text-indigo-400 mt-8 mb-4">$1</h2>');

    // Replace bold
    html = html.replace(/\*\*(.*)\*\*/gim, '<strong>$1</strong>');

    // Replace linebreaks / paragraphs
    html = html.replace(/\n\n/g, '<div class="h-3"></div>');
    
    // Replace bullet points
    html = html.replace(/^\- (.*$)/gim, '<li class="ml-4 list-disc text-zinc-300 mt-1">$1</li>');

    return <div dangerouslySetInnerHTML={{ __html: html }} class="text-xs leading-relaxed text-zinc-300 space-y-2 select-text" />;
  };

  return (
    <div class="space-y-6 max-w-7xl mx-auto h-full flex flex-col">
      {/* Header */}
      <div>
        <h1 class="text-3xl font-extrabold text-white tracking-tight">Multi-Agent Research</h1>
        <p class="text-zinc-400 mt-2 text-sm">Orchestrate a pipeline of 5 AI agents (Planner, Research, Critic, Writer, Citation) to compile deep reports.</p>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        {/* Launch panel & past reports */}
        <div class="space-y-6 lg:col-span-1">
          {/* Form */}
          <div class="glass p-6 rounded-2xl space-y-4">
            <h3 class="text-sm font-bold text-white">New Research Brief</h3>
            
            <form onSubmit={handleLaunchResearch} class="space-y-4">
              <div>
                <label class="block text-[10px] text-zinc-500 font-semibold uppercase mb-2">Research Question / Topic</label>
                <textarea
                  value={topic}
                  onChange={e => setTopic(e.target.value)}
                  disabled={isResearching}
                  rows="3"
                  required
                  placeholder="e.g., Deeptech startups funding trends in India for 2025"
                  class="w-full bg-zinc-950/40 border border-zinc-800 rounded-xl p-3 text-zinc-200 text-xs focus:border-indigo-500 focus:outline-none placeholder-zinc-600 leading-relaxed"
                />
              </div>

              <button
                type="submit"
                disabled={isResearching}
                class="w-full flex items-center justify-center gap-2 py-2.5 px-4 bg-indigo-600 hover:bg-indigo-500 text-white font-bold rounded-xl text-xs transition-colors shadow-lg shadow-indigo-600/20 disabled:opacity-50"
              >
                <BrainCircuit class="w-4 h-4" />
                <span>Launch Agentic Chain</span>
              </button>
            </form>
          </div>

          {/* Past reports */}
          <div class="glass p-6 rounded-2xl flex flex-col max-h-[300px]">
            <h3 class="text-sm font-bold text-white mb-4 border-b border-zinc-800/80 pb-3">Research Archives</h3>
            
            <div class="overflow-y-auto space-y-2 flex-1 pr-1">
              {pastTasks.length === 0 ? (
                <p class="text-[11px] text-zinc-500 text-center py-6">No archived research found.</p>
              ) : (
                pastTasks.map(task => {
                  let payload = {};
                  try { payload = JSON.parse(task.payload); } catch(e){}
                  
                  return (
                    <button
                      key={task.id}
                      onClick={() => {
                        setViewingTask(task);
                        setReportMarkdown('');
                      }}
                      class="w-full text-left p-2.5 bg-zinc-950/20 hover:bg-zinc-800/40 rounded-xl border border-zinc-800/50 flex flex-col gap-1 transition-all"
                    >
                      <p class="text-[11px] font-bold text-white truncate">{payload.topic || 'Research Task'}</p>
                      <div class="flex items-center justify-between text-[9px] text-zinc-500">
                        <span>{new Date(task.created_at).toLocaleDateString()}</span>
                        <span class="text-indigo-400 font-bold uppercase">{task.status}</span>
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          </div>
        </div>

        {/* Live streaming display screen */}
        <div class="lg:col-span-2 grid grid-cols-1 md:grid-cols-2 gap-6 h-[550px]">
          
          {/* Agent Console */}
          <div class="glass rounded-2xl p-5 flex flex-col h-full bg-zinc-950/60 overflow-hidden">
            <h3 class="text-xs font-bold text-zinc-400 uppercase tracking-wider mb-3 flex items-center gap-2">
              <Terminal class="w-4 h-4 text-indigo-400" />
              <span>Orchestrator Logs</span>
            </h3>

            <div class="flex-1 overflow-y-auto space-y-2.5 pr-2 font-mono text-[10px] py-1 border-t border-zinc-800/50 pt-3">
              {agentLogs.length === 0 && !isResearching ? (
                <div class="flex flex-col items-center justify-center h-full text-center text-zinc-600 gap-2">
                  <BrainCircuit class="w-8 h-8 opacity-40 animate-pulse" />
                  <p>Orchestrator idle. Launch a research brief to wake up agents.</p>
                </div>
              ) : (
                <>
                  {agentLogs.map((log, idx) => (
                    <div key={idx} class="space-y-0.5 leading-relaxed">
                      <div class="flex items-center gap-1.5">
                        <span class="text-[9px] text-zinc-600">[{log.timestamp}]</span>
                        <span class="text-indigo-400 font-extrabold">{log.agent}:</span>
                      </div>
                      <p class="text-zinc-300 ml-4">{log.message}</p>
                    </div>
                  ))}
                  {isResearching && (
                    <div class="flex items-center gap-2 text-indigo-400 ml-4 font-bold mt-2">
                      <span class="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-ping"></span>
                      <span>{activeAgent || 'Working...'}</span>
                    </div>
                  )}
                  <div ref={logsEndRef} />
                </>
              )}
            </div>
          </div>

          {/* Compiled Output Document Preview */}
          <div class="glass rounded-2xl p-5 flex flex-col h-full bg-zinc-900/20 overflow-hidden relative">
            <div class="flex items-center justify-between border-b border-zinc-800/80 pb-3 mb-3 shrink-0">
              <h3 class="text-xs font-bold text-zinc-400 uppercase tracking-wider flex items-center gap-2">
                <FileText class="w-4 h-4 text-emerald-400" />
                <span>Final Report</span>
              </h3>
              {(reportMarkdown || viewingTask?.result) && (
                <button
                  onClick={copyToClipboard}
                  class="p-1.5 rounded-lg border border-zinc-800 text-zinc-400 hover:text-white hover:bg-zinc-800/40"
                  title="Copy Report to Clipboard"
                >
                  <Clipboard class="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            <div class="flex-1 overflow-y-auto pr-2">
              {reportMarkdown ? (
                renderMarkdown(reportMarkdown)
              ) : viewingTask?.result ? (
                renderMarkdown(viewingTask.result)
              ) : (
                <div class="flex flex-col items-center justify-center h-full text-center text-zinc-600 py-12">
                  <FileText class="w-8 h-8 opacity-40 mb-2" />
                  <p class="text-xs">Report output will stream here in real time...</p>
                </div>
              )}
            </div>
          </div>

        </div>

      </div>
    </div>
  );
}
