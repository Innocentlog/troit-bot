## Переменные окружения для BotHost (панель → бот → «Переменные окружения»)

Задаются в панели Bothost при создании/настройке бота. Никакие секреты не хранятся в git.

| Переменная | Значение | Обязательна |
|---|---|---|
| `BOT_TOKEN` | Токен от @BotFather | **да** (автоматически при создании, но можно задать вручную) |
| `ADMIN_IDS` | `397809686,126426602` | да |
| `CHANNEL_ID` | `@troizadm` | да |
| `SITE_URL` | `https://dmtroizahram.ru` | да |
| `BOT_API_KEY` | Ключ из `domains/config.php` на Джино (BOT_API_KEY) | **да** |
| `VK_TOKEN` | Токен VK (пусто = канал VK отключён) | нет |
| `MAX_TOKEN` | Токен MAX (пусто = канал MAX отключён) | нет |
| `MAX_CHAT_ID` | ID чата MAX | нет |
| `SCHEDULE_HEADER` | Заголовок поста расписания | нет |
| `API_BASE_URL` | Пусто = прямое подключение к api.telegram.org | нет |
| `PROXY_URL` | Пусто = без прокси | нет |
| `DATA_DIR` | `/app/data` (по умолчанию на BotHost) | нет |

## Проверка локально

```powershell
$env:BOT_TOKEN="123:abc"
$env:BOT_API_KEY="ключ"
python config.py
```
