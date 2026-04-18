import React, { useState } from 'react';
import { Button } from '../components/ui/button';
import { runDiscussion } from '../api/api';
import { useNavigate } from 'react-router-dom';
import { DiscussionResponse } from '../types';

const MultiAgentDiscussion: React.FC = () => {
  const [topic, setTopic] = useState<string>('');
  const [requirements, setRequirements] = useState<string>('');
  const [result, setResult] = useState<DiscussionResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>('');
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!topic) {
      setError('请输入讨论主题');
      return;
    }

    setLoading(true);
    setError('');
    setResult(null);

    try {
      const response = await runDiscussion(topic, requirements);
      setResult(response);
    } catch (err) {
      setError('讨论失败，请重试');
      console.error('Error running discussion:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-green-50 to-teal-100 dark:from-gray-900 dark:to-teal-900 flex flex-col items-center justify-center p-4">
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
            多Agent讨论系统
          </h1>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* 讨论主题 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              讨论主题
            </label>
            <input
              type="text"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm dark:bg-gray-700 dark:border-gray-600 dark:text-gray-200"
              placeholder="例如：智能手表产品宣传视频"
            />
          </div>

          {/* 具体要求 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              具体要求
            </label>
            <textarea
              value={requirements}
              onChange={(e) => setRequirements(e.target.value)}
              rows={4}
              className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm dark:bg-gray-700 dark:border-gray-600 dark:text-gray-200"
              placeholder="例如：突出产品的健康监测功能，适合运动场景，时长30秒左右"
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
              variant="secondary"
            >
              {loading ? '讨论中...' : '开始讨论'}
            </Button>
          </div>
        </form>

        {/* 讨论结果 */}
        {result && (
          <div className="mt-8">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4">
              讨论结果
            </h2>

            {/* 讨论过程 */}
            <div className="bg-gray-50 dark:bg-gray-700 rounded-md p-4 mb-6">
              <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-3">
                讨论过程
              </h3>
              <div className="space-y-4">
                {result.discussion.map((message, index) => (
                  <div key={index} className="border-b border-gray-200 dark:border-gray-600 pb-3 last:border-0">
                    <p className="text-sm text-gray-800 dark:text-gray-200">
                      {message}
                    </p>
                  </div>
                ))}
              </div>
            </div>

            {/* 最终脚本 */}
            <div className="bg-gray-50 dark:bg-gray-700 rounded-md p-4">
              <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-3">
                最终脚本
              </h3>
              <pre className="text-sm text-gray-800 dark:text-gray-200 whitespace-pre-wrap">
                {result.final_script}
              </pre>
            </div>

            <div className="mt-4">
              <Button 
                onClick={() => {
                  const blob = new Blob([result.final_script], { type: 'text/plain' });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement('a');
                  a.href = url;
                  a.download = 'video_script.txt';
                  document.body.appendChild(a);
                  a.click();
                  document.body.removeChild(a);
                  URL.revokeObjectURL(url);
                }}
                variant="outline"
                className="w-full"
              >
                下载脚本文件
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default MultiAgentDiscussion;
