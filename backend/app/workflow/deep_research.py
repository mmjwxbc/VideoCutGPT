from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate
from app.providers.llm_providers import LLMProviderFactory
import requests
import json


class DeepResearchWorkflow:
    """深度研究工作流，仿照deerflow和google deepresearch架构"""
    
    def __init__(self, provider_name: str = "openai"):
        self.llm_provider = LLMProviderFactory.get_provider(provider_name)
        self.graph = self._build_graph()
    
    def _build_graph(self):
        """构建研究工作流图"""
        # 定义状态结构
        class ResearchState:
            def __init__(self):
                self.topic = ""
                self.research_question = ""
                self.sources = []
                self.extracted_info = []
                self.synthesis = ""
                self.citations = []
                self.iteration_count = 0
                self.max_iterations = 5
        
        # 初始化状态
        initial_state = ResearchState()
        
        # 定义节点
        def init_research(state, topic, research_question):
            state.topic = topic
            state.research_question = research_question
            state.iteration_count = 0
            return state
        
        def search_sources(state):
            """搜索相关资料"""
            search_query = f"{state.topic} {state.research_question}"
            # 模拟搜索API，实际项目中可以使用Google Custom Search API
            sources = self._simulate_search(search_query)
            state.sources = sources
            return state
        
        def extract_info(state):
            """从资料中提取信息"""
            extracted_info = []
            for source in state.sources:
                # 模拟从每个来源提取信息
                info = self._extract_from_source(source, state.research_question)
                extracted_info.append(info)
            state.extracted_info = extracted_info
            return state
        
        def synthesize_info(state):
            """综合分析信息"""
            prompt = ChatPromptTemplate.from_template(
                "基于以下资料，回答研究问题：{research_question}\n\n" +
                "资料：\n{extracted_info}\n\n" +
                "请提供详细的分析和结论，并引用资料来源。"
            )
            
            messages = [
                HumanMessage(content=prompt.format(
                    research_question=state.research_question,
                    extracted_info="\n".join(state.extracted_info)
                ))
            ]
            
            synthesis = self.llm_provider.generate_text(messages)
            state.synthesis = synthesis
            state.iteration_count += 1
            return state
        
        def check_completeness(state):
            """检查研究是否完整"""
            if state.iteration_count >= state.max_iterations:
                return "complete"
            
            # 评估当前综合结果是否足够全面
            prompt = ChatPromptTemplate.from_template(
                "评估以下研究结论是否全面回答了研究问题：{research_question}\n\n" +
                "结论：\n{synthesis}\n\n" +
                "请回答'是'或'否'，并简要说明原因。"
            )
            
            messages = [
                HumanMessage(content=prompt.format(
                    research_question=state.research_question,
                    synthesis=state.synthesis
                ))
            ]
            
            evaluation = self.llm_provider.generate_text(messages)
            if "是" in evaluation:
                return "complete"
            else:
                return "iterate"
        
        def refine_research(state):
            """优化研究方向"""
            # 基于当前结果生成新的搜索查询
            prompt = ChatPromptTemplate.from_template(
                "基于当前研究结果，生成3个更具体的搜索查询，以获取更全面的信息：\n\n" +
                "当前研究问题：{research_question}\n\n" +
                "当前结论：\n{synthesis}\n\n" +
                "请提供3个具体的搜索查询。"
            )
            
            messages = [
                HumanMessage(content=prompt.format(
                    research_question=state.research_question,
                    synthesis=state.synthesis
                ))
            ]
            
            new_queries = self.llm_provider.generate_text(messages)
            # 执行新的搜索并添加到现有资料中
            for query in new_queries.split('\n'):
                if query.strip():
                    new_sources = self._simulate_search(query.strip())
                    state.sources.extend(new_sources)
            return state
        
        # 构建图
        workflow = StateGraph(ResearchState)
        
        workflow.add_node("init", init_research)
        workflow.add_node("search", search_sources)
        workflow.add_node("extract", extract_info)
        workflow.add_node("synthesize", synthesize_info)
        workflow.add_node("refine", refine_research)
        
        workflow.set_entry_point("init")
        workflow.add_edge("init", "search")
        workflow.add_edge("search", "extract")
        workflow.add_edge("extract", "synthesize")
        workflow.add_conditional_edges(
            "synthesize",
            check_completeness,
            {"complete": END, "iterate": "refine"}
        )
        workflow.add_edge("refine", "extract")
        
        return workflow.compile()
    
    def _simulate_search(self, query: str) -> list:
        """模拟搜索API"""
        # 模拟搜索结果
        return [
            f"来源1: {query} - 详细信息...",
            f"来源2: {query} - 相关数据...",
            f"来源3: {query} - 专家观点..."
        ]
    
    def _extract_from_source(self, source: str, research_question: str) -> str:
        """从来源中提取信息"""
        prompt = ChatPromptTemplate.from_template(
            "从以下来源中提取与研究问题相关的信息：{research_question}\n\n" +
            "来源：\n{source}\n\n" +
            "请提取最相关的信息。"
        )
        
        messages = [
            HumanMessage(content=prompt.format(
                research_question=research_question,
                source=source
            ))
        ]
        
        return self.llm_provider.generate_text(messages)
    
    def run(self, topic: str, research_question: str) -> dict:
        """
        运行深度研究工作流
        :param topic: 研究主题
        :param research_question: 具体研究问题
        :return: 研究结果
        """
        result = self.graph.invoke(
            {},
            topic=topic,
            research_question=research_question
        )
        
        return {
            "topic": result.topic,
            "research_question": result.research_question,
            "synthesis": result.synthesis,
            "sources": result.sources,
            "iterations": result.iteration_count
        }
