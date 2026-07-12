import json
import logging
import requests
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from django.shortcuts import get_object_or_404

from ..models import Chat, Message
from ..serializers import ChatSerializer, MessageSerializer
from ..utils import ApiResponse, get_pagination_params
from .ai_views import (
    _build_user_context,
    _strip_json_fences,
    _execute_crud,
    SYSTEM_PROMPT_TEMPLATE,
    GROQ_API_KEY,
    GROQ_MODEL,
    GROQ_API_URL,
    GROQ_TEMPERATURE,
    GROQ_MAX_TOKENS,
    CRUD_INTENTS,
)

logger = logging.getLogger(__name__)


class ChatListCreateView(APIView):
    """
    GET /api/chats/ - List all chats for current user
    POST /api/chats/ - Create a new chat
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        page, limit = get_pagination_params(request.query_params)

        chats = Chat.objects.filter(user=request.user).order_by('-updated_at')
        total = chats.count()
        offset = (page - 1) * limit
        paginated = chats[offset:offset + limit]

        serializer = ChatSerializer(paginated, many=True)
        return ApiResponse.paginated(serializer.data, page, limit, total, message="Chats retrieved successfully")

    def post(self, request):
        chat = Chat.objects.create(user=request.user, title="New Chat")
        serializer = ChatSerializer(chat)
        return ApiResponse.success(data=serializer.data, status_code=201, message="Chat created successfully")


class ChatDetailView(APIView):
    """
    GET /api/chats/<id>/ - Retrieve chat details with messages
    PATCH /api/chats/<id>/ - Rename chat
    DELETE /api/chats/<id>/ - Delete chat
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        chat = get_object_or_404(Chat, id=pk, user=request.user)
        serializer = ChatSerializer(chat)
        return ApiResponse.success(data=serializer.data, message="Chat details retrieved")

    def patch(self, request, pk):
        chat = get_object_or_404(Chat, id=pk, user=request.user)
        title = request.data.get('title', '').strip()
        if not title:
            return ApiResponse.error("Title cannot be empty", 400)
        
        chat.title = title
        chat.save()
        serializer = ChatSerializer(chat)
        return ApiResponse.success(data=serializer.data, message="Chat renamed successfully")

    def delete(self, request, pk):
        chat = get_object_or_404(Chat, id=pk, user=request.user)
        chat.delete()
        return ApiResponse.success(message="Chat deleted successfully")


class MessageListCreateView(APIView):
    """
    GET /api/chats/<chat_id>/messages/ - Retrieve messages for chat
    POST /api/chats/<chat_id>/messages/ - Send message in chat & get AI response
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get(self, request, chat_pk):
        chat = get_object_or_404(Chat, id=chat_pk, user=request.user)
        page, limit = get_pagination_params(request.query_params)

        messages = Message.objects.filter(chat=chat).order_by('-created_at')
        total = messages.count()
        offset = (page - 1) * limit
        paginated = list(messages[offset:offset + limit])
        paginated.reverse()

        serializer = MessageSerializer(paginated, many=True)
        return ApiResponse.paginated(serializer.data, page, limit, total, message="Messages retrieved")

    def post(self, request, chat_pk):
        chat = get_object_or_404(Chat, id=chat_pk, user=request.user)
        
        # ── 1. Validate inputs ────────────────────────────────────────
        text       = request.data.get("text", "").strip()
        audio_file = request.FILES.get("audio")
        image_file = request.FILES.get("image")

        if not text and not audio_file and not image_file:
            return ApiResponse.error("Provide 'text', 'audio', or 'image' input.", 400)

        if not GROQ_API_KEY:
            logger.error("GROQ_API_KEY not set in environment.")
            return ApiResponse.error("AI service not configured. Set GROQ_API_KEY.", 503)

        # Build prompt string
        prompt = text or "Analyze the uploaded media for expense-related information."
        if audio_file:
            prompt += f"\n[Audio file: {audio_file.name}]"
        if image_file:
            prompt += f"\n[Image file: {image_file.name}]"

        # ── 2. Create User Message object ─────────────────────────────
        user_msg = Message.objects.create(
            chat=chat,
            role="user",
            content=prompt
        )

        # ── 3. Parse conversation history from Database ──────────────────
        db_messages = Message.objects.filter(chat=chat).order_by('created_at')

        # ── 4. Build live user context from DB ────────────────────────
        try:
            user_context = _build_user_context(request.user)
        except Exception as exc:
            logger.warning(f"Failed to build user context: {exc}")
            user_context = "No financial data available."

        # ── 5. Build messages for Groq ────────────────────────────────
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(user_context=user_context)
        messages_payload = [{"role": "system", "content": system_prompt}]

        for msg in db_messages:
            messages_payload.append({"role": msg.role, "content": msg.content})

        # ── 6. Call Groq API ──────────────────────────────────────────
        logger.info(f"Groq call: model={GROQ_MODEL} user={request.user.username} chat_id={chat.id}")
        try:
            resp = requests.post(
                GROQ_API_URL,
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model":       GROQ_MODEL,
                    "messages":    messages_payload,
                    "temperature": GROQ_TEMPERATURE,
                    "max_tokens":  GROQ_MAX_TOKENS,
                },
                timeout=60,
            )
            resp.raise_for_status()
        except requests.exceptions.Timeout:
            logger.error("Groq API timeout")
            return ApiResponse.error("AI service timed out. Please try again.", 503)
        except requests.exceptions.HTTPError as e:
            logger.error(f"Groq HTTP error: {e.response.status_code} — {e.response.text}")
            return ApiResponse.error(f"AI service error: {e.response.status_code}", 503)
        except Exception as exc:
            logger.exception(f"Groq call failed: {exc}")
            return ApiResponse.error(f"AI service unavailable: {exc}", 503)

        # ── 7. Parse AI JSON response ─────────────────────────────────
        raw_content = (
            resp.json()
            .get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        if isinstance(raw_content, list):
            raw_content = " ".join(str(p.get("text", "")) for p in raw_content if isinstance(p, dict))

        ai_message  = raw_content or "Sorry, I couldn't process that."
        intent      = "none"
        ai_data     = {}
        crud_type   = "none"
        crud_record = None

        try:
            cleaned = _strip_json_fences(raw_content)
            parsed  = json.loads(cleaned)
            if isinstance(parsed, dict):
                intent     = parsed.get("intent", "none")
                ai_message = parsed.get("message", ai_message)
                ai_data    = parsed.get("data") or {}
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning(f"AI response not JSON: {exc} — content: {raw_content[:200]}")

        # ── 8. Execute CRUD if needed ─────────────────────────────────
        if intent in CRUD_INTENTS:
            result      = _execute_crud(request.user, intent, ai_data)
            ai_message  = result["message"] or ai_message
            crud_type   = result["crud_type"]
            crud_record = result.get("crud_record")

        # ── 9. Save Assistant Message and update Chat ────────────────
        is_dash = (intent == "none" and "financial overview" in ai_message)
        assistant_msg = Message.objects.create(
            chat=chat,
            role="assistant",
            content=ai_message,
            crud_type=crud_type,
            crud_record=crud_record,
            is_dashboard=is_dash
        )

        chat.last_message = ai_message
        # Generate title if it was default or a placeholder
        if chat.title == "New Chat" or chat.title == "":
            clean_title = text.strip()[:40] if text else "Media Upload"
            if len(text.strip()) > 40:
                clean_title += "..."
            chat.title = clean_title
        chat.save()

        # ── 10. Return response ───────────────────────────────────────
        return ApiResponse.success(
            data={
                "message":     ai_message,
                "crud_type":   crud_type,
                "crud_record": crud_record,
                "action":      None,
                "user_msg":    MessageSerializer(user_msg).data,
                "assistant_msg": MessageSerializer(assistant_msg).data,
            },
            message="AI responded successfully",
        )
