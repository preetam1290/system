# ============================================================================
# FIBONACCI ALERT SYSTEM - Simplified Version
# ============================================================================
# Author: Preetam
# Description: alert system for crypto trading
# ============================================================================

# Core imports
import pandas as pd
import numpy as np
import websocket
import json
import time
import requests
import os
from datetime import datetime
from binance.client import Client
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Suppress warnings
import warnings
warnings.filterwarnings('ignore')

class FibonacciAlertSystem:
    def __init__(self, api_key=None, api_secret=None, symbol=None, interval=None):
        """
        24/7 Fibonacci Alert System with Auto-Recovery
        
        Args:
            api_key: Binance API key (optional, will use env var if not provided)
            api_secret: Binance API secret (optional, will use env var if not provided)
            symbol: Trading pair (optional, will use env var if not provided)
            interval: Timeframe (optional, will use env var if not provided)
        """
        # Load configuration from environment variables
        self.api_key = api_key or os.getenv('BINANCE_API_KEY')
        self.api_secret = api_secret or os.getenv('BINANCE_API_SECRET')
        self.symbol = symbol or os.getenv('SYMBOL', 'ETHUSDT')
        self.interval = interval or os.getenv('INTERVAL', '5m')
        
        # Validate required credentials
        if not self.api_key or not self.api_secret:
            raise ValueError("Binance API credentials not found. Please set BINANCE_API_KEY and BINANCE_API_SECRET in .env file")
        
        self.client = Client(self.api_key, self.api_secret)
        self.df = pd.DataFrame()
        self.ws = None
        
    
        # Core parameters from environment variables
        self.swing_lookback = int(os.getenv('SWING_LOOKBACK', 249))
        self.ema_length = int(os.getenv('EMA_LENGTH', 50))
        
        # Volume parameters from environment variables
        self.vol_lookback = int(os.getenv('VOL_LOOKBACK', 30))
        self.vol_threshold = float(os.getenv('VOL_THRESHOLD', 2.0))
        self.ml_sensitivity = float(os.getenv('ML_SENSITIVITY', 2.0))
        
        # Alert system parameters from environment variables
        self.fib_tolerance = float(os.getenv('FIB_TOLERANCE', 0.1))  # Percentage tolerance for Fibonacci level matching
        self.last_fib_alert_time = {}  # Track last alert time for each level
        self.last_ema_alert_time = {}  # Track last alert time for EMA intersections
        self.alert_cooldown = int(os.getenv('ALERT_COOLDOWN', 300))  # 5 minutes cooldown between alerts for same level
        
        # 24/7 Reliability Features from environment variables
        self.max_bars = int(os.getenv('MAX_BARS', 500))  # Keep last 500 bars in DataFrame
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = int(os.getenv('MAX_RECONNECT_ATTEMPTS', 50))  # Increased for 24/7 operation
        self.reconnect_delay = 10  # Start with 10 seconds
        self.max_reconnect_delay = 300  # Max 5 minutes between reconnects
        self.is_running = True
        self.last_heartbeat = time.time()
        self.heartbeat_interval = 60  # Check connection every minute
        self.last_data_time = 0
        self.data_timeout = 600  # 10 minutes without data = reconnect
        
        # Performance tracking
        self.update_count = 0
        self.start_time = time.time()
        self.total_alerts_sent = 0
        self.connection_drops = 0
        
        # Telegram configuration from environment variables
        self.telegram_config = {
            'enable_telegram_alerts': os.getenv('ENABLE_TELEGRAM_ALERTS', 'true').lower() == 'true',
            'bot_token': os.getenv('TELEGRAM_BOT_TOKEN'),
            'chat_id': os.getenv('TELEGRAM_CHAT_ID')
        }
        
        print(f"🚀 Initializing 24/7 Advanced Technical Analysis System for {symbol} on {interval} timeframe...")
        print(f"📊 Fibonacci Alert System Enabled - Tolerance: ±{self.fib_tolerance}%")
        print(f"📈 EMA Intersection Alerts Enabled (9, 21, 50 periods)")
        print(f"🔄 Auto-reconnect enabled with {self.max_reconnect_attempts} max attempts")
        print(f"📱 Telegram Alerts: {'Enabled' if self.telegram_config.get('enable_telegram_alerts') else 'Disabled'}")
        
        # Send startup confirmation to Telegram
        self.send_startup_confirmation()
    
    def dispatch_alert(self, channel, priority, title, body, tag):
        """Multi-channel alert dispatcher"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Log to console with formatted output
        self._dispatch_to_console(channel, priority, title, body, timestamp)
        
        # Log to file
        self._dispatch_to_file(channel, priority, title, body, tag, timestamp)
        
        # Send Telegram notification (if configured)
        self._dispatch_to_telegram(channel, priority, title, body, tag, timestamp)
        
        # Increment alert counter
        self.total_alerts_sent += 1
    
    def _dispatch_to_console(self, channel, priority, title, body, timestamp):
        """Dispatch alert to console output"""
        priority_icons = {
            "low": "ℹ️",
            "medium": "⚠️", 
            "high": "🚨",
            "critical": "🔥"
        }
        
        icon = priority_icons.get(priority.lower(), "📢")
        border = "🚨" * 50 if priority.lower() in ["high", "critical"] else "=" * 50
        
        print(f"\n{border}")
        print(f"{icon} {title.upper()} {icon}")
        print(f"{border}")
        print(f"Channel: {channel.upper()}")
        print(f"Priority: {priority.upper()}")
        print(f"Time: {timestamp}")
        print(f"Symbol: {self.symbol}")
        print(f"\n{body}")
        print(f"{border}")
        if priority.lower() in ["high", "critical"]:
            print("Action Required: Check the market immediately!")
            print(f"{border}")
    
    def _dispatch_to_file(self, channel, priority, title, body, tag, timestamp):
        """Dispatch alert to log file"""
        try:
            log_filename = f"{channel}_alerts_{self.symbol}.log"
            with open(log_filename, "a", encoding='utf-8') as f:
                f.write(f"{timestamp} | {self.symbol} | {channel.upper()} | {priority.upper()} | {tag} | {title} | {body.replace(chr(10), ' ')}\n")
        except Exception as e:
            print(f"Error writing to alert log file: {e}")
    
    def _dispatch_to_telegram(self, channel, priority, title, body, tag, timestamp):
        """Dispatch alert to Telegram"""
        if not self.telegram_config.get('enable_telegram_alerts', False):
            return

        bot_token = self.telegram_config.get('bot_token')
        chat_id = self.telegram_config.get('chat_id')

        if not bot_token or bot_token == 'your_bot_token_here' or not chat_id or chat_id == 'your_chat_id_here':
            print("Warning: Telegram bot token or chat ID not configured properly")
            return

        priority_emojis = {
            "low": "ℹ️",
            "medium": "⚠️", 
            "high": "🚨",
            "critical": "🔥"
        }
        emoji = priority_emojis.get(priority.lower(), "📢")

        telegram_message = f"{emoji} {title.upper()} {emoji}\n\n"
        telegram_message += f"📊 Symbol: {self.symbol}\n"
        telegram_message += f"🕐 Time: {timestamp}\n"
        telegram_message += f"📋 Channel: {channel.upper()}\n"
        telegram_message += f"⚡ Priority: {priority.upper()}\n\n"
        telegram_message += f"{body}"

        try:
            response = requests.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={'chat_id': chat_id, 'text': telegram_message},
                timeout=10
            )
            response.raise_for_status()
            print(f"Telegram message sent successfully: {title}")

        except requests.exceptions.RequestException as e:
            print(f"Failed to send Telegram message: {e}")
            if e.response:
                error_description = e.response.json().get('description', 'Unknown error')
                print(f"Error details: {error_description}")
                if "chat not found" in error_description.lower():
                    print("TELEGRAM TROUBLESHOOTING:")
                    print("1. Make sure the bot is added to your chat/group")
                    print("2. Send a message to the bot first if it's a private chat")
                    print(f"3. Verify chat ID: {chat_id}")
                    print("4. For groups, chat ID should start with '-'")
    
    
    def calculate_rsi(self, prices, period=14):
        """Calculate RSI using pandas (no TA-Lib needed)"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def calculate_ema(self, prices, period):
        """Calculate EMA using pandas (no TA-Lib needed)"""
        return prices.ewm(span=period, adjust=False).mean()
    
    def calculate_sma(self, prices, period):
        """Calculate Simple Moving Average"""
        return prices.rolling(window=period).mean()
        
    def get_historical_data(self, limit=500):
        """Get historical kline data from Binance"""
        try:
            klines = self.client.get_historical_klines(
                self.symbol, self.interval, f"{limit} hours ago UTC"
            )
            
            data = []
            for kline in klines:
                data.append({
                    'timestamp': pd.to_datetime(kline[0], unit='ms'),
                    'open': float(kline[1]),
                    'high': float(kline[2]),
                    'low': float(kline[3]),
                    'close': float(kline[4]),
                    'volume': float(kline[5])
                })
            
            self.df = pd.DataFrame(data)
            self.df.set_index('timestamp', inplace=True)
            print(f"Loaded {len(self.df)} historical bars")
            return True
            
        except Exception as e:
            print(f"Error getting historical data: {e}")
            return False

    def calculate_volume_ml_indicators(self):
        """Calculate Volume ML indicators matching Pine Script logic"""
        if len(self.df) < self.vol_lookback:
            return
        
        # Basic volume statistics
        self.df['vol_avg'] = self.df['volume'].rolling(window=self.vol_lookback).mean()
        self.df['vol_std'] = self.df['volume'].rolling(window=self.vol_lookback).std()
        self.df['vol_normalized'] = (self.df['volume'] - self.df['vol_avg']) / self.df['vol_std']
        
        # Price and volume changes
        self.df['price_change'] = self.df['close'].diff()
        self.df['volume_change'] = self.df['volume'].diff()
        
        # Volume-Price correlation
        self.df['vp_correlation'] = self.df['price_change'].rolling(20).corr(self.df['volume_change'])
        
        # Volume RSI and EMAs (using custom functions)
        self.df['vol_rsi'] = self.calculate_rsi(self.df['volume'], 14)
        self.df['vol_ema_short'] = self.calculate_ema(self.df['volume'], 8)
        self.df['vol_ema_long'] = self.calculate_ema(self.df['volume'], 21)
        self.df['vol_momentum'] = ((self.df['vol_ema_short'] - self.df['vol_ema_long']) / self.df['vol_ema_long']) * 100
        
        # Volume patterns
        self.df['vol_spike'] = self.df['volume'] > (self.df['vol_avg'] * self.vol_threshold)
        self.df['vol_dry_up'] = self.df['volume'] < (self.df['vol_avg'] * 0.5)
        self.df['vol_increasing'] = (self.df['volume'] > self.df['volume'].shift(1)) & (self.df['volume'].shift(1) > self.df['volume'].shift(2))
        self.df['vol_decreasing'] = (self.df['volume'] < self.df['volume'].shift(1)) & (self.df['volume'].shift(1) < self.df['volume'].shift(2))
        
        # Smart Money Flow Analysis
        hlc2 = (self.df['high'] + self.df['low']) / 2
        self.df['buying_pressure'] = np.where(self.df['close'] > hlc2, self.df['volume'], 0)
        self.df['selling_pressure'] = np.where(self.df['close'] < hlc2, self.df['volume'], 0)
        
        self.df['smart_money_flow'] = (self.df['buying_pressure'] - self.df['selling_pressure']).rolling(21).mean()
        self.df['smart_money_ratio'] = (self.df['smart_money_flow'] / self.df['vol_avg']) * 100
        
        # VWAP and deviation (cumulative calculation reset daily)
        hlc3 = (self.df['high'] + self.df['low'] + self.df['close']) / 3
        
        # Simple VWAP calculation (you might want to reset this daily in production)
        cumulative_volume = self.df['volume'].cumsum()
        cumulative_vol_price = (hlc3 * self.df['volume']).cumsum()
        self.df['vwap'] = cumulative_vol_price / cumulative_volume
        
        # For a more accurate daily VWAP, you'd need to reset at market open
        # Here's a rolling VWAP approximation for the last 100 periods
        rolling_periods = min(100, len(self.df))
        rolling_vol_price = (hlc3 * self.df['volume']).rolling(rolling_periods).sum()
        rolling_volume = self.df['volume'].rolling(rolling_periods).sum()
        self.df['vwap'] = rolling_vol_price / rolling_volume
        
        self.df['vwap_deviation'] = ((self.df['close'] - self.df['vwap']) / self.df['vwap']) * 100
        
    def calculate_volume_ml_score(self):
        """Calculate Volume ML Score matching Pine Script logic"""
        if len(self.df) == 0:
            return
        
        vol_ml_score = pd.Series(0.0, index=self.df.index)
        
        # Volume spike analysis
        condition1 = self.df['vol_spike'] & (self.df['price_change'] > 0)
        condition2 = self.df['vol_spike'] & (self.df['price_change'] < 0)
        vol_ml_score = np.where(condition1, vol_ml_score + 30, vol_ml_score)
        vol_ml_score = np.where(condition2, vol_ml_score - 25, vol_ml_score)
        
        # Volume momentum
        condition3 = self.df['vol_momentum'] > 10
        condition4 = self.df['vol_momentum'] < -10
        vol_ml_score = np.where(condition3, vol_ml_score + 20, vol_ml_score)
        vol_ml_score = np.where(condition4, vol_ml_score - 15, vol_ml_score)
        
        # Smart money flow
        condition5 = self.df['smart_money_ratio'] > 5
        condition6 = self.df['smart_money_ratio'] < -5
        vol_ml_score = np.where(condition5, vol_ml_score + 25, vol_ml_score)
        vol_ml_score = np.where(condition6, vol_ml_score - 20, vol_ml_score)
        
        # Volume-price correlation
        condition7 = self.df['vp_correlation'] > 0.3
        condition8 = self.df['vp_correlation'] < -0.3
        vol_ml_score = np.where(condition7, vol_ml_score + 15, vol_ml_score)
        vol_ml_score = np.where(condition8, vol_ml_score - 10, vol_ml_score)
        
        # VWAP analysis
        condition9 = (self.df['close'] > self.df['vwap']) & (self.df['volume'] > self.df['vol_avg'])
        condition10 = (self.df['close'] < self.df['vwap']) & (self.df['volume'] > self.df['vol_avg'])
        vol_ml_score = np.where(condition9, vol_ml_score + 10, vol_ml_score)
        vol_ml_score = np.where(condition10, vol_ml_score - 10, vol_ml_score)
        
        # Volume pattern recognition
        condition11 = self.df['vol_increasing'] & (self.df['price_change'] > 0)
        condition12 = self.df['vol_decreasing'] & (self.df['price_change'] < 0)
        vol_ml_score = np.where(condition11, vol_ml_score + 15, vol_ml_score)
        vol_ml_score = np.where(condition12, vol_ml_score - 10, vol_ml_score)
        
        # Apply ML sensitivity
        vol_ml_score = vol_ml_score * self.ml_sensitivity
        
        self.df['vol_ml_score'] = vol_ml_score
        
        # Volume trend classification
        self.df['vol_trend'] = np.where(
            self.df['vol_ml_score'] > 30, 'ACCUMULATION',
            np.where(self.df['vol_ml_score'] < -30, 'DISTRIBUTION', 'NEUTRAL')
        )
    
    def calculate_fibonacci_levels(self):
        """Calculate Fibonacci retracement levels (Magic Zone Strategy)"""
        if len(self.df) < self.swing_lookback:
            return
        
        # Calculate swing high and low
        self.df['swing_high'] = self.df['high'].rolling(window=self.swing_lookback).max()
        self.df['swing_low'] = self.df['low'].rolling(window=self.swing_lookback).min()
        
        # Calculate Fibonacci levels
        price_range = self.df['swing_high'] - self.df['swing_low']
        self.df['fib_595'] = self.df['swing_high'] - price_range * 0.595
        self.df['fib_650'] = self.df['swing_high'] - price_range * 0.65
        
        # Calculate EMAs (using custom function)
        self.df['ema_9'] = self.calculate_ema(self.df['close'], 9)
        self.df['ema_21'] = self.calculate_ema(self.df['close'], 21)
        self.df['ema_50'] = self.calculate_ema(self.df['close'], self.ema_length)
        
        # Calculate RSI with period 9
        self.df['rsi'] = self.calculate_rsi(self.df['close'], 9)
    
    def check_fibonacci_alerts(self):
        """Check if current price matches Fibonacci levels and send alerts"""
        if len(self.df) == 0:
            return []
        
        latest = self.df.iloc[-1]
        current_price = latest['close']
        current_time = time.time()
        alerts = []
        
        # Check if we have valid Fibonacci levels
        if pd.isna(latest['fib_595']) or pd.isna(latest['fib_650']):
            return alerts
        
        fib_595 = latest['fib_595']
        fib_650 = latest['fib_650']
        
        # Calculate tolerance range for each level
        tolerance_595 = fib_595 * (self.fib_tolerance / 100)
        tolerance_650 = fib_650 * (self.fib_tolerance / 100)
        
        # Check Fibonacci 59.5% level
        if (abs(current_price - fib_595) <= tolerance_595):
            alert_key = 'fib_595'
            if (alert_key not in self.last_fib_alert_time or 
                current_time - self.last_fib_alert_time[alert_key] > self.alert_cooldown):
                
                self.send_fibonacci_alert('59.5%', current_price, fib_595)
                self.last_fib_alert_time[alert_key] = current_time
                
                # Add to alerts list for return
                alerts.append({
                    'level': '59.5%',
                    'current_price': current_price,
                    'fib_price': fib_595,
                    'difference': abs(current_price - fib_595),
                    'position': 'ABOVE' if current_price > fib_595 else 'BELOW'
                })
        
        # Check Fibonacci 65.0% level
        if (abs(current_price - fib_650) <= tolerance_650):
            alert_key = 'fib_650'
            if (alert_key not in self.last_fib_alert_time or 
                current_time - self.last_fib_alert_time[alert_key] > self.alert_cooldown):
                
                self.send_fibonacci_alert('65.0%', current_price, fib_650)
                self.last_fib_alert_time[alert_key] = current_time
                
                # Add to alerts list for return
                alerts.append({
                    'level': '65.0%',
                    'current_price': current_price,
                    'fib_price': fib_650,
                    'difference': abs(current_price - fib_650),
                    'position': 'ABOVE' if current_price > fib_650 else 'BELOW'
                })
        
        return alerts
    
    def send_fibonacci_alert(self, fib_level, current_price, fib_price):
        """Send Fibonacci level alert using the multi-channel dispatch system"""
        # Determine priority based on how close the price is to the Fibonacci level
        difference = abs(current_price - fib_price)
        tolerance = fib_price * (self.fib_tolerance / 100)
        
        if difference <= tolerance * 0.5:
            priority = "high"
        else:
            priority = "medium"
        
        # Create alert title and body
        title = f"Fib {fib_level} Hit"
        position = "ABOVE" if current_price > fib_price else "BELOW"
        
        formatted_text = f"""Hey! Preetam need to look the market bro!
Current Price: ${current_price:.4f}
Fibonacci {fib_level} Level: ${fib_price:.4f}
Difference: ${difference:.4f}
Price is {position} Fibonacci {fib_level}"""
        
        # Dispatch alert through multi-channel system
        self.dispatch_alert(
            channel="fibonacci",
            priority=priority,
            title=title,
            body=formatted_text,
            tag=f"fib_{fib_level.replace('.', '').replace('%', '')}"
        )
    
    def check_ema_intersection_alerts(self):
        """Check for EMA intersections and send alerts"""
        if len(self.df) < 2:
            return []
        
        current = self.df.iloc[-1]
        previous = self.df.iloc[-2]
        current_time = time.time()
        alerts = []
        
        # Check if we have valid EMA values
        required_emas = ['ema_9', 'ema_21', 'ema_50']
        for ema in required_emas:
            if pd.isna(current[ema]) or pd.isna(previous[ema]):
                return alerts
        
        # Get current and previous EMA values
        current_ema_9 = current['ema_9']
        current_ema_21 = current['ema_21']
        current_ema_50 = current['ema_50']
        
        previous_ema_9 = previous['ema_9']
        previous_ema_21 = previous['ema_21']
        previous_ema_50 = previous['ema_50']
        
        # Check for EMA 9 crossing above EMA 21
        if (previous_ema_9 <= previous_ema_21 and current_ema_9 > current_ema_21):
            alert_key = 'ema_9_cross_21_up'
            if (alert_key not in self.last_ema_alert_time or 
                current_time - self.last_ema_alert_time[alert_key] > self.alert_cooldown):
                
                self.send_ema_intersection_alert('EMA 9 Crosses Above EMA 21', 'BULLISH', current['close'])
                self.last_ema_alert_time[alert_key] = current_time
                
                alerts.append({
                    'type': 'EMA 9 x 21 Bullish',
                    'ema_9': current_ema_9,
                    'ema_21': current_ema_21,
                    'price': current['close']
                })
        
        # Check for EMA 9 crossing below EMA 21
        elif (previous_ema_9 >= previous_ema_21 and current_ema_9 < current_ema_21):
            alert_key = 'ema_9_cross_21_down'
            if (alert_key not in self.last_ema_alert_time or 
                current_time - self.last_ema_alert_time[alert_key] > self.alert_cooldown):
                
                self.send_ema_intersection_alert('EMA 9 Crosses Below EMA 21', 'BEARISH', current['close'])
                self.last_ema_alert_time[alert_key] = current_time
                
                alerts.append({
                    'type': 'EMA 9 x 21 Bearish',
                    'ema_9': current_ema_9,
                    'ema_21': current_ema_21,
                    'price': current['close']
                })
        
        # Check for EMA 21 crossing above EMA 50
        if (previous_ema_21 <= previous_ema_50 and current_ema_21 > current_ema_50):
            alert_key = 'ema_21_cross_50_up'
            if (alert_key not in self.last_ema_alert_time or 
                current_time - self.last_ema_alert_time[alert_key] > self.alert_cooldown):
                
                self.send_ema_intersection_alert('EMA 21 Crosses Above EMA 50', 'BULLISH', current['close'])
                self.last_ema_alert_time[alert_key] = current_time
                
                alerts.append({
                    'type': 'EMA 21 x 50 Bullish',
                    'ema_21': current_ema_21,
                    'ema_50': current_ema_50,
                    'price': current['close']
                })
        
        # Check for EMA 21 crossing below EMA 50
        elif (previous_ema_21 >= previous_ema_50 and current_ema_21 < current_ema_50):
            alert_key = 'ema_21_cross_50_down'
            if (alert_key not in self.last_ema_alert_time or 
                current_time - self.last_ema_alert_time[alert_key] > self.alert_cooldown):
                
                self.send_ema_intersection_alert('EMA 21 Crosses Below EMA 50', 'BEARISH', current['close'])
                self.last_ema_alert_time[alert_key] = current_time
                
                alerts.append({
                    'type': 'EMA 21 x 50 Bearish',
                    'ema_21': current_ema_21,
                    'ema_50': current_ema_50,
                    'price': current['close']
                })
        
        # Check for EMA 9 crossing above EMA 50
        if (previous_ema_9 <= previous_ema_50 and current_ema_9 > current_ema_50):
            alert_key = 'ema_9_cross_50_up'
            if (alert_key not in self.last_ema_alert_time or 
                current_time - self.last_ema_alert_time[alert_key] > self.alert_cooldown):
                
                self.send_ema_intersection_alert('EMA 9 Crosses Above EMA 50', 'BULLISH', current['close'])
                self.last_ema_alert_time[alert_key] = current_time
                
                alerts.append({
                    'type': 'EMA 9 x 50 Bullish',
                    'ema_9': current_ema_9,
                    'ema_50': current_ema_50,
                    'price': current['close']
                })
        
        # Check for EMA 9 crossing below EMA 50
        elif (previous_ema_9 >= previous_ema_50 and current_ema_9 < current_ema_50):
            alert_key = 'ema_9_cross_50_down'
            if (alert_key not in self.last_ema_alert_time or 
                current_time - self.last_ema_alert_time[alert_key] > self.alert_cooldown):
                
                self.send_ema_intersection_alert('EMA 9 Crosses Below EMA 50', 'BEARISH', current['close'])
                self.last_ema_alert_time[alert_key] = current_time
                
                alerts.append({
                    'type': 'EMA 9 x 50 Bearish',
                    'ema_9': current_ema_9,
                    'ema_50': current_ema_50,
                    'price': current['close']
                })
        
        # Check for triple EMA bullish alignment (9 > 21 > 50)
        if (current_ema_9 > current_ema_21 > current_ema_50 and 
            not (previous_ema_9 > previous_ema_21 > previous_ema_50)):
            alert_key = 'triple_ema_bullish'
            if (alert_key not in self.last_ema_alert_time or 
                current_time - self.last_ema_alert_time[alert_key] > self.alert_cooldown):
                
                self.send_ema_intersection_alert('Triple EMA Bullish Alignment', 'STRONG_BULLISH', current['close'])
                self.last_ema_alert_time[alert_key] = current_time
                
                alerts.append({
                    'type': 'Triple EMA Bullish',
                    'ema_9': current_ema_9,
                    'ema_21': current_ema_21,
                    'ema_50': current_ema_50,
                    'price': current['close']
                })
        
        # Check for triple EMA bearish alignment (9 < 21 < 50)
        elif (current_ema_9 < current_ema_21 < current_ema_50 and 
              not (previous_ema_9 < previous_ema_21 < previous_ema_50)):
            alert_key = 'triple_ema_bearish'
            if (alert_key not in self.last_ema_alert_time or 
                current_time - self.last_ema_alert_time[alert_key] > self.alert_cooldown):
                
                self.send_ema_intersection_alert('Triple EMA Bearish Alignment', 'STRONG_BEARISH', current['close'])
                self.last_ema_alert_time[alert_key] = current_time
                
                alerts.append({
                    'type': 'Triple EMA Bearish',
                    'ema_9': current_ema_9,
                    'ema_21': current_ema_21,
                    'ema_50': current_ema_50,
                    'price': current['close']
                })
        
        return alerts
    
    def send_ema_intersection_alert(self, intersection_type, trend, current_price):
        """Send EMA intersection alert using the multi-channel dispatch system"""
        # Determine priority based on trend strength
        if trend in ['STRONG_BULLISH', 'STRONG_BEARISH']:
            priority = "high"
        else:
            priority = "medium"
        
        # Get current EMA values
        latest = self.df.iloc[-1]
        ema_9 = latest['ema_9']
        ema_21 = latest['ema_21']
        ema_50 = latest['ema_50']
        
        # Create alert title and body
        title = f"EMA Intersection - {trend}"
        
        if trend == 'STRONG_BULLISH':
            trend_emoji = "🚀"
            trend_desc = "STRONG BULLISH SIGNAL"
        elif trend == 'STRONG_BEARISH':
            trend_emoji = "🐻"
            trend_desc = "STRONG BEARISH SIGNAL"
        elif trend == 'BULLISH':
            trend_emoji = "📈"
            trend_desc = "BULLISH SIGNAL"
        else:
            trend_emoji = "📉"
            trend_desc = "BEARISH SIGNAL"
        
        formatted_text = f"""{trend_emoji} {intersection_type} {trend_emoji}

Hey Preetam! EMA intersection detected!

Signal: {trend_desc}
Current Price: ${current_price:.4f}

EMA Values:
• EMA 9: ${ema_9:.4f}
• EMA 21: ${ema_21:.4f}
• EMA 50: ${ema_50:.4f}

Time to check the charts! 📊"""
        
        # Dispatch alert through multi-channel system
        self.dispatch_alert(
            channel="ema_intersection",
            priority=priority,
            title=title,
            body=formatted_text,
            tag=f"ema_{trend.lower()}"
        )
    
    def send_startup_confirmation(self):
        """Send startup confirmation message to Telegram"""
        if not self.telegram_config.get('enable_telegram_alerts', False):
            return
        
        # Get current time in IST
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        startup_message = f"""🚀 ALERT SYSTEM STARTED 🚀

✅ Connection Status: SUCCESSFUL
📊 Symbol: {self.symbol}
⏰ Timeframe: {self.interval}
🕐 Start Time: {current_time}

📋 Active Monitoring:
• 📊 Fibonacci Levels (59.5% & 65.0%)
• 📈 EMA Crossovers (9, 21, 50)
• 📊 Volume Analysis & ML Scoring
• 🎯 Technical Confluence Signals

⚙️ Settings:
• Alert Tolerance: ±{self.fib_tolerance}%
• Cooldown Period: {self.alert_cooldown} seconds
• Max Reconnects: {self.max_reconnect_attempts}

🔔 You will receive alerts for:
✓ Fibonacci level hits
✓ EMA intersections
✓ Volume anomalies
✓ High confluence signals

System is now monitoring live data! 📈📉"""
        
        try:
            bot_token = self.telegram_config.get('bot_token')
            chat_id = self.telegram_config.get('chat_id')
            
            if bot_token and chat_id:
                response = requests.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={'chat_id': chat_id, 'text': startup_message},
                    timeout=10
                )
                response.raise_for_status()
                print("✅ Startup confirmation sent to Telegram successfully!")
            else:
                print("⚠️ Telegram credentials not configured for startup notification")
                
        except Exception as e:
            print(f"❌ Failed to send startup confirmation to Telegram: {e}")
    
    def calculate_confluence_score(self):
        """Calculate confluence score"""
        if len(self.df) == 0:
            return
        
        confluence_score = pd.Series(0.0, index=self.df.index)
        
        # Trend momentum
        momentum = self.df['close'].diff(5)
        confluence_score = np.where(momentum > 0, confluence_score + 15, confluence_score - 15)
        
        # Market structure analysis
        recent_high = self.df['high'].rolling(10).max().shift(1)
        recent_low = self.df['low'].rolling(10).min().shift(1)
        
        market_structure = np.where(
            self.df['close'] > recent_high, 1,
            np.where(self.df['close'] < recent_low, -1, 0)
        )
        
        confluence_score = np.where(market_structure == 1, confluence_score + 10, confluence_score)
        confluence_score = np.where(market_structure == -1, confluence_score - 10, confluence_score)
        
        # Volume confluence
        confluence_score = np.where(self.df['vol_ml_score'] > 20, confluence_score + 20, confluence_score)
        confluence_score = np.where(self.df['vol_ml_score'] < -20, confluence_score - 15, confluence_score)
        
        self.df['confluence_score'] = confluence_score
    
    def analyze_current_state(self):
        """Analyze current market state and return summary"""
        if len(self.df) == 0:
            return None
        
        latest = self.df.iloc[-1]
        current_time = self.df.index[-1].tz_localize('UTC').tz_convert('Asia/Kolkata')
        
        # Handle NaN values safely
        def safe_round(value, decimals=2):
            return round(float(value), decimals) if pd.notna(value) else 0.0
        
        # Volume analysis
        vol_ratio = latest['volume'] / latest['vol_avg'] if pd.notna(latest['vol_avg']) and latest['vol_avg'] > 0 else 0
        vol_ratio_status = 'HIGH' if vol_ratio > 1.5 else 'LOW' if vol_ratio < 0.5 else 'NORMAL'
        
        vol_rsi_status = 'OVERBOUGHT' if pd.notna(latest['vol_rsi']) and latest['vol_rsi'] > 70 else 'OVERSOLD' if pd.notna(latest['vol_rsi']) and latest['vol_rsi'] < 30 else 'NEUTRAL'
        
        vol_momentum_status = 'BULLISH' if pd.notna(latest['vol_momentum']) and latest['vol_momentum'] > 10 else 'BEARISH' if pd.notna(latest['vol_momentum']) and latest['vol_momentum'] < -10 else 'NEUTRAL'
        
        smart_money_status = 'BUYING' if pd.notna(latest['smart_money_ratio']) and latest['smart_money_ratio'] > 5 else 'SELLING' if pd.notna(latest['smart_money_ratio']) and latest['smart_money_ratio'] < -5 else 'NEUTRAL'
        
        vp_correlation_status = 'STRONG +' if pd.notna(latest['vp_correlation']) and latest['vp_correlation'] > 0.3 else 'STRONG -' if pd.notna(latest['vp_correlation']) and latest['vp_correlation'] < -0.3 else 'WEAK'
        
        vwap_dev_status = 'ABOVE' if pd.notna(latest['vwap_deviation']) and latest['vwap_deviation'] > 1 else 'BELOW' if pd.notna(latest['vwap_deviation']) and latest['vwap_deviation'] < -1 else 'NEUTRAL'
        
        # RSI analysis
        rsi_value = safe_round(latest['rsi'], 1)
        if rsi_value >= 70:
            rsi_status = 'OVERBOUGHT'
        elif rsi_value <= 30:
            rsi_status = 'OVERSOLD'
        else:
            rsi_status = 'NEUTRAL'
        
        # Volume pattern
        if pd.notna(latest['vol_spike']) and latest['vol_spike']:
            vol_pattern = 'SPIKE'
        elif pd.notna(latest['vol_dry_up']) and latest['vol_dry_up']:
            vol_pattern = 'DRY UP'
        elif pd.notna(latest['vol_increasing']) and latest['vol_increasing']:
            vol_pattern = 'RISING'
        elif pd.notna(latest['vol_decreasing']) and latest['vol_decreasing']:
            vol_pattern = 'FALLING'
        else:
            vol_pattern = 'STABLE'
        
        analysis = {
            'timestamp': current_time,
            'price': safe_round(latest['close']),
            'volume_analysis': {
                'vol_ratio': safe_round(vol_ratio, 2),
                'vol_ratio_status': vol_ratio_status,
                'vol_rsi': safe_round(latest['vol_rsi'], 1),
                'vol_rsi_status': vol_rsi_status,
                'vol_momentum': safe_round(latest['vol_momentum'], 1),
                'vol_momentum_status': vol_momentum_status,
                'smart_money_ratio': safe_round(latest['smart_money_ratio'], 1),
                'smart_money_status': smart_money_status,
                'vp_correlation': safe_round(latest['vp_correlation'], 2),
                'vp_correlation_status': vp_correlation_status,
                'vwap_deviation': safe_round(latest['vwap_deviation'], 2),
                'vwap_dev_status': vwap_dev_status,
                'vol_pattern': vol_pattern,
                'vol_ml_score': safe_round(latest['vol_ml_score'], 0),
                'vol_trend': latest['vol_trend'] if pd.notna(latest['vol_trend']) else 'NEUTRAL'
            },
            'technical_levels': {
                'ema_9': safe_round(latest['ema_9'], 2),
                'ema_21': safe_round(latest['ema_21'], 2),
                'ema_50': safe_round(latest['ema_50'], 2),
                'fib_595': safe_round(latest['fib_595'], 2),
                'fib_650': safe_round(latest['fib_650'], 2),
                'vwap': safe_round(latest['vwap'], 2),
                'rsi': rsi_value,
                'rsi_status': rsi_status
            },
            'confluence_score': safe_round(latest['confluence_score'], 0)
        }
        
        return analysis
    
    def on_message(self, ws, message):
        """Handle WebSocket messages"""
        try:
            data = json.loads(message)
            kline = data['k']
            
            # Only process closed candles
            if kline['x']:  # is_closed
                new_data = {
                    'timestamp': pd.to_datetime(kline['t'], unit='ms'),
                    'open': float(kline['o']),
                    'high': float(kline['h']),
                    'low': float(kline['l']),
                    'close': float(kline['c']),
                    'volume': float(kline['v'])
                }
                
                # Add new data to DataFrame
                new_row = pd.DataFrame([new_data])
                new_row.set_index('timestamp', inplace=True)
                self.df = pd.concat([self.df, new_row])
                
                # Keep only last max_bars
                if len(self.df) > self.max_bars:
                    self.df = self.df.tail(self.max_bars)
                
                # Recalculate all indicators
                self.calculate_volume_ml_indicators()
                self.calculate_volume_ml_score()
                self.calculate_fibonacci_levels()
                self.calculate_confluence_score()
                
                # Check for Fibonacci alerts
                self.check_fibonacci_alerts()
                
                # Check for EMA intersection alerts
                self.check_ema_intersection_alerts()
                
                # Print analysis
                analysis = self.analyze_current_state()
                if analysis:
                    self.print_analysis(analysis)
                    
        except Exception as e:
            print(f"Error processing WebSocket message: {e}")
    
    def on_error(self, ws, error):
        """Handle WebSocket errors"""
        print(f"WebSocket error: {error}")
    
    def on_close(self, ws, close_status_code, close_msg):
        """Handle WebSocket close"""
        print("WebSocket connection closed")
    
    def on_open(self, ws):
        """Handle WebSocket open"""
        print(f"WebSocket connected for {self.symbol}")
    
    def print_analysis(self, analysis):
        """Print formatted analysis"""
        print("\n" + "="*80)
        print(f"ADVANCED TECHNICAL ANALYSIS - {self.symbol}")
        print(f"Time: {analysis['timestamp']}")
        print(f"Price: ${analysis['price']:.2f}")
        print("="*80)
        
        print("\nVOLUME ML ANALYSIS:")
        vol = analysis['volume_analysis']
        print(f"  Vol Ratio: {vol['vol_ratio']} ({vol['vol_ratio_status']})")
        print(f"  Vol RSI: {vol['vol_rsi']} ({vol['vol_rsi_status']})")
        print(f"  Vol Momentum: {vol['vol_momentum']}% ({vol['vol_momentum_status']})")
        print(f"  Smart Money: {vol['smart_money_ratio']}% ({vol['smart_money_status']})")
        print(f"  VP Correlation: {vol['vp_correlation']} ({vol['vp_correlation_status']})")
        print(f"  VWAP Deviation: {vol['vwap_deviation']}% ({vol['vwap_dev_status']})")
        print(f"  Volume Pattern: {vol['vol_pattern']}")
        print(f"  ML Score: {vol['vol_ml_score']} ({vol['vol_trend']})")
        
        print(f"\nTECHNICAL LEVELS:")
        levels = analysis['technical_levels']
        print(f"  EMA 9: ${levels['ema_9']:.2f}")
        print(f"  EMA 21: ${levels['ema_21']:.2f}")
        print(f"  EMA 50: ${levels['ema_50']:.2f}")
        print(f"  Fibonacci 59.5%: ${levels['fib_595']:.2f}")
        print(f"  Fibonacci 65.0%: ${levels['fib_650']:.2f}")
        print(f"  VWAP: ${levels['vwap']:.2f}")
        print(f"  RSI(9): {levels['rsi']} ({levels['rsi_status']})")
        
        print(f"\nCONFLUENCE SCORE: {analysis['confluence_score']}")
        
        # Calculate distance to Fibonacci levels
        current_price = analysis['price']
        fib_595_distance = abs(current_price - levels['fib_595']) if levels['fib_595'] > 0 else 0
        fib_650_distance = abs(current_price - levels['fib_650']) if levels['fib_650'] > 0 else 0
        
        print(f"\nFIBONACCI DISTANCE:")
        print(f"  Distance to 59.5%: ${fib_595_distance:.4f}")
        print(f"  Distance to 65.0%: ${fib_650_distance:.4f}")
        
        # Check for volume alerts
        if vol['vol_ml_score'] > 50:
            self.dispatch_alert(
                channel="volume",
                priority="high",
                title="Strong Volume Accumulation",
                body=f"Volume ML Score: {vol['vol_ml_score']}\nVolume Trend: {vol['vol_trend']}\nPattern: {vol['vol_pattern']}",
                tag="vol_accumulation"
            )
        elif vol['vol_ml_score'] < -50:
            self.dispatch_alert(
                channel="volume",
                priority="high",
                title="Strong Volume Distribution",
                body=f"Volume ML Score: {vol['vol_ml_score']}\nVolume Trend: {vol['vol_trend']}\nPattern: {vol['vol_pattern']}",
                tag="vol_distribution"
            )
        
        # Check for confluence alerts
        if analysis['confluence_score'] > 70:
            self.dispatch_alert(
                channel="confluence",
                priority="medium",
                title="High Bullish Confluence",
                body=f"Confluence Score: {analysis['confluence_score']}\nRSI: {levels['rsi']} ({levels['rsi_status']})\nEMA 50: ${levels['ema_50']:.2f}",
                tag="confluence_bullish"
            )
        elif analysis['confluence_score'] < -70:
            self.dispatch_alert(
                channel="confluence",
                priority="medium",
                title="High Bearish Confluence",
                body=f"Confluence Score: {analysis['confluence_score']}\nRSI: {levels['rsi']} ({levels['rsi_status']})\nEMA 50: ${levels['ema_50']:.2f}",
                tag="confluence_bearish"
            )
    
    def start_live_analysis(self):
        """Start live analysis with WebSocket"""
        # Get historical data first
        if not self.get_historical_data():
            print("Failed to get historical data")
            return
        
        # Calculate initial indicators
        self.calculate_volume_ml_indicators()
        self.calculate_volume_ml_score()
        self.calculate_fibonacci_levels()
        self.calculate_confluence_score()
        
        # Check for initial Fibonacci alerts
        self.check_fibonacci_alerts()
        
        # Check for initial EMA intersection alerts
        self.check_ema_intersection_alerts()
        
         # Print initial analysis
        analysis = self.analyze_current_state()
        if analysis:
            self.print_analysis(analysis)
        
        # Start WebSocket for live updates
        socket = f"wss://stream.binance.com:9443/ws/{self.symbol.lower()}@kline_{self.interval}"
        
        self.ws = websocket.WebSocketApp(
            socket,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open
        )
        
        print(f"Starting live analysis for {self.symbol}...")
        print("📊 Fibonacci Alert System is ACTIVE!")
        print("📈 EMA Intersection Alert System is ACTIVE!")
        print(f"📊 Alert tolerance: ±{self.fib_tolerance}%")
        print(f"📊 Alert cooldown: {self.alert_cooldown} seconds")
        print("🎯 Monitoring: EMA 9, EMA 21, EMA 50 crossovers")
        self.ws.run_forever()

# Production usage
if __name__ == "__main__":
    print("🔧 Loading configuration from environment variables...")
    
    # Initialize the analysis system using environment variables
    try:
        analyzer = FibonacciAlertSystem()
        print("✅ Configuration loaded successfully!")
    except ValueError as e:
        print(f"❌ Configuration Error: {e}")
        print("Please check your .env file and ensure all required variables are set.")
        exit(1)
    except Exception as e:
        print(f"💥 Initialization Error: {e}")
        exit(1)
    
    print("🚀 Starting Advanced Technical Analysis System...")
    print(f"📊 Symbol: {analyzer.symbol}")
    print(f"⏱️ Interval: {analyzer.interval}")
    print(f"📱 Telegram Alerts: {'Enabled' if analyzer.telegram_config.get('enable_telegram_alerts') else 'Disabled'}")
    print(f"🎯 Fib Tolerance: ±{analyzer.fib_tolerance}%")
    print(f"⏰ Alert Cooldown: {analyzer.alert_cooldown} seconds")
    print(f"🔄 Max Reconnects: {analyzer.max_reconnect_attempts}")
    print("=" * 60)
    
    # Start live analysis
    try:
        analyzer.start_live_analysis()
    except KeyboardInterrupt:
        print("\n⛔ Stopping analysis...")
        print("📊 Trading system stopped by user.")
    except Exception as e:
        print(f"💥 Error: {e}")
        print("Check your API credentials and internet connection.")
