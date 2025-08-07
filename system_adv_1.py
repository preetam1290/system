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
from datetime import datetime, timezone
import pytz
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
        
        
        # Alert system parameters from environment variables
        self.base_fib_tolerance = float(os.getenv('FIB_TOLERANCE', 0.1))  # Base percentage tolerance for Fibonacci level matching
        self.fib_tolerance = self.base_fib_tolerance  # Dynamic tolerance (will be adjusted by ATR)
        self.last_fib_alert_time = {}  # Track last alert time for each level
        self.last_ema_alert_time = {}  # Track last alert time for EMA intersections
        self.alert_cooldown = int(os.getenv('ALERT_COOLDOWN', 300))  # 5 minutes cooldown between alerts for same level
        
        # ATR-based dynamic tolerance parameters
        self.atr_period = int(os.getenv('ATR_PERIOD', 14))  # ATR calculation period
        self.atr_multiplier = float(os.getenv('ATR_MULTIPLIER', 1.5))  # ATR multiplier for dynamic tolerance
        self.enable_atr_tolerance = os.getenv('ENABLE_ATR_TOLERANCE', 'true').lower() == 'true'
        
        # ATR Signal Generation Parameters
        self.enable_atr_signals = os.getenv('ENABLE_ATR_SIGNALS', 'true').lower() == 'true'
        self.atr_signal_lookback = int(os.getenv('ATR_SIGNAL_LOOKBACK', 20))  # Lookback for ATR comparison
        self.atr_expansion_threshold = float(os.getenv('ATR_EXPANSION_THRESHOLD', 1.5))  # ATR expansion multiplier
        self.atr_contraction_threshold = float(os.getenv('ATR_CONTRACTION_THRESHOLD', 0.7))  # ATR contraction multiplier
        self.atr_breakout_threshold = float(os.getenv('ATR_BREAKOUT_THRESHOLD', 2.0))  # Strong breakout multiplier
        self.last_atr_signal_time = {}  # Track last ATR signal time
        self.atr_signal_cooldown = int(os.getenv('ATR_SIGNAL_COOLDOWN', 180))  # 3 minutes cooldown for ATR signals
        
        # ATR-based TP/SL parameters for ETH 5-minute timeframe
        self.tp_atr_multiplier = float(os.getenv('TP_ATR_MULTIPLIER', 2.0))  # Take profit: 2x ATR
        self.sl_atr_multiplier = float(os.getenv('SL_ATR_MULTIPLIER', 1.0))  # Stop loss: 1x ATR
        
        # Simplified Indian Trading Sessions
        self.enable_session_awareness = os.getenv('ENABLE_SESSION_AWARENESS', 'true').lower() == 'true'
        self.session_parameters = {
            'morning': {
                'name': '🌅 Morning Session',
                'ist_start': 9,   # 9:00 AM IST
                'ist_end': 15,    # 3:00 PM IST
                'fib_tolerance_multiplier': float(os.getenv('MORNING_FIB_MULT', 1.0)),
                'alert_cooldown_multiplier': float(os.getenv('MORNING_COOLDOWN_MULT', 1.0)),
                'description': 'Indian market open + European session'
            },
            'evening': {
                'name': '🌆 Evening Session', 
                'ist_start': 18,  # 6:00 PM IST
                'ist_end': 2,     # 2:00 AM IST (next day)
                'fib_tolerance_multiplier': float(os.getenv('EVENING_FIB_MULT', 1.2)),
                'alert_cooldown_multiplier': float(os.getenv('EVENING_COOLDOWN_MULT', 0.8)),
                'description': 'US market active - high volatility'
            },
            'night': {
                'name': '🌙 Night Session',
                'ist_start': 2,   # 2:00 AM IST
                'ist_end': 9,     # 9:00 AM IST
                'fib_tolerance_multiplier': float(os.getenv('NIGHT_FIB_MULT', 0.9)),
                'alert_cooldown_multiplier': float(os.getenv('NIGHT_COOLDOWN_MULT', 1.3)),
                'description': 'Asian session - lower volatility'
            }
        }
        
        self.current_session = 'morning'  # Default session
        self.last_session_update = 0
        
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
        print(f"📊 Fibonacci Alert System Enabled - Base Tolerance: ±{self.base_fib_tolerance}%")
        print(f"📈 EMA Intersection Alerts Enabled (9, 21, 50 periods)")
        print(f"🔄 Auto-reconnect enabled with {self.max_reconnect_attempts} max attempts")
        print(f"📱 Telegram Alerts: {'Enabled' if self.telegram_config.get('enable_telegram_alerts') else 'Disabled'}")
        print(f"📊 ATR Dynamic Tolerance: {'Enabled' if self.enable_atr_tolerance else 'Disabled'} (Period: {self.atr_period}, Multiplier: {self.atr_multiplier})")
        print(f"📈 ATR Signal Generation: {'Enabled' if self.enable_atr_signals else 'Disabled'} (Expansion: {self.atr_expansion_threshold}x, Contraction: {self.atr_contraction_threshold}x)")
        print(f"🌍 Session-Aware Parameters: {'Enabled' if self.enable_session_awareness else 'Disabled'}")
        
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
    
    def calculate_atr(self, high, low, close, period=14):
        """Calculate Average True Range (ATR)"""
        if len(high) < period + 1:
            return pd.Series([0] * len(high), index=high.index)
        
        # Calculate True Range components
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        
        # True Range is the maximum of the three
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # ATR is the exponential moving average of True Range
        atr = true_range.ewm(span=period, adjust=False).mean()
        return atr
    
    def calculate_sma(self, prices, period):
        """Calculate Simple Moving Average"""
        return prices.rolling(window=period).mean()
    
    def get_current_session(self):
        """Determine current trading session based on Indian Standard Time (IST)"""
        if not self.enable_session_awareness:
            return 'morning'  # Default session
        
        # Get current time in IST
        ist_tz = pytz.timezone('Asia/Kolkata')
        current_time = datetime.now(ist_tz)
        ist_hour = current_time.hour
        
        # Simple IST-based session determination
        if 9 <= ist_hour < 15:      # 9:00 AM to 3:00 PM IST - Morning Session
            return 'morning'
        elif 18 <= ist_hour or ist_hour < 2:  # 6:00 PM to 2:00 AM IST - Evening Session  
            return 'evening'
        else:  # 2:00 AM to 9:00 AM IST - Night Session
            return 'night'
    
    def update_session_parameters(self):
        """Update parameters based on current trading session"""
        if not self.enable_session_awareness:
            return
        
        current_time = time.time()
        # Update session every 5 minutes
        if current_time - self.last_session_update < 300:
            return
        
        new_session = self.get_current_session()
        
        if new_session != self.current_session:
            self.current_session = new_session
            session_params = self.session_parameters[new_session]
            
            # Update parameters based on session
            base_tolerance = self.base_fib_tolerance
            if hasattr(self, 'current_atr_adjustment'):
                base_tolerance = self.current_atr_adjustment
            
            self.fib_tolerance = base_tolerance * session_params['fib_tolerance_multiplier']
            
            # Send session change alert
            self.send_session_change_alert(new_session, session_params)
            
        self.last_session_update = current_time
    
    def send_session_change_alert(self, session, params):
        """Send alert when trading session changes (IST-based)"""
        # Get current IST time
        ist_tz = pytz.timezone('Asia/Kolkata')
        current_time = datetime.now(ist_tz)
        
        # Session info
        session_info = {
            'morning': {
                'emoji': '🌅',
                'name': 'Morning Session (9AM-3PM IST)',
                'market': 'Indian + European markets active'
            },
            'evening': {
                'emoji': '🌆', 
                'name': 'Evening Session (6PM-2AM IST)',
                'market': 'US markets active - highest volatility'
            },
            'night': {
                'emoji': '🌙',
                'name': 'Night Session (2AM-9AM IST)', 
                'market': 'Asian markets - lower volatility'
            }
        }
        
        info = session_info[session]
        
        title = f"Session Change: {info['emoji']} {session.upper()}"
        body = f"""{info['emoji']} TRADING SESSION CHANGED!

New Session: {info['name']}
IST Time: {current_time.strftime('%I:%M %p')}
Date: {current_time.strftime('%d-%m-%Y')}

🎯 Market Info:
{info['market']}

⚙️ Adjusted Settings:
• Fib Tolerance: {params['fib_tolerance_multiplier']}x (±{self.fib_tolerance:.3f}%)
• Alert Cooldown: {params['alert_cooldown_multiplier']}x

Hey Preetam! Session changed - settings optimized for current market hours! 🚀"""
        
        self.dispatch_alert(
            channel="session",
            priority="low",
            title=title,
            body=body,
            tag=f"session_{session}"
        )
    
    def update_atr_tolerance(self):
        """Update Fibonacci tolerance based on ATR (volatility)"""
        if not self.enable_atr_tolerance or len(self.df) < self.atr_period + 1:
            return
        
        # Calculate ATR
        if 'atr' not in self.df.columns:
            self.df['atr'] = self.calculate_atr(self.df['high'], self.df['low'], self.df['close'], self.atr_period)
        
        latest_atr = self.df['atr'].iloc[-1]
        latest_price = self.df['close'].iloc[-1]
        
        if pd.isna(latest_atr) or latest_atr == 0 or pd.isna(latest_price) or latest_price == 0:
            return
        
        # Calculate ATR as percentage of current price
        atr_percentage = (latest_atr / latest_price) * 100
        
        # Adjust tolerance based on ATR
        atr_adjusted_tolerance = self.base_fib_tolerance + (atr_percentage * self.atr_multiplier)
        
        # Apply session multiplier if enabled
        if self.enable_session_awareness:
            session_params = self.session_parameters[self.current_session]
            atr_adjusted_tolerance *= session_params['fib_tolerance_multiplier']
        
        # Limit tolerance to reasonable bounds (min 0.05%, max 2.0%)
        self.fib_tolerance = max(0.05, min(2.0, atr_adjusted_tolerance))
        self.current_atr_adjustment = atr_adjusted_tolerance
        
        # Send ATR update alert if tolerance changed significantly
        tolerance_change = abs(self.fib_tolerance - self.base_fib_tolerance) / self.base_fib_tolerance
        if tolerance_change > 0.5:  # 50% change threshold
            self.send_atr_tolerance_alert(latest_atr, atr_percentage, tolerance_change)
    
    def send_atr_tolerance_alert(self, atr_value, atr_percentage, tolerance_change):
        """Send alert when ATR-based tolerance changes significantly"""
        title = "ATR Tolerance Update"
        
        change_direction = "INCREASED" if self.fib_tolerance > self.base_fib_tolerance else "DECREASED"
        change_emoji = "📈" if change_direction == "INCREASED" else "📉"
        
        body = f"""{change_emoji} ATR-Based Tolerance Adjustment!

Market volatility has changed significantly!

📊 Current ATR: ${atr_value:.4f}
📐 ATR %: {atr_percentage:.3f}% of price
🎯 Base Tolerance: ±{self.base_fib_tolerance:.3f}%
🎯 New Dynamic Tolerance: ±{self.fib_tolerance:.3f}%
📊 Change: {tolerance_change*100:.1f}%

🌍 Current Session: {self.current_session.upper()}

Tolerance has been {change_direction} to adapt to current market volatility!

Hey Preetam! Market volatility adjusted - tolerance updated for better signals!"""
        
        priority = "medium" if tolerance_change > 1.0 else "low"
        
        self.dispatch_alert(
            channel="atr",
            priority=priority,
            title=title,
            body=body,
            tag="atr_tolerance_update"
        )
    
    def generate_atr_signals(self):
        """Generate trading signals based on ATR levels and volatility analysis"""
        if not self.enable_atr_signals or len(self.df) < self.atr_signal_lookback + self.atr_period:
            return
        
        if 'atr' not in self.df.columns:
            return
        
        current_time = time.time()
        latest = self.df.iloc[-1]
        current_atr = latest['atr']
        current_price = latest['close']
        
        if pd.isna(current_atr) or current_atr == 0:
            return
        
        # Calculate ATR statistics for signal generation
        atr_series = self.df['atr'].tail(self.atr_signal_lookback)
        atr_mean = atr_series.mean()
        atr_std = atr_series.std()
        
        if pd.isna(atr_mean) or pd.isna(atr_std) or atr_mean == 0:
            return
        
        # ATR as percentage of price for normalization
        atr_percentage = (current_atr / current_price) * 100
        atr_mean_percentage = (atr_mean / current_price) * 100
        
        # Calculate ATR z-score (how many standard deviations from mean)
        atr_zscore = (current_atr - atr_mean) / atr_std if atr_std > 0 else 0
        
        # Store ATR metrics in DataFrame for analysis
        self.df.loc[self.df.index[-1], 'atr_mean'] = atr_mean
        self.df.loc[self.df.index[-1], 'atr_zscore'] = atr_zscore
        self.df.loc[self.df.index[-1], 'atr_percentage'] = atr_percentage
        
        # Generate different types of ATR signals
        signals = []
        
        # 1. ATR EXPANSION SIGNAL (Volatility Increasing)
        if current_atr > atr_mean * self.atr_expansion_threshold:
            signal_key = 'atr_expansion'
            if (signal_key not in self.last_atr_signal_time or 
                current_time - self.last_atr_signal_time[signal_key] > self.atr_signal_cooldown):
                
                self.send_atr_expansion_signal(current_atr, atr_mean, atr_percentage, atr_zscore)
                self.last_atr_signal_time[signal_key] = current_time
                signals.append('ATR_EXPANSION')
        
        # 2. ATR CONTRACTION SIGNAL (Volatility Decreasing)
        elif current_atr < atr_mean * self.atr_contraction_threshold:
            signal_key = 'atr_contraction'
            if (signal_key not in self.last_atr_signal_time or 
                current_time - self.last_atr_signal_time[signal_key] > self.atr_signal_cooldown):
                
                self.send_atr_contraction_signal(current_atr, atr_mean, atr_percentage, atr_zscore)
                self.last_atr_signal_time[signal_key] = current_time
                signals.append('ATR_CONTRACTION')
        
        # 3. EXTREME VOLATILITY BREAKOUT (Very High ATR)
        if current_atr > atr_mean * self.atr_breakout_threshold and atr_zscore > 2.0:
            signal_key = 'atr_breakout'
            if (signal_key not in self.last_atr_signal_time or 
                current_time - self.last_atr_signal_time[signal_key] > self.atr_signal_cooldown):
                
                self.send_atr_breakout_signal(current_atr, atr_mean, atr_percentage, atr_zscore)
                self.last_atr_signal_time[signal_key] = current_time
                signals.append('ATR_BREAKOUT')
        
        # 4. ATR SQUEEZE SETUP (Very Low Volatility - Potential Breakout Setup)
        elif atr_zscore < -1.5 and current_atr < atr_mean * 0.6:
            signal_key = 'atr_squeeze'
            if (signal_key not in self.last_atr_signal_time or 
                current_time - self.last_atr_signal_time[signal_key] > self.atr_signal_cooldown * 2):  # Longer cooldown for squeeze
                
                self.send_atr_squeeze_signal(current_atr, atr_mean, atr_percentage, atr_zscore)
                self.last_atr_signal_time[signal_key] = current_time
                signals.append('ATR_SQUEEZE')
        
        # 5. ATR TREND SIGNALS (Combined with price action)
        self.generate_atr_trend_signals(current_atr, atr_mean, atr_percentage, current_time)
        
        return signals
    
    def calculate_tp_sl_levels(self, current_price, current_atr, signal_direction):
        """Calculate TP and SL levels based on ATR for ETH 5min"""
        # Use current ATR for calculations
        atr_value = current_atr
        
        if signal_direction == 'LONG':
            # Long position
            stop_loss = current_price - (atr_value * self.sl_atr_multiplier)
            take_profit = current_price + (atr_value * self.tp_atr_multiplier)
        else:
            # Short position  
            stop_loss = current_price + (atr_value * self.sl_atr_multiplier)
            take_profit = current_price - (atr_value * self.tp_atr_multiplier)
        
        # Calculate risk/reward ratio
        risk = abs(current_price - stop_loss)
        reward = abs(take_profit - current_price)
        rr_ratio = reward / risk if risk > 0 else 0
        
        return {
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'risk': risk,
            'reward': reward,
            'rr_ratio': rr_ratio
        }
    
    def send_atr_expansion_signal(self, current_atr, atr_mean, atr_percentage, atr_zscore):
        """Send simplified ATR expansion signal with TP/SL"""
        current_price = self.df['close'].iloc[-1]
        
        # Determine signal direction based on recent price action
        price_change_5 = self.df['close'].iloc[-1] - self.df['close'].iloc[-6]  # 5 periods ago
        signal_direction = 'LONG' if price_change_5 > 0 else 'SHORT'
        
        # Calculate TP/SL levels
        levels = self.calculate_tp_sl_levels(current_price, current_atr, signal_direction)
        
        title = "ATR Expansion Signal"
        
        body = f"""ATR EXPANSION - {signal_direction} SIGNAL

Price: ${current_price:.2f}
ATR: ${current_atr:.2f} ({(current_atr/atr_mean):.1f}x avg)
Direction: {signal_direction}

Trade Setup:
Entry: ${current_price:.2f}
Stop Loss: ${levels['stop_loss']:.2f}
Take Profit: ${levels['take_profit']:.2f}
Risk: ${levels['risk']:.2f}
Reward: ${levels['reward']:.2f}
R/R: {levels['rr_ratio']:.1f}

Session: {self.current_session.upper()}"""
        
        priority = "high" if atr_zscore > 2.0 else "medium"
        
        self.dispatch_alert(
            channel="atr_signals",
            priority=priority,
            title=title,
            body=body,
            tag="atr_expansion"
        )
    
    def send_atr_contraction_signal(self, current_atr, atr_mean, atr_percentage, atr_zscore):
        """Send ATR contraction signal (volatility decreasing)"""
        title = "📉 ATR Contraction Signal"
        
        body = f"""📉 VOLATILITY CONTRACTION DETECTED

📊 Market volatility is decreasing

📈 Current ATR: ${current_atr:.4f}
📊 Average ATR: ${atr_mean:.4f}
📐 ATR %: {atr_percentage:.3f}% of price
🎯 Z-Score: {atr_zscore:.2f}
📏 Contraction: {(current_atr/atr_mean):.2f}x average

🌍 Session: {self.current_session.upper()}

💡 SIGNAL IMPLICATIONS:
• Smaller price movements expected
• Range-bound trading likely
• Tighter stop losses appropriate
• Look for consolidation patterns

Hey Preetam! Market is calming down - range trading mode! 📊"""
        
        self.dispatch_alert(
            channel="atr_signals",
            priority="low",
            title=title,
            body=body,
            tag="atr_contraction"
        )
    
    def send_atr_breakout_signal(self, current_atr, atr_mean, atr_percentage, atr_zscore):
        """Send extreme volatility breakout signal"""
        title = "🚨 EXTREME VOLATILITY BREAKOUT!"
        
        body = f"""🚨 EXTREME VOLATILITY BREAKOUT! 🚨

⚡ MAJOR MARKET MOVEMENT DETECTED!

🔥 Current ATR: ${current_atr:.4f}
📊 Average ATR: ${atr_mean:.4f}
📐 ATR %: {atr_percentage:.3f}% of price
🎯 Z-Score: {atr_zscore:.2f} (EXTREME!)
📏 Breakout: {(current_atr/atr_mean):.2f}x average

🌍 Session: {self.current_session.upper()}

🚨 CRITICAL IMPLICATIONS:
• MAJOR trend change likely in progress
• Massive price movements expected
• Old support/resistance may break
• High momentum trading opportunity
• Use very wide stops or no stops initially

🔴 IMMEDIATE ACTION REQUIRED!
Hey Preetam! This is a MAJOR volatility event - check charts NOW! 🚨"""
        
        self.dispatch_alert(
            channel="atr_signals",
            priority="critical",
            title=title,
            body=body,
            tag="atr_extreme_breakout"
        )
    
    def send_atr_squeeze_signal(self, current_atr, atr_mean, atr_percentage, atr_zscore):
        """Send ATR squeeze signal (potential breakout setup)"""
        title = "⚡ ATR Squeeze Setup"
        
        body = f"""⚡ VOLATILITY SQUEEZE DETECTED ⚡

🎯 Potential breakout setup forming!

📈 Current ATR: ${current_atr:.4f}
📊 Average ATR: ${atr_mean:.4f}
📐 ATR %: {atr_percentage:.3f}% of price
🎯 Z-Score: {atr_zscore:.2f} (Very Low!)
📏 Squeeze: {(current_atr/atr_mean):.2f}x average

🌍 Session: {self.current_session.upper()}

💡 SETUP IMPLICATIONS:
• Market coiling for potential breakout
• Low volatility often precedes big moves
• Look for consolidation patterns
• Prepare for directional breakout
• Good risk/reward setups possible

⏰ WATCH FOR:
• Range breakouts
• Momentum acceleration
• Price pattern confirmation

Hey Preetam! Market is squeezing - big move coming! Get ready! ⚡"""
        
        self.dispatch_alert(
            channel="atr_signals",
            priority="medium",
            title=title,
            body=body,
            tag="atr_squeeze_setup"
        )
    
    def generate_atr_trend_signals(self, current_atr, atr_mean, atr_percentage, current_time):
        """Generate ATR-based trend signals combined with price action"""
        if len(self.df) < 5:
            return
        
        latest = self.df.iloc[-1]
        previous = self.df.iloc[-2]
        
        current_price = latest['close']
        previous_price = previous['close']
        price_change = current_price - previous_price
        price_change_pct = (price_change / previous_price) * 100
        
        # ATR Momentum Signal (High ATR + Strong Price Move)
        if (current_atr > atr_mean * 1.3 and abs(price_change_pct) > atr_percentage * 0.5):
            signal_key = f'atr_momentum_{"bull" if price_change > 0 else "bear"}'
            if (signal_key not in self.last_atr_signal_time or 
                current_time - self.last_atr_signal_time[signal_key] > self.atr_signal_cooldown):
                
                self.send_atr_momentum_signal(current_atr, atr_mean, price_change_pct, price_change > 0)
                self.last_atr_signal_time[signal_key] = current_time
        
        # ATR Reversal Signal (High ATR + Price rejection)
        if hasattr(latest, 'ema_21') and not pd.isna(latest['ema_21']):
            ema_21 = latest['ema_21']
            wick_size = max(latest['high'] - max(latest['open'], latest['close']), 
                          min(latest['open'], latest['close']) - latest['low'])
            
            if (current_atr > atr_mean * 1.2 and wick_size > current_atr * 0.5):
                reversal_direction = "bullish" if latest['close'] > ema_21 and latest['low'] < ema_21 else "bearish"
                if latest['close'] < ema_21 and latest['high'] > ema_21:
                    reversal_direction = "bearish"
                
                signal_key = f'atr_reversal_{reversal_direction}'
                if (signal_key not in self.last_atr_signal_time or 
                    current_time - self.last_atr_signal_time[signal_key] > self.atr_signal_cooldown * 1.5):
                    
                    self.send_atr_reversal_signal(current_atr, atr_mean, wick_size, reversal_direction)
                    self.last_atr_signal_time[signal_key] = current_time
    
    def send_atr_momentum_signal(self, current_atr, atr_mean, price_change_pct, is_bullish):
        """Send ATR momentum signal"""
        direction = "BULLISH" if is_bullish else "BEARISH"
        emoji = "🚀" if is_bullish else "🐻"
        title = f"{emoji} ATR Momentum Signal - {direction}"
        
        body = f"""{emoji} ATR MOMENTUM SIGNAL {emoji}

📊 High volatility + strong price move detected!

📈 Direction: {direction}
💰 Price Change: {price_change_pct:+.3f}%
📊 Current ATR: ${current_atr:.4f}
📊 Average ATR: ${atr_mean:.4f}
📏 ATR Ratio: {(current_atr/atr_mean):.2f}x

🌍 Session: {self.current_session.upper()}

💡 MOMENTUM SIGNAL:
• Strong {direction.lower()} momentum confirmed
• High volatility supporting move
• Trend continuation likely
• {'Consider long positions' if is_bullish else 'Consider short positions'}

Hey Preetam! Strong {direction.lower()} momentum with high volatility! {emoji}"""
        
        priority = "high" if abs(price_change_pct) > 2.0 else "medium"
        
        self.dispatch_alert(
            channel="atr_signals",
            priority=priority,
            title=title,
            body=body,
            tag=f"atr_momentum_{direction.lower()}"
        )
    
    def send_atr_reversal_signal(self, current_atr, atr_mean, wick_size, reversal_direction):
        """Send ATR reversal signal"""
        emoji = "🔄" if reversal_direction == "bullish" else "🔄"
        title = f"{emoji} ATR Reversal Signal - {reversal_direction.upper()}"
        
        body = f"""{emoji} ATR REVERSAL SIGNAL {emoji}

🎯 High volatility rejection detected!

📊 Direction: {reversal_direction.upper()} REVERSAL
📏 Rejection Wick: ${wick_size:.4f}
📊 Current ATR: ${current_atr:.4f}
📊 Average ATR: ${atr_mean:.4f}
📏 Wick/ATR Ratio: {(wick_size/current_atr):.2f}x

🌍 Session: {self.current_session.upper()}

💡 REVERSAL SIGNAL:
• Strong rejection at key level
• High volatility confirming reversal
• Potential trend change setup
• Look for confirmation on next candle

Hey Preetam! Potential {reversal_direction} reversal with high volatility! 🔄"""
        
        self.dispatch_alert(
            channel="atr_signals",
            priority="medium",
            title=title,
            body=body,
            tag=f"atr_reversal_{reversal_direction}"
        )
        
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
                    'close': float(kline[4])
                })
            
            self.df = pd.DataFrame(data)
            self.df.set_index('timestamp', inplace=True)
            print(f"Loaded {len(self.df)} historical bars")
            return True
            
        except Exception as e:
            print(f"Error getting historical data: {e}")
            return False  

        
    
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
        
        # Update ATR-based tolerance
        self.update_atr_tolerance()
        
        # Update session-aware parameters
        self.update_session_parameters()
        
        # Generate ATR-based signals
        self.generate_atr_signals()
    
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
        # Add session and ATR info to alert
        enhanced_text = formatted_text + f"\n\n🌍 Session: {self.current_session.upper()}"
        if self.enable_atr_tolerance:
            atr_value = self.df['atr'].iloc[-1] if 'atr' in self.df.columns and not pd.isna(self.df['atr'].iloc[-1]) else 0
            enhanced_text += f"\n📊 ATR: ${atr_value:.4f}"
        enhanced_text += f"\n🎯 Dynamic Tolerance: ±{self.fib_tolerance:.3f}%"
        
        self.dispatch_alert(
            channel="fibonacci",
            priority=priority,
            title=title,
            body=enhanced_text,
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
        
        # Add session and ATR info to alert
        enhanced_text = formatted_text + f"\n\n🌍 Current Session: {self.current_session.upper()}"
        if self.enable_atr_tolerance:
            atr_value = self.df['atr'].iloc[-1] if 'atr' in self.df.columns and not pd.isna(self.df['atr'].iloc[-1]) else 0
            enhanced_text += f"\n📊 Current ATR: ${atr_value:.4f}"
        
        # Dispatch alert through multi-channel system
        self.dispatch_alert(
            channel="ema_intersection",
            priority=priority,
            title=title,
            body=enhanced_text,
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
• 📊 ATR-based Volatility Signals
• 🎯 Technical Confluence Signals

⚙️ Settings:
• Alert Tolerance: ±{self.fib_tolerance}%
• Cooldown Period: {self.alert_cooldown} seconds
• Max Reconnects: {self.max_reconnect_attempts}

🔔 You will receive alerts for:
✓ Fibonacci level hits
✓ EMA intersections
✓ ATR volatility signals
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
        
        # RSI analysis
        rsi_value = safe_round(latest['rsi'], 1)
        if rsi_value >= 70:
            rsi_status = 'OVERBOUGHT'
        elif rsi_value <= 30:
            rsi_status = 'OVERSOLD'
        else:
            rsi_status = 'NEUTRAL'
        
        
        analysis = {
            'timestamp': current_time,
            'price': safe_round(latest['close']),
            'technical_levels': {
                'ema_9': safe_round(latest['ema_9'], 2),
                'ema_21': safe_round(latest['ema_21'], 2),
                'ema_50': safe_round(latest['ema_50'], 2),
                'fib_595': safe_round(latest['fib_595'], 2),
                'fib_650': safe_round(latest['fib_650'], 2),
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
                    'close': float(kline['c'])
                }
                
                # Add new data to DataFrame
                new_row = pd.DataFrame([new_data])
                new_row.set_index('timestamp', inplace=True)
                self.df = pd.concat([self.df, new_row])
                
                # Keep only last max_bars
                if len(self.df) > self.max_bars:
                    self.df = self.df.tail(self.max_bars)
                
                # Recalculate all indicators
                self.calculate_fibonacci_levels()  # This includes ATR and session updates
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
        
        
        print(f"\nTECHNICAL LEVELS:")
        levels = analysis['technical_levels']
        print(f"  EMA 9: ${levels['ema_9']:.2f}")
        print(f"  EMA 21: ${levels['ema_21']:.2f}")
        print(f"  EMA 50: ${levels['ema_50']:.2f}")
        print(f"  Fibonacci 59.5%: ${levels['fib_595']:.2f}")
        print(f"  Fibonacci 65.0%: ${levels['fib_650']:.2f}")
        print(f"  RSI(9): {levels['rsi']} ({levels['rsi_status']})")
        
        print(f"\nCONFLUENCE SCORE: {analysis['confluence_score']}")
        
        # Calculate distance to Fibonacci levels
        current_price = analysis['price']
        fib_595_distance = abs(current_price - levels['fib_595']) if levels['fib_595'] > 0 else 0
        fib_650_distance = abs(current_price - levels['fib_650']) if levels['fib_650'] > 0 else 0
        
        print(f"\nFIBONACCI DISTANCE:")
        print(f"  Distance to 59.5%: ${fib_595_distance:.4f}")
        print(f"  Distance to 65.0%: ${fib_650_distance:.4f}")
        
        
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
