import React, { useState } from 'react';
import { Button } from '../components/ui/button';
import { researchMarket } from '../api/api';
import { useNavigate } from 'react-router-dom';
import { ResearchResponse } from '../types';

const DeepResearch: React.FC = () => {
  const [product, setProduct] = useState<string>('');
  const [targetMarket, setTargetMarket] = useState<string>('');
  const [result, setResult] = useState<ResearchResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>('');
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!product || !targetMarket) {
      setError('请输入产品名称和目标市场');
      return;
    }

    setLoading(true);
    setError('');
    setResult(null);

    try {
      const response = await researchMarket(product, targetMarket);
      setResult(response);
    } catch (err) {
      setError('调研失败，请重试');
      console.error('Error researching market:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-50 to-indigo-100 dark:from-gray-900 dark:to-indigo-900 flex flex-col items-center justify-center p-4">
      <div className="max-w-4xl w-full bg-white dark:bg-gray-800 rounded-2xl shadow-xl p-8 md:p-12">
        <div className="flex items-center mb-8">
          <button 
            onClick={() => navigate('/')}
            className="mr-4 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </button>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
            Deep Research
          </h1>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* 产品名称 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              产品名称
            </label>
            <input
              type="text"
              value={product}
              onChange={(e) => setProduct(e.target.value)}
              className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm dark:bg-gray-700 dark:border-gray-600 dark:text-gray-200"
              placeholder="例如：智能手表"
            />
          </div>

          {/* 目标市场 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              目标市场
            </label>
            <input
              type="text"
              value={targetMarket}
              onChange={(e) => setTargetMarket(e.target.value)}
              className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm dark:bg-gray-700 dark:border-gray-600 dark:text-gray-200"
              placeholder="例如：美国市场"
            />
          </div>

          {/* 错误信息 */}
          {error && (
            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 px-4 py-3 rounded-md">
              {error}
            </div>
          )}

          {/* 提交按钮 */}
          <div>
            <Button 
              type="submit" 
              className="w-full"
              disabled={loading}
              variant="outline"
            >
              {loading ? '调研中...' : '开始调研'}
            </Button>
          </div>
        </form>

        {/* 调研结果 */}
        {result && (
          <div className="mt-8 space-y-6">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4">
              调研结果
            </h2>

            {/* 市场趋势 */}
            <div className="bg-gray-50 dark:bg-gray-700 rounded-md p-4">
              <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-3">
                市场趋势
              </h3>
              <p className="text-sm text-gray-800 dark:text-gray-200">
                {result.market_trends}
              </p>
            </div>

            {/* 竞品分析 */}
            <div className="bg-gray-50 dark:bg-gray-700 rounded-md p-4">
              <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-3">
                竞品分析
              </h3>
              <p className="text-sm text-gray-800 dark:text-gray-200">
                {result.competitor_analysis}
              </p>
            </div>

            {/* 策略建议 */}
            <div className="bg-gray-50 dark:bg-gray-700 rounded-md p-4">
              <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-3">
                出海策略建议
              </h3>
              <p className="text-sm text-gray-800 dark:text-gray-200">
                {result.strategy_suggestions}
              </p>
            </div>

            <div className="mt-4">
              <Button 
                onClick={() => {
                  const content = `# 市场调研报告\n\n## 产品：${product}\n## 目标市场：${targetMarket}\n\n## 市场趋势\n${result.market_trends}\n\n## 竞品分析\n${result.competitor_analysis}\n\n## 出海策略建议\n${result.strategy_suggestions}`;
                  const blob = new Blob([content], { type: 'text/markdown' });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement('a');
                  a.href = url;
                  a.download = 'market_research_report.md';
                  document.body.appendChild(a);
                  a.click();
                  document.body.removeChild(a);
                  URL.revokeObjectURL(url);
                }}
                variant="default"
                className="w-full"
              >
                下载调研报告
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default DeepResearch;
