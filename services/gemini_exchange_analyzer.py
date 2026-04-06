"""
Gemini AI Exchange Rate Analyzer Service
This service uses Google's Gemini AI to analyze exchange rate patterns and trends.
Configuration is loaded from the ai_configs database table.
"""

import os
import json
import logging
import time
from typing import Dict, Optional

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

            # Compare HNB with other banks
            comparisons = {}
            for bank in ['CBSL', 'PB']:
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

            # Add comparison insights
            data_summary += "\nHNB vs OTHER BANKS:\n"
            for bank, comp in comparisons.items():
                better_worse = "BETTER (lower)" if comp['current_diff'] < 0 else "WORSE (higher)"
                diff_pct = abs(comp['current_diff'] / bank_stats[bank]['current'] * 100)
                data_summary += f"- HNB vs {bank}: {better_worse} by {abs(comp['current_diff']):.4f} LKR ({diff_pct:.2f}%)\n"

            # Recent 10-day history for HNB
            hnb_recent = bank_data[user_bank][-10:] if len(bank_data[user_bank]) >= 10 else bank_data[user_bank]
            data_summary += f"\nHNB RECENT HISTORY (Last {len(hnb_recent)} days):\n"
            data_summary += chr(10).join([f"- {item['date']}: {item['rate']:.4f} LKR" for item in hnb_recent])

            # Build transaction context for prompt
            transaction_context = ""
            if transaction_type == "salary_exchange":
                transaction_context = f"""

USER PROFILE: The user receives their monthly/regular SALARY in {currency_from} to their {user_bank} account.
They need to convert {currency_from} to {currency_to} for living expenses.

KEY CONSIDERATIONS FOR SALARY EXCHANGE:
- The user has flexibility in timing (can wait days/weeks after receiving salary)
- They want to maximize {currency_to} received per {currency_from}
- They care about the BUY rate (bank buys {currency_from} from them, gives {currency_to})
- Pattern: Does the rate improve on certain days of the week/month?
- Timing: Should they exchange immediately or wait for better rates?
"""
            elif transaction_type == "investment":
                transaction_context = f"""

USER PROFILE: The user is making an investment or large one-time exchange.
They may have more flexibility in timing and want to optimize the exchange rate.
"""

            # Create AI prompt focused on HNB patterns
            prompt = f"""{data_summary}{transaction_context}

You are a currency exchange specialist analyzing rates across CBSL (Central Bank), PB (People's Bank), 
and HNB (Hatton National Bank). The user banks with HNB.

TASK: Analyze the data and identify patterns that help the user know when it's the BEST time to 
exchange currency at HNB. Consider:
1. How HNB rates compare to CBSL and PB
2. HNB's historical patterns and trends
3. Whether HNB rates are currently favorable vs average
4. Patterns in how HNB rates move relative to other banks
5. For salary exchange: Timing advice based on when rates tend to be most favorable

Provide analysis in JSON format:

{{
    "recommendation": "NOW/WAIT/MONITOR - clear recommendation for exchanging at HNB",
    "hnb_position": "Is HNB currently offering good/average/poor rates compared to history and other banks?",
    "trend": "Brief analysis of HNB rate trends (2-3 sentences)",
    "best_time": "When is the best time to exchange at HNB? Specific timing advice",
    "insights": [
        "Key insight about HNB vs CBSL relationship/pattern",
        "Key insight about HNB vs PB relationship/pattern",
        "Key insight about HNB's current position",
        "Pattern or trend observation specific to HNB"
    ],
    "forecast": "Short-term forecast for HNB rates (next 7-14 days)",
    "confidence": "HIGH/MEDIUM/LOW - confidence level",
    "risk_level": "HIGH/MEDIUM/LOW - risk of exchanging at HNB now",
    "action_items": [
        "Specific action item 1 for HNB user",
        "Specific action item 2 for HNB user"
    ],
    "bank_comparison": "Which bank currently offers best rates? Should user consider switching?"
}}

IMPORTANT:
- Focus analysis on HNB since that's the user's bank
- Be specific about HNB rate patterns you observe
- Compare HNB meaningfully with CBSL and PB
- Give actionable timing advice for HNB exchanges
- Consider historical HNB averages vs current rates
- Return ONLY valid JSON, no markdown or code blocks"""

            # Log data being sent to AI
            logger.info(f"📤 Sending YOUR database data to Gemini AI:")
            logger.info(f"  - User Bank: {user_bank}")
            logger.info(f"  - Data Period: {bank_stats[user_bank]['first_date']} to {bank_stats[user_bank]['last_date']}")
            logger.info(f"  - Banks Analyzed: {', '.join(bank_stats.keys())}")
            logger.info(f"  - Current Rates: HNB={hnb_current:.4f}, " +
                       ', '.join([f"{bank}={bank_stats[bank]['current']:.4f}" for bank in ['CBSL', 'PB'] if bank in bank_stats]))
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
