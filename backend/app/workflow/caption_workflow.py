from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from app.core.utils import extract_keyframes
from app.providers.llm_providers import LLMProviderFactory
import requests


class CaptionWorkflow:
    """字幕生成工作流，包含审核分支"""
    
    def __init__(self, provider_name: str = "openai"):
        self.llm_provider = LLMProviderFactory.get_provider(provider_name)
        self.graph = self._build_graph()
    
    def _build_graph(self):
        """构建字幕生成工作流图，包含审核分支"""
        # 定义状态结构
        class CaptionState:
            def __init__(self):
                self.video_path = ""
                self.platform = ""
                self.product_manual = None
                self.keyframes = []
                self.frame_analyses = []
                self.product_info = ""
                self.generated_caption = ""
                self.review_result = ""
                self.revision_count = 0
                self.max_revisions = 3
        
        # 初始化状态
        initial_state = CaptionState()
        
        # 定义节点
        def init_workflow(state, video_path, platform, product_manual):
            state.video_path = video_path
            state.platform = platform
            state.product_manual = product_manual
            state.revision_count = 0
            return state
        
        def extract_keyframes_node(state):
            """提取视频关键帧"""
            state.keyframes = extract_keyframes(state.video_path)
            return state
        
        def analyze_frames(state):
            """分析关键帧内容"""
            frame_analyses = []
            for i, frame in enumerate(state.keyframes):
                prompt = f"请详细描述这个视频帧的内容，包括产品细节、场景、人物动作等。这是一个电商产品视频的第{i+1}帧。"
                analysis = self.llm_provider.analyze_image(frame, prompt)
                frame_analyses.append(analysis)
            state.frame_analyses = frame_analyses
            return state
        
        def get_product_info(state):
            """获取产品信息"""
            state.product_info = state.product_manual
            if not state.product_info:
                # 如果没有提供产品说明书，进行网络搜索
                state.product_info = self._search_product_info(state.frame_analyses)
            return state
        
        def generate_caption(state):
            """生成字幕"""
            prompt = f"请为以下电商产品视频生成字幕文件。\n\n视频内容分析：\n{''.join(state.frame_analyses)}\n\n产品信息：\n{state.product_info}\n\n发布平台：{state.platform}\n\n请生成适合该平台的字幕，包括时间轴和内容，确保字幕准确反映视频内容和产品特点。"
            state.generated_caption = self.llm_provider.generate_text(prompt)
            return state
        
        def review_caption(state):
            """审核字幕"""
            prompt = ChatPromptTemplate.from_template(
                "请审核以下生成的字幕，评估其质量：\n\n" +
                "字幕内容：\n{caption}\n\n" +
                "评估标准：\n" +
                "1. 准确性：字幕是否准确反映视频内容和产品信息\n" +
                "2. 流畅度：字幕是否流畅自然\n" +
                "3. 平台适配：字幕是否适合目标平台\n" +
                "4. 完整性：字幕是否完整覆盖视频内容\n\n" +
                "请回答'通过'或'需要修改'，并简要说明原因。"
            )
            
            messages = [
                HumanMessage(content=prompt.format(caption=state.generated_caption))
            ]
            
            state.review_result = self.llm_provider.generate_text(messages)
            return state
        
        def check_review_result(state):
            """检查审核结果"""
            if "通过" in state.review_result:
                return "approved"
            else:
                if state.revision_count >= state.max_revisions:
                    return "rejected"
                else:
                    return "revise"
        
        def revise_caption(state):
            """修改字幕"""
            prompt = ChatPromptTemplate.from_template(
                "请根据审核反馈修改以下字幕：\n\n" +
                "原字幕：\n{caption}\n\n" +
                "审核反馈：\n{review_result}\n\n" +
                "请生成修改后的字幕，确保解决审核反馈中提到的问题。"
            )
            
            messages = [
                HumanMessage(content=prompt.format(
                    caption=state.generated_caption,
                    review_result=state.review_result
                ))
            ]
            
            state.generated_caption = self.llm_provider.generate_text(messages)
            state.revision_count += 1
            return state
        
        # 构建图
        workflow = StateGraph(CaptionState)
        
        workflow.add_node("init", init_workflow)
        workflow.add_node("extract_keyframes", extract_keyframes_node)
        workflow.add_node("analyze_frames", analyze_frames)
        workflow.add_node("get_product_info", get_product_info)
        workflow.add_node("generate_caption", generate_caption)
        workflow.add_node("review_caption", review_caption)
        workflow.add_node("revise_caption", revise_caption)
        
        workflow.set_entry_point("init")
        workflow.add_edge("init", "extract_keyframes")
        workflow.add_edge("extract_keyframes", "analyze_frames")
        workflow.add_edge("analyze_frames", "get_product_info")
        workflow.add_edge("get_product_info", "generate_caption")
        workflow.add_edge("generate_caption", "review_caption")
        workflow.add_conditional_edges(
            "review_caption",
            check_review_result,
            {"approved": END, "rejected": END, "revise": "revise_caption"}
        )
        workflow.add_edge("revise_caption", "review_caption")
        
        return workflow.compile()
    
    def _search_product_info(self, frame_analyses: list) -> str:
        """
        搜索产品信息
        :param frame_analyses: 关键帧分析结果
        :return: 产品信息
        """
        # 从关键帧分析中提取产品关键词
        keywords = self._extract_keywords(frame_analyses)
        search_query = f"{keywords} 产品信息 说明书"
        
        # 这里使用一个简单的搜索API模拟，实际项目中可以使用Google API等
        # 模拟搜索结果
        return f"基于搜索结果，该产品是一款{keywords}，具有以下特点：..."
    
    def _extract_keywords(self, frame_analyses: list) -> str:
        """
        从关键帧分析中提取关键词
        :param frame_analyses: 关键帧分析结果
        :return: 产品关键词
        """
        prompt = f"从以下视频帧分析中提取产品的主要关键词，只返回关键词，不要其他内容：\n{''.join(frame_analyses)}"
        keywords = self.llm_provider.generate_text(prompt)
        return keywords
    
    def run(self, video_path: str, platform: str, product_manual: str = None) -> dict:
        """
        运行字幕生成工作流
        :param video_path: 视频文件路径
        :param platform: 发布平台
        :param product_manual: 产品说明书内容
        :return: 生成的字幕文件内容和审核结果
        """
        result = self.graph.invoke(
            {},
            video_path=video_path,
            platform=platform,
            product_manual=product_manual
        )
        
        return {
            "caption": result.generated_caption,
            "review_result": result.review_result,
            "revision_count": result.revision_count,
            "status": "approved" if "通过" in result.review_result else "rejected" if result.revision_count >= result.max_revisions else "revised"
        }

