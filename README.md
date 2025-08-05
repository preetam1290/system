# Fibonacci Alert System 🚨

A real-time 24/7 crypto trading alert system using Binance WebSocket API. The bot monitors **Fibonacci retracement levels**, **EMA crossovers**, **volume-based ML indicators**, and **technical confluence scores** to send alerts via console and Telegram.

---

## 🚀 Features

- 📊 Fibonacci Zone Alerts (59.5% & 65.0%)
- 📈 EMA Intersection Detection (9, 21, 50)
- 📉 Volume Momentum and Smart Money Analysis
- 🤖 ML-Based Volume Scoring System
- 📡 Binance WebSocket Live Data
- 🔔 Telegram Alert Integration
- 🔄 Auto-reconnect and cooldown system

---

## 📁 Project Structure

```
fibonacci-bot/
├── system_adv_1.py
├── requirements.txt
├── .env
└── README.md
```

---

## ⚙️ Setup Instructions

### 1. Clone the repo

```bash
git clone https://your-repo-url.git
cd fibonacci-bot
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Create a `.env` file

```env
BINANCE_API_KEY=your_api_key
BINANCE_API_SECRET=your_api_secret
SYMBOL=ETHUSDT
INTERVAL=5m
ENABLE_TELEGRAM_ALERTS=true
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
```

### 4. Run the bot

```bash
python system_adv_1.py
```

---

## 📬 Telegram Setup

1. Create a Telegram bot via [@BotFather](https://t.me/BotFather)
2. Get your bot token
3. Start a chat with the bot or add it to a group
4. Get your chat ID using [@userinfobot](https://t.me/userinfobot) or an API call

---

## 🧠 Author

**Preetam Panda**  
🚀 Built for serious traders with automation in mind.

---

## 📝 License

This project is under the MIT License.
