from app.providers.llm_providers import LLMProviderFactory
from typing import Dict, Any


class DeepResearch:
    """Deep Research服务"""
    
    def __init__(self, provider_name: str = "openai"):
        self.llm_provider = LLMProviderFactory.get_provider(provider_name)
    
    def research_market(self, product: str, target_market: str) -> Dict[str, Any]:
        """
        进行市场调研
        :param product: 产品名称
        :param target_market: 目标市场
        :return: 调研结果
        """
        # 1. 市场趋势分析
        market_trends = self._analyze_market_trends(product, target_market)
        
        # 2. 竞品分析
        competitor_analysis = self._analyze_competitors(product, target_market)
        
        # 3. 出海策略建议
        strategy_suggestions = self._generate_strategy_suggestions(product, target_market, market_trends, competitor_analysis)
        
        return {
            "market_trends": market_trends,
            "competitor_analysis": competitor_analysis,
            "strategy_suggestions": strategy_suggestions
        }
    
    def _analyze_market_trends(self, product: str, target_market: str) -> str:
        """
        分析市场趋势
        :param product: 产品名称
        :param target_market: 目标市场
        :return: 市场趋势分析结果
        """
        prompt = f"请分析{target_market}市场中{product}的最新市场趋势，包括市场规模、增长速度、消费者偏好变化等。"
        return self.llm_provider.generate_text(prompt)
    
    def _analyze_competitors(self, product: str, target_market: str) -> str:
        """
        分析竞品
        :param product: 产品名称
        :param target_market: 目标市场
        :return: 竞品分析结果
        """
        prompt = f"请分析{target_market}市场中{product}的主要竞争对手，包括他们的产品特点、价格策略、市场份额和优势劣势。"
        return self.llm_provider.generate_text(prompt)
    
    def _generate_strategy_suggestions(self, product: str, target_market: str, market_trends: str, competitor_analysis: str) -> str:
        """
        生成出海策略建议
        :param product: 产品名称
        :param target_market: 目标市场
        :param market_trends: 市场趋势分析
        :param competitor_analysis: 竞品分析
        :return: 策略建议
        """
        prompt = f"基于以下市场趋势和竞品分析，请为{product}进入{target_market}市场提供详细的出海策略建议，包括定价策略、营销渠道、差异化竞争优势等。\n\n市场趋势：\n{market_trends}\n\n竞品分析：\n{competitor_analysis}"
        return self.llm_provider.generate_text(prompt)
