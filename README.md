# 🌟 КРОК.Командировки

<div align="center">
  <img src="https://i.ibb.co/HpkL2PyJ/CROC-LOGO.png" alt="KROK Logo" style="border-radius: 10px; height: 200px">
  <br><br>
  <i>Автоматизированная система управления командировками</i>
  <br><br>
  <a href="https://github.com/petus1/krok_project?tab=readme-ov-file#-%D0%B2%D0%BE%D0%B7%D0%BC%D0%BE%D0%B6%D0%BD%D0%BE%D1%81%D1%82%D0%B8">Возможности</a> •
  <a href="https://github.com/petus1/krok_project#%EF%B8%8F-%D1%82%D0%B5%D1%85%D0%BD%D0%BE%D0%BB%D0%BE%D0%B3%D0%B8%D0%B8">Технологии</a> •
  <a href="#-установка-и-запуск">Установка</a> •
  <a href="#-тестовые-учетные-записи">Учетные записи</a>
  <br><br>
  <a href="https://github.com/petus1/krok_project"><img src="https://img.shields.io/badge/GitHub-View%20Repository-181717?style=for-the-badge&logo=github" alt="GitHub"></a>
</div>

---

## 🚀 Возможности

<div align="center">
  <table>
    <tr>
      <td align="center" width="50%">
        <img src="https://img.icons8.com/color/96/000000/manager.png" alt="Management">
        <h3>Управление заявками</h3>
        <p>Создание, просмотр, редактирование и отслеживание статусов заявок на командировки.</p>
      </td>
      <td align="center" width="50%">
        <img src="https://img.icons8.com/color/96/000000/approval.png" alt="Approval">
        <h3>Многоуровневое согласование</h3>
        <p>Поддержка ролей (Сотрудник, Руководитель, Главный руководитель) с разными правами доступа.</p>
      </td>
    </tr>
    <tr>
      <td align="center" width="50%">
        <img src="https://img.icons8.com/color/96/000000/calendar.png" alt="Planning">
        <h3>Планирование</h3>
        <p>Возможность создания "Планируемых" командировок, которые можно активировать позже.</p>
      </td>
      <td align="center" width="50%">
        <img src="https://img.icons8.com/color/96/000000/booking.png" alt="Booking">
        <h3>Управление бронированием</h3>
        <p>Интеграция с системой бронирования транспорта и проживания.</p>
      </td>
    </tr>
    <tr>
      <td align="center" width="50%">
        <img src="https://img.icons8.com/color/96/000000/shopping-cart.png" alt="Procurement">
        <h3>Управление закупками</h3>
        <p>Указание необходимости закупки материалов и отслеживание статуса.</p>
      </td>
      <td align="center" width="50%">
        <img src="https://img.icons8.com/color/96/000000/report-card.png" alt="Reporting">
        <h3>Отчетность и геолокация</h3>
        <p>Фиксация геопозиции, подтверждение пребывания, подготовка и проверка отчетов.</p>
      </td>
    </tr>
    <tr>
      <td align="center" width="50%">
        <img src="https://img.icons8.com/color/96/000000/admin-settings-male.png" alt="Roles">
        <h3>Гибкая система ролей</h3>
        <p>Четкое разделение прав доступа для разных типов пользователей (Администратор, Безопасность, Бухгалтерия, Кадры, Travel-координатор, Закупки).</p>
      </td>
      <td align="center" width="50%">
        <img src="https://img.icons8.com/color/96/000000/dashboard.png" alt="Dashboard">
        <h3>Администрирование</h3>
        <p>Управление пользователями, дашборд с аналитикой и статистикой.</p>
      </td>
    </tr>
  </table>
</div>

---

## 🛠️ Технологии

<div align="center">
  <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Flask-000000?style=for-the-badge&logo=flask&logoColor=white" alt="Flask">
  <img src="https://img.shields.io/badge/SQLAlchemy-333333?style=for-the-badge&logo=sqlalchemy&logoColor=white" alt="SQLAlchemy">
  <img src="https://img.shields.io/badge/PostgreSQL-316192?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL">
  <img src="https://img.shields.io/badge/HTML5-E34F26?style=for-the-badge&logo=html5&logoColor=white" alt="HTML5">
  <img src="https://img.shields.io/badge/Bootstrap-563D7C?style=for-the-badge&logo=bootstrap&logoColor=white" alt="Bootstrap">
  <img src="https://img.shields.io/badge/JavaScript-F7DF1E?style=for-the-badge&logo=javascript&logoColor=black" alt="JavaScript">
  <img src="https://img.shields.io/badge/python-dotenv-F1F1F1?style=for-the-badge&logo=python&logoColor=3776AB" alt="python-dotenv">
</div>

---

## 📋 Установка и запуск

<div align="center">
  <img src="https://i.ibb.co/v6s1rKTf/icons8-software-installer-96.png" alt="Install">
  <h3>Следуйте этим шагам, чтобы запустить приложение локально</h3>
</div>

### 1. Установите PostgreSQL

Следуйте инструкциям на официальном сайте:
[https://www.postgresql.org/download/](https://www.postgresql.org/download/)

**При установке:**
*   Запомните **имя пользователя администратора** (по умолчанию `postgres`).
*   Запомните **пароль** для этого пользователя.
*   Запомните **порт**, на котором запущен сервер (по умолчанию `5432`).
*   Создайте новую базу данных под пользователем `postgres`.
    *   Это можно сделать через `psql`:
        ```bash
        psql -U postgres -h localhost -p 5432
        ```
        Затем в консоли `psql`:
        ```sql
        CREATE DATABASE business_trips_db;
        \q
        ```

### 2. Клонируйте репозиторий

```bash
git clone https://github.com/petus1/krok_project.git  
cd krok_project
```

### 3. Создайте виртуальное окружение (рекомендуется)

```bash
python -m venv venv
```

*   **Windows:**
    ```bash
    venv\Scripts\activate
    ```
*   **macOS/Linux:**
    ```bash
    source venv/bin/activate
    ```

### 4. Установите зависимости

```bash
pip install -r requirements.txt
```

### 5. Настройте переменные окружения

Создайте файл `.env` в корне проекта (`krok_project/.env`) и укажите настройки подключения к базе данных:

```env
DATABASE_URL=postgresql://<ИМЯ_ПОЛЬЗОВАТЕЛЯ>:<ПАРОЛЬ>@localhost:5432/business_trips_db
```

Замените `<ИМЯ_ПОЛЬЗОВАТЕЛЯ>` и `<ПАРОЛЬ>` на учетные данные, которые вы использовали при установке PostgreSQL (или создайте специального пользователя для `business_trips_db` и используйте его).

### 6. Запустите приложение

Если вы ещё не запустили приложение в шаге 6, запустите его снова:

```bash
python app.py
```

<div align="center">
  <a href="http://127.0.0.1:5000"><img src="https://img.shields.io/badge/Запустить-Приложение-00C573?style=for-the-badge&logo=google-chrome&logoColor=white" alt="Run App"></a>
</div>

---

## 👤 Тестовые учетные записи

<div align="center">
  <table>
    <thead>
      <tr>
        <th>Роль</th>
        <th>Логин</th>
        <th>Пароль</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><strong>Администратор</strong></td>
        <td><code>admin</code></td>
        <td><code>admin123</code></td>
      </tr>
      <tr>
        <td><strong>Главный руководитель</strong></td>
        <td><code>gr</code></td>
        <td><code>gr123</code></td>
      </tr>
      <tr>
        <td><strong>Руководитель</strong></td>
        <td><code>r</code></td>
        <td><code>r123</code></td>
      </tr>
      <tr>
        <td><strong>Сотрудник</strong></td>
        <td><code>s</code></td>
        <td><code>s123</code></td>
      </tr>
    </tbody>
  </table>
</div>

---

<div align="center">
  <img src="https://i.postimg.cc/x1X918N8/success.gif" alt="Success">
  <h3>Готово! Приложение успешно установлено и запущено.</h3>
  <p>Наслаждайтесь удобным управлением командировками!</p>
</div>
