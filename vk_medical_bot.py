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
            
        # Целевые медицинские группы (больше групп = больше пользователей)
        self.medical_groups = [
            'medstudents',       # Студенты-медики
            'medicine_students', # Медицинские студенты
            'medkolledge',      # Медколледжи
            'nursing_students',  # Студенты-медсестры
            'first_aid',        # Первая помощь
            'medicine_ru',      # Медицина России
            'health_care',      # Здравоохранение
            'medic_life',       # Жизнь медика
            'doctor_life',      # Жизнь врача
            'med_university',   # Медуниверситеты
            'pharmacy_students',# Студенты-фармацевты
            'medical_education',# Медицинское образование
            'future_doctors',   # Будущие врачи
            'med_practice',     # Медицинская практика
            'healthcare_workers' # Медработники
        ]
        
        # Ключевые слова для поиска групп
        self.medical_keywords = [
            'медицинский', 'медколледж', 'медуниверситет', 'медицина',
            'врач', 'доктор', 'медсестра', 'фармацевт', 'стоматолог',
            'педиатр', 'хирург', 'терапевт', 'медик', 'здравоохранение',
            'первая помощь', 'анатомия', 'физиология', 'фармакология'
        ]
        
        self.stats_file = "medical_bot_stats.json"
        self.load_stats()
        
    def load_config(self):
        """Максимальные безопасные лимиты"""
        self.config = {
            "access_token": os.getenv("VK_ACCESS_TOKEN"),
            "your_group_id": os.getenv("YOUR_GROUP_ID"),
            
            # МАКСИМАЛЬНЫЕ ЛИМИТЫ (но безопасные)
            "max_friend_requests_per_day": 100,      # ВК лимит ~100-150 в день
            "max_invites_per_day": 80,               # Лимит приглашений
            "max_searches_per_day": 50,              # Поиск новых групп
            
            # Более агрессивные интервалы
            "delay_between_actions": {
                "min": 30,   # 30 секунд минимум
                "max": 90    # 1.5 минуты максимум
            },
            
            # Быстрее приглашаем в группу
            "invite_after_friendship_hours": 2,     # Через 2 часа вместо дней
            
            # Фильтры для качественной аудитории
            "filters": {
                "age_min": 16,      # От 16 лет
                "age_max": 35,      # До 35 лет
                "last_seen_days": 7, # Активные за неделю
                "has_photo": True,   # Обязательно с фото
                "require_medical_interest": True  # Обязательно из мед.групп
            }
        }
        
    def load_stats(self):
        """Загрузка статистики"""
        try:
            if os.path.exists(self.stats_file):
                with open(self.stats_file, 'r', encoding='utf-8') as f:
                    self.stats = json.load(f)
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
            "discovered_groups": [],
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
    
    def discover_medical_groups(self):
        """Поиск новых медицинских групп"""
        logger.info("🔍 Поиск новых медицинских групп")
        
        new_groups = []
        
        for keyword in self.medical_keywords[:10]:  # Ограничиваем для экономии API
            try:
                time.sleep(2)  # Задержка между поисками
                
                response = self.vk.groups.search(
                    q=keyword,
                    count=20,
                    fields="members_count,activity"
                )
                
                for group in response["items"]:
                    # Фильтруем группы
                    if (group.get("members_count", 0) > 100 and 
                        group.get("members_count", 0) < 50000 and  # Не слишком большие
                        group["id"] not in [g["id"] for g in self.stats["discovered_groups"]]):
                        
                        new_groups.append({
                            "id": group["id"],
                            "name": group["name"],
                            "members_count": group.get("members_count", 0),
                            "screen_name": group.get("screen_name", ""),
                            "discovered_date": datetime.now().isoformat()
                        })
                        
            except Exception as e:
                logger.error(f"Ошибка поиска групп по ключевому слову '{keyword}': {e}")
                continue
        
        # Добавляем найденные группы
        self.stats["discovered_groups"].extend(new_groups)
        self.stats["groups_found"] += len(new_groups)
        
        logger.info(f"🎯 Найдено {len(new_groups)} новых медицинских групп")
        return new_groups
    
    def get_all_target_groups(self):
        """Получение всех целевых групп (базовые + найденные)"""
        all_groups = self.medical_groups.copy()
        
        # Добавляем найденные группы
        for group in self.stats["discovered_groups"]:
            all_groups.append(group["screen_name"] or str(group["id"]))
        
        return all_groups
    
    def get_group_members_optimized(self, group_identifier, max_count=2000):
        """Оптимизированное получение участников группы"""
        try:
            # Получаем ID группы
            if isinstance(group_identifier, str) and not group_identifier.isdigit():
                try:
                    group_info = self.vk.groups.getById(group_id=group_identifier)[0]
                    group_id = group_info["id"]
                    group_name = group_info["name"]
                except:
                    return []
            else:
                group_id = int(group_identifier)
                group_name = group_identifier
            
            logger.info(f"📥 Получение участников группы: {group_name}")
            
            members = []
            offset = 0
            batch_size = 1000
            
            while offset < max_count:
                time.sleep(1)  # Задержка между запросами
                
                try:
                    response = self.vk.groups.getMembers(
                        group_id=group_id,
                        offset=offset,
                        count=min(batch_size, max_count - offset),
                        fields="sex,bdate,city,last_seen,has_photo,connections"
                    )
                    
                    batch = response["items"]
                    if not batch:
                        break
                    
                    members.extend(batch)
                    offset += len(batch)
                    
                    if len(batch) < batch_size:
                        break
                        
                except Exception as e:
                    if "access_denied" in str(e).lower():
                        logger.warning(f"❌ Нет доступа к группе {group_name}")
                        break
                    else:
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
            else:
                continue  # Пропускаем без информации о последнем визите
            
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
            
            # Проверка пола (предпочтительно девушки, но не обязательно)
            # Медицина больше привлекает женщин
            
            filtered.append(user)
        
        logger.info(f"🎯 Отфильтровано {len(filtered)} качественных пользователей")
        return filtered
    
    def send_friend_request_fast(self, user_id):
        """Быстрая отправка заявки в друзья"""
        try:
            self.vk.friends.add(user_id=user_id)
            
            # Быстрое обновление статистики
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
                logger.warning("🤖 Капча! Пауза 10 минут")
                time.sleep(600)
                return False
            elif "blacklist" in error_msg or "denied" in error_msg:
                self.stats["blacklisted_users"].add(user_id)
                logger.info(f"❌ Пользователь ID{user_id} в черном списке")
            elif "flood" in error_msg:
                logger.warning("🌊 Флуд-контроль! Пауза 5 минут")
                time.sleep(300)
                return False
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
                self.stats["friends_to_invite"].append({
                    "user_id": user_id,
                    "ready_since": current_time.isoformat()
                })
            
            if ready_to_invite:
                logger.info(f"👥 {len(ready_to_invite)} новых друзей готовы к приглашению")
            
        except Exception as e:
            logger.error(f"Ошибка проверки друзей: {e}")
    
    def invite_friends_to_group_fast(self):
        """Быстрое приглашение друзей в группу"""
        if not self.stats["friends_to_invite"]:
            return
        
        # Лимит приглашений
        max_invites = min(
            len(self.stats["friends_to_invite"]),
            self.config["max_invites_per_day"] - self.stats["invites_today"],
            10  # Максимум 10 за раз
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
                
                # Небольшая задержка
                time.sleep(random.randint(15, 45))
                
            except Exception as e:
                logger.error(f"Ошибка приглашения ID{user_id}: {e}")
        
        logger.info(f"📊 Успешно отправлено приглашений: {success_count}")
    
    def run_mass_friend_requests(self):
        """Массовая отправка заявок в друзья"""
        logger.info("🚀 ЗАПУСК МАССОВОЙ ОБРАБОТКИ ЗАЯВОК")
        
        # Ограничения на сегодня
        requests_left = self.config["max_friend_requests_per_day"] - self.stats["friend_requests_today"]
        if requests_left <= 0:
            logger.warning("⚠️ Достигнут дневной лимит заявок")
            return
        
        # Получаем все целевые группы
        all_groups = self.get_all_target_groups()
        
        # Собираем пользователей из нескольких групп
        all_users = []
        groups_to_process = min(len(all_groups), 5)  # Максимум 5 групп за раз
        
        for group in all_groups[:groups_to_process]:
            users = self.get_group_members_optimized(group, max_count=1000)
            all_users.extend(users)
            
            # Небольшая задержка между группами
            time.sleep(3)
        
        logger.info(f"📊 Собрано {len(all_users)} пользователей из {groups_to_process} групп")
        
        # Фильтрация
        filtered_users = self.filter_users_advanced(all_users)
        
        if not filtered_users:
            logger.warning("⚠️ Нет подходящих пользователей")
            return
        
        # Отправляем заявки
        target_count = min(len(filtered_users), requests_left, 30)  # Максимум 30 за раз
        
        logger.info(f"🎯 Отправка {target_count} заявок")
        
        success_count = 0
        
        for i in range(target_count):
            user = filtered_users[i]
            
            if self.send_friend_request_fast(user["id"]):
                success_count += 1
            
            # Умная задержка
            if i < target_count - 1:
                delay = random.randint(
                    self.config["delay_between_actions"]["min"],
                    self.config["delay_between_actions"]["max"]
                )
                time.sleep(delay)
        
        logger.info(f"📈 РЕЗУЛЬТАТ: {success_count}/{target_count} успешных заявок")
        self.save_stats()
    
    def run_cycle(self):
        """Один цикл работы бота"""
        logger.info("🔄 НАЧАЛО ЦИКЛА РАБОТЫ")
        
        # Сброс дневных лимитов
        self.reset_daily_counters()
        
        # 1. Поиск новых групп (периодически)
        if len(self.stats["discovered_groups"]) < 20:
            self.discover_medical_groups()
        
        # 2. Проверка новых друзей
        self.check_new_friends()
        
        # 3. Приглашение друзей в группу
        self.invite_friends_to_group_fast()
        
        # 4. Отправка заявок в друзья
        self.run_mass_friend_requests()
        
        # Сохранение статистики
        self.save_stats()
        
        # Отчет
        logger.info(f"""
📊 СТАТИСТИКА ЦИКЛА:
├── Заявок сегодня: {self.stats['friend_requests_today']}/{self.config['max_friend_requests_per_day']}
├── Приглашений сегодня: {self.stats['invites_today']}/{self.config['max_invites_per_day']}
├── Ожидает приглашения: {len(self.stats['friends_to_invite'])}
├── Успешных приглашений всего: {self.stats['successful_invites']}
└── Найдено групп: {len(self.stats['discovered_groups'])}
        """)
    
    def run_forever(self):
        """Непрерывная работа бота"""
        logger.info("🚀 ЗАПУСК БОТА В НЕПРЕРЫВНОМ РЕЖИМЕ")
        
        while True:
            try:
                # Проверяем время (работаем только днем)
                current_hour = datetime.now().hour
                
                if 8 <= current_hour <= 22:  # Работаем с 8 до 22
                    self.run_cycle()
                    
                    # Интервал между циклами (1-2 часа)
                    sleep_minutes = random.randint(60, 120)
                    logger.info(f"⏰ Следующий цикл через {sleep_minutes} минут")
                    time.sleep(sleep_minutes * 60)
                    
                else:
                    # Ночью спим
                    logger.info("🌙 Ночной режим, спим до утра")
                    time.sleep(1800)  # 30 минут
                    
            except KeyboardInterrupt:
                logger.info("⏹️ Остановка по команде пользователя")
                break
            except Exception as e:
                logger.error(f"❌ Критическая ошибка: {e}")
                logger.info("⏳ Пауза 30 минут перед перезапуском")
                time.sleep(1800)

def main():
    logger.info("🎯 МЕДИЦИНСКИЙ VK БОТ - МАКСИМАЛЬНАЯ ЭФФЕКТИВНОСТЬ")
    
    try:
        bot = VKMedicalBot()
        bot.run_forever()
    except Exception as e:
        logger.error(f"Фатальная ошибка: {e}")

if __name__ == "__main__":
    main()
