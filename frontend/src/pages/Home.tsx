import React, { useState, useCallback } from 'react';
import {
  ArrowRight,
  Bell,
  ChevronDown,
  Clapperboard,
  FileText,
  BookOpen,
  Globe,
  Layers,
  MessageSquare,
  Palette,
  Sparkles,
  Upload,
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
const Home: React.FC = () => {
  const navigate = useNavigate();
  const [transitioning, setTransitioning] = useState(false);

  const handleEnterCaption = useCallback(() => {
    setTransitioning(true);
  }, []);

  if (transitioning) {
    return <WormholeTransition onComplete={() => navigate('/caption')} />;
  }

  return (
    <div className="bg-app-hero min-h-screen">
      <Navbar />
      <Hero onEnterCaption={handleEnterCaption} />
      <FeatureSection />
      <Footer />
    </div>
  );
};

/* ── Blackhole Cinematic Transition ── */
interface WormholeTransitionProps {
  onComplete: () => void;
}

const STAR_COUNT = 36;
const RING_COUNT = 4;
const GPU_HINTS: React.CSSProperties = { willChange: 'transform, opacity', transform: 'translateZ(0)' };

const WormholeTransition: React.FC<WormholeTransitionProps> = ({ onComplete }) => {
  const prefersReducedMotion = useReducedMotion();
  const stars = React.useMemo(
    () =>
      Array.from({ length: STAR_COUNT }, (_, i) => {
        const angle = Math.random() * Math.PI * 2;
        const dist = 80 + Math.random() * 600;
        return {
          id: i,
          angle,
          dist,
          size: 1.0 + Math.random() * 3.0,
          brightness: 0.4 + Math.random() * 0.6,
          delay: Math.random() * 0.5,
          fallDuration: 0.6 + (dist / 600) * 1.2 + Math.random() * 0.4,
          hue: [200, 210, 220, 240, 260][Math.floor(Math.random() * 5)],
          streakBase: 4 + Math.random() * 8,
        };
      }),
    [],
  );

  const rings = React.useMemo(
    () =>
      Array.from({ length: RING_COUNT }, (_, i) => ({
        id: i,
        baseRadius: 80 + i * 60,
        opacity: 0.08 + (RING_COUNT - i) * 0.04,
        border: i < 2 ? 2 : 1,
        hue: i % 2 === 0 ? 220 : 260,
        spinDuration: 1.6 + i * 0.5,
        reverse: i % 2 === 0,
      })),
    [],
  );

  if (prefersReducedMotion) {
    return (
      <motion.div
        className="fixed inset-0 z-[9999] flex items-center justify-center bg-black"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.22 }}
        onAnimationComplete={onComplete}
      >
        <Sparkles className="h-8 w-8 text-blue-300/70" />
      </motion.div>
    );
  }

  return (
    <div className="fixed inset-0 z-[9999] overflow-hidden bg-[#000000]">
      {/* ── ENTRY PHASE ── */}

      {/* A: Stars appear then streak toward center — single merged layer */}
      <div className="absolute inset-0">
        {stars.map((s) => {
          const cosA = Math.cos(s.angle);
          const sinA = Math.sin(s.angle);
          const streakScaleX = s.streakBase * 8;
          return (
            <motion.div
              key={`s-${s.id}`}
              layout={false}
              className="absolute left-1/2 top-1/2"
              style={{
                rotate: `${(s.angle * 180) / Math.PI}deg`,
                transformOrigin: '0 50%',
                ...GPU_HINTS,
              }}
              initial={{
                x: cosA * s.dist,
                y: sinA * s.dist,
                scaleX: 1,
                scaleY: 1,
                opacity: 0,
              }}
              animate={{
                x: [cosA * s.dist, cosA * s.dist, cosA * s.dist * 0.03],
                y: [sinA * s.dist, sinA * s.dist, sinA * s.dist * 0.03],
                scaleX: [1, s.streakBase * 2, streakScaleX],
                scaleY: [1, 1, 0.6, 0.3],
                opacity: [0, s.brightness, s.brightness, 0],
              }}
              transition={{
                duration: 1.2 + s.fallDuration * 0.45,
                delay: s.delay * 0.3,
                ease: [0.15, 0, 0.85, 1],
                x: { times: [0, 0.3, 1] },
                y: { times: [0, 0.3, 1] },
                scaleX: { times: [0, 0.55, 1] },
                scaleY: { times: [0, 0.55, 0.8, 1] },
                opacity: { times: [0, 0.12, 0.45, 1] },
              }}
            >
              <div
                style={{
                  width: s.size,
                  height: s.size,
                  borderRadius: '50%',
                  backgroundColor: `hsl(${s.hue}, 80%, 85%)`,
                }}
              />
            </motion.div>
          );
        })}
      </div>

      {/* B: Concentric rings — scale-based animation (GPU-composited) */}
      <div className="absolute inset-0 pointer-events-none">
        {rings.map((r) => (
          <motion.div
            key={`ring-${r.id}`}
            layout={false}
            className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2"
            style={{
              width: r.baseRadius * 2,
              height: r.baseRadius * 2,
              ...GPU_HINTS,
            }}
            initial={{ scale: 1, opacity: 0 }}
            animate={{
              scale: [1, 1, 0.25, 0.04],
              opacity: [0, r.opacity, r.opacity * 2.5, 0],
            }}
            transition={{
              duration: 2.2,
              delay: 0.2 + r.id * 0.05,
              ease: [0.2, 0, 0.8, 1],
              scale: { times: [0, 0.3, 0.75, 1] },
              opacity: { times: [0, 0.2, 0.6, 1] },
            }}
          >
            <div
              className="wh-spin-vortex w-full h-full rounded-full"
              style={{
                border: `${r.border}px solid hsl(${r.hue}, 70%, 60% / ${r.opacity})`,
                animationDuration: `${r.spinDuration}s`,
                animationDirection: r.reverse ? 'reverse' : 'normal',
              }}
            />
          </motion.div>
        ))}
      </div>

      {/* C: Black hole center — grows from pinhole to dominate the frame */}
      <motion.div
        layout={false}
        className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2"
        style={GPU_HINTS}
        initial={{ scale: 0, opacity: 0 }}
        animate={{ scale: [0, 0.15, 0.6, 12], opacity: [0, 0.4, 0.9, 1] }}
        transition={{ duration: 2.5, delay: 0.1, ease: [0.3, 0, 0.7, 1], times: [0, 0.15, 0.5, 1] }}
      >
        <div className="absolute -inset-8 rounded-full bg-gradient-to-br from-blue-600/25 via-violet-500/15 to-transparent blur-2xl wh-glow" />
        <div
          className="wh-spin-vortex absolute -inset-4 rounded-full border-2 border-blue-300/25"
          style={{ animationDuration: '3s', boxShadow: '0 0 30px 8px rgba(147,197,253,0.12)' }}
        />
        <div className="relative h-20 w-20 rounded-full bg-black shadow-[0_0_80px_20px_rgba(0,0,0,0.9),0_0_160px_40px_rgba(30,58,138,0.08)]" />
      </motion.div>

      {/* ── THE OPENING UP CLIMAX ── */}

      {/* D: Explosive point-origin white burst */}
      <motion.div
        layout={false}
        className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2"
        style={GPU_HINTS}
        initial={{ scale: 0, opacity: 0 }}
        animate={{ scale: [0, 0.01, 0.8, 50], opacity: [0, 0, 0.7, 1] }}
        transition={{ duration: 0.7, delay: 2.3, ease: [0.1, 0, 0.2, 1] }}
      >
        <div className="h-4 w-4 rounded-full bg-white" style={{ boxShadow: '0 0 60px 30px rgba(255,255,255,0.8), 0 0 120px 60px rgba(147,197,253,0.4)' }} />
      </motion.div>

      {/* E: Anamorphic lens flare */}
      <motion.div
        layout={false}
        className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2"
        style={GPU_HINTS}
        initial={{ scaleX: 0, opacity: 0 }}
        animate={{ scaleX: [0, 0.5, 1.5, 20], opacity: [0, 0.9, 1, 0.6] }}
        transition={{ duration: 0.6, delay: 2.35, ease: [0.1, 0, 0.2, 1] }}
      >
        <div
          className="h-[3px] w-[300px] -translate-x-1/2 rounded-full"
          style={{
            background: 'linear-gradient(90deg, transparent 0%, rgba(147,197,253,0.3) 15%, rgba(255,255,255,0.95) 40%, white 50%, rgba(255,255,255,0.95) 60%, rgba(147,197,253,0.3) 85%, transparent 100%)',
            boxShadow: '0 0 20px 6px rgba(147,197,253,0.3), 0 0 60px 20px rgba(147,197,253,0.15)',
          }}
        />
      </motion.div>

      {/* F: Diagonal lens flare streaks */}
      {[0, 60, 120].map((deg) => (
        <motion.div
          key={`flare-${deg}`}
          layout={false}
          className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2"
          style={GPU_HINTS}
          initial={{ scale: 0, opacity: 0, rotate: deg }}
          animate={{ scale: [0, 0.3, 8], opacity: [0, 0.7, 0], rotate: deg }}
          transition={{ duration: 0.8, delay: 2.35, ease: 'easeOut' }}
        >
          <div className="h-[1px] w-[1600px] -translate-x-1/2 bg-gradient-to-r from-transparent via-white/70 to-transparent" />
        </motion.div>
      ))}

      {/* G: Blinding full-frame white */}
      <motion.div
        layout={false}
        className="absolute inset-0 bg-white"
        style={GPU_HINTS}
        initial={{ opacity: 0 }}
        animate={{ opacity: [0, 0, 1, 1, 1, 0.6] }}
        transition={{ duration: 1.8, delay: 2.5, times: [0, 0.05, 0.12, 0.5, 0.75, 1] }}
      />

      {/* ── INTERFACE EMERGENCE ── */}

      {/* H: White dissolves into the studio — radial wipe from center */}
      <motion.div
        layout={false}
        className="theme-transition absolute inset-0 ws-shell"
        style={GPU_HINTS}
        initial={{ clipPath: 'circle(0% at 50% 50%)' }}
        animate={{ clipPath: 'circle(75% at 50% 50%)' }}
        transition={{ duration: 0.8, delay: 3.8, ease: [0.22, 1, 0.36, 1] }}
        onAnimationComplete={onComplete}
      >
        {/* Soft residual light glow — fading */}
        <motion.div
          layout={false}
          className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2"
          style={GPU_HINTS}
          initial={{ scale: 3, opacity: 0.4 }}
          animate={{ scale: 2, opacity: 0 }}
          transition={{ duration: 1.2, delay: 4.0, ease: 'easeOut' }}
        >
          <div className="h-96 w-96 rounded-full bg-gradient-to-br from-blue-400/15 via-white/8 to-transparent blur-3xl" />
        </motion.div>

        {/* Studio loading content */}
        <motion.div
          layout={false}
          className="relative z-10 flex h-full w-full items-center justify-center"
          initial={{ opacity: 0, scale: 0.94 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.8, delay: 4.2, ease: 'easeOut' }}
        >
          <div className="text-center">
            <motion.div
              layout={false}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 4.3 }}
            >
              <Sparkles className="mx-auto h-8 w-8 text-blue-400/60" />
            </motion.div>
            <motion.p
              layout={false}
              className="text-ws-soft mt-3 text-sm"
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 4.5 }}
            >
              正在进入视频剪辑工作台...
            </motion.p>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
};

export default Home;
