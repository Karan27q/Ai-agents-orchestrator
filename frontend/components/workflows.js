import React, { useState, useEffect, useRef } from 'react';
import { 
  GitBranch, Plus, Save, Play, X, Trash2, ArrowRight, Settings, 
  Terminal, Shield, FileCode, CheckCircle, RefreshCw, Layers
} from 'lucide-react';

export function WorkflowsView({ apiFetch, user }) {
  const [workflows, setWorkflows] = useState([]);
  const [activeWorkflow, setActiveWorkflow] = useState(null);
  const [activeRun, setActiveRun] = useState(null);
  const [logs, setLogs] = useState([]);
  const [isBuilding, setIsBuilding] = useState(false);
  const [showLogsModal, setShowLogsModal] = useState(false);
  
  // Builder state
  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);
  const [selectedNode, setSelectedNode] = useState(null);
  const [connectionSource, setConnectionSource] = useState(null);
  const [wfName, setWfName] = useState('New Workflow');
  const [wfDesc, setWfDesc] = useState('');

  const dragNodeRef = useRef(null);
  const dragOffsetRef = useRef({ x: 0, y: 0 });

  const loadWorkflows = async () => {
    try {
      const data = await apiFetch('/workflows');
      setWorkflows(data);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    loadWorkflows();
  }, []);

  // Poll active run logs if a run is running
  useEffect(() => {
    if (!activeRun || activeRun.status === 'completed' || activeRun.status === 'failed') return;
    
    const interval = setInterval(async () => {
      try {
        const runData = await apiFetch(`/workflows/runs/${activeRun.id}`);
        setActiveRun(runData);
        setLogs(runData.logs ? runData.logs.split('\n') : []);
        
        if (runData.status === 'completed' || runData.status === 'failed') {
          clearInterval(interval);
          loadWorkflows(); // Refresh run count or active status
        }
      } catch (err) {
        console.error(err);
      }
    }, 1500);

    return () => clearInterval(interval);
  }, [activeRun]);

  const handleCreateNew = () => {
    setWfName('New Automation Workflow');
    setWfDesc('Describe your automation pipeline');
    // Start with a trigger node
    setNodes([
      { id: 'node_trigger', type: 'trigger', label: 'Trigger Event', x: 50, y: 150, data: {} }
    ]);
    setEdges([]);
    setSelectedNode(null);
    setActiveWorkflow(null);
    setIsBuilding(true);
  };

  const handleEdit = (wf) => {
    setActiveWorkflow(wf);
    setWfName(wf.name);
    setWfDesc(wf.description || '');
    try {
      const parsed = JSON.parse(wf.workflow_json);
      setNodes(parsed.nodes || []);
      setEdges(parsed.edges || []);
    } catch (e) {
      setNodes([{ id: 'node_trigger', type: 'trigger', label: 'Trigger Event', x: 50, y: 150, data: {} }]);
      setEdges([]);
    }
    setSelectedNode(null);
    setIsBuilding(true);
  };

  const handleSave = async () => {
    const payload = {
      name: wfName,
      description: wfDesc,
      workflow_json: JSON.stringify({ nodes, edges }),
      status: 'active'
    };

    try {
      if (activeWorkflow) {
        await apiFetch(`/workflows/${activeWorkflow.id}`, {
          method: 'PUT',
          body: JSON.stringify(payload)
        });
      } else {
        await apiFetch('/workflows', {
          method: 'POST',
          body: JSON.stringify(payload)
        });
      }
      setIsBuilding(false);
      loadWorkflows();
    } catch (err) {
      alert(err.message);
    }
  };

  const handleDelete = async (id) => {
    if (!confirm('Are you sure you want to delete this workflow?')) return;
    try {
      await apiFetch(`/workflows/${id}`, { method: 'DELETE' });
      loadWorkflows();
    } catch (err) {
      alert(err.message);
    }
  };

  const handleRun = async (id) => {
    try {
      const run = await apiFetch(`/workflows/${id}/run`, { method: 'POST' });
      setActiveRun(run);
      setLogs([run.logs || 'Initialising run...']);
      setShowLogsModal(true);
    } catch (err) {
      alert(err.message);
    }
  };

  // Node Dragger Handlers
  const handleNodeMouseDown = (e, node) => {
    dragNodeRef.current = node.id;
    dragOffsetRef.current = {
      x: e.clientX - node.x,
      y: e.clientY - node.y
    };
    e.stopPropagation();
  };

  const handleCanvasMouseMove = (e) => {
    if (!dragNodeRef.current) return;
    const canvasRect = e.currentTarget.getBoundingClientRect();
    
    // Bounds check and offset adjustment
    let newX = e.clientX - dragOffsetRef.current.x;
    let newY = e.clientY - dragOffsetRef.current.y;

    // Grid snap (15px)
    newX = Math.round(newX / 15) * 15;
    newY = Math.round(newY / 15) * 15;

    // Constraint within canvas size
    newX = Math.max(10, Math.min(newX, 900));
    newY = Math.max(10, Math.min(newY, 500));

    setNodes(prev => prev.map(n => n.id === dragNodeRef.current ? { ...n, x: newX, y: newY } : n));
  };

  const handleCanvasMouseUp = () => {
    dragNodeRef.current = null;
  };

  // Node operations
  const addNode = (type) => {
    const id = `node_${type}_${Date.now().toString().slice(-4)}`;
    let label = '';
    let defaultData = {};

    switch (type) {
      case 'http_request':
        label = 'HTTP Request';
        defaultData = { url: 'https://httpbin.org/get', method: 'GET', headers: '{}', body: '' };
        break;
      case 'llm_prompt':
        label = 'Gemini LLM Prompt';
        defaultData = { prompt: 'Summarise the following: {{node_trigger.payload}}' };
        break;
      case 'delay':
        label = 'Delay';
        defaultData = { seconds: 5 };
        break;
      case 'slack_message':
        label = 'Post to Slack';
        defaultData = { webhook_url: '', message: 'Workflow completed successfully!' };
        break;
      case 'conditional':
        label = 'Branch Condition';
        defaultData = { reference_value: '', comparison_value: '', operator: 'equals' };
        break;
    }

    setNodes(prev => [...prev, {
      id,
      type,
      label,
      x: 300,
      y: 150 + (prev.length * 20) % 150,
      data: defaultData
    }]);
  };

  const deleteNode = (nodeId) => {
    if (nodeId === 'node_trigger') return; // Cannot delete trigger
    setNodes(prev => prev.filter(n => n.id !== nodeId));
    setEdges(prev => prev.filter(e => e.source !== nodeId && e.target !== nodeId));
    if (selectedNode?.id === nodeId) setSelectedNode(null);
  };

  const startConnection = (nodeId) => {
    setConnectionSource(nodeId);
  };

  const completeConnection = (targetId) => {
    if (!connectionSource || connectionSource === targetId) {
      setConnectionSource(null);
      return;
    }
    // Prevent duplicate edges
    const exists = edges.some(e => e.source === connectionSource && e.target === targetId);
    if (!exists) {
      // For conditionals, let's prompt or specify handles
      const isConditional = nodes.find(n => n.id === connectionSource)?.type === 'conditional';
      let handle = 'true';
      if (isConditional) {
        const wantsTrue = confirm('Connect as the [TRUE] branch? (Cancel for [FALSE])');
        handle = wantsTrue ? 'true' : 'false';
      }

      setEdges(prev => [...prev, {
        source: connectionSource,
        target: targetId,
        sourceHandle: handle
      }]);
    }
    setConnectionSource(null);
  };

  const removeEdge = (edgeIdx) => {
    setEdges(prev => prev.filter((_, idx) => idx !== edgeIdx));
  };

  const updateNodeData = (field, val) => {
    if (!selectedNode) return;
    const updatedData = { ...selectedNode.data, [field]: val };
    setNodes(prev => prev.map(n => n.id === selectedNode.id ? { ...n, data: updatedData } : n));
    setSelectedNode(prev => ({ ...prev, data: updatedData }));
  };

  return (
    <div class="space-y-6 max-w-7xl mx-auto h-full flex flex-col">
      {/* Page Header */}
      <div class="flex items-center justify-between">
        <div>
          <h1 class="text-3xl font-extrabold text-white tracking-tight">Workflows</h1>
          <p class="text-zinc-400 mt-2 text-sm">Visual DAG runner optimized for low-resource environments.</p>
        </div>
        {!isBuilding && (
          <button
            onClick={handleCreateNew}
            class="flex items-center gap-2 py-2.5 px-4 bg-indigo-600 hover:bg-indigo-500 text-white font-bold rounded-xl text-xs transition-colors shadow-lg shadow-indigo-600/20"
          >
            <Plus class="w-4 h-4" />
            <span>Create Workflow</span>
          </button>
        )}
      </div>

      {/* Editor View */}
      {isBuilding ? (
        <div class="grid grid-cols-1 lg:grid-cols-4 gap-6 h-[600px]">
          {/* Builder Canvas Grid */}
          <div class="lg:col-span-3 glass rounded-2xl relative overflow-hidden flex flex-col">
            
            {/* Canvas Sub Header / Tools */}
            <div class="h-14 border-b border-zinc-800/80 px-6 flex items-center justify-between z-10 bg-zinc-950/40">
              <div class="flex items-center gap-3">
                <input
                  type="text"
                  value={wfName}
                  onChange={e => setWfName(e.target.value)}
                  class="bg-transparent border-b border-transparent hover:border-zinc-700 focus:border-indigo-500 focus:outline-none text-white font-bold text-sm"
                />
              </div>
              <div class="flex items-center gap-2">
                <button
                  onClick={() => setIsBuilding(false)}
                  class="p-2 text-zinc-400 hover:text-white"
                  title="Cancel"
                >
                  <X class="w-5 h-5" />
                </button>
                <button
                  onClick={handleSave}
                  class="flex items-center gap-2 py-1.5 px-3 bg-emerald-600 hover:bg-emerald-500 text-white font-bold rounded-lg text-xs"
                >
                  <Save class="w-3.5 h-3.5" />
                  <span>Save</span>
                </button>
              </div>
            </div>

            {/* Toolbox toolbar */}
            <div class="flex items-center gap-2 p-2 bg-zinc-900 border-b border-zinc-800/50 z-10 overflow-x-auto text-[11px] font-bold">
              <span class="text-zinc-500 px-2 uppercase tracking-wider text-[9px]">Add Nodes:</span>
              <button onClick={() => addNode('http_request')} class="px-2.5 py-1 bg-zinc-800 border border-zinc-700/60 rounded text-zinc-300 hover:text-white hover:border-zinc-500">
                + HTTP Request
              </button>
              <button onClick={() => addNode('llm_prompt')} class="px-2.5 py-1 bg-zinc-800 border border-zinc-700/60 rounded text-zinc-300 hover:text-white hover:border-zinc-500">
                + LLM Prompt
              </button>
              <button onClick={() => addNode('delay')} class="px-2.5 py-1 bg-zinc-800 border border-zinc-700/60 rounded text-zinc-300 hover:text-white hover:border-zinc-500">
                + Delay
              </button>
              <button onClick={() => addNode('slack_message')} class="px-2.5 py-1 bg-zinc-800 border border-zinc-700/60 rounded text-zinc-300 hover:text-white hover:border-zinc-500">
                + Slack message
              </button>
              <button onClick={() => addNode('conditional')} class="px-2.5 py-1 bg-zinc-800 border border-zinc-700/60 rounded text-zinc-300 hover:text-white hover:border-zinc-500">
                + Conditional
              </button>
            </div>

            {/* Connection mode indicator */}
            {connectionSource && (
              <div class="absolute top-24 left-4 bg-indigo-600 text-white px-3 py-1 rounded-full text-[10px] font-bold z-10 animate-bounce">
                Click target node to connect from {connectionSource}
              </div>
            )}

            {/* Canvas Body */}
            <div 
              onMouseMove={handleCanvasMouseMove}
              onMouseUp={handleCanvasMouseUp}
              class="flex-1 bg-[radial-gradient(#1f2937_1px,transparent_1px)] [background-size:16px_16px] relative cursor-crosshair overflow-hidden select-none"
            >
              {/* Connection Edges Canvas SVG layer */}
              <svg class="absolute inset-0 pointer-events-none w-full h-full">
                <defs>
                  <marker id="arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                    <path d="M 0 0 L 10 5 L 0 10 z" fill="#6366f1" />
                  </marker>
                </defs>
                {edges.map((edge, idx) => {
                  const src = nodes.find(n => n.id === edge.source);
                  const tgt = nodes.find(n => n.id === edge.target);
                  if (!src || !tgt) return null;

                  // Middle-right of source, middle-left of target
                  const x1 = src.x + 180;
                  const y1 = src.y + 45;
                  const x2 = tgt.x;
                  const y2 = tgt.y + 45;

                  const dx = Math.abs(x2 - x1) * 0.4;
                  const path = `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;

                  return (
                    <g key={idx} class="group pointer-events-auto cursor-pointer" onClick={() => removeEdge(idx)}>
                      <path 
                        d={path} 
                        stroke="#4f46e5" 
                        strokeWidth="3" 
                        fill="none" 
                        markerEnd="url(#arrow)"
                        class="transition-colors group-hover:stroke-red-500" 
                      />
                      <title>Click to delete connection</title>
                      {edge.sourceHandle && (
                        <text 
                          x={x1 + 30} 
                          y={y1 + (y2 - y1) / 2 - 5} 
                          fill="#818cf8" 
                          fontSize="9" 
                          fontWeight="bold"
                          class="bg-zinc-950"
                        >
                          {edge.sourceHandle.toUpperCase()}
                        </text>
                      )}
                    </g>
                  );
                })}
              </svg>

              {/* Nodes Layer */}
              {nodes.map(node => {
                const isSelected = selectedNode?.id === node.id;
                const isConnecting = connectionSource === node.id;

                return (
                  <div
                    key={node.id}
                    style={{ left: `${node.x}px`, top: `${node.y}px` }}
                    onClick={(e) => {
                      setSelectedNode(node);
                      e.stopPropagation();
                    }}
                    class={`absolute w-44 bg-zinc-950/90 border rounded-xl shadow-2xl flex flex-col z-10 transition-shadow ${
                      isSelected ? 'border-indigo-500 glow-indigo' : 'border-zinc-800'
                    }`}
                  >
                    {/* Node Header */}
                    <div 
                      onMouseDown={(e) => handleNodeMouseDown(e, node)}
                      class="px-3 py-2 border-b border-zinc-800/80 bg-zinc-900/60 rounded-t-xl cursor-grab active:cursor-grabbing flex items-center justify-between text-[11px] font-bold text-white select-none"
                    >
                      <span class="truncate">{node.label}</span>
                      <div class="flex items-center gap-1.5 shrink-0 ml-1">
                        <button 
                          onClick={(e) => { startConnection(node.id); e.stopPropagation(); }} 
                          class="text-indigo-400 hover:text-white"
                          title="Connect to other node"
                        >
                          <Layers class="w-3.5 h-3.5" />
                        </button>
                        {node.id !== 'node_trigger' && (
                          <button 
                            onClick={(e) => { deleteNode(node.id); e.stopPropagation(); }} 
                            class="text-zinc-500 hover:text-red-400"
                            title="Delete Node"
                          >
                            <Trash2 class="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Node Body details */}
                    <div 
                      onClick={() => {
                        if (connectionSource) completeConnection(node.id);
                      }}
                      class={`p-3 text-[10px] text-zinc-400 space-y-1 min-h-12 flex flex-col justify-center ${
                        connectionSource && connectionSource !== node.id ? 'hover:bg-indigo-600/10 cursor-pointer' : ''
                      }`}
                    >
                      <p class="font-mono text-zinc-500 break-all">{node.id}</p>
                      {node.type === 'http_request' && (
                        <p class="text-white font-semibold">{node.data.method} <span class="text-zinc-500">{node.data.url?.slice(0, 15)}...</span></p>
                      )}
                      {node.type === 'llm_prompt' && (
                        <p class="italic text-zinc-500">"{node.data.prompt?.slice(0, 20)}..."</p>
                      )}
                      {node.type === 'delay' && (
                        <p class="text-white font-semibold">{node.data.seconds} seconds</p>
                      )}
                      {node.type === 'conditional' && (
                        <p class="text-indigo-400 font-semibold">{node.data.operator}</p>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Configuration Side Panel */}
          <div class="glass rounded-2xl p-5 overflow-y-auto flex flex-col gap-4">
            <h3 class="text-sm font-bold text-white flex items-center gap-2 border-b border-zinc-800 pb-3">
              <Settings class="w-4 h-4 text-indigo-400" />
              <span>Node Parameters</span>
            </h3>

            {selectedNode ? (
              <div class="space-y-4 text-xs">
                <div>
                  <p class="text-[10px] text-zinc-500 font-semibold uppercase">Node Type</p>
                  <p class="text-white font-bold mt-1 text-sm">{selectedNode.label}</p>
                </div>

                {selectedNode.type === 'http_request' && (
                  <>
                    <div>
                      <label class="block text-[10px] text-zinc-500 font-semibold uppercase mb-1">Method</label>
                      <select 
                        value={selectedNode.data.method} 
                        onChange={e => updateNodeData('method', e.target.value)}
                        class="w-full bg-zinc-900 border border-zinc-800 rounded p-2 text-white focus:outline-none"
                      >
                        <option value="GET">GET</option>
                        <option value="POST">POST</option>
                      </select>
                    </div>
                    <div>
                      <label class="block text-[10px] text-zinc-500 font-semibold uppercase mb-1">URL</label>
                      <input 
                        type="text" 
                        value={selectedNode.data.url} 
                        onChange={e => updateNodeData('url', e.target.value)}
                        class="w-full bg-zinc-900 border border-zinc-800 rounded p-2 text-white font-mono"
                      />
                    </div>
                    <div>
                      <label class="block text-[10px] text-zinc-500 font-semibold uppercase mb-1">Headers (JSON)</label>
                      <textarea 
                        rows="3" 
                        value={selectedNode.data.headers} 
                        onChange={e => updateNodeData('headers', e.target.value)}
                        class="w-full bg-zinc-900 border border-zinc-800 rounded p-2 text-white font-mono"
                      />
                    </div>
                    {selectedNode.data.method === 'POST' && (
                      <div>
                        <label class="block text-[10px] text-zinc-500 font-semibold uppercase mb-1">Post Body</label>
                        <textarea 
                          rows="3" 
                          value={selectedNode.data.body} 
                          onChange={e => updateNodeData('body', e.target.value)}
                          class="w-full bg-zinc-900 border border-zinc-800 rounded p-2 text-white font-mono"
                        />
                      </div>
                    )}
                  </>
                )}

                {selectedNode.type === 'llm_prompt' && (
                  <div>
                    <label class="block text-[10px] text-zinc-500 font-semibold uppercase mb-1">Prompt Template</label>
                    <textarea 
                      rows="6" 
                      value={selectedNode.data.prompt} 
                      onChange={e => updateNodeData('prompt', e.target.value)}
                      placeholder="Enter prompt. You can use {{node_id.output}} to reference variables."
                      class="w-full bg-zinc-900 border border-zinc-800 rounded p-2 text-white leading-relaxed"
                    />
                  </div>
                )}

                {selectedNode.type === 'delay' && (
                  <div>
                    <label class="block text-[10px] text-zinc-500 font-semibold uppercase mb-1">Wait Duration (Seconds)</label>
                    <input 
                      type="number" 
                      value={selectedNode.data.seconds} 
                      onChange={e => updateNodeData('seconds', parseInt(e.target.value) || 1)}
                      class="w-full bg-zinc-900 border border-zinc-800 rounded p-2 text-white font-mono"
                    />
                  </div>
                )}

                {selectedNode.type === 'slack_message' && (
                  <>
                    <div>
                      <label class="block text-[10px] text-zinc-500 font-semibold uppercase mb-1">Slack Webhook URL</label>
                      <input 
                        type="text" 
                        value={selectedNode.data.webhook_url} 
                        onChange={e => updateNodeData('webhook_url', e.target.value)}
                        class="w-full bg-zinc-900 border border-zinc-800 rounded p-2 text-white font-mono"
                      />
                    </div>
                    <div>
                      <label class="block text-[10px] text-zinc-500 font-semibold uppercase mb-1">Message Template</label>
                      <textarea 
                        rows="4" 
                        value={selectedNode.data.message} 
                        onChange={e => updateNodeData('message', e.target.value)}
                        class="w-full bg-zinc-900 border border-zinc-800 rounded p-2 text-white"
                      />
                    </div>
                  </>
                )}

                {selectedNode.type === 'conditional' && (
                  <>
                    <div>
                      <label class="block text-[10px] text-zinc-500 font-semibold uppercase mb-1">Reference Value</label>
                      <input 
                        type="text" 
                        value={selectedNode.data.reference_value} 
                        onChange={e => updateNodeData('reference_value', e.target.value)}
                        placeholder="e.g. {{node_llm.text}}"
                        class="w-full bg-zinc-900 border border-zinc-800 rounded p-2 text-white"
                      />
                    </div>
                    <div>
                      <label class="block text-[10px] text-zinc-500 font-semibold uppercase mb-1">Operator</label>
                      <select 
                        value={selectedNode.data.operator} 
                        onChange={e => updateNodeData('operator', e.target.value)}
                        class="w-full bg-zinc-900 border border-zinc-800 rounded p-2 text-white"
                      >
                        <option value="equals">Equals</option>
                        <option value="contains">Contains</option>
                      </select>
                    </div>
                    <div>
                      <label class="block text-[10px] text-zinc-500 font-semibold uppercase mb-1">Comparison Value</label>
                      <input 
                        type="text" 
                        value={selectedNode.data.comparison_value} 
                        onChange={e => updateNodeData('comparison_value', e.target.value)}
                        class="w-full bg-zinc-900 border border-zinc-800 rounded p-2 text-white"
                      />
                    </div>
                  </>
                )}

              </div>
            ) : (
              <p class="text-zinc-500 text-xs text-center py-12">Click a node on the canvas to configure parameters</p>
            )}
          </div>
        </div>
      ) : (
        /* Workflows Grid list */
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {workflows.length === 0 ? (
            <div class="col-span-full glass p-12 text-center rounded-2xl">
              <GitBranch class="w-12 h-12 text-zinc-600 mx-auto mb-4" />
              <h3 class="text-white font-bold">No Workflows Configured</h3>
              <p class="text-zinc-500 text-xs mt-1">Create your first DAG-based AI automation sequence.</p>
              <button 
                onClick={handleCreateNew}
                class="mt-6 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white font-bold rounded-xl text-xs"
              >
                Get Started
              </button>
            </div>
          ) : (
            workflows.map(wf => (
              <div key={wf.id} class="glass glass-hover p-6 rounded-2xl flex flex-col justify-between min-h-[180px]">
                <div>
                  <div class="flex items-start justify-between">
                    <h3 class="text-base font-extrabold text-white">{wf.name}</h3>
                    <span class="px-2 py-0.5 rounded-full font-bold text-[9px] uppercase bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
                      {wf.status}
                    </span>
                  </div>
                  <p class="text-xs text-zinc-400 mt-2 line-clamp-2">{wf.description || 'No description provided'}</p>
                </div>

                <div class="flex items-center justify-between border-t border-zinc-800/80 pt-4 mt-6">
                  <button 
                    onClick={() => handleDelete(wf.id)}
                    class="text-zinc-500 hover:text-red-400 p-1.5"
                    title="Delete Workflow"
                  >
                    <Trash2 class="w-4 h-4" />
                  </button>

                  <div class="flex items-center gap-2">
                    <button 
                      onClick={() => handleEdit(wf)}
                      class="px-3 py-1.5 bg-zinc-900 border border-zinc-800 hover:bg-zinc-800 text-white font-bold rounded-lg text-xs"
                    >
                      Configure
                    </button>
                    <button 
                      onClick={() => handleRun(wf.id)}
                      class="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white font-bold rounded-lg text-xs"
                    >
                      <Play class="w-3 h-3 fill-current" />
                      <span>Execute</span>
                    </button>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* Logs View Modal */}
      {showLogsModal && activeRun && (
        <div class="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div class="w-full max-w-3xl glass rounded-2xl flex flex-col h-[550px] shadow-2xl relative glow-indigo">
            
            {/* Modal Header */}
            <div class="h-14 border-b border-zinc-800/80 px-6 flex items-center justify-between">
              <div class="flex items-center gap-3">
                <Terminal class="w-5 h-5 text-indigo-400" />
                <span class="text-sm font-bold text-white">Execution Console — Run #{activeRun.id}</span>
                <span class={`px-2 py-0.5 rounded-full font-bold text-[9px] uppercase border ${
                  activeRun.status === 'completed' ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400' :
                  activeRun.status === 'running' ? 'bg-indigo-500/10 border-indigo-500/20 text-indigo-400 animate-pulse' :
                  'bg-red-500/10 border-red-500/20 text-red-400'
                }`}>
                  {activeRun.status}
                </span>
              </div>
              <button 
                onClick={() => setShowLogsModal(false)}
                class="text-zinc-400 hover:text-white"
              >
                <X class="w-5 h-5" />
              </button>
            </div>

            {/* Logs Screen */}
            <div class="flex-1 bg-zinc-950 p-6 overflow-y-auto font-mono text-xs text-zinc-300 space-y-2 leading-relaxed">
              {logs.map((line, idx) => {
                let color = 'text-zinc-300';
                if (line.includes('ERROR') || line.includes('failure')) color = 'text-red-400 font-bold';
                else if (line.includes('completed successfully')) color = 'text-emerald-400';
                else if (line.includes('Running node')) color = 'text-indigo-400 font-semibold';
                return <p key={idx} class={color}>{line}</p>;
              })}
            </div>
            
            {/* Run Output (JSON Results if completed) */}
            {activeRun.status === 'completed' && activeRun.results && (
              <div class="p-4 border-t border-zinc-800 bg-zinc-900/40">
                <h4 class="text-[10px] font-semibold text-zinc-500 uppercase tracking-wider mb-2">Final Output Variables</h4>
                <pre class="bg-zinc-950/60 p-3 rounded-lg border border-zinc-800 text-[10px] text-indigo-300 overflow-x-auto font-mono max-h-24">
                  {JSON.stringify(JSON.parse(activeRun.results), null, 2)}
                </pre>
              </div>
            )}
          </div>
        </div>
      )}

    </div>
  );
}
