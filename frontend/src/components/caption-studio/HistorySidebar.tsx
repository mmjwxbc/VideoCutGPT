import React from 'react';
import { ChevronLeft, ChevronRight, Clapperboard, RefreshCcw } from 'lucide-react';
import { Link } from 'react-router-dom';

import ThemeToggle from '../ThemeToggle';
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
  <aside className="theme-transition ws-panel hidden min-h-0 overflow-hidden lg:block">
    <Panel
      title=""
      className="h-full overflow-hidden border-0 bg-transparent shadow-none"
      bodyClassName="flex min-h-0 flex-1 flex-col"
      hideHeader
    >
      {collapsed ? (
        <div className="flex shrink-0 flex-col items-center">
          <div className="mb-2">
            <ThemeToggle className="h-9 w-9 justify-center px-0" />
          </div>
          <button
            type="button"
            onClick={onExpand}
            className="theme-transition ws-card text-ws-secondary hover:text-ws-primary flex h-9 w-9 items-center justify-center rounded-full border"
            aria-label="展开历史侧栏"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      ) : (
        <>
          <div className="mb-3 flex shrink-0 items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="text-ws-soft flex items-center gap-2 text-[10px] font-medium uppercase tracking-[0.24em]">
                <Clapperboard className="h-3 w-3" />
                Caption Studio
              </div>
              <h1 className="text-ws-primary mt-1 text-[17px] font-semibold">
                桌面工作台
              </h1>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <ThemeToggle />
              <button
                type="button"
                onClick={onCollapse}
                className="theme-transition ws-card text-ws-secondary hover:text-ws-primary flex h-9 w-9 items-center justify-center rounded-full border"
                aria-label="收起历史侧栏"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              <Link
                to="/"
                className="theme-transition ws-card text-ws-secondary hover:text-ws-primary shrink-0 rounded-full border px-2.5 py-1.5 text-[11px] font-medium"
              >
                返回
              </Link>
            </div>
          </div>

          <Button
            type="button"
            variant="outline"
            className="theme-transition mb-3 w-full border-ws bg-[var(--workspace-card)] text-[var(--workspace-text-secondary)] hover:border-ws-strong hover:bg-[var(--workspace-card-muted)] hover:text-[var(--workspace-text-primary)]"
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
                          : 'theme-transition border-ws ws-card hover:border-ws-strong'
                      } ${isLoading ? 'cursor-wait opacity-80' : ''}`}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <p className="text-ws-primary truncate text-sm font-medium">
                          {item.title}
                        </p>
                        <div className="flex shrink-0 items-center gap-2">
                          {isLoading ? (
                            <span className="text-[10px] text-sky-300">加载中...</span>
                          ) : null}
                          <span className="text-ws-soft text-[11px]">
                            {formatTimestamp(item.updated_at)}
                          </span>
                        </div>
                      </div>
                      <p className="text-ws-muted mt-2 line-clamp-2 text-xs leading-5">
                        {item.subtitle}
                      </p>
                    </button>
                  );
                })
              ) : (
                <div className="theme-transition ws-empty text-ws-muted rounded-[18px] border border-dashed px-3.5 py-4 text-[13px] leading-5">
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
