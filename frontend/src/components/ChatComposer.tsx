import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import {
  ArrowUp,
  Check,
  ChevronDown,
  Loader2,
  Mic,
  Plus,
  Paperclip,
  Sparkles,
  X,
} from 'lucide-react';
import { cn } from '../lib/utils';
import { AnalysisMode } from '../types';

export interface ChatComposerOption {
  value: string;
  label: string;
  iconClassName: string;
}

interface ChatComposerProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  platform: string;
  platformOptions: ChatComposerOption[];
  onPlatformChange: (value: string) => void;
  onUploadClick?: () => void;
  uploadPreviews?: Array<{
    url: string;
    name: string;
    progress: number;
    status: 'idle' | 'uploading' | 'processing' | 'done' | 'failed';
  }>;
  selectedUploadIndex?: number;
  onSelectUpload?: (index: number) => void;
  onMoveUpload?: (fromIndex: number, toIndex: number) => void;
  onClearUploadPreview?: () => void;
  analysisMode: AnalysisMode;
  onAnalysisModeChange: (value: AnalysisMode) => void;
  sellingPointsValue: string;
  onSellingPointsChange: (value: string) => void;
  sellingPointsOpen: boolean;
  onSellingPointsToggle: () => void;
  toolsDisabled?: boolean;
  modeLabel?: string;
  isSubmitting?: boolean;
}

const MAX_TEXTAREA_HEIGHT = 160;
const PROGRESS_RADIUS = 15;
const PROGRESS_CIRCUMFERENCE = 2 * Math.PI * PROGRESS_RADIUS;

const UploadProgressRing: React.FC<{
  progress: number;
  status: 'idle' | 'uploading' | 'processing' | 'done' | 'failed';
}> = ({ progress, status }) => {
  if (status === 'idle') {
    return null;
  }

  const normalizedProgress = Math.max(0, Math.min(progress, 1));
  const strokeDashoffset =
    PROGRESS_CIRCUMFERENCE - normalizedProgress * PROGRESS_CIRCUMFERENCE;
  const ringClassName =
    status === 'failed'
      ? 'text-rose-400'
      : status === 'done'
        ? 'text-emerald-400'
        : 'text-sky-300';
  const label =
    status === 'done' ? (
      <Check className="h-3.5 w-3.5 text-emerald-300" />
    ) : status === 'failed' ? (
      <span className="text-[9px] font-semibold text-rose-200">!</span>
    ) : (
      <span className="text-[9px] font-semibold text-white">
        {Math.round(normalizedProgress * 100)}
      </span>
    );

  return (
    <div className="theme-transition ws-card-contrast border-ws-strong absolute bottom-1.5 right-1.5 flex h-9 w-9 items-center justify-center rounded-full border backdrop-blur-sm">
      <svg className="absolute inset-0 -rotate-90" viewBox="0 0 36 36" aria-hidden="true">
        <circle
          cx="18"
          cy="18"
          r={PROGRESS_RADIUS}
          fill="none"
          stroke="rgba(148,163,184,0.2)"
          strokeWidth="3"
        />
        <circle
          cx="18"
          cy="18"
          r={PROGRESS_RADIUS}
          fill="none"
          stroke="currentColor"
          strokeWidth="3"
          strokeLinecap="round"
          strokeDasharray={PROGRESS_CIRCUMFERENCE}
          strokeDashoffset={strokeDashoffset}
          className={ringClassName}
        />
      </svg>
      <span className="relative flex items-center justify-center">{label}</span>
    </div>
  );
};

const UploadStatusBadge: React.FC<{
  status: 'idle' | 'uploading' | 'processing' | 'done' | 'failed';
}> = ({ status }) => {
  if (status === 'idle') {
    return null;
  }

  const toneClassName =
    status === 'failed'
      ? 'bg-rose-500/85 text-white'
      : status === 'done'
        ? 'bg-emerald-500/85 text-white'
        : 'bg-sky-500/85 text-white';
  const label =
    status === 'uploading'
      ? '上传中'
      : status === 'processing'
        ? '处理中'
        : status === 'done'
          ? '完成'
          : '失败';

  return (
    <span
      className={cn(
        'absolute left-1.5 bottom-1.5 rounded-full px-1.5 py-0.5 text-[9px] font-medium',
        toneClassName,
      )}
    >
      {label}
    </span>
  );
};

const ChatComposer: React.FC<ChatComposerProps> = ({
  value,
  onChange,
  onSubmit,
  placeholder = '有问题，尽管问',
  disabled = false,
  className,
  platform,
  platformOptions,
  onPlatformChange,
  onUploadClick,
  uploadPreviews = [],
  selectedUploadIndex = 0,
  onSelectUpload,
  onMoveUpload,
  onClearUploadPreview,
  analysisMode,
  onAnalysisModeChange,
  sellingPointsValue,
  onSellingPointsChange,
  sellingPointsOpen,
  onSellingPointsToggle,
  toolsDisabled = false,
  modeLabel = 'Instant',
  isSubmitting = false,
}) => {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const platformMenuRef = useRef<HTMLDivElement | null>(null);
  const [platformMenuOpen, setPlatformMenuOpen] = useState(false);
  const [draggingUploadIndex, setDraggingUploadIndex] = useState<number | null>(null);
  const [dragOverUploadIndex, setDragOverUploadIndex] = useState<number | null>(null);
  const hasText = value.trim().length > 0;
  const activePlatform =
    platformOptions.find((option) => option.value === platform) ?? platformOptions[0];
  const resizeTextarea = useCallback(() => {
    const textarea = textareaRef.current;
    if (!textarea) {
      return;
    }
    textarea.style.height = '0px';
    const nextHeight = Math.min(textarea.scrollHeight, MAX_TEXTAREA_HEIGHT);
    textarea.style.height = `${nextHeight}px`;
    textarea.style.overflowY =
      textarea.scrollHeight > MAX_TEXTAREA_HEIGHT ? 'auto' : 'hidden';
  }, []);

  useLayoutEffect(() => {
    resizeTextarea();
  }, [value, resizeTextarea]);

  useEffect(() => {
    if (!platformMenuOpen) {
      return;
    }

    const handlePointerDown = (event: MouseEvent) => {
      if (!platformMenuRef.current?.contains(event.target as Node)) {
        setPlatformMenuOpen(false);
      }
    };

    window.addEventListener('mousedown', handlePointerDown);
    return () => {
      window.removeEventListener('mousedown', handlePointerDown);
    };
  }, [platformMenuOpen]);

  const handleSubmit = useCallback(() => {
    if (disabled || !hasText) {
      return;
    }
    onSubmit(value.trim());
  }, [disabled, hasText, onSubmit, value]);

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (event.key !== 'Enter' || event.shiftKey) {
        return;
      }
      event.preventDefault();
      handleSubmit();
    },
    [handleSubmit],
  );

  const handleUploadDrop = useCallback(
    (targetIndex: number) => {
      if (
        draggingUploadIndex === null ||
        draggingUploadIndex === targetIndex ||
        !onMoveUpload
      ) {
        setDragOverUploadIndex(null);
        setDraggingUploadIndex(null);
        return;
      }
      onMoveUpload(draggingUploadIndex, targetIndex);
      onSelectUpload?.(targetIndex);
      setDragOverUploadIndex(null);
      setDraggingUploadIndex(null);
    },
    [draggingUploadIndex, onMoveUpload, onSelectUpload],
  );

  return (
    <div className={cn('w-full', className)}>
      <div className="theme-transition ws-card mx-auto min-h-[96px] w-full max-w-[960px] rounded-[28px] border px-4 py-3.5 shadow-[0_12px_40px_rgba(0,0,0,0.18)]">
        {uploadPreviews.length ? (
          <div className="mb-3 flex flex-col gap-3">
            <div className="flex items-center justify-between gap-3">
              <p className="text-ws-muted text-[11px]">
                {uploadPreviews.length === 1
                  ? '1 个视频待上传'
                  : `${uploadPreviews.length} 个视频待上传，可拖拽调整顺序`}
              </p>
              {onClearUploadPreview ? (
                <button
                  type="button"
                  onClick={onClearUploadPreview}
                  disabled={toolsDisabled}
                  aria-label="移除附件"
                  className="theme-transition ws-card-muted text-ws-primary inline-flex h-7 w-7 items-center justify-center rounded-full border disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              ) : null}
            </div>

            <div className="flex gap-2 overflow-x-auto pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
              {uploadPreviews.map((preview, index) => {
                const isActive = index === selectedUploadIndex;
                const isDragging = index === draggingUploadIndex;
                const isDragOver = index === dragOverUploadIndex;
                return (
                  <button
                    key={`${preview.name}-${index}`}
                    type="button"
                    onClick={() => onSelectUpload?.(index)}
                    draggable={!toolsDisabled}
                    onDragStart={(event) => {
                      setDraggingUploadIndex(index);
                      setDragOverUploadIndex(index);
                      event.dataTransfer.effectAllowed = 'move';
                      event.dataTransfer.setData('text/plain', String(index));
                    }}
                    onDragEnter={() => {
                      if (!toolsDisabled && draggingUploadIndex !== null) {
                        setDragOverUploadIndex(index);
                      }
                    }}
                    onDragOver={(event) => {
                      if (toolsDisabled || draggingUploadIndex === null) {
                        return;
                      }
                      event.preventDefault();
                      event.dataTransfer.dropEffect = 'move';
                      if (dragOverUploadIndex !== index) {
                        setDragOverUploadIndex(index);
                      }
                    }}
                    onDrop={(event) => {
                      event.preventDefault();
                      handleUploadDrop(index);
                    }}
                    onDragEnd={() => {
                      setDraggingUploadIndex(null);
                      setDragOverUploadIndex(null);
                    }}
                    disabled={toolsDisabled}
                    className={cn(
                      'theme-transition ws-card-muted group relative flex w-[84px] shrink-0 flex-col overflow-hidden rounded-2xl border text-left transition',
                      isActive
                        ? 'border-sky-500/50 shadow-[0_0_0_1px_rgba(14,165,233,0.25)]'
                        : 'hover:border-ws-strong',
                      isDragOver && 'border-emerald-400/60 shadow-[0_0_0_1px_rgba(52,211,153,0.35)]',
                      isDragging && 'scale-[0.98] opacity-50',
                      toolsDisabled && 'cursor-not-allowed opacity-60',
                      !toolsDisabled && 'cursor-grab active:cursor-grabbing',
                    )}
                  >
                    <div className="relative h-14 w-full overflow-hidden">
                      <video
                        src={preview.url}
                        className="h-full w-full object-cover transition group-hover:scale-[1.03]"
                        muted
                        playsInline
                        preload="metadata"
                      />
                      <span className="absolute left-1.5 top-1.5 rounded-full bg-black/60 px-1.5 py-0.5 text-[9px] text-white">
                        {index + 1}
                      </span>
                      {(preview.status === 'uploading' ||
                        preview.status === 'processing' ||
                        preview.status === 'failed') ? (
                        <div className="absolute inset-0 bg-black/30" />
                      ) : null}
                      <UploadStatusBadge status={preview.status} />
                      <UploadProgressRing
                        progress={preview.progress}
                        status={preview.status}
                      />
                    </div>
                    <div className="px-2 py-1.5">
                      <p className="text-ws-secondary line-clamp-2 text-[10px] leading-4">
                        {preview.name}
                      </p>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        ) : null}

        <div className="mb-3 flex flex-wrap items-center gap-2">
          <div ref={platformMenuRef} className="relative">
            <button
              type="button"
              onClick={() => {
                if (toolsDisabled) {
                  return;
                }
                setPlatformMenuOpen((current) => !current);
              }}
              disabled={toolsDisabled}
              className="theme-transition ws-card-muted text-ws-secondary hover:text-ws-primary inline-flex h-9 items-center gap-2 rounded-full border px-3 text-[12px] font-medium disabled:cursor-not-allowed disabled:opacity-50"
            >
              <span className={cn('h-2.5 w-2.5 rounded-full', activePlatform.iconClassName)} />
              <span>{activePlatform.label}</span>
              <ChevronDown className="text-ws-soft h-4 w-4" />
            </button>

            {platformMenuOpen ? (
              <div className="theme-transition ws-card absolute bottom-full left-0 z-20 mb-2 min-w-[180px] rounded-2xl border p-1.5 shadow-[0_18px_40px_rgba(0,0,0,0.32)]">
                {platformOptions.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => {
                      onPlatformChange(option.value);
                      setPlatformMenuOpen(false);
                    }}
                    className="theme-transition text-ws-secondary hover:bg-[var(--workspace-card-muted)] hover:text-ws-primary flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-left text-[12px]"
                  >
                    <span className={cn('h-2.5 w-2.5 rounded-full', option.iconClassName)} />
                    <span>{option.label}</span>
                  </button>
                ))}
              </div>
            ) : null}
          </div>

          <button
            type="button"
            onClick={onUploadClick}
            disabled={toolsDisabled}
            className="theme-transition ws-card-muted text-ws-secondary hover:text-ws-primary inline-flex h-9 items-center rounded-full border px-3 text-[12px] font-medium disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Paperclip className="mr-2 h-4 w-4" />
            Upload
          </button>

          <button
            type="button"
            onClick={onSellingPointsToggle}
            disabled={toolsDisabled}
            className={cn(
              'inline-flex h-9 items-center gap-2 rounded-full border px-3 text-[12px] font-medium transition disabled:cursor-not-allowed disabled:opacity-50',
              sellingPointsOpen || sellingPointsValue.trim()
                ? 'border-emerald-400/30 bg-emerald-500/10 text-emerald-200'
                : 'ws-card-muted text-ws-secondary hover:text-ws-primary',
            )}
          >
            <Sparkles className="h-4 w-4" />
            <span>Selling Points</span>
          </button>

          <div className="theme-transition ws-card-muted inline-flex rounded-full border p-1">
            {([
              ['keyframe', '关键帧'],
              ['every_second', '逐帧分析'],
            ] as const).map(([value, label]) => {
              const selected = analysisMode === value;
              return (
                <button
                  key={value}
                  type="button"
                  onClick={() => onAnalysisModeChange(value)}
                  disabled={toolsDisabled}
                  className={cn(
                    'inline-flex h-7 items-center justify-center rounded-full px-3 text-[11px] font-medium transition',
                    selected
                      ? 'bg-sky-500/15 text-sky-200'
                      : 'text-ws-soft hover:text-ws-secondary',
                    toolsDisabled && 'cursor-not-allowed opacity-50',
                  )}
                >
                  {label}
                </button>
              );
            })}
          </div>
        </div>

        {sellingPointsOpen ? (
          <div className="theme-transition ws-input mb-3 rounded-2xl border px-3 py-2.5">
            <input
              value={sellingPointsValue}
              onChange={(event) => onSellingPointsChange(event.target.value)}
              disabled={toolsDisabled}
              placeholder="输入卖点、参数、品牌语气、禁用词"
              className="text-ws-primary placeholder:text-ws-soft w-full bg-transparent text-[12px] focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
            />
          </div>
        ) : null}

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onUploadClick}
            disabled={toolsDisabled}
            aria-label="添加附件"
            className="theme-transition ws-card-muted text-ws-secondary hover:text-ws-primary flex h-8 w-8 shrink-0 items-center justify-center rounded-full border disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Plus className="h-4 w-4" />
          </button>

          <textarea
            ref={textareaRef}
            value={value}
            onChange={(event) => onChange(event.target.value)}
            onKeyDown={handleKeyDown}
            disabled={disabled}
            rows={1}
            placeholder={placeholder}
            className="text-ws-primary placeholder:text-ws-soft min-h-[24px] flex-1 resize-none overflow-y-hidden bg-transparent px-0 py-2 text-[14px] leading-6 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
            style={{ maxHeight: MAX_TEXTAREA_HEIGHT }}
          />

          <button
            type="button"
            disabled
            className="theme-transition ws-card-muted text-ws-secondary inline-flex h-9 shrink-0 items-center gap-1.5 rounded-full border px-2.5 text-[12px] font-medium"
          >
            <span className="hidden max-w-[70px] truncate sm:inline">{modeLabel}</span>
            <ChevronDown className="text-ws-soft h-4 w-4" />
          </button>

          <button
            type="button"
            disabled
            aria-label="语音输入"
            className="theme-transition ws-card-muted text-ws-secondary flex h-9 w-9 shrink-0 items-center justify-center rounded-full border disabled:cursor-default"
          >
            <Mic className="h-4 w-4" />
          </button>

          <button
            type="button"
            onClick={handleSubmit}
            disabled={disabled || (!hasText && !isSubmitting)}
            aria-label="发送"
            className={cn(
              'flex h-11 w-11 shrink-0 items-center justify-center rounded-full transition',
              isSubmitting || (hasText && !disabled)
                ? 'bg-[var(--workspace-text-primary)] text-[var(--workspace-shell)] hover:opacity-92'
                : 'bg-[var(--workspace-card-contrast)] text-[var(--workspace-text-soft)]',
            )}
          >
            {isSubmitting ? (
              <Loader2 className="h-4.5 w-4.5 animate-spin" />
            ) : (
              <ArrowUp className="h-4.5 w-4.5" />
            )}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ChatComposer;
