import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import {
  ArrowUp,
  ChevronDown,
  Mic,
  Plus,
  Paperclip,
  Sparkles,
  X,
} from 'lucide-react';
import { cn } from '../lib/utils';

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
  uploadPreviewUrl?: string | null;
  uploadPreviewName?: string | null;
  onClearUploadPreview?: () => void;
  sellingPointsValue: string;
  onSellingPointsChange: (value: string) => void;
  sellingPointsOpen: boolean;
  onSellingPointsToggle: () => void;
  toolsDisabled?: boolean;
  modeLabel?: string;
}

const MAX_TEXTAREA_HEIGHT = 160;

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
  uploadPreviewUrl,
  uploadPreviewName,
  onClearUploadPreview,
  sellingPointsValue,
  onSellingPointsChange,
  sellingPointsOpen,
  onSellingPointsToggle,
  toolsDisabled = false,
  modeLabel = 'Instant',
}) => {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const platformMenuRef = useRef<HTMLDivElement | null>(null);
  const [platformMenuOpen, setPlatformMenuOpen] = useState(false);
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

  return (
    <div className={cn('w-full', className)}>
      <div className="mx-auto min-h-[96px] w-full max-w-[960px] rounded-[28px] bg-[#212121] px-4 py-3.5 shadow-[0_12px_40px_rgba(0,0,0,0.18)]">
        {uploadPreviewUrl ? (
          <div className="mb-3 flex items-start">
            <div className="relative h-20 w-20 overflow-hidden rounded-xl">
              <video
                src={uploadPreviewUrl}
                className="h-full w-full object-cover"
                muted
                playsInline
                preload="metadata"
              />
              {onClearUploadPreview ? (
                <button
                  type="button"
                  onClick={onClearUploadPreview}
                  disabled={toolsDisabled}
                  aria-label="移除附件"
                  className="absolute right-1.5 top-1.5 flex h-6 w-6 items-center justify-center rounded-full bg-black/55 text-white transition hover:bg-black/75 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              ) : null}
            </div>
            <div className="min-w-0 pl-3 pt-1">
              <p className="truncate text-[11px] font-medium text-slate-200">
                {uploadPreviewName || '已选择视频文件'}
              </p>
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
              className="inline-flex h-9 items-center gap-2 rounded-full border border-white/10 bg-[#2b2b2b] px-3 text-[12px] font-medium text-slate-200 transition hover:bg-[#343434] disabled:cursor-not-allowed disabled:opacity-50"
            >
              <span className={cn('h-2.5 w-2.5 rounded-full', activePlatform.iconClassName)} />
              <span>{activePlatform.label}</span>
              <ChevronDown className="h-4 w-4 text-slate-400" />
            </button>

            {platformMenuOpen ? (
              <div className="absolute left-0 top-12 z-20 min-w-[180px] rounded-2xl border border-white/10 bg-[#242424] p-1.5 shadow-[0_18px_40px_rgba(0,0,0,0.32)]">
                {platformOptions.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => {
                      onPlatformChange(option.value);
                      setPlatformMenuOpen(false);
                    }}
                    className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-left text-[12px] text-slate-200 transition hover:bg-[#303030]"
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
            className="inline-flex h-9 items-center rounded-full border border-white/10 bg-[#2b2b2b] px-3 text-[12px] font-medium text-slate-200 transition hover:bg-[#343434] disabled:cursor-not-allowed disabled:opacity-50"
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
                : 'border-white/10 bg-[#2b2b2b] text-slate-200 hover:bg-[#343434]',
            )}
          >
            <Sparkles className="h-4 w-4" />
            <span>Selling Points</span>
          </button>
        </div>

        {sellingPointsOpen ? (
          <div className="mb-3 rounded-2xl border border-white/10 bg-[#2b2b2b] px-3 py-2.5">
            <input
              value={sellingPointsValue}
              onChange={(event) => onSellingPointsChange(event.target.value)}
              disabled={toolsDisabled}
              placeholder="输入卖点、参数、品牌语气、禁用词"
              className="w-full bg-transparent text-[12px] text-slate-100 placeholder:text-slate-400 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
            />
          </div>
        ) : null}

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onUploadClick}
            disabled={toolsDisabled}
            aria-label="添加附件"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-white/10 bg-[#2b2b2b] text-slate-200 transition hover:bg-[#343434] disabled:cursor-not-allowed disabled:opacity-50"
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
            className="min-h-[24px] flex-1 resize-none overflow-y-hidden bg-transparent px-0 py-2 text-[14px] leading-6 text-white placeholder:text-slate-400 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
            style={{ maxHeight: MAX_TEXTAREA_HEIGHT }}
          />

          <button
            type="button"
            disabled
            className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-full border border-white/10 bg-[#2b2b2b] px-2.5 text-[12px] font-medium text-slate-200 transition hover:bg-[#343434]"
          >
            <span className="hidden max-w-[70px] truncate sm:inline">{modeLabel}</span>
            <ChevronDown className="h-4 w-4 text-slate-400" />
          </button>

          <button
            type="button"
            disabled
            aria-label="语音输入"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-white/10 bg-[#2b2b2b] text-slate-300 transition hover:bg-[#343434] disabled:cursor-default"
          >
            <Mic className="h-4 w-4" />
          </button>

          <button
            type="button"
            onClick={handleSubmit}
            disabled={disabled || !hasText}
            aria-label="发送"
            className={cn(
              'flex h-11 w-11 shrink-0 items-center justify-center rounded-full transition',
              hasText && !disabled
                ? 'bg-white text-black hover:bg-slate-100'
                : 'bg-[#3a3a3a] text-[#777777]',
            )}
          >
            <ArrowUp className="h-4.5 w-4.5" />
          </button>
        </div>
      </div>
    </div>
  );
};

export default ChatComposer;
