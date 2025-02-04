import asyncio
import logging
import datetime
import os
import random
from dotenv import load_dotenv, find_dotenv
from pyrogram import Client
from pyrogram.enums import ChatType
from pyrogram.errors import MessageIdInvalid


# Фильтр для подавления "Waiting for ..." сообщений от pyrogram
class PyrogramFilter(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        if "Waiting for" in msg and "messages.SendReaction" in msg:
            return False
        return True


# Формируем имя файла лога в формате dd.mm.yy_HH.MM.SS.log
log_filename = datetime.datetime.now().strftime("%d.%m.%y_%H.%M.%S.log")
logging.basicConfig(
    encoding='utf-8',
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s: %(message)s',
    datefmt='%m/%d/%Y %I:%M:%S %p',
    filename=log_filename
)
# Вывод в консоль
console = logging.StreamHandler()
console.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p')
console.setFormatter(formatter)
logging.getLogger('').addHandler(console)

# Подавляем лишние логи от pyrogram и asyncio
pyrogram_logger = logging.getLogger("pyrogram")
pyrogram_logger.setLevel(logging.WARNING)
pyrogram_logger.addFilter(PyrogramFilter())
logging.getLogger("asyncio").setLevel(logging.WARNING)


class ReactionBot:
    def __init__(self, client: Client, emojis: str, group_limit: int = 6):
        self.client = client
        # Превращаем строку со смайликами в список (каждый символ — отдельный эмодзи)
        self.default_emojis = list(emojis)
        self.group_limit = group_limit

    async def select_group(self):
        groups = []
        async for dialog in self.client.get_dialogs():
            if dialog.chat.type == ChatType.SUPERGROUP:
                groups.append(dialog)
        if not groups:
            logging.error("Нет супергрупп для работы, отъебись!")
            raise Exception("Нет супергрупп")
        for index, group in enumerate(groups):
            print(f"[{index}] {group.chat.title}")
        while True:
            try:
                num_group = int(input('Выбери группу: '))
                if num_group < 0 or num_group >= len(groups):
                    raise ValueError
                return groups[num_group]
            except ValueError:
                print("Неправильный ввод, попробуй еще раз, долбоёб.")

    async def get_msgids(self, chat_id: int, limit: int, all_messages: bool = False):
        msgids = []
        if not all_messages:
            async for msg in self.client.get_chat_history(chat_id=chat_id, limit=limit):
                msgids.append(msg.id)
        else:
            async for msg in self.client.get_chat_history(chat_id=chat_id):
                msgids.append(msg.id)
        return msgids

    async def react_on_message(self, chat_id: int, msg_id: int, chat_title: str, premium: bool, allowed_emojis: list):
        identifier = f'[{chat_title}/{msg_id}]'
        logging.info(f'{identifier} Начинаю ставить реакции')

        # Если премиум – ставим 1, 2 или 3 реакции, иначе ровно 1
        num_reactions = random.randint(1, 3) if premium else 1
        try:
            chosen_emojis = random.sample(allowed_emojis, num_reactions)
        except ValueError:
            chosen_emojis = allowed_emojis

        for emoji in chosen_emojis:
            try:
                await self.client.send_reaction(
                    chat_id=chat_id,
                    message_id=msg_id,
                    emoji=emoji  # передаём реакцию в виде строки
                )
                logging.info(f'{identifier} Поставил реакцию {emoji}')
            except MessageIdInvalid:
                logging.exception(f'{identifier} Неправильный message_id')
            except Exception as e:
                logging.exception(f'{identifier} Ошибка при реакции {emoji}: {e}')
            # Увеличил задержку до 6 секунд, чтобы телега не ругалась
            await asyncio.sleep(6)
        logging.info(f'{identifier} Завершил реакции')

    async def run(self):
        # Главное меню выбора режима
        while True:
            mode = input(
                "\nВыбери режим:\n1 - Поставить реакции на последние N сообщений\n2 - Поставить реакции на все сообщения в чате\n3 - Выход\nТвой выбор: "
            ).strip()
            if mode == "1":
                try:
                    last_messages = int(input('Введи число последних сообщений для реакции (1-6): '))
                    if last_messages < 1 or last_messages > self.group_limit:
                        raise ValueError
                except ValueError:
                    logging.error("Число должно быть от 1 до 6, отвали!")
                    continue
                fetch_all = False
            elif mode == "2":
                fetch_all = True
                last_messages = None
            elif mode == "3":
                logging.info("Выход из программы")
                return
            else:
                logging.error("Неправильный выбор режима, отвали!")
                continue

            async with self.client:
                me = await self.client.get_me()
                premium = getattr(me, "is_premium", False)
                logging.info(f"Пользователь premium: {premium}")

                selected_chat = await self.select_group()
                chat_id = selected_chat.chat.id
                chat_title = selected_chat.chat.title

                # Получаем список разрешённых эмодзи
                try:
                    chat_details = await self.client.get_chat(chat_id)
                    if hasattr(chat_details, "available_reactions") and chat_details.available_reactions:
                        if chat_details.available_reactions.all_are_enabled:
                            allowed_emojis = self.default_emojis  # Если в чате разрешены ВСЕ реакции
                        else:
                            # Извлекаем эмодзи из объектов Reaction
                            allowed_emojis = [r.emoji for r in chat_details.available_reactions.reactions]
                        logging.info(f"Использую смайлы, разрешённые в чате: {allowed_emojis}")
                    else:
                        allowed_emojis = self.default_emojis
                        logging.info("Использую стандартный список смайлов")
                except Exception as e:
                    logging.exception(f"Ошибка при получении разрешённых смайлов: {e}")
                    allowed_emojis = self.default_emojis

                logging.info(f'[{chat_title}] Запуск авто-реакций')
                # Цикл авто-реакций, который можно прервать командой "exit"
                while True:
                    if not fetch_all:
                        msg_ids = await self.get_msgids(chat_id, last_messages, all_messages=False)
                    else:
                        msg_ids = await self.get_msgids(chat_id, 0, all_messages=True)
                    if not msg_ids:
                        logging.info("Нет сообщений для реакции")
                        break

                    tasks = []
                    for msg_id in msg_ids:
                        tasks.append(
                            asyncio.create_task(
                                self.react_on_message(chat_id, msg_id, chat_title, premium, allowed_emojis))
                        )
                        await asyncio.sleep(0.5)  # небольшая задержка между задачами
                    if tasks:
                        await asyncio.gather(*tasks)

                    # Возможность выйти из авто-режима
                    exit_command = await asyncio.to_thread(
                        input, "Нажми Enter для продолжения авто-реакций или введи 'exit' для выхода в меню: "
                    )
                    if exit_command.strip().lower() == "exit":
                        logging.info("Выход из режима авто-реакций, возвращаюсь в главное меню")
                        break


def create_reaction_bot():
    dotenv_file = find_dotenv()
    load_dotenv(dotenv_file)
    api_hash = os.environ.get('api_hash')
    api_id = os.environ.get('api_id')
    emojis = "👍👎❤🔥🥰👏😁🤔🤯😱🤬😢🎉🤩🤮💩🙏👌🕊🤡🥱🥴😍🐳❤‍🔥🌚🌭💯🤣⚡🍌🏆💔🤨😐🍓🍾💋🖕😈😴😭🤓👻👨‍💻👀🎃🙈😇😨🤝✍🤗🫡🎅🎄☃💅🤪🗿🆒💘🙉🦄😘💊🙊😎👾🤷‍♂🤷🤷‍♀😡"
    session_name = './session'
    client = Client(session_name, api_id=api_id, api_hash=api_hash)
    return ReactionBot(client, emojis)


if __name__ == '__main__':
    bot = create_reaction_bot()
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(bot.run())
    except KeyboardInterrupt:
        logging.info("Останавливаем бот, до встречи!")
