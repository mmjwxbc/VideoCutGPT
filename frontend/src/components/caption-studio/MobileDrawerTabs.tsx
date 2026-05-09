import React, { useEffect, useRef } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { X, MessageSquare, Clapperboard } from 'lucide-react';

import { SessionListItem, WorkflowStateRow } from './shared';
import MobileChatHistoryDrawer from './MobileChatHistoryDrawer';
import MobileEditStatusDrawer from './MobileEditStatusDrawer';
import { CaptionAssistantSession } from '../../types';

export type DrawerType = 'history' | 'status';

interface MobileDrawerTabsProps {
  activeDrawer: DrawerType | null;
  onToggleDrawer: (type: DrawerType) => void;
  onCloseDrawer: () => void;
  sessionHistory: SessionListItem[];
  activeSessionId?: string;
  loadingSessionId?: string | null;
  onOpenSession: (sessionId: string) => void | Promise<void>;
  onReset: () => void;
  session: CaptionAssistantSession | null;
  activeSessionTitle: string;
  workflowRows: WorkflowStateRow[];
}

const overlayVariants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1 },
};

const reducedMotion =
  typeof window !== 'undefined' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches;

const springTransition = reducedMotion
  ? { duration: 0.15 }
  : { type: 'spring' as const, stiffness: 260, damping: 28 };

const MobileDrawerTabs: React.FC<MobileDrawerTabsProps> = ({
  activeDrawer,
  onToggleDrawer,
  onCloseDrawer,
  sessionHistory,
  activeSessionId,
  loadingSessionId,
  onOpenSession,
  onReset,
  session,
  activeSessionTitle,
  workflowRows,
}) => {
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (activeDrawer) {
      closeButtonRef.current?.focus();
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [activeDrawer]);

  useEffect(() => {
    if (!activeDrawer) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCloseDrawer();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [activeDrawer, onCloseDrawer]);

  return (
    <>
      {/* Top pill buttons */}
      <div className="flex items-center gap-2 border-b border-slate-800 bg-[#0f0f0f] px-4 py-3 lg:hidden">
        <button
          type="button"
          onClick={() => onToggleDrawer('history')}
          aria-expanded={activeDrawer === 'history'}
          aria-label="打开聊天记录"
          className={`inline-flex h-8 flex-1 items-center justify-center gap-1.5 rounded-full border text-[12px] font-medium transition ${
            activeDrawer === 'history'
              ? 'border-sky-500/40 bg-sky-500/10 text-sky-200'
              : 'border-slate-800 bg-[#171717] text-slate-400 hover:border-slate-700 hover:text-slate-200'
          }`}
        >
          <MessageSquare className="h-3.5 w-3.5" />
          聊天记录
        </button>
        <button
          type="button"
          onClick={() => onToggleDrawer('status')}
          aria-expanded={activeDrawer === 'status'}
          aria-label="打开剪辑状态"
          className={`inline-flex h-8 flex-1 items-center justify-center gap-1.5 rounded-full border text-[12px] font-medium transition ${
            activeDrawer === 'status'
              ? 'border-sky-500/40 bg-sky-500/10 text-sky-200'
              : 'border-slate-800 bg-[#171717] text-slate-400 hover:border-slate-700 hover:text-slate-200'
          }`}
        >
          <Clapperboard className="h-3.5 w-3.5" />
          剪辑状态
        </button>
      </div>

      {/* Overlay + Drawers */}
      <AnimatePresence>
        {activeDrawer ? (
          <>
            {/* Backdrop overlay */}
            <motion.div
              key="drawer-overlay"
              className="fixed inset-0 z-[80] bg-black/45 backdrop-blur-[2px] lg:hidden"
              variants={overlayVariants}
              initial="hidden"
              animate="visible"
              exit="hidden"
              transition={{ duration: reducedMotion ? 0.1 : 0.22 }}
              onClick={onCloseDrawer}
              aria-hidden="true"
            />

            {/* Left drawer: Chat history */}
            {activeDrawer === 'history' && (
              <motion.aside
                key="drawer-history"
                role="dialog"
                aria-label="聊天记录"
                aria-modal="true"
                className="fixed inset-y-0 left-0 z-[90] flex w-[82vw] max-w-[360px] flex-col border-r border-slate-700/40 bg-[#0f0f10] shadow-[4px_0_32px_rgba(0,0,0,0.45)] lg:hidden"
                initial={{ x: '-100%' }}
                animate={{ x: 0 }}
                exit={{ x: '-100%' }}
                transition={springTransition}
              >
                {/* Drawer header */}
                <div className="flex shrink-0 items-center justify-between border-b border-slate-800 px-4 py-3">
                  <div className="flex items-center gap-2">
                    <MessageSquare className="h-4 w-4 text-sky-400" />
                    <h2 className="text-[14px] font-semibold text-slate-100">聊天记录</h2>
                  </div>
                  <button
                    ref={closeButtonRef}
                    type="button"
                    onClick={onCloseDrawer}
                    aria-label="关闭聊天记录"
                    className="flex h-8 w-8 items-center justify-center rounded-full border border-slate-700 bg-[#1b1b1b] text-slate-400 transition hover:border-slate-600 hover:text-white"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>

                {/* Drawer content */}
                <MobileChatHistoryDrawer
                  sessionHistory={sessionHistory}
                  activeSessionId={activeSessionId}
                  loadingSessionId={loadingSessionId}
                  onOpenSession={onOpenSession}
                  onReset={onReset}
                  onCloseDrawer={onCloseDrawer}
                />
              </motion.aside>
            )}

            {/* Right drawer: Edit status */}
            {activeDrawer === 'status' && (
              <motion.aside
                key="drawer-status"
                role="dialog"
                aria-label="剪辑状态"
                aria-modal="true"
                className="fixed inset-y-0 right-0 z-[90] flex w-[82vw] max-w-[360px] flex-col border-l border-slate-700/40 bg-[#0f0f10] shadow-[-4px_0_32px_rgba(0,0,0,0.45)] lg:hidden"
                initial={{ x: '100%' }}
                animate={{ x: 0 }}
                exit={{ x: '100%' }}
                transition={springTransition}
              >
                {/* Drawer header */}
                <div className="flex shrink-0 items-center justify-between border-b border-slate-800 px-4 py-3">
                  <div className="flex items-center gap-2">
                    <Clapperboard className="h-4 w-4 text-sky-400" />
                    <h2 className="text-[14px] font-semibold text-slate-100">剪辑状态</h2>
                  </div>
                  <button
                    ref={closeButtonRef}
                    type="button"
                    onClick={onCloseDrawer}
                    aria-label="关闭剪辑状态"
                    className="flex h-8 w-8 items-center justify-center rounded-full border border-slate-700 bg-[#1b1b1b] text-slate-400 transition hover:border-slate-600 hover:text-white"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>

                {/* Drawer content */}
                <MobileEditStatusDrawer
                  session={session}
                  activeSessionTitle={activeSessionTitle}
                  workflowRows={workflowRows}
                />
              </motion.aside>
            )}
          </>
        ) : null}
      </AnimatePresence>
    </>
  );
};

export default MobileDrawerTabs;
