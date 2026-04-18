"""
Gemini AI Bill Scanner Service
This service uses Google's Gemini Flash 3 API to extract information from bill images and PDFs.
Configuration is loaded from the ai_configs database table.
"""

import json
import logging
import time
from typing import Dict, Optional, Union, List
from google import genai
from google.genai.types import Part
from PIL import Image
import io

logger = logging.getLogger(__name__)


class GeminiBillScanner:
    """Service for scanning bills using Gemini AI."""

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        """
        Initialize the Gemini Bill Scanner.

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

        logger.info(f"Gemini Bill Scanner initialized successfully with model: {self.model_name}")

    def _load_config_from_db(self) -> Optional[Dict]:
        """Load AI configuration from database."""
        try:
            from utils.ai_config_helper import get_ai_config
            config = get_ai_config('bill_scanner')
            if config:
                logger.info("Loaded Bill Scanner config from database")
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

    def _call_gemini_with_retry(self, content_parts: List, max_retries: int = 3,
                                 initial_delay: float = 2.0, max_delay: float = 30.0):
        """
        Call Gemini API with exponential backoff retry logic.

        Args:
            content_parts: The content to send to Gemini
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
                    contents=content_parts
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

    def _are_items_similar(self, name1: str, name2: str) -> bool:
        """
        Check if two item names are similar enough to be considered duplicates.
        Handles OCR errors where some words might be missing.

        Args:
            name1: First item name
            name2: Second item name

        Returns:
            True if items are likely duplicates, False otherwise
        """
        # Normalize names
        n1 = name1.lower().strip()
        n2 = name2.lower().strip()

        # Exact match
        if n1 == n2:
            return True

        # One name is substring of another (e.g., "Cola 330ml" vs "Coca Cola 330ml")
        if n1 in n2 or n2 in n1:
            return True

        # Word-based similarity for OCR errors
        words1 = set(n1.split())
        words2 = set(n2.split())

        # If either name has only 1-2 words, require higher overlap
        min_words = min(len(words1), len(words2))

        if min_words <= 2:
            # For short names, require all words to overlap
            overlap = len(words1.intersection(words2))
            return overlap >= min_words
        else:
            # For longer names, require 70% word overlap
            overlap = len(words1.intersection(words2))
            similarity = overlap / max(len(words1), len(words2))
            return similarity >= 0.7

    def scan_bill(self, image_data: Union[bytes, List[bytes]]) -> Dict[str, Optional[str]]:
        """
        Scan a bill image or PDF and extract shop name, amount, discounts, and line items.
        Supports both single and multiple images for long receipts.

        Args:
            image_data: Raw file bytes (JPEG, PNG, PDF, etc.) or list of bytes for multiple images

        Returns:
            Dictionary with 'shop_name', 'amount', 'subtotal', 'discounts', and 'items' keys.
            - shop_name: Name of the store
            - amount: Final total after discounts
            - subtotal: Subtotal before discounts
            - discounts: List of discount objects with 'description' and 'amount'
            - items: List of purchased items with 'name', 'quantity', and 'price'
        """
        try:
            # Normalize to list for consistent processing
            images_list = image_data if isinstance(image_data, list) else [image_data]

            # Validate we have at least one image
            if not images_list:
                raise ValueError("No image data provided")

            # Check if we have multiple images
            is_multiple = len(images_list) > 1

            # Create the prompt for bill extraction
            prompt = """
You are a bill/receipt analyzer. Extract the following information from this bill/receipt:

1. Shop/Store Name: The name of the business or store
2. Subtotal: The amount BEFORE summary discounts are applied (if shown on receipt)
3. Discounts: Extract ONLY the summary/total discount lines (usually near the bottom of the receipt)
4. Total Amount: The EXACT final total shown on the receipt (this is the most important field)
5. Line Items: Extract each item purchased with its details

"""
            if is_multiple:
                prompt += f"\nNote: You will see {len(images_list)} images of the SAME receipt. Analyze all images together to extract complete information.\n"

            prompt += """
Respond in this exact JSON format:
{
    "shop_name": "extracted shop name or 'Unknown Store'",
    "subtotal": "numeric subtotal or '0'",
    "discounts": [
        {
            "description": "exact discount label from bill",
            "amount": "total discount amount"
        }
    ],
    "amount": "final total numeric amount or '0'",
    "items": [
        {
            "name": "item name",
            "code": "item code/SKU (optional, only if visible on receipt)",
            "quantity": "quantity or '1'",
            "price": "unit price (before any item discount)",
            "discount": "item discount amount (optional, only if this specific item has a discount)"
        }
    ]
}

CRITICAL RULES:
1. AMOUNT FIELD (MOST IMPORTANT):
   - The 'amount' field MUST be the EXACT final total shown on the receipt
   - Look for labels like: "TOTAL", "AMOUNT PAYABLE", "TOTAL AMOUNT", "AMOUNT TO PAY", "NET TOTAL", "GRAND TOTAL", "BALANCE", "TO PAY"
   - Copy this number precisely - do not calculate or modify it
   - This is what the customer actually paid

2. SUBTOTAL FIELD (IMPORTANT - Avoid Double-Deduction):
   - The subtotal should be the amount BEFORE summary discounts are applied
   - If the receipt shows "Subtotal" AFTER item discounts but BEFORE total/summary discounts, use that value
   - If the receipt's subtotal already includes all discounts, set subtotal to '0' or omit it
   - DO NOT use a subtotal that would cause discounts to be deducted twice
   - Example: If receipt shows "Total Items: 1000", then "Your Savings: -100", then "Amount to Pay: 900"
     → subtotal should be "1000", not "900"

3. DISCOUNTS ARRAY (summary only):
   - Extract ONLY the final summary discount line(s) that appear at the BOTTOM of the receipt near the total
   - Look for discount labels like: "YOUR DISCOUNT", "TOTAL DISCOUNT", "TOTAL SAVINGS", "MEMBER DISCOUNT", "LOYALTY SAVINGS"
   - DO NOT extract individual "DISCOUNT" lines that appear throughout the receipt next to items
   - IGNORE any discount that appears in the items section - those go in the items array
   - Only include discounts from the summary/totals section (usually after subtotal, before final total)
   - Copy the exact label text as shown on the bill
   - If no summary discount line exists at the bottom, return empty array []
   - Typically there is only ONE summary discount line (e.g., "YOUR DISCOUNT: 1120.00")

4. ITEMS ARRAY (per-item discounts and codes):
   - Extract EACH UNIQUE item from the receipt ONLY ONCE - do not duplicate items
   - If item codes/SKUs are visible on the receipt, include them in the "code" field
   - IMPORTANT: Items with the SAME name but DIFFERENT codes are DIFFERENT items (e.g., "Milk" code "123" vs "Milk" code "456")
   - If the same item (same name AND same code) appears multiple times, combine them into a single entry with the total quantity
   - For each item, if there's a discount shown next to or below that specific item, include it in the "discount" field
   - The "price" should be the original price PER UNIT before discount
   - The "discount" field is the discount amount PER UNIT (optional - only include if that item has a discount)
   - Extract per-item discount amounts accurately

5. AVOID DUPLICATES (but respect item codes):
   - Read through the entire receipt carefully before extracting items
   - If you see the same product name AND same code multiple times, extract it only once with combined quantity
   - If you see the same product name but DIFFERENT codes, extract them as SEPARATE items
   - If no codes are visible, deduplicate by name only
   - Do not extract the same information twice
   - Do not extract the same information twice

EXAMPLE:
If a receipt shows:
- Many items with individual discounts throughout
- At bottom: "Subtotal: 1000", then "YOUR DISCOUNT: 100", then "Total: 900"
- The discounts array should contain ONLY [{"description": "YOUR DISCOUNT", "amount": "100"}]
- The subtotal should be "1000" and amount should be "900"

IMPORTANT: The 'amount' field should ALWAYS be the EXACT final total shown on the receipt - never calculate it yourself.
"""

            # Prepare content parts
            content_parts = [prompt]

            for idx, img_data in enumerate(images_list):
                # Detect if it's a PDF
                is_pdf = img_data[:4] == b'%PDF'

                if is_pdf:
                    logger.info(f"Processing PDF bill (image {idx + 1}/{len(images_list)})")
                    file_part = Part.from_bytes(data=img_data, mime_type="application/pdf")
                    content_parts.append(file_part)
                else:
                    logger.info(f"Processing image bill (image {idx + 1}/{len(images_list)})")
                    image = Image.open(io.BytesIO(img_data))
                    content_parts.append(image)

            # Send all images in one request to Gemini with retry logic
            logger.info(f"Sending {len(images_list)} image(s) to Gemini for analysis")
            response = self._call_gemini_with_retry(content_parts, max_retries=3, initial_delay=2.0)

            # Extract text from response
            response_text = response.text.strip()
            logger.info(f"Gemini response: {response_text}")

            # Remove markdown code blocks if present
            if response_text.startswith('```'):
                lines = response_text.split('\n')
                response_text = '\n'.join(lines[1:-1]) if len(lines) > 2 else response_text
                response_text = response_text.replace('```json', '').replace('```', '').strip()

            result = json.loads(response_text)
            result['raw_response'] = response.text

            # Validate and clean
            shop_name = result.get('shop_name', 'Unknown Store').strip()
            amount = result.get('amount', '0').strip()
            subtotal = result.get('subtotal', '0').strip()
            items = result.get('items', [])
            discounts = result.get('discounts', [])

            # Filter out generic "DISCOUNT" entries if there are more specific discount labels
            if isinstance(discounts, list) and len(discounts) > 1:
                specific_discounts = [d for d in discounts if d.get('description', '').strip().upper() not in ['DISCOUNT', 'DISCOUNT:']]
                # If we found specific discount labels, use only those
                if specific_discounts:
                    discounts = specific_discounts
                    logger.info(f"Filtered out generic 'DISCOUNT' entries, keeping {len(discounts)} specific discount(s)")

            # Deduplicate items by name with fuzzy matching to handle OCR errors
            # But respect item codes - items with different codes are different items
            # Only apply deduplication when scanning multiple images (for single images, trust Gemini's extraction)
            if is_multiple and isinstance(items, list) and len(items) > 0:
                deduplicated_items = []

                for item in items:
                    item_name = item.get('name', '').strip()
                    item_code = item.get('code', '').strip()
                    if not item_name:
                        continue

                    # Check if this item is similar to any existing item
                    is_duplicate = False
                    for idx, existing_item in enumerate(deduplicated_items):
                        existing_name = existing_item.get('name', '').strip()
                        existing_code = existing_item.get('code', '').strip()

                        # If both have codes, they must match for it to be a duplicate
                        if item_code and existing_code:
                            if item_code == existing_code and self._are_items_similar(item_name, existing_name):
                                is_duplicate = True
                                # Keep the longer/more complete name
                                if len(item_name) > len(existing_name):
                                    deduplicated_items[idx] = item
                                    logger.info(f"Replaced '{existing_name}' (code: {existing_code}) with more complete name '{item_name}'")
                                break
                        # If only one has a code, not a duplicate (different items)
                        elif item_code or existing_code:
                            continue
                        # If neither has a code, check name similarity only
                        else:
                            if self._are_items_similar(item_name, existing_name):
                                is_duplicate = True
                                # Keep the longer/more complete name
                                if len(item_name) > len(existing_name):
                                    deduplicated_items[idx] = item
                                    logger.info(f"Replaced '{existing_name}' with more complete name '{item_name}'")
                                break

                    if not is_duplicate:
                        deduplicated_items.append(item)

                if len(deduplicated_items) < len(items):
                    logger.info(f"Removed {len(items) - len(deduplicated_items)} duplicate/similar item(s) from multi-image scan")
                    items = deduplicated_items

            cleaned_amount = ''.join(c for c in amount if c.isdigit() or c == '.')
            cleaned_subtotal = ''.join(c for c in subtotal if c.isdigit() or c == '.')

            return {
                'shop_name': shop_name if shop_name else 'Unknown Store',
                'amount': cleaned_amount if cleaned_amount else '0',
                'subtotal': cleaned_subtotal if cleaned_subtotal else '0',
                'discounts': discounts if isinstance(discounts, list) else [],
                'items': items if isinstance(items, list) else [],
                'raw_response': result.get('raw_response', '')
            }

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini response as JSON: {e}")
            return {
                'shop_name': 'Unknown Store',
                'amount': '0',
                'subtotal': '0',
                'discounts': [],
                'items': [],
                'error': f'Failed to parse response: {str(e)}'
            }
        except Exception as e:
            logger.error(f"Error scanning bill with Gemini: {e}", exc_info=True)
            return {
                'shop_name': 'Unknown Store',
                'amount': '0',
                'subtotal': '0',
                'discounts': [],
                'items': [],
                'error': str(e)
            }


def get_gemini_bill_scanner() -> Optional[GeminiBillScanner]:
    """
    Get a configured Gemini Bill Scanner instance.

    Returns:
        GeminiBillScanner instance or None if API key is not configured.
    """
    try:
        return GeminiBillScanner()
    except ValueError as e:
        logger.warning(f"Gemini Bill Scanner not available: {e}")
        return None
