import React, { useCallback, useEffect, useState } from 'react';
import {
  ArrowRight,
  Bell,
  Bot,
  ChevronDown,
  ChevronLeft,
  Clapperboard,
  Download,
  FileText,
  BookOpen,
  Globe,
  Layers,
  MessageSquare,
  Palette,
  RefreshCcw,
  Sparkles,
  Upload,
  Wrench,
  Wand2,
  Languages,
  Type,
} from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { motion, useReducedMotion } from 'framer-motion';
import ThemeToggle from '../components/ThemeToggle';

/* ── Navigation ── */
const NAV_LINKS = [
  { label: '工作台', href: '/caption', active: true },
  { label: '剪辑任务', href: '/caption' },
  { label: '模板中心', href: '#' },
  { label: '术语库', href: '#' },
  { label: '团队管理', href: '#' },
  { label: '使用指南', href: '#' },
];

const Navbar: React.FC = () => (
  <nav className="theme-transition sticky top-0 z-50 border-b border-app bg-app-surface backdrop-blur-xl">
    <div className="mx-auto flex h-16 max-w-[1440px] items-center justify-between px-8">
      <div className="flex items-center gap-10">
        <Link to="/" className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-blue-600 to-blue-500 shadow-md shadow-blue-500/20">
            <Globe className="h-4.5 w-4.5 text-white" />
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-app-primary text-[15px] font-bold tracking-tight">
              电商出海助手
            </span>
            <span className="text-app-soft hidden text-[10px] font-semibold uppercase tracking-[0.2em] sm:inline">
              OVERSEA AGENT
            </span>
          </div>
        </Link>
        <div className="hidden items-center gap-1 lg:flex">
          {NAV_LINKS.map((link) => (
            <Link
              key={link.label}
              to={link.href}
              className={`rounded-lg px-3 py-1.5 text-[13px] font-medium transition ${
                link.active
                  ? 'bg-blue-50 text-blue-700'
                  : 'text-app-muted hover:bg-app-surface-subtle hover:text-app-primary'
              }`}
            >
              {link.label}
            </Link>
          ))}
        </div>
      </div>
      <div className="flex items-center gap-4">
        <ThemeToggle className="hidden sm:inline-flex" />
        <button
          type="button"
          className="theme-transition text-app-muted hover:text-app-primary relative flex h-9 w-9 items-center justify-center rounded-xl border border-app bg-app-surface-solid"
        >
          <Bell className="h-4 w-4" />
          <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-red-500" />
        </button>
        <div className="theme-transition flex items-center gap-2.5 rounded-xl border border-app bg-app-surface-solid px-3 py-1.5 hover:border-app-strong">
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-blue-600 text-[11px] font-bold text-white">
            A
          </div>
          <div className="hidden sm:block">
            <p className="text-app-primary text-[12px] font-semibold">Admin</p>
            <p className="text-app-soft text-[10px]">默认团队</p>
          </div>
          <ChevronDown className="text-app-soft h-3.5 w-3.5" />
        </div>
      </div>
    </div>
  </nav>
);

/* ── Hero ── */
const Hero: React.FC<{ onEnterCaption: () => void }> = ({ onEnterCaption }) => (
  <section className="relative overflow-hidden pb-20 pt-16">
    <div className="pointer-events-none absolute inset-0">
      <div className="absolute -left-32 -top-32 h-[500px] w-[500px] rounded-full bg-blue-400/8 blur-3xl" />
      <div className="absolute -right-20 top-20 h-[400px] w-[400px] rounded-full bg-sky-300/10 blur-3xl" />
      <div className="absolute bottom-0 left-1/3 h-[300px] w-[600px] -translate-x-1/2 rounded-full bg-blue-200/12 blur-3xl" />
    </div>

    <div className="relative mx-auto grid max-w-[1440px] items-center gap-12 px-8 lg:grid-cols-[1fr_580px]">
      {/* Left copy */}
      <div className="max-w-xl">
        <p className="text-[11px] font-bold uppercase tracking-[0.32em] text-blue-600">
          OVERSEA AGENT
        </p>
        <h1 className="text-app-primary mt-4 text-[42px] font-bold leading-[1.12] tracking-tight lg:text-[52px]">
          为电商出海团队构建真正好用的
          <span className="bg-gradient-to-r from-blue-600 to-blue-500 bg-clip-text text-transparent">
            AI 创作工作台
          </span>
        </h1>
        <p className="text-app-muted mt-5 text-[15px] leading-[1.8]">
          从视频上传到智能剪辑、特效包装、一键导出，一站式完成视频创作。
          <br />
          AI 理解语境，自动生成更专业的视频作品。
        </p>
        <div className="mt-8 flex flex-wrap items-center gap-4">
          <motion.button
            type="button"
            onClick={onEnterCaption}
            whileHover={{ scale: 1.04 }}
            whileTap={{ scale: 0.97 }}
            className="group relative inline-flex h-12 items-center gap-2 overflow-hidden rounded-2xl bg-gradient-to-r from-blue-600 to-blue-500 px-7 text-[14px] font-semibold text-white shadow-lg shadow-blue-500/25 transition-shadow hover:shadow-xl hover:shadow-blue-500/30"
          >
            <span className="relative z-10 flex items-center gap-2">
              进入视频剪辑工作台
              <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
            </span>
            <span className="absolute inset-0 bg-gradient-to-r from-blue-500 to-blue-400 opacity-0 transition-opacity group-hover:opacity-100" />
          </motion.button>
          <Link
            to="#"
            className="theme-transition text-app-secondary inline-flex h-12 items-center gap-2 rounded-2xl border border-app bg-app-surface-solid px-6 text-[14px] font-medium shadow-sm hover:border-app-strong hover:shadow-md"
          >
            <BookOpen className="h-4 w-4" />
            使用指南
          </Link>
        </div>
      </div>

      {/* Right preview mockup */}
      <WorkspacePreview />
    </div>
  </section>
);

/* ── Caption workspace preview mockup ── */
const WorkspacePreview: React.FC = () => (
  <div className="relative">
    <div className="absolute -inset-4 rounded-[32px] bg-gradient-to-br from-blue-500/10 to-sky-400/5 blur-2xl" />
    <div className="theme-transition relative overflow-hidden rounded-[24px] border border-ws bg-app-surface-solid shadow-2xl shadow-slate-300/20">
      <div className="grid h-[440px] grid-cols-[200px_1fr_180px]">
        {/* Sidebar */}
        <div className="theme-transition border-r border-ws ws-card-muted p-3.5">
          <div className="mb-3 flex items-center gap-2">
            <Clapperboard className="h-3.5 w-3.5 text-blue-500" />
            <span className="text-ws-secondary text-[11px] font-semibold">视频剪辑工作台</span>
          </div>
          <div className="space-y-1">
            {[
              { icon: <Sparkles className="h-3 w-3" />, label: '新建剪辑任务', active: true },
              { icon: <FileText className="h-3 w-3" />, label: '任务列表' },
              { icon: <Layers className="h-3 w-3" />, label: '最近文件' },
              { icon: <Palette className="h-3 w-3" />, label: '我的模板' },
              { icon: <Languages className="h-3 w-3" />, label: '术语库' },
            ].map((item) => (
              <div
                key={item.label}
                className={`flex items-center gap-2 rounded-lg px-2.5 py-2 text-[11px] font-medium ${
                  item.active
                    ? 'bg-blue-50 text-blue-700'
                    : 'text-ws-muted hover:bg-app-surface-solid hover:text-ws-secondary'
                }`}
              >
                {item.icon}
                {item.label}
              </div>
            ))}
          </div>
        </div>

        {/* Center: chat area */}
        <div className="theme-transition flex flex-col bg-app-surface-solid">
          <div className="border-b border-ws px-4 py-2.5">
            <p className="text-ws-secondary text-[11px] font-semibold">对话式视频创作助手</p>
          </div>
          <div className="flex-1 space-y-3 overflow-hidden px-4 py-3">
            {/* AI welcome */}
            <div className="flex gap-2">
              <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-blue-600">
                <Sparkles className="h-3 w-3 text-white" />
              </div>
              <div className="theme-transition ws-card-muted rounded-xl rounded-tl-sm px-3 py-2">
                <p className="text-ws-muted text-[11px] leading-5">
                  你好！上传视频后，我会帮你完成智能剪辑和创意包装。支持特效、转场和风格调整。
                </p>
              </div>
            </div>
            {/* Upload card */}
            <div className="ml-8 rounded-xl border border-dashed border-blue-200 bg-blue-50/50 px-3 py-3">
              <div className="flex items-center gap-2">
                <Upload className="h-3.5 w-3.5 text-blue-500" />
                <span className="text-[11px] font-medium text-blue-700">product_demo.mp4</span>
              </div>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-blue-100">
                <div className="h-full w-[72%] rounded-full bg-gradient-to-r from-blue-500 to-blue-400" />
              </div>
              <p className="mt-1 text-[10px] text-blue-400">上传中 72%</p>
            </div>
            {/* User bubble */}
            <div className="flex justify-end">
              <div className="max-w-[80%] rounded-xl rounded-tr-sm bg-blue-600 px-3 py-2">
                <p className="text-[11px] leading-5 text-white">
                  帮我制作适合 TikTok 的短视频，保持口语化风格
                </p>
              </div>
            </div>
            {/* AI reply */}
            <div className="flex gap-2">
              <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-blue-600">
                <Sparkles className="h-3 w-3 text-white" />
              </div>
              <div className="theme-transition ws-card-muted rounded-xl rounded-tl-sm px-3 py-2">
                <p className="text-ws-muted text-[11px] leading-5">
                  已为你生成短视频剪辑方案，共 12 个镜头，已适配 TikTok 竖版画面。
                </p>
              </div>
            </div>
          </div>
          {/* Input */}
          <div className="border-t border-ws px-4 py-2.5">
            <div className="theme-transition ws-card-muted flex items-center gap-2 rounded-xl px-3 py-2">
              <MessageSquare className="text-ws-soft h-3.5 w-3.5" />
              <span className="text-ws-soft text-[11px]">有问题，尽管问...</span>
            </div>
          </div>
        </div>

        {/* Right: caption drafts */}
        <div className="theme-transition border-l border-ws ws-card-muted p-3">
          <p className="text-ws-soft mb-2 text-[10px] font-semibold uppercase tracking-[0.16em]">
            剪辑草稿
          </p>
          <div className="space-y-2">
            {[
              { time: '00:02', zh: '这款产品真的太好用了', en: 'This product is amazing' },
              { time: '00:05', zh: '你一定要试试看', en: 'You gotta try this' },
              { time: '00:08', zh: '效果立竿见影', en: 'Instant results' },
              { time: '00:12', zh: '超值推荐给大家', en: 'Highly recommend' },
            ].map((item) => (
              <div key={item.time} className="theme-transition rounded-lg border border-ws bg-app-surface-solid px-2 py-1.5">
                <p className="text-[9px] font-mono text-blue-500">{item.time}</p>
                <p className="text-ws-secondary mt-0.5 truncate text-[10px]">{item.zh}</p>
                <p className="text-ws-soft truncate text-[10px]">{item.en}</p>
              </div>
            ))}
          </div>
          <button
            type="button"
            className="mt-2 flex w-full items-center justify-center gap-1 rounded-lg bg-blue-500 py-1.5 text-[10px] font-medium text-white"
          >
            <Wand2 className="h-3 w-3" />
            导出视频
          </button>
        </div>
      </div>
    </div>
  </div>
);

/* ── Feature section ── */
const CAPABILITY_CARDS = [
  {
    icon: <Wand2 className="h-5 w-5" />,
    title: '润色表达',
    description: '优化视频节奏和表达，让画面更流畅、更贴合目标受众。',
    color: 'from-blue-500 to-blue-400',
    bgLight: 'bg-blue-50',
    textColor: 'text-blue-600',
  },
  {
    icon: <Languages className="h-5 w-5" />,
    title: '翻译优化',
    description: '基于上下文理解精准翻译，保留原始语义和情感色彩。',
    color: 'from-violet-500 to-violet-400',
    bgLight: 'bg-violet-50',
    textColor: 'text-violet-600',
  },
  {
    icon: <Type className="h-5 w-5" />,
    title: '术语替换',
    description: '一键应用行业术语库，确保品牌和产品名称统一规范。',
    color: 'from-emerald-500 to-emerald-400',
    bgLight: 'bg-emerald-50',
    textColor: 'text-emerald-600',
  },
  {
    icon: <Palette className="h-5 w-5" />,
    title: '调整风格',
    description: '根据目标平台和受众，切换口语化、专业或轻松等视频风格。',
    color: 'from-amber-500 to-amber-400',
    bgLight: 'bg-amber-50',
    textColor: 'text-amber-600',
  },
];

const FeatureSection: React.FC = () => (
  <section className="relative pb-24 pt-8">
    <div className="mx-auto max-w-[1440px] px-8">
      <div className="text-center">
        <p className="text-[11px] font-bold uppercase tracking-[0.32em] text-blue-600">
          AI-Powered Video Editing
        </p>
        <h2 className="text-app-primary mt-3 text-[28px] font-bold tracking-tight lg:text-[34px]">
          视频创作对话助手
        </h2>
        <p className="text-app-muted mx-auto mt-3 max-w-2xl text-[15px] leading-[1.8]">
          像聊天一样与 AI 协作创作视频。上传素材、描述需求，AI 自动剪辑、迭代、优化，直到你满意为止。
        </p>
      </div>

      <div className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
        {CAPABILITY_CARDS.map((card, i) => (
          <motion.div
            key={card.title}
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-40px' }}
            transition={{ duration: 0.4, delay: i * 0.08 }}
            className="theme-transition group rounded-2xl border border-app bg-app-surface-solid p-6 shadow-sm hover:shadow-md"
          >
            <div
              className={`flex h-11 w-11 items-center justify-center rounded-xl ${card.bgLight} ${card.textColor}`}
            >
              {card.icon}
            </div>
            <h3 className="text-app-primary mt-4 text-[15px] font-semibold">{card.title}</h3>
            <p className="text-app-muted mt-2 text-[13px] leading-[1.7]">{card.description}</p>
          </motion.div>
        ))}
      </div>
    </div>
  </section>
);

/* ── Footer ── */
const Footer: React.FC = () => (
  <footer className="theme-transition border-t border-app bg-app-surface">
    <div className="mx-auto flex max-w-[1440px] items-center justify-between px-8 py-6">
      <p className="text-app-soft text-[12px]">&copy; 2026 电商出海助手 &middot; OVERSEA AGENT</p>
      <div className="flex items-center gap-6">
        <a href="#" className="text-app-soft hover:text-app-secondary text-[12px]">
          隐私政策
        </a>
        <a href="#" className="text-app-soft hover:text-app-secondary text-[12px]">
          服务条款
        </a>
        <a href="#" className="text-app-soft hover:text-app-secondary text-[12px]">
          帮助中心
        </a>
      </div>
    </div>
  </footer>
);

/* ── Home page ── */
const HomeScene: React.FC<{
  onEnterCaption: () => void;
  snapshot?: boolean;
}> = ({ onEnterCaption, snapshot = false }) => (
  <div
    className={`bg-app-hero min-h-screen ${snapshot ? 'pointer-events-none select-none' : ''}`}
    aria-hidden={snapshot}
  >
    <Navbar />
    <Hero onEnterCaption={onEnterCaption} />
    <FeatureSection />
    <Footer />
  </div>
);

const Home: React.FC = () => {
  const navigate = useNavigate();
  const [transitioning, setTransitioning] = useState(false);

  const handleEnterCaption = useCallback(() => {
    setTransitioning(true);
  }, []);

  return (
    <>
      <HomeScene onEnterCaption={handleEnterCaption} />
      {transitioning ? (
        <PageFoldRevealTransition onComplete={() => navigate('/caption')} />
      ) : null}
    </>
  );
};

/* ── Page Fold & Reveal Transition ── */
interface PageFoldRevealTransitionProps {
  onComplete: () => void;
}

const PAGE_FOLD_EASE: [number, number, number, number] = [0.22, 1, 0.36, 1];
const PAGE_FLIGHT_DURATION_S = 2.35;
const PAPER_SEGMENTS = [
  {
    id: 'nose-left',
    clipPath: 'polygon(0 0, 52% 0, 50% 46%)',
    transformOrigin: '100% 100%',
    foldedTransform:
      'translate3d(2%, -5%, 34px) rotateX(65deg) rotateY(-72deg) rotateZ(14deg)',
    shade:
      'linear-gradient(160deg, rgba(15,23,42,0.12) 0%, rgba(15,23,42,0.02) 40%, transparent 100%)',
  },
  {
    id: 'nose-right',
    clipPath: 'polygon(52% 0, 100% 0, 50% 46%)',
    transformOrigin: '0% 100%',
    foldedTransform:
      'translate3d(-2%, -5%, 34px) rotateX(65deg) rotateY(72deg) rotateZ(-14deg)',
    shade:
      'linear-gradient(200deg, rgba(15,23,42,0.12) 0%, rgba(15,23,42,0.02) 40%, transparent 100%)',
  },
  {
    id: 'wing-left',
    clipPath: 'polygon(0 0, 50% 46%, 0 100%)',
    transformOrigin: '100% 54%',
    foldedTransform:
      'translate3d(12%, -3%, 26px) rotateX(26deg) rotateY(-76deg) rotateZ(18deg)',
    shade:
      'linear-gradient(145deg, rgba(15,23,42,0.18) 0%, rgba(15,23,42,0.06) 45%, transparent 100%)',
  },
  {
    id: 'wing-right',
    clipPath: 'polygon(100% 0, 100% 100%, 50% 46%)',
    transformOrigin: '0% 54%',
    foldedTransform:
      'translate3d(-12%, -3%, 26px) rotateX(26deg) rotateY(76deg) rotateZ(-18deg)',
    shade:
      'linear-gradient(215deg, rgba(15,23,42,0.18) 0%, rgba(15,23,42,0.06) 45%, transparent 100%)',
  },
  {
    id: 'tail-left',
    clipPath: 'polygon(0 100%, 50% 46%, 50% 100%)',
    transformOrigin: '100% 0%',
    foldedTransform:
      'translate3d(6%, 0%, 18px) rotateX(-18deg) rotateY(-48deg) rotateZ(7deg)',
    shade:
      'linear-gradient(120deg, rgba(148,163,184,0.16) 0%, rgba(15,23,42,0.03) 48%, transparent 100%)',
  },
  {
    id: 'tail-right',
    clipPath: 'polygon(50% 46%, 100% 100%, 50% 100%)',
    transformOrigin: '0% 0%',
    foldedTransform:
      'translate3d(-6%, 0%, 18px) rotateX(-18deg) rotateY(48deg) rotateZ(-7deg)',
    shade:
      'linear-gradient(240deg, rgba(148,163,184,0.16) 0%, rgba(15,23,42,0.03) 48%, transparent 100%)',
  },
] as const;

const PageFoldRevealTransition: React.FC<PageFoldRevealTransitionProps> = ({ onComplete }) => {
  const prefersReducedMotion = useReducedMotion();

  useEffect(() => {
    const timeout = window.setTimeout(
      onComplete,
      prefersReducedMotion ? 180 : PAGE_FLIGHT_DURATION_S * 1000 + 120,
    );
    return () => window.clearTimeout(timeout);
  }, [onComplete, prefersReducedMotion]);

  if (prefersReducedMotion) {
    return (
      <motion.div
        className="fixed inset-0 z-[9999] flex items-center justify-center bg-[#edf4ff]"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.18 }}
      >
        <PageBBack />
      </motion.div>
    );
  }

  return (
    <div className="fixed inset-0 z-[9999] overflow-hidden bg-[#edf4ff]">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(96,165,250,0.22),transparent_28%),radial-gradient(circle_at_80%_14%,rgba(56,189,248,0.12),transparent_22%),linear-gradient(180deg,#f4f8ff_0%,#e6eefc_100%)]" />
      <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(255,255,255,0)_0%,rgba(255,255,255,0.12)_100%)]" />

      <div
        className="absolute inset-0"
        style={{ perspective: '2000px', transformStyle: 'preserve-3d' }}
      >
        <motion.div
          className="absolute inset-0"
          style={{ transform: 'translateZ(-1px)' }}
          initial={{ opacity: 0.72, scale: 0.975, filter: 'blur(4px)' }}
          animate={{ opacity: 1, scale: 1, filter: 'blur(0px)' }}
          transition={{ duration: 1.1, ease: PAGE_FOLD_EASE, delay: 0.55 }}
        >
          <PageBBack />
        </motion.div>

        <motion.div
          className="pointer-events-none absolute left-1/2 top-1/2 h-[72vh] w-[66vw] min-w-[360px] max-w-[980px] -translate-x-1/2 -translate-y-1/2 rounded-full"
          initial={{ opacity: 0.22, scale: 0.8 }}
          animate={{ opacity: [0.22, 0.3, 0.18, 0], scale: [0.8, 0.9, 1.1, 1.35] }}
          transition={{ duration: PAGE_FLIGHT_DURATION_S, times: [0, 0.34, 0.76, 1], ease: 'linear' }}
          style={{
            background:
              'radial-gradient(circle, rgba(37,99,235,0.20) 0%, rgba(56,189,248,0.12) 28%, rgba(255,255,255,0) 68%)',
            filter: 'blur(40px)',
          }}
        />

        <motion.div
          className="pointer-events-none absolute inset-[2.2vh_2vw]"
          style={{
            transformOrigin: '50% 44%',
            transformStyle: 'preserve-3d',
          }}
          initial={{
            transform: 'translate3d(0px,0px,0px) scale3d(1,1,1) rotateX(0deg) rotateY(0deg) rotateZ(0deg)',
            filter: 'blur(0px)',
            opacity: 1,
          }}
          animate={{
            transform: [
              'translate3d(0px,0px,0px) scale3d(1,1,1) rotateX(0deg) rotateY(0deg) rotateZ(0deg)',
              'translate3d(0px,-12px,0px) scale3d(0.38,0.38,1) rotateX(18deg) rotateY(0deg) rotateZ(0deg)',
              'translate3d(110px,-54px,760px) scale3d(1.04,1.04,1) rotateX(12deg) rotateY(-16deg) rotateZ(-14deg)',
              'translate3d(250px,-120px,2000px) scale3d(3.6,3.6,1) rotateX(18deg) rotateY(-34deg) rotateZ(-22deg)',
            ],
            filter: ['blur(0px)', 'blur(0px)', 'blur(5px)', 'blur(18px)'],
            opacity: [1, 1, 1, 0],
          }}
          transition={{
            duration: PAGE_FLIGHT_DURATION_S,
            times: [0, 0.38, 0.79, 1],
            ease: 'linear',
          }}
        >
          <motion.div
            className="absolute inset-[14%_28%_18%_28%]"
            initial={{ opacity: 0 }}
            animate={{ opacity: [0, 0.75, 0.52, 0] }}
            transition={{
              duration: PAGE_FLIGHT_DURATION_S,
              times: [0, 0.38, 0.72, 1],
              ease: 'linear',
            }}
            style={{
              background:
                'radial-gradient(circle at 50% 52%, rgba(15,23,42,0.58) 0%, rgba(15,23,42,0.22) 34%, rgba(15,23,42,0) 72%)',
              filter: 'blur(26px)',
              transform: 'translate3d(0, 16%, -120px) rotateX(82deg)',
            }}
          />

          {PAPER_SEGMENTS.map((segment, index) => (
            <motion.div
              key={segment.id}
              className="absolute inset-0 overflow-hidden rounded-[32px] border border-white/45"
              style={{
                clipPath: segment.clipPath,
                transformOrigin: segment.transformOrigin,
                transformStyle: 'preserve-3d',
                backfaceVisibility: 'hidden',
                boxShadow: '0 32px 78px rgba(15, 23, 42, 0.16)',
                background:
                  'linear-gradient(180deg, rgba(255,255,255,0.14) 0%, rgba(255,255,255,0.02) 100%)',
              }}
              initial={{
                transform: 'translate3d(0, 0, 0) rotateX(0deg) rotateY(0deg) rotateZ(0deg)',
              }}
              animate={{ transform: segment.foldedTransform }}
              transition={{
                duration: 0.9,
                delay: index * 0.045,
                ease: PAGE_FOLD_EASE,
              }}
            >
              <HomeScene onEnterCaption={() => undefined} snapshot />
              <motion.div
                className="absolute inset-0"
                initial={{ opacity: 0.02 }}
                animate={{ opacity: 1 }}
                transition={{
                  duration: 0.85,
                  delay: 0.12 + index * 0.04,
                  ease: PAGE_FOLD_EASE,
                }}
                style={{ background: segment.shade }}
              />
              <motion.div
                className="absolute inset-0"
                initial={{ opacity: 0 }}
                animate={{ opacity: [0, 0.18, 0.08] }}
                transition={{
                  duration: 1.4,
                  delay: 0.1,
                  times: [0, 0.5, 1],
                  ease: PAGE_FOLD_EASE,
                }}
                style={{
                  background:
                    'linear-gradient(135deg, rgba(255,255,255,0.34) 0%, rgba(255,255,255,0.10) 38%, rgba(255,255,255,0) 72%)',
                }}
              />
            </motion.div>
          ))}
        </motion.div>
      </div>
    </div>
  );
};

const PageFrame: React.FC<{
  children: React.ReactNode;
  className?: string;
}> = ({ children, className = '' }) => (
  <div className={`absolute inset-0 p-[2px] sm:p-1.5 lg:p-2 ${className}`}>
    <div className="h-full rounded-[28px] border border-white/50 bg-white/68 shadow-[0_30px_90px_rgba(15,23,42,0.18)] backdrop-blur-xl">
      {children}
    </div>
  </div>
);

const STATIC_HISTORY_ITEMS = [
  {
    title: '20s TikTok 开箱短片',
    subtitle: '已生成镜头拆解、字幕草稿和导出参数',
    time: '今天 14:28',
    active: true,
  },
  {
    title: '夏季促销合集',
    subtitle: '等待确认口播节奏和英文标题',
    time: '今天 11:04',
    active: false,
  },
  {
    title: '护肤品对比视频',
    subtitle: '已完成关键帧理解，待导出成片',
    time: '昨天 20:17',
    active: false,
  },
] as const;

const STATIC_TIMELINE_TRACKS = [
  {
    label: 'VIDEO',
    clips: [
      { name: 'Intro Hook', width: '20%', tone: 'from-sky-500 to-blue-500' },
      { name: 'Benefit Demo', width: '28%', tone: 'from-indigo-500 to-blue-600' },
      { name: 'Social Proof', width: '18%', tone: 'from-cyan-500 to-sky-500' },
      { name: 'CTA', width: '14%', tone: 'from-amber-500 to-orange-500' },
    ],
  },
  {
    label: 'CAPTION',
    clips: [
      { name: '口播字幕', width: '34%', tone: 'from-emerald-500 to-teal-500' },
      { name: '卖点强调', width: '22%', tone: 'from-fuchsia-500 to-pink-500' },
      { name: '行动引导', width: '16%', tone: 'from-violet-500 to-fuchsia-500' },
    ],
  },
] as const;

const StaticDisclosure: React.FC<{
  title: string;
  status?: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}> = ({ title, status, children, defaultOpen = true }) => (
  <details open={defaultOpen} className="theme-transition group rounded-[18px] border ws-card">
    <summary className="flex cursor-pointer list-none items-center justify-between gap-2.5 px-3 py-2.5">
      <div className="flex min-w-0 items-center gap-2">
        <span className="h-2 w-2 rounded-full bg-sky-500" />
        <h4 className="text-ws-primary truncate text-[13px] font-medium">{title}</h4>
      </div>
      <div className="flex items-center gap-2.5">
        {status ? (
          <span className="text-ws-soft text-[10px] uppercase tracking-[0.22em]">{status}</span>
        ) : null}
        <ChevronDown className="text-ws-soft h-3.5 w-3.5 transition group-open:rotate-180" />
      </div>
    </summary>
    <div className="text-ws-muted border-t border-ws px-3 py-2.5 text-[13px] leading-5">
      {children}
    </div>
  </details>
);

const StaticUserBubble: React.FC<{ content: string }> = ({ content }) => (
  <article className="flex w-full items-start justify-end gap-2.5 pl-10 sm:pl-24">
    <div className="theme-transition w-fit max-w-[min(72%,34rem)] min-w-0 rounded-2xl bg-[color:var(--workspace-text-primary)] px-3 py-2.5 text-[color:var(--workspace-shell)] shadow-[0_10px_24px_rgba(0,0,0,0.18)]">
      <div className="mb-1 flex items-center gap-2 text-[9px] uppercase tracking-[0.18em]">
        <span className="text-white/60">You</span>
      </div>
      <p className="whitespace-pre-wrap break-words text-[12px] leading-5">{content}</p>
    </div>
    <div className="theme-transition ws-icon text-ws-secondary flex h-7 w-7 shrink-0 items-center justify-center rounded-full border shadow-sm">
      <MessageSquare className="h-3 w-3" />
    </div>
  </article>
);

const StaticAssistantCard: React.FC = () => (
  <article className="flex w-full items-start justify-start gap-2.5 pr-3 sm:pr-8">
    <div className="theme-transition ws-icon text-ws-primary flex h-7 w-7 shrink-0 items-center justify-center rounded-full border shadow-sm">
      <Bot className="h-3 w-3" />
    </div>

    <div className="theme-transition text-ws-secondary w-full max-w-[min(92%,52rem)] rounded-2xl border ws-card px-3 py-2.5 shadow-[0_10px_24px_rgba(0,0,0,0.18)]">
      <div className="border-ws mb-3 flex items-center justify-between gap-3 border-b pb-3">
        <div className="flex items-center gap-2 text-[9px] uppercase tracking-[0.18em]">
          <span className="text-ws-soft">Assistant</span>
        </div>
        <span className="text-ws-soft shrink-0 text-[10px] uppercase tracking-[0.18em]">
          已完成
        </span>
      </div>

      <div className="space-y-2.5">
        <details open className="theme-transition group rounded-[14px] border ws-card-muted">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-3 py-2.5">
            <div className="flex min-w-0 items-center gap-2">
              <Wrench className="text-ws-muted h-3.5 w-3.5" />
              <p className="text-ws-primary truncate text-[12px] font-medium">
                generate_edit_plan
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <span className="text-ws-soft text-[10px]">今天 14:28</span>
              <ChevronDown className="text-ws-soft h-3.5 w-3.5 transition group-open:rotate-180" />
            </div>
          </summary>
          <div className="border-t border-ws px-3 py-2.5">
            <pre className="theme-transition text-ws-muted whitespace-pre-wrap break-words rounded-[12px] border ws-card-contrast px-3 py-2 text-[11px] leading-5">
{`{
  "platform": "tiktok",
  "goal": "20s 转化导向短视频",
  "style": "口语化、快节奏、强钩子"
}`}
            </pre>
          </div>
        </details>

        <div className="theme-transition rounded-[14px] border ws-card-muted px-3 py-2.5">
          <p className="text-ws-primary text-[12px] font-medium">最终输出</p>
          <p className="text-ws-secondary mt-2 whitespace-pre-wrap break-words text-[12px] leading-5">
            已生成 4 段式结构：前 3 秒用强钩子切入，中段展示核心卖点和使用前后差异，结尾补上优惠与行动引导。
          </p>
        </div>
      </div>
    </div>
  </article>
);

const StaticTimelineCard: React.FC = () => (
  <div className="theme-transition ws-card rounded-[18px] border p-3">
    <div className="mb-3 flex items-center justify-between gap-3">
      <div>
        <p className="text-ws-soft text-[10px] font-medium uppercase tracking-[0.22em]">
          Timeline Preview
        </p>
        <p className="text-ws-primary mt-1 text-[13px] font-semibold">20 秒剪辑时间线</p>
      </div>
      <button
        type="button"
        className="theme-transition ws-card-muted text-ws-secondary inline-flex items-center gap-2 rounded-full border border-ws px-3 py-1.5 text-[11px] font-medium"
      >
        <Wand2 className="h-3.5 w-3.5" />
        调整节奏
      </button>
    </div>

    <div className="theme-transition ws-card-contrast rounded-[16px] border px-3 py-3">
      <div className="mb-3 flex items-center justify-between text-[10px] uppercase tracking-[0.18em] text-[color:var(--workspace-text-soft)]">
        <span>00:00</span>
        <span>00:05</span>
        <span>00:10</span>
        <span>00:15</span>
        <span>00:20</span>
      </div>
      <div className="space-y-3">
        {STATIC_TIMELINE_TRACKS.map((track) => (
          <div key={track.label} className="flex items-center gap-3">
            <div className="text-ws-soft w-14 text-[10px] font-semibold uppercase tracking-[0.18em]">
              {track.label}
            </div>
            <div className="flex min-w-0 flex-1 gap-2">
              {track.clips.map((clip) => (
                <div
                  key={clip.name}
                  className={`flex h-10 items-center rounded-[12px] bg-gradient-to-r ${clip.tone} px-3 text-[11px] font-medium text-white shadow-sm`}
                  style={{ width: clip.width }}
                >
                  <span className="truncate">{clip.name}</span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  </div>
);

const PageBBack: React.FC = () => (
  <PageFrame className="ws-shell bg-[radial-gradient(circle_at_top_left,rgba(59,130,246,0.2),transparent_30%),linear-gradient(180deg,#eef4fb_0%,#e4edf9_100%)]">
    <div className="theme-transition ws-shell h-full overflow-hidden rounded-[28px] border border-ws shadow-[0_36px_100px_rgba(15,23,42,0.14)]">
      <div className="grid h-full min-h-0 lg:grid-cols-[272px_minmax(0,1fr)_368px]">
        <aside className="theme-transition ws-panel hidden min-h-0 overflow-hidden lg:block">
          <div className="flex h-full min-h-0 flex-col px-3.5 py-3">
            <div className="mb-3 flex shrink-0 items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="text-ws-soft flex items-center gap-2 text-[10px] font-medium uppercase tracking-[0.24em]">
                  <Clapperboard className="h-3 w-3" />
                  Caption Studio
                </div>
                <h1 className="text-ws-primary mt-1 text-[17px] font-semibold">桌面工作台</h1>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <ThemeToggle />
                <button
                  type="button"
                  className="theme-transition ws-card text-ws-secondary flex h-9 w-9 items-center justify-center rounded-full border"
                  aria-label="收起历史侧栏"
                >
                  <ChevronLeft className="h-4 w-4" />
                </button>
                <Link
                  to="/"
                  className="theme-transition ws-card text-ws-secondary shrink-0 rounded-full border px-2.5 py-1.5 text-[11px] font-medium"
                >
                  返回
                </Link>
              </div>
            </div>

            <button
              type="button"
              className="theme-transition mb-3 inline-flex w-full items-center justify-center rounded-xl border border-ws bg-[var(--workspace-card)] px-4 py-2.5 text-[12px] font-medium text-[var(--workspace-text-secondary)]"
            >
              <RefreshCcw className="mr-2 h-4 w-4" />
              新建任务
            </button>

            <div className="min-h-0 flex-1 space-y-2 overflow-y-auto pr-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
              {STATIC_HISTORY_ITEMS.map((item) => (
                <button
                  key={item.title}
                  type="button"
                  className={`w-full rounded-2xl border px-3 py-3 text-left transition ${
                    item.active
                      ? 'border-sky-500/40 bg-sky-500/10 shadow-sm'
                      : 'theme-transition border-ws ws-card hover:border-ws-strong'
                  }`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-ws-primary truncate text-sm font-medium">{item.title}</p>
                    <span className="text-ws-soft shrink-0 text-[11px]">{item.time}</span>
                  </div>
                  <p className="text-ws-muted mt-2 line-clamp-2 text-xs leading-5">
                    {item.subtitle}
                  </p>
                </button>
              ))}
            </div>
          </div>
        </aside>

        <section className="theme-transition ws-shell flex min-h-0 flex-col overflow-hidden">
          <div className="theme-transition ws-shell min-h-0 flex-1 overflow-hidden px-6 py-5">
            <div className="flex min-h-full flex-col gap-3">
              <StaticAssistantCard />
              <StaticUserBubble content="按 TikTok 节奏再压缩一点，前 3 秒更直接，结尾把优惠信息单独抬出来。" />
              <div className="flex w-full items-start gap-2.5 pr-3 sm:pr-8">
                <div className="theme-transition ws-icon text-ws-primary flex h-7 w-7 shrink-0 items-center justify-center rounded-full border shadow-sm">
                  <Sparkles className="h-3 w-3" />
                </div>
                <div className="flex w-full max-w-[min(92%,52rem)] flex-col gap-3">
                  <div className="theme-transition rounded-2xl border ws-card px-3 py-2.5 shadow-[0_10px_24px_rgba(0,0,0,0.18)]">
                    <div className="border-ws mb-3 flex items-center justify-between gap-3 border-b pb-3">
                      <span className="text-ws-soft text-[9px] uppercase tracking-[0.18em]">
                        Assistant
                      </span>
                      <span className="text-ws-soft text-[10px] uppercase tracking-[0.18em]">
                        已更新
                      </span>
                    </div>
                    <p className="text-ws-secondary text-[12px] leading-5">
                      已将节奏压缩到 20 秒内，开头改成“3 秒看到效果”，并把优惠 CTA 独立成最后一段。
                    </p>
                  </div>
                  <StaticTimelineCard />
                </div>
              </div>
              <div className="h-px shrink-0" />
            </div>
          </div>

          <div className="theme-transition ws-shell shrink-0 px-6 pb-5 pt-4">
            <div className="theme-transition ws-card mx-auto min-h-[96px] w-full max-w-[960px] rounded-[28px] border px-4 py-3.5 shadow-[0_12px_40px_rgba(0,0,0,0.18)]">
              <div className="mb-3 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    className="theme-transition ws-card-muted text-ws-secondary flex h-9 w-9 items-center justify-center rounded-full border border-ws"
                  >
                    <Upload className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    className="theme-transition ws-card-muted text-ws-secondary rounded-full border border-ws px-3 py-1.5 text-[11px] font-medium"
                  >
                    TikTok
                  </button>
                  <button
                    type="button"
                    className="theme-transition ws-card-muted text-ws-secondary rounded-full border border-ws px-3 py-1.5 text-[11px] font-medium"
                  >
                    Keyframe
                  </button>
                </div>
                <span className="text-ws-soft text-[10px] uppercase tracking-[0.18em]">
                  Instant
                </span>
              </div>
              <div className="flex items-end gap-3">
                <div className="theme-transition ws-card-contrast flex-1 rounded-[22px] border px-4 py-3">
                  <p className="text-ws-secondary text-[13px] leading-6">
                    帮我输出最终字幕版本，并保持结尾 CTA 与时间线一致。
                  </p>
                </div>
                <button
                  type="button"
                  className="inline-flex h-11 w-11 items-center justify-center rounded-full bg-[color:var(--workspace-text-primary)] text-[color:var(--workspace-shell)] shadow-[0_10px_24px_rgba(0,0,0,0.22)]"
                >
                  <ArrowRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          </div>
        </section>

        <aside className="theme-transition ws-panel hidden min-h-0 overflow-hidden lg:block">
          <div className="flex h-full min-h-0 flex-col px-3.5 py-3">
            <div className="theme-transition ws-card shrink-0 rounded-[18px] border px-3 py-2">
              <div className="flex items-center justify-between gap-2">
                <div className="flex min-w-0 items-center gap-2">
                  <div className="theme-transition ws-icon text-ws-secondary flex h-7 w-7 shrink-0 items-center justify-center rounded-full border shadow-sm">
                    <Sparkles className="h-3.5 w-3.5" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-ws-primary truncate text-[13px] font-semibold">
                      20s TikTok 开箱短片
                    </p>
                  </div>
                </div>
                <span className="theme-transition ws-chip text-ws-muted shrink-0 rounded-full border px-2 py-1 text-[10px] font-medium uppercase tracking-[0.18em]">
                  completed
                </span>
              </div>
              <p className="text-ws-muted mt-1.5 line-clamp-2 text-[11px] leading-4">
                当前轮次结束后，保留剪辑方案、字幕、导出命令和成片下载入口。
              </p>
            </div>

            <div className="min-h-0 flex-1 space-y-2.5 overflow-y-auto pt-2 pr-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
              <StaticDisclosure title="剪辑状态" status="进行中">
                <div className="space-y-2 text-[12px]">
                  {[
                    ['关键帧理解', '已完成', '识别出产品展示、近景细节和优惠口播节点。'],
                    ['字幕草稿', '已完成', '已按口语化风格重写，并控制在 20 秒节奏内。'],
                    ['导出成片', '待执行', '等待确认最终 CTA 后开始拼接导出。'],
                  ].map(([label, state, detail]) => (
                    <div key={label} className="theme-transition ws-card-muted rounded-[14px] border px-3 py-2">
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-ws-secondary text-[12px] font-medium">{label}</p>
                        <span className="text-ws-soft text-[10px] uppercase tracking-[0.18em]">
                          {state}
                        </span>
                      </div>
                      <p className="text-ws-muted mt-1 text-[11px] leading-4">{detail}</p>
                    </div>
                  ))}
                </div>
              </StaticDisclosure>

              <StaticDisclosure title="当前产物" status="已同步">
                <div className="space-y-2">
                  <div className="theme-transition group rounded-[14px] border ws-card-muted">
                    <div className="flex items-center justify-between gap-3 px-3 py-2">
                      <div className="text-ws-soft text-[11px] uppercase tracking-[0.18em]">
                        剪辑草稿
                      </div>
                      <ChevronDown className="text-ws-soft h-3.5 w-3.5" />
                    </div>
                    <div className="border-ws border-t px-3 py-2">
                      <pre className="text-ws-secondary whitespace-pre-wrap break-words font-sans text-[12px]">
{`00:00-00:03 强钩子
00:03-00:11 产品卖点
00:11-00:16 使用前后对比
00:16-00:20 优惠 CTA`}
                      </pre>
                    </div>
                  </div>

                  <div className="theme-transition group rounded-[14px] border ws-card-muted">
                    <div className="flex items-center justify-between gap-3 px-3 py-2">
                      <div className="text-ws-soft text-[11px] uppercase tracking-[0.18em]">
                        导出成片
                      </div>
                      <ChevronDown className="text-ws-soft h-3.5 w-3.5" />
                    </div>
                    <div className="border-ws border-t space-y-2 px-3 py-2">
                      <p className="text-ws-secondary break-words text-[12px]">
                        tiktok-product-cut-v4.mp4
                      </p>
                      <p className="text-ws-muted text-[12px] leading-5">
                        H.264，1080x1920，已套用快节奏转场与字幕安全区。
                      </p>
                      <button
                        type="button"
                        className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-[color:var(--workspace-text-primary)] px-3 py-2.5 text-[12px] font-medium text-[color:var(--workspace-shell)]"
                      >
                        <Download className="h-4 w-4" />
                        导出剪辑视频
                      </button>
                    </div>
                  </div>
                </div>
              </StaticDisclosure>
            </div>
          </div>
        </aside>
      </div>
    </div>
  </PageFrame>
);

export default Home;
