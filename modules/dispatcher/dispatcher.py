import time
import logging
import smtplib
from multiprocessing import Process
from email.mime.text import MIMEText
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from email.mime.multipart import MIMEMultipart

from config import config
from db.session import get_session_context
from db.models import Meeting, Invited, User
from messenger_bot_api.util import Request, MessageRequest

logger = logging.getLogger(__name__)

# Загрузка шаблона письма из внешнего файла
EMAIL_TEMPLATE = None

try:
    with open(config.email_template_path, 'r', encoding='utf-8') as f:
        EMAIL_TEMPLATE = f.read()
    logger.info(f"✓ Шаблон письма загружен: {config.email_template_path}")
except Exception as e:
    logger.error(f"✗ Не удалось загрузить шаблон {config.email_template_path}: {e}")
    raise  # Критическая ошибка — без шаблона рассылка невозможна


class NotificationDispatcher:
    """Диспетчер уведомлений с поддержкой трёх независимых каналов."""
    STATUS_SENT = "sent"
    STATUS_ERROR = "error"

    def __init__(self):
        self.smtp_host = config.smtp_host
        self.smtp_port = config.smtp_port
        self.smtp_user = config.smtp_user
        self.smtp_password = config.smtp_password
        self.smtp_sender = config.smtp_sender

        self.request = Request(
            api_base_url=config.api_base_url,
            sse_base_url=config.sse_base_url,
            token=config.bot_token
        )

        missing = [name for name, val in [
            ("SMTP host", self.smtp_host),
            ("SMTP port", self.smtp_port),
            ("SMTP sender", self.smtp_sender)
        ] if not val]
        if missing:
            logger.warning(f"⚠️ Неполная SMTP-конфигурация: {', '.join(missing)}")

    def dispatch_for_meeting(self, meeting_id: int, use_multiprocessing: bool = True) -> bool:
        try:
            with get_session_context() as session:
                if not session.get(Meeting, meeting_id):
                    logger.error(f"✗ Совещание ID={meeting_id} не найдено")
                    return False

            target = self._send_notifications_in_background
            if use_multiprocessing:
                Process(target=target, args=(meeting_id,), daemon=True).start()
                logger.info(f"🚀 Запущен процесс рассылки для совещания ID={meeting_id}")
            else:
                target(meeting_id)
            return True
        except Exception as e:
            logger.exception(f"✗ Ошибка запуска рассылки для совещания {meeting_id}: {e}")
            return False

    def _send_notifications_in_background(self, meeting_id: int) -> None:
        with get_session_context() as session:
            try:
                meeting = session.get(Meeting, meeting_id)
                if not meeting:
                    logger.error(f"✗ Совещание ID={meeting_id} не найдено в процессе")
                    return

                registered_emails, registered_phones = self._get_registered_contacts(session)
                pending_invited = self._get_pending_invited(session, meeting_id, registered_emails, registered_phones)

                if not pending_invited:
                    logger.info(f"ℹ️ Нет участников для обработки для совещания ID={meeting_id}")
                    return

                logger.info(f"📨 Начата обработка {len(pending_invited)} участников для совещания ID={meeting_id}")
                stats = self._process_invited_list(
                    session,
                    meeting,
                    pending_invited,
                    registered_emails,
                    registered_phones
                )
                session.commit()

                logger.info(
                    f"✅ Рассылка завершена для совещания ID={meeting_id} | "
                    f"KChat: ✅{stats['kchat_sent']}/❌{stats['kchat_error']} | "
                    f"Email: ✅{stats['email_sent']}/❌{stats['email_error']} | "
                    f"SMS: ✅{stats['sms_sent']}/❌{stats['sms_error']}"
                )
            except Exception as e:
                session.rollback()
                logger.exception(f"✗ Критическая ошибка в рассылке для совещания {meeting_id}: {e}")

    def _get_registered_contacts(self, session) -> tuple[set[str], set[str]]:
        emails = set(session.scalars(select(User.email).where(User.email.isnot(None))).all())
        phones = set(session.scalars(select(User.phone).where(User.phone.isnot(None))).all())
        return emails, phones

    def _get_pending_invited(self, session, meeting_id: int, reg_emails: set[str], reg_phones: set[str]) -> list[
        Invited]:
        stmt = select(Invited).where(Invited.meeting_id == meeting_id)
        pending = []
        for inv in session.scalars(stmt).all():
            is_registered = (inv.email and inv.email in reg_emails) or (inv.phone and inv.phone in reg_phones)

            if is_registered:
                if inv.kchat_status is None:
                    pending.append(inv)
            else:
                needs_email = inv.email is not None and inv.email_status is None
                needs_sms = inv.phone is not None and inv.sms_status is None
                if needs_email or needs_sms:
                    pending.append(inv)
        return pending

    def _process_invited_list(
            self,
            session,
            meeting: Meeting,
            invited_list: list[Invited],
            reg_emails: set[str],
            reg_phones: set[str]
    ) -> dict:
        stats = {k: 0 for k in ["kchat_sent", "kchat_error", "email_sent", "email_error", "sms_sent", "sms_error"]}

        for invited in invited_list:
            is_registered = (
                (invited.email and invited.email in reg_emails) or
                (invited.phone and invited.phone in reg_phones)
            )

            if is_registered:
                user = self._find_registered_user(session, invited.email, invited.phone)
                if user:
                    success = self._send_kchat(user, meeting)
                    self._update_kchat_status(session, invited.id, self.STATUS_SENT if success else self.STATUS_ERROR)
                    stats["kchat_sent" if success else "kchat_error"] += 1
                else:
                    logger.warning(f"⚠️ Приглашённый {invited.id} помечен как зарегистрированный, но не найден в User")
                    self._update_kchat_status(session, invited.id, self.STATUS_ERROR)
                    stats["kchat_error"] += 1
            else:
                if invited.email and invited.email_status is None:
                    success = self._send_email(invited, meeting)
                    self._update_email_status(session, invited.id, self.STATUS_SENT if success else self.STATUS_ERROR)
                    stats["email_sent" if success else "email_error"] += 1
                    time.sleep(0.5)

                if invited.phone and invited.sms_status is None:
                    success = self._send_sms_stub(invited, meeting)
                    self._update_sms_status(session, invited.id, self.STATUS_SENT if success else self.STATUS_ERROR)
                    stats["sms_sent" if success else "sms_error"] += 1

        return stats

    def _find_registered_user(self, session, email: str | None, phone: str | None) -> User | None:
        if not email and not phone:
            return None
        conditions = [User.email == email] if email else []
        if phone:
            conditions.append(User.phone == phone)
        return session.scalar(select(User).where(*conditions))

    def _update_kchat_status(self, session, invited_id: int, status: str) -> bool:
        return self._update_channel_status(session, invited_id, "kchat_status", status)

    def _update_email_status(self, session, invited_id: int, status: str) -> bool:
        return self._update_channel_status(session, invited_id, "email_status", status)

    def _update_sms_status(self, session, invited_id: int, status: str) -> bool:
        return self._update_channel_status(session, invited_id, "sms_status", status)

    def _update_channel_status(self, session, invited_id: int, field: str, status: str) -> bool:
        try:
            stmt = update(Invited).where(Invited.id == invited_id).values({field: status})
            return session.execute(stmt).rowcount > 0
        except SQLAlchemyError as e:
            logger.error(f"✗ Ошибка обновления {field} для invited.id={invited_id}: {e}")
            session.rollback()
            return False

    # === ОТПРАВКА С ЭМОДЗИ В КЧАТ (без markdown-звёздочек) ===
    def _send_kchat(self, user: User, meeting: Meeting) -> bool:
        """Отправка уведомления в КЧАТ с эмодзи и чистым текстом (без markdown)."""
        try:
            message = (
                f"👋 Уважаемый(ая) {user.full_name},\n\n"
                f"📢 Вы приглашены на оперативное совещание:\n\n"
                f"📌 Тема: {meeting.topic or 'не указана'}\n"
                f"📅 Дата: {meeting.date or '?'}\n"
                f"⏰ Время: {meeting.time or '?'}\n"
                f"📍 Место: {meeting.place or 'уточнить у организатора'}\n"
                f"🔗 Ссылка: {meeting.link or 'не предоставлена'}\n\n"
                f"💬 Чтобы подтвердить участие:\n"
                f"1️⃣ Напишите боту @OperGD в К-ЧАТ\n"
                f"2️⃣ Введите команду /start\n\n"
                f"✅ После этого бот предложит выбрать:\n"
                f"   • Да, буду присутствовать\n"
                f"   • Нет, не смогу присутствовать"
            )

            result = self.request.send_text(
                workspace_id=user.workspace_id,
                group_id=user.group_id,
                message=MessageRequest(message)
            )

            success = bool(result.get('messageId'))
            status_icon = "✅" if success else "❌"
            logger.info(f"{status_icon} KChat {'отправлен' if success else 'НЕ отправлен'}: "
                        f"{user.full_name} ({user.email}) | meeting_id={meeting.id}")
            return success
        except Exception as e:
            logger.exception(f"✗ Ошибка отправки KChat для {user.email}: {e}")
            return False

    def _send_email(self, invited: Invited, meeting: Meeting) -> bool:
        try:
            if not invited.email:
                return False
            msg = self._create_email_message(invited, meeting)
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30) as server:
                server.starttls()
                if self.smtp_user and self.smtp_password:
                    server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.smtp_sender, invited.email, msg.as_string())
            logger.info(f"✅ Email отправлен: {invited.full_name or 'N/A'} <{invited.email}> | meeting_id={meeting.id}")
            return True
        except Exception as e:
            logger.exception(f"✗ Ошибка отправки email на {invited.email}: {e}")
            return False

    def _create_email_message(self, invited: Invited, meeting: Meeting) -> MIMEMultipart:
        """Формирование письма на основе внешнего шаблона."""
        msg = MIMEMultipart("alternative")
        msg["From"] = self.smtp_sender
        msg["To"] = invited.email
        msg["Subject"] = "📩 Приглашение на оперативное совещание"

        datetime_display = f"{meeting.date} в {meeting.time}" if meeting.date and meeting.time else "не указана"
        link_html = f'<p><strong>🔗 Ссылка:</strong> <a href="{meeting.link}">{meeting.link}</a></p>' if meeting.link else ''

        html_content = EMAIL_TEMPLATE.format(
            full_name=invited.full_name or "Коллега",
            topic=meeting.topic or "Не указана",
            datetime_display=datetime_display,
            place=meeting.place or "Не указано",
            link_html=link_html
        )

        msg.attach(MIMEText(html_content, "html", "utf-8"))
        return msg

    def _send_sms_stub(self, invited: Invited, meeting: Meeting) -> bool:
        if not invited.phone:
            return False
        sms_text = (
            f"📩 Приглашение: {meeting.topic or 'Совещание'}. "
            f"📅 {meeting.date or ''} ⏰ {meeting.time or ''}. "
            f"📍 {meeting.place or ''}. "
            f"💬 Подтвердите участие через бота @OperGD в К-ЧАТ."
        )
        logger.info(f"📱 [SMS-STUB] Для {invited.phone}: {sms_text[:60]}...")
        return True


if __name__ == '__main__':
    NotificationDispatcher().dispatch_for_meeting(meeting_id=1, use_multiprocessing=False)