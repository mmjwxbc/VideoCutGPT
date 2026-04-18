from autogen import AssistantAgent, UserProxyAgent, GroupChat, GroupChatManager
import os
from app.providers.llm_providers import LLMProviderFactory


class MultiAgentDiscussion:
    """多agent团队无限讨论小组"""
    
    def __init__(self, provider_name: str = "openai"):
        self.llm_provider = LLMProviderFactory.get_provider(provider_name)
        self.agents = []
        self.group_chat = None
        self.manager = None
        self._initialize_agents()
    
    def _initialize_agents(self):
        """初始化多个agent角色"""
        # 定义不同角色的agent
        agent_config = {
            "llm_config": {
                "temperature": 0.7,
                "max_tokens": 1000,
            }
        }
        
        # 创建不同角色的agent
        self.agents = [
            AssistantAgent(
                name="专家",
                system_message="你是一个领域专家，提供专业的知识和见解",
                llm_config=agent_config
            ),
            AssistantAgent(
                name="质疑者",
                system_message="你是一个批判性思维者，善于提出质疑和不同观点",
                llm_config=agent_config
            ),
            AssistantAgent(
                name="协调者",
                system_message="你是一个协调者，负责整合不同观点，推动讨论进展",
                llm_config=agent_config
            ),
            AssistantAgent(
                name="创新者",
                system_message="你是一个创新者，提供创造性的解决方案和思路",
                llm_config=agent_config
            )
        ]
        
        # 创建群聊
        self.group_chat = GroupChat(
            agents=self.agents,
            messages=[],
            max_round=50,  # 设置最大轮数，但实际上可以通过用户输入继续
            speaker_selection_method="round_robin"
        )
        
        # 创建群聊管理器
        self.manager = GroupChatManager(
            groupchat=self.group_chat,
            llm_config=agent_config
        )
    
    def start_discussion(self, topic: str) -> list:
        """
        开始讨论
        :param topic: 讨论主题
        :return: 讨论记录
        """
        # 创建用户代理
        user_proxy = UserProxyAgent(
            name="用户",
            system_message="你是讨论的发起者，提出讨论主题并引导讨论",
            llm_config=agent_config,
            human_input_mode="NEVER"
        )
        
        # 启动讨论
        user_proxy.initiate_chat(
            self.manager,
            message=f"让我们开始讨论以下主题：{topic}"
        )
        
        # 返回讨论记录
        return self.group_chat.messages
    
    def continue_discussion(self, follow_up: str) -> list:
        """
        继续讨论
        :param follow_up: 后续问题或指令
        :return: 讨论记录
        """
        # 创建用户代理
        user_proxy = UserProxyAgent(
            name="用户",
            system_message="你是讨论的参与者，提出后续问题或指令",
            llm_config=agent_config,
            human_input_mode="NEVER"
        )
        
        # 继续讨论
        user_proxy.send(
            follow_up,
            self.manager
        )
        
        # 返回讨论记录
        return self.group_chat.messages
    
    def get_discussion_summary(self) -> str:
        """
        获取讨论总结
        :return: 讨论总结
        """
        # 创建总结代理
        summary_agent = AssistantAgent(
            name="总结者",
            system_message="你是一个总结者，负责总结讨论内容",
            llm_config=agent_config
        )
        
        # 生成总结
        messages = [
            {
                "role": "user",
                "content": f"请总结以下讨论内容：\n\n{'\n'.join([f'{msg["name"]}: {msg["content"]}' for msg in self.group_chat.messages])}"
            }
        ]
        
        summary = self.llm_provider.generate_text(messages)
        return summary


# 为了兼容现有代码，添加一个简单的agent配置
agent_config = {
    "llm_config": {
        "temperature": 0.7,
        "max_tokens": 1000,
    }
}
