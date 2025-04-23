#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import vk_api
import time
import random
import json
import os
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("vk_friends_bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("VK_Friends_Bot")

class VKFriendsInviteBot:
    def __init__(self):
        """Инициализация бота с параметрами из переменных окружения"""
        self.load_config()
        
        # Авторизация в ВК
        try:
            self.vk_session = vk_api.VkApi(token=self.config["access_token"])
            self.vk = self.vk_session.get_api()
            # Получение информации о текущем пользователе
            self.user_info = self.vk.users.get()[0]
            self.user_id = self.user_info['id']
            logger.info(f"Успешная авторизация в VK API. Пользователь: {self.user_info.get('first_name', '')} {self.user_info.get('last_name', '')}")
        except Exception as e:
            logger.error(f"Ошибка авторизации: {e}")
            exit(1)
            
        # Статистика и состояние
        self.stats_file = "friends_stats.json"
        self.load_stats()
        
    def load_config(self):
        """Загрузка настроек из переменных окружения"""
        try:
            # Функция для безопасного преобразования в целое число
            def safe_int(value, default=0):
                try:
                    return int(value)
                except (ValueError, TypeError):
                    if isinstance(value, str):
                        if value.startswith(('club', 'public')):
                            try:
                                return int(value[5:])
                            except ValueError:
                                pass
                    logger.warning(f"Не удалось преобразовать '{value}' в целое число, используется значение по умолчанию {default}")
                    return default

            # Получение конфигурации из переменных окружения
            self.config = {
                "access_token": os.getenv("VK_ACCESS_TOKEN"),
                "target_group_id": os.getenv("TARGET_GROUP_ID"),
                "your_group_id": os.getenv("YOUR_GROUP_ID"),
                "max_friend_requests_per_day": safe_int(os.getenv("MAX_FRIEND_REQUESTS_PER_DAY"), 15),
                "max_invites_per_day": safe_int(os.getenv("MAX_INVITES_PER_DAY"), 20),
                "delay_between_actions": {     
                    "min": safe_int(os.getenv("MIN_DELAY"), 180),   # 3 минуты
                    "max": safe_int(os.getenv("MAX_DELAY"), 300)    # 5 минут
                },
                "invite_after_friendship_days": safe_int(os.getenv("INVITE_AFTER_DAYS"), 2),  # Через сколько дней после добавления в друзья приглашать в группу
                "filters": {
                    "age": {
                        "enabled": os.getenv("FILTER_AGE_ENABLED", "False").lower() == "true",
                        "min": safe_int(os.getenv("FILTER_AGE_MIN"), 18),
                        "max": safe_int(os.getenv("FILTER_AGE_MAX"), 50)
                    },
                    "sex": {
                        "enabled": os.getenv("FILTER_SEX_ENABLED", "False").lower() == "true",
                        "value": safe_int(os.getenv("FILTER_SEX_VALUE"), 0)
                    },
                    "city_id": {
                        "enabled": os.getenv("FILTER_CITY_ENABLED", "False").lower() == "true",
                        "value": safe_int(os.getenv("FILTER_CITY_VALUE"), 1)
                    },
                    "has_photo": {
                        "enabled": os.getenv("FILTER_PHOTO_ENABLED", "False").lower() == "true"
                    },
                    "last_seen_days": {
                        "enabled": os.getenv("FILTER_LAST_SEEN_ENABLED", "True").lower() == "true",
                        "value": safe_int(os.getenv("FILTER_LAST_SEEN_DAYS"), 30)
                    }
                }
            }
            
            # Обработка ID группы
            target_group = self.config["target_group_id"]
            your_group = self.config["your_group_id"]
            
            logger.info(f"Исходное значение TARGET_GROUP_ID: {target_group}")
            logger.info(f"Исходное значение YOUR_GROUP_ID: {your_group}")
            
            # Проверка обязательных параметров
            if not self.config["access_token"]:
                logger.error("Не задан VK_ACCESS_TOKEN в переменных окружения")
                exit(1)
                
            logger.info("Конфигурация успешно загружена из переменных окружения")
                
        except Exception as e:
            logger.error(f"Ошибка загрузки конфигурации: {e}")
            import traceback
            logger.error(traceback.format_exc())
            exit(1)
    
    def get_group_id(self, group_identifier):
        """Получение числового ID группы по короткому имени или строковому ID"""
        try:
            # Если это уже число, просто возвращаем его
            try:
                return int(group_identifier)
            except (ValueError, TypeError):
                pass
                
            # Небольшая задержка перед API запросом
            time.sleep(1)
            
            # Пытаемся получить ID по короткому имени
            response = self.vk.groups.getById(group_id=group_identifier)
            if response and len(response) > 0:
                return response[0]['id']
                
            logger.warning(f"Не удалось получить ID группы для '{group_identifier}', используется как есть")
            return group_identifier
            
        except Exception as e:
            logger.error(f"Ошибка получения ID группы: {e}")
            return group_identifier
    
    def load_stats(self):
        """Загрузка статистики и состояния бота"""
        try:
            if os.path.exists(self.stats_file):
                with open(self.stats_file, 'r', encoding='utf-8') as f:
                    self.stats = json.load(f)
            else:
                self.stats = {
                    "friend_requests_sent": 0,
                    "friend_requests_today": 0,
                    "invites_sent": 0,
                    "invites_today": 0,
                    "last_request_date": None,
                    "last_invite_date": None,
                    "processed_users": [],
                    "friend_requests": [],  # Список отправленных заявок в друзья: [{"user_id": id, "date": "YYYY-MM-DD"}]
                    "friends_to_invite": [],  # Список друзей для приглашения: [{"user_id": id, "friendship_date": "YYYY-MM-DD"}]
                    "friend_request_failures": [],  # Список неудач при отправке заявок: [id1, id2, ...]
                    "invite_failures": [],  # Список неудач при приглашении: [id1, id2, ...]
                    "current_friends": [],  # Текущий список друзей
                    "last_activity_time": None
                }
                self.save_stats()
                
        except Exception as e:
            logger.error(f"Ошибка загрузки статистики: {e}")
            self.stats = {
                "friend_requests_sent": 0,
                "friend_requests_today": 0,
                "invites_sent": 0,
                "invites_today": 0,
                "last_request_date": None,
                "last_invite_date": None,
                "processed_users": [],
                "friend_requests": [],
                "friends_to_invite": [],
                "friend_request_failures": [],
                "invite_failures": [],
                "current_friends": [],
                "last_activity_time": None
            }
    
    def save_stats(self):
        """Сохранение статистики и состояния бота"""
        try:
            # Обновляем время последней активности
            self.stats["last_activity_time"] = datetime.now().isoformat()
            
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                json.dump(self.stats, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Ошибка сохранения статистики: {e}")
    
    def reset_daily_counters(self):
        """Сброс дневных счетчиков"""
        today = datetime.now().strftime("%Y-%m-%d")
        
        # Сброс счетчика заявок в друзья
        last_request_date = self.stats["last_request_date"]
        if last_request_date and last_request_date != today:
            logger.info("Сброс дневного счетчика заявок в друзья")
            self.stats["friend_requests_today"] = 0
            
        # Сброс счетчика приглашений в группу
        last_invite_date = self.stats["last_invite_date"]
        if last_invite_date and last_invite_date != today:
            logger.info("Сброс дневного счетчика приглашений в группу")
            self.stats["invites_today"] = 0
            
        self.save_stats()
    
    def update_current_friends(self):
        """Обновление списка текущих друзей"""
        try:
            logger.info("Обновление списка друзей")
            
            friends = []
            offset = 0
            
            while True:
                time.sleep(1)  # Задержка между запросами
                
                response = self.vk.friends.get(
                    user_id=self.user_id,
                    offset=offset,
                    count=5000
                )
                
                if not response or not response.get('items'):
                    break
                    
                batch = response['items']
                friends.extend(batch)
                
                if len(batch) < 5000:
                    break
                    
                offset += 5000
                
            # Обновляем список текущих друзей
            self.stats["current_friends"] = friends
            logger.info(f"Текущее количество друзей: {len(friends)}")
            
            # Проверяем, кто из заявок принял дружбу
            new_friends_to_invite = []
            friend_requests_remaining = []
            
            for request in self.stats["friend_requests"]:
                user_id = request["user_id"]
                request_date_str = request["date"]
                
                # Проверка, стал ли пользователь другом
                if user_id in friends:
                    # Проверка, прошло ли достаточно времени для приглашения в группу
                    request_date = datetime.strptime(request_date_str, "%Y-%m-%d")
                    days_passed = (datetime.now() - request_date).days
                    
                    if days_passed >= self.config["invite_after_friendship_days"]:
                        # Добавляем в список для приглашения
                        new_friends_to_invite.append({
                            "user_id": user_id,
                            "friendship_date": request_date_str
                        })
                        logger.info(f"Пользователь ID{user_id} принял заявку и готов к приглашению в группу")
                    else:
                        # Еще не прошло достаточно времени, оставляем в списке заявок
                        friend_requests_remaining.append(request)
                else:
                    # Заявка еще не принята, оставляем в списке
                    friend_requests_remaining.append(request)
            
            # Обновляем списки
            self.stats["friend_requests"] = friend_requests_remaining
            
            # Добавляем новых друзей для приглашения
            for new_friend in new_friends_to_invite:
                if new_friend not in self.stats["friends_to_invite"]:
                    self.stats["friends_to_invite"].append(new_friend)
            
            self.save_stats()
            logger.info(f"Обновлен список друзей и заявок. Ожидает приглашения в группу: {len(self.stats['friends_to_invite'])}")
            
        except Exception as e:
            logger.error(f"Ошибка при обновлении списка друзей: {e}")
    
    def get_group_members(self, group_id, count=1000):
        """Получение списка участников группы"""
        try:
            # Получаем числовой ID группы
            actual_group_id = self.get_group_id(group_id)
            logger.info(f"Получение участников группы: {group_id} (ID: {actual_group_id})")
            
            members = []
            offset = 0
            
            while True:
                # Задержка между запросами
                time.sleep(1)
                
                response = self.vk.groups.getMembers(
                    group_id=actual_group_id,
                    offset=offset,
                    count=1000,
                    fields="sex,bdate,city,last_seen,has_photo"
                )
                
                batch = response["items"]
                if not batch:
                    break
                    
                members.extend(batch)
                offset += 1000
                
                if offset >= count:
                    break
                    
                # Задержка между запросами для соблюдения ограничений API
                time.sleep(2)
                
            logger.info(f"Получено {len(members)} участников из группы {group_id}")
            
            # Перемешиваем список пользователей для более естественного поведения
            random.shuffle(members)
            
            return members
        except Exception as e:
            logger.error(f"Ошибка получения участников группы: {e}")
            
            if "captcha" in str(e).lower():
                logger.warning("Обнаружена капча, делаем паузу в 15 минут...")
                time.sleep(900)  # 15 минут
            
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    def filter_users_for_friend_requests(self, users):
        """Фильтрация пользователей для отправки заявок в друзья"""
        filtered_users = []
        filters = self.config["filters"]
        
        for user in users:
            # Пропускаем уже обработанных пользователей
            if user["id"] in self.stats["processed_users"]:
                continue
                
            # Пропускаем текущих друзей
            if user["id"] in self.stats["current_friends"]:
                continue
                
            # Пропускаем пользователей, которым уже отправлена заявка
            if any(request["user_id"] == user["id"] for request in self.stats["friend_requests"]):
                continue
                
            # Пропускаем пользователей из списка неудачных попыток добавления
            if user["id"] in self.stats["friend_request_failures"]:
                continue
                
            # Проверка, не является ли пользователь уже участником нашей группы
            try:
                time.sleep(0.5)  # Небольшая задержка
                
                actual_group_id = self.get_group_id(self.config["your_group_id"])
                is_member = self.vk.groups.isMember(
                    group_id=actual_group_id,
                    user_id=user["id"]
                )
                
                if is_member:
                    # Если уже участник группы, нет смысла добавлять в друзья
                    continue
            except Exception as e:
                # При ошибке пропускаем пользователя
                continue
                
            is_suitable = True
            
            # Фильтр по последней активности
            if filters["last_seen_days"]["enabled"] and "last_seen" in user:
                last_seen_time = user["last_seen"]["time"]
                last_seen_date = datetime.fromtimestamp(last_seen_time)
                days_ago = (datetime.now() - last_seen_date).days
                
                if days_ago > filters["last_seen_days"]["value"]:
                    is_suitable = False
                    
            # Фильтр по полу
            if filters["sex"]["enabled"] and filters["sex"]["value"] != 0:
                if "sex" not in user or user["sex"] != filters["sex"]["value"]:
                    is_suitable = False
                    
            # Фильтр по городу
            if filters["city_id"]["enabled"]:
                if "city" not in user or user["city"]["id"] != filters["city_id"]["value"]:
                    is_suitable = False
                    
            # Фильтр по наличию фото
            if filters["has_photo"]["enabled"]:
                if "has_photo" not in user or user["has_photo"] != 1:
                    is_suitable = False
                    
            # Фильтр по возрасту (если указана дата рождения)
            if filters["age"]["enabled"] and "bdate" in user:
                try:
                    bdate = user["bdate"]
                    if len(bdate.split(".")) == 3:  # Формат DD.MM.YYYY
                        birth_date = datetime.strptime(bdate, "%d.%m.%Y")
                        age = (datetime.now() - birth_date).days // 365
                        
                        if age < filters["age"]["min"] or age > filters["age"]["max"]:
                            is_suitable = False
                except:
                    # При ошибке парсинга даты рождения пропускаем этот фильтр
                    pass
                    
            if is_suitable:
                filtered_users.append(user)
                
        logger.info(f"Отфильтровано {len(filtered_users)} подходящих пользователей для заявок в друзья")
        return filtered_users
    
    def send_friend_request(self, user_id):
        """Отправка заявки в друзья пользователю"""
        try:
            # Задержка перед отправкой заявки
            time.sleep(random.uniform(1, 3))
            
            self.vk.friends.add(user_id=user_id)
            
            # Обновление статистики
            today = datetime.now().strftime("%Y-%m-%d")
            self.stats["friend_requests_sent"] += 1
            self.stats["friend_requests_today"] += 1
            self.stats["last_request_date"] = today
            self.stats["friend_requests"].append({
                "user_id": user_id,
                "date": today
            })
            self.stats["processed_users"].append(user_id)
            self.save_stats()
            
            logger.info(f"Успешно отправлена заявка в друзья пользователю ID{user_id}")
            return True
        except Exception as e:
            error_msg = str(e).lower()
            
            if "captcha" in error_msg:
                logger.warning(f"Капча при отправке заявки пользователю ID{user_id}. Делаем паузу...")
                time.sleep(900)  # 15 минут
            elif "cannot add this user to friends as they have put you on their blacklist" in error_msg:
                logger.info(f"Пользователь ID{user_id} добавил вас в черный список")
                self.stats["friend_request_failures"].append(user_id)
                self.stats["processed_users"].append(user_id)
            elif "this user has disabled adding them as friend" in error_msg:
                logger.info(f"Пользователь ID{user_id} отключил добавление в друзья")
                self.stats["friend_request_failures"].append(user_id)
                self.stats["processed_users"].append(user_id)
            else:
                logger.error(f"Ошибка при отправке заявки в друзья пользователю ID{user_id}: {e}")
                self.stats["friend_request_failures"].append(user_id)
                self.stats["processed_users"].append(user_id)
                
            self.save_stats()
            return False
    
    def invite_friend_to_group(self, user_id):
        """Отправка приглашения в группу другу"""
        try:
            # Задержка перед приглашением
            time.sleep(random.uniform(1, 3))
            
            actual_group_id = self.get_group_id(self.config["your_group_id"])
            self.vk.groups.invite(
                group_id=actual_group_id,
                user_id=user_id
            )
            
            # Обновление статистики
            today = datetime.now().strftime("%Y-%m-%d")
            self.stats["invites_sent"] += 1
            self.stats["invites_today"] += 1
            self.stats["last_invite_date"] = today
            
            # Удаляем из списка друзей для приглашения
            self.stats["friends_to_invite"] = [
                friend for friend in self.stats["friends_to_invite"] 
                if friend["user_id"] != user_id
            ]
            
            self.save_stats()
            
            logger.info(f"Успешно отправлено приглашение в группу другу ID{user_id}")
            return True
        except Exception as e:
            error_msg = str(e).lower()
            
            if "captcha" in error_msg:
                logger.warning(f"Капча при отправке приглашения в группу другу ID{user_id}. Делаем паузу...")
                time.sleep(900)  # 15 минут
            else:
                logger.error(f"Ошибка при отправке приглашения в группу другу ID{user_id}: {e}")
                self.stats["invite_failures"].append(user_id)
                
                # Удаляем из списка друзей для приглашения
                self.stats["friends_to_invite"] = [
                    friend for friend in self.stats["friends_to_invite"] 
                    if friend["user_id"] != user_id
                ]
                
            self.save_stats()
            return False
    
    def process_friend_requests(self):
        """Обработка отправки заявок в друзья"""
        logger.info("Начало процесса отправки заявок в друзья")
        
        # Проверка лимита на сегодня
        if self.stats["friend_requests_today"] >= self.config["max_friend_requests_per_day"]:
            logger.warning(f"Достигнут дневной лимит заявок в друзья ({self.config['max_friend_requests_per_day']})")
            return
            
        # Получение участников целевой группы
        target_users = self.get_group_members(self.config["target_group_id"])
        
        if not target_users:
            logger.error("Не удалось получить пользователей целевой группы")
            return
            
        # Фильтрация подходящих пользователей
        filtered_users = self.filter_users_for_friend_requests(target_users)
        
        if not filtered_users:
            logger.warning("Не найдено подходящих пользователей для заявок в друзья")
            return
        
        # Отправка заявок с учетом лимитов
        requests_left = self.config["max_friend_requests_per_day"] - self.stats["friend_requests_today"]
        
        # Ограничение для одного запуска
        max_batch = min(requests_left, 5)  # Максимум 5 заявок за один запуск
        requests_count = min(len(filtered_users), max_batch)
        
        logger.info(f"Планируется отправить {requests_count} заявок в друзья")
        
        success_count = 0
        error_count = 0
        
        for i in range(requests_count):
            user = filtered_users[i]
            
            # Отправка заявки
            result = self.send_friend_request(user["id"])
            
            if result:
                success_count += 1
            else:
                error_count += 1
            
            # Задержка между заявками
            if i < requests_count - 1:
                delay = random.randint(
                    self.config["delay_between_actions"]["min"],
                    self.config["delay_between_actions"]["max"]
                )
                logger.info(f"Ожидание {delay} секунд перед следующей заявкой...")
                time.sleep(delay)
        
        logger.info(f"Отправлено заявок в друзья: {success_count} успешно, {error_count} с ошибками")
    
    def process_group_invites(self):
        """Обработка приглашений друзей в группу"""
        logger.info("Начало процесса приглашения друзей в группу")
        
        # Проверка лимита на сегодня
        if self.stats["invites_today"] >= self.config["max_invites_per_day"]:
            logger.warning(f"Достигнут дневной лимит приглашений в группу ({self.config['max_invites_per_day']})")
            return
            
        # Обновляем список друзей
        self.update_current_friends()
        
        if not self.stats["friends_to_invite"]:
            logger.info("Нет друзей для приглашения в группу")
            return
        
        # Отправка приглашений с учетом лимитов
        invites_left = self.config["max_invites_per_day"] - self.stats["invites_today"]
        
        # Ограничение для одного запуска
        max_batch = min(invites_left, 5)  # Максимум 5 приглашений за один запуск
        invites_count = min(len(self.stats["friends_to_invite"]), max_batch)
        
        logger.info(f"Планируется отправить {invites_count} приглашений в группу друзьям")
        
        success_count = 0
        error_count = 0
        
        for i in range(invites_count):
            friend = self.stats["friends_to_invite"][i]
            
            # Отправка приглашения
            result = self.invite_friend_to_group(friend["user_id"])
            
            if result:
                success_count += 1
            else:
                error_count += 1
            
            # Задержка между приглашениями
            if i < invites_count - 1:
                delay = random.randint(
                    self.config["delay_between_actions"]["min"],
                    self.config["delay_between_actions"]["max"]
                )
                logger.info(f"Ожидание {delay} секунд перед следующим приглашением...")
                time.sleep(delay)
        
        logger.info(f"Отправлено приглашений в группу: {success_count} успешно, {error_count} с ошибками")
    
    def run(self):
        """Основная функция работы бота"""
        logger.info("Запуск бота для добавления в друзья и приглашения в группу")
        
        # Сброс дневных счетчиков при необходимости
        self.reset_daily_counters()
        
        # Обновляем список текущих друзей
        self.update_current_friends()
        
        # Сначала обрабатываем приглашения в группу (для тех, кто уже в друзьях)
        self.process_group_invites()
        
        # Затем обрабатываем отправку заявок в друзья
        self.process_friend_requests()
        
        logger.info("Работа бота завершена")
        
        # Отчет о состоянии
        friend_requests_count = len(self.stats["friend_requests"])
        friends_to_invite_count = len(self.stats["friends_to_invite"])
        
        logger.info(f"Статистика: отправлено заявок всего: {self.stats['friend_requests_sent']}, ожидает ответа: {friend_requests_count}, ожидает приглашения в группу: {friends_to_invite_count}")

def main():
    """Точка входа в программу"""
    logger.info("=" * 50)
    logger.info("Запуск программы")
    
    try:
        bot = VKFriendsInviteBot()
        bot.run()
        
        # Запуск по расписанию с интервалом
        while True:
            # Интервал между запусками (4-6 часов)
            sleep_hours = random.uniform(4.0, 6.0)
            logger.info(f"Ожидание следующего запуска ({sleep_hours:.2f} часов)...")
            time.sleep(sleep_hours * 60 * 60)
            logger.info("Запуск нового цикла")
            bot = VKFriendsInviteBot()
            bot.run()
    except KeyboardInterrupt:
        logger.info("Программа остановлена пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        import traceback
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    main()
