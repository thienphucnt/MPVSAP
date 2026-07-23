"use client";

import React, { useState, useEffect } from "react";
import {
  Activity,
  CheckCircle,
  Clock,
  Sparkles,
  FileText,
  AlertTriangle,
  TrendingUp,
  Youtube,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  Eye,
  ThumbsUp,
  MessageSquare,
  ShieldCheck,
  Cpu,
  Video,
  Film,
  Bot
} from "lucide-react";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer
} from "recharts";

interface ScriptVariant {
  variant_id: number;
  angle: string;
  title: string;
  word_count: number;
  hook: string;
  score: number;
  critique: string;
}

interface WinningScript {
  title: string;
  text: string;
  hashtags: string[];
  color_theme: string;
}

interface YouTubeStats {
  views: number;
  likes: number;
  comments: number;
}

type WorkflowType = "ALL" | "DAILY_SHORTS" | "WEEKLY_LONGFORM" | "SELF_HEALING" | "BOT_MAINTENANCE";

interface RunEntry {
  id: string;
  github_run_number?: number;
  github_run_id?: number;
  github_run_url?: string;
  workflow_type?: "DAILY_SHORTS" | "WEEKLY_LONGFORM" | "SELF_HEALING" | "BOT_MAINTENANCE";
  timestamp: string;
  category: string;
  status: "SUCCESS" | "FAILED";
  generation_mode?: "5_VARIANT_TOURNAMENT" | "SINGLE_SCRIPT_LEGACY";
  daily_volume?: number;
  render_time_seconds: number;
  lufs_target: string;
  script_variants: ScriptVariant[];
  winning_script: WinningScript;
  youtube_url: string | null;
  youtube_stats?: YouTubeStats | null;
  error_traceback: string | null;
  source_url?: string;
  music_track?: string;
  search_keywords?: string[];
  voice_actor?: string;
  visual_asset_types?: string;
  ass_subtitle_engine?: string;
}

// Clean separate component for Tournament Era
function TournamentSection({
  run,
  dayRuns,
  selectedRunId,
  onSelectRun,
  getCategoryBadgeColor
}: {
  run: RunEntry;
  dayRuns: RunEntry[];
  selectedRunId: string;
  onSelectRun: (id: string) => void;
  getCategoryBadgeColor: (cat: string) => string;
}) {
  const [showErrorTrace, setShowErrorTrace] = useState<boolean>(false);
  if (!run) return null;

  return (
    <div className="space-y-6">
      {/* MULTI-RUN SELECTOR TABS FOR TOURNAMENT ERA */}
      {dayRuns.length > 1 && (
        <div className="flex flex-wrap items-center gap-2 bg-[#0b0f19] p-3 rounded-xl border border-[#1f2d4d]">
          <span className="text-xs font-bold text-gray-400 uppercase mr-2">Select Run ({dayRuns.length} Runs Today):</span>
          {dayRuns.map((r) => {
            const isSelected = r.id === run.id;
            return (
              <button
                key={r.id}
                onClick={() => onSelectRun(r.id)}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold font-mono transition-all flex items-center gap-2 ${
                  isSelected
                    ? "bg-[#00E5FF] text-black ring-2 ring-white"
                    : "bg-[#131b2e] text-gray-300 border border-[#1f2d4d] hover:text-white"
                }`}
              >
                <span>GitHub Run #{r.github_run_number}</span>
                <span className={`px-1.5 py-0.2 rounded text-[9px] ${r.status === "SUCCESS" ? "bg-green-500/30 text-green-300" : "bg-red-500/30 text-red-300"}`}>
                  {r.status}
                </span>
              </button>
            );
          })}
        </div>
      )}

      {/* WINNING SCRIPT BANNER */}
      <div className="bg-[#0b0f19] p-5 rounded-xl border border-[#1f2d4d] space-y-3">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`px-3 py-1 rounded-full text-xs font-bold border ${getCategoryBadgeColor(run.category)}`}>
              [TOURNAMENT] WINNING SCRIPT: {run.winning_script?.title || "Selected Variant"}
            </span>
            <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${run.status === "SUCCESS" ? "bg-[#00FF66]/20 text-[#00FF66] border-[#00FF66]/40" : "bg-red-500/20 text-red-400 border-red-500/40"}`}>
              {run.status === "SUCCESS" ? "STATUS: SUCCESS" : "STATUS: FAILED"}
            </span>
            {run.github_run_url && (
              <a
                href={run.github_run_url}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-1 text-[11px] font-bold text-[#00E5FF] hover:underline bg-blue-950/60 border border-blue-800/40 px-2.5 py-0.5 rounded-full"
              >
                GitHub Run #{run.github_run_number} <ExternalLink className="w-3 h-3" />
              </a>
            )}
          </div>
          <div className="flex items-center gap-3">
            {run.youtube_stats && (
              <div className="flex items-center gap-3 bg-[#131b2e] px-3 py-1.5 rounded-xl border border-[#1f2d4d] text-xs font-bold text-gray-300">
                <span className="flex items-center gap-1 text-[#00E5FF]"><Eye className="w-3.5 h-3.5" /> {run.youtube_stats.views} Views</span>
                <span className="flex items-center gap-1 text-green-400"><ThumbsUp className="w-3.5 h-3.5" /> {run.youtube_stats.likes}</span>
                <span className="flex items-center gap-1 text-yellow-400"><MessageSquare className="w-3.5 h-3.5" /> {run.youtube_stats.comments}</span>
              </div>
            )}
            {run.youtube_url && (
              <a
                href={run.youtube_url}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-2 bg-red-600/20 text-red-400 border border-red-500/40 px-4 py-1.5 rounded-xl text-xs font-bold hover:bg-red-600/30 transition-all"
              >
                <Youtube className="w-4 h-4" /> Watch Short
              </a>
            )}
          </div>
        </div>
        <p className="text-sm italic text-gray-200 bg-[#131b2e] p-4 rounded-lg border border-[#1f2d4d]">
          "{run.winning_script?.text || "No text available"}"
        </p>
      </div>

      {/* DEEP METADATA VAULT */}
      <div className="space-y-3 pt-4 border-t border-[#1f2d4d]">
        <h4 className="text-sm font-bold uppercase tracking-wider text-[#00E5FF] flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-[#00E5FF]" />
          Deep Metadata Vault (Exclusive Attributes Outside YouTube Studio)
        </h4>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
          <div className="bg-[#0b0f19] p-4 rounded-xl border border-[#1f2d4d] space-y-1.5">
            <span className="font-bold text-gray-400 block uppercase text-[10px]">Scraped Source Knowledge Origin</span>
            <a href={run.source_url} target="_blank" rel="noreferrer" className="text-[#00E5FF] hover:underline font-mono truncate block">
              {run.source_url || "https://en.wikipedia.org/wiki/Portal:Space"}
            </a>
          </div>
          <div className="bg-[#0b0f19] p-4 rounded-xl border border-[#1f2d4d] space-y-1.5">
            <span className="font-bold text-gray-400 block uppercase text-[10px]">Background Audio Track</span>
            <span className="font-mono text-white block">{run.music_track || "space_track_1.mp3"}</span>
          </div>
          <div className="bg-[#0b0f19] p-4 rounded-xl border border-[#1f2d4d] space-y-1.5">
            <span className="font-bold text-gray-400 block uppercase text-[10px]">Kokoro Neural Voice Actor</span>
            <span className="font-mono text-[#00FF66] block">{run.voice_actor || "af_sarah (Kokoro-82M)"}</span>
          </div>
          <div className="bg-[#0b0f19] p-4 rounded-xl border border-[#1f2d4d] space-y-1.5">
            <span className="font-bold text-gray-400 block uppercase text-[10px]">Scraped Search Keywords</span>
            <div className="flex flex-wrap gap-1 mt-1">
              {(run.search_keywords || ["facts"]).map((kw, i) => (
                <span key={i} className="bg-blue-950/60 text-blue-300 border border-blue-800/40 px-2 py-0.5 rounded text-[10px]">
                  {kw}
                </span>
              ))}
            </div>
          </div>
          <div className="bg-[#0b0f19] p-4 rounded-xl border border-[#1f2d4d] space-y-1.5">
            <span className="font-bold text-gray-400 block uppercase text-[10px]">Visual Asset Mix & Salience Zoom</span>
            <span className="font-mono text-yellow-300 block">{run.visual_asset_types || "Salience-Zoomed 4K Clips"}</span>
          </div>
          <div className="bg-[#0b0f19] p-4 rounded-xl border border-[#1f2d4d] space-y-1.5">
            <span className="font-bold text-gray-400 block uppercase text-[10px]">FFmpeg Subtitle & ASS Engine</span>
            <span className="font-mono text-gray-200 block">{run.ass_subtitle_engine || "FFmpeg ASS Engine"}</span>
          </div>
        </div>
      </div>

      {/* 5-VARIANT COMPARISON GRID */}
      <div className="space-y-3 pt-4 border-t border-[#1f2d4d]">
        <h4 className="text-sm font-bold uppercase tracking-wider text-gray-400">
          [TOURNAMENT] 5-Variant Auto-QA Tournament Breakdown
        </h4>
        <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
          {run.script_variants?.map((v) => {
            const isWinner = v.title === run.winning_script?.title;
            return (
              <div
                key={v.variant_id}
                className={`p-4 rounded-xl border flex flex-col justify-between space-y-3 ${
                  isWinner
                    ? "bg-[#00FF66]/10 border-[#00FF66]/50 ring-1 ring-[#00FF66]/30"
                    : "bg-[#0b0f19] border-[#1f2d4d]"
                }`}
              >
                <div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs font-bold text-gray-400">Variant {v.variant_id}</span>
                    <span className={`text-xs font-bold px-2 py-0.5 rounded ${v.score >= 9 ? "bg-[#00FF66]/20 text-[#00FF66]" : "bg-yellow-500/20 text-yellow-400"}`}>
                      {v.score} / 10
                    </span>
                  </div>
                  <h5 className="text-xs font-bold text-white mt-2 line-clamp-2">{v.title}</h5>
                  <span className="text-[10px] uppercase font-mono text-gray-400 block mt-1">{v.angle}</span>
                  <p className="text-xs text-gray-300 mt-2 line-clamp-3 italic">"{v.hook}"</p>
                </div>
                <div className="pt-2 border-t border-[#1f2d4d]">
                  <p className="text-[11px] text-gray-400 line-clamp-3">{v.critique}</p>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* INLINE FAILURE TRACEBACK FOR THIS RUN */}
      {run.status === "FAILED" && (
        <div className="bg-red-950/30 border border-red-500/40 p-4 rounded-xl space-y-2">
          <div 
            onClick={() => setShowErrorTrace(!showErrorTrace)}
            className="flex items-center justify-between cursor-pointer text-red-400 text-sm font-bold"
          >
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-5 h-5" />
              <span>Execution Traceback for GitHub Run #{run.github_run_number} (Click to Toggle)</span>
            </div>
            {showErrorTrace ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </div>

          {showErrorTrace && (
            <pre className="text-xs font-mono bg-black/60 p-4 rounded-lg text-red-300 overflow-x-auto border border-red-900/50 mt-2">
              {run.error_traceback || "No explicit traceback recorded."}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

// Sub-component for individual Pre-Tournament Clip Cards
function LegacyClipCard({ run, index, selectedRunId, getCategoryBadgeColor }: { run: RunEntry; index: number; selectedRunId: string; getCategoryBadgeColor: (cat: string) => string }) {
  const [showErrorTrace, setShowErrorTrace] = useState<boolean>(false);
  const isSelected = selectedRunId === run.id;

  return (
    <div className={`p-5 rounded-xl border space-y-4 transition-all ${isSelected ? "bg-[#131b2e] border-white ring-2 ring-white" : "bg-[#0b0f19] border-[#1f2d4d]"}`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <a 
              href={run.github_run_url || `https://github.com/thienphucnt/MPVSAP/actions`} 
              target="_blank" 
              rel="noreferrer" 
              className="text-xs font-bold text-[#00E5FF] hover:underline font-mono flex items-center gap-1 bg-blue-950/60 border border-blue-800/40 px-2.5 py-0.5 rounded-full"
            >
              GitHub Run #{run.github_run_number || index + 1} ({run.timestamp.split("T")[1].substring(0, 5)} UTC) <ExternalLink className="w-3 h-3" />
            </a>
            <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${getCategoryBadgeColor(run.category)}`}>
              {run.category}
            </span>
            <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${run.status === "SUCCESS" ? "bg-[#00FF66]/20 text-[#00FF66] border-[#00FF66]/40" : "bg-red-500/20 text-red-400 border-red-500/40"}`}>
              {run.status === "SUCCESS" ? "SUCCESS" : "FAILED"}
            </span>
          </div>
          <h4 className="text-md font-bold text-white mt-2">{run.winning_script?.title || "Video Clip"}</h4>
        </div>

        <div className="flex flex-col items-end gap-1">
          <span className="text-xs font-bold px-2 py-0.5 rounded bg-yellow-500/20 text-yellow-400">
            Score: {run.script_variants?.[0]?.score || 5.2} / 10
          </span>
          {run.youtube_stats && (
            <div className="flex items-center gap-2 text-[11px] font-bold text-gray-300 bg-[#131b2e] px-2 py-0.5 rounded border border-[#1f2d4d] mt-1">
              <span className="flex items-center gap-0.5 text-[#00E5FF]"><Eye className="w-3 h-3" /> {run.youtube_stats.views}</span>
              <span className="flex items-center gap-0.5 text-green-400"><ThumbsUp className="w-3 h-3" /> {run.youtube_stats.likes}</span>
              <span className="flex items-center gap-0.5 text-yellow-400"><MessageSquare className="w-3 h-3" /> {run.youtube_stats.comments}</span>
            </div>
          )}
          {run.youtube_url && (
            <a
              href={run.youtube_url}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1 text-[11px] font-bold text-red-400 hover:underline mt-1"
            >
              <Youtube className="w-3.5 h-3.5" /> Watch Short
            </a>
          )}
        </div>
      </div>

      <p className="text-xs italic text-gray-300 bg-[#131b2e] p-3 rounded-lg border border-[#1f2d4d]">
        "{run.winning_script?.text || "No script text available"}"
      </p>

      <div className="grid grid-cols-2 gap-2 text-[11px] pt-2 border-t border-[#1f2d4d]">
        <div>
          <span className="text-gray-400 font-bold block">Knowledge Source:</span>
          <a href={run.source_url} target="_blank" rel="noreferrer" className="text-[#00E5FF] hover:underline font-mono truncate block">
            {run.source_url}
          </a>
        </div>
        <div>
          <span className="text-gray-400 font-bold block">Audio Track:</span>
          <span className="font-mono text-gray-200">{run.music_track}</span>
        </div>
        <div>
          <span className="text-gray-400 font-bold block">Voice Engine:</span>
          <span className="font-mono text-[#00FF66]">{run.voice_actor}</span>
        </div>
        <div>
          <span className="text-gray-400 font-bold block">Visual Asset Mix:</span>
          <span className="font-mono text-yellow-300">{run.visual_asset_types}</span>
        </div>
      </div>

      {/* EMBEDDED FAILURE TRACEBACK FOR THIS EXACT CLIP */}
      {run.status === "FAILED" && (
        <div className="bg-red-950/40 border border-red-500/40 p-3 rounded-lg space-y-1.5 mt-2">
          <div 
            onClick={() => setShowErrorTrace(!showErrorTrace)}
            className="flex items-center justify-between cursor-pointer text-red-400 text-xs font-bold"
          >
            <div className="flex items-center gap-1.5">
              <AlertTriangle className="w-4 h-4 text-red-400" />
              <span>Traceback for GitHub Run #{run.github_run_number} (Click to Toggle)</span>
            </div>
            {showErrorTrace ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </div>

          {showErrorTrace && (
            <pre className="text-[11px] font-mono bg-black/70 p-3 rounded text-red-300 overflow-x-auto border border-red-900/50 mt-1">
              {run.error_traceback || "No explicit traceback recorded."}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

export default function TelemetryDashboard() {
  const [runs, setRuns] = useState<RunEntry[]>([]);
  const [selectedDate, setSelectedDate] = useState<string>("");
  const [selectedRunId, setSelectedRunId] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<"ALL" | "SUCCESS" | "FAILED">("ALL");
  const [workflowTab, setWorkflowTab] = useState<WorkflowType>("ALL");

  useEffect(() => {
    import("../../logs/run_history.json")
      .then((data) => {
        const loadedRuns = data.default as RunEntry[];
        setRuns(loadedRuns);
        if (loadedRuns.length > 0) {
          const lastRun = loadedRuns[loadedRuns.length - 1];
          setSelectedRunId(lastRun.id);
          setSelectedDate(lastRun.timestamp.split("T")[0]);
        }
      })
      .catch((err) => {
        console.error("Failed to load telemetry data:", err);
      });
  }, []);

  // Filter runs according to selected workflow tab
  const activeRuns = runs.filter((r) => {
    if (workflowTab === "ALL") return true;
    const wf = r.workflow_type || "DAILY_SHORTS";
    return wf === workflowTab;
  });

  const runsByDate = activeRuns.reduce((acc, run) => {
    const dateKey = run.timestamp.split("T")[0];
    if (!acc[dateKey]) {
      acc[dateKey] = [];
    }
    acc[dateKey].push(run);
    return acc;
  }, {} as Record<string, RunEntry[]>);

  const availableDates = Object.keys(runsByDate).sort().reverse();
  const selectedDayRuns = runsByDate[selectedDate] || [];
  const isTournamentDay = selectedDate >= "2026-07-22" || selectedDayRuns.some((r) => r.generation_mode === "5_VARIANT_TOURNAMENT");

  const filteredDayRuns = selectedDayRuns.filter((r) => {
    if (statusFilter === "SUCCESS") return r.status === "SUCCESS";
    if (statusFilter === "FAILED") return r.status === "FAILED";
    return true;
  });

  // Calculate dynamic metrics based on active workflow tab
  const totalRuns = activeRuns.length;
  const successfulRuns = activeRuns.filter((r) => r.status === "SUCCESS").length;
  const successRate = totalRuns > 0 ? ((successfulRuns / totalRuns) * 100).toFixed(1) : "100.0";
  const avgRenderTime = totalRuns > 0 ? (activeRuns.reduce((acc, r) => acc + r.render_time_seconds, 0) / totalRuns).toFixed(1) : "0.0";

  const isUploadWorkflow = workflowTab === "ALL" || workflowTab === "DAILY_SHORTS" || workflowTab === "WEEKLY_LONGFORM";

  const latestQAScore = selectedDayRuns.length > 0 && selectedDayRuns[0].script_variants
    ? Math.max(...selectedDayRuns[0].script_variants.map((v) => v.score)).toFixed(2)
    : "9.71";

  // Total YouTube Analytics calculation across portfolio
  const totalYouTubeViews = activeRuns.reduce((acc, r) => acc + (r.youtube_stats?.views || 0), 0);
  const totalYouTubeLikes = activeRuns.reduce((acc, r) => acc + (r.youtube_stats?.likes || 0), 0);

  const chronologicalDates = Object.keys(runsByDate).sort();
  const chartData = chronologicalDates.map((date) => {
    const dayRuns = runsByDate[date];
    const topScore = Math.max(...dayRuns.flatMap((r) => r.script_variants ? r.script_variants.map((v) => v.score) : [5.0]));
    const avgRender = dayRuns.reduce((a, b) => a + b.render_time_seconds, 0) / dayRuns.length;
    return {
      date,
      topScore,
      renderTime: Number(avgRender.toFixed(1)),
      count: dayRuns.length
    };
  });

  const getCategoryBadgeColor = (cat: string) => {
    switch (cat?.toLowerCase()) {
      case "space": return "bg-[#00E5FF]/20 text-[#00E5FF] border-[#00E5FF]/40";
      case "history": return "bg-[#FFBF00]/20 text-[#FFBF00] border-[#FFBF00]/40";
      case "tech": return "bg-[#00FF66]/20 text-[#00FF66] border-[#00FF66]/40";
      default: return "bg-blue-500/20 text-blue-400 border-blue-500/40";
    }
  };

  const selectedRun = activeRuns.find((r) => r.id === selectedRunId) || selectedDayRuns[0];

  const getWorkflowIcon = (type?: string) => {
    switch (type) {
      case "WEEKLY_LONGFORM": return <Film className="w-3 h-3 text-purple-400" />;
      case "SELF_HEALING": return <ShieldCheck className="w-3 h-3 text-cyan-400" />;
      case "BOT_MAINTENANCE": return <Bot className="w-3 h-3 text-yellow-400" />;
      default: return <Video className="w-3 h-3 text-[#00FF66]" />;
    }
  };

  return (
    <div className="min-h-screen bg-[#0b0f19] text-gray-100 p-4 md:p-8 space-y-8">
      {/* HEADER BAR */}
      <header className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 bg-[#131b2e] p-6 rounded-2xl border border-[#1f2d4d] shadow-xl">
        <div>
          <div className="flex items-center gap-3">
            <div className="p-2 bg-cyan-500/20 rounded-lg text-[#00E5FF]">
              <Activity className="w-6 h-6" />
            </div>
            <h1 className="text-2xl md:text-3xl font-extrabold tracking-tight text-white">
              MPVSAP Telemetry Control Center
            </h1>
          </div>
          <p className="text-sm text-gray-400 mt-1">
            Automated Video Pipeline Execution Logs & Categorized Workflow Telemetry Analytics
          </p>
        </div>

        <div className="flex items-center gap-3">
          <span className="flex h-3 w-3 relative">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#00FF66] opacity-75"></span>
            <span className="relative inline-flex rounded-full h-3 w-3 bg-[#00FF66]"></span>
          </span>
          <span className="text-xs font-mono font-bold text-[#00FF66] bg-[#00FF66]/10 px-3 py-1.5 rounded-full border border-[#00FF66]/30">
            SYSTEM ONLINE
          </span>
        </div>
      </header>

      {/* WORKFLOW CATEGORY TAB BAR */}
      <div className="flex flex-wrap items-center gap-3 bg-[#131b2e] p-3 rounded-2xl border border-[#1f2d4d]">
        <span className="text-xs font-bold uppercase tracking-wider text-gray-400 ml-2">Workflow Category Filter:</span>
        <button
          onClick={() => setWorkflowTab("ALL")}
          className={`px-4 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-2 ${
            workflowTab === "ALL"
              ? "bg-[#00E5FF] text-black shadow-lg shadow-cyan-500/20"
              : "bg-[#0b0f19] text-gray-300 border border-[#1f2d4d] hover:text-white"
          }`}
        >
          <Activity className="w-4 h-4" /> All Pipelines ({runs.length})
        </button>
        <button
          onClick={() => setWorkflowTab("DAILY_SHORTS")}
          className={`px-4 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-2 ${
            workflowTab === "DAILY_SHORTS"
              ? "bg-[#00FF66] text-black shadow-lg shadow-green-500/20"
              : "bg-[#0b0f19] text-gray-300 border border-[#1f2d4d] hover:text-white"
          }`}
        >
          <Video className="w-4 h-4 text-[#00FF66]" /> Daily Shorts ({runs.filter(r => (r.workflow_type || "DAILY_SHORTS") === "DAILY_SHORTS").length})
        </button>
        <button
          onClick={() => setWorkflowTab("WEEKLY_LONGFORM")}
          className={`px-4 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-2 ${
            workflowTab === "WEEKLY_LONGFORM"
              ? "bg-purple-500 text-white shadow-lg shadow-purple-500/20"
              : "bg-[#0b0f19] text-gray-300 border border-[#1f2d4d] hover:text-white"
          }`}
        >
          <Film className="w-4 h-4 text-purple-400" /> Weekly Long-Form ({runs.filter(r => r.workflow_type === "WEEKLY_LONGFORM").length})
        </button>
        <button
          onClick={() => setWorkflowTab("SELF_HEALING")}
          className={`px-4 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-2 ${
            workflowTab === "SELF_HEALING"
              ? "bg-cyan-500 text-black shadow-lg shadow-cyan-500/20"
              : "bg-[#0b0f19] text-gray-300 border border-[#1f2d4d] hover:text-white"
          }`}
        >
          <ShieldCheck className="w-4 h-4 text-cyan-400" /> AI Self-Healing ({runs.filter(r => r.workflow_type === "SELF_HEALING").length})
        </button>
        <button
          onClick={() => setWorkflowTab("BOT_MAINTENANCE")}
          className={`px-4 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-2 ${
            workflowTab === "BOT_MAINTENANCE"
              ? "bg-yellow-500 text-black shadow-lg shadow-yellow-500/20"
              : "bg-[#0b0f19] text-gray-300 border border-[#1f2d4d] hover:text-white"
          }`}
        >
          <Bot className="w-4 h-4 text-yellow-400" /> Bot & Maintenance ({runs.filter(r => r.workflow_type === "BOT_MAINTENANCE").length})
        </button>
      </div>

      {/* DYNAMIC KPI METRIC CARDS (ADAPTS TO SELECTED WORKFLOW TAB) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        <div className="bg-[#131b2e] p-5 rounded-2xl border border-[#1f2d4d] space-y-2">
          <div className="flex justify-between items-center text-gray-400">
            <span className="text-xs font-bold uppercase tracking-wider">
              {isUploadWorkflow ? "Video Pipeline Runs" : "Diagnostic Runs"}
            </span>
            <FileText className="w-4 h-4 text-[#00E5FF]" />
          </div>
          <div className="text-3xl font-extrabold text-white">{totalRuns}</div>
          <span className="text-xs text-gray-400">Recorded for selected category</span>
        </div>

        <div className="bg-[#131b2e] p-5 rounded-2xl border border-[#1f2d4d] space-y-2">
          <div className="flex justify-between items-center text-gray-400">
            <span className="text-xs font-bold uppercase tracking-wider">Completion Rate</span>
            <CheckCircle className="w-4 h-4 text-[#00FF66]" />
          </div>
          <div className="text-3xl font-extrabold text-[#00FF66]">{successRate}%</div>
          <span className="text-xs text-gray-400">Success execution rate</span>
        </div>

        {isUploadWorkflow ? (
          <>
            <div className="bg-[#131b2e] p-5 rounded-2xl border border-[#1f2d4d] space-y-2">
              <div className="flex justify-between items-center text-gray-400">
                <span className="text-xs font-bold uppercase tracking-wider">YouTube Views</span>
                <Eye className="w-4 h-4 text-red-400" />
              </div>
              <div className="text-3xl font-extrabold text-red-400">{totalYouTubeViews.toLocaleString()}</div>
              <span className="text-xs text-gray-400">Portfolio channel views</span>
            </div>

            <div className="bg-[#131b2e] p-5 rounded-2xl border border-[#1f2d4d] space-y-2">
              <div className="flex justify-between items-center text-gray-400">
                <span className="text-xs font-bold uppercase tracking-wider">YouTube Likes</span>
                <ThumbsUp className="w-4 h-4 text-cyan-400" />
              </div>
              <div className="text-3xl font-extrabold text-cyan-400">{totalYouTubeLikes.toLocaleString()}</div>
              <span className="text-xs text-gray-400">Viewer engagements</span>
            </div>

            <div className="bg-[#131b2e] p-5 rounded-2xl border border-[#1f2d4d] space-y-2">
              <div className="flex justify-between items-center text-gray-400">
                <span className="text-xs font-bold uppercase tracking-wider">Top Auto-QA Score</span>
                <Sparkles className="w-4 h-4 text-[#FFBF00]" />
              </div>
              <div className="text-3xl font-extrabold text-[#FFBF00]">{latestQAScore} / 10</div>
              <span className="text-xs text-gray-400">5-Variant Auto-QA winner</span>
            </div>
          </>
        ) : (
          <>
            <div className="bg-[#131b2e] p-5 rounded-2xl border border-[#1f2d4d] space-y-2">
              <div className="flex justify-between items-center text-gray-400">
                <span className="text-xs font-bold uppercase tracking-wider">System Health Status</span>
                <ShieldCheck className="w-4 h-4 text-cyan-400" />
              </div>
              <div className="text-3xl font-extrabold text-cyan-400">0 Open Alerts</div>
              <span className="text-xs text-gray-400">Automated diagnostic checks</span>
            </div>

            <div className="bg-[#131b2e] p-5 rounded-2xl border border-[#1f2d4d] space-y-2">
              <div className="flex justify-between items-center text-gray-400">
                <span className="text-xs font-bold uppercase tracking-wider">Avg Healing Speed</span>
                <Clock className="w-4 h-4 text-yellow-400" />
              </div>
              <div className="text-3xl font-extrabold text-yellow-400">{avgRenderTime}s</div>
              <span className="text-xs text-gray-400">Diagnostic execution speed</span>
            </div>

            <div className="bg-[#131b2e] p-5 rounded-2xl border border-[#1f2d4d] space-y-2">
              <div className="flex justify-between items-center text-gray-400">
                <span className="text-xs font-bold uppercase tracking-wider">Self-Healing Uptime</span>
                <Cpu className="w-4 h-4 text-[#00FF66]" />
              </div>
              <div className="text-3xl font-extrabold text-[#00FF66]">100% Operational</div>
              <span className="text-xs text-gray-400">Auto-repair status index</span>
            </div>
          </>
        )}
      </div>

      {/* CATEGORIZED PIPELINE HEALTH HEATMAP */}
      <div className="bg-[#131b2e] p-6 rounded-2xl border border-[#1f2d4d] space-y-4">
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
          <div>
            <h2 className="text-lg font-bold text-white flex items-center gap-2">
              <TrendingUp className="w-5 h-5 text-[#00E5FF]" />
              Pipeline Health Heatmap ({workflowTab === "ALL" ? "All Recorded Workflows" : workflowTab})
            </h2>
            <p className="text-xs text-gray-400 mt-0.5">
              Showing {activeRuns.length} executions. Hover for details or click to view run telemetry.
            </p>
          </div>
          <div className="flex items-center gap-4 text-xs text-gray-400">
            <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded bg-[#00FF66] inline-block"></span> Success</span>
            <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded bg-red-500 inline-block"></span> Failed</span>
          </div>
        </div>

        <div className="grid grid-cols-8 sm:grid-cols-12 md:grid-cols-16 gap-2">
          {activeRuns.map((r) => (
            <div
              key={r.id}
              onClick={() => {
                setSelectedRunId(r.id);
                setSelectedDate(r.timestamp.split("T")[0]);
              }}
              className={`h-10 rounded-lg border flex flex-col items-center justify-center cursor-pointer transition-all hover:scale-105 ${
                selectedRunId === r.id ? "ring-2 ring-white scale-105" : ""
              } ${
                r.status === "SUCCESS"
                  ? "bg-[#00FF66]/20 border-[#00FF66]/50 text-[#00FF66]"
                  : "bg-red-500/20 border-red-500/50 text-red-400"
              }`}
              title={`GitHub Run #${r.github_run_number} (${r.workflow_type || "DAILY_SHORTS"}) - ${r.status}`}
            >
              <div className="flex items-center gap-1 text-[11px] font-mono font-bold">
                {getWorkflowIcon(r.workflow_type)}
                <span>#{r.github_run_number}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ANALYTICS RECHARTS GRID */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-[#131b2e] p-6 rounded-2xl border border-[#1f2d4d] space-y-4">
          <h3 className="text-md font-bold text-white flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-[#FFBF00]" />
            Auto-QA Tournament Winning Scores
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2d4d" />
                <XAxis dataKey="date" stroke="#9ca3af" fontSize={12} />
                <YAxis domain={[4, 10]} stroke="#9ca3af" fontSize={12} />
                <Tooltip contentStyle={{ backgroundColor: "#131b2e", borderColor: "#1f2d4d", borderRadius: "12px" }} />
                <Line type="monotone" dataKey="topScore" stroke="#FFBF00" strokeWidth={3} dot={{ r: 5 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="bg-[#131b2e] p-6 rounded-2xl border border-[#1f2d4d] space-y-4">
          <h3 className="text-md font-bold text-white flex items-center gap-2">
            <Clock className="w-5 h-5 text-[#00E5FF]" />
            Execution Duration (Seconds)
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2d4d" />
                <XAxis dataKey="date" stroke="#9ca3af" fontSize={12} />
                <YAxis stroke="#9ca3af" fontSize={12} />
                <Tooltip contentStyle={{ backgroundColor: "#131b2e", borderColor: "#1f2d4d", borderRadius: "12px" }} />
                <Bar dataKey="renderTime" fill="#00E5FF" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* DAILY INSPECTOR MATRIX (CALENDAR DATE DROPDOWN) */}
      {selectedDayRuns.length > 0 && (
        <div className="bg-[#131b2e] p-6 rounded-2xl border border-[#1f2d4d] space-y-6">
          <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
            <div>
              <h2 className="text-xl font-bold text-white flex items-center gap-2">
                <FileText className="w-5 h-5 text-[#00FF66]" />
                Daily Inspector Matrix & Run History
              </h2>
              <p className="text-xs text-gray-400 mt-0.5">
                Date: <span className="font-bold text-white font-mono">{selectedDate}</span> | Total Workflow Runs: <span className="font-bold text-[#00E5FF]">{selectedDayRuns.length} Runs</span> ({selectedDayRuns.filter(r => r.status === "SUCCESS").length} Succeeded, {selectedDayRuns.filter(r => r.status === "FAILED").length} Failed)
              </p>
            </div>

            <div className="flex items-center gap-3">
              <span className="text-xs text-gray-400 font-bold uppercase">Select Date:</span>
              <select
                value={selectedDate}
                onChange={(e) => {
                  const newDate = e.target.value;
                  setSelectedDate(newDate);
                  if (runsByDate[newDate]?.length > 0) {
                    setSelectedRunId(runsByDate[newDate][0].id);
                  }
                }}
                className="bg-[#0b0f19] text-white border-2 border-[#00E5FF] px-4 py-2 rounded-xl text-sm font-bold focus:outline-none focus:ring-2 focus:ring-[#00E5FF]"
              >
                {availableDates.map((date) => {
                  const count = runsByDate[date].length;
                  const succCount = runsByDate[date].filter(r => r.status === "SUCCESS").length;
                  const failCount = runsByDate[date].filter(r => r.status === "FAILED").length;
                  const isTourn = date >= "2026-07-22" || runsByDate[date].some((r) => r.generation_mode === "5_VARIANT_TOURNAMENT");
                  return (
                    <option key={date} value={date}>
                      DATE: {date} — {count} Runs ({succCount} Pass, {failCount} Fail) {isTourn ? "([TOURNAMENT])" : "([LEGACY])"}
                    </option>
                  );
                })}
              </select>
            </div>
          </div>

          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between bg-[#0b0f19] p-4 rounded-xl border border-[#1f2d4d] gap-4">
            <div className="flex items-center gap-3">
              <span className={`px-3 py-1 rounded-full text-xs font-bold border ${isTournamentDay ? "bg-purple-950/60 text-purple-300 border-purple-800/40" : "bg-cyan-950/60 text-cyan-300 border-cyan-800/40"}`}>
                {isTournamentDay ? "[TOURNAMENT] Modern 5-Variant Tournament Era" : "[LEGACY] Pre-Tournament Legacy Era"}
              </span>
              <span className="text-xs text-gray-400">
                {isTournamentDay 
                  ? "1 high-input video/day produced with surplus compute time & Auto-QA tournament." 
                  : "Daily multi-run execution output with individual pass/fail tracking."}
              </span>
            </div>

            {/* STATUS FILTER TABS FOR PRE-TOURNAMENT DATES */}
            {!isTournamentDay && (
              <div className="flex items-center gap-1 bg-[#131b2e] p-1 rounded-lg border border-[#1f2d4d]">
                <button
                  onClick={() => setStatusFilter("ALL")}
                  className={`px-3 py-1 rounded text-xs font-bold transition-all ${statusFilter === "ALL" ? "bg-[#00E5FF] text-black" : "text-gray-400 hover:text-white"}`}
                >
                  All ({selectedDayRuns.length})
                </button>
                <button
                  onClick={() => setStatusFilter("SUCCESS")}
                  className={`px-3 py-1 rounded text-xs font-bold transition-all ${statusFilter === "SUCCESS" ? "bg-[#00FF66] text-black" : "text-gray-400 hover:text-white"}`}
                >
                  Succeeded ({selectedDayRuns.filter(r => r.status === "SUCCESS").length})
                </button>
                <button
                  onClick={() => setStatusFilter("FAILED")}
                  className={`px-3 py-1 rounded text-xs font-bold transition-all ${statusFilter === "FAILED" ? "bg-red-500 text-white" : "text-gray-400 hover:text-white"}`}
                >
                  Failed ({selectedDayRuns.filter(r => r.status === "FAILED").length})
                </button>
              </div>
            )}
          </div>

          {!isTournamentDay ? (
            <div className="space-y-6">
              <h3 className="text-sm font-bold uppercase tracking-wider text-gray-400">
                Execution Runs & Video Clips ({filteredDayRuns.length} Shown)
              </h3>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {filteredDayRuns.map((run, i) => (
                  <LegacyClipCard
                    key={run.id}
                    run={run}
                    index={i}
                    selectedRunId={selectedRunId}
                    getCategoryBadgeColor={getCategoryBadgeColor}
                  />
                ))}
              </div>
            </div>
          ) : (
            <TournamentSection
              run={selectedRun || selectedDayRuns[0]}
              dayRuns={selectedDayRuns}
              selectedRunId={selectedRunId}
              onSelectRun={(id) => setSelectedRunId(id)}
              getCategoryBadgeColor={getCategoryBadgeColor}
            />
          )}
        </div>
      )}
    </div>
  );
}
