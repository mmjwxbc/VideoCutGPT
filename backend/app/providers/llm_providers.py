from abc import ABC, abstractmethod
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from app.core.config import settings


class LLMProvider(ABC):
    """LLM提供商抽象基类"""
    
    @abstractmethod
    def generate_text(self, prompt: str) -> str:
        """生成文本"""
        pass
    
    @abstractmethod
    def analyze_image(self, image_base64: str, prompt: str) -> str:
        """分析图像"""
        pass


class OpenAIProvider(LLMProvider):
    """OpenAI提供商"""
    
    def __init__(self):
        self.client = ChatOpenAI(
            model=settings.default_llm_model,
            api_key=settings.openai_api_key
        )
    
    def generate_text(self, prompt: str) -> str:
        response = self.client.invoke(prompt)
        return response.content
    
    def analyze_image(self, image_base64: str, prompt: str) -> str:
        message = HumanMessage(
            content=[
                {
                    "type": "text",
                    "text": prompt
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image_base64}"
                    }
                }
            ]
        )
        response = self.client.invoke([message])
        return response.content


class LLMProviderFactory:
    """LLM提供商工厂"""
    
    @staticmethod
    def get_provider(provider_name: str = "openai") -> LLMProvider:
        """
        获取LLM提供商实例
        :param provider_name: 提供商名称
        :return: LLMProvider实例
        """
        if provider_name.lower() == "openai":
            return OpenAIProvider()
        else:
            raise ValueError(f"不支持的LLM提供商: {provider_name}")
