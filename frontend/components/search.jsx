import React, { useState, useEffect } from 'react';
import { Search, GitBranch, FileText, Database, ArrowRight } from 'lucide-react';

export function SearchView({ apiFetch, query }) {
  const [results, setResults] = useState({
    workflows: [],
    documents: [],
    semantic_chunks: []
  });
  const [loading, setLoading] = useState(true);

  const performSearch = async () => {
    if (!query || query.length < 2) {
      setResults({ workflows: [], documents: [], semantic_chunks: [] });
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const data = await apiFetch(`/search?q=${encodeURIComponent(query)}`);
      setResults(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    performSearch();
  }, [query]);

  const totalResults = results.workflows.length + results.documents.length + results.semantic_chunks.length;

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <span className="w-6 h-6 border-2 border-indigo-500/20 border-t-indigo-500 rounded-full animate-spin"></span>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-extrabold text-white tracking-tight">Search Results</h1>
        <p className="text-zinc-400 mt-2 text-sm">
          Found {totalResults} matches for "{query}" across your workspace database.
        </p>
      </div>

      {totalResults === 0 ? (
        <div className="glass p-12 text-center rounded-2xl">
          <Search className="w-12 h-12 text-zinc-600 mx-auto mb-4" />
          <h3 className="text-white font-bold">No Results Found</h3>
          <p className="text-zinc-500 text-xs mt-1">Try modifying your query or uploading more documents.</p>
        </div>
      ) : (
        <div className="space-y-8">
          
          {/* Workflows matches */}
          {results.workflows.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-wider flex items-center gap-2">
                <GitBranch className="w-4 h-4 text-indigo-400" />
                <span>Workflows ({results.workflows.length})</span>
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {results.workflows.map(wf => (
                  <div key={wf.id} className="glass p-4 rounded-xl border border-zinc-800/80 flex items-center justify-between">
                    <div>
                      <h4 className="text-xs font-bold text-white">{wf.name}</h4>
                      <p className="text-[10px] text-zinc-400 mt-1 truncate max-w-[250px]">{wf.description || 'No description'}</p>
                    </div>
                    <span className="text-[9px] font-bold text-emerald-400 uppercase bg-emerald-500/10 border border-emerald-500/20 px-1.5 py-0.5 rounded">
                      {wf.status}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Documents matches */}
          {results.documents.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-wider flex items-center gap-2">
                <FileText className="w-4 h-4 text-violet-400" />
                <span>Files ({results.documents.length})</span>
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {results.documents.map(doc => (
                  <div key={doc.id} className="glass p-4 rounded-xl border border-zinc-800/80 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="p-2 bg-zinc-900 border border-zinc-800 text-indigo-400 rounded">
                        <FileText className="w-4 h-4" />
                      </div>
                      <div>
                        <h4 className="text-xs font-bold text-white">{doc.file_name}</h4>
                        <p className="text-[9px] text-zinc-500 mt-0.5">{doc.file_type}</p>
                      </div>
                    </div>
                    <span className="text-[9px] font-bold text-indigo-400 uppercase bg-indigo-500/5 border border-indigo-500/10 px-1.5 py-0.5 rounded">
                      {doc.status}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Semantic chunks matches */}
          {results.semantic_chunks.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-wider flex items-center gap-2">
                <Database className="w-4 h-4 text-emerald-400" />
                <span>Semantic Memories ({results.semantic_chunks.length})</span>
              </h3>
              <div className="space-y-3">
                {results.semantic_chunks.map((res, idx) => (
                  <div key={idx} className="glass p-4 rounded-xl border border-zinc-800/60 space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] font-bold text-white">{res.file_name}</span>
                      </div>
                      <span className="text-[9px] font-bold text-emerald-400 bg-emerald-500/5 border border-emerald-500/10 px-1.5 py-0.5 rounded">
                        {(res.similarity * 100).toFixed(1)}% Relevance
                      </span>
                    </div>
                    <p className="text-[10.5px] leading-relaxed text-zinc-300 font-mono select-text bg-zinc-950/20 p-2.5 rounded border border-zinc-900">
                      "{res.chunk_text}"
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}

        </div>
      )}

    </div>
  );
}
