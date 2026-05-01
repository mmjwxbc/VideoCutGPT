from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    # API Keys
    openai_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    glm_api_key: Optional[str] = None
    deepseek_api_key: Optional[str] = None
    multimodal_api_key: Optional[str] = None
    
    # Model Configurations
    default_llm_model: str = "gpt-4o"
    default_multimodal_model: str = "gpt-4o"
    glm_vision_model: str = "glm-4.6v"
    deepseek_chat_model: str = "deepseek-chat"
    glm_base_url: str = "https://open.bigmodel.cn/api/paas/v4/"
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    glm_enable_thinking: bool = True
    multimodal_provider: str = "glm"
    multimodal_model: Optional[str] = None
    multimodal_base_url: Optional[str] = None
    multimodal_enable_thinking: Optional[bool] = None
    glm_request_timeout_seconds: int = 120
    keyframe_interval_seconds: int = 3
    max_keyframes: int = 8
    keyframe_scene_threshold: float = 30.0
    agent_max_steps: int = 6
    
    # Server Config
    host: str = "0.0.0.0"
    port: int = 8000
    
    # File Upload Config
    upload_dir: str = "./uploads"
    max_upload_size: int = 50000000
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()

if settings.multimodal_model is None:
    settings.multimodal_model = settings.glm_vision_model
if settings.multimodal_base_url is None:
    settings.multimodal_base_url = settings.glm_base_url
if settings.multimodal_api_key is None:
    settings.multimodal_api_key = settings.glm_api_key
if settings.multimodal_enable_thinking is None:
    settings.multimodal_enable_thinking = settings.glm_enable_thinking

# Create upload directory if it doesn't exist
if not os.path.exists(settings.upload_dir):
    os.makedirs(settings.upload_dir)
