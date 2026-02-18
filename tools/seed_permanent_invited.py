#!/usr/bin/env python3
"""
Скрипт загрузки постоянных приглашённых из текстового файла в таблицу permanent_invited.

Формат файла: каждая строка в формате "ФИО | email | телефон"
- ФИО и телефон опциональны
- Строки, начинающиеся с #, игнорируются
- Пустые строки игнорируются

Примеры использования:
  uv run python tools/seed_permanent_invited.py --file config/permanent_invited.txt
  uv run python tools/seed_permanent_invited.py --file config/permanent_invited.txt --dry-run
  uv run python tools/seed_permanent_invited.py --file config/permanent_invited.txt --update
"""
import argparse
import logging
import sys
from pathlib import Path

# Добавляем корень проекта в path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.meeting.meeting_repository import MeetingRepository

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def _parse_file_line(line: str) -> dict | None:
    """
    Парсит строку файла: "ФИО | email | телефон".
    Возвращает dict с ключами full_name, email, phone или None при ошибке.
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    
    parts = [p.strip() for p in line.split("|")]
    if len(parts) < 2:
        logger.warning("Некорректный формат строки (требуется минимум 'ФИО | email'): %s", line)
        return None
    
    full_name = parts[0] if parts[0] else None
    email = parts[1] if len(parts) > 1 and parts[1] else None
    phone = parts[2] if len(parts) > 2 and parts[2] else None
    
    if not email:
        logger.warning("Email не указан в строке: %s", line)
        return None
    
    email = email.lower().strip()
    if "@" not in email:
        logger.warning("Некорректный email: %s", email)
        return None
    
    return {
        "full_name": full_name.strip() if full_name else None,
        "email": email,
        "phone": phone.strip() if phone else None,
    }


def _load_from_file(file_path: Path) -> list[dict]:
    """Загружает список постоянных приглашённых из файла."""
    result: list[dict] = []
    
    if not file_path.exists():
        logger.error("Файл %s не найден", file_path)
        return result
    
    with open(file_path, encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            parsed = _parse_file_line(line)
            if parsed:
                result.append(parsed)
            elif line.strip() and not line.strip().startswith("#"):
                logger.debug("Строка %d пропущена: %s", line_num, line.strip())
    
    return result


def main() -> int:
    """Главная функция скрипта."""
    parser = argparse.ArgumentParser(
        description="Загрузка постоянных приглашённых из текстового файла"
    )
    parser.add_argument(
        "--file",
        "-f",
        type=str,
        required=True,
        help="Путь к файлу со списком постоянных приглашённых",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Показать что будет загружено без сохранения в БД",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Обновлять существующие записи (по умолчанию пропускаются)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Подробный вывод",
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    file_path = Path(args.file)
    if not file_path.is_absolute():
        # Относительный путь от корня проекта
        project_root = Path(__file__).resolve().parent.parent
        file_path = project_root / file_path
    
    logger.info("Загрузка постоянных приглашённых из файла: %s", file_path)
    
    # Загружаем данные из файла
    entries = _load_from_file(file_path)
    
    if not entries:
        logger.warning("Не найдено ни одной валидной записи в файле")
        return 1
    
    logger.info("Найдено записей для обработки: %d", len(entries))
    
    if args.dry_run:
        logger.info("=== DRY RUN MODE (изменения не будут сохранены) ===")
        for entry in entries:
            logger.info(
                "  - %s | %s | %s",
                entry["full_name"] or "(без ФИО)",
                entry["email"],
                entry["phone"] or "(без телефона)",
            )
        logger.info("=== Конец DRY RUN ===")
        return 0
    
    # Загружаем в БД
    repo = MeetingRepository()
    added_count = 0
    updated_count = 0
    skipped_count = 0
    error_count = 0
    
    # Получаем список существующих записей один раз
    existing_list = repo.get_permanent_invited_list()
    existing_emails = {e["email"].lower() for e in existing_list}
    
    for entry in entries:
        try:
            if entry["email"].lower() in existing_emails:
                if args.update:
                    # Обновляем существующую запись
                    repo.save_permanent_invited(
                        full_name=entry["full_name"] or "",
                        email=entry["email"],
                        phone=entry.get("phone"),
                    )
                    updated_count += 1
                    logger.info("Обновлён: %s", entry["email"])
                else:
                    skipped_count += 1
                    logger.debug("Пропущен (уже существует): %s", entry["email"])
            else:
                # Добавляем новую запись
                repo.save_permanent_invited(
                    full_name=entry["full_name"] or "",
                    email=entry["email"],
                    phone=entry.get("phone"),
                )
                added_count += 1
                logger.info("Добавлен: %s", entry["email"])
        except Exception as e:
            error_count += 1
            logger.error("Ошибка при обработке %s: %s", entry["email"], e)
    
    # Итоговая статистика
    logger.info("=" * 50)
    logger.info("Итоги загрузки:")
    logger.info("  Добавлено: %d", added_count)
    logger.info("  Обновлено: %d", updated_count)
    logger.info("  Пропущено: %d", skipped_count)
    logger.info("  Ошибок: %d", error_count)
    logger.info("=" * 50)
    
    if error_count > 0:
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
