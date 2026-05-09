import React from 'react';
import { ChevronLeft, ChevronRight, Clapperboard, RefreshCcw } from 'lucide-react';
import { Link } from 'react-router-dom';

import { Button } from '../ui/button';
import { Panel, SessionListItem, formatTimestamp } from './shared';

interface HistorySidebarProps {
  collapsed: boolean;
  sessionHistory: SessionListItem[];
  activeSessionId?: string;
  loadingSessionId?: string | null;
  onExpand: () => void;
  onCollapse: () => void;
  onReset: () => void;
  onOpenSession: (sessionId: string) => void | Promise<void>;
}

const HistorySidebar: React.FC<HistorySidebarProps> = ({
  collapsed,
  sessionHistory,
  activeSessionId,
  loadingSessionId,
  onExpand,
  onCollapse,
  onReset,
  onOpenSession,
}) => (
  <aside className="hidden min-h-0 overflow-hidden bg-[#0f0f0f] lg:block">
    <Panel
      title=""
      className="h-full overflow-hidden border-0 bg-[#0f0f0f]"
      bodyClassName="flex min-h-0 flex-1 flex-col"
      hideHeader
    >
      {collapsed ? (
        <div className="flex shrink-0 flex-col items-center">
          <button
            type="button"
            onClick={onExpand}
            className="flex h-9 w-9 items-center justify-center rounded-full border border-slate-800 bg-[#171717] text-slate-300 transition hover:border-slate-700 hover:bg-[#1b1b1b] hover:text-white"
            aria-label="展开历史侧栏"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      ) : (
        <>
          <div className="mb-3 flex shrink-0 items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-[10px] font-medium uppercase tracking-[0.24em] text-slate-500">
                <Clapperboard className="h-3 w-3" />
                Caption Studio
              </div>
              <h1 className="mt-1 text-[17px] font-semibold text-slate-100">
                桌面工作台
              </h1>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <button
                type="button"
                onClick={onCollapse}
                className="flex h-9 w-9 items-center justify-center rounded-full border border-slate-800 bg-[#171717] text-slate-300 transition hover:border-slate-700 hover:bg-[#1b1b1b] hover:text-white"
                aria-label="收起历史侧栏"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              <Link
                to="/"
                className="shrink-0 rounded-full border border-slate-800 bg-[#171717] px-2.5 py-1.5 text-[11px] font-medium text-slate-300 transition hover:border-slate-700 hover:text-white"
              >
                返回
              </Link>
            </div>
          </div>

          <Button
            type="button"
            variant="outline"
            className="mb-3 w-full border-slate-800 bg-[#171717] text-slate-200 hover:border-slate-700 hover:bg-[#1b1b1b] hover:text-white"
            onClick={onReset}
          >
            <RefreshCcw className="mr-2 h-4 w-4" />
            新建任务
          </Button>

          <div className="min-h-0 flex-1 overflow-y-auto pr-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            <div className="space-y-2">
              {sessionHistory.length ? (
                sessionHistory.map((item) => {
                  const isActive = activeSessionId === item.session_id;
                  const isLoading = loadingSessionId === item.session_id;
                  return (
                    <button
                      key={item.session_id}
                      type="button"
                      onClick={() => void onOpenSession(item.session_id)}
                      disabled={isLoading}
                      className={`w-full rounded-2xl border px-3 py-3 text-left transition ${
                        isActive
                          ? 'border-sky-500/40 bg-sky-500/10 shadow-sm'
                          : 'border-slate-800 bg-[#171717] hover:border-slate-700 hover:bg-[#1b1b1b]'
                      } ${isLoading ? 'cursor-wait opacity-80' : ''}`}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <p className="truncate text-sm font-medium text-slate-100">
                          {item.title}
                        </p>
                        <div className="flex shrink-0 items-center gap-2">
                          {isLoading ? (
                            <span className="text-[10px] text-sky-300">加载中...</span>
                          ) : null}
                          <span className="text-[11px] text-slate-500">
                            {formatTimestamp(item.updated_at)}
                          </span>
                        </div>
                      </div>
                      <p className="mt-2 line-clamp-2 text-xs leading-5 text-slate-400">
                        {item.subtitle}
                      </p>
                    </button>
                  );
                })
              ) : (
                <div className="rounded-[18px] border border-dashed border-slate-800 bg-[#151515] px-3.5 py-4 text-[13px] leading-5 text-slate-400">
                  还没有历史会话。创建首轮任务后，后续所有版本都会沉淀在这里。
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </Panel>
  </aside>
);

export default HistorySidebar;
