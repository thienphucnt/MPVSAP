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
  ChevronDown,
  ChevronUp
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

interface RunEntry {
  id: string;
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
  error_traceback: string | null;
  source_url?: string;
  music_track?: string;
  search_keywords?: string[];
  voice_actor?: string;
  visual_asset_types?: string;
  ass_subtitle_engine?: string;
}

// Clean separate component for Tournament Era
function TournamentSection({ run, getCategoryBadgeColor }: { run: RunEntry; getCategoryBadgeColor: (cat: string) => string }) {
  if (!run) return null;
  return (
    <div className="space-y-6">
      {/* WINNING SCRIPT BANNER */}
      <div className="bg-[#0b0f19] p-5 rounded-xl border border-[#1f2d4d] space-y-3">
        <div className="flex items-center justify-between">
          <span className={`px-3 py-1 rounded-full text-xs font-bold border ${getCategoryBadgeColor(run.category)}`}>
            [TOURNAMENT] WINNING SCRIPT: {run.winning_script?.title || "Selected Variant"}
          </span>
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
    </div>
  );
}

export default function TelemetryDashboard() {
  const [runs, setRuns] = useState<RunEntry[]>([]);
  const [selectedDate, setSelectedDate] = useState<string>("");
  const [selectedRunId, setSelectedRunId] = useState<string>("");
  const [showErrorTrace, setShowErrorTrace] = useState<boolean>(false);

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

  const runsByDate = runs.reduce((acc, run) => {
    const dateKey = run.timestamp.split("T")[0];
    if (!acc[dateKey]) {
      acc[dateKey] = [];
    }
    acc[dateKey].push(run);
    return acc;
  }, {} as Record<string, RunEntry[]>);

  const availableDates = Object.keys(runsByDate).sort().reverse();
  const selectedDayRuns = runsByDate[selectedDate] || [];
  const isTournamentDay = selectedDayRuns.some((r) => r.generation_mode === "5_VARIANT_TOURNAMENT");

  const totalRuns = runs.length;
  const successfulRuns = runs.filter((r) => r.status === "SUCCESS").length;
  const successRate = totalRuns > 0 ? ((successfulRuns / totalRuns) * 100).toFixed(1) : "100.0";
  const avgRenderTime = totalRuns > 0 ? (runs.reduce((acc, r) => acc + r.render_time_seconds, 0) / totalRuns).toFixed(1) : "0.0";
  const latestQAScore = selectedDayRuns.length > 0 && selectedDayRuns[0].script_variants
    ? Math.max(...selectedDayRuns[0].script_variants.map((v) => v.score)).toFixed(2)
    : "9.71";

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

  const selectedRun = runs.find((r) => r.id === selectedRunId) || selectedDayRuns[0];

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
            Automated Video Pipeline Execution Logs & Telemetry Analytics
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

      {/* KPI METRIC CARDS */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-[#131b2e] p-5 rounded-2xl border border-[#1f2d4d] space-y-2">
          <div className="flex justify-between items-center text-gray-400">
            <span className="text-xs font-bold uppercase tracking-wider">Total Pipeline Runs</span>
            <FileText className="w-4 h-4 text-[#00E5FF]" />
          </div>
          <div className="text-3xl font-extrabold text-white">{totalRuns}</div>
          <span className="text-xs text-gray-400">Recorded across 90 days</span>
        </div>

        <div className="bg-[#131b2e] p-5 rounded-2xl border border-[#1f2d4d] space-y-2">
          <div className="flex justify-between items-center text-gray-400">
            <span className="text-xs font-bold uppercase tracking-wider">Pipeline Success Rate</span>
            <CheckCircle className="w-4 h-4 text-[#00FF66]" />
          </div>
          <div className="text-3xl font-extrabold text-[#00FF66]">{successRate}%</div>
          <span className="text-xs text-gray-400">Execution completion rate</span>
        </div>

        <div className="bg-[#131b2e] p-5 rounded-2xl border border-[#1f2d4d] space-y-2">
          <div className="flex justify-between items-center text-gray-400">
            <span className="text-xs font-bold uppercase tracking-wider">Avg Render Time</span>
            <Clock className="w-4 h-4 text-cyan-400" />
          </div>
          <div className="text-3xl font-extrabold text-white">{avgRenderTime}s</div>
          <span className="text-xs text-gray-400">FFmpeg / MoviePy engine</span>
        </div>

        <div className="bg-[#131b2e] p-5 rounded-2xl border border-[#1f2d4d] space-y-2">
          <div className="flex justify-between items-center text-gray-400">
            <span className="text-xs font-bold uppercase tracking-wider">Top Auto-QA Score</span>
            <Sparkles className="w-4 h-4 text-[#FFBF00]" />
          </div>
          <div className="text-3xl font-extrabold text-[#FFBF00]">{latestQAScore} / 10</div>
          <span className="text-xs text-gray-400">5-Variant Auto-QA winner</span>
        </div>
      </div>

      {/* PIPELINE HEALTH HEATMAP */}
      <div className="bg-[#131b2e] p-6 rounded-2xl border border-[#1f2d4d] space-y-4">
        <div className="flex justify-between items-center">
          <h2 className="text-lg font-bold text-white flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-[#00E5FF]" />
            Pipeline Health Heatmap (Past 90 Days Activity)
          </h2>
          <div className="flex items-center gap-4 text-xs text-gray-400">
            <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded bg-[#00FF66] inline-block"></span> Success</span>
            <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded bg-red-500 inline-block"></span> Failed</span>
          </div>
        </div>

        <div className="grid grid-cols-10 md:grid-cols-15 gap-2">
          {runs.map((r, idx) => (
            <div
              key={r.id}
              onClick={() => {
                setSelectedRunId(r.id);
                setSelectedDate(r.timestamp.split("T")[0]);
              }}
              className={`h-10 rounded-lg border flex items-center justify-center cursor-pointer transition-all hover:scale-105 ${
                selectedRunId === r.id ? "ring-2 ring-white scale-105" : ""
              } ${
                r.status === "SUCCESS"
                  ? "bg-[#00FF66]/20 border-[#00FF66]/50 text-[#00FF66]"
                  : "bg-red-500/20 border-red-500/50 text-red-400"
              }`}
              title={`Run ${idx + 1} (${r.category}) - ${r.status}`}
            >
              <span className="text-xs font-mono font-bold">{idx + 1}</span>
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
            FFmpeg Render Execution Duration (Seconds)
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
                Date: <span className="font-bold text-white font-mono">{selectedDate}</span> | Total Videos Generated: <span className="font-bold text-[#00E5FF]">{selectedDayRuns.length} Videos</span>
              </p>
            </div>

            <div className="flex items-center gap-3">
              <span className="text-xs text-gray-400 font-bold uppercase">Select Date:</span>
              <select
                value={selectedDate}
                onChange={(e) => setSelectedDate(e.target.value)}
                className="bg-[#0b0f19] text-white border-2 border-[#00E5FF] px-4 py-2 rounded-xl text-sm font-bold focus:outline-none focus:ring-2 focus:ring-[#00E5FF]"
              >
                {availableDates.map((date) => {
                  const count = runsByDate[date].length;
                  const isTourn = runsByDate[date].some((r) => r.generation_mode === "5_VARIANT_TOURNAMENT");
                  return (
                    <option key={date} value={date}>
                      DATE: {date} — {count} {count === 1 ? "Video Uploaded" : "Videos Uploaded"} {isTourn ? "([TOURNAMENT] Tournament Era)" : "([LEGACY] 6-Video Daily Output)"}
                    </option>
                  );
                })}
              </select>
            </div>
          </div>

          <div className="flex items-center justify-between bg-[#0b0f19] p-4 rounded-xl border border-[#1f2d4d]">
            <div className="flex items-center gap-3">
              <span className={`px-3 py-1 rounded-full text-xs font-bold border ${isTournamentDay ? "bg-purple-950/60 text-purple-300 border-purple-800/40" : "bg-cyan-950/60 text-cyan-300 border-cyan-800/40"}`}>
                {isTournamentDay ? "[TOURNAMENT] Modern 5-Variant Tournament Era" : "[LEGACY] Pre-Tournament Legacy Era (6 Videos/Day)"}
              </span>
              <span className="text-xs text-gray-400">
                {isTournamentDay 
                  ? "1 high-input video/day produced with surplus compute time & Auto-QA tournament." 
                  : "6 videos generated & uploaded per day across Space, History, and Tech categories."}
              </span>
            </div>
          </div>

          {!isTournamentDay ? (
            <div className="space-y-6">
              <h3 className="text-sm font-bold uppercase tracking-wider text-gray-400">
                Daily Video Output ({selectedDayRuns.length} Generated & Uploaded Clips)
              </h3>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {selectedDayRuns.map((run, i) => (
                  <div key={run.id} className="bg-[#0b0f19] p-5 rounded-xl border border-[#1f2d4d] space-y-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-bold text-gray-400 font-mono">Clip #{i + 1}</span>
                          <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${getCategoryBadgeColor(run.category)}`}>
                            {run.category}
                          </span>
                        </div>
                        <h4 className="text-md font-bold text-white mt-1">{run.winning_script?.title || "Video Clip"}</h4>
                      </div>

                      <div className="flex flex-col items-end gap-1">
                        <span className="text-xs font-bold px-2 py-0.5 rounded bg-yellow-500/20 text-yellow-400">
                          Score: {run.script_variants?.[0]?.score || 5.2} / 10
                        </span>
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
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <TournamentSection run={selectedRun || selectedDayRuns[0]} getCategoryBadgeColor={getCategoryBadgeColor} />
          )}

          {/* FAILURE & ERROR LOG CONTAINERS */}
          {selectedRun?.status === "FAILED" && (
            <div className="bg-red-950/30 border border-red-500/40 p-4 rounded-xl space-y-2">
              <div 
                onClick={() => setShowErrorTrace(!showErrorTrace)}
                className="flex items-center justify-between cursor-pointer text-red-400 text-sm font-bold"
              >
                <div className="flex items-center gap-2">
                  <AlertTriangle className="w-5 h-5" />
                  <span>Pipeline Execution Traceback (Click to Toggle)</span>
                </div>
                {showErrorTrace ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              </div>

              {showErrorTrace && (
                <pre className="text-xs font-mono bg-black/60 p-4 rounded-lg text-red-300 overflow-x-auto border border-red-900/50 mt-2">
                  {selectedRun.error_traceback || "No explicit traceback recorded."}
                </pre>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
