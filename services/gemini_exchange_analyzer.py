"""
Gemini AI Exchange Rate Analyzer Service
This service uses Google's Gemini AI to analyze exchange rate patterns and trends.
Configuration is loaded from the ai_configs database table.
"""

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
            api_key: Gemini API key. If not provided, reads from database (ai_provider_config table).
            model_name: Model name. If not provided, reads from database or uses default.
        """
        # Try to load config from database first
        config = self._load_config_from_db()

        # Priority: constructor parameter > database config
        self.api_key = api_key or (config.get('api_key') if config else None)
        if not self.api_key:
            raise ValueError("Gemini API key not provided. Set it in the ai_provider_config table via Admin → Settings.")

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

            # Compare user's bank with other banks (higher rate = BETTER for the user, more LKR per USD)
            comparisons = {}
            other_banks = [b for b in bank_stats if b != user_bank]
            for bank in other_banks:
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
            data_summary += f"\n{user_bank} vs OTHER BANKS (Higher rate = BETTER for user):\n"
            for bank, comp in comparisons.items():
                if comp['current_diff'] > 0:
                    label = f"BETTER ({user_bank} pays more LKR per USD)"
                elif comp['current_diff'] < 0:
                    label = f"WORSE ({user_bank} pays less LKR per USD)"
                else:
                    label = "EQUAL"
                diff_pct = abs(comp['current_diff'] / bank_stats[bank]['current'] * 100)
                data_summary += f"- {user_bank} vs {bank}: {label} by {abs(comp['current_diff']):.4f} LKR ({diff_pct:.2f}%)\n"

            # Recent 10-day history for user's bank
            user_recent = bank_data[user_bank][-10:] if len(bank_data[user_bank]) >= 10 else bank_data[user_bank]
            data_summary += f"\n{user_bank} RECENT HISTORY (Last {len(user_recent)} days):\n"
            data_summary += chr(10).join([f"- {item['date']}: {item['rate']:.4f} LKR" for item in user_recent])

            # Add recent history for all other banks
            for other_bank in other_banks:
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

                # Add user bank-specific forecast comparison
                if user_bank in bank_forecasts:
                    ub_fc = bank_forecasts[user_bank]
                    data_summary += f"{user_bank} FORECAST SUMMARY:\n"
                    data_summary += f"  - If trend continues, {user_bank} rate in 7 days: ~{ub_fc['predicted_7d']:.4f} LKR "
                    data_summary += f"(range: {ub_fc['predicted_7d'] - 1.96 * ub_fc['residual_std']:.4f} - {ub_fc['predicted_7d'] + 1.96 * ub_fc['residual_std']:.4f})\n"
                    data_summary += f"  - If trend continues, {user_bank} rate in 14 days: ~{ub_fc['predicted_14d']:.4f} LKR "
                    data_summary += f"(range: {ub_fc['predicted_14d'] - 1.96 * ub_fc['residual_std']:.4f} - {ub_fc['predicted_14d'] + 1.96 * ub_fc['residual_std']:.4f})\n"

                    # Compare predicted rates across banks
                    predicted_7d_rates = {b: f['predicted_7d'] for b, f in bank_forecasts.items()}
                    best_predicted_bank = max(predicted_7d_rates, key=predicted_7d_rates.get)
                    data_summary += f"\n  - Bank with highest predicted rate in 7 days: {best_predicted_bank} ({predicted_7d_rates[best_predicted_bank]:.4f} LKR)\n"
                    if best_predicted_bank != user_bank:
                        gap = predicted_7d_rates[best_predicted_bank] - predicted_7d_rates[user_bank]
                        data_summary += f"  - {user_bank} projected to be {gap:.4f} LKR LOWER than {best_predicted_bank}\n"
                    else:
                        data_summary += f"  - {user_bank} is projected to have the BEST rate!\n"

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

            # Create AI prompt focused on user's bank patterns
            bank_descriptions = {
                'CBSL': 'CBSL (Central Bank of Sri Lanka — the benchmark/indicative rate)',
                'PB': 'PB (People\'s Bank — state-owned commercial bank)',
                'HNB': 'HNB (Hatton National Bank — a leading private bank)',
                'SAMPATH': 'SAMPATH (Sampath Bank — a major private bank)',
            }
            bank_list = '\n'.join(
                f"- {bank_descriptions.get(b, b)}{' ← USER\'S BANK' if b == user_bank else ''}"
                for b in bank_stats
            )

            prompt = f"""{data_summary}{transaction_context}

You are a currency exchange specialist analyzing {currency_from} to {currency_to} rates in Sri Lanka.
You are comparing rates across these banks:
{bank_list}

The user banks with {user_bank} and wants the HIGHEST possible buy rate (more LKR per USD is ALWAYS better).

SRI LANKA CONTEXT:
- Sri Lanka's exchange rate was liberalized after the 2022 economic crisis; rates can vary significantly between banks.
- Commercial banks (HNB, Sampath, PB) set their own rates with a spread over CBSL's indicative rate.
- Private banks like HNB and Sampath often offer more competitive rates than state banks to attract forex.
- Rates can fluctuate within a day; banks typically update rates in the morning.
- Seasonal patterns: rates may shift around import-heavy periods, tourist seasons, and remittance cycles.
- The Central Bank intervenes occasionally to stabilize excessive volatility.

GLOBAL FACTORS AFFECTING USD/LKR:
- US Federal Reserve monetary policy: rate hikes strengthen USD (LKR weakens → higher rate numbers), rate cuts weaken USD (LKR strengthens → lower rate numbers).
- US Dollar Index (DXY): a rising DXY generally pushes USD/LKR higher; a falling DXY benefits LKR.
- Global oil & commodity prices: Sri Lanka is a net importer — rising oil prices increase USD demand, pressuring LKR downward.
- IMF program: Sri Lanka's ongoing IMF Extended Fund Facility affects investor confidence and forex reserves; compliance milestones can strengthen LKR.
- Sri Lanka's forex reserves & trade balance: higher reserves and improving exports support a stronger LKR.
- Global risk sentiment: risk-off environments (geopolitical tensions, market crashes) cause capital flight from emerging markets, weakening LKR.
- Regional currency movements: LKR often moves in tandem with INR and other South Asian currencies.
- Remittance flows: worker remittances from the Middle East, Europe, and East Asia are a major forex source; seasonal peaks (holidays, year-end) boost LKR.
- Sovereign credit rating changes and foreign debt restructuring progress directly impact LKR stability.
- Global inflation trends: persistent US inflation delays Fed rate cuts, keeping USD strong against LKR.

Based on these global dynamics, factor in whether the current USD/LKR trend is driven by local bank competition or broader macroeconomic forces.

TASK: Analyze the data to help the user maximize LKR received when converting USD at {user_bank}.
A HIGHER rate is ALWAYS better for the user. Consider:
1. Is {user_bank} currently offering the HIGHEST rate among all banks? If not, which bank is better and by how much?
2. {user_bank}'s historical patterns — is the current rate above or below its own average?
3. Rate trends — are rates rising, falling, or stable across all banks?
4. Spread analysis — how does {user_bank}'s markup over CBSL compare to other banks' markups?
5. Timing advice — are there days of the week/month when {user_bank} rates tend to peak?
6. If another bank consistently offers a higher rate, quantify the difference.

Provide analysis in JSON format:

{{
    "recommendation": "NOW/WAIT/MONITOR — clear recommendation factoring BOTH local bank data AND global macro conditions. NOW = {user_bank} rate is high relative to history/peers AND global factors favor exchanging now (e.g., USD expected to weaken). WAIT = rates are trending up OR global factors suggest USD will strengthen further soon. MONITOR = uncertain due to conflicting local vs global signals.",
    "hnb_position": "Is {user_bank} currently offering the best/competitive/below-average rates? Compare to other banks with specific numbers.",
    "trend": "Brief analysis of rate trends across all banks (2-3 sentences). Are rates rising or falling? Is {user_bank} improving faster or slower than others?",
    "best_time": "When is the best time to exchange at {user_bank}? Specific timing advice based on observed patterns.",
    "insights": [
        "How {user_bank}'s rate compares to the CBSL benchmark (spread analysis)",
        "How {user_bank} compares to other banks — with specific rate differences",
        "Whether {user_bank}'s current rate is above or below its own historical average",
        "Any day-of-week or monthly patterns observed in the data",
        "Which bank consistently offers the highest rate and by how much"
    ],
    "forecast": {{
        "hnb_7_day": "Predicted {user_bank} rate in 7 days with reasoning. State the number clearly.",
        "hnb_14_day": "Predicted {user_bank} rate in 14 days with reasoning. State the number clearly.",
        "direction": "RISING/FALLING/STABLE — overall trend direction for {user_bank}",
        "confidence_in_forecast": "HIGH/MEDIUM/LOW — how reliable is this prediction based on R², data consistency, AND global macro stability? Downgrade if major global events (Fed meeting, IMF review, geopolitical risk) could disrupt the trend.",
        "should_wait": "YES/NO — based on BOTH the statistical forecast AND global factors, should the user delay exchanging? Consider: if Fed signals rate cuts, USD may weaken and rates could drop — exchange NOW. If USD is strengthening globally, rates may rise — WAIT. Explain with numbers.",
        "optimal_window": "When in the next 14 days is the rate expected to peak at HNB? Be specific (e.g., 'around April 15-17').",
        "all_banks_7d": {{
            "CBSL": "predicted rate",
            "PB": "predicted rate",
            "HNB": "predicted rate",
            "SAMPATH": "predicted rate"
        }},
        "best_bank_7d": "Which bank is projected to offer the highest rate in 7 days?"
    }},
    "confidence": "HIGH/MEDIUM/LOW — confidence level considering both local data quality (R², data points) AND global macro certainty. Downgrade if global factors are highly uncertain (e.g., pending Fed decision, geopolitical tensions).",
    "risk_level": "HIGH/MEDIUM/LOW — risk of waiting vs exchanging now, factoring global risks (e.g., HIGH if global events could cause sudden LKR depreciation; LOW if macro environment is stable and rates are range-bound).",
    "action_items": [
        "Specific action item 1 — what should the user do RIGHT NOW?",
        "Specific action item 2 — what should the user watch for?"
    ],
    "bank_comparison": "Rank all banks by current rate. State clearly which offers the best rate and the LKR difference per USD compared to {user_bank}. If {user_bank} is not the best, quantify how much the user loses per $1000 by staying with {user_bank}.",
    "rate_advantage": "Calculate: for a $1000 exchange, how much more/less LKR the user gets at {user_bank} vs the best available bank",
    "global_insights": {{
        "usd_strength": "Is the USD currently strengthening or weakening globally? How does this affect USD/LKR?",
        "fed_policy_impact": "How is current/expected US Federal Reserve policy influencing USD/LKR rates?",
        "commodity_pressure": "Are global oil/commodity prices putting pressure on LKR through Sri Lanka's import bill?",
        "imf_program": "Any recent IMF-related developments affecting LKR stability and investor confidence?",
        "regional_context": "How is LKR performing relative to other South Asian currencies (INR, etc.)?",
        "risk_sentiment": "Is the current global risk environment (risk-on/risk-off) favorable or unfavorable for LKR?",
        "key_global_driver": "What is the single most important global factor driving USD/LKR right now?",
        "outlook": "Based on global factors, is LKR likely to strengthen or weaken in the near term? 1-2 sentences."
    }}
}}

IMPORTANT:
- HIGHER rate = BETTER for the user (they get more LKR per USD)
- Always rank banks from highest to lowest rate
- If {user_bank} is NOT the best, clearly state the gap and what the user loses
- If {user_bank} IS the best, celebrate it and advise to exchange now
- Be specific with numbers — don't say 'slightly better', say 'better by 0.45 LKR/USD'
- Give actionable timing advice for {user_bank} exchanges
- Consider Sri Lanka's post-crisis market dynamics
- USE the statistical forecast data provided above — reference the predicted rates, trend direction, and momentum
- If the forecast shows rates RISING, recommend WAIT and estimate when the peak might occur
- If the forecast shows rates FALLING, recommend NOW before rates drop further
- The forecast section must include specific predicted rate numbers from the statistical model
- In global_insights, analyze how global macroeconomic forces (Fed policy, DXY, oil prices, IMF program, risk sentiment) are currently affecting or likely to affect the USD/LKR rate
- Connect global factors to actionable advice — e.g., if Fed is expected to cut rates, USD may weaken and LKR rates could drop, so exchange sooner
- The recommendation, confidence, and risk_level MUST reflect global factors — not just local bank data. If local data says WAIT but global macro says exchange now (e.g., USD about to weaken), the recommendation should weigh both signals
- If global uncertainty is high (pending Fed decision, geopolitical tensions, IMF review), downgrade confidence and raise risk_level accordingly
- Return ONLY valid JSON, no markdown or code blocks"""

            # Log data being sent to AI
            logger.info(f"📤 Sending YOUR database data to Gemini AI:")
            logger.info(f"  - User Bank: {user_bank}")
            logger.info(f"  - Data Period: {bank_stats[user_bank]['first_date']} to {bank_stats[user_bank]['last_date']}")
            logger.info(f"  - Banks Analyzed: {', '.join(bank_stats.keys())}")
            logger.info(f"  - Current Rates: {user_bank}={hnb_current:.4f}, " +
                       ', '.join([f"{bank}={bank_stats[bank]['current']:.4f}" for bank in bank_stats if bank != user_bank]))
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
