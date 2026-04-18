from app.workflow.caption_workflow import CaptionWorkflow
import os


class CaptionGenerator:
    """字幕生成服务"""
    
    def __init__(self, provider_name: str = "openai"):
        self.workflow = CaptionWorkflow(provider_name)
    
    def generate_caption(self, video_path: str, platform: str, product_manual: str = None) -> str:
        """
        生成视频字幕
        :param video_path: 视频文件路径
        :param platform: 发布平台
        :param product_manual: 产品说明书内容
        :return: 生成的字幕文件内容
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"视频文件不存在: {video_path}")
        
        return self.workflow.run(video_path, platform, product_manual)
