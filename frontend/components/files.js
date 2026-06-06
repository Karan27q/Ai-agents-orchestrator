import React, { useState, useEffect } from 'react';
import { 
  FileText, UploadCloud, Database, RefreshCw, FileCode, CheckCircle, 
  HelpCircle, Search, AlertCircle, FileSpreadsheet, Eye
} from 'lucide-react';
import { API_URL } from '../app.js';

export function FilesView({ apiFetch, user }) {
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [ragQuery, setRagQuery] = useState('');
  const [ragResults, setRagResults] = useState([]);
  const [ragLoading, setRagLoading] = useState(false);
  const [selectedFileForRAG, setSelectedFileForRAG] = useState(null);

  const loadFiles = async () => {
    try {
      const data = await apiFetch('/files');
      setFiles(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadFiles();
  }, []);

  // Poll files index status if any is pending or processing
  useEffect(() => {
    const activeProcessing = files.some(f => f.embedding_status === 'pending' || f.embedding_status === 'processing');
    if (!activeProcessing) return;

    const interval = setInterval(loadFiles, 3000);
    return () => clearInterval(interval);
  }, [files]);

  const handleFileUpload = async (e) => {
    const selectedFiles = e.target.files;
    if (!selectedFiles || selectedFiles.length === 0) return;

    setUploading(true);
    const formData = new FormData();
    formData.append('file', selectedFiles[0]);

    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API_URL}/files/upload`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        },
        body: formData
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Upload failed');
      loadFiles();
    } catch (err) {
      alert(err.message);
    } finally {
      setUploading(false);
    }
  };

  const handleRAGSearch = async (e) => {
    e.preventDefault();
    if (!ragQuery.trim()) return;

    setRagLoading(true);
    setRagResults([]);
    try {
      const payload = {
        query: ragQuery,
        limit: 3
      };
      if (selectedFileForRAG) {
        payload.document_id = selectedFileForRAG.id;
      }
      const data = await apiFetch('/search/semantic', {
        method: 'POST',
        body: JSON.stringify(payload)
      });
      setRagResults(data);
    } catch (err) {
      alert(err.message);
    } finally {
      setRagLoading(false);
    }
  };

  const getFileIcon = (type) => {
    if (type.includes('pdf')) return FileText;
    if (type.includes('spreadsheet') || type.includes('csv')) return FileSpreadsheet;
    if (type.includes('json') || type.includes('javascript') || type.includes('html')) return FileCode;
    return FileText;
  };

  return (
    <div class="space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div>
        <h1 class="text-3xl font-extrabold text-white tracking-tight">File Indexer</h1>
        <p class="text-zinc-400 mt-2 text-sm">Upload documentation to extract contents and build local vector indexes.</p>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        {/* Left Side: Upload & list */}
        <div class="lg:col-span-2 space-y-6">
          {/* Upload card */}
          <div class="glass p-6 rounded-2xl border-dashed border-2 border-zinc-800 hover:border-indigo-500/50 transition-colors flex flex-col items-center justify-center py-8 text-center relative">
            <UploadCloud class="w-12 h-12 text-indigo-400/80 mb-3" />
            <h3 class="text-sm font-bold text-white mb-1">Index New Document</h3>
            <p class="text-zinc-500 text-xs max-w-xs mb-4">Drag and drop, or browse your files. Supported: TXT, MD, CSV, JSON, PDF.</p>
            
            <input
              type="file"
              onChange={handleFileUpload}
              disabled={uploading}
              class="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
            />
            
            {uploading && (
              <div class="absolute inset-0 bg-zinc-950/80 backdrop-blur-xs flex items-center justify-center rounded-2xl">
                <div class="flex items-center gap-3 bg-zinc-900 border border-zinc-800 p-4 rounded-xl shadow-2xl">
                  <span class="w-4 h-4 border-2 border-indigo-500/20 border-t-indigo-500 rounded-full animate-spin"></span>
                  <span class="text-xs font-bold text-white">Uploading & Indexing Chunks...</span>
                </div>
              </div>
            )}
          </div>

          {/* Files List */}
          <div class="glass p-6 rounded-2xl">
            <div class="flex items-center justify-between border-b border-zinc-800 pb-4 mb-4">
              <h3 class="text-sm font-bold text-white">Indexed Library</h3>
              <button onClick={loadFiles} class="p-1.5 rounded-lg border border-zinc-800 text-zinc-400 hover:text-white">
                <RefreshCw class="w-3.5 h-3.5" />
              </button>
            </div>

            <div class="overflow-x-auto">
              <table class="w-full text-left text-xs border-collapse">
                <thead>
                  <tr class="border-b border-zinc-800 text-zinc-500 font-semibold uppercase tracking-wider">
                    <th class="py-3 pr-4">File Name</th>
                    <th class="py-3 px-4">Index Status</th>
                    <th class="py-3 px-4">Uploaded</th>
                    <th class="py-3 pl-4 text-right">RAG Target</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-zinc-800/40 font-medium">
                  {loading ? (
                    <tr>
                      <td colSpan={4} class="py-8 text-center text-zinc-500">Loading document registry...</td>
                    </tr>
                  ) : files.length === 0 ? (
                    <tr>
                      <td colSpan={4} class="py-8 text-center text-zinc-500">No documents indexed in this organization yet.</td>
                    </tr>
                  ) : (
                    files.map(file => {
                      const FileIcon = getFileIcon(file.file_type);
                      return (
                        <tr key={file.id} class="hover:bg-zinc-800/10">
                          <td class="py-3.5 pr-4 text-white flex items-center gap-3">
                            <div class="p-2 rounded bg-zinc-900 border border-zinc-800 text-indigo-400 shrink-0">
                              <FileIcon class="w-4 h-4" />
                            </div>
                            <span class="truncate max-w-[200px]">{file.file_name}</span>
                          </td>
                          <td class="py-3.5 px-4">
                            <span class={`px-2 py-0.5 rounded-full font-bold text-[9px] uppercase border ${
                              file.embedding_status === 'completed' ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400' :
                              file.embedding_status === 'processing' ? 'bg-indigo-500/10 border-indigo-500/20 text-indigo-400 animate-pulse' :
                              file.embedding_status === 'failed' ? 'bg-red-500/10 border-red-500/20 text-red-400' :
                              'bg-zinc-500/10 border-zinc-500/20 text-zinc-400'
                            }`}>
                              {file.embedding_status}
                            </span>
                          </td>
                          <td class="py-3.5 px-4 text-zinc-500">
                            {new Date(file.created_at).toLocaleDateString()}
                          </td>
                          <td class="py-3.5 pl-4 text-right">
                            {file.embedding_status === 'completed' && (
                              <button 
                                onClick={() => {
                                  setSelectedFileForRAG(
                                    selectedFileForRAG?.id === file.id ? null : file
                                  );
                                }}
                                class={`px-2.5 py-1 rounded text-[10px] font-bold transition-colors ${
                                  selectedFileForRAG?.id === file.id 
                                    ? 'bg-indigo-600 text-white' 
                                    : 'bg-zinc-900 text-zinc-400 hover:text-white border border-zinc-800'
                                }`}
                              >
                                {selectedFileForRAG?.id === file.id ? 'Selected' : 'Filter Search'}
                              </button>
                            )}
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Right Side: RAG Test Console */}
        <div class="glass p-6 rounded-2xl h-fit space-y-4">
          <div>
            <h3 class="text-sm font-bold text-white flex items-center gap-2">
              <Database class="w-4 h-4 text-indigo-400" />
              <span>Semantic RAG Console</span>
            </h3>
            <p class="text-[11px] text-zinc-500 mt-1">Query indexed files directly via vector similarity.</p>
          </div>

          <form onSubmit={handleRAGSearch} class="space-y-3">
            {selectedFileForRAG && (
              <div class="flex items-center justify-between p-2 bg-indigo-500/5 border border-indigo-500/10 rounded-lg text-[10px] text-indigo-400 font-semibold">
                <span class="truncate">Filtering: {selectedFileForRAG.file_name}</span>
                <button onClick={() => setSelectedFileForRAG(null)} class="text-zinc-500 hover:text-white">
                  Clear
                </button>
              </div>
            )}
            
            <div class="relative">
              <input
                type="text"
                value={ragQuery}
                onChange={e => setRagQuery(e.target.value)}
                placeholder="Ask something about documents..."
                class="w-full pl-3 pr-9 py-2 bg-zinc-950/40 border border-zinc-800 rounded-xl text-xs text-white focus:outline-none focus:border-indigo-500 placeholder-zinc-600"
              />
              <button 
                type="submit" 
                class="absolute right-1 top-1 p-1 text-zinc-400 hover:text-white"
              >
                <Search class="w-4.5 h-4.5" />
              </button>
            </div>
          </form>

          {/* Results list */}
          <div class="space-y-3 pt-2 border-t border-zinc-800/80 max-h-[300px] overflow-y-auto pr-1">
            {ragLoading ? (
              <div class="flex items-center justify-center py-8">
                <span class="w-5 h-5 border-2 border-indigo-500/20 border-t-indigo-500 rounded-full animate-spin"></span>
              </div>
            ) : ragResults.length === 0 ? (
              <p class="text-[10px] text-zinc-600 text-center py-6">Submit a query to perform semantic retrieval.</p>
            ) : (
              ragResults.map((res, idx) => (
                <div key={idx} class="p-3 bg-zinc-950/20 rounded-xl border border-zinc-800/50 space-y-2 text-[10px]">
                  <div class="flex items-center justify-between font-semibold">
                    <span class="text-indigo-400 truncate max-w-[150px]">{res.file_name}</span>
                    <span class="text-emerald-400 bg-emerald-500/5 border border-emerald-500/10 px-1 rounded">
                      {(res.similarity * 100).toFixed(1)}% Match
                    </span>
                  </div>
                  <p class="text-zinc-300 leading-relaxed font-mono select-text bg-zinc-950/40 p-2 rounded border border-zinc-900">
                    "{res.chunk_text}"
                  </p>
                </div>
              ))
            )}
          </div>
        </div>

      </div>
    </div>
  );
}
