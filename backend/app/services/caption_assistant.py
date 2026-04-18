from __future__ import annotations

import asyncio
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from threading import Lock
from typing import Any, AsyncIterator, Dict, List, Optional
from uuid import uuid4

import httpx
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.core.utils import extract_keyframes, select_keyframes_for_analysis


def _utcnow() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


@dataclass
class ConversationMessage:
    role: str
    content: str
    created_at: str = field(default_factory=_utcnow)


@dataclass
class CaptionSession:
    session_id: str
    video_path: str
    platform: str
    product_manual: str
    messages: List[ConversationMessage] = field(default_factory=list)
    keyframes: List[Dict[str, Any]] = field(default_factory=list)
    frame_analyses: List[str] = field(default_factory=list)
    video_summary: str = ""
    execution_plan: List[str] = field(default_factory=list)
    subtitle_draft: str = ""
    editing_plan: str = ""
    english_title: str = ""
    tags: List[str] = field(default_factory=list)
    status: str = "idle"
    progress_message: str = ""
    error_message: str = ""
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)


class CaptionSessionStore:
    def __init__(self) -> None:
        self._sessions: Dict[str, CaptionSession] = {}
        self._lock = Lock()

    def save(self, session: CaptionSession) -> None:
        with self._lock:
            self._sessions[session.session_id] = session

    def get(self, session_id: str) -> CaptionSession:
        with self._lock:
            if session_id not in self._sessions:
                raise KeyError(f"session '{session_id}' not found")
            return self._sessions[session_id]


class CaptionEventBroker:
    def __init__(self) -> None:
        self._subscribers: Dict[str, List[asyncio.Queue[Dict[str, Any]]]] = {}
        self._lock = Lock()

    def subscribe(self, session_id: str) -> asyncio.Queue[Dict[str, Any]]:
        queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        with self._lock:
            self._subscribers.setdefault(session_id, []).append(queue)
        return queue

    def unsubscribe(self, session_id: str, queue: asyncio.Queue[Dict[str, Any]]) -> None:
        with self._lock:
            queues = self._subscribers.get(session_id, [])
            self._subscribers[session_id] = [item for item in queues if item is not queue]
            if not self._subscribers[session_id]:
                self._subscribers.pop(session_id, None)

    def publish(self, session_id: str, event: str, payload: Dict[str, Any]) -> None:
        with self._lock:
            queues = list(self._subscribers.get(session_id, []))
        message = {"event": event, "data": payload}
        for queue in queues:
            queue.put_nowait(message)


class CaptionConversationAssistant:
    def __init__(self) -> None:
        self.store = CaptionSessionStore()
        self.events = CaptionEventBroker()
        self._agent_llm: Optional[ChatOpenAI] = None
        self._http_client: Optional[httpx.AsyncClient] = None
        self._session_locks: Dict[str, asyncio.Lock] = {}
        self._completion_events: Dict[str, asyncio.Event] = {}
        self._meta_lock = Lock()

    async def create_session(
        self,
        video_path: str,
        platform: str,
        product_manual: Optional[str],
        user_prompt: str,
    ) -> Dict[str, Any]:
        session = CaptionSession(
            session_id=str(uuid4()),
            video_path=video_path,
            platform=platform,
            product_manual=product_manual or "",
            status="queued",
            progress_message="任务已创建，等待开始。",
        )
        session.messages.append(ConversationMessage(role="user", content=user_prompt))
        self.store.save(session)
        self._ensure_session_primitives(session.session_id)
        self._publish_snapshot(session, "session_created")
        asyncio.create_task(self._process_initial_session(session.session_id, user_prompt))
        return self._serialize(session)

    async def continue_session(self, session_id: str, user_prompt: str) -> Dict[str, Any]:
        session = self.store.get(session_id)
        if session.status == "processing":
            raise ValueError("session is still processing")

        session.messages.append(ConversationMessage(role="user", content=user_prompt))
        session.status = "queued"
        session.progress_message = "已收到修改要求，等待开始。"
        session.error_message = ""
        session.updated_at = _utcnow()
        self.store.save(session)
        self._ensure_session_primitives(session_id)
        self._publish_snapshot(session, "message_queued")
        asyncio.create_task(self._process_followup_session(session_id, user_prompt))
        return self._serialize(session)

    def get_session(self, session_id: str) -> Dict[str, Any]:
        return self._serialize(self.store.get(session_id))

    async def wait_for_completion(self, session_id: str) -> Dict[str, Any]:
        event = self._ensure_completion_event(session_id)
        await event.wait()
        return self.get_session(session_id)

    async def stream_session_events(self, session_id: str) -> AsyncIterator[Dict[str, Any]]:
        session = self.store.get(session_id)
        queue = self.events.subscribe(session_id)
        try:
            yield {"event": "snapshot", "data": self._serialize(session)}
            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=15)
                    yield message
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": {"session_id": session_id, "ts": _utcnow()}}
        finally:
            self.events.unsubscribe(session_id, queue)

    def _ensure_session_primitives(self, session_id: str) -> None:
        with self._meta_lock:
            self._session_locks.setdefault(session_id, asyncio.Lock())
            self._completion_events[session_id] = asyncio.Event()

    def _ensure_completion_event(self, session_id: str) -> asyncio.Event:
        with self._meta_lock:
            return self._completion_events.setdefault(session_id, asyncio.Event())

    def _get_session_lock(self, session_id: str) -> asyncio.Lock:
        with self._meta_lock:
            return self._session_locks.setdefault(session_id, asyncio.Lock())

    async def _process_initial_session(self, session_id: str, user_prompt: str) -> None:
        async with self._get_session_lock(session_id):
            try:
                session = self.store.get(session_id)
                await self._set_progress(session, "processing", "正在提取关键帧...")
                session.keyframes = await asyncio.to_thread(
                    extract_keyframes,
                    session.video_path,
                    settings.keyframe_interval_seconds,
                    None,
                    settings.keyframe_scene_threshold,
                )
                session.updated_at = _utcnow()
                self.store.save(session)
                self._publish_snapshot(session)

                await self._set_progress(session, "processing", "正在分析关键帧内容...")
                session.frame_analyses = await self._analyze_video_frames(session)
                session.updated_at = _utcnow()
                self.store.save(session)
                self._publish_snapshot(session)

                await self._set_progress(session, "processing", "正在总结视频内容...")
                session.video_summary = await self._summarize_video(session)
                session.updated_at = _utcnow()
                self.store.save(session)
                self._publish_snapshot(session)

                await self._set_progress(session, "processing", "正在生成字幕和剪辑方案...")
                await self._run_turn(session, user_prompt)

                session.status = "completed"
                session.progress_message = "处理完成。"
                session.updated_at = _utcnow()
                self.store.save(session)
                self._publish_snapshot(session, "completed")
                self._ensure_completion_event(session_id).set()
            except Exception as exc:
                await self._fail_session(session_id, exc)

    async def _process_followup_session(self, session_id: str, user_prompt: str) -> None:
        async with self._get_session_lock(session_id):
            try:
                session = self.store.get(session_id)
                await self._set_progress(session, "processing", "正在根据你的新要求改稿...")
                await self._run_turn(session, user_prompt)
                session.status = "completed"
                session.progress_message = "本轮修改完成。"
                session.updated_at = _utcnow()
                self.store.save(session)
                self._publish_snapshot(session, "completed")
                self._ensure_completion_event(session_id).set()
            except Exception as exc:
                await self._fail_session(session_id, exc)

    async def _fail_session(self, session_id: str, exc: Exception) -> None:
        session = self.store.get(session_id)
        session.status = "error"
        session.error_message = str(exc)
        session.progress_message = "处理失败。"
        session.updated_at = _utcnow()
        self.store.save(session)
        self._publish_snapshot(session, "error")
        self._ensure_completion_event(session_id).set()

    async def _set_progress(self, session: CaptionSession, status: str, message: str) -> None:
        session.status = status
        session.progress_message = message
        session.error_message = ""
        session.updated_at = _utcnow()
        self.store.save(session)
        self.events.publish(
            session.session_id,
            "progress",
            {
                "session_id": session.session_id,
                "status": status,
                "message": message,
                "updated_at": session.updated_at,
            },
        )

    def _publish_snapshot(self, session: CaptionSession, event: str = "snapshot") -> None:
        self.events.publish(session.session_id, event, self._serialize(session))

    def _get_agent_llm(self) -> ChatOpenAI:
        if self._agent_llm is None:
            if not settings.deepseek_api_key:
                raise ValueError("DEEPSEEK_API_KEY is not configured")
            self._agent_llm = ChatOpenAI(
                model=settings.deepseek_chat_model,
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
                temperature=0.2,
            )
        return self._agent_llm

    def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=settings.glm_request_timeout_seconds,
            )
        return self._http_client

    async def _llm_invoke(self, messages: List[Any]) -> Any:
        return await asyncio.to_thread(self._get_agent_llm().invoke, messages)

    async def _run_turn(self, session: CaptionSession, user_prompt: str) -> None:
        targets = await self._determine_update_targets(session, user_prompt)
        if not targets["is_supported_request"]:
            session.execution_plan = [
                "识别当前请求不属于当前会话支持的视频创意产出范围",
                "明确当前会话可处理的能力边界",
                "引导用户提供字幕、剪辑、标题或标签需求",
            ]
            session.messages.append(
                ConversationMessage(
                    role="assistant",
                    content=self._compose_scope_guard_reply(user_prompt, targets),
                )
            )
            session.updated_at = _utcnow()
            self.store.save(session)
            self._publish_snapshot(session)
            return

        session.execution_plan = await self._build_plan(session, user_prompt, targets)
        self.store.save(session)
        self._publish_snapshot(session)

        scratchpad = await self._run_react_loop(session, user_prompt, targets)
        if targets["update_subtitles"] and not session.subtitle_draft:
            session.subtitle_draft = await self._generate_subtitle_draft(session, "补全初始字幕草稿。")
        if targets["update_editing_plan"] and not session.editing_plan:
            session.editing_plan = await self._generate_editing_plan(session, "补全初始剪辑方案。")
        if targets["update_title"] and not session.english_title:
            session.english_title = await self._generate_english_title(session, "补全英文标题。")
        if targets["update_tags"] and not session.tags:
            session.tags = await self._generate_tags(session, "补全标签。")
        session.messages.append(
            ConversationMessage(
                role="assistant",
                content=await self._compose_assistant_reply(
                    session,
                    user_prompt,
                    scratchpad,
                    targets,
                ),
            )
        )
        session.updated_at = _utcnow()
        self.store.save(session)
        self._publish_snapshot(session)

    async def _analyze_video_frames(self, session: CaptionSession) -> List[str]:
        analysis_frames = select_keyframes_for_analysis(
            session.keyframes,
            max_frames=settings.max_keyframes,
        )
        analyses: List[str] = []
        total = len(analysis_frames)
        for index, keyframe in enumerate(analysis_frames, start=1):
            await self._set_progress(
                session,
                "processing",
                f"正在分析关键帧 {index}/{max(total, 1)}...",
            )
            frame_base64 = str(keyframe.get("image_base64", ""))
            timestamp = keyframe.get("timestamp_seconds")
            source = keyframe.get("source", "unknown")
            analysis = await self._analyze_single_frame(index, frame_base64)
            analyses.append(
                f"关键帧{index}（{timestamp}s, 来源: {source}）: {analysis}"
            )
            session.frame_analyses = analyses.copy()
            session.updated_at = _utcnow()
            self.store.save(session)
            self._publish_snapshot(session)
        return analyses

    async def _analyze_single_frame(self, frame_index: int, frame_base64: str) -> str:
        if not settings.glm_api_key:
            raise ValueError("GLM_API_KEY is not configured")

        prompt = (
            f"你正在分析短视频的第{frame_index}个关键帧。"
            "请把图像内容转成后续可供文案与剪辑模型消费的中文文本。"
            "\n请严格覆盖这些维度："
            "\n1. 画面主体、场景、拍摄景别与构图"
            "\n2. 产品出现方式、人物动作、使用步骤或演示细节"
            "\n3. 能识别到的字幕、贴纸、包装、品牌、价格、参数、口播线索"
            "\n4. 这一帧对短视频结构的作用：开场钩子 / 痛点引入 / 卖点展示 / 证明背书 / CTA / 转场"
            "\n5. 对字幕生成和剪辑节奏有帮助的补充判断"
            "\n输出要求：只输出简洁中文文本，不要 JSON，不要坐标，不要解释推理过程。"
        )

        payload: Dict[str, Any] = {
            "model": settings.glm_vision_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{frame_base64}"
                            },
                        },
                        {
                            "type": "text",
                            "text": prompt,
                        },
                    ],
                }
            ],
        }
        if settings.glm_enable_thinking:
            payload["thinking"] = {"type": "enabled"}

        response = await self._get_http_client().post(
            f"{settings.glm_base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.glm_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        return self._extract_glm_content(data)

    def _extract_glm_content(self, response_data: Dict[str, Any]) -> str:
        choices = response_data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ValueError("GLM response does not contain choices")

        message = choices[0].get("message", {})
        content = message.get("content", "")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            text_parts: List[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(str(item.get("text", "")).strip())
                elif isinstance(item, str):
                    text_parts.append(item.strip())
            merged = "\n".join(part for part in text_parts if part)
            if merged:
                return merged
        return str(content).strip()

    async def _summarize_video(self, session: CaptionSession) -> str:
        prompt = (
            "你是视频理解助手。请根据关键帧分析和说明书，总结视频的核心内容、产品卖点、"
            "适合的人群、镜头节奏，以及适合做字幕和剪辑决策的信息。"
            f"\n\n平台：{session.platform}"
            f"\n\n说明书：\n{session.product_manual or '无说明书'}"
            f"\n\n关键帧分析：\n" + "\n".join(session.frame_analyses)
        )
        response = await self._llm_invoke(
            [SystemMessage(content="请输出结构化但简洁的中文摘要。"), HumanMessage(content=prompt)]
        )
        return str(response.content)

    async def _determine_update_targets(
        self,
        session: CaptionSession,
        user_prompt: str,
    ) -> Dict[str, Any]:
        if not session.subtitle_draft and not session.editing_plan:
            return {
                "update_subtitles": True,
                "update_editing_plan": True,
                "update_title": False,
                "update_tags": False,
                "is_supported_request": True,
                "reason": "首轮任务需要同时产出字幕和剪辑方案。",
            }

        prompt = (
            "你是短视频制作任务分流器。请判断用户本轮需求需要更新哪些产物。"
            "\n产物只有两个：subtitle_draft 和 editing_plan。"
            "\n判断规则："
            "\n1. 如果用户明确要求改字幕、翻译字幕、改口播、改文案、改标题文案，update_subtitles=true。"
            "\n2. 如果用户明确要求改镜头、节奏、时长、转场、分镜、脚本结构、剪辑方案，update_editing_plan=true。"
            "\n3. 如果用户明确要求英文标题、广告标题、headline、title，update_title=true。"
            "\n4. 如果用户明确要求标签、hashtags、tag、话题标签，update_tags=true。"
            "\n5. 如果用户要求同时改内容表达和镜头结构，则字幕和剪辑都设为 true。"
            "\n6. 如果用户在讨论 agent 能力、前端页面、UI、系统 bug 等系统需求，而不是要视频创意产出，则四个更新项都设为 false。"
            "\n7. 如果用户意图模糊，但改动可能影响字幕与剪辑配合，也可以两个都设为 true。"
            "\n8. 只返回 JSON，格式为 "
            '{"update_subtitles": true, "update_editing_plan": false, "update_title": false, "update_tags": false, "reason": "..."}'
            f"\n\n用户需求：{user_prompt}"
            f"\n当前字幕草稿是否存在：{'是' if session.subtitle_draft else '否'}"
            f"\n当前剪辑方案是否存在：{'是' if session.editing_plan else '否'}"
            f"\n当前字幕草稿摘要：{session.subtitle_draft[:800] if session.subtitle_draft else '无'}"
            f"\n当前剪辑方案摘要：{session.editing_plan[:800] if session.editing_plan else '无'}"
        )
        raw = (await self._llm_invoke([HumanMessage(content=prompt)])).content
        parsed = self._parse_json_object(str(raw))
        if isinstance(parsed, dict):
            update_subtitles = bool(parsed.get("update_subtitles"))
            update_editing_plan = bool(parsed.get("update_editing_plan"))
            update_title = bool(parsed.get("update_title"))
            update_tags = bool(parsed.get("update_tags"))
            if update_subtitles or update_editing_plan or update_title or update_tags:
                return {
                    "update_subtitles": update_subtitles,
                    "update_editing_plan": update_editing_plan,
                    "update_title": update_title,
                    "update_tags": update_tags,
                    "is_supported_request": True,
                    "reason": str(parsed.get("reason", "")).strip() or "根据用户需求自动判断。",
                }

        normalized_prompt = user_prompt.lower()
        subtitle_keywords = [
            "字幕",
            "文案",
            "口播",
            "翻译",
            "标题",
            "台词",
            "语气",
            "英文",
            "中文",
        ]
        editing_keywords = [
            "剪辑",
            "镜头",
            "转场",
            "节奏",
            "分镜",
            "时长",
            "结构",
            "hook",
            "钩子",
            "cta",
        ]
        title_keywords = ["英文标题", "headline", "title", "英文题目"]
        tag_keywords = ["tag", "tags", "标签", "hashtags", "hashtag", "话题"]
        unsupported_keywords = [
            "agent",
            "前端",
            "frontend",
            "ui",
            "页面",
            "界面",
            "展示",
            "滑动",
            "滚动",
            "bug",
            "问题",
            "历史记录",
            "时间",
            "header",
            "sidebar",
            "工作区",
        ]
        update_subtitles = any(keyword in normalized_prompt for keyword in subtitle_keywords)
        update_editing_plan = any(keyword in normalized_prompt for keyword in editing_keywords)
        update_title = any(keyword in normalized_prompt for keyword in title_keywords)
        update_tags = any(keyword in normalized_prompt for keyword in tag_keywords)
        is_unsupported_request = (
            any(keyword in normalized_prompt for keyword in unsupported_keywords)
            and not update_subtitles
            and not update_editing_plan
            and not update_title
            and not update_tags
        )
        if is_unsupported_request:
            return {
                "update_subtitles": False,
                "update_editing_plan": False,
                "update_title": False,
                "update_tags": False,
                "is_supported_request": False,
                "reason": "当前输入更像系统、产品或界面需求，不属于字幕或剪辑修改指令。",
            }
        if not update_subtitles and not update_editing_plan and not update_title and not update_tags:
            update_subtitles = True
            update_editing_plan = True
        return {
            "update_subtitles": update_subtitles,
            "update_editing_plan": update_editing_plan,
            "update_title": update_title,
            "update_tags": update_tags,
            "is_supported_request": True,
            "reason": "基于关键词回退判断本轮需要更新的产物。",
        }

    async def _build_plan(
        self,
        session: CaptionSession,
        user_prompt: str,
        targets: Dict[str, Any],
    ) -> List[str]:
        prompt = (
            "你是视频制作任务规划器。请根据用户需求、当前视频理解和已有产出，"
            "给出本轮最合理的 3 到 5 个执行步骤。"
            "\n只返回 JSON，格式为 {\"goal\": \"...\", \"steps\": [\"...\", \"...\"]}。"
            f"\n\n用户需求：{user_prompt}"
            f"\n本轮更新范围："
            f"\n- 是否更新字幕草稿：{'是' if targets['update_subtitles'] else '否'}"
            f"\n- 是否更新剪辑方案：{'是' if targets['update_editing_plan'] else '否'}"
            f"\n- 判断原因：{targets['reason']}"
            f"\n\n视频摘要：{session.video_summary}"
            f"\n\n当前字幕草稿：{session.subtitle_draft or '无'}"
            f"\n\n当前剪辑方案：{session.editing_plan or '无'}"
        )
        raw = (await self._llm_invoke([HumanMessage(content=prompt)])).content
        parsed = self._parse_json_object(str(raw))
        steps = parsed.get("steps") if isinstance(parsed, dict) else None
        if isinstance(steps, list) and steps:
            return [str(step) for step in steps[:5]]
        fallback_steps = [
            "理解用户本轮修改目标",
            "读取视频与说明书上下文",
        ]
        if targets["update_subtitles"]:
            fallback_steps.append("更新字幕草稿")
        if targets["update_editing_plan"]:
            fallback_steps.append("更新剪辑执行方案")
        if targets["update_title"]:
            fallback_steps.append("生成或更新英文标题")
        if targets["update_tags"]:
            fallback_steps.append("生成或更新标签")
        fallback_steps.append("整理最终结果并直接回复用户")
        return fallback_steps

    async def _run_react_loop(
        self,
        session: CaptionSession,
        user_prompt: str,
        targets: Dict[str, Any],
    ) -> List[Dict[str, str]]:
        scratchpad: List[Dict[str, str]] = []
        subtitles_written = False
        editing_written = False
        title_written = False
        tags_written = False
        for _ in range(settings.agent_max_steps):
            decision = await self._next_react_action(session, user_prompt, scratchpad, targets)
            action = decision.get("action", "finalize")
            action_input = decision.get("action_input", "")
            thought = decision.get("thought", "")

            if action == "read_video_context":
                observation = self._tool_read_video_context(session)
            elif action == "read_manual":
                observation = self._tool_read_manual(session)
            elif action == "read_current_artifacts":
                observation = self._tool_read_current_artifacts(session)
            elif action == "write_subtitles":
                observation = await self._tool_write_subtitles(session, user_prompt, action_input)
                subtitles_written = True
            elif action == "write_edit_plan":
                observation = await self._tool_write_edit_plan(session, user_prompt, action_input)
                editing_written = True
            elif action == "write_title":
                observation = await self._tool_write_title(session, user_prompt, action_input)
                title_written = True
            elif action == "write_tags":
                observation = await self._tool_write_tags(session, user_prompt, action_input)
                tags_written = True
            else:
                break

            scratchpad.append(
                {
                    "thought": thought,
                    "action": action,
                    "observation": observation,
                }
            )

            subtitles_ready = (not targets["update_subtitles"]) or subtitles_written
            editing_ready = (not targets["update_editing_plan"]) or editing_written
            title_ready = (not targets["update_title"]) or title_written
            tags_ready = (not targets["update_tags"]) or tags_written
            if subtitles_ready and editing_ready and title_ready and tags_ready and len(scratchpad) >= 1:
                break

        return scratchpad

    async def _next_react_action(
        self,
        session: CaptionSession,
        user_prompt: str,
        scratchpad: List[Dict[str, str]],
        targets: Dict[str, Any],
    ) -> Dict[str, str]:
        prompt = (
            "你是一个采用 ReAct 风格的字幕与剪辑助手。你可以使用以下工具："
            "\n1. read_video_context: 读取视频关键帧和摘要"
            "\n2. read_manual: 读取说明书"
            "\n3. read_current_artifacts: 读取当前字幕、剪辑方案、标题和标签"
            "\n4. write_subtitles: 更新字幕草稿"
            "\n5. write_edit_plan: 更新剪辑方案"
            "\n6. write_title: 更新英文标题"
            "\n7. write_tags: 更新标签"
            "\n8. finalize: 结束工具调用"
            "\n\n请只返回 JSON，格式为 "
            "{\"thought\": \"...\", \"action\": \"...\", \"action_input\": \"...\"}。"
            f"\n\n用户需求：{user_prompt}"
            f"\n本轮更新范围："
            f"\n- update_subtitles={'true' if targets['update_subtitles'] else 'false'}"
            f"\n- update_editing_plan={'true' if targets['update_editing_plan'] else 'false'}"
            f"\n- update_title={'true' if targets['update_title'] else 'false'}"
            f"\n- update_tags={'true' if targets['update_tags'] else 'false'}"
            f"\n- reason={targets['reason']}"
            "\n注意：不要调用不需要的写入工具。"
            f"\n执行计划：{json.dumps(session.execution_plan, ensure_ascii=False)}"
            f"\n已有观察：{json.dumps(scratchpad, ensure_ascii=False)}"
            f"\n当前是否已有字幕草稿：{'是' if session.subtitle_draft else '否'}"
            f"\n当前是否已有剪辑方案：{'是' if session.editing_plan else '否'}"
        )
        raw = (await self._llm_invoke([HumanMessage(content=prompt)])).content
        parsed = self._parse_json_object(str(raw))
        if isinstance(parsed, dict) and parsed.get("action"):
            return {key: str(value) for key, value in parsed.items()}

        if targets["update_subtitles"] and not any(
            item.get("action") == "write_subtitles" for item in scratchpad
        ):
            return {"thought": "需要先产出字幕。", "action": "write_subtitles", "action_input": user_prompt}
        if targets["update_editing_plan"] and not any(
            item.get("action") == "write_edit_plan" for item in scratchpad
        ):
            return {"thought": "还需要产出剪辑方案。", "action": "write_edit_plan", "action_input": user_prompt}
        if targets["update_title"] and not any(
            item.get("action") == "write_title" for item in scratchpad
        ):
            return {"thought": "还需要产出英文标题。", "action": "write_title", "action_input": user_prompt}
        if targets["update_tags"] and not any(
            item.get("action") == "write_tags" for item in scratchpad
        ):
            return {"thought": "还需要产出标签。", "action": "write_tags", "action_input": user_prompt}
        return {"thought": "本轮结果已经齐备。", "action": "finalize", "action_input": ""}

    def _tool_read_video_context(self, session: CaptionSession) -> str:
        return f"视频摘要：{session.video_summary}\n关键帧分析：\n" + "\n".join(session.frame_analyses)

    def _tool_read_manual(self, session: CaptionSession) -> str:
        return session.product_manual or "用户未提供说明书。"

    def _tool_read_current_artifacts(self, session: CaptionSession) -> str:
        return (
            f"当前字幕草稿：\n{session.subtitle_draft or '暂无'}\n\n"
            f"当前剪辑方案：\n{session.editing_plan or '暂无'}\n\n"
            f"当前英文标题：\n{session.english_title or '暂无'}\n\n"
            f"当前标签：\n{', '.join(session.tags) if session.tags else '暂无'}"
        )

    async def _tool_write_subtitles(self, session: CaptionSession, user_prompt: str, action_input: str) -> str:
        guidance = action_input or user_prompt
        session.subtitle_draft = await self._generate_subtitle_draft(session, guidance)
        session.updated_at = _utcnow()
        self.store.save(session)
        self._publish_snapshot(session)
        return "字幕草稿已更新。"

    async def _tool_write_edit_plan(self, session: CaptionSession, user_prompt: str, action_input: str) -> str:
        guidance = action_input or user_prompt
        session.editing_plan = await self._generate_editing_plan(session, guidance)
        session.updated_at = _utcnow()
        self.store.save(session)
        self._publish_snapshot(session)
        return "剪辑执行方案已更新。"

    async def _tool_write_title(self, session: CaptionSession, user_prompt: str, action_input: str) -> str:
        guidance = action_input or user_prompt
        session.english_title = await self._generate_english_title(session, guidance)
        session.updated_at = _utcnow()
        self.store.save(session)
        self._publish_snapshot(session)
        return "英文标题已更新。"

    async def _tool_write_tags(self, session: CaptionSession, user_prompt: str, action_input: str) -> str:
        guidance = action_input or user_prompt
        session.tags = await self._generate_tags(session, guidance)
        session.updated_at = _utcnow()
        self.store.save(session)
        self._publish_snapshot(session)
        return "标签已更新。"

    async def _generate_subtitle_draft(self, session: CaptionSession, guidance: str) -> str:
        prompt = (
            "你是资深短视频字幕导演。请根据以下信息生成或修改字幕草稿。"
            "\n要求："
            "\n1. 输出中文"
            "\n2. 尽量按时间轴分段，格式示例：00:00-00:03 字幕内容"
            "\n3. 体现产品卖点、镜头节奏和平台语气"
            "\n4. 如果用户要求修改，请在当前草稿基础上改写而不是完全忽略历史版本"
            f"\n\n用户需求：{guidance}"
            f"\n平台：{session.platform}"
            f"\n说明书：\n{session.product_manual or '无'}"
            f"\n视频摘要：\n{session.video_summary}"
            f"\n关键帧分析：\n" + "\n".join(session.frame_analyses)
            + f"\n\n当前字幕草稿：\n{session.subtitle_draft or '无'}"
        )
        response = await self._llm_invoke([HumanMessage(content=prompt)])
        return str(response.content)

    async def _generate_editing_plan(self, session: CaptionSession, guidance: str) -> str:
        prompt = (
            "你是短视频剪辑导演。请根据视频摘要、关键帧和用户需求输出一个可执行的剪辑方案。"
            "\n要求："
            "\n1. 按镜头或时间段列出"
            "\n2. 明确镜头目标、转场、字幕配合、B-roll 或特写建议"
            "\n3. 包含开场 hook、卖点推进、收尾 CTA"
            "\n4. 如果用户要求修改，请在当前方案上迭代"
            f"\n\n用户需求：{guidance}"
            f"\n平台：{session.platform}"
            f"\n说明书：\n{session.product_manual or '无'}"
            f"\n视频摘要：\n{session.video_summary}"
            f"\n关键帧分析：\n" + "\n".join(session.frame_analyses)
            + f"\n\n当前剪辑方案：\n{session.editing_plan or '无'}"
            + f"\n\n当前字幕草稿：\n{session.subtitle_draft or '无'}"
        )
        response = await self._llm_invoke([HumanMessage(content=prompt)])
        return str(response.content)

    async def _generate_english_title(self, session: CaptionSession, guidance: str) -> str:
        prompt = (
            "你是短视频投放创意策划。请生成或修改一个英文标题。"
            "\n要求："
            "\n1. 输出 1 条最优英文标题"
            "\n2. 适合短视频投放或素材命名"
            "\n3. 不要加引号，不要解释"
            f"\n\n用户需求：{guidance}"
            f"\n平台：{session.platform}"
            f"\n说明书：\n{session.product_manual or '无'}"
            f"\n视频摘要：\n{session.video_summary}"
            f"\n关键帧分析：\n" + "\n".join(session.frame_analyses)
            + f"\n\n当前英文标题：\n{session.english_title or '无'}"
        )
        response = await self._llm_invoke([HumanMessage(content=prompt)])
        return str(response.content).strip()

    async def _generate_tags(self, session: CaptionSession, guidance: str) -> List[str]:
        prompt = (
            "你是短视频投放创意策划。请生成或修改一组标签。"
            "\n要求："
            "\n1. 输出 JSON，格式为 {\"tags\": [\"tag1\", \"tag2\"]}"
            "\n2. 生成 5 到 8 个英文标签"
            "\n3. 不要带 #"
            f"\n\n用户需求：{guidance}"
            f"\n平台：{session.platform}"
            f"\n说明书：\n{session.product_manual or '无'}"
            f"\n视频摘要：\n{session.video_summary}"
            f"\n关键帧分析：\n" + "\n".join(session.frame_analyses)
            + f"\n\n当前标签：\n{', '.join(session.tags) if session.tags else '无'}"
        )
        response = await self._llm_invoke([HumanMessage(content=prompt)])
        parsed = self._parse_json_object(str(response.content))
        tags = parsed.get("tags") if isinstance(parsed, dict) else None
        if isinstance(tags, list) and tags:
            return [str(tag).strip().lstrip("#") for tag in tags if str(tag).strip()][:8]
        return []

    async def _compose_assistant_reply(
        self,
        session: CaptionSession,
        user_prompt: str,
        scratchpad: List[Dict[str, str]],
        targets: Dict[str, Any],
    ) -> str:
        prompt = (
            "你是一个视频创意对话助手。请直接把本轮可交付结果回复给用户，而不是只做项目总结。"
            "\n要求："
            "\n1. 根据用户需求，判断应该展示字幕草稿、剪辑方案，或两者都展示。"
            "\n2. 如果本轮只改了字幕，就重点给出更新后的字幕；不要长篇解释已完成事项。"
            "\n3. 如果本轮只改了剪辑方案，就重点给出更新后的剪辑方案。"
            "\n4. 如果本轮生成了英文标题，就直接给出英文标题。"
            "\n5. 如果本轮生成了标签，就直接给出标签列表。"
            "\n6. 如果多个产物都改了，按产物分段给出。"
            "\n7. 允许先用一句话概括改动重点，但主体必须是可直接使用的结果内容。"
            "\n8. 不要虚构未修改的部分。"
            f"\n\n用户需求：{user_prompt}"
            f"\n本轮更新范围："
            f"\n- 是否更新字幕草稿：{'是' if targets['update_subtitles'] else '否'}"
            f"\n- 是否更新剪辑方案：{'是' if targets['update_editing_plan'] else '否'}"
            f"\n- 是否更新英文标题：{'是' if targets['update_title'] else '否'}"
            f"\n- 是否更新标签：{'是' if targets['update_tags'] else '否'}"
            f"\n- 判断原因：{targets['reason']}"
            f"\n执行计划：{json.dumps(session.execution_plan, ensure_ascii=False)}"
            f"\n工具执行记录：{json.dumps(scratchpad, ensure_ascii=False)}"
            f"\n最新字幕草稿全文：{session.subtitle_draft[:6000] if session.subtitle_draft else '无'}"
            f"\n最新剪辑方案全文：{session.editing_plan[:6000] if session.editing_plan else '无'}"
            f"\n最新英文标题：{session.english_title or '无'}"
            f"\n最新标签：{json.dumps(session.tags, ensure_ascii=False)}"
        )
        response = await self._llm_invoke([HumanMessage(content=prompt)])
        return str(response.content)

    def _compose_scope_guard_reply(self, user_prompt: str, targets: Dict[str, Any]) -> str:
        return (
            "这条需求没有落在当前视频创意会话的可执行范围内。"
            "\n\n当前会话支持的交付有："
            "\n1. 字幕草稿修改"
            "\n2. 剪辑方案修改"
            "\n3. 英文标题"
            "\n4. 标签"
            f"\n\n本轮识别结果：{targets['reason']}"
            f"\n\n你的原始输入：{user_prompt}"
            "\n\n如果你要继续这个视频任务，请直接告诉我："
            "\n- 想怎么改字幕"
            "\n- 想怎么改镜头/节奏/时长/转场"
            "\n- 想要什么风格的英文标题"
            "\n- 想要什么方向的标签"
            "\n\n例如："
            "\n- 把字幕改成更口语化，前三秒钩子更强"
            "\n- 保留字幕内容，但把视频压缩到 20 秒并重做镜头节奏"
            "\n- 给我一个更像广告投放素材的英文标题"
            "\n- 给我 6 个适合 TikTok 的英文标签"
        )

    def _parse_json_object(self, text: str) -> Dict[str, Any]:
        text = text.strip()
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if not match:
                return {}
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return {}

    def _serialize(self, session: CaptionSession) -> Dict[str, Any]:
        return {
            "session_id": session.session_id,
            "platform": session.platform,
            "keyframes": session.keyframes,
            "video_summary": session.video_summary,
            "frame_analyses": session.frame_analyses,
            "execution_plan": session.execution_plan,
            "subtitle_draft": session.subtitle_draft,
            "editing_plan": session.editing_plan,
            "english_title": session.english_title,
            "tags": session.tags,
            "messages": [asdict(message) for message in session.messages],
            "status": session.status,
            "progress_message": session.progress_message,
            "error_message": session.error_message,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
        }
