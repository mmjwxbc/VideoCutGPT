import React, { useState, useCallback } from 'react';
import { RefreshCcw, Search, Clapperboard } from 'lucide-react';

import { SessionListItem, formatTimestamp } from './shared';

interface MobileChatHistoryDrawerProps {
  sessionHistory: SessionListItem[];
  activeSessionId?: string;
  onOpenSession: (sessionId: string) => void | Promise<void>;
  onReset: () => void;
  onCloseDrawer: () => void;
}

const STATUS_MAP: Record<string, { label: string; className: string }> = {
  completed: { label: '已完成', className: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30' },
  processing: { label: '生成中', className: 'bg-sky-500/15 text-sky-300 border-sky-500/30' },
  idle: { label: '待处理', className: 'bg-slate-500/15 text-slate-300 border-slate-500/30' },
  error: { label: '异常', className: 'bg-rose-500/15 text-rose-300 border-rose-500/30' },
};

const MobileChatHistoryDrawer: React.FC<MobileChatHistoryDrawerProps> = ({
  sessionHistory,
  activeSessionId,
  onOpenSession,
  onReset,
  onCloseDrawer,
}) => {
  const [searchQuery, setSearchQuery] = useState('');

  const handleSessionClick = useCallback(
    (sessionId: string) => {
      void onOpenSession(sessionId);
      onCloseDrawer();
    },
    [onOpenSession, onCloseDrawer],
  );

  const filteredHistory = searchQuery.trim()
    ? sessionHistory.filter(
        (item) =>
          item.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
          item.subtitle.toLowerCase().includes(searchQuery.toLowerCase()),
      )
    : sessionHistory;

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      {/* Search */}
      <div className="shrink-0 px-4 pt-3">
        <div className="flex items-center gap-2 rounded-xl border border-slate-700/60 bg-[#171717] px-3 py-2">
          <Search className="h-3.5 w-3.5 text-slate-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="搜索历史任务"
            className="flex-1 bg-transparent text-[12px] text-slate-200 placeholder:text-slate-500 focus:outline-none"
          />
        </div>
      </div>

      {/* New task button */}
      <div className="shrink-0 px-4 pt-3">
        <button
          type="button"
          onClick={() => {
            onReset();
            onCloseDrawer();
          }}
          className="flex w-full items-center justify-center gap-2 rounded-xl border border-slate-700 bg-[#171717] px-4 py-2.5 text-[12px] font-medium text-slate-200 transition hover:border-slate-600 hover:bg-[#1b1b1b] hover:text-white"
        >
          <RefreshCcw className="h-4 w-4" />
          新建任务
        </button>
      </div>

      {/* Session list */}
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {filteredHistory.length ? (
          <div className="space-y-2">
            {filteredHistory.map((item) => {
              const isActive = activeSessionId === item.session_id;
              const statusInfo = STATUS_MAP['completed'];
              return (
                <button
                  key={item.session_id}
                  type="button"
                  onClick={() => handleSessionClick(item.session_id)}
                  className={`w-full rounded-2xl border px-3 py-3 text-left transition ${
                    isActive
                      ? 'border-sky-500/40 bg-sky-500/10 shadow-sm'
                      : 'border-slate-800 bg-[#171717] hover:border-slate-700 hover:bg-[#1b1b1b]'
                  }`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <p className="truncate text-[13px] font-medium text-slate-100">
                      {item.title}
                    </p>
                    <span className="shrink-0 text-[10px] text-slate-500">
                      {formatTimestamp(item.updated_at)}
                    </span>
                  </div>
                  <p className="mt-1.5 line-clamp-2 text-[11px] leading-5 text-slate-400">
                    {item.subtitle}
                  </p>
                  <div className="mt-2 flex items-center gap-2">
                    <span
                      className={`inline-flex rounded-full border px-2 py-0.5 text-[9px] font-medium ${statusInfo.className}`}
                    >
                      {statusInfo.label}
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl border border-slate-800 bg-[#151515]">
              <Clapperboard className="h-6 w-6 text-slate-600" />
            </div>
            <p className="mt-4 text-[13px] font-medium text-slate-300">
              暂无聊天记录
            </p>
            <p className="mt-1.5 max-w-[220px] text-[11px] leading-5 text-slate-500">
              创建第一轮字幕任务后，历史会话会显示在这里
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

export default MobileChatHistoryDrawer;
