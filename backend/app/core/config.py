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
    agent_max_steps: int = 12
    
    # Server Config
    host: str = "0.0.0.0"
    port: int = 8000

    # Cloudflare Access
    cloudflare_access_enabled: bool = False
    dev_access_user_id: str = "local-dev-user"
    dev_access_user_email: str = "local-dev@example.com"
    dev_access_user_name: str = "Local Dev"

    # File Upload Config
    upload_dir: str = "./uploads"
    export_dir: str = "./exports"
    session_store_dir: str = "./data/caption_sessions"
    max_upload_size: int = 1024 * 1024 * 1024
    upload_chunk_size: int = 512 * 1024
    ffmpeg_execution_timeout_seconds: int = 600

    # Backblaze B2 Config
    b2_authorize_url: str = "https://api.backblazeb2.com/b2api/v4/b2_authorize_account"
    b2_key_id: Optional[str] = None
    b2_application_key: Optional[str] = None
    b2_bucket_id: Optional[str] = None
    
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
if not os.path.exists(settings.export_dir):
    os.makedirs(settings.export_dir)
if not os.path.exists(settings.session_store_dir):
    os.makedirs(settings.session_store_dir)
