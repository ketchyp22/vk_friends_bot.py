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
import requests

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("vk_medical_bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("VK_Medical_Bot")

class VKMedicalBot:
    def __init__(self):
        """Инициализация бота с максимальными лимитами"""
        self.load_config()
        
        # Авторизация в ВК
        try:
            self.vk_session = vk_api.VkApi(token=self.config["access_token"])
            self.vk = self.vk_session.get_api()
            self.user_info = self.vk.users.get()[0]
            self.user_id = self.user_info['id']
            logger.info(f"Авторизация успешна: {self.user_info.get('first_name', '')} {self.user_info.get('last_name', '')}")
        except Exception as e:
            logger.error(f"Ошибка авторизации: {e}")
            exit(1)
            
        # Известные открытые медицинские группы (ID реальных открытых групп)
        self.verified_open_groups = [
            # Эти группы нужно найти вручную и проверить что они открытые
            "https://vk.com/belormedkol",
            "https://vk.com/chaikmedcol", 
            "https://vk.com/spbmedcol3",
            "https://vk.com/smk_professionalitet",
            "https://vk.com/officialtmk_professionalitet"
        ]
        
        # Ключевые слова для поиска открытых групп
        self.medical_keywords = [
            'медицинский студент', 'медколледж студенты', 'будущие врачи',
            'медицинское образование', 'студенты медики', 'медуниверситет',
            'первая помощь обучение', 'анатомия для всех', 'медицина изучаем',
            'фармацевт студент', 'медсестра обучение', 'врач практика'
        ]
        
        self.stats_file = "medical_bot_stats.json"
        self.load_stats()
        
    def load_config(self):
        """Конфигурация с переменными окружения"""
        self.config = {
            "access_token": os.getenv("VK_ACCESS_TOKEN"),
            "your_group_id": os.getenv("YOUR_GROUP_ID"),
            
            # Лимиты из переменных окружения
            "max_friend_requests_per_day": int(os.getenv("MAX_FRIEND_REQUESTS_PER_DAY", 50)),
            "max_invites_per_day": int(os.getenv("MAX_INVITES_PER_DAY", 40)),
            
            # Интервалы
            "delay_between_actions": {
                "min": int(os.getenv("MIN_DELAY", 45)),
                "max": int(os.getenv("MAX_DELAY", 120))
            },
            
            # Время до приглашения
            "invite_after_friendship_hours": int(os.getenv("INVITE_AFTER_HOURS", 4)),
            
            # Фильтры
            "filters": {
                "age_min": int(os.getenv("FILTER_AGE_MIN", 17)),
                "age_max": int(os.getenv("FILTER_AGE_MAX", 32)),
                "last_seen_days": int(os.getenv("FILTER_LAST_SEEN_DAYS", 10)),
                "has_photo": os.getenv("FILTER_PHOTO_ENABLED", "true").lower() == "true"
            }
        }
        
        # Проверяем обязательные параметры
        if not self.config["access_token"] or not self.config["your_group_id"]:
            logger.error("❌ Не заданы VK_ACCESS_TOKEN или YOUR_GROUP_ID")
            exit(1)
        
    def load_stats(self):
        """Загрузка статистики"""
        try:
            if os.path.exists(self.stats_file):
                with open(self.stats_file, 'r', encoding='utf-8') as f:
                    stats_data = json.load(f)
                    # Конвертируем списки обратно в множества
                    self.stats = stats_data.copy()
                    self.stats["processed_users"] = set(stats_data.get("processed_users", []))
                    self.stats["blacklisted_users"] = set(stats_data.get("blacklisted_users", []))
            else:
                self.stats = self.create_empty_stats()
                self.save_stats()
        except Exception as e:
            logger.error(f"Ошибка загрузки статистики: {e}")
            self.stats = self.create_empty_stats()
    
    def create_empty_stats(self):
        """Создание пустой статистики"""
        return {
            "friend_requests_sent": 0,
            "friend_requests_today": 0,
            "invites_sent": 0,
            "invites_today": 0,
            "groups_found": 0,
            "last_reset_date": datetime.now().strftime("%Y-%m-%d"),
            "processed_users": set(),
            "friend_requests": [],
            "friends_to_invite": [],
            "open_groups": [],  # Список проверенных открытых групп
            "blacklisted_users": set(),
            "successful_invites": 0
        }
    
    def save_stats(self):
        """Сохранение статистики"""
        try:
            # Конвертируем set в list для JSON
            stats_to_save = self.stats.copy()
            stats_to_save["processed_users"] = list(self.stats["processed_users"])
            stats_to_save["blacklisted_users"] = list(self.stats["blacklisted_users"])
            
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                json.dump(stats_to_save, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Ошибка сохранения статистики: {e}")
    
    def reset_daily_counters(self):
        """Сброс дневных счетчиков"""
        today = datetime.now().strftime("%Y-%m-%d")
        if self.stats["last_reset_date"] != today:
            logger.info("🔄 Сброс дневных лимитов")
            self.stats["friend_requests_today"] = 0
            self.stats["invites_today"] = 0
            self.stats["last_reset_date"] = today
            self.save_stats()
    
    def check_group_accessibility(self, group_id):
        """Проверка доступности группы для получения участников"""
        try:
            # Пробуем получить информацию о группе
            group_info = self.vk.groups.getById(group_ids=group_id, fields="members_count")[0]
            
            # Пробуем получить первых нескольких участников
            test_response = self.vk.groups.getMembers(
                group_id=group_id,
                count=1
            )
            
            return True, group_info
        except Exception as e:
            error_str = str(e).lower()
            if "access" in error_str or "denied" in error_str or "203" in error_str:
                return False, None
            else:
                logger.error(f"Неизвестная ошибка проверки группы {group_id}: {e}")
                return False, None
    
    def discover_open_medical_groups(self):
        """Поиск открытых медицинских групп"""
        logger.info("🔍 Поиск открытых медицинских групп")
        
        new_open_groups = []
        
        for keyword in self.medical_keywords[:5]:  # Ограничиваем количество поисков
            try:
                time.sleep(3)  # Задержка между поисками
                
                response = self.vk.groups.search(
                    q=keyword,
                    count=50,  # Увеличиваем количество для поиска
                    fields="members_count,activity,is_closed"
                )
                
                for group in response["items"]:
                    # Фильтруем только открытые группы среднего размера
                    if (group.get("members_count", 0) > 500 and 
                        group.get("members_count", 0) < 100000 and
                        group.get("is_closed", 1) == 0):  # 0 = открытая группа
                        
                        # Проверяем доступность
                        is_accessible, group_info = self.check_group_accessibility(group["id"])
                        
                        if is_accessible:
                            group_data = {
                                "id": group["id"],
                                "name": group["name"],
                                "screen_name": group.get("screen_name", ""),
                                "members_count": group.get("members_count", 0),
                                "verified_date": datetime.now().isoformat()
                            }
                            
                            # Проверяем, что группы еще нет в списке
                            existing_ids = [g["id"] for g in self.stats["open_groups"]]
                            if group["id"] not in existing_ids:
                                new_open_groups.append(group_data)
                                logger.info(f"✅ Найдена открытая группа: {group['name']} ({group.get('members_count', 0)} участников)")
                        
                        time.sleep(2)  # Задержка между проверками
                        
            except Exception as e:
                logger.error(f"Ошибка поиска групп по ключевому слову '{keyword}': {e}")
                continue
        
        # Добавляем найденные группы
        self.stats["open_groups"].extend(new_open_groups)
        self.stats["groups_found"] += len(new_open_groups)
        
        logger.info(f"🎯 Найдено {len(new_open_groups)} новых открытых групп")
        return new_open_groups
    
    def get_all_accessible_groups(self):
        """Получение всех доступных групп"""
        all_groups = []
        
        # Добавляем проверенные открытые группы
        for group in self.stats["open_groups"]:
            all_groups.append(group["id"])
        
        # Добавляем базовые группы (если они существуют)
        for group_name in self.verified_open_groups:
            all_groups.append(group_name)
        
        return all_groups
    
    def get_group_members_safe(self, group_identifier, max_count=1000):
        """Безопасное получение участников группы"""
        try:
            # Получаем ID группы
            if isinstance(group_identifier, str) and not str(group_identifier).isdigit():
                try:
                    group_info = self.vk.groups.getById(group_id=group_identifier)[0]
                    group_id = group_info["id"]
                    group_name = group_info["name"]
                except:
                    logger.warning(f"❌ Группа {group_identifier} не найдена")
                    return []
            else:
                group_id = int(group_identifier)
                
                # Получаем информацию о группе
                try:
                    group_info = self.vk.groups.getById(group_ids=group_id)[0]
                    group_name = group_info["name"]
                except:
                    group_name = f"ID{group_id}"
            
            logger.info(f"📥 Получение участников группы: {group_name}")
            
            # Проверяем доступность
            is_accessible, _ = self.check_group_accessibility(group_id)
            if not is_accessible:
                logger.warning(f"❌ Нет доступа к группе {group_name}")
                return []
            
            members = []
            offset = 0
            batch_size = 1000
            
            while offset < max_count:
                time.sleep(2)  # Увеличиваем задержку
                
                try:
                    response = self.vk.groups.getMembers(
                        group_id=group_id,
                        offset=offset,
                        count=min(batch_size, max_count - offset),
                        fields="sex,bdate,city,last_seen,has_photo,connections,online"
                    )
                    
                    batch = response["items"]
                    if not batch:
                        break
                    
                    members.extend(batch)
                    offset += len(batch)
                    
                    logger.info(f"📊 Загружено {len(members)} участников из {group_name}")
                    
                    if len(batch) < batch_size:
                        break
                        
                except Exception as e:
                    logger.error(f"Ошибка получения участников: {e}")
                    break
            
            # Перемешиваем для естественности
            random.shuffle(members)
            logger.info(f"✅ Получено {len(members)} участников из {group_name}")
            
            return members
            
        except Exception as e:
            logger.error(f"Критическая ошибка получения участников: {e}")
            return []
    
    def filter_users_advanced(self, users):
        """Продвинутая фильтрация пользователей"""
        filtered = []
        filters = self.config["filters"]
        
        for user in users:
            user_id = user["id"]
            
            # Базовые проверки
            if (user_id in self.stats["processed_users"] or
                user_id in self.stats["blacklisted_users"] or
                user_id == self.user_id):
                continue
            
            # Проверка активности
            if "last_seen" in user:
                last_seen = datetime.fromtimestamp(user["last_seen"]["time"])
                days_inactive = (datetime.now() - last_seen).days
                if days_inactive > filters["last_seen_days"]:
                    continue
            elif not user.get("online", 0):
                # Если нет данных о последнем визите и пользователь не онлайн
                continue
            
            # Проверка возраста (если есть дата рождения)
            if "bdate" in user and len(user["bdate"].split(".")) == 3:
                try:
                    birth_date = datetime.strptime(user["bdate"], "%d.%m.%Y")
                    age = (datetime.now() - birth_date).days // 365
                    if age < filters["age_min"] or age > filters["age_max"]:
                        continue
                except:
                    pass
            
            # Проверка наличия фото
            if filters["has_photo"] and not user.get("has_photo", 0):
                continue
            
            # Проверка на ботов (если есть подозрительные признаки)
            if not user.get("first_name") or not user.get("last_name"):
                continue
                
            # Проверка на деактивированные аккаунты
            if user.get("deactivated"):
                continue
            
            filtered.append(user)
        
        logger.info(f"🎯 Отфильтровано {len(filtered)} качественных пользователей")
        return filtered
    
    def send_friend_request_safe(self, user_id):
        """Безопасная отправка заявки в друзья"""
        try:
            self.vk.friends.add(user_id=user_id)
            
            # Обновление статистики
            self.stats["friend_requests_sent"] += 1
            self.stats["friend_requests_today"] += 1
            self.stats["processed_users"].add(user_id)
            self.stats["friend_requests"].append({
                "user_id": user_id,
                "timestamp": datetime.now().isoformat()
            })
            
            logger.info(f"✅ Заявка отправлена: ID{user_id}")
            return True
            
        except Exception as e:
            error_msg = str(e).lower()
            
            if "captcha" in error_msg:
                logger.warning("🤖 Капча! Пауза 15 минут")
                time.sleep(900)  # 15 минут
                return False
            elif "blacklist" in error_msg or "denied" in error_msg:
                self.stats["blacklisted_users"].add(user_id)
                logger.info(f"❌ Пользователь ID{user_id} в черном списке")
            elif "flood" in error_msg or "many requests" in error_msg:
                logger.warning("🌊 Флуд-контроль! Пауза 10 минут")
                time.sleep(600)  # 10 минут
                return False
            elif "already" in error_msg:
                logger.info(f"ℹ️ ID{user_id} уже в друзьях или заявка отправлена")
            else:
                logger.error(f"Ошибка заявки ID{user_id}: {e}")
            
            self.stats["processed_users"].add(user_id)
            return False
    
    def check_new_friends(self):
        """Проверка новых друзей для приглашения"""
        try:
            # Получаем текущих друзей
            friends = self.vk.friends.get()["items"]
            
            # Проверяем заявки
            current_time = datetime.now()
            ready_to_invite = []
            
            for request in self.stats["friend_requests"][:]:
                user_id = request["user_id"]
                request_time = datetime.fromisoformat(request["timestamp"])
                
                # Если пользователь теперь друг
                if user_id in friends:
                    # Проверяем, прошло ли достаточно времени
                    hours_passed = (current_time - request_time).total_seconds() / 3600
                    
                    if hours_passed >= self.config["invite_after_friendship_hours"]:
                        ready_to_invite.append(user_id)
                        # Удаляем из списка заявок
                        self.stats["friend_requests"].remove(request)
            
            # Добавляем в список для приглашения
            for user_id in ready_to_invite:
                # Проверяем, что его еще нет в списке
                existing_users = [f["user_id"] for f in self.stats["friends_to_invite"]]
                if user_id not in existing_users:
                    self.stats["friends_to_invite"].append({
                        "user_id": user_id,
                        "ready_since": current_time.isoformat()
                    })
            
            if ready_to_invite:
                logger.info(f"👥 {len(ready_to_invite)} новых друзей готовы к приглашению")
            
        except Exception as e:
            logger.error(f"Ошибка проверки друзей: {e}")
    
    def invite_friends_to_group_safe(self):
        """Безопасное приглашение друзей в группу"""
        if not self.stats["friends_to_invite"]:
            return
        
        # Лимит приглашений
        max_invites = min(
            len(self.stats["friends_to_invite"]),
            self.config["max_invites_per_day"] - self.stats["invites_today"],
            5  # Максимум 5 за раз для безопасности
        )
        
        if max_invites <= 0:
            return
        
        logger.info(f"📨 Отправка {max_invites} приглашений в группу")
        
        success_count = 0
        group_id = self.config["your_group_id"]
        
        for i in range(max_invites):
            friend = self.stats["friends_to_invite"].pop(0)
            user_id = friend["user_id"]
            
            try:
                self.vk.groups.invite(group_id=group_id, user_id=user_id)
                
                self.stats["invites_sent"] += 1
                self.stats["invites_today"] += 1
                self.stats["successful_invites"] += 1
                success_count += 1
                
                logger.info(f"✅ Приглашение отправлено: ID{user_id}")
                
                # Увеличенная задержка между приглашениями
                time.sleep(random.randint(30, 60))
                
            except Exception as e:
                error_msg = str(e).lower()
                if "flood" in error_msg:
                    logger.warning("🌊 Лимит приглашений! Остановка")
                    # Возвращаем пользователя в список
                    self.stats["friends_to_invite"].insert(0, friend)
                    break
                else:
                    logger.error(f"Ошибка приглашения ID{user_id}: {e}")
        
        logger.info(f"📊 Успешно отправлено приглашений: {success_count}")
    
    def run_friend_requests_cycle(self):
        """Цикл отправки заявок в друзья"""
        logger.info("🚀 ЗАПУСК ЦИКЛА ЗАЯВОК В ДРУЗЬЯ")
        
        # Ограничения на сегодня
        requests_left = self.config["max_friend_requests_per_day"] - self.stats["friend_requests_today"]
        if requests_left <= 0:
            logger.warning("⚠️ Достигнут дневной лимит заявок")
            return
        
        # Получаем все доступные группы
        all_groups = self.get_all_accessible_groups()
        
        if not all_groups:
            logger.warning("⚠️ Нет доступных групп для поиска")
            return
        
        # Собираем пользователей из нескольких групп
        all_users = []
        groups_processed = 0
        max_groups_per_cycle = 3  # Ограничиваем количество групп
        
        for group in all_groups:
            if groups_processed >= max_groups_per_cycle:
                break
                
            users = self.get_group_members_safe(group, max_count=500)
            if users:
                all_users.extend(users)
                groups_processed += 1
                logger.info(f"📊 Собрано {len(users)} пользователей из группы")
            
            # Задержка между группами
            time.sleep(5)
        
        if not all_users:
            logger.warning("⚠️ Не удалось получить пользователей ни из одной группы")
            return
        
        logger.info(f"📊 Всего собрано {len(all_users)} пользователей из {groups_processed} групп")
        
        # Фильтрация
        filtered_users = self.filter_users_advanced(all_users)
        
        if not filtered_users:
            logger.warning("⚠️ Нет подходящих пользователей после фильтрации")
            return
        
        # Отправляем заявки
        target_count = min(len(filtered_users), requests_left, 10)  # Максимум 10 за раз
        
        logger.info(f"🎯 Отправка {target_count} заявок")
        
        success_count = 0
        
        for i in range(target_count):
            user = filtered_users[i]
            
            if self.send_friend_request_safe(user["id"]):
                success_count += 1
            
            # Задержка между заявками
            if i < target_count - 1:
                delay = random.randint(
                    self.config["delay_between_actions"]["min"],
                    self.config["delay_between_actions"]["max"]
                )
                logger.info(f"⏳ Пауза {delay} секунд...")
                time.sleep(delay)
        
        logger.info(f"📈 РЕЗУЛЬТАТ: {success_count}/{target_count} успешных заявок")
        self.save_stats()
    
    def run_cycle(self):
        """Один цикл работы бота"""
        logger.info("🔄 НАЧАЛО ЦИКЛА РАБОТЫ")
        
        try:
            # Сброс дневных лимитов
            self.reset_daily_counters()
            
            # 1. Поиск новых групп (если мало групп)
            if len(self.stats["open_groups"]) < 10:
                logger.info("🔍 Мало групп, ищем новые...")
                self.discover_open_medical_groups()
            
            # 2. Проверка новых друзей
            self.check_new_friends()
            
            # 3. Приглашение друзей в группу
            self.invite_friends_to_group_safe()
            
            # 4. Отправка заявок в друзья
            self.run_friend_requests_cycle()
            
            # Сохранение статистики
            self.save_stats()
            
        except Exception as e:
            logger.error(f"Ошибка в цикле: {e}")
        
        # Отчет
        logger.info(f"""
📊 СТАТИСТИКА ЦИКЛА:
├── Заявок сегодня: {self.stats['friend_requests_today']}/{self.config['max_friend_requests_per_day']}
├── Приглашений сегодня: {self.stats['invites_today']}/{self.config['max_invites_per_day']}
├── Ожидает приглашения: {len(self.stats['friends_to_invite'])}
├── Успешных приглашений всего: {self.stats['successful_invites']}
├── Открытых групп найдено: {len(self.stats['open_groups'])}
└── Обработано пользователей: {len(self.stats['processed_users'])}
        """)
    
    def run_forever(self):
        """Непрерывная работа бота"""
        logger.info("🚀 ЗАПУСК БОТА В НЕПРЕРЫВНОМ РЕЖИМЕ")
        
        # Поиск открытых групп при старте
        if len(self.stats["open_groups"]) < 5:
            logger.info("🔍 Первичный поиск открытых групп...")
            self.discover_open_medical_groups()
        
        while True:
            try:
                # Проверяем время (работаем только днем для безопасности)
                current_hour = datetime.now().hour
                
                if 9 <= current_hour <= 21:  # Работаем с 9 до 21
                    self.run_cycle()
                    
                    # Интервал между циклами (2-4 часа)
                    sleep_minutes = random.randint(120, 240)
                    logger.info(f"⏰ Следующий цикл через {sleep_minutes} минут")
                    time.sleep(sleep_minutes * 60)
                    
                else:
                    # Ночью спим
                    logger.info("🌙 Ночной режим, спим до утра")
                    time.sleep(3600)  # 1 час
                    
            except KeyboardInterrupt:
                logger.info("⏹️ Остановка по команде пользователя")
                break
            except Exception as e:
                logger.error(f"❌ Критическая ошибка: {e}")
                logger.info("⏳ Пауза 30 минут перед перезапуском")
                time.sleep(1800)

def main():
    logger.info("🎯 МЕДИЦИНСКИЙ VK БОТ - ИСПРАВЛЕННАЯ ВЕРСИЯ")
    
    try:
        bot = VKMedicalBot()
        bot.run_forever()
    except Exception as e:
        logger.error(f"Фатальная ошибка: {e}")

if __name__ == "__main__":
    main()
