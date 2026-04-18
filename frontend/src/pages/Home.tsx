import React from 'react';
import { ArrowRight, Clapperboard, Compass, MessagesSquare } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Link } from 'react-router-dom';

const FEATURE_CARDS = [
  {
    title: '字幕生成对话助手',
    description:
      '上传视频后直接进入创作对话，连续修改字幕草稿、镜头节奏和钩子文案。',
    href: '/caption',
    icon: <Clapperboard className="h-6 w-6" />,
    accent:
      'from-sky-500/15 via-blue-500/10 to-transparent text-sky-700',
  },
  {
    title: '多 Agent 讨论',
    description:
      '让不同角色围绕宣传目标讨论，沉淀可执行的内容方向和脚本骨架。',
    href: '/multi-agent',
    icon: <MessagesSquare className="h-6 w-6" />,
    accent:
      'from-emerald-500/15 via-teal-500/10 to-transparent text-emerald-700',
  },
  {
    title: 'Deep Research',
    description:
      '汇总市场趋势、竞品信息和切入建议，为出海选题和卖点排序提供依据。',
    href: '/deep-research',
    icon: <Compass className="h-6 w-6" />,
    accent:
      'from-amber-500/15 via-orange-500/10 to-transparent text-amber-700',
  },
];

const Home: React.FC = () => {
  return (
    <div className="relative min-h-screen overflow-hidden px-4 py-6 md:px-6">
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute left-[-8%] top-[-10%] h-80 w-80 rounded-full bg-sky-300/20 blur-3xl" />
        <div className="absolute right-[-10%] top-[24%] h-96 w-96 rounded-full bg-amber-300/18 blur-3xl" />
        <div className="absolute bottom-[-14%] left-[36%] h-80 w-80 rounded-full bg-emerald-300/14 blur-3xl" />
      </div>

      <main className="relative mx-auto max-w-7xl rounded-[36px] border border-white/60 bg-white/48 px-6 py-8 shadow-[0_40px_120px_rgba(15,23,42,0.12)] backdrop-blur-2xl md:px-10 md:py-10">
        <section className="grid gap-8 border-b border-white/50 pb-10 lg:grid-cols-[minmax(0,1.15fr)_360px] lg:items-end">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.32em] text-slate-500">
              Oversea Agent
            </p>
            <h1 className="mt-4 max-w-4xl text-4xl font-semibold tracking-[-0.06em] text-slate-950 md:text-6xl md:leading-[1.02]">
              为电商出海团队做一套真正可用的 AI 创作工作台
            </h1>
            <p className="mt-5 max-w-2xl text-sm leading-8 text-slate-600 md:text-base">
              不只是几个调用模型的按钮，而是把字幕生成、协同讨论和调研洞察组织成清晰的工作流界面。字幕模块已重构为对话式创作体验。
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button asChild size="lg">
                <Link to="/caption">
                  进入字幕工作台
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Link>
              </Button>
              <Button asChild variant="outline" size="lg">
                <Link to="/deep-research">查看研究模块</Link>
              </Button>
            </div>
          </div>

          <div className="rounded-[28px] border border-slate-200/80 bg-[linear-gradient(160deg,#0f172a_0%,#1d4ed8_100%)] p-6 text-white shadow-[0_24px_70px_rgba(30,64,175,0.22)]">
            <p className="text-xs uppercase tracking-[0.26em] text-white/60">
              Current Focus
            </p>
            <h2 className="mt-3 text-2xl font-semibold tracking-[-0.04em]">
              字幕生成现在是会话界面
            </h2>
            <p className="mt-4 text-sm leading-7 text-white/78">
              上传视频、补充产品信息、直接发送任务要求。后续所有改稿都走同一条对话线程，体验更接近
              ChatGPT，而不是传统表单工具。
            </p>
          </div>
        </section>

        <section className="mt-10 grid gap-5 md:grid-cols-3">
          {FEATURE_CARDS.map((card) => (
            <Link
              key={card.title}
              to={card.href}
              className={`group rounded-[28px] border border-white/70 bg-gradient-to-br ${card.accent} p-6 shadow-[0_18px_60px_rgba(15,23,42,0.06)] transition duration-300 hover:-translate-y-1 hover:shadow-[0_22px_72px_rgba(15,23,42,0.1)]`}
            >
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white/80">
                {card.icon}
              </div>
              <h3 className="mt-5 text-2xl font-semibold tracking-[-0.04em] text-slate-950">
                {card.title}
              </h3>
              <p className="mt-3 text-sm leading-7 text-slate-600">
                {card.description}
              </p>
              <div className="mt-8 inline-flex items-center text-sm font-semibold text-slate-900">
                打开模块
                <ArrowRight className="ml-2 h-4 w-4 transition group-hover:translate-x-1" />
              </div>
            </Link>
          ))}
        </section>

        <footer className="mt-10 border-t border-white/50 pt-6 text-sm text-slate-500">
          © 2026 电商出海助手
        </footer>
      </main>
    </div>
  );
};

export default Home;
