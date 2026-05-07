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
import { motion } from 'framer-motion';

/* ── Navigation ── */
const NAV_LINKS = [
  { label: '工作台', href: '/caption', active: true },
  { label: '字幕任务', href: '/caption' },
  { label: '模板中心', href: '#' },
  { label: '术语库', href: '#' },
  { label: '团队管理', href: '#' },
  { label: '使用指南', href: '#' },
];

const Navbar: React.FC = () => (
  <nav className="sticky top-0 z-50 border-b border-slate-200/60 bg-white/72 backdrop-blur-xl">
    <div className="mx-auto flex h-16 max-w-[1440px] items-center justify-between px-8">
      <div className="flex items-center gap-10">
        <Link to="/" className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-blue-600 to-blue-500 shadow-md shadow-blue-500/20">
            <Globe className="h-4.5 w-4.5 text-white" />
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-[15px] font-bold tracking-tight text-slate-900">
              电商出海助手
            </span>
            <span className="hidden text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-400 sm:inline">
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
                  : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
              }`}
            >
              {link.label}
            </Link>
          ))}
        </div>
      </div>
      <div className="flex items-center gap-4">
        <button
          type="button"
          className="relative flex h-9 w-9 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-500 transition hover:border-slate-300 hover:text-slate-700"
        >
          <Bell className="h-4 w-4" />
          <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-red-500" />
        </button>
        <div className="flex items-center gap-2.5 rounded-xl border border-slate-200 bg-white px-3 py-1.5 transition hover:border-slate-300">
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-blue-600 text-[11px] font-bold text-white">
            A
          </div>
          <div className="hidden sm:block">
            <p className="text-[12px] font-semibold text-slate-800">Admin</p>
            <p className="text-[10px] text-slate-400">默认团队</p>
          </div>
          <ChevronDown className="h-3.5 w-3.5 text-slate-400" />
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
        <h1 className="mt-4 text-[42px] font-bold leading-[1.12] tracking-tight text-slate-900 lg:text-[52px]">
          为电商出海团队构建真正好用的
          <span className="bg-gradient-to-r from-blue-600 to-blue-500 bg-clip-text text-transparent">
            AI 创作工作台
          </span>
        </h1>
        <p className="mt-5 text-[15px] leading-[1.8] text-slate-500">
          从视频上传到字幕生成、编辑、导出，一站式完成字幕创作。
          <br />
          AI 理解语境，自动生成更自然准确的字幕。
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
              进入字幕工作台
              <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
            </span>
            <span className="absolute inset-0 bg-gradient-to-r from-blue-500 to-blue-400 opacity-0 transition-opacity group-hover:opacity-100" />
          </motion.button>
          <Link
            to="#"
            className="inline-flex h-12 items-center gap-2 rounded-2xl border border-slate-200 bg-white px-6 text-[14px] font-medium text-slate-700 shadow-sm transition hover:border-slate-300 hover:shadow-md"
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
    <div className="relative overflow-hidden rounded-[24px] border border-slate-200/80 bg-white shadow-2xl shadow-slate-300/30">
      <div className="grid h-[440px] grid-cols-[200px_1fr_180px]">
        {/* Sidebar */}
        <div className="border-r border-slate-100 bg-slate-50/80 p-3.5">
          <div className="mb-3 flex items-center gap-2">
            <Clapperboard className="h-3.5 w-3.5 text-blue-500" />
            <span className="text-[11px] font-semibold text-slate-700">字幕工作台</span>
          </div>
          <div className="space-y-1">
            {[
              { icon: <Sparkles className="h-3 w-3" />, label: '新建字幕任务', active: true },
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
                    : 'text-slate-500 hover:bg-white hover:text-slate-700'
                }`}
              >
                {item.icon}
                {item.label}
              </div>
            ))}
          </div>
        </div>

        {/* Center: chat area */}
        <div className="flex flex-col bg-white">
          <div className="border-b border-slate-100 px-4 py-2.5">
            <p className="text-[11px] font-semibold text-slate-700">对话式字幕生成助手</p>
          </div>
          <div className="flex-1 space-y-3 overflow-hidden px-4 py-3">
            {/* AI welcome */}
            <div className="flex gap-2">
              <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-blue-600">
                <Sparkles className="h-3 w-3 text-white" />
              </div>
              <div className="rounded-xl rounded-tl-sm bg-slate-50 px-3 py-2">
                <p className="text-[11px] leading-5 text-slate-600">
                  你好！上传视频后，我会帮你生成精准的字幕草稿。支持多语言翻译和风格调整。
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
                  帮我生成适合 TikTok 的英文字幕，保持口语化风格
                </p>
              </div>
            </div>
            {/* AI reply */}
            <div className="flex gap-2">
              <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-blue-600">
                <Sparkles className="h-3 w-3 text-white" />
              </div>
              <div className="rounded-xl rounded-tl-sm bg-slate-50 px-3 py-2">
                <p className="text-[11px] leading-5 text-slate-600">
                  已为你生成口语化英文字幕，共 12 条，已适配 TikTok 竖版画面。
                </p>
              </div>
            </div>
          </div>
          {/* Input */}
          <div className="border-t border-slate-100 px-4 py-2.5">
            <div className="flex items-center gap-2 rounded-xl bg-slate-50 px-3 py-2">
              <MessageSquare className="h-3.5 w-3.5 text-slate-400" />
              <span className="text-[11px] text-slate-400">有问题，尽管问...</span>
            </div>
          </div>
        </div>

        {/* Right: caption drafts */}
        <div className="border-l border-slate-100 bg-slate-50/80 p-3">
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-400">
            字幕草稿
          </p>
          <div className="space-y-2">
            {[
              { time: '00:02', zh: '这款产品真的太好用了', en: 'This product is amazing' },
              { time: '00:05', zh: '你一定要试试看', en: 'You gotta try this' },
              { time: '00:08', zh: '效果立竿见影', en: 'Instant results' },
              { time: '00:12', zh: '超值推荐给大家', en: 'Highly recommend' },
            ].map((item) => (
              <div key={item.time} className="rounded-lg border border-slate-100 bg-white px-2 py-1.5">
                <p className="text-[9px] font-mono text-blue-500">{item.time}</p>
                <p className="mt-0.5 truncate text-[10px] text-slate-700">{item.zh}</p>
                <p className="truncate text-[10px] text-slate-400">{item.en}</p>
              </div>
            ))}
          </div>
          <button
            type="button"
            className="mt-2 flex w-full items-center justify-center gap-1 rounded-lg bg-blue-500 py-1.5 text-[10px] font-medium text-white"
          >
            <Wand2 className="h-3 w-3" />
            导出字幕
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
    description: '优化字幕措辞，让翻译更地道、更贴合目标语言文化习惯。',
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
    description: '根据目标平台和受众，切换口语化、专业或轻松等字幕风格。',
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
          AI-Powered Caption
        </p>
        <h2 className="mt-3 text-[28px] font-bold tracking-tight text-slate-900 lg:text-[34px]">
          字幕生成对话助手
        </h2>
        <p className="mx-auto mt-3 max-w-2xl text-[15px] leading-[1.8] text-slate-500">
          像聊天一样与 AI 协作创作字幕。上传视频、描述需求，AI 自动生成、迭代、优化，直到你满意为止。
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
            className="group rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm transition-shadow hover:shadow-md"
          >
            <div
              className={`flex h-11 w-11 items-center justify-center rounded-xl ${card.bgLight} ${card.textColor}`}
            >
              {card.icon}
            </div>
            <h3 className="mt-4 text-[15px] font-semibold text-slate-900">{card.title}</h3>
            <p className="mt-2 text-[13px] leading-[1.7] text-slate-500">{card.description}</p>
          </motion.div>
        ))}
      </div>
    </div>
  </section>
);

/* ── Footer ── */
const Footer: React.FC = () => (
  <footer className="border-t border-slate-100 bg-white/60">
    <div className="mx-auto flex max-w-[1440px] items-center justify-between px-8 py-6">
      <p className="text-[12px] text-slate-400">&copy; 2026 电商出海助手 &middot; OVERSEA AGENT</p>
      <div className="flex items-center gap-6">
        <a href="#" className="text-[12px] text-slate-400 hover:text-slate-600">
          隐私政策
        </a>
        <a href="#" className="text-[12px] text-slate-400 hover:text-slate-600">
          服务条款
        </a>
        <a href="#" className="text-[12px] text-slate-400 hover:text-slate-600">
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
    <div className="min-h-screen bg-gradient-to-b from-slate-50 via-white to-slate-50">
      <Navbar />
      <Hero onEnterCaption={handleEnterCaption} />
      <FeatureSection />
      <Footer />
    </div>
  );
};

/* ── Wormhole Transition ── */
interface WormholeTransitionProps {
  onComplete: () => void;
}

const PARTICLE_COUNT = 40;
const ENERGY_LINE_COUNT = 16;

const WormholeTransition: React.FC<WormholeTransitionProps> = ({ onComplete }) => {
  const particles = React.useMemo(
    () =>
      Array.from({ length: PARTICLE_COUNT }, (_, i) => ({
        id: i,
        dx: `${(Math.random() - 0.5) * 600}px`,
        dy: `${(Math.random() - 0.5) * 600}px`,
        size: 2 + Math.random() * 4,
        delay: Math.random() * 0.4,
        duration: 0.6 + Math.random() * 0.6,
      })),
    [],
  );

  const energyLines = React.useMemo(
    () =>
      Array.from({ length: ENERGY_LINE_COUNT }, (_, i) => ({
        id: i,
        left: `${5 + Math.random() * 90}%`,
        travel: `${200 + Math.random() * 400}px`,
        delay: Math.random() * 0.5,
        height: 40 + Math.random() * 80,
      })),
    [],
  );

  return (
    <div className="fixed inset-0 z-[9999] overflow-hidden bg-[#020617]">
      {/* Phase 1: Ripple from center */}
      <motion.div
        className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2"
        initial={{ scale: 0, opacity: 0.8 }}
        animate={{ scale: 6, opacity: 0 }}
        transition={{ duration: 0.7, ease: 'easeOut' }}
      >
        <div className="h-48 w-48 rounded-full border-2 border-blue-400/60" />
      </motion.div>

      {/* Phase 2: Page distortion overlay */}
      <motion.div
        className="absolute inset-0"
        initial={{ opacity: 0, backdropFilter: 'blur(0px)' }}
        animate={{ opacity: 1, backdropFilter: 'blur(12px)' }}
        transition={{ duration: 0.4, delay: 0.15 }}
      >
        <div className="h-full w-full bg-gradient-radial from-blue-950/80 via-[#020617]/90 to-[#020617]" />
      </motion.div>

      {/* Phase 3: Vortex / blackhole */}
      <motion.div
        className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2"
        initial={{ scale: 0.3, opacity: 0 }}
        animate={{ scale: 1.8, opacity: 1 }}
        transition={{ duration: 0.8, delay: 0.25, ease: [0.22, 1, 0.36, 1] }}
      >
        {/* Outer ring */}
        <div className="wh-spin-vortex absolute -inset-32 rounded-full border border-blue-500/20" />
        <div
          className="wh-spin-vortex absolute -inset-24 rounded-full border border-blue-400/15"
          style={{ animationDirection: 'reverse', animationDuration: '1.6s' }}
        />
        <div
          className="wh-spin-vortex absolute -inset-16 rounded-full border border-violet-500/10"
          style={{ animationDuration: '2.4s' }}
        />
        {/* Core glow */}
        <div className="wh-glow absolute -inset-8 rounded-full bg-gradient-to-br from-blue-600/30 via-violet-600/20 to-transparent blur-2xl" />
        {/* Dark center */}
        <div className="relative h-32 w-32 rounded-full bg-gradient-to-br from-[#020617] via-[#0a1128] to-[#020617] shadow-[0_0_80px_20px_rgba(37,99,235,0.15)]" />
      </motion.div>

      {/* Phase 3b: Particles flying into center */}
      <div className="absolute inset-0">
        {particles.map((p) => (
          <motion.div
            key={p.id}
            className="absolute left-1/2 top-1/2 rounded-full bg-blue-400"
            style={{
              width: p.size,
              height: p.size,
              '--wh-dx': p.dx,
              '--wh-dy': p.dy,
            } as React.CSSProperties}
            initial={{ x: 0, y: 0, opacity: 0.8, scale: 1 }}
            animate={{
              x: [0, parseFloat(p.dx) * 0.3, 0],
              y: [0, parseFloat(p.dy) * 0.3, 0],
              opacity: [0, 0.9, 0],
              scale: [1, 0.6, 0],
            }}
            transition={{
              duration: p.duration,
              delay: 0.3 + p.delay,
              ease: 'easeIn',
            }}
          />
        ))}
      </div>

      {/* Phase 3c: Energy lines */}
      <div className="absolute inset-0">
        {energyLines.map((line) => (
          <motion.div
            key={line.id}
            className="absolute left-1/2 w-px bg-gradient-to-b from-transparent via-blue-400/60 to-transparent"
            style={{
              left: line.left,
              height: line.height,
              '--wh-travel': line.travel,
            } as React.CSSProperties}
            initial={{ y: -200, opacity: 0, scaleY: 0.5 }}
            animate={{ y: 200, opacity: [0, 0.8, 0], scaleY: [0.5, 1.2, 0.8] }}
            transition={{
              duration: 0.9,
              delay: 0.35 + line.delay,
              ease: 'easeInOut',
            }}
          />
        ))}
      </div>

      {/* Phase 4: Light at the end of the tunnel */}
      <motion.div
        className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2"
        initial={{ scale: 0, opacity: 0 }}
        animate={{ scale: [0, 0.5, 3], opacity: [0, 0.3, 1] }}
        transition={{ duration: 0.8, delay: 0.85, ease: [0.22, 1, 0.36, 1] }}
      >
        <div className="h-64 w-64 rounded-full bg-gradient-to-br from-white/90 via-blue-200/70 to-blue-400/30 blur-3xl" />
      </motion.div>

      {/* Phase 5: New page reveal — wipe from center */}
      <motion.div
        className="absolute inset-0 bg-[#090909]"
        initial={{ clipPath: 'circle(0% at 50% 50%)' }}
        animate={{ clipPath: 'circle(75% at 50% 50%)' }}
        transition={{ duration: 0.6, delay: 1.2, ease: [0.22, 1, 0.36, 1] }}
        onAnimationComplete={onComplete}
      >
        {/* Caption page silhouette elements */}
        <motion.div
          className="flex h-full w-full items-center justify-center"
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5, delay: 1.3 }}
        >
          <div className="text-center">
            <Sparkles className="mx-auto h-8 w-8 text-blue-400/60" />
            <p className="mt-3 text-sm text-slate-400">正在进入字幕工作台...</p>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
};

export default Home;
