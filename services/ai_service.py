"""
Сервис взаимодействия с AI API (DeepSeek / OpenAI).
Поддерживает официальный DeepSeek API (модель deepseek-chat) через библиотеку openai,
а также Function Calling для регистрации лидов и вызова живого оператора.
Оптимизирован для молниеносных ответов (temperature: 0.3, max_tokens: 250, короткий контекст).
"""

import json
import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from openai import AsyncOpenAI

from config import config
from data.prompts import SYSTEM_PROMPT, TOOLS_SCHEMA
from database import db

logger = logging.getLogger(__name__)


@dataclass
class AIResult:
    """Результат обработки сообщения пользователя моделью."""
    text: str
    is_lead: bool = False
    lead_data: Optional[Dict[str, Any]] = None
    is_operator_request: bool = False
    operator_reason: Optional[str] = None
    detected_language: str = "ru"


class AIService:
    def __init__(self):
        self.client: Optional[AsyncOpenAI] = None
        self.model: str = "deepseek-chat"
        self.provider: str = "DeepSeek"
        self._init_client()

    def _init_client(self) -> None:
        """Инициализирует асинхронный клиент OpenAI/DeepSeek с актуальными параметрами."""
        ai_cfg = config.get_active_ai_config()
        api_key = ai_cfg.get("api_key")

        if api_key and not config._is_placeholder(api_key):
            client_kwargs = {
                "api_key": api_key,
                "max_retries": 3,
                "timeout": 30.0,
            }
            if ai_cfg.get("base_url"):
                client_kwargs["base_url"] = ai_cfg["base_url"]

            self.client = AsyncOpenAI(**client_kwargs)
            self.model = ai_cfg["model"]
            self.provider = ai_cfg["provider"]
            logger.info(
                f"AIService успешно инициализирован: провайдер={self.provider}, "
                f"модель={self.model}, base_url={ai_cfg.get('base_url')}"
            )
        else:
            self.client = None
            self.model = ai_cfg.get("model", "deepseek-chat")
            self.provider = ai_cfg.get("provider", "DeepSeek")

    async def _call_llm_with_retry(self, **kwargs) -> Any:
        """Вызывает LLM с повторными попытками при ошибках 503 (Service Busy) или таймаутах."""
        max_attempts = 3
        last_exception = None

        for attempt in range(1, max_attempts + 1):
            try:
                return await self.client.chat.completions.create(**kwargs)
            except Exception as e:
                last_exception = e
                err_msg = str(e)
                if ("503" in err_msg or "busy" in err_msg.lower() or "timeout" in err_msg.lower()) and attempt < max_attempts:
                    wait_sec = attempt * 1.5
                    logger.warning(
                        f"Попытка {attempt}/{max_attempts}: {self.provider} временно занят (503). Повтор через {wait_sec} сек..."
                    )
                    await asyncio.sleep(wait_sec)
                    continue
                raise last_exception

    async def process_user_message(
        self,
        telegram_id: int,
        user_message: str,
        user_info: Optional[Dict[str, Any]] = None,
        forced_language: Optional[str] = None,
    ) -> AIResult:
        """
        Обрабатывает входящее сообщение пользователя:
        1. Извлекает короткую историю из базы (4-6 сообщений).
        2. Делает запрос к LLM (DeepSeek / OpenAI) с max_tokens=250 и temperature=0.3.
        3. Обрабатывает вызов функций (регистрация лида, вызов оператора).
        4. Сохраняет историю диалога.
        """
        if not self.client:
            self._init_client()

        if not self.client:
            return AIResult(
                text=(
                    "⚠️ Сервис AI временно не настроен (отсутствует DEEPSEEK_API_KEY).\n"
                    "Пожалуйста, свяжитесь с нами по телефону: +998 71 200 44 88.\n\n"
                    "Iltimos, biz bilan telefon orqali bog'laning: +998 71 200 44 88."
                )
            )

        # 1. Получаем короткую историю диалога (для молниеносного инференса)
        history = await db.get_chat_history(telegram_id, limit=config.HISTORY_LIMIT)

        # 2. Формируем список сообщений для LLM
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

        # Phase 7: PII Stripping & Privacy Guardrail
        # Never send user's real names, handles or phone numbers to external LLM provider.
        if forced_language:
            messages.append({
                "role": "system",
                "content": f"Язык пациента для ответа: {forced_language.upper()}."
            })

        for msg in history:
            # Mask phone numbers in history
            clean_history_content = re.sub(
                r'(\+?998[\s\-]?)?\(?\d{2}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',
                '[ТЕЛЕФОН_СКРЫТ]',
                msg["content"]
            )
            messages.append({"role": msg["role"], "content": clean_history_content})

        # Mask phone numbers in current user prompt
        clean_user_message = re.sub(
            r'(\+?998[\s\-]?)?\(?\d{2}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',
            '[ТЕЛЕФОН_СКРЫТ]',
            user_message
        )
        messages.append({"role": "user", "content": clean_user_message})

        try:
            # 3. Запрос к LLM (DeepSeek или OpenAI) с инструментами и лимитом 250 токенов
            response = await self._call_llm_with_retry(
                model=self.model,
                messages=messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto",
                temperature=0.3,
                max_tokens=250,
            )

            choice = response.choices[0]
            message = choice.message

            result = AIResult(text="", detected_language=forced_language or "ru")

            # 4. Проверяем наличие вызовов функций (Tool Calls)
            if message.tool_calls:
                for tool_call in message.tool_calls:
                    fn_name = tool_call.function.name
                    raw_args = tool_call.function.arguments

                    try:
                        args = json.loads(raw_args)
                    except json.JSONDecodeError:
                        args = {}

                    logger.info(f"{self.provider} вызвал функцию '{fn_name}' с параметрами: {args}")

                    if fn_name == "register_lead":
                        result.is_lead = True
                        result.lead_data = args
                        result.detected_language = args.get("language", forced_language or "ru")

                    elif fn_name == "request_human_operator":
                        result.is_operator_request = True
                        result.operator_reason = args.get("reason", "Запрос клиента")
                        result.detected_language = args.get("language", forced_language or "ru")

                # Если модель также сгенерировала текст вместе с вызовом функции
                if message.content:
                    result.text = message.content.strip()
                else:
                    tool_messages = list(messages)
                    tool_messages.append(message)
                    for tool_call in message.tool_calls:
                        tool_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps({"status": "success", "confirmed": True}, ensure_ascii=False)
                        })

                    second_resp = await self._call_llm_with_retry(
                        model=self.model,
                        messages=tool_messages,
                        temperature=0.3,
                        max_tokens=250,
                    )
                    result.text = second_resp.choices[0].message.content.strip()

            else:
                result.text = message.content.strip() if message.content else ""

            # Резервный текст, если модель ничего не вернула при регистрации лида
            if result.is_lead and not result.text:
                name = result.lead_data.get("client_name", "уважаемый пациент")
                if result.detected_language == "uz":
                    result.text = (
                        f"Rahmat, {name}! Arizangiz qabul qilindi va katta administratorimizga topshirildi. "
                        "Biz siz uchun vaqtni band qildik va 10 daqiqa ichida "
                        "tasdiqlash uchun qo'ng'iroq qilamiz! 🦷"
                    )
                elif result.detected_language == "en":
                    result.text = (
                        f"Thank you, {name}! Your request has been sent to our chief receptionist. "
                        "We have reserved your slot and will call you within 10 minutes to confirm! 🦷"
                    )
                else:
                    result.text = (
                        f"Рахмат, {name}! Заявка передана старшему администратору клиники DentaLux. "
                        "Мы забронировали за Вами время и перезвоним для подтверждения в течение 10 минут. "
                        "Ждем Вас! 🦷✨"
                    )

            if result.is_operator_request and not result.text:
                if result.detected_language == "uz":
                    result.text = (
                        "Katta administratorimizga xabar yuborildi. Tez orada jonli mutaxassisimiz "
                        "siz bilan ushbu chatda bog'lanadi! 👨‍💼"
                    )
                elif result.detected_language == "en":
                    result.text = (
                        "A notification has been sent to our receptionist. A live specialist will "
                        "join this chat shortly! 👨‍💼"
                    )
                else:
                    result.text = (
                        "Запрос передан старшему администратору клиники. "
                        "В ближайшие минуты живой специалист подключится к диалогу! 👨‍💼"
                    )

            # 5. Сохраняем сообщения в базу данных
            await db.save_message(telegram_id, "user", user_message)
            if result.text:
                await db.save_message(telegram_id, "assistant", result.text)

            return result

        except Exception as e:
            logger.error(f"Ошибка вызова {self.provider} API: {e}", exc_info=True)
            return AIResult(
                text=(
                    "Приносим извинения, произошла временная задержка связи. "
                    "Вы можете позвонить нам напрямую по номеру: +998 71 200 44 88, "
                    "или нажмите кнопку связи с администратором ниже.\n\n"
                    "Kechirasiz, aloqada vaqtinchalik uzilish yuz berdi. "
                    "Biz bilan to'g'ridan-to'g'ri bog'lanishingiz mumkin: +998 71 200 44 88."
                )
            )


ai_service = AIService()
