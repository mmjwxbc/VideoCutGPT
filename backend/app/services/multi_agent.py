from app.providers.llm_providers import LLMProviderFactory
from langgraph.graph import StateGraph, END
from typing import Dict, List, Any


class MultiAgentSystem:
    """多Agent讨论系统"""
    
    def __init__(self, provider_name: str = "openai"):
        self.llm_provider = LLMProviderFactory.get_provider(provider_name)
        self.graph = self._build_graph()
    
    def _build_graph(self):
        """构建Agent图"""
        # 定义状态
        class State(Dict):
            discussion: List[str]
            topic: str
            requirements: str
            final_script: str
        
        # 定义Agent
        def market_research_agent(state: State):
            """市场调研Agent"""
            prompt = f"作为市场调研专家，请针对'{state['topic']}'收集最新的热点信息和市场趋势，特别是与以下要求相关的内容：{state['requirements']}"
            research_result = self.llm_provider.generate_text(prompt)
            state['discussion'].append(f"【市场调研专家】: {research_result}")
            return state
        
        def video_analysis_agent(state: State):
            """视频分析Agent"""
            prompt = f"作为视频分析专家，请分析当前热门视频的特点和趋势，特别是与'{state['topic']}'相关的视频，以及如何满足以下要求：{state['requirements']}"
            analysis_result = self.llm_provider.generate_text(prompt)
            state['discussion'].append(f"【视频分析专家】: {analysis_result}")
            return state
        
        def script_writer_agent(state: State):
            """脚本编写Agent"""
            prompt = f"作为脚本编写专家，请根据以下讨论内容，为'{state['topic']}'创建一个视频拍摄脚本，包括转场效果和具体场景描述，满足以下要求：{state['requirements']}\n\n讨论内容：\n{''.join(state['discussion'])}"
            script = self.llm_provider.generate_text(prompt)
            state['final_script'] = script
            return state
        
        # 构建图
        workflow = StateGraph(State)
        workflow.add_node("market_research", market_research_agent)
        workflow.add_node("video_analysis", video_analysis_agent)
        workflow.add_node("script_writer", script_writer_agent)
        
        workflow.set_entry_point("market_research")
        workflow.add_edge("market_research", "video_analysis")
        workflow.add_edge("video_analysis", "script_writer")
        workflow.add_edge("script_writer", END)
        
        return workflow.compile()
    
    def run_discussion(self, topic: str, requirements: str) -> Dict[str, Any]:
        """
        运行多Agent讨论
        :param topic: 讨论主题
        :param requirements: 具体要求
        :return: 讨论结果和最终脚本
        """
        initial_state = {
            "discussion": [],
            "topic": topic,
            "requirements": requirements,
            "final_script": ""
        }
        
        result = self.graph.invoke(initial_state)
        return result
