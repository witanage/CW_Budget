"""
Gemini AI Exchange Rate Analyzer Service
This service uses Google's Gemini AI to analyze exchange rate patterns and trends.
Configuration is loaded from the ai_configs database table.
"""

import os
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from google import genai

logger = logging.getLogger(__name__)


class GeminiExchangeAnalyzer:
    """Service for analyzing exchange rate patterns using Gemini AI."""

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        """
        Initialize the Gemini Exchange Analyzer.

        Args:
            api_key: Gemini API key. If not provided, reads from database or GEMINI_API_KEY env variable.
            model_name: Model name. If not provided, reads from database or uses default.
        """
        # Try to load config from database first
        config = self._load_config_from_db()

        # Priority: constructor parameter > database config > environment variable
        self.api_key = api_key or (config.get('api_key') if config else None) or os.getenv('GEMINI_API_KEY')
        if not self.api_key:
            raise ValueError("Gemini API key not provided. Set it in ai_configs table or GEMINI_API_KEY env variable.")

        # Configure model name
        self.model_name = model_name or (config.get('model_name') if config else None) or 'gemini-3.1-flash-lite-preview'

        # Configure Gemini client
        self.client = genai.Client(api_key=self.api_key)

        logger.info(f"Gemini Exchange Analyzer initialized successfully with model: {self.model_name}")

    def _load_config_from_db(self) -> Optional[Dict]:
        """Load AI configuration from database."""
        try:
            from utils.ai_config_helper import get_ai_config
            config = get_ai_config('exchange_analyzer')
            if config:
                logger.info("Loaded Exchange Analyzer config from database")
                return config
        except Exception as e:
            logger.warning(f"Could not load AI config from database: {e}. Will use environment variables.")
        return None

    def _should_retry_error(self, error: Exception) -> bool:
        """
        Determine if an error is transient and should be retried.

        Args:
            error: The exception that occurred

        Returns:
            True if the error should be retried, False otherwise
        """
        error_str = str(error).lower()

        # Retry on these conditions:
        # - 503 Service Unavailable (high demand)
        # - 429 Too Many Requests (rate limiting)
        # - 500 Internal Server Error (temporary server issues)
        # - Connection errors, timeouts
        retry_indicators = [
            '503',
            '429',
            '500',
            'unavailable',
            'high demand',
            'try again',
            'timeout',
            'connection',
            'temporarily',
            'rate limit'
        ]

        return any(indicator in error_str for indicator in retry_indicators)

    def _call_gemini_with_retry(self, prompt: str, max_retries: int = 3,
                                 initial_delay: float = 2.0, max_delay: float = 30.0):
        """
        Call Gemini API with exponential backoff retry logic.

        Args:
            prompt: The prompt to send to Gemini
            max_retries: Maximum number of retry attempts (default: 3)
            initial_delay: Initial delay in seconds before first retry (default: 2.0)
            max_delay: Maximum delay between retries in seconds (default: 30.0)

        Returns:
            The Gemini API response

        Raises:
            Exception: If all retry attempts fail
        """
        last_error = None
        delay = initial_delay

        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    logger.info(f"Retry attempt {attempt}/{max_retries} for Gemini API call...")

                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt
                )

                # Success!
                if attempt > 0:
                    logger.info(f"✅ Gemini API call succeeded on retry attempt {attempt}")

                return response

            except Exception as e:
                last_error = e
                error_msg = str(e)

                # Check if we should retry
                if not self._should_retry_error(e):
                    logger.error(f"Non-retryable error from Gemini API: {error_msg}")
                    raise

                # Check if we have retries left
                if attempt >= max_retries:
                    logger.error(f"All {max_retries} retry attempts exhausted for Gemini API")
                    raise

                # Log and wait before retry
                logger.warning(
                    f"⚠️ Gemini API error (attempt {attempt + 1}/{max_retries + 1}): {error_msg}"
                )
                logger.info(f"Waiting {delay:.1f}s before retry...")
                time.sleep(delay)

                # Exponential backoff with jitter
                delay = min(delay * 2, max_delay)

        # Should not reach here, but just in case
        raise last_error if last_error else Exception("Unknown error during Gemini API retry")

    def _compute_per_bank_forecast(self, bank_data: dict, forecast_days: int = 14) -> Dict:
        """
        Compute linear-regression forecasts per bank.

        Uses the same approach as the /trends/all endpoint but runs on each
        bank's series independently.  Returns predicted rates, trend direction,
        and 7/14-day projected values with confidence bounds.
        """
        forecasts: Dict[str, dict] = {}

        for bank, data in bank_data.items():
            if not data or len(data) < 7:
                continue

            # Build numeric x (days since first date) and y (rate) arrays
            base_date = datetime.strptime(data[0]['date'], '%Y-%m-%d').date() if isinstance(data[0]['date'], str) else data[0]['date']
            xs: List[float] = []
            ys: List[float] = []
            for item in data:
                d = datetime.strptime(item['date'], '%Y-%m-%d').date() if isinstance(item['date'], str) else item['date']
                xs.append(float((d - base_date).days))
                ys.append(float(item['rate']))

            n = len(xs)
            sum_x = sum(xs)
            sum_y = sum(ys)
            sum_xy = sum(x * y for x, y in zip(xs, ys))
            sum_xx = sum(x * x for x in xs)
            denom = n * sum_xx - sum_x * sum_x

            if denom == 0:
                slope, intercept = 0.0, sum_y / n
            else:
                slope = (n * sum_xy - sum_x * sum_y) / denom
                intercept = (sum_y - slope * sum_x) / n

            # R-squared and residual standard deviation
            y_mean = sum_y / n
            ss_tot = sum((y - y_mean) ** 2 for y in ys)
            ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
            r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0
            res_std = (ss_res / max(n - 2, 1)) ** 0.5

            last_x = xs[-1]
            last_date = datetime.strptime(data[-1]['date'], '%Y-%m-%d').date() if isinstance(data[-1]['date'], str) else data[-1]['date']

            # Compute 7-day and 14-day moving averages from recent data
            recent_7 = ys[-7:] if len(ys) >= 7 else ys
            recent_14 = ys[-14:] if len(ys) >= 14 else ys
            ma_7 = sum(recent_7) / len(recent_7)
            ma_14 = sum(recent_14) / len(recent_14)

            # Momentum: rate of change over last 7 days
            if len(ys) >= 7:
                momentum_7d = ys[-1] - ys[-7]
            else:
                momentum_7d = ys[-1] - ys[0]

            # Generate forecast points
            fc_points = []
            for i in range(1, forecast_days + 1):
                fx = last_x + i
                predicted = slope * fx + intercept
                fc_points.append({
                    'date': (last_date + timedelta(days=i)).isoformat(),
                    'predicted_rate': round(predicted, 4),
                    'upper_bound': round(predicted + 1.96 * res_std, 4),
                    'lower_bound': round(predicted - 1.96 * res_std, 4),
                })

            # Determine trend direction
            if slope > 0.01:
                direction = "RISING"
            elif slope < -0.01:
                direction = "FALLING"
            else:
                direction = "STABLE"

            forecasts[bank] = {
                'direction': direction,
                'slope_per_day': round(slope, 6),
                'r_squared': round(r_squared, 4),
                'residual_std': round(res_std, 4),
                'moving_avg_7d': round(ma_7, 4),
                'moving_avg_14d': round(ma_14, 4),
                'momentum_7d': round(momentum_7d, 4),
                'current_rate': round(ys[-1], 4),
                'predicted_7d': round(slope * (last_x + 7) + intercept, 4),
                'predicted_14d': round(slope * (last_x + 14) + intercept, 4),
                'forecast_points': fc_points,
                'data_points_used': n,
            }

        return forecasts

    def analyze_multi_bank_patterns(self, bank_data: dict, current_rates: dict,
                                     user_bank: str = "HNB",
                                     currency_from: str = "USD",
                                     currency_to: str = "LKR",
                                     transaction_type: str = "salary_exchange") -> Dict:
        """
        Analyze exchange rate patterns across multiple banks (CBSL, PB, HNB).
        Focus on user's bank (HNB) and identifying the best times to exchange.

        Args:
            bank_data: Dictionary with bank names as keys and list of rate data as values
                       e.g., {'CBSL': [{date, rate}, ...], 'PB': [...], 'HNB': [...]}
            current_rates: Dictionary with current rates per bank {'CBSL': rate, 'PB': rate, 'HNB': rate}
            user_bank: User's preferred bank (default: HNB)
            currency_from: Source currency (default: USD)
            currency_to: Target currency (default: LKR)
            transaction_type: Type of transaction - 'salary_exchange', 'investment', 'general' (default: salary_exchange)

        Returns:
            Dictionary with AI analysis including bank comparisons and patterns
        """
        try:
            # Validate data
            if not bank_data or user_bank not in bank_data:
                return {
                    'recommendation': 'Insufficient data',
                    'trend': 'Unknown',
                    'insights': ['Not enough data available for analysis.'],
                    'forecast': 'Unable to forecast',
                    'statistics': {},
                    'error': 'Insufficient data'
                }

            # Calculate statistics for each bank
            bank_stats = {}
            for bank, data in bank_data.items():
                if not data:
                    continue

                rates = [item['rate'] for item in data]
                dates = [item['date'] for item in data]

                bank_stats[bank] = {
                    'current': current_rates.get(bank, rates[-1] if rates else 0),
                    'min': min(rates),
                    'max': max(rates),
                    'avg': sum(rates) / len(rates),
                    'count': len(rates),
                    'first_date': dates[0] if dates else None,
                    'last_date': dates[-1] if dates else None
                }

            # Calculate relative positioning of HNB
            hnb_current = bank_stats[user_bank]['current']
            hnb_avg = bank_stats[user_bank]['avg']

            # Compare HNB with other banks (higher rate = BETTER for the user, more LKR per USD)
            comparisons = {}
            for bank in ['CBSL', 'PB', 'SAMPATH']:
                if bank in bank_stats:
                    comparisons[bank] = {
                        'current_diff': hnb_current - bank_stats[bank]['current'],
                        'avg_diff': hnb_avg - bank_stats[bank]['avg']
                    }

            # Format data summary for AI
            data_summary = f"""
Multi-Bank Exchange Rate Analysis
Currency Pair: {currency_from} to {currency_to}
User's Bank: {user_bank}
Analysis Period: {bank_stats[user_bank]['first_date']} to {bank_stats[user_bank]['last_date']}

CURRENT RATES (Latest):
{chr(10).join([f"- {bank}: {stats['current']:.4f} {currency_to}" for bank, stats in bank_stats.items()])}

BANK STATISTICS COMPARISON:
"""
            for bank, stats in bank_stats.items():
                marker = " ← YOUR BANK" if bank == user_bank else ""
                data_summary += f"""
{bank}{marker}:
  - Current: {stats['current']:.4f} LKR
  - Average: {stats['avg']:.4f} LKR
  - Range: {stats['min']:.4f} - {stats['max']:.4f} LKR
  - Data Points: {stats['count']}
"""

            # Add comparison insights (HIGHER rate = BETTER for user, they get more LKR per USD)
            data_summary += "\nHNB vs OTHER BANKS (Higher rate = BETTER for user):\n"
            for bank, comp in comparisons.items():
                if comp['current_diff'] > 0:
                    label = "BETTER (HNB pays more LKR per USD)"
                elif comp['current_diff'] < 0:
                    label = "WORSE (HNB pays less LKR per USD)"
                else:
                    label = "EQUAL"
                diff_pct = abs(comp['current_diff'] / bank_stats[bank]['current'] * 100)
                data_summary += f"- HNB vs {bank}: {label} by {abs(comp['current_diff']):.4f} LKR ({diff_pct:.2f}%)\n"

            # Recent 10-day history for HNB
            hnb_recent = bank_data[user_bank][-10:] if len(bank_data[user_bank]) >= 10 else bank_data[user_bank]
            data_summary += f"\nHNB RECENT HISTORY (Last {len(hnb_recent)} days):\n"
            data_summary += chr(10).join([f"- {item['date']}: {item['rate']:.4f} LKR" for item in hnb_recent])

            # Add recent history for all banks (not just HNB)
            for other_bank in ['CBSL', 'PB', 'SAMPATH']:
                if other_bank in bank_data and bank_data[other_bank]:
                    other_recent = bank_data[other_bank][-10:] if len(bank_data[other_bank]) >= 10 else bank_data[other_bank]
                    data_summary += f"\n{other_bank} RECENT HISTORY (Last {len(other_recent)} days):\n"
                    data_summary += chr(10).join([f"- {item['date']}: {item['rate']:.4f} LKR" for item in other_recent])

            # Compute statistical forecasts per bank
            bank_forecasts = self._compute_per_bank_forecast(bank_data, forecast_days=14)

            # Add forecast data to the summary
            if bank_forecasts:
                data_summary += "\n\nSTATISTICAL FORECAST (Linear Regression + Moving Averages):\n"
                data_summary += "(These are mathematical projections from historical data — use them to inform your analysis)\n\n"

                for bank, fc in bank_forecasts.items():
                    marker = " ← YOUR BANK" if bank == user_bank else ""
                    data_summary += f"{bank}{marker}:\n"
                    data_summary += f"  - Trend Direction: {fc['direction']} (slope: {fc['slope_per_day']} LKR/day)\n"
                    data_summary += f"  - Current Rate: {fc['current_rate']:.4f} LKR\n"
                    data_summary += f"  - 7-Day Moving Average: {fc['moving_avg_7d']:.4f} LKR\n"
                    data_summary += f"  - 14-Day Moving Average: {fc['moving_avg_14d']:.4f} LKR\n"
                    data_summary += f"  - 7-Day Momentum (change over last 7 days): {fc['momentum_7d']:+.4f} LKR\n"
                    data_summary += f"  - Predicted Rate in 7 days: {fc['predicted_7d']:.4f} LKR\n"
                    data_summary += f"  - Predicted Rate in 14 days: {fc['predicted_14d']:.4f} LKR\n"
                    data_summary += f"  - Model Fit (R²): {fc['r_squared']:.4f} (1.0 = perfect fit)\n"
                    data_summary += f"  - Uncertainty (±): {fc['residual_std']:.4f} LKR\n\n"

                # Add HNB-specific forecast comparison
                if user_bank in bank_forecasts:
                    hnb_fc = bank_forecasts[user_bank]
                    data_summary += f"HNB FORECAST SUMMARY:\n"
                    data_summary += f"  - If trend continues, HNB rate in 7 days: ~{hnb_fc['predicted_7d']:.4f} LKR "
                    data_summary += f"(range: {hnb_fc['predicted_7d'] - 1.96 * hnb_fc['residual_std']:.4f} - {hnb_fc['predicted_7d'] + 1.96 * hnb_fc['residual_std']:.4f})\n"
                    data_summary += f"  - If trend continues, HNB rate in 14 days: ~{hnb_fc['predicted_14d']:.4f} LKR "
                    data_summary += f"(range: {hnb_fc['predicted_14d'] - 1.96 * hnb_fc['residual_std']:.4f} - {hnb_fc['predicted_14d'] + 1.96 * hnb_fc['residual_std']:.4f})\n"

                    # Compare predicted rates across banks
                    predicted_7d_rates = {b: f['predicted_7d'] for b, f in bank_forecasts.items()}
                    best_predicted_bank = max(predicted_7d_rates, key=predicted_7d_rates.get)
                    data_summary += f"\n  - Bank with highest predicted rate in 7 days: {best_predicted_bank} ({predicted_7d_rates[best_predicted_bank]:.4f} LKR)\n"
                    if best_predicted_bank != user_bank:
                        gap = predicted_7d_rates[best_predicted_bank] - predicted_7d_rates[user_bank]
                        data_summary += f"  - HNB projected to be {gap:.4f} LKR LOWER than {best_predicted_bank}\n"
                    else:
                        data_summary += f"  - HNB is projected to have the BEST rate!\n"

            # Build transaction context for prompt
            transaction_context = ""
            if transaction_type == "salary_exchange":
                transaction_context = f"""

USER PROFILE: The user receives their monthly/regular SALARY in {currency_from} to their {user_bank} account.
They need to convert {currency_from} to {currency_to} for daily living expenses in Sri Lanka.

CRITICAL PRINCIPLE — HIGHER RATE = BETTER FOR THE USER:
- The user SELLS {currency_from} and RECEIVES {currency_to}.
- A HIGHER buy rate at {user_bank} means MORE {currency_to} per {currency_from} — this is ALWAYS better.
- Example: 298.50 LKR/USD is BETTER than 297.80 LKR/USD (user gets 0.70 LKR more per dollar).
- The user WANTS {user_bank} to have the HIGHEST rate among all banks.

KEY CONSIDERATIONS FOR SALARY EXCHANGE:
- The user has flexibility in timing (can wait days/weeks after receiving salary)
- They want to maximize {currency_to} received per {currency_from}
- They care about the BUY rate (bank buys {currency_from} from them, gives {currency_to})
- Pattern: Does the rate improve on certain days of the week/month?
- Timing: Should they exchange immediately or wait for better rates?
- Compare: How does {user_bank} stack up against CBSL, People's Bank, and Sampath Bank?
"""
            elif transaction_type == "investment":
                transaction_context = f"""

USER PROFILE: The user is making an investment or large one-time exchange.
They may have more flexibility in timing and want to optimize the exchange rate.

CRITICAL PRINCIPLE — HIGHER RATE = BETTER FOR THE USER:
- A HIGHER buy rate means MORE {currency_to} per {currency_from} — this is ALWAYS better.
- The user wants to exchange when the rate is at its PEAK.
"""
            else:
                transaction_context = f"""

CRITICAL PRINCIPLE — HIGHER RATE = BETTER FOR THE USER:
- The user SELLS {currency_from} and RECEIVES {currency_to}.
- A HIGHER buy rate means MORE {currency_to} per {currency_from} — this is ALWAYS better.
"""

            # Create AI prompt focused on HNB patterns
            prompt = f"""{data_summary}{transaction_context}

You are a currency exchange specialist analyzing {currency_from} to {currency_to} rates in Sri Lanka.
You are comparing rates across these banks:
- CBSL (Central Bank of Sri Lanka — the benchmark/indicative rate)
- PB (People's Bank — state-owned commercial bank)
- HNB (Hatton National Bank — the user's bank, a leading private bank)
- SAMPATH (Sampath Bank — another major private bank)

The user banks with HNB and wants the HIGHEST possible buy rate (more LKR per USD is ALWAYS better).

SRI LANKA CONTEXT:
- Sri Lanka's exchange rate was liberalized after the 2022 economic crisis; rates can vary significantly between banks.
- Commercial banks (HNB, Sampath, PB) set their own rates with a spread over CBSL's indicative rate.
- Private banks like HNB and Sampath often offer more competitive rates than state banks to attract forex.
- Rates can fluctuate within a day; banks typically update rates in the morning.
- Seasonal patterns: rates may shift around import-heavy periods, tourist seasons, and remittance cycles.
- The Central Bank intervenes occasionally to stabilize excessive volatility.

TASK: Analyze the data to help the user maximize LKR received when converting USD at HNB.
A HIGHER rate is ALWAYS better for the user. Consider:
1. Is HNB currently offering the HIGHEST rate among all banks? If not, which bank is better and by how much?
2. HNB's historical patterns — is the current rate above or below its own average?
3. Rate trends — are rates rising, falling, or stable across all banks?
4. Spread analysis — how does HNB's markup over CBSL compare to other banks' markups?
5. Timing advice — are there days of the week/month when HNB rates tend to peak?
6. If another bank consistently offers a higher rate, quantify the difference.

Provide analysis in JSON format:

{{
    "recommendation": "NOW/WAIT/MONITOR — clear recommendation. NOW = HNB rate is high relative to history and peers. WAIT = rates are trending up, better rate expected soon. MONITOR = uncertain, check again in a few days.",
    "hnb_position": "Is HNB currently offering the best/competitive/below-average rates? Compare to other banks with specific numbers.",
    "trend": "Brief analysis of rate trends across all banks (2-3 sentences). Are rates rising or falling? Is HNB improving faster or slower than others?",
    "best_time": "When is the best time to exchange at HNB? Specific timing advice based on observed patterns.",
    "insights": [
        "How HNB's rate compares to the CBSL benchmark (spread analysis)",
        "How HNB compares to Sampath and PB — with specific rate differences",
        "Whether HNB's current rate is above or below its own historical average",
        "Any day-of-week or monthly patterns observed in the data",
        "Which bank consistently offers the highest rate and by how much"
    ],
    "forecast": {{
        "hnb_7_day": "Predicted HNB rate in 7 days with reasoning. State the number clearly.",
        "hnb_14_day": "Predicted HNB rate in 14 days with reasoning. State the number clearly.",
        "direction": "RISING/FALLING/STABLE — overall trend direction for HNB",
        "confidence_in_forecast": "HIGH/MEDIUM/LOW — how reliable is this prediction based on R² and data consistency?",
        "should_wait": "YES/NO — based on the forecast, should the user delay exchanging? Explain why with numbers.",
        "optimal_window": "When in the next 14 days is the rate expected to peak at HNB? Be specific (e.g., 'around April 15-17').",
        "all_banks_7d": {{
            "CBSL": "predicted rate",
            "PB": "predicted rate",
            "HNB": "predicted rate",
            "SAMPATH": "predicted rate"
        }},
        "best_bank_7d": "Which bank is projected to offer the highest rate in 7 days?"
    }},
    "confidence": "HIGH/MEDIUM/LOW — confidence level in this analysis",
    "risk_level": "HIGH/MEDIUM/LOW — risk of waiting vs exchanging now",
    "action_items": [
        "Specific action item 1 — what should the user do RIGHT NOW?",
        "Specific action item 2 — what should the user watch for?"
    ],
    "bank_comparison": "Rank all banks by current rate. State clearly which offers the best rate and the LKR difference per USD compared to HNB. If HNB is not the best, quantify how much the user loses per $1000 by staying with HNB.",
    "rate_advantage": "Calculate: for a $1000 exchange, how much more/less LKR the user gets at HNB vs the best available bank"
}}

IMPORTANT:
- HIGHER rate = BETTER for the user (they get more LKR per USD)
- Always rank banks from highest to lowest rate
- If HNB is NOT the best, clearly state the gap and what the user loses
- If HNB IS the best, celebrate it and advise to exchange now
- Be specific with numbers — don't say 'slightly better', say 'better by 0.45 LKR/USD'
- Give actionable timing advice for HNB exchanges
- Consider Sri Lanka's post-crisis market dynamics
- USE the statistical forecast data provided above — reference the predicted rates, trend direction, and momentum
- If the forecast shows rates RISING, recommend WAIT and estimate when the peak might occur
- If the forecast shows rates FALLING, recommend NOW before rates drop further
- The forecast section must include specific predicted rate numbers from the statistical model
- Return ONLY valid JSON, no markdown or code blocks"""

            # Log data being sent to AI
            logger.info(f"📤 Sending YOUR database data to Gemini AI:")
            logger.info(f"  - User Bank: {user_bank}")
            logger.info(f"  - Data Period: {bank_stats[user_bank]['first_date']} to {bank_stats[user_bank]['last_date']}")
            logger.info(f"  - Banks Analyzed: {', '.join(bank_stats.keys())}")
            logger.info(f"  - Current Rates: HNB={hnb_current:.4f}, " +
                       ', '.join([f"{bank}={bank_stats[bank]['current']:.4f}" for bank in ['CBSL', 'PB', 'SAMPATH'] if bank in bank_stats]))
            logger.info(f"  - Total Data Points: {sum(bank_stats[b]['count'] for b in bank_stats)}")
            logger.info(f"  - Data Summary (first 500 chars): {data_summary[:500]}")

            # Call Gemini AI with retry logic
            logger.info("🤖 Calling Gemini AI model for multi-bank analysis...")
            response = self._call_gemini_with_retry(prompt, max_retries=3, initial_delay=2.0)

            response_text = response.text.strip()
            logger.info(f"Multi-bank analysis response: {response_text[:200]}...")

            # Remove markdown code blocks if present
            if response_text.startswith('```'):
                lines = response_text.split('\n')
                response_text = '\n'.join(lines[1:-1]) if len(lines) > 2 else response_text
                response_text = response_text.replace('```json', '').replace('```', '').strip()

            analysis = json.loads(response_text)

            # Add bank statistics to response
            analysis['statistics'] = {
                'banks': bank_stats,
                'user_bank': user_bank,
                'comparisons': comparisons
            }

            analysis['currency_pair'] = f"{currency_from}/{currency_to}"
            analysis['raw_response'] = response.text

            # Add computed statistical forecasts to response
            if bank_forecasts:
                analysis['statistical_forecast'] = {}
                for bank, fc in bank_forecasts.items():
                    analysis['statistical_forecast'][bank] = {
                        'direction': fc['direction'],
                        'slope_per_day': fc['slope_per_day'],
                        'current_rate': fc['current_rate'],
                        'predicted_7d': fc['predicted_7d'],
                        'predicted_14d': fc['predicted_14d'],
                        'moving_avg_7d': fc['moving_avg_7d'],
                        'moving_avg_14d': fc['moving_avg_14d'],
                        'momentum_7d': fc['momentum_7d'],
                        'r_squared': fc['r_squared'],
                        'confidence_band': fc['residual_std'],
                        'forecast_points': fc['forecast_points'],
                    }

            return analysis

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response as JSON: {e}")
            return {
                'recommendation': 'Analysis failed',
                'trend': 'Unable to analyze',
                'insights': ['AI analysis encountered an error. Please try again.'],
                'forecast': 'Not available',
                'statistics': {},
                'error': f'JSON parsing error: {str(e)}',
                'raw_response': response_text if 'response_text' in locals() else ''
            }
        except Exception as e:
            logger.error(f"Error analyzing multi-bank rates: {e}", exc_info=True)
            return {
                'recommendation': 'Analysis failed',
                'trend': 'Unable to analyze',
                'insights': [f'Error: {str(e)}'],
                'forecast': 'Not available',
                'statistics': {},
                'error': str(e)
            }


def get_gemini_exchange_analyzer() -> Optional[GeminiExchangeAnalyzer]:
    """
    Get a configured Gemini Exchange Analyzer instance.

    Returns:
        GeminiExchangeAnalyzer instance or None if API key is not configured.
    """
    try:
        return GeminiExchangeAnalyzer()
    except ValueError as e:
        logger.warning(f"Gemini Exchange Analyzer not available: {e}")
        return None
